"""V2 A1-03 最终专项审计：no-op 行并发保护 —— 真实 PostgreSQL 镜像。

经 EXPLAINLAB_PG_TEST_URL 门控：未配置整模块跳过；配置后连真实 PG，经真实在线
Alembic 迁移建表。与 test_links_noop_coverage.py 同口径（八场景：全更新/全 no-op/混合
控制组 + no-op 行 title/alias/source_id 漂移拒绝 + 混合无部分更新 + 空 updates 拒绝 +
键/版本/phantom 边界），并额外以**真实双连接**证明：

- PG 表锁（SHARE ROW EXCLUSIVE + FOR UPDATE）在**空 updates** 的 apply 中仍被获取
  （步 1b 无条件取锁），阻一切并发写（含 no-op 行字段漂移）——窗口②在 PG 上由锁关闭；
- 同事务故障注入（monkeypatch 门禁 C）在 PG 上绕过表锁（锁阻他连接、不阻本事务），
  直接检验步 8 逐行复核逻辑本身（no-op 行不进步 7，故其保护只能来自步 8）。

绝不以离线 SQL/假数据/SQLite 结果冒充。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import event, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
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
    reason="未配置 EXPLAINLAB_PG_TEST_URL（真实 PostgreSQL 实例），跳过 no-op 并发 PG 测试",
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


def _setup_all_update(session, items, links, monkeypatch):
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


def _assert_noop(plan, link_id) -> None:
    assert link_id not in {u.link_id for u in plan.updates}
    assert link_id in {s.link_id for s in plan.row_snapshots}


class _LockUpdateCounter:
    """统计 apply 期间锁语句（LOCK TABLE / FOR UPDATE）与 UPDATE 数（PG 只读取锁取证）。"""

    def __init__(self, engine):
        self.locks = 0
        self.updates = 0
        self._engine = engine
        event.listen(engine, "before_cursor_execute", self._listen)

    def _listen(self, conn, cursor, statement, parameters, context, executemany):
        up = statement.upper()
        if up.startswith("LOCK TABLE") or (up.startswith("SELECT") and "FOR UPDATE" in up):
            self.locks += 1
        elif up.startswith("UPDATE KNOWLEDGE_LINK"):
            self.updates += 1

    def stop(self):
        event.remove(self._engine, "before_cursor_execute", self._listen)


# ------------------------------------------------- 场景1/2/3：控制组（无漂移）


def test_scenario1_all_rows_update_control(session, monkeypatch):
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    _setup_all_update(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    assert len(plan.updates) == 3
    session.commit()
    report = apply_link_key_plan(plan, session)
    assert report.status == "rebuilt"
    assert report.updated == 3
    assert _versions(session) == {2}
    _assert_keys_consistent(session)


def test_scenario2_all_noop_control(session, monkeypatch):
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    _setup_all_noop(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    assert plan.updates == ()
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
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_mixed(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    assert {u.link_id for u in plan.updates} == {r1.id}
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
            .values(target_title="Drifted Title")
        ),
    )
    with pytest.raises(LinkRebuildPostWriteError):
        apply_link_key_plan(plan, session)
    session.rollback()
    assert _snapshot(session) == before
    assert _versions(session) == {2}
    _assert_keys_consistent(session)


def test_scenario5_noop_alias_drift_rejected(session, monkeypatch):
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
            .values(alias="drifted alias")
        ),
    )
    with pytest.raises(LinkRebuildPostWriteError):
        apply_link_key_plan(plan, session)
    session.rollback()
    assert _snapshot(session) == before
    assert _versions(session) == {2}
    _assert_keys_consistent(session)


def test_scenario6_noop_source_id_drift_rejected(session, monkeypatch):
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_all_noop(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    _assert_noop(plan, r3.id)
    before = _snapshot(session)
    session.commit()

    _inject_after_gate_c(
        monkeypatch,
        session,
        lambda: session.execute(
            update(KnowledgeLinkORM)
            .where(KnowledgeLinkORM.id == str(r3.id))
            .values(source_item_id=str(a.id))  # b → a，无碰撞
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
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_mixed(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    assert {u.link_id for u in plan.updates} == {r1.id}
    _assert_noop(plan, r2.id)
    before = _snapshot(session)
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
    assert snap == before
    r1_after = next(r for r in snap["links"] if r["id"] == str(r1.id))
    assert r1_after["normalized_link_key"] == "STALE-KEY"  # update 行写入一并回滚
    r2_after = next(r for r in snap["links"] if r["id"] == str(r2.id))
    assert r2_after["target_title"] == "Target Two"  # no-op 行漂移一并回滚
    assert _versions(session) == {2}
    # 混合 before 态含故意键漂移的 r1（STALE-KEY）；回滚恢复该态，不适用全表 key-title
    # 一致不变量（仅成功重建后成立）。snap == before 已逐列证明零部分更新。


# ------------------------------------------------- 场景8：空 updates 并发修改


def test_scenario8_empty_updates_concurrent_modify_rejected(session, monkeypatch):
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


def test_pg_empty_updates_apply_holds_write_lock(pg_engine, session, monkeypatch):
    """只读取锁取证（PG）：空 updates 的 apply 仍取表锁（步 1b 无条件），零 UPDATE。

    与 SQLite（acquire no-op、空 updates 只读不锁）对照：PG 即便无行可写仍持
    SHARE ROW EXCLUSIVE + FOR UPDATE 至提交 → 窗口②由锁关闭，阻一切并发写。
    """
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    _setup_all_noop(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    assert plan.updates == ()
    session.commit()
    counter = _LockUpdateCounter(pg_engine)
    report = apply_link_key_plan(plan, session)
    counter.stop()
    assert report.status == "rebuilt"
    assert counter.locks >= 2  # LOCK TABLE + FOR UPDATE（空 updates 仍取锁）
    assert counter.updates == 0  # 无行可写
    assert _versions(session) == {2}
    _assert_keys_consistent(session)


# ------------------------------------------------- 补充：no-op 键/版本/phantom 边界


def test_noop_key_drift_rejected(session, monkeypatch):
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
            .values(normalized_link_key="GARBAGE-KEY")
        ),
    )
    with pytest.raises(LinkRebuildPostWriteError):
        apply_link_key_plan(plan, session)
    session.rollback()
    assert _snapshot(session) == before
    assert _versions(session) == {2}
    _assert_keys_consistent(session)


def test_noop_version_drift_rejected_by_step8_homogeneity(session, monkeypatch):
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
    assert "版本不同构" in str(ei.value)
    session.rollback()
    assert _snapshot(session) == before
    assert _versions(session) == {2}


def test_noop_phantom_insert_collision_rejected(session, monkeypatch):
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
                normalized_link_key=r1.normalized_link_key,
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


# ------------------------------------------------- PG 表锁阻 no-op 行并发漂移（真实双连接）


def _seed_noop_link(pg_engine) -> tuple[str, str]:
    """播一行 version=2、键与 title 一致的 no-op 行（独立连接，供锁排除测试）。"""
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
    link_id = str(uuid4())
    s.add(
        KnowledgeLinkORM(
            id=link_id,
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
    s.commit()
    item_id = item.id
    s.close()
    return link_id, item_id


def test_pg_lock_blocks_concurrent_noop_row_drift(pg_engine):
    """PG 表锁字段无关地阻 no-op 行并发写：持锁期间第二连接改 title/alias/source 均被阻。

    重建（含空 updates）步 1b 取 SHARE ROW EXCLUSIVE + FOR UPDATE；no-op 行虽不进步 7，
    其窗口②外部漂移在 PG 上被表锁直接关闭（lock_timeout 确定性触发）；释放后可写。
    """
    link_id, item_id = _seed_noop_link(pg_engine)
    factory = sessionmaker(bind=pg_engine, autoflush=False, expire_on_commit=False)
    a = factory()
    a.begin()
    acquire_rebuild_write_lock(a)  # 持锁至提交/回滚（模拟 apply 步 1b，含空 updates）
    b = factory()
    for values in (
        {"target_title": "Drifted"},
        {"alias": "drifted"},
        {"source_item_id": item_id},
    ):
        # lock_timeout 每轮重设：上次锁超时使事务中止，会话级 SET 随事务回滚失效（PG 语义）。
        b.execute(text("SET lock_timeout = '500ms'"))
        with pytest.raises(DBAPIError) as ei:
            b.execute(
                update(KnowledgeLinkORM)
                .where(KnowledgeLinkORM.id == link_id)
                .values(**values)
            )
        assert "lock timeout" in str(ei.value).lower()
        b.rollback()
    a.rollback()
    a.close()
    b.close()

    # 锁释放后 no-op 行并发写者可提交（暂时排除，非死锁）
    c = factory()
    c.execute(
        update(KnowledgeLinkORM)
        .where(KnowledgeLinkORM.id == link_id)
        .values(target_title="After Release")
    )
    c.commit()
    assert c.execute(
        select(KnowledgeLinkORM.target_title).where(KnowledgeLinkORM.id == link_id)
    ).scalar() == "After Release"
    c.close()