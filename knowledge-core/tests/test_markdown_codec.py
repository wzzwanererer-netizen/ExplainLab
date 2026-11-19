"""StdlibMarkdownCodec 单测与导入/导出往返测试（V2 A1-02，设计 §2.2.3 / §2.3 / §2.6）。

覆盖：交换格式映射、正文逐字保真、确定性再生、语义无损往返（正常态）、
未知字段保留与复杂值原始兜底、**frontmatter 冲突三态**（原始保留 / 实体未写 /
用户显式规范化后恢复）、重复键、已知键命名空间冲突、告警稳定码，
以及三 Hash 在「同一文件重复导入」与「跨实例再生」下的幂等基础。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from knowledge_core.domain.entities import KnowledgeStatus
from knowledge_core.markdown import (
    EXTRA_KEY_PREFIX,
    KNOWN_FRONTMATTER_KEYS,
    FrontmatterResolution,
    FrontmatterState,
    MarkdownCodec,
    MarkdownDocument,
    MarkdownWarningCode,
    compute_document_hashes,
    decode_space,
    encode_space,
    resolve_frontmatter_conflict,
)
from knowledge_core.markdown.codec import StdlibMarkdownCodec

ITEM_ID = "550e8400-e29b-41d4-a716-446655440000"
TARGET_ID = "660e8400-e29b-41d4-a716-446655440000"

# 设计 §2.2.3 的交换格式示例（含未知字段与正文 wikilink / 附件引用）。
DESIGN_EXAMPLE = f"""---
id: {ITEM_ID}
title: 知识图谱的定义
tags: [概念, 图谱]
space: personal-null
status: active
version: 3
created_at: 2026-11-17T12:00:00Z
updated_at: 2026-11-17T12:30:00Z
sources: [{{type: conversation, conversation_id: c1, uri: null, excerpt: 片段}}]
links: [{{target_id: {TARGET_ID}, title: 知识表示, alias: null, resolution: resolved}}]
custom_field: 任意值
---
知识图谱是一种网络结构数据模型，参见 [[知识表示]] 与 [[本体论|本体]]。
![](attachments/abc123)
"""


@pytest.fixture()
def codec() -> StdlibMarkdownCodec:
    return StdlibMarkdownCodec()


def codes(warnings) -> list[str]:
    return [warning.code for warning in warnings]


def frontmatter_keys(text: str) -> list[str]:
    block = text.split("---\n")[1]
    return [
        line.split(":", 1)[0]
        for line in block.split("\n")
        if line and not line.startswith((" ", "\t", "#"))
    ]


class TestCodecContract:
    def test_interface_is_abstract(self):
        with pytest.raises(TypeError):
            MarkdownCodec()

    def test_impl_is_subclass_of_interface(self):
        assert issubclass(StdlibMarkdownCodec, MarkdownCodec)

    def test_space_encoding_roundtrip(self):
        assert encode_space(None) == "personal-null"
        assert encode_space("p1") == "project-p1"
        assert decode_space("personal-null") is None
        assert decode_space("project-p1") == "p1"

    @pytest.mark.parametrize("token", ["", "team-x", "project-", "personal"])
    def test_invalid_space_token_rejected(self, token):
        with pytest.raises(ValueError):
            decode_space(token)


class TestParseExchangeFormat:
    def test_design_example_maps_every_known_field(self, codec):
        parsed = codec.parse(DESIGN_EXAMPLE)
        document = parsed.document
        assert parsed.state == FrontmatterState.NORMAL
        assert parsed.warnings == []
        assert document.id == UUID(ITEM_ID)
        assert document.title == "知识图谱的定义"
        assert document.tags == ["概念", "图谱"]
        assert document.space_id is None
        assert document.status == KnowledgeStatus.ACTIVE
        assert document.version == 3
        assert document.created_at == datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
        assert document.updated_at == datetime(2026, 11, 17, 12, 30, tzinfo=UTC)
        assert document.sources == [
            {"type": "conversation", "conversation_id": "c1", "uri": None, "excerpt": "片段"}
        ]
        assert document.links == [
            {"target_id": TARGET_ID, "title": "知识表示", "alias": None, "resolution": "resolved"}
        ]
        assert document.extra_metadata == {"custom_field": "任意值"}

    def test_project_space_maps_to_space_id(self, codec):
        parsed = codec.parse("---\nspace: project-p1\n---\nbody")
        assert parsed.document.space_id == "p1"

    def test_attachments_manifest_is_known_exchange_field(self, codec):
        parsed = codec.parse(
            "---\nattachments: [{storage_key: aa, filename: 图.png, mime: image/png, "
            "size: 12, content_hash: aa}]\n---\n![](attachments/aa)\n"
        )
        assert parsed.state == FrontmatterState.NORMAL
        assert parsed.document.attachments == [
            {
                "storage_key": "aa",
                "filename": "图.png",
                "mime": "image/png",
                "size": 12,
                "content_hash": "aa",
            }
        ]

    def test_block_style_frontmatter_is_parsed(self, codec):
        parsed = codec.parse(
            "---\ntitle: t\ntags:\n  - 概念\n  - 图谱\nsources:\n"
            "  - type: manual\n    uri: null\n---\nbody"
        )
        assert parsed.document.tags == ["概念", "图谱"]
        assert parsed.document.sources == [{"type": "manual", "uri": None}]

    def test_missing_frontmatter_is_legacy_plaintext(self, codec):
        parsed = codec.parse("旧版纯文本正文，没有任何 frontmatter。\n第二行\n")
        assert parsed.state == FrontmatterState.NORMAL
        assert parsed.raw_frontmatter is None
        assert parsed.document.content == "旧版纯文本正文，没有任何 frontmatter。\n第二行\n"
        assert parsed.document.id is None
        assert parsed.document.title is None

    def test_naive_timestamp_is_normalized_to_utc(self, codec):
        parsed = codec.parse("---\ncreated_at: 2026-11-17T12:00:00\n---\nbody")
        assert parsed.document.created_at == datetime(2026, 11, 17, 12, 0, tzinfo=UTC)

    def test_offset_timestamp_is_converted_to_utc(self, codec):
        parsed = codec.parse("---\ncreated_at: 2026-11-17T20:00:00+08:00\n---\nbody")
        assert parsed.document.created_at == datetime(2026, 11, 17, 12, 0, tzinfo=UTC)


class TestBodyFidelity:
    @pytest.mark.parametrize(
        "body",
        [
            "正文 [[链接]] 与 [[目标|别名]]\n",
            "# 标题\n\n```python\nprint('[[不是链接]]')\n```\n",
            "![](attachments/abc)\n\n\\[[转义]]\n",
            "第一行\r\n第二行\r\n",
            "\n\n前置空行保留\n\n\n",
            "尾部无换行",
            "---\n正文里的分隔线\n---\n",
        ],
    )
    def test_body_is_preserved_verbatim(self, codec, body):
        parsed = codec.parse(f"---\ntitle: t\n---\n{body}")
        assert parsed.body == body
        assert parsed.document.content == body
        assert codec.dump(parsed.document).text.endswith(body)

    def test_legacy_plaintext_body_survives_roundtrip(self, codec):
        text = "旧正文\n\n## 小节\n内容\n"
        once = codec.dump(codec.parse(text).document)
        assert once.text == text
        assert codec.parse(once.text).document.content == text


class TestDeterministicEmission:
    def test_known_keys_in_fixed_order_unknown_sorted(self, codec):
        document = MarkdownDocument(
            title="t",
            id=UUID(ITEM_ID),
            tags=["a"],
            status=KnowledgeStatus.DRAFT,
            extra_metadata={"zeta": 1, "alpha": 2},
            content="body",
        )
        text = codec.dump(document).text
        assert frontmatter_keys(text) == [
            "id",
            "title",
            "tags",
            "status",
            "alpha",
            "zeta",
        ]

    def test_repeated_dump_is_byte_identical(self, codec):
        document = codec.parse(DESIGN_EXAMPLE).document
        assert len({codec.dump(document).text for _ in range(10)}) == 1

    def test_dict_insertion_order_does_not_change_output(self, codec):
        first = MarkdownDocument(
            content="b", extra_metadata={"b": 1, "a": 2}, title="t", tags=["x"]
        )
        second = MarkdownDocument(
            tags=["x"], title="t", extra_metadata={"a": 2, "b": 1}, content="b"
        )
        assert codec.dump(first).text == codec.dump(second).text

    def test_timestamps_regenerated_in_fixed_utc_microseconds(self, codec):
        text = codec.dump(codec.parse(DESIGN_EXAMPLE).document).text
        assert "created_at: 2026-11-17T12:00:00.000000Z" in text
        assert "updated_at: 2026-11-17T12:30:00.000000Z" in text

    def test_empty_frontmatter_document_emits_body_only(self, codec):
        assert codec.dump(MarkdownDocument(content="只有正文")).text == "只有正文"


class TestSemanticRoundtrip:
    def test_design_example_roundtrip_is_semantically_lossless(self, codec):
        first = codec.parse(DESIGN_EXAMPLE)
        rendered = codec.dump(first.document)
        second = codec.parse(rendered.text)
        assert second.state == FrontmatterState.NORMAL
        assert second.document.payload_hash() == first.document.payload_hash()
        assert second.document.content_hash() == first.document.content_hash()
        assert second.document.extra_metadata == first.document.extra_metadata
        assert second.document.content == first.document.content

    def test_byte_level_losslessness_is_not_claimed(self, codec):
        first = codec.parse(DESIGN_EXAMPLE)
        rendered = codec.dump(first.document)
        # 确定性再生会规范化时间戳精度/键序/引号 → 字节不同但语义相同。
        assert rendered.text != DESIGN_EXAMPLE
        assert codec.parse(rendered.text).document.payload_hash() == (
            first.document.payload_hash()
        )

    def test_roundtrip_is_stable_after_first_regeneration(self, codec):
        once = codec.dump(codec.parse(DESIGN_EXAMPLE).document).text
        twice = codec.dump(codec.parse(once).document).text
        assert once == twice

    @pytest.mark.parametrize(
        "frontmatter",
        [
            "title: null",
            "tags: []",
            "sources: []",
            "links: []",
            "attachments: []",
            "extra: {}",
            "version: 0",
            "status: draft",
            'title: "true"',
            "title: 2026-11-17",
            "custom: 1.50",
            "custom: 'it''s'",
            'custom: "a: b, c"',
            "custom: [x, y]",
            "custom: {a: 1, b: [x, y]}",
            "custom:\n  - a\n  - b",
            "custom:\n  a: 1\n  b: 文本",
        ],
    )
    def test_field_presence_and_values_survive_roundtrip(self, codec, frontmatter):
        text = f"---\n{frontmatter}\n---\n正文\n"
        first = codec.parse(text)
        assert first.state == FrontmatterState.NORMAL, codes(first.warnings)
        second = codec.parse(codec.dump(first.document).text)
        assert second.document.payload_fields() == first.document.payload_fields()
        assert second.document.payload_hash() == first.document.payload_hash()

    def test_null_is_not_confused_with_missing(self, codec):
        explicit = codec.parse("---\ntitle: null\n---\nc")
        missing = codec.parse("---\nversion: 1\n---\nc")
        assert "title" in explicit.document.payload_fields()
        assert explicit.document.payload_fields()["title"] is None
        assert "title" not in missing.document.payload_fields()
        assert explicit.document.payload_hash() != missing.document.payload_hash()
        assert "title: null" in codec.dump(explicit.document).text

    def test_empty_collection_is_not_confused_with_missing(self, codec):
        empty = codec.parse("---\ntags: []\n---\nc")
        missing = codec.parse("---\ntitle: t\n---\nc")
        assert empty.document.payload_fields()["tags"] == []
        assert "tags" not in missing.document.payload_fields()
        assert empty.document.payload_hash() != missing.document.payload_hash()

    def test_decimal_unknown_value_keeps_precision_through_roundtrip(self, codec):
        first = codec.parse("---\ncustom: 0.1000000000000000000000000001\n---\nc")
        second = codec.parse(codec.dump(first.document).text)
        assert second.document.extra_metadata == first.document.extra_metadata
        assert second.document.payload_hash() == first.document.payload_hash()


class TestUnknownFieldPreservation:
    def test_simple_unknown_fields_are_preserved_verbatim_in_value(self, codec):
        text = "---\ntitle: t\ncustom_a: 值\ncustom_b: [1, 2]\ncustom_c: {k: v}\n---\nc"
        first = codec.parse(text)
        assert first.document.extra_metadata == {
            "custom_a": "值",
            "custom_b": [1, 2],
            "custom_c": {"k": "v"},
        }
        second = codec.parse(codec.dump(first.document).text)
        assert second.document.extra_metadata == first.document.extra_metadata

    def test_complex_unknown_value_falls_back_to_raw_with_warning(self, codec):
        text = "---\ntitle: t\ncustom: |\n  第一行\n  第二行\n---\n正文\n"
        parsed = codec.parse(text)
        assert parsed.state == FrontmatterState.NORMAL  # 未知键逐字兜底仍语义无损
        assert MarkdownWarningCode.UNKNOWN_COMPLEX_VALUE in codes(parsed.warnings)
        assert parsed.document.extra_metadata["_raw"]["custom"] == (
            "custom: |\n  第一行\n  第二行"
        )

    def test_complex_unknown_value_roundtrips_verbatim(self, codec):
        text = "---\ntitle: t\ncustom: |\n  第一行\n  第二行\n---\n正文\n"
        first = codec.parse(text)
        rendered = codec.dump(first.document)
        assert "custom: |\n  第一行\n  第二行" in rendered.text
        second = codec.parse(rendered.text)
        assert second.document.extra_metadata == first.document.extra_metadata
        assert second.document.payload_hash() == first.document.payload_hash()

    def test_deep_nested_unknown_value_falls_back_to_raw(self, codec):
        text = "---\ncustom: {a: {b: {c: 1}}}\n---\nbody"
        parsed = codec.parse(text)
        assert "_raw" in parsed.document.extra_metadata
        assert codec.parse(codec.dump(parsed.document).text).document.extra_metadata == (
            parsed.document.extra_metadata
        )

    def test_diagnostic_meta_keys_are_never_emitted_as_frontmatter_keys(self, codec):
        text = "---\ntitle: t\ncustom: |\n  x\n---\nbody"
        rendered = codec.dump(codec.parse(text).document)
        keys = frontmatter_keys(rendered.text)
        for meta in ("_raw", "_frontmatter_raw", "_duplicates", "_conflict"):
            assert meta not in keys


class TestDuplicateKeys:
    def test_last_value_wins_and_all_values_recorded(self, codec):
        parsed = codec.parse("---\ncustom: 1\ncustom: 2\n---\nbody")
        assert parsed.document.extra_metadata["custom"] == 2
        assert parsed.document.extra_metadata["_duplicates"]["custom"] == ["1", "2"]
        assert codes(parsed.warnings).count(MarkdownWarningCode.DUPLICATE_KEY) == 1

    def test_regenerated_frontmatter_has_no_duplicate_keys(self, codec):
        parsed = codec.parse("---\ntitle: a\ntitle: b\ncustom: 1\ncustom: 2\n---\nbody")
        keys = frontmatter_keys(codec.dump(parsed.document).text)
        assert len(keys) == len(set(keys))
        assert parsed.document.title == "b"

    def test_same_source_file_reparses_to_same_payload_hash(self, codec):
        text = "---\ncustom: 1\ncustom: 2\n---\nbody"
        assert codec.parse(text).document.payload_hash() == (
            codec.parse(text).document.payload_hash()
        )


class TestKnownKeyNamespaceCollision:
    def test_extra_metadata_known_name_gets_prefix_and_warning(self, codec):
        document = MarkdownDocument(
            title="实体标题", content="body", extra_metadata={"title": "未知同名值"}
        )
        rendered = codec.dump(document)
        assert MarkdownWarningCode.KNOWN_KEY_COLLISION in codes(rendered.warnings)
        assert f"{EXTRA_KEY_PREFIX}title: 未知同名值" in rendered.text
        assert "title: 实体标题" in rendered.text
        keys = frontmatter_keys(rendered.text)
        assert len(keys) == len(set(keys))

    def test_prefixed_collision_gets_deterministic_suffix(self, codec):
        document = MarkdownDocument(
            title="实体标题",
            content="body",
            extra_metadata={"title": "值一", f"{EXTRA_KEY_PREFIX}title": "值二"},
        )
        rendered = codec.dump(document)
        assert f"{EXTRA_KEY_PREFIX}title_2: 值一" in rendered.text
        assert f"{EXTRA_KEY_PREFIX}title: 值二" in rendered.text
        keys = frontmatter_keys(rendered.text)
        assert len(keys) == len(set(keys))

    def test_collision_prefix_survives_roundtrip_as_unknown_field(self, codec):
        document = MarkdownDocument(
            title="实体标题", content="body", extra_metadata={"title": "未知同名值"}
        )
        second = codec.parse(codec.dump(document).text)
        assert second.document.title == "实体标题"
        assert second.document.extra_metadata[f"{EXTRA_KEY_PREFIX}title"] == "未知同名值"


class TestFrontmatterConflictThreeState:
    """设计 §2.3 口径 A：正常 / 冲突未解决 / 用户显式规范化后。"""

    @pytest.mark.parametrize(
        "frontmatter",
        [
            "id: not-a-uuid",
            "title: 123",
            "tags: 概念",
            "tags: [a, 1]",
            "status: published",
            "version: 三点五",
            "version: 3.0",
            "created_at: 昨天",
            "space: team-x",
            "sources: [a, b]",
            "links: {a: 1}",
            "attachments: 5",
        ],
    )
    def test_known_key_type_mismatch_enters_conflict(self, codec, frontmatter):
        parsed = codec.parse(f"---\n{frontmatter}\n---\n正文\n")
        assert parsed.state == FrontmatterState.CONFLICT
        assert MarkdownWarningCode.KNOWN_TYPE_MISMATCH in codes(parsed.warnings)
        assert MarkdownWarningCode.CONFLICT_REQUIRES_RESOLUTION in codes(parsed.warnings)
        key = frontmatter.split(":", 1)[0]
        assert key in parsed.document.extra_metadata["_conflict"]
        assert parsed.document.extra_metadata["_frontmatter_raw"] == frontmatter

    def test_known_key_complex_value_enters_conflict(self, codec):
        parsed = codec.parse("---\nlinks: [{a: {b: {c: 1}}}]\n---\nbody")
        assert parsed.state == FrontmatterState.CONFLICT
        assert MarkdownWarningCode.KNOWN_COMPLEX_VALUE in codes(parsed.warnings)
        assert "_frontmatter_raw" in parsed.document.extra_metadata

    def test_structural_failure_enters_conflict(self, codec):
        parsed = codec.parse("---\ntitle: t\n  orphan: 1\n---\nbody")
        assert parsed.state == FrontmatterState.CONFLICT
        assert parsed.document.title == "t"  # 可解析部分仍映射
        assert parsed.document.extra_metadata["_frontmatter_raw"] == "title: t\n  orphan: 1"

    def test_raw_block_presence_implies_conflict_invariant(self, codec):
        for text in (
            DESIGN_EXAMPLE,
            "---\nid: bad\n---\nb",
            "---\ntitle: t\n  orphan: 1\n---\nb",
            "---\ncustom: |\n  x\n---\nb",
        ):
            parsed = codec.parse(text)
            has_raw = "_frontmatter_raw" in parsed.document.extra_metadata
            assert has_raw == (parsed.state == FrontmatterState.CONFLICT)

    def test_unresolved_conflict_dump_preserves_raw_and_stages_entity_edits(self, codec):
        parsed = codec.parse(f"---\nid: {ITEM_ID}\nversion: 三点五\n---\n正文\n")
        edited = parsed.document.model_copy(update={"title": "实体新标题", "version": 9})
        rendered = codec.dump(edited)
        assert rendered.state == FrontmatterState.CONFLICT
        assert MarkdownWarningCode.ENTITY_EDITS_NOT_EXPORTED in codes(rendered.warnings)
        # 原始块逐字回写；实体修改**未**写入交换文件。
        assert rendered.text == f"---\nid: {ITEM_ID}\nversion: 三点五\n---\n正文\n"
        assert "实体新标题" not in rendered.text
        assert "version: 9" not in rendered.text

    def test_unresolved_conflict_never_emits_duplicate_known_keys(self, codec):
        parsed = codec.parse("---\ntitle: 原始\nversion: bad\n---\nbody")
        edited = parsed.document.model_copy(update={"title": "实体改"})
        rendered = codec.dump(edited)
        keys = frontmatter_keys(rendered.text)
        assert len(keys) == len(set(keys))
        assert keys.count("title") == 1

    def test_system_never_silently_normalizes(self, codec):
        parsed = codec.parse("---\nversion: bad\n---\nbody")
        rendered = codec.dump(parsed.document)  # 未给 resolution
        assert rendered.state == FrontmatterState.CONFLICT
        assert "_frontmatter_raw" in parsed.document.extra_metadata
        assert parsed.document.frontmatter_state == FrontmatterState.CONFLICT

    def test_user_normalize_regenerates_known_and_keeps_unknown(self, codec):
        text = (
            f"---\nid: {ITEM_ID}\ntitle: 原始标题\nversion: 三点五\n"
            "custom: 保留值\ncomplex: |\n  原始片段\n---\n正文\n"
        )
        parsed = codec.parse(text)
        edited = parsed.document.model_copy(update={"title": "实体新标题", "version": 9})
        rendered = codec.dump(edited, resolution=FrontmatterResolution.NORMALIZE)
        assert rendered.state == FrontmatterState.NORMALIZED
        assert MarkdownWarningCode.NORMALIZE_DISCARDS_RAW in codes(rendered.warnings)
        assert "title: 实体新标题" in rendered.text
        assert "version: 9" in rendered.text
        assert "custom: 保留值" in rendered.text
        assert "complex: |\n  原始片段" in rendered.text  # 复杂未知值仍逐字保留
        assert "_frontmatter_raw" not in rendered.text
        keys = frontmatter_keys(rendered.text)
        assert len(keys) == len(set(keys))

    def test_normalized_document_resumes_semantic_lossless_roundtrip(self, codec):
        parsed = codec.parse(f"---\nid: {ITEM_ID}\nversion: bad\ncustom: 值\n---\n正文\n")
        normalized = codec.dump(parsed.document, resolution=FrontmatterResolution.NORMALIZE)
        second = codec.parse(normalized.text)
        assert second.state == FrontmatterState.NORMAL
        third = codec.parse(codec.dump(second.document).text)
        assert third.document.payload_hash() == second.document.payload_hash()
        assert third.document.content_hash() == second.document.content_hash()

    def test_normalize_drops_invalid_known_raw_value_with_warning(self, codec):
        parsed = codec.parse("---\nversion: 三点五\n---\nbody")
        rendered = codec.dump(parsed.document, resolution=FrontmatterResolution.NORMALIZE)
        assert "version:" not in rendered.text  # 实体无 version → 不再生该键
        assert any(
            warning.code == MarkdownWarningCode.KNOWN_TYPE_MISMATCH
            and warning.key == "version"
            for warning in rendered.warnings
        )

    def test_normalize_without_stable_id_warns(self, codec):
        parsed = codec.parse("---\nid: not-a-uuid\n---\nbody")
        rendered = codec.dump(parsed.document, resolution=FrontmatterResolution.NORMALIZE)
        assert MarkdownWarningCode.MISSING_STABLE_ID in codes(rendered.warnings)

    def test_keep_original_makes_raw_authoritative_and_stages_edits(self, codec):
        parsed = codec.parse("---\ntitle: 原始\nversion: bad\n---\n正文\n")
        edited = parsed.document.model_copy(update={"title": "实体改"})
        rendered = codec.dump(edited, resolution=FrontmatterResolution.KEEP_ORIGINAL)
        assert rendered.state == FrontmatterState.CONFLICT
        assert MarkdownWarningCode.KEEP_ORIGINAL_AUTHORITATIVE in codes(rendered.warnings)
        assert MarkdownWarningCode.ENTITY_EDITS_NOT_EXPORTED in codes(rendered.warnings)
        assert rendered.text == "---\ntitle: 原始\nversion: bad\n---\n正文\n"

    def test_resolve_is_noop_outside_conflict(self, codec):
        document = codec.parse(DESIGN_EXAMPLE).document
        for resolution in FrontmatterResolution:
            outcome = resolve_frontmatter_conflict(document, resolution)
            assert outcome.document is document
            assert outcome.warnings == []

    def test_conflict_state_does_not_change_payload_hash(self, codec):
        parsed = codec.parse("---\nversion: bad\n---\nbody")
        # 状态是实例本地诊断；但 _frontmatter_raw 属 extra_metadata，参与身份。
        assert parsed.document.frontmatter_state == FrontmatterState.CONFLICT
        stripped = parsed.document.model_copy(
            update={
                "extra_metadata": {
                    k: v
                    for k, v in parsed.document.extra_metadata.items()
                    if k != "_frontmatter_raw"
                },
                "frontmatter_state": FrontmatterState.NORMAL,
            }
        )
        assert stripped.payload_hash() != parsed.document.payload_hash()

    def test_defensive_upgrade_when_raw_block_present_in_normal_state(self, codec):
        document = MarkdownDocument(
            title="t",
            content="body",
            extra_metadata={"_frontmatter_raw": "title: 原始"},
            frontmatter_state=FrontmatterState.NORMAL,
        )
        rendered = codec.dump(document)
        assert rendered.state == FrontmatterState.CONFLICT
        assert rendered.text == "---\ntitle: 原始\n---\nbody"


class TestUnclosedAndBom:
    def test_unclosed_frontmatter_keeps_whole_text_and_warns(self, codec):
        text = "---\ntitle: t\n正文没有闭合\n"
        parsed = codec.parse(text)
        assert parsed.state == FrontmatterState.NORMAL
        assert MarkdownWarningCode.FRONTMATTER_NOT_CLOSED in codes(parsed.warnings)
        assert parsed.document.content == text
        assert codec.dump(parsed.document).text == text

    def test_bom_removal_warns_and_keeps_semantics(self, codec):
        parsed = codec.parse("\ufeff" + DESIGN_EXAMPLE)
        assert MarkdownWarningCode.BOM_REMOVED in codes(parsed.warnings)
        assert parsed.document.payload_hash() == codec.parse(DESIGN_EXAMPLE).document.payload_hash()


class TestHashIdempotencyBasis:
    """§2.6.2 / §2.6.3：源 payload_hash 是幂等权威，目标再生不得污染它。"""

    def test_same_inbound_file_yields_same_source_payload_hash(self, codec):
        first = codec.parse(DESIGN_EXAMPLE).document
        second = codec.parse(DESIGN_EXAMPLE).document
        assert first.payload_hash() == second.payload_hash()
        assert first.content_hash() == second.content_hash()

    def test_cross_instance_regeneration_keeps_source_hash(self, codec):
        source = codec.parse(DESIGN_EXAMPLE).document
        source_hash = source.payload_hash()
        # 目标实例再生：status → draft、version → 1、timestamps → 导入时间。
        target = source.model_copy(
            update={
                "status": KnowledgeStatus.DRAFT,
                "version": 1,
                "created_at": datetime(2026, 11, 18, 9, 0, tzinfo=UTC),
                "updated_at": datetime(2026, 11, 18, 9, 0, tzinfo=UTC),
            }
        )
        assert target.payload_hash() != source_hash  # 目标自身身份已变
        assert codec.parse(DESIGN_EXAMPLE).document.payload_hash() == source_hash
        assert target.content_hash() == source.content_hash()  # 内容未变

    def test_reimport_of_own_export_is_skipped_by_source_hash(self, codec):
        source = codec.parse(DESIGN_EXAMPLE).document
        exported = codec.dump(source).text
        reimported = codec.parse(exported).document
        assert reimported.payload_hash() == source.payload_hash()

    def test_no_id_document_dedups_by_content_hash(self, codec):
        first = codec.parse("---\ntitle: 同标题\n---\n同正文\n").document
        second = codec.parse("---\ntitle: 同标题\n---\n同正文\n").document
        assert first.id is None and second.id is None
        assert first.content_hash() == second.content_hash()
        assert first.payload_hash() == second.payload_hash()

    def test_component_hashes_classify_change_kind(self, codec):
        base = codec.parse(DESIGN_EXAMPLE).document
        tags_changed = base.model_copy(update={"tags": ["概念", "图谱", "新标签"]})
        before, after = compute_document_hashes(base), compute_document_hashes(tags_changed)
        assert before.document_content_hash == after.document_content_hash
        assert before.document_payload_hash != after.document_payload_hash
        assert before.tags_hash != after.tags_hash
        assert before.links_hash == after.links_hash

    def test_all_known_keys_are_covered_by_payload_fields(self, codec):
        document = codec.parse(DESIGN_EXAMPLE).document
        payload = document.payload_fields()
        for key in KNOWN_FRONTMATTER_KEYS:
            if key == "attachments":
                continue  # 示例未含附件清单
            assert key in payload
        assert "extra_metadata" in payload
        assert "content" in payload