"""A1-03b/c Core 层服务与纯函数测试（计划 §12 A1-03b/c 门禁）。

覆盖：解析规则矩阵、场景 A–M（Core 层）、同步/恢复不变量、
T11 局部守卫（纵深防御）、T13–T17 纯判定 + T16 双层对照、
T22–T29/T35–T38 门禁 C 纯函数判定、T1–T12 重建计划层（Core 部分）、
H1–H20 提示聚合与导入空间语义、三 Hash 不变性与导出白名单守护、
D3 签名守护、单一事实来源/无缓存守护。
"""

from __future__ import annotations

import builtins
import inspect
import itertools
import json
from pathlib import Path
from uuid import uuid4

import pytest
from helpers import (
    InMemoryKnowledgeRepository,
    InMemoryLinkRepository,
    InMemoryRelationRepository,
    InMemoryVersionRepository,
)
from pydantic import ValidationError

from knowledge_core.domain import entities
from knowledge_core.domain.entities import (
    CANONICALIZATION_VERSION,
    KnowledgeItem,
    KnowledgeLink,
    KnowledgeStatus,
    LinkResolution,
    utcnow,
)
from knowledge_core.markdown import MarkdownDocument, compute_document_hashes
from knowledge_core.markdown.codec import StdlibMarkdownCodec
from knowledge_core.markdown.link_service import (
    BacklinkQuery,
    BindingFirstLinkSync,
    LinkImportRestorer,
    LinkKeyRebuild,
    LinkNormalizationVersionMismatch,
    LinkRebuildPlan,
    LinkRebuildReport,
    LinkReresolve,
    LinkRowState,
    RepositoryLinkResolver,
    check_global_version_homogeneity,
    check_plan_freshness,
)
from knowledge_core.markdown.links import (
    LINK_KEY_RULES,
    LinkWarningCode,
    normalized_link_key,
    normalized_link_key_v1,
)
from knowledge_core.ports import LinkRepository


@pytest.fixture
def items() -> InMemoryKnowledgeRepository:
    return InMemoryKnowledgeRepository()


@pytest.fixture
def links() -> InMemoryLinkRepository:
    return InMemoryLinkRepository()


@pytest.fixture
def resolver(items: InMemoryKnowledgeRepository) -> RepositoryLinkResolver:
    return RepositoryLinkResolver(items)


@pytest.fixture
def sync(
    items: InMemoryKnowledgeRepository,
    links: InMemoryLinkRepository,
    resolver: RepositoryLinkResolver,
) -> BindingFirstLinkSync:
    return BindingFirstLinkSync(items, links, resolver)


def _item(items, title, *, space_id=None, status=KnowledgeStatus.ACTIVE, content=""):
    return items.save(
        KnowledgeItem(title=title, content=content, space_id=space_id, status=status)
    )


def _inject(links: InMemoryLinkRepository, link: KnowledgeLink) -> KnowledgeLink:
    """绕过守卫直接注入（模拟历史数据/外部写入，测试夹具专用）。"""
    links._links[link.id] = link
    return link


def _row_state(link: KnowledgeLink) -> LinkRowState:
    return LinkRowState(
        link_id=link.id,
        source_id=link.source_id,
        normalized_link_key=link.normalized_link_key,
        link_normalization_version=link.link_normalization_version,
        target_title=link.target_title,
        alias=link.alias,
        target_id=link.target_id,
    )


def _current_rows(links: InMemoryLinkRepository) -> list[LinkRowState]:
    return [_row_state(r) for r in links.list_all_links()]


def _v2_key_fixture(title: str, alias: str | None) -> str:
    """v2 测试夹具规则：v1 键去空格（**不发布为生产规则**，仅注册表注入）。"""
    return normalized_link_key_v1(title, alias).replace(" ", "")


@pytest.fixture
def v2_registry(monkeypatch):
    monkeypatch.setitem(LINK_KEY_RULES, 2, _v2_key_fixture)
    return 2


def _codes(reasons) -> set[str]:
    return {r.reason_code for r in reasons}


# --- 解析规则矩阵（§6.2 / D7 / E5）---


def test_unique_match_resolved(items, links, sync, resolver) -> None:
    a = _item(items, "A", content="见 [[B]]")
    b = _item(items, "B")
    sync.sync(a, a.content)
    row = links.list_links(a.id)[0]
    assert row.resolution == LinkResolution.RESOLVED
    assert row.target_id == b.id
    assert row.target_title == "B"  # 原始字面
    assert BacklinkQuery(links).backlinks(b.id)[0].id == row.id


def test_multiple_candidates_ambiguous_no_random_bind(items, links, sync, resolver) -> None:
    a = _item(items, "A", content="[[B]]")
    _item(items, "B")
    _item(items, "Ｂ")  # NFKC 同标题键 → 两候选
    report = sync.sync(a, a.content)
    row = links.list_links(a.id)[0]
    assert row.resolution == LinkResolution.AMBIGUOUS
    assert row.target_id is None  # 绝不随机绑定
    assert report.ambiguous == 1
    assert len(resolver.find_candidates("B")) == 2  # 全部候选可查


def test_no_match_missing_no_auto_cross_space(items, links, sync) -> None:
    a = _item(items, "A", space_id="p1", content="[[B]]")
    _item(items, "B", space_id="p2")
    sync.sync(a, a.content)
    row = links.list_links(a.id)[0]
    assert row.resolution == LinkResolution.MISSING
    assert row.target_id is None
    assert row.cross_space is False  # 自动解析绝不跨空间


def test_none_space_source_never_binds_project_e5(items, links, sync) -> None:
    # J 扩展 / R24：space_id=None 的源不得把 project 条目纳入自动候选。
    a = _item(items, "A", space_id=None, content="[[B]]")
    _item(items, "B", space_id="p1")
    sync.sync(a, a.content)
    assert links.list_links(a.id)[0].resolution == LinkResolution.MISSING


def test_both_none_space_is_same_space(items, links, sync) -> None:
    a = _item(items, "A", space_id=None, content="[[B]]")
    b = _item(items, "B", space_id=None)
    sync.sync(a, a.content)
    row = links.list_links(a.id)[0]
    assert row.resolution == LinkResolution.RESOLVED
    assert row.target_id == b.id and row.cross_space is False


def test_archived_excluded_from_auto_resolution_l1(items, links, sync) -> None:
    a = _item(items, "A", content="[[B]]")
    _item(items, "B", status=KnowledgeStatus.ARCHIVED)
    sync.sync(a, a.content)
    assert links.list_links(a.id)[0].resolution == LinkResolution.MISSING


def test_active_plus_archived_same_key_not_ambiguous_l5(items, links, sync) -> None:
    a = _item(items, "A", content="[[B]]")
    active = _item(items, "B")
    _item(items, "B", status=KnowledgeStatus.ARCHIVED)
    sync.sync(a, a.content)
    row = links.list_links(a.id)[0]
    assert row.resolution == LinkResolution.RESOLVED
    assert row.target_id == active.id


def test_self_link_allowed_k(items, links, sync) -> None:
    a = _item(items, "A", content="自指 [[A]]")
    for _ in range(5):
        sync.sync(a, a.content)
    rows = links.list_links(a.id)
    assert len(rows) == 1
    assert rows[0].resolution == LinkResolution.RESOLVED
    assert rows[0].target_id == a.id
    assert any(r.id == rows[0].id for r in BacklinkQuery(links).backlinks(a.id))


def test_explicit_bind_archived_core_only_l3(items, links, sync, resolver) -> None:
    # L③：Core 层显式绑定规则已验证（A1-03 无 HTTP 写入口）。
    a = _item(items, "A", content="[[B]]")
    archived = _item(items, "B", status=KnowledgeStatus.ARCHIVED)
    link, warnings = resolver.bind_explicit(a, archived, title="B")
    links.save_link(link)
    assert link.resolution == LinkResolution.RESOLVED
    assert link.target_id == archived.id
    # L④ Core 部分：显式绑定后连续保存不被自动解绑。
    first_id = link.id
    for _ in range(3):
        sync.sync(a, a.content)
    rows = links.list_links(a.id)
    assert len(rows) == 1 and rows[0].id == first_id
    assert rows[0].target_id == archived.id


def test_explicit_bind_cross_space_core_only_j(items, links, resolver) -> None:
    a = _item(items, "A", space_id="p1")
    target = _item(items, "B", space_id="p2")
    link, warnings = resolver.bind_explicit(a, target, title="B")
    links.save_link(link)
    assert link.resolution == LinkResolution.CROSS_SPACE
    assert link.cross_space is True
    assert any(w.code.value == "cross_space_binding_restored" for w in warnings)


def test_find_candidates_includes_archived_and_cross_space(items, resolver) -> None:
    _item(items, "B", space_id="p1")
    _item(items, "B", space_id="p2", status=KnowledgeStatus.ARCHIVED)
    candidates = resolver.find_candidates("Ｂ")  # NFKC 匹配
    assert len(candidates) == 2
    assert {c.status for c in candidates} == {KnowledgeStatus.ACTIVE, KnowledgeStatus.ARCHIVED}


# --- 场景 A/B/C/E（Core 层）---


def test_scenario_a_rename_keeps_binding(items, links, sync) -> None:
    a = _item(items, "A", content="见 [[B]]")
    b = _item(items, "B")
    sync.sync(a, a.content)
    row = links.list_links(a.id)[0]
    b.title = "B 新名"
    items.update(b)
    sync.sync(a, a.content)  # 键未变 → 不重解析
    after = links.list_links(a.id)[0]
    assert after.id == row.id and after.target_id == b.id
    assert after.target_title == "B"  # 字面留存（D9）
    assert BacklinkQuery(links).backlinks(b.id)[0].id == row.id


def test_scenario_c_unrelated_edits_no_churn(items, links, sync) -> None:
    a = _item(items, "A", content="前文 [[B]] 后文")
    b = _item(items, "B")
    sync.sync(a, a.content)
    row = links.list_links(a.id)[0]
    for i in range(3):
        a.content = f"改无关正文 {i} [[B]] 尾"
        items.update(a)
        sync.sync(a, a.content)
    after = links.list_links(a.id)[0]
    assert after.id == row.id
    assert after.target_id == b.id
    assert after.created_at == row.created_at
    assert after.updated_at == row.updated_at  # 未绑定 churn 也不允许


def test_scenario_c_manual_adjudication_preserved(items, links, sync) -> None:
    a = _item(items, "A", content="[[B]]")
    b1 = _item(items, "B")
    _item(items, "B")
    sync.sync(a, a.content)
    row = links.list_links(a.id)[0]
    assert row.resolution == LinkResolution.AMBIGUOUS
    # 人工裁决：显式绑定到 b1（治理列写入，键不变）。
    adjudicated = row.model_copy(
        update={"target_id": b1.id, "resolution": LinkResolution.RESOLVED, "updated_at": utcnow()}
    )
    links.update_link(adjudicated)
    sync.sync(a, a.content)
    after = links.list_links(a.id)[0]
    assert after.target_id == b1.id and after.id == row.id


def test_scenario_e_five_syncs_stable(items, links, sync) -> None:
    versions = InMemoryVersionRepository()
    relations = InMemoryRelationRepository()
    a = _item(items, "A", content="[[B]] [[C|别名]] [[B]]")
    _item(items, "B")
    _item(items, "C")
    sync.sync(a, a.content)
    first = {r.id for r in links.list_links(a.id)}
    item_updated_at = a.updated_at
    for _ in range(5):
        sync.sync(a, a.content)
    rows = links.list_links(a.id)
    assert {r.id for r in rows} == first
    assert len(rows) == 2  # [[B]] 两次书写合并为一行
    assert all(r.target_id is not None for r in rows)
    assert versions.list_versions(a.id) == []  # 不写版本行
    assert relations.list_all_relations() == []  # 不写关系
    assert items.get(a.id).updated_at == item_updated_at  # 不碰条目时间戳


def test_sync_removes_disappeared_keys(items, links, sync) -> None:
    a = _item(items, "A", content="[[B]] [[C]]")
    _item(items, "B")
    _item(items, "C")
    sync.sync(a, a.content)
    assert len(links.list_links(a.id)) == 2
    report = sync.sync(a, "只剩 [[B]]")
    assert report.removed == 1
    rows = links.list_links(a.id)
    assert len(rows) == 1 and rows[0].target_title == "B"


def test_sync_does_not_touch_item_updated_at(items, links, sync) -> None:
    a = _item(items, "A", content="[[B]]")
    _item(items, "B")
    before = a.updated_at
    sync.sync(a, a.content)
    assert items.get(a.id).updated_at == before  # 同步本身不改条目时间戳


def test_alias_only_change_reparse_not_inherit_d5(items, links, sync) -> None:
    # 场景 H：alias-only 变更 → 新键重解析；歧义环境下不继承旧绑定。
    a = _item(items, "A", content="[[B|旧]]")
    b = _item(items, "B")
    sync.sync(a, a.content)
    old = links.list_links(a.id)[0]
    assert old.target_id == b.id
    _item(items, "B")  # 制造歧义
    report = sync.sync(a, "[[B|新]]")
    rows = links.list_links(a.id)
    assert len(rows) == 1
    assert rows[0].id != old.id  # 新键新行，不继承
    assert rows[0].resolution == LinkResolution.AMBIGUOUS
    assert rows[0].target_id is None
    assert report.removed == 1 and report.created == 1


# --- reresolve（只重试 missing/ambiguous）---


def test_reresolve_missing_to_resolved(items, links, sync, resolver) -> None:
    a = _item(items, "A", content="[[B]]")
    sync.sync(a, a.content)
    assert links.list_links(a.id)[0].resolution == LinkResolution.MISSING
    b = _item(items, "B")
    reresolve = LinkReresolve(items, links, resolver)
    reresolve.reresolve(a)
    row = links.list_links(a.id)[0]
    assert row.resolution == LinkResolution.RESOLVED and row.target_id == b.id


def test_reresolve_leaves_conflict_and_cross_space(items, links, sync, resolver) -> None:
    a = _item(items, "A", space_id="p1", content="[[B]] [[C]]")
    cross_target = _item(items, "B", space_id="p2")
    link, _ = resolver.bind_explicit(a, cross_target, title="B")
    links.save_link(link)
    conflict = KnowledgeLink(
        source_id=a.id,
        target_title="C",
        normalized_link_key=normalized_link_key("C", None),
        resolution=LinkResolution.CONFLICT,
    )
    links.save_link(conflict)
    _item(items, "C", space_id="p1")  # 即便有候选也不得自动解 conflict
    LinkReresolve(items, links, resolver).reresolve(a)
    by_title = {r.target_title: r for r in links.list_links(a.id)}
    assert by_title["B"].resolution == LinkResolution.CROSS_SPACE
    assert by_title["B"].id == link.id
    assert by_title["C"].resolution == LinkResolution.CONFLICT
    assert by_title["C"].target_id is None


def test_reresolve_no_churn_when_unchanged(items, links, sync, resolver) -> None:
    a = _item(items, "A", content="[[B]]")
    sync.sync(a, a.content)
    row = links.list_links(a.id)[0]
    LinkReresolve(items, links, resolver).reresolve(a)
    after = links.list_links(a.id)[0]
    assert after.updated_at == row.updated_at and after.id == row.id


# --- T13–T17 全局同构纯判定 + T16 双层对照 ---


def test_t13_empty_table_allowed() -> None:
    check_global_version_homogeneity([], 1)  # 不抛


def test_t14_homogeneous_allowed() -> None:
    check_global_version_homogeneity([1, 1, 1], 1)


def test_t15_foreign_version_refused() -> None:
    with pytest.raises(LinkNormalizationVersionMismatch) as exc:
        check_global_version_homogeneity([1, 1], 2)
    assert exc.value.observed_versions == [1]
    assert exc.value.current_version == 2
    assert exc.value.scope == "global"


def test_t17_mixed_refused() -> None:
    with pytest.raises(LinkNormalizationVersionMismatch) as exc:
        check_global_version_homogeneity([1, 2], 1)
    assert exc.value.observed_versions == [1, 2]


def test_t16_local_passes_global_refuses(items, links, sync, monkeypatch) -> None:
    # 审查反例：source 无链接行（局部 all([])==True 放行），其他 source 有 v1，
    # 常量 bump 到 v2 → 全局预检真实拒绝，零写入。
    other = _item(items, "Other", content="[[B]]")
    _item(items, "B")
    sync.sync(other, other.content)  # v1 行入库
    monkeypatch.setattr(entities, "LINK_NORMALIZATION_VERSION", 2)
    fresh = _item(items, "Fresh", content="[[B]]")
    with pytest.raises(LinkNormalizationVersionMismatch) as exc:
        sync.sync(fresh, fresh.content)
    assert exc.value.scope == "global"
    assert links.list_links(fresh.id) == []  # 零写入
    # 恢复同构（回退常量）后保存正常。
    monkeypatch.setattr(entities, "LINK_NORMALIZATION_VERSION", 1)
    sync.sync(fresh, fresh.content)
    assert links.list_links(fresh.id)[0].resolution == LinkResolution.RESOLVED


def test_t11_local_guard_defense_in_depth(items, links, sync, monkeypatch) -> None:
    # 本 source 存在旧版本行 → Core 局部守卫先拒（纵深防御，scope=local）。
    a = _item(items, "A", content="[[B]]")
    _item(items, "B")
    stale = KnowledgeLink(
        source_id=a.id,
        target_title="B",
        normalized_link_key=normalized_link_key("B", None),
        link_normalization_version=2,
    )
    _inject(links, stale)
    with pytest.raises(LinkNormalizationVersionMismatch) as exc:
        sync.sync(a, a.content)
    assert exc.value.scope == "local"
    assert exc.value.link_id == stale.id


def test_inmemory_global_guard_mixed_table_refused(items, links) -> None:
    a = _item(items, "A")
    _inject(
        links,
        KnowledgeLink(
            source_id=a.id, target_title="X",
            normalized_link_key=normalized_link_key("X", None),
            link_normalization_version=1,
        ),
    )
    _inject(
        links,
        KnowledgeLink(
            source_id=uuid4(), target_title="Y",
            normalized_link_key=normalized_link_key("Y", None),
            link_normalization_version=2,
        ),
    )
    with pytest.raises(LinkNormalizationVersionMismatch):
        links.save_link(
            KnowledgeLink(
                source_id=a.id, target_title="Z",
                normalized_link_key=normalized_link_key("Z", None),
            )
        )


def test_t20_exempt_writes_no_precheck(items, links) -> None:
    # 治理列豁免写入与删除 → 0 次预检；受守卫写入 → 每次 1 次（无缓存）。
    a = _item(items, "A")
    row = links.save_link(
        KnowledgeLink(
            source_id=a.id, target_title="B",
            normalized_link_key=normalized_link_key("B", None),
        )
    )
    assert links.precheck_calls == 1
    links.update_link(row.model_copy(update={"target_title": "B 改", "updated_at": utcnow()}))
    links.update_link(row.model_copy(update={"resolution": LinkResolution.MISSING, "target_id": None}))
    assert links.precheck_calls == 1  # 治理豁免不预检
    links.delete_link(row.id)
    assert links.precheck_calls == 1  # 删除豁免
    for i in range(5):
        links.save_link(
            KnowledgeLink(
                source_id=a.id, target_title=f"T{i}",
                normalized_link_key=normalized_link_key(f"T{i}", None),
            )
        )
    assert links.precheck_calls == 6  # k 次写入 = k 次预检


def test_inmemory_no_version_set_cache_attribute(links) -> None:
    # 无缓存结构守护：实例属性只有行字典与单调计数仪表，无版本集合缓存。
    attrs = vars(links)
    assert set(attrs) == {"_links", "precheck_calls"}
    assert isinstance(attrs["precheck_calls"], int)
    source = inspect.getsource(InMemoryLinkRepository)
    assert "lru_cache" not in source and "ContextVar" not in source
    assert "check_global_version_homogeneity" in source  # 单一事实来源


# --- T22–T29 / T35–T38 门禁 C 纯函数判定 ---


@pytest.fixture
def rebuild_fixture(items, links, v2_registry):
    """两行 v1 链接（其中一行键含空格，v2 去空格后键变化）。"""
    a = _item(items, "A")
    r1 = links.save_link(
        KnowledgeLink(
            source_id=a.id, target_title="Foo Bar", alias="x",
            normalized_link_key=normalized_link_key("Foo Bar", "x"),
        )
    )
    r2 = links.save_link(
        KnowledgeLink(
            source_id=a.id, target_title="Baz",
            normalized_link_key=normalized_link_key("Baz", None),
        )
    )
    plan = LinkKeyRebuild(links).plan(2)
    assert plan.status == "ready" and len(plan.updates) == 2
    return plan, r1, r2


def test_freshness_ok_when_unchanged(rebuild_fixture, links) -> None:
    plan, _, _ = rebuild_fixture
    result = check_plan_freshness(plan, _current_rows(links))
    assert result.ok and result.reasons == ()


def test_t22_target_title_changed(rebuild_fixture, links) -> None:
    plan, r1, _ = rebuild_fixture
    links.update_link(r1.model_copy(update={"target_title": "Foo Bar 改", "updated_at": utcnow()}))
    result = check_plan_freshness(plan, _current_rows(links))
    assert not result.ok
    assert "target_title_changed" in _codes(result.reasons)


def test_t23_alias_four_variants_exact_compare(rebuild_fixture, links) -> None:
    plan, r1, r2 = rebuild_fixture
    # ① None → ""（原始精确比对，None ≠ ""）
    links.update_link(r2.model_copy(update={"alias": "", "updated_at": utcnow()}))
    result = check_plan_freshness(plan, _current_rows(links))
    assert "alias_changed" in _codes(result.reasons)
    # ② "x" → "X"（casefold 同键但原始字面不同 → 仍拒）
    links.update_link(r1.model_copy(update={"alias": "X", "updated_at": utcnow()}))
    result = check_plan_freshness(plan, _current_rows(links))
    assert "alias_changed" in _codes(result.reasons)
    # ③ "x" → " x "（空白折叠同键但原始不同 → 仍拒）
    links.update_link(r1.model_copy(update={"alias": " x ", "updated_at": utcnow()}))
    result = check_plan_freshness(plan, _current_rows(links))
    assert "alias_changed" in _codes(result.reasons)
    # ④ "x" → None（非空 → None 反向，None ≠ "x"）
    links.update_link(r2.model_copy(update={"alias": None, "updated_at": utcnow()}))
    links.update_link(r1.model_copy(update={"alias": None, "updated_at": utcnow()}))
    result = check_plan_freshness(plan, _current_rows(links))
    assert "alias_changed" in _codes(result.reasons)


def test_t24_row_added(rebuild_fixture, links, items) -> None:
    plan, _, _ = rebuild_fixture
    links.save_link(
        KnowledgeLink(
            source_id=uuid4(), target_title="New",
            normalized_link_key=normalized_link_key("New", None),
        )
    )
    result = check_plan_freshness(plan, _current_rows(links))
    assert not result.ok
    assert {"row_added", "row_not_covered"} <= _codes(result.reasons)


def test_t25_row_deleted_update_and_noop(rebuild_fixture, links, items) -> None:
    plan, r1, _ = rebuild_fixture
    links.delete_link(r1.id)  # update 行被删
    result = check_plan_freshness(plan, _current_rows(links))
    assert "row_deleted" in _codes(result.reasons)
    # no-op 行被删同样被发现（plan(1) 全 no-op）。
    plan1 = LinkKeyRebuild(links).plan(1)
    assert plan1.status == "ready" and plan1.updates == ()
    remaining = links.list_all_links()[0]
    links.delete_link(remaining.id)
    result = check_plan_freshness(plan1, _current_rows(links))
    assert "row_deleted" in _codes(result.reasons)


def test_t26_key_changed_incl_changed_to_new_key(rebuild_fixture, links) -> None:
    plan, r1, _ = rebuild_fixture
    update = next(u for u in plan.updates if u.link_id == r1.id)
    # 改成恰好等于 new_key 也必须拒（快照比对先于重算）。
    links.update_link(r1.model_copy(update={"normalized_link_key": update.new_key, "updated_at": utcnow()}))
    result = check_plan_freshness(plan, _current_rows(links))
    assert "key_changed" in _codes(result.reasons)


def test_t27_version_changed_and_unsupported_registry(rebuild_fixture, links) -> None:
    plan, r1, _ = rebuild_fixture
    _inject(links, r1.model_copy(update={"link_normalization_version": 3}))
    result = check_plan_freshness(plan, _current_rows(links))
    assert "version_changed" in _codes(result.reasons)
    tampered = plan.model_copy(update={"target_version": 99})
    result = check_plan_freshness(tampered, _current_rows(links))
    assert "unsupported_target_version" in _codes(result.reasons)


def test_t28_incomplete_coverage_three_constructions(rebuild_fixture, links) -> None:
    plan, r1, r2 = rebuild_fixture
    current = _current_rows(links)
    # ① 快照漏行（observed_row_count 与当前行数不符也被发现）
    missing_snap = plan.model_copy(
        update={"row_snapshots": tuple(s for s in plan.row_snapshots if s.link_id != r1.id)}
    )
    result = check_plan_freshness(missing_snap, current)
    assert {"row_added", "row_not_covered"} <= _codes(result.reasons)
    assert any(r.field == "observed_row_count" for r in result.reasons)
    # observed_row_count 被篡改（与当前行数不符）也被发现。
    count_tampered = plan.model_copy(update={"observed_row_count": 99})
    result = check_plan_freshness(count_tampered, current)
    assert any(r.field == "observed_row_count" for r in result.reasons)
    # ② updates 漏行 → 该行按 no-op 校验失败（C 的 no-op 盲区守护）
    missing_upd = plan.model_copy(
        update={"updates": tuple(u for u in plan.updates if u.link_id != r1.id)}
    )
    result = check_plan_freshness(missing_upd, current)
    assert "noop_row_requires_update" in _codes(result.reasons)
    # ③ update 含不在快照中的 link_id
    ghost = plan.updates[0].model_copy(update={"link_id": uuid4()})
    ghost_plan = plan.model_copy(update={"updates": plan.updates + (ghost,)})
    result = check_plan_freshness(ghost_plan, current)
    assert "update_row_not_in_plan" in _codes(result.reasons)


def test_t29_duplicate_link_id_in_plan(rebuild_fixture, links) -> None:
    plan, _, _ = rebuild_fixture
    dup_snap = plan.model_copy(update={"row_snapshots": plan.row_snapshots + (plan.row_snapshots[0],)})
    result = check_plan_freshness(dup_snap, _current_rows(links))
    assert "duplicate_link_id_in_plan" in _codes(result.reasons)
    dup_upd = plan.model_copy(update={"updates": plan.updates + (plan.updates[0],)})
    result = check_plan_freshness(dup_upd, _current_rows(links))
    assert "duplicate_link_id_in_plan" in _codes(result.reasons)


def test_t35_source_id_changed(rebuild_fixture, links) -> None:
    plan, r1, _ = rebuild_fixture
    _inject(links, r1.model_copy(update={"source_id": uuid4()}))
    result = check_plan_freshness(plan, _current_rows(links))
    assert "source_id_changed" in _codes(result.reasons)


def test_t36_tamper_new_key_new_version_status(rebuild_fixture, links) -> None:
    plan, _, _ = rebuild_fixture
    current = _current_rows(links)
    swapped = plan.updates[0].model_copy(update={"new_key": "tampered\x1f"})
    result = check_plan_freshness(plan.model_copy(update={"updates": (swapped,) + plan.updates[1:]}), current)
    assert "new_key_mismatch" in _codes(result.reasons)
    bad_ver = plan.updates[0].model_copy(update={"new_version": 7})
    result = check_plan_freshness(plan.model_copy(update={"updates": (bad_ver,) + plan.updates[1:]}), current)
    assert "new_version_mismatch" in _codes(result.reasons)
    result = check_plan_freshness(plan.model_copy(update={"status": "refused_collision"}), current)
    assert "plan_not_ready" in _codes(result.reasons)


def test_t37_noop_blindspot_closed_and_no_false_refusal(items, links, v2_registry) -> None:
    # plan(1)：全表 v1 → 全 no-op（updates 为空）。R2 式「只比 updates」会放行。
    a = _item(items, "A")
    row = links.save_link(
        KnowledgeLink(
            source_id=a.id, target_title="B", alias="x",
            normalized_link_key=normalized_link_key("B", "x"),
        )
    )
    plan = LinkKeyRebuild(links).plan(1)
    assert plan.updates == () and len(plan.row_snapshots) == 1
    assert check_plan_freshness(plan, _current_rows(links)).ok  # 正常 no-op 不误拒
    # 治理列合法变更 alias → no-op 行重算发现必须更新 → 拒绝。
    links.update_link(row.model_copy(update={"alias": "y", "updated_at": utcnow()}))
    result = check_plan_freshness(plan, _current_rows(links))
    assert not result.ok
    assert {"noop_row_requires_update", "alias_changed"} <= _codes(result.reasons)


def test_t38_frozen_tuple_deterministic_no_digest(rebuild_fixture, links) -> None:
    plan, _, _ = rebuild_fixture
    with pytest.raises(ValidationError):
        plan.status = "ready"
    with pytest.raises(ValidationError):
        plan.row_snapshots[0].target_title = "x"
    with pytest.raises(AttributeError):
        plan.updates.append(plan.updates[0])
    # 确定性序列化：同输入两次 plan 字节相同。
    again = LinkKeyRebuild(links).plan(2)
    assert plan.model_dump_json() == again.model_dump_json()
    # 无摘要字段（字段集合精确锁定）。
    assert set(type(plan).model_fields) == {
        "status", "source_version", "target_version", "updates", "unchanged",
        "collision_groups", "warnings", "row_snapshots", "observed_row_count",
        "requires_replan",
    }
    for name in ("digest", "hash", "checksum", "plan_hash"):
        assert name not in type(plan).model_fields
    # 链接模块不使用内置 hash()。
    import re

    import knowledge_core.markdown.link_service as ls_mod
    import knowledge_core.markdown.links as links_mod

    for mod in (ls_mod, links_mod):
        source = inspect.getsource(mod)
        assert re.search(r"(?<![\w.])hash\(", source) is None


def test_freshness_pure_functions_no_io(rebuild_fixture, links, monkeypatch) -> None:
    plan, _, _ = rebuild_fixture

    def _boom(*args, **kwargs):
        raise AssertionError("纯函数不得 IO")

    monkeypatch.setattr("builtins.open", _boom)
    monkeypatch.setattr(Path, "write_text", _boom)
    monkeypatch.setattr(Path, "mkdir", _boom)
    assert check_plan_freshness(plan, _current_rows(links)).ok
    check_global_version_homogeneity([1, 1], 1)


def test_freshness_raw_unicode_no_normalization_before_compare(items, links, v2_registry) -> None:
    a = _item(items, "A")
    row = links.save_link(
        KnowledgeLink(
            source_id=a.id, target_title="Ｆoo", alias="A",
            normalized_link_key=normalized_link_key("Ｆoo", "A"),
        )
    )
    plan = LinkKeyRebuild(links).plan(2)
    # NFKC/casefold 等价但原始字面不同 → 必须拒（比对前不做规范化）。
    _inject(links, row.model_copy(update={"target_title": "Foo", "alias": "a"}))
    result = check_plan_freshness(plan, _current_rows(links))
    assert {"target_title_changed", "alias_changed"} <= _codes(result.reasons)


# --- D3 签名守护 + 单一事实来源 + ABC ---


def test_d3_link_repository_signatures_frozen() -> None:
    expected = {
        "save_link": (["self", "link"], "KnowledgeLink"),
        "get_link": (["self", "link_id"], "KnowledgeLink | None"),
        "list_links": (["self", "source_id"], "list[KnowledgeLink]"),
        "list_backlinks": (["self", "target_id"], "list[KnowledgeLink]"),
        "find_by_key": (["self", "source_id", "normalized_link_key"], "KnowledgeLink | None"),
        "list_by_key": (["self", "normalized_link_key"], "list[KnowledgeLink]"),
        "list_all_links": (["self"], "list[KnowledgeLink]"),
        "update_link": (["self", "link"], "KnowledgeLink"),
        "delete_link": (["self", "link_id"], "bool"),
        "delete_links_of_item": (["self", "source_id"], "int"),
    }
    methods = {
        name
        for name, member in inspect.getmembers(LinkRepository)
        if not name.startswith("_") and callable(member)
    }
    assert methods == set(expected)  # 恰为 A1-01 的 10 个，无新增
    for name, (params, ret) in expected.items():
        sig = inspect.signature(getattr(LinkRepository, name))
        assert list(sig.parameters) == params, name
        assert str(sig.return_annotation) == ret, name


def test_single_source_of_truth_homogeneity_and_freshness() -> None:
    # Core 内只有一处定义；InMemory 与（d 阶段的）backend 共用。
    import knowledge_core.markdown.link_service as ls_mod

    source = inspect.getsource(ls_mod)
    assert source.count("def check_global_version_homogeneity") == 1
    assert source.count("def check_plan_freshness") == 1
    helpers_source = Path(__file__).parent.joinpath("helpers.py").read_text(encoding="utf-8")
    assert "check_global_version_homogeneity" in helpers_source
    # 纯函数签名无 Session/IO 参数。
    sig = inspect.signature(check_plan_freshness)
    assert list(sig.parameters) == ["plan", "current_rows"]
    sig = inspect.signature(check_global_version_homogeneity)
    assert list(sig.parameters) == ["versions", "expected"]


def test_six_link_abcs_not_instantiable() -> None:
    from knowledge_core.markdown import (
        BacklinkService,
        LinkRebuildService,
        LinkReresolveService,
        LinkResolver,
        LinkRestoreService,
        LinkSyncService,
    )

    for cls in (
        LinkResolver, LinkSyncService, LinkRestoreService,
        BacklinkService, LinkReresolveService, LinkRebuildService,
    ):
        with pytest.raises(TypeError):
            cls()


def test_entity_validator_not_weakened() -> None:
    # D12：非法组合构造仍抛 ValueError（读取侧防御映射不得弱化校验器）。
    with pytest.raises(ValidationError):
        KnowledgeLink(
            source_id=uuid4(), target_title="B",
            normalized_link_key=normalized_link_key("B", None),
            resolution=LinkResolution.RESOLVED, target_id=None,
        )
    with pytest.raises(ValidationError):
        KnowledgeLink(
            source_id=uuid4(), target_title="B",
            normalized_link_key=normalized_link_key("B", None),
            resolution=LinkResolution.MISSING, target_id=uuid4(),
        )


# ===========================================================================
# A1-03c：Restorer（场景 D/M + H1–H20）+ Rebuild.plan（场景 F/G + T1–T12 Core
# 计划层）+ 三 Hash 不变性 + 导出白名单守护。
# 分层口径（§7.5 R3）：Core 断言计划内容与拒绝决策；真实写入/逐列快照/事务
# 回滚在 A1-03d 的真实 SQLite/PG 层断言，不以 Core 计划测试冒充重建已验证。
# ===========================================================================

_REVIEW_PROPOSAL = {"title": "A′", "content": "新正文"}  # 固定非空审核 payload（F 口径）


def _export_doc(item: KnowledgeItem, links: InMemoryLinkRepository) -> MarkdownDocument:
    """由实体 + 链接行构造交换文档；links[] 只含白名单四子字段（D1）。"""
    return MarkdownDocument(
        id=item.id,
        title=item.title,
        content=item.content,
        space_id=item.space_id,
        status=item.status,
        created_at=item.created_at,
        updated_at=item.updated_at,
        links=[
            {
                "target_id": None if r.target_id is None else str(r.target_id),
                "title": r.target_title,
                "alias": r.alias,
                "resolution": r.resolution.value,
            }
            for r in links.list_links(item.id)
        ],
    )


def _three_hashes(doc: MarkdownDocument) -> tuple[str, str, str]:
    h = compute_document_hashes(doc)
    return h.document_content_hash, h.document_payload_hash, h.links_hash


def _all_row_dumps(links: InMemoryLinkRepository) -> list[dict]:
    return [r.model_dump(mode="json") for r in links.list_all_links()]


def _apply_plan_bulk(links: InMemoryLinkRepository, plan) -> None:
    """测试夹具：模拟 backend 单事务批量写（只改键/版本/updated_at 三列）。

    真实 apply 在 A1-03d 验证；此处不能逐行走 update_link 守卫——中间态必然
    混合版本，逐行守卫会拒绝（这正是 backend 用门禁 A 单事务批量写的原因）。
    """
    for u in plan.updates:
        row = links.get_link(u.link_id)
        links._links[u.link_id] = row.model_copy(
            update={
                "normalized_link_key": u.new_key,
                "link_normalization_version": u.new_version,
                "updated_at": utcnow(),
            }
        )


def _warn_struct(w) -> tuple:
    """结构化告警指纹（不含 message：明细展示顺序随输入序，§7.3 已声明）。"""
    return (w.code, w.title, w.alias, w.target_id, w.target_ids)


@pytest.fixture
def codec() -> StdlibMarkdownCodec:
    return StdlibMarkdownCodec()


@pytest.fixture
def restorer(items, links, resolver) -> LinkImportRestorer:
    return LinkImportRestorer(items, links, resolver)


def _hint(title, target_id, alias=None, resolution="resolved") -> dict:
    return {"title": title, "alias": alias, "target_id": target_id, "resolution": resolution}


# --- 场景 B：规范化碰撞（NFKC 同键，不随机绑定）---


@pytest.mark.parametrize(("t1", "t2"), [("ﬁle", "file"), ("Ｆoo", "Foo"), ("①", "1")])
def test_scenario_b_nfkc_collision_ambiguous(items, links, sync, resolver, t1, t2) -> None:
    a = _item(items, "A", content=f"[[{t2}]]")
    i1 = _item(items, t1)
    i2 = _item(items, t2)
    sync.sync(a, a.content)
    row = links.list_links(a.id)[0]
    assert row.resolution == LinkResolution.AMBIGUOUS and row.target_id is None
    candidates = resolver.find_candidates(t2)
    assert {c.id for c in candidates} == {i1.id, i2.id}
    assert {c.title for c in candidates} == {t1, t2}  # 原始标题各自保留


def test_j2_project_source_never_binds_none_space(items, links, sync) -> None:
    a = _item(items, "A", content="[[B]]", space_id="p1")
    _item(items, "B", space_id=None)
    sync.sync(a, a.content)
    row = links.list_links(a.id)[0]
    assert row.resolution == LinkResolution.MISSING and row.target_id is None


def test_auto_candidates_all_same_space(items, resolver) -> None:
    a = _item(items, "A", space_id=None)
    _item(items, "X", space_id=None)
    _item(items, "Y", space_id="p1")
    _item(items, "Z", space_id=None, status=KnowledgeStatus.ARCHIVED)
    candidates = resolver.auto_candidates(a)
    assert all(c.space_id == a.space_id for c in candidates)
    assert {c.title for c in candidates} == {"A", "X"}  # archived 排除、跨空间排除


# --- 场景 D：导出 → 毁索引 → 导入恢复（codec 真实往返）---


def test_scenario_d_export_destroy_restore(items, links, sync, restorer, codec) -> None:
    a = _item(items, "A", content="参见 [[目标B]]")
    b = _item(items, "目标B")
    sync.sync(a, a.content)
    before_doc = _export_doc(a, links)
    before_hashes = _three_hashes(before_doc)
    from knowledge_core.markdown import review_payload_hash

    before_review = review_payload_hash(_REVIEW_PROPOSAL)
    text = codec.dump(before_doc).text
    # 导出白名单：links[] 只含四子字段，文本不含派生键/治理列名。
    assert set(before_doc.links[0]) == {"target_id", "title", "alias", "resolution"}
    for forbidden in ("normalized_link_key", "link_normalization_version"):
        assert forbidden not in text
    assert "cross_space:" not in text  # resolution 值可为 cross_space，但不得有该布尔列键
    # B 改名 + 显式毁索引（D3 允许用途）。
    b.title = "B′"
    items.update(b)
    assert links.delete_links_of_item(a.id) == 1
    parsed = codec.parse(text)
    report = restorer.restore(a, parsed.document.links, parsed.body)
    assert report.restored == 1 and report.conflicts == 0
    row = links.list_links(a.id)[0]
    assert row.target_id == b.id  # 依稳定 ID 恢复，改名不阻断
    assert row.resolution == LinkResolution.RESOLVED and row.cross_space is False
    assert row.target_title == "目标B"  # 原书写字面
    after_doc = _export_doc(a, links)
    assert _three_hashes(after_doc) == before_hashes  # resolution 未变 → 三 Hash 一致
    assert review_payload_hash(_REVIEW_PROPOSAL) == before_review


def test_scenario_d_target_gone_fallback_unresolved(items, links, sync, restorer, codec) -> None:
    a = _item(items, "A", content="[[目标B]]")
    b = _item(items, "目标B")
    sync.sync(a, a.content)
    text = codec.dump(_export_doc(a, links)).text
    links.delete_links_of_item(a.id)
    items.delete(b.id)  # 目标不存在（模拟跨实例）
    parsed = codec.parse(text)
    report = restorer.restore(a, parsed.document.links, parsed.body)
    assert [i.reason for i in report.invalid_hints] == ["target_not_found"]
    assert report.fallbacks == 1
    row = links.list_links(a.id)[0]
    assert row.resolution == LinkResolution.MISSING and row.target_id is None
    assert row.normalized_link_key in report.unresolved_links
    assert any(w.code == LinkWarningCode.INVALID_HINT_TARGET_NOT_FOUND for w in report.warnings)


# --- 场景 F：键重建不改交换身份（Core 计划层 + 夹具模拟批量写）---


def test_scenario_f_rebuild_preserves_exchange_identity(items, links, sync, v2_registry) -> None:
    a = _item(items, "A", content="见 [[Foo Bar]] 与 [[Baz]]")
    b1 = _item(items, "Foo Bar")
    b2 = _item(items, "Baz")
    sync.sync(a, a.content)
    rows_before = {r.id: r for r in links.list_links(a.id)}
    doc_before = _export_doc(a, links)
    hashes_before = _three_hashes(doc_before)
    text_before = StdlibMarkdownCodec().dump(doc_before).text
    item_before = items.get(a.id).model_dump(mode="json")
    from knowledge_core.markdown import review_payload_hash

    review_before = review_payload_hash(_REVIEW_PROPOSAL)

    plan = LinkKeyRebuild(links).plan(v2_registry)
    assert plan.status == "ready" and plan.source_version == 1
    assert len(plan.updates) == 2  # 非空洞：两行键都含空格，v2 必变
    _apply_plan_bulk(links, plan)
    # ② 先断言重建确实生效（避免「没重建所以 hash 当然不变」的空洞通过）。
    changed_keys = 0
    for r in links.list_links(a.id):
        assert r.link_normalization_version == 2
        assert r.normalized_link_key == _v2_key_fixture(r.target_title, r.alias)
        if r.normalized_link_key != rows_before[r.id].normalized_link_key:
            changed_keys += 1
    assert changed_keys >= 1  # "Foo Bar" 键必变；"Baz" 无空格键不变但版本升
    # ③ 三 Hash / 导出字节 / 绑定 / 五列 / 条目全列不变。
    doc_after = _export_doc(a, links)
    assert _three_hashes(doc_after) == hashes_before
    assert StdlibMarkdownCodec().dump(doc_after).text == text_before
    assert review_payload_hash(_REVIEW_PROPOSAL) == review_before
    for r in links.list_links(a.id):
        old = rows_before[r.id]
        assert r.target_id == old.target_id
        assert (r.target_title, r.alias, r.resolution, r.cross_space, r.created_at) == (
            old.target_title, old.alias, old.resolution, old.cross_space, old.created_at
        )
    assert items.get(a.id).model_dump(mode="json") == item_before
    assert {r.target_id for r in links.list_links(a.id)} == {b1.id, b2.id}


# --- 场景 G / T2 / T3 / T4：碰撞 → 整体拒绝 + 零写入（Core 计划层）---


def _collision_source(items, links, sync, title, t1, t2):
    a = _item(items, title, content=f"[[{t1}]] [[{t2}]]")
    b1 = _item(items, t1)
    b2 = _item(items, t2)
    sync.sync(a, a.content)
    assert all(r.resolution == LinkResolution.RESOLVED for r in links.list_links(a.id))
    return a, b1, b2


def test_t2_single_collision_full_report_zero_write(items, links, sync, v2_registry) -> None:
    a, b1, b2 = _collision_source(items, links, sync, "A", "Foo Bar", "FooBar")
    rows_before = _all_row_dumps(links)
    item_before = items.get(a.id).model_dump(mode="json")
    doc_before = _export_doc(a, links)
    plan = LinkKeyRebuild(links).plan(v2_registry)
    assert plan.status == "refused_collision" and plan.requires_replan is True
    assert plan.updates == () and plan.unchanged == 2 and plan.observed_row_count == 2
    assert len(plan.collision_groups) == 1
    group = plan.collision_groups[0]
    assert group.source_id == a.id and group.new_key == _v2_key_fixture("Foo Bar", None)
    assert len(group.entries) == 2
    # T4：不同 target_id 碰撞——两个绑定各自原样保留，不合并/不随机/不删除。
    assert {e.target_id for e in group.entries} == {b1.id, b2.id}
    for e in group.entries:
        assert e.old_version == 1 and e.source_id == a.id
        assert e.old_key and e.new_key and e.target_title
        original = links.get_link(e.link_id)
        assert e.old_key == original.normalized_link_key
        assert e.target_id == original.target_id
    assert _all_row_dumps(links) == rows_before  # 零写入（含 updated_at）
    assert items.get(a.id).model_dump(mode="json") == item_before
    assert _three_hashes(_export_doc(a, links)) == _three_hashes(doc_before)
    assert len(links.list_all_links()) == 2


def test_t3_three_collision_groups_all_listed(items, links, sync, v2_registry) -> None:
    pairs = [("Foo Bar", "FooBar"), ("Baz Qux", "BazQux"), ("Alpha Beta", "AlphaBeta")]
    for i, (t1, t2) in enumerate(pairs):
        _collision_source(items, links, sync, f"A{i}", t1, t2)
    rows_before = _all_row_dumps(links)
    plan = LinkKeyRebuild(links).plan(v2_registry)
    assert plan.status == "refused_collision"
    assert len(plan.collision_groups) == 3  # 不漏报、不只报第一组
    assert all(len(g.entries) == 2 for g in plan.collision_groups)
    assert len({g.new_key for g in plan.collision_groups}) == 3
    assert _all_row_dumps(links) == rows_before


def test_t8_cross_source_same_new_key_not_collision(items, links, sync, v2_registry) -> None:
    _item(items, "Foo Bar")
    a1 = _item(items, "A1", content="[[Foo Bar]]")
    a2 = _item(items, "A2", content="[[Foo Bar]]")
    sync.sync(a1, a1.content)
    sync.sync(a2, a2.content)
    plan = LinkKeyRebuild(links).plan(v2_registry)
    assert plan.status == "ready" and len(plan.updates) == 2  # 复合唯一键，跨源不碰撞


def test_t9_idempotent_replan_no_churn(items, links, sync, v2_registry) -> None:
    a = _item(items, "A", content="[[Foo Bar]] [[Baz]]")
    _item(items, "Foo Bar")
    _item(items, "Baz")
    sync.sync(a, a.content)
    plan = LinkKeyRebuild(links).plan(v2_registry)
    _apply_plan_bulk(links, plan)
    rows_before = _all_row_dumps(links)
    again = LinkKeyRebuild(links).plan(v2_registry)
    assert again.status == "ready" and again.source_version == 2
    assert again.updates == () and again.unchanged == 2 and again.observed_row_count == 2
    assert _all_row_dumps(links) == rows_before  # 不 churn updated_at


def test_t10_rollback_rerun_and_collision_refusal(items, links, sync, v2_registry) -> None:
    a = _item(items, "A", content="[[Foo Bar]] [[Baz]]")
    b1 = _item(items, "Foo Bar")
    b2 = _item(items, "Baz")
    sync.sync(a, a.content)
    hashes_before = _three_hashes(_export_doc(a, links))
    v1_keys = {r.id: r.normalized_link_key for r in links.list_links(a.id)}
    plan2 = LinkKeyRebuild(links).plan(v2_registry)
    _apply_plan_bulk(links, plan2)
    # 回滚 = 旧版本重跑：确定性恢复旧键旧版本，绑定全保留，三 Hash 不变。
    plan1 = LinkKeyRebuild(links).plan(1)
    assert plan1.status == "ready" and len(plan1.updates) == 2
    _apply_plan_bulk(links, plan1)
    for r in links.list_links(a.id):
        assert r.link_normalization_version == 1
        assert r.normalized_link_key == v1_keys[r.id]
    assert {r.target_id for r in links.list_links(a.id)} == {b1.id, b2.id}
    assert _three_hashes(_export_doc(a, links)) == hashes_before
    # 旧键在新数据下碰撞 → 同样整体拒绝，保持 v2 现状，不做部分回滚。
    _apply_plan_bulk(links, LinkKeyRebuild(links).plan(v2_registry))
    dirty = KnowledgeLink(
        source_id=a.id, target_title="Foo  Bar",
        normalized_link_key=_v2_key_fixture("Foo  Bar", None),
        link_normalization_version=2, resolution=LinkResolution.MISSING,
    )
    _inject(links, dirty)
    rows_before = _all_row_dumps(links)
    refused = LinkKeyRebuild(links).plan(1)
    assert refused.status == "refused_collision" and refused.requires_replan is True
    assert _all_row_dumps(links) == rows_before
    assert all(r.link_normalization_version == 2 for r in links.list_all_links())


def test_t11_mixed_version_plan_refused_and_rebuild_gate(items, links, sync, v2_registry, monkeypatch) -> None:
    a = _item(items, "A", content="[[B]]")
    _item(items, "B")
    sync.sync(a, a.content)
    foreign = KnowledgeLink(
        source_id=a.id, target_title="C",
        normalized_link_key=normalized_link_key("C", None),
        link_normalization_version=2, resolution=LinkResolution.MISSING,
    )
    _inject(links, foreign)
    plan = LinkKeyRebuild(links).plan(v2_registry)
    assert plan.status == "refused_mixed_version"
    assert plan.source_version is None and plan.requires_replan is True
    assert plan.observed_row_count == 2 and len(plan.row_snapshots) == 2
    assert any(w.code == LinkWarningCode.REBUILD_MIXED_VERSION for w in plan.warnings)
    # 重建专用门禁：全表 v1 + 代码常量 v2 → 常规写拒绝但重建入口允许（§8.4.4）。
    links.delete_link(foreign.id)
    monkeypatch.setattr(entities, "LINK_NORMALIZATION_VERSION", 2)
    with pytest.raises(LinkNormalizationVersionMismatch):
        sync.sync(a, "[[B]] [[D]]")
    allowed = LinkKeyRebuild(links).plan(v2_registry)
    assert allowed.status == "ready" and allowed.source_version == 1


def test_t12_plan_report_roundtrip_and_core_zero_io_zero_write(items, links, sync, v2_registry, monkeypatch) -> None:
    a, _, _ = _collision_source(items, links, sync, "A", "Foo Bar", "FooBar")
    rebuild = LinkKeyRebuild(links)
    refused = rebuild.plan(v2_registry)
    ready = LinkKeyRebuild(links).plan(1)
    for plan in (refused, ready):
        dumped = plan.model_dump(mode="json")
        assert LinkRebuildPlan.model_validate(json.loads(json.dumps(dumped))) == plan
    report = LinkRebuildReport(
        status="refused_collision", source_version=1, target_version=2,
        updated=0, unchanged=2, collision_groups=refused.collision_groups,
        warnings=refused.warnings, stale_reasons=(), requires_replan=True,
        observed_row_count=2,
    )
    assert LinkRebuildReport.model_validate(
        json.loads(json.dumps(report.model_dump(mode="json")))
    ) == report
    # 行为守护①：文件系统不可用时 plan() 仍成功（Core 零文件 IO）。
    def _boom(*args, **kwargs):
        raise AssertionError("Core 计划层不得触碰文件系统")

    monkeypatch.setattr(builtins, "open", _boom)
    monkeypatch.setattr(Path, "write_text", _boom)
    monkeypatch.setattr(Path, "mkdir", _boom)
    assert rebuild.plan(v2_registry).status == "refused_collision"
    # 行为守护②：仓库写方法全部不可用时 plan() 仍成功（Core 零数据库写入）。
    monkeypatch.setattr(links, "save_link", _boom)
    monkeypatch.setattr(links, "update_link", _boom)
    monkeypatch.setattr(links, "delete_link", _boom)
    assert rebuild.plan(v2_registry).status == "refused_collision"
    assert items.get(a.id) is not None


# --- 场景 M / H1–H12：提示聚合（先聚合再判定，无效 ≠ 矛盾）---


def test_h1_duplicate_hints_single_row(items, links, restorer) -> None:
    a = _item(items, "A", content="[[B]]")
    b = _item(items, "B")
    report = restorer.restore(a, [_hint("B", str(b.id)), _hint("B", str(b.id))], a.content)
    assert report.restored == 1
    rows = links.list_links(a.id)
    assert len(rows) == 1 and rows[0].target_id == b.id


def test_h2_same_title_different_alias_same_target(items, links, restorer) -> None:
    a = _item(items, "A", content="[[B|别名1]] [[B|别名2]]")
    b = _item(items, "B")
    hints = [_hint("B", str(b.id), alias="别名1"), _hint("B", str(b.id), alias="别名2")]
    report = restorer.restore(a, hints, a.content)
    assert report.restored == 2
    rows = links.list_links(a.id)
    assert len(rows) == 2 and all(r.target_id == b.id for r in rows)


def test_h3_conflicting_hints_conflict_no_random(items, links, restorer) -> None:
    a = _item(items, "A", content="[[B]]")
    b1 = _item(items, "B")
    b2 = _item(items, "B")
    report = restorer.restore(a, [_hint("B", str(b1.id)), _hint("B", str(b2.id))], a.content)
    assert report.conflicts == 1 and report.restored == 0
    row = links.list_links(a.id)[0]
    assert row.resolution == LinkResolution.CONFLICT and row.target_id is None
    warning = next(w for w in report.warnings if w.code == LinkWarningCode.CONFLICTING_HINTS)
    assert set(warning.target_ids) == {str(b1.id), str(b2.id)}
    assert str(b1.id) in warning.message and str(b2.id) in warning.message


def test_h4_conflict_order_independent(items, links, restorer) -> None:
    a = _item(items, "A", content="[[B]]")
    b1 = _item(items, "B")
    b2 = _item(items, "B")
    hints = [_hint("B", str(b1.id)), _hint("B", str(b2.id))]
    results = []
    for perm in itertools.permutations(hints):
        links.delete_links_of_item(a.id)
        report = restorer.restore(a, list(perm), a.content)
        row = links.list_links(a.id)[0]
        results.append(
            (row.target_id, row.resolution, row.cross_space,
             tuple(sorted(_warn_struct(w) for w in report.warnings)))
        )
    assert len(set(results)) == 1  # 无 last-write-wins


def test_h5_malformed_uuid_invalid_not_conflict(items, links, restorer) -> None:
    a = _item(items, "A", content="[[B]]")
    b = _item(items, "B")
    for bad in ("not-a-uuid", "", 123):
        links.delete_links_of_item(a.id)
        report = restorer.restore(a, [_hint("B", bad)], a.content)
        assert [i.reason for i in report.invalid_hints] == ["malformed_uuid"]
        assert report.conflicts == 0 and report.fallbacks == 1
        warning = next(
            w for w in report.warnings if w.code == LinkWarningCode.INVALID_HINT_MALFORMED_UUID
        )
        assert str(bad) in warning.message  # 保留原始文本
        assert links.list_links(a.id)[0].target_id == b.id  # 回退标题解析成功


def test_h6_target_not_found_fallback_unresolved(items, links, restorer) -> None:
    a = _item(items, "A", content="[[不存在]]")
    report = restorer.restore(a, [_hint("不存在", str(uuid4()))], a.content)
    assert [i.reason for i in report.invalid_hints] == ["target_not_found"]
    assert report.conflicts == 0 and report.fallbacks == 1
    row = links.list_links(a.id)[0]
    assert row.resolution == LinkResolution.MISSING
    assert row.normalized_link_key in report.unresolved_links


def test_h7_valid_plus_invalid_mixed(items, links, restorer) -> None:
    a = _item(items, "A", content="[[B]]")
    b = _item(items, "B")
    report = restorer.restore(
        a, [_hint("B", str(b.id)), _hint("B", "broken"), _hint("B", None)], a.content
    )
    assert report.restored == 1
    assert {i.reason for i in report.invalid_hints} == {"malformed_uuid", "no_target_id"}
    codes = {w.code for w in report.warnings}
    assert LinkWarningCode.INVALID_HINT_MALFORMED_UUID in codes
    assert LinkWarningCode.INVALID_HINT_NO_TARGET_ID in codes
    assert links.list_links(a.id)[0].target_id == b.id


def test_h8_three_way_conflict_all_listed(items, links, restorer) -> None:
    a = _item(items, "A", content="[[B]]")
    targets = [_item(items, "B") for _ in range(3)]
    report = restorer.restore(a, [_hint("B", str(t.id)) for t in targets], a.content)
    assert report.conflicts == 1
    warning = next(w for w in report.warnings if w.code == LinkWarningCode.CONFLICTING_HINTS)
    assert set(warning.target_ids) == {str(t.id) for t in targets}


def test_h9_orphan_hint_no_row(items, links, restorer) -> None:
    a = _item(items, "A", content="[[B]]")
    b = _item(items, "B")
    ghost = _item(items, "Ghost")
    report = restorer.restore(a, [_hint("B", str(b.id)), _hint("Ghost", str(ghost.id))], a.content)
    assert len(report.orphan_hints) == 1 and report.orphan_hints[0].title == "Ghost"
    assert any(w.code == LinkWarningCode.ORPHAN_HINT for w in report.warnings)
    rows = links.list_links(a.id)
    assert len(rows) == 1 and rows[0].target_title == "B"


def test_h10_hint_without_target_id_fallback(items, links, restorer) -> None:
    a = _item(items, "A", content="[[B]]")
    b = _item(items, "B")
    report = restorer.restore(
        a, [{"title": "B", "alias": "x", "resolution": "resolved"}], a.content
    )
    assert [i.reason for i in report.invalid_hints] == ["no_target_id"]
    assert report.fallbacks == 1
    assert links.list_links(a.id)[0].target_id == b.id  # 回退解析，不凭提示建行


def test_h11_empty_hints_same_as_title_resolution(items, links, sync, restorer) -> None:
    a = _item(items, "A", content="[[B]] [[C]]")
    b = _item(items, "B")
    sync.sync(a, a.content)
    via_sync = {
        r.normalized_link_key: (r.target_id, r.resolution) for r in links.list_links(a.id)
    }
    links.delete_links_of_item(a.id)
    report = restorer.restore(a, [], a.content)
    via_restore = {
        r.normalized_link_key: (r.target_id, r.resolution) for r in links.list_links(a.id)
    }
    assert via_restore == via_sync
    assert report.fallbacks == 2 and report.restored == 0
    assert b.id in {t for t, _ in via_restore.values()}


def test_h12_hashes_unaffected_by_hint_aggregation(items, links, sync, restorer) -> None:
    a = _item(items, "A", content="[[B]]")
    b = _item(items, "B")
    sync.sync(a, a.content)
    doc_before = _export_doc(a, links)
    from knowledge_core.markdown import review_payload_hash

    review_before = review_payload_hash(_REVIEW_PROPOSAL)
    links.delete_links_of_item(a.id)
    restorer.restore(a, [_hint("B", str(b.id)), _hint("B", str(b.id))], a.content)
    doc_after = _export_doc(a, links)
    assert doc_after.content_hash() == doc_before.content_hash()
    assert review_payload_hash(_REVIEW_PROPOSAL) == review_before
    assert set(doc_after.links[0]) == {"target_id", "title", "alias", "resolution"}


# --- H13–H20：导入绑定的空间语义（E2）---


@pytest.mark.parametrize(("src_space", "tgt_space"), [(None, None), ("p1", "p1")])
def test_h13_same_space_restore_resolved_false(items, links, restorer, src_space, tgt_space) -> None:
    a = _item(items, "A", content="[[B]]", space_id=src_space)
    b = _item(items, "B", space_id=tgt_space)
    report = restorer.restore(a, [_hint("B", str(b.id))], a.content)
    row = links.list_links(a.id)[0]
    assert report.restored == 1
    assert row.resolution == LinkResolution.RESOLVED and row.cross_space is False
    assert not any(
        w.code == LinkWarningCode.CROSS_SPACE_BINDING_RESTORED for w in report.warnings
    )


def test_h14_cross_space_restore_true_and_contrast_auto(items, links, sync, restorer) -> None:
    a = _item(items, "A", content="[[B|别名]]", space_id="p1")
    b = _item(items, "B", space_id="p2")
    report = restorer.restore(a, [_hint("B", str(b.id), alias="别名")], a.content)
    row = links.list_links(a.id)[0]
    assert row.target_id == b.id
    assert row.resolution == LinkResolution.CROSS_SPACE and row.cross_space is True
    assert not (row.resolution == LinkResolution.RESOLVED and row.cross_space is False)
    warning = next(
        w for w in report.warnings if w.code == LinkWarningCode.CROSS_SPACE_BINDING_RESTORED
    )
    for fragment in ("p1", "p2", str(b.id), "B", "别名"):
        assert fragment in warning.message
    # 对照 J：同一对条目无提示时自动解析必为 missing（跨空间绑定只来自历史意图）。
    links.delete_links_of_item(a.id)
    sync.sync(a, a.content)
    auto = links.list_links(a.id)[0]
    assert auto.resolution == LinkResolution.MISSING and auto.target_id is None


@pytest.mark.parametrize(("src_space", "tgt_space"), [(None, "p1"), ("p1", None)])
def test_h15_h16_none_vs_project_is_cross_space(items, links, restorer, src_space, tgt_space) -> None:
    a = _item(items, "A", content="[[B]]", space_id=src_space)
    b = _item(items, "B", space_id=tgt_space)
    restorer.restore(a, [_hint("B", str(b.id))], a.content)
    row = links.list_links(a.id)[0]
    assert row.resolution == LinkResolution.CROSS_SPACE and row.cross_space is True
    assert row.target_id == b.id


def test_h17_archived_target_restore_kept(items, links, restorer) -> None:
    # 同空间 archived → resolved+False + archived warning。
    a = _item(items, "A", content="[[B]]", space_id="p1")
    b = _item(items, "B", space_id="p1", status=KnowledgeStatus.ARCHIVED)
    report = restorer.restore(a, [_hint("B", str(b.id))], a.content)
    row = links.list_links(a.id)[0]
    assert row.target_id == b.id
    assert row.resolution == LinkResolution.RESOLVED and row.cross_space is False
    assert any(w.code == LinkWarningCode.ARCHIVED_TARGET_RESTORED for w in report.warnings)
    # 跨空间 archived → cross_space+True，空间语义不被 archived 改写。
    links.delete_links_of_item(a.id)
    b.space_id = "p2"
    items.update(b)
    report = restorer.restore(a, [_hint("B", str(b.id))], a.content)
    row = links.list_links(a.id)[0]
    assert row.resolution == LinkResolution.CROSS_SPACE and row.cross_space is True
    codes = {w.code for w in report.warnings}
    assert LinkWarningCode.ARCHIVED_TARGET_RESTORED in codes
    assert LinkWarningCode.CROSS_SPACE_BINDING_RESTORED in codes


def test_h18_not_found_never_conflict_never_cross_space(items, links, restorer) -> None:
    a = _item(items, "A", content="[[B]]", space_id="p1")
    report = restorer.restore(a, [_hint("B", str(uuid4()))], a.content)
    assert [i.reason for i in report.invalid_hints] == ["target_not_found"]
    assert report.conflicts == 0
    row = links.list_links(a.id)[0]
    assert row.resolution == LinkResolution.MISSING and row.cross_space is False
    codes = {w.code for w in report.warnings}
    assert LinkWarningCode.INVALID_HINT_TARGET_NOT_FOUND in codes
    assert LinkWarningCode.INVALID_HINT_MALFORMED_UUID not in codes  # 与 H5 语义分离


def test_h19_mixed_hints_order_independent(items, links, restorer) -> None:
    a = _item(items, "A", content="[[Same]] [[Cross]] [[Arch]] [[Bad]] [[Gone]] [[Con]]", space_id="p1")
    same = _item(items, "Same", space_id="p1")
    cross = _item(items, "Cross", space_id="p2")
    arch = _item(items, "Arch", space_id="p1", status=KnowledgeStatus.ARCHIVED)
    con1 = _item(items, "Con", space_id="p1")
    con2 = _item(items, "Con", space_id="p1")
    hints = [
        _hint("Same", str(same.id)),
        _hint("Cross", str(cross.id)),
        _hint("Arch", str(arch.id)),
        _hint("Bad", "not-a-uuid"),
        _hint("Gone", str(uuid4())),
        _hint("Con", str(con1.id)),
        _hint("Con", str(con2.id)),
    ]
    orders = [list(reversed(hints)), hints[3:] + hints[:3], hints[1::2] + hints[::2]]
    results = []
    for order in orders:
        links.delete_links_of_item(a.id)
        report = restorer.restore(a, order, a.content)
        rows = {
            r.normalized_link_key: (r.target_id, r.resolution, r.cross_space)
            for r in links.list_links(a.id)
        }
        for r in links.list_links(a.id):
            assert r.cross_space == (r.resolution == LinkResolution.CROSS_SPACE)
        results.append(
            (tuple(sorted(rows.items())),
             tuple(sorted(_warn_struct(w) for w in report.warnings)),
             report.restored, report.conflicts, report.fallbacks)
        )
    assert len(set(results)) == 1
    rows = {
        r.normalized_link_key: (r.target_id, r.resolution, r.cross_space)
        for r in links.list_links(a.id)
    }
    assert rows[normalized_link_key("Same", None)] == (same.id, LinkResolution.RESOLVED, False)
    assert rows[normalized_link_key("Cross", None)] == (cross.id, LinkResolution.CROSS_SPACE, True)
    assert rows[normalized_link_key("Con", None)] == (None, LinkResolution.CONFLICT, False)


def test_h20_reexport_hash_semantics(items, links, sync, restorer, codec) -> None:
    from knowledge_core.markdown import review_payload_hash

    review_before = review_payload_hash(_REVIEW_PROPOSAL)
    # ① 同空间布局往返：payload_hash / content_hash / 导出字节逐位相同。
    a = _item(items, "A", content="见 [[B]]")
    b = _item(items, "B")
    sync.sync(a, a.content)
    source_doc = _export_doc(a, links)
    source_text = codec.dump(source_doc).text
    parsed = codec.parse(source_text)
    # 模拟导入新实例：保留导出身份与时间戳，目标同空间。
    items2, links2 = InMemoryKnowledgeRepository(), InMemoryLinkRepository()
    imported_b = items2.save(
        KnowledgeItem(id=b.id, title="B", content="", space_id=None)
    )
    imported_a = items2.save(
        KnowledgeItem(
            id=a.id, title=parsed.document.title, content=parsed.body, space_id=None,
            status=parsed.document.status,
            created_at=parsed.document.created_at, updated_at=parsed.document.updated_at,
        )
    )
    restorer2 = LinkImportRestorer(items2, links2, RepositoryLinkResolver(items2))
    restorer2.restore(imported_a, parsed.document.links, parsed.body)
    reexport_doc = _export_doc(imported_a, links2)
    assert reexport_doc.payload_hash() == source_doc.payload_hash()
    assert reexport_doc.content_hash() == source_doc.content_hash()
    assert codec.dump(reexport_doc).text == source_text
    assert links2.list_links(imported_a.id)[0].target_id == imported_b.id
    # ② 跨空间布局导入：resolution 变 cross_space → payload_hash 预期变化，content_hash 不变。
    items3, links3 = InMemoryKnowledgeRepository(), InMemoryLinkRepository()
    items3.save(KnowledgeItem(id=b.id, title="B", content="", space_id="p2"))
    imported_a3 = items3.save(
        KnowledgeItem(
            id=a.id, title=parsed.document.title, content=parsed.body, space_id=None,
            status=parsed.document.status,
            created_at=parsed.document.created_at, updated_at=parsed.document.updated_at,
        )
    )
    restorer3 = LinkImportRestorer(items3, links3, RepositoryLinkResolver(items3))
    restorer3.restore(imported_a3, parsed.document.links, parsed.body)
    row3 = links3.list_links(imported_a3.id)[0]
    assert row3.resolution == LinkResolution.CROSS_SPACE and row3.cross_space is True
    reexport3 = _export_doc(imported_a3, links3)
    assert reexport3.payload_hash() != source_doc.payload_hash()  # 诚实断言（H20）
    assert reexport3.content_hash() == source_doc.content_hash()
    # ③ 两种情形导出 links[] 只含白名单四子字段，不含 cross_space/派生键。
    for doc in (reexport_doc, reexport3):
        assert all(
            set(entry) == {"target_id", "title", "alias", "resolution"}
            for entry in doc.links
        )
        text = codec.dump(doc).text
        for forbidden in ("normalized_link_key", "link_normalization_version"):
            assert forbidden not in text
        assert "cross_space:" not in text  # 白名单不含 cross_space 布尔列键
    # ④ 固定非空 payload 的 review_payload_hash 两种情形均不变。
    assert review_payload_hash(_REVIEW_PROPOSAL) == review_before


def test_d1_canonicalization_version_still_one() -> None:
    assert CANONICALIZATION_VERSION == 1
    assert entities.CANONICALIZATION_VERSION == 1