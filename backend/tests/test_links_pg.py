"""A1-03 真实 PostgreSQL 测试：与 test_links.py 同断言（T18/T31 双方言要求）。

经 EXPLAINLAB_PG_TEST_URL 门控：未配置时整模块跳过（默认 SQLite 套件不受影响）；
配置后连真实 PG 实例执行真实在线 Alembic 迁移与真实 SQL，绝不用离线 SQL 或假数据
替代，不得用 SQLite 结果冒充 PG。

覆盖：仓库契约（唯一约束/FK CASCADE/SET NULL/D12 防御映射/1024 边界/布尔与 UTC）、
场景 B/D/I/J/L/M、T13–T17 全局版本同构守卫、T19–T30 门禁与零写入矩阵、
T32–T34 事务生命周期与无缓存预检计数、T35–T37、T39 十步顺序/故障注入/事务所有权、
T40 savepoint 边界。夹具与助手和 SQLite 版同名同口径，仅引擎/会话来源不同。
"""

from __future__ import annotations

import ast
import inspect
import json
import os
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401  确保 ORM 元数据注册
import app.services.links as links_module
from alembic import command
from app.core.config import get_settings
from app.db.session import create_engine_from_url
from app.models import (
    KnowledgeItemORM,
    KnowledgeLinkORM,
    KnowledgeRelationORM,
    KnowledgeSpace,
    KnowledgeVersionORM,
)
from app.services.errors import NotFoundError
from app.services.knowledge import SQLAlchemyKnowledgeRepository
from app.services.links import (
    SQLAlchemyLinkRepository,
    apply_link_key_plan,
    build_link_restorer,
    build_link_sync,
    demote_backlinks_on_delete,
    persist_rebuild_report,
)
from knowledge_core.domain import entities
from knowledge_core.domain.entities import (
    KnowledgeItem,
    KnowledgeLink,
    KnowledgeStatus,
    LinkResolution,
    utcnow,
)
from knowledge_core.markdown import (
    MarkdownDocument,
    compute_document_hashes,
    review_payload_hash,
)
from knowledge_core.markdown.codec import StdlibMarkdownCodec
from knowledge_core.markdown.link_service import (
    LinkKeyRebuild,
    LinkNormalizationVersionMismatch,
    LinkRebuildPlan,
)
from knowledge_core.markdown.links import (
    LINK_KEY_RULES,
    LinkWarningCode,
    link_key_for_version,
    normalized_link_key,
)

# --- 夹具与助手 ---


BACKEND_DIR = Path(__file__).resolve().parents[1]
PG_URL = os.environ.get("EXPLAINLAB_PG_TEST_URL")

pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason="未配置 EXPLAINLAB_PG_TEST_URL（真实 PostgreSQL 实例），跳过 A1-03 PG 链接测试",
)


def _alembic_cfg() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


@pytest.fixture(scope="module")
def engine() -> Iterator:
    """真实在线迁移到 head（非离线 SQL），提供 PG 引擎。"""
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


def _clean(s: Session) -> None:
    s.execute(text("DELETE FROM knowledge_item"))  # 级联清空 link/attachment/origin/item_tag
    s.execute(text("DELETE FROM tag"))
    s.execute(text("DELETE FROM gc_task"))
    s.execute(text("DELETE FROM storage_lock"))
    s.execute(text("DELETE FROM tag_change_log"))
    s.commit()


@pytest.fixture
def session(engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    s = factory()
    _clean(s)
    # 真实空间行：knowledge_item.space_id 是 FK（PG 同样强制）。
    for sid, kind in (("s1", "personal"), ("s2", "project"), ("p1", "project")):
        if s.get(KnowledgeSpace, sid) is None:
            s.add(KnowledgeSpace(id=sid, name=f"space-{sid}", kind=kind))
    s.commit()
    try:
        yield s
    finally:
        _clean(s)
        s.close()


@pytest.fixture
def items(session: Session) -> SQLAlchemyKnowledgeRepository:
    return SQLAlchemyKnowledgeRepository(session)


@pytest.fixture
def links(session: Session) -> SQLAlchemyLinkRepository:
    return SQLAlchemyLinkRepository(session)


@pytest.fixture
def sync(session: Session):
    return build_link_sync(session)


@pytest.fixture
def restorer(session: Session):
    return build_link_restorer(session)


def _mk_item(
    items: SQLAlchemyKnowledgeRepository,
    session: Session,
    title: str,
    *,
    content: str = "正文",
    space_id: str | None = "s1",
    status: KnowledgeStatus = KnowledgeStatus.ACTIVE,
) -> KnowledgeItem:
    item = KnowledgeItem(title=title, content=content, space_id=space_id, status=status)
    saved = items.save(item)
    session.commit()
    return saved


def _mk_link(
    source: KnowledgeItem,
    title: str,
    *,
    alias: str | None = None,
    target: KnowledgeItem | None = None,
    resolution: LinkResolution | None = None,
    cross_space: bool = False,
) -> KnowledgeLink:
    res = resolution if resolution is not None else (
        LinkResolution.RESOLVED if target is not None else LinkResolution.MISSING
    )
    return KnowledgeLink(
        source_id=source.id,
        target_id=None if target is None else target.id,
        target_title=title,
        alias=alias,
        # 按当前常量取注册表规则算键（v2 夹具下与生产口径一致）。
        normalized_link_key=link_key_for_version(entities.LINK_NORMALIZATION_VERSION, title, alias),
        link_normalization_version=entities.LINK_NORMALIZATION_VERSION,
        resolution=res,
        cross_space=cross_space,
    )


def _raw_insert_link(
    session: Session,
    source_id: UUID,
    key: str,
    *,
    version: int = 1,
    title: str = "X",
    alias: str | None = None,
    target_id: UUID | None = None,
    resolution: str = "missing",
    cross_space: bool = False,
) -> str:
    """直接 ORM 插入（绕过守卫，模拟外部写入/历史脏数据）。"""
    row = KnowledgeLinkORM(
        id=str(uuid4()),
        source_item_id=str(source_id),
        target_item_id=None if target_id is None else str(target_id),
        target_title=title,
        alias=alias,
        normalized_link_key=key,
        link_normalization_version=version,
        resolution=resolution,
        cross_space=cross_space,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    session.add(row)
    session.flush()
    return row.id


def _rows(session: Session, orm) -> list[dict]:
    return [
        {c.name: getattr(r, c.name) for c in orm.__table__.columns}
        for r in session.scalars(select(orm).order_by(orm.id))
    ]


def _snapshot(session: Session) -> dict:
    """全表逐列快照（T19/T30 最强零写入断言的比对基准）。"""
    return {
        "links": _rows(session, KnowledgeLinkORM),
        "items": _rows(session, KnowledgeItemORM),
        "version_count": len(_rows(session, KnowledgeVersionORM)),
        "relation_count": len(_rows(session, KnowledgeRelationORM)),
    }


_REVIEW_PROPOSAL = {"title": "A′", "content": "新正文"}  # 固定非空审核 payload（F 口径）


def _export_doc(item: KnowledgeItem, link_entities: list[KnowledgeLink]) -> MarkdownDocument:
    """交换文档：links[] 只含白名单四子字段（D1），与 Core 测试同口径。"""
    return MarkdownDocument(
        id=item.id,
        title=item.title,
        content=item.content,
        space_id=item.space_id,
        status=item.status,
        created_at=item.created_at,
        updated_at=item.updated_at,
        links=[
            {
                "target_id": None if r.target_id is None else str(r.target_id),
                "title": r.target_title,
                "alias": r.alias,
                "resolution": r.resolution.value,
            }
            for r in link_entities
        ],
    )


def _identity(links: SQLAlchemyLinkRepository, item: KnowledgeItem) -> dict:
    doc = _export_doc(item, links.list_links(item.id))
    h = compute_document_hashes(doc)
    return {
        "content_hash": h.document_content_hash,
        "payload_hash": h.document_payload_hash,
        "links_hash": h.links_hash,
        "review_hash": review_payload_hash(_REVIEW_PROPOSAL),
        "export_text": StdlibMarkdownCodec().dump(doc).text,
    }


def _assert_refusal(
    report,
    session: Session,
    before: dict,
    identity_before: dict,
    links: SQLAlchemyLinkRepository,
    item: KnowledgeItem,
    status: str,
    codes: tuple[str, ...] = (),
) -> None:
    """拒绝报告 + 全表逐列零写入 + 三 Hash/审核 Hash/导出字节不变（T30）。"""
    assert report.status == status
    assert report.requires_replan is True
    assert report.updated == 0
    assert report.unchanged == report.observed_row_count
    assert not hasattr(report, "skipped_rows")  # 无「已跳过行」清单（无部分更新分支）
    if codes:
        assert set(codes) <= {r.reason_code for r in report.stale_reasons}
    assert _snapshot(session) == before
    assert _identity(links, item) == identity_before


def _assert_write_refused(
    session: Session,
    before: dict,
    identity_before: dict,
    links: SQLAlchemyLinkRepository,
    item: KnowledgeItem,
) -> None:
    """常规写入抛异常后的零写入断言（T19）。"""
    session.rollback()
    assert _snapshot(session) == before
    assert _identity(links, item) == identity_before


def _v2_key(title: str, alias: str | None = None) -> str:
    """测试夹具 v2 规则：去掉全部空格（**不发布为生产规则**，仅 monkeypatch 注入）。"""
    return normalized_link_key(title, alias).replace(" ", "")


@pytest.fixture
def v2(monkeypatch):
    monkeypatch.setitem(LINK_KEY_RULES, 2, _v2_key)
    monkeypatch.setattr(entities, "LINK_NORMALIZATION_VERSION", 2)
    return _v2_key


@pytest.fixture
def rebuild_setup(session: Session, items, links, monkeypatch):
    """三条 v1 链接行（键含空格 → v2 键必变）+ 三个条目；随后注入 v2 规则与常量。"""
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


def _plan_ready(links: SQLAlchemyLinkRepository, session: Session, target: int = 2) -> LinkRebuildPlan:
    plan = LinkKeyRebuild(links).plan(target)
    # plan() 经仓库 autobegin 读事务；apply 要求无活动事务 → 先 commit。
    session.commit()
    assert plan.status == "ready"
    return plan


def _apply(plan: LinkRebuildPlan, session: Session):
    """apply 要求事务所有权（§8.3.7 步①）：基线快照等只读操作会 autobegin
    读事务，先 commit 释放（只读提交，不改数据），再交给 apply 自开事务。"""
    session.commit()
    return apply_link_key_plan(plan, session)


class _QueryCounter:
    """SQLAlchemy 事件监听：按语句文本分类计数（T20③/T34/T39 顺序守护）。"""

    def __init__(self, engine):
        self.events: list[str] = []
        self._engine = engine
        event.listen(engine, "before_cursor_execute", self._listen)

    def _listen(self, conn, cursor, statement, parameters, context, executemany):
        up = statement.upper()
        if "DISTINCT" in up and "link_normalization_version" in statement:
            kind = "distinct"
        elif up.startswith("UPDATE KNOWLEDGE_LINK"):
            kind = "update"
        elif up.startswith("SELECT") and "knowledge_link" in statement:
            if "target_title" in statement:
                kind = "sixcol"  # 6 列重读（含全量 ORM SELECT，apply 内只有列选择）
            elif "resolution" in statement:
                kind = "gov"
            elif "normalized_link_key" in statement:
                kind = "pairs"
            else:
                kind = "other_select"
        elif up.startswith("SELECT") and "knowledge_item" in statement:
            kind = "items"
        else:
            kind = "other"  # BEGIN/COMMIT/SAVEPOINT 等（方言差异，顺序断言时过滤）
        self.events.append(kind)

    def count(self, kind: str) -> int:
        return self.events.count(kind)

    def stop(self) -> None:
        event.remove(self._engine, "before_cursor_execute", self._listen)


# --- §7.4 仓库契约 ---


def test_save_get_roundtrip_all_columns(session, items, links):
    a = _mk_item(items, session, "A")
    b = _mk_item(items, session, "B")
    link = _mk_link(a, "B", alias="别名", target=b)
    saved = links.save_link(link)
    session.commit()
    got = links.get_link(saved.id)
    assert got is not None
    assert got.model_dump() == link.model_dump()
    raw = _rows(session, KnowledgeLinkORM)[0]
    assert raw["id"] == str(link.id)
    assert raw["source_item_id"] == str(a.id)
    assert raw["target_item_id"] == str(b.id)
    assert raw["target_title"] == "B"
    assert raw["alias"] == "别名"
    assert raw["normalized_link_key"] == normalized_link_key("B", "别名")
    assert raw["link_normalization_version"] == entities.LINK_NORMALIZATION_VERSION
    assert raw["resolution"] == "resolved"
    assert raw["cross_space"] is False or raw["cross_space"] == 0
    assert links.get_link(uuid4()) is None


def test_unique_source_key_alias_null(session, items, links):
    """T7：同源同键（alias NULL）重复插入真实抛 IntegrityError。"""
    a = _mk_item(items, session, "A")
    links.save_link(_mk_link(a, "B"))
    session.commit()
    with pytest.raises(IntegrityError):
        links.save_link(_mk_link(a, "B"))
    session.rollback()


def test_unique_source_key_alias_nonnull(session, items, links):
    """T7：alias 非 NULL 变体同样被拒（非空键修复了 NULL≠NULL 问题）。"""
    a = _mk_item(items, session, "A")
    links.save_link(_mk_link(a, "B", alias="x"))
    session.commit()
    with pytest.raises(IntegrityError):
        links.save_link(_mk_link(a, "B", alias="x"))
    session.rollback()


def test_cross_source_same_key_allowed(session, items, links):
    a = _mk_item(items, session, "A")
    b = _mk_item(items, session, "B")
    links.save_link(_mk_link(a, "Same"))
    links.save_link(_mk_link(b, "Same"))
    session.commit()
    assert len(links.list_by_key(normalized_link_key("Same", None))) == 2


def test_fk_cascade_source_delete(session, items, links):
    a = _mk_item(items, session, "A")
    b = _mk_item(items, session, "B")
    link = links.save_link(_mk_link(a, "B", target=b))
    session.commit()
    assert items.delete(a.id) is True
    session.commit()
    assert links.get_link(link.id) is None  # 源删除 → 出链 CASCADE
    assert _rows(session, KnowledgeLinkORM) == []


def test_fk_set_null_target_delete_read_side_missing(session, items, links):
    """FK SET NULL（外部级联路径）+ D12 读取侧防御映射。"""
    a = _mk_item(items, session, "A")
    b = _mk_item(items, session, "B")
    link = links.save_link(_mk_link(a, "B", target=b))
    session.commit()
    # 不经 demote 直接删目标（模拟外部级联）：FK ON DELETE SET NULL。
    assert items.delete(b.id) is True
    session.commit()
    raw = _rows(session, KnowledgeLinkORM)[0]
    assert raw["target_item_id"] is None
    assert raw["id"] == str(link.id)  # 行仍在
    got = links.get_link(link.id)
    assert got.resolution == LinkResolution.MISSING
    assert got.cross_space is False
    assert got.target_id is None
    assert got.target_title == "B"  # 字面留存
    assert links.list_backlinks(b.id) == []


def test_list_backlinks_stable_id_after_rename(session, items, links, sync):
    a = _mk_item(items, session, "A")
    b = _mk_item(items, session, "B")
    sync.sync(a, "[[B]]")
    session.commit()
    items.update(b.model_copy(update={"title": "B′"}))
    session.commit()
    back = links.list_backlinks(b.id)
    assert len(back) == 1
    assert back[0].source_id == a.id
    assert back[0].target_title == "B"  # 原书写字面不变


def test_list_by_key_exact_no_like(session, items, links):
    """%/_ 字符证明精确等值（LIKE 会把它们当通配符）。"""
    a = _mk_item(items, session, "A")
    links.save_link(_mk_link(a, "100%_done"))
    links.save_link(_mk_link(a, "100X_done"))
    session.commit()
    key = normalized_link_key("100%_done", None)
    assert "%" in key and "_" in key
    hits = links.list_by_key(key)
    assert len(hits) == 1
    assert hits[0].target_title == "100%_done"
    assert links.find_by_key(a.id, key).target_title == "100%_done"
    assert links.find_by_key(a.id, normalized_link_key("100X_done", None)).target_title == "100X_done"
    assert links.find_by_key(a.id, normalized_link_key("absent", None)) is None


def test_list_links_created_at_order(session, items, links):
    a = _mk_item(items, session, "A")
    # 显式递增 created_at：避免高频创建时微秒级时间戳并列导致次序不确定。
    t0 = utcnow()
    l1 = links.save_link(_mk_link(a, "First").model_copy(update={"created_at": t0}))
    l2 = links.save_link(
        _mk_link(a, "Second").model_copy(update={"created_at": t0 + timedelta(seconds=1)})
    )
    l3 = links.save_link(
        _mk_link(a, "Third").model_copy(update={"created_at": t0 + timedelta(seconds=2)})
    )
    session.commit()
    assert [r.id for r in links.list_links(a.id)] == [l1.id, l2.id, l3.id]


def test_list_all_links_order(session, items, links):
    a = _mk_item(items, session, "A")
    b = _mk_item(items, session, "B")
    links.save_link(_mk_link(b, "Zulu"))
    links.save_link(_mk_link(a, "Yankee"))
    links.save_link(_mk_link(a, "Alpha"))
    session.commit()
    rows = links.list_all_links()
    keys = [(str(r.source_id), r.normalized_link_key, str(r.id)) for r in rows]
    assert keys == sorted(keys)


def test_update_link_key_change_and_governance(session, items, links):
    a = _mk_item(items, session, "A")
    b = _mk_item(items, session, "B")
    link = links.save_link(_mk_link(a, "B", target=b))
    session.commit()
    # 改键（alias 变化）→ 受守卫，同构 v1 放行。
    changed = link.model_copy(
        update={
            "alias": "新别名",
            "normalized_link_key": normalized_link_key("B", "新别名"),
            "updated_at": utcnow(),
        }
    )
    got = links.update_link(changed)
    session.commit()
    assert got.alias == "新别名"
    assert got.target_id == b.id  # 保留绑定
    assert got.normalized_link_key == normalized_link_key("B", "新别名")
    # 治理列-only（键/版本不变）→ 豁免。
    gov = got.model_copy(update={"resolution": LinkResolution.RESOLVED, "updated_at": utcnow()})
    links.update_link(gov)
    session.commit()
    assert links.get_link(link.id).target_id == b.id


def test_update_link_not_found(session, links):
    a = KnowledgeItem(title="A", content="x")
    ghost = _mk_link(a, "B")
    with pytest.raises(NotFoundError):
        links.update_link(ghost)


def test_delete_link_bool(session, items, links):
    a = _mk_item(items, session, "A")
    link = links.save_link(_mk_link(a, "B"))
    session.commit()
    assert links.delete_link(link.id) is True
    assert links.delete_link(link.id) is False
    session.commit()


def test_delete_links_of_item_count(session, items, links):
    a = _mk_item(items, session, "A")
    b = _mk_item(items, session, "B")
    links.save_link(_mk_link(a, "B", target=b))
    links.save_link(_mk_link(a, "C"))
    links.save_link(_mk_link(b, "A", target=a))
    session.commit()
    assert links.delete_links_of_item(a.id) == 2
    session.commit()
    assert links.list_links(a.id) == []
    assert len(links.list_links(b.id)) == 1


def test_key_1024_boundary_ok(session, items, links):
    """键长恰 1024：NFKC 扩展（㍿→株式会社 4 字、ﬁ→fi 2 字）使标题键达 1023。

    原始标题 257 字 ≤ 500（DB 列限），alias NULL；双方言行为一致。
    """
    a = _mk_item(items, session, "A")
    title = "㍿" * 255 + "ﬁ" + "x"  # NFKC: 255*4 + 2 + 1 = 1023
    link = _mk_link(a, title)
    assert len(link.normalized_link_key) == 1024
    links.save_link(link)
    session.commit()
    assert links.get_link(link.id).normalized_link_key == link.normalized_link_key


def test_key_over_1024_core_rejects():
    """超长在 Core 层就被拒（不依赖 DB 报错，§9 R4）：键函数长度守卫先抛
    ValueError；绕过键函数直接构造实体，Pydantic max_length 仍拒（ValidationError）。"""
    a = KnowledgeItem(title="A", content="x")
    with pytest.raises(ValueError):
        _mk_link(a, "㍿" * 256)  # NFKC 1024 + \x1f = 1025 > 1024
    with pytest.raises(ValidationError):
        KnowledgeLink(
            source_id=a.id,
            target_id=None,
            target_title="㍿" * 256,
            alias=None,
            normalized_link_key="k" * 1025,
            link_normalization_version=1,
            resolution=LinkResolution.MISSING,
            cross_space=False,
        )


def test_cross_space_bool_utc_roundtrip(session, items, links):
    a = _mk_item(items, session, "A", space_id="s1")
    b = _mk_item(items, session, "B", space_id="s2")
    link = _mk_link(a, "B", target=b, resolution=LinkResolution.CROSS_SPACE, cross_space=True)
    saved = links.save_link(link)
    session.commit()
    got = links.get_link(saved.id)
    assert got.cross_space is True
    assert got.resolution == LinkResolution.CROSS_SPACE
    raw = _rows(session, KnowledgeLinkORM)[0]
    assert raw["cross_space"] in (1, True)
    assert got.created_at.tzinfo is not None
    assert got.created_at.utcoffset().total_seconds() == 0
    assert got.updated_at.utcoffset().total_seconds() == 0


# --- 场景 A–M（DB 层；Core 层同场景见 test_markdown_link_service.py）---


def test_scenario_a_rename_keeps_binding(session, items, links, sync):
    a = _mk_item(items, session, "A")
    b = _mk_item(items, session, "B")
    sync.sync(a, "[[B]]")
    session.commit()
    before = _identity(links, a)
    items.update(b.model_copy(update={"title": "B′"}))
    session.commit()
    sync.sync(a, "[[B]]")  # A 再次保存（正文未改）
    session.commit()
    row = links.list_links(a.id)[0]
    assert row.target_id == b.id
    assert row.resolution == LinkResolution.RESOLVED
    assert row.target_title == "B"
    assert [r.source_id for r in links.list_backlinks(b.id)] == [a.id]
    doc = _export_doc(a, links.list_links(a.id))
    assert doc.links[0]["target_id"] == str(b.id)
    assert _identity(links, a)["content_hash"] == before["content_hash"]


def test_scenario_b_nfkc_collision_db(session, items, links, sync):
    for t1, t2, literal in [("ﬁle", "file", "file"), ("Ｆoo", "Foo", "Foo"), ("①", "1", "1")]:
        i1 = _mk_item(items, session, t1)
        i2 = _mk_item(items, session, t2)
        a = _mk_item(items, session, f"A-{literal}")
        sync.sync(a, f"[[{literal}]]")
        session.commit()
        row = links.list_links(a.id)[0]
        assert row.resolution == LinkResolution.AMBIGUOUS
        assert row.target_id is None  # 绝不随机绑定
        resolver = build_link_sync(session)._resolver
        cands = resolver.find_candidates(literal)
        assert {c.id for c in cands} == {i1.id, i2.id}
        assert {c.title for c in cands} == {t1, t2}  # 原始标题各自保留


def test_scenario_c_unrelated_edit_no_churn(session, items, links, sync):
    a = _mk_item(items, session, "A")
    b = _mk_item(items, session, "B")
    sync.sync(a, "[[B]]\n\n段落一")
    session.commit()
    row = links.list_links(a.id)[0]
    snap0 = _snapshot(session)
    for text_body in ("[[B]]\n\n段落一改", "[[B]]\n\n段落一再改"):
        a = items.update(a.model_copy(update={"content": text_body}))
        session.commit()
        report = sync.sync(a, text_body)
        session.commit()
        assert report.created == 0 and report.removed == 0 and report.kept == 1
        rows = links.list_links(a.id)
        assert len(rows) == 1
        assert rows[0].id == row.id
        assert rows[0].target_id == b.id
        assert rows[0].created_at == row.created_at
    snap1 = _snapshot(session)
    assert snap1["version_count"] == snap0["version_count"]  # 链接同步不增长版本
    assert snap1["relation_count"] == snap0["relation_count"]


def test_scenario_d_export_destroy_restore_db(session, items, links, sync, restorer):
    a = _mk_item(items, session, "A", content="[[B]]")
    b = _mk_item(items, session, "B")
    sync.sync(a, "[[B]]")
    session.commit()
    before = _identity(links, a)
    text = before["export_text"]
    # 毁索引：显式删除全部链接行（D3 允许用途；键重建不删行）。
    assert links.delete_links_of_item(a.id) == 1
    session.commit()
    assert links.list_links(a.id) == []
    # B 改名后仍按稳定 ID 恢复。
    items.update(b.model_copy(update={"title": "B′"}))
    session.commit()
    parsed = StdlibMarkdownCodec().parse(text)
    report = restorer.restore(a, parsed.document.links, parsed.body)
    session.commit()
    assert report.restored == 1
    rows = links.list_links(a.id)
    assert len(rows) == 1
    assert rows[0].target_id == b.id
    assert rows[0].resolution == LinkResolution.RESOLVED
    after = _identity(links, a)
    assert after["content_hash"] == before["content_hash"]
    assert after["payload_hash"] == before["payload_hash"]
    assert after["review_hash"] == before["review_hash"]


def test_scenario_d_target_gone_fallback(session, items, links, sync, restorer):
    a = _mk_item(items, session, "A", content="[[B]]")
    b = _mk_item(items, session, "B")
    sync.sync(a, "[[B]]")
    session.commit()
    text = _identity(links, a)["export_text"]
    links.delete_links_of_item(a.id)
    demote_backlinks_on_delete(session, b.id)
    items.delete(b.id)
    session.commit()
    parsed = StdlibMarkdownCodec().parse(text)
    report = restorer.restore(a, parsed.document.links, parsed.body)
    session.commit()
    assert any(h.reason == "target_not_found" for h in report.invalid_hints)
    # unresolved_links 口径与 Core 一致：存标题键（非原始字面）。
    assert normalized_link_key("B", None) in report.unresolved_links
    rows = links.list_links(a.id)
    assert len(rows) == 1
    assert rows[0].resolution == LinkResolution.MISSING
    assert rows[0].target_id is None


def test_scenario_e_five_syncs_no_growth(session, items, links, sync):
    a = _mk_item(items, session, "A")
    _mk_item(items, session, "B")
    body = "[[B]] 与 [[C]]"
    sync.sync(a, body)
    session.commit()
    ids0 = {r.id for r in links.list_links(a.id)}
    snap0 = _snapshot(session)
    for _ in range(5):
        report = sync.sync(a, body)
        session.commit()
        assert report.created == 0 and report.removed == 0
    rows = links.list_links(a.id)
    assert {r.id for r in rows} == ids0
    assert len(rows) == 2
    snap1 = _snapshot(session)
    assert snap1["items"] == snap0["items"]  # updated_at 不因同步而变
    assert snap1["version_count"] == snap0["version_count"]
    assert snap1["relation_count"] == snap0["relation_count"]


def test_scenario_f_rebuild_real_apply(session, items, links, rebuild_setup):
    """T1/F：真实 apply 全量更新 + 非空洞 + 三 Hash/导出字节/治理列/条目全列不变。"""
    a, b, c, r1, r2, r3 = rebuild_setup
    before = _snapshot(session)
    identity_a = _identity(links, a)
    identity_b = _identity(links, b)
    plan = _plan_ready(links, session, 2)
    assert len(plan.updates) == 3  # v1→v2：全部行都需变更（无 no-op）
    report = _apply(plan, session)
    assert report.status == "rebuilt"
    assert report.updated == 3 and report.unchanged == 0
    assert report.requires_replan is False
    after = _snapshot(session)
    # 非空洞：键与版本真的变了。
    changed = 0
    for old, new in zip(before["links"], after["links"], strict=True):
        assert new["link_normalization_version"] == 2
        assert new["normalized_link_key"] == _v2_key(new["target_title"], new["alias"])
        if new["normalized_link_key"] != old["normalized_link_key"]:
            changed += 1
        # 治理五列 + created_at 逐行不变。
        for col in ("target_item_id", "target_title", "alias", "resolution", "cross_space", "created_at"):
            assert new[col] == old[col], col
        assert new["updated_at"] != old["updated_at"]  # 链接行自身 updated_at 更新
    assert changed == 3
    # 全部 target_id 保留。
    assert {r["target_item_id"] for r in after["links"]} == {r["target_item_id"] for r in before["links"]}
    # knowledge_item 全列不变。
    assert after["items"] == before["items"]
    assert after["version_count"] == before["version_count"]
    assert after["relation_count"] == before["relation_count"]
    # 三 Hash + 审核 Hash + 导出字节 + links_hash 不变。
    assert _identity(links, a) == identity_a
    assert _identity(links, b) == identity_b


def test_scenario_g_collision_refused_zero_write(session, items, links, monkeypatch):
    """T2/T4/G：单组碰撞（含不同 target_id）→ plan 拒绝 + apply 零写入。"""
    a = _mk_item(items, session, "A")
    b1 = _mk_item(items, session, "B1")
    b2 = _mk_item(items, session, "B2")
    # 脏键构造：v1 键不同（双空格），v2 键相同（去空格）→ 碰撞。
    id1 = _raw_insert_link(session, a.id, "foo bar\x1f", title="Foo Bar", target_id=b1.id, resolution="resolved")
    id2 = _raw_insert_link(session, a.id, "foo  bar\x1f", title="Foo Bar", target_id=b2.id, resolution="resolved")
    session.commit()
    monkeypatch.setitem(LINK_KEY_RULES, 2, _v2_key)
    monkeypatch.setattr(entities, "LINK_NORMALIZATION_VERSION", 2)
    before = _snapshot(session)
    identity = _identity(links, a)
    plan = LinkKeyRebuild(links).plan(2)
    session.commit()
    assert plan.status == "refused_collision"
    assert len(plan.collision_groups) == 1
    group = plan.collision_groups[0]
    assert {e.link_id for e in group.entries} == {UUID(id1), UUID(id2)}
    assert {e.target_id for e in group.entries} == {b1.id, b2.id}  # 两个绑定都保留
    for e in group.entries:
        assert e.old_key and e.new_key and e.old_version == 1
    report = _apply(plan, session)
    _assert_refusal(report, session, before, identity, links, a, "refused_stale_plan", ("plan_not_ready",))
    # 无行被合并/覆盖/删除。
    assert len(_rows(session, KnowledgeLinkORM)) == 2


def test_t3_three_collision_groups_db(session, items, links, monkeypatch):
    a = _mk_item(items, session, "A")
    b = _mk_item(items, session, "B")
    c = _mk_item(items, session, "C")
    for src, key, title in [
        (a.id, "foo bar\x1f", "Foo Bar"), (a.id, "foo  bar\x1f", "Foo Bar"),
        (b.id, "baz qux\x1f", "Baz Qux"), (b.id, "baz  qux\x1f", "Baz Qux"),
        (c.id, "one two\x1f", "One Two"), (c.id, "one  two\x1f", "One Two"),
    ]:
        _raw_insert_link(session, src, key, title=title)
    session.commit()
    monkeypatch.setitem(LINK_KEY_RULES, 2, _v2_key)
    monkeypatch.setattr(entities, "LINK_NORMALIZATION_VERSION", 2)
    before = _snapshot(session)
    plan = LinkKeyRebuild(links).plan(2)
    session.commit()
    assert plan.status == "refused_collision"
    assert len(plan.collision_groups) == 3  # 完整列出，不漏报
    report = _apply(plan, session)
    assert report.status == "refused_stale_plan"
    assert len(report.collision_groups) == 3
    assert _snapshot(session) == before


def test_t8_cross_source_same_new_key_not_collision(session, items, links, rebuild_setup):
    a, b, c, r1, r2, r3 = rebuild_setup
    # 两个不同 source 在 v2 下同键（复合唯一约束允许）。
    _raw_insert_link(session, a.id, "shared key\x1f", title="Shared Key", version=1)
    _raw_insert_link(session, b.id, "shared key\x1f", title="Shared Key", version=1)
    session.commit()
    plan = _plan_ready(links, session, 2)
    before = _snapshot(session)
    report = _apply(plan, session)
    assert report.status == "rebuilt"
    after = _snapshot(session)
    shared = [r for r in after["links"] if r["target_title"] == "Shared Key"]
    assert len(shared) == 2
    assert shared[0]["normalized_link_key"] == shared[1]["normalized_link_key"] == "sharedkey\x1f"
    assert {r["source_item_id"] for r in shared} == {str(a.id), str(b.id)}
    assert after["items"] == before["items"]


def test_t9_idempotent_replan_no_churn(session, items, links, rebuild_setup):
    a, b, c, r1, r2, r3 = rebuild_setup
    plan = _plan_ready(links, session, 2)
    assert _apply(plan, session).status == "rebuilt"
    before = _snapshot(session)
    plan2 = _plan_ready(links, session, 2)
    assert plan2.updates == ()
    report = _apply(plan2, session)
    assert report.status == "rebuilt"
    assert report.updated == 0 and report.unchanged == 3
    assert _snapshot(session) == before  # 不 churn updated_at


def test_t10_rollback_rerun_and_collision_refusal(session, items, links, monkeypatch):
    """T10：回滚 = 旧版本重跑（同受门禁）；旧键碰撞 → 整体拒绝保持现状。"""
    a = _mk_item(items, session, "A")
    b = _mk_item(items, session, "B")
    r1 = links.save_link(_mk_link(a, "Foo Bar", target=b))
    session.commit()
    monkeypatch.setitem(LINK_KEY_RULES, 2, _v2_key)
    monkeypatch.setattr(entities, "LINK_NORMALIZATION_VERSION", 2)
    identity = _identity(links, a)
    plan = _plan_ready(links, session, 2)
    assert _apply(plan, session).status == "rebuilt"
    assert links.get_link(r1.id).normalized_link_key == "foobar\x1f"
    # 回滚到 v1。
    back = _plan_ready(links, session, 1)
    report = _apply(back, session)
    assert report.status == "rebuilt"
    row = links.get_link(r1.id)
    assert row.normalized_link_key == "foo bar\x1f"
    assert row.link_normalization_version == 1
    assert row.target_id == b.id
    assert _identity(links, a) == identity
    # 再升到 v2 后注入脏键行 → 回滚计划 v1 键碰撞 → 拒绝，保持 v2 现状。
    assert _apply(_plan_ready(links, session, 2), session).status == "rebuilt"
    _raw_insert_link(session, a.id, "foob ar\x1f", version=2, title="Foo Bar")
    session.commit()
    before = _snapshot(session)
    rollback = LinkKeyRebuild(links).plan(1)
    session.commit()
    assert rollback.status == "refused_collision"
    report = _apply(rollback, session)
    assert report.status == "refused_stale_plan"
    assert _snapshot(session) == before  # 不做部分回滚


def test_scenario_h_alias_change_reparse_not_inherit(session, items, links, sync):
    a = _mk_item(items, session, "A")
    b = _mk_item(items, session, "B")
    x = _mk_item(items, session, "X")
    sync.sync(a, "[[B]]")
    session.commit()
    old = links.list_links(a.id)[0]
    assert old.target_id == b.id
    # 制造歧义：X 改名为 B → 两个同标题键条目。
    items.update(x.model_copy(update={"title": "B"}))
    session.commit()
    report = sync.sync(a, "[[B|别名]]")
    session.commit()
    assert report.removed == 1 and report.created == 1
    rows = links.list_links(a.id)
    assert len(rows) == 1
    new = rows[0]
    assert new.id != old.id  # 旧行删、新行建
    assert new.resolution == LinkResolution.AMBIGUOUS  # 重新解析得歧义
    assert new.target_id is None  # 不继承旧绑定
    # alias-only 变更同理。
    report = sync.sync(a, "[[B|别名2]]")
    session.commit()
    assert report.removed == 1 and report.created == 1
    assert links.list_links(a.id)[0].target_id is None


def test_scenario_i_delete_demote_db(session, items, links, sync):
    """D12：写侧降级 + 读取不抛异常 + 防御映射 + 实体校验器未弱化。"""
    a = _mk_item(items, session, "A")
    b = _mk_item(items, session, "B")
    sync.sync(a, "[[B]]")
    session.commit()
    content_hash = _identity(links, a)["content_hash"]
    row = links.list_links(a.id)[0]
    assert demote_backlinks_on_delete(session, b.id) == 1
    assert items.delete(b.id) is True
    session.commit()
    raw = _rows(session, KnowledgeLinkORM)[0]
    assert raw["target_item_id"] is None
    assert raw["resolution"] == "missing"
    assert raw["cross_space"] in (0, False)
    assert raw["target_title"] == "B"
    got = links.get_link(row.id)
    assert got.resolution == LinkResolution.MISSING and got.target_id is None
    assert links.list_links(a.id) and links.list_backlinks(b.id) == []
    assert _identity(links, a)["content_hash"] == content_hash  # A 正文未改
    # 读取侧防御映射：手工置 NULL + resolved（历史脏数据）→ 仍读成 missing。
    session.execute(
        text("UPDATE knowledge_link SET resolution = 'resolved' WHERE target_item_id IS NULL")
    )
    session.commit()
    assert links.get_link(row.id).resolution == LinkResolution.MISSING
    # 实体校验器未被弱化：直接构造非法实体仍抛 ValueError。
    with pytest.raises(ValidationError):
        KnowledgeLink(
            source_id=a.id, target_id=None, target_title="B",
            normalized_link_key=normalized_link_key("B", None),
            resolution=LinkResolution.RESOLVED,
        )


def test_scenario_j_no_auto_cross_space(session, items, links, sync, restorer):
    # ① 源 space None + project 同名条目 → 自动不绑定。
    a = _mk_item(items, session, "A", space_id=None)
    p = _mk_item(items, session, "B", space_id="p1")
    sync.sync(a, "[[B]]")
    session.commit()
    assert links.list_links(a.id)[0].resolution == LinkResolution.MISSING
    # ② 源 p1 + 目标 None → 同样不跨空间。
    a2 = _mk_item(items, session, "A2", space_id="p1")
    _mk_item(items, session, "C", space_id=None)
    sync.sync(a2, "[[C]]")
    session.commit()
    assert links.list_links(a2.id)[0].resolution == LinkResolution.MISSING
    # 候选接口可列出跨空间候选（只读）。
    resolver = build_link_sync(session)._resolver
    assert p.id in {c.id for c in resolver.find_candidates("B")}
    # ③ 对照：有效 UUID 提示恢复 → 必须 cross_space=True（E2 空间重算）。
    report = restorer.restore(a, [{"title": "B", "target_id": str(p.id), "alias": None}], "[[B]]")
    session.commit()
    assert any(w.code == LinkWarningCode.CROSS_SPACE_BINDING_RESTORED for w in report.warnings)
    rows = links.list_links(a.id)
    bound = [r for r in rows if r.target_id == p.id]
    assert len(bound) == 1
    assert bound[0].resolution == LinkResolution.CROSS_SPACE
    assert bound[0].cross_space is True
    raw = next(r for r in _rows(session, KnowledgeLinkORM) if r["target_item_id"] == str(p.id))
    assert raw["resolution"] == "cross_space"
    assert raw["cross_space"] in (1, True)


def test_scenario_k_self_link(session, items, links, sync):
    a = _mk_item(items, session, "A")
    sync.sync(a, "[[A]]")
    session.commit()
    row = links.list_links(a.id)[0]
    assert row.resolution == LinkResolution.RESOLVED
    assert row.target_id == a.id
    assert a.id in {r.source_id for r in links.list_backlinks(a.id)}
    items.update(a.model_copy(update={"title": "A′"}))
    session.commit()
    report = sync.sync(a, "[[A]]")
    session.commit()
    assert report.kept == 1 and report.created == 0
    assert links.list_links(a.id)[0].id == row.id


def test_scenario_l_archived(session, items, links, sync):
    a = _mk_item(items, session, "A")
    arch = _mk_item(items, session, "Arch", status=KnowledgeStatus.ARCHIVED)
    sync.sync(a, "[[Arch]]")
    session.commit()
    assert links.list_links(a.id)[0].resolution == LinkResolution.MISSING  # ① 自动排除 archived
    resolver = build_link_sync(session)._resolver
    cands = resolver.find_candidates("Arch")
    assert any(c.id == arch.id and c.status == KnowledgeStatus.ARCHIVED for c in cands)  # ② 候选仍列出
    # ③ 显式绑定允许 archived（Core 规则；A1-03 无 HTTP 写入口）。
    # 用新 source，避免与 a 既有 missing 行同键触发 UNIQUE。
    a_exp = _mk_item(items, session, "A-exp")
    link, warnings = resolver.bind_explicit(a_exp, arch, title="Arch")
    assert link.resolution == LinkResolution.RESOLVED
    links.save_link(link)
    session.commit()
    assert links.get_link(link.id).target_id == arch.id
    # ⑤ active + archived 同键标题 → 自动只看 active，唯一 active → resolved。
    a2 = _mk_item(items, session, "A2")
    _mk_item(items, session, "Dup", status=KnowledgeStatus.ARCHIVED)
    act = _mk_item(items, session, "Dup")
    sync.sync(a2, "[[Dup]]")
    session.commit()
    row = links.list_links(a2.id)[0]
    assert row.resolution == LinkResolution.RESOLVED
    assert row.target_id == act.id


def test_scenario_m_hint_aggregation_db(session, items, links, restorer):
    a = _mk_item(items, session, "A")
    b = _mk_item(items, session, "B")
    c = _mk_item(items, session, "C")
    body = "[[B]] [[C]] [[D]]"
    hints = [
        {"title": "B", "target_id": str(b.id), "alias": None},
        {"title": "B", "target_id": str(b.id), "alias": None},  # 重复提示
        {"title": "C", "target_id": str(b.id), "alias": None},
        {"title": "C", "target_id": str(c.id), "alias": None},  # 矛盾 → conflict
        {"title": "D", "target_id": "not-a-uuid", "alias": None},  # 无效 UUID → 回退
        {"title": "Ghost", "target_id": str(b.id), "alias": None},  # 正文无 [[Ghost]] → 孤儿提示
    ]
    report = restorer.restore(a, hints, body)
    session.commit()
    rows = {r.target_title: r for r in links.list_links(a.id)}
    assert rows["B"].target_id == b.id  # 重复提示不产生重复行
    assert rows["C"].resolution == LinkResolution.CONFLICT
    assert rows["C"].target_id is None
    assert any(w.code == LinkWarningCode.CONFLICTING_HINTS for w in report.warnings)
    assert rows["D"].resolution == LinkResolution.MISSING  # 回退标题解析（D 不存在）
    assert any(h.reason == "malformed_uuid" for h in report.invalid_hints)
    assert "Ghost" not in rows  # 孤儿提示不建行
    assert any(w.code == LinkWarningCode.ORPHAN_HINT for w in report.warnings)
    # 提示顺序打乱 → 行集合与状态不变。
    links.delete_links_of_item(a.id)
    session.commit()
    restorer.restore(a, list(reversed(hints)), body)
    session.commit()
    rows2 = {r.target_title: r for r in links.list_links(a.id)}
    assert {t: (r.target_id, r.resolution) for t, r in rows.items()} == {
        t: (r.target_id, r.resolution) for t, r in rows2.items()
    }


# --- T13–T17 全局版本同构守卫（DB 级；T18 双方言见 test_links_pg.py）---


def test_t13_empty_table_first_link(session, items, links):
    a = _mk_item(items, session, "A")
    link = links.save_link(_mk_link(a, "B"))  # 空表放行
    session.commit()
    assert link.link_normalization_version == entities.LINK_NORMALIZATION_VERSION
    assert len(_rows(session, KnowledgeLinkORM)) == 1


def test_t14_homogeneous_v1_writes_ok(session, items, links):
    a = _mk_item(items, session, "A")
    b = _mk_item(items, session, "B")
    existing = links.save_link(_mk_link(a, "B", target=b))
    session.commit()
    # 新建 + 改键更新都正常。
    links.save_link(_mk_link(a, "C"))
    changed = existing.model_copy(
        update={"alias": "x", "normalized_link_key": normalized_link_key("B", "x"), "updated_at": utcnow()}
    )
    links.update_link(changed)
    session.commit()
    rows = _rows(session, KnowledgeLinkORM)
    assert all(r["link_normalization_version"] == 1 for r in rows)
    assert len(rows) == 2


def test_t15_constant_v2_refuses_v1_table(session, items, links, sync, monkeypatch):
    a = _mk_item(items, session, "A")
    b = _mk_item(items, session, "B")
    links.save_link(_mk_link(a, "B", target=b))  # v1 行（常量当时为 1）
    session.commit()
    # v1 行落库后才注入 v2 规则与常量（夹具参数会在测试体前生效，故手动注入）。
    monkeypatch.setitem(LINK_KEY_RULES, 2, _v2_key)
    monkeypatch.setattr(entities, "LINK_NORMALIZATION_VERSION", 2)
    before = _snapshot(session)
    identity = _identity(links, a)
    # 直接仓库写入 → 全局预检拒绝。
    with pytest.raises(LinkNormalizationVersionMismatch) as exc:
        links.save_link(_mk_link(a, "C"))
    assert exc.value.scope == "global"
    _assert_write_refused(session, before, identity, links, a)
    # 同步路径：本 source 无行 → 局部守卫放行、全局预检拒绝（纵深防御两层都真实）。
    c = _mk_item(items, session, "C")
    before = _snapshot(session)  # 条目 C 的创建是合法写入，基线在其后重取
    identity = _identity(links, a)
    with pytest.raises(LinkNormalizationVersionMismatch) as exc2:
        sync.sync(c, "[[B]]")
    assert exc2.value.scope == "global"
    _assert_write_refused(session, before, identity, links, a)


def test_t16_review_counterexample(session, items, links, sync, monkeypatch):
    """★ 审查反例：C 无链接行，A/B 有 v1 行，常量 v2。"""
    a = _mk_item(items, session, "A")
    b = _mk_item(items, session, "B")
    c = _mk_item(items, session, "C")
    links.save_link(_mk_link(a, "B", target=b))
    links.save_link(_mk_link(b, "A", target=a))
    session.commit()
    monkeypatch.setitem(LINK_KEY_RULES, 2, _v2_key)
    monkeypatch.setattr(entities, "LINK_NORMALIZATION_VERSION", 2)
    before = _snapshot(session)
    identity = _identity(links, c)
    # ① 局部守卫 all([])==True 确实通过（sync 走到全局预检才拒，scope=global 证明）。
    with pytest.raises(LinkNormalizationVersionMismatch) as exc:
        sync.sync(c, "[[A]]")
    assert exc.value.scope == "global"
    # ②③ 全局预检拒绝 C 创建 v2 链接，全表零写入。
    with pytest.raises(LinkNormalizationVersionMismatch):
        links.save_link(_mk_link(c, "A", target=a))
    _assert_write_refused(session, before, identity, links, c)
    # ④ 把 A/B 的行重建到 v2 后，C 的写入恢复正常。
    plan = _plan_ready(links, session, 2)
    assert _apply(plan, session).status == "rebuilt"
    links.save_link(_mk_link(c, "A", target=a))
    session.commit()
    assert all(r["link_normalization_version"] == 2 for r in _rows(session, KnowledgeLinkORM))


def test_t17_mixed_refuses_all(session, items, links, v2):
    a = _mk_item(items, session, "A")
    b = _mk_item(items, session, "B")
    c = _mk_item(items, session, "C")
    links.save_link(_mk_link(a, "B", target=b))  # v2 行（常量 2）
    session.commit()
    _raw_insert_link(session, b.id, normalized_link_key("A", None), version=1, title="A", target_id=a.id, resolution="resolved")
    session.commit()
    before = _snapshot(session)
    # 任何 source（含 v2 行的、含 v1 行的、无行的）常规写入全部拒绝。
    for src, title in [(a, "X"), (b, "Y"), (c, "Z")]:
        with pytest.raises(LinkNormalizationVersionMismatch):
            links.save_link(_mk_link(src, title))
        session.rollback()
    assert _snapshot(session) == before
    # 重建入口亦拒绝（混合版本 → plan refused_mixed_version → apply plan_not_ready）。
    plan = LinkKeyRebuild(links).plan(2)
    session.commit()
    assert plan.status == "refused_mixed_version"
    report = _apply(plan, session)
    assert report.status == "refused_stale_plan"
    assert report.updated == 0
    assert _snapshot(session) == before


def test_t19_refusal_full_zero_change(session, items, links, monkeypatch):
    """T19：三种拒绝情形全表逐列 + 条目全列 + 三 Hash + 导出字节 + 版本/关系行数不变。"""
    a = _mk_item(items, session, "A")
    b = _mk_item(items, session, "B")
    c = _mk_item(items, session, "C")
    links.save_link(_mk_link(a, "B", target=b))
    session.commit()
    monkeypatch.setitem(LINK_KEY_RULES, 2, _v2_key)
    monkeypatch.setattr(entities, "LINK_NORMALIZATION_VERSION", 2)
    # 情形一：全表 v1 + 常量 v2（T15）。
    before = _snapshot(session)
    identity = _identity(links, a)
    with pytest.raises(LinkNormalizationVersionMismatch):
        links.save_link(_mk_link(c, "B"))
    _assert_write_refused(session, before, identity, links, a)
    # 情形二：C 无行（T16）。
    with pytest.raises(LinkNormalizationVersionMismatch):
        links.save_link(_mk_link(c, "A"))
    _assert_write_refused(session, before, identity, links, a)
    # 情形三：混合（T17）——v1 表里插入异版本行构成真实混合。
    _raw_insert_link(session, b.id, normalized_link_key("A", None), version=99, title="A")
    session.commit()
    before = _snapshot(session)
    with pytest.raises(LinkNormalizationVersionMismatch):
        links.save_link(_mk_link(a, "X"))
    _assert_write_refused(session, before, identity, links, a)


def test_t20_exempt_and_counts(engine, session, items, links):
    a = _mk_item(items, session, "A")
    b = _mk_item(items, session, "B")
    r1 = links.save_link(_mk_link(a, "B", target=b))
    session.commit()
    # ① 不同构窗口内 D12 降级仍可执行（治理豁免）。
    _raw_insert_link(session, a.id, normalized_link_key("Dirty", None), version=99, title="Dirty")
    session.commit()
    assert demote_backlinks_on_delete(session, b.id) == 1
    assert items.delete(b.id) is True
    session.commit()
    assert links.get_link(r1.id).resolution == LinkResolution.MISSING
    # ② 删掉异版本行 → 剩余同构 → 写入恢复（⑤）。
    dirty = next(r for r in links.list_links(a.id) if r.target_title == "Dirty")
    assert links.delete_link(dirty.id) is True
    session.commit()
    links.save_link(_mk_link(a, "New"))
    session.commit()
    # ③ 【R3.1 断言修订】同一事务内 5 次受守卫写入 → DISTINCT 计数 == 5。
    counter = _QueryCounter(engine)
    for i in range(5):
        links.save_link(_mk_link(a, f"K{i}"))
    assert counter.count("distinct") == 5
    session.commit()
    # ④ rollback 后新事务重新预检。
    links.save_link(_mk_link(a, "RollbackMe"))
    session.rollback()
    n = counter.count("distinct")
    links.save_link(_mk_link(a, "AfterRollback"))
    session.commit()
    assert counter.count("distinct") == n + 1
    counter.stop()


def test_t21_gate_a_drift(session, items, links, rebuild_setup):
    a, b, c, r1, r2, r3 = rebuild_setup
    plan = _plan_ready(links, session, 2)
    # ① 改某行版本为异值 → 门禁 A 拒绝。
    session.execute(
        text("UPDATE knowledge_link SET link_normalization_version = 99 WHERE id = :id"),
        {"id": str(r1.id)},
    )
    session.commit()
    before = _snapshot(session)
    identity = _identity(links, a)
    report = _apply(plan, session)
    _assert_refusal(report, session, before, identity, links, a, "refused_version_drift")
    # 恢复后再测插入异版本新行。
    session.execute(
        text("UPDATE knowledge_link SET link_normalization_version = 1 WHERE id = :id"),
        {"id": str(r1.id)},
    )
    session.commit()
    plan = _plan_ready(links, session, 2)
    _raw_insert_link(session, c.id, normalized_link_key("Extra", None), version=2, title="Extra")
    session.commit()
    before = _snapshot(session)
    identity = _identity(links, a)
    report = _apply(plan, session)
    _assert_refusal(report, session, before, identity, links, a, "refused_version_drift")


def test_t21_gate_b_incomplete_and_dup(session, items, links, rebuild_setup):
    a, b, c, r1, r2, r3 = rebuild_setup
    plan = _plan_ready(links, session, 2)
    before = _snapshot(session)
    identity = _identity(links, a)
    # ② 删掉一条 update（部分计划）→ 门禁 B 拒绝。
    partial = plan.model_copy(update={"updates": plan.updates[:-1]})
    report = _apply(partial, session)
    _assert_refusal(report, session, before, identity, links, a, "refused_incomplete_plan", ("incomplete_coverage",))
    # ③ 不同 link_id 含重复 (source_id, new_key) → 门禁 B 拒绝。
    u0, u1 = plan.updates[0], plan.updates[1]
    dup = u1.model_copy(update={"source_id": u0.source_id, "new_key": u0.new_key})
    dup_plan = plan.model_copy(update={"updates": (u0, dup) + plan.updates[2:]})
    report = _apply(dup_plan, session)
    _assert_refusal(report, session, before, identity, links, a, "refused_incomplete_plan", ("duplicate_new_key_in_plan",))
    # ④ 正常 plan → 单事务全量更新成功（写后复核在 apply 内部）。
    report = _apply(plan, session)
    assert report.status == "rebuilt"
    rows = _rows(session, KnowledgeLinkORM)
    assert all(r["link_normalization_version"] == 2 for r in rows)
    pairs = [(r["source_item_id"], r["normalized_link_key"]) for r in rows]
    assert len(set(pairs)) == len(pairs)


# --- T22–T30 门禁 C 过期计划矩阵（DB 级；Core 纯函数部分见 Core 测试）---


def test_t22_target_title_changed(session, items, links, rebuild_setup):
    a, b, c, r1, r2, r3 = rebuild_setup
    plan = _plan_ready(links, session, 2)
    # 治理列豁免写入：改 target_title 但键/版本不变 → 全局守卫不拦、版本集合不变。
    links.update_link(r1.model_copy(update={"target_title": "改后标题", "updated_at": utcnow()}))
    session.commit()
    before = _snapshot(session)
    identity = _identity(links, a)
    report = _apply(plan, session)
    # refused_stale_plan（而非 refused_version_drift）证明门禁 A 确实放行。
    _assert_refusal(report, session, before, identity, links, a, "refused_stale_plan", ("target_title_changed",))
    reason = next(r for r in report.stale_reasons if r.reason_code == "target_title_changed")
    assert reason.link_id == r1.id
    assert reason.field == "target_title"
    assert reason.expected == "Target One"
    assert reason.actual == "改后标题"


@pytest.mark.parametrize(
    ("old_alias", "new_alias"),
    [(None, ""), ("", None), ("A", "a"), ("A", " A ")],
)
def test_t23_alias_changed_raw_compare(session, items, links, rebuild_setup, old_alias, new_alias):
    a, b, c, r1, r2, r3 = rebuild_setup
    # 把 r2 的 alias 置为 old_alias（键同步重算，保持干净 v1 行）。
    # 用直接 SQL（模拟外部治理写入）：常量已为 2，受守卫的改键写入会被全局预检拒绝。
    session.execute(
        text("UPDATE knowledge_link SET alias = :alias, normalized_link_key = :key WHERE id = :id"),
        {"alias": old_alias, "key": normalized_link_key("Target Two", old_alias), "id": str(r2.id)},
    )
    session.commit()
    plan = _plan_ready(links, session, 2)
    # 豁免写入改 alias（键不动）→ 原值精确比对拒绝（规范化后相等也拒）。
    row = links.get_link(r2.id)
    links.update_link(row.model_copy(update={"alias": new_alias, "updated_at": utcnow()}))
    session.commit()
    before = _snapshot(session)
    identity = _identity(links, a)
    report = _apply(plan, session)
    _assert_refusal(report, session, before, identity, links, a, "refused_stale_plan", ("alias_changed",))
    reason = next(r for r in report.stale_reasons if r.reason_code == "alias_changed" and r.link_id == r2.id)
    assert reason.field == "alias"
    assert reason.expected == old_alias
    assert reason.actual == new_alias


def test_t24_row_added(session, items, links, rebuild_setup):
    a, b, c, r1, r2, r3 = rebuild_setup
    plan = _plan_ready(links, session, 2)
    # 新增同版本行：A 放行、B（计划内部）放行 → C 发现。
    new_id = _raw_insert_link(session, c.id, normalized_link_key("Brand New", None), version=1, title="Brand New")
    session.commit()
    before = _snapshot(session)
    identity = _identity(links, a)
    report = _apply(plan, session)
    _assert_refusal(report, session, before, identity, links, a, "refused_stale_plan", ("row_added", "row_not_covered"))
    added = next(r for r in report.stale_reasons if r.reason_code == "row_added")
    assert added.link_id == UUID(new_id)
    # 新行原样保留（未被更新也未被删除）。
    raw = next(r for r in _rows(session, KnowledgeLinkORM) if r["id"] == new_id)
    assert raw["link_normalization_version"] == 1
    assert raw["normalized_link_key"] == normalized_link_key("Brand New", None)


def test_t25_row_deleted(session, items, links, rebuild_setup):
    a, b, c, r1, r2, r3 = rebuild_setup
    plan = _plan_ready(links, session, 2)
    # 删掉一条 update 对应的行。
    links.delete_link(r1.id)
    session.commit()
    before = _snapshot(session)
    identity = _identity(links, a)
    report = _apply(plan, session)
    _assert_refusal(report, session, before, identity, links, a, "refused_stale_plan", ("row_deleted",))
    assert any(r.link_id == r1.id for r in report.stale_reasons if r.reason_code == "row_deleted")
    # 另测 no-op 行被删（同版本计划，updates 为空）→ 同样拒绝（快照覆盖全表）。
    # 先把剩余行重建到 v2（常量 2），再建一行 v2，得到全 no-op 计划。
    assert _apply(_plan_ready(links, session, 2), session).status == "rebuilt"
    links.save_link(_mk_link(a, "Back One", target=b))
    session.commit()
    plan2 = _plan_ready(links, session, 2)
    assert plan2.updates == ()
    noop_row = links.list_links(a.id)[0]
    links.delete_link(noop_row.id)
    session.commit()
    before2 = _snapshot(session)
    report2 = _apply(plan2, session)
    assert report2.status == "refused_stale_plan"
    assert "row_deleted" in {r.reason_code for r in report2.stale_reasons}
    assert _snapshot(session) == before2


def test_t26_key_changed_incl_to_new_key(session, items, links, rebuild_setup):
    a, b, c, r1, r2, r3 = rebuild_setup
    plan = _plan_ready(links, session, 2)
    # 改成任意其它键。
    session.execute(
        text("UPDATE knowledge_link SET normalized_link_key = 'other\x1f' WHERE id = :id"),
        {"id": str(r1.id)},
    )
    session.commit()
    before = _snapshot(session)
    identity = _identity(links, a)
    report = _apply(plan, session)
    _assert_refusal(report, session, before, identity, links, a, "refused_stale_plan", ("key_changed",))
    # 恢复后改成恰好等于计划 new_key → 仍拒绝（old_key 快照不符）。
    session.execute(
        text("UPDATE knowledge_link SET normalized_link_key = :k WHERE id = :id"),
        {"k": r1.normalized_link_key, "id": str(r1.id)},
    )
    session.commit()
    plan = _plan_ready(links, session, 2)
    new_key = next(u.new_key for u in plan.updates if u.link_id == r1.id)
    session.execute(
        text("UPDATE knowledge_link SET normalized_link_key = :k WHERE id = :id"),
        {"k": new_key, "id": str(r1.id)},
    )
    session.commit()
    before = _snapshot(session)
    report = _apply(plan, session)
    _assert_refusal(report, session, before, identity, links, a, "refused_stale_plan", ("key_changed",))


def test_t27_version_drift_precedence_and_unsupported(session, items, links, rebuild_setup):
    a, b, c, r1, r2, r3 = rebuild_setup
    plan = _plan_ready(links, session, 2)
    # 改某行版本 → 门禁 A 先拒（优先级 A→B→C）。
    session.execute(
        text("UPDATE knowledge_link SET link_normalization_version = 3 WHERE id = :id"),
        {"id": str(r1.id)},
    )
    session.commit()
    before = _snapshot(session)
    identity = _identity(links, a)
    report = _apply(plan, session)
    _assert_refusal(report, session, before, identity, links, a, "refused_version_drift")
    # 全部行统一改成另一单一值 N'（集合仍同构但 ≠ source_version）→ A 拒。
    session.execute(text("UPDATE knowledge_link SET link_normalization_version = 1"))
    session.commit()
    session.execute(text("UPDATE knowledge_link SET link_normalization_version = 7"))
    session.commit()
    before = _snapshot(session)
    report = _apply(plan, session)
    _assert_refusal(report, session, before, identity, links, a, "refused_version_drift")
    session.execute(text("UPDATE knowledge_link SET link_normalization_version = 1"))
    session.commit()
    # 计划 target_version 不在注册表 → unsupported_target_version（零写入，不开事务）。
    plan = _plan_ready(links, session, 2)
    before = _snapshot(session)
    tampered = plan.model_copy(update={"target_version": 99})
    report = _apply(tampered, session)
    _assert_refusal(report, session, before, identity, links, a, "refused_stale_plan", ("unsupported_target_version",))


def test_t28_incomplete_coverage_three_constructions(session, items, links, rebuild_setup):
    a, b, c, r1, r2, r3 = rebuild_setup
    plan = _plan_ready(links, session, 2)
    before = _snapshot(session)
    identity = _identity(links, a)
    # ① row_snapshots 缺行（observed_row_count 与快照数不符）→ B 拒绝。
    missing_snap = plan.model_copy(update={"row_snapshots": plan.row_snapshots[1:]})
    report = _apply(missing_snap, session)
    _assert_refusal(report, session, before, identity, links, a, "refused_incomplete_plan", ("incomplete_coverage",))
    # ② updates 未覆盖全部快照行 → B 拒绝。
    missing_upd = plan.model_copy(update={"updates": plan.updates[1:]})
    report = _apply(missing_upd, session)
    _assert_refusal(report, session, before, identity, links, a, "refused_incomplete_plan", ("incomplete_coverage",))
    # ③ updates 含快照外 link_id → B 放行（快照⊆updates 仍成立）、C 拒绝。
    # ghost 的 new_key 一并改掉，避免与 updates[0] 构成 (source_id,new_key)
    # 重复而先触发 B 的 duplicate_new_key_in_plan（那属于 T29 对照情形）。
    u0 = plan.updates[0]
    ghost = u0.model_copy(update={"link_id": uuid4(), "new_key": u0.new_key + "x"})
    ghost_plan = plan.model_copy(update={"updates": plan.updates + (ghost,)})
    report = _apply(ghost_plan, session)
    _assert_refusal(report, session, before, identity, links, a, "refused_stale_plan", ("update_row_not_in_plan",))
    # observed_row_count 与当前行数不符也被 C 发现（篡改计数）。
    count_tampered = plan.model_copy(update={"observed_row_count": 99, "row_snapshots": plan.row_snapshots})
    # 注意：observed_row_count=99 ≠ len(snapshots)=3 → B 先拒（内部一致性）。
    report = _apply(count_tampered, session)
    assert report.status == "refused_incomplete_plan"
    assert _snapshot(session) == before


def test_t29_duplicate_link_id_belongs_to_c(session, items, links, rebuild_setup):
    a, b, c, r1, r2, r3 = rebuild_setup
    plan = _plan_ready(links, session, 2)
    before = _snapshot(session)
    identity = _identity(links, a)
    # ① row_snapshots 重复 link_id → C（同步 bump count，避免 B 内部一致性先拒）。
    dup_snap = plan.model_copy(
        update={
            "row_snapshots": plan.row_snapshots + (plan.row_snapshots[0],),
            "observed_row_count": len(plan.row_snapshots) + 1,
        }
    )
    report = _apply(dup_snap, session)
    _assert_refusal(report, session, before, identity, links, a, "refused_stale_plan", ("duplicate_link_id_in_plan",))
    # ② updates 重复 link_id（即使 new_key 相同）→ C（不归 B）。
    dup_upd = plan.model_copy(update={"updates": plan.updates + (plan.updates[0],)})
    report = _apply(dup_upd, session)
    _assert_refusal(report, session, before, identity, links, a, "refused_stale_plan", ("duplicate_link_id_in_plan",))
    # 对照：不同 link_id 的 (source_id,new_key) 重复 → B（两类不混淆）。
    u0, u1 = plan.updates[0], plan.updates[1]
    pair_dup = u1.model_copy(update={"source_id": u0.source_id, "new_key": u0.new_key})
    pair_plan = plan.model_copy(update={"updates": (u0, pair_dup) + plan.updates[2:]})
    report = _apply(pair_plan, session)
    assert report.status == "refused_incomplete_plan"
    assert "duplicate_new_key_in_plan" in {r.reason_code for r in report.stale_reasons}
    assert _snapshot(session) == before


@pytest.mark.parametrize(
    "mutation",
    ["title", "alias", "row_added", "row_deleted", "key", "version", "snap_missing", "upd_missing", "ghost_upd", "dup_snap", "dup_upd"],
)
def test_t30_strongest_zero_write_matrix(session, items, links, rebuild_setup, mutation):
    """T30：T22–T29 每一种拒绝情形 → 全表逐列 + 条目全列 + 三 Hash + 导出字节 + 行数不变。"""
    a, b, c, r1, r2, r3 = rebuild_setup
    plan = _plan_ready(links, session, 2)
    if mutation == "title":
        links.update_link(r1.model_copy(update={"target_title": "T", "updated_at": utcnow()}))
    elif mutation == "alias":
        links.update_link(r1.model_copy(update={"alias": "Z", "updated_at": utcnow()}))
    elif mutation == "row_added":
        _raw_insert_link(session, c.id, normalized_link_key("Added", None), version=1, title="Added")
    elif mutation == "row_deleted":
        links.delete_link(r1.id)
    elif mutation == "key":
        session.execute(
            text("UPDATE knowledge_link SET normalized_link_key = 'zzz\x1f' WHERE id = :id"),
            {"id": str(r1.id)},
        )
    elif mutation == "version":
        session.execute(
            text("UPDATE knowledge_link SET link_normalization_version = 9 WHERE id = :id"),
            {"id": str(r1.id)},
        )
    elif mutation == "snap_missing":
        plan = plan.model_copy(update={"row_snapshots": plan.row_snapshots[1:]})
    elif mutation == "upd_missing":
        plan = plan.model_copy(update={"updates": plan.updates[1:]})
    elif mutation == "ghost_upd":
        ghost = plan.updates[0].model_copy(update={"link_id": uuid4()})
        plan = plan.model_copy(update={"updates": plan.updates + (ghost,)})
    elif mutation == "dup_snap":
        plan = plan.model_copy(
            update={
                "row_snapshots": plan.row_snapshots + (plan.row_snapshots[0],),
                "observed_row_count": len(plan.row_snapshots) + 1,
            }
        )
    elif mutation == "dup_upd":
        plan = plan.model_copy(update={"updates": plan.updates + (plan.updates[0],)})
    session.commit()
    before = _snapshot(session)
    identity = _identity(links, a)
    report = _apply(plan, session)
    assert report.status in ("refused_stale_plan", "refused_incomplete_plan", "refused_version_drift")
    _assert_refusal(report, session, before, identity, links, a, report.status)


# --- T32/T33/T34 事务生命周期与无缓存预检 ---


def test_t32_commit_then_external_change(engine, session, items, links):
    a = _mk_item(items, session, "A")
    b = _mk_item(items, session, "B")
    counter = _QueryCounter(engine)
    links.save_link(_mk_link(a, "B", target=b))  # T1 受守卫写入
    session.commit()
    n1 = counter.count("distinct")
    assert n1 == 1
    # 另一连接把全表改成异版本并提交。
    with engine.connect() as conn:
        conn.execute(text("UPDATE knowledge_link SET link_normalization_version = 99"))
        conn.commit()
    before = _snapshot(session)
    identity = _identity(links, a)
    same_session = session
    with pytest.raises(LinkNormalizationVersionMismatch):
        links.save_link(_mk_link(a, "C"))  # autobegin T2
    assert session is same_session  # ③ Session 自始至终同一个
    assert counter.count("distinct") == n1 + 1  # ① 确实重新 DISTINCT
    _assert_write_refused(session, before, identity, links, a)  # ② 零写入
    counter.stop()


def test_t33_rollback_then_reprecheck(engine, session, items, links, v2):
    a = _mk_item(items, session, "A")
    b = _mk_item(items, session, "B")
    counter = _QueryCounter(engine)
    # 「rollback 撤销了 T1 自己的写入」：T1 插入 v2 行后 rollback。
    link = _mk_link(a, "B", target=b)
    assert link.link_normalization_version == 2
    links.save_link(link)
    session.rollback()
    assert links.get_link(link.id) is None
    # 外部提交 v1 行 → T2 预检读到 {1} ≠ 常量 2 → 拒绝。
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO knowledge_link (id, source_item_id, target_item_id, target_title,"
                " alias, normalized_link_key, link_normalization_version, resolution,"
                " cross_space, created_at, updated_at)"
                " VALUES (:id, :src, NULL, 'Ext', NULL, :key, 1, 'missing', FALSE, :now, :now)"
            ),
            {"id": str(uuid4()), "src": str(a.id), "key": normalized_link_key("Ext", None), "now": utcnow().isoformat()},
        )
        conn.commit()
    before = _snapshot(session)
    n = counter.count("distinct")
    with pytest.raises(LinkNormalizationVersionMismatch):
        links.save_link(_mk_link(a, "C"))
    assert counter.count("distinct") == n + 1  # 重新预检，不含被撤销的行
    session.rollback()
    assert _snapshot(session) == before
    counter.stop()


def test_t33_rollback_no_external_change_passes(engine, session, items, links):
    """该通则通：rollback 后无外部变化 → 重新预检放行。"""
    a = _mk_item(items, session, "A")
    counter = _QueryCounter(engine)
    links.save_link(_mk_link(a, "B"))
    session.rollback()
    links.save_link(_mk_link(a, "B"))
    session.commit()
    assert counter.count("distinct") == 2
    assert len(links.list_links(a.id)) == 1
    counter.stop()


@pytest.mark.parametrize("k", [1, 5, 20])
def test_t34_no_cache_k_writes(engine, session, items, links, k):
    a = _mk_item(items, session, "A")
    counter = _QueryCounter(engine)
    for i in range(k):
        links.save_link(_mk_link(a, f"T{i}"))
    session.commit()
    assert counter.count("distinct") == k  # 同一事务内 k 次写入 = k 次预检
    counter.stop()


def test_t34_exempt_zero_precheck(engine, session, items, links):
    a = _mk_item(items, session, "A")
    row = links.save_link(_mk_link(a, "B"))  # missing 行
    session.commit()
    counter = _QueryCounter(engine)
    # 治理列-only 更新（键/版本不变）→ 豁免。
    links.update_link(row.model_copy(update={"resolution": LinkResolution.AMBIGUOUS, "updated_at": utcnow()}))
    # 删除 → 豁免。
    links.delete_link(row.id)
    session.commit()
    assert counter.count("distinct") == 0
    counter.stop()


def test_t34_apply_counts_and_structure(engine, session, items, links, rebuild_setup):
    a, b, c, r1, r2, r3 = rebuild_setup
    plan = _plan_ready(links, session, 2)
    counter = _QueryCounter(engine)
    start = len(counter.events)
    report = _apply(plan, session)
    window = counter.events[start:]
    assert report.status == "rebuilt"
    assert window.count("distinct") == 2  # 门禁 A 1 次 + 写后复核 1 次（不逐行预检）
    assert window.count("sixcol") == 1  # 1 次 6 列重读
    assert window.count("update") == len(plan.updates)
    assert window.count("gov") == 2  # 写前/写后治理基线
    assert window.count("items") == 2  # 写前/写后条目基线
    assert window.count("pairs") == 1  # 写后键对复核
    # ④ 仓库实例无任何版本集合缓存属性（结构守护）。
    assert set(vars(links)) == {"_session"}
    counter.stop()


# --- T35–T37 配套 ---


def test_t35_source_id_changed(session, items, links, rebuild_setup):
    a, b, c, r1, r2, r3 = rebuild_setup
    plan = _plan_ready(links, session, 2)
    # 把 r1 的 source 改成 c（版本集合不变 ⇒ A 通过）。
    session.execute(
        text("UPDATE knowledge_link SET source_item_id = :src WHERE id = :id"),
        {"src": str(c.id), "id": str(r1.id)},
    )
    session.commit()
    before = _snapshot(session)
    identity_a = _identity(links, a)
    identity_b = _identity(links, b)
    report = _apply(plan, session)
    _assert_refusal(report, session, before, identity_a, links, a, "refused_stale_plan", ("source_id_changed",))
    reason = next(r for r in report.stale_reasons if r.reason_code == "source_id_changed")
    assert reason.link_id == r1.id
    assert reason.expected == str(a.id)
    assert reason.actual == str(c.id)
    # 两个 source 的条目全列不变（含在 _snapshot 内）；b 的交换身份亦不变。
    assert _identity(links, b) == identity_b


def test_t36_tamper_matrix(session, items, links, rebuild_setup):
    a, b, c, r1, r2, r3 = rebuild_setup
    plan = _plan_ready(links, session, 2)
    before = _snapshot(session)
    identity = _identity(links, a)
    # ① 改 new_key 为任意其它字符串 → 每行新键重算发现。
    tampered = plan.updates[0].model_copy(update={"new_key": "tampered\x1f"})
    p1 = plan.model_copy(update={"updates": (tampered,) + plan.updates[1:]})
    report = _apply(p1, session)
    _assert_refusal(report, session, before, identity, links, a, "refused_stale_plan", ("new_key_mismatch",))
    # ② new_version 改为注册表存在但非目标（1）→ new_version_mismatch。
    bad_ver = plan.updates[0].model_copy(update={"new_version": 1})
    p2 = plan.model_copy(update={"updates": (bad_ver,) + plan.updates[1:]})
    report = _apply(p2, session)
    _assert_refusal(report, session, before, identity, links, a, "refused_stale_plan", ("new_version_mismatch",))
    # ③ 目标版本不在注册表 → unsupported_target_version。
    p3 = plan.model_copy(update={"target_version": 99})
    report = _apply(p3, session)
    _assert_refusal(report, session, before, identity, links, a, "refused_stale_plan", ("unsupported_target_version",))
    # ④ 交换两条 update 的 new_key（集合相同、逐行不同）→ 仍拒绝。
    u0, u1 = plan.updates[0], plan.updates[1]
    swapped = (
        u0.model_copy(update={"new_key": u1.new_key}),
        u1.model_copy(update={"new_key": u0.new_key}),
    ) + plan.updates[2:]
    p4 = plan.model_copy(update={"updates": swapped})
    report = _apply(p4, session)
    _assert_refusal(report, session, before, identity, links, a, "refused_stale_plan", ("new_key_mismatch",))
    # ⑤ 篡改 status → plan_not_ready。
    p5 = plan.model_copy(update={"status": "refused_collision"})
    report = _apply(p5, session)
    _assert_refusal(report, session, before, identity, links, a, "refused_stale_plan", ("plan_not_ready",))


def test_t37_noop_blindspot_and_no_false_refusal(session, items, links, monkeypatch):
    a = _mk_item(items, session, "A")
    b = _mk_item(items, session, "B")
    row = links.save_link(_mk_link(a, "B", alias="x", target=b))
    session.commit()
    monkeypatch.setitem(LINK_KEY_RULES, 2, _v2_key)
    monkeypatch.setattr(entities, "LINK_NORMALIZATION_VERSION", 2)
    # 先重建到 v2，得到全 no-op 的同版本计划。
    assert _apply(_plan_ready(links, session, 2), session).status == "rebuilt"
    row = links.get_link(row.id)  # 重取：拿到 v2 版本/键，避免把旧实体版本写回
    plan = _plan_ready(links, session, 2)
    assert plan.source_version == 2 and plan.updates == ()
    # ①② 「只比 updates」会放行（updates 为空）；R3.1 对 no-op 行也重算 → 拒绝。
    links.update_link(row.model_copy(update={"alias": "y", "updated_at": utcnow()}))
    session.commit()
    before = _snapshot(session)
    identity = _identity(links, a)
    report = _apply(plan, session)
    _assert_refusal(report, session, before, identity, links, a, "refused_stale_plan", ("noop_row_requires_update", "alias_changed"))
    # ④ 正常 no-op 行不误拒（幂等重跑 updated=0）。
    links.update_link(row.model_copy(update={"alias": "x", "updated_at": utcnow()}))
    session.commit()
    plan = _plan_ready(links, session, 2)
    report = _apply(plan, session)
    assert report.status == "rebuilt"
    assert report.updated == 0 and report.unchanged == 1


# --- T39 十步顺序 / 写后复核 / 故障注入 / 事务所有权 ---


def test_t39_order_guard_success(engine, session, items, links, rebuild_setup):
    a, b, c, r1, r2, r3 = rebuild_setup
    plan = _plan_ready(links, session, 2)
    counter = _QueryCounter(engine)
    start = len(counter.events)
    report = _apply(plan, session)
    assert report.status == "rebuilt"
    seq = [e for e in counter.events[start:] if e != "other"]
    n = len(plan.updates)
    expected = (
        ["distinct", "sixcol", "gov", "items"]
        + ["update"] * n
        + ["distinct", "pairs", "gov", "items"]
    )
    assert seq == expected  # 开事务 → A → 6 列重读 → 基线 → B/C → 批量写 → 写后复核 → 提交
    counter.stop()


@pytest.mark.parametrize("gate", ["a", "b", "c"])
def test_t39_no_update_after_gate_failure(engine, session, items, links, rebuild_setup, gate):
    a, b, c, r1, r2, r3 = rebuild_setup
    plan = _plan_ready(links, session, 2)
    if gate == "a":
        session.execute(
            text("UPDATE knowledge_link SET link_normalization_version = 9 WHERE id = :id"),
            {"id": str(r1.id)},
        )
        session.commit()
    elif gate == "b":
        plan = plan.model_copy(update={"updates": plan.updates[1:]})
    else:
        links.update_link(r1.model_copy(update={"target_title": "Drift", "updated_at": utcnow()}))
        session.commit()
    counter = _QueryCounter(engine)
    start = len(counter.events)
    report = _apply(plan, session)
    assert report.status != "rebuilt"
    seq = [e for e in counter.events[start:] if e != "other"]
    assert "update" not in seq  # 任一门禁失败后不得出现任何 UPDATE
    if gate == "a":
        assert seq == ["distinct"]  # A 失败：其后步骤一律不执行
    else:
        assert seq == ["distinct", "sixcol", "gov", "items"]
    counter.stop()


def test_t39_post_write_governance_and_items(engine, session, items, links, rebuild_setup):
    a, b, c, r1, r2, r3 = rebuild_setup
    before = _snapshot(session)
    identity_a = _identity(links, a)
    identity_b = _identity(links, b)
    plan = _plan_ready(links, session, 2)
    # apply 事务内第 3 步重读值 == 此刻数据库值（无并发治理变更）。
    report = _apply(plan, session)
    assert report.status == "rebuilt"
    after = _snapshot(session)
    for old, new in zip(before["links"], after["links"], strict=True):
        for col in ("target_item_id", "target_title", "alias", "resolution", "cross_space", "created_at"):
            assert new[col] == old[col]
    assert after["items"] == before["items"]
    assert _identity(links, a) == identity_a
    assert _identity(links, b) == identity_b
    # 全部 updated 行共享同一 updated_at（单时间戳批量写）。
    stamps = {r["updated_at"] for r in after["links"]}
    assert len(stamps) == 1


@pytest.mark.parametrize("fail_at", [1, 2, 3])
def test_t39_fault_injection_runtime_error(engine, session, items, links, rebuild_setup, fail_at):
    a, b, c, r1, r2, r3 = rebuild_setup
    plan = _plan_ready(links, session, 2)
    assert len(plan.updates) == 3
    before = _snapshot(session)
    identity = _identity(links, a)
    state = {"n": 0}

    def fault(conn, cursor, statement, parameters, context, executemany):
        if statement.upper().startswith("UPDATE KNOWLEDGE_LINK"):
            state["n"] += 1
            if state["n"] == fail_at:
                raise RuntimeError("注入故障")

    event.listen(engine, "before_cursor_execute", fault)
    try:
        with pytest.raises(RuntimeError, match="注入故障"):
            _apply(plan, session)
    finally:
        event.remove(engine, "before_cursor_execute", fault)
    # 整体回滚：全表逐列与 apply 前完全一致，无「半套新键」残留。
    assert _snapshot(session) == before
    assert _identity(links, a) == identity


def test_t39_fault_injection_integrity_error(engine, session, items, links, rebuild_setup):
    """故意触发真实 IntegrityError（第 2 行 UPDATE 前注入冲突行）→ 整体回滚。"""
    a, b, c, r1, r2, r3 = rebuild_setup
    plan = _plan_ready(links, session, 2)
    u2 = plan.updates[1]
    before = _snapshot(session)
    state = {"done": False}

    def fault(conn, cursor, statement, parameters, context, executemany):
        if statement.upper().startswith("UPDATE KNOWLEDGE_LINK") and not state["done"]:
            state["done"] = True
            conn.execute(
                text(
                    "INSERT INTO knowledge_link (id, source_item_id, target_item_id, target_title,"
                    " alias, normalized_link_key, link_normalization_version, resolution,"
                    " cross_space, created_at, updated_at)"
                    " VALUES (:id, :src, NULL, 'Inject', NULL, :key, :ver, 'missing', FALSE, :now, :now)"
                ),
                {
                    "id": str(uuid4()),
                    "src": str(u2.source_id),
                    "key": u2.new_key,
                    "ver": u2.new_version,
                    "now": utcnow().isoformat(),
                },
            )

    event.listen(engine, "before_cursor_execute", fault)
    try:
        with pytest.raises(IntegrityError):
            _apply(plan, session)
    finally:
        event.remove(engine, "before_cursor_execute", fault)
    assert _snapshot(session) == before  # 注入行也随事务回滚消失


def test_t39_transaction_ownership(session, items, links, rebuild_setup):
    a, b, c, r1, r2, r3 = rebuild_setup
    plan = _plan_ready(links, session, 2)
    before = _snapshot(session)
    session.commit()  # 释放快照读事务，begin() 才能独占
    # 已有活动事务 → InvalidRequestError，零写入，不静默加入外部事务。
    with session.begin(), pytest.raises(InvalidRequestError):
        apply_link_key_plan(plan, session)
    assert _snapshot(session) == before
    session.commit()  # 释放快照读事务，下一个 begin() 才能独占
    # savepoint 内同样拒绝。
    with session.begin(), session.begin_nested(), pytest.raises(InvalidRequestError):
        apply_link_key_plan(plan, session)
    assert _snapshot(session) == before
    # 干净 Session 上正常成功（对照）。
    assert _apply(plan, session).status == "rebuilt"


# --- T40 savepoint / nested 边界 ---


def test_t40_nested_precheck_lifecycle(engine, session, items, links):
    a = _mk_item(items, session, "A")
    b = _mk_item(items, session, "B")
    counter = _QueryCounter(engine)
    # ① begin_nested 内受守卫写入 → 照常重新预检。
    with session.begin():
        with session.begin_nested():
            links.save_link(_mk_link(a, "B", target=b))
        assert counter.count("distinct") == 1
        # ② savepoint 内插入异版本行后 rollback → 下一次预检读到回滚后的真实集合。
        nested = session.begin_nested()
        _raw_insert_link(session, a.id, normalized_link_key("Foreign", None), version=99, title="Foreign")
        nested.rollback()
        links.save_link(_mk_link(a, "C"))  # 集合仍 {1} → 放行
        assert counter.count("distinct") == 2
        # ③ nested.commit()（RELEASE SAVEPOINT）不结束外层事务。
        nested2 = session.begin_nested()
        links.save_link(_mk_link(a, "D"))
        nested2.commit()
        assert session.in_transaction()  # 外层仍活动
        assert session.get_transaction() is not None
        links.save_link(_mk_link(a, "E"))  # 外层后续写入仍重新预检
        assert counter.count("distinct") == 4
    session.commit()
    assert len(links.list_links(a.id)) == 4
    counter.stop()


def test_t40_repo_source_guard():
    """⑤ 仓库不主动 commit/rollback/begin_nested；apply 恰好一个 session.begin()（AST 守护）。"""
    source = inspect.getsource(links_module)
    tree = ast.parse(source)
    forbidden = {"commit", "rollback", "begin_nested"}
    begin_calls = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in forbidden, f"仓库/apply 不得调用 {node.func.attr}()"
            if node.func.attr == "begin" and isinstance(node.func.value, ast.Name) and node.func.value.id == "session":
                begin_calls += 1
    assert begin_calls == 1  # 只有 apply 的独占事务边界


# --- 报告落盘 + 空表 apply ---


def test_persist_rebuild_report_roundtrip(session, items, links, rebuild_setup, tmp_path):
    a, b, c, r1, r2, r3 = rebuild_setup
    plan = _plan_ready(links, session, 2)
    report = _apply(plan, session)
    path = persist_rebuild_report(report, tmp_path / "ops")
    assert path.parent == tmp_path / "ops"
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded == report.model_dump(mode="json")
    # 拒绝报告同样可落盘往返。
    refusal = _apply(plan.model_copy(update={"status": "refused_collision"}), session)
    path2 = persist_rebuild_report(refusal, tmp_path / "ops")
    assert json.loads(path2.read_text(encoding="utf-8")) == refusal.model_dump(mode="json")
    assert path2 != path


def test_apply_empty_table_plan(session, items, links):
    _mk_item(items, session, "A")
    plan = LinkKeyRebuild(links).plan(1)
    session.commit()
    assert plan.status == "ready"
    assert plan.observed_row_count == 0
    report = _apply(plan, session)
    assert report.status == "rebuilt"
    assert report.updated == 0 and report.unchanged == 0