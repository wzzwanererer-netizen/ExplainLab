"""API 数据传输对象。

读模型通过 from_attributes 映射 ORM 行或 Knowledge Core 领域实体；
写模型负责入参校验。DTO 不含任何密钥字段。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from knowledge_core.domain.entities import KnowledgeStatus


class SpaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    kind: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class SpaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    content: str
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    space_id: str | None
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class ConversationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    space_id: str | None = None


class ChatRequest(BaseModel):
    content: str = Field(min_length=1)


class SourceRefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_type: str
    uri: str | None
    conversation_id: str | None
    excerpt: str | None
    created_at: datetime


class KnowledgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    space_id: str | None
    title: str
    content: str
    status: str
    source_refs: list[SourceRefOut]
    created_at: datetime
    updated_at: datetime


class KnowledgeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1)
    space_id: str | None = None


class KnowledgeUpdate(BaseModel):
    """部分更新；未提供的字段保持不变（space_id 传 null 亦表示不修改）。"""

    title: str | None = Field(default=None, min_length=1, max_length=500)
    content: str | None = None
    status: KnowledgeStatus | None = None
    space_id: str | None = None


class ExtractRequest(BaseModel):
    space_id: str | None = None


class ExtractResponse(BaseModel):
    count: int
    items: list[KnowledgeOut]