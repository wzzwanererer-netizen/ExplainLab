"""V2 A1-03 最终专项审计：no-op 行并发保护完整性（默认 SQLite）。

审计问题：K2 P2 六字段修复（步 7 WHERE 扩至 source_id/old_key/old_version/title/alias）
**只作用于 plan.updates 中的行**。no-op 行（键已等于目标版本重算键且版本已是目标）被
plan() 排除出 updates（link_service.py:1005-1008），故**不进入步 7 UPDATE**，不受 P2
六字段前置保护。其窗口②（门禁 C 重读之后 → 提交）漂移是否被检测？

关键事实（源码审查）：
- plan() 的 row_snapshots 覆盖**全部**行（含 no-op）；updates 仅含需改键/改版本的行。
- 跨版本重建（source≠target）时**每行都是 update**（no-op 条件要求 version==target）；
  「混合 update + no-op」与「全 no-op（空 updates）」只在 **source==target**（同版本修复
  键漂移）时出现。本文件据此构造真实 no-op / 混合 / 空 updates 计划。
- 步 8 写后复核仅查：全表版本同构、(source_id,key) 唯一、治理列基线
  （target_id/resolution/cross_space/created_at）、knowledge_item 基线。**不重读
  target_title/alias，不逐行比对快照，不验 key==norm(title,alias)** → no-op 行的
  title/alias/source_id（无碰撞时）/key 漂移在窗口②不被既有步 8 发现。

本文件以**真实故障注入**（monkeypatch 门禁 C 在重读判定后、写之前于同一事务注入漂移）
确定性复现窗口②，逐项断言：检测漂移 + 拒绝过期计划 + 整体回滚 + 零部分更新 +
回滚后 key-title 一致 + 版本同构。**不得以普通 update 行的 P2 测试冒充 no-op 测试**：
下列漂移全部施加于 **no-op 行**（不在 plan.updates 中），并显式断言该行确为 no-op。

真实 PostgreSQL 镜像见 test_links_noop_coverage_pg.py（同口径 + PG 表锁排除）。
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import event, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

import app.services.links as links_module
from app.db.base import Base
from app.db.session import create_engine_from_url
from app.models import (
    KnowledgeItemORM,
    KnowledgeLinkORM,
    KnowledgeRelationORM,
    KnowledgeSpace,
    KnowledgeVersionORM,
)
from app.services.knowledge import SQLAlchemyKnowledgeRepository
from app.services.links import (
    LinkRebuildPostWriteError,
    SQLAlchemyLinkRepository,
    apply_link_key_plan,
)
from knowledge_core.domain import entities
from knowledge_core.domain.entities import (
    KnowledgeItem,
    KnowledgeLink,
    KnowledgeStatus,
    LinkResolution,
    utcnow,
)
from knowledge_core.markdown.link_service import LinkKeyRebuild
from knowledge_core.markdown.links import (
    LINK_KEY_RULES,
    link_key_for_version,
    normalized_link_key,
)


@pytest.fixture
def engine(tmp_path: Path):
    eng = create_engine_from_url(f"sqlite:///{tmp_path / 'noopcov.db'}")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine) -> Session:
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    s = factory()
    for sid, kind in (("s1", "personal"), ("s2", "project")):
        s.add(KnowledgeSpace(id=sid, name=f"space-{sid}", kind=kind))
    s.commit()
    yield s
    s.close()


def _mk_item(items, session, title: str) -> KnowledgeItem:
    item = KnowledgeItem(
        title=title, content="正文", space_id="s1", status=KnowledgeStatus.ACTIVE
    )
    saved = items.save(item)
    session.commit()
    return saved


def _mk_link(source, title, *, alias=None, target=None) -> KnowledgeLink:
    return KnowledgeLink(
        source_id=source.id,
        target_id=None if target is None else target.id,
        target_title=title,
        alias=alias,
        normalized_link_key=link_key_for_version(
            entities.LINK_NORMALIZATION_VERSION, title, alias
        ),
        link_normalization_version=entities.LINK_NORMALIZATION_VERSION,
        resolution=LinkResolution.RESOLVED if target is not None else LinkResolution.MISSING,
    )


def _v2_key(title: str, alias: str | None = None) -> str:
    return normalized_link_key(title, alias).replace(" ", "")


def _setup_all_update(session, items, links, monkeypatch):
    """场景1：跨版本 1→2，全部行均需更新（无 no-op）。"""
    a = _mk_item(items, session, "A")
    b = _mk_item(items, session, "B")
    c = _mk_item(items, session, "C")
    r1 = links.save_link(_mk_link(a, "Target One", target=b))
    r2 = links.save_link(_mk_link(a, "Target Two", alias="al ias", target=c))
    r3 = links.save_link(_mk_link(b, "Other Target", target=c))
    session.commit()
    monkeypatch.setitem(LINK_KEY_RULES, 2, _v2_key)
    monkeypatch.setattr(entities, "LINK_NORMALIZATION_VERSION", 2)
    return a, b, c, r1, r2, r3


def _setup_all_noop(session, items, links, monkeypatch):
    """场景2/8：同版本 2→2，全部行已是目标键 → updates 为空（全 no-op）。

    先注入 v2 规则与常量再建行，使每行 version=2、key=_v2_key(title,alias)。
    """
    monkeypatch.setitem(LINK_KEY_RULES, 2, _v2_key)
    monkeypatch.setattr(entities, "LINK_NORMALIZATION_VERSION", 2)
    a = _mk_item(items, session, "A")
    b = _mk_item(items, session, "B")
    c = _mk_item(items, session, "C")
    r1 = links.save_link(_mk_link(a, "Target One", target=b))
    r2 = links.save_link(_mk_link(a, "Target Two", alias="al ias", target=c))
    r3 = links.save_link(_mk_link(b, "Other Target", target=c))
    session.commit()
    return a, b, c, r1, r2, r3


def _setup_mixed(session, items, links, monkeypatch):
    """场景3/7：同版本 2→2，r1 键漂移（version 仍 2）→ r1 为 update，r2/r3 为 no-op。"""
    a, b, c, r1, r2, r3 = _setup_all_noop(session, items, links, monkeypatch)
    # 仅改 r1 键列为过期值，版本保持 2 → plan(2) 视 r1 需重算（update），r2/r3 no-op。
    session.execute(
        update(KnowledgeLinkORM)
        .where(KnowledgeLinkORM.id == str(r1.id))
        .values(normalized_link_key="STALE-KEY")
    )
    session.commit()
    return a, b, c, r1, r2, r3


def _plan_ready(links, session, target: int = 2):
    plan = LinkKeyRebuild(links).plan(target)
    session.commit()
    assert plan.status == "ready"
    return plan


def _rows(session, orm) -> list[dict]:
    return [
        {c.name: getattr(r, c.name) for c in orm.__table__.columns}
        for r in session.scalars(select(orm).order_by(orm.id))
    ]


def _snapshot(session) -> dict:
    return {
        "links": _rows(session, KnowledgeLinkORM),
        "items": _rows(session, KnowledgeItemORM),
        "version_count": len(_rows(session, KnowledgeVersionORM)),
        "relation_count": len(_rows(session, KnowledgeRelationORM)),
    }


def _inject_after_gate_c(monkeypatch, session, drift):
    """门禁 C 以重读快照判定新鲜后，于同一事务注入漂移（确定性复现窗口②）。"""
    real = links_module.check_plan_freshness

    def wrapper(plan_, current):
        res = real(plan_, current)
        drift()
        return res

    monkeypatch.setattr(links_module, "check_plan_freshness", wrapper)


def _assert_keys_consistent(session) -> None:
    """不变量：每行 key == 按该行版本对当前 title/alias 重算的键。"""
    for r in session.scalars(select(KnowledgeLinkORM)):
        expected = link_key_for_version(
            r.link_normalization_version, r.target_title, r.alias
        )
        assert r.normalized_link_key == expected, (
            f"key-title 不一致: link={r.id} title={r.target_title!r} "
            f"alias={r.alias!r} key={r.normalized_link_key!r} expected={expected!r}"
        )


def _versions(session) -> set:
    return set(
        session.execute(
            select(KnowledgeLinkORM.link_normalization_version).distinct()
        ).scalars()
    )


def _assert_noop(plan, link_id) -> None:
    """显式断言某行确为 no-op（不在 updates 中，但在快照中）——防止以 update 行冒充。"""
    assert link_id not in {u.link_id for u in plan.updates}
    assert link_id in {s.link_id for s in plan.row_snapshots}


class _UpdateCounter:
    """统计 apply 期间 UPDATE knowledge_link 语句数（只读事务取证）。"""

    def __init__(self, engine):
        self.updates = 0
        self._engine = engine
        event.listen(engine, "before_cursor_execute", self._listen)

    def _listen(self, conn, cursor, statement, parameters, context, executemany):
        if statement.upper().startswith("UPDATE KNOWLEDGE_LINK"):
            self.updates += 1

    def stop(self):
        event.remove(self._engine, "before_cursor_execute", self._listen)


# ------------------------------------------------- 场景1/2/3：控制组（无漂移）


def test_scenario1_all_rows_update_control(session, monkeypatch):
    """场景1：全部行均需更新（1→2），无漂移 → 重建正常，key-title 一致，版本同构。"""
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    _setup_all_update(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    assert len(plan.updates) == 3  # 无 no-op
    session.commit()
    report = apply_link_key_plan(plan, session)
    assert report.status == "rebuilt"
    assert report.updated == 3
    assert _versions(session) == {2}
    _assert_keys_consistent(session)


def test_scenario2_all_noop_control(session, monkeypatch):
    """场景2：全部行均为 no-op（2→2，空 updates），无漂移 → rebuilt updated=0，一致性保持。"""
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    _setup_all_noop(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    assert plan.updates == ()  # 空 updates
    assert plan.observed_row_count == 3
    assert plan.source_version == 2 and plan.target_version == 2
    session.commit()
    report = apply_link_key_plan(plan, session)
    assert report.status == "rebuilt"
    assert report.updated == 0
    assert report.unchanged == 3
    assert _versions(session) == {2}
    _assert_keys_consistent(session)


def test_scenario3_mixed_update_and_noop_control(session, monkeypatch):
    """场景3：混合 update（r1）与 no-op（r2/r3），无漂移 → rebuilt updated=1 unchanged=2。"""
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_mixed(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    assert {u.link_id for u in plan.updates} == {r1.id}  # 仅 r1 需更新
    _assert_noop(plan, r2.id)
    _assert_noop(plan, r3.id)
    session.commit()
    report = apply_link_key_plan(plan, session)
    assert report.status == "rebuilt"
    assert report.updated == 1
    assert report.unchanged == 2
    assert _versions(session) == {2}
    _assert_keys_consistent(session)


# ------------------------------------------------- 场景4/5/6：no-op 行单字段漂移


def test_scenario4_noop_title_drift_rejected(session, monkeypatch):
    """场景4：门禁 C 后并发修改 **no-op 行** 的 target_title（键列/版本不变）。

    no-op 行不进步 7 UPDATE → 无 P2 保护；步 8 不重读 title → 须由逐行快照/key-title
    复核拒绝，否则过期不一致行被提交（key 仍按旧 title）。
    """
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_all_noop(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    _assert_noop(plan, r2.id)  # 确为 no-op，非 update 行
    before = _snapshot(session)
    session.commit()

    _inject_after_gate_c(
        monkeypatch,
        session,
        lambda: session.execute(
            update(KnowledgeLinkORM)
            .where(KnowledgeLinkORM.id == str(r2.id))
            .values(target_title="Drifted Title")  # 规范化不同；键列/版本不变
        ),
    )
    with pytest.raises(LinkRebuildPostWriteError):
        apply_link_key_plan(plan, session)
    session.rollback()
    assert _snapshot(session) == before  # 整体回滚零写入
    assert _versions(session) == {2}  # 版本同构
    _assert_keys_consistent(session)  # 回滚后 key-title 一致


def test_scenario5_noop_alias_drift_rejected(session, monkeypatch):
    """场景5：门禁 C 后并发修改 **no-op 行** 的 alias（键列/版本不变）→ 须拒绝 + 零写入。"""
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_all_noop(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    _assert_noop(plan, r2.id)
    before = _snapshot(session)
    session.commit()

    _inject_after_gate_c(
        monkeypatch,
        session,
        lambda: session.execute(
            update(KnowledgeLinkORM)
            .where(KnowledgeLinkORM.id == str(r2.id))
            .values(alias="drifted alias")  # 原 "al ias"；键列/版本不变
        ),
    )
    with pytest.raises(LinkRebuildPostWriteError):
        apply_link_key_plan(plan, session)
    session.rollback()
    assert _snapshot(session) == before
    assert _versions(session) == {2}
    _assert_keys_consistent(session)


def test_scenario6_noop_source_id_drift_rejected(session, monkeypatch):
    """场景6：门禁 C 后并发修改 **no-op 行** 的 source_id（键/版本/字面不变，无碰撞）。

    source_id 决定唯一域；漂移后计划过期。无碰撞时步 8 键对唯一复核不报 → 须由逐行
    快照 source_id 比对拒绝（与 update 行 P2 同口径，无条件拒绝而非仅碰撞时）。
    """
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_all_noop(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    _assert_noop(plan, r3.id)  # r3 source=b
    before = _snapshot(session)
    session.commit()

    # b → a：r3 键与 r1/r2 键不同 → 不产生 (source,key) 碰撞，隔离 source 守护。
    _inject_after_gate_c(
        monkeypatch,
        session,
        lambda: session.execute(
            update(KnowledgeLinkORM)
            .where(KnowledgeLinkORM.id == str(r3.id))
            .values(source_item_id=str(a.id))
        ),
    )
    with pytest.raises(LinkRebuildPostWriteError):
        apply_link_key_plan(plan, session)
    session.rollback()
    assert _snapshot(session) == before
    assert _versions(session) == {2}
    _assert_keys_consistent(session)


# ------------------------------------------------- 场景7：混合计划 no-op 漂移（无部分更新）


def test_scenario7_mixed_noop_drift_no_partial_update(session, monkeypatch):
    """场景7：混合计划中 no-op 行（r2）漂移，update 行（r1）正常 → 整体回滚，无部分更新。

    关键：步 7 已写 r1 新键；若 no-op 漂移在步 8 被拒，必须**连同 r1 的写入一并回滚**
    （零部分更新），而非提交 r1 却放过 r2。
    """
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_mixed(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    assert {u.link_id for u in plan.updates} == {r1.id}
    _assert_noop(plan, r2.id)
    before = _snapshot(session)  # r1 键仍 "STALE-KEY"
    session.commit()

    _inject_after_gate_c(
        monkeypatch,
        session,
        lambda: session.execute(
            update(KnowledgeLinkORM)
            .where(KnowledgeLinkORM.id == str(r2.id))
            .values(target_title="Drifted Noop")
        ),
    )
    with pytest.raises(LinkRebuildPostWriteError):
        apply_link_key_plan(plan, session)
    session.rollback()
    snap = _snapshot(session)
    assert snap == before  # r1 写入被回滚（键仍 STALE-KEY），r2 漂移被回滚 → 零部分更新
    r1_after = next(r for r in snap["links"] if r["id"] == str(r1.id))
    assert r1_after["normalized_link_key"] == "STALE-KEY"  # update 行未残留半套新键
    r2_after = next(r for r in snap["links"] if r["id"] == str(r2.id))
    assert r2_after["target_title"] == "Target Two"  # no-op 行漂移一并回滚
    assert _versions(session) == {2}
    # 注：混合 before 态含**故意**键漂移的 r1（STALE-KEY，使其成为 update 行），
    # 回滚恢复该 before 态，故此处不适用「全表 key-title 一致」不变量（仅成功重建后成立）；
    # snap == before 已逐列证明零部分更新（r1 写入与 r2 漂移均回滚）。


# ------------------------------------------------- 场景8：空 updates 并发修改


def test_scenario8_empty_updates_concurrent_modify_rejected(session, monkeypatch):
    """场景8：空 updates（全 no-op）时发生并发修改 → 须拒绝 + 零写入。

    空 updates 时步 7 循环体不执行（无任何 UPDATE/P2）；保护完全依赖步 8 逐行复核。
    """
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_all_noop(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    assert plan.updates == ()
    before = _snapshot(session)
    session.commit()

    _inject_after_gate_c(
        monkeypatch,
        session,
        lambda: session.execute(
            update(KnowledgeLinkORM)
            .where(KnowledgeLinkORM.id == str(r1.id))
            .values(target_title="Empty Updates Drift")
        ),
    )
    with pytest.raises(LinkRebuildPostWriteError):
        apply_link_key_plan(plan, session)
    session.rollback()
    assert _snapshot(session) == before
    assert _versions(session) == {2}
    _assert_keys_consistent(session)


def test_sqlite_empty_updates_apply_is_readonly_no_write_lock(engine, session, monkeypatch):
    """只读事务取证（SQLite）：空 updates 的 apply **零 UPDATE** → 读阶段不持写锁。

    SQLite acquire_rebuild_write_lock 为 no-op；空 updates 时步 7 不写 → 整个 apply
    事务为只读，从不取 RESERVED 写锁（与 test_links_concurrency.py 实测读阶段语义一致）。
    因此窗口②在 SQLite 上**不由锁保护**，而由步 8 逐行乐观复核兜底（见场景8）。
    本测试固化「空 updates apply 只读、无写锁」这一真实语义，防止误以为已锁保护。
    """
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    _setup_all_noop(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    assert plan.updates == ()
    session.commit()
    counter = _UpdateCounter(engine)
    report = apply_link_key_plan(plan, session)
    counter.stop()
    assert report.status == "rebuilt"
    assert counter.updates == 0  # 零 UPDATE → 只读事务，未取写锁
    assert _versions(session) == {2}
    _assert_keys_consistent(session)


# ------------------------------------------------- 补充：no-op 键/版本漂移的既有/新增守护


def test_noop_key_drift_rejected(session, monkeypatch):
    """no-op 行键列被并发篡改为与 title 不一致的垃圾值（版本不变）→ key-title 复核拒绝。"""
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_all_noop(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    _assert_noop(plan, r1.id)
    before = _snapshot(session)
    session.commit()

    _inject_after_gate_c(
        monkeypatch,
        session,
        lambda: session.execute(
            update(KnowledgeLinkORM)
            .where(KnowledgeLinkORM.id == str(r1.id))
            .values(normalized_link_key="GARBAGE-KEY")  # 与 title 不一致；版本仍 2
        ),
    )
    with pytest.raises(LinkRebuildPostWriteError):
        apply_link_key_plan(plan, session)
    session.rollback()
    assert _snapshot(session) == before
    assert _versions(session) == {2}
    _assert_keys_consistent(session)


def test_noop_version_drift_rejected_by_step8_homogeneity(session, monkeypatch):
    """no-op 行版本被并发改为 99 → 步 8 全表版本同构复核拒绝（既有守护，记录其覆盖）。"""
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_all_noop(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    _assert_noop(plan, r1.id)
    before = _snapshot(session)
    session.commit()

    _inject_after_gate_c(
        monkeypatch,
        session,
        lambda: session.execute(
            update(KnowledgeLinkORM)
            .where(KnowledgeLinkORM.id == str(r1.id))
            .values(link_normalization_version=99)
        ),
    )
    with pytest.raises(LinkRebuildPostWriteError) as ei:
        apply_link_key_plan(plan, session)
    assert "版本不同构" in str(ei.value)  # 步 8 版本同构拒绝（先于逐行复核）
    session.rollback()
    assert _snapshot(session) == before
    assert _versions(session) == {2}


def test_noop_phantom_insert_collision_rejected(session, monkeypatch):
    """空 updates 下并发新增碰撞行（phantom，键撞某 no-op 行）→ 步 8 键对唯一复核拒绝。"""
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_all_noop(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    assert plan.updates == ()
    before = _snapshot(session)
    session.commit()

    def drift():
        session.add(
            KnowledgeLinkORM(
                id=str(uuid4()),
                source_item_id=str(a.id),
                target_item_id=None,
                target_title="Phantom",
                alias=None,
                normalized_link_key=r1.normalized_link_key,  # 撞 r1（source 同为 a）
                link_normalization_version=2,
                resolution="missing",
                cross_space=False,
                created_at=utcnow(),
                updated_at=utcnow(),
            )
        )
        session.flush()

    _inject_after_gate_c(monkeypatch, session, drift)
    with pytest.raises((LinkRebuildPostWriteError, IntegrityError)):
        apply_link_key_plan(plan, session)
    session.rollback()
    assert _snapshot(session) == before
    assert _versions(session) == {2}