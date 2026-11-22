"""导入结果报告与导入审核 envelope 的纯逻辑（V2 A1-04 Batch A）。

本模块只依赖标准库 + Pydantic（Core 独立性约束），不触 DB / 文件 / Web。
``ImportReport`` 是 backend ``services/markdown.py`` 的汇总载体；
``ImportEnvelope`` 是 Active 审核单 ``payload.__a1_import`` 的数据契约
（D16：Core ``ReviewService`` 仍只应用 title/content/status/space_id 四字段）。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from knowledge_core.markdown.canonical import (
    CanonicalizationError,
    sha256_canonical,
    sort_links,
    sort_sources,
    sort_tags,
)

__all__ = [
    "IMPORT_ENVELOPE_KEY",
    "ChangeSet",
    "ImportDecision",
    "ImportEnvelope",
    "ImportItemResult",
    "ImportItemStatus",
    "ImportReport",
    "classify_changes",
    "decide_import",
]

IMPORT_ENVELOPE_KEY = "__a1_import"
IMPORT_ENVELOPE_SCHEMA_VERSION = 1


class ImportItemStatus(StrEnum):
    """单文档导入结果状态（稳定字符串，供 API/报告消费）。"""

    CREATED = "created"
    UPDATED = "updated"
    SKIPPED = "skipped"
    PENDING_REVIEW = "pending_review"
    REUSED_PENDING = "reused_pending"
    DUPLICATE = "duplicate"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


class ImportItemResult(BaseModel):
    """单文档导入结果。"""

    model_config = ConfigDict(extra="forbid")

    filename: str | None = None
    item_id: UUID | None = None
    status: ImportItemStatus
    source_content_hash: str | None = None
    source_payload_hash: str | None = None
    canonicalization_version: int | None = None
    duplicates: list[UUID] = Field(default_factory=list)
    review_id: UUID | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    status_changes: list[str] = Field(default_factory=list)
    unsupported: list[str] = Field(default_factory=list)
    unresolved_links: list[str] = Field(default_factory=list)


class ImportReport(BaseModel):
    """批量导入汇总（非全有全无；逐文档结果如实保留）。"""

    model_config = ConfigDict(extra="forbid")

    total: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    pending_review: int = 0
    reused_pending: int = 0
    duplicates: int = 0
    errors: int = 0
    unsupported: int = 0
    rejected_conflicts: int = 0
    legacy: int = 0
    items: list[ImportItemResult] = Field(default_factory=list)

    def add(self, item: ImportItemResult) -> None:
        self.items.append(item)
        self.total += 1
        if item.status == ImportItemStatus.CREATED:
            self.created += 1
        elif item.status == ImportItemStatus.UPDATED:
            self.updated += 1
        elif item.status == ImportItemStatus.SKIPPED:
            self.skipped += 1
        elif item.status == ImportItemStatus.PENDING_REVIEW:
            self.pending_review += 1
        elif item.status == ImportItemStatus.REUSED_PENDING:
            self.reused_pending += 1
        elif item.status == ImportItemStatus.DUPLICATE:
            self.duplicates += 1
        elif item.status == ImportItemStatus.UNSUPPORTED:
            self.unsupported += 1
        elif item.status == ImportItemStatus.ERROR:
            self.errors += 1
        if item.conflicts:
            self.rejected_conflicts += 1


class ImportDecision(StrEnum):
    """锁内 S1 判定结果（D15）。"""

    APPLY = "apply"
    SKIP_APPLIED = "skip_applied"
    REUSE_PENDING = "reuse_pending"
    HAS_PENDING = "has_pending"


def decide_import(
    *,
    incoming_payload_hash: str,
    applied_payload_hash: str | None,
    pending_same_hash: bool,
    pending_other_hash: bool,
) -> ImportDecision:
    """按 D15 判定：已应用同 hash → skipped；同 hash pending → 复用；
    不同 hash pending → 拒绝新导入；否则应用。"""
    if applied_payload_hash is not None and applied_payload_hash == incoming_payload_hash:
        return ImportDecision.SKIP_APPLIED
    if pending_same_hash:
        return ImportDecision.REUSE_PENDING
    if pending_other_hash:
        return ImportDecision.HAS_PENDING
    return ImportDecision.APPLY


class ChangeSet(BaseModel):
    """既有条目 vs 入站文档的变化分类（内容 / 低风险元数据 / 治理）。"""

    model_config = ConfigDict(extra="forbid")

    title: bool = False
    content: bool = False
    tags: bool = False
    metadata: bool = False
    links: bool = False
    attachments: bool = False
    governance: bool = False
    sources: bool = False

    @property
    def has_content_change(self) -> bool:
        return self.title or self.content

    @property
    def has_change(self) -> bool:
        return any(
            (
                self.title,
                self.content,
                self.tags,
                self.metadata,
                self.links,
                self.attachments,
                self.governance,
                self.sources,
            )
        )


def _hash(value: Any) -> str:
    return sha256_canonical(value)


def classify_changes(
    *,
    current_title: str,
    current_content: str,
    current_status: str,
    current_space_id: str | None,
    current_tags: list[str],
    current_extra_metadata: dict[str, Any],
    current_links: list[dict[str, Any]],
    current_attachments: list[dict[str, Any]],
    incoming: Any,
) -> ChangeSet:
    """比较既有条目与入站 ``MarkdownDocument``，产出变化分类。

    ``incoming`` 使用鸭子类型（避免与 markdown/__init__ 循环导入）：
    需要 title/content/status/space_id/tags/extra_metadata/links/attachments。
    """
    incoming_tags = sort_tags(list(getattr(incoming, "tags", []) or []))
    incoming_meta = dict(getattr(incoming, "extra_metadata", {}) or {})
    incoming_links = sort_links(list(getattr(incoming, "links", []) or []))
    incoming_attachments = sort_links(list(getattr(incoming, "attachments", []) or []))
    incoming_status = getattr(incoming, "status", None)
    incoming_space = getattr(incoming, "space_id", None)
    incoming_title = getattr(incoming, "title", None)
    return ChangeSet(
        title=(incoming_title is not None and incoming_title != current_title),
        content=getattr(incoming, "content", "") != current_content,
        tags=incoming_tags != sort_tags(current_tags),
        metadata=_hash(incoming_meta) != _hash(current_extra_metadata),
        links=_hash(incoming_links) != _hash(sort_links(current_links)),
        attachments=_hash(incoming_attachments)
        != _hash(sort_links(current_attachments)),
        governance=(
            (incoming_status is not None and str(incoming_status) != current_status)
            or (incoming_space != current_space_id)
        ),
        sources=_hash(sort_sources(list(getattr(incoming, "sources", []) or [])))
        != _hash(sort_sources([])),
    )


class ImportEnvelope(BaseModel):
    """Active 导入审核 envelope（``payload.__a1_import``）。

    只承载 backend 在 approve 时需要的可重建上下文；Core ``_apply_update``
    忽略本键，仅应用四字段。``context_digest`` 仅做一致性校验，不是签名边界。
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = IMPORT_ENVELOPE_SCHEMA_VERSION
    target_item_id: str | None = None
    filename: str | None = None
    source_instance_id: str | None = None
    source_document_id: str | None = None
    source_payload_hash: str = Field(min_length=1, max_length=64)
    source_content_hash: str = Field(min_length=1, max_length=64)
    canonicalization_version: int
    space_id: str | None = None
    status: str
    tags: list[str] = Field(default_factory=list)
    extra_metadata: dict[str, Any] = Field(default_factory=dict)
    links: list[dict[str, Any]] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    context_digest: str = ""

    def compute_context_digest(self) -> str:
        body = self.model_dump(mode="json", exclude={"context_digest"})
        # envelope 自身已携带 canonicalization_version 字段；把它作为包络版本
        # 传给 canonical 原语，避免与保留键重复（否则 canonicalize 会拒绝）。
        version = int(body.pop("canonicalization_version"))
        return sha256_canonical(body, canonicalization_version=version)

    def with_digest(self) -> ImportEnvelope:
        return self.model_copy(update={"context_digest": self.compute_context_digest()})

    @classmethod
    def from_review_payload(cls, payload: dict[str, Any]) -> ImportEnvelope | None:
        """从审核单 payload 提取 envelope；无本键返回 None。

        结构/摘要不合法抛 ``CanonicalizationError``（调用方 fail-closed）。
        """
        raw = payload.get(IMPORT_ENVELOPE_KEY)
        if raw is None:
            return None
        try:
            envelope = cls.model_validate(raw)
        except Exception as exc:  # pydantic.ValidationError → 稳定失败
            raise CanonicalizationError("导入审核 envelope 结构不合法") from exc
        if envelope.schema_version != IMPORT_ENVELOPE_SCHEMA_VERSION:
            raise CanonicalizationError("导入审核 envelope 版本不受支持")
        expected = envelope.compute_context_digest()
        if envelope.context_digest != expected:
            raise CanonicalizationError("导入审核 envelope 摘要不一致")
        return envelope

    def review_payload(self, core_changes: dict[str, Any]) -> dict[str, Any]:
        """构造提交给 Core ReviewService 的 payload（四字段 + envelope）。"""
        body = self.with_digest().model_dump(mode="json")
        return {**core_changes, IMPORT_ENVELOPE_KEY: body}