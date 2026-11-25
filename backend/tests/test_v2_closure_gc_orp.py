"""ExplainLab V2 Backend Final Closure tests for GC-02, ORP-01, and ORP-05.

Covers both SQLite (Windows/POSIX) and real PostgreSQL 18.6 (gated by EXPLAINLAB_PG_TEST_URL)
with real filesystems, real concurrent GcWorker instances, and real subprocess crash injection.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from hashlib import sha256
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
from app.core.config import Settings, get_settings
from app.db.session import dispose_db, get_engine, get_session_factory
from app.main import create_app
from app.models import AttachmentORM, GcTaskORM, StorageLockORM
from app.services.attachment_maintenance import GcWorker
from app.services.repositories_v2 import SQLAlchemyGcTaskRepository
from knowledge_core.domain.entities import GcStatus, GcTask, utcnow

DATA = b"%PDF-1.7\nv2-closure-gc-orp-payload"
KEY = sha256(DATA).hexdigest()


def _wait_startup_scan(worker) -> None:
    ops = worker.gc.layout.data_dir / "ops"
    deadline = time.monotonic() + 10
    while not list(ops.glob("attachment-consistency-*.json")):
        assert time.monotonic() < deadline, "startup orphan report did not appear"
        time.sleep(0.02)


@pytest.fixture
def maintenance(client):
    worker = client.app.state.attachment_maintenance
    _wait_startup_scan(worker)
    return worker


@pytest.fixture
def pg_closure_client(tmp_path, monkeypatch):
    url = os.environ.get("EXPLAINLAB_PG_TEST_URL")
    if not url:
        pytest.skip("EXPLAINLAB_PG_TEST_URL is required for PostgreSQL closure tests")
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
    settings = Settings(database_url=url, data_dir=tmp_path / "data", _env_file=None)
    try:
        with TestClient(create_app(settings)) as client:
            with get_engine().begin() as conn:
                conn.execute(text("DELETE FROM gc_task"))
                conn.execute(text("DELETE FROM attachment"))
                conn.execute(text("DELETE FROM storage_lock"))
                conn.execute(text("DELETE FROM review_request"))
                conn.execute(text("DELETE FROM knowledge_item"))
                ver = conn.scalar(text("SHOW server_version_num"))
                print(f"[PG_ENV] server_version_num={ver} db={parsed.database}")
            _wait_startup_scan(client.app.state.attachment_maintenance)
            yield client, settings
    finally:
        dispose_db()


def _item(client) -> str:
    resp = client.post("/api/knowledge", json={"title": "closure-note", "content": "body"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _post_attachment(client, item: str, data: bytes):
    return client.post(
        f"/api/knowledge/{item}/attachments",
        json={
            "filename": "closure.pdf",
            "mime": "application/pdf",
            "content_base64": base64.b64encode(data).decode(),
        },
    )


def _upload(client, item: str, data: bytes = DATA) -> str:
    resp = _post_attachment(client, item, data)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _delete(client, item: str, attachment_id: str) -> None:
    resp = client.delete(f"/api/knowledge/{item}/attachments/{attachment_id}")
    assert resp.status_code == 204, resp.text


def _tasks(key: str = KEY) -> list[GcTask]:
    with get_session_factory()() as session:
        return SQLAlchemyGcTaskRepository(session).list_tasks(storage_key=key)


def _slot(layout, task: GcTask, key: str = KEY) -> Path:
    return layout.quarantine_dir / f"{key}.{task.id}"


def _advance_isolation(task: GcTask, slot: Path) -> None:
    previous = utcnow() - timedelta(hours=25)
    with get_session_factory()() as session:
        row = session.get(GcTaskORM, str(task.id))
        assert row is not None
        row.quarantined_at = previous
        row.next_retry_at = previous + timedelta(hours=24)
        row.lease_expires_at = previous
        session.commit()
    os.utime(slot, (previous.timestamp(), previous.timestamp()))


def _mark_expired(path: Path) -> None:
    past = (utcnow() - timedelta(hours=25)).timestamp()
    os.utime(path, (past, past))


def _pg_advisory_locks() -> list[tuple[int, int, int, bool]]:
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT pid, classid, objid, granted FROM pg_locks "
                "WHERE locktype = 'advisory' "
                "AND database = (SELECT oid FROM pg_database WHERE datname = current_database()) "
                "ORDER BY pid, classid, objid"
            )
        ).all()
    return [(int(r[0]), int(r[1]), int(r[2]), bool(r[3])) for r in rows]


def _dump_db_state(label: str, key: str = KEY) -> dict:
    with get_session_factory()() as session:
        attachments = list(session.scalars(select(AttachmentORM).where(AttachmentORM.storage_key == key)))
        tasks = [
            {
                "id": str(t.id),
                "status": t.status.value,
                "attempts": t.attempts,
                "lease_token": t.lease_token,
                "lease_owner": t.lease_owner,
                "quarantine_path": t.quarantine_path,
                "quarantined_at": t.quarantined_at.isoformat() if t.quarantined_at else None,
            }
            for t in SQLAlchemyGcTaskRepository(session).list_tasks(storage_key=key)
        ]
    snapshot = {"label": label, "attachment_refs": len(attachments), "tasks": tasks}
    print(f"[DB_STATE] {json.dumps(snapshot, sort_keys=True)}")
    return snapshot


def _publish_without_commit(client, item: str, layout, data: bytes) -> Path:
    blob = layout.final_path(sha256(data).hexdigest())

    def mark_write(session, *_args):
        if any(isinstance(obj, AttachmentORM) for obj in session.new):
            session.info["closure_fail_attachment_commit"] = True

    def fail_commit(session):
        if session.in_nested_transaction():
            return
        if session.info.get("closure_fail_attachment_commit"):
            assert blob.read_bytes() == data
            raise RuntimeError("injected closure DB commit failure")

    event.listen(Session, "after_flush", mark_write)
    event.listen(Session, "before_commit", fail_commit)
    try:
        resp = _post_attachment(client, item, data)
    finally:
        event.remove(Session, "before_commit", fail_commit)
        event.remove(Session, "after_flush", mark_write)
    assert resp.status_code == 500, resp.text
    assert blob.read_bytes() == data
    return blob


def _run_subprocess(program: str, settings: Settings, *extra: str) -> subprocess.CompletedProcess:
    root = Path(__file__).resolve().parents[2]
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(map(str, (root / "backend", root / "knowledge-core/src"))),
    }
    return subprocess.run(
        [sys.executable, "-B", "-c", program, settings.database_url, str(settings.data_dir), *extra],
        cwd=root,
        env=env,
        capture_output=True,
        timeout=30,
        check=False,
    )


# ---------------------------------------------------------------------------
# GC-02: Real PostgreSQL concurrency — two real GcWorkers competing on same storage_key
# ---------------------------------------------------------------------------


def test_pg_gc02_two_workers_compete_same_storage_key_different_tasks(
    pg_closure_client, monkeypatch,
):
    """GC-02 PostgreSQL: two real GcWorkers, two distinct GC tasks, same storage_key."""
    client, settings = pg_closure_client
    maint = client.app.state.attachment_maintenance
    worker_1 = maint.gc
    worker_2 = GcWorker(get_session_factory(), worker_1.layout, worker_1.storage_lock, settings)
    assert worker_1.owner != worker_2.owner

    item = _item(client)
    # Generation 1: upload -> delete -> quarantine -> age 24h
    _delete(client, item, _upload(client, item))
    worker_1.run_due()
    task_1, = _tasks()
    slot_1 = _slot(worker_1.layout, task_1)
    assert task_1.status == GcStatus.RUNNING
    assert slot_1.read_bytes() == DATA

    # Generation 2: re-upload same key -> delete -> enqueue second distinct GC task
    _delete(client, item, _upload(client, item))
    _advance_isolation(task_1, slot_1)
    task_2 = GcTask(storage_key=KEY, status=GcStatus.PENDING)
    with get_session_factory()() as session:
        SQLAlchemyGcTaskRepository(session).save_task(task_2)
        session.commit()
    slot_2 = _slot(worker_1.layout, task_2)
    assert task_1.id != task_2.id
    _dump_db_state("pg_gc02_before_contention")

    w1_inside, w2_acquiring, w2_inside, release_w1 = (Event() for _ in range(4))
    orig_p1, orig_p2 = worker_1._process, worker_2._process
    orig_acquire = worker_1.storage_lock.acquire_many
    observed: dict[str, object] = {}

    def observe_acquire(keys, owner, *args, **kwargs):
        if w1_inside.is_set():
            w2_acquiring.set()
        return orig_acquire(keys, owner, *args, **kwargs)

    def hold_worker_1(task, guard, referenced):
        locks = _pg_advisory_locks()
        observed["w1_locks"] = locks
        observed["w1_pids"] = sorted({row[0] for row in locks if row[3]})
        print(f"[PG_GC02] worker_1 entered _process task={task.id} locks={locks}")
        w1_inside.set()
        assert release_w1.wait(15), "worker_1 release timed out"
        return orig_p1(task, guard, referenced)

    def observe_worker_2(task, guard, referenced):
        locks = _pg_advisory_locks()
        observed["w2_locks"] = locks
        observed["w2_pids"] = sorted({row[0] for row in locks if row[3]})
        print(f"[PG_GC02] worker_2 entered _process task={task.id} locks={locks}")
        w2_inside.set()
        assert not slot_1.exists(), "slot_1 must be purged before worker_2 enters"
        assert worker_1.layout.final_path(KEY).read_bytes() == DATA
        return orig_p2(task, guard, referenced)

    monkeypatch.setattr(worker_1.storage_lock, "acquire_many", observe_acquire)
    monkeypatch.setattr(worker_1, "_process", hold_worker_1)
    monkeypatch.setattr(worker_2, "_process", observe_worker_2)

    t1, t2 = _tasks()
    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(worker_1._run_task, t1)
        try:
            assert w1_inside.wait(15)
            f2 = pool.submit(worker_2._run_task, t2)
            assert w2_acquiring.wait(15)
            time.sleep(0.25)
            assert not w2_inside.is_set(), "StorageKeyLock failed to serialize worker_2"
            assert slot_1.read_bytes() == DATA and not slot_2.exists()
            locks_during_wait = _pg_advisory_locks()
            print(f"[PG_GC02] locks_during_contention={locks_during_wait}")
            assert any(row[3] for row in locks_during_wait)
        finally:
            release_w1.set()
        f1.result(timeout=20)
        f2.result(timeout=20)

    monkeypatch.undo()
    _dump_db_state("pg_gc02_after_contention")

    # Verify serialization, distinct slots, and generation isolation
    assert observed["w1_pids"], "worker_1 must hold a real PostgreSQL advisory lock"
    assert observed["w2_pids"], "worker_2 must hold a real PostgreSQL advisory lock"
    assert _pg_advisory_locks() == []

    tasks_mid = {t.id: t for t in _tasks()}
    done_1, waiting_2 = tasks_mid[task_1.id], tasks_mid[task_2.id]
    assert done_1.status == GcStatus.DONE and done_1.attempts == 2 and done_1.lease_token == 2
    assert waiting_2.status == GcStatus.RUNNING and waiting_2.attempts == 1 and waiting_2.lease_token == 1
    assert not slot_1.exists()
    assert slot_2.read_bytes() == DATA
    assert not worker_1.layout.final_path(KEY).exists()
    assert waiting_2.next_retry_at - waiting_2.quarantined_at == timedelta(hours=24)

    # Fencing verification: stale token / old worker cannot overwrite task_2
    with get_session_factory()() as session:
        repo = SQLAlchemyGcTaskRepository(session)
        stale_attempt = repo.update_task(
            waiting_2.model_copy(update={"status": GcStatus.DONE}),
            expected_lease_token=0,
        )
        assert stale_attempt is None
        session.commit()

    # Before 24h wait expires, generation 2 slot must NOT be purged
    worker_1.run_due()
    assert slot_2.is_file()
    assert {t.id: t for t in _tasks()}[task_2.id].attempts == 1

    # After 24h wait expires, generation 2 converges cleanly to DONE
    _advance_isolation(waiting_2, slot_2)
    worker_2.run_due()
    final_tasks = {t.id: t for t in _tasks()}
    assert final_tasks[task_1.id].status == GcStatus.DONE
    assert final_tasks[task_2.id].status == GcStatus.DONE
    assert final_tasks[task_2.id].attempts == 2 and final_tasks[task_2.id].lease_token == 2
    assert not slot_1.exists() and not slot_2.exists()
    assert not worker_1.layout.final_path(KEY).exists()
    assert _pg_advisory_locks() == []
    _dump_db_state("pg_gc02_converged")


def test_pg_gc02_two_workers_race_same_task(pg_closure_client):
    """GC-02 PostgreSQL: two real GcWorkers racing to claim the same pending task."""
    client, settings = pg_closure_client
    worker_1 = client.app.state.attachment_maintenance.gc
    worker_2 = GcWorker(get_session_factory(), worker_1.layout, worker_1.storage_lock, settings)

    item = _item(client)
    _delete(client, item, _upload(client, item))
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(w.run_due) for w in (worker_1, worker_2)]
        for job in jobs:
            job.result(timeout=20)

    task, = _tasks()
    assert task.status == GcStatus.RUNNING
    assert task.attempts == 1 and task.lease_token == 1
    assert task.lease_owner in {worker_1.owner, worker_2.owner}
    assert _slot(worker_1.layout, task).read_bytes() == DATA
    assert _pg_advisory_locks() == []
    _dump_db_state("pg_gc02_same_task_race")


# ---------------------------------------------------------------------------
# ORP-01: Full chain DB Commit Failure -> Orphan -> Scan -> GC -> Quarantine -> 24h -> Purge
# ---------------------------------------------------------------------------


def _run_orp01_full_chain(client, maint, *, dialect_label: str) -> None:
    gc = maint.gc
    item = _item(client)
    protected_data = DATA + b"-protected-reference"
    protected_key = sha256(protected_data).hexdigest()
    protected_att_id = _upload(client, item, protected_data)
    protected_path = gc.layout.final_path(protected_key)

    # 1. Inject DB commit failure after physical publish
    orphan_path = _publish_without_commit(client, item, gc.layout, DATA)
    assert sha256(orphan_path.read_bytes()).hexdigest() == KEY
    assert _tasks(KEY) == []
    _dump_db_state(f"{dialect_label}_orp01_after_commit_failure")

    # 2. Pre-24h scan: detects orphan, does NOT enqueue GC task yet, does NOT flag protected
    pre_report = maint.recovery.scan_once()
    assert pre_report is not None
    assert {e["storage_key"] for e in pre_report["orphan_blobs"]} == {KEY}
    assert _tasks(KEY) == []
    print(f"[{dialect_label}_ORP01] pre_24h_report_counts={json.dumps(pre_report['counts'])}")

    # 3. Advance mtime past 24h on BOTH orphan and protected files -> scan enqueues ONLY orphan
    _mark_expired(orphan_path)
    _mark_expired(protected_path)
    post_report = maint.recovery.scan_once()
    assert post_report is not None
    assert {e["storage_key"] for e in post_report["orphan_blobs"]} == {KEY}
    pending_task, = _tasks(KEY)
    assert pending_task.status == GcStatus.PENDING
    assert _tasks(protected_key) == []
    _dump_db_state(f"{dialect_label}_orp01_after_scan_enqueue")

    # 4. Worker claims, locks StorageKeyLock, rechecks refs==0, moves to quarantine
    gc.run_due()
    running_task, = _tasks(KEY)
    slot = _slot(gc.layout, running_task)
    assert running_task.status == GcStatus.RUNNING
    assert running_task.attempts == 1 and running_task.lease_token == 1
    assert running_task.quarantine_path == slot.name
    assert running_task.next_retry_at - running_task.quarantined_at == timedelta(hours=24)
    assert not orphan_path.exists()
    assert sha256(slot.read_bytes()).hexdigest() == KEY
    _dump_db_state(f"{dialect_label}_orp01_after_quarantine")

    # 5. Retention period check: running before 24h MUST NOT purge
    gc.run_due()
    assert slot.is_file()
    assert _tasks(KEY)[0].attempts == 1

    # 6. Advance isolation past 24h -> purge safely
    _advance_isolation(running_task, slot)
    gc.run_due()
    done_task, = _tasks(KEY)
    assert done_task.status == GcStatus.DONE
    assert done_task.attempts == 2 and done_task.lease_token == 2
    assert not slot.exists()
    assert not orphan_path.exists()
    _dump_db_state(f"{dialect_label}_orp01_after_purge")

    # 7. Referenced file remains completely untouched in DB and on disk
    assert sha256(protected_path.read_bytes()).hexdigest() == protected_key
    with get_session_factory()() as session:
        assert list(session.scalars(select(AttachmentORM.id))) == [protected_att_id]


def test_orp01_full_chain_sqlite(client, maintenance):
    _run_orp01_full_chain(client, maintenance, dialect_label="sqlite")


def test_pg_orp01_full_chain(pg_closure_client):
    client, _ = pg_closure_client
    _run_orp01_full_chain(client, client.app.state.attachment_maintenance, dialect_label="pg")
    assert _pg_advisory_locks() == []


# ---------------------------------------------------------------------------
# ORP-05: Real subprocess crash windows & quarantine slot recovery rules
# ---------------------------------------------------------------------------


_ORP05_HANDOFF_CHILD = """
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
    os._exit(31)

def exit_after_receiver(*args):
    assert write(*args) is not None
    os._exit(32)

def transfer_then_exit(*args):
    if point == "after_transfer":
        transfer(*args)
    os._exit(33)

def restore_then_exit(*args, **kwargs):
    restore(*args, **kwargs)
    os._exit(34)

if point == "before_receiver":
    scanner.database.enqueue = exit_before_receiver
elif point == "after_receiver":
    scanner.database.write = exit_after_receiver
elif point == "during_restore":
    module.restore_from_quarantine = restore_then_exit
else:
    scanner._transfer_slot = transfer_then_exit
scanner.scan_once()
"""

_ORP05_MOVE_BEFORE_DB_CHILD = """
import os
import sys
from pathlib import Path
from app.core.config import Settings
from app.db.session import get_session_factory, init_db
from app.db.storage_lock import build_storage_lock
from app.services.attachment_maintenance import GcWorker
from app.services.attachment_storage import validate_storage_roots

class CrashAfterMoveWorker(GcWorker):
    def _wait_quarantine(self, *args):
        os._exit(35)

settings = Settings(database_url=sys.argv[1], data_dir=Path(sys.argv[2]), _env_file=None)
init_db(settings)
CrashAfterMoveWorker(
    get_session_factory(),
    validate_storage_roots(settings),
    build_storage_lock(settings),
    settings,
).run_due()
"""


def _run_orp05_terminal_task_crash(
    client, maint, settings: Settings, point: str, *, is_pg: bool,
) -> None:
    """Subprocess crash during ORP recovery of a terminal-task (DONE) quarantine residual."""
    gc = maint.gc
    layout = gc.layout
    item = _item(client)

    # Create a real terminal DONE task as owner of the quarantine residual
    terminal_task = GcTask(storage_key=KEY, status=GcStatus.DONE, attempts=2, lease_token=2)
    with get_session_factory()() as session:
        SQLAlchemyGcTaskRepository(session).save_task(terminal_task)
        session.commit()

    if point == "during_restore":
        attachment_id = _upload(client, item)
        formal = layout.final_path(KEY)
    else:
        attachment_id = None
        formal = _publish_without_commit(client, item, layout, DATA)

    source = layout.quarantine_dir / f"{KEY}.{terminal_task.id}"
    formal.rename(source)

    # Also place an unknown-named file and a corrupt slot file to verify both are preserved
    unknown_named = layout.quarantine_dir / "unknown-residual-artifact.bin"
    unknown_named.write_bytes(b"unknown-must-not-delete")
    corrupt_slot = layout.quarantine_dir / f"{KEY}.{uuid4()}"
    corrupt_slot.write_bytes(b"corrupt-must-not-delete")

    child = _run_subprocess(_ORP05_HANDOFF_CHILD, settings, point)
    expected_rc = {
        "before_receiver": 31,
        "after_receiver": 32,
        "before_transfer": 33,
        "after_transfer": 33,
        "during_restore": 34,
    }[point]
    assert child.returncode == expected_rc, child.stderr.decode(errors="replace")
    print(f"[ORP05] dialect={'pg' if is_pg else 'sqlite'} point={point} child_exit={child.returncode}")

    if is_pg:
        # On PostgreSQL, dead subprocess connection closes and advisory lock releases automatically!
        assert _pg_advisory_locks() == []
    else:
        with get_session_factory()() as session:
            lock_row = session.get(StorageLockORM, KEY)
            if lock_row is not None:
                lock_row.lease_expires_at = utcnow() - timedelta(seconds=1)
                session.commit()

    assert unknown_named.read_bytes() == b"unknown-must-not-delete"
    assert corrupt_slot.read_bytes() == b"corrupt-must-not-delete"

    if point == "during_restore":
        assert formal.read_bytes() == DATA
        assert client.get(f"/api/knowledge/{item}/attachments/{attachment_id}").content == DATA
        report = maint.recovery.scan_once()
        assert report is not None
        assert any(e.get("event") == "unrecognized_slot" for e in report["quarantine_residual"])
        assert formal.read_bytes() == DATA
        assert unknown_named.read_bytes() == b"unknown-must-not-delete"
        assert corrupt_slot.read_bytes() == b"corrupt-must-not-delete"
        return

    # Restarted worker & recovery scan take over
    if point in {"after_receiver", "before_transfer"}:
        non_done = [t for t in _tasks() if t.id != terminal_task.id]
        assert len(non_done) == 1 and non_done[0].status == GcStatus.PENDING
        assert source.read_bytes() == DATA
        gc.run_due()
        assert {t.id: t for t in _tasks()}[non_done[0].id].status == GcStatus.DONE
    elif point == "before_receiver":
        assert [t.id for t in _tasks()] == [terminal_task.id]
        assert source.read_bytes() == DATA
    else:
        non_done = [t for t in _tasks() if t.id != terminal_task.id]
        assert len(non_done) == 1
        assert not source.exists()
        assert _slot(layout, non_done[0]).read_bytes() == DATA

    report = maint.recovery.scan_once()
    assert report is not None
    assert any(e.get("event") == "unrecognized_slot" for e in report["quarantine_residual"])
    gc.run_due()

    running, = [t for t in _tasks() if t.status == GcStatus.RUNNING]
    slot = _slot(layout, running)
    assert running.id != terminal_task.id
    assert slot.read_bytes() == DATA and not source.exists()
    assert running.next_retry_at - running.quarantined_at == timedelta(hours=24)

    # Before 24h elapses, receiver slot must NOT be purged
    gc.run_due()
    assert slot.is_file()

    # After 24h, receiver slot is safely purged; terminal_task remains DONE; unknown/corrupt kept
    _advance_isolation(running, slot)
    gc.run_due()
    assert not slot.exists()
    assert {t.id: t for t in _tasks()}[running.id].status == GcStatus.DONE
    assert {t.id: t for t in _tasks()}[terminal_task.id].status == GcStatus.DONE
    assert unknown_named.read_bytes() == b"unknown-must-not-delete"
    assert corrupt_slot.read_bytes() == b"corrupt-must-not-delete"
    _dump_db_state(f"orp05_{'pg' if is_pg else 'sqlite'}_{point}_converged")


def _run_orp05_move_before_db_writeback_and_active_slot(
    client, maint, settings: Settings, *, is_pg: bool,
) -> None:
    """Window 3: physical move completes, child dies before DB writeback; plus active-slot protection."""
    gc = maint.gc
    layout = gc.layout
    item = _item(client)
    _delete(client, item, _upload(client, item))
    task, = _tasks()

    child = _run_subprocess(_ORP05_MOVE_BEFORE_DB_CHILD, settings)
    assert child.returncode == 35, child.stderr.decode(errors="replace")
    slot = _slot(layout, task)
    assert slot.read_bytes() == DATA
    assert not layout.final_path(KEY).exists()

    with get_session_factory()() as session:
        row = session.get(GcTaskORM, str(task.id))
        assert row is not None
        assert row.status == "running"
        assert row.quarantined_at is None
        assert row.quarantine_path is None

    # Active task slot protection: ORP must recognize active task ownership & preserve slot
    if is_pg:
        assert _pg_advisory_locks() == []
    else:
        with get_session_factory()() as session:
            session.get(StorageLockORM, KEY).lease_expires_at = utcnow() - timedelta(seconds=1)
            session.commit()

    unknown = layout.quarantine_dir / "unrecognized-orphan-file"
    unknown.write_bytes(b"keep-me")
    report = maint.recovery.scan_once()
    assert report is not None
    assert {"storage_key": KEY, "event": "owned_slot_preserved"} in report["quarantine_residual"]
    assert {"event": "unrecognized_slot"} in report["quarantine_residual"]
    assert slot.read_bytes() == DATA
    assert unknown.read_bytes() == b"keep-me"

    # Expire task lease so new worker takes over, adopts slot, and starts fresh 24h wait
    with get_session_factory()() as session:
        session.get(GcTaskORM, str(task.id)).lease_expires_at = utcnow() - timedelta(seconds=1)
        session.commit()

    gc.run_due()
    adopted, = _tasks()
    assert adopted.id == task.id
    assert adopted.status == GcStatus.RUNNING
    assert adopted.attempts == 2 and adopted.lease_token == 2
    assert adopted.quarantined_at is not None
    assert adopted.quarantine_path == slot.name
    assert adopted.next_retry_at - adopted.quarantined_at == timedelta(hours=24)
    assert slot.read_bytes() == DATA

    # Advance 24h and converge
    _advance_isolation(adopted, slot)
    gc.run_due()
    assert _tasks()[0].status == GcStatus.DONE
    assert not slot.exists()
    assert unknown.read_bytes() == b"keep-me"
    if is_pg:
        assert _pg_advisory_locks() == []
    _dump_db_state(f"orp05_{'pg' if is_pg else 'sqlite'}_move_before_db_converged")


@pytest.mark.parametrize(
    "point",
    ["before_receiver", "after_receiver", "before_transfer", "after_transfer", "during_restore"],
)
def test_orp05_terminal_task_crash_sqlite(client, maintenance, settings, point):
    _run_orp05_terminal_task_crash(client, maintenance, settings, point, is_pg=False)


def test_orp05_move_before_db_and_active_slot_sqlite(client, maintenance, settings):
    _run_orp05_move_before_db_writeback_and_active_slot(client, maintenance, settings, is_pg=False)


@pytest.mark.parametrize(
    "point",
    ["before_receiver", "after_receiver", "before_transfer", "after_transfer", "during_restore"],
)
def test_pg_orp05_terminal_task_crash(pg_closure_client, point):
    client, settings = pg_closure_client
    _run_orp05_terminal_task_crash(
        client, client.app.state.attachment_maintenance, settings, point, is_pg=True,
    )


def test_pg_orp05_move_before_db_and_active_slot(pg_closure_client):
    client, settings = pg_closure_client
    _run_orp05_move_before_db_writeback_and_active_slot(
        client, client.app.state.attachment_maintenance, settings, is_pg=True,
    )
