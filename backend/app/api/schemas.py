"""API 数据传输对象。

读模型通过 from_attributes 映射 ORM 行或 Knowledge Core 领域实体；
写模型负责入参校验。DTO 不含任何密钥字段。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from knowledge_core.domain.entities import (
    KnowledgeStatus,
    LinkResolution,
    RelationType,
    ReviewAction,
    SourceType,
)
from knowledge_core.experiments.entities import ExperimentKind


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


class AttachmentUploadIn(BaseModel):
    """JSON Base64 上传体；只接受三个字段，不使用 multipart。"""

    model_config = ConfigDict(extra="forbid")

    filename: str
    mime: str
    content_base64: str


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    item_id: UUID
    filename: str
    mime: str
    size: int
    storage_key: str
    content_hash: str
    created_at: datetime


class ExtractRequest(BaseModel):
    space_id: str | None = None


class ExtractResponse(BaseModel):
    count: int
    items: list[KnowledgeOut]


class LinkOut(BaseModel):
    """出链读模型（V2 A1-03，D8 只读 GET）。target_title/alias 为原始书写字面。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: UUID
    target_id: UUID | None
    target_title: str
    alias: str | None
    normalized_link_key: str
    link_normalization_version: int
    resolution: LinkResolution
    cross_space: bool
    created_at: datetime
    updated_at: datetime


class BacklinkOut(BaseModel):
    """反链读模型：指向本条目的链接行（source_id 为引用方条目）。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: UUID
    target_id: UUID | None
    target_title: str
    alias: str | None
    resolution: LinkResolution
    cross_space: bool
    created_at: datetime
    updated_at: datetime


class ResolveCandidateOut(BaseModel):
    """解析候选读模型（只读）：含 archived 条目并带 status 标注（D7），
    跨空间候选同样列出；cross_space 相对查询给定的 space_id 判定
    （None 与 None 视为同空间，§2.5 精确等值口径）。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    space_id: str | None
    status: KnowledgeStatus
    cross_space: bool


class RelationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: UUID
    target_id: UUID
    relation_type: str
    confidence: float
    origin: str
    created_at: datetime


class GraphNodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    status: str
    space_id: str | None


class GraphEdgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: UUID
    target_id: UUID
    relation_type: str
    confidence: float
    origin: str


class GraphOut(BaseModel):
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]


class RelationCreate(BaseModel):
    target_id: UUID
    relation_type: RelationType
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    item_id: UUID
    version: int
    title: str
    content: str
    change_summary: str | None
    created_at: datetime


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    item_id: UUID
    action: str
    payload: dict
    reason: str | None
    status: str
    created_at: datetime
    resolved_at: datetime | None
    resolution_note: str | None


class ReviewSubmit(BaseModel):
    item_id: UUID
    action: ReviewAction
    payload: dict = Field(default_factory=dict)
    reason: str | None = None


class ReviewSubmitResult(BaseModel):
    """POST /reviews 的结果：重要变更生成审核单；否则直接应用。"""

    applied: bool
    review: ReviewOut | None = None


class ReviewResolve(BaseModel):
    note: str | None = None


class DuplicateOut(BaseModel):
    item_id: UUID
    score: float
    title: str


class AnalyzeResponse(BaseModel):
    duplicates: list[DuplicateOut]
    relations: list[RelationOut]


class SourceAttach(BaseModel):
    source_type: SourceType
    uri: str | None = None
    conversation_id: str | None = None
    excerpt: str | None = None


SearchMode = Literal["hybrid", "fts", "vector"]


class SearchHitOut(BaseModel):
    """一条检索命中（映射 Knowledge Core SearchResult）。"""

    model_config = ConfigDict(from_attributes=True)

    item_id: UUID
    score: float
    snippet: str
    title: str
    space_id: str | None
    status: str
    channels: dict[str, float]


class SearchResponse(BaseModel):
    query: str
    mode: str
    count: int
    # 向量通道能力：not_configured / configured / supported / unsupported（如实上报）
    embed_capability: str
    results: list[SearchHitOut]


class ReindexResponse(BaseModel):
    indexed: int
    embed_capability: str


class ExperimentCreate(BaseModel):
    """创建实验会话：quiz/compare 需模型，chain 确定性无需模型。"""

    kind: ExperimentKind
    item_ids: list[UUID] = Field(min_length=1)
    space_id: str | None = None
    count: int = Field(default=5, ge=1, le=20)
    seed_id: UUID | None = None


class ExperimentAnswer(BaseModel):
    index: int = Field(ge=0)
    value: int = Field(ge=0)


class ExperimentComplete(BaseModel):
    answers: list[ExperimentAnswer] = Field(default_factory=list)


class ExperimentOut(BaseModel):
    """实验会话对外视图。测验未完成时 payload 不含正确答案与解析。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    title: str
    space_id: str | None
    item_ids: list[UUID]
    payload: dict
    status: str
    created_at: datetime
    updated_at: datetime


class AnswerFeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    correct: bool
    correct_value: int
    explanation: str


class AttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    answers: list[dict]
    correct_count: int
    total: int
    score: float
    created_at: datetime


class ExperimentCompleteResult(BaseModel):
    session: ExperimentOut
    attempt: AttemptOut

class MarkdownImportItemIn(BaseModel):
    """单篇 Markdown 入参（非附件 Batch A）。

    ``attachments`` 仅用于识别附件请求（显式拒绝），本批不写任何附件。
    """

    content: str = Field(min_length=1)
    filename: str | None = None
    target_item_id: UUID | None = None
    frontmatter_resolution: Literal["normalize", "keep_original"] | None = None
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class MarkdownImportIn(BaseModel):
    """单篇/批量导入 JSON 入参；``archive_base64`` 支持导出 ZIP 回灌。"""

    content: str | None = None
    filename: str | None = None
    target_item_id: UUID | None = None
    frontmatter_resolution: Literal["normalize", "keep_original"] | None = None
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    documents: list[MarkdownImportItemIn] | None = None
    space_id: str | None = None
    batch_id: str | None = None
    manifest: dict[str, Any] | None = None
    archive_base64: str | None = None


class MarkdownExportIn(BaseModel):
    ids: list[UUID] = Field(default_factory=list)
    space_id: str | None = None
    include_attachments: bool = False
