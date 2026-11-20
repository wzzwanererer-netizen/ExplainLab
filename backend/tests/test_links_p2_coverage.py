"""K1+K2 整改后专项审计：P2 乐观前置字段覆盖完整性（默认 SQLite）。

审计问题：步 7 P2 前置原仅 guard ``id + old_key + old_version``（3 字段），而门禁 C
快照比对 6 字段（link_id / source_id / normalized_link_key / link_normalization_version
/ target_title / alias）。``new_key = norm(target_title) + \\x1f + norm(alias)``，唯一域
为 ``(source_id, normalized_link_key)``。本文件以**真实故障注入**（monkeypatch 门禁 C
在重读判定后、写之前于同一事务注入漂移）核实：门禁 C 通过后并发修改 source_id /
target_title / alias / 组合，P2 是否仍 rowcount=1 而应用过期计划。

每项断言：正确拒绝过期计划（LinkRebuildPostWriteError）+ 整体回滚 + 零部分写入
（全列快照相等）+ 全表版本同构 + 原始链接数据保留。控制组证明无漂移不误拒，且
重建后每行 key == link_key_for_version(version, title, alias)（key-title 一致性不变量）。
边界：并发删除 / 新增（phantom）/ 治理列变化的处理。

真实 PostgreSQL 镜像见 test_links_p2_coverage_pg.py（同口径 + PG 表锁排除）。
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select, update
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
    eng = create_engine_from_url(f"sqlite:///{tmp_path / 'p2cov.db'}")
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


def _setup_rebuild(session, items, links, monkeypatch):
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


def _plan_ready(links, session):
    plan = LinkKeyRebuild(links).plan(2)
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
    """重建后不变量：每行 key == 按该行版本对当前 title/alias 重算的键。"""
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


# ------------------------------------------------- 六字段漂移：拒绝 + 零写入


def test_p2_source_id_drift_after_reread_rejects(session, monkeypatch):
    """门禁 C 后并发漂移 source_id（键/版本/字面不变）→ P2 须拒绝 + 整体回滚零写入。

    source_id 决定唯一域 (source_id, key)；计划按旧 source 计算碰撞，漂移后计划过期。
    """
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_rebuild(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    before = _snapshot(session)
    session.commit()

    _inject_after_gate_c(
        monkeypatch,
        session,
        lambda: session.execute(
            update(KnowledgeLinkORM)
            .where(KnowledgeLinkORM.id == str(r1.id))
            .values(source_item_id=str(b.id))  # a → b，键/版本/字面不变
        ),
    )
    with pytest.raises(LinkRebuildPostWriteError):
        apply_link_key_plan(plan, session)
    session.rollback()
    assert _snapshot(session) == before  # 零部分写入（含注入漂移一并回滚）
    assert _versions(session) == {1}  # 全表版本同构于源版本（未被重建触碰）


def test_p2_target_title_drift_after_reread_rejects(session, monkeypatch):
    """门禁 C 后并发漂移 target_title（规范化不同值，键列/版本不变）→ P2 须拒绝。

    new_key 由 title 派生；若 P2 仅 guard old_key/old_version，title 漂移而键列未改
    时 rowcount=1 → 写入按旧 title 算的过期 new_key（key-title 不一致）。此为审计核心缺陷。
    """
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_rebuild(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    before = _snapshot(session)
    session.commit()

    _inject_after_gate_c(
        monkeypatch,
        session,
        lambda: session.execute(
            update(KnowledgeLinkORM)
            .where(KnowledgeLinkORM.id == str(r1.id))
            .values(target_title="Drifted Title")  # 规范化不同；键列/版本不变
        ),
    )
    with pytest.raises(LinkRebuildPostWriteError):
        apply_link_key_plan(plan, session)
    session.rollback()
    assert _snapshot(session) == before
    assert _versions(session) == {1}


def test_p2_alias_drift_after_reread_rejects(session, monkeypatch):
    """门禁 C 后并发漂移 alias（键列/版本不变）→ P2 须拒绝（alias 亦派生 new_key）。"""
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_rebuild(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
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
    assert _versions(session) == {1}


def test_p2_combined_field_drift_after_reread_rejects(session, monkeypatch):
    """组合漂移：r1 source_id+title、r2 alias 同时变 → P2 须拒绝 + 零写入。"""
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_rebuild(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    before = _snapshot(session)
    session.commit()

    def drift():
        session.execute(
            update(KnowledgeLinkORM)
            .where(KnowledgeLinkORM.id == str(r1.id))
            .values(source_item_id=str(b.id), target_title="Combined X")
        )
        session.execute(
            update(KnowledgeLinkORM)
            .where(KnowledgeLinkORM.id == str(r2.id))
            .values(alias="combined alias")
        )

    _inject_after_gate_c(monkeypatch, session, drift)
    with pytest.raises(LinkRebuildPostWriteError):
        apply_link_key_plan(plan, session)
    session.rollback()
    assert _snapshot(session) == before
    assert _versions(session) == {1}


# ------------------------------------------------- 控制组：不误拒 + 一致性


def test_p2_no_drift_control_rebuilds_and_keys_consistent(session, monkeypatch):
    """无漂移控制组：六字段前置恒匹配 → rowcount=1，重建正常（证明修复不误拒）。

    并断言重建后每行 key == link_key_for_version(version, title, alias)（一致性不变量）。
    """
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    _setup_rebuild(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    session.commit()
    report = apply_link_key_plan(plan, session)
    assert report.status == "rebuilt"
    assert report.updated == 3
    assert _versions(session) == {2}
    _assert_keys_consistent(session)


# ------------------------------------------------- 边界：删除 / 新增 / 治理列


def test_p2_row_delete_drift_after_reread_rejects(session, monkeypatch):
    """门禁 C 后并发删除某链接行 → 步 7 该行 rowcount=0 → 拒绝 + 零写入。"""
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_rebuild(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    before = _snapshot(session)
    session.commit()

    _inject_after_gate_c(
        monkeypatch,
        session,
        lambda: session.execute(
            KnowledgeLinkORM.__table__.delete().where(
                KnowledgeLinkORM.id == str(r1.id)
            )
        ),
    )
    with pytest.raises(LinkRebuildPostWriteError):
        apply_link_key_plan(plan, session)
    session.rollback()
    assert _snapshot(session) == before
    assert _versions(session) == {1}


def test_p2_phantom_insert_drift_after_reread_rejects(session, monkeypatch):
    """门禁 C 后并发新增碰撞行（phantom）→ 写被拒（DB UNIQUE 步7 / 步8 后备）+ 零写入。"""
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_rebuild(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    new_key_r1 = next(u.new_key for u in plan.updates if u.link_id == r1.id)
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
                normalized_link_key=new_key_r1,
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
    assert _versions(session) == {1}


def test_p2_governance_drift_rejected_by_step8_baseline(session, monkeypatch):
    """治理列边界：门禁 C 后并发改 resolution（治理列）→ 步 8 治理基线复核拒绝 + 零写入。

    治理列不在 P2 六字段前置内（重建不拥有它们）；其窗口②变化由步 8 治理基线
    （步 3b 快照）兜底拒绝。证明 P2 扩字段未改变治理列处理边界，亦未误纳治理列。
    """
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_rebuild(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    before = _snapshot(session)
    session.commit()

    _inject_after_gate_c(
        monkeypatch,
        session,
        lambda: session.execute(
            update(KnowledgeLinkORM)
            .where(KnowledgeLinkORM.id == str(r1.id))
            .values(resolution="missing", target_item_id=None)  # 治理列漂移
        ),
    )
    with pytest.raises(LinkRebuildPostWriteError) as ei:
        apply_link_key_plan(plan, session)
    assert "治理列" in str(ei.value)  # 步 8 治理基线拒绝（非 P2 rowcount）
    session.rollback()
    assert _snapshot(session) == before
    assert _versions(session) == {1}