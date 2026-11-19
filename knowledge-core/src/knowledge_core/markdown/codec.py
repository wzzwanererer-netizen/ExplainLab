"""StdlibMarkdownCodec：零依赖 Markdown 交换编解码实现（V2 A1，设计 A1-T3）。

只依赖标准库 + Pydantic（**不引入 PyYAML**，未获批准）。保守解析边界见
knowledge_core.markdown.frontmatter 模块文档；三态冲突契约见 §2.3 口径 A。

不变量（本实现的核心安全保证）：
1. ``extra_metadata._frontmatter_raw`` 存在 ⟺ **冲突态**。原始块无法安全外科再生
   时逐字保留，导出器**拒绝同时再生原始块中的已知键**（绝不静默生成重复键）。
2. 冲突态未解决时，实体已知字段的修改**暂存实体、不写入交换文件** + 明确告警；
   此时**不得宣称完全无损往返**。
3. 复杂未知值经 ``_raw`` **逐字回写**（正常态语义无损）；诊断元键
   ``_duplicates``/``_conflict``/``_frontmatter_raw``/``_raw`` 不作为 frontmatter 键再生。
4. 正文（body）**逐字保真**，不做任何 Markdown 规范化/重排。
5. 解析失败一律降级兜底 + 告警，**绝不静默丢数据**。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from knowledge_core.domain.entities import KnowledgeStatus
from knowledge_core.markdown import (
    EXTRA_KEY_PREFIX,
    KNOWN_FRONTMATTER_KEYS,
    RESERVED_META_KEYS,
    CodecWarning,
    FrontmatterResolution,
    FrontmatterState,
    MarkdownCodec,
    MarkdownDocument,
    MarkdownWarningCode,
    ParsedMarkdown,
    RenderedMarkdown,
    decode_space,
    encode_space,
    resolve_frontmatter_conflict,
)
from knowledge_core.markdown.frontmatter import (
    emit_frontmatter,
    parse_frontmatter,
    split_frontmatter,
)

_SCALAR_KEYS = frozenset(
    {"id", "title", "space", "status", "version", "created_at", "updated_at"}
)
_COLLECTION_KEYS = frozenset({"tags", "sources", "links", "attachments"})


def _warn(
    code: MarkdownWarningCode, message: str, key: str | None = None
) -> CodecWarning:
    return CodecWarning(code=code, message=message, key=key)


def _read_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value)
    else:
        raise ValueError("时间戳必须是 ISO-8601 字符串")
    # naive 视为 UTC（与 canonical 规则一致），保证再生确定性。
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _coerce_known(key: str, value: Any) -> Any:
    """把已解析的原始值转换为交换文档字段；类型不符抛 ValueError（→ 冲突态）。"""
    if key in _COLLECTION_KEYS:
        if not isinstance(value, list):
            raise ValueError(f"{key} 必须是列表（null 亦属类型不符，缺失请省略该键）")
        if key == "tags":
            if not all(isinstance(item, str) for item in value):
                raise ValueError("tags 成员必须是字符串")
            return list(value)
        if not all(isinstance(item, dict) for item in value):
            raise ValueError(f"{key} 成员必须是映射（清单对象）")
        return [dict(item) for item in value]
    if value is None:
        return None
    if key == "id":
        if isinstance(value, UUID):
            return value
        if isinstance(value, str):
            return UUID(value)
        raise ValueError("id 必须是 UUID 字符串")
    if key == "title":
        if not isinstance(value, str):
            raise ValueError("title 必须是字符串")
        return value
    if key == "space":
        if not isinstance(value, str):
            raise ValueError("space 必须是 personal-null 或 project-<id>")
        return decode_space(value)
    if key == "status":
        if not isinstance(value, str):
            raise ValueError("status 必须是字符串")
        return KnowledgeStatus(value)
    if key == "version":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("version 必须是整数")
        return value
    if key in ("created_at", "updated_at"):
        return _read_datetime(value)
    raise ValueError(f"未知已知键 {key}")  # pragma: no cover - 防御


class StdlibMarkdownCodec(MarkdownCodec):
    """确定性 emitter + 保守解析器 + frontmatter 三态冲突（零新增依赖）。"""

    def parse(self, text: str) -> ParsedMarkdown:
        split = split_frontmatter(text)
        warnings: list[CodecWarning] = []
        if split.bom_removed:
            warnings.append(
                _warn(MarkdownWarningCode.BOM_REMOVED, "已移除 UTF-8 BOM（字节级变化，语义不变）。")
            )
        if split.raw_block is None:
            if split.not_closed:
                warnings.append(
                    _warn(
                        MarkdownWarningCode.FRONTMATTER_NOT_CLOSED,
                        "检测到起始 '---' 但无闭合分隔行：整段按正文逐字保留，不猜测 frontmatter。",
                    )
                )
            return ParsedMarkdown(
                document=MarkdownDocument(content=split.body),
                state=FrontmatterState.NORMAL,
                warnings=warnings,
                raw_frontmatter=None,
                body=split.body,
            )

        block = parse_frontmatter(split.raw_block)
        warnings.extend(block.warnings)
        kwargs: dict[str, Any] = {"content": split.body}
        extra: dict[str, Any] = {}
        conflicts: dict[str, str] = {}
        per_key_raw: dict[str, str] = {}
        conflict = False

        for key in KNOWN_FRONTMATTER_KEYS:
            if key in block.unsupported:
                conflicts[key] = block.raw_values.get(key, "")
                conflict = True
                continue
            if key not in block.fields:
                continue
            try:
                # 交换键 space ↔ 模型字段 space_id（其余同名）。
                field = "space_id" if key == "space" else key
                kwargs[field] = _coerce_known(key, block.fields[key])
            except (ValueError, KeyError) as exc:
                conflicts[key] = block.raw_values.get(key, "")
                conflict = True
                warnings.append(
                    _warn(
                        MarkdownWarningCode.KNOWN_TYPE_MISMATCH,
                        f"已知键 {key} 类型不符（{exc}）：原始值保留于 _conflict，不猜测语义。",
                        key,
                    )
                )

        for key, value in block.fields.items():
            if key not in KNOWN_FRONTMATTER_KEYS:
                extra[key] = value
        for key, segment in block.unsupported.items():
            if key not in KNOWN_FRONTMATTER_KEYS:
                per_key_raw[key] = segment
        if block.duplicates:
            extra["_duplicates"] = {
                key: list(values) for key, values in block.duplicates.items()
            }
        if conflicts:
            extra["_conflict"] = conflicts
        if per_key_raw:
            extra["_raw"] = per_key_raw

        if block.structural_failure:
            conflict = True
        if conflict:
            # 不变量 1：原始块逐字保留 ⟺ 冲突态。
            extra["_frontmatter_raw"] = split.raw_block
            warnings.append(
                _warn(
                    MarkdownWarningCode.FRONTMATTER_RAW_PRESERVED,
                    "原始 frontmatter 块已逐字保留于 extra_metadata._frontmatter_raw。",
                )
            )
            warnings.append(
                _warn(
                    MarkdownWarningCode.CONFLICT_REQUIRES_RESOLUTION,
                    "frontmatter 冲突未解决：需用户主动选择「规范化」或「保留原始」；"
                    "在此之前实体已知字段修改不会写入交换文件，不得称完全无损往返。",
                )
            )
        if extra:
            kwargs["extra_metadata"] = extra

        state = FrontmatterState.CONFLICT if conflict else FrontmatterState.NORMAL
        kwargs["frontmatter_state"] = state
        document = MarkdownDocument(**kwargs)
        return ParsedMarkdown(
            document=document,
            state=state,
            warnings=warnings,
            raw_frontmatter=split.raw_block,
            body=split.body,
        )

    def dump(
        self,
        document: MarkdownDocument,
        *,
        resolution: FrontmatterResolution | None = None,
    ) -> RenderedMarkdown:
        warnings: list[CodecWarning] = []
        state = document.frontmatter_state
        raw_block = document.extra_metadata.get("_frontmatter_raw")
        if raw_block is not None and state != FrontmatterState.CONFLICT:
            # 防御：不变量被外部破坏时保守升级为冲突态，绝不静默再生重复键。
            state = FrontmatterState.CONFLICT
            warnings.append(
                _warn(
                    MarkdownWarningCode.CONFLICT_REQUIRES_RESOLUTION,
                    "检测到 _frontmatter_raw 但状态非冲突：保守升级为冲突态。",
                )
            )

        if state == FrontmatterState.CONFLICT and resolution is not None:
            outcome = resolve_frontmatter_conflict(document, resolution)
            document = outcome.document
            warnings.extend(outcome.warnings)
            state = document.frontmatter_state
            raw_block = document.extra_metadata.get("_frontmatter_raw")

        if state == FrontmatterState.CONFLICT:
            warnings.append(
                _warn(
                    MarkdownWarningCode.CONFLICT_REQUIRES_RESOLUTION,
                    "frontmatter 冲突未解决：原始块逐字回写，拒绝再生其中的已知键（避免重复键）。",
                )
            )
            warnings.append(
                _warn(
                    MarkdownWarningCode.ENTITY_EDITS_NOT_EXPORTED,
                    "实体已知字段的修改尚未写入交换文件（待用户解决冲突）。",
                )
            )
            body = document.content
            text = f"---\n{raw_block}\n---\n{body}" if raw_block is not None else body
            return RenderedMarkdown(text=text, state=state, warnings=warnings)

        values, raw_overrides, collisions = self._exchange_values(document)
        warnings.extend(collisions)
        block = emit_frontmatter(values, raw_overrides=raw_overrides)
        text = f"---\n{block}\n---\n{document.content}" if block else document.content
        return RenderedMarkdown(text=text, state=state, warnings=warnings)

    def _exchange_values(
        self, document: MarkdownDocument
    ) -> tuple[dict[str, Any], dict[str, str], list[CodecWarning]]:
        """构造确定性再生用的已知键值 + 未知键逐字兜底 + 命名空间冲突告警。"""
        present = document.present_exchange_fields()
        values: dict[str, Any] = {
            key: present[key] for key in KNOWN_FRONTMATTER_KEYS if key in present
        }
        if "space" in values:
            values["space"] = encode_space(values["space"])

        extra = {
            key: value
            for key, value in document.extra_metadata.items()
            if key not in RESERVED_META_KEYS
        }
        per_key_raw = dict(document.extra_metadata.get("_raw", {}))
        warnings: list[CodecWarning] = []
        raw_overrides: dict[str, str] = {}
        for key in sorted(set(extra) | set(per_key_raw)):
            target = key
            if key in KNOWN_FRONTMATTER_KEYS:
                # 已知键保留命名空间：extra_metadata 同名 → x_explainlab_ 前缀 + 告警。
                target = EXTRA_KEY_PREFIX + key
                suffix = 2
                while target in extra or target in values or target in per_key_raw:
                    target = f"{EXTRA_KEY_PREFIX}{key}_{suffix}"
                    suffix += 1
                warnings.append(
                    _warn(
                        MarkdownWarningCode.KNOWN_KEY_COLLISION,
                        f"extra_metadata 键 {key} 与已知键同名：回写为 {target}（已知键保留命名空间）。",
                        key,
                    )
                )
            if key in per_key_raw:
                raw_overrides[target] = per_key_raw[key]
            else:
                values[target] = extra[key]
        return values, raw_overrides, warnings