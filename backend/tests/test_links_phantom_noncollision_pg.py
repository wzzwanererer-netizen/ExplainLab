"""V2 A1-03 最终审计补充：步 8c Phantom **非碰撞**新增覆盖 —— 真实 PostgreSQL 镜像。

经 EXPLAINLAB_PG_TEST_URL 门控：未配置整模块跳过；配置后连真实 PG，经真实在线
Alembic 迁移建表。与 test_links_phantom_noncollision.py 同口径，并额外以**真实双连接**
证明 PG 表锁（SHARE ROW EXCLUSIVE + FOR UPDATE，步 1b 无条件取锁，含空 updates）阻断
外部**非碰撞 phantom INSERT**（lock_timeout 确定性触发）——审计场景3/4 的 PG 侧实证。

两条防线分别取证：
- 外部并发 INSERT：PG 表锁字段无关地阻一切写（含 INSERT），窗口②在 PG 上由锁关闭；
- 同事务故障注入（monkeypatch 门禁 C）绕过表锁（锁阻他连接、不阻本事务），直接检验
  步 8 治理基线全表 id dict 比对：非碰撞 phantom（满足版本同构 + key-title、不在快照
  中、绕过步 8c 单向遍历）仍使治理基线 dict 多一键 → 拒绝 + 整体回滚 + 零部分更新。

绝不以离线 SQL/假数据/SQLite 结果冒充。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import insert, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401  确保 ORM 元数据注册
import app.services.links as links_module
from alembic import command
from app.core.config import get_settings
from app.db.locking import acquire_rebuild_write_lock
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

BACKEND_DIR = Path(__file__).resolve().parents[1]
PG_URL = os.environ.get("EXPLAINLAB_PG_TEST_URL")

pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason="未配置 EXPLAINLAB_PG_TEST_URL（真实 PostgreSQL 实例），跳过 phantom 非碰撞 PG 测试",
)


def _alembic_cfg() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


@pytest.fixture(scope="module")
def pg_engine() -> Iterator:
    os.environ["DATABASE_URL"] = PG_URL  # type: ignore[assignment]
    get_settings.cache_clear()
    command.upgrade(_alembic_cfg(), "head")
    eng = create_engine_from_url(PG_URL)  # type: ignore[arg-type]
    try:
        yield eng
    finally:
        eng.dispose()
        get_settings.cache_clear()
        os.environ.pop("DATABASE_URL", None)


@pytest.fixture
def session(pg_engine) -> Iterator[Session]:
    factory = sessionmaker(bind=pg_engine, autoflush=False, expire_on_commit=False)
    s = factory()
    s.execute(text("DELETE FROM knowledge_item"))
    s.execute(text("DELETE FROM tag"))
    s.execute(text("DELETE FROM gc_task"))
    s.execute(text("DELETE FROM storage_lock"))
    s.execute(text("DELETE FROM tag_change_log"))
    s.commit()
    for sid, kind in (("s1", "personal"), ("s2", "project")):
        if s.get(KnowledgeSpace, sid) is None:
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
    """非碰撞 phantom：新 id、目标版本 2、key==norm(title,alias)、可通过约束。"""
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


def test_pg_empty_updates_control_no_phantom(session, monkeypatch):
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


# ------------------------------------------------- 同事务注入：治理基线兜底（绕过表锁）


def test_pg_empty_updates_noncollision_phantom_rejected_by_governance(session, monkeypatch):
    """P1（审计场景1/5/6）PG 同事务：空 updates 非碰撞 phantom（满足版本同构+key-title、
    不在快照、绕过步 8c）→ 步 8 治理基线全表 id dict 多一键 → 拒绝 + 整体回滚 + ID 还原。
    """
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_all_noop(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    assert plan.updates == ()
    before = _snapshot(session)
    ids_before = _link_ids(session)
    snap_ids = {str(s.link_id) for s in plan.row_snapshots}
    assert ids_before == snap_ids
    session.commit()

    phantom_ids: list[str] = []

    def drift():
        pid = _add_noncollision_phantom(session, str(a.id))
        phantom_ids.append(pid)
        pairs = set(
            session.execute(
                select(KnowledgeLinkORM.source_item_id, KnowledgeLinkORM.normalized_link_key)
            )
        )
        assert len(pairs) == 4  # 非碰撞
        row = session.get(KnowledgeLinkORM, pid)
        assert row.link_normalization_version == plan.target_version == 2  # 版本同构
        assert row.normalized_link_key == link_key_for_version(2, row.target_title, row.alias)
        assert pid not in snap_ids  # 步 8c 单向遍历不检查它

    _inject_after_gate_c(monkeypatch, session, drift)
    with pytest.raises(LinkRebuildPostWriteError) as ei:
        apply_link_key_plan(plan, session)
    assert "治理列" in str(ei.value)  # 治理基线触发，非步 8c
    session.rollback()
    assert _snapshot(session) == before
    assert _link_ids(session) == ids_before
    assert phantom_ids[0] not in _link_ids(session)
    assert _versions(session) == {2}
    _assert_keys_consistent(session)


def test_pg_mixed_updates_noncollision_phantom_no_partial_update(session, monkeypatch):
    """P2（审计场景2）PG 同事务：混合 updates 非碰撞 phantom → 治理基线拒绝，r1 写入
    一并回滚（零部分更新），ID 集合还原。
    """
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_mixed(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    assert {u.link_id for u in plan.updates} == {r1.id}
    before = _snapshot(session)
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
    assert snap == before
    assert _link_ids(session) == ids_before
    r1_after = next(r for r in snap["links"] if r["id"] == str(r1.id))
    assert r1_after["normalized_link_key"] == "STALE-KEY"  # 零部分更新
    assert _versions(session) == {2}


def test_pg_phantom_id_set_guarantee_is_governance_not_step8c(session, monkeypatch):
    """P3（审计场景5）PG：独立复算治理基线全表 id dict，证明 phantom 使其多一键 →
    步 8 line457 比较必失败；ID 集合双向一致由治理基线保证，而非步 8c 单向遍历。
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
    assert set(gov_before) == snap_ids
    session.commit()

    pid = _add_noncollision_phantom(session, str(a.id))
    gov_after = gov_baseline()
    assert pid not in snap_ids
    assert set(gov_after) == snap_ids | {pid}
    assert gov_after != gov_before
    session.rollback()
    assert gov_baseline() == gov_before
    assert _link_ids(session) == snap_ids


# ------------------------------------------------- PG 表锁阻外部非碰撞 INSERT（真实双连接）


def _seed_lock_state(pg_engine, *, mixed: bool) -> tuple[str, list[str]]:
    """独立连接播种锁排除测试状态：empty=单 no-op 行；mixed=no-op 行 + 键漂移 update 行。

    返回 (item_id, link_ids)。步 1b 取锁无条件（空/混合计划同口径），故两种状态均持
    SHARE ROW EXCLUSIVE + FOR UPDATE 至提交，阻外部 INSERT。
    """
    factory = sessionmaker(bind=pg_engine, autoflush=False, expire_on_commit=False)
    s = factory()
    s.execute(text("DELETE FROM knowledge_item"))
    s.commit()
    if s.get(KnowledgeSpace, "s1") is None:
        s.add(KnowledgeSpace(id="s1", name="s1", kind="personal"))
        s.commit()
    item = KnowledgeItemORM(
        id=str(uuid4()), title="A", content="正文", space_id="s1", status="active"
    )
    s.add(item)
    s.flush()
    link_ids: list[str] = []
    # no-op 行（version 2，键与 title 一致）
    lid = str(uuid4())
    s.add(
        KnowledgeLinkORM(
            id=lid,
            source_item_id=item.id,
            target_item_id=None,
            target_title="T",
            alias=None,
            normalized_link_key=_v2_key("T", None),
            link_normalization_version=2,
            resolution="missing",
            cross_space=False,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
    )
    link_ids.append(lid)
    if mixed:
        # update 行（version 2，键漂移 STALE-KEY → 同版本计划中需重算）
        lid2 = str(uuid4())
        s.add(
            KnowledgeLinkORM(
                id=lid2,
                source_item_id=item.id,
                target_item_id=None,
                target_title="U",
                alias=None,
                normalized_link_key="STALE-KEY",
                link_normalization_version=2,
                resolution="missing",
                cross_space=False,
                created_at=utcnow(),
                updated_at=utcnow(),
            )
        )
        link_ids.append(lid2)
    s.commit()
    item_id = item.id
    s.close()
    return item_id, link_ids


def _assert_external_insert_blocked_then_allowed(pg_engine, *, mixed: bool):
    item_id, link_ids = _seed_lock_state(pg_engine, mixed=mixed)
    factory = sessionmaker(bind=pg_engine, autoflush=False, expire_on_commit=False)
    a = factory()
    a.begin()
    acquire_rebuild_write_lock(a)  # 步 1b：持锁至提交/回滚（空/混合计划无条件取锁）
    b = factory()
    b.execute(text("SET lock_timeout = '500ms'"))
    phantom_id = str(uuid4())
    with pytest.raises(DBAPIError) as ei:
        b.execute(
            insert(KnowledgeLinkORM).values(
                id=phantom_id,
                source_item_id=item_id,
                target_item_id=None,
                target_title="Phantom External",
                alias=None,
                normalized_link_key=_v2_key("Phantom External", None),  # 非碰撞
                link_normalization_version=2,
                resolution="missing",
                cross_space=False,
                created_at=utcnow(),
                updated_at=utcnow(),
            )
        )
    assert "lock timeout" in str(ei.value).lower()  # 表锁阻外部 INSERT
    b.rollback()
    a.rollback()  # 释放锁
    a.close()
    b.close()

    # 锁释放后外部非碰撞 INSERT 可提交（暂时排除，非死锁）
    c = factory()
    c.execute(
        insert(KnowledgeLinkORM).values(
            id=phantom_id,
            source_item_id=item_id,
            target_item_id=None,
            target_title="Phantom External",
            alias=None,
            normalized_link_key=_v2_key("Phantom External", None),
            link_normalization_version=2,
            resolution="missing",
            cross_space=False,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
    )
    c.commit()
    assert c.execute(
        select(KnowledgeLinkORM.id).where(KnowledgeLinkORM.id == phantom_id)
    ).scalar() == phantom_id
    c.close()


def test_pg_lock_blocks_external_noncollision_phantom_insert_empty_updates(pg_engine):
    """P4（审计场景3）：PG 空 updates 计划状态，重建持表锁期间外部**非碰撞 INSERT**
    被 lock_timeout 阻断；释放后可插入。证明窗口②外部 phantom 在 PG 上由表锁关闭。
    """
    _assert_external_insert_blocked_then_allowed(pg_engine, mixed=False)


def test_pg_lock_blocks_external_noncollision_phantom_insert_mixed_updates(pg_engine):
    """P5（审计场景4）：PG 混合 updates 计划状态（no-op + update 行），步 1b 无条件取
    同一表锁，外部**非碰撞 INSERT** 同样被 lock_timeout 阻断；释放后可插入。
    """
    _assert_external_insert_blocked_then_allowed(pg_engine, mixed=True)