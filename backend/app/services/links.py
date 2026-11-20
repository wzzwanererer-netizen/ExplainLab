"""双向链接持久化与键重建执行（V2 A1-03，计划 §3③ / §8.3 / §8.4）。

- ``SQLAlchemyLinkRepository`` 实现 ``knowledge_core.ports.LinkRepository`` 端口。
  **全局版本同构守卫的权威执行点**：每次受守卫写入（save_link / 改键或改版本的
  update_link）在同一数据库事务内、写入之前执行单列 ``SELECT DISTINCT
  link_normalization_version``，交 Core 纯函数 ``check_global_version_homogeneity``
  判定。**无缓存**（R3.1，§8.4.3（3））：不存储、不复用任何版本集合结论；
  治理列-only 更新与删除豁免（不改变版本集合）。
- **读取侧防御映射（D12）**：``target_item_id`` 为 NULL 且列为 resolved/cross_space
  的**非法组合**映射为 ``resolution=missing`` + ``cross_space=False``（外部级联/
  历史脏数据不抛异常）；ambiguous/conflict 的合法 NULL 绑定原样保留。
  实体校验器不被弱化。
- ``apply_link_key_plan()`` 是重建写入的**唯一执行入口**（非端口方法）：
  独占单事务十步顺序（§8.3.7）——门禁 A（DISTINCT == plan.source_version）→
  6 列重读 → 门禁 B（覆盖 + 新键无重复）→ 门禁 C（Core ``check_plan_freshness``）→
  新键唯一性再验 → 批量只写 3 列 → 写后复核 → 提交；任一失败整体回滚。
- ``demote_backlinks_on_delete()``：删除目标条目前同事务降级入链（D12 写侧）。
- ``persist_rebuild_report()``：报告落盘（D10，backend 侧 IO；Core 零文件 IO）。

方言边界：预检/重读/批量写全部为 SQLAlchemy 表达式，SQLite 与 PostgreSQL
同一段代码、零方言分支（AGENTS.md §5）。仓库只 ``flush()``，不 commit/rollback/
begin_nested；事务边界由调用方（路由 / apply 的 ``with session.begin():``）持有。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.locking import acquire_rebuild_write_lock
from app.models import KnowledgeItemORM, KnowledgeLinkORM
from app.services.errors import NotFoundError
from app.services.knowledge import SQLAlchemyKnowledgeRepository
from knowledge_core.domain import entities
from knowledge_core.domain.entities import KnowledgeLink, LinkResolution, utcnow
from knowledge_core.markdown.link_service import (
    BindingFirstLinkSync,
    LinkImportRestorer,
    LinkRebuildPlan,
    LinkRebuildReport,
    LinkRowState,
    LinkStaleReason,
    RepositoryLinkResolver,
    check_global_version_homogeneity,
    check_plan_freshness,
)
from knowledge_core.markdown.links import LINK_KEY_RULES, link_key_for_version


class LinkRebuildPostWriteError(Exception):
    """重建写后复核失败（步 8）：必须整体回滚，不是拒绝报告。"""


def _utc(dt: datetime) -> datetime:
    """方言边界：SQLite DateTime 回读为 naive（实际存 UTC），补 UTC 时区；
    PostgreSQL timestamptz 回读带会话时区（如 Asia/Shanghai），换算到 UTC。
    实体层时间一律 UTC-aware，双方言往返一致。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _to_entity(row: KnowledgeLinkORM) -> KnowledgeLink:
    """ORM → 实体；D12 读取侧防御映射：NULL 绑定 + resolved/cross_space 的
    **非法组合**（外部级联/历史脏数据）降级为 missing + cross_space=False，
    不抛异常、不弱化实体校验器。ambiguous/conflict 行合法地 target_id=None
    （§6.4 服务级不变量），其 resolution 原样保留，不被误降级。"""
    target_id = UUID(row.target_item_id) if row.target_item_id is not None else None
    stored = LinkResolution(row.resolution)
    if target_id is None:
        if stored in (LinkResolution.RESOLVED, LinkResolution.CROSS_SPACE):
            resolution, cross_space = LinkResolution.MISSING, False
        else:
            resolution, cross_space = stored, False
    else:
        resolution, cross_space = stored, row.cross_space
    return KnowledgeLink(
        id=UUID(row.id),
        source_id=UUID(row.source_item_id),
        target_id=target_id,
        target_title=row.target_title,
        alias=row.alias,
        normalized_link_key=row.normalized_link_key,
        link_normalization_version=row.link_normalization_version,
        resolution=resolution,
        cross_space=cross_space,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
    )


def _precheck_global_version(session: Session) -> None:
    """单列 DISTINCT 预检（不加载 ORM 实体）；结果即丢弃，绝不缓存。"""
    stmt = select(KnowledgeLinkORM.link_normalization_version).distinct()
    versions = session.execute(stmt).scalars().all()
    check_global_version_homogeneity(versions, entities.LINK_NORMALIZATION_VERSION)


class SQLAlchemyLinkRepository:
    """LinkRepository 端口的 SQLAlchemy 实现（10 个方法，签名与 A1-01 一致）。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save_link(self, link: KnowledgeLink) -> KnowledgeLink:
        _precheck_global_version(self._session)
        row = KnowledgeLinkORM(
            id=str(link.id),
            source_item_id=str(link.source_id),
            target_item_id=None if link.target_id is None else str(link.target_id),
            target_title=link.target_title,
            alias=link.alias,
            normalized_link_key=link.normalized_link_key,
            link_normalization_version=link.link_normalization_version,
            resolution=link.resolution.value,
            cross_space=link.cross_space,
            created_at=link.created_at,
            updated_at=link.updated_at,
        )
        self._session.add(row)
        self._session.flush()
        return _to_entity(row)

    def get_link(self, link_id: UUID) -> KnowledgeLink | None:
        row = self._session.get(KnowledgeLinkORM, str(link_id))
        return _to_entity(row) if row is not None else None

    def list_links(self, source_id: UUID) -> list[KnowledgeLink]:
        stmt = (
            select(KnowledgeLinkORM)
            .where(KnowledgeLinkORM.source_item_id == str(source_id))
            .order_by(KnowledgeLinkORM.created_at, KnowledgeLinkORM.id)
        )
        return [_to_entity(row) for row in self._session.scalars(stmt)]

    def list_backlinks(self, target_id: UUID) -> list[KnowledgeLink]:
        stmt = (
            select(KnowledgeLinkORM)
            .where(KnowledgeLinkORM.target_item_id == str(target_id))
            .order_by(KnowledgeLinkORM.created_at, KnowledgeLinkORM.id)
        )
        return [_to_entity(row) for row in self._session.scalars(stmt)]

    def find_by_key(
        self, source_id: UUID, normalized_link_key: str
    ) -> KnowledgeLink | None:
        stmt = select(KnowledgeLinkORM).where(
            KnowledgeLinkORM.source_item_id == str(source_id),
            KnowledgeLinkORM.normalized_link_key == normalized_link_key,
        )
        row = self._session.scalars(stmt).first()
        return _to_entity(row) if row is not None else None

    def list_by_key(self, normalized_link_key: str) -> list[KnowledgeLink]:
        stmt = (
            select(KnowledgeLinkORM)
            .where(KnowledgeLinkORM.normalized_link_key == normalized_link_key)
            .order_by(KnowledgeLinkORM.created_at, KnowledgeLinkORM.id)
        )
        return [_to_entity(row) for row in self._session.scalars(stmt)]

    def list_all_links(self) -> list[KnowledgeLink]:
        stmt = select(KnowledgeLinkORM).order_by(
            KnowledgeLinkORM.source_item_id,
            KnowledgeLinkORM.normalized_link_key,
            KnowledgeLinkORM.id,
        )
        return [_to_entity(row) for row in self._session.scalars(stmt)]

    def update_link(self, link: KnowledgeLink) -> KnowledgeLink:
        row = self._session.get(KnowledgeLinkORM, str(link.id))
        if row is None:
            raise NotFoundError(f"链接不存在: {link.id}")
        # 守卫范围（§8.4.3 表）：仅改键/改版本受守卫；治理列-only 更新豁免。
        if (
            row.normalized_link_key != link.normalized_link_key
            or row.link_normalization_version != link.link_normalization_version
        ):
            _precheck_global_version(self._session)
        row.target_item_id = None if link.target_id is None else str(link.target_id)
        row.target_title = link.target_title
        row.alias = link.alias
        row.normalized_link_key = link.normalized_link_key
        row.link_normalization_version = link.link_normalization_version
        row.resolution = link.resolution.value
        row.cross_space = link.cross_space
        row.updated_at = link.updated_at
        self._session.flush()
        return _to_entity(row)

    def delete_link(self, link_id: UUID) -> bool:
        row = self._session.get(KnowledgeLinkORM, str(link_id))
        if row is None:
            return False
        self._session.delete(row)
        self._session.flush()
        return True

    def delete_links_of_item(self, source_id: UUID) -> int:
        """仅用于知识条目删除或显式重置（D3）；常规保存走绑定优先同步。"""
        stmt = select(KnowledgeLinkORM).where(
            KnowledgeLinkORM.source_item_id == str(source_id)
        )
        rows = list(self._session.scalars(stmt))
        for row in rows:
            self._session.delete(row)
        self._session.flush()
        return len(rows)


def demote_backlinks_on_delete(session: Session, target_id: UUID) -> int:
    """D12 写侧：删除目标条目前，同事务把入链降级为 missing（治理列豁免）。

    必须在条目删除**之前**调用（先捕获入链）；只改 target_item_id/resolution/
    cross_space/updated_at，键与版本不变 → 不触发全局守卫，版本窗口内 DELETE
    不被 409 阻断。target_title/alias 原书写字面留存。
    """
    stmt = select(KnowledgeLinkORM).where(
        KnowledgeLinkORM.target_item_id == str(target_id)
    )
    rows = list(session.scalars(stmt))
    now = utcnow()
    for row in rows:
        row.target_item_id = None
        row.resolution = LinkResolution.MISSING.value
        row.cross_space = False
        row.updated_at = now
    session.flush()
    return len(rows)


def _refusal_report(
    plan: LinkRebuildPlan,
    status: str,
    *,
    stale_reasons: tuple[LinkStaleReason, ...] = (),
) -> LinkRebuildReport:
    """所有拒绝一律零写入：updated=0、unchanged=observed_row_count、须重生成计划。"""
    return LinkRebuildReport(
        status=status,
        source_version=plan.source_version,
        target_version=plan.target_version,
        updated=0,
        unchanged=plan.observed_row_count,
        collision_groups=plan.collision_groups,
        warnings=plan.warnings,
        stale_reasons=stale_reasons,
        requires_replan=True,
        observed_row_count=plan.observed_row_count,
    )


def _gate_b(plan: LinkRebuildPlan) -> str | None:
    """门禁 B：**只查计划内部，不查数据库**（§8.3.6 反例表第 4 行；T24/T28）。

    ① ``observed_row_count == len(row_snapshots)``（计划自身一致）；
    ② ``source_version ≠ target_version`` 时 updates 必须覆盖全部快照行
    （单向：快照 ⊆ updates；updates 含快照外 id 归门禁 C 的
    ``update_row_not_in_plan``，T28③）；③ 计划内 ``(source_id, new_key)``
    无重复（**不同 link_id** 才算；重复 link_id 归门禁 C，T29②）。
    与当前数据库的双向覆盖/逐字段比对/新键重算一律是门禁 C 的职责。
    """
    if plan.observed_row_count != len(plan.row_snapshots):
        return "incomplete_coverage"
    if plan.source_version != plan.target_version:
        snap_ids = {s.link_id for s in plan.row_snapshots}
        upd_ids = {u.link_id for u in plan.updates}
        if not snap_ids <= upd_ids:
            return "incomplete_coverage"
    seen_ids: set[UUID] = set()
    seen_pairs: set[tuple[UUID, str]] = set()
    for u in plan.updates:
        # 重复 link_id 归门禁 C（duplicate_link_id_in_plan），B 不抢占：
        # 同一 link_id 的重复条目不参与 (source_id, new_key) 判重。
        if u.link_id not in seen_ids:
            seen_ids.add(u.link_id)
            pair = (u.source_id, u.new_key)
            if pair in seen_pairs:
                return "duplicate_new_key_in_plan"
            seen_pairs.add(pair)
    return None


def _item_baseline(session: Session) -> dict[str, dict]:
    """knowledge_item 全列基线（步 3b）：写后复核证明重建未触碰条目。"""
    baseline: dict[str, dict] = {}
    for row in session.scalars(select(KnowledgeItemORM)):
        baseline[row.id] = {c.name: getattr(row, c.name) for c in row.__table__.columns}
    return baseline


def _governance_baseline(session: Session) -> dict[str, tuple]:
    """链接行治理列基线（步 3b）：target_id/resolution/cross_space/created_at。"""
    stmt = select(
        KnowledgeLinkORM.id,
        KnowledgeLinkORM.target_item_id,
        KnowledgeLinkORM.resolution,
        KnowledgeLinkORM.cross_space,
        KnowledgeLinkORM.created_at,
    )
    return {r.id: (r.target_item_id, r.resolution, r.cross_space, r.created_at) for r in session.execute(stmt)}


def apply_link_key_plan(plan: LinkRebuildPlan, session: Session) -> LinkRebuildReport:
    """重建批量执行的唯一入口（§8.3.7 十步；独占单事务；任一失败整体回滚）。

    事务所有权：要求传入 Session **无活动事务**（``session.begin()`` 在已有活动
    事务/savepoint 上抛 InvalidRequestError → 零写入，不静默接管他人提交权）。
    拒绝报告在 with 块内返回 → 事务无变更结束（零写入）；写后复核失败抛
    ``LinkRebuildPostWriteError`` → with 块退出整体回滚。

    K2 并发控制：步 1b 取方言写锁（``acquire_rebuild_write_lock``，持锁至提交）。
    PG 表锁关闭门禁 C 重读 → 提交窗口②（含 phantom）；SQLite 读阶段不锁保护，
    窗口②由步 7 的 P2 乐观前置 + rowcount 校验兜底（rowcount!=1 即整体回滚零写入），
    写阶段 RESERVED 锁 + busy_timeout 补充。P2 前置经专项审计扩至门禁 C 同口径 6 字段
    （link_id + source_id/old_key/old_version/target_title/alias），覆盖全部影响 new_key
    与唯一域的正确性字段，杜绝「改 title/alias/source 但键列未同步改」的过期计划应用。
    门禁 A/B/C 与步 8 写后复核全部保留。步 8c（no-op 专项审计）逐行复核全部快照行
    （含不进步 7 的 no-op 行）：source_id/title/alias 不可变 + key-title 一致 + 行存在，
    补齐 no-op 行窗口②保护（与 update 行 P2 同口径，方言中立，零新增门禁删除）。
    """
    # 前置拒绝（零写入，不开事务）。
    if plan.status != "ready":
        return _refusal_report(
            plan, "refused_stale_plan",
            stale_reasons=(LinkStaleReason(reason_code="plan_not_ready", field="status", actual=plan.status),),
        )
    if plan.target_version not in LINK_KEY_RULES:
        return _refusal_report(
            plan, "refused_stale_plan",
            stale_reasons=(LinkStaleReason(reason_code="unsupported_target_version", field="target_version", actual=str(plan.target_version)),),
        )

    with session.begin():  # 步 1：独占事务边界
        # 步 1b（K2）：获取方言写锁，持锁至提交——关闭门禁 C 重读 → 提交窗口②。
        # PG 表锁串行化重建写者并阻并发写（含 phantom）；SQLite 读阶段不锁保护，
        # 窗口②由步 7 P2 乐观前置兜底（写阶段 RESERVED 锁 + busy_timeout 补充）。
        acquire_rebuild_write_lock(session)
        # 步 2：门禁 A——全表版本集合恰为 {plan.source_version}（不要求等于常量）。
        versions = set(
            session.execute(
                select(KnowledgeLinkORM.link_normalization_version).distinct()
            ).scalars()
        )
        if versions:
            if versions != {plan.source_version}:
                return _refusal_report(plan, "refused_version_drift")
        elif plan.observed_row_count != 0:
            # 空表只放行「计划生成时也是空表」的情形。
            return _refusal_report(plan, "refused_version_drift")

        # 步 3：重读当前全表 6 列（不加载全量 ORM 实体）。
        stmt = select(
            KnowledgeLinkORM.id,
            KnowledgeLinkORM.source_item_id,
            KnowledgeLinkORM.normalized_link_key,
            KnowledgeLinkORM.link_normalization_version,
            KnowledgeLinkORM.target_title,
            KnowledgeLinkORM.alias,
        )
        current = [
            LinkRowState(
                link_id=UUID(r.id),
                source_id=UUID(r.source_item_id),
                normalized_link_key=r.normalized_link_key,
                link_normalization_version=r.link_normalization_version,
                target_title=r.target_title,
                alias=r.alias,
            )
            for r in session.execute(stmt)
        ]
        # 步 3b：治理列 + knowledge_item 全列基线（写后复核用，同事务读取）。
        governance_before = _governance_baseline(session)
        items_before = _item_baseline(session)

        # 步 4：门禁 B（计划内部覆盖 + 唯一性；不查数据库）。
        gate_b_reason = _gate_b(plan)
        if gate_b_reason is not None:
            return _refusal_report(
                plan, "refused_incomplete_plan",
                stale_reasons=(LinkStaleReason(reason_code=gate_b_reason),),
            )

        # 步 5：门禁 C（Core 纯函数，规则单一事实来源）。
        freshness = check_plan_freshness(plan, current)
        if not freshness.ok:
            return _refusal_report(plan, "refused_stale_plan", stale_reasons=freshness.reasons)

        # 步 6：新键唯一性再验（以当前全表为基准代入 updates，含 no-op 行）。
        upd_by_id = {u.link_id: u for u in plan.updates}
        final_pairs = []
        for r in current:
            u = upd_by_id.get(r.link_id)
            if u is not None:
                final_pairs.append((u.source_id, u.new_key))
            else:
                final_pairs.append((r.source_id, r.normalized_link_key))
        if len(set(final_pairs)) != len(final_pairs):
            return _refusal_report(
                plan, "refused_stale_plan",
                stale_reasons=(LinkStaleReason(reason_code="duplicate_new_key"),),
            )

        # 步 7（K2 P2 乐观前置；专项审计扩至门禁 C 同口径 6 字段）：批量只写 3 列
        # （键/版本/链接行自身 updated_at），WHERE 附加 link_id 之外全部 5 个正确性字段
        # 前置——source_id / old_key / old_version / target_title / alias——+ rowcount 校验。
        # new_key 由 target_title+alias 派生、唯一域为 (source_id, key)，故这 5 字段任一在
        # 窗口②被并发修改都使 rowcount=0 → 抛异常整体回滚（零写入），杜绝按过期字面/源/键/
        # 版本应用重建计划。仅 guard old_key/old_version 不足以覆盖「改 title/alias 但键列
        # 未同步改」的漂移（会写入与当前 title 不一致的过期键，步 8 版本同构无法发现）。
        # 写锁正常持有时无并发修改，6 字段恒匹配 rowcount=1（纵深防御，不依赖锁单一手段）。
        # alias=None 经 SQLAlchemy == 生成 IS NULL，双方言一致；前置字段取自计划 update
        # 已携带的 source_id/target_title/alias（门禁 C 已校验其等于重读快照）。
        now = utcnow()
        for u in plan.updates:
            result = session.execute(
                update(KnowledgeLinkORM)
                .where(
                    KnowledgeLinkORM.id == str(u.link_id),
                    KnowledgeLinkORM.source_item_id == str(u.source_id),
                    KnowledgeLinkORM.normalized_link_key == u.old_key,
                    KnowledgeLinkORM.link_normalization_version == u.old_version,
                    KnowledgeLinkORM.target_title == u.target_title,
                    KnowledgeLinkORM.alias == u.alias,
                )
                .values(
                    normalized_link_key=u.new_key,
                    link_normalization_version=u.new_version,
                    updated_at=now,
                )
            )
            if result.rowcount != 1:
                raise LinkRebuildPostWriteError(
                    "重建写前置条件失配：链接行 source_id/键/版本/标题/别名已被并发修改（rowcount!=1）"
                )

        # 步 8：写后复核（任一不符 → 抛异常 → 整体回滚，不是拒绝报告）。
        versions_after = set(
            session.execute(
                select(KnowledgeLinkORM.link_normalization_version).distinct()
            ).scalars()
        )
        if versions_after and versions_after != {plan.target_version}:
            raise LinkRebuildPostWriteError("写后全表版本不同构于目标版本")
        pairs_after = list(
            session.execute(
                select(KnowledgeLinkORM.source_item_id, KnowledgeLinkORM.normalized_link_key)
            )
        )
        if len(set(pairs_after)) != len(pairs_after):
            raise LinkRebuildPostWriteError("写后存在重复 (source_id, normalized_link_key)")
        if _governance_baseline(session) != governance_before:
            raise LinkRebuildPostWriteError("写后治理列与步 3b 基线不一致")
        if _item_baseline(session) != items_before:
            raise LinkRebuildPostWriteError("写后 knowledge_item 与步 3b 基线不一致")

        # 步 8c（no-op 专项审计）：逐行复核**全部原始快照行**（含 no-op 行）。
        # no-op 行（键已等于目标重算键且版本已是目标）被 plan() 排除出 updates，故
        # **不进入步 7 UPDATE**，不受 P2 六字段前置保护；其窗口②（门禁 C 重读 → 提交）
        # 漂移此前不被步 8 发现（步 8 只查版本同构/键对唯一/治理列/条目基线，不重读
        # title/alias、不逐行比对快照、不验 key-title 一致）。此处补齐：
        #   ① 快照行须仍存在（窗口②删除 → 拒绝；治理基线已兜底，再逐行确认）；
        #   ② source_id/target_title/alias 对**全部行**不可变（重建只写键/版本/updated_at），
        #      任一漂移 → 拒绝（与 update 行 P2 同口径，no-op 行无条件拒绝而非仅碰撞时）；
        #   ③ 每行 key == 按当前字面与版本重算（key-title 一致性，含 no-op 行过期键）。
        # 版本同构已于上方确认（全表 == target），故 link_key_for_version 取目标规则有效。
        # 纯 SQLAlchemy 列选择 + Core 纯函数，零方言分支；任一不符抛异常 → 整体回滚零写入。
        final_rows = {
            r.id: r
            for r in session.execute(
                select(
                    KnowledgeLinkORM.id,
                    KnowledgeLinkORM.source_item_id,
                    KnowledgeLinkORM.normalized_link_key,
                    KnowledgeLinkORM.link_normalization_version,
                    KnowledgeLinkORM.target_title,
                    KnowledgeLinkORM.alias,
                )
            )
        }
        for snap in plan.row_snapshots:
            r = final_rows.get(str(snap.link_id))
            if r is None:
                raise LinkRebuildPostWriteError("写后快照行缺失（窗口②删除行）")
            if (
                UUID(r.source_item_id) != snap.source_id
                or r.target_title != snap.target_title
                or r.alias != snap.alias
            ):
                raise LinkRebuildPostWriteError(
                    "写后 source_id/标题/别名与计划快照不一致（窗口②漂移，含 no-op 行）"
                )
            expected_key = link_key_for_version(
                r.link_normalization_version, r.target_title, r.alias
            )
            if r.normalized_link_key != expected_key:
                raise LinkRebuildPostWriteError("写后键与当前 title/alias 不一致（过期键）")

    # 步 9：with 块正常退出即提交；步 10：任何异常已整体回滚。
    return LinkRebuildReport(
        status="rebuilt",
        source_version=plan.source_version,
        target_version=plan.target_version,
        updated=len(plan.updates),
        unchanged=plan.observed_row_count - len(plan.updates),
        collision_groups=(),
        warnings=(),
        stale_reasons=(),
        requires_replan=False,
        observed_row_count=plan.observed_row_count,
    )


def persist_rebuild_report(report: LinkRebuildReport, ops_dir: Path) -> Path:
    """D10：报告落盘（backend 侧 IO）。目录 gitignore（backend/data/ops/）。"""
    ops_dir.mkdir(parents=True, exist_ok=True)
    path = ops_dir / f"link-key-rebuild-{uuid4().hex}.json"
    path.write_text(
        json.dumps(report.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def build_link_sync(session: Session) -> BindingFirstLinkSync:
    """装配绑定优先同步（路由挂接用）。"""
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    return BindingFirstLinkSync(items, links, RepositoryLinkResolver(items))


def build_link_restorer(session: Session) -> LinkImportRestorer:
    """装配导入绑定恢复（A1-04 导入路径预留；本轮 Core/测试消费）。"""
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    return LinkImportRestorer(items, links, RepositoryLinkResolver(items))