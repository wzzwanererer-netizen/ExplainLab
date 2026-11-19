"""确定性规范化与三 Hash 单测（V2 A1-02，设计 §2.6.1 / §8.1 / §8.2 R5-5）。

覆盖：canonical JSON 基础、版本包络、datetime/Decimal/float/null-缺失/列表序、
语义排序全序、三 Hash 分离与字段污染拒绝、组件 Hash 变化分类、版本 bump 不可比。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

import pytest

from knowledge_core.domain.entities import CANONICALIZATION_VERSION, KnowledgeStatus
from knowledge_core.markdown import (
    CanonicalizationError,
    MarkdownDocument,
    compute_document_hashes,
    document_content_hash,
    document_payload_hash,
    hashes_comparable,
    require_comparable_versions,
    review_payload_hash,
)
from knowledge_core.markdown.canonical import (
    CANONICAL_SEPARATORS,
    canonical_datetime,
    canonical_decimal,
    canonical_json,
    canonicalize,
    sha256_canonical,
    sort_attachments,
    sort_links,
    sort_sources,
    sort_tags,
)


class TestCanonicalJsonBasics:
    def test_separators_are_fixed_compact(self):
        assert CANONICAL_SEPARATORS == (",", ":")

    def test_envelope_carries_version_and_sorts_keys(self):
        assert canonical_json({"b": 1, "a": 2}) == (
            '{"a":2,"b":1,"canonicalization_version":1}'
        )

    def test_key_order_does_not_change_bytes(self):
        assert canonical_json({"a": 1, "b": 2}) == canonical_json({"b": 2, "a": 1})

    def test_repeated_computation_is_byte_identical(self):
        value = {"title": "知识图谱", "tags": ["概念", "图谱"], "n": 3}
        assert len({canonical_json(value) for _ in range(20)}) == 1

    def test_non_ascii_is_not_escaped(self):
        assert "知识图谱" in canonical_json({"title": "知识图谱"})
        assert "\\u" not in canonical_json({"title": "知识图谱"})

    def test_non_mapping_subset_is_wrapped_in_value(self):
        assert canonical_json(["a", "b"]) == (
            '{"canonicalization_version":1,"value":["a","b"]}'
        )

    def test_reserved_version_key_is_rejected(self):
        with pytest.raises(CanonicalizationError, match="保留键"):
            canonicalize({"canonicalization_version": 9, "title": "x"})

    def test_nested_structures_are_normalized_recursively(self):
        value = {"outer": {"inner": [Decimal("1.50"), None, True]}}
        assert canonical_json(value) == (
            '{"canonicalization_version":1,"outer":{"inner":["1.5",null,true]}}'
        )

    def test_hash_is_lowercase_hex_sha256(self):
        digest = sha256_canonical({"a": 1})
        assert len(digest) == 64
        assert digest == digest.lower()
        assert all(char in "0123456789abcdef" for char in digest)


class TestCanonicalDatetime:
    def test_fixed_six_digit_microseconds_utc(self):
        moment = datetime(2026, 11, 17, 12, 0, 0, 123456, tzinfo=UTC)
        assert canonical_datetime(moment) == "2026-11-17T12:00:00.123456Z"

    def test_zero_microseconds_still_six_digits(self):
        moment = datetime(2026, 11, 17, 12, 0, 0, tzinfo=UTC)
        assert canonical_datetime(moment) == "2026-11-17T12:00:00.000000Z"

    def test_naive_is_treated_as_utc(self):
        naive = datetime(2026, 11, 17, 12, 0, 0)
        aware = naive.replace(tzinfo=UTC)
        assert canonical_datetime(naive) == canonical_datetime(aware)

    def test_other_timezone_same_instant_same_string(self):
        east = datetime(2026, 11, 17, 20, 0, 0, tzinfo=timezone(timedelta(hours=8)))
        assert canonical_datetime(east) == "2026-11-17T12:00:00.000000Z"

    def test_year_and_fields_are_zero_padded(self):
        assert canonical_datetime(datetime(7, 3, 4, 5, 6, 7, 8, tzinfo=UTC)) == (
            "0007-03-04T05:06:07.000008Z"
        )

    def test_precision_difference_changes_hash(self):
        base = datetime(2026, 11, 17, 12, 0, 0, tzinfo=UTC)
        assert sha256_canonical({"t": base}) != sha256_canonical(
            {"t": base.replace(microsecond=1)}
        )


class TestCanonicalDecimalAndFloat:
    def test_decimal_uses_fixed_string_not_float(self):
        assert canonical_decimal(Decimal("1.2300")) == "1.23"
        assert canonical_decimal(Decimal("1E+3")) == "1000"
        assert canonical_decimal(Decimal("0.000")) == "0"
        assert canonical_decimal(Decimal("-0.00")) == "0"

    def test_decimal_precision_is_preserved_exactly(self):
        # 经 float 会丢精度；Decimal 定字符串必须逐字保留。
        assert canonical_decimal(Decimal("0.1000000000000000000000000001")) == (
            "0.1000000000000000000000000001"
        )

    def test_equal_decimals_with_different_scale_hash_the_same(self):
        assert sha256_canonical({"n": Decimal("1.50")}) == sha256_canonical(
            {"n": Decimal("1.5")}
        )

    def test_naked_float_is_banned(self):
        with pytest.raises(CanonicalizationError, match="float"):
            canonical_json({"n": 1.5})

    def test_naked_float_banned_even_when_integral(self):
        with pytest.raises(CanonicalizationError, match="float"):
            canonical_json({"n": 2.0})

    def test_non_finite_decimal_rejected(self):
        for value in (Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")):
            with pytest.raises(CanonicalizationError, match="非有限"):
                canonical_decimal(value)

    def test_bool_and_int_are_distinct(self):
        assert canonical_json({"v": True}) != canonical_json({"v": 1})
        assert canonical_json({"v": False}) != canonical_json({"v": 0})


class TestNullVersusMissing:
    def test_explicit_null_differs_from_missing_key(self):
        assert sha256_canonical({"title": None}) != sha256_canonical({})

    def test_missing_keys_are_not_filled_with_null(self):
        assert canonical_json({"a": 1}) == '{"a":1,"canonicalization_version":1}'

    def test_empty_list_differs_from_null_and_missing(self):
        digests = {
            sha256_canonical({"tags": []}),
            sha256_canonical({"tags": None}),
            sha256_canonical({}),
        }
        assert len(digests) == 3

    def test_document_presence_tracks_explicit_fields(self):
        explicit = MarkdownDocument(title=None, content="x")
        missing = MarkdownDocument(content="x")
        assert "title" in explicit.payload_fields()
        assert explicit.payload_fields()["title"] is None
        assert "title" not in missing.payload_fields()
        assert explicit.payload_hash() != missing.payload_hash()


class TestListOrdering:
    def test_canonicalize_does_not_reorder_lists(self):
        assert sha256_canonical({"v": [1, 2]}) != sha256_canonical({"v": [2, 1]})

    def test_sort_tags_casefold_with_secondary_key(self):
        # 主键 casefold 相同 → 次级键用原始字面（大写码位在前），保证全序确定。
        assert sort_tags(["Beta", "alpha", "ALPHA", "beta"]) == [
            "ALPHA",
            "alpha",
            "Beta",
            "beta",
        ]

    def test_sort_tags_is_total_order_for_case_variants(self):
        tags = ["a", "A", "á", "Á"]
        assert sort_tags(tags) == sort_tags(list(reversed(tags)))

    def test_sort_links_by_normalized_key_then_secondary(self):
        links = [
            {"normalized_link_key": "b\x1f", "title": "B"},
            {"normalized_link_key": "a\x1f", "title": "A", "alias": "z"},
            {"normalized_link_key": "a\x1f", "title": "A", "alias": "a"},
        ]
        ordered = sort_links(links)
        assert [link.get("alias") for link in ordered[:2]] == ["a", "z"]
        assert ordered[2]["title"] == "B"

    def test_sort_links_falls_back_to_title_when_key_absent(self):
        # 排序按 Unicode 码位（确定性），不做拼音/语言特化排序。
        links = [{"title": "乙"}, {"title": "甲"}]
        assert [link["title"] for link in sort_links(links)] == ["乙", "甲"]
        assert [link["title"] for link in sort_links([{"title": "B"}, {"title": "A"}])] == [
            "A",
            "B",
        ]

    def test_sort_links_does_not_mutate_input_dicts(self):
        links = [{"title": "A", "alias": None}]
        sort_links(links)
        assert links == [{"title": "A", "alias": None}]

    def test_sort_attachments_by_content_hash(self):
        attachments = [
            {"content_hash": "ff", "storage_key": "s1"},
            {"content_hash": "aa", "storage_key": "s2"},
            {"content_hash": "aa", "storage_key": "s0"},
        ]
        assert [att["storage_key"] for att in sort_attachments(attachments)] == [
            "s0",
            "s2",
            "s1",
        ]

    def test_sort_sources_stable_key(self):
        sources = [
            {"type": "manual", "uri": "b"},
            {"type": "conversation", "conversation_id": "c2"},
            {"type": "conversation", "conversation_id": "c1"},
        ]
        ordered = sort_sources(sources)
        assert [src.get("conversation_id") or src["type"] for src in ordered] == [
            "c1",
            "c2",
            "manual",
        ]

    def test_document_payload_sorts_semantic_lists(self):
        first = MarkdownDocument(content="x", tags=["b", "a"], links=[{"title": "B"}, {"title": "A"}])
        second = MarkdownDocument(content="x", tags=["a", "b"], links=[{"title": "A"}, {"title": "B"}])
        assert first.payload_hash() == second.payload_hash()


class TestUnsupportedTypes:
    @pytest.mark.parametrize("value", [set(), b"bytes", object(), 3 + 4j])
    def test_unsupported_type_raises(self, value):
        with pytest.raises(CanonicalizationError, match="不支持"):
            canonical_json({"v": value})

    def test_non_string_mapping_key_raises(self):
        with pytest.raises(CanonicalizationError, match="字符串"):
            canonical_json({1: "a"})

    def test_uuid_and_enum_are_normalized(self):
        item_id = UUID("550e8400-e29b-41d4-a716-446655440000")

        class Color(StrEnum):
            RED = "red"

        assert canonical_json({"id": item_id, "c": Color.RED}) == (
            '{"c":"red","canonicalization_version":1,'
            '"id":"550e8400-e29b-41d4-a716-446655440000"}'
        )


class TestCanonicalizationVersion:
    def test_default_version_matches_domain_constant(self):
        assert CANONICALIZATION_VERSION == 1
        assert canonicalize({})["canonicalization_version"] == 1

    @pytest.mark.parametrize("version", [0, -1, True, "1", 1.0])
    def test_invalid_version_rejected(self, version):
        with pytest.raises(CanonicalizationError):
            canonical_json({"a": 1}, canonicalization_version=version)

    def test_version_bump_changes_every_hash(self):
        document = MarkdownDocument(title="t", content="c", tags=["a"])
        base = compute_document_hashes(document)
        bumped = compute_document_hashes(document, canonicalization_version=2)
        for field in (
            "document_content_hash",
            "document_payload_hash",
            "tags_hash",
            "links_hash",
            "attachments_hash",
            "extra_metadata_hash",
            "governance_hash",
        ):
            assert getattr(base, field) != getattr(bumped, field)

    def test_hashes_comparable_only_within_same_version(self):
        assert hashes_comparable(1, 1)
        assert not hashes_comparable(1, 2)

    def test_require_comparable_versions_raises_on_mismatch(self):
        require_comparable_versions(1, 1)
        with pytest.raises(CanonicalizationError, match="不可直接比较"):
            require_comparable_versions(1, 2)


class TestThreeHashSeparation:
    def test_content_hash_covers_only_title_and_content(self):
        assert document_content_hash({"title": "t", "content": "c"}) == (
            sha256_canonical({"title": "t", "content": "c"})
        )

    def test_content_hash_rejects_governance_pollution(self):
        with pytest.raises(CanonicalizationError, match="多余键"):
            document_content_hash({"title": "t", "content": "c", "status": "active"})

    def test_content_hash_requires_content(self):
        with pytest.raises(CanonicalizationError, match="content"):
            document_content_hash({"title": "t"})

    def test_content_hash_allows_missing_title(self):
        assert document_content_hash({"content": "c"}) == sha256_canonical({"content": "c"})

    def test_payload_hash_is_whole_document_not_component_concat(self):
        document = MarkdownDocument(title="t", content="c", tags=["a"])
        hashes = compute_document_hashes(document)
        joined = hashes.tags_hash + hashes.governance_hash + hashes.document_content_hash
        assert hashes.document_payload_hash != joined
        assert hashes.document_payload_hash == document_payload_hash(document.payload_fields())

    def test_review_hash_only_applied_change_fields(self):
        assert review_payload_hash({"title": "new"}) == sha256_canonical({"title": "new"})

    def test_review_hash_rejects_tags_and_metadata(self):
        for changes in ({"tags": ["a"]}, {"version": 2}, {"id": "x"}, {"updated_at": "t"}):
            with pytest.raises(CanonicalizationError, match="多余键"):
                review_payload_hash(changes)

    def test_review_hash_rejects_empty_changes(self):
        with pytest.raises(CanonicalizationError, match="空变更"):
            review_payload_hash({})

    def test_review_hash_distinguishes_null_from_missing(self):
        assert review_payload_hash({"title": None}) != review_payload_hash({"content": "c"})


class TestChangeClassification:
    """§2.6.2：content_hash 与 payload_hash 分离驱动变化分类（组件 hash 仅分类用）。"""

    def _base(self) -> MarkdownDocument:
        return MarkdownDocument(
            id=UUID("550e8400-e29b-41d4-a716-446655440000"),
            title="原标题",
            content="正文 [[链接]]",
            tags=["概念"],
            space_id=None,
            status=KnowledgeStatus.ACTIVE,
            version=3,
            created_at=datetime(2026, 11, 17, 12, 0, tzinfo=UTC),
            updated_at=datetime(2026, 11, 17, 12, 30, tzinfo=UTC),
            sources=[{"type": "manual"}],
            links=[{"title": "链接", "resolution": "missing"}],
            extra_metadata={"custom": "值"},
        )

    def test_timestamp_or_version_change_is_not_content_change(self):
        base = self._base()
        changed = base.model_copy(
            update={
                "version": 4,
                "updated_at": datetime(2026, 11, 18, 9, 0, tzinfo=UTC),
            }
        )
        assert base.content_hash() == changed.content_hash()
        assert base.payload_hash() != changed.payload_hash()
        assert compute_document_hashes(base).governance_hash != (
            compute_document_hashes(changed).governance_hash
        )

    def test_status_change_is_not_content_change(self):
        base = self._base()
        changed = base.model_copy(update={"status": KnowledgeStatus.DRAFT})
        assert base.content_hash() == changed.content_hash()
        assert base.payload_hash() != changed.payload_hash()

    def test_tags_only_change_is_low_risk(self):
        base = self._base()
        changed = base.model_copy(update={"tags": ["概念", "图谱"]})
        assert base.content_hash() == changed.content_hash()
        assert base.payload_hash() != changed.payload_hash()
        before, after = compute_document_hashes(base), compute_document_hashes(changed)
        assert before.tags_hash != after.tags_hash
        assert before.links_hash == after.links_hash
        assert before.governance_hash == after.governance_hash
        assert before.document_content_hash == after.document_content_hash

    def test_extra_metadata_only_change_is_low_risk(self):
        base = self._base()
        changed = base.model_copy(update={"extra_metadata": {"custom": "新值"}})
        assert base.content_hash() == changed.content_hash()
        assert base.payload_hash() != changed.payload_hash()
        before, after = compute_document_hashes(base), compute_document_hashes(changed)
        assert before.extra_metadata_hash != after.extra_metadata_hash
        assert before.tags_hash == after.tags_hash

    def test_title_only_change_is_content_change(self):
        base = self._base()
        changed = base.model_copy(update={"title": "新标题"})
        assert base.content_hash() != changed.content_hash()
        assert base.payload_hash() != changed.payload_hash()

    def test_body_change_is_content_change(self):
        base = self._base()
        changed = base.model_copy(update={"content": "新正文"})
        assert base.content_hash() != changed.content_hash()

    def test_links_only_change_is_not_content_change(self):
        base = self._base()
        changed = base.model_copy(
            update={
                "links": [
                    {
                        "title": "链接",
                        "resolution": "resolved",
                        "target_id": "660e8400-e29b-41d4-a716-446655440000",
                    }
                ]
            }
        )
        assert base.content_hash() == changed.content_hash()
        assert base.payload_hash() != changed.payload_hash()
        assert compute_document_hashes(base).links_hash != (
            compute_document_hashes(changed).links_hash
        )

    def test_attachments_change_only_moves_attachments_hash(self):
        base = self._base()
        changed = base.model_copy(
            update={"attachments": [{"content_hash": "aa", "storage_key": "aa"}]}
        )
        assert base.content_hash() == changed.content_hash()
        before, after = compute_document_hashes(base), compute_document_hashes(changed)
        assert before.attachments_hash != after.attachments_hash
        assert before.tags_hash == after.tags_hash

    def test_id_participates_in_payload_but_not_content(self):
        base = self._base()
        other = base.model_copy(update={"id": UUID("660e8400-e29b-41d4-a716-446655440000")})
        assert base.content_hash() == other.content_hash()
        assert base.payload_hash() != other.payload_hash()

    def test_same_content_different_id_dedups_by_content_hash(self):
        first = MarkdownDocument(title="t", content="c")
        second = MarkdownDocument(
            id=UUID("660e8400-e29b-41d4-a716-446655440000"), title="t", content="c"
        )
        assert first.content_hash() == second.content_hash()
        assert first.payload_hash() != second.payload_hash()


class TestUnicodeIdentity:
    def test_hash_input_uses_raw_unicode_not_nfkc(self):
        # Ｆｏｏ（全角）与 Foo 的**内容身份不同**；规范化只用于链接键（A1-03）。
        assert document_content_hash({"title": "Ｆｏｏ", "content": "c"}) != (
            document_content_hash({"title": "Foo", "content": "c"})
        )

    def test_casefold_not_applied_to_hash_input(self):
        assert document_content_hash({"title": "Foo", "content": "c"}) != (
            document_content_hash({"title": "foo", "content": "c"})
        )

    def test_ligature_and_composed_forms_keep_distinct_identity(self):
        assert document_content_hash({"title": "ﬁle", "content": "c"}) != (
            document_content_hash({"title": "file", "content": "c"})
        )


class TestDeterminismAcrossConstructions:
    def test_equivalent_documents_built_differently_hash_the_same(self):
        first = MarkdownDocument(
            title="t",
            content="c",
            tags=["b", "a"],
            status=KnowledgeStatus.ACTIVE,
            created_at=datetime(2026, 11, 17, 12, 0, tzinfo=UTC),
        )
        second = MarkdownDocument(
            created_at=datetime(2026, 11, 17, 20, 0, tzinfo=timezone(timedelta(hours=8))),
            status="active",
            tags=["a", "b"],
            content="c",
            title="t",
        )
        assert first.payload_hash() == second.payload_hash()
        assert compute_document_hashes(first) == compute_document_hashes(second)

    def test_frontmatter_state_does_not_enter_payload_hash(self):
        from knowledge_core.markdown import FrontmatterState

        base = MarkdownDocument(title="t", content="c")
        conflicted = base.model_copy(
            update={"frontmatter_state": FrontmatterState.CONFLICT}
        )
        assert base.payload_hash() == conflicted.payload_hash()