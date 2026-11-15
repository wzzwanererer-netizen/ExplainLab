"""M3 / ZIP-01 检索装配：按方言的全文索引 + 通用向量存储 + 索引同步 + 混合检索。

FullTextIndex / VectorStore 端口的数据库适配实现：
- 全文：SQLite 用 FTS5（trigram），PostgreSQL 用原生 tsvector / tsquery（GIN）。
  方言差异封装在本适配层（SQLiteFullTextIndex / PostgresFullTextIndex）与 app/db/fts.py，
  编排逻辑（RetrievalIndexer / sync_index / build_retrieval_service）不含任何方言 SQL。
- 向量：JSON 存储 + Python 余弦，双方言通用（不依赖 pgvector 扩展）。

FTS 日常同步由迁移触发器完成，这里的 upsert/remove 主要用于 backfill 与兜底；
向量同步由 RetrievalIndexer 在条目变更后调用（embed 为异步，故在路由层 await）。
Core 不绑定数据库。
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import KnowledgeVectorORM
from app.services.knowledge import SQLAlchemyKnowledgeRepository
from knowledge_core.domain.entities import KnowledgeItem, utcnow
from knowledge_core.model_adapter import ModelAdapterError
from knowledge_core.ports import Embedder, FullTextIndex, VectorStore
from knowledge_core.retrieval.hybrid import HybridRetrievalService

logger = logging.getLogger(__name__)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class SQLiteFullTextIndex:
    """SQLite FTS5（trigram）全文索引。短查询（<3 字符）回退 LIKE。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _rowid(self, item_id: UUID) -> int | None:
        return self._session.execute(
            text("SELECT rowid FROM knowledge_item WHERE id = :id"),
            {"id": str(item_id)},
        ).scalar_one_or_none()

    def upsert(self, item_id: UUID, title: str, content: str) -> None:
        rowid = self._rowid(item_id)
        if rowid is None:
            return
        self._session.execute(
            text("DELETE FROM knowledge_fts WHERE rowid = :r"), {"r": rowid}
        )
        self._session.execute(
            text(
                "INSERT INTO knowledge_fts(rowid, item_id, title, content) "
                "VALUES (:r, :id, :t, :c)"
            ),
            {"r": rowid, "id": str(item_id), "t": title, "c": content},
        )

    def remove(self, item_id: UUID) -> None:
        rowid = self._rowid(item_id)
        if rowid is not None:
            self._session.execute(
                text("DELETE FROM knowledge_fts WHERE rowid = :r"), {"r": rowid}
            )

    def search(self, query: str, limit: int) -> list[tuple[UUID, float]]:
        q = query.strip()
        if not q or limit <= 0:
            return []
        if len(q) >= 3:
            match = '"' + q.replace('"', '""') + '"'
            rows = self._session.execute(
                text(
                    "SELECT item_id, bm25(knowledge_fts) AS r FROM knowledge_fts "
                    "WHERE knowledge_fts MATCH :m ORDER BY r ASC LIMIT :l"
                ),
                {"m": match, "l": limit},
            ).all()
            return [(UUID(r[0]), float(r[1])) for r in rows]
        like = f"%{q}%"
        rows = self._session.execute(
            text(
                "SELECT id FROM knowledge_item "
                "WHERE title LIKE :pat OR content LIKE :pat LIMIT :lim"
            ),
            {"pat": like, "lim": limit},
        ).all()
        return [(UUID(r[0]), 0.0) for r in rows]


class PostgresFullTextIndex:
    """PostgreSQL 原生全文索引（tsvector / tsquery + GIN）。

    不使用 FTS5 / MATCH / bm25 / rowid。tsv 由迁移触发器维护；upsert/remove 用于
    backfill 与兜底。ts_rank 越大越相关，故返回 -ts_rank（越小越相关，与 SQLite
    bm25 契约一致），并按相关性降序返回。原生 'simple' 分词对无空格中文不成词，
    此类查询无 tsvector 命中时回退 ILIKE 子串匹配（真实匹配，不造假）。
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(self, item_id: UUID, title: str, content: str) -> None:
        exists = self._session.execute(
            text("SELECT 1 FROM knowledge_item WHERE id = :id"), {"id": str(item_id)}
        ).first()
        if exists is None:
            return
        self._session.execute(
            text(
                "INSERT INTO knowledge_fts(item_id, tsv) "
                "VALUES (:id, to_tsvector('simple', :t || ' ' || :c)) "
                "ON CONFLICT (item_id) DO UPDATE SET tsv = EXCLUDED.tsv"
            ),
            {"id": str(item_id), "t": title, "c": content},
        )

    def remove(self, item_id: UUID) -> None:
        self._session.execute(
            text("DELETE FROM knowledge_fts WHERE item_id = :id"), {"id": str(item_id)}
        )

    def search(self, query: str, limit: int) -> list[tuple[UUID, float]]:
        q = query.strip()
        if not q or limit <= 0:
            return []
        rows = self._session.execute(
            text(
                "SELECT item_id, ts_rank(tsv, q) AS r "
                "FROM knowledge_fts, plainto_tsquery('simple', :query) AS q "
                "WHERE tsv @@ q ORDER BY r DESC LIMIT :lim"
            ),
            {"query": q, "lim": limit},
        ).all()
        if rows:
            return [(UUID(r[0]), -float(r[1])) for r in rows]
        # 原生 tsvector 对无空格中文等不成词查询无命中：回退 ILIKE 子串匹配。
        # JOIN knowledge_fts 限定「已索引」集合，使 remove() 后回退同样不再命中，
        # 与 tsvector 主路径的成员资格语义一致（索引是可搜索集合的唯一来源）。
        like = f"%{q}%"
        rows = self._session.execute(
            text(
                "SELECT k.id FROM knowledge_item k "
                "JOIN knowledge_fts f ON f.item_id = k.id "
                "WHERE k.title ILIKE :pat OR k.content ILIKE :pat LIMIT :lim"
            ),
            {"pat": like, "lim": limit},
        ).all()
        return [(UUID(r[0]), 0.0) for r in rows]


class JsonVectorStore:
    """向量表（JSON 文本）+ Python 余弦。SQLite 与 PostgreSQL 通用，不依赖 pgvector。

    本地规模足够；如需数据库内向量检索可未来引入 pgvector，但非本轮必需依赖。
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(self, item_id: UUID, vector: list[float], model: str) -> None:
        row = self._session.get(KnowledgeVectorORM, str(item_id))
        if row is None:
            row = KnowledgeVectorORM(item_id=str(item_id))
            self._session.add(row)
        row.model = model
        row.dim = len(vector)
        row.vector = json.dumps(vector)
        row.updated_at = utcnow()
        self._session.flush()

    def remove(self, item_id: UUID) -> None:
        row = self._session.get(KnowledgeVectorORM, str(item_id))
        if row is not None:
            self._session.delete(row)
            self._session.flush()

    def query(self, vector: list[float], limit: int) -> list[tuple[UUID, float]]:
        rows = self._session.scalars(select(KnowledgeVectorORM)).all()
        hits = [
            (UUID(r.item_id), _cosine(vector, json.loads(r.vector))) for r in rows
        ]
        hits.sort(key=lambda kv: kv[1], reverse=True)
        return hits[:limit]


# 向后兼容别名：既有测试与文档以 SQLiteVectorStore 引用该通用实现。
SQLiteVectorStore = JsonVectorStore


def build_full_text_index(session: Session) -> FullTextIndex:
    """按会话绑定的方言选择全文索引实现（方言差异封装于此适配层）。"""
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        return PostgresFullTextIndex(session)
    if dialect == "sqlite":
        return SQLiteFullTextIndex(session)
    raise ValueError(f"不支持的数据库方言: {dialect}")


def build_vector_store(session: Session) -> VectorStore:
    """向量存储：JSON + Python 余弦，双方言通用。"""
    return JsonVectorStore(session)


class RetrievalIndexer:
    """条目变更后的索引同步：FTS 兜底 + 向量重算（embed 异步）。方言由工厂选择。"""

    def __init__(
        self,
        session: Session,
        embedder: Embedder | None,
        *,
        model: str = "none",
    ) -> None:
        self._fts = build_full_text_index(session)
        self._vectors = build_vector_store(session)
        self._embedder = embedder
        self._model = model
        self._items = SQLAlchemyKnowledgeRepository(session)

    async def index_item(self, item: KnowledgeItem) -> None:
        self._fts.upsert(item.id, item.title, item.content)
        if self._embedder is not None:
            vectors = await self._embedder.embed([f"{item.title}\n{item.content}"])
            if vectors:
                self._vectors.upsert(item.id, vectors[0], self._model)

    async def remove_item(self, item_id: UUID) -> None:
        self._fts.remove(item_id)
        self._vectors.remove(item_id)

    async def reindex_all(self) -> int:
        count = 0
        for item in self._items.list():
            try:
                await self.index_item(item)
            except ModelAdapterError as exc:
                # index_item 已先行 upsert FTS；embed 失败仅缺向量，如实降级不阻断 backfill。
                logger.warning("backfill 向量失败，FTS 已兜底 item=%s: %s", item.id, exc)
            count += 1
        return count


def build_retrieval_service(
    session: Session,
    embedder: Embedder | None,
    *,
    personal_space_id: str | None = None,
) -> HybridRetrievalService:
    return HybridRetrievalService(
        SQLAlchemyKnowledgeRepository(session),
        build_full_text_index(session),
        build_vector_store(session),
        embedder,
        personal_space_id=personal_space_id,
    )


async def sync_index(
    session: Session,
    embedder: Embedder | None,
    *,
    index_ids: Sequence[UUID] = (),
    remove_ids: Sequence[UUID] = (),
) -> None:
    """条目变更提交后同步检索索引（路由层 await）。

    FTS 日常由触发器同步，这里 upsert 作兜底；向量在此重算（embed 异步）。
    embedder 为 None 时仅维护 FTS，向量通道如实关闭。单条 embed 失败不阻断
    已提交的变更，也不影响其余条目：记录告警并降级（FTS 仍可用），不造假。
    """
    if not index_ids and not remove_ids:
        return
    model = getattr(embedder, "default_model", "none") if embedder else "none"
    indexer = RetrievalIndexer(session, embedder, model=model)
    repository = SQLAlchemyKnowledgeRepository(session)
    for item_id in index_ids:
        item = repository.get(item_id)
        if item is None:
            continue
        try:
            await indexer.index_item(item)
        except ModelAdapterError as exc:
            logger.warning("向量索引失败，降级为仅全文 item=%s: %s", item_id, exc)
    for item_id in remove_ids:
        await indexer.remove_item(item_id)


async def probe_embed_capability(embedder: Embedder | None) -> str:
    """只读探测 embed 端点能力，返回 not_configured / supported / unsupported。

    未配置→not_configured（向量通道如实关闭）；配置后以极小文本调 /embeddings，
    成功且返回非空向量→supported；调用失败或空向量→unsupported（如 DeepSeek 无
    /embeddings）。探测不写入任何数据，不造假；供健康检查如实上报。
    """
    if embedder is None:
        return "not_configured"
    try:
        vectors = await embedder.embed(["能力探测"])
    except ModelAdapterError as exc:
        logger.info("embed 能力探测失败（unsupported）: %s", exc)
        return "unsupported"
    if vectors and len(vectors[0]) > 0:
        return "supported"
    return "unsupported"