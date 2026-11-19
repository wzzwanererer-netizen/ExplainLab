"""V2 A1 数据模型真实 SQLite 测试（迁移 0006 + ORM）。

覆盖两条建表路径的一致性（API 测试走 Base.metadata.create_all，迁移走 Alembic）、
唯一约束（含非空 normalized_link_key 修复 alias NULL≠NULL）、外键 CASCADE/SET NULL、
append-only 审计快照、旧数据无损升级、租约锁表与 ORM 默认值。

全部使用真实临时 SQLite 文件库与真实 SQL，不用假数据替代。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import inspect, text
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

BACKEND_DIR = Path(__file__).resolve().parents[1]

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


@pytest.fixture()
def engine(tmp_path: Path):
    eng = create_engine_from_url(f"sqlite:///{tmp_path / 'v2_models.db'}")
    Base.metadata.create_all(eng)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture()
def session(engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    sess = factory()
    try:
        yield sess
    finally:
        sess.close()


def _item(session: Session, title: str = "知识图谱的定义", content: str = "正文") -> KnowledgeItemORM:
    row = KnowledgeItemORM(title=title, content=content, status="active")
    session.add(row)
    session.commit()
    return row


def _link(session: Session, source: str, key: str, **kwargs) -> KnowledgeLinkORM:
    row = KnowledgeLinkORM(
        source_item_id=source,
        target_title=kwargs.pop("target_title", "目标"),
        normalized_link_key=key,
        **kwargs,
    )
    session.add(row)
    session.commit()
    return row


class TestSchemaPaths:
    def test_create_all_creates_new_tables_and_columns(self, engine):
        insp = inspect(engine)
        tables = set(insp.get_table_names())
        assert set(NEW_TABLES) <= tables
        item_cols = {c["name"] for c in insp.get_columns("knowledge_item")}
        assert set(ITEM_NEW_COLUMNS) <= item_cols

    def test_alembic_and_create_all_schemas_match(self, tmp_path: Path, monkeypatch):
        """两条建表路径必须产出同一 schema（列/类型/可空/默认/索引/唯一/外键）。"""
        orm_url = f"sqlite:///{tmp_path / 'orm_path.db'}"
        mig_url = f"sqlite:///{tmp_path / 'mig_path.db'}"
        orm_engine = create_engine_from_url(orm_url)
        Base.metadata.create_all(orm_engine)
        monkeypatch.setenv("DATABASE_URL", mig_url)
        get_settings.cache_clear()
        try:
            command.upgrade(_alembic_cfg(), "head")
            mig_engine = create_engine_from_url(mig_url)
            try:
                orm_insp, mig_insp = inspect(orm_engine), inspect(mig_engine)
                for table in (*NEW_TABLES, "knowledge_item"):
                    assert _columns(orm_insp, table) == _columns(mig_insp, table), table
                    assert _indexes(orm_insp, table) == _indexes(mig_insp, table), table
                    assert _uniques(orm_insp, table) == _uniques(mig_insp, table), table
                    assert _fks(orm_insp, table) == _fks(mig_insp, table), table
                    assert orm_insp.get_pk_constraint(table)["constrained_columns"] == (
                        mig_insp.get_pk_constraint(table)["constrained_columns"]
                    ), table
            finally:
                mig_engine.dispose()
        finally:
            get_settings.cache_clear()
            orm_engine.dispose()

    def test_v1_tables_unchanged_by_0006(self, tmp_path: Path, monkeypatch):
        """0006 为 additive：V1 既有表的列/索引/外键不因升级而改变。"""
        url = f"sqlite:///{tmp_path / 'v1_shape.db'}"
        monkeypatch.setenv("DATABASE_URL", url)
        get_settings.cache_clear()
        try:
            cfg = _alembic_cfg()
            command.upgrade(cfg, "0005_m5_experiments")
            engine = create_engine_from_url(url)
            try:
                before = {
                    t: (_columns(inspect(engine), t), _indexes(inspect(engine), t),
                        _fks(inspect(engine), t))
                    for t in (
                        "knowledge_space", "conversation", "message", "source_ref",
                        "knowledge_relation", "knowledge_version", "review_request",
                        "knowledge_vector", "experiment_session", "experiment_attempt",
                    )
                }
                item_before = _columns(inspect(engine), "knowledge_item")
                command.upgrade(cfg, "head")
                after = {
                    t: (_columns(inspect(engine), t), _indexes(inspect(engine), t),
                        _fks(inspect(engine), t))
                    for t in before
                }
                assert after == before
                item_after = _columns(inspect(engine), "knowledge_item")
                # knowledge_item 只增列，旧列定义不变
                assert {c[0]: c[1:] for c in item_after if c[0] in {x[0] for x in item_before}} == {
                    c[0]: c[1:] for c in item_before
                }
                assert {c[0] for c in item_after} - {c[0] for c in item_before} == set(
                    ITEM_NEW_COLUMNS
                )
            finally:
                engine.dispose()
        finally:
            get_settings.cache_clear()


def _columns(insp, table: str):
    return sorted(
        (c["name"], str(c["type"]), c["nullable"], c.get("default"))
        for c in insp.get_columns(table)
    )


def _indexes(insp, table: str):
    return sorted(
        (i["name"], tuple(i["column_names"]), i["unique"]) for i in insp.get_indexes(table)
    )


def _uniques(insp, table: str):
    return sorted(
        (u["name"], tuple(u["column_names"])) for u in insp.get_unique_constraints(table)
    )


def _fks(insp, table: str):
    return sorted(
        (
            tuple(f["constrained_columns"]),
            f["referred_table"],
            tuple(f["referred_columns"]),
            f.get("options", {}).get("ondelete"),
        )
        for f in insp.get_foreign_keys(table)
    )


class TestLegacyDataLossless:
    def test_upgrade_0005_to_0006_keeps_old_rows(self, tmp_path: Path, monkeypatch):
        """先有 V1 数据再升级：title/content/status/时间原样保留，extra_metadata 回填 '{}'。"""
        url = f"sqlite:///{tmp_path / 'legacy.db'}"
        monkeypatch.setenv("DATABASE_URL", url)
        get_settings.cache_clear()
        try:
            cfg = _alembic_cfg()
            command.upgrade(cfg, "0005_m5_experiments")
            engine = create_engine_from_url(url)
            try:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "INSERT INTO knowledge_item "
                            "(id, title, content, status, created_at, updated_at) VALUES "
                            "('legacy-1', '旧知识', '# 已经是 Markdown\n\n[[另一条]]', 'active', "
                            "'2026-11-15 08:00:00', '2026-11-15 09:30:00')"
                        )
                    )
                    conn.execute(
                        text(
                            "INSERT INTO knowledge_item "
                            "(id, title, content, status, created_at, updated_at) VALUES "
                            "('legacy-2', '纯文本旧知识', '第一行\n第二行', 'draft', "
                            "'2026-11-15 08:00:00', '2026-11-15 08:00:00')"
                        )
                    )
                command.upgrade(cfg, "head")
                with engine.connect() as conn:
                    rows = conn.execute(
                        text(
                            "SELECT id, title, content, status, extra_metadata, "
                            "source_payload_hash, source_content_hash, source_instance_id, "
                            "created_at, updated_at FROM knowledge_item ORDER BY id"
                        )
                    ).fetchall()
                assert len(rows) == 2
                first, second = rows
                assert first[0] == "legacy-1"
                assert first[1] == "旧知识"
                assert first[2] == "# 已经是 Markdown\n\n[[另一条]]"
                assert first[3] == "active"
                assert first[4] == "{}"
                assert first[5] is None and first[6] is None and first[7] is None
                assert str(first[8]).startswith("2026-11-15 08:00:00")
                assert second[2] == "第一行\n第二行"
                assert second[4] == "{}"
            finally:
                engine.dispose()
        finally:
            get_settings.cache_clear()

    def test_extra_metadata_server_default_on_raw_insert(self, session: Session):
        """不经 ORM 的裸 INSERT 也得到 '{}'（server_default），NOT NULL 不阻塞旧写入路径。"""
        session.execute(
            text(
                "INSERT INTO knowledge_item (id, title, content, status, created_at, updated_at) "
                "VALUES ('raw-1', '裸插入', '正文', 'draft', "
                "'2026-11-18 00:00:00', '2026-11-18 00:00:00')"
            )
        )
        session.commit()
        value = session.execute(
            text("SELECT extra_metadata FROM knowledge_item WHERE id='raw-1'")
        ).scalar_one()
        assert value == "{}"

    def test_extra_metadata_not_null(self, session: Session):
        item = _item(session)
        with pytest.raises(IntegrityError):
            session.execute(
                text("UPDATE knowledge_item SET extra_metadata=NULL WHERE id=:id"),
                {"id": item.id},
            )
            session.commit()
        session.rollback()


class TestTagConstraints:
    def test_tag_name_unique(self, session: Session):
        session.add(TagORM(name="概念"))
        session.commit()
        session.add(TagORM(name="概念"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_item_tag_composite_pk_dedup(self, session: Session):
        item = _item(session)
        tag = TagORM(name="图谱")
        session.add(tag)
        session.commit()
        session.add(ItemTagORM(item_id=item.id, tag_id=tag.id))
        session.commit()
        session.add(ItemTagORM(item_id=item.id, tag_id=tag.id))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_item_tag_cascade_on_item_delete(self, session: Session):
        item = _item(session)
        tag = TagORM(name="图谱")
        session.add(tag)
        session.commit()
        session.add(ItemTagORM(item_id=item.id, tag_id=tag.id))
        session.commit()
        session.execute(text("DELETE FROM knowledge_item WHERE id=:id"), {"id": item.id})
        session.commit()
        assert session.execute(text("SELECT count(*) FROM item_tag")).scalar_one() == 0
        # 标签字典本身保留（不随条目删除）
        assert session.execute(text("SELECT count(*) FROM tag")).scalar_one() == 1

    def test_item_tag_cascade_on_tag_delete(self, session: Session):
        item = _item(session)
        tag = TagORM(name="图谱")
        session.add(tag)
        session.commit()
        session.add(ItemTagORM(item_id=item.id, tag_id=tag.id))
        session.commit()
        session.execute(text("DELETE FROM tag WHERE id=:id"), {"id": tag.id})
        session.commit()
        assert session.execute(text("SELECT count(*) FROM item_tag")).scalar_one() == 0
        assert session.execute(text("SELECT count(*) FROM knowledge_item")).scalar_one() == 1


class TestLinkConstraints:
    def test_unique_source_and_key_even_with_different_alias(self, session: Session):
        """核心修复：alias 不同/为 NULL 也不得绕过 (source, normalized_link_key) 唯一。"""
        item = _item(session)
        _link(session, item.id, "knowledge graph", alias=None)
        session.add(
            KnowledgeLinkORM(
                source_item_id=item.id,
                target_title="Knowledge Graph",
                alias="另一个别名",
                normalized_link_key="knowledge graph",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_unique_source_and_key_both_null_alias(self, session: Session):
        item = _item(session)
        _link(session, item.id, "same key", alias=None)
        session.add(
            KnowledgeLinkORM(
                source_item_id=item.id,
                target_title="same key",
                alias=None,
                normalized_link_key="same key",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_same_key_different_source_allowed(self, session: Session):
        a = _item(session, title="A")
        b = _item(session, title="B")
        _link(session, a.id, "shared key")
        _link(session, b.id, "shared key")
        assert session.execute(text("SELECT count(*) FROM knowledge_link")).scalar_one() == 2

    def test_normalized_key_not_null(self, session: Session):
        item = _item(session)
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO knowledge_link (id, source_item_id, target_title, "
                    "normalized_link_key, link_normalization_version, resolution, cross_space, "
                    "created_at, updated_at) VALUES ('l-null', :src, 'T', NULL, 1, 'missing', 0, "
                    "'2026-11-18 00:00:00', '2026-11-18 00:00:00')"
                ),
                {"src": item.id},
            )
            session.commit()
        session.rollback()

    def test_orm_defaults(self, session: Session):
        item = _item(session)
        link = _link(session, item.id, "t")
        assert link.link_normalization_version == 1
        assert link.resolution == "missing"
        assert link.cross_space is False
        assert link.target_item_id is None
        assert link.created_at <= link.updated_at

    def test_source_cascade_target_set_null(self, session: Session):
        """源删除→链接消失（CASCADE）；目标删除→链接保留但 target 置 NULL（SET NULL）。"""
        source = _item(session, title="源条目")
        target = _item(session, title="目标条目")
        link = _link(
            session, source.id, "目标条目", target_title="目标条目",
            target_item_id=target.id, resolution="resolved",
        )
        session.execute(text("DELETE FROM knowledge_item WHERE id=:id"), {"id": target.id})
        session.commit()
        session.refresh(link)
        assert link.target_item_id is None
        assert link.target_title == "目标条目"  # 原始字面保留，可重新解析
        assert link.normalized_link_key == "目标条目"
        session.execute(text("DELETE FROM knowledge_item WHERE id=:id"), {"id": source.id})
        session.commit()
        assert session.execute(text("SELECT count(*) FROM knowledge_link")).scalar_one() == 0

    def test_backlink_query_by_stable_id(self, session: Session):
        """反向链接按稳定 ID 查询：目标改名后反链不断（改名只改 title，不改 id）。"""
        target = _item(session, title="原标题")
        s1 = _item(session, title="引用者一")
        s2 = _item(session, title="引用者二")
        _link(session, s1.id, "原标题", target_item_id=target.id, resolution="resolved")
        _link(session, s2.id, "原标题", target_item_id=target.id, resolution="resolved")
        session.execute(
            text("UPDATE knowledge_item SET title='改名后的标题' WHERE id=:id"),
            {"id": target.id},
        )
        session.commit()
        backlinks = session.execute(
            text("SELECT source_item_id FROM knowledge_link WHERE target_item_id=:tid"),
            {"tid": target.id},
        ).scalars().all()
        assert set(backlinks) == {s1.id, s2.id}

    def test_cross_space_boolean_roundtrip(self, session: Session):
        item = _item(session)
        link = _link(
            session, item.id, "其它空间条目", resolution="cross_space", cross_space=True
        )
        session.refresh(link)
        assert link.cross_space is True
        raw = session.execute(
            text("SELECT cross_space FROM knowledge_link WHERE id=:id"), {"id": link.id}
        ).scalar_one()
        assert raw in (1, True)


class TestAttachmentConstraints:
    def test_storage_key_shared_and_reference_count_derived(self, session: Session):
        a = _item(session, title="A")
        b = _item(session, title="B")
        key = "k" * 64
        for item in (a, b):
            session.add(
                AttachmentORM(
                    item_id=item.id, filename="图.png", mime="image/png", size=10,
                    storage_key=key, content_hash="c" * 64,
                )
            )
        session.commit()
        count = session.execute(
            text("SELECT count(*) FROM attachment WHERE storage_key=:k"), {"k": key}
        ).scalar_one()
        assert count == 2  # 引用数由 COUNT 派生，无冗余计数列

    def test_cascade_on_item_delete(self, session: Session):
        item = _item(session)
        session.add(
            AttachmentORM(
                item_id=item.id, filename="f.png", mime="image/png", size=1,
                storage_key="key-1", content_hash="h" * 64,
            )
        )
        session.commit()
        session.execute(text("DELETE FROM knowledge_item WHERE id=:id"), {"id": item.id})
        session.commit()
        assert session.execute(text("SELECT count(*) FROM attachment")).scalar_one() == 0

    def test_storage_key_index_exists(self, engine):
        names = {i["name"] for i in inspect(engine).get_indexes("attachment")}
        assert "ix_attachment_storage_key" in names


class TestTagChangeLogAudit:
    def test_append_only_snapshot_survives_item_delete(self, session: Session):
        """条目删除后 item_id 置 NULL，快照仍保留身份与标题（口径 C）。"""
        item = _item(session, title="会被删除的条目")
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
        session.add(record)
        session.commit()
        session.execute(text("DELETE FROM knowledge_item WHERE id=:id"), {"id": item.id})
        session.commit()
        session.refresh(record)
        assert record.item_id is None
        assert record.item_id_snapshot == item.id
        assert record.item_title_snapshot == "会被删除的条目"
        assert record.old_tags == '["a"]'
        assert record.new_tags == '["a","b"]'
        assert record.correlation_id == "op-1"

    def test_snapshot_not_null(self, session: Session):
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO tag_change_log (id, item_id_snapshot, item_title_snapshot, "
                    "old_tags, new_tags, changed_at) VALUES ('t-null', NULL, '标题', '[]', '[]', "
                    "'2026-11-18 00:00:00')"
                )
            )
            session.commit()
        session.rollback()

    def test_multiple_records_per_item_accumulate(self, session: Session):
        item = _item(session)
        for old, new in (("[]", '["a"]'), ('["a"]', '["a","b"]'), ('["a","b"]', '["b"]')):
            session.add(
                TagChangeLogORM(
                    item_id=item.id, item_id_snapshot=item.id,
                    item_title_snapshot=item.title, old_tags=old, new_tags=new,
                )
            )
        session.commit()
        rows = session.execute(
            text("SELECT old_tags, new_tags FROM tag_change_log WHERE item_id=:id"),
            {"id": item.id},
        ).fetchall()
        assert len(rows) == 3  # 追加而非覆盖


class TestGcTaskAndLock:
    def test_gc_defaults_and_indexes(self, session: Session, engine):
        task = GcTaskORM(storage_key="key-1")
        session.add(task)
        session.commit()
        assert task.status == "pending"
        assert task.lease_token == 0
        assert task.attempts == 0
        assert task.lease_owner is None
        assert task.quarantine_path is None
        names = {i["name"] for i in inspect(engine).get_indexes("gc_task")}
        assert {"ix_gc_task_status_next_retry_at", "ix_gc_task_storage_key"} <= names

    def test_gc_cancelled_terminal_state_persisted(self, session: Session):
        task = GcTaskORM(storage_key="key-1", status="cancelled", attempts=1, lease_token=2)
        session.add(task)
        session.commit()
        session.refresh(task)
        assert task.status == "cancelled"
        assert task.quarantine_path is None  # cancelled 不删任何文件

    def test_gc_quarantine_fields(self, session: Session):
        task = GcTaskORM(
            storage_key="key-1",
            status="running",
            lease_owner="worker-1",
            lease_token=5,
            attempts=2,
            quarantine_path="attachments/_quarantine/key-1.op-9",
        )
        session.add(task)
        session.commit()
        session.refresh(task)
        assert task.quarantine_path == "attachments/_quarantine/key-1.op-9"
        assert task.lease_token == 5

    def test_storage_lock_pk_unique(self, session: Session):
        from knowledge_core.domain.entities import utcnow

        expires = utcnow()
        session.add(
            StorageLockORM(storage_key="key-1", owner="w1", lease_token=1, lease_expires_at=expires)
        )
        session.commit()
        session.add(
            StorageLockORM(storage_key="key-1", owner="w2", lease_token=2, lease_expires_at=expires)
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_storage_lock_takeover_after_expiry(self, session: Session):
        """过期接管：条件更新（owner/token 变化）成功，旧 token 释放失配（fencing 基础）。"""
        from datetime import timedelta

        from knowledge_core.domain.entities import utcnow

        now = utcnow()
        session.add(
            StorageLockORM(
                storage_key="key-1", owner="old", lease_token=1,
                lease_expires_at=now - timedelta(seconds=1),
            )
        )
        session.commit()
        result = session.execute(
            text(
                "UPDATE storage_lock SET owner='new', lease_token=lease_token+1, "
                "lease_expires_at=:expires WHERE storage_key='key-1' AND lease_expires_at < :now"
            ),
            {"expires": now + timedelta(seconds=30), "now": now},
        )
        session.commit()
        assert result.rowcount == 1
        row = session.execute(
            text("SELECT owner, lease_token FROM storage_lock WHERE storage_key='key-1'")
        ).fetchone()
        assert row[0] == "new"
        assert row[1] == 2
        # 旧 owner + 旧 token 释放：rowcount==0（防误释放）
        stale = session.execute(
            text(
                "DELETE FROM storage_lock WHERE storage_key='key-1' AND owner='old' AND lease_token=1"
            )
        )
        session.commit()
        assert stale.rowcount == 0
        assert session.execute(text("SELECT count(*) FROM storage_lock")).scalar_one() == 1


class TestImportOriginConstraints:
    def test_defaults_and_indexes(self, session: Session, engine):
        item = _item(session)
        origin = ImportOriginORM(
            item_id=item.id,
            source_payload_hash="p" * 64,
            source_content_hash="c" * 64,
            source_document_id=item.id,
        )
        session.add(origin)
        session.commit()
        assert origin.source_canonicalization_version == 1
        assert origin.source_instance_id is None
        assert origin.import_batch_id is None
        names = {i["name"] for i in inspect(engine).get_indexes("import_origin")}
        assert {"ix_import_origin_item_id", "ix_import_origin_source_payload_hash"} <= names

    def test_cascade_on_item_delete(self, session: Session):
        item = _item(session)
        session.add(
            ImportOriginORM(
                item_id=item.id, source_payload_hash="p" * 64,
                source_content_hash="c" * 64, source_document_id=item.id,
            )
        )
        session.commit()
        session.execute(text("DELETE FROM knowledge_item WHERE id=:id"), {"id": item.id})
        session.commit()
        assert session.execute(text("SELECT count(*) FROM import_origin")).scalar_one() == 0

    def test_source_hash_lookup_for_idempotency(self, session: Session):
        """按源 payload_hash + canonicalization_version 查历史（幂等判定基础）。"""
        item = _item(session)
        session.add(
            ImportOriginORM(
                item_id=item.id, source_payload_hash="p" * 64,
                source_content_hash="c" * 64, source_document_id=item.id,
                source_instance_id="instance-A", source_canonicalization_version=1,
            )
        )
        session.commit()
        hit = session.execute(
            text(
                "SELECT item_id FROM import_origin WHERE source_payload_hash=:h "
                "AND source_canonicalization_version=1"
            ),
            {"h": "p" * 64},
        ).scalars().all()
        assert hit == [item.id]
        miss = session.execute(
            text(
                "SELECT item_id FROM import_origin WHERE source_payload_hash=:h "
                "AND source_canonicalization_version=2"
            ),
            {"h": "p" * 64},
        ).scalars().all()
        assert miss == []  # 版本不同不可直接比 hash

    def test_item_source_identity_columns(self, session: Session):
        item = _item(session)
        item.source_payload_hash = "p" * 64
        item.source_content_hash = "c" * 64
        item.source_instance_id = "instance-A"
        item.extra_metadata = '{"unknown_frontmatter": true}'
        session.commit()
        session.refresh(item)
        assert item.source_payload_hash == "p" * 64
        assert item.source_instance_id == "instance-A"
        assert item.extra_metadata == '{"unknown_frontmatter": true}'