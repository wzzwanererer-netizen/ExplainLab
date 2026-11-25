"""附件业务编排（V2 A1-04 Batch B，B2-T02）。

职责严格限定为：上传入参校验、归档策略、内容去重、引用写入、元数据列表、
下载文件句柄、删除引用与 GC 入队、稳定错误码映射。物理存储与锁复用 B1 的
``attachment_storage`` / ``storage_lock``；Repository 只 flush，本服务及
Repository **不 commit/rollback**，提交边界由路由外层 Unit of Work 独占。

冻结契约见 ``docs/plans/V2-A1-04-Batch-B/``（api-contracts、attachment-lifecycle、
storage-and-lock-contract、architecture §4）。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Collection
from dataclasses import dataclass
from typing import BinaryIO
from urllib.parse import quote
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.storage_lock import (
    LockGuard,
    StorageLeaseLost,
    StorageLockError,
    StorageLockTransient,
    new_owner,
)
from app.models import KnowledgeItemORM
from app.services.attachment_storage import (
    ATTACHMENT_BLOB_CORRUPTED,
    ATTACHMENT_BLOB_MISSING,
    ATTACHMENT_HASH_MISMATCH,
    ATTACHMENT_KEY_COLLISION,
    ATTACHMENT_STORAGE_CROSS_VOLUME,
    ATTACHMENT_STORAGE_UNAVAILABLE,
    ATTACHMENT_WRITE_BUSY,
    ATTACHMENT_WRITE_CORRUPTED,
    ATTACHMENT_WRITE_FAILED,
    AttachmentStorageError,
    StorageLayout,
    TempBlob,
    open_verified_blob,
    publish_no_clobber,
    sha256_bytes,
    verify_blob,
    write_temp,
)
from app.services.attachment_validation import (
    ATTACHMENT_BASE64_INVALID,
    ATTACHMENT_CONTENT_MISMATCH,
    ATTACHMENT_EMPTY,
    ATTACHMENT_FILENAME_INVALID,
    ATTACHMENT_MIME_UNSUPPORTED,
    ATTACHMENT_TOO_LARGE,
    AttachmentValidationError,
    validate_attachment_upload,
)
from app.services.repositories_v2 import (
    SQLAlchemyAttachmentRepository,
    SQLAlchemyGcTaskRepository,
)
from knowledge_core.domain.entities import (
    Attachment,
    GcStatus,
    GcTask,
    KnowledgeStatus,
    utcnow,
)

__all__ = [
    "ATTACHMENT_FAILED",
    "ATTACHMENT_ITEM_ARCHIVED",
    "ATTACHMENT_MAINTENANCE_UNAVAILABLE",
    "ATTACHMENT_NOT_FOUND",
    "ITEM_NOT_FOUND",
    "STORAGE_LOCK_TIMEOUT",
    "AttachmentDownload",
    "AttachmentService",
    "AttachmentServiceError",
    "AttachmentUploadResult",
    "attachment_content_disposition",
    "release_storage_guard",
]

logger = logging.getLogger(__name__)

ITEM_NOT_FOUND = "ITEM_NOT_FOUND"
ATTACHMENT_NOT_FOUND = "ATTACHMENT_NOT_FOUND"
ATTACHMENT_ITEM_ARCHIVED = "ATTACHMENT_ITEM_ARCHIVED"
ATTACHMENT_FAILED = "ATTACHMENT_FAILED"
ATTACHMENT_MAINTENANCE_UNAVAILABLE = "ATTACHMENT_MAINTENANCE_UNAVAILABLE"
STORAGE_LOCK_TIMEOUT = "STORAGE_LOCK_TIMEOUT"
STORAGE_LOCK_UNAVAILABLE = "STORAGE_LOCK_UNAVAILABLE"

_VALIDATION_STATUS = {
    ATTACHMENT_BASE64_INVALID: 400,
    ATTACHMENT_EMPTY: 400,
    ATTACHMENT_FILENAME_INVALID: 400,
    ATTACHMENT_TOO_LARGE: 413,
    ATTACHMENT_MIME_UNSUPPORTED: 415,
    ATTACHMENT_CONTENT_MISMATCH: 415,
}

_STORAGE_STATUS = {
    ATTACHMENT_HASH_MISMATCH: 422,
    ATTACHMENT_KEY_COLLISION: 409,
    ATTACHMENT_WRITE_BUSY: 503,
    ATTACHMENT_WRITE_CORRUPTED: 503,
    ATTACHMENT_WRITE_FAILED: 503,
    ATTACHMENT_STORAGE_UNAVAILABLE: 503,
    ATTACHMENT_STORAGE_CROSS_VOLUME: 503,
    ATTACHMENT_BLOB_MISSING: 503,
    ATTACHMENT_BLOB_CORRUPTED: 503,
}

_ACTIVE_GC_STATUSES = {
    GcStatus.PENDING,
    GcStatus.RUNNING,
    GcStatus.FAILED_RETRYABLE,
}
_BLOCKING_GC_STATUSES = {
    GcStatus.FAILED_PERMANENT,
    GcStatus.NEEDS_MANUAL,
}


class AttachmentServiceError(RuntimeError):
    """业务拒绝，只携带冻结稳定码与 HTTP 状态。"""

    def __init__(
        self,
        code: str,
        status_code: int,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.code = code
        self.status_code = status_code
        self.headers = headers
        self.attachment_guard: LockGuard | None = None
        super().__init__(code)


@dataclass(frozen=True)
class AttachmentUploadResult:
    attachment: Attachment
    created: bool
    guard: LockGuard | None

    def release(self) -> None:
        """Commit/rollback 之后释放存储锁；释放失败不改变已提交业务结果。"""
        release_storage_guard(self.guard)


@dataclass(frozen=True)
class AttachmentDownload:
    attachment: Attachment
    handle: BinaryIO


def _storage_service_error(exc: AttachmentStorageError) -> AttachmentServiceError:
    status = _STORAGE_STATUS.get(exc.code, 503)
    headers = {"Retry-After": "1"} if exc.code == ATTACHMENT_WRITE_BUSY else None
    return AttachmentServiceError(exc.code, status, headers=headers)


def _lock_service_error(exc: StorageLockError) -> AttachmentServiceError:
    code = getattr(exc, "code", STORAGE_LOCK_UNAVAILABLE)
    if code == "STORAGE_LEASE_LOST":
        return AttachmentServiceError(code, 503)
    return AttachmentServiceError(code or STORAGE_LOCK_UNAVAILABLE, 503)


def _discard_temp(temp: TempBlob) -> None:
    try:
        info = temp.path.lstat()
        if (info.st_dev, info.st_ino) == temp.identity:
            os.unlink(temp.path)
    except OSError:
        pass


def release_storage_guard(guard: LockGuard | None) -> None:
    """释放存储锁；只用于路由完成 rollback 之后或已提交之后。"""
    if guard is None:
        return
    try:
        if not guard.release():
            logger.warning("STORAGE_LOCK_RELEASE_FAILED")
    except StorageLockError:
        logger.warning("STORAGE_LOCK_RELEASE_FAILED")
    except Exception:  # noqa: BLE001 - cleanup cannot change the response
        logger.warning("STORAGE_LOCK_RELEASE_FAILED")


def _clean_header_filename(filename: str) -> str:
    cleaned = "".join(
        char for char in filename
        if char not in {'"', "\\", "\r", "\n"} and ord(char) >= 0x20
    )
    return cleaned or "attachment"


def attachment_content_disposition(filename: str) -> str:
    """RFC 5987/6266 下载头；ASCII fallback 与 UTF-8 原名均做头字段清洗。"""
    cleaned = _clean_header_filename(filename)
    fallback = "".join(
        char if 0x20 <= ord(char) < 0x7F else "_" for char in cleaned
    ) or "_"
    encoded = quote(cleaned, safe="")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"


class AttachmentService:
    """附件业务服务；所有 DB 写入只 flush，提交由路由外层协调器完成。"""

    def __init__(
        self,
        *,
        session_factory,
        layout: StorageLayout,
        storage_lock,
        max_bytes: int,
        mime_allowlist: Collection[str],
        lock_ttl_seconds: float,
        lock_wait_seconds: float,
        lock_heartbeat_seconds: float,
        gc_max_attempts: int = 8,
        gc_quarantine_seconds: int = 86400,
    ) -> None:
        self.session_factory = session_factory
        self.layout = layout
        self.storage_lock = storage_lock
        self.max_bytes = max_bytes
        self.mime_allowlist = tuple(mime_allowlist)
        self.lock_ttl_seconds = lock_ttl_seconds
        self.lock_wait_seconds = lock_wait_seconds
        self.lock_heartbeat_seconds = lock_heartbeat_seconds
        self.gc_max_attempts = gc_max_attempts
        self.gc_quarantine_seconds = gc_quarantine_seconds

    # -- 读取入口 -----------------------------------------------------------
    def _require_item(self, session: Session, item_id: UUID) -> KnowledgeItemORM:
        item = session.get(KnowledgeItemORM, str(item_id))
        if item is None:
            raise AttachmentServiceError(ITEM_NOT_FOUND, 404)
        return item

    def _require_upload_target(self, item_id: UUID) -> None:
        with self.session_factory() as probe:
            item = probe.get(KnowledgeItemORM, str(item_id))
            if item is None:
                raise AttachmentServiceError(ITEM_NOT_FOUND, 404)
            if item.status == KnowledgeStatus.ARCHIVED.value:
                raise AttachmentServiceError(ATTACHMENT_ITEM_ARCHIVED, 409)

    def _find_reference(self, session: Session, item_id: UUID, storage_key: str) -> Attachment | None:
        for attachment in SQLAlchemyAttachmentRepository(session).list_attachments(item_id):
            if attachment.storage_key == storage_key:
                return attachment
        return None

    # -- 上传 ---------------------------------------------------------------
    def upload(
        self,
        session: Session,
        item_id: UUID,
        *,
        filename: str,
        mime: str,
        content_base64: str,
    ) -> AttachmentUploadResult:
        # 1. archived 早拒：必须发生在解码与写临时文件之前。
        self._require_upload_target(item_id)

        # 2. 纯函数校验（Base64/大小/MIME/magic/UTF-8/文件名）。
        try:
            validated = validate_attachment_upload(
                filename,
                mime,
                content_base64,
                max_bytes=self.max_bytes,
                mime_allowlist=self.mime_allowlist,
            )
        except AttachmentValidationError as exc:
            raise AttachmentServiceError(
                exc.code, _VALIDATION_STATUS.get(exc.code, 400)
            ) from None

        storage_key = sha256_bytes(validated.data)

        # 3. 快速路径：已有同 item+key 引用且正式 blob 可验证 → 200，不重写。
        with self.session_factory() as probe:
            existing = self._find_reference(probe, item_id, storage_key)
        if existing is not None:
            try:
                verify_blob(self.layout, storage_key, expected_size=existing.size)
            except AttachmentStorageError as exc:
                if exc.code == ATTACHMENT_BLOB_MISSING:
                    existing = None  # 在锁内重新发布后再复用引用。
                elif exc.code == ATTACHMENT_BLOB_CORRUPTED:
                    raise AttachmentServiceError(ATTACHMENT_KEY_COLLISION, 409) from None
                else:
                    raise _storage_service_error(exc) from None
            if existing is not None:
                return AttachmentUploadResult(existing, False, None)

        # 4. 锁外写临时文件并重读 Hash；临时文件不进入正式根。
        try:
            temp = write_temp(self.layout, validated.data)
        except AttachmentStorageError as exc:
            raise _storage_service_error(exc) from None
        if temp.sha256 != storage_key:
            _discard_temp(temp)
            raise AttachmentServiceError(ATTACHMENT_HASH_MISMATCH, 422)

        # 5. 先取 key 锁、再发布；业务写事务从发布之后才开始。
        try:
            guard = self.storage_lock.acquire_many(
                [storage_key],
                new_owner(),
                ttl_seconds=self.lock_ttl_seconds,
                wait_seconds=self.lock_wait_seconds,
                heartbeat_seconds=self.lock_heartbeat_seconds,
            )
        except StorageLockError as exc:
            _discard_temp(temp)
            raise _lock_service_error(exc) from None
        except StorageLockTransient:
            _discard_temp(temp)
            raise AttachmentServiceError(STORAGE_LOCK_UNAVAILABLE, 503) from None
        if guard is None:
            _discard_temp(temp)
            raise AttachmentServiceError(STORAGE_LOCK_TIMEOUT, 409)

        try:
            try:
                publish_no_clobber(
                    self.layout, temp, storage_key, lock_guard=guard
                )
            except StorageLeaseLost as exc:
                raise _lock_service_error(exc) from None
            except AttachmentStorageError as exc:
                raise _storage_service_error(exc) from None
            except StorageLockError as exc:
                raise _lock_service_error(exc) from None

            try:
                self._guard_writable_item(session, item_id)
                attachment = self._find_reference(session, item_id, storage_key)
                created = attachment is None
                if attachment is None:
                    attachment = Attachment(
                        item_id=item_id,
                        filename=validated.filename,
                        mime=validated.mime,
                        size=len(validated.data),
                        storage_key=storage_key,
                        content_hash=storage_key,
                        created_at=utcnow(),
                    )
                    SQLAlchemyAttachmentRepository(session).save_attachment(attachment)
                # 与将执行 commit 的同一 session 做末次 fencing。
                guard.verify_all(session)
            except AttachmentServiceError:
                raise
            except StorageLeaseLost as exc:
                raise _lock_service_error(exc) from None
            except StorageLockError as exc:
                raise _lock_service_error(exc) from None
            except SQLAlchemyError:
                raise
            return AttachmentUploadResult(attachment, created, guard)
        except BaseException as exc:
            if isinstance(exc, Exception):
                # 路由须先 rollback 业务事务，再释放锁（architecture §4.4 / F13）。
                exc.attachment_guard = guard  # type: ignore[attr-defined]
                raise
            _release_after_failure(guard)
            raise

    def _guard_writable_item(self, session: Session, item_id: UUID) -> None:
        """在业务写事务内做归档保护（PG 行锁 / SQLite 条件防护更新）。"""
        dialect = session.get_bind().dialect.name
        if dialect == "postgresql":
            session.execute(
                select(KnowledgeItemORM)
                .where(KnowledgeItemORM.id == str(item_id))
                .with_for_update()
            )
        elif dialect == "sqlite":
            session.execute(
                update(KnowledgeItemORM)
                .where(
                    KnowledgeItemORM.id == str(item_id),
                    KnowledgeItemORM.status != KnowledgeStatus.ARCHIVED.value,
                )
                .values(
                    status=KnowledgeItemORM.status,
                    updated_at=KnowledgeItemORM.updated_at,
                )
                .execution_options(synchronize_session=False)
            )
        else:
            raise AttachmentServiceError(ATTACHMENT_FAILED, 500)

        item = session.get(
            KnowledgeItemORM, str(item_id), populate_existing=True
        )
        if item is None:
            raise AttachmentServiceError(ITEM_NOT_FOUND, 404)
        if item.status == KnowledgeStatus.ARCHIVED.value:
            raise AttachmentServiceError(ATTACHMENT_ITEM_ARCHIVED, 409)

    # -- 列表 ---------------------------------------------------------------
    def list(self, session: Session, item_id: UUID) -> list[Attachment]:
        self._require_item(session, item_id)
        return SQLAlchemyAttachmentRepository(session).list_attachments(item_id)

    # -- 下载 ---------------------------------------------------------------
    def download(
        self, session: Session, item_id: UUID, attachment_id: UUID
    ) -> AttachmentDownload:
        if session.get(KnowledgeItemORM, str(item_id)) is None:
            raise AttachmentServiceError(ATTACHMENT_NOT_FOUND, 404)
        repository = SQLAlchemyAttachmentRepository(session)
        attachment = repository.get_attachment(attachment_id)
        if attachment is None or attachment.item_id != item_id:
            raise AttachmentServiceError(ATTACHMENT_NOT_FOUND, 404)
        try:
            handle = open_verified_blob(
                self.layout,
                attachment.storage_key,
                expected_size=attachment.size,
            )
        except AttachmentStorageError as exc:
            raise _storage_service_error(exc) from None
        return AttachmentDownload(attachment, handle)

    # -- 删除 ---------------------------------------------------------------
    def delete(
        self, session: Session, item_id: UUID, attachment_id: UUID
    ) -> None:
        if session.get(KnowledgeItemORM, str(item_id)) is None:
            raise AttachmentServiceError(ATTACHMENT_NOT_FOUND, 404)
        repository = SQLAlchemyAttachmentRepository(session)
        attachment = repository.get_attachment(attachment_id)
        if attachment is None or attachment.item_id != item_id:
            raise AttachmentServiceError(ATTACHMENT_NOT_FOUND, 404)
        if not repository.delete_attachment(attachment_id):
            raise AttachmentServiceError(ATTACHMENT_NOT_FOUND, 404)
        if repository.count_references(attachment.storage_key) != 0:
            return
        try:
            self._ensure_gc_task(session, attachment.storage_key)
        except SQLAlchemyError:
            raise AttachmentServiceError(
                ATTACHMENT_MAINTENANCE_UNAVAILABLE, 503
            ) from None

    def _ensure_gc_task(self, session: Session, storage_key: str) -> None:
        repository = SQLAlchemyGcTaskRepository(
            session,
            max_attempts=self.gc_max_attempts,
            quarantine_seconds=self.gc_quarantine_seconds,
        )
        for task in repository.list_tasks(storage_key=storage_key):
            if task.status in _ACTIVE_GC_STATUSES:
                return
            if task.status in _BLOCKING_GC_STATUSES:
                logger.warning(
                    "gc task requires manual attention for key prefix %s",
                    storage_key[:8],
                )
                return
        repository.save_task(GcTask(storage_key=storage_key, status=GcStatus.PENDING))


def _release_after_failure(guard: LockGuard) -> None:
    try:
        guard.release()
    except Exception:  # noqa: BLE001 - original failure is authoritative
        logger.warning("STORAGE_LOCK_RELEASE_FAILED")