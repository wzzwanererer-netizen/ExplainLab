"""K2 链接重建并发控制测试（默认 SQLite）。

验证整改批 K2 的两层纵深防御与 SQLite 方言语义：
- P2 乐观前置（步 7）：重读后并发改键 / 改版本 → UPDATE WHERE old_key+old_version
  rowcount=0 → LinkRebuildPostWriteError → 整体回滚零写入（故障注入，确定性）；
- 无并发漂移时 rowcount 恒为 1，重建正常（控制组，证明 P2 不误报）；
- phantom INSERT（并发新增碰撞行）→ 步 8 写后复核 (source,key) 重复 → 回滚零写入；
- SQLite busy_timeout=5000 已设置（liveness，降低写锁争用即失败概率）；
- SQLite 锁语义（实测固化）：写阶段（步 7 UPDATE 持 RESERVED）阻并发提交；
  读阶段（重读 SELECT）**不**阻并发提交 → 窗口②「重读 → 写」在 SQLite 上由 P2
  乐观前置兜底（非锁保护），此为已知局限，如实记录而非伪称读阶段已锁。

故障注入经 monkeypatch 门禁 C（check_plan_freshness）在重读快照之后、写之前
于**同一事务**注入行变更，确定性复现窗口②漂移，不依赖线程竞态（非 flaky）。
真实跨连接锁排除见 PG 镜像 test_links_concurrency_pg.py。
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError, OperationalError
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
    eng = create_engine_from_url(f"sqlite:///{tmp_path / 'conc.db'}")
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


def _plan_ready(links, session) -> object:
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


# ---------------------------------------------------------------- P2 乐观前置


def test_p2_key_drift_after_reread_rolls_back(session, monkeypatch):
    """重读后并发漂移键 → 步 7 rowcount=0 → 抛异常整体回滚零写入。"""
    items = SQLAlchemyKnowledgeRepository(session)
    links = SQLAlchemyLinkRepository(session)
    a, b, c, r1, r2, r3 = _setup_rebuild(session, items, links, monkeypatch)
    plan = _plan_ready(links, session)
    before = _snapshot(session)
    session.commit()

    real = links_module.check_plan_freshness

    def inject(plan_, current):
        res = real(plan_, current)  # 门禁 C 以重读快照判定（此时仍新鲜）
        # 模拟并发写者在重读之后改了 r1 的键（同事务确定性注入窗口②漂移）
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
    assert _snapshot(session) == before  # 零写入


def test_p2_version_drift_after_reread_rolls_back(session, monkeypatch):
    """重读后并发漂移版本 → 步 7 old_version 前置失配 rowcount=0 → 回滚零写入。"""
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
    """控制组：无并发漂移 → rowcount 恒 1，重建正常（P2 不误报）。"""
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
    """并发 phantom INSERT 碰撞新键 → 写被拒（DB UNIQUE 于步 7，步 8 复核为后备）→ 回滚零写入。"""
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
        # 并发新增一行：与 r1 规划新键碰撞（source 同为 a），版本已是目标 2
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
    # 碰撞写被拒：DB UNIQUE(source,key) 在步 7 即抛 IntegrityError；
    # 步 8 写后 (source,key) 复核为同口径后备（LinkRebuildPostWriteError）。两者均整体回滚。
    with pytest.raises((LinkRebuildPostWriteError, IntegrityError)):
        apply_link_key_plan(plan, session)
    session.rollback()
    assert _snapshot(session) == before


# ---------------------------------------------------------------- SQLite 方言语义


def test_sqlite_busy_timeout_pragma_is_5000(engine):
    """K2 liveness：连接初始化设置 busy_timeout=5000（写锁争用等待而非即失败）。"""
    with engine.connect() as conn:
        val = conn.execute(text("PRAGMA busy_timeout")).scalar()
    assert val == 5000


def _seed_one_link(engine) -> str:
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    setup = factory()
    setup.add(KnowledgeSpace(id="s1", name="s1", kind="personal"))
    setup.commit()  # 先落空间行，满足 knowledge_item.space_id 外键
    item = KnowledgeItemORM(
        id=str(uuid4()), title="A", content="正文", space_id="s1", status="active"
    )
    setup.add(item)
    setup.flush()
    link_id = str(uuid4())
    setup.add(
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
    setup.commit()
    setup.close()
    return link_id


def test_sqlite_write_phase_blocks_concurrent_commit(engine):
    """写阶段锁排除（真实成立）：重建一旦进入写（步 7 UPDATE，持 RESERVED），
    并发连接提交被阻（busy_timeout=0 即失败）；重建事务释放后并发写者可提交。
    """
    link_id = _seed_one_link(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    a = factory()
    a.begin()
    a.execute(
        update(KnowledgeLinkORM)
        .where(KnowledgeLinkORM.id == link_id)
        .values(resolution="missing")
    )  # 写阶段 → 持 RESERVED 锁
    b = factory()
    b.execute(text("PRAGMA busy_timeout=0"))
    with pytest.raises(OperationalError):
        b.execute(
            update(KnowledgeLinkORM)
            .where(KnowledgeLinkORM.id == link_id)
            .values(resolution="resolved")
        )
        b.commit()  # 升级 EXCLUSIVE 与 A 的写锁冲突 → database is locked
    a.rollback()
    b.rollback()
    a.close()
    b.close()

    c = factory()
    c.execute(
        update(KnowledgeLinkORM)
        .where(KnowledgeLinkORM.id == link_id)
        .values(resolution="resolved")
    )
    c.commit()  # A 释放后并发写者正常提交（暂时排除，非死锁）
    c.close()


def test_sqlite_read_phase_not_lock_protected(engine):
    """已知局限（如实记录，驱动 P2 为 SQLite 窗口②主防御）：

    实测 SQLite（isolation_level=None，journal_mode=delete）下，重建事务自门禁 C
    重读（SELECT）起至写之前**不持阻塞写者的锁**——并发连接此时可写并提交。
    因此「重读 → 写」窗口②在 SQLite 上**不由锁保护**，而由步 7 P2 乐观前置
    （old_key/old_version + rowcount）兜底：并发漂移使 rowcount=0 → 整体回滚零写入
    （见 test_p2_*_drift_after_reread_rolls_back）。写阶段开始后锁才生效（上一测试）。
    本测试固化该真实语义，防止误以为读阶段已锁保护。
    """
    link_id = _seed_one_link(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    a = factory()
    a.begin()
    a.execute(select(KnowledgeLinkORM.id))  # 读阶段：实测不持阻塞写者的锁
    b = factory()
    b.execute(text("PRAGMA busy_timeout=0"))
    b.execute(
        update(KnowledgeLinkORM)
        .where(KnowledgeLinkORM.id == link_id)
        .values(resolution="resolved")
    )
    b.commit()  # 读阶段不阻并发提交（真实语义）→ 成功，无异常
    assert b.execute(
        select(KnowledgeLinkORM.resolution).where(KnowledgeLinkORM.id == link_id)
    ).scalar() == "resolved"
    a.rollback()
    b.rollback()
    a.close()
    b.close()