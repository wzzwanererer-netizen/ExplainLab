"""D23 身份初始化、Journal 恢复/归档与 ROTATE 验收（SQLite 真实 DB + FS）。

覆盖身份状态 1/2a/2b/3/4、ImportOrigin 多记录审计、MATERIALIZE/ROTATE
Journal 恢复与故障注入。Windows 目录 fsync 为 best-effort，不宣称断电持久。
"""

from __future__ import annotations

import json
import uuid
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.db.session import get_engine, get_session_factory
from app.models import ImportOriginORM, KnowledgeItemORM
from app.services.markdown import MarkdownImportDocument
from app.services.source_identity import (
    JOURNAL_CORRUPT,
    SOURCE_DOCUMENT_UNMATERIALIZED,
    SOURCE_IDENTITY_INCONSISTENT,
    SOURCE_IDENTITY_ORPHAN,
    JournalStore,
    SourceIdentityError,
    SourceIdentityService,
    build_identity_snapshots,
    identity_audit_digest,
    item_identity_digest,
    materialization_digest,
)
from knowledge_core.domain.entities import KnowledgeStatus

X = "550e8400-e29b-41d4-a716-446655440000"
Y = "770e8400-e29b-41d4-a716-446655440002"
Z = "880e8400-e29b-41d4-a716-446655440004"
D1 = "660e8400-e29b-41d4-a716-446655440001"
D2 = "660e8400-e29b-41d4-a716-446655440003"
PAYLOAD = "a" * 64
PAYLOAD2 = "b" * 64
CONTENT = "c" * 64


def _new_item(
    *,
    title: str = "条目",
    source_instance: str | None = None,
    extra_metadata: dict | None = None,
    item_id: str | None = None,
) -> str:
    session = get_session_factory()()
    try:
        item = KnowledgeItemORM(
            id=item_id or str(uuid.uuid4()),
            title=title,
            content=f"{title}正文",
            status=KnowledgeStatus.DRAFT.value,
            space_id=None,
            extra_metadata=json.dumps(extra_metadata or {}),
            source_instance_id=source_instance,
        )
        session.add(item)
        session.commit()
        return item.id
    finally:
        session.close()


def _new_origin(
    item_id: str,
    *,
    instance: str | None = X,
    document: str | None = D1,
    payload: str = PAYLOAD,
    origin_id: str | None = None,
) -> str:
    session = get_session_factory()()
    try:
        origin = ImportOriginORM(
            id=origin_id or str(uuid.uuid4()),
            item_id=item_id,
            source_payload_hash=payload,
            source_content_hash=CONTENT,
            source_instance_id=instance,
            source_document_id=document,
            source_canonicalization_version=1,
        )
        session.add(origin)
        session.commit()
        return origin.id
    finally:
        session.close()


def _classify(client: TestClient, item_id: str):
    session = get_session_factory()()
    try:
        return client.app.state.source_identity.classify(session, item_id)
    finally:
        session.close()


def _snapshot(client: TestClient, item_id: str) -> dict:
    session = get_session_factory()()
    try:
        return next(
            snap
            for snap in build_identity_snapshots(session)
            if snap["item_id"] == item_id
        )
    finally:
        session.close()


def _digest() -> str:
    session = get_session_factory()()
    try:
        return identity_audit_digest(session)
    finally:
        session.close()


def _item(item_id: str) -> KnowledgeItemORM:
    session = get_session_factory()()
    try:
        item = session.get(KnowledgeItemORM, item_id)
        assert item is not None
        session.expunge(item)
        return item
    finally:
        session.close()


def _journal(client: TestClient) -> JournalStore:
    return JournalStore(client.app.state.source_identity.journal.data_dir)


def _restart(client: TestClient, settings: Settings) -> SourceIdentityService:
    return SourceIdentityService(
        get_session_factory(),
        settings.data_dir,
        client.app.state.source_instance_store,
    )


def _entry(item_id: str, instance: str) -> dict:
    entry = {
        "item_id": item_id,
        "source_instance_id": instance,
        "source_document_id": item_id,
        "identity_record_version": 1,
    }
    entry["item_identity_digest"] = item_identity_digest(entry)
    return entry


def _prepare_materialize(
    client: TestClient, item_id: str, instance: str, *, phase: str = "PREPARED"
):
    identity = client.app.state.source_identity
    session = get_session_factory()()
    try:
        expected = identity_audit_digest(
            session, materialized={item_id: (instance, item_id)}
        )
    finally:
        session.close()
    record = identity._new_record(
        kind="MATERIALIZE",
        phase=phase,
        item_id=item_id,
        source_instance_id=instance,
        source_document_id=item_id,
        items=[_entry(item_id, instance)],
        audit_digest=expected,
    )
    identity.journal.write_current(record)
    if phase == "COMMITTED":
        session = get_session_factory()()
        try:
            row = session.get(KnowledgeItemORM, item_id)
            assert row is not None
            row.source_instance_id = instance
            session.commit()
        finally:
            session.close()
    return record


def _materialized_local(client: TestClient, title: str) -> tuple[str, str]:
    item_id = _new_item(title=title)
    response = client.get(f"/api/knowledge/{item_id}/markdown")
    assert response.status_code == 200
    instance = client.app.state.source_instance_store.read()
    assert _item(item_id).source_instance_id == instance
    assert _classify(client, item_id).state == "2b"
    return item_id, instance


def _assert_record_conflict_readonly(
    client: TestClient, item_id: str, instance: str
) -> dict:
    """并存冲突：拒绝认领/物化/导出修复，且 DB/Journal 原始数据零变化。"""
    identity = client.app.state.source_identity
    journal = _journal(client)
    before_digest = _digest()
    before_snapshot = _snapshot(client, item_id)
    before_archive = len(journal.read_archive())
    before_source = _item(item_id).source_instance_id

    classified = _classify(client, item_id)
    assert classified.state == "3"
    assert classified.source_instance_id is None
    assert classified.source_document_id is None

    export = client.get(f"/api/knowledge/{item_id}/markdown")
    assert export.status_code == 200
    assert "X-ExplainLab-Source-Instance-Id" not in export.headers
    assert "source_instance_id" not in export.text

    with pytest.raises(SourceIdentityError) as excinfo:
        identity.ensure_local_export_identity(item_id)
    assert excinfo.value.code == SOURCE_DOCUMENT_UNMATERIALIZED
    with pytest.raises(SourceIdentityError) as excinfo:
        identity.materialize(item_id)
    assert excinfo.value.code == SOURCE_DOCUMENT_UNMATERIALIZED

    assert _digest() == before_digest
    assert _snapshot(client, item_id) == before_snapshot
    assert _item(item_id).source_instance_id == before_source == instance
    assert len(journal.read_archive()) == before_archive
    assert journal.current.exists() is False
    return before_snapshot


class TestIdentityStates:
    def test_state_2a_first_export_materializes_once(self, client: TestClient):
        created = client.post(
            "/api/knowledge", json={"title": "本地", "content": "本地正文"}
        ).json()
        item_id = UUID(created["id"])
        assert _classify(client, str(item_id)).state == "2a"
        store_id = client.app.state.source_instance_store.read()

        first = client.get(f"/api/knowledge/{item_id}/markdown")
        assert first.status_code == 200
        assert first.headers["X-ExplainLab-Source-Instance-Id"] == store_id
        assert first.headers["X-ExplainLab-Source-Document-Id"] == str(item_id)
        assert _item(str(item_id)).source_instance_id == store_id
        assert _classify(client, str(item_id)).state == "2b"
        journal = _journal(client)
        assert journal.current.exists() is False
        records = journal.read_archive()
        assert len(records) == 1
        assert records[0]["kind"] == "MATERIALIZE"
        assert records[0]["phase"] == "COMMITTED"

        again = client.get(f"/api/knowledge/{item_id}/markdown")
        assert again.headers["X-ExplainLab-Source-Instance-Id"] == store_id
        assert again.headers["X-ExplainLab-Document-Payload-Hash"] == (
            first.headers["X-ExplainLab-Document-Payload-Hash"]
        )
        assert len(journal.read_archive()) == 1

    def test_restart_keeps_2b_and_hash_stable(
        self, client: TestClient, settings: Settings
    ):
        created = client.post(
            "/api/knowledge", json={"title": "重启", "content": "正文"}
        ).json()
        item_id = UUID(created["id"])
        first = client.get(f"/api/knowledge/{item_id}/markdown")
        restarted = _restart(client, settings)
        session = get_session_factory()()
        try:
            classified = restarted.classify(session, item_id)
        finally:
            session.close()
        assert classified.state == "2b"
        assert classified.source_instance_id == (
            first.headers["X-ExplainLab-Source-Instance-Id"]
        )
        again = client.get(f"/api/knowledge/{item_id}/markdown")
        assert again.headers["X-ExplainLab-Document-Payload-Hash"] == (
            first.headers["X-ExplainLab-Document-Payload-Hash"]
        )
        assert len(_journal(client).read_archive()) == 1

    def test_state_4_without_committed_evidence_is_not_claimed(
        self, client: TestClient
    ):
        store_id = client.app.state.source_instance_store.read()
        item_id = _new_item(title="无证据", source_instance=store_id)
        assert _classify(client, item_id).state == "4"
        response = client.get(f"/api/knowledge/{item_id}/markdown")
        # 状态 4 不得猜测或认领：导出仍可用，但不写来源身份头/元数据。
        assert response.status_code == 200
        assert "X-ExplainLab-Source-Instance-Id" not in response.headers
        assert "source_instance_id" not in response.text
        assert _item(item_id).source_instance_id == store_id
        assert _journal(client).read_archive() == []

    def test_imported_item_state_1_uses_origin_identity(self, client: TestClient):
        client.app.state.markdown_service.import_documents(
            [
                MarkdownImportDocument(
                    content=(
                        "---\ntitle: 导入\n"
                        f"source_instance_id: {X}\n"
                        f"source_document_id: {D1}\n---\n正文"
                    ),
                    filename="id.md",
                )
            ]
        )
        session = get_session_factory()()
        try:
            item_id = session.scalar(select(KnowledgeItemORM.id))
        finally:
            session.close()
        assert item_id is not None
        classified = _classify(client, item_id)
        assert classified.state == "1"
        assert classified.source_instance_id == X
        assert classified.source_document_id == D1
        response = client.get(f"/api/knowledge/{item_id}/markdown")
        assert response.headers["X-ExplainLab-Source-Instance-Id"] == X
        assert response.headers["X-ExplainLab-Source-Document-Id"] == D1

    def test_incomplete_origin_is_state_3_zero_claim(self, client: TestClient):
        item_id = _new_item(title="残缺", source_instance=X)
        _new_origin(item_id, instance=None)
        classified = _classify(client, item_id)
        assert classified.state == "3"
        assert classified.source_instance_id is None
        snap = _snapshot(client, item_id)
        assert snap["import_origin_state"] == "incomplete"
        response = client.get(f"/api/knowledge/{item_id}/markdown")
        # 状态 3 不得认领残缺来源：不写来源身份头/元数据，也不覆盖 DB 值。
        assert response.status_code == 200
        assert "X-ExplainLab-Source-Instance-Id" not in response.headers
        assert "source_instance_id" not in response.text
        assert _item(item_id).source_instance_id == X


class TestMaterializeOriginConflict:
    """§22.2：ImportOrigin 与 MATERIALIZE 记录并存一律冲突，不得认领。"""

    def test_single_materialize_plus_single_complete_origin(self, client: TestClient):
        item_id, instance = _materialized_local(client, "并存单条")
        _new_origin(item_id, instance=instance, document=D1)
        snapshot = _assert_record_conflict_readonly(client, item_id, instance)
        assert snapshot["import_origin_state"] == "complete"
        assert snapshot["import_origin_count"] == 1

    def test_single_materialize_plus_multiple_complete_origins(
        self, client: TestClient
    ):
        item_id, instance = _materialized_local(client, "并存多版本")
        _new_origin(item_id, instance=instance, document=D1, payload=PAYLOAD)
        _new_origin(item_id, instance=instance, document=D1, payload=PAYLOAD2)
        snapshot = _assert_record_conflict_readonly(client, item_id, instance)
        assert snapshot["import_origin_state"] == "complete"
        assert snapshot["import_origin_count"] == 2

    def test_materialize_plus_incomplete_origin(self, client: TestClient):
        item_id, instance = _materialized_local(client, "并存残缺")
        _new_origin(item_id, instance=None)
        snapshot = _assert_record_conflict_readonly(client, item_id, instance)
        assert snapshot["import_origin_state"] == "incomplete"
        assert snapshot["incomplete_origin_count"] == 1

    def test_materialize_plus_duplicate_origin(self, client: TestClient):
        item_id, instance = _materialized_local(client, "并存重复")
        _new_origin(item_id, instance=instance, document=D1)
        _new_origin(item_id, instance=instance, document=D1)
        snapshot = _assert_record_conflict_readonly(client, item_id, instance)
        assert snapshot["import_origin_state"] == "duplicate"
        assert snapshot["duplicate_origin_count"] == 2

    def test_materialize_plus_multiple_legal_identity_pairs(self, client: TestClient):
        item_id, instance = _materialized_local(client, "并存多身份")
        _new_origin(item_id, instance=instance, document=D1)
        _new_origin(item_id, instance=instance, document=D2)
        snapshot = _assert_record_conflict_readonly(client, item_id, instance)
        assert snapshot["import_origin_state"] == "conflict"
        assert snapshot["source_instance_id"] is None

    def test_materialize_and_origin_same_instance_id(self, client: TestClient):
        item_id, instance = _materialized_local(client, "并存同实例")
        _new_origin(item_id, instance=instance, document=item_id)
        snapshot = _assert_record_conflict_readonly(client, item_id, instance)
        assert snapshot["import_origins"][0]["source_instance_id"] == instance
        assert snapshot["source_instance_id"] == instance

    def test_materialize_and_origin_different_instance_id(self, client: TestClient):
        item_id, instance = _materialized_local(client, "并存异实例")
        _new_origin(item_id, instance=Y, document=D1)
        snapshot = _assert_record_conflict_readonly(client, item_id, instance)
        assert snapshot["import_origins"][0]["source_instance_id"] == Y
        assert snapshot["import_origin_state"] == "conflict"

    def test_multiple_materialize_records_plus_origin_still_conflict(
        self, client: TestClient
    ):
        item_id, instance = _materialized_local(client, "并存多物化")
        identity = client.app.state.source_identity
        record = identity._new_record(
            kind="MATERIALIZE",
            phase="COMMITTED",
            item_id=item_id,
            source_instance_id=instance,
            source_document_id=item_id,
            items=[_entry(item_id, instance)],
            audit_digest=_digest(),
        )
        identity.journal.archive_committed(record)
        _new_origin(item_id, instance=instance, document=D1)
        snapshot = _assert_record_conflict_readonly(client, item_id, instance)
        assert snapshot["import_origin_state"] == "complete"
        assert len(_journal(client).read_archive()) == 2

    def test_control_normal_import_without_materialize_is_state_1(
        self, client: TestClient
    ):
        item_id = _new_item(source_instance=X)
        _new_origin(item_id)
        assert _classify(client, item_id).state == "1"
        assert _journal(client).read_archive() == []

    def test_control_local_materialize_without_origin_is_state_2b(
        self, client: TestClient
    ):
        item_id, instance = _materialized_local(client, "正常本地")
        assert _classify(client, item_id).state == "2b"
        assert _snapshot(client, item_id)["import_origin_count"] == 0
        assert _item(item_id).source_instance_id == instance


class TestImportOriginAudit:
    def test_single_complete_origin(self, client: TestClient):
        item_id = _new_item(source_instance=X)
        origin_id = _new_origin(item_id)
        snap = _snapshot(client, item_id)
        assert snap["import_origin_count"] == 1
        assert snap["import_origin_state"] == "complete"
        assert snap["incomplete_origin_count"] == 0
        assert snap["invalid_origin_count"] == 0
        assert snap["duplicate_origin_count"] == 0
        assert snap["source_instance_id"] == X
        assert snap["import_origins"][0]["import_origin_id"] == origin_id
        assert snap["import_origins"][0]["status_flags"] == []
        assert snap["import_origin_identity_digest"] is not None

    def test_duplicate_origins_are_kept_and_flagged(self, client: TestClient):
        item_id = _new_item(source_instance=X)
        first = _new_origin(item_id)
        second = _new_origin(item_id)
        snap = _snapshot(client, item_id)
        assert snap["import_origin_count"] == 2
        assert snap["duplicate_origin_count"] == 2
        assert snap["import_origin_state"] == "duplicate"
        assert [row["import_origin_id"] for row in snap["import_origins"]] == sorted(
            [first, second]
        )
        assert all(row["duplicate_group_size"] == 2 for row in snap["import_origins"])
        assert snap["source_instance_id"] is None

    def test_full_plus_incomplete_is_incomplete(self, client: TestClient):
        item_id = _new_item(source_instance=X)
        _new_origin(item_id)
        _new_origin(item_id, instance=None)
        snap = _snapshot(client, item_id)
        assert snap["import_origin_state"] == "incomplete"
        assert snap["incomplete_origin_count"] == 1
        assert snap["source_instance_id"] is None

    def test_two_identity_pairs_are_conflict(self, client: TestClient):
        item_id = _new_item(source_instance=X)
        _new_origin(item_id)
        _new_origin(item_id, document=D2)
        snap = _snapshot(client, item_id)
        assert snap["import_origin_state"] == "conflict"
        assert snap["source_instance_id"] is None
        assert _classify(client, item_id).state == "3"

    def test_db_instance_mismatch_is_conflict(self, client: TestClient):
        item_id = _new_item(source_instance=Y)
        _new_origin(item_id)
        snap = _snapshot(client, item_id)
        assert snap["import_origin_state"] == "conflict"
        assert snap["source_instance_id"] is None

    def test_same_identity_versions_are_complete(self, client: TestClient):
        item_id = _new_item(source_instance=X)
        _new_origin(item_id, payload=PAYLOAD)
        _new_origin(item_id, payload=PAYLOAD2)
        snap = _snapshot(client, item_id)
        assert snap["import_origin_state"] == "complete"
        assert snap["source_instance_id"] == X
        assert snap["source_document_id"] == D1
        assert snap["import_origin_identity_digest"] is None
        assert {row["source_payload_hash"] for row in snap["import_origins"]} == {
            PAYLOAD,
            PAYLOAD2,
        }

    def test_audit_digest_changes_when_raw_origin_changes(self, client: TestClient):
        item_id = _new_item(source_instance=X)
        origin_id = _new_origin(item_id)
        before = _digest()
        session = get_session_factory()()
        try:
            origin = session.get(ImportOriginORM, origin_id)
            assert origin is not None
            origin.source_payload_hash = PAYLOAD2
            session.commit()
        finally:
            session.close()
        assert _digest() != before

    def test_invalid_raw_origin_is_preserved_and_not_claimed(
        self, client: TestClient
    ):
        item_id = _new_item(source_instance=X)
        bad_document = "660E8400-E29B-41D4-A716-446655440001"
        _new_origin(item_id, document=bad_document)
        snap = _snapshot(client, item_id)
        assert snap["import_origin_state"] == "invalid"
        assert snap["invalid_origin_count"] == 1
        assert snap["source_instance_id"] is None
        assert snap["import_origins"][0]["source_document_id"] == bad_document
        assert snap["import_origins"][0]["status_flags"] == ["invalid"]
        assert _classify(client, item_id).state == "3"

    def test_orphan_origin_fails_closed(self, client: TestClient):
        # 真实 SQLite 启用外键，正常 ORM 无法写入孤儿；注入一条损坏 DB 状态，
        # 验证审计入口 fail-closed 而不是静默忽略。
        origin_id = str(uuid.uuid4())
        missing_item = str(uuid.uuid4())
        raw = get_engine().raw_connection()
        try:
            cursor = raw.cursor()
            cursor.execute("PRAGMA foreign_keys=OFF")
            cursor.execute(
                "INSERT INTO import_origin (id, item_id, source_payload_hash, "
                "source_content_hash, source_instance_id, source_document_id, "
                "source_canonicalization_version, imported_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    origin_id,
                    missing_item,
                    PAYLOAD,
                    CONTENT,
                    X,
                    D1,
                    1,
                    "2026-11-22 00:00:00.000000",
                ),
            )
            raw.commit()
            cursor.close()
        finally:
            raw.close()
        with pytest.raises(SourceIdentityError) as excinfo:
            _digest()
        assert excinfo.value.code == SOURCE_IDENTITY_ORPHAN


class TestJournalRecovery:
    def test_prepared_materialize_recovers_db_empty(
        self, client: TestClient, settings: Settings
    ):
        item_id = _new_item()
        instance = client.app.state.source_instance_store.read()
        record = _prepare_materialize(client, item_id, instance)
        assert record["materialization_digest"] == materialization_digest(
            record["materialization_items"]
        )
        _restart(client, settings).recover_if_needed()
        assert _item(item_id).source_instance_id == instance
        journal = _journal(client)
        assert journal.current.exists() is False
        archived = journal.read_archive()
        assert len(archived) == 1
        assert archived[0]["operation_id"] == record["operation_id"]
        assert archived[0]["phase"] == "COMMITTED"

    def test_prepared_materialize_other_db_value_fails_closed(
        self, client: TestClient, settings: Settings
    ):
        item_id = _new_item(source_instance=Y)
        instance = client.app.state.source_instance_store.read()
        _prepare_materialize(client, item_id, instance)
        with pytest.raises(SourceIdentityError) as excinfo:
            _restart(client, settings).recover_if_needed()
        assert excinfo.value.code == SOURCE_IDENTITY_INCONSISTENT
        assert _item(item_id).source_instance_id == Y
        assert _journal(client).current.exists()

    def test_corrupt_current_blocks_import_before_any_write(
        self, client: TestClient
    ):
        item_id = _new_item()
        journal = _journal(client)
        journal.current.write_text('{"schema_version":1}', encoding="utf-8")
        before = _item(item_id)
        with pytest.raises(SourceIdentityError) as excinfo:
            client.app.state.markdown_service.import_documents(
                [MarkdownImportDocument(content="正文", filename="x.md")]
            )
        assert excinfo.value.code == JOURNAL_CORRUPT
        assert _item(item_id).source_instance_id == before.source_instance_id

    def test_committed_unarchived_only_archives_without_db_rewrite(
        self, client: TestClient, settings: Settings
    ):
        item_id = _new_item()
        instance = client.app.state.source_instance_store.read()
        record = _prepare_materialize(client, item_id, instance, phase="COMMITTED")
        updated_at = _item(item_id).updated_at
        _restart(client, settings).recover_if_needed()
        assert _item(item_id).updated_at == updated_at
        journal = _journal(client)
        assert journal.current.exists() is False
        archived = journal.read_archive()
        assert len(archived) == 1
        assert archived[0]["operation_id"] == record["operation_id"]

    def test_crash_after_db_before_committed_recovers(
        self, client: TestClient, settings: Settings, monkeypatch
    ):
        item_id = _new_item()
        identity = client.app.state.source_identity

        def boom(record, session):
            raise RuntimeError("injected after db commit")

        with monkeypatch.context() as patch:
            patch.setattr(identity, "_commit_and_archive", boom)
            with pytest.raises(RuntimeError):
                identity.materialize(item_id)
        journal = _journal(client)
        assert journal.current.exists()
        assert _item(item_id).source_instance_id == (
            client.app.state.source_instance_store.read()
        )

        _restart(client, settings).recover_if_needed()
        assert journal.current.exists() is False
        assert len(journal.read_archive()) == 1
        assert _classify(client, item_id).state == "2b"

    def test_current_archive_same_operation_dedupes(self, client: TestClient):
        item_id = _new_item()
        instance = client.app.state.source_instance_store.read()
        record = _prepare_materialize(client, item_id, instance, phase="COMMITTED")
        journal = _journal(client)
        journal.archive_committed(record)
        records = journal.committed_materialize_records()
        assert len(records) == 1
        assert records[0]["operation_id"] == record["operation_id"]
        assert len(journal.read_archive()) == 1
        journal.remove_current()

    def test_archive_corruption_fails_closed(self, client: TestClient):
        journal = _journal(client)
        journal.archive_dir.mkdir(parents=True, exist_ok=True)
        (journal.archive_dir / "broken.json").write_text("{", encoding="utf-8")
        with pytest.raises(SourceIdentityError) as excinfo:
            journal.read_archive()
        assert excinfo.value.code == JOURNAL_CORRUPT

    def test_checksum_mismatch_fails_closed_before_db_write(
        self, client: TestClient, settings: Settings
    ):
        item_id = _new_item()
        instance = client.app.state.source_instance_store.read()
        record = _prepare_materialize(client, item_id, instance)
        record["updated_at"] = "2020-01-01T00:00:00Z"  # 摘要不再匹配
        _journal(client).write_current(record)
        with pytest.raises(SourceIdentityError) as excinfo:
            _restart(client, settings).recover_if_needed()
        assert excinfo.value.code == JOURNAL_CORRUPT
        assert _item(item_id).source_instance_id is None


class TestRotate:
    def test_rotate_materializes_2a_keeps_imported_identity_and_exporter(
        self, client: TestClient
    ):
        identity = client.app.state.source_identity
        old = client.app.state.source_instance_store.read()
        local = client.post(
            "/api/knowledge", json={"title": "本地", "content": "正文"}
        ).json()
        imported_outcome = client.app.state.markdown_service.import_documents(
            [
                MarkdownImportDocument(
                    content=(
                        "---\ntitle: 导入\n"
                        f"source_instance_id: {X}\n"
                        f"source_document_id: {D1}\n---\n正文"
                    ),
                    filename="imported.md",
                )
            ]
        )
        imported_id = str(imported_outcome.report.items[0].item_id)
        incomplete = _new_item(
            title="残缺", source_instance="99999999-9999-4999-8999-999999999998"
        )
        _new_origin(incomplete, instance=None)
        report = identity.rotate(Z)
        assert report.old_instance_id == old
        assert report.target_instance_id == Z
        assert client.app.state.source_instance_store.read() == Z
        assert _item(local["id"]).source_instance_id == old
        assert _classify(client, local["id"]).state == "2b"
        assert _classify(client, imported_id).state == "1"
        assert _item(imported_id).source_instance_id == X
        # 状态 3 不物化、不改写、不认领。
        assert _classify(client, incomplete).state == "3"
        assert _item(incomplete).source_instance_id == (
            "99999999-9999-4999-8999-999999999998"
        )
        snap = _snapshot(client, incomplete)
        assert snap["import_origin_count"] == 1
        assert snap["import_origin_state"] == "incomplete"

        local_export = client.get(f"/api/knowledge/{local['id']}/markdown")
        assert local_export.headers["X-ExplainLab-Source-Instance-Id"] == old
        assert local_export.headers["X-ExplainLab-Exporter-Instance-Id"] == Z
        imported_export = client.get(f"/api/knowledge/{imported_id}/markdown")
        assert imported_export.headers["X-ExplainLab-Source-Instance-Id"] == X
        assert imported_export.headers["X-ExplainLab-Exporter-Instance-Id"] == Z

        second = identity.rotate()
        assert second.old_instance_id == Z
        assert client.app.state.source_instance_store.read() == (
            second.target_instance_id
        )
        assert len(_journal(client).read_archive()) >= 2

    def test_rotate_blocks_on_state_4(self, client: TestClient):
        identity = client.app.state.source_identity
        old = client.app.state.source_instance_store.read()
        _new_item(
            title="状态4",
            source_instance="99999999-9999-4999-8999-999999999999",
        )
        with pytest.raises(SourceIdentityError) as excinfo:
            identity.rotate()
        assert excinfo.value.code == SOURCE_IDENTITY_INCONSISTENT
        assert client.app.state.source_instance_store.read() == old

    def test_prepared_rotate_old_id_recovery_completes_replace(
        self, client: TestClient, settings: Settings, monkeypatch
    ):
        identity = client.app.state.source_identity
        old = client.app.state.source_instance_store.read()
        target = "f0e8400a-e29b-41d4-a716-446655440099"

        def boom(new_id):
            raise RuntimeError("crash before id replace")

        with monkeypatch.context() as patch:
            patch.setattr(identity._store, "replace", boom)
            with pytest.raises(RuntimeError):
                identity.rotate(target)
        journal = _journal(client)
        assert journal.current.exists()
        assert identity._store.read() == old

        _restart(client, settings).recover_if_needed()
        assert identity._store.read() == target
        assert journal.current.exists() is False
        assert len(journal.read_archive()) == 1

    def test_prepared_rotate_new_id_recovery_only_commits(
        self, client: TestClient, settings: Settings, monkeypatch
    ):
        identity = client.app.state.source_identity
        target = "f1e8400a-e29b-41d4-a716-446655440098"
        original_replace = identity._store.replace

        def replace_then_boom(new_id):
            original_replace(new_id)
            raise RuntimeError("crash after id replace")

        with monkeypatch.context() as patch:
            patch.setattr(identity._store, "replace", replace_then_boom)
            with pytest.raises(RuntimeError):
                identity.rotate(target)
        journal = _journal(client)
        assert journal.current.exists()
        assert identity._store.read() == target

        _restart(client, settings).recover_if_needed()
        assert identity._store.read() == target
        assert journal.current.exists() is False
        assert len(journal.read_archive()) == 1

class TestMaterializeClassificationBeforeIdentityWrite:
    """P1-01：恢复门之后先只读分类；冲突/非 2a 不得创建实例身份文件。

    这些用例使用真实 SQLite 与真实文件系统，并在调用前后对 ID 文件、当前
    Journal、归档、DB 身份投影做逐字节/摘要取证，断言冲突路径零写入。
    """

    @staticmethod
    def _identity_dir_state(client: TestClient) -> dict:
        journal = _journal(client)
        archive = {
            path.name: path.read_bytes()
            for path in sorted(journal.archive_dir.glob("*.json"))
        }
        current = journal.current.read_bytes() if journal.current.exists() else None
        store = client.app.state.source_instance_store
        id_bytes = store.path.read_bytes() if store.path.exists() else None
        return {"archive": archive, "current": current, "id": id_bytes}

    def _assert_no_identity_write(
        self, client: TestClient, item_id: str, before: dict, before_digest: str
    ) -> None:
        assert self._identity_dir_state(client) == before
        assert _digest() == before_digest
        assert _classify(client, item_id).state == "3"

    def test_conflict_with_existing_id_keeps_id_and_journal_bytes(
        self, client: TestClient
    ):
        item_id, instance = _materialized_local(client, "冲突-ID存在")
        _new_origin(item_id, instance=instance, document=item_id)
        before = self._identity_dir_state(client)
        before_digest = _digest()
        assert before["id"] is not None

        with pytest.raises(SourceIdentityError) as excinfo:
            client.app.state.source_identity.materialize(item_id)
        assert excinfo.value.code == SOURCE_DOCUMENT_UNMATERIALIZED
        self._assert_no_identity_write(client, item_id, before, before_digest)

    def test_conflict_with_empty_identity_dir_creates_no_id_files(
        self, client: TestClient
    ):
        item_id, instance = _materialized_local(client, "冲突-ID缺失")
        _new_origin(item_id, instance=instance, document=item_id)
        store = client.app.state.source_instance_store
        store.path.unlink()
        before = self._identity_dir_state(client)
        before_digest = _digest()
        assert before["id"] is None
        assert before["archive"]

        with pytest.raises(SourceIdentityError) as excinfo:
            client.app.state.source_identity.materialize(item_id)
        assert excinfo.value.code == SOURCE_DOCUMENT_UNMATERIALIZED
        self._assert_no_identity_write(client, item_id, before, before_digest)
        assert store.path.exists() is False

    def test_empty_data_dir_origin_plus_db_instance_creates_no_id(
        self, client: TestClient
    ):
        # 数据目录身份文件/Journal 全部缺失，DB 仍有 ImportOrigin 与非空实例值。
        # 分类先于 ensure，任何非 2a 状态都不得创建 source-instance-id。
        item_id, instance = _materialized_local(client, "缺失全部证据")
        _new_origin(item_id, instance=instance, document=item_id)
        store = client.app.state.source_instance_store
        store.path.unlink()
        journal = _journal(client)
        for path in journal.archive_dir.glob("*.json"):
            path.unlink()
        if journal.current.exists():
            journal.current.unlink()
        before = self._identity_dir_state(client)
        before_digest = _digest()
        assert before["id"] is None and before["archive"] == {}
        assert _classify(client, item_id).state == "1"

        with pytest.raises(SourceIdentityError) as excinfo:
            client.app.state.source_identity.materialize(item_id)
        assert excinfo.value.code == SOURCE_DOCUMENT_UNMATERIALIZED
        assert self._identity_dir_state(client) == before
        assert _digest() == before_digest
        assert store.path.exists() is False

    def test_prepared_materialize_plus_origin_conflict_keeps_journal(
        self, client: TestClient
    ):
        item_id = _new_item(title="PREPARED冲突")
        _new_origin(item_id, instance=None)
        store = client.app.state.source_instance_store
        store.path.unlink()
        expected_instance = X
        _prepare_materialize(client, item_id, expected_instance)
        before = self._identity_dir_state(client)
        before_digest = _digest()
        assert before["current"] is not None
        assert before["id"] is None

        with pytest.raises(SourceIdentityError) as excinfo:
            client.app.state.source_identity.materialize(item_id)
        assert excinfo.value.code == SOURCE_IDENTITY_INCONSISTENT
        assert self._identity_dir_state(client) == before
        assert _digest() == before_digest
        assert _item(item_id).source_instance_id is None

    def test_normal_2a_materializes_after_classification(self, client: TestClient):
        item_id = _new_item(title="正常2a")
        store = client.app.state.source_instance_store
        store.path.unlink()
        assert _classify(client, item_id).state == "2a"

        report = client.app.state.source_identity.materialize(item_id)
        assert report.materialized is True
        assert store.path.exists()
        assert store.read() == report.source_instance_id
        assert _item(item_id).source_instance_id == report.source_instance_id
        assert _classify(client, item_id).state == "2b"
        assert len(_journal(client).read_archive()) == 1

    def test_normal_state_1_materialize_creates_no_id(self, client: TestClient):
        item_id = _new_item(source_instance=X)
        _new_origin(item_id)
        store = client.app.state.source_instance_store
        store.path.unlink()
        before = self._identity_dir_state(client)
        before_digest = _digest()

        with pytest.raises(SourceIdentityError) as excinfo:
            client.app.state.source_identity.materialize(item_id)
        assert excinfo.value.code == SOURCE_DOCUMENT_UNMATERIALIZED
        assert self._identity_dir_state(client) == before
        assert _digest() == before_digest
        assert store.path.exists() is False
        assert _classify(client, item_id).state == "1"

    def test_normal_2b_materialize_does_not_recreate_or_rewrite_id(
        self, client: TestClient
    ):
        item_id, instance = _materialized_local(client, "正常2b")
        before = self._identity_dir_state(client)
        before_digest = _digest()

        report = client.app.state.source_identity.materialize(item_id)
        assert report.materialized is False
        assert report.source_instance_id == instance
        assert self._identity_dir_state(client) == before
        assert _digest() == before_digest


class TestRotateMaterializeOriginConflict:
    """P1-03：ROTATE 对状态 3 并存冲突不物化/不重写/不认领，仅替换 exporter。"""

    @staticmethod
    def _rotate_records(client: TestClient) -> list[dict]:
        return [
            record
            for record in _journal(client).read_archive()
            if record["kind"] == "ROTATE"
        ]

    def test_rotate_conflict_only_keeps_audit_and_replaces_exporter(
        self, client: TestClient
    ):
        identity = client.app.state.source_identity
        old = client.app.state.source_instance_store.read()
        conflict_id, instance = _materialized_local(client, "rotate冲突")
        _new_origin(conflict_id, instance=instance, document=conflict_id)
        imported = client.app.state.markdown_service.import_documents(
            [
                MarkdownImportDocument(
                    content=(
                        "---\ntitle: rotate导入\n"
                        f"source_instance_id: {X}\n"
                        f"source_document_id: {D1}\n---\n正文"
                    ),
                    filename="rotate-imported.md",
                )
            ]
        )
        imported_id = str(imported.report.items[0].item_id)
        before_snapshot = _snapshot(client, conflict_id)
        before_digest = _digest()
        before_archive = len(_journal(client).read_archive())
        before_materialize = [
            (record["operation_id"], record["item_id"])
            for record in _journal(client).read_archive()
            if record["kind"] == "MATERIALIZE"
        ]
        assert _classify(client, conflict_id).state == "3"

        report = identity.rotate(Z)
        assert report.old_instance_id == old
        assert report.target_instance_id == Z
        assert report.materialized_items == []
        assert client.app.state.source_instance_store.read() == Z

        # 冲突条目来源身份与 DB 值零改写，仍可识别为状态 3。
        assert _classify(client, conflict_id).state == "3"
        assert _item(conflict_id).source_instance_id == instance
        assert _snapshot(client, conflict_id) == before_snapshot
        # 导入条目与冲突条目均不改写来源；exporter 轮换不影响审计投影。
        assert _classify(client, imported_id).state == "1"
        assert _item(imported_id).source_instance_id == X
        assert _digest() == before_digest

        rotate_records = self._rotate_records(client)
        assert len(rotate_records) == 1
        assert rotate_records[0]["materialization_items"] == []
        assert rotate_records[0]["identity_audit_digest"] == _digest()
        assert len(_journal(client).read_archive()) == before_archive + 1
        # 冲突条目没有新增 MATERIALIZE 记录（既有证明记录保持原样）。
        after_materialize = [
            (record["operation_id"], record["item_id"])
            for record in _journal(client).read_archive()
            if record["kind"] == "MATERIALIZE"
        ]
        assert after_materialize == before_materialize

        exported = client.get(f"/api/knowledge/{conflict_id}/markdown")
        assert exported.status_code == 200
        assert "X-ExplainLab-Source-Instance-Id" not in exported.headers
        assert exported.headers["X-ExplainLab-Exporter-Instance-Id"] == Z
        assert "source_instance_id" not in exported.text

        # 再轮换一次，冲突仍保持原状且可识别。
        second = identity.rotate()
        assert client.app.state.source_instance_store.read() == (
            second.target_instance_id
        )
        assert _classify(client, conflict_id).state == "3"
        assert _item(conflict_id).source_instance_id == instance
        assert _snapshot(client, conflict_id) == before_snapshot
        assert len(self._rotate_records(client)) == 2

    def test_rotate_conflict_does_not_block_other_2a_materialization(
        self, client: TestClient
    ):
        identity = client.app.state.source_identity
        old = client.app.state.source_instance_store.read()
        conflict_id, instance = _materialized_local(client, "rotate冲突2a")
        _new_origin(conflict_id, instance=instance, document=conflict_id)
        local_id = _new_item(title="rotate待物化")
        assert _classify(client, local_id).state == "2a"
        before_snapshot = _snapshot(client, conflict_id)

        report = identity.rotate(Z)
        assert report.materialized_items == [local_id]
        assert _item(local_id).source_instance_id == old
        assert _classify(client, local_id).state == "2b"
        assert _classify(client, conflict_id).state == "3"
        assert _item(conflict_id).source_instance_id == instance
        assert _snapshot(client, conflict_id) == before_snapshot

        rotate_record = self._rotate_records(client)[0]
        assert rotate_record["identity_audit_digest"] == _digest()
        assert [entry["item_id"] for entry in rotate_record["materialization_items"]] == [
            local_id
        ]
