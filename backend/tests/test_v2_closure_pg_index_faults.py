"""ExplainLab V2 Backend Final Closure: PostgreSQL index commit failure injection.

Gated by EXPLAINLAB_PG_TEST_URL (real PostgreSQL 18.6 required; never substituted with SQLite).
Explicitly distinguishes:
1. Business transaction commit failure (rolls back business data, preserves staging).
2. Post-commit independent index Session failure (business stays committed, HTTP 200,
   no dangling references, attachment intact, index recoverable via reindex/sync).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import zipfile
from hashlib import sha256
from io import BytesIO
from pathlib import Path
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
from app.services.repositories_v2 import SQLAlchemyTagRepository
from app.services.retrieval import PostgresFullTextIndex, sync_index
from knowledge_core.model_adapter import ModelAdapterError

DATA = b"%PDF-1.7\npg-index-failure-injection"
KEY = sha256(DATA).hexdigest()


@pytest.fixture
def audit_warning_loggers(monkeypatch):
    for logger in (governance.logger, logging.getLogger("app.services.retrieval")):
        monkeypatch.setattr(logger, "disabled", False)


@pytest.fixture
def pg_index_client(tmp_path, monkeypatch):
    url = os.environ.get("EXPLAINLAB_PG_TEST_URL")
    if not url:
        pytest.skip("EXPLAINLAB_PG_TEST_URL is required for PostgreSQL index failure tests")
    parsed = make_url(url)
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
    # Alembic's logging fileConfig disables already-imported loggers on every upgrade call.
    for logger in (governance.logger, logging.getLogger("app.services.retrieval")):
        monkeypatch.setattr(logger, "disabled", False)
    settings = Settings(database_url=url, data_dir=tmp_path / "data", _env_file=None)
    try:
        with TestClient(create_app(settings)) as client:
            with get_engine().begin() as conn:
                conn.execute(text("DELETE FROM gc_task"))
                conn.execute(text("DELETE FROM attachment"))
                conn.execute(text("DELETE FROM storage_lock"))
                conn.execute(text("DELETE FROM review_request"))
                conn.execute(text("DELETE FROM import_origin"))
                conn.execute(text("DELETE FROM knowledge_link"))
                conn.execute(text("DELETE FROM knowledge_item"))
                ver = conn.scalar(text("SHOW server_version_num"))
                print(f"[PG_INDEX_ENV] server_version_num={ver} db={parsed.database}")
            yield client
    finally:
        dispose_db()


def _pg_advisory_count() -> int:
    with get_engine().connect() as conn:
        return int(
            conn.scalar(
                text(
                    "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
                    "AND database = (SELECT oid FROM pg_database WHERE datname = current_database())"
                )
            )
            or 0
        )


def _pending_import(client, *, target_title: str, tag_name: str, with_attachment: bool = True):
    assert (
        client.post("/api/knowledge", json={"title": target_title, "content": "link target"}).status_code
        == 201
    )
    created = client.post("/api/knowledge", json={"title": "before", "content": "old content"})
    assert created.status_code == 201, created.text
    item_id = created.json()["id"]
    with get_session_factory()() as session:
        session.get(KnowledgeItemORM, item_id).status = "active"
        session.commit()

    body = f"approved content unique_token_{tag_name} [[{target_title}]]"
    markdown = (
        f"---\ntitle: after-{tag_name}\ntags: [{tag_name}]\n"
        f"source_instance_id: {uuid4()}\nsource_document_id: {uuid4()}\n---\n{body}"
    )
    req = {"target_item_id": item_id, "filename": "note.md"}
    if with_attachment:
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            archive.writestr("note.md", markdown)
            archive.writestr("attachments/report.pdf", DATA)
        req["archive_base64"] = base64.b64encode(buf.getvalue()).decode()
    else:
        req["content"] = markdown

    resp = client.post("/api/knowledge/import", json=req)
    assert resp.status_code == 202, resp.text
    review_id = resp.json()["items"][0]["review_id"]
    if not with_attachment:
        return item_id, review_id, None
    with get_session_factory()() as session:
        manifest = json.loads(session.get(ReviewRequestORM, review_id).payload)["__a1_import"]
    staging = client.app.state.attachment_storage.staging_root / manifest["attachments"][0]["staging_id"]
    return item_id, review_id, staging


@pytest.mark.parametrize("focus", ["attachment", "tags", "origin", "links", "archive_guard"])
@pytest.mark.usefixtures("audit_warning_loggers")
def test_pg_index_commit_failure_by_business_path(
    pg_index_client, monkeypatch, caplog, focus,
):
    """PostgreSQL index commit failure injection across attachment/tags/origin/links/archive paths."""
    client = pg_index_client
    target_title = f"pg-target-{focus}-{uuid4().hex[:8]}"
    tag_name = f"pgtag_{focus}_{uuid4().hex[:6]}"
    item_id, review_id, staging = _pending_import(
        client, target_title=target_title, tag_name=tag_name, with_attachment=True,
    )
    assert staging is not None and (staging / ".complete").is_file()

    if focus == "archive_guard":
        # Archive path: business TX must reject with 409, preserve staging, and NOT run index sync
        index_called = []

        async def record_index(*args, **kwargs):
            index_called.append(True)

        with get_session_factory()() as session:
            session.get(KnowledgeItemORM, item_id).status = "archived"
            session.commit()
        monkeypatch.setattr(governance, "_sync_applied_action", record_index)
        resp = client.post(f"/api/reviews/{review_id}/approve", json={"note": "archived"})
        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"] == "ATTACHMENT_ITEM_ARCHIVED"
        assert index_called == []
        assert (staging / ".complete").is_file()
        with get_session_factory()() as session:
            assert session.get(KnowledgeItemORM, item_id).status == "archived"
            assert session.get(ReviewRequestORM, review_id).status == "pending"
            assert list(session.scalars(select(AttachmentORM).where(AttachmentORM.item_id == item_id))) == []
            assert SQLAlchemyTagRepository(session).list_item_tags(item_id) == []
            assert session.scalar(select(ImportOriginORM).where(ImportOriginORM.item_id == item_id)) is None
            assert session.scalar(select(KnowledgeLinkORM).where(KnowledgeLinkORM.source_item_id == item_id)) is None
        assert _pg_advisory_count() == 0
        print(f"[PG_INDEX_FAULT] focus={focus} status=409 staging_preserved=True index_called=False")
        return

    # Inject PostgreSQL commit failure strictly in the independent index Session
    orig_sync = governance._sync_applied_action
    commit_sessions: list[Session] = []

    async def flag_index_session(session, *args):
        await orig_sync(session, *args)
        session.info["pg_fail_index_commit"] = True

    def fail_index_commit(session):
        commit_sessions.append(session)
        if session.info.get("pg_fail_index_commit"):
            raise RuntimeError(f"pg injected index commit failure ({focus})")

    monkeypatch.setattr(governance, "_sync_applied_action", flag_index_session)
    event.listen(Session, "before_commit", fail_index_commit)
    try:
        resp = client.post(f"/api/reviews/{review_id}/approve", json={"note": focus})
    finally:
        event.remove(Session, "before_commit", fail_index_commit)

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"
    # Verify business session and index session are distinct objects
    assert len(set(commit_sessions)) >= 2
    assert commit_sessions[-1].info.get("pg_fail_index_commit") is True
    assert commit_sessions[0] is not commit_sessions[-1]
    assert "REVIEW_INDEX_SYNC_FAILED: RuntimeError" in caplog.text
    assert "pg injected index commit failure" not in caplog.text

    # Verify ALL committed business artifacts persisted cleanly in PostgreSQL
    with get_session_factory()() as session:
        item_row = session.get(KnowledgeItemORM, item_id)
        review_row = session.get(ReviewRequestORM, review_id)
        att_rows = list(session.scalars(select(AttachmentORM).where(AttachmentORM.item_id == item_id)))
        tags = SQLAlchemyTagRepository(session).list_item_tags(item_id)
        origin = session.scalar(select(ImportOriginORM).where(ImportOriginORM.item_id == item_id))
        links = list(session.scalars(select(KnowledgeLinkORM).where(KnowledgeLinkORM.source_item_id == item_id)))

    assert item_row.title == f"after-{tag_name}"
    assert item_row.status == "draft"
    assert review_row.status == "approved"
    assert [a.storage_key for a in att_rows] == [KEY]
    assert tags == [tag_name]
    assert origin is not None
    assert len(links) == 1
    assert client.app.state.attachment_storage.final_path(KEY).read_bytes() == DATA
    assert not staging.exists()
    assert _pg_advisory_count() == 0

    # Re-approving an already approved review must return 409 (not re-apply)
    assert client.post(f"/api/reviews/{review_id}/approve", json={}).status_code == 409

    # Subsequent recovery: PG FTS index sync succeeds and item is searchable via PostgresFullTextIndex
    with get_session_factory()() as session:
        import asyncio
        from uuid import UUID

        asyncio.run(sync_index(session, None, index_ids=[UUID(item_id)]))
        session.commit()
        hits = PostgresFullTextIndex(session).search(f"unique_token_{tag_name}", 5)
        assert any(str(hit_id) == item_id for hit_id, _ in hits)

    print(
        f"[PG_INDEX_FAULT] focus={focus} http=200 distinct_sessions={len(set(commit_sessions))} "
        f"refs={len(att_rows)} tags={tags} links={len(links)} advisory_locks=0 fts_recovered=True"
    )


@pytest.mark.usefixtures("audit_warning_loggers")
def test_pg_business_commit_failure_preserves_staging_and_rolls_back(pg_index_client):
    """Distinguish TX1 (business commit failure): rolls back business data and preserves staging."""
    client = pg_index_client
    target_title = f"pg-bizfail-{uuid4().hex[:8]}"
    item_id, review_id, staging = _pending_import(
        client, target_title=target_title, tag_name="bizfail", with_attachment=True,
    )
    assert staging is not None and (staging / ".complete").is_file()

    def mark_review_approval(session, *_args):
        for obj in session.dirty:
            if isinstance(obj, ReviewRequestORM) and obj.status == "approved":
                session.info["pg_fail_business_commit"] = True

    def fail_business_commit(session):
        if session.in_nested_transaction():
            return
        if session.info.get("pg_fail_business_commit"):
            raise RuntimeError("pg injected business commit failure")

    event.listen(Session, "after_flush", mark_review_approval)
    event.listen(Session, "before_commit", fail_business_commit)
    try:
        with pytest.raises(RuntimeError, match="pg injected business commit failure"):
            client.post(f"/api/reviews/{review_id}/approve", json={"note": "bizfail"})
    finally:
        event.remove(Session, "before_commit", fail_business_commit)
        event.remove(Session, "after_flush", mark_review_approval)

    # Business TX rolled back completely; staging MUST NOT be deleted prematurely!
    assert (staging / ".complete").is_file()
    with get_session_factory()() as session:
        assert session.get(ReviewRequestORM, review_id).status == "pending"
        assert session.get(KnowledgeItemORM, item_id).status == "active"
        assert session.get(KnowledgeItemORM, item_id).content == "old content"
        assert list(session.scalars(select(AttachmentORM).where(AttachmentORM.item_id == item_id))) == []
        assert SQLAlchemyTagRepository(session).list_item_tags(item_id) == []
        assert session.scalar(select(ImportOriginORM).where(ImportOriginORM.item_id == item_id)) is None
        assert session.scalar(select(KnowledgeLinkORM).where(KnowledgeLinkORM.source_item_id == item_id)) is None
    assert _pg_advisory_count() == 0
    print("[PG_BIZ_COMMIT_FAIL] rolled_back=True staging_preserved=True advisory_locks=0")


@pytest.mark.parametrize("route", ["ordinary_approve", "draft_apply", "restore"])
@pytest.mark.usefixtures("audit_warning_loggers")
def test_pg_p1_01_routes_index_commit_failure_preserves_committed_business(
    pg_index_client, monkeypatch, caplog, route,
):
    """P1-01 on real PostgreSQL 18.6: ordinary approve, draft apply, and version restore."""
    client = pg_index_client
    created = client.post("/api/knowledge", json={"title": "p1-pg", "content": "previous"})
    assert created.status_code == 201
    item_id = created.json()["id"]
    submission = {"item_id": item_id, "action": "update_item", "payload": {"content": "updated"}}

    if route == "ordinary_approve":
        with get_session_factory()() as session:
            session.get(KnowledgeItemORM, item_id).status = "active"
            session.commit()
        pending = client.post("/api/reviews", json=submission)
        assert pending.status_code == 201
        review_id = pending.json()["review"]["id"]
    elif route == "restore":
        assert client.patch(f"/api/knowledge/{item_id}", json={"content": "updated"}).status_code == 200

    observed_in_fresh_session = []

    async def fail_index(*_args):
        with get_session_factory()() as observer:
            observed_in_fresh_session.append(observer.get(KnowledgeItemORM, item_id).content)
        raise RuntimeError("private pg index failure detail")

    monkeypatch.setattr(governance, "_sync_applied_action", fail_index)
    if route == "ordinary_approve":
        res = client.post(f"/api/reviews/{review_id}/approve", json={"note": "ok"})
        assert res.status_code == 200 and res.json()["status"] == "approved"
        assert client.post(f"/api/reviews/{review_id}/approve", json={}).status_code == 409
    elif route == "draft_apply":
        res = client.post("/api/reviews", json=submission)
        assert res.status_code == 200 and res.json()["applied"] is True
    else:
        res = client.post(f"/api/knowledge/{item_id}/versions/1/restore")
        assert res.status_code == 200 and res.json()["content"] == "previous"

    expected = "previous" if route == "restore" else "updated"
    assert observed_in_fresh_session == [expected]
    assert client.get(f"/api/knowledge/{item_id}").json()["content"] == expected
    assert "REVIEW_INDEX_SYNC_FAILED: RuntimeError" in caplog.text
    assert "private pg index failure detail" not in caplog.text
    assert _pg_advisory_count() == 0
    print(f"[PG_P1_01] route={route} http=200 committed_content={expected}")


@pytest.mark.usefixtures("audit_warning_loggers")
def test_pg_index_embedding_failure_preserves_fts_and_redacts_log(
    pg_index_client, monkeypatch, caplog,
):
    """PostgreSQL embedding failure logs only exception type and leaves PG FTS intact."""
    client = pg_index_client
    target_title = f"pg-embed-{uuid4().hex[:8]}"
    item_id, review_id, _ = _pending_import(
        client, target_title=target_title, tag_name="embedfail", with_attachment=False,
    )
    secret_msg = "secret-provider-endpoint-fragment"

    class FailingEmbedder:
        async def embed(self, texts):
            raise ModelAdapterError(secret_msg)

    monkeypatch.setitem(client.app.dependency_overrides, governance.get_embedder, FailingEmbedder)
    res = client.post(f"/api/reviews/{review_id}/approve", json={"note": "embed"})
    assert res.status_code == 200 and res.json()["status"] == "approved"
    assert "INDEX_EMBEDDING_SYNC_FAILED: ModelAdapterError" in caplog.text
    assert secret_msg not in caplog.text

    with get_session_factory()() as session:
        hits = PostgresFullTextIndex(session).search("unique_token_embedfail", 5)
        assert any(str(hit_id) == item_id for hit_id, _ in hits)
    assert _pg_advisory_count() == 0
    print("[PG_EMBED_FAIL] http=200 fts_searchable=True log_redacted=True")
