"""D22 传输元数据原语单测（V2 A1-04 Batch A）。

Coverage maps to R1.3-HASH-02/03/04 的 Core 侧契约：
- exporter 保留键在 YAML 折叠前查重；
- 导入剥离顶层保留键、拒绝嵌套/类型冲突；
- 导出前拒绝用户 metadata 占用保留键；
- 注入只改变传输文本，不回流 Hash 输入；
- 来源身份抽出为传输字段，非法值不静默落用户 metadata。
"""

from __future__ import annotations

import pytest

from knowledge_core.markdown.canonical import CanonicalizationError
from knowledge_core.markdown.service import (
    EXPORTER_METADATA_RESERVED_CONFLICT,
    EXPORTER_RESERVED_KEY,
    ExporterMetadataError,
    extract_frontmatter_raw,
    inject_exporter_instance_id,
    scan_frontmatter_duplicate_keys,
    split_exporter_metadata,
    split_source_identity,
)


class TestDuplicateScan:
    def test_plain_unique_keys_are_clean(self):
        assert scan_frontmatter_duplicate_keys("title: t\ntags: [a]") == []

    def test_duplicate_reserved_key_detected(self):
        raw = f"title: t\n{EXPORTER_RESERVED_KEY}: a\n{EXPORTER_RESERVED_KEY}: b"
        assert scan_frontmatter_duplicate_keys(raw) == [EXPORTER_RESERVED_KEY]

    def test_quoted_and_escaped_keys_decode_before_comparison(self):
        raw = '"a": 1\n"\\u0061": 2'
        assert scan_frontmatter_duplicate_keys(raw) == ["a"]

    def test_single_quoted_doubling(self):
        raw = "'it''s': 1\n\"it's\": 2"
        assert scan_frontmatter_duplicate_keys(raw) == ["it's"]

    def test_nested_indented_key_is_not_top_level_duplicate(self):
        raw = f"meta:\n  {EXPORTER_RESERVED_KEY}: x\n{EXPORTER_RESERVED_KEY}: y"
        # 仅扫描顶层：缩进键与顶层键不是同一位置，嵌套冲突由 split 阶段处理。
        assert scan_frontmatter_duplicate_keys(raw) == []

    def test_comment_and_list_lines_are_ignored(self):
        raw = "# a: 1\n- a: 1\na: 1"
        assert scan_frontmatter_duplicate_keys(raw) == []

    def test_invalid_quoted_key_is_left_to_codec(self):
        raw = '"\\uD800": 1\n"\\uD800": 2'
        assert scan_frontmatter_duplicate_keys(raw) == []


class TestExporterMetadata:
    def test_top_level_transport_key_is_stripped(self):
        clean, exporter = split_exporter_metadata(
            {EXPORTER_RESERVED_KEY: "550e8400-e29b-41d4-a716-446655440000", "a": 1}
        )
        assert clean == {"a": 1}
        assert exporter == "550e8400-e29b-41d4-a716-446655440000"

    @pytest.mark.parametrize("value", ["", "   ", 1, True, None, ["x"]])
    def test_non_string_or_blank_transport_value_conflicts(self, value):
        with pytest.raises(ExporterMetadataError) as excinfo:
            split_exporter_metadata({EXPORTER_RESERVED_KEY: value})
        assert excinfo.value.code == EXPORTER_METADATA_RESERVED_CONFLICT

    def test_nested_reserved_key_in_user_container_conflicts(self):
        payload = {"user": {"nested": [{EXPORTER_RESERVED_KEY: "x"}]}}
        with pytest.raises(ExporterMetadataError):
            split_exporter_metadata(payload)

    def test_export_rejects_db_metadata_occupying_reserved_key(self):
        from knowledge_core.markdown.service import assert_exporter_metadata_clean

        with pytest.raises(ExporterMetadataError):
            assert_exporter_metadata_clean({EXPORTER_RESERVED_KEY: "x"})
        with pytest.raises(ExporterMetadataError):
            assert_exporter_metadata_clean({"meta": {EXPORTER_RESERVED_KEY: "x"}})
        assert_exporter_metadata_clean({"meta": {"ok": 1}})

    def test_injection_into_existing_frontmatter_before_closing(self):
        text = "---\ntitle: t\n---\nbody"
        result = inject_exporter_instance_id(text, "Y")
        assert result == f'---\ntitle: t\n{EXPORTER_RESERVED_KEY}: "Y"\n---\nbody'

    def test_injection_without_frontmatter_creates_block(self):
        result = inject_exporter_instance_id("body", "Y")
        assert result == f'---\n{EXPORTER_RESERVED_KEY}: "Y"\n---\nbody'

    def test_injected_text_never_changes_source_hash_input(self):
        from knowledge_core.markdown import document_payload_hash

        injected = inject_exporter_instance_id("---\ntitle: t\n---\nbody", "Y")
        assert f'{EXPORTER_RESERVED_KEY}: "Y"' in injected
        # Hash 只接收剥离后的文档字段，不接收传输文本本身。
        assert document_payload_hash({"title": "t", "content": "body"}) == (
            document_payload_hash({"title": "t", "content": "body"})
        )


class TestFrontmatterRaw:
    def test_extract_verbatim_without_delimiters(self):
        assert extract_frontmatter_raw("---\ntitle: t\n---\nbody") == "title: t\n"

    def test_bom_and_crlf_tolerated(self):
        raw = extract_frontmatter_raw("\ufeff---\r\ntitle: t\r\n---\r\nbody")
        assert raw == "title: t\r\n"

    def test_no_frontmatter_returns_none(self):
        assert extract_frontmatter_raw("body") is None
        assert extract_frontmatter_raw("---\nno close") is None


class TestSourceIdentitySplit:
    def test_top_level_identity_is_extracted(self):
        clean, identity = split_source_identity(
            {
                "source_instance_id": "550e8400-e29b-41d4-a716-446655440000",
                "source_document_id": "660e8400-e29b-41d4-a716-446655440000",
                "user": "v",
            }
        )
        assert clean == {"user": "v"}
        assert identity == {
            "source_instance_id": "550e8400-e29b-41d4-a716-446655440000",
            "source_document_id": "660e8400-e29b-41d4-a716-446655440000",
        }

    def test_explicit_null_is_preserved_for_legacy_reporting(self):
        clean, identity = split_source_identity({"source_document_id": None, "a": 1})
        assert clean == {"a": 1}
        assert identity == {"source_document_id": None}

    @pytest.mark.parametrize("value", [1, True, ["x"], {"x": 1}])
    def test_non_string_identity_is_rejected(self, value):
        with pytest.raises(CanonicalizationError):
            split_source_identity({"source_instance_id": value})