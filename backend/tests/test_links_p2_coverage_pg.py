"""K1+K2 整改后专项审计：P2 乐观前置字段覆盖 —— 真实 PostgreSQL 镜像。

经 EXPLAINLAB_PG_TEST_URL 门控：未配置整模块跳过；配置后连真实 PG，经真实在线
Alembic 迁移建表。与 test_links_p2_coverage.py 同口径（六字段漂移拒绝 + 零写入 +
版本同构 + 控制组一致性 + 删除/新增/治理列边界），并额外以**真实双连接**证明
PG 表锁（SHARE ROW EXCLUSIVE + FOR UPDATE）完整覆盖 source_id/target_title/alias
并发写入（lock_timeout 确定性触发）——审计问题 6 的 PG 侧实证。

同事务故障注入（monkeypatch 门禁 C）在 PG 上绕过表锁（锁阻他连接、不阻本事务），
直接检验步 7 P2 六字段前置逻辑本身；真实跨连接锁排除见末尾 lock 测试。
绝不以离线 SQL/假数据/SQLite 结果冒充。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import select, text, update
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
    reason="未配置 EXPLAINLAB_PG_TEST_URL（真实 PostgreSQL 实例），跳过 P2 字段覆盖 PG 测试",
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


# ------------------------------------------------- 六字段漂移：拒绝 + 零写入


def test_p2_source_id_drift_after_reread_rejects(session, monkeypatch):
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
            .values(source_item_id=str(b.id))
        ),
    )
    with pytest.raises(LinkRebuildPostWriteError):
        apply_link_key_plan(plan, session)
    session.rollback()
    assert _snapshot(session) == before
    assert _versions(session) == {1}


def test_p2_target_title_drift_after_reread_rejects(session, monkeypatch):
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
            .values(target_title="Drifted Title")
        ),
    )
    with pytest.raises(LinkRebuildPostWriteError):
        apply_link_key_plan(plan, session)
    session.rollback()
    assert _snapshot(session) == before
    assert _versions(session) == {1}


def test_p2_alias_drift_after_reread_rejects(session, monkeypatch):
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
            .values(alias="drifted alias")
        ),
    )
    with pytest.raises(LinkRebuildPostWriteError):
        apply_link_key_plan(plan, session)
    session.rollback()
    assert _snapshot(session) == before
    assert _versions(session) == {1}


def test_p2_combined_field_drift_after_reread_rejects(session, monkeypatch):
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
            .values(resolution="missing", target_item_id=None)
        ),
    )
    with pytest.raises(LinkRebuildPostWriteError) as ei:
        apply_link_key_plan(plan, session)
    assert "治理列" in str(ei.value)
    session.rollback()
    assert _snapshot(session) == before
    assert _versions(session) == {1}


# ------------------------------------------------- PG 表锁覆盖字段漂移（真实双连接）


def _seed_one_link(pg_engine) -> tuple[str, str]:
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
            normalized_link_key=normalized_link_key("T", None),
            link_normalization_version=1,
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


def test_pg_lock_blocks_concurrent_correctness_field_drift(pg_engine):
    """审计问题 6：PG 表锁完整覆盖 source_id/target_title/alias 并发写入。

    重建持 SHARE ROW EXCLUSIVE + FOR UPDATE 期间，第二连接对这三个正确性字段的
    UPDATE 均被 lock_timeout 阻断（表锁字段无关，阻一切写）；释放后可写。
    """
    link_id, item_id = _seed_one_link(pg_engine)
    factory = sessionmaker(bind=pg_engine, autoflush=False, expire_on_commit=False)
    a = factory()
    a.begin()
    acquire_rebuild_write_lock(a)
    b = factory()
    for values in (
        {"target_title": "Drifted"},
        {"alias": "drifted"},
        {"source_item_id": item_id},
    ):
        # lock_timeout 须每轮重设：上一次 UPDATE 锁超时使事务中止，会话级 SET 随
        # 事务回滚失效（PG 语义），故每个新事务重新设置，避免后续尝试无限等待。
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

    # 锁释放后正确性字段并发写者可提交（暂时排除，非死锁）
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