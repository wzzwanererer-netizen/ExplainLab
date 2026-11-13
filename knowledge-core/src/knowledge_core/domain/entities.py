"""领域实体：知识条目、关系、版本、来源。

纯 Pydantic 模型，不绑定数据库 ORM 与 Web 框架。
M0 为骨架定义，字段将随 M1+ 业务实现演进。
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


def utcnow() -> datetime:
    return datetime.now(UTC)


class KnowledgeStatus(StrEnum):
    """知识条目生命周期状态。"""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class RelationType(StrEnum):
    """知识关系类型（M0 最小集合，后续可扩展）。"""

    RELATED = "related"
    DEPENDS_ON = "depends_on"
    DUPLICATE_OF = "duplicate_of"
    REFINES = "refines"
    CONTRADICTS = "contradicts"


class RelationOrigin(StrEnum):
    """知识关系的产生方式（M2）。"""

    MANUAL = "manual"
    LLM = "llm"
    DEDUP = "dedup"


class SourceType(StrEnum):
    """知识来源类型。"""

    CONVERSATION = "conversation"
    DOCUMENT = "document"
    MANUAL = "manual"
    IMPORT = "import"


class SourceRef(BaseModel):
    """来源追溯最小单元：一条知识可追溯到多个来源。"""

    id: UUID = Field(default_factory=uuid4)
    source_type: SourceType
    uri: str | None = None
    conversation_id: str | None = None
    excerpt: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class KnowledgeItem(BaseModel):
    """知识条目。

    space_id 为 None 表示个人总知识库；否则归属某个项目知识空间。
    """

    id: UUID = Field(default_factory=uuid4)
    title: str = Field(min_length=1, max_length=500)
    content: str
    status: KnowledgeStatus = KnowledgeStatus.DRAFT
    space_id: str | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class KnowledgeRelation(BaseModel):
    """两条知识之间的关系。"""

    id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    target_id: UUID
    relation_type: RelationType
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    origin: RelationOrigin = RelationOrigin.MANUAL
    created_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def _no_self_relation(self) -> KnowledgeRelation:
        if self.source_id == self.target_id:
            raise ValueError("知识关系不允许指向自身")
        return self


class KnowledgeVersion(BaseModel):
    """知识条目的一个历史版本。"""

    id: UUID = Field(default_factory=uuid4)
    item_id: UUID
    version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=500)
    content: str
    change_summary: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class ReviewStatus(StrEnum):
    """审核单生命周期状态（M2）。"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewAction(StrEnum):
    """审核单所承载的拟变更类型（M2）。"""

    UPDATE_ITEM = "update_item"
    DELETE_ITEM = "delete_item"
    MERGE_DUPLICATE = "merge_duplicate"
    RESTORE_VERSION = "restore_version"


class ReviewRequest(BaseModel):
    """重要变更的审核单（M2）。

    payload 承载拟变更内容（如新 title/content/status、合并目标 id、回滚版本号），
    批准后才应用；驳回不改动数据。
    """

    id: UUID = Field(default_factory=uuid4)
    item_id: UUID
    action: ReviewAction
    payload: dict = Field(default_factory=dict)
    reason: str | None = None
    status: ReviewStatus = ReviewStatus.PENDING
    created_at: datetime = Field(default_factory=utcnow)
    resolved_at: datetime | None = None
    resolution_note: str | None = None