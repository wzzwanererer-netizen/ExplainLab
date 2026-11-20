"""A1-03a 纯文本层测试（计划 §7.3 / §12 A1-03a 门禁）。

覆盖：规范化 v1（NFKC/casefold/空白折叠 + NFC 反例）、两个键（D2）、
解析排除矩阵逐行（§6.3）、键长边界与控制字符守卫、同键合并（首现字面）、
提示聚合（问题 B：先聚合再判定、顺序无关、无 last-write-wins）、确定性。
"""

from __future__ import annotations

import unicodedata

import pytest

from knowledge_core.markdown.links import (
    LINK_KEY_RULES,
    MAX_KEY_CHARS,
    LinkHint,
    WikilinkParser,
    group_hints_by_title_key,
    link_key_for_version,
    merge_same_key,
    normalize_link_text,
    normalize_link_text_v1,
    normalized_link_key,
    normalized_link_key_v1,
    normalized_title_key,
)


def _codes(warnings) -> list[str]:
    return [w.code.value for w in warnings]


# --- 规范化 v1（§6.1）---


def test_nfkc_fullwidth_halfwidth_same_key() -> None:
    assert normalize_link_text("Ｆoo") == normalize_link_text("Foo") == "foo"
    assert normalized_title_key("Ｆoo") == normalized_title_key("Foo")


def test_nfkc_counterexample_nfc_would_not_merge() -> None:
    # NFC 反例：NFC 不分解全角 Ｆ，只有 NFKC 合并（证明必须 NFKC）。
    assert unicodedata.normalize("NFC", "Ｆoo") != "Foo"
    assert unicodedata.normalize("NFKC", "Ｆoo") == "Foo"
    assert normalize_link_text("Ｆoo") == "foo"


def test_ligature_and_circled_number() -> None:
    assert normalize_link_text("ﬁle") == normalize_link_text("file") == "file"
    assert normalize_link_text("①") == normalize_link_text("1") == "1"


def test_casefold_not_lower() -> None:
    assert normalize_link_text("Straße") == "strasse"  # lower 会保留 ß
    assert normalize_link_text("Σ") == normalize_link_text("ς") == normalize_link_text("σ")


def test_whitespace_collapse_and_strip() -> None:
    assert normalize_link_text("  A \t B  ") == "a b"
    assert normalize_link_text("A\n\nB") == "a b"


def test_normalize_empty_and_whitespace_only() -> None:
    assert normalize_link_text("") == ""
    assert normalize_link_text("   ") == ""


def test_v1_rule_kept_callable_and_registry() -> None:
    # 旧规则函数永久保留（回滚确定性重算依赖）；注册表 v1 与公共函数一致。
    assert normalize_link_text_v1("Ｆoo") == normalize_link_text("Ｆoo")
    assert LINK_KEY_RULES[1] is normalized_link_key_v1
    assert link_key_for_version(1, "B", "x") == normalized_link_key("B", "x")


def test_unsupported_version_rejected() -> None:
    with pytest.raises(ValueError, match="未注册"):
        link_key_for_version(99, "B", None)


# --- 两个键（D2 / §5.5）---


def test_row_key_vs_title_key_distinction() -> None:
    # [[B]] 与 [[B|别名]]：行身份键不同、解析标题键相同。
    assert normalized_link_key("B", None) != normalized_link_key("B", "别名")
    assert normalized_title_key("B") == normalized_link_key("B", None)
    assert normalized_title_key("B") == normalized_title_key("Ｂ")  # NFKC 同键


def test_empty_alias_is_empty_string_not_null() -> None:
    key = normalized_link_key("B", None)
    assert key.endswith("\x1f")
    assert key == normalized_link_key("B", "")
    assert "\x1f" in key and key.split("\x1f")[1] == ""


def test_key_length_boundary_1024_accepted_1025_rejected() -> None:
    assert len(normalized_link_key("a" * (MAX_KEY_CHARS - 1), None)) == MAX_KEY_CHARS
    with pytest.raises(ValueError, match="超过上限"):
        normalized_link_key("a" * MAX_KEY_CHARS, None)


def test_key_control_char_rejected() -> None:
    with pytest.raises(ValueError, match="控制字符"):
        normalized_link_key("a\x1fb", None)
    with pytest.raises(ValueError, match="控制字符"):
        normalized_link_key("B", "x\x00y")
    with pytest.raises(ValueError, match="控制字符"):
        normalized_title_key("a\x1fb")


def test_key_empty_title_rejected() -> None:
    with pytest.raises(ValueError, match="为空"):
        normalized_link_key("   ", None)
    with pytest.raises(ValueError, match="为空"):
        normalized_title_key("")


def test_original_literal_never_overwritten_by_parser() -> None:
    literals, warnings = WikilinkParser.parse("[[Ｆoo|Ｂar]]")
    assert not warnings
    assert literals[0].title == "Ｆoo"  # 原始字面保留
    assert literals[0].alias == "Ｂar"
    assert literals[0].normalized_link_key == normalized_link_key("Foo", "Bar")


# --- 解析排除矩阵（§6.3 逐行）---


def test_plain_and_aliased_links() -> None:
    literals, warnings = WikilinkParser.parse("见 [[B]] 与 [[B|别名]] 以及 [[C]]")
    assert not warnings
    assert [(lit.title, lit.alias) for lit in literals] == [
        ("B", None),
        ("B", "别名"),
        ("C", None),
    ]


def test_fenced_code_backtick_excluded() -> None:
    body = "前\n```\n[[X]]\n```\n后 [[Y]]"
    literals, warnings = WikilinkParser.parse(body)
    assert not warnings
    assert [lit.title for lit in literals] == ["Y"]


def test_fenced_code_tilde_and_info_string_excluded() -> None:
    body = "~~~python [[Info]]\n[[X]]\n~~~\n[[Y]]"
    literals, _ = WikilinkParser.parse(body)
    assert [lit.title for lit in literals] == ["Y"]


def test_longer_outer_fence_nesting() -> None:
    body = "````\n```\n[[Inner]]\n```\n````\n[[Outer]]"
    literals, _ = WikilinkParser.parse(body)
    assert [lit.title for lit in literals] == ["Outer"]


def test_inline_code_excluded_single_and_double_backtick() -> None:
    literals, _ = WikilinkParser.parse("`[[X]]` 与 ``[[Y]]`` 与 [[Z]]")
    assert [lit.title for lit in literals] == ["Z"]


def test_escaped_wikilink_skipped() -> None:
    literals, warnings = WikilinkParser.parse(r"\[[X]] 与 [[Y]]")
    assert not warnings
    assert [lit.title for lit in literals] == ["Y"]


def test_double_backslash_is_not_escape() -> None:
    literals, _ = WikilinkParser.parse("\\\\[[X]]")
    assert [lit.title for lit in literals] == ["X"]


def test_unclosed_wikilink_malformed() -> None:
    literals, warnings = WikilinkParser.parse("见 [[X")
    assert not literals
    assert _codes(warnings) == ["wikilink_unclosed"]


def test_empty_title_variants_malformed() -> None:
    for body in ("[[]]", "[[   ]]", "[[|alias]]"):
        literals, warnings = WikilinkParser.parse(body)
        assert not literals, body
        assert _codes(warnings) == ["wikilink_empty_title"], body


def test_nested_wikilink_malformed() -> None:
    literals, warnings = WikilinkParser.parse("[[A[[B]]]]")
    assert not literals
    assert _codes(warnings) == ["wikilink_nested"]


def test_cross_line_wikilink_malformed() -> None:
    literals, warnings = WikilinkParser.parse("[[A\nB]]")
    assert not literals
    assert _codes(warnings) == ["wikilink_cross_line"]


def test_raw_title_over_500_rejected_boundary_500_ok() -> None:
    literals, warnings = WikilinkParser.parse(f"[[{'a' * 501}]]")
    assert not literals
    assert _codes(warnings) == ["wikilink_too_long"]
    literals, warnings = WikilinkParser.parse(f"[[{'a' * 500}]]")
    assert len(literals) == 1 and not warnings


def test_raw_alias_over_500_rejected() -> None:
    literals, warnings = WikilinkParser.parse(f"[[B|{'a' * 501}]]")
    assert not literals
    assert _codes(warnings) == ["wikilink_too_long"]


def test_nfkc_expansion_key_over_1024_rejected() -> None:
    # ﷺ NFKC 展开为 18 字符：57 个字面 → 键 1027 > 1024（字面本身 ≤500）。
    assert len(unicodedata.normalize("NFKC", "ﷺ")) == 18
    literals, warnings = WikilinkParser.parse(f"[[{'ﷺ' * 57}]]")
    assert not literals
    assert _codes(warnings) == ["wikilink_key_too_long"]


def test_control_char_literals_rejected() -> None:
    for ch in ("\x1f", "\x00"):
        literals, warnings = WikilinkParser.parse(f"[[A{ch}B]]")
        assert not literals
        assert _codes(warnings) == ["wikilink_control_char"]
        literals, warnings = WikilinkParser.parse(f"[[B|a{ch}b]]")
        assert not literals
        assert _codes(warnings) == ["wikilink_control_char"]


def test_embed_excluded_with_warning_d6() -> None:
    literals, warnings = WikilinkParser.parse("![[X]] 与 [[Y]]")
    assert [lit.title for lit in literals] == ["Y"]
    assert _codes(warnings) == ["wikilink_embed_excluded"]


def test_honest_limitation_indented_code_not_excluded() -> None:
    # R7 诚实局限：4 空格缩进代码块不排除（设计字面口径，验收如实记录）。
    literals, _ = WikilinkParser.parse("    [[X]]")
    assert [lit.title for lit in literals] == ["X"]


def test_alias_pipe_split_first_only() -> None:
    literals, _ = WikilinkParser.parse("[[B|显示|更多]]")
    assert literals[0].alias == "显示|更多"


def test_title_whitespace_raw_preserved_key_folded() -> None:
    literals, _ = WikilinkParser.parse("[[  Title   X  ]]")
    assert literals[0].title == "  Title   X  "
    assert literals[0].normalized_link_key == normalized_link_key("Title X", None)


# --- 同键合并（§6.2）---


def test_merge_same_key_keeps_first_literal() -> None:
    literals, _ = WikilinkParser.parse("[[B|alias]] [[B|ALIAS]] [[B]]")
    merged = merge_same_key(literals)
    # [[B|alias]] 与 [[B|ALIAS]] 同键（casefold）→ 合并保留首现字面；[[B]] 键不同。
    assert len(merged) == 2
    assert merged[0].alias == "alias"
    assert merged[1].alias is None


def test_merge_same_key_order_and_no_mutation() -> None:
    literals, _ = WikilinkParser.parse("[[C]] [[B]] [[C]] [[A]]")
    before = list(literals)
    merged = merge_same_key(literals)
    assert [lit.title for lit in merged] == ["C", "B", "A"]
    assert literals == before


# --- 提示聚合（问题 B / §6.5）---


def test_group_hints_aggregates_all_not_last_write_wins() -> None:
    hints = [
        LinkHint(title="B", alias="x", target_id="t1"),
        LinkHint(title="B", alias="y", target_id="t2"),
        LinkHint(title="Ｂ", target_id="t3"),  # NFKC 同标题键
    ]
    groups = group_hints_by_title_key(hints)
    key = normalized_title_key("B")
    assert set(groups) == {key}
    assert len(groups[key]) == 3  # 全部保留，无 last-write-wins


def test_group_hints_order_independent() -> None:
    hints = [
        LinkHint(title="B", target_id="t1"),
        LinkHint(title="C", target_id="t2"),
        LinkHint(title="B", alias="a", target_id="t3"),
    ]
    forward = group_hints_by_title_key(hints)
    backward = group_hints_by_title_key(list(reversed(hints)))
    assert set(forward) == set(backward)
    for key in forward:
        assert sorted(h.model_dump_json() for h in forward[key]) == sorted(
            h.model_dump_json() for h in backward[key]
        )


def test_group_hints_empty_title_goes_to_orphan_bucket() -> None:
    groups = group_hints_by_title_key([LinkHint(title=None), LinkHint(title="  ")])
    assert set(groups) == {""}  # 正文标题键恒非空 → "" 组永不匹配 → 孤儿
    assert len(groups[""]) == 2


def test_group_hints_control_char_title_goes_to_orphan_bucket() -> None:
    groups = group_hints_by_title_key([LinkHint(title="a\x1fb", target_id="t")])
    assert set(groups) == {""}


# --- 确定性 ---


def test_parse_deterministic_and_input_unchanged() -> None:
    body = "# 标题\n见 [[B]] 与 [[C|别名]]\n```\n[[X]]\n```\n![[E]]"
    first = WikilinkParser.parse(body)
    second = WikilinkParser.parse(body)
    assert [lit.model_dump() for lit in first[0]] == [lit.model_dump() for lit in second[0]]
    assert [w.model_dump() for w in first[1]] == [w.model_dump() for w in second[1]]
    assert body == "# 标题\n见 [[B]] 与 [[C|别名]]\n```\n[[X]]\n```\n![[E]]"


def test_parse_empty_body() -> None:
    literals, warnings = WikilinkParser.parse("")
    assert literals == [] and warnings == []