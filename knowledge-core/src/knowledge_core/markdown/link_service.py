"""Wikilink 端口驱动服务层（V2 A1-03b/c，计划 §3② / §6 / §8.3）。

只经 ``knowledge_core.ports`` 端口与 ``ModelAdapter`` 之外的注入协作，
**零 ORM、零 dialect SQL、零 Session、零文件 IO**（D10/R19）：
``LinkKeyRebuild.plan()`` 只算计划，真实执行在 backend ``apply_link_key_plan()``。

两个 Core 单一事实来源纯函数（backend 仓库与 InMemory 测试替身共用，
不得出现第二套实现，计划 §7.7）：
- ``check_global_version_homogeneity``：全局版本同构判定（E1，§8.4.2）；
- ``check_plan_freshness``：重建计划逐行新鲜度判定（E6 门禁 C，§8.3.6）。

版本常量经 ``entities.LINK_NORMALIZATION_VERSION`` **动态读取**（不在导入时
固化），测试夹具 bump 常量时全链路一致生效。
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from knowledge_core.domain import entities
from knowledge_core.domain.entities import (
    KnowledgeItem,
    KnowledgeLink,
    KnowledgeStatus,
    LinkResolution,
    utcnow,
)
from knowledge_core.markdown import (
    BacklinkService,
    LinkRebuildService,
    LinkReresolveService,
    LinkResolver,
    LinkRestoreService,
    LinkSyncService,
)
from knowledge_core.markdown.links import (
    LINK_KEY_RULES,
    LinkHint,
    LinkWarning,
    LinkWarningCode,
    ParsedWikilink,
    WikilinkParser,
    group_hints_by_title_key,
    link_key_for_version,
    merge_same_key,
    normalized_link_key,
    normalized_title_key,
)
from knowledge_core.ports import KnowledgeRepository, LinkRepository

__all__ = [
    "BacklinkQuery",
    "BindingFirstLinkSync",
    "InvalidHint",
    "LinkCollisionEntry",
    "LinkCollisionGroup",
    "LinkImportRestorer",
    "LinkKeyRebuild",
    "LinkKeyUpdate",
    "LinkNormalizationVersionMismatch",
    "LinkRebuildPlan",
    "LinkRebuildReport",
    "LinkReresolve",
    "LinkRestoreReport",
    "LinkRowState",
    "LinkStaleReason",
    "LinkSyncReport",
    "PlanFreshnessResult",
    "RepositoryLinkResolver",
    "binding_semantics",
    "check_global_version_homogeneity",
    "check_plan_freshness",
]


# --- 异常（E1：backend 路由翻译为 409 + 稳定码 link_version_mismatch）---


class LinkNormalizationVersionMismatch(Exception):
    """链接规范化版本不同构（全局守卫 / Core 局部纵深防御共用）。

    scope="global"：backend 持久化边界全表预检；scope="local"：Core 同步
    对本 source 行的纵深防御检查。HTTP 层只回传稳定码，不回传本异常文本。
    """

    def __init__(
        self,
        *,
        observed_versions: Iterable[int],
        current_version: int,
        scope: Literal["global", "local"],
        link_id: UUID | None = None,
        row_version: int | None = None,
    ) -> None:
        self.observed_versions = sorted(set(observed_versions))
        self.current_version = current_version
        self.scope = scope
        self.link_id = link_id
        self.row_version = row_version
        super().__init__(
            f"链接规范化版本不同构: scope={scope} "
            f"observed={self.observed_versions} current={current_version}"
        )


# --- 纯函数①：全局版本同构判定（E1，§8.4.2；空表放行）---


def check_global_version_homogeneity(versions: Iterable[int], expected: int) -> None:
    """全表版本集合判定：空 → 放行；== {expected} → 放行；否则抛异常。

    纯函数：无 IO、无 Session、无模块级可变状态。查询由调用方负责
    （backend 单列 SELECT DISTINCT；InMemory 扫描 dict），每次受守卫写入
    重新执行，**无缓存**（R3.1，§8.4.3）。
    """
    observed = set(versions)
    if not observed:
        return
    if observed == {expected}:
        return
    raise LinkNormalizationVersionMismatch(
        observed_versions=sorted(observed),
        current_version=expected,
        scope="global",
    )


# --- 值类型（frozen + tuple，T38；不新增任何摘要/digest 字段，§8.3.8）---


class LinkRowState(BaseModel):
    """链接行只读快照（门禁 C 比对载体；target_id 携带但**不参与比对**）。"""

    model_config = ConfigDict(frozen=True)

    link_id: UUID
    source_id: UUID
    normalized_link_key: str
    link_normalization_version: int
    target_title: str
    alias: str | None
    target_id: UUID | None = None


class LinkKeyUpdate(BaseModel):
    """重建计划中的单行更新（只改键/版本两列 + updated_at，绝不触碰它列）。"""

    model_config = ConfigDict(frozen=True)

    link_id: UUID
    source_id: UUID
    old_key: str
    new_key: str
    old_version: int
    new_version: int
    target_id: UUID | None
    target_title: str
    alias: str | None


class LinkCollisionEntry(BaseModel):
    """碰撞组内的一行（保留全部原行信息，供用户处置）。"""

    model_config = ConfigDict(frozen=True)

    link_id: UUID
    source_id: UUID
    old_key: str
    new_key: str
    old_version: int
    target_id: UUID | None
    target_title: str
    alias: str | None


class LinkCollisionGroup(BaseModel):
    """一个 (source_id, new_key) 碰撞组（≥2 行）。"""

    model_config = ConfigDict(frozen=True)

    source_id: UUID
    new_key: str
    entries: tuple[LinkCollisionEntry, ...]


class LinkRebuildPlan(BaseModel):
    """Core ``plan()`` 产物：只算不写（零数据库写入、零文件 IO）。

    ``row_snapshots`` 覆盖全表**每一行（含 no-op 行）**——门禁 C 的比对基准；
    ``observed_row_count`` 为计划生成时全表行数。拒绝态计划同样携带快照。
    """

    model_config = ConfigDict(frozen=True)

    status: Literal["ready", "refused_collision", "refused_mixed_version"]
    source_version: int | None
    target_version: int
    updates: tuple[LinkKeyUpdate, ...]
    unchanged: int
    collision_groups: tuple[LinkCollisionGroup, ...]
    warnings: tuple[LinkWarning, ...]
    row_snapshots: tuple[LinkRowState, ...]
    observed_row_count: int
    requires_replan: bool


class LinkStaleReason(BaseModel):
    """门禁 C 的一条过期原因（稳定 reason_code + 脱敏摘要）。"""

    model_config = ConfigDict(frozen=True)

    reason_code: str
    link_id: UUID | None = None
    field: str | None = None
    expected: str | None = None
    actual: str | None = None


class PlanFreshnessResult(BaseModel):
    """门禁 C 判定结果（ok=False 时 reasons 非空）。"""

    model_config = ConfigDict(frozen=True)

    ok: bool
    reasons: tuple[LinkStaleReason, ...]


class LinkRebuildReport(BaseModel):
    """backend ``apply_link_key_plan()`` 的结构化执行报告（D10：Core 不写文件）。"""

    model_config = ConfigDict(frozen=True)

    status: str
    source_version: int | None
    target_version: int
    updated: int
    unchanged: int
    collision_groups: tuple[LinkCollisionGroup, ...]
    warnings: tuple[LinkWarning, ...]
    stale_reasons: tuple[LinkStaleReason, ...]
    requires_replan: bool
    observed_row_count: int


class LinkSyncReport(BaseModel):
    """绑定优先同步报告。ambiguous/conflict 为同步后存活行的状态计数。"""

    model_config = ConfigDict(frozen=True)

    created: int
    kept: int
    removed: int
    ambiguous: int
    conflict: int
    warnings: tuple[LinkWarning, ...]


class InvalidHint(BaseModel):
    """无效绑定提示（三类语义分离：无效 ≠ 矛盾，不参与投票）。"""

    model_config = ConfigDict(frozen=True)

    hint: LinkHint
    reason: Literal["no_target_id", "malformed_uuid", "target_not_found"]


class LinkRestoreReport(BaseModel):
    """导入绑定恢复报告（先聚合再判定；保留冲突双方与无效/孤儿提示）。"""

    model_config = ConfigDict(frozen=True)

    restored: int
    conflicts: int
    fallbacks: int
    kept: int
    orphan_hints: tuple[LinkHint, ...]
    invalid_hints: tuple[InvalidHint, ...]
    unresolved_links: tuple[str, ...]
    warnings: tuple[LinkWarning, ...]


# --- 纯函数②：重建计划逐行新鲜度（E6 门禁 C，§8.3.6）---


def check_plan_freshness(
    plan: LinkRebuildPlan, current_rows: Sequence[LinkRowState]
) -> PlanFreshnessResult:
    """比对「计划快照」与「apply 事务内重读的当前全表」，逐行判定新鲜度。

    规则（§8.3.6）：双向覆盖 + link_id 唯一 + 6 字段**原始 Unicode 精确等值**
    （比对前不做 NFKC/casefold/空白折叠，None ≠ ""）+ **每行新键重算**
    （update 行与 no-op 行都算，篡改与 no-op 盲区因此被发现）。
    纯函数：无 IO、无 Session 参数、无模块级可变状态。
    target_id/resolution/cross_space/created_at/updated_at **不比对**
    （重建不写它们；治理写入在窗口内合法改变它们）。
    """
    reasons: list[LinkStaleReason] = []
    if plan.status != "ready":
        reasons.append(LinkStaleReason(reason_code="plan_not_ready", field="status", actual=plan.status))
        return PlanFreshnessResult(ok=False, reasons=tuple(reasons))
    if plan.target_version not in LINK_KEY_RULES:
        reasons.append(
            LinkStaleReason(
                reason_code="unsupported_target_version",
                field="target_version",
                actual=str(plan.target_version),
            )
        )
        return PlanFreshnessResult(ok=False, reasons=tuple(reasons))

    snap_ids = [s.link_id for s in plan.row_snapshots]
    upd_ids = [u.link_id for u in plan.updates]
    for lid, count in Counter(snap_ids).items():
        if count > 1:
            reasons.append(LinkStaleReason(reason_code="duplicate_link_id_in_plan", link_id=lid, field="row_snapshots"))
    for lid, count in Counter(upd_ids).items():
        if count > 1:
            reasons.append(LinkStaleReason(reason_code="duplicate_link_id_in_plan", link_id=lid, field="updates"))

    snap_by_id = {s.link_id: s for s in plan.row_snapshots}
    upd_by_id = {u.link_id: u for u in plan.updates}
    current_by_id = {r.link_id: r for r in current_rows}

    for lid in upd_by_id:
        if lid not in snap_by_id:
            reasons.append(LinkStaleReason(reason_code="update_row_not_in_plan", link_id=lid))

    if plan.observed_row_count != len(current_rows):
        reasons.append(
            LinkStaleReason(
                reason_code="row_not_covered",
                field="observed_row_count",
                expected=str(len(current_rows)),
                actual=str(plan.observed_row_count),
            )
        )
    if plan.observed_row_count != len(plan.row_snapshots):
        reasons.append(
            LinkStaleReason(
                reason_code="row_not_covered",
                field="observed_row_count",
                expected=str(len(plan.row_snapshots)),
                actual=str(plan.observed_row_count),
            )
        )

    for lid in sorted(set(snap_by_id) - set(current_by_id), key=str):
        reasons.append(LinkStaleReason(reason_code="row_deleted", link_id=lid))
    for lid in sorted(set(current_by_id) - set(snap_by_id), key=str):
        reasons.append(LinkStaleReason(reason_code="row_added", link_id=lid))
        reasons.append(LinkStaleReason(reason_code="row_not_covered", link_id=lid))

    for lid in sorted(current_by_id, key=str):
        cur = current_by_id[lid]
        snap = snap_by_id.get(lid)
        if snap is not None:
            if snap.source_id != cur.source_id:
                reasons.append(LinkStaleReason(reason_code="source_id_changed", link_id=lid, field="source_id", expected=str(snap.source_id), actual=str(cur.source_id)))
            if snap.normalized_link_key != cur.normalized_link_key:
                reasons.append(LinkStaleReason(reason_code="key_changed", link_id=lid, field="normalized_link_key", expected=snap.normalized_link_key, actual=cur.normalized_link_key))
            if snap.link_normalization_version != cur.link_normalization_version:
                reasons.append(LinkStaleReason(reason_code="version_changed", link_id=lid, field="link_normalization_version", expected=str(snap.link_normalization_version), actual=str(cur.link_normalization_version)))
            if snap.target_title != cur.target_title:
                reasons.append(LinkStaleReason(reason_code="target_title_changed", link_id=lid, field="target_title", expected=snap.target_title, actual=cur.target_title))
            if snap.alias != cur.alias:
                reasons.append(LinkStaleReason(reason_code="alias_changed", link_id=lid, field="alias", expected=snap.alias, actual=cur.alias))

        expected_key = link_key_for_version(plan.target_version, cur.target_title, cur.alias)
        upd = upd_by_id.get(lid)
        if upd is not None:
            if upd.new_key != expected_key:
                reasons.append(LinkStaleReason(reason_code="new_key_mismatch", link_id=lid, field="new_key", expected=expected_key, actual=upd.new_key))
            if upd.new_version != plan.target_version:
                reasons.append(LinkStaleReason(reason_code="new_version_mismatch", link_id=lid, field="new_version", expected=str(plan.target_version), actual=str(upd.new_version)))
            if upd.old_key != cur.normalized_link_key:
                reasons.append(LinkStaleReason(reason_code="key_changed", link_id=lid, field="old_key", expected=cur.normalized_link_key, actual=upd.old_key))
            if upd.old_version != cur.link_normalization_version:
                reasons.append(LinkStaleReason(reason_code="version_changed", link_id=lid, field="old_version", expected=str(cur.link_normalization_version), actual=str(upd.old_version)))
            if upd.source_id != cur.source_id:
                reasons.append(LinkStaleReason(reason_code="source_id_changed", link_id=lid, field="source_id", expected=str(cur.source_id), actual=str(upd.source_id)))
            if upd.target_title != cur.target_title:
                reasons.append(LinkStaleReason(reason_code="target_title_changed", link_id=lid, field="target_title", expected=cur.target_title, actual=upd.target_title))
            if upd.alias != cur.alias:
                reasons.append(LinkStaleReason(reason_code="alias_changed", link_id=lid, field="alias", expected=cur.alias, actual=upd.alias))
        elif (
            cur.normalized_link_key != expected_key
            or cur.link_normalization_version != plan.target_version
        ):
            # no-op 行盲区（T37）：不在 updates 中的行也必须已是目标版本键。
            reasons.append(
                LinkStaleReason(
                    reason_code="noop_row_requires_update",
                    link_id=lid,
                    field="normalized_link_key",
                    expected=expected_key,
                    actual=cur.normalized_link_key,
                )
            )

    return PlanFreshnessResult(ok=not reasons, reasons=tuple(reasons))


# --- E2 空间语义（§6.6：按当前空间关系重算，绝不伪装 resolved+False）---


def binding_semantics(
    source_space_id: str | None,
    target: KnowledgeItem,
    *,
    title: str,
    alias: str | None,
) -> tuple[LinkResolution, bool, list[LinkWarning]]:
    """有效 UUID 提示恢复绑定时的 resolution/cross_space 判定（None==None 同空间）。

    archived 不改变 resolution/cross_space，只附 archived warning（D7 一致）。
    """
    warnings: list[LinkWarning] = []
    same_space = source_space_id == target.space_id
    resolution = LinkResolution.RESOLVED if same_space else LinkResolution.CROSS_SPACE
    cross_space = not same_space
    if cross_space:
        warnings.append(
            LinkWarning(
                code=LinkWarningCode.CROSS_SPACE_BINDING_RESTORED,
                message=(
                    f"跨空间绑定恢复：源空间 {source_space_id!r} ≠ 目标空间 "
                    f"{target.space_id!r}（target_id={target.id}，title={title!r}，"
                    f"alias={alias!r}）。"
                ),
                title=title,
                alias=alias,
                target_id=str(target.id),
            )
        )
    if target.status == KnowledgeStatus.ARCHIVED:
        warnings.append(
            LinkWarning(
                code=LinkWarningCode.ARCHIVED_TARGET_RESTORED,
                message=(
                    f"绑定目标已归档（显式绑定意图保留，D7）：target_id={target.id}，"
                    f"title={title!r}，alias={alias!r}。"
                ),
                title=title,
                alias=alias,
                target_id=str(target.id),
            )
        )
    return resolution, cross_space, warnings


def _assert_link_invariants(link: KnowledgeLink) -> None:
    """服务层不变量（实体校验器之外）：ambiguous/conflict 无绑定；cross_space ⟺ resolution。"""
    if link.resolution in (LinkResolution.AMBIGUOUS, LinkResolution.CONFLICT) and link.target_id is not None:
        raise ValueError(f"resolution={link.resolution} 不得绑定 target_id（不随机绑定）")
    if link.cross_space != (link.resolution == LinkResolution.CROSS_SPACE):
        raise ValueError("服务层不变量违反：cross_space=True ⟺ resolution=cross_space")


def _title_key_or_none(title: str) -> str | None:
    try:
        return normalized_title_key(title)
    except ValueError:
        return None


def _to_hint(raw: Mapping[str, Any]) -> LinkHint:
    """交换 dict → 提示值类型；target_id 保留原始文本（非法 UUID 不在此拒绝）。"""
    target_id = raw.get("target_id")
    return LinkHint(
        title=raw.get("title"),
        alias=raw.get("alias"),
        target_id=None if target_id is None else str(target_id),
        resolution=raw.get("resolution"),
    )


# --- 具体服务（ABC 在 markdown/__init__.py）---


class RepositoryLinkResolver(LinkResolver):
    """标题键解析（D7：自动排除 archived、允许自链接；E5：精确空间等值过滤）。"""

    def __init__(self, items: KnowledgeRepository) -> None:
        self._items = items

    def auto_candidates(self, source: KnowledgeItem) -> list[KnowledgeItem]:
        # ⚠ E5/R24：space_id=None 时仓库 list 返回全库，必须 Core 侧再精确过滤
        # （None==None 视为同空间）；archived 仅排除自动解析（D7）。
        raw = self._items.list(
            space_id=source.space_id, include_unassigned=(source.space_id is None)
        )
        return [
            item
            for item in raw
            if item.space_id == source.space_id and item.status != KnowledgeStatus.ARCHIVED
        ]

    def resolve(
        self,
        literal: ParsedWikilink,
        source: KnowledgeItem,
        candidates: Sequence[KnowledgeItem],
    ) -> KnowledgeLink:
        title_key = _title_key_or_none(literal.title)
        matches = [
            c for c in candidates if title_key is not None and _title_key_or_none(c.title) == title_key
        ]
        if len(matches) == 1:
            resolution, target_id = LinkResolution.RESOLVED, matches[0].id
        elif len(matches) > 1:
            resolution, target_id = LinkResolution.AMBIGUOUS, None
        else:
            resolution, target_id = LinkResolution.MISSING, None
        return KnowledgeLink(
            source_id=source.id,
            target_id=target_id,
            target_title=literal.title,
            alias=literal.alias,
            normalized_link_key=literal.normalized_link_key,
            link_normalization_version=entities.LINK_NORMALIZATION_VERSION,
            resolution=resolution,
            cross_space=False,
        )

    def find_candidates(self, title: str) -> list[KnowledgeItem]:
        """只读候选发现：全库标题键匹配（含 archived/跨空间，带 status 供标注）。"""
        title_key = _title_key_or_none(title)
        if title_key is None:
            return []
        return [
            item
            for item in self._items.list()
            if _title_key_or_none(item.title) == title_key
        ]

    def bind_explicit(
        self,
        source: KnowledgeItem,
        target: KnowledgeItem,
        *,
        title: str,
        alias: str | None = None,
    ) -> tuple[KnowledgeLink, list[LinkWarning]]:
        """Core 层显式绑定（D7/D8：允许 archived/跨空间；**无 HTTP 写入口**）。

        返回未保存的链接实体与告警；调用方经 LinkRepository.save_link 持久化。
        """
        resolution, cross_space, warnings = binding_semantics(
            source.space_id, target, title=title, alias=alias
        )
        link = KnowledgeLink(
            source_id=source.id,
            target_id=target.id,
            target_title=title,
            alias=alias,
            normalized_link_key=normalized_link_key(title, alias),
            link_normalization_version=entities.LINK_NORMALIZATION_VERSION,
            resolution=resolution,
            cross_space=cross_space,
        )
        _assert_link_invariants(link)
        return link, warnings


class BindingFirstLinkSync(LinkSyncService):
    """绑定优先同步（§6.4）：按键匹配，绑定行不重解析，未绑定不 churn，新键解析，消失键删除。"""

    def __init__(
        self,
        items: KnowledgeRepository,
        links: LinkRepository,
        resolver: LinkResolver,
    ) -> None:
        self._items = items
        self._links = links
        self._resolver = resolver

    def sync(self, item: KnowledgeItem, body: str) -> LinkSyncReport:
        rows = self._links.list_links(item.id)
        # Core 局部守卫（纵深防御，非全局权威；all([])==True 空放行是已知边界，
        # 全局同构由 backend 持久化边界预检保证，T16 双层对照）。
        current_version = entities.LINK_NORMALIZATION_VERSION
        bad = [r for r in rows if r.link_normalization_version != current_version]
        if bad:
            raise LinkNormalizationVersionMismatch(
                observed_versions={r.link_normalization_version for r in rows},
                current_version=current_version,
                scope="local",
                link_id=bad[0].id,
                row_version=bad[0].link_normalization_version,
            )
        parsed, warnings = WikilinkParser.parse(body)
        merged = merge_same_key(parsed)
        existing = {r.normalized_link_key: r for r in rows}
        candidates = self._resolver.auto_candidates(item)
        created = kept = removed = 0
        new_links: list[KnowledgeLink] = []
        merged_keys: set[str] = set()
        for literal in merged:
            merged_keys.add(literal.normalized_link_key)
            old = existing.get(literal.normalized_link_key)
            if old is not None:
                kept += 1  # 绑定/未绑定行一律保留（不重解析、不 churn id/时间戳）
                continue
            link = self._resolver.resolve(literal, item, candidates)
            _assert_link_invariants(link)
            self._links.save_link(link)
            new_links.append(link)
            created += 1
        for key, old in existing.items():
            if key not in merged_keys:
                self._links.delete_link(old.id)
                removed += 1
        surviving = [existing[k] for k in merged_keys if k in existing] + new_links
        return LinkSyncReport(
            created=created,
            kept=kept,
            removed=removed,
            ambiguous=sum(1 for r in surviving if r.resolution == LinkResolution.AMBIGUOUS),
            conflict=sum(1 for r in surviving if r.resolution == LinkResolution.CONFLICT),
            warnings=tuple(warnings),
        )


class LinkImportRestorer(LinkRestoreService):
    """导入绑定恢复（§6.5 先聚合再判定 + §6.6 空间重算；正文是存在性权威 D4）。"""

    def __init__(
        self,
        items: KnowledgeRepository,
        links: LinkRepository,
        resolver: LinkResolver,
    ) -> None:
        self._items = items
        self._links = links
        self._resolver = resolver

    def restore(
        self,
        item: KnowledgeItem,
        frontmatter_links: Sequence[Mapping[str, Any]],
        body: str,
    ) -> LinkRestoreReport:
        parsed, parse_warnings = WikilinkParser.parse(body)
        literals = merge_same_key(parsed)
        groups = group_hints_by_title_key([_to_hint(h) for h in frontmatter_links])
        existing = {r.normalized_link_key: r for r in self._links.list_links(item.id)}
        candidates = self._resolver.auto_candidates(item)
        warnings: list[LinkWarning] = list(parse_warnings)
        restored = conflicts = fallbacks = kept = 0
        invalid: list[InvalidHint] = []
        body_title_keys: set[str] = set()

        for literal in literals:
            title_key = normalized_title_key(literal.title)
            body_title_keys.add(title_key)
            valid: list[tuple[LinkHint, KnowledgeItem]] = []
            for hint in groups.get(title_key, []):
                if hint.target_id is None:
                    invalid.append(InvalidHint(hint=hint, reason="no_target_id"))
                    warnings.append(
                        LinkWarning(
                            code=LinkWarningCode.INVALID_HINT_NO_TARGET_ID,
                            message=f"提示缺少 target_id（无效，不参与投票）：title={hint.title!r} alias={hint.alias!r}。",
                            title=hint.title,
                            alias=hint.alias,
                        )
                    )
                    continue
                try:
                    target_uuid = UUID(hint.target_id)
                except ValueError:
                    invalid.append(InvalidHint(hint=hint, reason="malformed_uuid"))
                    warnings.append(
                        LinkWarning(
                            code=LinkWarningCode.INVALID_HINT_MALFORMED_UUID,
                            message=f"提示 target_id 非法 UUID（无效，不参与投票）：{hint.target_id!r}，title={hint.title!r} alias={hint.alias!r}。",
                            title=hint.title,
                            alias=hint.alias,
                            target_id=hint.target_id,
                        )
                    )
                    continue
                target = self._items.get(target_uuid)
                if target is None:
                    invalid.append(InvalidHint(hint=hint, reason="target_not_found"))
                    warnings.append(
                        LinkWarning(
                            code=LinkWarningCode.INVALID_HINT_TARGET_NOT_FOUND,
                            message=f"提示目标不存在（无效，不参与投票，回退标题解析）：target_id={hint.target_id}，title={hint.title!r} alias={hint.alias!r}。",
                            title=hint.title,
                            alias=hint.alias,
                            target_id=hint.target_id,
                        )
                    )
                    continue
                valid.append((hint, target))

            old = existing.get(literal.normalized_link_key)
            if old is not None and old.target_id is not None:
                kept += 1  # 绑定优先：既有绑定不被提示/回退覆盖（人工裁决保留）
                continue

            distinct = {t.id for _, t in valid}
            if len(distinct) == 1:
                target = valid[0][1]
                resolution, cross_space, sem_warnings = binding_semantics(
                    item.space_id, target, title=literal.title, alias=literal.alias
                )
                warnings.extend(sem_warnings)
                if old is not None:
                    updated = old.model_copy(
                        update={
                            "target_id": target.id,
                            "resolution": resolution,
                            "cross_space": cross_space,
                            "updated_at": utcnow(),
                        }
                    )
                    _assert_link_invariants(updated)
                    self._links.update_link(updated)
                else:
                    link = KnowledgeLink(
                        source_id=item.id,
                        target_id=target.id,
                        target_title=literal.title,
                        alias=literal.alias,
                        normalized_link_key=literal.normalized_link_key,
                        link_normalization_version=entities.LINK_NORMALIZATION_VERSION,
                        resolution=resolution,
                        cross_space=cross_space,
                    )
                    _assert_link_invariants(link)
                    self._links.save_link(link)
                restored += 1
            elif len(distinct) > 1:
                warnings.append(
                    LinkWarning(
                        code=LinkWarningCode.CONFLICTING_HINTS,
                        message=(
                            f"矛盾绑定提示（有效目标 >1，conflict，保留全部信息）："
                            f"title={literal.title!r} alias={literal.alias!r} "
                            f"target_ids={sorted(str(t) for t in distinct)}；"
                            f"提示明细={[(h.title, h.alias, h.target_id) for h, _ in valid]}。"
                        ),
                        title=literal.title,
                        alias=literal.alias,
                        target_ids=tuple(sorted(str(t) for t in distinct)),
                    )
                )
                if old is not None:
                    updated = old.model_copy(
                        update={
                            "target_id": None,
                            "resolution": LinkResolution.CONFLICT,
                            "cross_space": False,
                            "updated_at": utcnow(),
                        }
                    )
                    _assert_link_invariants(updated)
                    self._links.update_link(updated)
                else:
                    link = KnowledgeLink(
                        source_id=item.id,
                        target_id=None,
                        target_title=literal.title,
                        alias=literal.alias,
                        normalized_link_key=literal.normalized_link_key,
                        link_normalization_version=entities.LINK_NORMALIZATION_VERSION,
                        resolution=LinkResolution.CONFLICT,
                        cross_space=False,
                    )
                    _assert_link_invariants(link)
                    self._links.save_link(link)
                conflicts += 1
            else:
                fresh = self._resolver.resolve(literal, item, candidates)
                if old is not None:
                    if old.resolution == fresh.resolution and old.target_id == fresh.target_id:
                        kept += 1
                        continue
                    updated = old.model_copy(
                        update={
                            "target_id": fresh.target_id,
                            "resolution": fresh.resolution,
                            "cross_space": False,
                            "updated_at": utcnow(),
                        }
                    )
                    _assert_link_invariants(updated)
                    self._links.update_link(updated)
                else:
                    _assert_link_invariants(fresh)
                    self._links.save_link(fresh)
                fallbacks += 1

        orphan: list[LinkHint] = []
        for title_key, group in groups.items():
            if title_key not in body_title_keys:
                for hint in group:
                    orphan.append(hint)
                    warnings.append(
                        LinkWarning(
                            code=LinkWarningCode.ORPHAN_HINT,
                            message=f"孤儿提示（标题键不在正文，不建行）：title={hint.title!r} alias={hint.alias!r} target_id={hint.target_id!r}。",
                            title=hint.title,
                            alias=hint.alias,
                            target_id=hint.target_id,
                        )
                    )

        final_rows = self._links.list_links(item.id)
        unresolved = tuple(
            r.normalized_link_key
            for r in final_rows
            if r.resolution in (LinkResolution.MISSING, LinkResolution.AMBIGUOUS)
        )
        return LinkRestoreReport(
            restored=restored,
            conflicts=conflicts,
            fallbacks=fallbacks,
            kept=kept,
            orphan_hints=tuple(orphan),
            invalid_hints=tuple(invalid),
            unresolved_links=unresolved,
            warnings=tuple(warnings),
        )


class BacklinkQuery(BacklinkService):
    """反链查询：按稳定 target_id（改名不断链）。"""

    def __init__(self, links: LinkRepository) -> None:
        self._links = links

    def backlinks(self, target_id: UUID) -> list[KnowledgeLink]:
        return self._links.list_backlinks(target_id)


class LinkReresolve(LinkReresolveService):
    """显式重解析：只重试 missing/ambiguous，守同一套自动解析规则；不 churn 未变行。"""

    def __init__(
        self,
        items: KnowledgeRepository,
        links: LinkRepository,
        resolver: LinkResolver,
    ) -> None:
        self._items = items
        self._links = links
        self._resolver = resolver

    def reresolve(self, item: KnowledgeItem) -> LinkSyncReport:
        rows = self._links.list_links(item.id)
        candidates = self._resolver.auto_candidates(item)
        changed = 0
        for row in rows:
            if row.resolution not in (LinkResolution.MISSING, LinkResolution.AMBIGUOUS):
                continue
            literal = ParsedWikilink(
                title=row.target_title,
                alias=row.alias,
                normalized_link_key=row.normalized_link_key,
            )
            fresh = self._resolver.resolve(literal, item, candidates)
            if fresh.resolution == row.resolution and fresh.target_id == row.target_id:
                continue
            updated = row.model_copy(
                update={
                    "target_id": fresh.target_id,
                    "resolution": fresh.resolution,
                    "cross_space": False,
                    "updated_at": utcnow(),
                }
            )
            _assert_link_invariants(updated)
            self._links.update_link(updated)
            changed += 1
        final_rows = self._links.list_links(item.id)
        return LinkSyncReport(
            created=0,
            kept=len(final_rows) - changed,
            removed=0,
            ambiguous=sum(1 for r in final_rows if r.resolution == LinkResolution.AMBIGUOUS),
            conflict=sum(1 for r in final_rows if r.resolution == LinkResolution.CONFLICT),
            warnings=(),
        )


class LinkKeyRebuild(LinkRebuildService):
    """规范化键重建**计划**（E4：只算不写；真实执行在 backend apply）。

    零数据库写入（只读 list_all_links）、零文件 IO（D10/R19，T12 行为守护）。
    有碰撞 → refused_collision 整体拒绝（全部碰撞组完整列出）；
    混合版本 → refused_mixed_version；绝不部分重建/合并/随机重绑。
    """

    def __init__(self, links: LinkRepository) -> None:
        self._links = links

    def plan(self, target_version: int) -> LinkRebuildPlan:
        if target_version not in LINK_KEY_RULES:
            raise ValueError(f"未注册的链接规范化版本: {target_version}")
        rows = self._links.list_all_links()
        snapshots = tuple(
            LinkRowState(
                link_id=r.id,
                source_id=r.source_id,
                normalized_link_key=r.normalized_link_key,
                link_normalization_version=r.link_normalization_version,
                target_title=r.target_title,
                alias=r.alias,
                target_id=r.target_id,
            )
            for r in rows
        )
        versions = {r.link_normalization_version for r in rows}
        if len(versions) > 1:
            return LinkRebuildPlan(
                status="refused_mixed_version",
                source_version=None,
                target_version=target_version,
                updates=(),
                unchanged=len(rows),
                collision_groups=(),
                warnings=(
                    LinkWarning(
                        code=LinkWarningCode.REBUILD_MIXED_VERSION,
                        message=f"全表版本混合 {sorted(versions)}，拒绝重建（须先恢复同构）。",
                    ),
                ),
                row_snapshots=snapshots,
                observed_row_count=len(rows),
                requires_replan=True,
            )
        source_version = versions.pop() if versions else target_version
        new_keys: dict[UUID, str] = {}
        groups: dict[tuple[UUID, str], list[KnowledgeLink]] = {}
        for row in rows:
            new_key = link_key_for_version(target_version, row.target_title, row.alias)
            new_keys[row.id] = new_key
            groups.setdefault((row.source_id, new_key), []).append(row)
        collisions = [
            LinkCollisionGroup(
                source_id=source_id,
                new_key=new_key,
                entries=tuple(
                    LinkCollisionEntry(
                        link_id=r.id,
                        source_id=r.source_id,
                        old_key=r.normalized_link_key,
                        new_key=new_key,
                        old_version=r.link_normalization_version,
                        target_id=r.target_id,
                        target_title=r.target_title,
                        alias=r.alias,
                    )
                    for r in members
                ),
            )
            for (source_id, new_key), members in groups.items()
            if len(members) >= 2
        ]
        if collisions:
            collisions.sort(key=lambda g: (str(g.source_id), g.new_key))
            return LinkRebuildPlan(
                status="refused_collision",
                source_version=source_version,
                target_version=target_version,
                updates=(),
                unchanged=len(rows),
                collision_groups=tuple(collisions),
                warnings=tuple(
                    LinkWarning(
                        code=LinkWarningCode.REBUILD_COLLISION,
                        message=(
                            f"碰撞组 (source_id={g.source_id}, new_key={g.new_key!r}) "
                            f"含 {len(g.entries)} 行；整体拒绝，零写入，等用户处置后重跑。"
                        ),
                    )
                    for g in collisions
                ),
                row_snapshots=snapshots,
                observed_row_count=len(rows),
                requires_replan=True,
            )
        updates = tuple(
            LinkKeyUpdate(
                link_id=r.id,
                source_id=r.source_id,
                old_key=r.normalized_link_key,
                new_key=new_keys[r.id],
                old_version=r.link_normalization_version,
                new_version=target_version,
                target_id=r.target_id,
                target_title=r.target_title,
                alias=r.alias,
            )
            for r in rows
            if not (
                new_keys[r.id] == r.normalized_link_key
                and r.link_normalization_version == target_version
            )
        )
        return LinkRebuildPlan(
            status="ready",
            source_version=source_version,
            target_version=target_version,
            updates=updates,
            unchanged=len(rows) - len(updates),
            collision_groups=(),
            warnings=(),
            row_snapshots=snapshots,
            observed_row_count=len(rows),
            requires_replan=False,
        )