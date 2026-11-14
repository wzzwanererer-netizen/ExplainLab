"""M3-T3 检索装配测试：SQLite FTS / 向量存储 / 索引同步 / backfill / 混合检索。

使用 Alembic 迁移到 head 的临时 SQLite 库（含 FTS5 虚表 + 触发器 + 向量表），
向量用本地 FakeEmbedder（确定性向量，不发网络请求），全文用真实 FTS5 trigram。
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.core.config import get_settings
from app.db.session import create_engine_from_url
from app.services.knowledge import SQLAlchemyKnowledgeRepository
from app.services.retrieval import (
    RetrievalIndexer,
    SQLiteFullTextIndex,
    SQLiteVectorStore,
    build_retrieval_service,
    probe_embed_capability,
    sync_index,
)
from knowledge_core.domain.entities import KnowledgeItem, SourceRef, SourceType
from knowledge_core.model_adapter import ModelAdapterError

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture()
def session(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    db_url = f"sqlite:///{tmp_path / 'retrieval_svc.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")
    engine = create_engine_from_url(db_url)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    sess = factory()
    try:
        yield sess
    finally:
        sess.close()
        engine.dispose()
        get_settings.cache_clear()


class FakeEmbedder:
    """确定性向量替身：按文本查表，缺省 [1, 0]；可模拟故障。不发网络请求。"""

    def __init__(self, vectors: dict[str, list[float]] | None = None, *, fail: bool = False):
        self.vectors = vectors or {}
        self.fail = fail
        self.default_model = "fake-embed"

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if self.fail:
            raise ModelAdapterError("模拟向量故障")
        return [self.vectors.get(t, [1.0, 0.0]) for t in texts]


def _make_item(session: Session, title: str, content: str) -> KnowledgeItem:
    item = KnowledgeItem(
        title=title,
        content=content,
        source_refs=[SourceRef(source_type=SourceType.MANUAL)],
    )
    saved = SQLAlchemyKnowledgeRepository(session).save(item)
    session.commit()
    return saved


def test_fts_search_trigram_chinese(session: Session) -> None:
    item = _make_item(session, "知识图谱的定义", "知识图谱是一种网络结构数据模型")
    hits = SQLiteFullTextIndex(session).search("知识图谱", 10)
    assert [h[0] for h in hits] == [item.id]
    # bm25 排名越小越优（FTS5 返回负值）
    assert hits[0][1] < 0


def test_fts_search_short_query_like_fallback(session: Session) -> None:
    item = _make_item(session, "图谱笔记", "知识图谱相关内容")
    # 2 字符查询走 LIKE 回退（trigram 需 >=3 字符）
    hits = SQLiteFullTextIndex(session).search("图谱", 10)
    assert item.id in [h[0] for h in hits]


def test_fts_upsert_and_remove(session: Session) -> None:
    item = _make_item(session, "原标题", "原内容")
    fts = SQLiteFullTextIndex(session)
    # 兜底 upsert：不改 knowledge_item 行，直接重写 FTS 文档
    fts.upsert(item.id, "全新标题", "全新内容")
    session.commit()
    assert [h[0] for h in fts.search("全新标题", 10)] == [item.id]
    assert fts.search("原标题", 10) == []
    fts.remove(item.id)
    session.commit()
    assert fts.search("全新标题", 10) == []


def test_vector_store_upsert_query_cosine(session: Session) -> None:
    a = _make_item(session, "条目甲", "内容甲")
    b = _make_item(session, "条目乙", "内容乙")
    vectors = SQLiteVectorStore(session)
    vectors.upsert(a.id, [1.0, 0.0], "fake-embed")
    vectors.upsert(b.id, [0.0, 1.0], "fake-embed")
    session.commit()
    hits = vectors.query([1.0, 0.0], 10)
    assert hits[0][0] == a.id
    assert hits[0][1] == pytest.approx(1.0)
    assert hits[1][0] == b.id
    assert hits[1][1] == pytest.approx(0.0)
    vectors.remove(a.id)
    session.commit()
    assert [h[0] for h in vectors.query([1.0, 0.0], 10)] == [b.id]


@pytest.mark.asyncio
async def test_indexer_reindex_all_backfill(session: Session) -> None:
    a = _make_item(session, "知识图谱", "网络结构")
    b = _make_item(session, "搜索引擎", "语义理解")
    indexer = RetrievalIndexer(session, FakeEmbedder(), model="fake-embed")
    count = await indexer.reindex_all()
    session.commit()
    assert count == 2
    vectors = SQLiteVectorStore(session)
    ids = {h[0] for h in vectors.query([1.0, 0.0], 10)}
    assert {a.id, b.id} <= ids
    # backfill 同时兜底全文
    assert a.id in [h[0] for h in SQLiteFullTextIndex(session).search("知识图谱", 10)]


@pytest.mark.asyncio
async def test_indexer_without_embedder_fts_only(session: Session) -> None:
    item = _make_item(session, "知识图谱", "网络结构")
    indexer = RetrievalIndexer(session, None)
    await indexer.index_item(item)
    session.commit()
    assert item.id in [h[0] for h in SQLiteFullTextIndex(session).search("知识图谱", 10)]
    # 未配置 embed：向量通道如实关闭，不写任何向量
    assert SQLiteVectorStore(session).query([1.0, 0.0], 10) == []


@pytest.mark.asyncio
async def test_sync_index_index_and_remove(session: Session) -> None:
    item = _make_item(session, "知识图谱", "网络结构")
    embedder = FakeEmbedder()
    await sync_index(session, embedder, index_ids=[item.id])
    session.commit()
    assert item.id in [h[0] for h in SQLiteVectorStore(session).query([1.0, 0.0], 10)]
    await sync_index(session, embedder, remove_ids=[item.id])
    session.commit()
    assert SQLiteVectorStore(session).query([1.0, 0.0], 10) == []
    assert SQLiteFullTextIndex(session).search("知识图谱", 10) == []


@pytest.mark.asyncio
async def test_sync_index_degrades_on_embed_failure(session: Session) -> None:
    item = _make_item(session, "知识图谱", "网络结构")
    # embed 故障不阻断已提交变更：FTS 仍可用，向量如实缺失，不抛错不造假
    await sync_index(session, FakeEmbedder(fail=True), index_ids=[item.id])
    session.commit()
    assert item.id in [h[0] for h in SQLiteFullTextIndex(session).search("知识图谱", 10)]
    assert SQLiteVectorStore(session).query([1.0, 0.0], 10) == []


@pytest.mark.asyncio
async def test_build_retrieval_service_hybrid(session: Session) -> None:
    item = _make_item(session, "知识图谱的定义", "知识图谱是一种网络结构数据模型")
    _make_item(session, "无关条目", "完全不同的主题内容")
    embedder = FakeEmbedder()
    await RetrievalIndexer(session, embedder, model="fake-embed").reindex_all()
    session.commit()
    service = build_retrieval_service(session, embedder)
    results = await service.search("知识图谱", limit=10)
    assert item.id in [r.item_id for r in results]
    top = next(r for r in results if r.item_id == item.id)
    assert "fts" in top.channels


@pytest.mark.asyncio
async def test_probe_embed_not_configured() -> None:
    assert await probe_embed_capability(None) == "not_configured"


@pytest.mark.asyncio
async def test_probe_embed_supported() -> None:
    assert await probe_embed_capability(FakeEmbedder()) == "supported"


@pytest.mark.asyncio
async def test_probe_embed_unsupported_on_error() -> None:
    assert await probe_embed_capability(FakeEmbedder(fail=True)) == "unsupported"


@pytest.mark.asyncio
async def test_probe_embed_unsupported_on_empty_vector() -> None:
    class EmptyEmbedder:
        default_model = "empty"

        async def embed(self, texts: Sequence[str]) -> list[list[float]]:
            return [[] for _ in texts]

    assert await probe_embed_capability(EmptyEmbedder()) == "unsupported"