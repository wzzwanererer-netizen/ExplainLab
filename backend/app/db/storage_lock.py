"""storage_key 级互斥锁的双方言实现（V2 A1-04 Batch B，B1-T03）。

- **SQLite**：``storage_lock`` 租约式逻辑锁；短事务条件 UPDATE + INSERT 竞争，
  ``lease_token`` 单调递增，心跳续租，释放只清 owner、不删除行。
- **PostgreSQL**：会话级 advisory lock 是互斥权威；每个 guard 使用一个专用物理
  连接（``NullPool``，关闭即物理断开），``storage_lock`` 行只保存单调 token 与
  展示租约。行 TTL 过期**不授权**接管仍存活的 advisory lock。

业务/Core 只依赖 ``knowledge_core.ports.StorageKeyLock`` 语义；本模块提供批
``LockGuard``、末次 ``verify_all`` 和 10s 获取预算。所有时间 UTC。
"""

from __future__ import annotations

import logging
import math
import os
import socket
import threading
import time
import uuid
from collections.abc import Iterable
from contextlib import contextmanager, suppress
from datetime import UTC, datetime, timedelta

from psycopg import Connection as PsycopgConnection
from psycopg.errors import _WaitTimeout as PsycopgWaitTimeout
from sqlalchemy import Engine, select, text, update
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, QueuePool

from app.db.session import (
    DatabaseDeadline,
    SQLiteWriteTimeout,
    bounded_db_call,
    checkout_budget,
    configure_postgres_checkout,
    is_sqlite_busy,
    run_sqlite_write,
    sqlite_fence_session,
)
from app.models import StorageLockORM
from knowledge_core.domain.entities import StorageLease, utcnow

__all__ = [
    "LockGuard",
    "PostgresStorageKeyLock",
    "PostgresLockFailure",
    "SQLiteStorageKeyLock",
    "StorageLeaseLost",
    "StorageLockError",
    "StorageLockTransient",
    "build_storage_lock",
    "new_owner",
]

logger = logging.getLogger(__name__)

STORAGE_LOCK_TIMEOUT = "STORAGE_LOCK_TIMEOUT"
STORAGE_LEASE_LOST = "STORAGE_LEASE_LOST"
STORAGE_LOCK_UNAVAILABLE = "STORAGE_LOCK_UNAVAILABLE"

_POLL_SECONDS = 0.05
_PG_CLEANUP_RESERVE = 0.02
_MAX_KEYS = 100


class StorageLockError(RuntimeError):
    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        detail = f": {message}" if message else ""
        super().__init__(f"{code}{detail}")


class StorageLeaseLost(StorageLockError):
    def __init__(self, message: str = "storage lease lost") -> None:
        super().__init__(STORAGE_LEASE_LOST, message)


class PostgresLockFailure(StorageLockError):
    """Database failure distinct from an advisory lock held by another session."""

    def __init__(self, phase: str, reason: str) -> None:
        self.phase = phase
        self.reason = reason
        super().__init__(STORAGE_LOCK_UNAVAILABLE, f"PostgreSQL {phase}: {reason}")


class _PostgresDeadline(TimeoutError):
    pass


class StorageLockTransient(RuntimeError):
    """SQLite busy/locked 等瞬时竞争：心跳应稍后重试，不立即 abort。"""


def new_owner() -> str:
    host = socket.gethostname()[:16]
    return f"{host}:{os.getpid()}:{uuid.uuid4().hex[:12]}"[:64]


def _aware(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _validate_key(key: str) -> None:
    if not isinstance(key, str) or len(key) != 64 or any(
        ch not in "0123456789abcdef" for ch in key
    ):
        raise StorageLockError(STORAGE_LOCK_UNAVAILABLE, "invalid storage key")


def _validate_owner(owner: str) -> None:
    if not owner or len(owner) > 64:
        raise StorageLockError(STORAGE_LOCK_UNAVAILABLE, "invalid owner")


class _ActiveRegistry:
    """同 manager 内同一 owner 的完整 key 不得重复持有（非重入）。"""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._active: dict[str, set[str]] = {}

    def register(self, owner: str, keys: Iterable[str]) -> bool:
        with self._guard:
            held = self._active.setdefault(owner, set())
            if any(key in held for key in keys):
                return False
            held.update(keys)
            return True

    def unregister(self, owner: str, keys: Iterable[str]) -> None:
        with self._guard:
            held = self._active.get(owner)
            if held is None:
                return
            held.difference_update(keys)
            if not held:
                self._active.pop(owner, None)


class LockGuard:
    """一批完整 key 的 guard：心跳、abort 标志、末次 fencing 与幂等释放。"""

    def __init__(
        self,
        manager,
        leases: list[StorageLease],
        *,
        ttl_seconds: float,
        heartbeat_seconds: float,
    ) -> None:
        self.manager = manager
        self.leases = tuple(leases)
        self.ttl_seconds = ttl_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self._state_lock = threading.RLock()
        self._released = False
        self._final_fencing = False
        self._abort = False
        self._abort_code = ""
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- 状态 ---------------------------------------------------------------
    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(lease.storage_key for lease in self.leases)

    @property
    def released(self) -> bool:
        return self._released

    @property
    def aborted(self) -> bool:
        return self._abort

    def lease_for(self, storage_key: str) -> StorageLease | None:
        for lease in self.leases:
            if lease.storage_key == storage_key:
                return lease
        return None

    def assert_active(self) -> None:
        if self._released:
            raise StorageLeaseLost("guard released")
        if self._abort:
            raise StorageLeaseLost(self._abort_code or "guard aborted")

    def _mark_abort(self, code: str) -> None:
        with self._state_lock:
            if not self._abort:
                self._abort = True
                self._abort_code = code
                logger.warning("storage guard aborted: %s", code)

    # -- 心跳 ---------------------------------------------------------------
    def start_heartbeat(self) -> None:
        if self.heartbeat_seconds <= 0 or not self.leases or self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._heartbeat_loop,
            name="storage-lock-heartbeat",
            daemon=True,
        )
        self._thread.start()

    def _deadline(self) -> float:
        return time.monotonic() + min(self.manager.wait_seconds, self.ttl_seconds)

    def _wait_failure(self, phase: str):
        if self.manager.manager_name == "postgresql":
            return PostgresLockFailure(phase, "deadline")
        return StorageLeaseLost(f"{phase} deadline")

    @contextmanager
    def _serialized(self, deadline: float, phase: str):
        if not self._state_lock.acquire(timeout=max(0.0, deadline - time.monotonic())):
            raise self._wait_failure(phase)
        try:
            yield
        finally:
            self._state_lock.release()

    def stop_heartbeat(self, deadline: float | None = None) -> bool:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            deadline = self._deadline() if deadline is None else deadline
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
            return not thread.is_alive()
        return True

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(self.heartbeat_seconds):
            with self._state_lock:
                if self._stop.is_set() or self._abort or self._released:
                    return
                try:
                    if not self.manager._renew_guard(self):
                        self._mark_abort(STORAGE_LEASE_LOST)
                        return
                except StorageLockTransient:
                    continue
                except Exception as exc:  # noqa: BLE001 - background thread fails closed
                    self._mark_abort(getattr(exc, "code", STORAGE_LEASE_LOST))
                    logger.warning("storage heartbeat failed: %s", type(exc).__name__)
                    return

    def renew_all(self, *, ttl_seconds: float | None = None) -> bool:
        with self._state_lock:
            self.assert_active()
            if self._final_fencing:
                raise StorageLeaseLost("final fencing already started")
            try:
                ok = self.manager._renew_guard(self, ttl_seconds=ttl_seconds)
            except StorageLockError as exc:
                self._mark_abort(exc.code)
                raise
            if not ok:
                self._mark_abort(STORAGE_LEASE_LOST)
            return ok

    def verify_all(self, session: Session | None = None, *, deadline: float | None = None) -> None:
        deadline = self._deadline() if deadline is None else min(deadline, self._deadline())
        # Final PG verification retains token row locks in session until commit.
        # Drain the heartbeat before taking those locks and never restart it.
        final_pg = session is not None and self.manager.manager_name == "postgresql"
        if final_pg and not self.stop_heartbeat(deadline):
            self._abort = True
            raise self._wait_failure("verify")
        try:
            with self._serialized(deadline, "verify"):
                self.assert_active()
                if final_pg:
                    self._final_fencing = True
                try:
                    if not self.manager._verify_guard(self, session, deadline):
                        raise StorageLeaseLost()
                except BaseException:
                    self._abort = True
                    raise
        except BaseException:
            self._abort = True
            raise

    def release(self) -> bool:
        deadline = time.monotonic() + self.manager.wait_seconds
        try:
            if not self.stop_heartbeat(deadline):
                raise self._wait_failure("release")
            with self._serialized(deadline, "release"):
                return self._release_locked(deadline)
        except StorageLockError:
            if not self._released:
                self._abort = True
                threading.Thread(
                    target=self._deferred_release, name="storage-guard-cleanup", daemon=True,
                ).start()
            raise

    def _release_locked(self, deadline: float) -> bool:
        if self._released:
            return True
        self._released = True
        return self.manager._release_guard(self, deadline)

    def _deferred_release(self):
        with self._state_lock:
            try:
                if self._release_locked(time.monotonic() + self.manager.wait_seconds):
                    return
            except Exception:  # noqa: BLE001 - cleanup cannot change the business outcome
                pass
            logger.warning("STORAGE_LOCK_RELEASE_FAILED")

    def __enter__(self) -> LockGuard:
        return self

    def __exit__(self, *_exc: object) -> None:
        try:
            if self.release():
                return
        except Exception:  # noqa: BLE001 - preserve the business result and traceback
            pass
        logger.warning("STORAGE_LOCK_RELEASE_FAILED")


class _BaseStorageKeyLock:
    manager_name = "base"

    def __init__(
        self,
        *,
        ttl_seconds: float,
        wait_seconds: float,
        heartbeat_seconds: float,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.wait_seconds = wait_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self._registry = _ActiveRegistry()
        self._single_guards: dict[tuple[str, str, int], LockGuard] = {}
        self._single_lock = threading.Lock()

    def acquire_many(
        self,
        storage_keys: Iterable[str],
        owner: str,
        *,
        ttl_seconds: float | None = None,
        wait_seconds: float | None = None,
        heartbeat_seconds: float | None = None,
    ) -> LockGuard | None:
        _validate_owner(owner)
        keys = sorted(set(storage_keys))
        if not keys or len(keys) > _MAX_KEYS:
            raise StorageLockError(STORAGE_LOCK_UNAVAILABLE, "invalid key batch")
        for key in keys:
            _validate_key(key)
        ttl = self.ttl_seconds if ttl_seconds is None else ttl_seconds
        wait = self.wait_seconds if wait_seconds is None else wait_seconds
        heartbeat = self.heartbeat_seconds if heartbeat_seconds is None else heartbeat_seconds
        if not self._registry.register(owner, keys):
            return None
        deadline = time.monotonic() + max(0.0, wait)
        batch_deadline = deadline
        leases: list[StorageLease] = []
        try:
            for index, key in enumerate(keys):
                remaining = batch_deadline - time.monotonic()
                if remaining <= 0:
                    self._release_leases(leases, deadline)
                    self._registry.unregister(owner, keys)
                    return None
                lease = self._acquire_batch_key(
                    key, owner, ttl_seconds=ttl, deadline=batch_deadline, index=index
                )
                if lease is None:
                    self._release_leases(leases, deadline)
                    self._registry.unregister(owner, keys)
                    return None
                leases.append(lease)
                ttl_remaining = (lease.lease_expires_at - utcnow()).total_seconds()
                batch_deadline = min(batch_deadline, time.monotonic() + ttl_remaining)
            guard = LockGuard(self, leases, ttl_seconds=ttl, heartbeat_seconds=heartbeat)
            if time.monotonic() >= batch_deadline:
                raise StorageLeaseLost()
            if len(leases) > 1:
                guard.verify_all(deadline=batch_deadline)
        except StorageLeaseLost:
            self._release_leases(leases, deadline)
            self._registry.unregister(owner, keys)
            return None
        except BaseException:
            self._release_leases(leases, deadline)
            self._registry.unregister(owner, keys)
            raise
        guard.start_heartbeat()
        return guard

    # Core StorageKeyLock 端口：单 key 便捷入口（不自动心跳，调用方 renew）。
    def acquire(
        self, storage_key: str, owner: str, *, ttl_seconds: float
    ) -> StorageLease | None:
        guard = self.acquire_many(
            [storage_key],
            owner,
            ttl_seconds=ttl_seconds,
            heartbeat_seconds=0,
        )
        if guard is None:
            return None
        lease = guard.leases[0]
        with self._single_lock:
            self._single_guards[(lease.owner, lease.storage_key, lease.lease_token)] = guard
        return lease

    def _single_guard(self, lease: StorageLease) -> LockGuard | None:
        with self._single_lock:
            return self._single_guards.get(
                (lease.owner, lease.storage_key, lease.lease_token)
            )

    def renew(self, lease: StorageLease, *, ttl_seconds: float) -> bool:
        guard = self._single_guard(lease)
        if guard is not None:
            try:
                return guard.renew_all(ttl_seconds=ttl_seconds)
            except StorageLeaseLost:
                return False
        return self._renew_lease(lease, ttl_seconds)

    def verify(self, lease: StorageLease) -> bool:
        guard = self._single_guard(lease)
        if guard is not None:
            try:
                guard.verify_all()
            except StorageLeaseLost:
                return False
            return True
        return self._verify_lease(lease)

    def release(self, lease: StorageLease) -> bool:
        key = (lease.owner, lease.storage_key, lease.lease_token)
        with self._single_lock:
            guard = self._single_guards.pop(key, None)
        if guard is not None:
            return guard.release()
        return self._release_lease(lease)

    # 子类实现 -------------------------------------------------------------
    def _acquire_batch_key(
        self, key: str, owner: str, *, ttl_seconds: float, deadline: float, index: int
    ) -> StorageLease | None:
        raise NotImplementedError

    def _renew_lease(self, lease: StorageLease, ttl_seconds: float) -> bool:
        raise NotImplementedError

    def _verify_lease(self, lease: StorageLease) -> bool:
        raise NotImplementedError

    def _release_lease(self, lease: StorageLease) -> bool:
        raise NotImplementedError

    def _renew_guard(self, guard: LockGuard, *, ttl_seconds: float | None = None) -> bool:
        ttl = guard.ttl_seconds if ttl_seconds is None else ttl_seconds
        return all(self._renew_lease(lease, ttl) for lease in guard.leases)

    def _verify_guard(self, guard: LockGuard, session: Session | None, deadline: float) -> bool:
        return all(self._verify_lease(lease) for lease in guard.leases)

    def _release_guard(self, guard: LockGuard, deadline: float) -> bool:
        ok = True
        for lease in reversed(guard.leases):
            try:
                ok = self._release_lease(lease) and ok
            except Exception:  # noqa: BLE001 - 释放失败不回滚已提交业务
                logger.warning("storage lease release failed: %s", lease.storage_key)
                ok = False
        self._registry.unregister(guard.leases[0].owner if guard.leases else "", guard.keys)
        return ok

    def _release_leases(self, leases: list[StorageLease], deadline: float) -> None:
        for lease in reversed(leases):
            try:
                self._release_lease(lease)
            except Exception:  # noqa: BLE001
                logger.warning("partial storage lease release failed")


class SQLiteStorageKeyLock(_BaseStorageKeyLock):
    """SQLite 租约锁；诚实限制：逻辑锁降低而非消除 TOCTOU。"""

    manager_name = "sqlite"

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        ttl_seconds: float = 60.0,
        wait_seconds: float = 10.0,
        heartbeat_seconds: float = 15.0,
    ) -> None:
        super().__init__(
            ttl_seconds=ttl_seconds,
            wait_seconds=wait_seconds,
            heartbeat_seconds=heartbeat_seconds,
        )
        self._session_factory = session_factory

    def _new_lease(self, row: StorageLockORM) -> StorageLease:
        return StorageLease(
            storage_key=row.storage_key,
            owner=row.owner,
            lease_token=row.lease_token,
            lease_expires_at=_aware(row.lease_expires_at),
        )

    def _acquire_batch_key(
        self, key: str, owner: str, *, ttl_seconds: float, deadline: float, index: int
    ) -> StorageLease | None:
        def attempt(session: Session) -> tuple[StorageLease | None, bool]:
            now = utcnow()
            expires = now + timedelta(seconds=ttl_seconds)
            result = session.execute(
                update(StorageLockORM)
                .where(
                    StorageLockORM.storage_key == key,
                    StorageLockORM.lease_expires_at <= now,
                    StorageLockORM.owner != owner,
                )
                .values(
                    owner=owner, lease_token=StorageLockORM.lease_token + 1,
                    lease_expires_at=expires, locked_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            if result.rowcount == 1:
                return self._new_lease(_reload_lock_row(session, key)), False
            row = _reload_lock_row(session, key)
            if row is None:
                row = StorageLockORM(
                    storage_key=key, owner=owner, lease_token=1,
                    lease_expires_at=expires, locked_at=now,
                )
                session.add(row)
                return self._new_lease(row), False
            return None, row.owner == owner

        while time.monotonic() < deadline:
            try:
                lease, reentrant = run_sqlite_write(self._session_factory, attempt, deadline=deadline)
            except SQLiteWriteTimeout:
                return None
            if lease is not None:
                return lease
            if reentrant:
                return None
            time.sleep(min(_POLL_SECONDS, max(0, deadline - time.monotonic())))
        return None

    def _renew_guard(self, guard: LockGuard, *, ttl_seconds: float | None = None) -> bool:
        ttl = guard.ttl_seconds if ttl_seconds is None else ttl_seconds
        return self._renew_leases(guard.leases, ttl)

    def _renew_leases(self, leases: tuple[StorageLease, ...], ttl_seconds: float) -> bool:
        def renew(session: Session) -> bool:
            now = utcnow()
            expires = now + timedelta(seconds=ttl_seconds)
            for lease in leases:
                result = session.execute(
                    update(StorageLockORM)
                    .where(
                        StorageLockORM.storage_key == lease.storage_key,
                        StorageLockORM.owner == lease.owner,
                        StorageLockORM.lease_token == lease.lease_token,
                        StorageLockORM.lease_expires_at > now,
                    )
                    .values(lease_expires_at=expires)
                    .execution_options(synchronize_session=False)
                )
                if result.rowcount != 1:
                    raise StorageLeaseLost()
            return True

        deadline = time.monotonic() + min(self.wait_seconds, _POLL_SECONDS)
        try:
            return run_sqlite_write(self._session_factory, renew, deadline=deadline)
        except SQLiteWriteTimeout as exc:
            raise StorageLockTransient("SQLite storage renewal remained busy") from exc
        except StorageLeaseLost:
            return False

    def _renew_lease(self, lease: StorageLease, ttl_seconds: float) -> bool:
        return self._renew_leases((lease,), ttl_seconds)

    def _verify_lease(self, lease: StorageLease) -> bool:
        deadline = time.monotonic() + self.wait_seconds
        try:
            return self._verify_leases((lease,), None, deadline)
        except StorageLeaseLost:
            return False

    def _verify_guard(self, guard: LockGuard, session: Session | None, deadline: float) -> bool:
        return self._verify_leases(guard.leases, session, deadline)

    def _verify_leases(self, leases, session, deadline: float) -> bool:
        def read() -> bool:
            with sqlite_fence_session(self._session_factory, session, deadline) as reader:
                rows = {
                    row.storage_key: row for row in reader.scalars(
                        select(StorageLockORM)
                        .where(StorageLockORM.storage_key.in_([lease.storage_key for lease in leases]))
                        .execution_options(populate_existing=True)
                    )
                }
                now = utcnow()
                return time.monotonic() < deadline and all(
                    _lease_matches(rows.get(lease.storage_key), lease, now)
                    for lease in leases
                )

        try:
            if session is None and isinstance(self._session_factory.kw["bind"].pool, QueuePool):
                return bounded_db_call(read, deadline)
            return read()
        except (SQLiteWriteTimeout, DatabaseDeadline) as exc:
            raise StorageLeaseLost("SQLite fencing deadline") from exc
        except OperationalError as exc:
            if not is_sqlite_busy(exc):
                raise
            raise StorageLeaseLost("SQLite fencing remained busy") from exc

    @staticmethod
    def _clear_leases(session: Session, leases: Iterable[StorageLease]) -> bool:
        now = utcnow()
        ok = True
        for lease in leases:
            result = session.execute(
                update(StorageLockORM)
                .where(
                    StorageLockORM.storage_key == lease.storage_key,
                    StorageLockORM.owner == lease.owner,
                    StorageLockORM.lease_token == lease.lease_token,
                    StorageLockORM.lease_expires_at > now,
                )
                .values(owner="", lease_expires_at=now)
                .execution_options(synchronize_session=False)
            )
            ok = (result.rowcount == 1) and ok
        return ok

    def _release_lease(self, lease: StorageLease) -> bool:
        try:
            return run_sqlite_write(
                self._session_factory, lambda session: self._clear_leases(session, (lease,)),
                deadline=time.monotonic() + _POLL_SECONDS,
            )
        except SQLiteWriteTimeout:
            return False

    def _release_guard(self, guard: LockGuard, deadline: float) -> bool:
        try:
            return run_sqlite_write(
                self._session_factory,
                lambda session: self._clear_leases(session, reversed(guard.leases)),
                deadline=deadline,
            )
        except (SQLiteWriteTimeout, DBAPIError):
            return False
        finally:
            self._registry.unregister(guard.leases[0].owner, guard.keys)

    def _release_leases(self, leases: list[StorageLease], deadline: float) -> None:
        if not leases:
            return
        # Try reverse cleanup in one nonblocking transaction after contention.
        # If another writer owns SQLite, leave the safe TTL expiry fallback.
        try:
            run_sqlite_write(
                self._session_factory, lambda session: self._clear_leases(session, reversed(leases)),
                deadline=max(deadline, time.monotonic() + _POLL_SECONDS), retry_busy=False,
            )
        except (DBAPIError, SQLiteWriteTimeout):
            logger.warning("partial SQLite storage lock cleanup failed; waiting for lease expiry")




def _reload_lock_row(session: Session, key: str) -> StorageLockORM | None:
    return session.execute(
        select(StorageLockORM)
        .where(StorageLockORM.storage_key == key)
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()


def _lease_matches(row: StorageLockORM | None, lease: StorageLease, now: datetime) -> bool:
    if row is None:
        return False
    return (
        row.owner == lease.owner
        and row.lease_token == lease.lease_token
        and _aware(row.lease_expires_at) > now
    )


def _signed32(value: int) -> int:
    return value - 2**32 if value >= 2**31 else value


def _advisory_identity(storage_key: str) -> tuple[int, int]:
    return _signed32(int(storage_key[:8], 16)), _signed32(int(storage_key[8:16], 16))


def _unsigned32(value: int) -> int:
    return value & 0xFFFFFFFF


def _pg_remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise _PostgresDeadline()
    return remaining


def _pg_apply_budget(executor, deadline: float) -> None:
    remaining_ms = int(_pg_remaining(deadline) * 1000)
    if remaining_ms < 1:
        raise _PostgresDeadline()
    executor.execute(
        text(
            "SELECT set_config('statement_timeout', :ms, true), "
            "set_config('lock_timeout', :ms, true)"
        ),
        {"ms": str(remaining_ms)},
    )
    _pg_remaining(deadline)


def _pg_execute(executor, statement, deadline: float, parameters=None):
    _pg_apply_budget(executor, deadline)
    return executor.execute(statement, parameters or {})


@contextmanager
def _pg_transport_budget(connection, deadline: float):
    """Give synchronous psycopg I/O its own client-side deadline."""
    driver = connection.connection.driver_connection
    if not isinstance(driver, PsycopgConnection):
        yield
        return
    original_wait = driver.wait
    instance_wait = vars(driver).get("wait")

    def wait(generator, interval=0.1, timeout=None):
        remaining = _pg_remaining(deadline)
        try:
            return original_wait(
                generator, interval=interval,
                timeout=remaining if timeout is None else min(remaining, timeout),
            )
        except PsycopgWaitTimeout:
            # A timed-out operation can still be active. End the physical session
            # before SQLAlchemy or the business unit of work can reuse it.
            driver.pgconn.finish()
            raise

    driver.wait = wait
    try:
        yield
    finally:
        if instance_wait is None:
            del driver.wait
        else:
            driver.wait = instance_wait


def _pg_reason(exc: DBAPIError) -> str:
    sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None) or ""
    if isinstance(exc.orig, PsycopgWaitTimeout):
        return "SQL deadline"
    if exc.connection_invalidated or sqlstate.startswith("08"):
        return "session disconnected"
    if sqlstate in {"55P03", "57014"}:
        return "SQL deadline"
    return "SQL error"


def _close_pg(connection, *, abort=False) -> None:
    if connection is not None:
        driver = None
        try:
            if not connection.closed and not connection.invalidated:
                driver = connection.connection.driver_connection
            if abort and isinstance(driver, PsycopgConnection):
                driver.pgconn.finish()
            connection.close()  # NullPool closes the physical connection
        except Exception:  # noqa: BLE001 - best effort physical invalidation
            if isinstance(driver, PsycopgConnection):
                with suppress(Exception):
                    driver.pgconn.finish()
            with suppress(Exception):
                connection.invalidate()
            logger.warning("STORAGE_LOCK_RELEASE_FAILED")
            raise


def _cleanup_pg_after_call(connection, _result=None) -> None:
    with suppress(Exception):
        _close_pg(connection, abort=True)


class PostgresStorageKeyLock(_BaseStorageKeyLock):
    """One dedicated, non-reconnecting PostgreSQL session per guard."""

    manager_name = "postgresql"

    def __init__(
        self,
        engine: Engine,
        *,
        ttl_seconds: float = 60.0,
        wait_seconds: float = 10.0,
        heartbeat_seconds: float = 15.0,
    ) -> None:
        super().__init__(
            ttl_seconds=ttl_seconds, wait_seconds=wait_seconds,
            heartbeat_seconds=heartbeat_seconds,
        )
        if engine.dialect.name != "postgresql":
            raise StorageLockError(STORAGE_LOCK_UNAVAILABLE, "not a PostgreSQL engine")
        self._engine = engine
        self._batch_guards: dict[tuple[str, str, int], LockGuard] = {}

    def verify(self, lease: StorageLease) -> bool:
        with self._single_lock:
            guard = self._batch_guards.get((lease.owner, lease.storage_key, lease.lease_token))
        if guard is None:
            return False
        try:
            guard.verify_all()
        except StorageLeaseLost:
            return False
        return True

    def _connect(self, deadline: float):
        from sqlalchemy import create_engine

        # libpq accepts whole seconds. The caller also bounds its wait using the
        # exact remaining budget; a late connection is closed by its own thread.
        timeout = max(2, math.ceil(_pg_remaining(deadline)))
        def connect():
            engine = create_engine(
                self._engine.url, poolclass=NullPool,
                connect_args={"connect_timeout": timeout},
            )
            if not isinstance(engine, Engine):
                return engine.connect()
            configure_postgres_checkout(engine)
            with checkout_budget(deadline):
                return engine.connect()

        try:
            return bounded_db_call(
                connect, deadline, on_abandon=lambda done: (
                    _cleanup_pg_after_call(done.result()) if done.exception() is None else None
                ),
            )
        except DatabaseDeadline as exc:
            raise PostgresLockFailure("connect", "connection deadline") from exc
        except DBAPIError as exc:
            raise PostgresLockFailure("connect", "connection failed") from exc

    def acquire_many(
        self,
        storage_keys: Iterable[str],
        owner: str,
        *,
        ttl_seconds: float | None = None,
        wait_seconds: float | None = None,
        heartbeat_seconds: float | None = None,
    ) -> LockGuard | None:
        _validate_owner(owner)
        keys = sorted(set(storage_keys))
        if not keys or len(keys) > _MAX_KEYS:
            raise StorageLockError(STORAGE_LOCK_UNAVAILABLE, "invalid key batch")
        for key in keys:
            _validate_key(key)
        ttl = self.ttl_seconds if ttl_seconds is None else ttl_seconds
        wait = self.wait_seconds if wait_seconds is None else wait_seconds
        heartbeat = self.heartbeat_seconds if heartbeat_seconds is None else heartbeat_seconds
        if not self._registry.register(owner, keys):
            return None
        deadline = time.monotonic() + max(0.0, wait)
        connection = None
        acquired: list[tuple[int, int]] = []
        handed_off = False
        phase = "connect"
        try:
            connection = self._connect(deadline)
            phase = "advisory acquisition"
            dedicated = connection
            try:
                leases = bounded_db_call(
                    lambda: self._acquire_connected(dedicated, keys, owner, ttl, deadline, acquired),
                    deadline,
                    on_abandon=lambda _: _cleanup_pg_after_call(dedicated),
                )
            except DatabaseDeadline as exc:
                if exc.started:
                    connection = None  # the operation retains ownership through cleanup
                raise PostgresLockFailure(phase, "deadline") from exc
            except (KeyboardInterrupt, SystemExit):
                connection = None
                raise
            if leases is None:
                return None
            state = _PostgresGuardState(connection=connection, identities=tuple(acquired))
            guard = _PostgresLockGuard(
                self, leases, ttl_seconds=ttl, heartbeat_seconds=heartbeat, state=state,
            )
            guard.start_heartbeat()
            with self._single_lock:
                for lease in leases:
                    self._batch_guards[(lease.owner, lease.storage_key, lease.lease_token)] = guard
            handed_off = True
            return guard
        except _PostgresDeadline as exc:
            raise PostgresLockFailure(phase, "deadline") from exc
        except DBAPIError as exc:
            raise PostgresLockFailure(phase, _pg_reason(exc)) from exc
        finally:
            if not handed_off:
                try:
                    self._bounded_finish(connection, acquired, deadline)
                finally:
                    self._registry.unregister(owner, keys)

    def _acquire_connected(self, connection, keys, owner, ttl, deadline, acquired):
        phase = "advisory acquisition"
        try:
            with _pg_transport_budget(connection, deadline):
                for identity in sorted({_advisory_identity(key) for key in keys}):
                    if not self._try_advisory(connection, identity, deadline):
                        return None
                    acquired.append(identity)
                _pg_apply_budget(connection, deadline)
                connection.commit()
                phase = "token UPSERT"
                return self._write_tokens(connection, keys, owner, ttl, deadline)
        except _PostgresDeadline as exc:
            raise PostgresLockFailure(phase, "deadline") from exc
        except DBAPIError as exc:
            raise PostgresLockFailure(phase, _pg_reason(exc)) from exc

    def _try_advisory(self, connection, identity: tuple[int, int], deadline: float) -> bool:
        classid, objid = identity
        while True:
            held = _pg_execute(
                connection, text("SELECT pg_try_advisory_lock(:classid, :objid)"), deadline,
                {"classid": classid, "objid": objid},
            ).scalar_one()
            if held:
                return True
            remaining = deadline - time.monotonic()
            if remaining <= _PG_CLEANUP_RESERVE:
                return False
            time.sleep(min(_POLL_SECONDS, (remaining - _PG_CLEANUP_RESERVE) / 2))
            if deadline - time.monotonic() <= _PG_CLEANUP_RESERVE:
                return False

    def _write_tokens(
        self, connection, keys: list[str], owner: str, ttl_seconds: float, deadline: float
    ) -> list[StorageLease]:
        now = utcnow()
        expires = now + timedelta(seconds=ttl_seconds)
        rows = []
        with connection.begin():
            for key in keys:
                token = _pg_execute(
                    connection,
                    text(
                        "INSERT INTO storage_lock "
                        "(storage_key, owner, lease_token, lease_expires_at, locked_at) "
                        "VALUES (:key, :owner, 1, :expires, :now) "
                        "ON CONFLICT (storage_key) DO UPDATE SET "
                        "owner=EXCLUDED.owner, lease_token=storage_lock.lease_token + 1, "
                        "lease_expires_at=EXCLUDED.lease_expires_at, locked_at=EXCLUDED.locked_at "
                        "RETURNING lease_token"
                    ),
                    deadline, {"key": key, "owner": owner, "expires": expires, "now": now},
                ).scalar_one()
                rows.append(StorageLease(
                    storage_key=key, owner=owner, lease_token=int(token), lease_expires_at=expires
                ))
            _pg_apply_budget(connection, deadline)
            if utcnow() >= expires:
                raise StorageLeaseLost("lease expired during acquisition")
        _pg_remaining(deadline)
        return rows

    def _finish_connection(self, connection, identities, deadline: float) -> None:
        if connection is None:
            return
        try:
            if not connection.closed and not connection.invalidated:
                if deadline <= time.monotonic():
                    connection.invalidate()
                    return
                with _pg_transport_budget(connection, deadline):
                    if connection.in_transaction():
                        connection.rollback()
                    for classid, objid in reversed(identities):
                        _pg_execute(
                            connection, text("SELECT pg_advisory_unlock(:classid, :objid)"),
                            deadline, {"classid": classid, "objid": objid},
                        )
                    if connection.in_transaction():
                        connection.rollback()
        except (DBAPIError, _PostgresDeadline):
            logger.debug("Explicit advisory unlock incomplete; closing dedicated connection")
        finally:
            _close_pg(connection, abort=deadline <= time.monotonic())

    def _bounded_finish(self, connection, identities, deadline: float, *, strict=False) -> None:
        if connection is None:
            return
        if deadline <= time.monotonic():
            threading.Thread(target=_cleanup_pg_after_call, args=(connection,), daemon=True).start()
            if strict:
                raise _PostgresDeadline()
            return
        try:
            bounded_db_call(lambda: self._finish_connection(connection, identities, deadline), deadline)
        except DatabaseDeadline as exc:
            if strict:
                raise _PostgresDeadline() from exc
        except Exception:  # noqa: BLE001 - acquisition failure remains primary
            if strict:
                raise

    def _renew_lease(self, lease: StorageLease, ttl_seconds: float) -> bool:
        return False

    def _verify_lease(self, lease: StorageLease) -> bool:
        return False

    def _release_lease(self, lease: StorageLease) -> bool:
        return False

    def _renew_guard(self, guard: LockGuard, *, ttl_seconds: float | None = None) -> bool:
        state = guard.pg_state
        deadline = time.monotonic() + min(self.wait_seconds, guard.ttl_seconds)
        ttl = guard.ttl_seconds if ttl_seconds is None else ttl_seconds
        try:
            return state.run(lambda: self._renew_connected(guard, ttl, deadline), deadline)
        except StorageLeaseLost:
            return False
        except (DatabaseDeadline, _PostgresDeadline) as exc:
            raise PostgresLockFailure("heartbeat", "deadline") from exc
        except DBAPIError as exc:
            raise PostgresLockFailure("heartbeat", _pg_reason(exc)) from exc

    def _renew_connected(self, guard, ttl: float, deadline: float) -> bool:
        state = guard.pg_state
        now = utcnow()
        try:
            with state.connection.begin():
                for lease in guard.leases:
                    result = _pg_execute(
                        state.connection,
                        text(
                            "UPDATE storage_lock SET lease_expires_at=:expires "
                            "WHERE storage_key=:key AND owner=:owner "
                            "AND lease_token=:token AND lease_expires_at > clock_timestamp()"
                        ),
                        deadline, {
                            "expires": now + timedelta(seconds=ttl),
                            "key": lease.storage_key, "owner": lease.owner, "token": lease.lease_token,
                        },
                    )
                    if result.rowcount != 1:
                        raise StorageLeaseLost()
                _pg_apply_budget(state.connection, deadline)
            return True
        except StorageLeaseLost:
            return False

    def _verify_guard(self, guard: LockGuard, session: Session | None, deadline: float) -> bool:
        state = guard.pg_state
        state.require_live()
        stmt = (
            select(
                StorageLockORM.storage_key, StorageLockORM.owner,
                StorageLockORM.lease_token, StorageLockORM.lease_expires_at,
            )
            .where(StorageLockORM.storage_key.in_(guard.keys))
            .order_by(StorageLockORM.storage_key)
        )
        try:
            rows = None
            if session is not None:
                _pg_remaining(deadline)
                if isinstance(session, Session):
                    with checkout_budget(deadline):
                        business_connection = session.connection()
                    with _pg_transport_budget(business_connection, deadline):
                        rows = self._read_rows(session, stmt.with_for_update(), deadline)
                else:
                    rows = bounded_db_call(
                        lambda: self._read_rows(session, stmt.with_for_update(), deadline),
                        deadline,
                    )
            return state.run(
                lambda: self._verify_connected(guard, stmt, rows, deadline), deadline,
            )
        except (DatabaseDeadline, _PostgresDeadline, PoolTimeout) as exc:
            raise PostgresLockFailure("verify", "deadline") from exc
        except DBAPIError as exc:
            raise PostgresLockFailure("verify", _pg_reason(exc)) from exc

    @staticmethod
    def _read_rows(executor, stmt, deadline):
        return {
            key: (owner, token, _aware(expires))
            for key, owner, token, expires in _pg_execute(executor, stmt, deadline)
        }

    def _verify_connected(self, guard, stmt, rows, deadline: float) -> bool:
        state = guard.pg_state
        with state.connection.begin():
            if rows is None:
                rows = self._read_rows(state.connection, stmt, deadline)
            held = {
                (int(classid), int(objid))
                for classid, objid in _pg_execute(
                    state.connection,
                    text(
                        "SELECT classid::text, objid::text FROM pg_locks "
                        "WHERE locktype='advisory' AND pid=pg_backend_pid() AND granted "
                        "AND objsubid=2 AND mode='ExclusiveLock'"
                    ),
                    deadline,
                )
            }
            _pg_remaining(deadline)
            state.require_live()
        _pg_remaining(deadline)
        now = utcnow()
        return state.required.issubset(held) and all(
            lease.storage_key in rows
            and rows[lease.storage_key][:2] == (lease.owner, lease.lease_token)
            and rows[lease.storage_key][2] > now
            for lease in guard.leases
        )

    def _release_guard(self, guard: LockGuard, deadline: float) -> bool:
        state = guard.pg_state
        try:
            try:
                ok = state.run(lambda: self._clear_connected(guard, deadline), deadline)
            except StorageLeaseLost:
                self._bounded_finish(state.connection if not state.abandoned else None, (), deadline)
                return False
            except BaseException:
                if not state.abandoned:
                    self._bounded_finish(state.connection, state.identities, deadline)
                raise
            self._bounded_finish(state.connection, state.identities, deadline, strict=True)
            return ok
        except (DatabaseDeadline, _PostgresDeadline) as exc:
            raise PostgresLockFailure("release", "deadline") from exc
        except DBAPIError as exc:
            raise PostgresLockFailure("release", _pg_reason(exc)) from exc
        finally:
            with self._single_lock:
                for lease in guard.leases:
                    self._batch_guards.pop((lease.owner, lease.storage_key, lease.lease_token), None)
            self._registry.unregister(guard.leases[0].owner, guard.keys)

    def _clear_connected(self, guard, deadline: float) -> bool:
        state = guard.pg_state
        try:
            state.require_live()
            with state.connection.begin():
                ok = True
                for lease in reversed(guard.leases):
                    result = _pg_execute(
                        state.connection,
                        text(
                            "UPDATE storage_lock SET owner='', lease_expires_at=clock_timestamp() "
                            "WHERE storage_key=:key AND owner=:owner AND lease_token=:token "
                            "AND lease_expires_at > clock_timestamp()"
                        ),
                        deadline, {
                            "key": lease.storage_key, "owner": lease.owner, "token": lease.lease_token,
                        },
                    )
                    ok = result.rowcount == 1 and ok
                _pg_apply_budget(state.connection, deadline)
            return ok
        except StorageLeaseLost:
            return False


class _PostgresGuardState:
    def __init__(self, *, connection, identities: tuple[tuple[int, int], ...]) -> None:
        self.connection = connection
        self.abandoned = False
        self.driver_connection = connection.connection.driver_connection
        self.identities = identities
        self.required = {
            (_unsigned32(classid), _unsigned32(objid)) for classid, objid in identities
        }

    def require_live(self) -> None:
        if (
            self.abandoned
            or self.connection.closed
            or self.connection.invalidated
            or self.connection.connection.driver_connection is not self.driver_connection
        ):
            raise StorageLeaseLost("PostgreSQL dedicated session lost")

    def run(self, operation, deadline: float):
        self.require_live()

        def execute():
            with _pg_transport_budget(self.connection, deadline):
                return operation()

        try:
            return bounded_db_call(
                execute, deadline,
                on_abandon=lambda _: _cleanup_pg_after_call(self.connection),
            )
        except DatabaseDeadline as exc:
            self.abandoned = exc.started
            raise
        except BaseException as exc:
            if not isinstance(exc, Exception):
                self.abandoned = True
            raise


class _PostgresLockGuard(LockGuard):
    def __init__(self, *args, state: _PostgresGuardState, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.pg_state = state


def build_storage_lock(settings) -> _BaseStorageKeyLock:
    """按数据库方言装配 StorageKeyLock（main lifespan 调用）。"""
    if settings.database_url.startswith("postgresql"):
        from app.db.session import get_engine

        return PostgresStorageKeyLock(
            get_engine(),
            ttl_seconds=settings.storage_lock_ttl_seconds,
            wait_seconds=settings.storage_lock_wait_seconds,
            heartbeat_seconds=settings.storage_lock_heartbeat_seconds,
        )
    from app.db.session import get_session_factory

    return SQLiteStorageKeyLock(
        get_session_factory(),
        ttl_seconds=settings.storage_lock_ttl_seconds,
        wait_seconds=settings.storage_lock_wait_seconds,
        heartbeat_seconds=settings.storage_lock_heartbeat_seconds,
    )
