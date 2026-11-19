"""领域实体：知识条目、关系、版本、来源。

纯 Pydantic 模型，不绑定数据库 ORM 与 Web 框架。
M0 为骨架定义，字段将随 M1+ 业务实现演进。
V2 A1 增量：Markdown 文档模型（tags/extra_metadata）、双向链接基础设施
（KnowledgeLink + 规范化版本）、附件、标签变更审计、GC 租约任务、导入来源身份。
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


def utcnow() -> datetime:
    return datetime.now(UTC)


# V2 A1：两类独立的规则版本号（设计 §2.4 / §2.6.1）。
# canonicalization_version：hash 输入包络的序列化规则版本（三 Hash 共用）。
# link_normalization_version：链接身份键规范化规则版本（v1 = NFKC + casefold + 空白折叠）。
# 规则变更必须 bump 版本并重算/重建，不同版本的 hash/键不可直接比较。
CANONICALIZATION_VERSION = 1
LINK_NORMALIZATION_VERSION = 1


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
    # V2 A1：标签（低风险直改+留痕）与未知 frontmatter 字段保留（extra_metadata）。
    # content 即 Markdown 正文；纯文本是合法 Markdown，旧正文原样保留（零转换）。
    tags: list[str] = Field(default_factory=list)
    extra_metadata: dict = Field(default_factory=dict)
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


class LinkResolution(StrEnum):
    """双向链接的解析状态（V2 A1，设计 §2.4）。

    resolved    已绑定唯一稳定 ID；
    missing     目标标题在本库无匹配（悬空链接，保留原文不删除）；
    ambiguous   规范化键碰撞出多个候选，不随机绑定；
    cross_space 目标存在于其它知识空间；
    conflict    显式冲突（如人工指定与解析结果矛盾），须人工裁决。
    """

    RESOLVED = "resolved"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    CROSS_SPACE = "cross_space"
    CONFLICT = "conflict"


class KnowledgeLink(BaseModel):
    """Markdown 双向链接（V2 A1）。

    身份键 normalized_link_key 非空且双方言唯一；target_title / alias 保留原始
    书写字面用于展示，规范化绝不覆盖原文。target_id 绑定稳定 UUID，改名不断链。
    """

    id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    target_id: UUID | None = None
    target_title: str = Field(min_length=1, max_length=500)
    alias: str | None = None
    normalized_link_key: str = Field(min_length=1, max_length=1024)
    link_normalization_version: int = Field(default=LINK_NORMALIZATION_VERSION, ge=1)
    resolution: LinkResolution = LinkResolution.MISSING
    cross_space: bool = False
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def _resolution_matches_binding(self) -> KnowledgeLink:
        if self.resolution == LinkResolution.RESOLVED and self.target_id is None:
            raise ValueError("resolution=resolved 必须绑定 target_id（稳定 UUID）")
        if self.target_id is not None and self.resolution == LinkResolution.MISSING:
            raise ValueError("已绑定 target_id 的链接不得标记为 missing")
        return self


class Attachment(BaseModel):
    """知识条目附件（V2 A1）。storage_key 内容寻址，可被多条知识共享。"""

    id: UUID = Field(default_factory=uuid4)
    item_id: UUID
    filename: str = Field(min_length=1, max_length=500)
    mime: str = Field(min_length=1, max_length=200)
    size: int = Field(ge=0)
    storage_key: str = Field(min_length=1, max_length=64)
    content_hash: str = Field(min_length=1, max_length=64)
    created_at: datetime = Field(default_factory=utcnow)


class TagChangeRecord(BaseModel):
    """标签变更审计（V2 A1，append-only）。

    item_id 为可空外键（条目删除后 SET NULL 保留审计）；item_id_snapshot /
    item_title_snapshot 在写入时固化，删除后仍可追溯身份与标题。
    """

    id: UUID = Field(default_factory=uuid4)
    item_id: UUID | None = None
    item_id_snapshot: UUID
    item_title_snapshot: str = Field(min_length=1, max_length=500)
    old_tags: list[str] = Field(default_factory=list)
    new_tags: list[str] = Field(default_factory=list)
    actor: str | None = None
    change_source: str | None = None
    correlation_id: str | None = None
    changed_at: datetime = Field(default_factory=utcnow)


class GcStatus(StrEnum):
    """附件 GC 任务状态机（V2 A1，设计 §2.8，含 cancelled）。"""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_PERMANENT = "failed_permanent"
    NEEDS_MANUAL = "needs_manual"


class GcTask(BaseModel):
    """附件存储 GC 任务（V2 A1）：租约认领 + fencing token + 持锁 quarantine。

    lease_token 单调递增，旧 worker 持过期 token 的写入必须被拒绝（fencing）。
    quarantine_path/quarantined_at 记录「持锁隔离」后的隔离区位置，可恢复。
    """

    id: UUID = Field(default_factory=uuid4)
    storage_key: str = Field(min_length=1, max_length=64)
    status: GcStatus = GcStatus.PENDING
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    lease_token: int = Field(default=0, ge=0)
    attempts: int = Field(default=0, ge=0)
    next_retry_at: datetime | None = None
    quarantine_path: str | None = Field(default=None, max_length=512)
    quarantined_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class StorageLease(BaseModel):
    """storage_key 租约凭证（V2 A1，设计 §2.5.1）。

    纯值对象：由 backend 适配层（SQLite 租约锁表 / PG advisory lock）签发，
    Core 与业务只携带它做 fencing 校验，不接触任何方言 SQL。
    lease_token 单调递增；owner+token 失配即视为租约已被接管，必须中止不可逆操作。
    """

    storage_key: str = Field(min_length=1, max_length=64)
    owner: str = Field(min_length=1, max_length=64)
    lease_token: int = Field(ge=0)
    lease_expires_at: datetime


class ImportOrigin(BaseModel):
    """导入来源身份（V2 A1，设计 §2.6.3 R5-2）。

    source_payload_hash / source_content_hash 是**源实例**在其
    source_canonicalization_version 下算出的 hash，原样持久化，
    不被目标实例再生覆盖；幂等判定比对源 hash 而非目标重算 hash。
    """

    id: UUID = Field(default_factory=uuid4)
    item_id: UUID
    source_payload_hash: str = Field(min_length=1, max_length=64)
    source_content_hash: str = Field(min_length=1, max_length=64)
    source_instance_id: str | None = Field(default=None, max_length=64)
    source_document_id: UUID
    source_canonicalization_version: int = Field(default=CANONICALIZATION_VERSION, ge=1)
    imported_at: datetime = Field(default_factory=utcnow)
    import_batch_id: str | None = Field(default=None, max_length=64)