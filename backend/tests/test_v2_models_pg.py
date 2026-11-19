"""V2 A1 数据模型真实 PostgreSQL 测试（迁移 0006 + 约束 + 降级）。

经 EXPLAINLAB_PG_TEST_URL 门控：未配置时整模块跳过（默认 SQLite 套件不受影响）；
配置后连真实 PG 实例执行真实在线 Alembic 迁移与真实 SQL，绝不用离线 SQL 或假数据替代。

覆盖：0006 在 PG 上建表/加列、迁移与 ORM 元数据一致、非空 normalized_link_key
唯一（修复 alias NULL≠NULL）、外键 CASCADE/SET NULL、审计快照保留、租约条件更新
与 fencing、downgrade 删列（op.drop_column 路径）→ upgrade 恢复且历史数据无损、
V1 全文检索触发器不受 0006 影响。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import create_engine_from_url
from app.models import (
    AttachmentORM,
    GcTaskORM,
    ImportOriginORM,
    ItemTagORM,
    KnowledgeItemORM,
    KnowledgeLinkORM,
    StorageLockORM,
    TagChangeLogORM,
    TagORM,
)
from app.services.retrieval import PostgresFullTextIndex
from knowledge_core.domain.entities import utcnow

BACKEND_DIR = Path(__file__).resolve().parents[1]
PG_URL = os.environ.get("EXPLAINLAB_PG_TEST_URL")

pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason="未配置 EXPLAINLAB_PG_TEST_URL（真实 PostgreSQL 实例），跳过 V2 PG 数据模型测试",
)

NEW_TABLES = (
    "tag",
    "item_tag",
    "knowledge_link",
    "attachment",
    "tag_change_log",
    "gc_task",
    "import_origin",
    "storage_lock",
)
ITEM_NEW_COLUMNS = (
    "extra_metadata",
    "source_payload_hash",
    "source_content_hash",
    "source_instance_id",
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
    _clean(sess)
    try:
        yield sess
    finally:
        _clean(sess)
        sess.close()


def _clean(sess: Session) -> None:
    sess.execute(text("DELETE FROM knowledge_item"))  # 级联清空 link/attachment/origin/item_tag
    sess.execute(text("DELETE FROM tag"))
    sess.execute(text("DELETE FROM gc_task"))
    sess.execute(text("DELETE FROM storage_lock"))
    sess.execute(text("DELETE FROM tag_change_log"))
    sess.commit()


def _item(sess: Session, title: str = "knowledge graph", content: str = "network structure") -> KnowledgeItemORM:
    row = KnowledgeItemORM(title=title, content=content, status="active")
    sess.add(row)
    sess.commit()
    return row


def _link(sess: Session, source: str, key: str, **kwargs) -> KnowledgeLinkORM:
    row = KnowledgeLinkORM(
        source_item_id=source,
        target_title=kwargs.pop("target_title", key),
        normalized_link_key=key,
        **kwargs,
    )
    sess.add(row)
    sess.commit()
    return row


class TestPgMigration:
    def test_head_creates_new_tables_and_columns(self, pg_engine) -> None:
        insp = inspect(pg_engine)
        tables = set(insp.get_table_names())
        assert set(NEW_TABLES) <= tables
        cols = {c["name"]: c for c in insp.get_columns("knowledge_item")}
        assert set(ITEM_NEW_COLUMNS) <= set(cols)
        assert cols["extra_metadata"]["nullable"] is False
        for name in ("source_payload_hash", "source_content_hash", "source_instance_id"):
            assert cols[name]["nullable"] is True

    def test_pg_column_types(self, pg_engine) -> None:
        """PG 侧类型正确：boolean / timestamptz / varchar 长度 / text。"""
        with pg_engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT table_name, column_name, data_type, character_maximum_length "
                    "FROM information_schema.columns WHERE table_name = ANY(:tables)"
                ),
                {"tables": list(NEW_TABLES)},
            ).fetchall()
        types = {(r[0], r[1]): (r[2], r[3]) for r in rows}
        assert types[("knowledge_link", "cross_space")][0] == "boolean"
        assert types[("knowledge_link", "normalized_link_key")] == ("character varying", 1024)
        assert types[("knowledge_link", "link_normalization_version")][0] == "integer"
        assert types[("knowledge_link", "created_at")][0] == "timestamp with time zone"
        assert types[("knowledge_link", "target_item_id")] == ("character varying", 36)
        assert types[("tag", "name")] == ("character varying", 100)
        assert types[("attachment", "storage_key")] == ("character varying", 64)
        assert types[("tag_change_log", "old_tags")][0] == "text"
        assert types[("gc_task", "quarantine_path")] == ("character varying", 512)
        assert types[("gc_task", "status")] == ("character varying", 24)
        assert types[("storage_lock", "storage_key")] == ("character varying", 64)
        assert types[("import_origin", "source_canonicalization_version")][0] == "integer"

    def test_migration_matches_orm_metadata(self, pg_engine) -> None:
        """真实 PG 迁移结果与 ORM 元数据一致（列名/类型/可空/索引/唯一/外键）。"""
        insp = inspect(pg_engine)
        pg_dialect = postgresql.dialect()
        for table_name in (*NEW_TABLES, "knowledge_item"):
            orm_table = Base.metadata.tables[table_name]
            actual = {c["name"]: c for c in insp.get_columns(table_name)}
            assert set(actual) == {c.name for c in orm_table.columns}, table_name
            for col in orm_table.columns:
                assert actual[col.name]["nullable"] == col.nullable, (table_name, col.name)
                expected_type = str(col.type.compile(dialect=pg_dialect))
                actual_type = str(actual[col.name]["type"].compile(dialect=pg_dialect))
                assert actual_type == expected_type, (table_name, col.name, actual_type, expected_type)
            orm_indexes = {
                (i.name, tuple(c.name for c in i.columns), i.unique)
                for i in orm_table.indexes
            }
            actual_indexes = {
                (i["name"], tuple(i["column_names"]), i["unique"])
                for i in insp.get_indexes(table_name)
            }
            assert orm_indexes <= actual_indexes, table_name
            orm_uniques = {
                (c.name, tuple(col.name for col in c.columns))
                for c in orm_table.constraints
                if c.__class__.__name__ == "UniqueConstraint"
            }
            actual_uniques = {
                (u["name"], tuple(u["column_names"]))
                for u in insp.get_unique_constraints(table_name)
            }
            assert orm_uniques <= actual_uniques, table_name
            orm_fks = {
                (tuple(fk.column_keys), fk.referred_table.name, fk.ondelete)
                for fk in orm_table.foreign_key_constraints
            }
            actual_fks = {
                (tuple(f["constrained_columns"]), f["referred_table"], f.get("options", {}).get("ondelete"))
                for f in insp.get_foreign_keys(table_name)
            }
            assert orm_fks <= actual_fks, (table_name, orm_fks, actual_fks)

    def test_v1_fts_triggers_survive_0006(self, pg_session: Session) -> None:
        """0006 不破坏 V1 PG 全文检索：新增条目仍由触发器入 tsvector 索引。"""
        item = _item(pg_session, "knowledge graph definition", "knowledge graph is a network structure")
        hits = PostgresFullTextIndex(pg_session).search("knowledge graph", 10)
        assert item.id in [str(h[0]) for h in hits]


class TestPgConstraints:
    def test_link_unique_key_with_null_alias(self, pg_session: Session) -> None:
        """PG 下 alias 为 NULL 也不得绕过 (source, normalized_link_key) 唯一。"""
        item = _item(pg_session)
        _link(pg_session, item.id, "knowledge graph", alias=None)
        pg_session.add(
            KnowledgeLinkORM(
                source_item_id=item.id,
                target_title="Knowledge Graph",
                alias=None,
                normalized_link_key="knowledge graph",
            )
        )
        with pytest.raises(IntegrityError):
            pg_session.commit()
        pg_session.rollback()

    def test_link_unique_key_with_different_alias(self, pg_session: Session) -> None:
        item = _item(pg_session)
        _link(pg_session, item.id, "knowledge graph", alias="甲")
        pg_session.add(
            KnowledgeLinkORM(
                source_item_id=item.id,
                target_title="Knowledge Graph",
                alias="乙",
                normalized_link_key="knowledge graph",
            )
        )
        with pytest.raises(IntegrityError):
            pg_session.commit()
        pg_session.rollback()

    def test_link_key_not_null(self, pg_session: Session) -> None:
        item = _item(pg_session)
        with pytest.raises(IntegrityError):
            pg_session.execute(
                text(
                    "INSERT INTO knowledge_link (id, source_item_id, target_title, "
                    "normalized_link_key, link_normalization_version, resolution, cross_space, "
                    "created_at, updated_at) VALUES ('l-null', :src, 'T', NULL, 1, 'missing', false, "
                    "now(), now())"
                ),
                {"src": item.id},
            )
            pg_session.commit()
        pg_session.rollback()

    def test_same_key_different_source_allowed(self, pg_session: Session) -> None:
        a = _item(pg_session, title="A")
        b = _item(pg_session, title="B")
        _link(pg_session, a.id, "shared key")
        _link(pg_session, b.id, "shared key")
        assert pg_session.execute(text("SELECT count(*) FROM knowledge_link")).scalar_one() == 2

    def test_tag_name_unique(self, pg_session: Session) -> None:
        pg_session.add(TagORM(name="概念"))
        pg_session.commit()
        pg_session.add(TagORM(name="概念"))
        with pytest.raises(IntegrityError):
            pg_session.commit()
        pg_session.rollback()

    def test_item_tag_composite_pk(self, pg_session: Session) -> None:
        item = _item(pg_session)
        tag = TagORM(name="图谱")
        pg_session.add(tag)
        pg_session.commit()
        pg_session.add(ItemTagORM(item_id=item.id, tag_id=tag.id))
        pg_session.commit()
        pg_session.add(ItemTagORM(item_id=item.id, tag_id=tag.id))
        with pytest.raises(IntegrityError):
            pg_session.commit()
        pg_session.rollback()

    def test_storage_lock_pk_unique(self, pg_session: Session) -> None:
        expires = utcnow()
        pg_session.add(
            StorageLockORM(storage_key="key-1", owner="w1", lease_token=1, lease_expires_at=expires)
        )
        pg_session.commit()
        pg_session.add(
            StorageLockORM(storage_key="key-1", owner="w2", lease_token=2, lease_expires_at=expires)
        )
        with pytest.raises(IntegrityError):
            pg_session.commit()
        pg_session.rollback()


class TestPgForeignKeys:
    def test_source_cascade_target_set_null(self, pg_session: Session) -> None:
        source = _item(pg_session, title="source item")
        target = _item(pg_session, title="target item")
        link = _link(
            pg_session, source.id, "target item", target_item_id=target.id, resolution="resolved"
        )
        pg_session.execute(text("DELETE FROM knowledge_item WHERE id=:id"), {"id": target.id})
        pg_session.commit()
        pg_session.refresh(link)
        assert link.target_item_id is None
        assert link.target_title == "target item"  # 原始字面保留
        pg_session.execute(text("DELETE FROM knowledge_item WHERE id=:id"), {"id": source.id})
        pg_session.commit()
        assert pg_session.execute(text("SELECT count(*) FROM knowledge_link")).scalar_one() == 0

    def test_backlinks_by_stable_id_after_rename(self, pg_session: Session) -> None:
        target = _item(pg_session, title="original title")
        s1 = _item(pg_session, title="ref one")
        s2 = _item(pg_session, title="ref two")
        _link(pg_session, s1.id, "original title", target_item_id=target.id, resolution="resolved")
        _link(pg_session, s2.id, "original title", target_item_id=target.id, resolution="resolved")
        pg_session.execute(
            text("UPDATE knowledge_item SET title='renamed title' WHERE id=:id"), {"id": target.id}
        )
        pg_session.commit()
        backlinks = pg_session.execute(
            text("SELECT source_item_id FROM knowledge_link WHERE target_item_id=:tid"),
            {"tid": target.id},
        ).scalars().all()
        assert set(backlinks) == {s1.id, s2.id}

    def test_attachment_and_origin_cascade(self, pg_session: Session) -> None:
        item = _item(pg_session)
        pg_session.add(
            AttachmentORM(
                item_id=item.id, filename="f.png", mime="image/png", size=1,
                storage_key="key-1", content_hash="h" * 64,
            )
        )
        pg_session.add(
            ImportOriginORM(
                item_id=item.id, source_payload_hash="p" * 64,
                source_content_hash="c" * 64, source_document_id=item.id,
            )
        )
        pg_session.commit()
        pg_session.execute(text("DELETE FROM knowledge_item WHERE id=:id"), {"id": item.id})
        pg_session.commit()
        assert pg_session.execute(text("SELECT count(*) FROM attachment")).scalar_one() == 0
        assert pg_session.execute(text("SELECT count(*) FROM import_origin")).scalar_one() == 0

    def test_item_tag_cascade_both_sides(self, pg_session: Session) -> None:
        item = _item(pg_session)
        tag = TagORM(name="图谱")
        pg_session.add(tag)
        pg_session.commit()
        pg_session.add(ItemTagORM(item_id=item.id, tag_id=tag.id))
        pg_session.commit()
        pg_session.execute(text("DELETE FROM tag WHERE id=:id"), {"id": tag.id})
        pg_session.commit()
        assert pg_session.execute(text("SELECT count(*) FROM item_tag")).scalar_one() == 0
        pg_session.add(TagORM(name="图谱"))
        pg_session.commit()
        tag_id = pg_session.execute(text("SELECT id FROM tag WHERE name='图谱'")).scalar_one()
        pg_session.add(ItemTagORM(item_id=item.id, tag_id=tag_id))
        pg_session.commit()
        pg_session.execute(text("DELETE FROM knowledge_item WHERE id=:id"), {"id": item.id})
        pg_session.commit()
        assert pg_session.execute(text("SELECT count(*) FROM item_tag")).scalar_one() == 0
        assert pg_session.execute(text("SELECT count(*) FROM tag")).scalar_one() == 1

    def test_tag_change_log_set_null_keeps_snapshot(self, pg_session: Session) -> None:
        item = _item(pg_session, title="will be deleted")
        record = TagChangeLogORM(
            item_id=item.id,
            item_id_snapshot=item.id,
            item_title_snapshot=item.title,
            old_tags='["a"]',
            new_tags='["a","b"]',
            actor="user",
            change_source="api",
            correlation_id="op-1",
        )
        pg_session.add(record)
        pg_session.commit()
        pg_session.execute(text("DELETE FROM knowledge_item WHERE id=:id"), {"id": item.id})
        pg_session.commit()
        pg_session.refresh(record)
        assert record.item_id is None
        assert record.item_id_snapshot == item.id
        assert record.item_title_snapshot == "will be deleted"
        assert record.new_tags == '["a","b"]'


class TestPgDefaultsAndLease:
    def test_orm_defaults(self, pg_session: Session) -> None:
        item = _item(pg_session)
        link = _link(pg_session, item.id, "t")
        assert link.link_normalization_version == 1
        assert link.resolution == "missing"
        assert link.cross_space is False
        task = GcTaskORM(storage_key="key-1")
        pg_session.add(task)
        pg_session.commit()
        assert task.status == "pending"
        assert task.lease_token == 0
        assert task.attempts == 0
        origin = ImportOriginORM(
            item_id=item.id, source_payload_hash="p" * 64,
            source_content_hash="c" * 64, source_document_id=item.id,
        )
        pg_session.add(origin)
        pg_session.commit()
        assert origin.source_canonicalization_version == 1

    def test_extra_metadata_server_default(self, pg_session: Session) -> None:
        pg_session.execute(
            text(
                "INSERT INTO knowledge_item (id, title, content, status, created_at, updated_at) "
                "VALUES ('raw-1', 'raw insert', 'body', 'draft', now(), now())"
            )
        )
        pg_session.commit()
        value = pg_session.execute(
            text("SELECT extra_metadata FROM knowledge_item WHERE id='raw-1'")
        ).scalar_one()
        assert value == "{}"

    def test_lease_takeover_and_fencing(self, pg_session: Session) -> None:
        """过期接管（条件更新 rowcount==1）+ 旧 token 释放失配（rowcount==0）。"""
        now = utcnow()
        pg_session.add(
            StorageLockORM(
                storage_key="key-1", owner="old", lease_token=1,
                lease_expires_at=now - timedelta(seconds=1),
            )
        )
        pg_session.commit()
        taken = pg_session.execute(
            text(
                "UPDATE storage_lock SET owner='new', lease_token=storage_lock.lease_token+1, "
                "lease_expires_at=:expires WHERE storage_key='key-1' AND lease_expires_at < :now"
            ),
            {"expires": now + timedelta(seconds=30), "now": now},
        )
        pg_session.commit()
        assert taken.rowcount == 1
        row = pg_session.execute(
            text("SELECT owner, lease_token FROM storage_lock WHERE storage_key='key-1'")
        ).fetchone()
        assert (row[0], row[1]) == ("new", 2)
        stale = pg_session.execute(
            text(
                "DELETE FROM storage_lock WHERE storage_key='key-1' AND owner='old' AND lease_token=1"
            )
        )
        pg_session.commit()
        assert stale.rowcount == 0

    def test_gc_conditional_claim(self, pg_session: Session) -> None:
        """GC 原子认领：pending → running（token+1, attempts+1）；重复认领 rowcount==0。"""
        task = GcTaskORM(storage_key="key-1")
        pg_session.add(task)
        pg_session.commit()
        now = utcnow()
        claim_sql = text(
            "UPDATE gc_task SET status='running', lease_owner=:owner, lease_expires_at=:expires, "
            "lease_token=gc_task.lease_token+1, attempts=gc_task.attempts+1 "
            "WHERE id=:id AND (status='pending' OR (status='running' AND lease_expires_at < :now))"
        )
        first = pg_session.execute(
            claim_sql,
            {"owner": "w1", "expires": now + timedelta(seconds=30), "now": now, "id": task.id},
        )
        pg_session.commit()
        assert first.rowcount == 1
        second = pg_session.execute(
            claim_sql,
            {"owner": "w2", "expires": now + timedelta(seconds=30), "now": now, "id": task.id},
        )
        pg_session.commit()
        assert second.rowcount == 0  # 租约未过期，他人认领失败
        row = pg_session.execute(
            text("SELECT lease_owner, lease_token, attempts, status FROM gc_task WHERE id=:id"),
            {"id": task.id},
        ).fetchone()
        assert tuple(row) == ("w1", 1, 1, "running")


@pytest.fixture()
def pg_roundtrip(pg_engine) -> Iterator[dict]:
    """真实 downgrade 到 0005（删表+删列）再 upgrade，验证历史数据无损与 V1 检索不坏。"""
    cfg = _alembic_cfg()
    factory = sessionmaker(bind=pg_engine, autoflush=False, expire_on_commit=False)
    sess = factory()
    _clean(sess)
    # 先在 head 写入数据，再降级：验证降级不丢 V1 数据、加列回填正确
    item = _item(sess, "historical knowledge", "entanglement correlates particles")
    item_id = item.id
    sess.close()
    try:
        yield {"cfg": cfg, "engine": pg_engine, "item_id": item_id}
    finally:
        command.upgrade(cfg, "head")
        cleanup = factory()
        _clean(cleanup)
        cleanup.close()


class TestPgDowngradeUpgrade:
    def test_downgrade_drops_tables_and_columns(self, pg_roundtrip) -> None:
        ctx = pg_roundtrip
        command.downgrade(ctx["cfg"], "0005_m5_experiments")
        insp = inspect(ctx["engine"])
        tables = set(insp.get_table_names())
        assert not set(NEW_TABLES) & tables
        cols = {c["name"] for c in insp.get_columns("knowledge_item")}
        assert not set(ITEM_NEW_COLUMNS) & cols
        with ctx["engine"].connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            content = conn.execute(
                text("SELECT content FROM knowledge_item WHERE id=:id"), {"id": ctx["item_id"]}
            ).scalar_one()
        assert version == "0005_m5_experiments"
        assert content == "entanglement correlates particles"  # V1 数据无损

    def test_upgrade_restores_and_backfills_extra_metadata(self, pg_roundtrip) -> None:
        ctx = pg_roundtrip
        command.downgrade(ctx["cfg"], "0005_m5_experiments")
        command.upgrade(ctx["cfg"], "head")
        insp = inspect(ctx["engine"])
        assert set(NEW_TABLES) <= set(insp.get_table_names())
        with ctx["engine"].connect() as conn:
            row = conn.execute(
                text(
                    "SELECT title, content, extra_metadata, source_payload_hash "
                    "FROM knowledge_item WHERE id=:id"
                ),
                {"id": ctx["item_id"]},
            ).fetchone()
        assert tuple(row) == ("historical knowledge", "entanglement correlates particles", "{}", None)

    def test_v1_search_works_after_roundtrip(self, pg_roundtrip) -> None:
        """降级删列再升级后，V1 PG 全文检索（触发器 + 回填）仍命中历史知识。"""
        ctx = pg_roundtrip
        command.downgrade(ctx["cfg"], "0005_m5_experiments")
        command.upgrade(ctx["cfg"], "head")
        factory = sessionmaker(bind=ctx["engine"], autoflush=False, expire_on_commit=False)
        sess = factory()
        try:
            hits = PostgresFullTextIndex(sess).search("entanglement", 10)
            assert ctx["item_id"] in [str(h[0]) for h in hits]
            new = _item(sess, "thermodynamics entropy", "entropy measures disorder")
            assert new.id in [str(h[0]) for h in PostgresFullTextIndex(sess).search("entropy", 10)]
        finally:
            sess.close()

    def test_roundtrip_repeatable(self, pg_roundtrip) -> None:
        """连续两次 downgrade→upgrade 均成功（幂等，无残留对象冲突）。"""
        ctx = pg_roundtrip
        for _ in range(2):
            command.downgrade(ctx["cfg"], "0005_m5_experiments")
            command.upgrade(ctx["cfg"], "head")
        insp = inspect(ctx["engine"])
        assert set(NEW_TABLES) <= set(insp.get_table_names())
        with ctx["engine"].connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert version == "0006_v2_markdown_kb"