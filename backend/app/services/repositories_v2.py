"""V2 端口仓储的 SQLAlchemy 实现（标签 / 标签审计 / 导入来源 / 附件 / GC 任务）。

严格实现 ``knowledge_core.ports`` 协议；只 ``flush`` 不 ``commit``，
事务边界由调用方（导入协调器 / 审核钩子 / GC 协调器）统一控制。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AttachmentORM,
    GcTaskORM,
    ImportOriginORM,
    ItemTagORM,
    TagChangeLogORM,
    TagORM,
)
from knowledge_core.domain.entities import (
    Attachment,
    GcStatus,
    GcTask,
    ImportOrigin,
    TagChangeRecord,
    utcnow,
)

__all__ = [
    "SQLAlchemyAttachmentRepository",
    "SQLAlchemyGcTaskRepository",
    "SQLAlchemyImportOriginRepository",
    "SQLAlchemyTagChangeLogRepository",
    "SQLAlchemyTagRepository",
]

def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(value)


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


class SQLAlchemyTagRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def ensure_tag(self, name: str) -> UUID:
        tag_name = name.strip()
        if not tag_name:
            raise ValueError("tag name must not be empty")
        if len(tag_name) > 100:
            raise ValueError("tag name too long")
        existing = self.session.scalar(select(TagORM).where(TagORM.name == tag_name))
        if existing is not None:
            return UUID(existing.id)
        tag = TagORM(id=str(uuid4()), name=tag_name)
        try:
            with self.session.begin_nested():
                self.session.add(tag)
                self.session.flush()
        except IntegrityError:
            # 并发下由 UNIQUE(name) 兜底：回读已存在行（savepoint 已回滚）。
            row = self.session.scalar(select(TagORM).where(TagORM.name == tag_name))
            if row is None:
                raise
            return UUID(row.id)
        return UUID(tag.id)

    def set_item_tags(self, item_id: UUID, tags: Sequence[str]) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for raw in tags:
            name = raw.strip()
            if not name or name in seen:
                continue
            seen.add(name)
            ordered.append(name)
        self.session.execute(delete(ItemTagORM).where(ItemTagORM.item_id == str(item_id)))
        for name in ordered:
            tag_id = self.ensure_tag(name)
            self.session.add(ItemTagORM(item_id=str(item_id), tag_id=str(tag_id)))
        self.session.flush()
        return ordered

    def list_item_tags(self, item_id: UUID) -> list[str]:
        rows = self.session.scalars(
            select(TagORM.name)
            .join(ItemTagORM, ItemTagORM.tag_id == TagORM.id)
            .where(ItemTagORM.item_id == str(item_id))
            .order_by(TagORM.name)
        )
        return list(rows)

    def list_items_by_tag(self, name: str) -> list[UUID]:
        rows = self.session.scalars(
            select(ItemTagORM.item_id)
            .join(TagORM, TagORM.id == ItemTagORM.tag_id)
            .where(TagORM.name == name.strip())
        )
        return [UUID(row) for row in rows]

    def list_tags(self) -> list[str]:
        return list(self.session.scalars(select(TagORM.name).order_by(TagORM.name)))

    def delete_tag(self, name: str) -> bool:
        tag = self.session.scalar(select(TagORM).where(TagORM.name == name.strip()))
        if tag is None:
            return False
        self.session.delete(tag)
        self.session.flush()
        return True


class SQLAlchemyTagChangeLogRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def append(self, record: TagChangeRecord) -> TagChangeRecord:
        orm = TagChangeLogORM(
            id=str(record.id),
            item_id=str(record.item_id) if record.item_id is not None else None,
            item_id_snapshot=str(record.item_id_snapshot),
            item_title_snapshot=record.item_title_snapshot,
            old_tags=json.dumps(record.old_tags, ensure_ascii=False),
            new_tags=json.dumps(record.new_tags, ensure_ascii=False),
            actor=record.actor,
            change_source=record.change_source,
            correlation_id=record.correlation_id,
            changed_at=record.changed_at,
        )
        self.session.add(orm)
        self.session.flush()
        return record

    @staticmethod
    def _to_entity(orm: TagChangeLogORM) -> TagChangeRecord:
        return TagChangeRecord(
            id=UUID(orm.id),
            item_id=UUID(orm.item_id) if orm.item_id else None,
            item_id_snapshot=UUID(orm.item_id_snapshot),
            item_title_snapshot=orm.item_title_snapshot,
            old_tags=json.loads(orm.old_tags),
            new_tags=json.loads(orm.new_tags),
            actor=orm.actor,
            change_source=orm.change_source,
            correlation_id=orm.correlation_id,
            changed_at=_utc(orm.changed_at),
        )

    def list_for_item(self, item_id_snapshot: UUID) -> list[TagChangeRecord]:
        rows = self.session.scalars(
            select(TagChangeLogORM)
            .where(TagChangeLogORM.item_id_snapshot == str(item_id_snapshot))
            .order_by(TagChangeLogORM.changed_at)
        )
        return [self._to_entity(row) for row in rows]

    def list_all(self, *, limit: int | None = None) -> list[TagChangeRecord]:
        stmt = select(TagChangeLogORM).order_by(TagChangeLogORM.changed_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        return [self._to_entity(row) for row in self.session.scalars(stmt)]


class SQLAlchemyImportOriginRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save_origin(self, origin: ImportOrigin) -> ImportOrigin:
        orm = ImportOriginORM(
            id=str(origin.id),
            item_id=str(origin.item_id),
            source_payload_hash=origin.source_payload_hash,
            source_content_hash=origin.source_content_hash,
            source_instance_id=origin.source_instance_id,
            source_document_id=str(origin.source_document_id),
            source_canonicalization_version=origin.source_canonicalization_version,
            imported_at=origin.imported_at,
            import_batch_id=origin.import_batch_id,
        )
        self.session.add(orm)
        self.session.flush()
        return origin

    @staticmethod
    def _to_entity(orm: ImportOriginORM) -> ImportOrigin:
        return ImportOrigin(
            id=UUID(orm.id),
            item_id=UUID(orm.item_id),
            source_payload_hash=orm.source_payload_hash,
            source_content_hash=orm.source_content_hash,
            source_instance_id=orm.source_instance_id,
            source_document_id=UUID(orm.source_document_id),
            source_canonicalization_version=orm.source_canonicalization_version,
            imported_at=_utc(orm.imported_at),
            import_batch_id=orm.import_batch_id,
        )

    def list_for_item(self, item_id: UUID) -> list[ImportOrigin]:
        rows = self.session.scalars(
            select(ImportOriginORM)
            .where(ImportOriginORM.item_id == str(item_id))
            .order_by(ImportOriginORM.imported_at, ImportOriginORM.id)
        )
        return [self._to_entity(row) for row in rows]

    def find_by_source_payload_hash(
        self,
        source_payload_hash: str,
        *,
        source_canonicalization_version: int | None = None,
    ) -> list[ImportOrigin]:
        stmt = select(ImportOriginORM).where(
            ImportOriginORM.source_payload_hash == source_payload_hash
        )
        if source_canonicalization_version is not None:
            stmt = stmt.where(
                ImportOriginORM.source_canonicalization_version
                == source_canonicalization_version
            )
        stmt = stmt.order_by(ImportOriginORM.imported_at, ImportOriginORM.id)
        return [self._to_entity(row) for row in self.session.scalars(stmt)]

    def find_by_source_document(
        self,
        source_document_id: UUID,
        *,
        source_instance_id: str | None = None,
    ) -> list[ImportOrigin]:
        stmt = select(ImportOriginORM).where(
            ImportOriginORM.source_document_id == str(source_document_id)
        )
        if source_instance_id is not None:
            stmt = stmt.where(ImportOriginORM.source_instance_id == source_instance_id)
        stmt = stmt.order_by(ImportOriginORM.imported_at, ImportOriginORM.id)
        return [self._to_entity(row) for row in self.session.scalars(stmt)]


def list_all_import_origins(session: Session) -> list[ImportOrigin]:
    """审计快照用：全部导入来源（稳定顺序由调用方按 item 分组排序）。"""
    rows = session.scalars(
        select(ImportOriginORM).order_by(ImportOriginORM.item_id, ImportOriginORM.id)
    )
    return [SQLAlchemyImportOriginRepository._to_entity(row) for row in rows]


class SQLAlchemyAttachmentRepository:
    """附件元数据仓储（端口不涉及物理文件；只 flush 不 commit）。"""

    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _to_entity(orm: AttachmentORM) -> Attachment:
        return Attachment(
            id=UUID(orm.id),
            item_id=UUID(orm.item_id),
            filename=orm.filename,
            mime=orm.mime,
            size=orm.size,
            storage_key=orm.storage_key,
            content_hash=orm.content_hash,
            created_at=_utc(orm.created_at),
        )

    def save_attachment(self, attachment: Attachment) -> Attachment:
        orm = AttachmentORM(
            id=str(attachment.id),
            item_id=str(attachment.item_id),
            filename=attachment.filename,
            mime=attachment.mime,
            size=attachment.size,
            storage_key=attachment.storage_key,
            content_hash=attachment.content_hash,
            created_at=attachment.created_at,
        )
        self.session.add(orm)
        self.session.flush()
        return attachment

    def get_attachment(self, attachment_id: UUID) -> Attachment | None:
        orm = self.session.get(AttachmentORM, str(attachment_id))
        return None if orm is None else self._to_entity(orm)

    def list_attachments(self, item_id: UUID) -> list[Attachment]:
        rows = self.session.scalars(
            select(AttachmentORM)
            .where(AttachmentORM.item_id == str(item_id))
            .order_by(AttachmentORM.created_at, AttachmentORM.id)
        )
        return [self._to_entity(row) for row in rows]

    def find_by_hash(self, content_hash: str) -> list[Attachment]:
        rows = self.session.scalars(
            select(AttachmentORM)
            .where(AttachmentORM.content_hash == content_hash)
            .order_by(AttachmentORM.created_at, AttachmentORM.id)
        )
        return [self._to_entity(row) for row in rows]

    def count_references(self, storage_key: str) -> int:
        """派生引用数（COUNT 为唯一权威，不维护冗余计数列）。"""
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(AttachmentORM)
                .where(AttachmentORM.storage_key == storage_key)
            )
            or 0
        )

    def list_storage_keys(self) -> list[str]:
        rows = self.session.scalars(
            select(AttachmentORM.storage_key)
            .distinct()
            .order_by(AttachmentORM.storage_key)
        )
        return list(rows)

    def delete_attachment(self, attachment_id: UUID) -> bool:
        orm = self.session.get(AttachmentORM, str(attachment_id))
        if orm is None:
            return False
        self.session.delete(orm)
        self.session.flush()
        return True


def _utc_or_none(value: datetime | None) -> datetime | None:
    return None if value is None else _utc(value)


class SQLAlchemyGcTaskRepository:
    """GC 任务仓储：原子条件认领 + token fencing；只 flush 不 commit。

    ``claim`` 的写事务必须在调用方提交并关闭后，才可获取 StorageKeyLock
    （SQLite 单写者互等）。本类不做任何提交。
    """

    def __init__(
        self, session: Session, *, max_attempts: int = 8, quarantine_seconds: int = 86400
    ) -> None:
        self.session = session
        self.max_attempts = max_attempts
        self.quarantine_period = timedelta(seconds=quarantine_seconds)

    @staticmethod
    def _to_entity(orm: GcTaskORM) -> GcTask:
        return GcTask(
            id=UUID(orm.id),
            storage_key=orm.storage_key,
            status=GcStatus(orm.status),
            lease_owner=orm.lease_owner,
            lease_expires_at=_utc_or_none(orm.lease_expires_at),
            lease_token=orm.lease_token,
            attempts=orm.attempts,
            next_retry_at=_utc_or_none(orm.next_retry_at),
            quarantine_path=orm.quarantine_path,
            quarantined_at=_utc_or_none(orm.quarantined_at),
            created_at=_utc(orm.created_at),
            updated_at=_utc(orm.updated_at),
        )

    def _reload(self, task_id: UUID) -> GcTask | None:
        orm = self.session.execute(
            select(GcTaskORM)
            .where(GcTaskORM.id == str(task_id))
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        return None if orm is None else self._to_entity(orm)

    def save_task(self, task: GcTask) -> GcTask:
        orm = GcTaskORM(
            id=str(task.id),
            storage_key=task.storage_key,
            status=task.status.value,
            lease_owner=task.lease_owner,
            lease_expires_at=task.lease_expires_at,
            lease_token=task.lease_token,
            attempts=task.attempts,
            next_retry_at=task.next_retry_at,
            quarantine_path=task.quarantine_path,
            quarantined_at=task.quarantined_at,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )
        self.session.add(orm)
        self.session.flush()
        return task

    def get_task(self, task_id: UUID) -> GcTask | None:
        return self._reload(task_id)

    def list_tasks(
        self,
        *,
        status: GcStatus | None = None,
        storage_key: str | None = None,
    ) -> list[GcTask]:
        stmt = select(GcTaskORM)
        if status is not None:
            stmt = stmt.where(GcTaskORM.status == status.value)
        if storage_key is not None:
            stmt = stmt.where(GcTaskORM.storage_key == storage_key)
        stmt = stmt.order_by(GcTaskORM.created_at, GcTaskORM.id).execution_options(
            populate_existing=True
        )
        return [self._to_entity(row) for row in self.session.scalars(stmt)]

    def claim(
        self,
        task_id: UUID,
        *,
        owner: str,
        lease_ttl_seconds: float,
        now: datetime | None = None,
    ) -> GcTask | None:
        """条件认领：pending 或租约过期的 running → running（token+1, attempts+1）。

        隔离等待（running 且 next_retry_at > now）与预算耗尽的 running 不得被接管；
        终态、未过期 running、他人持有均返回 None。
        """
        if not owner or lease_ttl_seconds <= 0:
            raise ValueError("claim requires a nonempty owner and a positive TTL")
        moment = _utc(now) if now is not None else utcnow()
        expires = moment + timedelta(seconds=lease_ttl_seconds)
        claimable = or_(
            GcTaskORM.status == GcStatus.PENDING.value,
            (
                (GcTaskORM.status == GcStatus.RUNNING.value)
                & GcTaskORM.lease_expires_at.is_not(None)
                & (GcTaskORM.lease_expires_at <= moment)
            ),
        )
        due = or_(
            GcTaskORM.next_retry_at.is_(None),
            GcTaskORM.next_retry_at <= moment,
        )
        result = self.session.execute(
            update(GcTaskORM)
            .where(
                GcTaskORM.id == str(task_id),
                claimable,
                due,
                GcTaskORM.attempts < self.max_attempts,
            )
            .values(
                status=GcStatus.RUNNING.value,
                lease_owner=owner,
                lease_expires_at=expires,
                lease_token=GcTaskORM.lease_token + 1,
                attempts=GcTaskORM.attempts + 1,
                updated_at=moment,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            return None
        self.session.flush()
        return self._reload(task_id)

    def _db_now(self):
        if self.session.get_bind().dialect.name == "postgresql":
            return func.clock_timestamp()
        # SQLite stores UTC ORM timestamps as text with six fractional digits.
        # Pad SQLite's millisecond clock to the same sortable representation.
        return func.strftime("%Y-%m-%d %H:%M:%f000", "now")

    def _transition(self, task_id: UUID, *conditions, **values) -> GcTask | None:
        result = self.session.execute(
            update(GcTaskORM)
            .where(GcTaskORM.id == str(task_id), *conditions)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            return None
        self.session.flush()
        return self._reload(task_id)

    def update_task(self, task: GcTask, *, expected_lease_token: int) -> GcTask | None:
        """Worker-only writeback from a currently held running lease."""
        now = utcnow()
        if not task.lease_owner or task.lease_token != expected_lease_token:
            return None
        conditions = [
            GcTaskORM.status == GcStatus.RUNNING.value,
            GcTaskORM.lease_owner == task.lease_owner,
            GcTaskORM.lease_token == expected_lease_token,
            GcTaskORM.lease_expires_at > self._db_now(),
        ]
        values = {
            "status": task.status.value,
            "lease_owner": None,
            "lease_expires_at": None,
            "next_retry_at": None,
            "updated_at": now,
        }
        if task.status == GcStatus.RUNNING:
            # Only the quarantine wait can leave a worker writeback in running.
            if (
                not task.quarantine_path
                or task.quarantined_at is None
                or task.next_retry_at is None
                or _utc(task.quarantined_at) > now
                or _utc(task.next_retry_at) < _utc(task.quarantined_at) + self.quarantine_period
                or _utc(task.next_retry_at) <= now
            ):
                return None
            values.update(
                lease_owner=task.lease_owner, lease_expires_at=now,
                quarantine_path=task.quarantine_path, quarantined_at=task.quarantined_at,
                next_retry_at=task.next_retry_at,
            )
        elif task.status == GcStatus.FAILED_RETRYABLE:
            if task.next_retry_at is None or _utc(task.next_retry_at) <= now:
                return None
            conditions.append(GcTaskORM.attempts < self.max_attempts)
            values["next_retry_at"] = task.next_retry_at
        elif task.status not in {
            GcStatus.DONE, GcStatus.CANCELLED, GcStatus.FAILED_PERMANENT, GcStatus.NEEDS_MANUAL,
        }:
            return None
        return self._transition(task.id, *conditions, **values)

    def renew_task(
        self, task_id: UUID, *, owner: str, lease_token: int, lease_ttl_seconds: float
    ) -> GcTask | None:
        if not owner or lease_ttl_seconds <= 0:
            raise ValueError("renewal requires a nonempty owner and a positive TTL")
        now = utcnow()
        return self._transition(
            task_id,
            GcTaskORM.status == GcStatus.RUNNING.value,
            GcTaskORM.lease_owner == owner,
            GcTaskORM.lease_token == lease_token,
            GcTaskORM.lease_expires_at > self._db_now(),
            lease_expires_at=now + timedelta(seconds=lease_ttl_seconds), updated_at=now,
        )

    def requeue_due(self, task_id: UUID, *, expected_lease_token: int) -> GcTask | None:
        """Scheduler-only transition for a due retry with remaining attempts."""
        now = utcnow()
        return self._transition(
            task_id,
            GcTaskORM.status == GcStatus.FAILED_RETRYABLE.value,
            GcTaskORM.lease_token == expected_lease_token,
            GcTaskORM.next_retry_at <= self._db_now(),
            GcTaskORM.attempts < self.max_attempts,
            status=GcStatus.PENDING.value, next_retry_at=None, updated_at=now,
        )

    def fail_unretryable(
        self, task_id: UUID, *, expected_lease_token: int, non_retryable: bool = False
    ) -> GcTask | None:
        """Scheduler finalizes exhausted jobs or a classified permanent retry failure."""
        now = utcnow()
        retry_failure = GcTaskORM.status == GcStatus.FAILED_RETRYABLE.value
        if not non_retryable:
            retry_failure &= GcTaskORM.attempts >= self.max_attempts
        expired_exhausted = (
            (GcTaskORM.status == GcStatus.RUNNING.value)
            & (GcTaskORM.lease_expires_at <= self._db_now())
            & (GcTaskORM.attempts >= self.max_attempts)
            & or_(GcTaskORM.next_retry_at.is_(None), GcTaskORM.next_retry_at <= self._db_now())
        )
        return self._transition(
            task_id,
            GcTaskORM.lease_token == expected_lease_token,
            or_(retry_failure, expired_exhausted),
            status=GcStatus.FAILED_PERMANENT.value, next_retry_at=None,
            lease_owner=None, lease_expires_at=None, updated_at=now,
        )

    def operator_transition(
        self, task_id: UUID, *, source: GcStatus, target: GcStatus, expected_lease_token: int
    ) -> GcTask | None:
        """Internal operator entry point, separate from worker and scheduler writes."""
        if (source, target) not in {
            (GcStatus.FAILED_PERMANENT, GcStatus.NEEDS_MANUAL),
            (GcStatus.NEEDS_MANUAL, GcStatus.PENDING),
            (GcStatus.NEEDS_MANUAL, GcStatus.CANCELLED),
            (GcStatus.PENDING, GcStatus.CANCELLED),
        }:
            return None
        changes = {"attempts": 0} if target == GcStatus.PENDING else {}
        return self._transition(
            task_id,
            GcTaskORM.status == source.value,
            GcTaskORM.lease_token == expected_lease_token,
            status=target.value, next_retry_at=None, lease_owner=None,
            lease_expires_at=None, updated_at=utcnow(), **changes,
        )
