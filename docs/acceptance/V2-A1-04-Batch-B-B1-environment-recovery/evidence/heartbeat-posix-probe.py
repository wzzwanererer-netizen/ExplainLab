"""Check live heartbeat interleavings and modes on the B1 acceptance host."""

import hashlib
import os
from pathlib import Path
import stat
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.db.session import create_engine_from_url
from app.db.storage_lock import PostgresStorageKeyLock, SQLiteStorageKeyLock, new_owner
from app.models import StorageLockORM
from app.services import attachment_storage as storage


def mode(path, expected):
    actual = stat.S_IMODE(path.stat().st_mode)
    assert actual == expected, (path, oct(actual), oct(expected))
    print(f"Mode {actual:04o}: {path}")


def check_storage(root):
    root.mkdir(mode=0o700)
    sqlite_url = f"sqlite:///{root / 'lock.db'}"
    layout = storage.validate_storage_roots(Settings(
        _env_file=None, data_dir=root / "data", database_url=sqlite_url,
    ))
    for folder in (layout.storage_root, layout.staging_root, layout.quarantine_dir, layout.temp_dir):
        mode(folder, 0o700)
    engine = create_engine_from_url(sqlite_url)
    try:
        StorageLockORM.__table__.create(engine)
        manager = SQLiteStorageKeyLock(sessionmaker(engine), heartbeat_seconds=0)
        payload = b"ExplainLab B1 ext4 mode probe"
        key = storage.sha256_bytes(payload)
        temp = storage.write_temp(layout, payload)
        mode(temp.path, 0o600)
        guard = manager.acquire_many([key], new_owner())
        assert guard is not None
        with guard:
            published = storage.publish_no_clobber(layout, temp, key, lock_guard=guard)
        mode(published.path, 0o600)
        mode(published.path.parent, 0o700)
        assert published.path.read_bytes() == payload
        print("PASS ext4 storage directory, staging, quarantine, temp and final Unix modes")
    finally:
        engine.dispose()


def heartbeat_blocked(monitor, deadline):
    while time.monotonic() < deadline:
        pid = monitor.execute(text(
            "SELECT l.pid FROM pg_locks l JOIN pg_stat_activity a ON a.pid=l.pid "
            "WHERE l.locktype='advisory' AND l.granted AND a.datname=current_database() "
            "AND a.usename=current_user AND a.wait_event_type='Lock' "
            "AND a.query LIKE 'UPDATE storage_lock SET lease_expires_at%%'"
        )).scalar_one_or_none()
        monitor.commit()
        if pid is not None:
            return pid
        time.sleep(0.025)
    raise AssertionError("no real PostgreSQL heartbeat row-lock wait observed")


def check_interleaving(engine, action):
    key = hashlib.sha256(uuid4().bytes).hexdigest()
    manager = PostgresStorageKeyLock(
        engine, ttl_seconds=30, wait_seconds=5, heartbeat_seconds=0.6,
    )
    guard = manager.acquire_many([key], f"b1-probe-{action}")
    assert guard is not None

    def verify_and_commit():
        with Session(engine) as session:
            guard.verify_all(session)
            session.commit()

    try:
        with engine.connect() as blocker, engine.connect() as monitor:
            def execute_action():
                return verify_and_commit() if action == "verify" else guard.release()

            with ThreadPoolExecutor(max_workers=1) as thread:
                try:
                    blocker.execute(text(
                        "SELECT 1 FROM storage_lock WHERE storage_key=:key FOR UPDATE"
                    ), {"key": key})
                    pid = heartbeat_blocked(monitor, time.monotonic() + 3)
                    future = thread.submit(execute_action)
                    assert guard._stop.wait(timeout=1)
                    assert not future.done(), f"{action} did not wait for heartbeat backend {pid}"
                    print(f"Observed heartbeat backend {pid} blocked on row lock while {action} waited")
                finally:
                    blocker.rollback()
                result = future.result(timeout=6)
                assert result is (None if action == "verify" else True)
            if action == "verify":
                assert guard.release() is True
            gone = monitor.execute(text(
                "SELECT count(*) FROM pg_stat_activity WHERE pid=:pid"
            ), {"pid": pid}).scalar_one()
            assert gone == 0
            print(f"PASS live PostgreSQL heartbeat/{action} drain, dedicated backend closed")
    finally:
        guard.release()


check_storage(Path(sys.argv[1]) / "posix-modes")
with create_engine(os.environ["EXPLAINLAB_PG_TEST_URL"], poolclass=NullPool).connect() as check:
    engine = check.engine
    try:
        assert check.execute(text("SELECT current_database(), current_user")).one() == (
            "explainlab_b1_acceptance", "explainlab_b1_runner"
        )
        for action in ("verify", "release"):
            check_interleaving(engine, action)
    finally:
        engine.dispose()
