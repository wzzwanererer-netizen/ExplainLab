"""Markdown 交换编解码接口与三 Hash（V2 A1，设计 §2.2.3 / §2.3 / §2.6.1）。

接口（MarkdownCodec ABC）与交换文档模型在此定义；具体实现见
knowledge_core.markdown.codec.StdlibMarkdownCodec（**零新增依赖**，仅标准库；
PyYAML 未获批准，不得引入）。规范化原语见 knowledge_core.markdown.canonical。

已知 frontmatter 键（保留命名空间，设计 §2.3）：
``id/title/tags/space/status/version/created_at/updated_at/sources/links``，
另加 ``attachments``——§2.6.1 明确把「attachments（清单+content_hash）」列为
交换字段并参与 payload_hash，故本实现将其纳入已知键（§2.2.3 示例未列出，
属示例非穷举；此为落地的实现决定，已记入验收报告）。

开放性口径 A（§2.3）：未知键全存 extra_metadata 原样回写；**语义无损（正常态
保证），字节级不保证**；复杂未知值 ``_raw`` 逐字兜底 + 告警；整块无法安全再生
时 ``_frontmatter_raw`` 保留原始块并进入**冲突态**。stdlib 保守解析器**不是通用
YAML 解析器**，只覆盖固定已知 schema + 简单未知值。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from knowledge_core.domain.entities import CANONICALIZATION_VERSION, KnowledgeStatus
from knowledge_core.markdown.canonical import (
    CanonicalizationError,
    canonical_datetime,
    hashes_comparable,
    require_comparable_versions,
    sha256_canonical,
    sort_attachments,
    sort_links,
    sort_sources,
    sort_tags,
)

__all__ = [
    "CANONICALIZATION_VERSION",
    "EXTRA_KEY_PREFIX",
    "KNOWN_FRONTMATTER_KEYS",
    "PERSONAL_SPACE_TOKEN",
    "PROJECT_SPACE_PREFIX",
    "RESERVED_META_KEYS",
    "CanonicalizationError",
    "CodecWarning",
    "ConflictResolution",
    "DocumentHashes",
    "FrontmatterResolution",
    "FrontmatterState",
    "MarkdownCodec",
    "MarkdownDocument",
    "MarkdownWarningCode",
    "ParsedMarkdown",
    "RenderedMarkdown",
    "compute_document_hashes",
    "decode_space",
    "document_content_hash",
    "document_payload_hash",
    "encode_space",
    "hashes_comparable",
    "require_comparable_versions",
    "resolve_frontmatter_conflict",
    "review_payload_hash",
]

# 确定性 emission 顺序：已知键按此固定顺序，未知键按名称排序追加。
KNOWN_FRONTMATTER_KEYS: tuple[str, ...] = (
    "id",
    "title",
    "tags",
    "space",
    "status",
    "version",
    "created_at",
    "updated_at",
    "sources",
    "links",
    "attachments",
)

# extra_metadata 内的诊断/兜底保留元键：**不作为 frontmatter 键回写**。
# _frontmatter_raw 存在 ⟺ 冲突态（原始块无法安全外科再生）。
RESERVED_META_KEYS: tuple[str, ...] = (
    "_frontmatter_raw",
    "_raw",
    "_duplicates",
    "_conflict",
)

# extra_metadata 与已知键同名时的前缀（设计 §2.3：已知键保留命名空间）。
EXTRA_KEY_PREFIX = "x_explainlab_"

PERSONAL_SPACE_TOKEN = "personal-null"
PROJECT_SPACE_PREFIX = "project-"

# 模型字段名 → 存在性判定分组（模块级常量，避免 Pydantic 私有属性语义歧义）。
_SCALAR_FIELDS: tuple[str, ...] = (
    "id",
    "title",
    "space_id",
    "status",
    "version",
    "created_at",
    "updated_at",
)
_COLLECTION_FIELDS: tuple[str, ...] = ("tags", "sources", "links", "attachments")


def encode_space(space_id: str | None) -> str:
    """知识空间 → 交换标识：None（个人总知识库）→ ``personal-null``。"""
    return PERSONAL_SPACE_TOKEN if space_id is None else PROJECT_SPACE_PREFIX + space_id


def decode_space(token: str) -> str | None:
    """交换标识 → space_id；非法形式抛 ValueError（调用方据此置类型不符冲突）。"""
    if token == PERSONAL_SPACE_TOKEN:
        return None
    if token.startswith(PROJECT_SPACE_PREFIX) and len(token) > len(PROJECT_SPACE_PREFIX):
        return token[len(PROJECT_SPACE_PREFIX) :]
    raise ValueError(f"space 必须是 {PERSONAL_SPACE_TOKEN} 或 {PROJECT_SPACE_PREFIX}<id>：{token!r}")


class FrontmatterState(StrEnum):
    """frontmatter 冲突三态（设计 §2.3 口径 A）。

    NORMAL      正常：语义无损往返（已知映射 + 未知保留 + 正文保真）；不保证字节级。
    CONFLICT    冲突未解决（``frontmatter_conflict_requires_resolution``）：原始块 +
                全部未知字段不动；**不保证实体修改写入交换文件**；不得称完全无损往返。
    NORMALIZED  用户显式规范化后：已知字段由实体再生 + 未知回写，无重复键，
                恢复正常语义无损；仍不保证字节级。
    """

    NORMAL = "normal"
    CONFLICT = "frontmatter_conflict_requires_resolution"
    NORMALIZED = "normalized"


class FrontmatterResolution(StrEnum):
    """冲突解决方式（**必须由用户主动选择**，设计 §2.3）。"""

    NORMALIZE = "normalize"
    KEEP_ORIGINAL = "keep_original"


class MarkdownWarningCode(StrEnum):
    """告警稳定码（ImportReport.warnings 消费，设计 §2.7）。"""

    BOM_REMOVED = "bom_removed"
    FRONTMATTER_NOT_CLOSED = "frontmatter_not_closed"
    FRONTMATTER_RAW_PRESERVED = "frontmatter_raw_preserved"
    UNSUPPORTED_CONSTRUCT = "unsupported_yaml_construct"
    UNKNOWN_COMPLEX_VALUE = "unknown_complex_value"
    KNOWN_COMPLEX_VALUE = "known_complex_value"
    KNOWN_TYPE_MISMATCH = "known_type_mismatch"
    DUPLICATE_KEY = "duplicate_key"
    KNOWN_KEY_COLLISION = "known_key_collision"
    CONFLICT_REQUIRES_RESOLUTION = "frontmatter_conflict_requires_resolution"
    ENTITY_EDITS_NOT_EXPORTED = "entity_edits_not_exported"
    NORMALIZE_DISCARDS_RAW = "normalize_discards_raw"
    KEEP_ORIGINAL_AUTHORITATIVE = "keep_original_authoritative"
    MISSING_STABLE_ID = "missing_stable_id"


class CodecWarning(BaseModel):
    """一条编解码告警（稳定码 + 关联键 + 人读说明）。"""

    code: MarkdownWarningCode
    message: str
    key: str | None = None


class MarkdownDocument(BaseModel):
    """Markdown 交换文档（frontmatter 已知字段 + 正文 + 未知字段）。

    这是**交换层**模型，不是持久化实体：sources/links/attachments 为交换形状的
    dict 列表（原样保留全部子键），实体映射由导入/导出服务负责（A1-04/A1-05）。

    字段存在性（设计 §2.6.1「null ≠ 缺失」）：以 Pydantic ``model_fields_set``
    记录**实际给出**的字段——显式 ``null`` 会进入 payload，缺失字段**不补 null**。
    解析时只传入文件中出现的键，故存在性与源文件一致。

    frontmatter_state / conflict_resolution 是**实例本地诊断**，不属交换字段，
    绝不进入 payload_hash（否则跨实例再生会破坏幂等）。

    ``extra="forbid"``：交换键名拼错必须**立刻报错**，不得静默丢字段。
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID | None = None
    title: str | None = None
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    space_id: str | None = None
    status: KnowledgeStatus | None = None
    version: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    links: list[dict[str, Any]] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    extra_metadata: dict[str, Any] = Field(default_factory=dict)
    frontmatter_state: FrontmatterState = FrontmatterState.NORMAL
    conflict_resolution: FrontmatterResolution | None = None

    # --- 字段存在性 → 交换字段 ---

    def present_exchange_fields(self) -> dict[str, Any]:
        """只含**实际存在**的交换键（显式 null 保留，缺失不补）。"""
        present = self.model_fields_set
        out: dict[str, Any] = {}
        for name in _SCALAR_FIELDS:
            value = getattr(self, name)
            if name in present or value is not None:
                out["space" if name == "space_id" else name] = value
        for name in _COLLECTION_FIELDS:
            if name in present:
                out[name] = getattr(self, name)
        if "extra_metadata" in present or self.extra_metadata:
            out["extra_metadata"] = self.extra_metadata
        # 正文恒存在（Markdown 文件必有 body，空正文为 ""）。
        out["content"] = self.content
        return out

    def payload_fields(self) -> dict[str, Any]:
        """完整交换载荷（payload_hash 输入）：类型规范化 + 语义序列表排序。

        hash 输入用**原始 Unicode 值**（不做 NFKC/casefold）；排序只决定顺序，
        不改写任何值，也不补缺失键。
        """
        out: dict[str, Any] = {}
        for key, value in self.present_exchange_fields().items():
            if key == "id":
                out[key] = None if value is None else str(value)
            elif key == "space":
                out[key] = encode_space(value)
            elif key == "status":
                out[key] = None if value is None else KnowledgeStatus(value).value
            elif key in ("created_at", "updated_at"):
                out[key] = None if value is None else canonical_datetime(value)
            elif key == "tags":
                out[key] = sort_tags(value)
            elif key == "links":
                out[key] = sort_links(value)
            elif key == "attachments":
                out[key] = sort_attachments(value)
            elif key == "sources":
                out[key] = sort_sources(value)
            else:
                out[key] = value
        return out

    def content_fields(self) -> dict[str, Any]:
        """内容身份子集：仅 title + content（排除治理状态与易变交换元数据）。"""
        fields: dict[str, Any] = {"content": self.content}
        if "title" in self.model_fields_set or self.title is not None:
            fields["title"] = self.title
        return fields

    def governance_fields(self) -> dict[str, Any]:
        """治理状态子集（status/version/space），仅用于变化分类。"""
        payload = self.payload_fields()
        return {k: payload[k] for k in ("status", "version", "space") if k in payload}

    def content_hash(
        self, *, canonicalization_version: int = CANONICALIZATION_VERSION
    ) -> str:
        return document_content_hash(
            self.content_fields(), canonicalization_version=canonicalization_version
        )

    def payload_hash(
        self, *, canonicalization_version: int = CANONICALIZATION_VERSION
    ) -> str:
        return document_payload_hash(
            self.payload_fields(), canonicalization_version=canonicalization_version
        )


class ParsedMarkdown(BaseModel):
    """解析结果：交换文档 + 三态 + 告警 + 原始 frontmatter 块（逐字）。"""

    document: MarkdownDocument
    state: FrontmatterState = FrontmatterState.NORMAL
    warnings: list[CodecWarning] = Field(default_factory=list)
    raw_frontmatter: str | None = None
    body: str = ""


class RenderedMarkdown(BaseModel):
    """导出结果：确定性文本 + 三态 + 告警（冲突态实体修改未写入时明确告警）。"""

    text: str
    state: FrontmatterState = FrontmatterState.NORMAL
    warnings: list[CodecWarning] = Field(default_factory=list)


class ConflictResolution(BaseModel):
    """用户主动解决冲突的结果（新文档 + 告警）。"""

    document: MarkdownDocument
    warnings: list[CodecWarning] = Field(default_factory=list)


class MarkdownCodec(ABC):
    """Markdown 交换编解码端口（设计 A1-T2）。

    实现必须：确定性再生（同输入字节一致）、未知字段原样保留、复杂值原始兜底 +
    告警、冲突三态不静默生成重复键、正文逐字保真。**不得**宣称字节级无损。
    """

    @abstractmethod
    def parse(self, text: str) -> ParsedMarkdown:
        """把 Markdown 交换文本解析为文档（保守解析，失败降级不丢数据）。"""
        raise NotImplementedError

    @abstractmethod
    def dump(
        self,
        document: MarkdownDocument,
        *,
        resolution: FrontmatterResolution | None = None,
    ) -> RenderedMarkdown:
        """把文档再生为 Markdown 交换文本。

        Args:
            document: 交换文档（含 extra_metadata 与 frontmatter 状态）。
            resolution: 冲突态下**用户主动选择**的解决方式；None 表示未解决，
                此时原始块逐字回写、实体已知字段修改不写入交换文件 + 告警。
        """
        raise NotImplementedError


# --- 三 Hash（设计 §2.6.1）---

_CONTENT_KEYS = frozenset({"title", "content"})
_REVIEW_KEYS = frozenset({"title", "content", "status", "space_id"})


def document_content_hash(
    fields: Mapping[str, Any],
    *,
    canonicalization_version: int = CANONICALIZATION_VERSION,
) -> str:
    """内容身份：仅 ``title`` + ``content``（与 id 解耦，利于同内容去重）。

    多余键一律拒绝，防止治理状态/易变元数据污染内容身份。
    """
    unexpected = set(fields) - _CONTENT_KEYS
    if unexpected:
        raise CanonicalizationError(
            f"document_content_hash 只接受 title/content，收到多余键: {sorted(unexpected)}"
        )
    if "content" not in fields:
        raise CanonicalizationError("document_content_hash 必须包含 content 字段")
    return sha256_canonical(fields, canonicalization_version=canonicalization_version)


def document_payload_hash(
    payload: Mapping[str, Any],
    *,
    canonicalization_version: int = CANONICALIZATION_VERSION,
) -> str:
    """完整交换载荷身份（**独立整体身份**，含 version/timestamps/status）。

    不是组件 hash 的拼接；输入须为 ``MarkdownDocument.payload_fields()`` 产出的
    完整交换字段（含 extra_metadata 与 attachments 清单）。
    """
    return sha256_canonical(payload, canonicalization_version=canonicalization_version)


def review_payload_hash(
    changes: Mapping[str, Any],
    *,
    canonicalization_version: int = CANONICALIZATION_VERSION,
) -> str:
    """实际审核变更身份：仅 ``title?/content?/status?/space_id?``（tags 不入审核）。

    用于提案防覆盖与「批准 == 应用」校验（§2.7，A1-05 集成）。其它审核动作
    （delete/merge/restore）的 payload 请直接用 ``sha256_canonical``。
    """
    unexpected = set(changes) - _REVIEW_KEYS
    if unexpected:
        raise CanonicalizationError(
            "review_payload_hash 只接受实际应用字段 title/content/status/space_id，"
            f"收到多余键: {sorted(unexpected)}"
        )
    if not changes:
        raise CanonicalizationError("review_payload_hash 不接受空变更（无实际审核内容）")
    return sha256_canonical(changes, canonicalization_version=canonicalization_version)


class DocumentHashes(BaseModel):
    """一次计算得到的全部 hash（payload 为整体身份；组件仅用于变化分类）。"""

    canonicalization_version: int = CANONICALIZATION_VERSION
    document_content_hash: str
    document_payload_hash: str
    tags_hash: str
    links_hash: str
    attachments_hash: str
    extra_metadata_hash: str
    governance_hash: str


def _subset(payload: Mapping[str, Any], keys: Sequence[str]) -> dict[str, Any]:
    """取**实际存在**的键构成子集（缺失 ≠ 空列表，二者组件 hash 不同）。"""
    return {key: payload[key] for key in keys if key in payload}


def compute_document_hashes(
    document: MarkdownDocument,
    *,
    canonicalization_version: int = CANONICALIZATION_VERSION,
) -> DocumentHashes:
    """确定性计算三 Hash 与组件 Hash（同文档多次计算字节一致）。"""
    payload = document.payload_fields()
    return DocumentHashes(
        canonicalization_version=canonicalization_version,
        document_content_hash=document_content_hash(
            document.content_fields(), canonicalization_version=canonicalization_version
        ),
        document_payload_hash=document_payload_hash(
            payload, canonicalization_version=canonicalization_version
        ),
        tags_hash=sha256_canonical(
            _subset(payload, ("tags",)), canonicalization_version=canonicalization_version
        ),
        links_hash=sha256_canonical(
            _subset(payload, ("links",)), canonicalization_version=canonicalization_version
        ),
        attachments_hash=sha256_canonical(
            _subset(payload, ("attachments",)),
            canonicalization_version=canonicalization_version,
        ),
        extra_metadata_hash=sha256_canonical(
            _subset(payload, ("extra_metadata",)),
            canonicalization_version=canonicalization_version,
        ),
        governance_hash=sha256_canonical(
            document.governance_fields(),
            canonicalization_version=canonicalization_version,
        ),
    )


def resolve_frontmatter_conflict(
    document: MarkdownDocument, resolution: FrontmatterResolution
) -> ConflictResolution:
    """用户主动解决 frontmatter 冲突（设计 §2.3，**不得由系统静默选择**）。

    NORMALIZE：丢弃原始块（用户授权），已知字段由实体再生、未知字段回写，
    无重复键 → NORMALIZED（恢复正常语义无损）。复杂未知值的 ``_raw`` 逐字兜底
    **保留**（否则未知字段会丢失）；已知键的 ``_raw``/``_conflict`` 丢弃并告警。

    KEEP_ORIGINAL：已知键以原始为准，实体修改不导出 + warning → 仍为 CONFLICT
    （「不保证实体修改写入交换文件」）。

    非冲突态调用为幂等 no-op（返回原文档，无告警）。
    """
    if document.frontmatter_state != FrontmatterState.CONFLICT:
        return ConflictResolution(document=document)

    warnings: list[CodecWarning] = []
    extra = dict(document.extra_metadata)

    if resolution == FrontmatterResolution.KEEP_ORIGINAL:
        warnings.append(
            CodecWarning(
                code=MarkdownWarningCode.KEEP_ORIGINAL_AUTHORITATIVE,
                message="用户选择保留原始 frontmatter：已知键以原始块为准。",
            )
        )
        warnings.append(
            CodecWarning(
                code=MarkdownWarningCode.ENTITY_EDITS_NOT_EXPORTED,
                message="实体已知字段的修改不会写入交换文件（原始块逐字回写）。",
            )
        )
        resolved = document.model_copy(
            update={"conflict_resolution": FrontmatterResolution.KEEP_ORIGINAL}
        )
        return ConflictResolution(document=resolved, warnings=warnings)

    raw_block = extra.pop("_frontmatter_raw", None)
    conflicts = extra.pop("_conflict", {})
    extra.pop("_duplicates", None)
    per_key_raw = dict(extra.get("_raw", {}))
    for key in list(per_key_raw):
        if key in KNOWN_FRONTMATTER_KEYS:
            per_key_raw.pop(key)
            warnings.append(
                CodecWarning(
                    code=MarkdownWarningCode.NORMALIZE_DISCARDS_RAW,
                    key=key,
                    message=f"已知键 {key} 的复杂原始值在规范化后由实体再生，原始片段已丢弃。",
                )
            )
    if per_key_raw:
        extra["_raw"] = per_key_raw
    else:
        extra.pop("_raw", None)

    if raw_block is not None:
        warnings.append(
            CodecWarning(
                code=MarkdownWarningCode.NORMALIZE_DISCARDS_RAW,
                message="用户授权规范化：原始 frontmatter 块已丢弃，已知字段由实体确定性再生。",
            )
        )
    for key in sorted(conflicts):
        warnings.append(
            CodecWarning(
                code=MarkdownWarningCode.KNOWN_TYPE_MISMATCH,
                key=key,
                message=f"已知键 {key} 原始值类型不符，规范化后以实体值再生（原始无效值已丢弃）。",
            )
        )
    if document.id is None:
        warnings.append(
            CodecWarning(
                code=MarkdownWarningCode.MISSING_STABLE_ID,
                key="id",
                message="规范化后文档仍无稳定 id：导入服务须分配/查重，不得静默覆盖既有知识。",
            )
        )

    resolved = document.model_copy(
        update={
            "extra_metadata": extra,
            "frontmatter_state": FrontmatterState.NORMALIZED,
            "conflict_resolution": FrontmatterResolution.NORMALIZE,
        }
    )
    return ConflictResolution(document=resolved, warnings=warnings)