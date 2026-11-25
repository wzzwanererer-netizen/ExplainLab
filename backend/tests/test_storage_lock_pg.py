"""真实 PostgreSQL StorageKeyLock 测试（V2 A1-04 Batch B，B1-T03）。

经 ``EXPLAINLAB_PG_TEST_URL`` 门控：未配置时整模块跳过。配置后连真实 PG 实例，
经真实在线 Alembic 迁移取得 ``storage_lock`` 表，以**两个真实物理连接**覆盖
LCK-10 核心语义：

- advisory lock 是互斥权威；行 TTL 过期不授权接管仍存活的 advisory；
- 专用连接关闭与客户端进程终止分别验证，另一连接可接管且 token 单调 +1；
- 相同 advisory 投影（前 16 hex 相同）的不同完整 key 串行、不互相卡死；
- 专用 NullPool 连接、verify/fencing、批量排序与释放。

不得以 SQLite 结果替代本文件；无 PG 环境时本文件必须如实跳过。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.core.config import get_settings
from app.db.session import create_engine_from_url
from app.db.storage_lock import (
    PostgresStorageKeyLock,
    StorageLeaseLost,
    new_owner,
)
from app.models import StorageLockORM
from knowledge_core.domain.entities import StorageLease, utcnow

BACKEND_DIR = Path(__file__).resolve().parents[1]
PG_URL = os.environ.get("EXPLAINLAB_PG_TEST_URL")

pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason="未配置 EXPLAINLAB_PG_TEST_URL（真实 PostgreSQL 实例），跳过 StorageKeyLock PG 测试",
)

KEY_A = "a" * 64
KEY_B = "b" * 64
KEY_C = "c" * 64
# 前 16 hex 相同 → 相同 advisory 投影；完整 key 不同 → 独立 token 行。
KEY_PROJ_1 = "ab" * 32
KEY_PROJ_2 = "ab" * 8 + "cd" * 24


def _alembic_cfg() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


@pytest.fixture(scope="module")
def pg_engine() -> Engine:
    os.environ["DATABASE_URL"] = PG_URL  # type: ignore[assignment]
    get_settings.cache_clear()
    command.upgrade(_alembic_cfg(), "head")
    engine = create_engine_from_url(PG_URL)  # type: ignore[arg-type]
    try:
        yield engine
    finally:
        engine.dispose()
        get_settings.cache_clear()
        os.environ.pop("DATABASE_URL", None)


@pytest.fixture
def factory(pg_engine: Engine):
    return sessionmaker(bind=pg_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture(autouse=True)
def clean_locks(factory: sessionmaker[Session]):
    with factory() as session:
        session.execute(text("DELETE FROM storage_lock"))
        session.commit()
    yield
    with factory() as session:
        session.execute(text("DELETE FROM storage_lock"))
        session.commit()


@pytest.fixture
def manager(pg_engine: Engine) -> PostgresStorageKeyLock:
    lock = PostgresStorageKeyLock(
        pg_engine, ttl_seconds=60.0, wait_seconds=2.0, heartbeat_seconds=0
    )
    yield lock
    # 兜底：确保没有残留 advisory lock 卡住后续用例。
    with pg_engine.connect() as conn:
        conn.execute(text("SELECT pg_advisory_unlock_all()"))
        conn.commit()


def _row(factory: sessionmaker[Session], key: str):
    with factory() as session:
        return session.execute(
            text(
                "SELECT owner, lease_token, lease_expires_at FROM storage_lock "
                "WHERE storage_key = :key"
            ),
            {"key": key},
        ).one_or_none()


def _force_row_expiry(factory: sessionmaker[Session], key: str) -> None:
    with factory() as session:
        session.execute(
            text(
                "UPDATE storage_lock SET lease_expires_at = :past "
                "WHERE storage_key = :key"
            ),
            {"key": key, "past": utcnow().replace(year=2000)},
        )
        session.commit()


# --- LCK-01 / LCK-06：acquire、token、release ------------------------------


def test_lck01_pg_acquire_writes_token_row(factory, manager):
    owner = new_owner()
    lease = manager.acquire(KEY_A, owner, ttl_seconds=60)
    assert lease is not None
    assert lease.lease_token == 1
    row = _row(factory, KEY_A)
    assert row is not None
    assert row.owner == owner and row.lease_token == 1
    assert manager.verify(lease) is True
    assert manager.release(lease) is True
    row = _row(factory, KEY_A)
    assert row.owner == "" and row.lease_token == 1
    # 释放后 advisory 已 unlock，可再次取得且 token 单调。
    again = manager.acquire(KEY_A, owner, ttl_seconds=60)
    assert again is not None and again.lease_token == 2
    manager.release(again)


# --- LCK-02：两个真实连接互斥 ----------------------------------------------


def test_lck02_pg_two_connections_mutual_exclusion(factory, pg_engine):
    first = PostgresStorageKeyLock(pg_engine, wait_seconds=2.0, heartbeat_seconds=0)
    second = PostgresStorageKeyLock(pg_engine, wait_seconds=0.3, heartbeat_seconds=0)
    lease_a = first.acquire(KEY_A, "owner-a", ttl_seconds=60)
    assert lease_a is not None
    assert second.acquire(KEY_A, "owner-b", ttl_seconds=60) is None
    assert _row(factory, KEY_A).owner == "owner-a"
    first.release(lease_a)
    lease_b = second.acquire(KEY_A, "owner-b", ttl_seconds=60)
    assert lease_b is not None and lease_b.lease_token == 2
    second.release(lease_b)


# --- LCK-03 / LCK-07 / LCK-10：行 TTL 与 advisory 权威 -----------------------


def test_lck10_row_ttl_expiry_does_not_authorize_takeover(factory, pg_engine):
    holder = PostgresStorageKeyLock(pg_engine, wait_seconds=1.0, heartbeat_seconds=0)
    contender = PostgresStorageKeyLock(pg_engine, wait_seconds=0.3, heartbeat_seconds=0)
    guard = holder.acquire_many([KEY_A], "owner-a", heartbeat_seconds=0)
    assert guard is not None
    # 行 TTL 推到过去，但 holder 的专用连接与 advisory 仍存活。
    _force_row_expiry(factory, KEY_A)
    assert contender.acquire(KEY_A, "owner-b", ttl_seconds=60) is None
    assert _row(factory, KEY_A).owner == "owner-a"
    # 模拟进程死亡：关闭 holder 专用物理连接 → advisory 随会话释放。
    guard.pg_state.connection.close()
    lease_b = contender.acquire(KEY_A, "owner-b", ttl_seconds=60)
    assert lease_b is not None
    assert lease_b.lease_token == guard.leases[0].lease_token + 1
    contender.release(lease_b)
    guard.release()


def test_lck03_pg_takeover_after_disconnect(factory, pg_engine):
    first = PostgresStorageKeyLock(pg_engine, wait_seconds=1.0, heartbeat_seconds=0)
    second = PostgresStorageKeyLock(pg_engine, wait_seconds=1.0, heartbeat_seconds=0)
    lease_a = first.acquire(KEY_A, "owner-a", ttl_seconds=60)
    assert lease_a is not None
    assert second.acquire(KEY_A, "owner-b", ttl_seconds=60) is None
    assert first.release(lease_a) is True
    lease_b = second.acquire(KEY_A, "owner-b", ttl_seconds=60)
    assert lease_b is not None and lease_b.lease_token == lease_a.lease_token + 1
    assert second.verify(lease_b) is True
    second.release(lease_b)


def test_lck05_pg_old_guard_aborts_after_takeover(factory, pg_engine):
    holder = PostgresStorageKeyLock(pg_engine, wait_seconds=1.0, heartbeat_seconds=0)
    contender = PostgresStorageKeyLock(pg_engine, wait_seconds=1.0, heartbeat_seconds=0)
    guard = holder.acquire_many([KEY_A], "owner-a", heartbeat_seconds=0)
    assert guard is not None
    guard.pg_state.connection.close()  # 模拟崩溃
    lease_b = contender.acquire(KEY_A, "owner-b", ttl_seconds=60)
    assert lease_b is not None
    with pytest.raises(StorageLeaseLost):
        guard.verify_all()
    assert guard.aborted is True
    contender.release(lease_b)


def test_lck07_pg_client_process_death_releases_advisory_lock(factory, pg_engine, tmp_path):
    ready = tmp_path / "client-ready.json"
    child_code = """
import json
import os
import sys
import threading
from pathlib import Path

from app.db.session import create_engine_from_url
from app.db.storage_lock import PostgresStorageKeyLock

ready, key = Path(sys.argv[1]), sys.argv[2]
engine = create_engine_from_url(os.environ["EXPLAINLAB_PG_TEST_URL"])
manager = PostgresStorageKeyLock(engine, ttl_seconds=60, wait_seconds=5, heartbeat_seconds=0)
guard = manager.acquire_many([key], "terminated-client", heartbeat_seconds=0)
assert guard is not None
guard.verify_all()
receipt = ready.with_suffix(".tmp")
receipt.write_text(json.dumps({
    "backend_pid": guard.pg_state.driver_connection.info.backend_pid,
    "lease": guard.leases[0].model_dump(mode="json"),
}), encoding="utf-8")
receipt.replace(ready)
threading.Event().wait()
"""
    log = tmp_path / "child.log"
    with log.open("w", encoding="utf-8") as stream:
        child = subprocess.Popen(
            [sys.executable, "-u", "-c", child_code, str(ready), KEY_A],
            stdout=stream, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 15
            while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            assert ready.exists(), log.read_text(encoding="utf-8")
            receipt = json.loads(ready.read_text(encoding="utf-8"))
            backend_pid = receipt["backend_pid"]
            stale = StorageLease.model_validate(receipt["lease"])
            advisory = text("""
                SELECT count(*) FROM pg_locks
                WHERE pid=:pid AND locktype='advisory' AND objsubid=2
                  AND mode='ExclusiveLock' AND granted
                  AND classid::bigint=:class_id AND objid::bigint=:object_id
            """)
            lock_params = {
                "pid": backend_pid, "class_id": int(KEY_A[:8], 16),
                "object_id": int(KEY_A[8:16], 16),
            }
            contender = PostgresStorageKeyLock(pg_engine, wait_seconds=0.5, heartbeat_seconds=0)
            with pg_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as observer:
                assert observer.execute(advisory, lock_params).scalar_one() == 1
                assert contender.acquire(KEY_A, "replacement", ttl_seconds=60) is None
                assert child.poll() is None
                print(f"client pid={child.pid}; PG pid={backend_pid}; advisory lock confirmed")
                child.kill()
                assert child.wait(timeout=10) != 0
                deadline = time.monotonic() + 10
                activity = text("SELECT count(*) FROM pg_stat_activity WHERE pid=:pid")
                while observer.execute(activity, {"pid": backend_pid}).scalar_one():
                    assert time.monotonic() < deadline, "terminated client's PG backend persisted"
                    time.sleep(0.05)
                assert observer.execute(advisory, lock_params).scalar_one() == 0
            replacement = contender.acquire(KEY_A, "replacement", ttl_seconds=60)
            assert replacement is not None
            try:
                assert replacement.lease_token == stale.lease_token + 1
                assert not contender.verify(stale)
                assert not contender.release(stale)
                assert contender.verify(replacement)
                row = _row(factory, KEY_A)
                assert (row.owner, row.lease_token) == ("replacement", replacement.lease_token)
                print(f"client exit={child.returncode}; old PG pid closed; "
                      f"token {stale.lease_token} -> {replacement.lease_token}")
            finally:
                assert contender.release(replacement)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)


# --- 相同 advisory 投影与批顺序 --------------------------------------------


def test_lck10_same_projection_keys_serialize(factory, pg_engine):
    first = PostgresStorageKeyLock(pg_engine, wait_seconds=1.0, heartbeat_seconds=0)
    second = PostgresStorageKeyLock(pg_engine, wait_seconds=0.3, heartbeat_seconds=0)
    guard = first.acquire_many([KEY_PROJ_1], "owner-a", heartbeat_seconds=0)
    assert guard is not None
    # 不同完整 key、相同 advisory 投影：只能等待，不能并发通过。
    assert second.acquire(KEY_PROJ_2, "owner-b", ttl_seconds=60) is None
    assert guard.release() is True
    other = second.acquire(KEY_PROJ_2, "owner-b", ttl_seconds=60)
    assert other is not None
    # 两个 key 独立 token 行（不是同一条记录）。
    assert _row(factory, KEY_PROJ_1).lease_token == 1
    assert _row(factory, KEY_PROJ_2).lease_token == 1
    second.release(other)


def test_lck10_batch_disjoint_keys_do_not_self_block(factory, pg_engine):
    manager = PostgresStorageKeyLock(pg_engine, wait_seconds=2.0, heartbeat_seconds=0)
    guard = manager.acquire_many(
        [KEY_A, KEY_B], "owner-batch", heartbeat_seconds=0
    )
    assert guard is not None
    assert guard.keys == (KEY_A, KEY_B)
    # 同一 manager 再取已持有 key → 非重入拒绝；不同 key 可另批取得。
    assert manager.acquire_many([KEY_A], "owner-batch", heartbeat_seconds=0) is None
    other = manager.acquire_many([KEY_C], "owner-other", heartbeat_seconds=0)
    assert other is not None
    other.release()
    guard.release()


def test_lck10_reverse_order_no_deadlock(factory, pg_engine):
    first = PostgresStorageKeyLock(pg_engine, wait_seconds=3.0, heartbeat_seconds=0)
    second = PostgresStorageKeyLock(pg_engine, wait_seconds=3.0, heartbeat_seconds=0)
    results: list[object] = []
    barrier = threading.Barrier(2)

    def worker(manager: PostgresStorageKeyLock, owner: str, keys: list[str]) -> None:
        barrier.wait()
        results.append(manager.acquire_many(keys, owner, heartbeat_seconds=0))

    threads = [
        threading.Thread(target=worker, args=(first, "one", [KEY_A, KEY_B])),
        threading.Thread(target=worker, args=(second, "two", [KEY_B, KEY_A])),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    assert all(not thread.is_alive() for thread in threads)
    # 排序后同一顺序获取：两个都能成功（第二个等待第一个释放）或串行退出；
    # 关键断言是无死锁且退出码干净，随后释放。
    for guard in results:
        if guard is not None:
            guard.release()


# --- 心跳 / verify / 清理 ---------------------------------------------------


def test_lck04_pg_renew_extends_row(factory, manager):
    guard = manager.acquire_many(
        [KEY_A], "owner-a", ttl_seconds=30, heartbeat_seconds=0.1
    )
    assert guard is not None
    before = _row(factory, KEY_A).lease_expires_at
    time.sleep(0.35)
    after = _row(factory, KEY_A).lease_expires_at
    assert after > before
    assert manager.verify(guard.leases[0]) is True
    guard.release()


def test_lck06_pg_release_mismatch_does_not_release_other(factory, pg_engine):
    first = PostgresStorageKeyLock(pg_engine, wait_seconds=1.0, heartbeat_seconds=0)
    second = PostgresStorageKeyLock(pg_engine, wait_seconds=1.0, heartbeat_seconds=0)
    lease_a = first.acquire(KEY_A, "owner-a", ttl_seconds=60)
    assert lease_a is not None
    # 构造同行不同 token 的旧 lease：释放必须失败且不改变当前 owner。
    stale = lease_a.model_copy(update={"lease_token": lease_a.lease_token - 1})
    assert second.release(stale) is False
    assert _row(factory, KEY_A).owner == "owner-a"
    assert first.release(lease_a) is True


def test_lck06_pg_guard_release_idempotent(manager):
    guard = manager.acquire_many([KEY_A], "owner-a", heartbeat_seconds=0)
    assert guard is not None
    assert guard.release() is True
    assert guard.release() is True

def test_pg_real_token_upsert_respects_budget_and_closes_connection(factory, pg_engine):
    from sqlalchemy import update

    from app.db.storage_lock import PostgresLockFailure

    holder = PostgresStorageKeyLock(pg_engine, wait_seconds=2, heartbeat_seconds=0)
    initial = holder.acquire_many([KEY_A], "initial", heartbeat_seconds=0)
    assert initial is not None and initial.release()
    with factory() as blocker:
        blocker.execute(
            update(StorageLockORM)
            .where(StorageLockORM.storage_key == KEY_A)
            .values(owner="row-blocker")
        )
        start = time.monotonic()
        with pytest.raises(PostgresLockFailure) as error:
            holder.acquire_many([KEY_A], "budget-owner", wait_seconds=0.25, heartbeat_seconds=0)
        assert error.value.phase == "token UPSERT"
        assert error.value.reason in {"deadline", "SQL deadline"}
        assert time.monotonic() - start < 0.8
        blocker.rollback()
    reacquired = holder.acquire_many([KEY_A], "budget-owner", heartbeat_seconds=0)
    assert reacquired is not None
    assert reacquired.release()


def test_pg_real_final_verify_row_lock_budget(factory, pg_engine):
    from sqlalchemy import update

    from app.db.storage_lock import PostgresLockFailure

    manager = PostgresStorageKeyLock(pg_engine, wait_seconds=0.5, heartbeat_seconds=0)
    guard = manager.acquire_many([KEY_A], "final-fence", heartbeat_seconds=0)
    assert guard is not None
    with factory() as blocker, factory() as business:
        blocker.execute(
            update(StorageLockORM)
            .where(StorageLockORM.storage_key == KEY_A)
            .values(owner="uncommitted")
        )
        with pytest.raises(PostgresLockFailure) as error:
            guard.verify_all(business)
        assert error.value.phase == "verify"
        assert error.value.reason == "SQL deadline"
        assert guard.aborted
        business.rollback()
        blocker.rollback()
    assert guard.release()
