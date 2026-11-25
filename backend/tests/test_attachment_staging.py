"""B3-T01 staging/manifest acceptance on real tmp filesystem + real SQLite.

Covers the frozen B3-T01 areas without mocking the filesystem or database:
manifest round-trip, schema bounds, duplicate/unsafe ZIP paths, ownership,
missing/corrupt staging, activity time, Active attachment-only rejection,
pending zero formal refs, reuse/conflict, archived target, and JSON entry
compatibility.  B3-T02/B4/B5 behaviour is intentionally not exercised.
"""

from __future__ import annotations

import base64
import contextlib
import errno
import json
import os
import struct
import time
import uuid
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import UUID

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event, func, select, text
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import Settings, get_settings
from app.db.session import dispose_db, get_engine, get_session_factory
from app.main import create_app
from app.models import AttachmentORM, KnowledgeItemORM, ReviewRequestORM
from app.services.attachment_promotion import PublishedAttachments, publish_staged
from app.services.attachment_staging import (
    ATTACHMENT_CONTENT_MISMATCH,
    ATTACHMENT_EMPTY,
    ATTACHMENT_IMPORT_UNSUPPORTED,
    ATTACHMENT_MANIFEST_CORRUPTED,
    ATTACHMENT_MANIFEST_DUPLICATE,
    ATTACHMENT_ONLY_IMPORT_UNSUPPORTED,
    ATTACHMENT_STAGING_INVALID,
    ATTACHMENT_STAGING_MISSING,
    ATTACHMENT_STORAGE_UNAVAILABLE,
    ATTACHMENT_WRITE_FAILED,
    IMPORT_ARCHIVE_INVALID,
    AttachmentManifestItem,
    AttachmentStagingError,
    AttachmentStagingService,
    logical_manifest_set,
    manifest_digest,
)
from app.services.markdown import MarkdownItemRepository
from knowledge_core.domain.entities import KnowledgeStatus
from knowledge_core.markdown.import_report import ImportEnvelope

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"staging-png"
PNG2 = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"staging-png-2"
PDF = b"%PDF-1.7\n" + b"staging-pdf"


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _zip(files: list[tuple[str, bytes]]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files:
            archive.writestr(name, data)
    return buffer.getvalue()


def _raw_single_entry_zip(
    name: bytes,
    data: bytes,
    *,
    method: int = zipfile.ZIP_STORED,
    compressed: bytes | None = None,
    crc: int | None = None,
) -> bytes:
    """Build a one-entry ZIP without ``zipfile`` normalization.

    This lets tests keep a raw NUL in the central-directory name and inject
    corrupt CRC / deflate streams that ``zipfile`` would otherwise repair or
    truncate on write.
    """
    payload = data if compressed is None else compressed
    checksum = zlib.crc32(data) if crc is None else crc
    local = struct.pack(
        "<IHHHHHIIIHH",
        0x04034B50,
        20,
        0,
        method,
        0,
        0,
        checksum,
        len(payload),
        len(data),
        len(name),
        0,
    ) + name + payload
    central = struct.pack(
        "<IHHHHHHIIIHHHHHII",
        0x02014B50,
        20,
        20,
        0,
        method,
        0,
        0,
        checksum,
        len(payload),
        len(data),
        len(name),
        0,
        0,
        0,
        0,
        0,
        0,
    ) + name
    eocd = struct.pack(
        "<IHHHHIIH",
        0x06054B50,
        0,
        0,
        1,
        1,
        len(central),
        len(local),
        0,
    )
    return local + central + eocd


def _markdown(title: str, body: str) -> bytes:
    return f"---\ntitle: {title}\n---\n{body}".encode()


def _attachment_zip(
    body: str = "新正文",
    *,
    title: str = "附件文档",
    attachment: tuple[str, bytes] = ("attachments/design.png", PNG),
) -> bytes:
    return _zip([("doc.md", _markdown(title, body)), attachment])


def _staging(client: TestClient, settings) -> AttachmentStagingService:
    return AttachmentStagingService(
        client.app.state.attachment_storage,
        max_file_bytes=settings.attachment_max_bytes,
        max_attachment_count=settings.attachment_import_max_count,
        max_total_bytes=settings.attachment_import_max_total_bytes,
        mime_allowlist=settings.attachment_mime_allowlist,
        staging_grace_seconds=settings.staging_grace_seconds,
        session_factory=get_session_factory(),
    )


def _staging_dirs(client: TestClient) -> list[Path]:
    root = Path(client.app.state.attachment_storage.staging_root)
    if not root.exists():
        return []
    return [path for path in root.iterdir() if path.is_dir()]


def _attachment_count() -> int:
    session = get_session_factory()()
    try:
        return int(
            session.scalar(select(func.count()).select_from(AttachmentORM)) or 0
        )
    finally:
        session.close()


def _reviews() -> list[ReviewRequestORM]:
    session = get_session_factory()()
    try:
        return list(session.scalars(select(ReviewRequestORM).order_by(ReviewRequestORM.id)))
    finally:
        session.close()


def _item(client: TestClient, *, title: str = "活跃条目", content: str = "旧正文",
          status: str = KnowledgeStatus.ACTIVE.value) -> str:
    response = client.post("/api/knowledge", json={"title": title, "content": content})
    assert response.status_code == 201
    item_id = response.json()["id"]
    session = get_session_factory()()
    try:
        row = session.get(KnowledgeItemORM, item_id)
        assert row is not None
        row.status = status
        session.commit()
    finally:
        session.close()
    return item_id


def _import_zip(
    client: TestClient,
    payload: bytes,
    *,
    target: str | None = None,
    batch: bool = False,
    extra: dict | None = None,
):
    body = {"archive_base64": _b64(payload)}
    if target is not None:
        body["target_item_id"] = target
    if extra:
        body.update(extra)
    path = "/api/knowledge/import/batch" if batch else "/api/knowledge/import"
    return client.post(path, json=body)


def _manifest_item(**overrides) -> dict:
    value = {
        "schema_version": 1,
        "staging_id": str(uuid.uuid4()),
        "ordinal": 1,
        "blob": "blobs/000001.bin",
        "filename": "a.png",
        "mime": "image/png",
        "size": 1,
        "storage_key": "a" * 64,
    }
    value.update(overrides)
    return value


class TestManifestSchema:
    def test_manifest_round_trip_and_complete_marker(self, client, settings):
        service = _staging(client, settings)
        parsed = service.inspect_zip(_attachment_zip())
        assert parsed.has_attachments
        staged = service.create_from_zip(parsed, document_path="doc.md")

        assert staged.directory == Path(service.staging_root) / str(staged.staging_id)
        assert (staged.directory / ".creating").is_file()
        assert (staged.directory / ".activity").is_file()
        complete = json.loads((staged.directory / ".complete").read_text("utf-8"))
        assert complete == {
            "completed_at": complete["completed_at"],
            "file_count": 1,
            "schema_version": 1,
            "staging_id": str(staged.staging_id),
            "total_bytes": len(PNG),
        }
        assert staged.manifest[0].blob == "blobs/000001.bin"
        assert staged.manifest[0].storage_key == staged.manifest[0].storage_key.lower()
        assert staged.manifest[0].size == len(PNG)
        assert (staged.directory / staged.manifest[0].blob).read_bytes() == PNG
        validated = service.validate_manifest(
            staged.staging_id, staged.manifest_dicts
        )
        assert validated == staged.manifest
        assert manifest_digest(validated) == manifest_digest(staged.manifest_dicts)
        assert logical_manifest_set(validated) == staged.logical_set
        assert service.staging_activity_at(staged.staging_id) is not None
        assert _attachment_count() == 0

    def test_unknown_fields_and_strict_bounds(self):
        with pytest.raises(ValidationError):
            AttachmentManifestItem.model_validate(
                _manifest_item(unexpected="x")
            )
        with pytest.raises(ValidationError):
            AttachmentManifestItem.model_validate(_manifest_item(ordinal=True))
        with pytest.raises(ValidationError):
            AttachmentManifestItem.model_validate(_manifest_item(size=0))
        with pytest.raises(ValidationError):
            AttachmentManifestItem.model_validate(
                _manifest_item(size=10 * 1024 * 1024 + 1)
            )
        with pytest.raises(ValidationError):
            AttachmentManifestItem.model_validate(
                _manifest_item(staging_id=str(uuid.uuid4()).upper())
            )
        with pytest.raises(ValidationError):
            AttachmentManifestItem.model_validate(
                _manifest_item(filename="../evil.png")
            )
        with pytest.raises(ValidationError):
            AttachmentManifestItem.model_validate(
                _manifest_item(mime="image/svg+xml")
            )
        with pytest.raises(ValidationError):
            AttachmentManifestItem.model_validate(
                _manifest_item(blob="blobs/000002.bin")
            )

    def test_duplicate_storage_key_rejected_before_staging(self, client, settings):
        service = _staging(client, settings)
        payload = _zip(
            [
                ("doc.md", _markdown("重复", "正文")),
                ("attachments/a.png", PNG),
                ("attachments/b.png", PNG),
            ]
        )
        with pytest.raises(AttachmentStagingError) as exc:
            service.create_from_zip(payload)
        assert exc.value.code == ATTACHMENT_MANIFEST_DUPLICATE
        assert _staging_dirs(client) == []

    def test_validate_manifest_duplicate_ordinal_key_and_staging_id(
        self, client, settings
    ):
        service = _staging(client, settings)
        payload = _zip(
            [
                ("doc.md", _markdown("多附件", "正文")),
                ("attachments/a.png", PNG),
                ("attachments/b.pdf", PDF),
            ]
        )
        staged = service.create_from_zip(payload)
        first, second = staged.manifest
        duplicate_ordinal = [
            first.model_dump(mode="json"),
            second.model_dump(mode="json"),
        ]
        duplicate_ordinal[1]["ordinal"] = 1
        duplicate_ordinal[1]["blob"] = "blobs/000001.bin"
        with pytest.raises(AttachmentStagingError) as exc:
            service.validate_manifest(staged.staging_id, duplicate_ordinal)
        assert exc.value.code == ATTACHMENT_MANIFEST_CORRUPTED

        duplicate_key = [
            first.model_dump(mode="json"),
            second.model_dump(mode="json"),
        ]
        duplicate_key[1]["storage_key"] = first.storage_key
        with pytest.raises(AttachmentStagingError) as exc:
            service.validate_manifest(staged.staging_id, duplicate_key)
        assert exc.value.code == ATTACHMENT_MANIFEST_DUPLICATE

        wrong_id = str(uuid.uuid4())
        wrong_staging = [
            first.model_dump(mode="json"),
            second.model_dump(mode="json"),
        ]
        for item in wrong_staging:
            item["staging_id"] = wrong_id
        with pytest.raises(AttachmentStagingError) as exc:
            service.validate_manifest(staged.staging_id, wrong_staging)
        assert exc.value.code == ATTACHMENT_STAGING_INVALID


class TestZipSafety:
    @pytest.mark.parametrize(
        "unsafe",
        [
            "../evil.png",
            "/evil.png",
            "//server/share/evil.png",
            "C:/evil.png",
            "attachments/a:b.png",
            "attachments/../evil.png",
        ],
    )
    def test_zip_traversal_absolute_unc_ads_backslash_rejected(
        self, client, settings, unsafe
    ):
        service = _staging(client, settings)
        payload = _zip(
            [
                ("doc.md", _markdown("恶意路径", "正文")),
                (unsafe, PNG),
            ]
        )
        with pytest.raises(AttachmentStagingError) as exc:
            service.inspect_zip(payload)
        assert exc.value.code == "IMPORT_ARCHIVE_INVALID"
        assert _staging_dirs(client) == []

    def test_duplicate_exact_and_case_normalized_paths_rejected(self, client, settings):
        service = _staging(client, settings)
        duplicate = _zip(
            [
                ("doc.md", _markdown("重复路径", "正文")),
                ("attachments/a.png", PNG),
                ("attachments/a.png", PNG2),
            ]
        )
        with pytest.raises(AttachmentStagingError) as exc:
            service.inspect_zip(duplicate)
        assert exc.value.code == "IMPORT_ARCHIVE_INVALID"

        case_collision = _zip(
            [
                ("doc.md", _markdown("大小写", "正文")),
                ("attachments/A.png", PNG),
                ("attachments/a.png", PNG2),
            ]
        )
        with pytest.raises(AttachmentStagingError) as exc:
            service.inspect_zip(case_collision)
        assert exc.value.code == "IMPORT_ARCHIVE_INVALID"

    def test_ambiguous_ownership_is_rejected_whole(self, client, settings):
        service = _staging(client, settings)
        payload = _zip(
            [
                ("a.md", _markdown("A", "A正文")),
                ("b.md", _markdown("B", "B正文")),
                ("attachments/design.png", PNG),
            ]
        )
        with pytest.raises(AttachmentStagingError) as exc:
            service.inspect_zip(payload)
        assert exc.value.code == ATTACHMENT_IMPORT_UNSUPPORTED
        assert _staging_dirs(client) == []

    def test_attachment_count_and_zip_bomb_limits(self, client, settings):
        service = _staging(client, settings)
        many = [
            ("doc.md", _markdown("过多", "正文")),
            *[
                (f"attachments/{index:03d}.png", PNG + bytes([index]))
                for index in range(101)
            ],
        ]
        with pytest.raises(AttachmentStagingError) as exc:
            service.inspect_zip(_zip(many))
        assert exc.value.code == "ATTACHMENT_COUNT_EXCEEDED"

        # Highly compressible 2 MiB text exceeds the frozen ratio guard and is
        # rejected from metadata before extraction.
        bomb = _zip(
            [
                ("doc.md", _markdown("炸弹", "正文")),
                ("attachments/bomb.txt", b"a" * (2 * 1024 * 1024)),
            ]
        )
        with pytest.raises(AttachmentStagingError) as exc:
            service.inspect_zip(bomb)
        assert exc.value.code == "IMPORT_ARCHIVE_INVALID"

    def test_mime_mismatch_rejected_before_staging(self, client, settings):
        service = _staging(client, settings)
        payload = _zip(
            [
                ("doc.md", _markdown("伪装", "正文")),
                ("attachments/fake.png", PDF),
            ]
        )
        with pytest.raises(AttachmentStagingError) as exc:
            service.create_from_zip(payload)
        assert exc.value.code == ATTACHMENT_CONTENT_MISMATCH
        assert _staging_dirs(client) == []


class TestStagingValidation:
    def _staged(self, client, settings):
        service = _staging(client, settings)
        staged = service.create_from_zip(_attachment_zip())
        return service, staged

    def test_missing_blob_and_missing_complete_are_invalid(self, client, settings):
        service, staged = self._staged(client, settings)
        (staged.directory / staged.manifest[0].blob).unlink()
        with pytest.raises(AttachmentStagingError) as exc:
            service.validate_manifest(staged.staging_id, staged.manifest_dicts)
        assert exc.value.code == ATTACHMENT_STAGING_INVALID

        service, staged = self._staged(client, settings)
        (staged.directory / ".complete").unlink()
        with pytest.raises(AttachmentStagingError) as exc:
            service.validate_manifest(staged.staging_id, staged.manifest_dicts)
        assert exc.value.code == ATTACHMENT_STAGING_INVALID

    def test_hash_mismatch_and_unexpected_file_are_invalid(self, client, settings):
        service, staged = self._staged(client, settings)
        blob = staged.directory / staged.manifest[0].blob
        blob.write_bytes(b"x" * len(PNG))
        with pytest.raises(AttachmentStagingError) as exc:
            service.validate_manifest(staged.staging_id, staged.manifest_dicts)
        assert exc.value.code == ATTACHMENT_STAGING_INVALID

        service, staged = self._staged(client, settings)
        (staged.directory / "extra.bin").write_bytes(b"extra")
        with pytest.raises(AttachmentStagingError) as exc:
            service.validate_manifest(staged.staging_id, staged.manifest_dicts)
        assert exc.value.code == ATTACHMENT_STAGING_INVALID

    def test_activity_uses_marker_and_file_mtime_not_root(self, client, settings):
        service, staged = self._staged(client, settings)
        now = time.time()
        blob = staged.directory / staged.manifest[0].blob
        old = now - 3600
        os.utime(blob, (old, old))
        os.utime(staged.directory / ".activity", (old, old))
        os.utime(staged.directory / ".creating", (old, old))
        os.utime(staged.directory / ".complete", (old, old))
        root_old = now - 10 * 86400
        os.utime(staged.directory, (root_old, root_old))
        activity = service.staging_activity_at(staged.staging_id)
        assert activity is not None
        assert activity.timestamp() >= old - 2
        assert activity.timestamp() > root_old

    def test_symlink_or_junction_in_staging_rejected(self, client, settings):
        service, staged = self._staged(client, settings)
        target_dir = staged.directory / "evil-target"
        target_dir.mkdir()
        (target_dir / "payload.bin").write_bytes(b"outside")
        link = staged.directory / "blobs" / "link"
        created = "symlink"
        try:
            os.symlink(target_dir, link, target_is_directory=True)
        except OSError:
            import subprocess

            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(target_dir)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                pytest.skip("platform denies symlink and junction creation")
            created = "junction"
        try:
            with pytest.raises(AttachmentStagingError) as exc:
                service.validate_manifest(staged.staging_id, staged.manifest_dicts)
            assert exc.value.code == ATTACHMENT_STAGING_INVALID
        finally:
            if link.exists() or link.is_symlink():
                with contextlib.suppress(OSError):
                    os.rmdir(link)
        assert created in {"symlink", "junction"}

    def test_empty_extra_directory_is_invalid(self, client, settings):
        service, staged = self._staged(client, settings)
        (staged.directory / "unexpected-empty-dir").mkdir()
        with pytest.raises(AttachmentStagingError) as exc:
            service.validate_manifest(staged.staging_id, staged.manifest_dicts)
        assert exc.value.code == ATTACHMENT_STAGING_INVALID

    def test_overlapping_roots_and_invalid_ids_rejected(self, client, settings):
        layout = client.app.state.attachment_storage
        overlapping = replace(layout, staging_root=layout.storage_root)
        service = AttachmentStagingService(
            overlapping, session_factory=get_session_factory()
        )
        with pytest.raises(AttachmentStagingError) as exc:
            service.create_from_zip(_attachment_zip())
        assert exc.value.code in {
            ATTACHMENT_STAGING_INVALID,
            ATTACHMENT_STORAGE_UNAVAILABLE,
        }
        with pytest.raises(AttachmentStagingError):
            service.staging_activity_at("../../outside")


class TestDraftImport:
    def test_draft_create_update_replay_and_share_blob(self, client):
        payload = _attachment_zip()
        first = _import_zip(client, payload)
        assert first.status_code == 201, first.text
        result = first.json()["items"][0]
        assert result["status"] == "created"
        assert "attachments_applied" in result["warnings"]
        item_id = result["item_id"]

        replay = _import_zip(client, payload, target=item_id)
        assert replay.status_code == 200, replay.text
        assert replay.json()["items"][0]["status"] == "skipped"
        assert "attachments_already_satisfied" in replay.json()["items"][0]["warnings"]

        other = _item(client, status="draft")
        updated = _import_zip(client, _attachment_zip(body="updated draft"), target=other)
        assert updated.status_code == 200, updated.text
        assert updated.json()["items"][0]["status"] == "updated"
        key = sha256(PNG).hexdigest()
        layout = client.app.state.attachment_storage
        assert layout.final_path(key).read_bytes() == PNG
        with get_session_factory()() as session:
            attachments = list(session.scalars(select(AttachmentORM)))
            assert {row.item_id for row in attachments} == {item_id, other}
            assert {row.storage_key for row in attachments} == {key}
        assert _staging_dirs(client) == []
        assert _reviews() == []

    def test_concurrent_draft_replay_creates_one_reference(self, client):
        target = _item(client, status="draft")
        payload = _attachment_zip()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(_import_zip, client, payload, target=target)
            second = pool.submit(_import_zip, client, payload, target=target)
            responses = [first.result(timeout=25), second.result(timeout=25)]
        assert all(response.status_code == 200 for response in responses), [
            response.text for response in responses
        ]
        assert {response.json()["items"][0]["status"] for response in responses} == {
            "skipped", "updated",
        }
        assert _attachment_count() == 1
        assert _staging_dirs(client) == []

    def test_draft_replay_reports_missing_blob_or_reference(self, client):
        payload = _attachment_zip()
        created = _import_zip(client, payload)
        assert created.status_code == 201, created.text
        item_id = created.json()["items"][0]["item_id"]
        key = sha256(PNG).hexdigest()
        client.app.state.attachment_storage.final_path(key).unlink()
        missing_blob = _import_zip(client, payload, target=item_id)
        assert missing_blob.status_code == 503
        assert missing_blob.json()["detail"] == "ATTACHMENT_BLOB_MISSING"
        with get_session_factory()() as session:
            row = session.scalar(select(AttachmentORM).where(AttachmentORM.storage_key == key))
            assert row is not None
            session.delete(row)
            session.commit()
        missing_ref = _import_zip(client, payload, target=item_id)
        assert missing_ref.status_code == 400
        assert missing_ref.json()["detail"] == "ATTACHMENT_IMPORT_UNSUPPORTED"
        assert _staging_dirs(client) == []

    def test_publish_precedes_business_write_and_rollback_preserves_blob(
        self, client, monkeypatch,
    ):
        target = _item(client, status="draft")
        layout = client.app.state.attachment_storage
        blob = layout.final_path(sha256(PNG).hexdigest())
        store = PublishedAttachments.save_references

        def fail_after_flush(plan, session, item_id):
            assert blob.read_bytes() == PNG
            store(plan, session, item_id)
            assert session.scalar(select(func.count()).select_from(AttachmentORM)) == 1
            raise RuntimeError("draft reference write rolled back")

        def check_before_write(_conn, _cursor, statement, *_args):
            if statement.lstrip().upper().startswith("UPDATE KNOWLEDGE_ITEM"):
                assert blob.read_bytes() == PNG

        engine = get_engine()
        event.listen(engine, "before_cursor_execute", check_before_write)
        try:
            with monkeypatch.context() as patch:
                patch.setattr(PublishedAttachments, "save_references", fail_after_flush)
                with pytest.raises(RuntimeError, match="draft reference write rolled back"):
                    _import_zip(client, _attachment_zip(), target=target)
        finally:
            event.remove(engine, "before_cursor_execute", check_before_write)
        assert blob.read_bytes() == PNG
        assert _attachment_count() == 0
        assert _staging_dirs(client) == []
        with get_session_factory()() as session:
            assert session.get(KnowledgeItemORM, target).content == "旧正文"
        assert _import_zip(client, _attachment_zip(), target=target).status_code == 200
        assert _attachment_count() == 1

    def test_archive_after_publish_preserves_archived_item(self, client, monkeypatch):
        target = _item(client, status="draft")

        def publish_and_archive(*args):
            plan = publish_staged(*args)
            with get_session_factory()() as independent:
                independent.get(KnowledgeItemORM, target).status = "archived"
                independent.commit()
            return plan

        monkeypatch.setattr("app.services.markdown.publish_staged", publish_and_archive)
        response = _import_zip(client, _attachment_zip(), target=target)
        assert response.status_code == 409
        assert response.json()["detail"] == "SOURCE_CHANGED_DURING_WAIT"
        with get_session_factory()() as session:
            row = session.get(KnowledgeItemORM, target)
            assert row.status == "archived"
            assert row.content == "旧正文"
        assert _attachment_count() == 0
        assert _staging_dirs(client) == []

    def test_ambiguous_draft_commit_retains_staging_for_orp(self, client, monkeypatch):
        target = _item(client, status="draft")
        factory = client.app.state.markdown_service.session_factory
        base_session = factory.class_
        store = PublishedAttachments.save_references

        def track_attachments(plan, session, item_id):
            store(plan, session, item_id)
            session.info["draft_commit_uncertain"] = True

        class UnknownCommitSession(base_session):
            def commit(self):
                super().commit()
                if self.info.pop("draft_commit_uncertain", False):
                    raise RuntimeError("draft commit acknowledgement lost")

        with monkeypatch.context() as patch:
            patch.setattr(PublishedAttachments, "save_references", track_attachments)
            patch.setattr(factory, "class_", UnknownCommitSession)
            with pytest.raises(RuntimeError, match="draft commit acknowledgement lost"):
                _import_zip(client, _attachment_zip(), target=target)
        assert _attachment_count() == 1
        assert len(_staging_dirs(client)) == 1
        assert (_staging_dirs(client)[0] / ".complete").is_file()
        replay = _import_zip(client, _attachment_zip(), target=target)
        assert replay.status_code == 200
        assert replay.json()["items"][0]["status"] == "skipped"
        assert _attachment_count() == 1

    def test_publish_io_failure_cleans_staging_without_draft_writes(
        self, client, monkeypatch,
    ):
        target = _item(client, status="draft")
        layout = client.app.state.attachment_storage

        def fail(*args, **kwargs):
            raise OSError(errno.EIO, "injected publish failure")

        with monkeypatch.context() as patch:
            patch.setattr("app.services.attachment_storage.os.link", fail)
            patch.setattr("app.services.attachment_storage.os.rename", fail)
            response = _import_zip(client, _attachment_zip(), target=target)
        assert response.status_code == 503, response.text
        assert response.json()["detail"] == "ATTACHMENT_WRITE_FAILED"
        assert not layout.final_path(sha256(PNG).hexdigest()).exists()
        assert not list(layout.temp_dir.iterdir())
        assert _attachment_count() == 0
        assert _staging_dirs(client) == []
        with get_session_factory()() as session:
            assert session.get(KnowledgeItemORM, target).content == "旧正文"

    def test_pg_concurrent_drafts_share_blob(self, tmp_path, monkeypatch):
        url = os.environ.get("EXPLAINLAB_PG_TEST_URL")
        if not url:
            pytest.skip("EXPLAINLAB_PG_TEST_URL unavailable for real PostgreSQL HTTP")
        parsed = make_url(url)
        if not (parsed.database or "").startswith("explainlab_b3_http_"):
            pytest.skip("dedicated explainlab_b3_http_ PostgreSQL database required")
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
                first = _item(client, status="draft")
                second = _item(client, status="draft")
                data = PNG + first.encode()
                payload = _attachment_zip(attachment=("attachments/design.png", data))
                with get_engine().connect() as one, get_engine().connect() as two:
                    assert one.scalar(text("select pg_backend_pid()")) != two.scalar(
                        text("select pg_backend_pid()")
                    )
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        requests = [
                            pool.submit(_import_zip, client, payload, target=target)
                            for target in (first, second)
                        ]
                        for pending in requests:
                            response = pending.result(timeout=30)
                            assert response.status_code == 200, response.text
                    key = sha256(data).hexdigest()
                    stmt = select(AttachmentORM.item_id).where(
                        AttachmentORM.storage_key == key
                    )
                    assert set(one.scalars(stmt)) == set(two.scalars(stmt)) == {
                        first, second,
                    }
                assert client.app.state.attachment_storage.final_path(key).read_bytes() == data
                assert _staging_dirs(client) == []
        finally:
            dispose_db()


class TestActiveImport:
    def test_active_attachment_only_rejected_with_zero_staging(self, client, settings):
        item_id = _item(client, content="相同正文")
        payload = _attachment_zip(body="相同正文", title="活跃条目")
        response = _import_zip(client, payload, target=item_id)
        assert response.status_code == 400
        assert response.json()["detail"] == ATTACHMENT_ONLY_IMPORT_UNSUPPORTED
        assert _staging_dirs(client) == []
        assert _reviews() == []
        assert _attachment_count() == 0

    def test_active_content_change_creates_pending_manifest_zero_formal_refs(
        self, client, settings
    ):
        item_id = _item(client, content="旧正文")
        response = _import_zip(client, _attachment_zip(body="新正文"), target=item_id)
        assert response.status_code == 202, response.text
        body = response.json()
        assert body["pending_review"] == 1
        assert body["items"][0]["status"] == "pending_review"

        reviews = _reviews()
        assert len(reviews) == 1
        payload = json.loads(reviews[0].payload)
        envelope = ImportEnvelope.from_review_payload(payload)
        assert envelope is not None
        assert len(envelope.attachments) == 1
        manifest = AttachmentManifestItem.model_validate(envelope.attachments[0])
        staging_dir = Path(client.app.state.attachment_storage.staging_root) / manifest.staging_id
        assert staging_dir.is_dir()
        assert (staging_dir / ".complete").is_file()
        assert _attachment_count() == 0
        service = _staging(client, settings)
        assert service.validate_manifest(manifest.staging_id, envelope.attachments)

        session = get_session_factory()()
        try:
            row = MarkdownItemRepository(session).get(UUID(item_id))
        finally:
            session.close()
        assert row is not None
        assert row.title == "活跃条目"
        assert row.content == "旧正文"

    def test_same_source_same_attachment_set_reuses_pending(
        self, client, settings
    ):
        item_id = _item(client, content="旧正文")
        payload = _attachment_zip(body="新正文")
        first = _import_zip(client, payload, target=item_id)
        assert first.status_code == 202, first.text
        first_review = _reviews()[0]
        first_payload = json.loads(first_review.payload)
        first_staging_id = first_payload["__a1_import"]["attachments"][0]["staging_id"]

        second = _import_zip(client, payload, target=item_id)
        assert second.status_code == 200, second.text
        report = second.json()
        assert report["reused_pending"] == 1
        assert report["items"][0]["status"] == "reused_pending"
        assert "attachments_pending_reused" in report["items"][0]["warnings"]
        assert len(_reviews()) == 1
        assert len(_staging_dirs(client)) == 1
        second_payload = json.loads(_reviews()[0].payload)
        assert (
            second_payload["__a1_import"]["attachments"][0]["staging_id"]
            == first_staging_id
        )

    def test_reuse_pending_with_invalid_staging_fails_closed(
        self, client, settings
    ):
        item_id = _item(client, content="旧正文")
        payload = _attachment_zip(body="新正文")
        first = _import_zip(client, payload, target=item_id)
        assert first.status_code == 202, first.text
        review = _reviews()[0]
        envelope_payload = json.loads(review.payload)
        staging_id = envelope_payload["__a1_import"]["attachments"][0]["staging_id"]
        staging_dir = Path(client.app.state.attachment_storage.staging_root) / staging_id
        (staging_dir / ".complete").unlink()

        second = _import_zip(client, payload, target=item_id)
        assert second.status_code == 409
        assert second.json()["detail"] == ATTACHMENT_STAGING_INVALID
        assert len(_reviews()) == 1
        assert len(_staging_dirs(client)) == 1

    def test_different_attachment_set_conflicts_without_new_staging(
        self, client, settings
    ):
        item_id = _item(client, content="旧正文")
        first = _import_zip(client, _attachment_zip(body="新正文"), target=item_id)
        assert first.status_code == 202, first.text
        second_payload = _attachment_zip(
            body="新正文",
            attachment=("attachments/design.pdf", PDF),
        )
        second = _import_zip(client, second_payload, target=item_id)
        assert second.status_code == 409
        assert second.json()["detail"] == "SOURCE_HAS_PENDING_IMPORT"
        assert len(_reviews()) == 1
        assert len(_staging_dirs(client)) == 1
        assert _attachment_count() == 0

    def test_zero_document_attachment_zip_is_attachment_only_or_unsupported(
        self, client, settings
    ):
        item_id = _item(client, content="旧正文")
        attachment_only = _zip([("attachments/design.png", PNG)])
        response = _import_zip(client, attachment_only, target=item_id)
        assert response.status_code == 400
        assert response.json()["detail"] == ATTACHMENT_ONLY_IMPORT_UNSUPPORTED
        assert _staging_dirs(client) == []
        assert _reviews() == []

        response = _import_zip(client, attachment_only)
        assert response.status_code == 400
        assert response.json()["detail"] == ATTACHMENT_IMPORT_UNSUPPORTED
        assert _staging_dirs(client) == []

    def test_already_applied_same_hash_with_satisfied_attachment_is_skipped(
        self, client, settings, monkeypatch
    ):
        text = _markdown("已应用", "已应用正文").decode("utf-8")
        first = client.post(
            "/api/knowledge/import",
            json={"content": text, "filename": "doc.md"},
        )
        assert first.status_code == 201, first.text
        item_id = first.json()["items"][0]["item_id"]
        session = get_session_factory()()
        try:
            row = session.get(KnowledgeItemORM, item_id)
            assert row is not None
            row.status = KnowledgeStatus.ACTIVE.value
            session.commit()
        finally:
            session.close()
        upload = client.post(
            f"/api/knowledge/{item_id}/attachments",
            json={
                "filename": "design.png",
                "mime": "image/png",
                "content_base64": _b64(PNG),
            },
        )
        assert upload.status_code in {200, 201}, upload.text
        manager = client.app.state.storage_key_lock
        key = upload.json()["storage_key"]
        guard = manager.acquire_many([key], "b3-replay-contender", heartbeat_seconds=0)
        assert guard is not None
        try:
            with monkeypatch.context() as contention:
                contention.setattr(manager, "wait_seconds", 0.1)
                blocked = _import_zip(
                    client,
                    _zip([("doc.md", text.encode()), ("attachments/design.png", PNG)]),
                    target=item_id,
                )
            assert blocked.status_code == 409, blocked.text
            assert blocked.json()["detail"] == "STORAGE_LOCK_TIMEOUT"
        finally:
            assert guard.release()
        response = _import_zip(
            client,
            _zip([("doc.md", text.encode()), ("attachments/design.png", PNG)]),
            target=item_id,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["skipped"] == 1
        assert "attachments_already_satisfied" in body["items"][0]["warnings"]
        assert _staging_dirs(client) == []
        assert len(_reviews()) == 0

    def test_pending_with_attachments_rejects_same_hash_empty_set(
        self, client, settings
    ):
        item_id = _item(client, content="旧正文")
        first = _import_zip(client, _attachment_zip(body="新正文"), target=item_id)
        assert first.status_code == 202, first.text
        second = client.post(
            "/api/knowledge/import",
            json={
                "content": _markdown("附件文档", "新正文").decode("utf-8"),
                "filename": "doc.md",
                "target_item_id": item_id,
            },
        )
        assert second.status_code == 409
        assert second.json()["detail"] == "SOURCE_HAS_PENDING_IMPORT"
        assert len(_reviews()) == 1
        assert len(_staging_dirs(client)) == 1

    def test_archived_target_with_attachment_zip_rejected(self, client, settings):
        item_id = _item(
            client,
            content="旧正文",
            status=KnowledgeStatus.ARCHIVED.value,
        )
        response = _import_zip(
            client, _attachment_zip(body="新正文"), target=item_id
        )
        assert response.status_code == 400
        assert response.json()["detail"] == ATTACHMENT_IMPORT_UNSUPPORTED
        assert _staging_dirs(client) == []
        assert _reviews() == []


class TestEntryCompatibility:
    def test_single_and_batch_json_attachment_compatibility(self, client):
        single = client.post(
            "/api/knowledge/import",
            json={
                "content": "正文",
                "filename": "a.md",
                "attachments": [{"filename": "a.png"}],
            },
        )
        assert single.status_code == 400
        assert single.json()["detail"] == ATTACHMENT_IMPORT_UNSUPPORTED

        batch = client.post(
            "/api/knowledge/import/batch",
            json={
                "documents": [
                    {
                        "content": "---\ntitle: 附件\n---\n正文",
                        "filename": "with-att.md",
                        "attachments": [{"filename": "a.png"}],
                    },
                    {
                        "content": "---\ntitle: 正常\n---\n正文",
                        "filename": "ok.md",
                    },
                ]
            },
        )
        assert batch.status_code == 200
        body = batch.json()
        assert body["unsupported"] == 1
        assert body["created"] == 1
        statuses = {item["filename"]: item["status"] for item in body["items"]}
        assert statuses["with-att.md"] == "unsupported"
        assert statuses["ok.md"] == "created"
        assert _staging_dirs(client) == []

        top_level = client.post(
            "/api/knowledge/import/batch",
            json={
                "documents": [
                    {"content": "---\ntitle: 顶层\n---\n正文", "filename": "top.md"}
                ],
                "attachments": [{"filename": "top.png"}],
            },
        )
        assert top_level.status_code == 200
        assert top_level.json()["unsupported"] == 1
        assert _staging_dirs(client) == []

    def test_attachment_zip_cannot_borrow_json_attachment_fields(self, client):
        payload = _attachment_zip()
        response = client.post(
            "/api/knowledge/import",
            json={
                "archive_base64": _b64(payload),
                "attachments": [{"filename": "extra.png"}],
            },
        )
        assert response.status_code == 400
        assert response.json()["detail"] == ATTACHMENT_IMPORT_UNSUPPORTED
        assert _staging_dirs(client) == []

    def test_zip_without_attachments_still_supports_multiple_docs(self, client):
        payload = _zip(
            [
                ("a.md", _markdown("A", "A正文")),
                ("b.md", _markdown("B", "B正文")),
            ]
        )
        response = _import_zip(client, payload, batch=True)
        assert response.status_code == 200, response.text
        assert response.json()["created"] == 2


class TestDiscardAndSweep:
    def test_discard_respects_pending_and_sweep_activity(self, client, settings):
        item_id = _item(client, content="旧正文")
        response = _import_zip(client, _attachment_zip(body="新正文"), target=item_id)
        assert response.status_code == 202, response.text
        review = _reviews()[0]
        payload = json.loads(review.payload)
        staging_id = payload["__a1_import"]["attachments"][0]["staging_id"]
        service = _staging(client, settings)

        assert service.discard_rejected(staging_id) is False
        decision = service.sweep_candidate(staging_id)
        assert decision.candidate is False
        assert decision.reason == "active_pending"

        session = get_session_factory()()
        try:
            row = session.get(ReviewRequestORM, review.id)
            assert row is not None
            row.status = "approved"
            session.commit()
        finally:
            session.close()

        staging_dir = Path(client.app.state.attachment_storage.staging_root) / staging_id
        old = time.time() - 2 * 86400
        for path in staging_dir.rglob("*"):
            if path.is_file():
                os.utime(path, (old, old))
        os.utime(staging_dir, (old, old))
        decision = service.sweep_candidate(staging_id)
        assert decision.candidate is True
        assert decision.reason == "activity"
        assert service.discard_committed(staging_id) is True
        assert not staging_dir.exists()

    def test_missing_staging_and_failed_complete_do_not_look_complete(
        self, client, settings, monkeypatch
    ):
        service = _staging(client, settings)
        with pytest.raises(AttachmentStagingError) as exc:
            service.validate_manifest(str(uuid.uuid4()), [
                _manifest_item(staging_id=str(uuid.uuid4()))
            ])
        assert exc.value.code == ATTACHMENT_STAGING_MISSING

        parsed = service.inspect_zip(_attachment_zip())
        original = service._write_complete

        def fail_complete(path, marker):
            raise AttachmentStagingError("ATTACHMENT_WRITE_FAILED")

        monkeypatch.setattr(service, "_write_complete", fail_complete)
        with pytest.raises(AttachmentStagingError):
            service.create_from_zip(parsed)
        monkeypatch.setattr(service, "_write_complete", original)
        assert _staging_dirs(client) == []


class TestStagingGuardLifetime:
    def test_guard_covers_creation_and_releases_after_commit(
        self, client, settings
    ):
        item_id = _item(client, content="旧正文")
        service = _staging(client, settings)
        observed: list[tuple[Path, bool, bool, int]] = []

        def recording_sync(path):
            path = Path(path)
            observed.append(
                (
                    path,
                    any(lock.locked() for lock in service._guards.values()),
                    (path / ".complete").exists(),
                    len(list(path.glob("*.bin"))),
                )
            )

        service._directory_sync = recording_sync
        client.app.state.attachment_staging_service = service

        response = _import_zip(client, _attachment_zip(body="新正文"), target=item_id)
        assert response.status_code == 202, response.text
        assert observed
        assert all(held for _, held, _, _ in observed)
        review = _reviews()[0]
        envelope = ImportEnvelope.from_review_payload(json.loads(review.payload))
        assert envelope is not None
        sid = envelope.attachments[0]["staging_id"]
        staging_dir = Path(client.app.state.attachment_storage.staging_root) / sid
        assert (staging_dir / ".complete").is_file()
        last_for_staging = [entry for entry in observed if entry[0] == staging_dir][-1]
        assert last_for_staging[2] is True
        blob_syncs = [entry for entry in observed if entry[0].name == "blobs"]
        assert blob_syncs and all(entry[3] >= 1 for entry in blob_syncs)
        assert sid not in service._guards

    def test_guard_held_during_business_commit(
        self, client, settings, monkeypatch
    ):
        item_id = _item(client, content="旧正文")
        service = _staging(client, settings)
        client.app.state.attachment_staging_service = service
        seen: dict[str, object] = {}
        # Resolve the session class through the factory the import service
        # actually uses (a top-level ``sqlalchemy.orm.Session`` import can
        # resolve to a duplicate class object under pytest's importlib mode).
        factory = client.app.state.markdown_service._factory
        base_session = factory.class_

        class ObservedSession(base_session):
            def commit(self):
                sid = seen.get("sid")
                if sid is not None and "held" not in seen:
                    lock = service._guards[sid]
                    seen["held"] = lock.locked()
                    acquired = lock.acquire(blocking=False)
                    seen["acquired_elsewhere"] = acquired
                    if acquired:
                        lock.release()
                return super().commit()

        monkeypatch.setattr(factory, "class_", ObservedSession)
        from app.services.governance import SQLAlchemyReviewRepository

        original_save = SQLAlchemyReviewRepository.save_review

        def save_probe(repo, review):
            seen["sid"] = review.payload["__a1_import"]["attachments"][0][
                "staging_id"
            ]
            return original_save(repo, review)

        monkeypatch.setattr(
            SQLAlchemyReviewRepository, "save_review", save_probe
        )
        response = _import_zip(
            client, _attachment_zip(body="新正文"), target=item_id
        )

        assert response.status_code == 202, response.text
        assert seen["held"] is True
        assert seen["acquired_elsewhere"] is False
        assert str(seen["sid"]) not in service._guards

    def test_known_precommit_failure_cleans_staging(
        self, client, settings, monkeypatch
    ):
        item_id = _item(client, content="旧正文")
        service = _staging(client, settings)
        client.app.state.attachment_staging_service = service

        def boom(session):
            raise RuntimeError("submit failed before commit")

        monkeypatch.setattr("app.services.markdown.build_review_service", boom)
        with pytest.raises(RuntimeError, match="submit failed before commit"):
            _import_zip(
                client, _attachment_zip(body="新正文"), target=item_id
            )

        assert _staging_dirs(client) == []
        assert _reviews() == []
        assert _attachment_count() == 0
        assert all(not lock.locked() for lock in service._guards.values())

    @pytest.mark.parametrize("rollback_fails", [False, True])
    def test_ambiguous_commit_keeps_staging_for_orp(
        self, client, settings, monkeypatch, rollback_fails
    ):
        item_id = _item(client, content="旧正文")
        service = _staging(client, settings)
        client.app.state.attachment_staging_service = service

        def mark_pending(session, flush_context, instances):
            if any(
                type(obj).__name__ == "ReviewRequestORM"
                and obj.status == "pending"
                for obj in session.new
            ):
                session.info["b3_pending_commit"] = True

        factory = client.app.state.markdown_service._factory
        base_session = factory.class_

        class ObservedSession(base_session):
            def commit(self):
                super().commit()
                if self.info.pop("b3_pending_commit", False):
                    if rollback_fails:
                        self.info["b3_fail_rollback"] = True
                    raise RuntimeError("simulated ambiguous commit outcome")

            def rollback(self):
                super().rollback()
                if self.info.pop("b3_fail_rollback", False):
                    raise RuntimeError("simulated rollback disconnect")

        event.listen(base_session, "before_flush", mark_pending)
        monkeypatch.setattr(factory, "class_", ObservedSession)
        try:
            with pytest.raises(
                RuntimeError,
                match=("simulated rollback disconnect" if rollback_fails
                       else "simulated ambiguous commit outcome"),
            ):
                _import_zip(
                    client, _attachment_zip(body="新正文"), target=item_id
                )
        finally:
            event.remove(base_session, "before_flush", mark_pending)

        reviews = _reviews()
        assert len(reviews) == 1
        assert reviews[0].status == "pending"
        assert len(_staging_dirs(client)) == 1
        assert all(not lock.locked() for lock in service._guards.values())
        assert _attachment_count() == 0


class TestDirectoryDurability:
    def test_directory_sync_failure_rejects_without_pending(
        self, client, settings
    ):
        item_id = _item(client, content="旧正文")

        def failing_sync(path):
            raise OSError(5, "simulated directory fsync failure")

        service = AttachmentStagingService(
            client.app.state.attachment_storage,
            max_file_bytes=settings.attachment_max_bytes,
            max_attachment_count=settings.attachment_import_max_count,
            max_total_bytes=settings.attachment_import_max_total_bytes,
            mime_allowlist=settings.attachment_mime_allowlist,
            staging_grace_seconds=settings.staging_grace_seconds,
            session_factory=get_session_factory(),
            directory_sync=failing_sync,
        )
        client.app.state.attachment_staging_service = service

        response = _import_zip(client, _attachment_zip(body="新正文"), target=item_id)
        assert response.status_code == 503
        assert response.json()["detail"] == ATTACHMENT_WRITE_FAILED
        assert _staging_dirs(client) == []
        assert _reviews() == []
        assert _attachment_count() == 0
        assert all(not lock.locked() for lock in service._guards.values())

    def test_directory_sync_is_platform_explicit(self):
        from app.services.attachment_staging import _default_directory_sync

        missing = Path("Z:/explainlab-nonexistent-dir-sync")
        if os.name == "nt":
            _default_directory_sync(missing)
        else:
            with pytest.raises(AttachmentStagingError) as exc:
                _default_directory_sync(missing)
            assert exc.value.code == ATTACHMENT_WRITE_FAILED


class TestEmptyAttachmentRejection:
    @pytest.mark.parametrize(
        "name",
        [
            "attachments/note.txt",
            "attachments/note.md",
            "attachments/data.csv",
        ],
    )
    def test_zero_byte_attachment_rejected_before_staging(self, client, name):
        item_id = _item(client, content="旧正文")
        before_attachments = _attachment_count()
        payload = _zip(
            [
                ("doc.md", _markdown("附件文档", "新正文")),
                (name, b""),
            ]
        )
        response = _import_zip(client, payload, target=item_id)
        assert response.status_code == 400
        assert response.json()["detail"] == ATTACHMENT_EMPTY
        assert _staging_dirs(client) == []
        assert _attachment_count() == before_attachments
        assert _reviews() == []


class TestCorruptZipMapping:
    def test_crc_mismatch_maps_to_import_archive_invalid(self, client):
        item_id = _item(client, content="旧正文")
        payload = _raw_single_entry_zip(
            b"attachments/design.png",
            PNG,
            crc=zlib.crc32(PNG) ^ 0xFFFFFFFF,
        )
        response = _import_zip(client, payload, target=item_id)
        assert response.status_code == 400
        assert response.json()["detail"] == IMPORT_ARCHIVE_INVALID
        assert _staging_dirs(client) == []
        assert _reviews() == []

    def test_invalid_deflate_stream_maps_to_import_archive_invalid(self, client):
        item_id = _item(client, content="旧正文")
        payload = _raw_single_entry_zip(
            b"attachments/design.png",
            PNG,
            method=zipfile.ZIP_DEFLATED,
            compressed=b"\xff\xff\xff\xff",
        )
        response = _import_zip(client, payload, target=item_id)
        assert response.status_code == 400
        assert response.json()["detail"] == IMPORT_ARCHIVE_INVALID
        assert _staging_dirs(client) == []

    def test_truncated_deflate_maps_to_import_archive_invalid(self, client):
        item_id = _item(client, content="旧正文")
        compressed = zlib.compress(PNG * 8)
        payload = _raw_single_entry_zip(
            b"attachments/design.png",
            PNG * 8,
            method=zipfile.ZIP_DEFLATED,
            compressed=compressed[:-8],
        )
        response = _import_zip(client, payload, target=item_id)
        assert response.status_code == 400
        assert response.json()["detail"] == IMPORT_ARCHIVE_INVALID
        assert _staging_dirs(client) == []


class TestPendingFailClosed:
    def test_null_import_envelope_prevents_staging_cleanup(self, client, settings):
        item_id = _item(client, content="旧正文")
        service = _staging(client, settings)
        client.app.state.attachment_staging_service = service
        response = _import_zip(client, _attachment_zip(body="新正文"), target=item_id)
        assert response.status_code == 202, response.text
        staging_dir, = _staging_dirs(client)
        with get_session_factory()() as session:
            review = session.scalar(select(ReviewRequestORM))
            assert review is not None and review.status == "pending"
            payload = json.loads(review.payload)
            payload["__a1_import"] = None
            review.payload = json.dumps(payload)
            session.commit()

        assert service.pending_staging_ids() is None
        assert not service.discard_rejected(staging_dir.name)
        decision = service.sweep_candidate(staging_dir.name)
        assert not decision.candidate
        assert decision.reason == "pending_manifest_malformed"
        assert (staging_dir / ".complete").is_file()

    def test_missing_session_factory_discard_fails_closed(self, client):
        service = AttachmentStagingService(
            client.app.state.attachment_storage,
            session_factory=None,
        )
        staged = service.create_from_zip(_attachment_zip())
        assert service.pending_staging_ids() is None
        assert service.discard_committed(staged.staging_id) is False
        assert staged.directory.is_dir()

    def test_missing_session_factory_sweep_fails_closed(self, client):
        service = AttachmentStagingService(
            client.app.state.attachment_storage,
            session_factory=None,
        )
        staged = service.create_from_zip(_attachment_zip())
        decision = service.sweep_candidate(staged.staging_id)
        assert decision.candidate is False
        assert decision.reason == "pending_manifest_malformed"
        assert staged.directory.is_dir()

    def test_pending_query_failure_preserves_staging(self, client):
        def broken_factory():
            raise RuntimeError("database unavailable")

        service = AttachmentStagingService(
            client.app.state.attachment_storage,
            session_factory=broken_factory,
        )
        staged = service.create_from_zip(_attachment_zip())
        assert service.discard_rejected(staged.staging_id) is False
        assert service.sweep_candidate(staged.staging_id).candidate is False
        assert staged.directory.is_dir()


class TestZipBudgetBoundaries:
    def _small_service(self, client, *, max_total_bytes):
        return AttachmentStagingService(
            client.app.state.attachment_storage,
            max_total_bytes=max_total_bytes,
        )

    def test_original_nul_filename_rejected(self, client):
        service = self._small_service(client, max_total_bytes=1024 * 1024)
        payload = _raw_single_entry_zip(b"attachments/a\x00.png", PNG)
        with pytest.raises(AttachmentStagingError) as exc:
            service.inspect_zip(payload)
        assert exc.value.code == IMPORT_ARCHIVE_INVALID

    def test_whole_archive_compressed_budget_includes_unselected(self, client):
        service = self._small_service(client, max_total_bytes=512)
        payload = _zip(
            [
                ("doc.md", _markdown("预算", "正文")),
                ("attachments/a.bin", os.urandom(400)),
                ("other/blob.bin", os.urandom(400)),
            ]
        )
        with pytest.raises(AttachmentStagingError) as exc:
            service.inspect_zip(payload)
        assert exc.value.code == IMPORT_ARCHIVE_INVALID

    def test_root_manifest_is_included_in_budget(self, client):
        service = self._small_service(client, max_total_bytes=700)
        manifest = json.dumps({"pad": "a" * 600}).encode("utf-8")
        payload = _zip(
            [
                ("doc.md", _markdown("预算", "正文")),
                ("attachments/design.png", os.urandom(400)),
                ("manifest.json", manifest),
            ]
        )
        with pytest.raises(AttachmentStagingError) as exc:
            service.inspect_zip(payload)
        assert exc.value.code == "ATTACHMENT_TOTAL_TOO_LARGE"


class TestPendingReuseGuard:
    def test_reuse_validates_manifest_under_guard(
        self, client, settings, monkeypatch
    ):
        item_id = _item(client, content="旧正文")
        payload = _attachment_zip(body="新正文")
        first = _import_zip(client, payload, target=item_id)
        assert first.status_code == 202, first.text
        service = _staging(client, settings)
        client.app.state.attachment_staging_service = service
        observed: list[bool] = []
        original = service.validate_manifest_locked

        def checked(staging_id, manifest, **kwargs):
            observed.append(service._guards[str(staging_id)].locked())
            return original(staging_id, manifest, **kwargs)

        monkeypatch.setattr(service, "validate_manifest_locked", checked)
        second = _import_zip(client, payload, target=item_id)
        assert second.status_code == 200, second.text
        assert observed == [True]
        assert len(_staging_dirs(client)) == 1

    def test_reuse_rereads_pending_under_guard(
        self, client, settings, monkeypatch
    ):
        item_id = _item(client, content="旧正文")
        payload = _attachment_zip(body="新正文")
        first = _import_zip(client, payload, target=item_id)
        assert first.status_code == 202, first.text
        review = _reviews()[0]
        service = _staging(client, settings)
        client.app.state.attachment_staging_service = service
        original_guard = service.staging_guard

        @contextlib.contextmanager
        def guard_after_resolving(staging_id):
            session = get_session_factory()()
            try:
                row = session.get(ReviewRequestORM, review.id)
                assert row is not None
                row.status = "approved"
                session.commit()
            finally:
                session.close()
            with original_guard(staging_id):
                yield

        monkeypatch.setattr(service, "staging_guard", guard_after_resolving)
        second = _import_zip(client, payload, target=item_id)
        assert second.status_code == 409
        assert second.json()["detail"] == "SOURCE_CHANGED_DURING_WAIT"
        assert len(_reviews()) == 1
        assert len(_staging_dirs(client)) == 1
