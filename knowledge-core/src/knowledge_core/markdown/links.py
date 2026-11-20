"""Wikilink 纯文本层（V2 A1-03a，设计 §2.4 / 计划 §3① / §6.1 / §6.3）。

本模块**只做纯文本计算**：规范化、两个派生键、``[[标题|别名]]`` 解析与排除矩阵、
同键合并、frontmatter 绑定提示按标题键聚合。**零持久化、零网络、零文件 IO**，
不 import 任何端口/仓库/Session（分层红线，计划 §4.1）。

规范化规则 v1（设计 §2.4，与 A1-02 的 Hash 规范化**相互独立**）：
NFKC → strip → 连续空白折叠为单空格 → casefold（**不是 lower**）。
Hash 输入仍用原始 Unicode（A1-02 契约不变）；本模块的键是**派生索引**，
绝不进入交换载荷（计划 §5.3）。

两个键（D2）：
- ``normalized_link_key(title, alias)``：行身份键，持久化于链接行，
  同源唯一（A1-01 唯一约束），非空、≤1024 字符；空 alias → ``""``（不是 NULL）。
- ``normalized_title_key(title)``：解析匹配/提示分组用，**不持久化**、不进载荷。

版本化规则注册表（计划 §8.3.6 规则 7）：旧规则函数永久保留为可调用函数
（``normalize_link_text_v1`` 等），重建按 ``link_key_for_version`` 取规则重算；
v2 生产规则**本轮不发布**（仅测试夹具经注册表注入）。
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

__all__ = [
    "LINK_KEY_RULES",
    "MAX_ALIAS_CHARS",
    "MAX_KEY_CHARS",
    "MAX_TITLE_CHARS",
    "LinkHint",
    "LinkWarning",
    "LinkWarningCode",
    "ParsedWikilink",
    "WikilinkParser",
    "group_hints_by_title_key",
    "link_key_for_version",
    "merge_same_key",
    "normalize_link_text",
    "normalize_link_text_v1",
    "normalized_link_key",
    "normalized_link_key_v1",
    "normalized_title_key",
    "normalized_title_key_v1",
]

# 行身份键长度上限（A1-01 列宽；Core 层守卫保证 SQLite/PG 行为一致，R4）。
MAX_TITLE_CHARS = 500
MAX_ALIAS_CHARS = 500
MAX_KEY_CHARS = 1024

# 行身份键分隔符：标题规范化值 + \x1f + 别名规范化值（空别名 → ""）。
_KEY_SEPARATOR = "\x1f"

_WHITESPACE_RE = re.compile(r"\s+")


def _reject_control_chars(text: str) -> None:
    """控制字符守卫（防键注入）：拒绝除制表符外的 Cc 类字符（含 \\x1f/\\x00）。"""
    for ch in text:
        if ch != "\t" and unicodedata.category(ch) == "Cc":
            raise ValueError(f"链接字面含控制字符: U+{ord(ch):04X}")


def normalize_link_text_v1(s: str) -> str:
    """规范化规则 v1：NFKC → strip → 空白折叠 → casefold。

    必须 NFKC（不是 NFC）：全角/合字/圈码等兼容分解只有 NFKC 能合并。
    casefold（不是 lower）：ß→ss、Σ/ς/σ 等正确折叠。
    """
    return _WHITESPACE_RE.sub(" ", unicodedata.normalize("NFKC", s).strip()).casefold()


# 当前发布规则 = v1。将来 bump 时同步更新注册表与 LINK_NORMALIZATION_VERSION。
normalize_link_text = normalize_link_text_v1


def normalized_link_key_v1(title: str, alias: str | None) -> str:
    """行身份键 v1：``norm(title) + \\x1f + norm(alias or "")``。

    守卫：控制字符拒绝；标题规范化后为空拒绝；键长 >1024 拒绝（R4）。
    空 alias 落 ``""``（不落 NULL），保证双方言唯一约束语义一致。
    """
    _reject_control_chars(title)
    _reject_control_chars(alias or "")
    norm_title = normalize_link_text_v1(title)
    if not norm_title:
        raise ValueError("标题规范化后为空，不能构成链接键")
    norm_alias = normalize_link_text_v1(alias) if alias else ""
    key = norm_title + _KEY_SEPARATOR + norm_alias
    if len(key) > MAX_KEY_CHARS:
        raise ValueError(f"链接键长度 {len(key)} 超过上限 {MAX_KEY_CHARS}")
    return key


def normalized_title_key_v1(title: str) -> str:
    """解析标题键 v1：``norm(title) + \\x1f + ""``（D2：不持久化、不进载荷）。"""
    return normalized_link_key_v1(title, None)


normalized_link_key = normalized_link_key_v1
normalized_title_key = normalized_title_key_v1

# 版本化规则注册表：重建按目标版本取规则重算（旧规则永久保留，可回滚）。
# v2 生产规则本轮不发布；测试夹具可经 monkeypatch.setitem 注入。
LINK_KEY_RULES: dict[int, Callable[[str, str | None], str]] = {
    1: normalized_link_key_v1,
}


def link_key_for_version(version: int, title: str, alias: str | None) -> str:
    """按规则版本重算行身份键；未注册版本抛 ValueError（重建门禁拒绝）。"""
    rule = LINK_KEY_RULES.get(version)
    if rule is None:
        raise ValueError(f"未注册的链接规范化版本: {version}")
    return rule(title, alias)


class LinkWarningCode(StrEnum):
    """链接告警稳定码（计划 §6.3 / §6.5 / §6.6 / §8.3）。"""

    WIKILINK_UNCLOSED = "wikilink_unclosed"
    WIKILINK_EMPTY_TITLE = "wikilink_empty_title"
    WIKILINK_NESTED = "wikilink_nested"
    WIKILINK_CROSS_LINE = "wikilink_cross_line"
    WIKILINK_TOO_LONG = "wikilink_too_long"
    WIKILINK_KEY_TOO_LONG = "wikilink_key_too_long"
    WIKILINK_CONTROL_CHAR = "wikilink_control_char"
    WIKILINK_EMBED_EXCLUDED = "wikilink_embed_excluded"
    CONFLICTING_HINTS = "conflicting_hints"
    INVALID_HINT_NO_TARGET_ID = "invalid_hint_no_target_id"
    INVALID_HINT_MALFORMED_UUID = "invalid_hint_malformed_uuid"
    INVALID_HINT_TARGET_NOT_FOUND = "invalid_hint_target_not_found"
    ORPHAN_HINT = "orphan_hint"
    CROSS_SPACE_BINDING_RESTORED = "cross_space_binding_restored"
    ARCHIVED_TARGET_RESTORED = "archived_target_restored"
    REBUILD_COLLISION = "rebuild_collision"
    REBUILD_MIXED_VERSION = "rebuild_mixed_version"


class LinkWarning(BaseModel):
    """一条链接告警（稳定码 + 人读说明 + 原始信息保留）。

    冲突/跨空间等告警必须保留全部相关原始信息（title/alias/target_id），
    不得静默丢弃矛盾双方（问题 B / E2）。
    """

    model_config = ConfigDict(frozen=True)

    code: LinkWarningCode
    message: str
    title: str | None = None
    alias: str | None = None
    target_id: str | None = None
    target_ids: tuple[str, ...] = ()


class ParsedWikilink(BaseModel):
    """解析出的 wikilink 字面（原始 title/alias 永不覆盖）+ 行身份键。"""

    model_config = ConfigDict(frozen=True)

    title: str
    alias: str | None = None
    normalized_link_key: str


class LinkHint(BaseModel):
    """frontmatter ``links[]`` 绑定提示（交换形状子集；resolution 仅参考）。

    ``target_id`` 保留**原始文本**（可能非法 UUID），有效性判定在恢复服务；
    本模型不做 UUID 校验（无效 ≠ 矛盾，三类语义分离，计划 §6.5）。
    """

    title: str | None = None
    alias: str | None = None
    target_id: str | None = None
    resolution: str | None = None


def merge_same_key(links: Sequence[ParsedWikilink]) -> list[ParsedWikilink]:
    """同源同键多次书写合并为一行，**保留首现字面**（计划 §6.2）。

    确定性：输出按首现顺序；不修改输入。意图矛盾（不同 target 提示）的
    conflict 判定在恢复服务层（此处只有字面，无绑定意图）。
    """
    seen: set[str] = set()
    out: list[ParsedWikilink] = []
    for literal in links:
        if literal.normalized_link_key not in seen:
            seen.add(literal.normalized_link_key)
            out.append(literal)
    return out


def group_hints_by_title_key(hints: Sequence[LinkHint]) -> dict[str, list[LinkHint]]:
    """按 ``normalized_title_key`` 聚合**全部**提示（问题 B：先聚合再判定）。

    绝不 last-write-wins：同键所有提示完整保留，顺序无关。
    标题缺失/规范化为空/含控制字符的提示归入 ``""`` 组——正文标题键恒非空，
    该组永不匹配正文，恢复服务按孤儿提示处理（不建行 + warning）。
    """
    groups: dict[str, list[LinkHint]] = {}
    for hint in hints:
        try:
            key = normalized_title_key(hint.title) if hint.title else ""
        except ValueError:
            key = ""
        groups.setdefault(key, []).append(hint)
    return groups


_FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_BACKTICK_RUN_RE = re.compile(r"`+")
_EMBED = "!"


def _mask_inline_code(line: str) -> str:
    """把行内代码 `` `…` `` / `` ``…`` `` 区间掩为等长空格（保持偏移）。

    按 CommonMark 口径：开闭反引号串**等长**配对；未配对的反引号串保留字面。
    """
    runs = [(m.start(), m.end()) for m in _BACKTICK_RUN_RE.finditer(line)]
    chars = list(line)
    i = 0
    while i < len(runs):
        start, end = runs[i]
        length = end - start
        j = i + 1
        while j < len(runs) and runs[j][1] - runs[j][0] != length:
            j += 1
        if j < len(runs):
            for pos in range(start, runs[j][1]):
                chars[pos] = " "
            i = j + 1
        else:
            i += 1
    return "".join(chars)


def _has_control_char(text: str) -> bool:
    return any(ch != "\t" and unicodedata.category(ch) == "Cc" for ch in text)


class WikilinkParser:
    """``[[标题|别名]]`` 解析器（纯函数；确定性：同输入同输出，不修改输入）。

    排除矩阵（计划 §6.3）：围栏代码块（含 info string、更长外围栏嵌套）、
    行内代码、转义 ``\\[[``、未闭合、空标题、嵌套、跨行、原始字面 >500、
    键长 >1024、控制字符、``![[embed]]``（D6：排除 + warning，保留给 A1-04）。

    诚实局限（R7，取设计字面口径）：4 空格缩进代码块与 HTML 注释**不排除**。
    frontmatter 不在本层处理（调用方只传正文 body）。
    """

    @staticmethod
    def parse(body: str) -> tuple[list[ParsedWikilink], list[LinkWarning]]:
        """解析正文，返回（字面列表, 告警列表）。畸形构造不产生字面。"""
        literals: list[ParsedWikilink] = []
        warnings: list[LinkWarning] = []
        fence_char = ""
        fence_len = 0
        offset = 0
        for raw_line in body.split("\n"):
            line = raw_line.rstrip("\r")
            fence_match = _FENCE_OPEN_RE.match(line)
            if fence_char:
                # 围栏内：只找同字符、长度 >= 开栏、无 info string 的闭栏。
                if (
                    fence_match
                    and fence_match.group(1)[0] == fence_char
                    and len(fence_match.group(1)) >= fence_len
                    and not fence_match.group(2).strip()
                ):
                    fence_char = ""
                    fence_len = 0
                offset += len(raw_line) + 1
                continue
            if fence_match:
                fence_char = fence_match.group(1)[0]
                fence_len = len(fence_match.group(1))
                offset += len(raw_line) + 1
                continue
            WikilinkParser._parse_line(
                _mask_inline_code(line), body, offset, literals, warnings
            )
            offset += len(raw_line) + 1
        return literals, warnings

    @staticmethod
    def _parse_line(
        line: str,
        body: str,
        line_offset: int,
        literals: list[ParsedWikilink],
        warnings: list[LinkWarning],
    ) -> None:
        pos = 0
        while True:
            start = line.find("[[", pos)
            if start < 0:
                return
            # 转义：前置奇数个反斜杠 → 跳过（不告警，设计字面口径）。
            backslashes = 0
            j = start - 1
            while j >= 0 and line[j] == "\\":
                backslashes += 1
                j -= 1
            if backslashes % 2 == 1:
                pos = start + 2
                continue
            end = line.find("]]", start + 2)
            # 嵌入 ![[X]]：D6 排除 + warning（保留给附件嵌入 A1-04）。
            if start > 0 and line[start - 1] == _EMBED:
                raw = line[start + 2 : end] if end >= 0 else line[start + 2 :]
                warnings.append(
                    LinkWarning(
                        code=LinkWarningCode.WIKILINK_EMBED_EXCLUDED,
                        message=f"![[{raw}]] 为附件嵌入语法，排除出知识链接解析（保留给 A1-04）。",
                        title=raw or None,
                    )
                )
                pos = end + 2 if end >= 0 else len(line)
                continue
            if end < 0:
                # 未闭合 vs 跨行：向后找首个 ]]，其间含换行且无其它 [[ → 跨行。
                abs_start = line_offset + start + 2
                close = body.find("]]", abs_start)
                between = body[abs_start:close] if close >= 0 else ""
                code = (
                    LinkWarningCode.WIKILINK_CROSS_LINE
                    if close >= 0 and "\n" in between and "[[" not in between
                    else LinkWarningCode.WIKILINK_UNCLOSED
                )
                warnings.append(
                    LinkWarning(
                        code=code,
                        message=f"wikilink 未在本行闭合：[[{line[start + 2 :]}（畸形，不建行）。",
                    )
                )
                pos = start + 2
                continue
            content = line[start + 2 : end]
            if "[[" in content:
                warnings.append(
                    LinkWarning(
                        code=LinkWarningCode.WIKILINK_NESTED,
                        message=f"wikilink 嵌套：[[{content}]]（畸形，不建行）。",
                    )
                )
                pos = end + 2
                continue
            title_part, sep, alias_part = content.partition("|")
            alias_raw = alias_part if sep else None
            literal = WikilinkParser._build_literal(title_part, alias_raw, warnings)
            if literal is not None:
                literals.append(literal)
            pos = end + 2

    @staticmethod
    def _build_literal(
        title_raw: str, alias_raw: str | None, warnings: list[LinkWarning]
    ) -> ParsedWikilink | None:
        """字面守卫 + 键计算；任一守卫失败 → 对应稳定码告警，不产生字面。"""
        if not title_raw.strip() or not normalize_link_text(title_raw):
            warnings.append(
                LinkWarning(
                    code=LinkWarningCode.WIKILINK_EMPTY_TITLE,
                    message=f"wikilink 标题为空：[[{title_raw}|{alias_raw or ''}]]（畸形，不建行）。",
                    alias=alias_raw,
                )
            )
            return None
        if _has_control_char(title_raw) or _has_control_char(alias_raw or ""):
            warnings.append(
                LinkWarning(
                    code=LinkWarningCode.WIKILINK_CONTROL_CHAR,
                    message="wikilink 字面含控制字符（防键注入，畸形，不建行）。",
                    title=title_raw,
                    alias=alias_raw,
                )
            )
            return None
        if len(title_raw) > MAX_TITLE_CHARS or len(alias_raw or "") > MAX_ALIAS_CHARS:
            warnings.append(
                LinkWarning(
                    code=LinkWarningCode.WIKILINK_TOO_LONG,
                    message=(
                        f"wikilink 原始字面超长（title≤{MAX_TITLE_CHARS}、"
                        f"alias≤{MAX_ALIAS_CHARS}，畸形，不建行）。"
                    ),
                    title=title_raw[:64],
                    alias=None if alias_raw is None else alias_raw[:64],
                )
            )
            return None
        try:
            key = normalized_link_key(title_raw, alias_raw)
        except ValueError:
            warnings.append(
                LinkWarning(
                    code=LinkWarningCode.WIKILINK_KEY_TOO_LONG,
                    message=f"wikilink 规范化键超过 {MAX_KEY_CHARS} 字符（NFKC 扩展，畸形，不建行）。",
                    title=title_raw[:64],
                    alias=None if alias_raw is None else alias_raw[:64],
                )
            )
            return None
        return ParsedWikilink(title=title_raw, alias=alias_raw, normalized_link_key=key)