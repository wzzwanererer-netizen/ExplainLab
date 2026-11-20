"""V2 A1-03 最终审计补充：步 8c Phantom **非碰撞**新增覆盖（默认 SQLite）。

审计问题：步 8c 逐行复核 plan.row_snapshots（单向：快照→当前），**不**做全表 ID
集合双向比较。那么一条**非碰撞 phantom INSERT**（新链接 ID、不与现有 (source_id,key)
冲突、使用目标 normalization version、key==norm(title,alias)、可通过数据库约束）在
SQLite 空 updates / 混合 updates 的窗口②（门禁 C 通过后、apply 未取得 RESERVED 写锁）
被并发插入，是否会被发现？

源码审查结论（待本文件真实测试证实）：
- 步 8c（services/links.py:486-502）只遍历 plan.row_snapshots → 单向存在性 + 不可变 +
  key-title 复核；phantom 不在快照中，步 8c **不**检查它。
- 但步 8 的 ``_governance_baseline``（services/links.py:297-306）是**全表** id 键 dict
  （无 WHERE），步 8 line457 比较写前/写后**整 dict 相等**。phantom 新增一个 id →
  dict 多一键 → 不等 → 抛 ``LinkRebuildPostWriteError("写后治理列与步 3b 基线不一致")``
  → 整体回滚。故 **ID 集合完全一致由步 8 治理基线（全表 dict 相等）保证**，而非步 8c。
- 该 phantom 即便满足版本同构（version==target）与 key-title 一致（key==norm），绕过
  这两项专项复核，仍被治理基线的全表 ID/治理列比对拒绝。

本文件以**真实故障注入**（monkeypatch 门禁 C 在重读判定后、写之前于同一事务插入
非碰撞 phantom）确定性复现窗口②，逐项断言：检测 + 拒绝（治理基线触发）+ 整体回滚 +
零部分更新 + ID 集合双向还原 + 版本同构 + key-title 一致。phantom 显式构造为**非碰撞**
（键不同于任何现有行）且**满足版本同构与 key-title**，证明其绕过这两项仍被拒。

真实 PostgreSQL 镜像见 test_links_phantom_noncollision_pg.py（同口径 + 表锁阻外部 INSERT）。
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select, update
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
    eng = create_engine_from_url(f"sqlite:///{tmp_path / 'phantomnc.db'}")
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


def _setup_all_noop(session, items, links, monkeypatch):
    """同版本 2→2，全部行已是目标键 → updates 为空（全 no-op）。"""
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
    """同版本 2→2，r1 键漂移（version 仍 2）→ r1 update，r2/r3 no-op。"""
    a, b, c, r1, r2, r3 = _setup_all_noop(session, items, links, monkeypatch)
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


def _link_ids(session) -> set:
    return set(session.execute(select(KnowledgeLinkORM.id)).scalars())


def _inject_after_gate_c(monkeypatch, session, drift):
    real = links_module.check_plan_freshness

    def wrapper(plan_, current):
        res = real(plan_, current)
        drift()
        return res

    monkeypatch.setattr(links_module, "check_plan_freshness", wrapper)


def _assert_keys_consistent(session) -> None:
    for r in session.scalars(select(KnowledgeLinkORM)):
        expected = link_key_for_version(
            r.link_normalization_version, r.target_title, r.alias
        )
        assert r.normalized_link_key == expected


def _versions(session) -> set:
    return set(
        session.execute(
            select(KnowledgeLinkORM.link_normalization_version).distinct()
        ).scalars()
    )


def _add_noncollision_phantom(session, source_item_id: str) -> str:
    """插入一条**非碰撞** phantom：新 id、目标版本 2、key==norm(title,alias)、可通过约束。

    title="Phantom Noncollision" 的键不同于任何现有行（Target One/Two/Other Target），
    故 (source_id,key) 不撞 → 步 8 键对唯一复核不报；version=2 → 版本同构不报；
    key==_v2_key(title) → 即便被 key-title 复核也一致。唯一能发现它的是治理基线全表
    id dict 比对（多出一个 id）。返回 phantom id 供断言。
    """
    pid = str(uuid4())
    title = "Phantom Noncollision"
    session.add(
        KnowledgeLinkORM(
            id=pid,
            source_item_id=source_item_id,
            target_item_id=None,
            target_title=title,
            alias=None,
            normalized_link_key=_v2_key(title, None),
            link_normalization_version=2,
            resolution="missing",
            cross_space=False,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
    )
    session.flush()
    return pid


# ------------------------------------------------- 控制组：无 phantom 不误拒


def test_sqlite_empty_updates_control_no_phantom(session, monkeypatch):
    """空 updates 无漂移 → rebuilt updated=0，ID 集合/版本/key-title 保持。"""
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    _setup_all_noop(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    assert plan.updates == ()
    ids_before = _link_ids(session)
    session.commit()
    report = apply_link_key_plan(plan, session)
    assert report.status == "rebuilt"
    assert report.updated == 0
    assert _link_ids(session) == ids_before
    assert _versions(session) == {2}
    _assert_keys_consistent(session)


# ------------------------------------------------- P1：空 updates 非碰撞 phantom


def test_sqlite_empty_updates_noncollision_phantom_rejected_by_governance(session, monkeypatch):
    """P1（审计场景1）：SQLite 空 updates，门禁 C 后并发插入**非碰撞** phantom。

    phantom 满足版本同构（v2）+ key-title 一致 + 非碰撞 → 绕过步 8 版本/键对复核与
    步 8c（不在快照中），但步 8 治理基线全表 id dict 多一键 → 拒绝 + 整体回滚 +
    ID 集合双向还原。显式断言触发守护为**治理基线**（非步 8c），证明 ID 集合一致性
    由步 8 全表 dict 相等保证。
    """
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_all_noop(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    assert plan.updates == ()
    before = _snapshot(session)
    ids_before = _link_ids(session)
    snap_ids = {str(s.link_id) for s in plan.row_snapshots}
    assert ids_before == snap_ids  # 计划快照 ID 集合 == 当前全表 ID 集合
    session.commit()

    phantom_ids: list[str] = []

    def drift():
        pid = _add_noncollision_phantom(session, str(a.id))
        phantom_ids.append(pid)
        # 证明 phantom 非碰撞 + 满足版本同构 + key-title（绕过这两项专项复核）。
        pairs = set(
            session.execute(
                select(KnowledgeLinkORM.source_item_id, KnowledgeLinkORM.normalized_link_key)
            )
        )
        assert len(pairs) == 4  # 3 原行 + phantom，无重复 → 非碰撞
        row = session.get(KnowledgeLinkORM, pid)
        assert row.link_normalization_version == plan.target_version == 2  # 版本同构
        assert row.normalized_link_key == link_key_for_version(2, row.target_title, row.alias)
        assert pid not in snap_ids  # phantom 不在快照 → 步 8c 不检查它

    _inject_after_gate_c(monkeypatch, session, drift)
    with pytest.raises(LinkRebuildPostWriteError) as ei:
        apply_link_key_plan(plan, session)
    assert "治理列" in str(ei.value)  # 步 8 治理基线（全表 id dict）触发，非步 8c
    session.rollback()
    assert _snapshot(session) == before  # 整体回滚零写入
    assert _link_ids(session) == ids_before  # ID 集合双向还原（phantom 已回滚）
    assert phantom_ids[0] not in _link_ids(session)
    assert _versions(session) == {2}
    _assert_keys_consistent(session)


# ------------------------------------------------- P2：混合 updates 非碰撞 phantom


def test_sqlite_mixed_updates_noncollision_phantom_no_partial_update(session, monkeypatch):
    """P2（审计场景2）：SQLite 混合 updates（r1 update，r2/r3 no-op），非碰撞 phantom。

    步 7 已写 r1 新键；phantom 在步 8 治理基线被拒 → 必须连同 r1 写入一并回滚
    （零部分更新），ID 集合还原。
    """
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_mixed(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    assert {u.link_id for u in plan.updates} == {r1.id}
    before = _snapshot(session)  # r1 键仍 STALE-KEY
    ids_before = _link_ids(session)
    session.commit()

    _inject_after_gate_c(
        monkeypatch, session, lambda: _add_noncollision_phantom(session, str(a.id))
    )
    with pytest.raises(LinkRebuildPostWriteError) as ei:
        apply_link_key_plan(plan, session)
    assert "治理列" in str(ei.value)
    session.rollback()
    snap = _snapshot(session)
    assert snap == before  # r1 写入 + phantom 均回滚 → 零部分更新
    assert _link_ids(session) == ids_before
    r1_after = next(r for r in snap["links"] if r["id"] == str(r1.id))
    assert r1_after["normalized_link_key"] == "STALE-KEY"  # update 行未残留半套新键
    assert _versions(session) == {2}
    # 混合 before 态含故意键漂移 r1（STALE-KEY），回滚恢复该态，不适用全表 key-title
    # 一致不变量（仅成功重建后成立）；snap == before 已逐列证明零部分更新。


# ------------------------------------------------- P3：ID 集合双向比较机制取证


def test_sqlite_phantom_id_set_guarantee_is_governance_not_step8c(session, monkeypatch):
    """P3（审计场景5/6）：固化「ID 集合完全一致」的真实守护来源。

    直接验证：① 步 8c 仅单向遍历快照（phantom 不在快照 → 步 8c 逻辑上不会检查它）；
    ② 治理基线为全表 id dict，phantom 使其多一键 → 写前/写后不等。本测试在 apply
    之外独立复算治理基线 dict，证明 phantom 确实改变该 dict（即步 8 line457 的比较
    会失败），从而 ID 集合双向一致由治理基线保证，而非步 8c 的单向遍历。
    """
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_all_noop(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    snap_ids = {str(s.link_id) for s in plan.row_snapshots}

    def gov_baseline():
        stmt = select(
            KnowledgeLinkORM.id,
            KnowledgeLinkORM.target_item_id,
            KnowledgeLinkORM.resolution,
            KnowledgeLinkORM.cross_space,
            KnowledgeLinkORM.created_at,
        )
        return {
            r.id: (r.target_item_id, r.resolution, r.cross_space, r.created_at)
            for r in session.execute(stmt)
        }

    gov_before = gov_baseline()
    assert set(gov_before) == snap_ids  # 治理基线覆盖全表 ID（== 快照 ID）
    session.commit()

    pid = _add_noncollision_phantom(session, str(a.id))
    gov_after = gov_baseline()
    # phantom 不在快照（步 8c 单向遍历不会检查它），但治理基线全表 dict 多一键。
    assert pid not in snap_ids
    assert set(gov_after) == snap_ids | {pid}
    assert gov_after != gov_before  # 步 8 line457 比较必失败 → 拒绝
    session.rollback()
    assert gov_baseline() == gov_before  # 回滚后 ID 集合还原
    assert _link_ids(session) == snap_ids