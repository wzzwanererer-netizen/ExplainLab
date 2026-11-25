"""Review resolution through the API with a real database and storage layout."""

import base64
import json
import logging
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from alembic import command
from app.api.routes import governance
from app.core.config import Settings, get_settings
from app.db.session import dispose_db, get_engine, get_session_factory
from app.main import create_app
from app.models import (
    AttachmentORM,
    ImportOriginORM,
    KnowledgeItemORM,
    KnowledgeLinkORM,
    ReviewRequestORM,
)
from app.services.attachment_promotion import PublishedAttachments
from app.services.import_review_hook import build_link_restorer
from app.services.repositories_v2 import SQLAlchemyImportOriginRepository, SQLAlchemyTagRepository
from app.services.source_identity import identity_audit_digest, item_identity_digest
from knowledge_core.model_adapter import ModelAdapterError

DATA = b"%PDF-1.7\nreview attachment"
KEY = sha256(DATA).hexdigest()


@pytest.fixture
def audit_warning_loggers(monkeypatch):
    # Alembic's logging bootstrap can disable loggers already imported by pytest.
    for logger in (governance.logger, logging.getLogger("app.services.retrieval")):
        monkeypatch.setattr(logger, "disabled", False)


def _pending(client, *, with_attachment=True, body="new content"):
    created = client.post("/api/knowledge", json={"title": "before", "content": "old content"})
    assert created.status_code == 201, created.text
    item = created.json()["id"]
    with get_session_factory()() as session:
        session.get(KnowledgeItemORM, item).status = "active"
        session.commit()
    content = (
        f"---\ntitle: after\ntags: [reviewed]\nsource_instance_id: {uuid4()}\n"
        f"source_document_id: {uuid4()}\n---\n{body}"
    )
    request = {"target_item_id": item, "content": content, "filename": "note.md"}
    if with_attachment:
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("note.md", content)
            archive.writestr("attachments/report.pdf", DATA)
        request.pop("content")
        request["archive_base64"] = base64.b64encode(buffer.getvalue()).decode()
    response = client.post("/api/knowledge/import", json=request)
    assert response.status_code == 202, response.text
    review = response.json()["items"][0]["review_id"]
    if not with_attachment:
        return item, review, None
    with get_session_factory()() as session:
        manifest = json.loads(session.get(ReviewRequestORM, review).payload)["__a1_import"]
    layout = client.app.state.attachment_storage
    return item, review, layout.staging_root / manifest["attachments"][0]["staging_id"]


def _resolve(client, review, action="approve"):
    return client.post(f"/api/reviews/{review}/{action}", json={"note": "checked"})


def _state(item, review):
    with get_session_factory()() as session:
        target = session.get(KnowledgeItemORM, item)
        refs = list(session.scalars(select(AttachmentORM).where(AttachmentORM.item_id == item)))
        status = session.get(ReviewRequestORM, review).status
        return target.content, target.status, status, [row.storage_key for row in refs]


def _check_approval(client, item, review, staging):
    assert _state(item, review) == ("new content", "draft", "approved", [KEY])
    assert not staging.exists()
    assert client.app.state.attachment_storage.final_path(KEY).read_bytes() == DATA
    _check_metadata(item, expected=True)


def _check_metadata(item, *, expected):
    with get_session_factory()() as session:
        assert SQLAlchemyTagRepository(session).list_item_tags(item) == (
            ["reviewed"] if expected else []
        )
        stmt = select(ImportOriginORM).where(ImportOriginORM.item_id == item)
        assert (session.scalar(stmt) is not None) == expected


def test_approve_publishes_before_writing_and_cleans_staging(client):
    item, review, staging = _pending(client)
    assert (staging / ".complete").is_file()
    assert _state(item, review) == ("old content", "active", "pending", [])
    blob = client.app.state.attachment_storage.final_path(KEY)
    writes = []

    def observe_write(_connection, _cursor, sql, *_args):
        if sql.lstrip().upper().startswith(("UPDATE KNOWLEDGE_ITEM", "UPDATE REVIEW_REQUEST")):
            writes.append(sql)
            assert blob.read_bytes() == DATA
            assert staging.is_dir()

    engine = get_engine()
    event.listen(engine, "before_cursor_execute", observe_write)
    try:
        result = _resolve(client, review)
    finally:
        event.remove(engine, "before_cursor_execute", observe_write)
    assert result.status_code == 200, result.text
    assert writes
    _check_approval(client, item, review, staging)
    assert _resolve(client, review).status_code == 409


def test_reject_cleans_only_its_staging(client):
    item, review, staging = _pending(client)
    result = _resolve(client, review, "reject")
    assert result.status_code == 200, result.text
    assert _state(item, review) == ("old content", "active", "rejected", [])
    assert not staging.exists()
    assert not client.app.state.attachment_storage.final_path(KEY).exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows sharing violation")
def test_reject_commits_when_windows_handle_blocks_cleanup(client):
    item, review, staging = _pending(client)
    staged_blob = next((staging / "blobs").iterdir())
    with staged_blob.open("rb") as open_download:
        with pytest.raises(PermissionError):
            staged_blob.unlink()
        result = _resolve(client, review, "reject")
        assert result.status_code == 200, result.text
        assert _state(item, review) == ("old content", "active", "rejected", [])
        assert open_download.read() == DATA
        assert staged_blob.is_file()
    assert not client.app.state.attachment_storage.final_path(KEY).exists()


def test_resolve_rejects_distinct_payloads_without_deadlocking(client, monkeypatch):
    item, review, staging = _pending(client)
    captured, resume = Event(), Event()
    read = governance._review_snapshot

    def pause_approve(session, review_id, *, rejecting=False):
        snapshot = read(session, review_id, rejecting=rejecting)
        if not rejecting:
            assert snapshot.envelope.source_instance_id
            session.close()
            captured.set()
            assert resume.wait(15)
        return snapshot

    monkeypatch.setattr(governance, "_review_snapshot", pause_approve)
    with ThreadPoolExecutor(max_workers=2) as pool:
        approve = pool.submit(_resolve, client, review)
        try:
            assert captured.wait(15)
            with get_session_factory()() as session:
                row = session.get(ReviewRequestORM, review)
                payload = json.loads(row.payload)
                payload["__a1_import"]["context_digest"] = "0" * 64
                row.payload = json.dumps(payload)
                session.commit()
            rejected = pool.submit(_resolve, client, review, "reject").result(timeout=15)
        finally:
            resume.set()
        approved = approve.result(timeout=15)
    assert approved.status_code == 409, approved.text
    assert rejected.status_code == 200, rejected.text
    assert _state(item, review) == ("old content", "active", "rejected", [])
    assert (staging / ".complete").is_file()


def test_approve_and_reject_have_one_terminal_decision(client):
    item, review, staging = _pending(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        approve = pool.submit(_resolve, client, review)
        reject = pool.submit(_resolve, client, review, "reject")
        approved, rejected = approve.result(timeout=20), reject.result(timeout=20)
    assert sorted([approved.status_code, rejected.status_code]) == [200, 409]
    if approved.status_code == 200:
        _check_approval(client, item, review, staging)
    else:
        assert _state(item, review) == ("old content", "active", "rejected", [])
        assert not staging.exists()


def test_approval_requires_complete_marker(client):
    item, review, staging = _pending(client)
    (staging / ".complete").unlink()
    response = _resolve(client, review)
    assert response.status_code == 409
    assert response.json()["detail"] == "ATTACHMENT_STAGING_INVALID"
    assert _state(item, review) == ("old content", "active", "pending", [])
    assert not client.app.state.attachment_storage.final_path(KEY).exists()


@pytest.mark.parametrize("after_publish", [False, True])
def test_archived_target_remains_archived(client, monkeypatch, after_publish):
    item, review, staging = _pending(client)

    def archive():
        with get_session_factory()() as session:
            session.get(KnowledgeItemORM, item).status = "archived"
            session.commit()

    if after_publish:
        publish = governance.publish_staged

        def publish_then_archive(*args):
            plan = publish(*args)
            archive()
            return plan

        monkeypatch.setattr(governance, "publish_staged", publish_then_archive)
    else:
        archive()
    response = _resolve(client, review)
    assert response.status_code == 409
    assert response.json()["detail"] == "ATTACHMENT_ITEM_ARCHIVED"
    assert _state(item, review) == ("old content", "archived", "pending", [])
    assert staging.is_dir()
    assert client.app.state.attachment_storage.final_path(KEY).exists() == after_publish


def test_payload_drift_after_publish_rolls_back(client, monkeypatch):
    item, review, staging = _pending(client)
    publish = governance.publish_staged

    def publish_then_change(*args):
        plan = publish(*args)
        with get_session_factory()() as session:
            row = session.get(ReviewRequestORM, review)
            payload = json.loads(row.payload)
            payload["content"] = "drift"
            row.payload = json.dumps(payload)
            session.commit()
        return plan

    monkeypatch.setattr(governance, "publish_staged", publish_then_change)
    response = _resolve(client, review)
    assert response.status_code == 409
    assert response.json()["detail"] == "IMPORT_ENVELOPE_INVALID"
    assert _state(item, review) == ("old content", "active", "pending", [])
    _check_metadata(item, expected=False)
    assert staging.is_dir()


def test_db_hook_failure_rolls_back_and_retry_reuses_blob(client, monkeypatch):
    item, review, staging = _pending(client)
    save = PublishedAttachments.save_references

    def fail_after_flush(plan, session, item_id):
        save(plan, session, item_id)
        raise RuntimeError("before review commit")

    with monkeypatch.context() as patch:
        patch.setattr(PublishedAttachments, "save_references", fail_after_flush)
        with pytest.raises(RuntimeError, match="before review commit"):
            _resolve(client, review)
    assert _state(item, review) == ("old content", "active", "pending", [])
    assert staging.is_dir()
    assert client.app.state.attachment_storage.final_path(KEY).is_file()
    assert _resolve(client, review).status_code == 200
    _check_approval(client, item, review, staging)


@pytest.mark.parametrize("point", ["origin", "tags", "links"])
def test_hook_write_points_roll_back(client, monkeypatch, point):
    item, review, staging = _pending(client)
    if point == "origin":
        cls, method = SQLAlchemyImportOriginRepository, "save_origin"
    elif point == "tags":
        cls, method = SQLAlchemyTagRepository, "set_item_tags"
    else:
        with get_session_factory()() as session:
            cls, method = type(build_link_restorer(session)), "restore"
    write = getattr(cls, method)

    def fail_after_write(*args, **kwargs):
        write(*args, **kwargs)
        raise RuntimeError(f"injected {point} write failure")

    monkeypatch.setattr(cls, method, fail_after_write)
    with pytest.raises(RuntimeError, match=f"injected {point} write failure"):
        _resolve(client, review)
    assert _state(item, review) == ("old content", "active", "pending", [])
    _check_metadata(item, expected=False)
    assert (staging / ".complete").is_file()
    assert client.app.state.attachment_storage.final_path(KEY).read_bytes() == DATA


@pytest.mark.parametrize("with_attachment", [True, False])
@pytest.mark.usefixtures("audit_warning_loggers")
def test_index_commit_failure_does_not_unapprove_review(
    client, monkeypatch, caplog, with_attachment,
):
    item, review, staging = _pending(client, with_attachment=with_attachment)
    sync = governance._sync_applied_action
    commits = []

    async def flag_index_commit(session, *args):
        await sync(session, *args)
        session.info["fail_index_commit"] = True

    def fail_commit(session):
        commits.append(session)
        if session.info.get("fail_index_commit"):
            raise RuntimeError("index commit intercepted")

    monkeypatch.setattr(governance, "_sync_applied_action", flag_index_commit)
    event.listen(Session, "before_commit", fail_commit)
    try:
        response = _resolve(client, review)
    finally:
        event.remove(Session, "before_commit", fail_commit)
    assert response.status_code == 200, response.text
    assert len(set(commits)) == 2 and all(session is commits[0] for session in commits[:-1])
    assert commits[-1].info["fail_index_commit"]
    assert "REVIEW_INDEX_SYNC_FAILED: RuntimeError" in caplog.text
    assert "index commit intercepted" not in caplog.text
    if with_attachment:
        _check_approval(client, item, review, staging)
    else:
        assert _state(item, review) == ("new content", "draft", "approved", [])
        _check_metadata(item, expected=True)
    assert _resolve(client, review).status_code == 409
    assert len(client.get("/api/reviews").json()) == 1


@pytest.mark.parametrize("route", ["ordinary_approve", "draft_apply", "restore"])
@pytest.mark.usefixtures("audit_warning_loggers")
def test_review_index_failure_preserves_committed_business(client, monkeypatch, caplog, route):
    response = client.post("/api/knowledge", json={"title": "note", "content": "previous"})
    assert response.status_code == 201
    item = response.json()["id"]
    submission = {
        "item_id": item, "action": "update_item", "payload": {"content": "updated"},
    }
    if route == "ordinary_approve":
        with get_session_factory()() as session:
            session.get(KnowledgeItemORM, item).status = "active"
            session.commit()
        pending = client.post("/api/reviews", json=submission)
        assert pending.status_code == 201
        review = pending.json()["review"]["id"]
    elif route == "restore":
        assert client.patch(f"/api/knowledge/{item}", json={"content": "updated"}).status_code == 200

    calls = []

    async def fail_index(*args):
        with get_session_factory()() as observer:
            calls.append(observer.get(KnowledgeItemORM, item).content)
        raise RuntimeError("private index error text")

    monkeypatch.setattr(governance, "_sync_applied_action", fail_index)
    if route == "ordinary_approve":
        result = _resolve(client, review)
        assert result.status_code == 200 and result.json()["status"] == "approved"
        assert _resolve(client, review).status_code == 409
    elif route == "draft_apply":
        result = client.post("/api/reviews", json=submission)
        assert result.status_code == 200 and result.json()["applied"] is True
    else:
        result = client.post(f"/api/knowledge/{item}/versions/1/restore")
        assert result.status_code == 200 and result.json()["content"] == "previous"
    expected = "previous" if route == "restore" else "updated"
    assert calls == [expected]
    assert client.get(f"/api/knowledge/{item}").json()["content"] == expected
    reviews = client.get("/api/reviews").json()
    assert len(reviews) == (1 if route == "ordinary_approve" else 0)
    assert "REVIEW_INDEX_SYNC_FAILED: RuntimeError" in caplog.text
    assert "private index error text" not in caplog.text


def test_index_failure_does_not_unapprove_review(client, monkeypatch):
    item, review, staging = _pending(client)
    observed = []

    async def index_failure(*args):
        observed.append((
            _state(item, review),
            staging.exists(),
            client.app.state.import_coordinator.is_held(f"review:{review}"),
        ))
        raise RuntimeError("independent index failure")

    monkeypatch.setattr(governance, "_sync_applied_action", index_failure)
    response = _resolve(client, review)
    assert response.status_code == 200, response.text
    assert observed == [(("new content", "draft", "approved", [KEY]), False, False)]
    _check_approval(client, item, review, staging)


@pytest.mark.usefixtures("audit_warning_loggers")
def test_review_index_embedding_failure_logs_only_exception_type(client, monkeypatch, caplog):
    item, review, _ = _pending(client, with_attachment=False)
    private_message = "private provider error with request fragment"

    class FailingEmbedder:
        async def embed(self, texts):
            raise ModelAdapterError(private_message)

    monkeypatch.setitem(
        client.app.dependency_overrides, governance.get_embedder, FailingEmbedder,
    )
    result = _resolve(client, review)
    assert result.status_code == 200 and result.json()["status"] == "approved"
    assert _state(item, review) == ("new content", "draft", "approved", [])
    assert "INDEX_EMBEDDING_SYNC_FAILED: ModelAdapterError" in caplog.text
    assert private_message not in caplog.text


def test_recovery_finishes_before_attachment_publication(client, monkeypatch):
    item, review, staging = _pending(client)
    other = client.post("/api/knowledge", json={
        "title": "recovery target", "content": "unrelated document",
    }).json()["id"]
    identity = client.app.state.source_identity
    instance = client.app.state.source_instance_store.read()
    entry = {
        "item_id": other, "source_instance_id": instance,
        "source_document_id": other, "identity_record_version": 1,
    }
    entry["item_identity_digest"] = item_identity_digest(entry)
    with get_session_factory()() as session:
        audit_digest = identity_audit_digest(
            session, materialized={other: (instance, other)},
        )
    record = identity._new_record(
        kind="MATERIALIZE", phase="PREPARED", item_id=other,
        source_instance_id=instance, source_document_id=other,
        items=[entry], audit_digest=audit_digest,
    )
    identity.journal.write_current(record)
    publish = governance.publish_staged

    def check_then_publish(*args):
        assert identity.journal.read_current() is None
        assert identity.journal.read_archive()[0]["phase"] == "COMMITTED"
        with get_session_factory()() as session:
            assert session.get(KnowledgeItemORM, other).source_instance_id == instance
        return publish(*args)

    monkeypatch.setattr(governance, "publish_staged", check_then_publish)
    response = _resolve(client, review)
    assert response.status_code == 200, response.text
    _check_approval(client, item, review, staging)


@pytest.fixture
def pg_review_client(tmp_path, monkeypatch):
    url = os.environ.get("EXPLAINLAB_PG_TEST_URL")
    if not url:
        pytest.skip("EXPLAINLAB_PG_TEST_URL is required for the PostgreSQL review test")
    parsed = make_url(url)
    if not (parsed.database or "").startswith("explainlab_b4_http_"):
        pytest.skip("dedicated explainlab_b4_http_ PostgreSQL database required")
    assert parsed.get_backend_name() == "postgresql"
    backend = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    with monkeypatch.context() as patch:
        patch.setenv("DATABASE_URL", url)
        get_settings.cache_clear()
        try:
            command.upgrade(cfg, "head")
        finally:
            get_settings.cache_clear()
    settings = Settings(database_url=url, data_dir=tmp_path / "data", _env_file=None)
    try:
        with TestClient(create_app(settings)) as client:
            with get_engine().connect() as connection:
                assert connection.scalar(text("SHOW server_version_num")) == "180006"
            yield client
    finally:
        dispose_db()


def test_pg_review_approval_commits_and_releases_advisory_lock(pg_review_client, monkeypatch):
    client = pg_review_client
    test_archived_target_remains_archived(client, monkeypatch, False)
    test_reject_cleans_only_its_staging(client)
    with monkeypatch.context() as patch:
        test_payload_drift_after_publish_rolls_back(client, patch)
    test_db_hook_failure_rolls_back_and_retry_reuses_blob(client, monkeypatch)
    item, review, staging = _pending(client)
    response = _resolve(client, review)
    assert response.status_code == 200, response.text
    _check_approval(client, item, review, staging)
    with get_engine().connect() as connection:
        assert connection.scalar(text(
            "select count(*) from pg_locks where locktype = 'advisory' "
            "and database = (select oid from pg_database "
            "where datname = current_database())"
        )) == 0


@pytest.mark.parametrize("point", ["attachment", "tags", "origin", "links", "archive"])
def test_pg_review_hook_all_breakpoints(pg_review_client, monkeypatch, point):
    client = pg_review_client
    if point == "archive":
        test_archived_target_remains_archived(client, monkeypatch, True)
        return
    target = f"link-target-{uuid4()}"
    assert client.post("/api/knowledge", json={"title": target, "content": "target"}).status_code == 201
    item, review, staging = _pending(client, body=f"new content [[{target}]]")
    if point == "attachment":
        cls, method = PublishedAttachments, "save_references"
    elif point == "tags":
        cls, method = SQLAlchemyTagRepository, "set_item_tags"
    elif point == "origin":
        cls, method = SQLAlchemyImportOriginRepository, "save_origin"
    else:
        with get_session_factory()() as session:
            cls, method = type(build_link_restorer(session)), "restore"
    write = getattr(cls, method)

    def fail_after_write(*args, **kwargs):
        write(*args, **kwargs)
        raise RuntimeError(f"PG hook failure after {point}")

    monkeypatch.setattr(cls, method, fail_after_write)
    with pytest.raises(RuntimeError, match=f"PG hook failure after {point}"):
        _resolve(client, review)
    assert _state(item, review) == ("old content", "active", "pending", [])
    _check_metadata(item, expected=False)
    with get_session_factory()() as session:
        assert session.get(KnowledgeItemORM, item).title == "before"
        assert session.scalar(select(KnowledgeLinkORM).where(
            KnowledgeLinkORM.source_item_id == item,
        )) is None
    assert (staging / ".complete").is_file()
    assert client.app.state.attachment_storage.final_path(KEY).read_bytes() == DATA
