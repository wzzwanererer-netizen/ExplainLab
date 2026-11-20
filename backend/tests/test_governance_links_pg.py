"""K1 治理链接维护 —— 真实 PostgreSQL 镜像（与 test_governance_links.py 同断言）。

经 EXPLAINLAB_PG_TEST_URL 门控：未配置时整模块跳过（默认 SQLite 套件不受影响）；
配置后连真实 PG 实例，经真实在线 Alembic 迁移建表，真实 TestClient 调用治理端点。
绝不用离线 SQL 或假数据替代，不得用 SQLite 结果冒充 PG。

写侧降级以原始数据库列断言（独立连接读同一 PG 库的 resolution/target_item_id），
区别于读取侧 D12 防御映射。覆盖 approve / submit 草稿直改 / restore 三入口 ×
UPDATE / DELETE / MERGE / RESTORE 四动作 + 409 零写入。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  确保 ORM 元数据注册
from alembic import command
from app.core.config import Settings, get_settings
from app.db.session import create_engine_from_url, dispose_db
from app.main import create_app
from knowledge_core.markdown.links import normalized_link_key

BACKEND_DIR = Path(__file__).resolve().parents[1]
PG_URL = os.environ.get("EXPLAINLAB_PG_TEST_URL")

pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason="未配置 EXPLAINLAB_PG_TEST_URL（真实 PostgreSQL 实例），跳过 K1 治理链接 PG 测试",
)


def _alembic_cfg() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


@pytest.fixture(scope="module")
def pg_engine() -> Iterator:
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


def _clean(pg_engine) -> None:
    factory = sessionmaker(bind=pg_engine, autoflush=False, expire_on_commit=False)
    with factory() as s:
        s.execute(text("DELETE FROM knowledge_item"))  # 级联清空 link/version/review/origin
        s.execute(text("DELETE FROM tag"))
        s.execute(text("DELETE FROM gc_task"))
        s.execute(text("DELETE FROM storage_lock"))
        s.execute(text("DELETE FROM tag_change_log"))
        s.commit()


@pytest.fixture
def pg_client(pg_engine) -> Iterator[TestClient]:
    _clean(pg_engine)  # 每测试隔离（保留启动初始化的默认空间）
    settings = Settings(
        database_url=PG_URL,
        model_provider=None,
        model_base_url=None,
        model_api_key=None,
        model_name=None,
        _env_file=None,
    )
    app = create_app(settings)
    with TestClient(app) as c:
        yield c
    dispose_db()


# --- 助手（与 SQLite 版同口径，仅连接来源为真实 PG）---


def _create(client: TestClient, title: str, content: str, **kw) -> dict:
    resp = client.post("/api/knowledge", json={"title": title, "content": content, **kw})
    assert resp.status_code == 201
    return resp.json()


def _publish(client: TestClient, item_id: str) -> None:
    assert client.patch(f"/api/knowledge/{item_id}", json={"status": "active"}).status_code == 200


def _links(client: TestClient, item_id: str) -> list[dict]:
    resp = client.get(f"/api/knowledge/{item_id}/links")
    assert resp.status_code == 200
    return resp.json()


def _review_id(resp) -> str:
    body = resp.json()
    return body["id"] if "id" in body else body["review"]["id"]


def _raw_links(source_id: str) -> list[dict]:
    engine = create_engine_from_url(PG_URL)  # type: ignore[arg-type]
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT resolution, target_item_id, cross_space, target_title, alias, "
                    "normalized_link_key, link_normalization_version "
                    "FROM knowledge_link WHERE source_item_id = :src"
                ),
                {"src": source_id},
            )
            .mappings()
            .all()
        )
    engine.dispose()
    return [dict(r) for r in rows]


def _inject_version_row(source_id: str, version: int = 99) -> None:
    engine = create_engine_from_url(PG_URL)  # type: ignore[arg-type]
    now = datetime.now(UTC).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO knowledge_link (id, source_item_id, target_item_id, "
                "target_title, alias, normalized_link_key, link_normalization_version, "
                "resolution, cross_space, created_at, updated_at) "
                "VALUES (:id, :src, NULL, 'Z', NULL, :key, :ver, 'missing', FALSE, :now, :now)"
            ),
            {
                "id": str(uuid4()),
                "src": source_id,
                "key": normalized_link_key("Z", None),
                "ver": version,
                "now": now,
            },
        )
    engine.dispose()


# ---------------------------------------------------------------- UPDATE


def test_approve_update_syncs_new_links(pg_client: TestClient):
    t = _create(pg_client, "T", "目标")
    s = _create(pg_client, "S", "参见 [[T]]")
    _publish(pg_client, s["id"])
    assert {r["target_title"] for r in _links(pg_client, s["id"])} == {"T"}

    resp = pg_client.patch(f"/api/knowledge/{s['id']}", json={"content": "参见 [[T]] [[U]]"})
    assert resp.status_code == 202
    rid = _review_id(resp)
    assert {r["target_title"] for r in _links(pg_client, s["id"])} == {"T"}

    u = _create(pg_client, "U", "另一目标")
    assert pg_client.post(f"/api/reviews/{rid}/approve", json={}).status_code == 200

    rows = {r["target_title"]: r for r in _links(pg_client, s["id"])}
    assert set(rows) == {"T", "U"}
    assert rows["T"]["target_id"] == t["id"] and rows["T"]["resolution"] == "resolved"
    assert rows["U"]["target_id"] == u["id"] and rows["U"]["resolution"] == "resolved"


def test_submit_draft_update_syncs_links(pg_client: TestClient):
    t = _create(pg_client, "T", "目标")
    s = _create(pg_client, "S", "参见 [[T]]")
    u = _create(pg_client, "U", "另一目标")
    resp = pg_client.post(
        "/api/reviews",
        json={
            "item_id": s["id"],
            "action": "update_item",
            "payload": {"content": "参见 [[T]] [[U]]"},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["applied"] is True
    rows = {r["target_title"]: r for r in _links(pg_client, s["id"])}
    assert set(rows) == {"T", "U"}
    assert rows["U"]["target_id"] == u["id"] and rows["U"]["resolution"] == "resolved"
    assert t["id"]


# ---------------------------------------------------------------- DELETE（写侧降级）


def test_approve_delete_demotes_backlinks_write_side(pg_client: TestClient):
    t = _create(pg_client, "T", "目标")
    _publish(pg_client, t["id"])
    s = _create(pg_client, "S", "参见 [[T|别名]]")
    bound = _links(pg_client, s["id"])[0]
    assert bound["resolution"] == "resolved" and bound["target_id"] == t["id"]

    resp = pg_client.delete(f"/api/knowledge/{t['id']}")
    assert resp.status_code == 202
    rid = _review_id(resp)
    assert _links(pg_client, s["id"])[0]["target_id"] == t["id"]

    assert pg_client.post(f"/api/reviews/{rid}/approve", json={}).status_code == 200
    assert pg_client.get(f"/api/knowledge/{t['id']}").status_code == 404

    raw = _raw_links(s["id"])
    assert len(raw) == 1
    assert raw[0]["resolution"] == "missing"
    assert raw[0]["target_item_id"] is None
    assert not raw[0]["cross_space"]
    assert raw[0]["target_title"] == "T" and raw[0]["alias"] == "别名"
    http = _links(pg_client, s["id"])[0]
    assert http["resolution"] == "missing" and http["target_id"] is None


def test_submit_draft_delete_demotes_backlinks_write_side(pg_client: TestClient):
    t = _create(pg_client, "T", "目标")
    s = _create(pg_client, "S", "参见 [[T]]")
    assert _links(pg_client, s["id"])[0]["target_id"] == t["id"]

    resp = pg_client.post(
        "/api/reviews", json={"item_id": t["id"], "action": "delete_item"}
    )
    assert resp.status_code == 200
    assert resp.json()["applied"] is True
    assert pg_client.get(f"/api/knowledge/{t['id']}").status_code == 404

    raw = _raw_links(s["id"])
    assert len(raw) == 1
    assert raw[0]["resolution"] == "missing"
    assert raw[0]["target_item_id"] is None
    assert not raw[0]["cross_space"]
    assert raw[0]["target_title"] == "T"


# ---------------------------------------------------------------- RESTORE


def test_restore_draft_syncs_links_removes_stale(pg_client: TestClient):
    t = _create(pg_client, "T", "目标")
    s = _create(pg_client, "S", "参见 [[T]]")
    u = _create(pg_client, "U", "另一目标")
    assert (
        pg_client.patch(
            f"/api/knowledge/{s['id']}", json={"content": "参见 [[T]] [[U]]"}
        ).status_code
        == 200
    )
    assert {r["target_title"] for r in _links(pg_client, s["id"])} == {"T", "U"}

    resp = pg_client.post(f"/api/knowledge/{s['id']}/versions/1/restore")
    assert resp.status_code == 200
    assert resp.json()["content"] == "参见 [[T]]"
    rows = {r["target_title"]: r for r in _links(pg_client, s["id"])}
    assert set(rows) == {"T"}
    assert rows["T"]["target_id"] == t["id"] and rows["T"]["resolution"] == "resolved"
    assert u["id"]


def test_approve_restore_active_syncs_links(pg_client: TestClient):
    t = _create(pg_client, "T", "目标")
    s = _create(pg_client, "S", "参见 [[T]]")
    _publish(pg_client, s["id"])
    _create(pg_client, "U", "另一目标")
    rid = _review_id(
        pg_client.patch(f"/api/knowledge/{s['id']}", json={"content": "参见 [[T]] [[U]]"})
    )
    assert pg_client.post(f"/api/reviews/{rid}/approve", json={}).status_code == 200
    assert {r["target_title"] for r in _links(pg_client, s["id"])} == {"T", "U"}

    resp = pg_client.post(f"/api/knowledge/{s['id']}/versions/1/restore")
    assert resp.status_code == 202
    rid2 = _review_id(resp)
    assert pg_client.post(f"/api/reviews/{rid2}/approve", json={}).status_code == 200
    assert {r["target_title"] for r in _links(pg_client, s["id"])} == {"T"}
    assert t["id"]


# ---------------------------------------------------------------- MERGE（不降级）


def test_approve_merge_keeps_bindings_no_demote(pg_client: TestClient):
    t = _create(pg_client, "T", "目标")
    s = _create(pg_client, "S", "参见 [[T]]")
    r = _create(pg_client, "R", "参见 [[S]]")
    d = _create(pg_client, "D", "合并目标")
    assert _links(pg_client, s["id"])[0]["target_id"] == t["id"]
    assert _links(pg_client, r["id"])[0]["target_id"] == s["id"]

    resp = pg_client.post(
        "/api/reviews",
        json={
            "item_id": s["id"],
            "action": "merge_duplicate",
            "payload": {"target_id": d["id"]},
        },
    )
    assert resp.status_code == 201
    rid = _review_id(resp)
    assert pg_client.post(f"/api/reviews/{rid}/approve", json={}).status_code == 200

    assert pg_client.get(f"/api/knowledge/{s['id']}").json()["status"] == "archived"
    s_row = _links(pg_client, s["id"])[0]
    assert s_row["target_id"] == t["id"] and s_row["resolution"] == "resolved"
    raw = _raw_links(r["id"])
    assert len(raw) == 1
    assert raw[0]["resolution"] == "resolved"
    assert raw[0]["target_item_id"] == s["id"]
    assert pg_client.get(f"/api/knowledge/{d['id']}").json()["status"] != "archived"


# ---------------------------------------------------------------- 409 零写入


def test_approve_update_409_zero_write(pg_client: TestClient):
    _create(pg_client, "T", "目标")
    s = _create(pg_client, "S", "参见 [[T]]")
    _publish(pg_client, s["id"])
    rid = _review_id(
        pg_client.patch(f"/api/knowledge/{s['id']}", json={"content": "参见 [[T]] [[U]]"})
    )
    _inject_version_row(s["id"])

    resp = pg_client.post(f"/api/reviews/{rid}/approve", json={})
    assert resp.status_code == 409
    assert resp.json() == {"detail": "link_version_mismatch"}

    pending = pg_client.get("/api/reviews", params={"status": "pending"}).json()
    assert rid in {r["id"] for r in pending}
    assert pg_client.get(f"/api/knowledge/{s['id']}").json()["content"] == "参见 [[T]]"
    assert "U" not in {r["target_title"] for r in _links(pg_client, s["id"])}


def test_submit_draft_update_409_zero_write(pg_client: TestClient):
    _create(pg_client, "T", "目标")
    s = _create(pg_client, "S", "参见 [[T]]")
    _inject_version_row(s["id"])
    resp = pg_client.post(
        "/api/reviews",
        json={"item_id": s["id"], "action": "update_item", "payload": {"content": "新 [[T]]"}},
    )
    assert resp.status_code == 409
    assert resp.json() == {"detail": "link_version_mismatch"}
    assert pg_client.get(f"/api/knowledge/{s['id']}").json()["content"] == "参见 [[T]]"


def test_restore_draft_409_zero_write(pg_client: TestClient):
    _create(pg_client, "T", "目标")
    s = _create(pg_client, "S", "参见 [[T]]")
    pg_client.patch(f"/api/knowledge/{s['id']}", json={"content": "参见 [[T]] [[U]]"})
    _inject_version_row(s["id"])
    resp = pg_client.post(f"/api/knowledge/{s['id']}/versions/1/restore")
    assert resp.status_code == 409
    assert resp.json() == {"detail": "link_version_mismatch"}
    assert pg_client.get(f"/api/knowledge/{s['id']}").json()["content"] == "参见 [[T]] [[U]]"


def test_approve_delete_not_blocked_in_version_window(pg_client: TestClient):
    t = _create(pg_client, "T", "目标")
    _publish(pg_client, t["id"])
    s = _create(pg_client, "S", "参见 [[T]]")
    rid = _review_id(pg_client.delete(f"/api/knowledge/{t['id']}"))
    _inject_version_row(s["id"])

    assert pg_client.post(f"/api/reviews/{rid}/approve", json={}).status_code == 200
    assert pg_client.get(f"/api/knowledge/{t['id']}").status_code == 404
    raw = _raw_links(s["id"])
    b_row = next(r for r in raw if r["target_title"] == "T")
    assert b_row["resolution"] == "missing" and b_row["target_item_id"] is None