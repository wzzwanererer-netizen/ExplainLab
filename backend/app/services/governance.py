"""M2 治理持久化与服务装配。

Relation / Version / Review 三个仓库端口的 SQLAlchemy 实现，
以及各治理服务的装配助手。领域逻辑全部在 Knowledge Core，本层只做映射与装配。
"""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import KnowledgeRelationORM, KnowledgeVersionORM, ReviewRequestORM
from app.services.errors import NotFoundError
from app.services.knowledge import SQLAlchemyKnowledgeRepository
from knowledge_core.domain.entities import (
    KnowledgeRelation,
    KnowledgeVersion,
    RelationOrigin,
    RelationType,
    ReviewAction,
    ReviewRequest,
    ReviewStatus,
)
from knowledge_core.extraction.llm import LLMExtractionService
from knowledge_core.model_adapter import ModelAdapter
from knowledge_core.provenance.service import RepositoryProvenanceService
from knowledge_core.relations.llm import LLMRelationService
from knowledge_core.review import ReviewService
from knowledge_core.services import KnowledgeService
from knowledge_core.versioning.service import RepositoryVersionService


def _to_relation(row: KnowledgeRelationORM) -> KnowledgeRelation:
    return KnowledgeRelation(
        id=UUID(row.id),
        source_id=UUID(row.source_id),
        target_id=UUID(row.target_id),
        relation_type=RelationType(row.relation_type),
        confidence=row.confidence,
        origin=RelationOrigin(row.origin),
        created_at=row.created_at,
    )


def _to_version(row: KnowledgeVersionORM) -> KnowledgeVersion:
    return KnowledgeVersion(
        id=UUID(row.id),
        item_id=UUID(row.item_id),
        version=row.version,
        title=row.title,
        content=row.content,
        change_summary=row.change_summary,
        created_at=row.created_at,
    )


def _to_review(row: ReviewRequestORM) -> ReviewRequest:
    return ReviewRequest(
        id=UUID(row.id),
        item_id=UUID(row.item_id),
        action=ReviewAction(row.action),
        payload=json.loads(row.payload),
        reason=row.reason,
        status=ReviewStatus(row.status),
        created_at=row.created_at,
        resolved_at=row.resolved_at,
        resolution_note=row.resolution_note,
    )


class SQLAlchemyRelationRepository:
    """RelationRepository 端口的 SQLAlchemy 实现。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save_relation(self, relation: KnowledgeRelation) -> KnowledgeRelation:
        row = KnowledgeRelationORM(
            id=str(relation.id),
            source_id=str(relation.source_id),
            target_id=str(relation.target_id),
            relation_type=relation.relation_type.value,
            confidence=relation.confidence,
            origin=relation.origin.value,
            created_at=relation.created_at,
        )
        self._session.add(row)
        self._session.flush()
        return _to_relation(row)

    def list_relations(self, item_id: UUID) -> list[KnowledgeRelation]:
        key = str(item_id)
        stmt = (
            select(KnowledgeRelationORM)
            .where(
                or_(
                    KnowledgeRelationORM.source_id == key,
                    KnowledgeRelationORM.target_id == key,
                )
            )
            .order_by(KnowledgeRelationORM.created_at)
        )
        return [_to_relation(row) for row in self._session.scalars(stmt)]

    def find_relation(
        self, source_id: UUID, target_id: UUID, relation_type: RelationType
    ) -> KnowledgeRelation | None:
        stmt = select(KnowledgeRelationORM).where(
            KnowledgeRelationORM.source_id == str(source_id),
            KnowledgeRelationORM.target_id == str(target_id),
            KnowledgeRelationORM.relation_type == relation_type.value,
        )
        row = self._session.scalars(stmt).first()
        return _to_relation(row) if row is not None else None

    def delete_relation(self, relation_id: UUID) -> bool:
        row = self._session.get(KnowledgeRelationORM, str(relation_id))
        if row is None:
            return False
        self._session.delete(row)
        self._session.flush()
        return True


class SQLAlchemyVersionRepository:
    """VersionRepository 端口的 SQLAlchemy 实现。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save_version(self, version: KnowledgeVersion) -> KnowledgeVersion:
        row = KnowledgeVersionORM(
            id=str(version.id),
            item_id=str(version.item_id),
            version=version.version,
            title=version.title,
            content=version.content,
            change_summary=version.change_summary,
            created_at=version.created_at,
        )
        self._session.add(row)
        self._session.flush()
        return _to_version(row)

    def list_versions(self, item_id: UUID) -> list[KnowledgeVersion]:
        stmt = (
            select(KnowledgeVersionORM)
            .where(KnowledgeVersionORM.item_id == str(item_id))
            .order_by(KnowledgeVersionORM.version)
        )
        return [_to_version(row) for row in self._session.scalars(stmt)]

    def get_version(self, item_id: UUID, version: int) -> KnowledgeVersion | None:
        stmt = select(KnowledgeVersionORM).where(
            KnowledgeVersionORM.item_id == str(item_id),
            KnowledgeVersionORM.version == version,
        )
        row = self._session.scalars(stmt).first()
        return _to_version(row) if row is not None else None


class SQLAlchemyReviewRepository:
    """ReviewRepository 端口的 SQLAlchemy 实现。payload 以 JSON 文本存储。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save_review(self, review: ReviewRequest) -> ReviewRequest:
        row = ReviewRequestORM(
            id=str(review.id),
            item_id=str(review.item_id),
            action=review.action.value,
            payload=json.dumps(review.payload, ensure_ascii=False),
            reason=review.reason,
            status=review.status.value,
            created_at=review.created_at,
            resolved_at=review.resolved_at,
            resolution_note=review.resolution_note,
        )
        self._session.add(row)
        self._session.flush()
        return _to_review(row)

    def get_review(self, review_id: UUID) -> ReviewRequest | None:
        row = self._session.get(ReviewRequestORM, str(review_id))
        return _to_review(row) if row is not None else None

    def list_reviews(self, status: ReviewStatus | None = None) -> list[ReviewRequest]:
        stmt = select(ReviewRequestORM).order_by(ReviewRequestORM.created_at.desc())
        if status is not None:
            stmt = stmt.where(ReviewRequestORM.status == status.value)
        return [_to_review(row) for row in self._session.scalars(stmt)]

    def update_review(self, review: ReviewRequest) -> ReviewRequest:
        row = self._session.get(ReviewRequestORM, str(review.id))
        if row is None:
            raise NotFoundError(f"审核单不存在: {review.id}")
        row.status = review.status.value
        row.resolved_at = review.resolved_at
        row.resolution_note = review.resolution_note
        self._session.flush()
        return _to_review(row)


def build_version_service(session: Session) -> RepositoryVersionService:
    return RepositoryVersionService(
        SQLAlchemyVersionRepository(session), SQLAlchemyKnowledgeRepository(session)
    )


def build_review_service(session: Session) -> ReviewService:
    return ReviewService(
        SQLAlchemyKnowledgeRepository(session),
        SQLAlchemyReviewRepository(session),
        build_version_service(session),
        SQLAlchemyRelationRepository(session),
    )


def build_provenance_service(session: Session) -> RepositoryProvenanceService:
    return RepositoryProvenanceService(SQLAlchemyKnowledgeRepository(session))


def build_analysis_service(session: Session, adapter: ModelAdapter) -> KnowledgeService:
    """装配带去重 / 关系推断能力的知识工作流（analyze 入口）。"""
    return KnowledgeService(
        LLMExtractionService(adapter),
        SQLAlchemyKnowledgeRepository(session),
        relation_service=LLMRelationService(adapter),
        relation_repository=SQLAlchemyRelationRepository(session),
    )