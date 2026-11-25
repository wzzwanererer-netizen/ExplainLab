"""导入审核钩子（V2 A1-04 Batch A）。

Core ``ReviewService`` 只应用 title/content/status/space 四字段；导入 envelope 中
的 tags / metadata / 来源身份 / 显式链接由本钩子在 **同一事务** 内补齐：

- approve：Core approve 之后、首次 commit 之前调用；任何校验/写入失败由路由
  回滚整个事务，审核单保持 PENDING。
- reject：没有任何导入写入；本模块只提供显式空操作，便于测试断言。

附件引用只消费业务写事务之前生成的发布计划。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.attachment_promotion import PublishedAttachments
from app.services.links import build_link_restorer
from app.services.markdown import (
    ATTACHMENT_REVIEW_UNSUPPORTED,
    IMPORT_ENVELOPE_INVALID,
    MarkdownServiceError,
)
from app.services.markdown_item_repository import MarkdownItemRecord, MarkdownItemRepository
from app.services.repositories_v2 import (
    SQLAlchemyImportOriginRepository,
    SQLAlchemyTagChangeLogRepository,
    SQLAlchemyTagRepository,
)
from app.services.source_identity import SourceIdentityService
from knowledge_core.domain.entities import (
    ImportOrigin,
    KnowledgeItem,
    KnowledgeStatus,
    ReviewRequest,
    TagChangeRecord,
)
from knowledge_core.markdown.import_report import IMPORT_ENVELOPE_KEY, ImportEnvelope
from knowledge_core.markdown.service import (
    SOURCE_IDENTITY_KEYS,
    assert_exporter_metadata_clean,
)

__all__ = ["ImportReviewHook", "envelope_from_review", "review_is_import"]


def _envelope(payload: dict[str, Any] | None) -> ImportEnvelope | None:
    if not isinstance(payload, dict) or IMPORT_ENVELOPE_KEY not in payload:
        return None
    try:
        return ImportEnvelope.from_review_payload(payload)
    except Exception as exc:
        raise MarkdownServiceError(
            IMPORT_ENVELOPE_INVALID, "导入审核 envelope 非法", status_code=409
        ) from exc


def review_is_import(review: ReviewRequest) -> bool:
    return isinstance(review.payload, dict) and IMPORT_ENVELOPE_KEY in review.payload


def envelope_from_review(review: ReviewRequest) -> ImportEnvelope | None:
    return _envelope(review.payload)


@dataclass(frozen=True)
class ReviewAttachmentPlan:
    review_id: UUID
    context_digest: str
    published: PublishedAttachments

    def require_match(self, review: ReviewRequest, envelope: ImportEnvelope) -> None:
        if (
            self.review_id != review.id
            or self.published.target != review.item_id
            or self.context_digest != envelope.context_digest
            or [entry.model_dump(mode="json") for entry in self.published.manifest]
            != envelope.attachments
        ):
            raise MarkdownServiceError(IMPORT_ENVELOPE_INVALID, status_code=409)


class ImportReviewHook:
    """在同一事务内补齐导入审核的非 Core 字段。"""

    def __init__(self, session: Session, identity: SourceIdentityService) -> None:
        self._session = session
        self._identity = identity
        self._items = MarkdownItemRepository(session)
        self._tags = SQLAlchemyTagRepository(session)
        self._origins = SQLAlchemyImportOriginRepository(session)
        self._logs = SQLAlchemyTagChangeLogRepository(session)

    def validate_target(
        self, review: ReviewRequest, envelope: ImportEnvelope, *, attachments: bool,
    ) -> tuple[MarkdownItemRecord, list[ImportOrigin]]:
        if envelope.target_item_id is not None and str(review.item_id) != str(
            envelope.target_item_id
        ):
            raise MarkdownServiceError(
                IMPORT_ENVELOPE_INVALID,
                "envelope target 与审核条目不一致",
                status_code=409,
            )
        assert_exporter_metadata_clean(envelope.extra_metadata)
        for key in SOURCE_IDENTITY_KEYS:
            if key in envelope.extra_metadata:
                raise MarkdownServiceError(
                    IMPORT_ENVELOPE_INVALID,
                    "envelope metadata 含来源身份保留键",
                    status_code=409,
                )
        record = self._items.get(review.item_id)
        if record is None:
            raise MarkdownServiceError(
                "IMPORT_FAILED", "审核条目不存在", status_code=409
            )
        materialized = (
            self._identity.has_recovered_materialize(record.id)
            if attachments
            else self._identity.has_committed_materialize(record.id)
        )
        if materialized:
            # §22.2：审核批准时条目已被物化 → 追加 ImportOrigin 会造成冲突态。
            # 在写任何导入字段前 fail-closed；路由回滚整个审核事务。
            raise MarkdownServiceError(
                "SOURCE_IDENTITY_CONFLICT",
                "目标条目已物化，导入审核不得追加来源身份",
                status_code=409,
            )

        origins = []
        if envelope.source_instance_id and envelope.source_document_id:
            origins = self._origins.list_for_item(record.id)
            pairs = {
                (origin.source_instance_id, str(origin.source_document_id))
                for origin in origins
            }
            incoming = {
                (envelope.source_instance_id, str(envelope.source_document_id))
            }
            if pairs and pairs != incoming:
                raise MarkdownServiceError(
                    "SOURCE_IDENTITY_CONFLICT",
                    "目标条目来源身份与审核 envelope 不一致",
                    status_code=409,
                )
        return record, origins

    def apply_approved(
        self, review: ReviewRequest, envelope: ImportEnvelope,
        plan: ReviewAttachmentPlan | None = None,
    ) -> None:
        if envelope.attachments:
            if plan is None:
                raise MarkdownServiceError(ATTACHMENT_REVIEW_UNSUPPORTED, status_code=400)
            plan.require_match(review, envelope)
        record, origins = self.validate_target(review, envelope, attachments=plan is not None)
        if envelope.source_instance_id and envelope.source_document_id:
            existing_versions = {
                origin.source_payload_hash for origin in origins
            }
            if envelope.source_payload_hash not in existing_versions:
                self._origins.save_origin(
                    ImportOrigin(
                        item_id=record.id,
                        source_payload_hash=envelope.source_payload_hash,
                        source_content_hash=envelope.source_content_hash,
                        source_instance_id=envelope.source_instance_id,
                        source_document_id=UUID(envelope.source_document_id),
                        source_canonicalization_version=envelope.canonicalization_version,
                        imported_at=datetime.now(UTC),
                    )
                )
            record = self._items.update_fields(
                record.id,
                extra_metadata=envelope.extra_metadata,
                source_payload_hash=envelope.source_payload_hash,
                source_content_hash=envelope.source_content_hash,
                source_instance_id=envelope.source_instance_id,
            )
        else:
            record = self._items.update_fields(
                record.id,
                extra_metadata=envelope.extra_metadata,
                source_payload_hash=envelope.source_payload_hash,
                source_content_hash=envelope.source_content_hash,
            )

        old_tags = self._tags.list_item_tags(record.id)
        new_tags = self._tags.set_item_tags(record.id, envelope.tags)
        if old_tags != new_tags:
            self._logs.append(
                TagChangeRecord(
                    item_id=record.id,
                    item_id_snapshot=record.id,
                    item_title_snapshot=record.title,
                    old_tags=old_tags,
                    new_tags=new_tags,
                    actor="review",
                    change_source="markdown_import_approved",
                    correlation_id=str(review.id),
                )
            )

        item = KnowledgeItem(
            id=record.id,
            title=record.title,
            content=record.content,
            status=KnowledgeStatus(record.status),
            space_id=record.space_id,
            tags=new_tags,
            extra_metadata=record.extra_metadata,
            created_at=record.created_at or datetime.now(UTC),
            updated_at=record.updated_at or datetime.now(UTC),
        )
        build_link_restorer(self._session).restore(item, envelope.links, record.content)
        if plan is not None:
            plan.published.save_references(self._session, review.item_id)

    def apply_rejected(self, review: ReviewRequest) -> None:
        """拒绝导入审核：不写 ImportOrigin / item / tags / links。"""
        _ = review
