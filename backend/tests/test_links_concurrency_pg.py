"""K2 链接重建并发控制 —— 真实 PostgreSQL 镜像（test_links_concurrency.py 同口径 + PG 锁排除）。

经 EXPLAINLAB_PG_TEST_URL 门控：未配置时整模块跳过；配置后连真实 PG 实例，
经真实在线 Alembic 迁移建表，真实双连接验证锁排除。绝不以离线 SQL/假数据/SQLite 结果冒充。

覆盖：
- P2 乐观前置（步 7）键/版本漂移 → rowcount=0 → 回滚零写入（故障注入，确定性）；
- 无漂移控制组 → 重建正常；phantom INSERT 碰撞 → 写被拒回滚零写入；
- **PG 表锁排除（K2 核心新增）**：重建事务持 SHARE ROW EXCLUSIVE + FOR UPDATE 期间，
  并发连接 UPDATE / INSERT（phantom）被阻（lock_timeout 确定性触发）；释放后可写。
  这是 PG READ COMMITTED 下窗口②（重读 → 提交，含步 8 → 步 9 间隙）的锁保护实证。
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
    reason="未配置 EXPLAINLAB_PG_TEST_URL（真实 PostgreSQL 实例），跳过 K2 并发 PG 测试",
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


# ---------------------------------------------------------------- P2 乐观前置


def test_p2_key_drift_after_reread_rolls_back(session, monkeypatch):
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_rebuild(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    before = _snapshot(session)
    session.commit()

    real = links_module.check_plan_freshness

    def inject(plan_, current):
        res = real(plan_, current)
        session.execute(
            update(KnowledgeLinkORM)
            .where(KnowledgeLinkORM.id == str(r1.id))
            .values(normalized_link_key="CONCURRENT-KEY")
        )
        return res

    monkeypatch.setattr(links_module, "check_plan_freshness", inject)
    with pytest.raises(LinkRebuildPostWriteError):
        apply_link_key_plan(plan, session)
    session.rollback()
    assert _snapshot(session) == before


def test_p2_version_drift_after_reread_rolls_back(session, monkeypatch):
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_rebuild(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    before = _snapshot(session)
    session.commit()

    real = links_module.check_plan_freshness

    def inject(plan_, current):
        res = real(plan_, current)
        session.execute(
            update(KnowledgeLinkORM)
            .where(KnowledgeLinkORM.id == str(r2.id))
            .values(link_normalization_version=99)
        )
        return res

    monkeypatch.setattr(links_module, "check_plan_freshness", inject)
    with pytest.raises(LinkRebuildPostWriteError):
        apply_link_key_plan(plan, session)
    session.rollback()
    assert _snapshot(session) == before


def test_p2_no_drift_rebuilds_successfully(session, monkeypatch):
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    _setup_rebuild(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    session.commit()
    report = apply_link_key_plan(plan, session)
    assert report.status == "rebuilt"
    assert report.updated == 3
    versions = set(
        session.execute(
            select(KnowledgeLinkORM.link_normalization_version).distinct()
        ).scalars()
    )
    assert versions == {2}


def test_phantom_insert_collision_post_write_rolls_back(session, monkeypatch):
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_rebuild(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    new_key_r1 = next(u.new_key for u in plan.updates if u.link_id == r1.id)
    before = _snapshot(session)
    session.commit()

    real = links_module.check_plan_freshness

    def inject(plan_, current):
        res = real(plan_, current)
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
        return res

    monkeypatch.setattr(links_module, "check_plan_freshness", inject)
    with pytest.raises((LinkRebuildPostWriteError, IntegrityError)):
        apply_link_key_plan(plan, session)
    session.rollback()
    assert _snapshot(session) == before


# ---------------------------------------------------------------- PG 表锁排除（K2 核心）


def test_pg_rebuild_lock_blocks_concurrent_update(pg_engine):
    """重建持 SHARE ROW EXCLUSIVE + FOR UPDATE 期间，并发 UPDATE 被 lock_timeout 阻断。"""
    link_id, _ = _seed_one_link(pg_engine)
    factory = sessionmaker(bind=pg_engine, autoflush=False, expire_on_commit=False)
    a = factory()
    a.begin()
    acquire_rebuild_write_lock(a)  # 持锁至提交/回滚
    b = factory()
    b.execute(text("SET lock_timeout = '500ms'"))
    with pytest.raises(DBAPIError) as ei:
        b.execute(
            update(KnowledgeLinkORM)
            .where(KnowledgeLinkORM.id == link_id)
            .values(resolution="resolved")
        )
    assert "lock timeout" in str(ei.value).lower()
    a.rollback()
    b.rollback()
    a.close()
    b.close()

    # 锁释放后并发写者正常提交（暂时排除，非死锁）
    c = factory()
    c.execute(
        update(KnowledgeLinkORM)
        .where(KnowledgeLinkORM.id == link_id)
        .values(resolution="resolved")
    )
    c.commit()
    assert c.execute(
        select(KnowledgeLinkORM.resolution).where(KnowledgeLinkORM.id == link_id)
    ).scalar() == "resolved"
    c.close()


def test_pg_rebuild_lock_blocks_concurrent_insert_phantom(pg_engine):
    """SHARE ROW EXCLUSIVE 与 INSERT 的 ROW EXCLUSIVE 冲突 → 并发 phantom INSERT 被阻。"""
    link_id, item_id = _seed_one_link(pg_engine)
    factory = sessionmaker(bind=pg_engine, autoflush=False, expire_on_commit=False)
    a = factory()
    a.begin()
    acquire_rebuild_write_lock(a)
    b = factory()
    b.execute(text("SET lock_timeout = '500ms'"))
    with pytest.raises(DBAPIError) as ei:
        b.execute(
            text(
                "INSERT INTO knowledge_link (id, source_item_id, target_item_id, "
                "target_title, alias, normalized_link_key, link_normalization_version, "
                "resolution, cross_space, created_at, updated_at) "
                "VALUES (:id, :src, NULL, 'P', NULL, :key, 1, 'missing', FALSE, :now, :now)"
            ),
            {
                "id": str(uuid4()),
                "src": item_id,
                "key": normalized_link_key("P", None),
                "now": utcnow().isoformat(),
            },
        )
    assert "lock timeout" in str(ei.value).lower()
    a.rollback()
    b.rollback()
    a.close()
    b.close()
    assert link_id


def test_pg_rebuild_lock_serializes_second_rebuild(pg_engine):
    """两个重建写者串行化：第二个 acquire_rebuild_write_lock 在第一个持锁期间被阻。"""
    _seed_one_link(pg_engine)
    factory = sessionmaker(bind=pg_engine, autoflush=False, expire_on_commit=False)
    a = factory()
    a.begin()
    acquire_rebuild_write_lock(a)
    b = factory()
    b.execute(text("SET lock_timeout = '500ms'"))
    with pytest.raises(DBAPIError) as ei:
        acquire_rebuild_write_lock(b)  # LOCK TABLE 与 A 的表锁冲突
    assert "lock timeout" in str(ei.value).lower()
    a.rollback()
    b.rollback()
    a.close()
    b.close()
    # A 释放后 B 可取锁
    c = factory()
    c.begin()
    acquire_rebuild_write_lock(c)
    c.rollback()
    c.close()