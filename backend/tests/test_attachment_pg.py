"""附件/GC 任务仓储真实 PostgreSQL 测试（V2 A1-04 Batch B，B1-T04）。

经 ``EXPLAINLAB_PG_TEST_URL`` 门控；未配置时整模块跳过。配置后连真实 PG，
经真实在线 Alembic 迁移，验证附件引用 COUNT、删除、GC 条件认领的真实并发
（两个独立 session + 行锁）与 token fencing。不得以 SQLite 结果替代。
"""

from __future__ import annotations

import os
import threading
import time
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.core.config import get_settings
from app.db.session import create_engine_from_url
from app.models import KnowledgeItemORM
from app.services.repositories_v2 import (
    SQLAlchemyAttachmentRepository,
    SQLAlchemyGcTaskRepository,
)
from knowledge_core.domain.entities import Attachment, GcStatus, GcTask, utcnow

BACKEND_DIR = Path(__file__).resolve().parents[1]
PG_URL = os.environ.get("EXPLAINLAB_PG_TEST_URL")

pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason="未配置 EXPLAINLAB_PG_TEST_URL（真实 PostgreSQL 实例），跳过附件/GC 仓储 PG 测试",
)

KEY = "f1" * 32


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
    maker = sessionmaker(bind=pg_engine, autoflush=False, expire_on_commit=False)
    with maker() as session:
        session.execute(text("DELETE FROM gc_task"))
        session.execute(text("DELETE FROM attachment"))
        session.execute(text("DELETE FROM knowledge_item"))
        session.commit()
    yield maker
    with maker() as session:
        session.execute(text("DELETE FROM gc_task"))
        session.execute(text("DELETE FROM attachment"))
        session.execute(text("DELETE FROM knowledge_item"))
        session.commit()


def _item(session: Session, title: str = "pg-item") -> str:
    row = KnowledgeItemORM(id=str(uuid4()), title=title, content="body", status="active")
    session.add(row)
    session.commit()
    return row.id


def _attachment(item_id: str, **overrides) -> Attachment:
    values = {
        "item_id": item_id,
        "filename": "a.pdf",
        "mime": "application/pdf",
        "size": 5,
        "storage_key": KEY,
        "content_hash": KEY,
    }
    values.update(overrides)
    return Attachment(**values)


def test_pg_attachment_shared_count_and_delete(factory):
    with factory() as session:
        item_a = _item(session, "a")
        item_b = _item(session, "b")
        repo = SQLAlchemyAttachmentRepository(session)
        first = repo.save_attachment(_attachment(item_a))
        repo.save_attachment(_attachment(item_b, filename="b.pdf"))
        session.commit()
        assert repo.count_references(KEY) == 2
        assert repo.list_storage_keys() == [KEY]
        assert len(repo.find_by_hash(KEY)) == 2
        assert repo.list_attachments(first.item_id) == [first]
        assert repo.delete_attachment(first.id) is True
        session.commit()
        assert repo.count_references(KEY) == 1
        assert repo.delete_attachment(first.id) is False


def test_pg_attachment_flushed_insert_is_rolled_back_by_owner(factory):
    with factory() as writer, factory() as observer:
        item_id = _item(writer)
        repo = SQLAlchemyAttachmentRepository(writer)
        saved = repo.save_attachment(_attachment(item_id))
        assert repo.get_attachment(saved.id) == saved
        assert SQLAlchemyAttachmentRepository(observer).get_attachment(saved.id) is None
        writer.rollback()
    with factory() as reader:
        assert SQLAlchemyAttachmentRepository(reader).get_attachment(saved.id) is None


def test_pg_attachment_foreign_key_rejection_rolls_back_transaction(factory):
    invalid = _attachment(str(uuid4()))
    with factory() as writer:
        item_id = _item(writer)
        repo = SQLAlchemyAttachmentRepository(writer)
        valid = repo.save_attachment(_attachment(item_id))
        with pytest.raises(IntegrityError) as error:
            repo.save_attachment(invalid)
        assert error.value.orig.sqlstate == "23503"
        assert not writer.is_active
        writer.rollback()
        assert writer.is_active
    with factory() as reader:
        repo = SQLAlchemyAttachmentRepository(reader)
        assert repo.get_attachment(invalid.id) is None
        assert repo.get_attachment(valid.id) is None


def test_pg_gc_claim_pending_and_expired_running_increments_token_and_attempts(factory):
    now = utcnow()
    with factory() as session:
        repo = SQLAlchemyGcTaskRepository(session)
        task = repo.save_task(GcTask(storage_key=KEY))
        session.commit()
        first = repo.claim(task.id, owner="first", lease_ttl_seconds=10, now=now)
        assert first is not None
        assert (first.lease_token, first.attempts, first.lease_owner) == (1, 1, "first")
        session.commit()
    with factory() as session:
        repo = SQLAlchemyGcTaskRepository(session)
        assert repo.claim(task.id, owner="second", lease_ttl_seconds=10, now=now) is None
        assert repo.get_task(task.id) == first
        second = repo.claim(
            task.id, owner="second", lease_ttl_seconds=10, now=now + timedelta(seconds=11)
        )
        assert second is not None and second.status is GcStatus.RUNNING
        assert (second.lease_token, second.attempts, second.lease_owner) == (2, 2, "second")
        session.commit()
    with factory() as session:
        assert SQLAlchemyGcTaskRepository(session).get_task(task.id) == second


@pytest.mark.parametrize("status", [
    GcStatus.PENDING, GcStatus.RUNNING, GcStatus.DONE, GcStatus.CANCELLED,
    GcStatus.FAILED_PERMANENT, GcStatus.NEEDS_MANUAL,
])
def test_pg_gc_claim_rejects_exhausted_attempts_or_terminal_state(factory, status):
    now = utcnow()
    attempts = 8 if status in {GcStatus.PENDING, GcStatus.RUNNING} else 1
    with factory() as session:
        repo = SQLAlchemyGcTaskRepository(session)
        task = repo.save_task(GcTask(
            storage_key=KEY, status=status, attempts=attempts, lease_token=3,
            lease_owner="prior" if status is GcStatus.RUNNING else None,
            lease_expires_at=now - timedelta(seconds=1) if status is GcStatus.RUNNING else None,
        ))
        session.commit()
        assert repo.claim(task.id, owner="next", lease_ttl_seconds=60, now=now) is None
        assert repo.get_task(task.id) == task


def test_pg_gc_claim_concurrent_two_sessions(factory):
    with factory() as session:
        repo = SQLAlchemyGcTaskRepository(session)
        task = repo.save_task(GcTask(storage_key=KEY))
        session.commit()

    ready = threading.Event()
    results: dict[str, object] = {}

    def first_worker() -> None:
        with factory() as session:
            repo = SQLAlchemyGcTaskRepository(session)
            results["first"] = repo.claim(
                task.id, owner="worker-1", lease_ttl_seconds=60
            )
            ready.set()
            time.sleep(0.3)  # 持有行锁，给第二 session 进入条件更新
            session.commit()

    def second_worker() -> None:
        ready.wait(timeout=5)
        with factory() as session:
            repo = SQLAlchemyGcTaskRepository(session)
            results["second"] = repo.claim(
                task.id, owner="worker-2", lease_ttl_seconds=60
            )
            session.commit()

    threads = [
        threading.Thread(target=first_worker),
        threading.Thread(target=second_worker),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    assert all(not thread.is_alive() for thread in threads)

    first = results["first"]
    second = results["second"]
    assert first is not None and first.lease_token == 1
    assert second is None  # 第二 session 在行锁释放后重估条件：running 未过期
    with factory() as session:
        repo = SQLAlchemyGcTaskRepository(session)
        stored = repo.get_task(task.id)
        assert stored is not None
        assert stored.status is GcStatus.RUNNING
        assert stored.lease_token == 1 and stored.attempts == 1
        assert stored.lease_owner == "worker-1"


def test_pg_gc_fencing_update_and_terminal_guard(factory):
    with factory() as session:
        repo = SQLAlchemyGcTaskRepository(session)
        task = repo.save_task(GcTask(storage_key=KEY))
        session.commit()
        claimed = repo.claim(task.id, owner="worker-1", lease_ttl_seconds=60)
        assert claimed is not None
        session.commit()
        token = claimed.lease_token
        original_attempts = claimed.attempts
        claimed.attempts = original_attempts + 1
        claimed.status = GcStatus.FAILED_RETRYABLE
        claimed.next_retry_at = utcnow() + timedelta(seconds=60)
        updated = repo.update_task(claimed, expected_lease_token=token)
        assert updated is not None and updated.status is GcStatus.FAILED_RETRYABLE
        assert updated.attempts == original_attempts
        session.commit()
        claimed.status = GcStatus.DONE
        assert repo.update_task(claimed, expected_lease_token=token - 1) is None
        final = repo.update_task(claimed, expected_lease_token=token)
        assert final is None
        session.commit()
        claimed.status = GcStatus.RUNNING
        assert repo.update_task(claimed, expected_lease_token=token) is None
        stored = repo.get_task(task.id)
        assert stored is not None and stored.status is GcStatus.FAILED_RETRYABLE
        assert stored.attempts == original_attempts


def test_pg_gc_claim_respects_quarantine_wait(factory):
    with factory() as session:
        repo = SQLAlchemyGcTaskRepository(session)
        task = repo.save_task(GcTask(storage_key=KEY))
        session.commit()
        now = utcnow()
        first = repo.claim(task.id, owner="worker-1", lease_ttl_seconds=1, now=now)
        assert first is not None
        session.commit()
        session.execute(
            text(
                "UPDATE gc_task SET lease_expires_at = :past, next_retry_at = :future "
                "WHERE id = :id"
            ),
            {
                "past": now - timedelta(seconds=5),
                "future": now + timedelta(hours=24),
                "id": str(task.id),
            },
        )
        session.commit()
        assert repo.claim(task.id, owner="worker-2", lease_ttl_seconds=60, now=now) is None
        waiting = repo.get_task(task.id)
        assert waiting is not None and waiting.status is GcStatus.RUNNING
        assert (waiting.lease_token, waiting.attempts, waiting.lease_owner) == (1, 1, "worker-1")
