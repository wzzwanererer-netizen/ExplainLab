"""ZIP-01：PostgreSQL 原生全文检索真实实例测试。

这些测试连接真实 PostgreSQL（经 EXPLAINLAB_PG_TEST_URL 指定），执行真实在线
Alembic 迁移与真实 SQL，绝不用离线 SQL 或假数据替代。未配置该环境变量时整模块
跳过（默认 SQLite 套件不受影响）；配置后必须连真实实例运行。

覆盖：迁移 up/down、原生 tsvector 表与 GIN 索引、插入/更新触发器、删除级联、
upsert/remove 兜底、向量余弦、backfill、混合检索端到端、CJK 子串回退、方言分派。
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.core.config import get_settings
from app.db.fts import PG_FTS_BACKFILL
from app.db.session import create_engine_from_url
from app.services.knowledge import SQLAlchemyKnowledgeRepository
from app.services.retrieval import (
    JsonVectorStore,
    PostgresFullTextIndex,
    RetrievalIndexer,
    build_full_text_index,
    build_retrieval_service,
    sync_index,
)
from knowledge_core.domain.entities import KnowledgeItem, SourceRef, SourceType
from knowledge_core.model_adapter import ModelAdapterError

BACKEND_DIR = Path(__file__).resolve().parents[1]
PG_URL = os.environ.get("EXPLAINLAB_PG_TEST_URL")

pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason="未配置 EXPLAINLAB_PG_TEST_URL（真实 PostgreSQL 实例），跳过 PG 检索测试",
)


def _alembic_cfg() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


@pytest.fixture(scope="module")
def pg_engine() -> Iterator:
    """真实在线迁移到 head（非离线 SQL），提供 PG 引擎。"""
    os.environ["DATABASE_URL"] = PG_URL  # type: ignore[assignment]
    get_settings.cache_clear()
    command.upgrade(_alembic_cfg(), "head")
    engine = create_engine_from_url(PG_URL)  # type: ignore[arg-type]
    try:
        yield engine
    finally:
        engine.dispose()
        get_settings.cache_clear()
        os.environ.pop("DATABASE_URL", None)


@pytest.fixture()
def pg_session(pg_engine) -> Iterator[Session]:
    factory = sessionmaker(bind=pg_engine, autoflush=False, expire_on_commit=False)
    sess = factory()
    sess.execute(text("DELETE FROM knowledge_item"))  # 级联清空 fts/vector/refs
    sess.commit()
    try:
        yield sess
    finally:
        sess.execute(text("DELETE FROM knowledge_item"))
        sess.commit()
        sess.close()


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


def test_pg_migration_creates_native_fts(pg_engine) -> None:
    """迁移后 knowledge_fts 为原生 tsvector 表 + GIN 索引，而非 FTS5 虚表。"""
    with pg_engine.connect() as conn:
        cols = {c["name"] for c in inspect(conn).get_columns("knowledge_fts")}
        assert {"item_id", "tsv"} <= cols
        data_type = conn.execute(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name='knowledge_fts' AND column_name='tsv'"
            )
        ).scalar_one()
        assert data_type == "tsvector"
        idx = {i["name"] for i in inspect(conn).get_indexes("knowledge_fts")}
        assert "knowledge_fts_tsv_idx" in idx
        vec_cols = {c["name"] for c in inspect(conn).get_columns("knowledge_vector")}
        assert {"item_id", "model", "dim", "vector", "updated_at"} <= vec_cols


def test_pg_migration_downgrade_and_upgrade(pg_engine) -> None:
    """真实 PG 上 0004 可 downgrade（删除 fts/触发器/函数/向量表）再 upgrade 恢复。"""
    cfg = _alembic_cfg()
    try:
        command.downgrade(cfg, "0003_m2_governance")
        with pg_engine.connect() as conn:
            tables = set(inspect(conn).get_table_names())
        assert "knowledge_fts" not in tables
        assert "knowledge_vector" not in tables
    finally:
        command.upgrade(cfg, "head")
    with pg_engine.connect() as conn:
        tables = set(inspect(conn).get_table_names())
    assert "knowledge_fts" in tables
    assert "knowledge_vector" in tables


def test_pg_insert_trigger_and_tsvector_search(pg_session: Session) -> None:
    """插入触发器填充 tsv；原生 tsquery 命中可分词查询，rank 越小越相关。"""
    item = _make_item(
        pg_session, "knowledge graph definition", "knowledge graph is a network structure"
    )
    tsv = pg_session.execute(
        text("SELECT tsv FROM knowledge_fts WHERE item_id=:id"), {"id": str(item.id)}
    ).scalar_one_or_none()
    assert tsv is not None
    hits = PostgresFullTextIndex(pg_session).search("knowledge graph", 10)
    assert [h[0] for h in hits] == [item.id]
    assert hits[0][1] < 0  # -ts_rank，越小越相关


def test_pg_update_trigger_refreshes_tsv(pg_session: Session) -> None:
    """更新 title/content 后旧词消失、新词命中（触发器维护 tsv）。"""
    item = _make_item(pg_session, "knowledge graph", "network structure model")
    fts = PostgresFullTextIndex(pg_session)
    assert [h[0] for h in fts.search("knowledge graph", 10)] == [item.id]
    pg_session.execute(
        text("UPDATE knowledge_item SET title='search engine', content='semantic understanding' WHERE id=:id"),
        {"id": str(item.id)},
    )
    pg_session.commit()
    assert fts.search("knowledge graph", 10) == []
    assert [h[0] for h in fts.search("search engine", 10)] == [item.id]


def test_pg_delete_cascades_fts(pg_session: Session) -> None:
    """删除条目经外键 ON DELETE CASCADE 级联清理 knowledge_fts 行。"""
    item = _make_item(pg_session, "knowledge graph", "network structure")
    pg_session.execute(text("DELETE FROM knowledge_item WHERE id=:id"), {"id": str(item.id)})
    pg_session.commit()
    remaining = pg_session.execute(
        text("SELECT count(*) FROM knowledge_fts WHERE item_id=:id"), {"id": str(item.id)}
    ).scalar_one()
    assert remaining == 0
    assert PostgresFullTextIndex(pg_session).search("knowledge graph", 10) == []


def test_pg_upsert_and_remove_backfill(pg_session: Session) -> None:
    """upsert 重写 tsv（backfill 兜底），remove 删除索引行；以原生 tsvector 精确验证。"""
    item = _make_item(pg_session, "original title", "original content")
    fts = PostgresFullTextIndex(pg_session)
    # 初始：插入触发器已索引，tsvector 命中 original
    assert [h[0] for h in fts.search("original title", 10)] == [item.id]
    # upsert 兜底：仅重写索引文档为 brand new（不改 knowledge_item 源行）
    fts.upsert(item.id, "brand new title", "brand new content")
    pg_session.commit()
    assert [h[0] for h in fts.search("brand new", 10)] == [item.id]
    # 直接以 tsvector 布尔验证旧词已从索引移除（不受 ILIKE 源表回退干扰）
    still_original = pg_session.execute(
        text(
            "SELECT tsv @@ plainto_tsquery('simple', 'original') "
            "FROM knowledge_fts WHERE item_id=:id"
        ),
        {"id": str(item.id)},
    ).scalar_one()
    assert still_original is False
    # remove：索引行删除，search 不再命中（回退 JOIN 限定已索引集合）
    fts.remove(item.id)
    pg_session.commit()
    assert fts.search("brand new", 10) == []
    assert (
        pg_session.execute(
            text("SELECT count(*) FROM knowledge_fts WHERE item_id=:id"),
            {"id": str(item.id)},
        ).scalar_one()
        == 0
    )


def test_pg_cjk_substring_fallback(pg_session: Session) -> None:
    """无空格中文不成词，tsvector 无命中时回退 ILIKE 子串匹配（真实命中）。"""
    item = _make_item(pg_session, "知识图谱的定义", "知识图谱是一种网络结构数据模型")
    hits = PostgresFullTextIndex(pg_session).search("知识图谱", 10)
    assert item.id in [h[0] for h in hits]


def test_pg_vector_store_cosine(pg_session: Session) -> None:
    """向量存储（JSON + 余弦）在 PG 上 upsert/query/remove 正常。"""
    a = _make_item(pg_session, "item alpha", "content alpha")
    b = _make_item(pg_session, "item beta", "content beta")
    vectors = JsonVectorStore(pg_session)
    vectors.upsert(a.id, [1.0, 0.0], "fake-embed")
    vectors.upsert(b.id, [0.0, 1.0], "fake-embed")
    pg_session.commit()
    hits = vectors.query([1.0, 0.0], 10)
    assert hits[0][0] == a.id
    assert hits[0][1] == pytest.approx(1.0)
    vectors.remove(a.id)
    pg_session.commit()
    assert [h[0] for h in vectors.query([1.0, 0.0], 10)] == [b.id]


@pytest.mark.asyncio
async def test_pg_indexer_reindex_all_backfill(pg_session: Session) -> None:
    """RetrievalIndexer 在 PG 上 backfill：全文兜底 + 向量重算。"""
    a = _make_item(pg_session, "knowledge graph", "network structure")
    b = _make_item(pg_session, "search engine", "semantic understanding")
    indexer = RetrievalIndexer(pg_session, FakeEmbedder(), model="fake-embed")
    count = await indexer.reindex_all()
    pg_session.commit()
    assert count == 2
    ids = {h[0] for h in JsonVectorStore(pg_session).query([1.0, 0.0], 10)}
    assert {a.id, b.id} <= ids
    assert a.id in [h[0] for h in PostgresFullTextIndex(pg_session).search("knowledge graph", 10)]


@pytest.mark.asyncio
async def test_pg_sync_index_and_remove(pg_session: Session) -> None:
    """sync_index 在 PG 上建索引与移除；embed 故障如实降级为仅全文。"""
    item = _make_item(pg_session, "knowledge graph", "network structure")
    await sync_index(pg_session, FakeEmbedder(), index_ids=[item.id])
    pg_session.commit()
    assert item.id in [h[0] for h in JsonVectorStore(pg_session).query([1.0, 0.0], 10)]
    await sync_index(pg_session, FakeEmbedder(), remove_ids=[item.id])
    pg_session.commit()
    assert JsonVectorStore(pg_session).query([1.0, 0.0], 10) == []
    assert PostgresFullTextIndex(pg_session).search("knowledge graph", 10) == []


@pytest.mark.asyncio
async def test_pg_hybrid_search_end_to_end(pg_session: Session) -> None:
    """build_retrieval_service 在 PG 上混合检索端到端命中，含 fts 通道。"""
    item = _make_item(pg_session, "knowledge graph definition", "knowledge graph is a network structure")
    _make_item(pg_session, "unrelated entry", "completely different topic")
    embedder = FakeEmbedder()
    await RetrievalIndexer(pg_session, embedder, model="fake-embed").reindex_all()
    pg_session.commit()
    service = build_retrieval_service(pg_session, embedder)
    results = await service.search("knowledge graph", limit=10)
    assert item.id in [r.item_id for r in results]
    top = next(r for r in results if r.item_id == item.id)
    assert "fts" in top.channels


def test_pg_dialect_dispatch(pg_session: Session) -> None:
    """工厂按方言分派：PG 会话返回 PostgresFullTextIndex。"""
    assert isinstance(build_full_text_index(pg_session), PostgresFullTextIndex)


# --- 复审修复回归：迁移 0004 必须回填历史 knowledge_item（真实 PG）---
# 缺陷：0004 只建 tsvector 表 + 触发器，未回填迁移前已存在的知识，历史知识检索
# 不到（触发器只对建索引之后的变更生效；CJK 的 ILIKE 回退也 JOIN knowledge_fts，
# 同样依赖回填）。下列测试先把库停在 0003 插入历史知识，再 upgrade 到 head，
# **不调用 reindex**，直接检索；并验证幂等、downgrade→upgrade、触发器不破坏。

PG_ITEM_A = ("quantum entanglement", "entanglement correlates particles across distance")
PG_ITEM_B = ("classical mechanics", "newtonian motion describes macroscopic bodies")
PG_ITEM_C = ("知识图谱的定义", "知识图谱是一种网络结构数据模型")


@pytest.fixture()
def pg_hist(pg_engine) -> Iterator[dict]:
    """真实 downgrade 到 0003 并插入历史知识（此时无 FTS 表/触发器），yield 上下文。

    teardown 恢复 head 并清空 knowledge_item，保证模块状态不影响其它测试。
    """
    cfg = _alembic_cfg()
    factory = sessionmaker(bind=pg_engine, autoflush=False, expire_on_commit=False)
    sess = factory()
    sess.execute(text("DELETE FROM knowledge_item"))
    sess.commit()
    command.downgrade(cfg, "0003_m2_governance")
    try:
        assert "knowledge_fts" not in set(inspect(pg_engine).get_table_names())
        a = _make_item(sess, *PG_ITEM_A)
        b = _make_item(sess, *PG_ITEM_B)
        c = _make_item(sess, *PG_ITEM_C)
        sess.close()
        yield {"cfg": cfg, "engine": pg_engine, "a": a.id, "b": b.id, "c": c.id}
    finally:
        command.upgrade(cfg, "head")
        cleanup = factory()
        cleanup.execute(text("DELETE FROM knowledge_item"))
        cleanup.commit()
        cleanup.close()


def _pg_sess(engine) -> Session:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def _pg_fts_count(session: Session) -> int:
    return session.execute(text("SELECT count(*) FROM knowledge_fts")).scalar_one()


def test_pg_migration_backfills_historical_items(pg_hist) -> None:
    """先有知识再 upgrade 0004：不 reindex，原生 tsvector 直接检索命中历史知识。"""
    ctx = pg_hist
    command.upgrade(ctx["cfg"], "head")
    sess = _pg_sess(ctx["engine"])
    try:
        fts = build_full_text_index(sess)
        assert isinstance(fts, PostgresFullTextIndex)
        assert [h[0] for h in fts.search("entanglement", 10)] == [ctx["a"]]
        assert [h[0] for h in fts.search("newtonian", 10)] == [ctx["b"]]
        assert _pg_fts_count(sess) == 3  # A/B/C 全部回填
        assert sess.execute(text("SELECT count(*) FROM knowledge_item")).scalar_one() == 3
    finally:
        sess.close()


def test_pg_backfill_idempotent(pg_hist) -> None:
    """重复执行回填不产生重复索引行（item_id 主键 ON CONFLICT 收敛）。"""
    ctx = pg_hist
    command.upgrade(ctx["cfg"], "head")
    sess = _pg_sess(ctx["engine"])
    try:
        assert _pg_fts_count(sess) == 3
        for statement in PG_FTS_BACKFILL:
            sess.execute(text(statement))
        sess.commit()
        assert _pg_fts_count(sess) == 3
        assert [h[0] for h in PostgresFullTextIndex(sess).search("entanglement", 10)] == [ctx["a"]]
    finally:
        sess.close()


def test_pg_downgrade_upgrade_keeps_history_searchable(pg_hist) -> None:
    """downgrade 删除索引表后重新 upgrade，历史知识仍可检索（再次回填，无重复）。"""
    ctx = pg_hist
    cfg = ctx["cfg"]
    command.upgrade(cfg, "head")
    sess = _pg_sess(ctx["engine"])
    try:
        assert [h[0] for h in PostgresFullTextIndex(sess).search("entanglement", 10)] == [ctx["a"]]
    finally:
        sess.close()
    command.downgrade(cfg, "0003_m2_governance")
    assert "knowledge_fts" not in set(inspect(ctx["engine"]).get_table_names())
    command.upgrade(cfg, "head")
    sess = _pg_sess(ctx["engine"])
    try:
        assert [h[0] for h in PostgresFullTextIndex(sess).search("entanglement", 10)] == [ctx["a"]]
        assert [h[0] for h in PostgresFullTextIndex(sess).search("newtonian", 10)] == [ctx["b"]]
        assert _pg_fts_count(sess) == 3
    finally:
        sess.close()


def test_pg_cjk_history_backfill_searchable(pg_hist) -> None:
    """历史中文知识回填后，CJK 的 ILIKE 回退（JOIN knowledge_fts）也能命中。"""
    ctx = pg_hist
    command.upgrade(ctx["cfg"], "head")
    sess = _pg_sess(ctx["engine"])
    try:
        # 无空格中文不成词，走 ILIKE 回退；回退 JOIN 索引表，故必须已回填才命中。
        assert ctx["c"] in [h[0] for h in PostgresFullTextIndex(sess).search("知识图谱", 10)]
    finally:
        sess.close()


def test_pg_triggers_still_work_after_backfill(pg_hist) -> None:
    """回填不破坏 INSERT/UPDATE 触发器与 DELETE 外键级联（迁移后新变更仍同步）。"""
    ctx = pg_hist
    command.upgrade(ctx["cfg"], "head")
    sess = _pg_sess(ctx["engine"])
    try:
        fts = PostgresFullTextIndex(sess)
        assert [h[0] for h in fts.search("entanglement", 10)] == [ctx["a"]]
        # INSERT 触发器：迁移后新增条目自动入索引。
        d = _make_item(sess, "thermodynamics entropy", "entropy measures disorder in systems")
        assert [h[0] for h in fts.search("entropy", 10)] == [d.id]
        # UPDATE 触发器：改写 A 后旧词消失、新词命中。
        sess.execute(
            text("UPDATE knowledge_item SET title='photon optics', content='photon interference patterns' WHERE id=:id"),
            {"id": str(ctx["a"])},
        )
        sess.commit()
        assert fts.search("entanglement", 10) == []
        assert [h[0] for h in fts.search("photon", 10)] == [ctx["a"]]
        # DELETE 外键级联：删除 D 后索引同步移除。
        sess.execute(text("DELETE FROM knowledge_item WHERE id=:id"), {"id": str(d.id)})
        sess.commit()
        assert fts.search("entropy", 10) == []
        assert _pg_fts_count(sess) == 3  # A(改写)+B+C 仍在，D 已删
    finally:
        sess.close()