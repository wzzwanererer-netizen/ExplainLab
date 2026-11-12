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