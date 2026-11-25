"""附件/GC 任务仓储真实 SQLite 测试（V2 A1-04 Batch B，B1-T04）。

覆盖 AttachmentRepository 七个方法与 GcTaskRepository 的保存/读取/条件认领/
fencing 更新；全部使用真实 SQLite 文件库，验证“仓储只 flush、不 commit”，
以及 token 失配、终态保护、隔离等待（next_retry_at）与预算耗尽不可认领。
"""

from __future__ import annotations

import threading
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401  ORM 元数据
from app.db.base import Base
from app.db.session import create_engine_from_url
from app.models import AttachmentORM, GcTaskORM, KnowledgeItemORM
from app.services.repositories_v2 import (
    SQLAlchemyAttachmentRepository,
    SQLAlchemyGcTaskRepository,
)
from knowledge_core.domain.entities import Attachment, GcStatus, GcTask, utcnow

KEY = "a1" * 32
KEY_B = "b2" * 32


@pytest.fixture
def factory(tmp_path: Path):
    engine = create_engine_from_url(f"sqlite:///{tmp_path / 'repo.db'}")
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        yield maker
    finally:
        engine.dispose()


@pytest.fixture
def db(factory: sessionmaker[Session]):
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _item(session: Session, title: str = "item") -> str:
    row = KnowledgeItemORM(id=str(uuid4()), title=title, content="body", status="active")
    session.add(row)
    session.flush()
    return row.id


def _attachment(item_id: str, **overrides) -> Attachment:
    values = {
        "item_id": item_id,
        "filename": "a.png",
        "mime": "image/png",
        "size": 3,
        "storage_key": KEY,
        "content_hash": KEY,
    }
    values.update(overrides)
    return Attachment(**values)


def _task(storage_key: str = KEY, **overrides) -> GcTask:
    values = {"storage_key": storage_key}
    values.update(overrides)
    return GcTask(**values)


# --- 附件：CRUD / 派生引用 / 稳定顺序 --------------------------------------


def test_attachment_save_get_roundtrip(factory, db):
    item_id = _item(db)
    repo = SQLAlchemyAttachmentRepository(db)
    attachment = repo.save_attachment(_attachment(item_id))
    assert repo.get_attachment(attachment.id) == attachment
    assert repo.get_attachment(uuid4()) is None
    # 只 flush：未提交时另开 session 不可见。
    with factory() as other:
        assert other.scalar(select(func.count()).select_from(AttachmentORM)) == 0
    db.commit()
    with factory() as other:
        assert other.scalar(select(func.count()).select_from(AttachmentORM)) == 1


def test_attachment_list_order_and_isolation(db):
    item_a = _item(db, "a")
    item_b = _item(db, "b")
    repo = SQLAlchemyAttachmentRepository(db)
    base = utcnow()
    first = repo.save_attachment(
        _attachment(item_a, filename="1.txt", created_at=base)
    )
    second = repo.save_attachment(
        _attachment(item_a, filename="2.txt", created_at=base + timedelta(seconds=1))
    )
    repo.save_attachment(_attachment(item_b, filename="3.txt"))
    listed = repo.list_attachments(item_a)
    assert [row.id for row in listed] == [first.id, second.id]
    assert all(row.item_id == first.item_id for row in listed)


def test_attachment_shared_storage_key_count_and_keys(db):
    item_a = _item(db, "a")
    item_b = _item(db, "b")
    repo = SQLAlchemyAttachmentRepository(db)
    repo.save_attachment(_attachment(item_a))
    repo.save_attachment(_attachment(item_b, filename="copy.png"))
    repo.save_attachment(_attachment(item_b, filename="other.png", storage_key=KEY_B, content_hash=KEY_B))
    assert repo.count_references(KEY) == 2
    assert repo.count_references(KEY_B) == 1
    assert repo.count_references("c" * 64) == 0
    assert repo.list_storage_keys() == [KEY, KEY_B]
    assert len(repo.find_by_hash(KEY)) == 2
    assert repo.find_by_hash("c" * 64) == []


def test_attachment_delete_only_row(db):
    item_id = _item(db)
    repo = SQLAlchemyAttachmentRepository(db)
    attachment = repo.save_attachment(_attachment(item_id))
    assert repo.delete_attachment(attachment.id) is True
    assert repo.get_attachment(attachment.id) is None
    assert repo.count_references(KEY) == 0
    assert repo.delete_attachment(attachment.id) is False


def test_attachment_save_foreign_key_failure_rolls_back(factory, db):
    repo = SQLAlchemyAttachmentRepository(db)
    orphan = _attachment(str(uuid4()))
    with pytest.raises(IntegrityError):
        repo.save_attachment(orphan)
    db.rollback()
    assert repo.count_references(KEY) == 0


def test_attachment_item_cascade_removes_rows(db):
    item_id = _item(db)
    repo = SQLAlchemyAttachmentRepository(db)
    repo.save_attachment(_attachment(item_id))
    db.delete(db.get(KnowledgeItemORM, item_id))
    db.flush()
    assert repo.count_references(KEY) == 0


# --- GC 任务：保存 / 读取 / 过滤 ------------------------------------------


def test_gc_save_get_defaults_and_list_filters(db):
    repo = SQLAlchemyGcTaskRepository(db)
    task = repo.save_task(_task())
    loaded = repo.get_task(task.id)
    assert loaded is not None
    assert loaded.status is GcStatus.PENDING
    assert loaded.lease_token == 0 and loaded.attempts == 0
    assert loaded.lease_owner is None and loaded.next_retry_at is None
    other = repo.save_task(_task(KEY_B))
    db.commit()
    assert [row.id for row in repo.list_tasks()] == [task.id, other.id]
    assert [row.id for row in repo.list_tasks(status=GcStatus.PENDING)] == [
        task.id,
        other.id,
    ]
    assert [row.id for row in repo.list_tasks(storage_key=KEY_B)] == [other.id]
    assert repo.list_tasks(status=GcStatus.DONE) == []
    assert repo.get_task(uuid4()) is None


# --- GC 任务：条件认领 ------------------------------------------------------


def test_gc_claim_pending_and_second_claim_blocked(factory, db):
    repo = SQLAlchemyGcTaskRepository(db)
    task = repo.save_task(_task())
    db.commit()
    claimed = repo.claim(task.id, owner="worker-1", lease_ttl_seconds=60)
    assert claimed is not None
    assert claimed.status is GcStatus.RUNNING
    assert claimed.lease_owner == "worker-1"
    assert claimed.lease_token == 1 and claimed.attempts == 1
    assert claimed.lease_expires_at is not None
    db.commit()
    assert repo.claim(task.id, owner="worker-2", lease_ttl_seconds=60) is None
    row = db.get(GcTaskORM, str(task.id))
    assert row.lease_owner == "worker-1" and row.lease_token == 1


def test_gc_claim_expired_running_increments_token_and_attempts(factory, db):
    repo = SQLAlchemyGcTaskRepository(db)
    task = repo.save_task(_task())
    db.commit()
    now = utcnow()
    first = repo.claim(task.id, owner="worker-1", lease_ttl_seconds=60, now=now)
    assert first is not None
    db.commit()
    # 未到期不可接管。
    assert (
        repo.claim(
            task.id,
            owner="worker-2",
            lease_ttl_seconds=60,
            now=now + timedelta(seconds=5),
        )
        is None
    )
    # 到期后接管：token/attempts 均 +1。
    second = repo.claim(
        task.id,
        owner="worker-2",
        lease_ttl_seconds=60,
        now=now + timedelta(seconds=90),
    )
    assert second is not None
    assert second.lease_token == 2 and second.attempts == 2
    assert second.lease_owner == "worker-2"


def test_gc_claim_respects_quarantine_wait(factory, db):
    repo = SQLAlchemyGcTaskRepository(db)
    task = repo.save_task(_task())
    db.commit()
    now = utcnow()
    assert repo.claim(task.id, owner="worker-1", lease_ttl_seconds=1, now=now) is not None
    db.commit()
    # 隔离后：保持 running、租约过期、next_retry_at = now + 24h。
    row = db.get(GcTaskORM, str(task.id))
    row.lease_expires_at = now - timedelta(seconds=5)
    row.next_retry_at = now + timedelta(hours=24)
    db.commit()
    assert repo.claim(task.id, owner="worker-2", lease_ttl_seconds=60, now=now) is None
    later = repo.claim(
        task.id,
        owner="worker-2",
        lease_ttl_seconds=60,
        now=now + timedelta(hours=25),
    )
    assert later is not None and later.lease_token == 2


def test_gc_claim_rejects_terminal_and_exhausted(factory, db):
    repo = SQLAlchemyGcTaskRepository(db, max_attempts=8)
    done = repo.save_task(_task(storage_key=KEY_B, status=GcStatus.DONE))
    cancelled = repo.save_task(
        _task(storage_key="c" * 64, status=GcStatus.CANCELLED)
    )
    manual = repo.save_task(
        _task(storage_key="d" * 64, status=GcStatus.NEEDS_MANUAL)
    )
    exhausted = repo.save_task(
        _task(storage_key="e" * 64, status=GcStatus.PENDING, attempts=8)
    )
    db.commit()
    for task in (done, cancelled, manual, exhausted):
        assert repo.claim(task.id, owner="worker", lease_ttl_seconds=60) is None


# --- GC 任务：fencing 更新 ---------------------------------------------------


def test_gc_update_fencing_and_no_attempt_mutation(factory, db):
    repo = SQLAlchemyGcTaskRepository(db)
    task = repo.save_task(_task())
    db.commit()
    claimed = repo.claim(task.id, owner="worker-1", lease_ttl_seconds=60)
    assert claimed is not None
    db.commit()
    token = claimed.lease_token
    claimed.status = GcStatus.FAILED_RETRYABLE
    claimed.next_retry_at = utcnow() + timedelta(seconds=60)
    updated = repo.update_task(claimed, expected_lease_token=token)
    assert updated is not None
    assert updated.status is GcStatus.FAILED_RETRYABLE
    assert updated.attempts == 1  # update 不改变 attempts
    assert updated.lease_token == token
    db.commit()
    # 旧 token 再更新：拒绝且不覆盖。
    claimed.status = GcStatus.DONE
    assert repo.update_task(claimed, expected_lease_token=token - 1) is None
    row = db.get(GcTaskORM, str(task.id))
    assert row.status == GcStatus.FAILED_RETRYABLE.value
    final = repo.update_task(claimed, expected_lease_token=token)
    assert final is None
    assert repo.get_task(task.id).status is GcStatus.FAILED_RETRYABLE


def test_gc_update_terminal_not_overwritable(factory, db):
    repo = SQLAlchemyGcTaskRepository(db)
    task = repo.save_task(_task())
    db.commit()
    claimed = repo.claim(task.id, owner="worker-1", lease_ttl_seconds=60)
    assert claimed is not None
    db.commit()
    token = claimed.lease_token
    claimed.status = GcStatus.CANCELLED
    assert repo.update_task(claimed, expected_lease_token=token) is not None
    db.commit()
    claimed.status = GcStatus.RUNNING
    assert repo.update_task(claimed, expected_lease_token=token) is None
    row = db.get(GcTaskORM, str(task.id))
    assert row.status == GcStatus.CANCELLED.value


def test_gc_claim_concurrent_sqlite_only_one_wins(factory, db):
    repo = SQLAlchemyGcTaskRepository(db)
    task = repo.save_task(_task())
    db.commit()
    db.close()

    barrier = threading.Barrier(2)
    results: list[object] = []
    results_lock = threading.Lock()

    def worker(owner: str) -> None:
        with factory() as session:
            repo_local = SQLAlchemyGcTaskRepository(session)
            barrier.wait()
            claimed = repo_local.claim(task.id, owner=owner, lease_ttl_seconds=60)
            session.commit()
            with results_lock:
                results.append(claimed)

    threads = [
        threading.Thread(target=worker, args=("worker-1",)),
        threading.Thread(target=worker, args=("worker-2",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    assert all(not thread.is_alive() for thread in threads)
    winners = [item for item in results if item is not None]
    assert len(winners) == 1
    with factory() as session:
        row = session.get(GcTaskORM, str(task.id))
        assert row.lease_token == 1 and row.attempts == 1
        assert row.lease_owner == winners[0].lease_owner


def test_gc_claim_flush_only_visible_after_commit(factory, db):
    repo = SQLAlchemyGcTaskRepository(db)
    task = repo.save_task(_task())
    db.commit()
    claimed = repo.claim(task.id, owner="worker-1", lease_ttl_seconds=60)
    assert claimed is not None
    with factory() as other:
        row = other.get(GcTaskORM, str(task.id))
        other.refresh(row)
        assert row.status == GcStatus.PENDING.value  # 尚未 commit
    db.commit()
    with factory() as other:
        row = other.get(GcTaskORM, str(task.id))
        assert row.status == GcStatus.RUNNING.value
        assert row.lease_token == 1


def test_gc_claim_flush_failure_rolls_back(factory, db):
    repo = SQLAlchemyGcTaskRepository(db)
    task = repo.save_task(_task())
    db.commit()

    def boom() -> None:
        raise RuntimeError("flush failed")

    db.flush = boom  # type: ignore[method-assign]  - 模拟外层 flush 失败
    with pytest.raises(RuntimeError):
        repo.claim(task.id, owner="worker-1", lease_ttl_seconds=60)
    db.rollback()
    with factory() as other:
        row = other.get(GcTaskORM, str(task.id))
        assert row.status == GcStatus.PENDING.value
        assert row.lease_token == 0 and row.attempts == 0
        assert row.lease_owner is None

def test_gc_worker_rejects_stale_owner_and_token(db):
    repo = SQLAlchemyGcTaskRepository(db)
    task = repo.save_task(_task())
    claimed = repo.claim(task.id, owner="worker-1", lease_ttl_seconds=60)
    db.commit()
    claimed.status = GcStatus.DONE
    assert repo.update_task(claimed, expected_lease_token=2) is None
    claimed.lease_owner = "wrong-owner"
    assert repo.update_task(claimed, expected_lease_token=1) is None
    assert repo.get_task(task.id).status is GcStatus.RUNNING
    claimed.lease_owner = "worker-1"
    assert repo.update_task(claimed, expected_lease_token=1).status is GcStatus.DONE


def test_gc_expired_lease_cannot_update_or_renew(db):
    repo = SQLAlchemyGcTaskRepository(db)
    task = repo.save_task(_task())
    claimed = repo.claim(
        task.id, owner="expired-worker", lease_ttl_seconds=1,
        now=utcnow() - timedelta(seconds=5),
    )
    db.commit()
    claimed.status = GcStatus.DONE
    assert repo.update_task(claimed, expected_lease_token=claimed.lease_token) is None
    assert repo.renew_task(
        task.id, owner=claimed.lease_owner, lease_token=claimed.lease_token, lease_ttl_seconds=60,
    ) is None
    assert repo.get_task(task.id).status is GcStatus.RUNNING


def test_gc_scheduler_cannot_requeue_early_and_due_retry_is_reclaimable(db):
    repo = SQLAlchemyGcTaskRepository(db)
    task = repo.save_task(_task())
    claimed = repo.claim(task.id, owner="worker-1", lease_ttl_seconds=60)
    claimed.status = GcStatus.FAILED_RETRYABLE
    claimed.next_retry_at = utcnow() + timedelta(seconds=60)
    assert repo.update_task(claimed, expected_lease_token=1).status is GcStatus.FAILED_RETRYABLE
    db.commit()
    assert repo.requeue_due(task.id, expected_lease_token=1) is None
    assert repo.claim(task.id, owner="worker-2", lease_ttl_seconds=60) is None
    row = db.get(GcTaskORM, str(task.id))
    row.next_retry_at = utcnow() - timedelta(seconds=1)
    db.flush()
    assert repo.requeue_due(task.id, expected_lease_token=0) is None
    assert repo.requeue_due(task.id, expected_lease_token=1).status is GcStatus.PENDING
    next_claim = repo.claim(task.id, owner="worker-2", lease_ttl_seconds=60)
    assert (next_claim.lease_token, next_claim.attempts) == (2, 2)


def test_gc_operator_recovers_permanent_failure_only_through_manual(db):
    repo = SQLAlchemyGcTaskRepository(db)
    task = repo.save_task(_task(status=GcStatus.FAILED_PERMANENT, attempts=8))
    db.commit()
    assert repo.operator_transition(
        task.id, source=GcStatus.FAILED_PERMANENT, target=GcStatus.PENDING, expected_lease_token=0,
    ) is None
    assert repo.operator_transition(
        task.id, source=GcStatus.FAILED_PERMANENT, target=GcStatus.NEEDS_MANUAL,
        expected_lease_token=0,
    ).status is GcStatus.NEEDS_MANUAL
    restarted = repo.operator_transition(
        task.id, source=GcStatus.NEEDS_MANUAL, target=GcStatus.PENDING, expected_lease_token=0,
    )
    assert (restarted.status, restarted.attempts, restarted.lease_token) == (GcStatus.PENDING, 0, 0)


def test_gc_retry_and_running_wait_conditions(db):
    repo = SQLAlchemyGcTaskRepository(db, max_attempts=1)
    task = repo.save_task(_task())
    claimed = repo.claim(task.id, owner="worker", lease_ttl_seconds=60)
    db.commit()
    claimed.status = GcStatus.PENDING
    assert repo.update_task(claimed, expected_lease_token=1) is None
    claimed.status = GcStatus.FAILED_RETRYABLE
    claimed.next_retry_at = utcnow() + timedelta(seconds=60)
    assert repo.update_task(claimed, expected_lease_token=1) is None
    claimed.status = GcStatus.RUNNING
    claimed.quarantine_path = f"{task.storage_key}.{task.id}"
    claimed.quarantined_at = utcnow()
    assert repo.update_task(claimed, expected_lease_token=1) is None
    claimed.next_retry_at = claimed.quarantined_at + timedelta(days=1)
    waiting = repo.update_task(claimed, expected_lease_token=1)
    assert waiting.status is GcStatus.RUNNING
    assert waiting.lease_expires_at <= utcnow()
    assert repo.fail_unretryable(task.id, expected_lease_token=1) is None
    assert repo.claim(task.id, owner="early-takeover", lease_ttl_seconds=60) is None


def test_gc_concurrent_worker_terminal_updates_have_one_winner(factory, db):
    from concurrent.futures import ThreadPoolExecutor

    repo = SQLAlchemyGcTaskRepository(db)
    task = repo.save_task(_task())
    claimed = repo.claim(task.id, owner="same-worker", lease_ttl_seconds=60)
    db.commit()
    barrier = threading.Barrier(2)

    def finish(status):
        with factory.begin() as session:
            barrier.wait(timeout=3)
            return SQLAlchemyGcTaskRepository(session).update_task(
                claimed.model_copy(update={"status": status}), expected_lease_token=claimed.lease_token,
            )

    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(finish, (GcStatus.DONE, GcStatus.CANCELLED)))
    winner, = [outcome for outcome in outcomes if outcome is not None]
    db.expire_all()
    assert repo.get_task(task.id).status is winner.status



def test_gc_lease_expired_while_waiting_for_sqlite_writer(factory, db):
    import time
    from concurrent.futures import ThreadPoolExecutor

    from app.db.session import run_short_write

    repo = SQLAlchemyGcTaskRepository(db)
    task = repo.save_task(_task())
    claimed = repo.claim(task.id, owner="worker", lease_ttl_seconds=0.10)
    db.commit()
    claimed.status = GcStatus.DONE

    def finish():
        return run_short_write(
            factory, lambda session: SQLAlchemyGcTaskRepository(session).update_task(
                claimed, expected_lease_token=claimed.lease_token,
            ),
            is_sqlite=True, deadline=time.monotonic() + 1,
        )

    with ThreadPoolExecutor(1) as pool, factory.kw["bind"].connect() as blocker:
        blocker.exec_driver_sql("BEGIN IMMEDIATE")
        pending = pool.submit(finish)
        time.sleep(0.17)
        blocker.rollback()
        assert pending.result(timeout=2) is None
    assert repo.get_task(task.id).status is GcStatus.RUNNING
