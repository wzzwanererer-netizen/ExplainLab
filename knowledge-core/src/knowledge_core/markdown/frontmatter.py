"""零依赖保守 frontmatter 解析 + 确定性 emitter（V2 A1，设计 §2.3 / §1.3）。

**诚实边界（【事实】，不得夸大）**：本模块只用标准库，覆盖**固定已知 schema +
简单未知值**，**不是通用 YAML 解析器**，不能完整解析任意 YAML。超出范围的构造
（锚点/别名/标签/块标量/深层嵌套/指令/Tab 缩进等）一律**原始文本兜底 + 告警**，
绝不静默丢弃或猜测语义。需要结构化理解任意 YAML 须另行审批 PyYAML（**暂不批准**）。

支持范围：
- 顶层 ``key: value``；标量（null/bool/int/Decimal/字符串，含单双引号与转义）；
- 流式集合 ``[a, b]`` / ``{k: v}``，以及块序列 ``- item`` / 块映射 ``  k: v``；
- 嵌套深度上限：顶层值(1) → 集合成员(2) → **仅标量**(3)。
  即 ``sources: [{type: ..., uri: ...}]`` 可读；``{a: {b: {c: 1}}}`` 不可读 → 兜底。
- 小数解析为 **Decimal**（不是 float）：hash 输入禁用裸 float（§2.6.1），
  Decimal 保留字面精度且可确定性序列化。

emitter 确定性：已知键按固定顺序、未知键按名称排序；标量按需加引号（避免被
其它 YAML 解析器误读为数字/布尔/日期）；集合用流式；复杂未知值按 ``_raw`` 逐字回写。
**语义无损（正常态），字节级不保证**。
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from knowledge_core.markdown import (
    KNOWN_FRONTMATTER_KEYS,
    CodecWarning,
    MarkdownWarningCode,
)
from knowledge_core.markdown.canonical import canonical_datetime, canonical_decimal

# 深度 >= 此值只接受标量：顶层值(1) → 集合成员(2) → 标量(3)。
_MAX_COLLECTION_DEPTH = 3

_KEY_LINE = re.compile(r"^([^\s:#][^:#]*?)\s*:(?:\s(.*))?$")
_INT = re.compile(r"^[+-]?\d+$")
_DECIMAL = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?$")
_DATEISH = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[Tt\s].*)?$")
_NULL_TOKENS = frozenset({"", "null", "Null", "NULL", "~"})
_TRUE_TOKENS = frozenset({"true", "True", "TRUE"})
_FALSE_TOKENS = frozenset({"false", "False", "FALSE"})
# YAML 指示字符：以其开头的plain标量必须加引号。
_INDICATORS = "-?:,[]{}#&*!|>'\"%@`"
_DOUBLE_ESCAPES = {
    "\\": "\\",
    '"': '"',
    "/": "/",
    "0": "\0",
    "a": "\a",
    "b": "\b",
    "t": "\t",
    "n": "\n",
    "v": "\v",
    "f": "\f",
    "r": "\r",
    "e": "\x1b",
    " ": " ",
    "N": "\x85",
    "_": "\xa0",
    "L": "\u2028",
    "P": "\u2029",
}


class UnsupportedYaml(ValueError):
    """超出保守解析范围（内部信号）：调用方据此原始兜底 + 告警，不丢数据。"""


class FrontmatterSplit(BaseModel):
    """正文与 frontmatter 原始块的切分结果（正文逐字保留）。"""

    raw_block: str | None = None
    body: str = ""
    bom_removed: bool = False
    not_closed: bool = False


class BlockParse(BaseModel):
    """frontmatter 块的保守解析结果。

    fields        成功解析的键值（已知 + 简单未知）。
    raw_values    键 → 最后一次出现的原始值文本（类型不符时进 ``_conflict``）。
    raw_segments  键 → 原始整段（含键行与续行），用于 ``_raw`` 逐字回写。
    unsupported   键 → 无法安全解析的原始整段。
    duplicates    键 → 全部出现的原始值文本（按出现顺序，取最后值生效）。
    structural_failure  整块存在无法归属/无法安全再生的结构 → 需 ``_frontmatter_raw``。
    """

    fields: dict[str, Any] = Field(default_factory=dict)
    raw_values: dict[str, str] = Field(default_factory=dict)
    raw_segments: dict[str, str] = Field(default_factory=dict)
    unsupported: dict[str, str] = Field(default_factory=dict)
    duplicates: dict[str, list[str]] = Field(default_factory=dict)
    warnings: list[CodecWarning] = Field(default_factory=list)
    structural_failure: bool = False


def split_frontmatter(text: str) -> FrontmatterSplit:
    """切分 ``---`` 包围的 frontmatter 与正文。

    无 frontmatter（V1 纯文本正文）→ raw_block=None，body 为全文逐字。
    有起始 ``---`` 但无闭合 → **不猜测**：整段当作正文 + not_closed 告警（零丢失）。
    """
    bom_removed = text.startswith("\ufeff")
    if bom_removed:
        text = text[1:]
    lines = text.split("\n")
    if not lines or lines[0].rstrip("\r") != "---":
        return FrontmatterSplit(body=text, bom_removed=bom_removed)
    for index in range(1, len(lines)):
        if lines[index].rstrip("\r") in ("---", "..."):
            return FrontmatterSplit(
                raw_block="\n".join(lines[1:index]),
                body="\n".join(lines[index + 1 :]),
                bom_removed=bom_removed,
            )
    return FrontmatterSplit(body=text, bom_removed=bom_removed, not_closed=True)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _strip_comment(text: str) -> str:
    """去掉引号外的 ``#`` 注释（``#`` 前须为空白或行首）。"""
    quote: str | None = None
    escaped = False
    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if quote == '"' and char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
            continue
        if char == "#" and (index == 0 or text[index - 1] in " \t"):
            return text[:index].rstrip()
    return text.rstrip()


def _read_quoted(token: str) -> tuple[str, str]:
    """读取起始引号字符串，返回 (字面值, 剩余文本)；不闭合 → UnsupportedYaml。"""
    quote = token[0]
    out: list[str] = []
    index = 1
    while index < len(token):
        char = token[index]
        if quote == "'":
            if char == "'":
                if index + 1 < len(token) and token[index + 1] == "'":
                    out.append("'")
                    index += 2
                    continue
                return "".join(out), token[index + 1 :].strip()
            out.append(char)
            index += 1
            continue
        if char == "\\":
            index += 1
            if index >= len(token):
                break
            esc = token[index]
            if esc in _DOUBLE_ESCAPES:
                out.append(_DOUBLE_ESCAPES[esc])
                index += 1
                continue
            if esc in ("x", "u", "U"):
                width = {"x": 2, "u": 4, "U": 8}[esc]
                digits = token[index + 1 : index + 1 + width]
                if len(digits) != width or not re.fullmatch(r"[0-9a-fA-F]+", digits):
                    raise UnsupportedYaml(f"双引号转义 \\{esc} 位数不足或非法")
                out.append(chr(int(digits, 16)))
                index += 1 + width
                continue
            raise UnsupportedYaml(f"不支持的双引号转义 \\{esc}")
        if char == '"':
            return "".join(out), token[index + 1 :].strip()
        out.append(char)
        index += 1
    raise UnsupportedYaml("引号字符串未闭合")


def _split_flow_items(inner: str) -> list[str]:
    """按顶层逗号切分流式集合成员（尊重引号与嵌套括号）。"""
    items: list[str] = []
    depth = 0
    quote: str | None = None
    escaped = False
    start = 0
    for index, char in enumerate(inner):
        if escaped:
            escaped = False
            continue
        if quote == '"' and char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        elif char == "," and depth == 0:
            items.append(inner[start:index])
            start = index + 1
    if quote:
        raise UnsupportedYaml("流式集合内引号未闭合")
    if depth != 0:
        raise UnsupportedYaml("流式集合括号不匹配")
    items.append(inner[start:])
    if items and not items[-1].strip():
        items.pop()  # 允许尾随逗号
    return [item.strip() for item in items]


def _split_key_value(text: str) -> tuple[str, str]:
    """切分 ``key: value``（键可为引号字符串）；无冒号分隔 → UnsupportedYaml。"""
    if text[:1] in ("'", '"'):
        key, rest = _read_quoted(text)
        if not rest.startswith(":"):
            raise UnsupportedYaml("流式映射成员缺少 ':' 分隔")
        return key, rest[1:].strip()
    match = _KEY_LINE.match(text)
    if not match:
        raise UnsupportedYaml(f"无法识别的映射成员: {text!r}")
    return match.group(1).strip(), (match.group(2) or "").strip()


def _parse_scalar(token: str) -> Any:
    """保守标量解析：null/bool/int/Decimal/引号字符串/plain 字符串。"""
    if token in _NULL_TOKENS:
        return None
    if token in _TRUE_TOKENS:
        return True
    if token in _FALSE_TOKENS:
        return False
    if token[:1] in ("'", '"'):
        value, rest = _read_quoted(token)
        if rest:
            raise UnsupportedYaml(f"引号字符串后有多余内容: {rest!r}")
        return value
    if token[:1] in ("&", "*", "!"):
        raise UnsupportedYaml("锚点/别名/标签超出保守解析范围")
    if _INT.fullmatch(token):
        return int(token)
    if _DECIMAL.fullmatch(token):
        try:
            return Decimal(token)
        except InvalidOperation as exc:  # pragma: no cover - 正则已保证可解析
            raise UnsupportedYaml(f"无法解析数值 {token!r}") from exc
    return token


def _parse_flow(token: str, depth: int) -> Any:
    if depth >= _MAX_COLLECTION_DEPTH:
        raise UnsupportedYaml("嵌套深度超出保守解析范围（集合成员只能是标量或一层扁平映射）")
    opener, closer = token[0], token[-1]
    if (opener, closer) not in (("[", "]"), ("{", "}")):
        raise UnsupportedYaml("流式集合未闭合")
    inner = token[1:-1].strip()
    if not inner:
        return [] if opener == "[" else {}
    items = _split_flow_items(inner)
    if opener == "[":
        return [_parse_inline(item, depth + 1) for item in items]
    out: dict[str, Any] = {}
    for item in items:
        key, value = _split_key_value(item)
        if key in out:
            raise UnsupportedYaml(f"流式映射内重复键 {key!r}（顶层重复键规则不适用于流式内部）")
        out[key] = _parse_inline(value, depth + 1)
    return out


def _parse_inline(token: str, depth: int) -> Any:
    token = _strip_comment(token.strip())
    if token[:1] in ("[", "{"):
        return _parse_flow(token, depth)
    if token[:1] in ("|", ">"):
        raise UnsupportedYaml("块标量（| / >）超出保守解析范围")
    return _parse_scalar(token)


def _parse_block_mapping(lines: Sequence[str], depth: int) -> dict[str, Any]:
    """块映射：所有行同缩进、均为 ``key: value``，值只能是标量或流式集合。"""
    if depth >= _MAX_COLLECTION_DEPTH:
        raise UnsupportedYaml("块映射嵌套深度超出保守解析范围")
    if not lines:
        raise UnsupportedYaml("空块映射")
    base = _indent(lines[0])
    out: dict[str, Any] = {}
    for line in lines:
        if not line.strip():
            continue
        if line.lstrip(" ").startswith("\t"):
            raise UnsupportedYaml("Tab 缩进超出保守解析范围")
        if _indent(line) != base:
            raise UnsupportedYaml("块映射缩进不一致或存在更深嵌套")
        key, value = _split_key_value(line.strip())
        if key in out:
            raise UnsupportedYaml(f"块映射内重复键 {key!r}")
        out[key] = _parse_inline(value, depth + 1)
    return out


def _parse_block_sequence(lines: Sequence[str], depth: int) -> list[Any]:
    """块序列：``- 标量`` 或 ``- key: value`` + 更深缩进的同项续行。"""
    if depth >= _MAX_COLLECTION_DEPTH:
        raise UnsupportedYaml("块序列嵌套深度超出保守解析范围")
    base = _indent(lines[0])
    items: list[Any] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if _indent(line) != base:
            raise UnsupportedYaml("块序列缩进不一致")
        stripped = line.strip()
        if stripped != "-" and not stripped.startswith("- "):
            raise UnsupportedYaml("块序列项必须以 '-' 开头")
        first = stripped[1:].strip()
        cursor = index + 1
        continuation: list[str] = []
        while cursor < len(lines) and (
            not lines[cursor].strip() or _indent(lines[cursor]) > base
        ):
            continuation.append(lines[cursor])
            cursor += 1
        while continuation and not continuation[-1].strip():
            continuation.pop()
        if continuation:
            if first.startswith("- "):
                raise UnsupportedYaml("嵌套块序列超出保守解析范围")
            pair_lines = ([first] if first else []) + [
                item.strip() for item in continuation
            ]
            items.append(_parse_block_mapping(pair_lines, depth + 1))
        elif first:
            # ``- key: value`` 单项映射（无续行）仍是映射，不是 plain 标量。
            if first[:1] not in ("[", "{") and _KEY_LINE.match(first):
                items.append(_parse_block_mapping([first], depth + 1))
            else:
                items.append(_parse_inline(first, depth + 1))
        else:
            items.append(None)
        index = cursor
    return items


def _is_block_scalar_indicator(text: str) -> bool:
    """``|`` / ``>``（含 chomping +/- 与显式缩进数字）——块标量指示符。"""
    return bool(re.fullmatch(r"[|>](?:[+-]?\d*|\d*[+-]?)", text))


def _parse_block_value(lines: Sequence[str], depth: int) -> Any:
    """顶层键后的缩进块：块序列或块映射。"""
    content = [line for line in lines if line.strip()]
    if not content:
        return None
    if any(line.lstrip(" ").startswith("\t") for line in content):
        raise UnsupportedYaml("Tab 缩进超出保守解析范围")
    if content[0].strip().startswith("- ") or content[0].strip() == "-":
        return _parse_block_sequence(content, depth)
    return _parse_block_mapping(content, depth)


def parse_frontmatter(raw_block: str) -> BlockParse:
    """保守解析 frontmatter 块；任何超范围构造都原始兜底 + 告警，绝不丢数据。"""
    result = BlockParse()
    lines = raw_block.split("\n")
    order: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        if line[:1] in (" ", "\t"):
            result.structural_failure = True
            result.warnings.append(
                CodecWarning(
                    code=MarkdownWarningCode.UNSUPPORTED_CONSTRUCT,
                    message=f"frontmatter 第 {index + 1} 行意外缩进，无法安全归属：{line.strip()!r}",
                )
            )
            index += 1
            continue
        if line.startswith("%"):
            result.structural_failure = True
            result.warnings.append(
                CodecWarning(
                    code=MarkdownWarningCode.UNSUPPORTED_CONSTRUCT,
                    message=f"YAML 指令超出保守解析范围：{line.strip()!r}",
                )
            )
            index += 1
            continue
        try:
            key, inline_value = _split_key_value(line)
        except UnsupportedYaml:
            result.structural_failure = True
            result.warnings.append(
                CodecWarning(
                    code=MarkdownWarningCode.UNSUPPORTED_CONSTRUCT,
                    message=f"frontmatter 第 {index + 1} 行无法识别为 'key: value'：{line.strip()!r}",
                )
            )
            index += 1
            continue
        cursor = index + 1
        continuation: list[str] = []
        stripped_value = _strip_comment(inline_value)
        # 空值 → 缩进块；块标量指示符（| / >）→ 其缩进内容属于该键，须一并逐字兜底。
        if not stripped_value or _is_block_scalar_indicator(stripped_value):
            while cursor < len(lines) and (
                not lines[cursor].strip() or _indent(lines[cursor]) > 0
            ):
                continuation.append(lines[cursor])
                cursor += 1
            while continuation and not continuation[-1].strip():
                continuation.pop()
            # 尾部空行不属于该键的原始片段（交回外层循环跳过）。
            cursor = index + 1 + len(continuation)
        segment = "\n".join(lines[index:cursor])
        value_text = "\n".join(part for part in [inline_value, *continuation] if part)

        if key not in order:
            order.append(key)
        else:
            result.duplicates.setdefault(key, [result.raw_values.get(key, "")]).append(
                value_text
            )
            result.warnings.append(
                CodecWarning(
                    code=MarkdownWarningCode.DUPLICATE_KEY,
                    key=key,
                    message=f"frontmatter 重复键 {key}：取最后值生效，全部原始值保留于 extra_metadata._duplicates。",
                )
            )
        result.raw_values[key] = value_text
        result.raw_segments[key] = segment

        try:
            if _is_block_scalar_indicator(stripped_value):
                raise UnsupportedYaml("块标量（| / >）超出保守解析范围")
            if continuation:
                parsed = _parse_block_value(continuation, 1)
            else:
                parsed = _parse_inline(inline_value, 1)
        except UnsupportedYaml as exc:
            result.unsupported[key] = segment
            result.fields.pop(key, None)
            code = (
                MarkdownWarningCode.KNOWN_COMPLEX_VALUE
                if key in KNOWN_FRONTMATTER_KEYS
                else MarkdownWarningCode.UNKNOWN_COMPLEX_VALUE
            )
            result.warnings.append(
                CodecWarning(
                    code=code,
                    key=key,
                    message=f"键 {key} 超出零依赖保守解析范围（{exc}）：原始文本逐字兜底，不做语义猜测。",
                )
            )
        else:
            result.fields[key] = parsed
            result.unsupported.pop(key, None)
        index = cursor
    return result


# --- 确定性 emitter ---


def _needs_quotes(text: str) -> bool:
    if text == "" or text != text.strip():
        return True
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in text):
        return True
    if text[0] in _INDICATORS:
        return True
    # 流式上下文分隔符与引号：plain 形式会破坏成员切分，必须加引号。
    if any(char in text for char in ":,[]{}\"'") or " #" in text or text.endswith("#"):
        return True
    if text in _NULL_TOKENS or text in _TRUE_TOKENS or text in _FALSE_TOKENS:
        return True
    return bool(
        _INT.fullmatch(text) or _DECIMAL.fullmatch(text) or _DATEISH.fullmatch(text)
    )


def _emit_string(text: str) -> str:
    if not _needs_quotes(text):
        return text
    # JSON 双引号转义是 YAML 双引号转义的子集；额外转义 DEL 提升互操作。
    return json.dumps(text, ensure_ascii=False).replace("\x7f", "\\u007f")


def emit_scalar(value: Any) -> str:
    """标量 → 确定性 YAML 文本（裸 float 拒绝，与 hash 规则一致）。"""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, float):
        raise UnsupportedYaml("拒绝再生裸 float（精度/平台差异）；请改用 Decimal")
    if isinstance(value, datetime):
        return canonical_datetime(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return emit_scalar(value.value)
    if isinstance(value, str):
        return _emit_string(value)
    raise UnsupportedYaml(f"不支持再生的标量类型: {type(value).__name__}")


def emit_inline(value: Any) -> str:
    """任意值 → 单行流式 YAML（集合嵌套用流式，保证可被其它工具读取）。"""
    if isinstance(value, Mapping):
        if not value:
            return "{}"
        members = [
            f"{_emit_string(str(key))}: {emit_inline(item)}"
            for key, item in sorted(value.items(), key=lambda kv: str(kv[0]))
        ]
        return "{" + ", ".join(members) + "}"
    if isinstance(value, (list, tuple)):
        if not value:
            return "[]"
        return "[" + ", ".join(emit_inline(item) for item in value) + "]"
    return emit_scalar(value)


def emit_frontmatter(
    values: Mapping[str, Any],
    *,
    raw_overrides: Mapping[str, str] | None = None,
) -> str:
    """再生 frontmatter 内块（不含 ``---`` 分隔行）。

    顺序确定：已知键按 KNOWN_FRONTMATTER_KEYS，其余键按名称排序。
    ``raw_overrides`` 中的键**逐字回写原始整段**（复杂未知值兜底），不再生该键，
    因此绝不会产生重复键。
    """
    overrides = dict(raw_overrides or {})
    known = [key for key in KNOWN_FRONTMATTER_KEYS if key in values or key in overrides]
    unknown = sorted((set(values) | set(overrides)) - set(KNOWN_FRONTMATTER_KEYS))
    lines: list[str] = []
    for key in [*known, *unknown]:
        if key in overrides:
            lines.append(overrides[key])
            continue
        value = values[key]
        if isinstance(value, (Mapping, list, tuple)):
            lines.append(f"{key}: {emit_inline(value)}")
        else:
            lines.append(f"{key}: {emit_scalar(value)}")
    return "\n".join(lines)