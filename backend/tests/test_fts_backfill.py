"""复审修复回归：迁移 0004 必须回填历史 knowledge_item 到全文索引（SQLite）。

缺陷：0004 只建 FTS5 虚表 + 同步触发器，未回填迁移前已存在的知识记录，导致
历史知识检索不到（触发器只对建索引之后的变更生效）。

本测试在临时 SQLite 上真实执行 Alembic 迁移：先把库停在 0003 并插入知识记录，
再 upgrade 到 head（0004 回填），**不调用 reindex**，直接检索历史知识。
覆盖：回填命中、幂等（重复回填不产生重复文档）、downgrade→upgrade 仍可检索、
回填后 INSERT/UPDATE/DELETE 触发器不被破坏。

检索查询刻意用 ≥3 字符词，确保走 FTS5 MATCH 索引路径（<3 字符会回退
knowledge_item LIKE，从而掩盖回填缺失）。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.core.config import get_settings
from app.db.fts import FTS_BACKFILL
from app.db.session import create_engine_from_url
from app.services.knowledge import SQLAlchemyKnowledgeRepository
from app.services.retrieval import SQLiteFullTextIndex, build_full_text_index
from knowledge_core.domain.entities import KnowledgeItem, SourceRef, SourceType, utcnow

BACKEND_DIR = Path(__file__).resolve().parents[1]

# 历史知识：含 ≥3 字符的可检索词，走 FTS5 MATCH（trigram）路径。
ITEM_A = ("quantum entanglement", "entanglement correlates particles across distance")
ITEM_B = ("classical mechanics", "newtonian motion describes macroscopic bodies")


def _alembic_cfg() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


def _insert(session: Session, title: str, content: str) -> UUID:
    item = KnowledgeItem(
        title=title,
        content=content,
        source_refs=[SourceRef(source_type=SourceType.MANUAL)],
    )
    saved = SQLAlchemyKnowledgeRepository(session).save(item)
    session.commit()
    return saved.id


def _insert_legacy(session: Session, title: str, content: str) -> UUID:
    """以 **0003 时期的列集合** 写入历史知识（裸 SQL，不用当前 ORM）。

    V2 迁移 0006 给 knowledge_item 增列后，当前 ORM 的 INSERT 会带上新列，
    无法写入停在 0003 的旧 schema。历史数据本就由旧版本写入，故这里按旧列集合
    插入（含一条 MANUAL 来源），语义与原来一致：0003 时已有知识、尚无 FTS 表。
    """
    item_id = str(uuid4())
    now = utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")
    session.execute(
        text(
            "INSERT INTO knowledge_item (id, title, content, status, created_at, updated_at) "
            "VALUES (:id, :title, :content, 'draft', :now, :now)"
        ),
        {"id": item_id, "title": title, "content": content, "now": now},
    )
    session.execute(
        text(
            "INSERT INTO source_ref (id, item_id, source_type, created_at) "
            "VALUES (:id, :item_id, 'manual', :now)"
        ),
        {"id": str(uuid4()), "item_id": item_id, "now": now},
    )
    session.commit()
    return UUID(item_id)


@pytest.fixture()
def hist_sqlite(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict]:
    """真实迁移到 0003，插入历史知识（此时无 FTS 表/触发器），yield 建库上下文。

    库停在 0003_m2_governance：knowledge_item 已有数据，knowledge_fts 尚不存在。
    各测试自行 upgrade/downgrade 验证回填。teardown 释放引擎并清配置缓存。
    """
    db_url = f"sqlite:///{tmp_path / 'hist.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    cfg = _alembic_cfg()
    command.upgrade(cfg, "0003_m2_governance")
    engine = create_engine_from_url(db_url)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    sess = factory()
    try:
        # 0003 尚无 knowledge_fts，插入不触发任何 FTS 同步（模拟迁移前历史数据）。
        assert "knowledge_fts" not in set(inspect(engine).get_table_names())
        id_a = _insert_legacy(sess, *ITEM_A)
        id_b = _insert_legacy(sess, *ITEM_B)
    finally:
        sess.close()
    try:
        yield {"cfg": cfg, "engine": engine, "db_url": db_url, "a": id_a, "b": id_b}
    finally:
        engine.dispose()
        get_settings.cache_clear()


def _session(engine) -> Session:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def _fts_count(session: Session) -> int:
    return session.execute(text("SELECT count(*) FROM knowledge_fts")).scalar_one()


def test_sqlite_migration_backfills_historical_items(hist_sqlite) -> None:
    """先有知识再 upgrade 0004：不 reindex，直接 FTS5 检索命中历史知识。"""
    ctx = hist_sqlite
    command.upgrade(ctx["cfg"], "head")
    sess = _session(ctx["engine"])
    try:
        fts = build_full_text_index(sess)
        assert isinstance(fts, SQLiteFullTextIndex)
        # 未调用任何 reindex/upsert，历史知识应已被迁移回填并可检索。
        assert [h[0] for h in fts.search("entanglement", 10)] == [ctx["a"]]
        assert [h[0] for h in fts.search("newtonian", 10)] == [ctx["b"]]
        # 全部历史记录进入索引，且无遗漏。
        assert _fts_count(sess) == 2
        assert sess.execute(text("SELECT count(*) FROM knowledge_item")).scalar_one() == 2
    finally:
        sess.close()


def test_sqlite_backfill_idempotent(hist_sqlite) -> None:
    """重复执行回填不产生重复 FTS5 文档（NOT EXISTS 跳过已索引 rowid）。"""
    ctx = hist_sqlite
    command.upgrade(ctx["cfg"], "head")
    sess = _session(ctx["engine"])
    try:
        assert _fts_count(sess) == 2
        # 再次执行同一回填语句（模拟重复运行），文档数不变。
        for statement in FTS_BACKFILL:
            sess.execute(text(statement))
        sess.commit()
        assert _fts_count(sess) == 2
        assert [h[0] for h in SQLiteFullTextIndex(sess).search("entanglement", 10)] == [ctx["a"]]
    finally:
        sess.close()


def test_sqlite_downgrade_upgrade_keeps_history_searchable(hist_sqlite) -> None:
    """downgrade 删除索引表后重新 upgrade，历史知识仍能被检索（再次回填）。"""
    ctx = hist_sqlite
    cfg = ctx["cfg"]
    command.upgrade(cfg, "head")
    sess = _session(ctx["engine"])
    try:
        assert [h[0] for h in SQLiteFullTextIndex(sess).search("entanglement", 10)] == [ctx["a"]]
    finally:
        sess.close()
    # downgrade 到 0003：knowledge_fts 被删除，knowledge_item 历史数据保留。
    command.downgrade(cfg, "0003_m2_governance")
    assert "knowledge_fts" not in set(inspect(ctx["engine"]).get_table_names())
    assert sess_count_items(ctx["engine"]) == 2
    # 重新 upgrade：0004 再次回填历史数据。
    command.upgrade(cfg, "head")
    sess = _session(ctx["engine"])
    try:
        assert [h[0] for h in SQLiteFullTextIndex(sess).search("entanglement", 10)] == [ctx["a"]]
        assert [h[0] for h in SQLiteFullTextIndex(sess).search("newtonian", 10)] == [ctx["b"]]
        assert _fts_count(sess) == 2  # 无重复
    finally:
        sess.close()


def sess_count_items(engine) -> int:
    sess = _session(engine)
    try:
        return sess.execute(text("SELECT count(*) FROM knowledge_item")).scalar_one()
    finally:
        sess.close()


def test_sqlite_triggers_still_work_after_backfill(hist_sqlite) -> None:
    """回填不破坏 INSERT/UPDATE/DELETE 同步触发器（迁移后新变更仍同步）。"""
    ctx = hist_sqlite
    command.upgrade(ctx["cfg"], "head")
    sess = _session(ctx["engine"])
    try:
        fts = SQLiteFullTextIndex(sess)
        # 历史 A 已回填可检索。
        assert [h[0] for h in fts.search("entanglement", 10)] == [ctx["a"]]
        # INSERT 触发器：迁移后新增条目自动入索引。
        id_c = _insert(sess, "thermodynamics entropy", "entropy measures disorder in systems")
        assert [h[0] for h in fts.search("entropy", 10)] == [id_c]
        # UPDATE 触发器：改写 A 后旧词消失、新词命中。
        sess.execute(
            text("UPDATE knowledge_item SET title='photon optics', content='photon interference patterns' WHERE id=:id"),
            {"id": str(ctx["a"])},
        )
        sess.commit()
        assert fts.search("entanglement", 10) == []
        assert [h[0] for h in fts.search("photon", 10)] == [ctx["a"]]
        # DELETE 触发器：删除 C 后索引同步移除。
        sess.execute(text("DELETE FROM knowledge_item WHERE id=:id"), {"id": str(id_c)})
        sess.commit()
        assert fts.search("entropy", 10) == []
        assert _fts_count(sess) == 2  # A(改写) + B 仍在，C 已删
    finally:
        sess.close()