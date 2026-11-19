"""确定性规范化原语（V2 A1，设计 §1.4 / §2.6.1 第五轮 R5-5）。

零新增依赖：仅标准库（hashlib / json / datetime / decimal / uuid / enum）。
本模块只提供**序列化原语与语义排序助手**；三 Hash 的业务定义见
knowledge_core.markdown（document_content_hash / document_payload_hash /
review_payload_hash）。

canonicalization_version = 1 的规则（规则变更必须 bump 版本并重算 hash，
不同版本的 hash 不可直接比较）：

- canonical JSON：``sort_keys=True``、``ensure_ascii=False``、固定紧凑分隔符
  ``(",", ":")``（设计允许紧凑或带空格，此处**定其一为紧凑**），UTF-8 后 SHA-256。
- 包络显式携带版本：映射 → ``{"canonicalization_version": 1, **字段}``；
  非映射子集（如 tags 列表）→ ``{"canonicalization_version": 1, "value": ...}``。
- datetime → UTC 固定 6 位微秒 ``YYYY-MM-DDTHH:MM:SS.ffffffZ``；naive 视为 UTC；
  用显式格式化而非 strftime，避免平台/年份补零差异。
- Decimal → ``format(d, "f")`` 去尾零定字符串，**不经 float**（保留精度语义）。
- **裸 float 禁用**（平台 repr 差异）；需要小数请传 Decimal。
- **null ≠ 缺失**：只序列化调用方实际给出的键，绝不把缺失字段补成 null。
- 列表顺序：语义序列表用 ``sort_*`` 助手排序（含次级键保证全序）；顺序敏感
  列表保留原序——本模块**不擅自重排任何列表**。
- Unicode：hash 输入用**原始值**，不做 NFKC/casefold（规范化只用于链接键，
  见 markdown/links.py，A1-03）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from knowledge_core.domain.entities import CANONICALIZATION_VERSION

# 固定紧凑分隔符（设计 §2.6.1「定其一」）：确定性优先，字节最少。
CANONICAL_SEPARATORS: tuple[str, str] = (",", ":")

# 包络版本键为保留键，业务字段不得占用（否则包络会被覆盖）。
VERSION_KEY = "canonicalization_version"


class CanonicalizationError(ValueError):
    """规范化失败：不支持的类型 / 裸 float / 非字符串键 / 保留键冲突 / 版本不可比。"""


def canonical_datetime(value: datetime) -> str:
    """UTC 固定微秒表示；naive 时间视为 UTC（设计 §2.6.1）。"""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    value = value.astimezone(UTC)
    return (
        f"{value.year:04d}-{value.month:02d}-{value.day:02d}T"
        f"{value.hour:02d}:{value.minute:02d}:{value.second:02d}."
        f"{value.microsecond:06d}Z"
    )


def canonical_decimal(value: Decimal) -> str:
    """Decimal 定字符串：``format(d, 'f')`` 后去尾零，不经 float。

    ``1E+3`` → ``"1000"``；``0.000`` → ``"0"``；``-0.00`` → ``"0"``（负零归一）。
    NaN / Infinity 无确定语义，拒绝进入 hash。
    """
    if not value.is_finite():
        raise CanonicalizationError("Decimal 非有限值（NaN/Infinity）不得进入 hash 输入")
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in ("", "-"):
        text = "0"
    if text == "-0":
        text = "0"
    return text


def _normalize(value: Any) -> Any:
    """把输入递归转换为 canonical JSON 可表达的结构（不补缺失键、不重排列表）。"""
    # bool 必须先于 int 判断（bool 是 int 子类）。
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        raise CanonicalizationError(
            "hash 输入禁用裸 float（平台 repr 差异）；请改用 Decimal 定表示"
        )
    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, datetime):
        return canonical_datetime(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return _normalize(value.value)
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalizationError(
                    f"canonical 映射键必须是字符串，收到 {type(key).__name__}"
                )
            normalized[key] = _normalize(item)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    raise CanonicalizationError(f"不支持的 hash 输入类型: {type(value).__name__}")


def canonicalize(
    value: Any, *, canonicalization_version: int = CANONICALIZATION_VERSION
) -> dict[str, Any]:
    """构造带版本包络的 canonical 结构（设计 §2.6.1）。

    映射：字段平铺进包络（``{"canonicalization_version": 1, ...字段}``）。
    非映射：包一层 ``value``（组件子集如 tags 列表）。
    """
    if not isinstance(canonicalization_version, int) or isinstance(
        canonicalization_version, bool
    ):
        raise CanonicalizationError("canonicalization_version 必须是整数")
    if canonicalization_version < 1:
        raise CanonicalizationError("canonicalization_version 必须 >= 1")
    normalized = _normalize(value)
    if isinstance(normalized, dict):
        if VERSION_KEY in normalized:
            raise CanonicalizationError(
                f"业务字段不得占用保留键 {VERSION_KEY}（包络版本键）"
            )
        return {VERSION_KEY: canonicalization_version, **normalized}
    return {VERSION_KEY: canonicalization_version, "value": normalized}


def canonical_json(
    value: Any, *, canonicalization_version: int = CANONICALIZATION_VERSION
) -> str:
    """确定性 canonical JSON 文本（同输入多次计算字节一致）。"""
    return json.dumps(
        canonicalize(value, canonicalization_version=canonicalization_version),
        sort_keys=True,
        ensure_ascii=False,
        separators=CANONICAL_SEPARATORS,
        allow_nan=False,
    )


def sha256_canonical(
    value: Any, *, canonicalization_version: int = CANONICALIZATION_VERSION
) -> str:
    """canonical JSON 的 UTF-8 SHA-256（小写十六进制）。"""
    payload = canonical_json(
        value, canonicalization_version=canonicalization_version
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def hashes_comparable(source_version: int, target_version: int) -> bool:
    """不同 canonicalization_version 的 hash **不可直接比较**（设计 §2.6.1/§2.6.3）。"""
    return source_version == target_version


def require_comparable_versions(source_version: int, target_version: int) -> None:
    """版本不一致时抛错，调用方须降级为字段级判定并重算（不得静默比对）。"""
    if not hashes_comparable(source_version, target_version):
        raise CanonicalizationError(
            f"canonicalization_version 不一致（源 {source_version} / 目标 {target_version}）："
            "hash 不可直接比较，须按字段级降级判定并重算"
        )


# --- 语义序列表排序（含次级键保证全序；不修改原字典，只决定顺序） ---


def sort_tags(tags: Sequence[str]) -> list[str]:
    """tags 按 casefold 名排序，次级键用原始字面保证全序（大小写变体相邻且稳定）。"""
    return sorted(tags, key=lambda tag: (tag.casefold(), tag))


def _text(value: Any) -> str:
    """排序键用的稳定文本化：None/缺失统一为空串（**不影响 payload 中的存在性**）。"""
    if value is None:
        return ""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def sort_links(links: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """links 按 normalized_link_key 排序；次级键 target_id/title/alias/resolution。

    键缺失（A1-02 阶段链接尚未规范化）时回退 title，仍保证全序与确定性。
    """

    def key(link: Mapping[str, Any]) -> tuple[str, ...]:
        return (
            _text(link.get("normalized_link_key")) or _text(link.get("title")),
            _text(link.get("target_id")),
            _text(link.get("title")),
            _text(link.get("alias")),
            _text(link.get("resolution")),
        )

    return sorted(links, key=key)


def sort_attachments(
    attachments: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    """attachments 按 content_hash 排序；次级键 storage_key/filename/mime/size。"""

    def key(att: Mapping[str, Any]) -> tuple[str, ...]:
        return (
            _text(att.get("content_hash")),
            _text(att.get("storage_key")),
            _text(att.get("filename")),
            _text(att.get("mime")),
            _text(att.get("size")),
        )

    return sorted(attachments, key=key)


def sort_sources(sources: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """sources 按稳定键排序：type/conversation_id/uri/excerpt，次级键 id。"""

    def key(src: Mapping[str, Any]) -> tuple[str, ...]:
        return (
            _text(src.get("type") or src.get("source_type")),
            _text(src.get("conversation_id")),
            _text(src.get("uri")),
            _text(src.get("excerpt")),
            _text(src.get("id")),
        )

    return sorted(sources, key=key)