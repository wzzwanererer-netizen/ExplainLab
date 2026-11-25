"""Deterministic fault injection for PostgreSQL lock scheduling (no live PG)."""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

from app.db import storage_lock as locks
from knowledge_core.domain.entities import utcnow

KEY_A = "a" * 64
KEY_B = "b" * 64
KEY_ALIAS = "a" * 16 + "b" * 48


class DriverFailure(Exception):
    def __init__(self, sqlstate):
        self.sqlstate = sqlstate


class Result:
    rowcount = 1

    def __init__(self, value=None, rows=()):
        self.value = value
        self.rows = rows

    def scalar_one(self):
        return self.value

    def __iter__(self):
        return iter(self.rows)


class DedicatedConnection:
    def __init__(self):
        self.closed = False
        self.invalidated = False
        self.connection = SimpleNamespace(driver_connection=object())
        self.transaction = False
        self.calls = []
        self.identities = set()
        self.closed_event = threading.Event()

    @contextmanager
    def begin(self):
        self.transaction = True
        try:
            yield
        finally:
            self.transaction = False

    def in_transaction(self):
        return self.transaction

    def rollback(self):
        self.transaction = False

    def commit(self):
        self.transaction = False

    def invalidate(self):
        self.invalidated = True

    def close(self):
        self.closed = True
        self.closed_event.set()

    def execute(self, sql, parameters=None):
        assert not self.closed and not self.invalidated
        sql = str(sql)
        self.calls.append((sql, parameters))
        if "pg_try_advisory_lock" in sql:
            self.identities.add((parameters["classid"], parameters["objid"]))
            return Result(True)
        if "INSERT INTO storage_lock" in sql:
            return Result(1)
        if "pg_advisory_unlock" in sql:
            self.identities.discard((parameters["classid"], parameters["objid"]))
        if "pg_locks" in sql:
            held = [(str(a & 0xFFFFFFFF), str(b & 0xFFFFFFFF)) for a, b in self.identities]
            return Result(rows=held)
        return Result()


@pytest.fixture
def pg_manager(monkeypatch):
    conn = DedicatedConnection()
    manager = locks.PostgresStorageKeyLock(
        SimpleNamespace(dialect=SimpleNamespace(name="postgresql"), url="postgresql+psycopg://"),
        wait_seconds=1,
        heartbeat_seconds=0,
    )
    monkeypatch.setattr(manager, "_connect", lambda _deadline: conn)
    return manager, conn


def test_batch_orders_deduplicated_identities_and_tokens(pg_manager):
    manager, conn = pg_manager
    guard = manager.acquire_many([KEY_B, KEY_ALIAS, KEY_A, KEY_A], "worker")
    assert guard is not None
    expected = [locks._advisory_identity(key) for key in (KEY_A, KEY_B)]
    acquired = [
        (p["classid"], p["objid"]) for q, p in conn.calls if "pg_try_advisory" in q
    ]
    keys = [p["key"] for q, p in conn.calls if "INSERT INTO storage_lock" in q]
    assert acquired == expected
    assert keys == [KEY_A, KEY_ALIAS, KEY_B]
    assert guard.release()
    unlocks = [(p["classid"], p["objid"]) for q, p in conn.calls if "pg_advisory_unlock" in q]
    assert unlocks == expected[::-1]
    assert conn.closed and not conn.identities


@pytest.mark.parametrize("phase, sqlstate, invalidated, reason", [
    ("token UPSERT", "57014", False, "SQL deadline"),
    ("token UPSERT", "42P01", False, "SQL error"),
    ("advisory acquisition", "08006", True, "session disconnected"),
])
def test_acquisition_fault_is_distinct_and_closes_connection(
    pg_manager, monkeypatch, phase, sqlstate, invalidated, reason
):
    manager, conn = pg_manager
    execute = conn.execute

    def inject(statement, params=None):
        check = "INSERT INTO" if phase == "token UPSERT" else "pg_try_advisory_lock"
        if check in str(statement):
            conn.invalidated = invalidated
            raise OperationalError(
                str(statement), {}, DriverFailure(sqlstate), connection_invalidated=invalidated,
            )
        return execute(statement, params)

    monkeypatch.setattr(conn, "execute", inject)
    with pytest.raises(locks.PostgresLockFailure) as error:
        manager.acquire_many([KEY_A], "worker")
    assert (error.value.phase, error.value.reason) == (phase, reason)
    assert conn.closed


def test_pg_busy_advisory_is_none_and_timeout_is_shared(pg_manager, monkeypatch):
    manager, conn = pg_manager
    execute = conn.execute
    keys = []

    def contend(statement, params=None):
        if "pg_try_advisory_lock" in str(statement):
            identity = (params["classid"], params["objid"])
            keys.append(identity)
            if identity == locks._advisory_identity(KEY_A):
                time.sleep(0.025)
            else:
                return Result(False)
        return execute(statement, params)

    monkeypatch.setattr(conn, "execute", contend)
    start = time.monotonic()
    assert manager.acquire_many([KEY_A, KEY_B], "worker", wait_seconds=0.06) is None
    assert time.monotonic() - start < 0.14
    assert keys[0] != keys[1] and conn.closed
    assert not any("INSERT INTO" in sql for sql, _ in conn.calls)


def test_pg_connect_deadline_returns_and_closes_late_physical_connection(monkeypatch):
    import sqlalchemy

    conn = DedicatedConnection()
    resume = threading.Event()
    started = threading.Event()
    close_engine = SimpleNamespace()

    def slow_connect():
        started.set()
        assert resume.wait(3)
        return conn

    close_engine.connect = slow_connect

    def create_engine(_url, *, poolclass, connect_args):
        assert poolclass is NullPool
        assert connect_args["connect_timeout"] >= 2
        return close_engine

    monkeypatch.setattr(sqlalchemy, "create_engine", create_engine)
    manager = locks.PostgresStorageKeyLock(
        SimpleNamespace(dialect=SimpleNamespace(name="postgresql"), url="postgresql+psycopg://")
    )
    try:
        with pytest.raises(locks.PostgresLockFailure, match="connection deadline"):
            manager.acquire_many([KEY_A], "worker", wait_seconds=0.05)
        assert started.wait(0.5)
        assert not conn.closed
    finally:
        resume.set()
    assert conn.closed_event.wait(1)
    assert conn.calls == []


def test_pg_expired_or_disconnected_guard_does_not_reconnect(pg_manager):
    manager, conn = pg_manager
    guard = manager.acquire_many([KEY_A], "worker")
    conn.invalidated = True
    with pytest.raises(locks.StorageLeaseLost, match="dedicated session lost"):
        guard.verify_all()
    assert guard.aborted
    assert guard.release() is False
    assert conn.closed


def test_pg_release_sql_error_is_reported_and_closes_connection(pg_manager, monkeypatch):
    manager, conn = pg_manager
    guard = manager.acquire_many([KEY_A], "worker")
    assert guard is not None
    execute = conn.execute

    def fail_release(statement, params=None):
        if "SET owner=''" in str(statement):
            raise OperationalError(str(statement), {}, DriverFailure("42P01"))
        return execute(statement, params)

    monkeypatch.setattr(conn, "execute", fail_release)
    with pytest.raises(locks.PostgresLockFailure) as error:
        guard.release()
    assert (error.value.phase, error.value.reason) == ("release", "SQL error")
    assert conn.closed and guard.released
    assert guard.release()


@pytest.mark.parametrize("action", ["verify", "release"])
def test_pg_heartbeat_is_drained_before_verify_or_release(pg_manager, monkeypatch, action):
    manager, conn = pg_manager
    execute = conn.execute
    entered = threading.Event()
    proceed = threading.Event()
    exclusive_operation = threading.Event()
    results = []
    errors = []

    def inject(statement, params=None):
        if "UPDATE storage_lock SET lease_expires_at" in str(statement):
            entered.set()
            assert proceed.wait(2)
        if "SET owner=''" in str(statement):
            exclusive_operation.set()
        return execute(statement, params)

    monkeypatch.setattr(conn, "execute", inject)
    guard = manager.acquire_many([KEY_A], "worker", heartbeat_seconds=0.01)
    assert guard is not None

    class Business:
        def execute(self, statement, _params):
            if "FOR UPDATE" in str(statement):
                exclusive_operation.set()
                expiry = utcnow() + locks.timedelta(seconds=60)
                return Result(rows=[(KEY_A, "worker", 1, expiry)])
            return Result()

    def second_operation():
        try:
            results.append(guard.verify_all(Business()) if action == "verify" else guard.release())
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=second_operation)
    try:
        assert entered.wait(1)
        thread.start()
        assert not exclusive_operation.wait(0.05)
    finally:
        proceed.set()
        if thread.ident is not None:
            thread.join(timeout=2)
        guard.release()
    assert exclusive_operation.is_set() and conn.closed
    assert not thread.is_alive() and errors == []
    assert results == ([None] if action == "verify" else [True])
    assert sum("UPDATE storage_lock SET lease_expires_at" in q for q, _ in conn.calls) == 1


@pytest.mark.parametrize("stage", ["budget SQL", "commit", "rollback", "close"])
def test_pg_client_deadline_bounds_driver_call_and_late_cleanup(pg_manager, monkeypatch, stage):
    manager, conn = pg_manager
    release_stage = stage in {"rollback", "close"}
    guard = manager.acquire_many([KEY_A], "worker") if release_stage else None
    manager.wait_seconds = 0.10
    entered, proceed = threading.Event(), threading.Event()
    calls = 0

    def stall(original, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            assert proceed.wait(3)
        return original(*args, **kwargs)

    if stage == "budget SQL":
        original = conn.execute

        def delayed_sql(statement, params=None):
            if "set_config" in str(statement):
                return stall(original, statement, params)
            return original(statement, params)

        monkeypatch.setattr(conn, "execute", delayed_sql)
    else:
        original = getattr(conn, stage)
        monkeypatch.setattr(conn, stage, lambda: stall(original))
    if stage == "rollback":
        monkeypatch.setattr(conn, "in_transaction", lambda: True)
    try:
        started = time.monotonic()
        with pytest.raises(locks.PostgresLockFailure, match="deadline"):
            if release_stage:
                assert guard is not None
                guard.release()
            else:
                manager.acquire_many([KEY_A], "worker")
        assert time.monotonic() - started < 0.40
        assert entered.is_set()
        assert not conn.closed
    finally:
        proceed.set()
    assert conn.closed_event.wait(1)
    assert not manager._registry._active


@pytest.fixture
def release_log(monkeypatch, caplog):
    # The in-process Alembic suite may disable application loggers and
    # replace the root handlers. Capture warnings directly on this logger.
    monkeypatch.setattr(locks.logger, "disabled", False)
    monkeypatch.setattr(locks.logger, "propagate", False)
    caplog.set_level("WARNING", logger=locks.logger.name)
    locks.logger.addHandler(caplog.handler)
    try:
        yield caplog
    finally:
        locks.logger.removeHandler(caplog.handler)


@pytest.mark.parametrize("stage", ["success", "exception", "committed"])
def test_pg_context_release_failure_preserves_business_result(
    pg_manager, monkeypatch, release_log, stage,
):
    import sqlite3

    manager, conn = pg_manager
    guard = manager.acquire_many([KEY_A], "worker")
    assert guard is not None
    original = conn.execute
    original_error = ValueError("business failure")

    def fail_release(statement, params=None):
        if "SET owner=''" in str(statement):
            raise OperationalError(str(statement), {}, DriverFailure("42P01"))
        return original(statement, params)

    def business(db):
        with guard:
            if stage == "exception":
                raise original_error
            if stage == "committed":
                db.execute("INSERT INTO business VALUES (1)")
                db.commit()
            return "completed"

    monkeypatch.setattr(conn, "execute", fail_release)
    db = sqlite3.connect(":memory:")
    try:
        db.execute("CREATE TABLE business (id INTEGER)")
        if stage == "exception":
            with pytest.raises(ValueError) as error:
                business(db)
            assert error.value is original_error
            assert error.traceback[-1].name == "business"
        else:
            assert business(db) == "completed"
        assert db.execute("SELECT id FROM business").fetchall() == (
            [(1,)] if stage == "committed" else []
        )
    finally:
        db.close()
    assert conn.closed and guard.released
    assert any(record.message == "STORAGE_LOCK_RELEASE_FAILED" for record in release_log.records)


def test_pg_close_failure_invalidates_session_and_preserves_result(
    pg_manager, monkeypatch, release_log,
):
    manager, conn = pg_manager
    guard = manager.acquire_many([KEY_A], "worker")
    assert guard is not None

    def fail_close():
        raise OperationalError("close", {}, DriverFailure("08006"))

    monkeypatch.setattr(conn, "close", fail_close)
    with guard:
        result = "completed"
    assert result == "completed"
    assert conn.invalidated and guard.released
    assert any(record.message == "STORAGE_LOCK_RELEASE_FAILED" for record in release_log.records)


@pytest.mark.parametrize("action", ["verify", "release"])
def test_pg_drain_deadline_does_not_reuse_connection_with_stalled_heartbeat(
    pg_manager, monkeypatch, action,
):
    manager, conn = pg_manager
    entered, proceed = threading.Event(), threading.Event()
    execute = conn.execute

    def stall_renewal(statement, params=None):
        if "UPDATE storage_lock SET lease_expires_at" in str(statement):
            entered.set()
            assert proceed.wait(3)
        return execute(statement, params)

    monkeypatch.setattr(conn, "execute", stall_renewal)
    guard = manager.acquire_many([KEY_A], "worker", heartbeat_seconds=0.01)
    assert guard is not None
    try:
        assert entered.wait(1)
        manager.wait_seconds = 0.10  # this operation has a shorter budget than the active renewal
        started = time.monotonic()
        with pytest.raises(locks.PostgresLockFailure, match="deadline"):
            if action == "verify":
                guard.verify_all(SimpleNamespace())
            else:
                guard.release()
        assert time.monotonic() - started < 0.40
        assert guard.aborted and not conn.closed
        assert not any("SET owner=''" in sql for sql, _ in conn.calls)
    finally:
        proceed.set()
        if action == "verify":
            guard.release()
    assert conn.closed_event.wait(2)
