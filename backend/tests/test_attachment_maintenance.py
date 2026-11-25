"""GC and orphan recovery through true storage, SQLite, and HTTP routes."""

import base64
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from threading import Event
from uuid import uuid4
from zipfile import ZipFile

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import delete, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import Settings, get_settings
from app.db.orphan_scan_lock import orphan_scan_leadership
from app.db.session import dispose_db, get_engine, get_session_factory
from app.db.storage_lock import new_owner
from app.main import create_app
from app.models import AttachmentORM, GcTaskORM, KnowledgeItemORM, ReviewRequestORM, StorageLockORM
from app.services import attachment_maintenance
from app.services.attachment_maintenance import GcWorker
from app.services.attachment_staging import AttachmentStagingError
from app.services.repositories_v2 import SQLAlchemyGcTaskRepository
from knowledge_core.domain.entities import GcStatus, GcTask, utcnow

DATA = b"%PDF-1.7\nattachment maintenance"
KEY = sha256(DATA).hexdigest()


@pytest.fixture
def maintenance(client):
    worker = client.app.state.attachment_maintenance
    ops = worker.gc.layout.data_dir / "ops"
    deadline = time.monotonic() + 5
    while not list(ops.glob("attachment-consistency-*.json")):
        assert time.monotonic() < deadline, "startup orphan report did not appear"
        time.sleep(0.02)
    return worker


def _item(client):
    response = client.post("/api/knowledge", json={"title": "note", "content": "text"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _post_attachment(client, item, data):
    return client.post(f"/api/knowledge/{item}/attachments", json={
        "filename": "review.pdf", "mime": "application/pdf",
        "content_base64": base64.b64encode(data).decode(),
    })


def _upload(client, item, data=DATA):
    response = _post_attachment(client, item, data)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _delete(client, item, attachment):
    response = client.delete(f"/api/knowledge/{item}/attachments/{attachment}")
    assert response.status_code == 204, response.text


def _tasks():
    with get_session_factory()() as session:
        return SQLAlchemyGcTaskRepository(session).list_tasks(storage_key=KEY)


def _slot(layout, task):
    return layout.quarantine_dir / f"{KEY}.{task.id}"


def _advance_isolation(task, slot):
    now = utcnow()
    previous = now - timedelta(hours=25)
    with get_session_factory()() as session:
        row = session.get(GcTaskORM, str(task.id))
        row.quarantined_at = previous
        row.next_retry_at = previous + timedelta(hours=24)
        row.lease_expires_at = previous
        session.commit()
    os.utime(slot, (previous.timestamp(), previous.timestamp()))


def _mark_expired(path):
    past = (utcnow() - timedelta(hours=25)).timestamp()
    os.utime(path, (past, past))


def test_shared_references_then_gc_quarantine_and_purge(client, maintenance):
    gc = maintenance.gc
    item_a, item_b = _item(client), _item(client)
    first, second = _upload(client, item_a), _upload(client, item_b)
    blob = gc.layout.final_path(KEY)
    _delete(client, item_a, first)
    assert _tasks() == []
    assert blob.read_bytes() == DATA
    _delete(client, item_b, second)
    assert _tasks()[0].status == GcStatus.PENDING
    assert blob.read_bytes() == DATA
    gc.run_due()
    task = _tasks()[0]
    slot = _slot(gc.layout, task)
    assert task.status == GcStatus.RUNNING
    assert task.attempts == 1
    assert task.next_retry_at - task.quarantined_at == timedelta(hours=24)
    assert not blob.exists()
    assert slot.read_bytes() == DATA
    gc.run_due()
    assert _tasks()[0].attempts == 1
    assert slot.is_file()
    _advance_isolation(task, slot)
    gc.run_due()
    assert _tasks()[0].status == GcStatus.DONE
    assert _tasks()[0].attempts == 2
    assert not slot.exists()


def test_old_slot_purge_leaves_republished_formal_for_successor(client, maintenance):
    gc = maintenance.gc
    item = _item(client)
    _delete(client, item, _upload(client, item))
    gc.run_due()
    first = _tasks()[0]
    old_slot = _slot(gc.layout, first)
    _delete(client, item, _upload(client, item))
    assert len(_tasks()) == 1
    _advance_isolation(first, old_slot)
    gc.run_due()
    done, successor = _tasks()
    assert done.status == GcStatus.DONE
    assert successor.status == GcStatus.PENDING
    assert not old_slot.exists()
    assert gc.layout.final_path(KEY).read_bytes() == DATA
    gc.run_due()
    assert _slot(gc.layout, successor).read_bytes() == DATA


def test_two_workers_only_claim_one_slot(client, maintenance, settings):
    first = maintenance.gc
    second = GcWorker(get_session_factory(), first.layout, first.storage_lock, settings)
    item = _item(client)
    _delete(client, item, _upload(client, item))
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(worker.run_due) for worker in (first, second)]
        for job in jobs:
            job.result(timeout=25)
    task = _tasks()[0]
    assert task.status == GcStatus.RUNNING
    assert task.attempts == task.lease_token == 1
    assert _slot(first.layout, task).read_bytes() == DATA


def test_wrong_task_token_cannot_mutate_formal_path(client, maintenance, monkeypatch):
    worker = maintenance.gc
    item = _item(client)
    _delete(client, item, _upload(client, item))
    process = worker._process

    def rotate_task_token(task, guard, referenced):
        with get_session_factory()() as session:
            session.get(GcTaskORM, str(task.id)).lease_token += 1
            session.commit()
        process(task, guard, referenced)

    monkeypatch.setattr(worker, "_process", rotate_task_token)
    worker.run_due()
    assert worker.layout.final_path(KEY).read_bytes() == DATA
    assert not _slot(worker.layout, _tasks()[0]).exists()
    assert _tasks()[0].lease_token == 2


def test_real_key_contention_retries_and_exhausts_budget(client, maintenance, monkeypatch):
    gc = maintenance.gc
    item = _item(client)
    _delete(client, item, _upload(client, item))
    guard = gc.storage_lock.acquire_many([KEY], new_owner())
    assert guard is not None
    try:
        monkeypatch.setattr(gc.storage_lock, "wait_seconds", 0.1)
        for claim_number in range(1, 9):
            gc.run_due()
            task = _tasks()[0]
            assert task.attempts == task.lease_token == claim_number
            assert gc.layout.final_path(KEY).read_bytes() == DATA
            if claim_number == 8:
                assert task.status == GcStatus.FAILED_PERMANENT
                assert task.next_retry_at is None
                break
            assert task.status == GcStatus.FAILED_RETRYABLE
            assert abs(
                (task.next_retry_at - task.updated_at).total_seconds() - 60 * 2 ** (claim_number - 1)
            ) < 1
            with get_session_factory()() as session:
                session.get(GcTaskORM, str(task.id)).next_retry_at = utcnow() - timedelta(seconds=1)
                session.commit()
    finally:
        guard.release()
    manual = gc.operate(task.id, target=GcStatus.NEEDS_MANUAL, actor="operator")
    assert manual.status == GcStatus.NEEDS_MANUAL
    pending = gc.operate(task.id, target=GcStatus.PENDING, actor="operator")
    assert pending.attempts == 0
    gc.run_due()
    assert _tasks()[0].status == GcStatus.RUNNING


@pytest.mark.skipif(os.name != "nt", reason="Windows sharing violation")
def test_open_windows_handle_defers_gc(client, maintenance):
    gc = maintenance.gc
    item = _item(client)
    _delete(client, item, _upload(client, item))
    formal = gc.layout.final_path(KEY)
    with formal.open("rb") as reader:
        started = time.monotonic()
        gc.run_due()
        assert time.monotonic() - started >= 4.9
        assert _tasks()[0].status == GcStatus.FAILED_RETRYABLE
        assert reader.read() == DATA
        assert formal.read_bytes() == DATA


def test_orphan_scan_enqueues_aged_formal_blob_and_preserves_temp(client, maintenance):
    gc = maintenance.gc
    item = _item(client)
    attachment = _upload(client, item)
    blob = gc.layout.final_path(KEY)
    with get_session_factory()() as session:
        session.execute(delete(AttachmentORM).where(AttachmentORM.id == attachment))
        session.commit()
    residual = gc.layout.temp_dir / "temporary"
    residual.write_bytes(b"temp")
    first = maintenance.recovery.scan_once()
    assert first["counts"]["orphan_blobs"] == 1
    assert first["temp_residual"]["count"] == 1
    assert _tasks() == []
    _mark_expired(blob)
    maintenance.recovery.scan_once()
    assert _tasks()[0].status == GcStatus.PENDING
    assert blob.is_file()
    gc.run_due()
    assert _slot(gc.layout, _tasks()[0]).read_bytes() == DATA
    assert residual.read_bytes() == b"temp"


def test_orp_restores_referenced_blob_from_unknown_quarantine_slot(client, maintenance):
    layout = maintenance.gc.layout
    _upload(client, _item(client))
    formal = layout.final_path(KEY)
    slot = layout.quarantine_dir / f"{KEY}.{uuid4()}"
    formal.rename(slot)
    report = maintenance.recovery.scan_once()
    assert formal.read_bytes() == DATA
    assert slot.read_bytes() == DATA
    assert any(
        result["event"] == "referenced_blob_restored" for result in report["quarantine_residual"]
    )
    maintenance.recovery.scan_once()
    requested = _tasks()[0]
    assert requested.status == GcStatus.PENDING
    assert not slot.exists()
    assert _slot(layout, requested).read_bytes() == DATA


def _zip(title="updated", content="new content"):
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("note.md", f"---\ntitle: {title}\n---\n{content}")
        archive.writestr("attachments/report.pdf", DATA)
    return stream.getvalue()


def test_zip_review_draft_and_last_reference_gc(client, maintenance):
    def import_zip(payload, **scope):
        return client.post("/api/knowledge/import", json={
            "archive_base64": base64.b64encode(payload).decode(), **scope,
        })

    def attachment_ids(item):
        response = client.get(f"/api/knowledge/{item}/attachments")
        assert response.status_code == 200, response.text
        return [row["id"] for row in response.json()]

    gc = maintenance.gc
    active = _item(client)
    rejected_item = _item(client)
    with get_session_factory()() as session:
        for item in (active, rejected_item):
            session.get(KnowledgeItemORM, item).status = "active"
        session.commit()
    rejected = import_zip(_zip("not accepted"), target_item_id=rejected_item)
    assert rejected.status_code == 202, rejected.text
    rejected_id = rejected.json()["items"][0]["review_id"]
    assert client.post(f"/api/reviews/{rejected_id}/reject", json={}).status_code == 200
    assert attachment_ids(rejected_item) == []
    assert list(gc.layout.staging_root.iterdir()) == []
    assert not gc.layout.final_path(KEY).exists()

    pending = import_zip(_zip(), target_item_id=active)
    assert pending.status_code == 202, pending.text
    assert attachment_ids(active) == []
    review = pending.json()["items"][0]["review_id"]
    approved = client.post(f"/api/reviews/{review}/approve", json={})
    assert approved.status_code == 200, approved.text
    exported = client.get(f"/api/knowledge/{active}/markdown")
    assert exported.status_code == 200 and "new content" in exported.text

    draft_zip = _zip("second document", "shared bytes")
    response = import_zip(draft_zip)
    assert response.status_code == 201, response.text
    draft = response.json()["items"][0]["item_id"]
    retried = import_zip(draft_zip, target_item_id=draft)
    assert retried.status_code == 200 and retried.json()["items"][0]["status"] == "skipped"
    active_ref, = attachment_ids(active)
    draft_ref, = attachment_ids(draft)
    for item, attachment in ((active, active_ref), (draft, draft_ref)):
        download = client.get(f"/api/knowledge/{item}/attachments/{attachment}")
        assert download.status_code == 200 and download.content == DATA
    _delete(client, active, active_ref)
    assert _tasks() == []
    assert gc.layout.final_path(KEY).read_bytes() == DATA
    _delete(client, draft, draft_ref)
    gc.run_due()
    task, = _tasks()
    slot = _slot(gc.layout, task)
    assert task.status == GcStatus.RUNNING
    assert slot.read_bytes() == DATA
    _advance_isolation(task, slot)
    gc.run_due()
    assert _tasks()[0].status == GcStatus.DONE
    assert not slot.exists() and not gc.layout.final_path(KEY).exists()
    assert list(gc.layout.staging_root.iterdir()) == []


def test_staging_sweep_leaves_pending_and_restores_isolated_pending(client, maintenance):
    layout = maintenance.gc.layout
    staging = maintenance.recovery.staging
    orphan = staging.create_from_zip(_zip())
    for path in orphan.directory.rglob("*"):
        if path.is_file():
            _mark_expired(path)
    item = _item(client)
    with get_session_factory()() as session:
        session.get(KnowledgeItemORM, item).status = "active"
        session.commit()
    result = client.post("/api/knowledge/import", json={
        "target_item_id": item, "archive_base64": base64.b64encode(_zip()).decode(),
    })
    assert result.status_code == 202, result.text
    pending_id, = staging.pending_staging_ids()
    pending = layout.staging_root / pending_id
    for path in pending.rglob("*"):
        if path.is_file():
            _mark_expired(path)
    maintenance.recovery.scan_once()
    isolated = layout.quarantine_dir / "staging"
    assert pending.is_dir()
    assert not orphan.directory.exists()
    orphan_slot, = isolated.glob(f"{orphan.staging_id}.*")
    assert (orphan_slot / ".complete").is_file()
    stamp = (utcnow() - timedelta(hours=25)).strftime("%Y%m%dT%H%M%S%fZ")
    old_slot = isolated / f"{orphan.staging_id}.{stamp}"
    orphan_slot.rename(old_slot)
    pending.rename(isolated / f"{pending_id}.{stamp}")
    maintenance.recovery.scan_once()
    assert (pending / ".complete").is_file()
    assert not old_slot.exists()
    assert not layout.final_path(KEY).exists()


def test_malformed_pending_manifest_stops_staging_sweep(client, maintenance):
    staging = maintenance.recovery.staging
    orphan = staging.create_from_zip(_zip())
    for path in orphan.directory.rglob("*"):
        if path.is_file():
            _mark_expired(path)
    item = _item(client)
    with get_session_factory()() as session:
        session.get(KnowledgeItemORM, item).status = "active"
        session.commit()
    response = client.post("/api/knowledge/import", json={
        "target_item_id": item, "archive_base64": base64.b64encode(_zip()).decode(),
    })
    assert response.status_code == 202
    review_id = response.json()["items"][0]["review_id"]
    with get_session_factory()() as session:
        row = session.get(ReviewRequestORM, review_id)
        row.payload = json.dumps({"__a1_import": None})
        session.commit()
    report = maintenance.recovery.scan_once()
    assert report["malformed_manifests"]
    assert orphan.directory.is_dir()


def test_corrupt_quarantine_is_preserved_for_manual_action(maintenance):
    gc = maintenance.gc
    task = GcTask(storage_key=KEY, status=GcStatus.PENDING)
    with get_session_factory()() as session:
        SQLAlchemyGcTaskRepository(session).save_task(task)
        session.commit()
    slot = _slot(gc.layout, task)
    slot.write_bytes(b"wrong content")
    gc.run_due()
    assert _tasks()[0].status == GcStatus.NEEDS_MANUAL
    assert slot.read_bytes() == b"wrong content"


def _run_program(program, settings, *extra):
    root = Path(__file__).resolve().parents[2]
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(map(str, (root / "backend", root / "knowledge-core/src"))),
    }
    return subprocess.run(
        [sys.executable, "-B", "-c", program, settings.database_url,
         str(settings.data_dir), *extra],
        cwd=root, env=env, capture_output=True, timeout=30, check=False,
    )


def test_worker_process_death_after_move_is_reclaimed(client, maintenance, settings):
    gc = maintenance.gc
    item = _item(client)
    _delete(client, item, _upload(client, item))
    task = _tasks()[0]
    program = """
import os
import sys
from pathlib import Path
from app.core.config import Settings
from app.db.session import get_session_factory, init_db
from app.db.storage_lock import build_storage_lock
from app.services.attachment_maintenance import GcWorker
from app.services.attachment_storage import validate_storage_roots

class ExitingWorker(GcWorker):
    def _wait_quarantine(self, *args):
        os._exit(23)

settings = Settings(database_url=sys.argv[1], data_dir=Path(sys.argv[2]), _env_file=None)
init_db(settings)
worker = ExitingWorker(get_session_factory(), validate_storage_roots(settings),
                       build_storage_lock(settings), settings)
worker.run_due()
"""
    process = _run_program(program, settings)
    assert process.returncode == 23, process.stderr.decode(errors="replace")
    slot = _slot(gc.layout, task)
    assert slot.read_bytes() == DATA
    assert not gc.layout.final_path(KEY).exists()
    with get_session_factory()() as session:
        row = session.get(GcTaskORM, str(task.id))
        assert row.status == "running"
        assert row.quarantined_at is None
        row.lease_expires_at = utcnow() - timedelta(seconds=1)
        session.commit()
    # The dead process also held the SQLite storage lease. Use its real DB row
    # to make the lease eligible for takeover without waiting sixty seconds.
    with get_session_factory()() as session:
        session.scalar(select(StorageLockORM).where(
            StorageLockORM.storage_key == KEY,
        )).lease_expires_at = utcnow() - timedelta(seconds=1)
        session.commit()
    gc.run_due()
    assert _tasks()[0].attempts == 2
    assert _tasks()[0].quarantined_at is not None
    assert slot.read_bytes() == DATA


def test_worker_process_death_after_purge_keeps_new_formal_generation(
    client, maintenance, settings,
):
    gc = maintenance.gc
    item = _item(client)
    _delete(client, item, _upload(client, item))
    gc.run_due()
    task, = _tasks()
    old_slot = _slot(gc.layout, task)
    _delete(client, item, _upload(client, item))
    _advance_isolation(task, old_slot)
    program = """
import os
import sys
from pathlib import Path
from app.core.config import Settings
from app.db.session import get_session_factory, init_db
from app.db.storage_lock import build_storage_lock
from app.services.attachment_maintenance import GcWorker
from app.services.attachment_storage import validate_storage_roots
from knowledge_core.domain.entities import GcStatus

class ExitingWorker(GcWorker):
    def _finish(self, task, status, reason, **kwargs):
        if status == GcStatus.DONE and reason == 'slot_purged':
            os._exit(25)
        super()._finish(task, status, reason, **kwargs)

settings = Settings(database_url=sys.argv[1], data_dir=Path(sys.argv[2]), _env_file=None)
init_db(settings)
ExitingWorker(get_session_factory(), validate_storage_roots(settings),
              build_storage_lock(settings), settings).run_due()
"""
    child = _run_program(program, settings)
    assert child.returncode == 25, child.stderr.decode(errors="replace")
    assert not old_slot.exists()
    formal = gc.layout.final_path(KEY)
    assert formal.read_bytes() == DATA
    with get_session_factory()() as session:
        expired = utcnow() - timedelta(seconds=1)
        row = session.get(GcTaskORM, str(task.id))
        assert row.status == "running" and row.quarantine_path == old_slot.name
        row.lease_expires_at = expired
        session.get(StorageLockORM, KEY).lease_expires_at = expired
        session.commit()
    gc.run_due()
    done, successor = _tasks()
    assert done.status == GcStatus.DONE
    assert successor.status == GcStatus.PENDING
    assert formal.read_bytes() == DATA


def test_orp_and_gc_serialize_same_slot(client, maintenance, monkeypatch):
    gc = maintenance.gc
    item = _item(client)
    _delete(client, item, _upload(client, item))
    isolated, attempting = Event(), Event()
    wait = gc._wait_quarantine
    recover = maintenance.recovery._recover_slot

    def pause_after_move(*args):
        isolated.set()
        assert attempting.wait(10)
        return wait(*args)

    def observe_orp(*args):
        attempting.set()
        return recover(*args)

    monkeypatch.setattr(gc, "_wait_quarantine", pause_after_move)
    monkeypatch.setattr(maintenance.recovery, "_recover_slot", observe_orp)
    with ThreadPoolExecutor(max_workers=2) as pool:
        worker = pool.submit(gc.run_due)
        assert isolated.wait(10)
        scanner = pool.submit(maintenance.recovery.scan_once)
        worker.result(timeout=15)
        report = scanner.result(timeout=15)
    task, = _tasks()
    assert task.status == GcStatus.RUNNING and task.attempts == 1
    assert _slot(gc.layout, task).read_bytes() == DATA
    assert report["quarantine_residual"] == [
        {"storage_key": KEY, "event": "owned_slot_preserved"},
    ]


def test_staging_process_death_never_creates_pending_and_orp_isolates(
    maintenance, settings,
):
    program = """
import base64
import os
import sys
from pathlib import Path
from app.core.config import Settings
from app.services.attachment_staging import AttachmentStagingService
from app.services.attachment_storage import validate_storage_roots

class ExitingStaging(AttachmentStagingService):
    def _write_blob(self, *args, **kwargs):
        super()._write_blob(*args, **kwargs)
        os._exit(24)

settings = Settings(database_url=sys.argv[1], data_dir=Path(sys.argv[2]), _env_file=None)
ExitingStaging(validate_storage_roots(settings)).create_from_zip(base64.b64decode(sys.argv[3]))
"""
    child = _run_program(program, settings, base64.b64encode(_zip()).decode())
    assert child.returncode == 24, child.stderr.decode(errors="replace")
    staging = maintenance.recovery.staging
    partial, = staging.staging_root.iterdir()
    assert (partial / ".creating").is_file()
    assert not (partial / ".complete").exists()
    assert staging.pending_staging_ids() == set()
    for path in partial.rglob("*"):
        if path.is_file():
            _mark_expired(path)
    report = maintenance.recovery.scan_once()
    assert report["counts"]["staging_incomplete"] == 1
    assert not partial.exists()
    isolated, = (maintenance.gc.layout.quarantine_dir / "staging").iterdir()
    staged_file, = (isolated / "blobs").iterdir()
    assert staged_file.read_bytes() == DATA


def test_consistency_reports_are_redacted_and_retained(maintenance):
    recovery = maintenance.recovery
    for _ in range(35):
        report = recovery.scan_once()
    paths = list((recovery.layout.data_dir / "ops").glob("attachment-consistency-*.json"))
    assert len(paths) == 30
    assert report["storage_root"] == "<data_dir>/attachments"
    assert json.loads(max(paths).read_text(encoding="utf-8"))["storage_root"] == report["storage_root"]
    assert str(recovery.layout.data_dir) not in json.dumps(report)


def _publish_without_commit(client, item, layout, data):
    blob = layout.final_path(sha256(data).hexdigest())

    def mark_attachment_write(session, *_args):
        if any(isinstance(obj, AttachmentORM) for obj in session.new):
            session.info["test_attachment_write"] = True

    def fail_commit(session):
        if session.in_nested_transaction():
            return
        if session.info.get("test_attachment_write"):
            assert blob.read_bytes() == data
            raise RuntimeError("injected attachment commit failure")

    event.listen(Session, "after_flush", mark_attachment_write)
    event.listen(Session, "before_commit", fail_commit)
    try:
        response = _post_attachment(client, item, data)
    finally:
        event.remove(Session, "before_commit", fail_commit)
        event.remove(Session, "after_flush", mark_attachment_write)
    assert response.status_code == 500, response.text
    assert blob.read_bytes() == data
    return blob


def test_orp01_publish_commit_failure_recovers_through_purge(client, maintenance):
    gc = maintenance.gc
    item = _item(client)
    protected = DATA + b" retained reference"
    protected_key = sha256(protected).hexdigest()
    attachment = _upload(client, item, protected)
    orphan = _publish_without_commit(client, item, gc.layout, DATA)
    assert _tasks() == []
    _mark_expired(orphan)
    _mark_expired(gc.layout.final_path(protected_key))
    report = maintenance.recovery.scan_once()
    assert {entry["storage_key"] for entry in report["orphan_blobs"]} == {KEY}
    pending, = _tasks()
    assert pending.status == GcStatus.PENDING
    gc.run_due()
    task, = _tasks()
    slot = _slot(gc.layout, task)
    assert task.status == GcStatus.RUNNING and task.attempts == 1
    assert not orphan.exists() and slot.read_bytes() == DATA
    gc.run_due()
    assert slot.is_file()
    _advance_isolation(task, slot)
    gc.run_due()
    assert _tasks()[0].status == GcStatus.DONE and not slot.exists()
    assert gc.layout.final_path(protected_key).read_bytes() == protected
    with get_session_factory()() as session:
        assert list(session.scalars(select(AttachmentORM.id))) == [attachment]


def test_orp07_one_report_preserves_missing_orphan_and_corrupt(client, maintenance):
    recovery = maintenance.recovery
    item = _item(client)
    missing = _upload(client, item)
    recovery.layout.final_path(KEY).unlink()
    corrupt_data = DATA + b" second file"
    corrupt_key = sha256(corrupt_data).hexdigest()
    corrupt_id = _upload(client, item, corrupt_data)
    corrupt = recovery.layout.final_path(corrupt_key)
    corrupted_contents = b"private sentinel payload"
    corrupt.write_bytes(corrupted_contents)
    orphan_data = DATA + b" orphan"
    orphan = _publish_without_commit(client, item, recovery.layout, orphan_data)
    report = recovery.scan_once()
    paths = (recovery.layout.data_dir / "ops").glob("attachment-consistency-*.json")
    raw = max(paths).read_text(encoding="utf-8")
    assert json.loads(raw) == report
    assert report["missing_blobs"] == [{"storage_key": KEY, "attachment_id": missing}]
    assert [entry["storage_key"] for entry in report["orphan_blobs"]] == [orphan.name]
    assert report["hash_mismatched"] == [{
        "storage_key": corrupt_key, "actual_hash": sha256(corrupted_contents).hexdigest(),
    }]
    assert "private sentinel payload" not in raw and "review.pdf" not in raw
    assert str(recovery.layout.data_dir) not in raw
    assert corrupt.read_bytes() == corrupted_contents and orphan.read_bytes() == orphan_data
    with get_session_factory()() as session:
        assert set(session.scalars(select(AttachmentORM.id))) == {missing, corrupt_id}


def test_gc02_different_tasks_serialize_physical_generations(
    client, maintenance, settings, monkeypatch,
):
    first = maintenance.gc
    second = GcWorker(get_session_factory(), first.layout, first.storage_lock, settings)
    item = _item(client)
    _delete(client, item, _upload(client, item))
    first.run_due()
    older, = _tasks()
    old_slot = _slot(first.layout, older)
    _delete(client, item, _upload(client, item))
    _advance_isolation(older, old_slot)
    newer = GcTask(storage_key=KEY, status=GcStatus.PENDING)
    with get_session_factory()() as session:
        SQLAlchemyGcTaskRepository(session).save_task(newer)
        session.commit()
    new_slot = _slot(first.layout, newer)
    first_inside, second_waiting, second_inside, release_first = (Event() for _ in range(4))
    process_first, process_second = first._process, second._process
    acquire = first.storage_lock.acquire_many

    def observe_acquire(*args, **kwargs):
        if first_inside.is_set():
            second_waiting.set()
        return acquire(*args, **kwargs)

    def hold_first(*args):
        first_inside.set()
        assert release_first.wait(10)
        return process_first(*args)

    def observe_second(*args):
        second_inside.set()
        assert not old_slot.exists()
        assert first.layout.final_path(KEY).read_bytes() == DATA
        return process_second(*args)

    monkeypatch.setattr(first.storage_lock, "acquire_many", observe_acquire)
    monkeypatch.setattr(first, "_process", hold_first)
    monkeypatch.setattr(second, "_process", observe_second)
    older, newer = _tasks()
    with ThreadPoolExecutor(max_workers=2) as pool:
        old_job = pool.submit(first._run_task, older)
        try:
            assert first_inside.wait(10)
            new_job = pool.submit(second._run_task, newer)
            assert second_waiting.wait(10)
            assert not second_inside.is_set()
            assert old_slot.read_bytes() == DATA and not new_slot.exists()
        finally:
            release_first.set()
        old_job.result(timeout=15)
        new_job.result(timeout=15)
    done, waiting = _tasks()
    assert done.status == GcStatus.DONE and waiting.status == GcStatus.RUNNING
    assert done.id != waiting.id and not old_slot.exists() and new_slot.read_bytes() == DATA
    assert waiting.next_retry_at - waiting.quarantined_at == timedelta(hours=24)
    monkeypatch.undo()
    first.run_due()
    assert new_slot.is_file() and _tasks()[-1].attempts == 1
    _advance_isolation(waiting, new_slot)
    first.run_due()
    assert [task.status for task in _tasks()] == [GcStatus.DONE, GcStatus.DONE]
    assert not new_slot.exists() and not first.layout.final_path(KEY).exists()


@pytest.mark.parametrize("point", [
    "before_receiver", "after_receiver", "before_transfer", "after_transfer", "during_restore",
])
def test_orp05_handoff_process_death(client, maintenance, settings, point):
    gc = maintenance.gc
    layout = gc.layout
    item = _item(client)
    if point == "during_restore":
        attachment = _upload(client, item)
        formal = layout.final_path(KEY)
    else:
        attachment = None
        formal = _publish_without_commit(client, item, layout, DATA)
    source = layout.quarantine_dir / f"{KEY}.{uuid4()}"
    formal.rename(source)
    untrusted = layout.quarantine_dir / f"{KEY}.{uuid4()}"
    untrusted.write_bytes(b"untrusted")
    program = """
import os
import sys
from pathlib import Path
from app.core.config import Settings
from app.db.session import get_engine, get_session_factory, init_db
from app.db.storage_lock import build_storage_lock
from app.services import attachment_maintenance as module
from app.services.attachment_staging import AttachmentStagingService
from app.services.attachment_storage import validate_storage_roots

settings = Settings(database_url=sys.argv[1], data_dir=Path(sys.argv[2]), _env_file=None)
point = sys.argv[3]
init_db(settings)
layout = validate_storage_roots(settings)
gc = module.GcWorker(get_session_factory(), layout, build_storage_lock(settings), settings)
staging = AttachmentStagingService(layout, session_factory=get_session_factory())
scanner = module.OrphanRecovery(gc, staging, get_engine())
transfer = scanner._transfer_slot
write = scanner.database.write
restore = module.restore_from_quarantine

def exit_before_receiver(*args):
    os._exit(26)

def exit_after_receiver(*args):
    assert write(*args) is not None
    os._exit(26)

def transfer_then_exit(*args):
    if point == 'after_transfer':
        transfer(*args)
    os._exit(26)

def restore_then_exit(*args, **kwargs):
    restore(*args, **kwargs)
    os._exit(26)

if point == 'before_receiver':
    scanner.database.enqueue = exit_before_receiver
elif point == 'after_receiver':
    scanner.database.write = exit_after_receiver
elif point == 'during_restore':
    module.restore_from_quarantine = restore_then_exit
else:
    scanner._transfer_slot = transfer_then_exit
scanner.scan_once()
"""
    child = _run_program(program, settings, point)
    assert child.returncode == 26, child.stderr.decode(errors="replace")
    with get_session_factory()() as session:
        session.get(StorageLockORM, KEY).lease_expires_at = utcnow() - timedelta(seconds=1)
        session.commit()
    assert untrusted.read_bytes() == b"untrusted"


    if point == "during_restore":
        assert formal.read_bytes() == DATA and source.read_bytes() == DATA
        assert client.get(f"/api/knowledge/{item}/attachments/{attachment}").content == DATA
        maintenance.recovery.scan_once()
        assert formal.read_bytes() == DATA and untrusted.read_bytes() == b"untrusted"
        return

    if point in {"after_receiver", "before_transfer"}:
        assert source.read_bytes() == DATA and _tasks()[0].status == GcStatus.PENDING
        gc.run_due()
        assert _tasks()[0].status == GcStatus.DONE
    elif point == "before_receiver":
        assert not _tasks() and source.read_bytes() == DATA
    else:
        assert not source.exists() and _slot(layout, _tasks()[0]).read_bytes() == DATA
    maintenance.recovery.scan_once()
    gc.run_due()
    task, = [task for task in _tasks() if task.status == GcStatus.RUNNING]
    slot = _slot(layout, task)
    assert slot.read_bytes() == DATA and not source.exists()
    _delete(client, item, _upload(client, item))
    _advance_isolation(task, slot)
    gc.run_due()
    assert not slot.exists() and formal.read_bytes() == DATA
    assert untrusted.read_bytes() == b"untrusted"


@pytest.mark.parametrize("fresh_entry", [".creating", ".activity", ".complete", "blob"])
def test_sweep42_activity_uses_maximum_entry_mtime(maintenance, fresh_entry):
    recovery = maintenance.recovery
    staged = recovery.staging.create_from_zip(_zip())
    directory = staged.directory
    marker = directory / ".creating"
    marker.touch()
    for path in directory.rglob("*"):
        if path.is_file():
            _mark_expired(path)
    _mark_expired(directory)
    fresh = next((directory / "blobs").iterdir()) if fresh_entry == "blob" else directory / fresh_entry
    os.utime(fresh)
    recovery.scan_once()
    assert directory.is_dir()
    _mark_expired(fresh)
    os.utime(directory)
    recovery.scan_once()
    assert not directory.exists()
    isolated, = (recovery.layout.quarantine_dir / "staging").glob(f"{staged.staging_id}.*")
    assert next((isolated / "blobs").iterdir()).read_bytes() == DATA


def test_sweep42_empty_and_unsafe_paths_preserve_formal(client, maintenance, tmp_path):
    recovery = maintenance.recovery
    _upload(client, _item(client))
    root = recovery.layout.staging_root
    empty = root / str(uuid4())
    empty.mkdir()
    _mark_expired(empty)
    outside = tmp_path / "outside-test-staging"
    outside.mkdir()
    (outside / "sentinel").write_bytes(b"outside")
    link = root / str(uuid4())
    if os.name == "nt":
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(outside)],
            capture_output=True, check=False,
        )
        if result.returncode:
            pytest.skip("normal Windows token could not create a junction")
        assert link.lstat().st_file_attributes & 0x400
    else:
        link.symlink_to(outside, target_is_directory=True)
        assert link.is_symlink()
    try:
        report = recovery.scan_once()
        assert not empty.exists()
        assert list((recovery.layout.quarantine_dir / "staging").glob(f"{empty.name}.*"))
        assert link.lstat() and (outside / "sentinel").read_bytes() == b"outside"
        assert recovery.layout.final_path(KEY).read_bytes() == DATA
        assert any(entry["staging_id"] == link.name for entry in report["staging_orphans"])
    finally:
        if os.name == "nt":
            link.rmdir()
        else:
            link.unlink()


def _sweep_pending(client, maintenance):
    item = _item(client)
    with get_session_factory()() as session:
        session.get(KnowledgeItemORM, item).status = "active"
        session.commit()
    response = client.post("/api/knowledge/import", json={
        "target_item_id": item, "archive_base64": base64.b64encode(_zip()).decode(),
    })
    assert response.status_code == 202, response.text
    review = response.json()["items"][0]["review_id"]
    staging_id, = maintenance.recovery.staging.pending_staging_ids()
    return review, maintenance.gc.layout.staging_root / staging_id


@pytest.mark.parametrize("phase", ["move", "purge"])
def test_sweep42_pending_rises_during_physical_boundary(
    client, maintenance, monkeypatch, phase,
):
    recovery = maintenance.recovery
    review, staging = _sweep_pending(client, maintenance)

    def set_status(status):
        with get_session_factory()() as session:
            session.get(ReviewRequestORM, review).status = status
            session.commit()

    set_status("rejected")
    for path in staging.rglob("*"):
        if path.is_file():
            _mark_expired(path)
    tracked = staging
    if phase == "purge":
        isolated = recovery.layout.quarantine_dir / "staging"
        stamp = (utcnow() - timedelta(hours=25)).strftime("%Y%m%dT%H%M%S%fZ")
        tracked = staging.rename(isolated / f"{staging.name}.{stamp}")
    evidence = {p.relative_to(tracked): p.read_bytes() for p in tracked.rglob("*") if p.is_file()}
    crossed = Event()

    def concurrent_pending(*args):
        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(set_status, "pending").result(timeout=10)
        crossed.set()
        return operation(*args)

    with monkeypatch.context() as patch:
        if phase == "move":
            operation = attachment_maintenance._rename_directory_no_clobber
            patch.setattr(attachment_maintenance, "_rename_directory_no_clobber", concurrent_pending)
        else:
            operation = recovery._purge_stage
            patch.setattr(recovery, "_purge_stage", concurrent_pending)
        recovery.scan_once()
    assert crossed.is_set()
    assert evidence == {p.relative_to(tracked): p.read_bytes() for p in tracked.rglob("*") if p.is_file()}
    assert recovery.staging.pending_staging_ids() == {staging.name}
    recovery.scan_once()
    assert staging.is_dir()
    assert not recovery.layout.final_path(KEY).exists()


def test_sweep42_producer_and_waiter_share_one_staging_guard(maintenance, monkeypatch):
    recovery = maintenance.recovery
    service = recovery.staging
    sid = str(uuid4())
    producer_entered, release_producer = Event(), Event()
    waiter_entered, release_waiter = Event(), Event()
    write_complete = service._write_complete

    def pause_before_completion(path, marker):
        for member in path.parent.rglob("*"):
            if member.is_file():
                _mark_expired(member)
        producer_entered.set()
        assert release_producer.wait(10)
        write_complete(path, marker)

    monkeypatch.setattr(service, "_write_complete", pause_before_completion)

    def wait_on_producer():
        with service.staging_guard(sid):
            waiter_entered.set()
            assert release_waiter.wait(10)

    with ThreadPoolExecutor(max_workers=2) as executor:
        producing = executor.submit(service.create_from_zip, _zip(), staging_id=sid)
        try:
            assert producer_entered.wait(10)
            lock = service._guards[sid]
            future = executor.submit(wait_on_producer)
            deadline = time.monotonic() + 5
            while service._guard_users.get(sid) != 2:
                assert time.monotonic() < deadline
                time.sleep(0.01)
            recovery.scan_once()
            directory = service.staging_root / sid
            assert directory.is_dir() and not (directory / ".complete").exists()
            assert service._guards[sid] is lock
            release_producer.set()
            assert producing.result(timeout=10).directory == directory
            assert waiter_entered.wait(10)
            assert service._guards[sid] is lock
            with (
                pytest.raises(AttachmentStagingError, match="staging guard timeout"),
                service.staging_guard(sid, wait_seconds=0),
            ):
                pytest.fail("a second lock was issued for a live waiter")
        finally:
            release_producer.set()
            release_waiter.set()
        future.result(timeout=10)
    assert sid not in service._guards and sid not in service._guard_users
def test_pg_gc_and_orphan_scan_leadership(tmp_path, monkeypatch):
    url = os.environ.get("EXPLAINLAB_PG_TEST_URL")
    if not url:
        pytest.skip("real PostgreSQL GC database unavailable")
    parsed = make_url(url)
    if not (parsed.database or "").startswith("explainlab_b5_http_"):
        pytest.skip("dedicated explainlab_b5_http_ database required")
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
            maint = client.app.state.attachment_maintenance
            engine = get_engine()
            # The worker's startup scan can lead first; wait until it finishes.
            deadline = time.monotonic() + 10
            ops = settings.data_dir / "ops"
            while not list(ops.glob("attachment-consistency-*.json")):
                assert time.monotonic() < deadline
                time.sleep(0.02)
            with orphan_scan_leadership(engine) as leading:
                assert leading
                with orphan_scan_leadership(engine) as competing:
                    assert not competing
                assert maint.recovery.scan_once() is None
            with orphan_scan_leadership(engine) as again:
                assert again
            test_zip_review_draft_and_last_reference_gc(client, maint)
            first, second = _item(client), _item(client)
            ids = (_upload(client, first), _upload(client, second))
            with ThreadPoolExecutor(max_workers=2) as pool:
                deletes = [
                    pool.submit(_delete, client, item, attachment)
                    for item, attachment in zip((first, second), ids, strict=True)
                ]
                for deletion in deletes:
                    deletion.result(timeout=20)
            _mark_expired(maint.gc.layout.final_path(KEY))
            maint.recovery.scan_once()
            assert _tasks()[-1].status == GcStatus.PENDING
            maint.gc.run_due()
            assert _slot(maint.gc.layout, _tasks()[-1]).read_bytes() == DATA
            with engine.connect() as connection:
                assert connection.scalar(text(
                    "select count(*) from pg_locks where locktype = 'advisory' "
                    "and database = (select oid from pg_database where datname=current_database())"
                )) == 0
    finally:
        dispose_db()
