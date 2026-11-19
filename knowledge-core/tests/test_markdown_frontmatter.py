"""零依赖保守 frontmatter 解析 / 确定性 emitter 单测（V2 A1-02，设计 §2.3 / §1.3）。

重点验证**诚实边界**：超范围构造原始兜底 + 告警，绝不静默丢数据或猜测语义；
以及 emitter 的确定性（固定键序、按需引号、不产生重复键）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from knowledge_core.markdown import KNOWN_FRONTMATTER_KEYS, MarkdownWarningCode
from knowledge_core.markdown.frontmatter import (
    UnsupportedYaml,
    emit_frontmatter,
    emit_inline,
    emit_scalar,
    parse_frontmatter,
    split_frontmatter,
)


class TestSplitFrontmatter:
    def test_plain_body_without_frontmatter(self):
        split = split_frontmatter("# 标题\n\n正文\n")
        assert split.raw_block is None
        assert split.body == "# 标题\n\n正文\n"
        assert not split.not_closed

    def test_basic_split_preserves_body_verbatim(self):
        split = split_frontmatter("---\ntitle: t\n---\n正文\n\n第二段\n")
        assert split.raw_block == "title: t"
        assert split.body == "正文\n\n第二段\n"

    def test_empty_body(self):
        split = split_frontmatter("---\ntitle: t\n---\n")
        assert split.raw_block == "title: t"
        assert split.body == ""

    def test_empty_frontmatter_block(self):
        split = split_frontmatter("---\n---\nbody")
        assert split.raw_block == ""
        assert split.body == "body"

    def test_dot_closing_delimiter_supported(self):
        split = split_frontmatter("---\ntitle: t\n...\nbody")
        assert split.raw_block == "title: t"
        assert split.body == "body"

    def test_unclosed_frontmatter_keeps_whole_text_as_body(self):
        text = "---\ntitle: t\n正文没有闭合分隔行\n"
        split = split_frontmatter(text)
        assert split.raw_block is None
        assert split.not_closed
        assert split.body == text  # 零丢失

    def test_leading_horizontal_rule_is_not_frontmatter(self):
        text = "---\n\n# 标题\n"
        split = split_frontmatter(text)
        assert split.not_closed
        assert split.body == text

    def test_body_containing_delimiter_line_is_preserved(self):
        text = "---\ntitle: t\n---\n正文\n---\n更多\n"
        split = split_frontmatter(text)
        assert split.raw_block == "title: t"
        assert split.body == "正文\n---\n更多\n"

    def test_bom_is_detected_and_removed(self):
        split = split_frontmatter("\ufeff---\ntitle: t\n---\nbody")
        assert split.bom_removed
        assert split.raw_block == "title: t"

    def test_crlf_delimiters_recognized(self):
        split = split_frontmatter("---\r\ntitle: t\r\n---\r\nbody\r\n")
        assert split.raw_block == "title: t\r"
        assert split.body == "body\r\n"


class TestScalarParsing:
    @pytest.mark.parametrize("token", ["null", "Null", "NULL", "~"])
    def test_null_tokens(self, token):
        assert parse_frontmatter(f"k: {token}").fields["k"] is None

    def test_missing_value_is_null(self):
        assert parse_frontmatter("k:").fields["k"] is None

    @pytest.mark.parametrize("token", ["true", "True", "TRUE"])
    def test_true_tokens(self, token):
        assert parse_frontmatter(f"k: {token}").fields["k"] is True

    @pytest.mark.parametrize("token", ["false", "False", "FALSE"])
    def test_false_tokens(self, token):
        assert parse_frontmatter(f"k: {token}").fields["k"] is False

    def test_integer(self):
        assert parse_frontmatter("version: 3").fields["version"] == 3
        assert parse_frontmatter("k: -7").fields["k"] == -7

    def test_decimal_not_float(self):
        value = parse_frontmatter("k: 1.50").fields["k"]
        assert isinstance(value, Decimal)
        assert value == Decimal("1.50")

    def test_scientific_notation_is_decimal(self):
        value = parse_frontmatter("k: 1e3").fields["k"]
        assert isinstance(value, Decimal)
        assert value == Decimal("1000")

    def test_double_quoted_escapes(self):
        parsed = parse_frontmatter(r'k: "a\nb\tc\\d\"e\u4e2d"')
        assert parsed.fields["k"] == 'a\nb\tc\\d"e中'

    def test_single_quoted_doubling(self):
        assert parse_frontmatter("k: 'it''s'").fields["k"] == "it's"

    def test_single_quoted_keeps_backslash_literal(self):
        assert parse_frontmatter(r"k: 'a\nb'").fields["k"] == "a\\nb"

    def test_plain_unicode_string(self):
        assert parse_frontmatter("title: 知识图谱的定义").fields["title"] == "知识图谱的定义"

    def test_trailing_comment_stripped_outside_quotes(self):
        parsed = parse_frontmatter("title: 值   # 注释")
        assert parsed.fields["title"] == "值"

    def test_hash_inside_quotes_is_not_comment(self):
        assert parse_frontmatter('k: "a # b"').fields["k"] == "a # b"

    def test_hash_without_preceding_space_is_literal(self):
        assert parse_frontmatter("k: a#b").fields["k"] == "a#b"

    def test_full_line_comment_ignored(self):
        parsed = parse_frontmatter("# 注释\nk: v\n\n# 另一条")
        assert parsed.fields == {"k": "v"}
        assert not parsed.structural_failure

    def test_quoted_number_stays_string(self):
        assert parse_frontmatter('k: "123"').fields["k"] == "123"

    def test_colon_inside_quoted_value(self):
        assert parse_frontmatter('k: "a: b"').fields["k"] == "a: b"


class TestCollectionParsing:
    def test_inline_flow_list(self):
        assert parse_frontmatter("tags: [概念, 图谱]").fields["tags"] == ["概念", "图谱"]

    def test_empty_flow_collections(self):
        parsed = parse_frontmatter("tags: []\nmeta: {}")
        assert parsed.fields["tags"] == []
        assert parsed.fields["meta"] == {}

    def test_flow_list_trailing_comma(self):
        assert parse_frontmatter("tags: [a, b,]").fields["tags"] == ["a", "b"]

    def test_flow_list_of_flat_maps(self):
        parsed = parse_frontmatter(
            "sources: [{type: conversation, conversation_id: c1, uri: null}]"
        )
        assert parsed.fields["sources"] == [
            {"type": "conversation", "conversation_id": "c1", "uri": None}
        ]

    def test_flow_map_with_list_value(self):
        assert parse_frontmatter("meta: {a: 1, b: [x, y]}").fields["meta"] == {
            "a": 1,
            "b": ["x", "y"],
        }

    def test_block_sequence_of_scalars(self):
        parsed = parse_frontmatter("tags:\n  - 概念\n  - 图谱\n")
        assert parsed.fields["tags"] == ["概念", "图谱"]

    def test_block_sequence_of_maps(self):
        parsed = parse_frontmatter(
            "sources:\n  - type: conversation\n    conversation_id: c1\n"
            "  - type: manual\n"
        )
        assert parsed.fields["sources"] == [
            {"type": "conversation", "conversation_id": "c1"},
            {"type": "manual"},
        ]

    def test_block_mapping(self):
        parsed = parse_frontmatter("meta:\n  a: 1\n  b: 文本\n")
        assert parsed.fields["meta"] == {"a": 1, "b": "文本"}

    def test_block_sequence_null_item(self):
        assert parse_frontmatter("k:\n  -\n  - a\n").fields["k"] == [None, "a"]

    def test_quoted_members_with_commas(self):
        assert parse_frontmatter('tags: ["a,b", c]').fields["tags"] == ["a,b", "c"]

    def test_nested_brackets_respected_when_splitting(self):
        # 深度 2 的集合成员其成员为标量 → 在保守范围内，切分须尊重嵌套括号。
        parsed = parse_frontmatter("k: [[a, b], {c: d}]")
        assert parsed.fields["k"] == [["a", "b"], {"c": "d"}]

    def test_depth_three_collection_is_out_of_range(self):
        parsed = parse_frontmatter("k: [[[a]]]")
        assert "k" in parsed.unsupported

    def test_raw_segment_includes_continuation_lines(self):
        parsed = parse_frontmatter("tags:\n  - a\n  - b\ntitle: t")
        assert parsed.raw_segments["tags"] == "tags:\n  - a\n  - b"
        assert parsed.raw_segments["title"] == "title: t"


class TestConservativeBoundary:
    """超范围构造 → 原始兜底 + 告警（【事实】非通用 YAML 解析器）。"""

    @pytest.mark.parametrize(
        "block",
        [
            "k: &anchor value",
            "k: *anchor",
            "k: !!str 1",
            "k: |",
            "k: >",
            "k: |-",
            "k: {a: {b: {c: 1}}}",
            "k:\n  a:\n    - 1\n",
            "k:\n  \t- a\n",
            'k: "未闭合',
            "k: [a, b",
            "k: {a: 1",
        ],
    )
    def test_unsupported_value_falls_back_to_raw(self, block):
        parsed = parse_frontmatter(block)
        assert "k" in parsed.unsupported
        assert parsed.unsupported["k"].startswith("k:")
        assert "k" not in parsed.fields
        assert any(
            warning.code == MarkdownWarningCode.UNKNOWN_COMPLEX_VALUE
            for warning in parsed.warnings
        )

    def test_known_key_complex_value_uses_known_code(self):
        parsed = parse_frontmatter("links: [{a: {b: {c: 1}}}]")
        assert "links" in parsed.unsupported
        assert any(
            warning.code == MarkdownWarningCode.KNOWN_COMPLEX_VALUE
            and warning.key == "links"
            for warning in parsed.warnings
        )

    def test_raw_fallback_is_verbatim(self):
        block = "k: |\n  第一行\n  第二行\n"
        parsed = parse_frontmatter(block)
        assert parsed.unsupported["k"] == "k: |\n  第一行\n  第二行"

    @pytest.mark.parametrize(
        "block",
        ["%YAML 1.2", "  orphan: 1", "not a mapping line", "k:value"],
    )
    def test_structural_failure_flagged(self, block):
        parsed = parse_frontmatter(block)
        assert parsed.structural_failure
        assert any(
            warning.code == MarkdownWarningCode.UNSUPPORTED_CONSTRUCT
            for warning in parsed.warnings
        )

    def test_structural_failure_does_not_lose_other_keys(self):
        parsed = parse_frontmatter("title: t\n  orphan: 1\nversion: 2")
        assert parsed.structural_failure
        assert parsed.fields["title"] == "t"
        assert parsed.fields["version"] == 2

    def test_unsupported_construct_inside_flow_map_falls_back(self):
        parsed = parse_frontmatter("k: {a, b}")
        assert "k" in parsed.unsupported
        assert "k" not in parsed.fields

    def test_tab_indented_line_is_structural_failure(self):
        parsed = parse_frontmatter("title: t\n\t- a\n")
        assert parsed.structural_failure
        assert parsed.fields["title"] == "t"


class TestDuplicateKeys:
    def test_last_value_wins_and_all_raw_values_recorded(self):
        parsed = parse_frontmatter("tags: [a]\ntags: [b]\ntags: [c]")
        assert parsed.fields["tags"] == ["c"]
        assert parsed.duplicates["tags"] == ["[a]", "[b]", "[c]"]
        assert sum(
            warning.code == MarkdownWarningCode.DUPLICATE_KEY
            for warning in parsed.warnings
        ) == 2

    def test_duplicate_unknown_key_records_warning_with_key(self):
        parsed = parse_frontmatter("custom: 1\ncustom: 2")
        assert parsed.fields["custom"] == 2
        assert parsed.duplicates["custom"] == ["1", "2"]
        assert any(
            warning.key == "custom" and warning.code == MarkdownWarningCode.DUPLICATE_KEY
            for warning in parsed.warnings
        )

    def test_duplicates_do_not_set_structural_failure(self):
        parsed = parse_frontmatter("k: 1\nk: 2")
        assert not parsed.structural_failure

    def test_flow_map_internal_duplicate_is_unsupported(self):
        parsed = parse_frontmatter("k: {a: 1, a: 2}")
        assert "k" in parsed.unsupported


class TestEmitter:
    def test_known_key_order_is_fixed(self):
        values = {"title": "t", "id": "i", "tags": ["a"], "status": "active"}
        block = emit_frontmatter(values)
        keys = [line.split(":", 1)[0] for line in block.split("\n")]
        assert keys == [key for key in KNOWN_FRONTMATTER_KEYS if key in values]

    def test_unknown_keys_sorted_after_known(self):
        block = emit_frontmatter({"title": "t", "zeta": 1, "alpha": 2})
        assert block.split("\n") == ["title: t", "alpha: 2", "zeta: 1"]

    def test_emission_is_deterministic_regardless_of_input_order(self):
        first = emit_frontmatter({"b": 1, "a": 2, "title": "t"})
        second = emit_frontmatter({"title": "t", "a": 2, "b": 1})
        assert first == second

    def test_empty_collections_emit_flow_not_scalar(self):
        assert emit_frontmatter({"tags": [], "meta": {}}) == "tags: []\nmeta: {}"

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (None, "null"),
            (True, "true"),
            (False, "false"),
            (3, "3"),
            (Decimal("1.50"), "1.5"),
            ("plain", "plain"),
            ("知识图谱", "知识图谱"),
            ("123", '"123"'),
            ("true", '"true"'),
            ("null", '"null"'),
            ("2026-11-17", '"2026-11-17"'),
            ("a,b", '"a,b"'),
            ("a: b", '"a: b"'),
            ("- item", '"- item"'),
            ("", '""'),
            (" leading", '" leading"'),
            ("a #b", '"a #b"'),
            ("a#b", "a#b"),
        ],
    )
    def test_scalar_emission(self, value, expected):
        assert emit_scalar(value) == expected

    def test_string_with_quotes_is_escaped(self):
        assert emit_scalar('say "hi"') == '"say \\"hi\\""'

    def test_control_characters_are_escaped(self):
        assert emit_scalar("a\nb\tc") == '"a\\nb\\tc"'

    def test_del_character_is_escaped_for_interop(self):
        assert emit_scalar("a\x7fb") == '"a\\u007fb"'

    def test_datetime_emits_fixed_utc_microseconds(self):
        assert emit_scalar(datetime(2026, 11, 17, 12, 0, tzinfo=UTC)) == (
            "2026-11-17T12:00:00.000000Z"
        )

    def test_uuid_emits_lowercase_string(self):
        assert emit_scalar(UUID("550E8400-E29B-41D4-A716-446655440000")) == (
            "550e8400-e29b-41d4-a716-446655440000"
        )

    def test_naked_float_refused(self):
        with pytest.raises(UnsupportedYaml, match="float"):
            emit_scalar(1.5)

    def test_unsupported_scalar_type_refused(self):
        with pytest.raises(UnsupportedYaml, match="不支持"):
            emit_scalar(object())

    def test_inline_map_keys_sorted(self):
        assert emit_inline({"b": 1, "a": 2}) == "{a: 2, b: 1}"

    def test_inline_nested_collections(self):
        assert emit_inline([{"type": "manual"}, ["x"]]) == "[{type: manual}, [x]]"

    def test_quoted_top_level_key_is_supported(self):
        parsed = parse_frontmatter('"my key": 值')
        assert parsed.fields == {"my key": "值"}
        assert not parsed.structural_failure

    def test_raw_override_written_verbatim_and_key_not_regenerated(self):
        block = emit_frontmatter(
            {"title": "再生标题", "custom": "会被忽略"},
            raw_overrides={"custom": "custom: |\n  原始第一行\n  原始第二行"},
        )
        assert block == "title: 再生标题\ncustom: |\n  原始第一行\n  原始第二行"
        assert block.count("custom:") == 1  # 绝不产生重复键

    def test_raw_override_for_known_key_not_duplicated(self):
        block = emit_frontmatter(
            {"title": "再生"}, raw_overrides={"title": "title: 原始"}
        )
        assert block == "title: 原始"
        assert block.count("title:") == 1


class TestParseEmitStability:
    @pytest.mark.parametrize(
        "block",
        [
            "title: 知识图谱的定义",
            "tags: [概念, 图谱]",
            "tags:\n  - 概念\n  - 图谱",
            "version: 3",
            "k: 1.50",
            "k: 'it''s'",
            'k: "a: b, c"',
            "sources: [{type: conversation, conversation_id: c1}]",
            "sources:\n  - type: manual\n    uri: null",
            "meta:\n  a: 1\n  b: 文本",
            "meta: {a: 1, b: [x, y]}",
            "tags: []",
            "k: null",
            "title: 值 # 注释",
        ],
    )
    def test_supported_constructs_survive_parse_emit_parse(self, block):
        first = parse_frontmatter(block)
        assert not first.unsupported, first.warnings
        emitted = emit_frontmatter(first.fields)
        second = parse_frontmatter(emitted)
        assert second.fields == first.fields
        assert not second.unsupported
        assert not second.structural_failure

    def test_complex_unknown_value_survives_via_raw_verbatim(self):
        block = "title: t\ncustom: |\n  第一行\n  第二行\n"
        first = parse_frontmatter(block)
        emitted = emit_frontmatter(first.fields, raw_overrides=first.unsupported)
        second = parse_frontmatter(emitted)
        assert second.fields == first.fields
        assert second.unsupported == first.unsupported

    def test_emitted_block_never_contains_duplicate_keys(self):
        block = "k: 1\nk: 2\ntitle: t"
        parsed = parse_frontmatter(block)
        emitted = emit_frontmatter(parsed.fields)
        keys = [line.split(":", 1)[0] for line in emitted.split("\n")]
        assert len(keys) == len(set(keys))