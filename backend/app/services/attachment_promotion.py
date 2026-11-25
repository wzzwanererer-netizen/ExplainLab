"""Publish verified staging files and bind their references to a business transaction."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.storage_lock import LockGuard
from app.services.attachment_staging import (
    AttachmentManifestItem,
    AttachmentStagingService,
)
from app.services.attachment_storage import (
    ATTACHMENT_HASH_MISMATCH,
    AttachmentStorageError,
    _unlink_owned,
    copy_to_temp,
    publish_no_clobber,
)
from app.services.repositories_v2 import SQLAlchemyAttachmentRepository
from knowledge_core.domain.entities import Attachment, utcnow


@dataclass(frozen=True)
class PublishedAttachments:
    staging_id: UUID
    target: UUID | None
    manifest: tuple[AttachmentManifestItem, ...]

    def save_references(self, session: Session, item_id: UUID) -> None:
        if self.target is not None and self.target != item_id:
            raise ValueError("attachment publication target changed")
        repo = SQLAlchemyAttachmentRepository(session)
        existing = {attachment.storage_key for attachment in repo.list_attachments(item_id)}
        for entry in self.manifest:
            if entry.storage_key not in existing:
                repo.save_attachment(
                    Attachment(
                        item_id=item_id,
                        filename=entry.filename,
                        mime=entry.mime,
                        size=entry.size,
                        storage_key=entry.storage_key,
                        content_hash=entry.storage_key,
                        created_at=utcnow(),
                    )
                )


def publish_staged(
    staging: AttachmentStagingService,
    staging_id: UUID,
    manifest: tuple[AttachmentManifestItem, ...],
    target: UUID | None,
    guard: LockGuard,
) -> PublishedAttachments:
    """Run with both guards held and before the business write starts."""
    entries = staging.validate_manifest_locked(staging_id, manifest)
    directory = staging.staging_root / str(staging_id)
    for entry in entries:
        guard.verify_all()
        temp = copy_to_temp(staging.layout, directory / entry.blob)
        try:
            if temp.sha256 != entry.storage_key or temp.size != entry.size:
                raise AttachmentStorageError(ATTACHMENT_HASH_MISMATCH)
            publish_no_clobber(staging.layout, temp, entry.storage_key, lock_guard=guard)
        finally:
            _unlink_owned(temp.path, temp.identity)
    return PublishedAttachments(staging_id, target, entries)
