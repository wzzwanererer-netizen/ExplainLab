"""Extra real-PostgreSQL observations against the dedicated B1 cluster."""

import hashlib
import os
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.db.storage_lock import PostgresLockFailure, PostgresStorageKeyLock, _advisory_identity

engine = create_engine(os.environ["EXPLAINLAB_PG_TEST_URL"], poolclass=NullPool)
salt = uuid4().hex


def keys(count):
    return [hashlib.sha256(f"{salt}:{count}:{i}".encode()).hexdigest() for i in range(count)]


def manager(wait=4):
    return PostgresStorageKeyLock(engine, wait_seconds=wait, heartbeat_seconds=0)


def backend(guard):
    connection = guard.pg_state.connection
    pid = connection.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
    connection.rollback()
    return pid


with engine.connect() as monitor:
    assert monitor.execute(text("SELECT current_database(), current_user")).one() == (
        "explainlab_b1_acceptance", "explainlab_b1_runner"
    )

    batch = keys(100)
    assert len({_advisory_identity(key) for key in batch}) == 100
    large = manager().acquire_many(batch, "b1-probe-large")
    assert large is not None
    try:
        pid = backend(large)
        held = monitor.execute(text(
            "SELECT count(*) FROM pg_locks WHERE pid=:pid AND locktype='advisory' AND granted"
        ), {"pid": pid}).scalar_one()
        assert held == len(large.leases) == 100
        print(f"PASS 100 keys, 100 granted advisory locks, dedicated backend {pid}")
    finally:
        large.release()

    low, high = sorted(keys(2), key=_advisory_identity)
    holder = manager().acquire_many([high], "b1-probe-hold")
    assert holder is not None
    try:
        failed = manager(0.6).acquire_many([low, high], "b1-probe-partial")
        assert failed is None
        other = manager().acquire_many([low], "b1-probe-clean")
        assert other is not None
        assert other.leases[0].lease_token == 1
        other.release()
        print("PASS partial acquisition released earlier advisory lock and did not write its token")
    finally:
        holder.release()

    first, blocked = sorted(keys(3))[:2]
    seed = manager().acquire_many([blocked], "b1-probe-seed")
    assert seed is not None
    seed.release()
    with engine.connect() as row_lock, ThreadPoolExecutor(max_workers=1) as worker:
        row_lock.execute(text("SELECT 1 FROM storage_lock WHERE storage_key=:key FOR UPDATE"),
                         {"key": blocked})
        future = worker.submit(manager(8).acquire_many, [first, blocked], "b1-probe-killed")
        stop = time.monotonic() + 4
        victim = None
        while time.monotonic() < stop and victim is None:
            victim = monitor.execute(text(
                "SELECT l.pid FROM pg_locks l JOIN pg_stat_activity a ON a.pid=l.pid "
                "WHERE l.locktype='advisory' AND l.granted "
                "AND a.datname=current_database() AND a.usename=current_user "
                "AND a.wait_event_type='Lock' GROUP BY l.pid HAVING count(*)=2"
            )).scalar_one_or_none()
            monitor.commit()
            if victim is None:
                time.sleep(0.025)
        assert victim is not None
        assert monitor.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": victim}).scalar_one()
        try:
            future.result(timeout=9)
        except PostgresLockFailure as exc:
            print("Blocked batch failed after real pg_terminate_backend:", type(exc).__name__)
        else:
            raise AssertionError("batch did not report a connection failure")
        row_lock.rollback()
    takeover = manager().acquire_many([first, blocked], "b1-probe-takeover")
    assert takeover is not None
    try:
        tokens = {lease.storage_key: lease.lease_token for lease in takeover.leases}
        assert tokens == {first: 1, blocked: 2}, tokens
        print(f"PASS backend {victim} terminated mid-batch, advisory cleanup and atomic token takeover")
    finally:
        takeover.release()

engine.dispose()
