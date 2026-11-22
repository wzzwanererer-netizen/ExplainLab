"""Markdown 导入/导出编排的纯逻辑（V2 A1-04 Batch A；零 IO / 零方言）。

本模块承载可脱离数据库与文件系统验证的决策与传输适配原语：

- D22：``exporter_instance_id`` 仅传输元数据。导出时先算文档 Hash 再注入；
  导入时在 YAML 折叠前检测重复保留键、剥离传输位置、检测用户 metadata 占用。
- 交换文档 ↔ 字段映射的辅助函数（值规范化仍由 A1-02 codec/canonical 决定）。

Core 不 import backend / SQLAlchemy / FastAPI；所有 DB/文件事务在 backend。
"""

from __future__ import annotations

import json
import re
from typing import Any

from knowledge_core.markdown.canonical import CanonicalizationError

__all__ = [
    "EXPORTER_METADATA_RESERVED_CONFLICT",
    "EXPORTER_RESERVED_KEY",
    "SOURCE_IDENTITY_KEYS",
    "ExporterMetadataError",
    "extract_frontmatter_raw",
    "inject_exporter_instance_id",
    "scan_frontmatter_duplicate_keys",
    "split_exporter_metadata",
    "split_source_identity",
]

EXPORTER_RESERVED_KEY = "__explainlab_exporter_instance_id"
EXPORTER_METADATA_RESERVED_CONFLICT = "EXPORTER_METADATA_RESERVED_CONFLICT"
# 文档来源身份（D18）：交换 frontmatter 顶层键；导入时抽出、不落 extra_metadata。
SOURCE_IDENTITY_KEYS = ("source_instance_id", "source_document_id")


class ExporterMetadataError(CanonicalizationError):
    """保留传输键冲突（稳定码 ``EXPORTER_METADATA_RESERVED_CONFLICT``）。"""

    code = EXPORTER_METADATA_RESERVED_CONFLICT

    def __init__(self, reason: str) -> None:
        super().__init__(f"{EXPORTER_METADATA_RESERVED_CONFLICT}: {reason}")
        self.reason = reason


_KEY_LINE = re.compile(r"^(?P<key>[^\s:#][^:]*?)\s*:(?:\s|$)")


def _decode_key(raw: str) -> str:
    """把 frontmatter 键字面解码为字符串（双/单引号 + JSON 转义）。"""
    text = raw.strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        key = json.loads(text)
        if any(0xD800 <= ord(char) <= 0xDFFF for char in key):
            # 孤立代理项不是可用键：留给 codec 按非法构造处理。
            raise UnicodeDecodeError("utf-8", b"", 0, 1, "surrogate key")
        return key
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        return text[1:-1].replace("''", "'")
    return text


def scan_frontmatter_duplicate_keys(raw_block: str) -> list[str]:
    """在 YAML 映射折叠前扫描顶层重复键（含 ``"a"`` vs ``"\\u0061"``）。

    只识别顶层（无缩进、非注释）``key:`` 行；块内嵌套由 codec 保守处理。
    重复键（解码后相同）返回键列表，调用方 fail-closed。
    """
    seen: dict[str, int] = {}
    duplicates: list[str] = []
    for line in raw_block.splitlines():
        if not line or line[0] in " \t#-":
            # 顶层列表项/缩进/注释不参与键扫描；- 开头的标量块保持保守跳过。
            continue
        match = _KEY_LINE.match(line)
        if match is None:
            continue
        try:
            key = _decode_key(match.group("key"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # 键本身非法：保留给 codec 归入冲突态，不在此误判重复。
            continue
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 2:
            duplicates.append(key)
    return duplicates


def _contains_key(value: Any, key: str, *, depth: int = 0) -> bool:
    if depth > 32:
        return True
    if isinstance(value, dict):
        for child_key, child in value.items():
            if child_key == key or _contains_key(child, key, depth=depth + 1):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_key(child, key, depth=depth + 1) for child in value)
    return False


def split_exporter_metadata(
    extra_metadata: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    """剥离传输位置保留键，返回 (纯文档 metadata, exporter 值)。

    - 顶层保留键视为传输位置（导出注入），剥离。
    - 值不是字符串/空串 → 冲突（不得静默删除用户数据）。
    - 保留键出现在**嵌套用户 metadata 容器**内 → 冲突（D22 类型④）。
    """
    clean = dict(extra_metadata)
    present = EXPORTER_RESERVED_KEY in clean
    exporter = clean.pop(EXPORTER_RESERVED_KEY, None)
    if present and (not isinstance(exporter, str) or not exporter.strip()):
        raise ExporterMetadataError("保留键值必须是当前实例 ID 字符串")
    for key, value in clean.items():
        if _contains_key(value, EXPORTER_RESERVED_KEY):
            raise ExporterMetadataError(
                f"保留键出现在用户 metadata 容器内（键 {key!r}）；拒绝覆盖用户数据"
            )
    return clean, exporter


def assert_exporter_metadata_clean(extra_metadata: dict[str, Any]) -> None:
    """导出前检查：用户 DB metadata 不得占用/嵌套保留键（D22 类型①③）。"""
    if EXPORTER_RESERVED_KEY in extra_metadata:
        raise ExporterMetadataError(
            "用户 extra_metadata 已占用保留键；拒绝导出而不是静默删除"
        )
    for key, value in extra_metadata.items():
        if _contains_key(value, EXPORTER_RESERVED_KEY):
            raise ExporterMetadataError(
                f"保留键出现在用户 metadata 容器内（键 {key!r}）；拒绝导出"
            )


def extract_frontmatter_raw(text: str) -> str | None:
    """逐字取 frontmatter 块（不含首尾 ``---``），供折叠前重复键扫描。"""
    if text.startswith("\ufeff"):
        text = text[1:]
    if not text.startswith("---"):
        return None
    head_end = text.find("\n")
    if head_end == -1 or text[:head_end].strip() != "---":
        return None
    rest = text[head_end + 1 :]
    lines = rest.splitlines(keepends=True)
    offset = 0
    for line in lines:
        if line.strip() == "---":
            return rest[:offset]
        offset += len(line)
    return None


def split_source_identity(
    extra_metadata: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str | None]]:
    """从交换 metadata 抽出顶层来源身份键（顶层即传输位置，不落用户 metadata）。

    非字符串值抛 ``CanonicalizationError``（legacy/非法，调用方按 legacy 处理并报告）。
    """
    clean = dict(extra_metadata)
    identity: dict[str, str | None] = {}
    for key in SOURCE_IDENTITY_KEYS:
        if key not in clean:
            continue
        value = clean.pop(key)
        if value is not None and not isinstance(value, str):
            raise CanonicalizationError(f"{key} 必须是字符串或 null")
        identity[key] = value
    return clean, identity


def inject_exporter_instance_id(text: str, exporter_instance_id: str) -> str:
    """在 codec 再生后的文本中注入传输元数据（**不回流 Hash**）。

    有 frontmatter 时插在闭合 ``---`` 之前；无 frontmatter 时补一个只含该键的块。
    值使用双引号单行字符串，键为固定 ASCII 保留键。
    """
    line = f'{EXPORTER_RESERVED_KEY}: "{exporter_instance_id}"'
    if text.startswith("---\n"):
        closing = text.find("\n---\n", 4)
        if closing != -1:
            return f"{text[:closing]}\n{line}{text[closing:]}"
    return f"---\n{line}\n---\n{text}"