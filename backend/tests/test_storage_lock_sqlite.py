"""SQLite StorageKeyLock 真实文件库测试（V2 A1-04 Batch B，B1-T03）。

覆盖 LCK-01…09 的 SQLite 部分：租约签发、双 owner 竞争、过期接管、续租、
失配中止、释放/幂等、批锁排序与预算、心跳、末次 fencing、非重入与非法输入。
全部使用真实 SQLite 文件数据库与多线程，不以 mock 代替锁行为。
"""

from __future__ import annotations

import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401  ORM 元数据
from app.core.config import Settings
from app.db.base import Base
from app.db.session import create_engine_from_url, dispose_db
from app.db.storage_lock import (
    SQLiteStorageKeyLock,
    StorageLeaseLost,
    StorageLockError,
    build_storage_lock,
    new_owner,
)
from app.main import create_app
from app.models import StorageLockORM

KEY_A = "a" * 64
KEY_B = "b" * 64
KEY_C = "c" * 64


@pytest.fixture
def lock_env(tmp_path: Path) -> tuple[sessionmaker[Session], SQLiteStorageKeyLock]:
    url = f"sqlite:///{tmp_path / 'lock.db'}"
    engine = create_engine_from_url(url)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    lock = SQLiteStorageKeyLock(factory, ttl_seconds=60.0, wait_seconds=2.0)
    try:
        yield factory, lock
    finally:
        engine.dispose()


def _row(factory: sessionmaker[Session], key: str) -> StorageLockORM | None:
    with factory() as session:
        return session.get(StorageLockORM, key)


def test_batch_discards_first_lease_when_second_outlives_it(lock_env):
    factory, manager = lock_env
    blocker = manager.acquire_many([KEY_B], "second-key", heartbeat_seconds=0)
    assert blocker is not None
    try:
        started = time.monotonic()
        batch = manager.acquire_many(
            [KEY_A, KEY_B], "batch", ttl_seconds=0.15, wait_seconds=1,
            heartbeat_seconds=0,
        )
        assert batch is None
        assert 0.09 <= time.monotonic() - started < 0.50
        old = _row(factory, KEY_A)
        assert old is not None and old.lease_token == 1
        assert _row(factory, KEY_B).owner == "second-key"
    finally:
        assert blocker.release()
    retry = manager.acquire_many([KEY_A, KEY_B], "retry", wait_seconds=0.6, heartbeat_seconds=0)
    assert retry is not None and retry.leases[0].lease_token == old.lease_token + 1
    assert retry.release()


def test_independent_fencing_is_bounded_under_sqlite_exclusive_writer(lock_env):
    factory, _manager = lock_env
    manager = SQLiteStorageKeyLock(factory, wait_seconds=0.15, heartbeat_seconds=0)
    guard = manager.acquire_many([KEY_A], "worker")
    assert guard is not None
    with factory.kw["bind"].connect() as writer:
        writer.exec_driver_sql("BEGIN EXCLUSIVE")
        try:
            started = time.monotonic()
            with pytest.raises(StorageLeaseLost, match="busy|deadline"):
                guard.verify_all()
            assert time.monotonic() - started < 0.35
            assert guard.aborted
        finally:
            writer.rollback()
    assert guard.release()


def test_sqlite_pool_checkout_obeys_budget_for_write_and_business_fence(lock_env):
    from contextlib import ExitStack

    factory, _manager = lock_env
    engine = factory.kw["bind"]
    manager = SQLiteStorageKeyLock(factory, wait_seconds=0.15, heartbeat_seconds=0)
    guard = manager.acquire_many([KEY_A], "owner")
    assert guard is not None
    with ExitStack() as occupied:
        for _ in range(engine.pool.size() + 10):
            occupied.enter_context(engine.connect())
        started = time.monotonic()
        assert manager.acquire_many([KEY_B], "contender") is None
        assert time.monotonic() - started < 0.35
        with factory() as business:
            started = time.monotonic()
            with pytest.raises(StorageLeaseLost, match="deadline"):
                guard.verify_all(business)
            assert time.monotonic() - started < 0.35
            business.rollback()
    assert guard.release()


# --- LCK-01：新 key acquire -------------------------------------------------


def test_lck01_new_key_acquire(lock_env):
    factory, lock = lock_env
    owner = new_owner()
    before = time.time()
    lease = lock.acquire(KEY_A, owner, ttl_seconds=60)
    assert lease is not None
    assert lease.storage_key == KEY_A
    assert lease.owner == owner
    assert lease.lease_token == 1
    assert lease.lease_expires_at.timestamp() >= before + 59
    row = _row(factory, KEY_A)
    assert row is not None
    assert (row.owner, row.lease_token) == (owner, 1)
    assert lock.release(lease) is True


# --- LCK-02：双 owner 同 key 竞争 -------------------------------------------


def test_lck02_two_owners_same_key_only_one_wins(lock_env):
    factory, lock = lock_env
    barrier = threading.Barrier(2)
    results: list[object] = []
    results_lock = threading.Lock()

    def worker(owner: str) -> None:
        barrier.wait()
        lease = lock.acquire(KEY_A, owner, ttl_seconds=60)
        with results_lock:
            results.append(lease)

    threads = [
        threading.Thread(target=worker, args=("owner-1",)),
        threading.Thread(target=worker, args=("owner-2",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    winners = [lease for lease in results if lease is not None]
    assert len(winners) == 1
    row = _row(factory, KEY_A)
    assert row is not None
    assert row.owner == winners[0].owner
    lock.release(winners[0])


def test_lck02_two_managers_share_db(lock_env):
    factory, lock = lock_env
    other = SQLiteStorageKeyLock(factory, ttl_seconds=60.0, wait_seconds=2.0)
    lease = lock.acquire(KEY_A, "owner-1", ttl_seconds=60)
    assert lease is not None
    assert other.acquire(KEY_A, "owner-2", ttl_seconds=60) is None
    lock.release(lease)
    second = other.acquire(KEY_A, "owner-3", ttl_seconds=60)
    assert second is not None
    assert second.lease_token == 2
    other.release(second)


# --- LCK-03：租约过期后接管 -------------------------------------------------


def test_lck03_expired_lease_takeover(lock_env):
    factory, lock = lock_env
    lease_a = lock.acquire(KEY_A, "owner-a", ttl_seconds=0.2)
    assert lease_a is not None
    time.sleep(0.35)
    lease_b = lock.acquire(KEY_A, "owner-b", ttl_seconds=60)
    assert lease_b is not None
    assert lease_b.lease_token == lease_a.lease_token + 1
    assert lease_b.owner == "owner-b"
    # 旧 lease 续租/校验/释放全部失配。
    assert lock.renew(lease_a, ttl_seconds=60) is False
    assert lock.verify(lease_a) is False
    assert lock.release(lease_a) is False
    row = _row(factory, KEY_A)
    assert row is not None and row.owner == "owner-b"
    lock.release(lease_b)


def test_lck03_unexpired_lease_blocks_takeover(lock_env):
    factory, lock = lock_env
    lease = lock.acquire(KEY_A, "owner-a", ttl_seconds=60)
    assert lease is not None
    assert lock.acquire(KEY_A, "owner-b", ttl_seconds=60) is None
    lock.release(lease)


# --- LCK-04：renew 匹配 ------------------------------------------------------


def test_lck04_renew_extends_expiry(lock_env):
    factory, lock = lock_env
    lease = lock.acquire(KEY_A, "owner-a", ttl_seconds=30)
    assert lease is not None
    row_before = _row(factory, KEY_A)
    assert row_before is not None
    first_expiry = row_before.lease_expires_at
    assert lock.renew(lease, ttl_seconds=120) is True
    row_after = _row(factory, KEY_A)
    assert row_after is not None
    assert row_after.lease_expires_at > first_expiry
    assert row_after.lease_token == lease.lease_token
    lock.release(lease)


def test_lck04_renew_after_own_expiry_fails(lock_env):
    factory, lock = lock_env
    lease = lock.acquire(KEY_A, "owner-a", ttl_seconds=0.2)
    assert lease is not None
    time.sleep(0.35)
    assert lock.renew(lease, ttl_seconds=60) is False
    lock.release(lease)


# --- LCK-05：失配立即中止 ----------------------------------------------------


def test_lck05_old_lease_verify_false_after_takeover(lock_env):
    lock = lock_env[1]
    lease_a = lock.acquire(KEY_A, "owner-a", ttl_seconds=0.2)
    assert lease_a is not None
    time.sleep(0.35)
    lease_b = lock.acquire(KEY_A, "owner-b", ttl_seconds=60)
    assert lease_b is not None
    assert lock.verify(lease_a) is False
    assert lock.renew(lease_a, ttl_seconds=60) is False
    # 旧 worker 的受保护步骤必须据此中止（异常型验证）。
    guard = lock.acquire_many(
        [KEY_B], "owner-b", ttl_seconds=0.2, heartbeat_seconds=0
    )
    assert guard is not None
    time.sleep(0.35)
    # 另一 owner 接管 KEY_B 后 guard.verify_all 必须抛 StorageLeaseLost。
    takeover = lock.acquire(KEY_B, "owner-x", ttl_seconds=60)
    assert takeover is not None
    with pytest.raises(StorageLeaseLost):
        guard.verify_all()
    assert guard.aborted is True
    lock.release(takeover)
    guard.release()


# --- LCK-06：release 匹配/失配 ----------------------------------------------


def test_lck06_release_matching_and_mismatch(lock_env):
    factory, lock = lock_env
    lease = lock.acquire(KEY_A, "owner-a", ttl_seconds=60)
    assert lease is not None
    assert lock.release(lease) is True
    row = _row(factory, KEY_A)
    assert row is not None
    assert row.owner == ""
    token_after_release = row.lease_token
    assert token_after_release == lease.lease_token
    # 释放后行仍保留（不 DELETE）；token 单调。
    assert lock.release(lease) is False
    second = lock.acquire(KEY_A, "owner-b", ttl_seconds=60)
    assert second is not None
    assert second.lease_token == token_after_release + 1
    # 旧 lease 不能释放他人。
    assert lock.release(lease) is False
    assert _row(factory, KEY_A).owner == "owner-b"
    lock.release(second)


def test_lck06_guard_release_idempotent(lock_env):
    lock = lock_env[1]
    guard = lock.acquire_many([KEY_A], "owner-a", heartbeat_seconds=0)
    assert guard is not None
    assert guard.release() is True
    assert guard.release() is True
    assert guard.released is True


# --- 批锁：排序、预算、部分失败回滚 ----------------------------------------


def test_acquire_many_dedupes_and_sorts(lock_env):
    factory, lock = lock_env
    guard = lock.acquire_many([KEY_C, KEY_A, KEY_C, KEY_B], "owner-a", heartbeat_seconds=0)
    assert guard is not None
    assert guard.keys == (KEY_A, KEY_B, KEY_C)
    with factory() as session:
        owners = {
            row.storage_key: row.owner
            for row in session.scalars(select(StorageLockORM))
        }
    assert owners == {KEY_A: "owner-a", KEY_B: "owner-a", KEY_C: "owner-a"}
    guard.release()
    with factory() as session:
        owners = {
            row.storage_key: row.owner
            for row in session.scalars(select(StorageLockORM))
        }
    assert owners == {KEY_A: "", KEY_B: "", KEY_C: ""}


def test_acquire_many_partial_failure_releases_acquired(lock_env):
    factory, lock = lock_env
    holder = lock.acquire(KEY_C, "holder", ttl_seconds=60)
    assert holder is not None
    guard = lock.acquire_many(
        [KEY_A, KEY_B, KEY_C],
        "owner-a",
        wait_seconds=0.1,
        heartbeat_seconds=0,
    )
    assert guard is None
    with factory() as session:
        rows = {
            row.storage_key: row.owner for row in session.scalars(select(StorageLockORM))
        }
    # 已取得的 KEY_A/KEY_B 必须回滚释放，不能遗留幽灵 owner。
    assert rows.get(KEY_A) == ""
    assert rows.get(KEY_B) == ""
    assert rows.get(KEY_C) == "holder"
    lock.release(holder)


def test_acquire_many_same_owner_non_reentrant(lock_env):
    lock = lock_env[1]
    guard = lock.acquire_many([KEY_A], "owner-a", heartbeat_seconds=0)
    assert guard is not None
    assert lock.acquire_many([KEY_A], "owner-a", heartbeat_seconds=0) is None
    assert lock.acquire(KEY_A, "owner-a", ttl_seconds=60) is None
    guard.release()
    again = lock.acquire(KEY_A, "owner-a", ttl_seconds=60)
    assert again is not None
    lock.release(again)


def test_acquire_many_invalid_inputs(lock_env):
    lock = lock_env[1]
    with pytest.raises(StorageLockError):
        lock.acquire_many([], "owner-a")
    with pytest.raises(StorageLockError):
        lock.acquire_many(["not-a-key"], "owner-a")
    with pytest.raises(StorageLockError):
        lock.acquire_many([KEY_A], "")
    with pytest.raises(StorageLockError):
        lock.acquire("F" * 64, "owner-a", ttl_seconds=60)


def test_acquire_many_over_100_keys_rejected(lock_env):
    lock = lock_env[1]
    keys = [format(index, "064x") for index in range(101)]
    with pytest.raises(StorageLockError):
        lock.acquire_many(keys, "owner-a")


# --- 心跳 ----------------------------------------------------------------


def test_heartbeat_keeps_lease_alive(lock_env):
    factory, lock = lock_env
    guard = lock.acquire_many(
        [KEY_A], "owner-a", ttl_seconds=0.6, heartbeat_seconds=0.1
    )
    assert guard is not None
    time.sleep(1.0)
    guard.verify_all()  # 不抛异常即心跳续租成功（verify_all 只做断言）
    assert guard.aborted is False
    row = _row(factory, KEY_A)
    assert row is not None
    assert row.owner == "owner-a"
    guard.release()


def test_verify_all_with_session_sees_takeover(lock_env):
    factory, lock = lock_env
    guard = lock.acquire_many([KEY_A], "owner-a", heartbeat_seconds=0)
    assert guard is not None
    with factory() as session:
        guard.verify_all(session)
    # 让行过期并由另一 owner 接管。
    with factory() as session:
        row = session.get(StorageLockORM, KEY_A)
        assert row is not None
        row.lease_expires_at = row.lease_expires_at - timedelta(seconds=120)
        session.commit()
    takeover = lock.acquire(KEY_A, "owner-b", ttl_seconds=60)
    assert takeover is not None
    with factory() as session, pytest.raises(StorageLeaseLost):
        guard.verify_all(session)
    assert guard.aborted is True
    lock.release(takeover)


def test_aborted_guard_rejects_further_use(lock_env):
    lock = lock_env[1]
    guard = lock.acquire_many([KEY_A], "owner-a", heartbeat_seconds=0)
    assert guard is not None
    guard._mark_abort("boom")  # noqa: SLF001 - 验证 abort 对外契约
    with pytest.raises(StorageLeaseLost):
        guard.verify_all()
    with pytest.raises(StorageLeaseLost):
        guard.renew_all()
    guard.release()


# --- 装配 ----------------------------------------------------------------


def test_build_storage_lock_sqlite(settings: Settings):
    from app.db.session import init_db

    engine = init_db(settings)
    Base.metadata.create_all(engine)
    try:
        lock = build_storage_lock(settings)
        assert isinstance(lock, SQLiteStorageKeyLock)
        lease = lock.acquire(KEY_A, "owner-a", ttl_seconds=60)
        assert lease is not None
        assert lock.release(lease) is True
    finally:
        dispose_db()


def test_lifespan_exposes_storage_key_lock(settings: Settings):
    engine = create_engine_from_url(settings.database_url)
    Base.metadata.create_all(engine)
    engine.dispose()
    try:
        app = create_app(settings)
        with TestClient(app) as client:
            lock = client.app.state.storage_key_lock
            assert isinstance(lock, SQLiteStorageKeyLock)
            assert client.app.state.attachment_storage is not None
    finally:
        dispose_db()

def test_short_acquire_budget_with_real_sqlite_writer(lock_env):
    factory, lock = lock_env
    with factory.kw["bind"].connect() as writer:
        writer.exec_driver_sql("BEGIN IMMEDIATE")
        start = time.monotonic()
        assert lock.acquire_many([KEY_A, KEY_B], "deadline-owner", wait_seconds=0.15) is None
        elapsed = time.monotonic() - start
        assert 0.10 <= elapsed < 0.45
        writer.rollback()
    assert _row(factory, KEY_A) is None
    assert _row(factory, KEY_B) is None
    guard = lock.acquire_many([KEY_A, KEY_B], "deadline-owner")
    assert guard is not None
    guard.release()


def test_zero_budget_does_not_create_any_lock_row(lock_env):
    factory, lock = lock_env
    assert lock.acquire_many([KEY_A], "zero-budget", wait_seconds=0) is None
    assert _row(factory, KEY_A) is None


def test_final_fencing_reloads_cached_orm_and_rolls_back_business_write(lock_env):
    from sqlalchemy import update

    factory, lock = lock_env
    guard = lock.acquire_many([KEY_A], "before-takeover", heartbeat_seconds=0)
    assert guard is not None
    with guard, factory() as business:
        cached = business.get(StorageLockORM, KEY_A)
        assert cached.lease_token == 1
        with factory.begin() as other:
            other.execute(
                update(StorageLockORM)
                .where(StorageLockORM.storage_key == KEY_A)
                .values(owner="after-takeover", lease_token=2)
            )

        with pytest.raises(StorageLeaseLost), business.begin_nested():
            business.add(StorageLockORM(
                storage_key=KEY_B, owner="business-sentinel",
                lease_token=1, lease_expires_at=cached.lease_expires_at, locked_at=cached.locked_at,
            ))
            business.flush()
            guard.verify_all(business)
            pytest.fail("commit path reached after losing storage fencing")
        business.rollback()
    assert cached is not None
    assert _row(factory, KEY_A).lease_token == 2
    assert _row(factory, KEY_B) is None


def test_sqlite_busy_retries_in_a_new_transaction_after_rollback(lock_env):
    import sqlite3

    from sqlalchemy.exc import OperationalError

    from app.db.session import run_short_write

    factory, _ = lock_env
    attempts = []

    def write(session):
        attempts.append(session)
        assert session.get(StorageLockORM, KEY_A) is None
        from knowledge_core.domain.entities import utcnow

        now = utcnow()
        session.add(StorageLockORM(
            storage_key=KEY_A, owner="retry", lease_token=1, lease_expires_at=now, locked_at=now,
        ))
        session.flush()
        if len(attempts) == 1:
            raise OperationalError("test", {}, sqlite3.OperationalError("database is locked"))
        return "committed"

    assert run_short_write(
        factory, write, is_sqlite=True, deadline=time.monotonic() + 1,
    ) == "committed"
    assert len(attempts) == 2 and attempts[0] is not attempts[1]
    assert _row(factory, KEY_A).owner == "retry"


def test_sqlite_transaction_owner_raises_at_busy_deadline(lock_env):
    from app.db.session import SQLiteWriteTimeout, run_short_write

    factory, _ = lock_env
    with factory.kw["bind"].connect() as writer:
        writer.exec_driver_sql("BEGIN IMMEDIATE")
        start = time.monotonic()
        with pytest.raises(SQLiteWriteTimeout):
            run_short_write(
                factory, lambda _session: pytest.fail("must not start without a write slot"),
                is_sqlite=True, deadline=start + 0.15,
            )
        assert time.monotonic() - start < 0.45
        writer.rollback()
