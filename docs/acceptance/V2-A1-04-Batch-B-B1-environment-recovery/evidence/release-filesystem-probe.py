"""Supplemental release-failure and cross-filesystem observations."""

import errno
import hashlib
import logging
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
import traceback
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.db.storage_lock import PostgresStorageKeyLock


class OriginalBusinessError(Exception):
    pass


class ReleaseLog(logging.Handler):
    def __init__(self):
        super().__init__()
        self.seen = False

    def emit(self, record):
        if record.getMessage() == "STORAGE_LOCK_RELEASE_FAILED":
            self.seen = True


def business_failure():
    raise OriginalBusinessError("deliberate probe error")


def wait_for_heartbeat(connection):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        pid = connection.execute(text(
            "SELECT l.pid FROM pg_locks l JOIN pg_stat_activity a ON a.pid=l.pid "
            "WHERE l.locktype='advisory' AND l.granted AND a.datname=current_database() "
            "AND a.usename=current_user AND a.wait_event_type='Lock' "
            "AND starts_with(a.query, 'UPDATE storage_lock SET lease_expires_at')"
        )).scalar_one_or_none()
        connection.commit()
        if pid is not None:
            return pid
        time.sleep(0.025)
    raise AssertionError("no heartbeat row-lock wait observed")


def release_failure(engine, *, committed):
    key = hashlib.sha256(uuid4().bytes).hexdigest()
    marker = uuid4().hex
    manager = PostgresStorageKeyLock(engine, ttl_seconds=30, wait_seconds=5, heartbeat_seconds=0.6)
    guard = manager.acquire_many([key], "b1-probe-release")
    assert guard is not None
    logger = logging.getLogger("app.db.storage_lock")
    handler = ReleaseLog()
    logger.addHandler(handler)
    try:
        with engine.connect() as blocker, engine.connect() as monitor:
            blocker.execute(text("SELECT 1 FROM storage_lock WHERE storage_key=:key FOR UPDATE"), {"key": key})
            try:
                pid = wait_for_heartbeat(monitor)
                # The already-running heartbeat captured five seconds. Give the
                # independent release 250 ms so the server row lock forces failure.
                manager.wait_seconds = 0.25
                if committed:
                    with guard:
                        with engine.begin() as business:
                            business.execute(text(
                                "INSERT INTO b1_release_probe (marker) VALUES (:marker)"
                            ), {"marker": marker})
                    assert monitor.execute(text(
                        "SELECT count(*) FROM b1_release_probe WHERE marker=:marker"
                    ), {"marker": marker}).scalar_one() == 1
                    monitor.commit()
                else:
                    try:
                        with guard:
                            business_failure()
                    except OriginalBusinessError as exc:
                        assert traceback.extract_tb(exc.__traceback__)[-1].name == "business_failure"
                    else:
                        raise AssertionError("business exception was swallowed")
                assert handler.seen, "release failure was not recorded"
            finally:
                manager.wait_seconds = 5
                blocker.rollback()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                alive = monitor.execute(text(
                    "SELECT count(*) FROM pg_stat_activity WHERE pid=:pid"
                ), {"pid": pid}).scalar_one()
                monitor.commit()
                if not alive:
                    break
                time.sleep(0.025)
            else:
                raise AssertionError("dedicated backend did not close")
            other = PostgresStorageKeyLock(engine, wait_seconds=2, heartbeat_seconds=0)
            next_guard = other.acquire_many([key], "b1-probe-after-release")
            assert next_guard is not None
            assert next_guard.release()
            print("PASS release deadline with live PG row lock:",
                  "preserved committed result" if committed else "preserved original traceback",
                  f"and cleaned backend {pid}")
    finally:
        logger.removeHandler(handler)
        if not guard.released:
            guard.release()


def cross_filesystem(ext4_path):
    with TemporaryDirectory(prefix="explainlab-b1-", dir="/dev/shm") as tmp:
        source = ext4_path / "cross-filesystem-source"
        source.write_bytes(b"ExplainLab B1 cross-filesystem probe")
        destination = Path(tmp) / "destination"
        assert source.stat().st_dev != destination.parent.stat().st_dev
        for operation in (os.link, os.rename):
            try:
                operation(source, destination)
            except OSError as exc:
                assert exc.errno == errno.EXDEV, (operation.__name__, exc.errno)
            else:
                raise AssertionError(f"{operation.__name__} unexpectedly crossed filesystems")
            assert source.read_bytes() == b"ExplainLab B1 cross-filesystem probe"
            assert not destination.exists()
        print("PASS kernel EXDEV for link and rename between ext4 and /dev/shm")


cross_filesystem(Path(sys.argv[1]))
engine = create_engine(os.environ["EXPLAINLAB_PG_TEST_URL"], poolclass=NullPool)
try:
    with engine.begin() as setup:
        assert setup.execute(text("SELECT current_database(), current_user")).one() == (
            "explainlab_b1_acceptance", "explainlab_b1_runner"
        )
        setup.execute(text("CREATE TABLE IF NOT EXISTS b1_release_probe (marker text PRIMARY KEY)"))
    for committed in (False, True):
        release_failure(engine, committed=committed)
finally:
    engine.dispose()
