"""B2 附件 HTTP API 验收（真实 SQLite + 真实 tmp 文件系统）。

覆盖冻结 acceptance-plan ATT-01…13 的 HTTP/DB/FS 部分；不替 B3 staging、
B4 approve 或 B5 GC/ORP worker 取证。所有断言直接查询真实数据库与文件系统，
不以响应体推断替代。
"""

from __future__ import annotations

import base64
import errno
import hashlib
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

import app.models  # noqa: F401  ORM 元数据
from alembic import command
from app.api.routes import attachments as attachments_route
from app.core.config import Settings, get_settings
from app.db.session import dispose_db, get_engine, get_session_factory
from app.db.storage_lock import LockGuard, PostgresStorageKeyLock
from app.main import create_app
from app.models import AttachmentORM, GcTaskORM, KnowledgeItemORM
from app.services import attachment_storage
from app.services import attachments as attachments_module
from knowledge_core.domain.entities import GcStatus

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"png-body"
PDF = b"%PDF-1.7\n" + b"pdf-body"
TEXT = "普通文本\n".encode()


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _upload(
    client: TestClient,
    item_id: str,
    data: bytes = PNG,
    *,
    mime: str = "image/png",
    filename: str = "design.png",
):
    return client.post(
        f"/api/knowledge/{item_id}/attachments",
        json={"filename": filename, "mime": mime, "content_base64": _b64(data)},
    )


def _item(client: TestClient, title: str = "附件条目") -> str:
    response = client.post("/api/knowledge", json={"title": title, "content": "正文"})
    assert response.status_code == 201
    return response.json()["id"]


def _set_status(item_id: str, status: str) -> None:
    with get_session_factory()() as session:
        row = session.get(KnowledgeItemORM, item_id)
        assert row is not None
        row.status = status
        session.commit()


def _attachment_rows(item_id: str | None = None) -> list[AttachmentORM]:
    with get_session_factory()() as session:
        stmt = select(AttachmentORM).order_by(AttachmentORM.created_at, AttachmentORM.id)
        if item_id is not None:
            stmt = stmt.where(AttachmentORM.item_id == item_id)
        return list(session.scalars(stmt))


def _gc_rows() -> list[GcTaskORM]:
    with get_session_factory()() as session:
        return list(session.scalars(select(GcTaskORM)))


def _layout(client: TestClient):
    return client.app.state.attachment_storage


def _blob(client: TestClient, key: str) -> Path:
    return _layout(client).final_path(key)


def _temp_files(client: TestClient) -> list[Path]:
    return list(_layout(client).temp_dir.iterdir())


def test_upload_png_creates_row_blob_and_download_headers(client: TestClient):
    item_id = _item(client)
    response = _upload(client, item_id, PNG)
    assert response.status_code == 201
    body = response.json()
    key = hashlib.sha256(PNG).hexdigest()
    assert body["storage_key"] == body["content_hash"] == key
    assert body["size"] == len(PNG)
    assert body["mime"] == "image/png"
    assert body["filename"] == "design.png"
    assert body["item_id"] == item_id
    assert response.headers["location"] == (
        f"/api/knowledge/{item_id}/attachments/{body['id']}"
    )

    blob = _blob(client, key)
    assert blob == _layout(client).storage_root / key[:2] / key[2:4] / key
    assert blob.read_bytes() == PNG
    assert _temp_files(client) == []
    assert len(_attachment_rows(item_id)) == 1

    download = client.get(f"/api/knowledge/{item_id}/attachments/{body['id']}")
    assert download.status_code == 200
    assert download.content == PNG
    assert download.headers["content-type"] == "image/png"
    assert download.headers["content-length"] == str(len(PNG))
    assert download.headers["etag"] == f'"{key}"'
    assert download.headers["x-content-type-options"] == "nosniff"
    assert download.headers["cache-control"] == "private, max-age=0, must-revalidate"
    disposition = download.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="design.png"')
    assert "filename*=UTF-8''design.png" in disposition

    listed = client.get(f"/api/knowledge/{item_id}/attachments")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [body["id"]]


def test_pdf_is_accepted_and_declared_magic_is_checked(client: TestClient):
    item_id = _item(client)
    response = _upload(client, item_id, PDF, mime="application/pdf", filename="paper.pdf")
    assert response.status_code == 201
    assert response.json()["mime"] == "application/pdf"
    mismatch = _upload(client, item_id, PDF, mime="image/png", filename="paper.pdf")
    assert mismatch.status_code == 415
    assert mismatch.json()["detail"] == "ATTACHMENT_CONTENT_MISMATCH"


def test_same_content_two_items_shares_one_physical_blob(client: TestClient):
    item_a = _item(client, "A")
    item_b = _item(client, "B")
    first = _upload(client, item_a, PNG)
    second = _upload(client, item_b, PNG, filename="copy.png")
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert first.json()["storage_key"] == second.json()["storage_key"]
    key = first.json()["storage_key"]
    shard = _blob(client, key).parent
    assert [path.name for path in shard.iterdir()] == [key]
    with get_session_factory()() as session:
        count = session.scalar(
            select(func.count())
            .select_from(AttachmentORM)
            .where(AttachmentORM.storage_key == key)
        )
    assert count == 2

    duplicate = _upload(client, item_a, PNG, filename="again.png")
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == first.json()["id"]
    assert len(_attachment_rows(item_a)) == 1


def test_size_and_base64_limits_write_nothing(client: TestClient):
    item_id = _item(client)
    too_large = b"a" * (10 * 1024 * 1024 + 1)
    response = _upload(client, item_id, too_large, mime="text/plain", filename="big.txt")
    assert response.status_code == 413
    assert response.json()["detail"] == "ATTACHMENT_TOO_LARGE"

    invalid = client.post(
        f"/api/knowledge/{item_id}/attachments",
        json={"filename": "x.txt", "mime": "text/plain", "content_base64": "YQ==="},
    )
    assert invalid.status_code == 400
    assert invalid.json()["detail"] == "ATTACHMENT_BASE64_INVALID"

    empty = _upload(client, item_id, b"", mime="text/plain", filename="empty.txt")
    assert empty.status_code == 400
    assert empty.json()["detail"] == "ATTACHMENT_EMPTY"

    assert _attachment_rows(item_id) == []
    assert _temp_files(client) == []
    assert not any(
        path.is_file() for path in _layout(client).storage_root.rglob("*")
    )


def test_content_mismatch_svg_and_text_subtypes(client: TestClient):
    item_id = _item(client)
    mismatch = _upload(
        client, item_id, b"not a png", mime="image/png", filename="fake.png"
    )
    assert mismatch.status_code == 415
    assert mismatch.json()["detail"] == "ATTACHMENT_CONTENT_MISMATCH"

    text_as_png = _upload(
        client, item_id, TEXT, mime="image/png", filename="fake.png"
    )
    assert text_as_png.status_code == 415
    assert text_as_png.json()["detail"] == "ATTACHMENT_CONTENT_MISMATCH"

    svg = _upload(
        client,
        item_id,
        b"<svg xmlns='http://www.w3.org/2000/svg'/>",
        mime="image/svg+xml",
        filename="vector.svg",
    )
    assert svg.status_code == 415
    assert svg.json()["detail"] == "ATTACHMENT_MIME_UNSUPPORTED"

    for mime in ("text/plain", "text/markdown", "text/csv"):
        response = _upload(
            client,
            item_id,
            f"same {mime}".encode(),
            mime=mime,
            filename="note.dat",
        )
        assert response.status_code == 201
        assert response.json()["mime"] == mime

    text_svg = _upload(
        client, item_id, b"<svg/>", mime="text/plain", filename="safe.svg"
    )
    assert text_svg.status_code == 201
    assert text_svg.json()["mime"] == "text/plain"
    assert len(_attachment_rows(item_id)) == 4


def test_filename_is_sanitized_and_extra_fields_rejected(client: TestClient):
    item_id = _item(client)
    traversal = _upload(
        client, item_id, PNG, filename="../../evil\r\n.png"
    )
    assert traversal.status_code == 201
    assert traversal.json()["filename"] == "evil.png"
    download = client.get(
        f"/api/knowledge/{item_id}/attachments/{traversal.json()['id']}"
    )
    disposition = download.headers["content-disposition"]
    assert "\r" not in disposition and "\n" not in disposition
    assert ".." not in disposition

    windows = _upload(client, item_id, b"%PDF-1.7\nx", mime="application/pdf",
                      filename="C:\\temp\\paper.pdf")
    assert windows.status_code == 201
    assert windows.json()["filename"] == "paper.pdf"

    reserved = _upload(client, item_id, TEXT, mime="text/plain", filename="CON")
    assert reserved.status_code == 201
    assert reserved.json()["filename"] == "_CON"

    unicode = _upload(
        client, item_id, TEXT + b"unicode", mime="text/plain", filename="报告 2026.txt"
    )
    assert unicode.status_code == 201
    assert unicode.json()["filename"] == "报告 2026.txt"
    unicode_download = client.get(
        f"/api/knowledge/{item_id}/attachments/{unicode.json()['id']}"
    )
    disposition = unicode_download.headers["content-disposition"]
    assert "filename*=UTF-8''%E6%8A%A5%E5%91%8A%202026.txt" in disposition
    assert disposition.isascii()

    empty = _upload(client, item_id, TEXT, mime="text/plain", filename="")
    assert empty.status_code == 400
    assert empty.json()["detail"] == "ATTACHMENT_FILENAME_INVALID"

    extra = client.post(
        f"/api/knowledge/{item_id}/attachments",
        json={
            "filename": "x.txt",
            "mime": "text/plain",
            "content_base64": _b64(TEXT),
            "path": "escape",
        },
    )
    assert extra.status_code == 422

    missing = client.post(
        f"/api/knowledge/{item_id}/attachments",
        json={"filename": "x.txt", "mime": "text/plain"},
    )
    assert missing.status_code == 422


def test_unknown_item_and_cross_item_do_not_leak(client: TestClient):
    missing_item = str(uuid4())
    assert _upload(client, missing_item, PNG).status_code == 404
    assert _upload(client, missing_item, PNG).json()["detail"] == "ITEM_NOT_FOUND"
    assert client.get(
        f"/api/knowledge/{missing_item}/attachments"
    ).status_code == 404

    item_a = _item(client, "A")
    item_b = _item(client, "B")
    created = _upload(client, item_a, PNG)
    attachment_id = created.json()["id"]

    assert client.get(f"/api/knowledge/{item_b}/attachments").json() == []
    assert client.get(
        f"/api/knowledge/{item_b}/attachments/{attachment_id}"
    ).status_code == 404
    assert client.delete(
        f"/api/knowledge/{item_b}/attachments/{attachment_id}"
    ).status_code == 404
    assert client.get(
        f"/api/knowledge/{item_a}/attachments/{uuid4()}"
    ).status_code == 404


def test_delete_last_reference_enqueues_gc_but_shared_reference_does_not(
    client: TestClient,
):
    item_a = _item(client, "A")
    item_b = _item(client, "B")
    first = _upload(client, item_a, PNG).json()
    second = _upload(client, item_b, PNG).json()
    key = first["storage_key"]

    shared_delete = client.delete(
        f"/api/knowledge/{item_a}/attachments/{first['id']}"
    )
    assert shared_delete.status_code == 204
    assert _attachment_rows(item_a) == []
    assert _blob(client, key).read_bytes() == PNG
    assert _gc_rows() == []

    last_delete = client.delete(
        f"/api/knowledge/{item_b}/attachments/{second['id']}"
    )
    assert last_delete.status_code == 204
    assert _blob(client, key).read_bytes() == PNG
    tasks = _gc_rows()
    assert len(tasks) == 1
    assert tasks[0].storage_key == key
    assert tasks[0].status == GcStatus.PENDING.value

    assert client.delete(
        f"/api/knowledge/{item_b}/attachments/{second['id']}"
    ).status_code == 404


def test_delete_does_not_duplicate_active_gc_task(client: TestClient):
    item_id = _item(client)
    first = _upload(client, item_id, PNG).json()
    assert client.delete(
        f"/api/knowledge/{item_id}/attachments/{first['id']}"
    ).status_code == 204
    assert len(_gc_rows()) == 1

    second = _upload(client, item_id, PNG).json()
    assert second["id"] != first["id"]
    assert client.delete(
        f"/api/knowledge/{item_id}/attachments/{second['id']}"
    ).status_code == 204
    assert len(_gc_rows()) == 1


def test_archived_blocks_upload_but_allows_list_download_delete(
    client: TestClient,
):
    item_id = _item(client)
    created = _upload(client, item_id, PNG).json()
    _set_status(item_id, "archived")

    blocked = _upload(client, item_id, PDF, mime="application/pdf", filename="x.pdf")
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "ATTACHMENT_ITEM_ARCHIVED"
    assert len(_attachment_rows(item_id)) == 1
    assert _temp_files(client) == []

    assert client.get(f"/api/knowledge/{item_id}/attachments").status_code == 200
    download = client.get(
        f"/api/knowledge/{item_id}/attachments/{created['id']}"
    )
    assert download.status_code == 200 and download.content == PNG
    assert client.delete(
        f"/api/knowledge/{item_id}/attachments/{created['id']}"
    ).status_code == 204
    assert _attachment_rows(item_id) == []
    assert _blob(client, created["storage_key"]).exists()


def test_archive_committed_after_publish_leaves_zero_references(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    item_id = _item(client)
    original = attachments_module.publish_no_clobber

    def publish_then_archive(*args, **kwargs):
        result = original(*args, **kwargs)
        _set_status(item_id, "archived")
        return result

    monkeypatch.setattr(attachments_module, "publish_no_clobber", publish_then_archive)
    response = _upload(client, item_id, PNG)
    assert response.status_code == 409
    assert response.json()["detail"] == "ATTACHMENT_ITEM_ARCHIVED"
    assert _attachment_rows(item_id) == []
    assert _blob(client, hashlib.sha256(PNG).hexdigest()).read_bytes() == PNG
    assert _temp_files(client) == []


def test_corrupted_and_missing_blob_return_503(client: TestClient):
    item_id = _item(client)
    first = _upload(client, item_id, PNG).json()
    blob = _blob(client, first["storage_key"])
    original = blob.read_bytes()
    blob.write_bytes(b"\x00" * len(original))

    response = client.get(
        f"/api/knowledge/{item_id}/attachments/{first['id']}"
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "ATTACHMENT_BLOB_CORRUPTED"
    # 列表只读元数据，不做 hash 校验。
    assert client.get(f"/api/knowledge/{item_id}/attachments").status_code == 200

    blob.unlink()
    missing = client.get(
        f"/api/knowledge/{item_id}/attachments/{first['id']}"
    )
    assert missing.status_code == 503
    assert missing.json()["detail"] == "ATTACHMENT_BLOB_MISSING"
    assert len(_attachment_rows(item_id)) == 1


@pytest.mark.parametrize("io_call", [
    "link",
    pytest.param("rename", marks=pytest.mark.skipif(os.name != "nt", reason="Windows rename fallback")),
])
def test_publish_io_failure_returns_503_and_cleans_temp(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, io_call: str
):
    item_id = _item(client)
    target = _blob(client, hashlib.sha256(PNG).hexdigest())
    calls = []
    original_link, original_rename = os.link, os.rename

    def fault(name, original, source, destination, *args, **kwargs):
        if Path(destination) != target:
            return original(source, destination, *args, **kwargs)
        source = Path(source)
        assert source.parent == _layout(client).temp_dir
        assert source.read_bytes() == PNG
        calls.append(name)
        if name == io_call:
            raise OSError(errno.EIO, "injected publication I/O fault")
        unsupported = OSError(errno.ENOTSUP, "injected Windows hard-link limitation")
        unsupported.winerror = 50
        raise unsupported

    with monkeypatch.context() as patch:
        patch.setattr(attachment_storage.os, "link", lambda *a, **kw: fault("link", original_link, *a, **kw))
        if io_call == "rename":
            patch.setattr(
                attachment_storage.os, "rename", lambda *a, **kw: fault("rename", original_rename, *a, **kw)
            )
        response = _upload(client, item_id)

    assert calls == (["link"] if io_call == "link" else ["link", "rename"])
    assert response.status_code == 503
    assert response.json() == {"detail": "ATTACHMENT_WRITE_FAILED"}
    assert _attachment_rows() == []
    assert _temp_files(client) == []
    assert not target.exists()
    assert not any(path.is_file() for path in _layout(client).storage_root.rglob("*"))


def test_upload_repairs_missing_blob_for_existing_reference(client: TestClient):
    item_id = _item(client)
    first = _upload(client, item_id, PNG).json()
    _blob(client, first["storage_key"]).unlink()

    repaired = _upload(client, item_id, PNG)
    assert repaired.status_code == 200
    assert repaired.json()["id"] == first["id"]
    assert _blob(client, first["storage_key"]).read_bytes() == PNG
    assert len(_attachment_rows(item_id)) == 1


def test_upload_refuses_to_reuse_corrupted_blob(client: TestClient):
    item_id = _item(client)
    first = _upload(client, item_id, PNG).json()
    blob = _blob(client, first["storage_key"])
    blob.write_bytes(b"\x00" * len(PNG))

    response = _upload(client, item_id, PNG)
    assert response.status_code == 409
    assert response.json()["detail"] == "ATTACHMENT_KEY_COLLISION"
    assert blob.read_bytes() == b"\x00" * len(PNG)
    assert len(_attachment_rows(item_id)) == 1
    assert _temp_files(client) == []


def test_storage_lock_timeout_returns_409_and_writes_nothing(client: TestClient):
    item_id = _item(client)
    key = hashlib.sha256(PNG).hexdigest()
    manager = client.app.state.storage_key_lock
    service = client.app.state.attachment_service
    guard = manager.acquire_many([key], "test-blocker", heartbeat_seconds=0)
    assert guard is not None
    previous_wait = service.lock_wait_seconds
    service.lock_wait_seconds = 0.05
    try:
        response = _upload(client, item_id, PNG)
    finally:
        service.lock_wait_seconds = previous_wait
        guard.release()
    assert response.status_code == 409
    assert response.json()["detail"] == "STORAGE_LOCK_TIMEOUT"
    assert _attachment_rows(item_id) == []
    assert _temp_files(client) == []
    assert not _blob(client, key).exists()


def test_archived_failure_releases_key_lock_after_rollback(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    item_id = _item(client)
    service = client.app.state.attachment_service
    previous_wait = service.lock_wait_seconds
    service.lock_wait_seconds = 0.05
    original = attachments_module.publish_no_clobber

    def publish_then_archive(*args, **kwargs):
        result = original(*args, **kwargs)
        _set_status(item_id, "archived")
        return result

    try:
        monkeypatch.setattr(
            attachments_module, "publish_no_clobber", publish_then_archive
        )
        assert _upload(client, item_id, PNG).status_code == 409
        monkeypatch.setattr(attachments_module, "publish_no_clobber", original)
        _set_status(item_id, "active")
        recovered = _upload(client, item_id, PNG)
    finally:
        service.lock_wait_seconds = previous_wait
    assert recovered.status_code == 201
    assert len(_attachment_rows(item_id)) == 1


def test_commit_failure_leaves_no_row_but_published_blob(client: TestClient, monkeypatch):
    item_id = _item(client)
    key = hashlib.sha256(PNG).hexdigest()
    original_commit = Session.commit

    def failing_commit(self):
        raise RuntimeError("commit failed")

    monkeypatch.setattr(Session, "commit", failing_commit)
    response = _upload(client, item_id, PNG)
    monkeypatch.setattr(Session, "commit", original_commit)

    assert response.status_code == 500
    assert response.json()["detail"] == "ATTACHMENT_FAILED"
    assert _attachment_rows(item_id) == []
    assert _blob(client, key).read_bytes() == PNG
    assert _temp_files(client) == []


def test_concurrent_same_item_upload_reuses_one_reference(client: TestClient):
    item_id = _item(client)
    barrier = threading.Barrier(2)

    def send(filename: str):
        barrier.wait(timeout=5)
        return _upload(client, item_id, PNG, filename=filename)

    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(send, ("one.png", "two.png")))
    assert sorted(response.status_code for response in responses) == [200, 201]
    assert len({response.json()["id"] for response in responses}) == 1
    assert len(_attachment_rows(item_id)) == 1
    assert len(list(_blob(client, hashlib.sha256(PNG).hexdigest()).parent.iterdir())) == 1


def test_concurrent_different_items_share_one_physical_blob(client: TestClient):
    item_a = _item(client, "A")
    item_b = _item(client, "B")
    barrier = threading.Barrier(2)

    def send(item_id: str):
        barrier.wait(timeout=5)
        return _upload(client, item_id, PDF, mime="application/pdf", filename="p.pdf")

    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(send, (item_a, item_b)))
    assert [response.status_code for response in responses] == [201, 201]
    key = responses[0].json()["storage_key"]
    assert responses[1].json()["storage_key"] == key
    assert len(list(_blob(client, key).parent.iterdir())) == 1
    assert len(_attachment_rows()) == 2


def test_large_text_download_is_streamed_from_verified_handle(client: TestClient):
    item_id = _item(client)
    payload = ("段落" * 400_000).encode()  # >2 MiB, 合法 UTF-8
    created = _upload(client, item_id, payload, mime="text/plain", filename="long.txt")
    assert created.status_code == 201
    response = client.get(
        f"/api/knowledge/{item_id}/attachments/{created.json()['id']}"
    )
    assert response.status_code == 200
    assert response.content == payload
    assert response.headers["content-length"] == str(len(payload))


def test_download_streams_the_same_verified_handle(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    item_id = _item(client)
    created = _upload(client, item_id, PNG).json()
    original_iter_file = attachments_route.iter_file
    handles: list[object] = []

    def spy(handle):
        handles.append(handle)
        yield from original_iter_file(handle)

    monkeypatch.setattr(attachments_route, "iter_file", spy)
    response = client.get(
        f"/api/knowledge/{item_id}/attachments/{created['id']}"
    )
    assert response.status_code == 200
    assert response.content == PNG
    assert len(handles) == 1
    assert handles[0].closed


def test_list_sorts_by_created_at_then_id(client: TestClient):
    item_id = _item(client)
    ids = [
        _upload(client, item_id, data).json()["id"]
        for data in (PNG + b"1", PNG + b"2", PNG + b"3")
    ]
    base = datetime(2026, 1, 1, tzinfo=UTC)
    with get_session_factory()() as session:
        for offset, attachment_id in enumerate(ids):
            row = session.get(AttachmentORM, attachment_id)
            assert row is not None
            row.created_at = base + timedelta(seconds=offset)
        session.commit()

    listed = client.get(f"/api/knowledge/{item_id}/attachments")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == ids


@pytest.fixture(scope="module")
def pg_http_url():
    url = os.environ.get("EXPLAINLAB_PG_TEST_URL")
    if not url:
        pytest.skip("EXPLAINLAB_PG_TEST_URL unavailable for real PostgreSQL HTTP")
    parsed = make_url(url)
    assert parsed.get_backend_name() == "postgresql"
    assert (parsed.database or "").startswith("explainlab_b2_http_"), "dedicated B2 test DB required"
    backend = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("DATABASE_URL", url)
        get_settings.cache_clear()
        try:
            command.upgrade(cfg, "head")
        finally:
            get_settings.cache_clear()
    return url


@pytest.fixture
def pg_http_client(pg_http_url, tmp_path):
    settings = Settings(database_url=pg_http_url, data_dir=tmp_path / "data", _env_file=None)
    try:
        with TestClient(create_app(settings)) as client:
            assert isinstance(client.app.state.storage_key_lock, PostgresStorageKeyLock)
            with get_engine().connect() as conn:
                assert conn.execute(text("SELECT current_database()")).scalar_one() == (
                    make_url(pg_http_url).database
                )
            yield client
    finally:
        dispose_db()


def _assert_pg_blob(client, key, data):
    assert _blob(client, key).read_bytes() == data
    assert list(_blob(client, key).parent.iterdir()) == [_blob(client, key)]
    assert _temp_files(client) == []


def test_pg_http_upload_download_and_shared_reference(pg_http_client):
    client = pg_http_client
    item_a, item_b = _item(client), _item(client)
    data = PNG + item_a.encode()
    first, second = (_upload(client, item, data) for item in (item_a, item_b))
    assert first.status_code == second.status_code == 201
    key = hashlib.sha256(data).hexdigest()
    assert first.json()["storage_key"] == second.json()["storage_key"] == key
    assert _attachment_rows(item_a)[0].storage_key == _attachment_rows(item_b)[0].storage_key == key
    assert len(_attachment_rows(item_a)) == len(_attachment_rows(item_b)) == 1
    url = f"/api/knowledge/{item_a}/attachments/{first.json()['id']}"
    response = client.get(url)
    assert response.status_code == 200 and response.content == data
    assert response.headers["etag"] == f'"{key}"'
    _assert_pg_blob(client, key, data)
    assert client.delete(url).status_code == 204
    assert _attachment_rows(item_a) == [] and len(_attachment_rows(item_b)) == 1
    assert all(task.storage_key != key for task in _gc_rows())
    _assert_pg_blob(client, key, data)
    print(f"PG HTTP upload=201/201, download=200, shared delete=204; remaining=1; SHA-256={key}")


def test_pg_http_archive_update_blocks_upload_select_for_update(pg_http_client):
    client = pg_http_client
    item = _item(client)
    data = PNG + item.encode()
    engine = get_engine()
    selecting = threading.Event()
    upload_pids = []

    def observe_sql(conn, _cursor, statement, *_args):
        if "knowledge_item" in statement.lower() and "FOR UPDATE" in statement.upper():
            upload_pids.append(conn.connection.driver_connection.info.backend_pid)
            selecting.set()

    event.listen(engine, "before_cursor_execute", observe_sql)
    try:
        with ThreadPoolExecutor(1) as pool, engine.connect() as archiver:
            archiver_pid = archiver.execute(text("SELECT pg_backend_pid()")).scalar_one()
            archiver.execute(
                text("UPDATE knowledge_item SET status='archived' WHERE id=:id"), {"id": item}
            )
            pending = pool.submit(_upload, client, item, data)
            assert selecting.wait(timeout=10)
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as observer:
                deadline = time.monotonic() + 5
                while archiver_pid not in observer.execute(
                    text("SELECT pg_blocking_pids(:pid)"), {"pid": upload_pids[0]}
                ).scalar_one():
                    assert time.monotonic() < deadline
                    time.sleep(0.02)
            archiver.commit()
            response = pending.result(timeout=10)
    finally:
        event.remove(engine, "before_cursor_execute", observe_sql)
    assert upload_pids[0] != archiver_pid
    assert response.status_code == 409
    assert response.json() == {"detail": "ATTACHMENT_ITEM_ARCHIVED"}
    assert _attachment_rows(item) == []
    _assert_pg_blob(client, hashlib.sha256(data).hexdigest(), data)
    print(f"PG FOR UPDATE backend={upload_pids[0]}, archiver={archiver_pid}; HTTP=409, references=0")


def test_pg_http_concurrent_uploads_wait_on_distinct_advisory_sessions(
    pg_http_client, monkeypatch,
):
    client = pg_http_client
    item = _item(client)
    data = PNG + item.encode()
    key = hashlib.sha256(data).hexdigest()
    engine = get_engine()
    manager = client.app.state.storage_key_lock
    original_connect = manager._connect
    original_commit = Session.commit
    first_at_commit, second_connected, allow_commit = (threading.Event() for _ in range(3))
    pids = []

    def observe_connect(deadline):
        conn = original_connect(deadline)
        pids.append(conn.connection.driver_connection.info.backend_pid)
        if len(pids) == 2:
            second_connected.set()
        return conn

    def hold_first_commit(session):
        if not first_at_commit.is_set():
            first_at_commit.set()
            assert allow_commit.wait(timeout=8)
        return original_commit(session)

    monkeypatch.setattr(manager, "_connect", observe_connect)
    monkeypatch.setattr(Session, "commit", hold_first_commit)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(_upload, client, item, data)
        try:
            assert first_at_commit.wait(timeout=8)
            second = pool.submit(_upload, client, item, data)
            assert second_connected.wait(timeout=5)
            assert pids[0] != pids[1] and not second.done()
            with engine.connect() as observer:
                holding = observer.execute(
                    text("SELECT pid FROM pg_locks WHERE locktype='advisory' AND granted AND pid IN (:a,:b)"),
                    {"a": pids[0], "b": pids[1]},
                ).scalars().all()
            assert holding == [pids[0]]
            assert _attachment_rows(item) == []
        finally:
            allow_commit.set()
        responses = first.result(timeout=10), second.result(timeout=10)
    assert [r.status_code for r in responses] == [201, 200]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    assert len(_attachment_rows(item)) == 1
    _assert_pg_blob(client, key, data)
    print(f"PG advisory backends={pids}; holder={holding}; HTTP=201/200; one row/blob")


@pytest.mark.parametrize("fail_commit", [False, True], ids=["commit", "rollback"])
def test_pg_http_finishes_transaction_before_advisory_release(pg_http_client, monkeypatch, fail_commit):
    client = pg_http_client
    item = _item(client)
    data = PNG + item.encode()
    original_commit, original_rollback, original_release = Session.commit, Session.rollback, LockGuard.release
    sequence = []

    def commit(session):
        if fail_commit:
            session.execute(text("SELECT 1 / 0"))  # Real server error aborts the write transaction.
        original_commit(session)
        sequence.append("committed")

    def rollback(session):
        original_rollback(session)
        sequence.append("rolled back")

    def release(guard):
        pid = guard.pg_state.driver_connection.info.backend_pid
        with get_engine().connect() as observer:
            held = observer.execute(
                text("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND granted AND pid=:pid"),
                {"pid": pid},
            ).scalar_one()
        assert held == 1
        assert len(_attachment_rows(item)) == int(not fail_commit)
        sequence.append("released")
        return original_release(guard)

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", commit)
        patch.setattr(Session, "rollback", rollback)
        patch.setattr(LockGuard, "release", release)
        response = _upload(client, item, data)
    assert sequence == ["rolled back" if fail_commit else "committed", "released"]
    if fail_commit:
        assert response.status_code == 500
        assert response.json() == {"detail": "ATTACHMENT_FAILED"}
    else:
        assert response.status_code == 201
    key = hashlib.sha256(data).hexdigest()
    _assert_pg_blob(client, key, data)
    guard = client.app.state.storage_key_lock.acquire_many([key], "release-observer", heartbeat_seconds=0)
    assert guard is not None
    assert guard.release()
    print(f"PG transaction order={sequence}; references={len(_attachment_rows(item))}; HTTP={response.status_code}")
