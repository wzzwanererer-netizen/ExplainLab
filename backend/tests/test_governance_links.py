"""K1 治理链接维护测试（A1-03 审核批准路径缺口整改，默认 SQLite）。

governance.py 三处应用点（approve_review / submit_review 草稿直改 / restore_version）
× 四动作（UPDATE_ITEM / DELETE_ITEM / MERGE_DUPLICATE / RESTORE_VERSION）的链接维护：

- DELETE：批准 / 草稿直删在删除前同事务降级入链为 missing。
  **写侧原始列断言**（独立连接读同一 SQLite 文件的 resolution/target_item_id），
  区别于读取侧 D12 防御映射（NULL+resolved 仅在读取时映射 missing，写侧列仍是 resolved）。
- UPDATE / RESTORE：批准 / 草稿直改应用后、commit 前同步出链（新增字面建行解析、移除字面删行）。
- MERGE：归档源（非删除），入链绑定保留、不降级；源正文不变，无出链同步。
- 409：治理同步遇版本异写 → link_version_mismatch 稳定码，整请求零写入
  （审核单仍 pending、条目正文与链接不变）。

挂接位于路由层（option A，Core ReviewService 零改动）；本文件以真实 TestClient
调用治理端点验证，不 mock 应用动作。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import Settings
from app.db.session import create_engine_from_url
from knowledge_core.markdown.links import normalized_link_key


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


def _raw_links(settings: Settings, source_id: str) -> list[dict]:
    """独立连接读取链接行原始治理列（写侧权威，非读取侧 D12 映射）。"""
    engine = create_engine_from_url(settings.database_url)
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


def _inject_version_row(settings: Settings, source_id: str, version: int = 99) -> None:
    """直连同一 SQLite 文件注入异版本链接行（构造全局版本窗口）。"""
    engine = create_engine_from_url(settings.database_url)
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


def test_approve_update_syncs_new_links(client: TestClient):
    """active 条目编辑经审核批准应用后，出链同步：新增 [[U]] 建行并解析。"""
    t = _create(client, "T", "目标")
    s = _create(client, "S", "参见 [[T]]")
    _publish(client, s["id"])
    assert {r["target_title"] for r in _links(client, s["id"])} == {"T"}

    resp = client.patch(f"/api/knowledge/{s['id']}", json={"content": "参见 [[T]] [[U]]"})
    assert resp.status_code == 202  # active 重要变更仅生成审核单
    rid = _review_id(resp)
    # 未批准前变更未应用：不得产生 U 链接
    assert {r["target_title"] for r in _links(client, s["id"])} == {"T"}

    u = _create(client, "U", "另一目标")
    assert client.post(f"/api/reviews/{rid}/approve", json={}).status_code == 200

    rows = {r["target_title"]: r for r in _links(client, s["id"])}
    assert set(rows) == {"T", "U"}
    assert rows["T"]["target_id"] == t["id"] and rows["T"]["resolution"] == "resolved"
    assert rows["U"]["target_id"] == u["id"] and rows["U"]["resolution"] == "resolved"


def test_submit_draft_update_syncs_links(client: TestClient):
    """submit_review 草稿直改（非重要变更直接应用）后出链同步。"""
    t = _create(client, "T", "目标")
    s = _create(client, "S", "参见 [[T]]")  # 草稿
    u = _create(client, "U", "另一目标")
    resp = client.post(
        "/api/reviews",
        json={
            "item_id": s["id"],
            "action": "update_item",
            "payload": {"content": "参见 [[T]] [[U]]"},
        },
    )
    assert resp.status_code == 200  # 草稿直接应用（review 为 None → 200）
    assert resp.json()["applied"] is True
    rows = {r["target_title"]: r for r in _links(client, s["id"])}
    assert set(rows) == {"T", "U"}
    assert rows["T"]["target_id"] == t["id"] and rows["T"]["resolution"] == "resolved"
    assert rows["U"]["target_id"] == u["id"] and rows["U"]["resolution"] == "resolved"


# ---------------------------------------------------------------- DELETE（写侧降级）


def test_approve_delete_demotes_backlinks_write_side(client: TestClient, settings: Settings):
    """active 目标删除经批准后，入链在写侧降级 missing（原始列断言，非仅 D12 读取映射）。"""
    t = _create(client, "T", "目标")
    _publish(client, t["id"])
    s = _create(client, "S", "参见 [[T|别名]]")
    bound = _links(client, s["id"])[0]
    assert bound["resolution"] == "resolved" and bound["target_id"] == t["id"]

    resp = client.delete(f"/api/knowledge/{t['id']}")
    assert resp.status_code == 202  # active 删除走审核
    rid = _review_id(resp)
    # 批准前绑定保留
    assert _links(client, s["id"])[0]["target_id"] == t["id"]

    assert client.post(f"/api/reviews/{rid}/approve", json={}).status_code == 200
    assert client.get(f"/api/knowledge/{t['id']}").status_code == 404  # 目标已删除

    # 写侧原始列：resolution=missing、target NULL、cross_space=False、字面留存
    raw = _raw_links(settings, s["id"])
    assert len(raw) == 1
    assert raw[0]["resolution"] == "missing"
    assert raw[0]["target_item_id"] is None
    assert not raw[0]["cross_space"]
    assert raw[0]["target_title"] == "T" and raw[0]["alias"] == "别名"
    # 读取侧一致
    http = _links(client, s["id"])[0]
    assert http["resolution"] == "missing" and http["target_id"] is None


def test_submit_draft_delete_demotes_backlinks_write_side(client: TestClient, settings: Settings):
    """submit_review 草稿目标直删（直接应用）前同事务降级入链（写侧列断言）。"""
    t = _create(client, "T", "目标")  # 草稿
    s = _create(client, "S", "参见 [[T]]")
    assert _links(client, s["id"])[0]["target_id"] == t["id"]

    resp = client.post(
        "/api/reviews", json={"item_id": t["id"], "action": "delete_item"}
    )
    assert resp.status_code == 200  # 草稿直删直接应用 → 200
    assert resp.json()["applied"] is True
    assert client.get(f"/api/knowledge/{t['id']}").status_code == 404

    raw = _raw_links(settings, s["id"])
    assert len(raw) == 1
    assert raw[0]["resolution"] == "missing"
    assert raw[0]["target_item_id"] is None
    assert not raw[0]["cross_space"]
    assert raw[0]["target_title"] == "T"


# ---------------------------------------------------------------- RESTORE


def test_restore_draft_syncs_links_removes_stale(client: TestClient):
    """草稿回滚直接应用后出链同步：回到旧正文，移除不再引用的 [[U]] 行。"""
    t = _create(client, "T", "目标")
    s = _create(client, "S", "参见 [[T]]")  # 草稿，version 1 快照 = 参见 [[T]]
    u = _create(client, "U", "另一目标")
    # 草稿编辑加入 [[U]]（直接应用并同步）
    assert (
        client.patch(f"/api/knowledge/{s['id']}", json={"content": "参见 [[T]] [[U]]"}).status_code
        == 200
    )
    assert {r["target_title"] for r in _links(client, s["id"])} == {"T", "U"}

    resp = client.post(f"/api/knowledge/{s['id']}/versions/1/restore")
    assert resp.status_code == 200  # 草稿回滚直接应用
    assert resp.json()["content"] == "参见 [[T]]"
    rows = {r["target_title"]: r for r in _links(client, s["id"])}
    assert set(rows) == {"T"}  # U 行随正文回滚被同步移除
    assert rows["T"]["target_id"] == t["id"] and rows["T"]["resolution"] == "resolved"
    assert u["id"]  # U 条目本身仍存在（仅链接行移除）


def test_approve_restore_active_syncs_links(client: TestClient):
    """active 回滚经批准应用后出链同步。"""
    t = _create(client, "T", "目标")
    s = _create(client, "S", "参见 [[T]]")
    _publish(client, s["id"])
    u = _create(client, "U", "另一目标")
    # active 编辑 → 审核批准，使正文含 [[U]]
    rid = _review_id(
        client.patch(f"/api/knowledge/{s['id']}", json={"content": "参见 [[T]] [[U]]"})
    )
    assert client.post(f"/api/reviews/{rid}/approve", json={}).status_code == 200
    first = {r["target_title"]: r for r in _links(client, s["id"])}
    assert set(first) == {"T", "U"}
    assert first["U"]["target_id"] == u["id"]

    # active 回滚到 version 1（参见 [[T]]）→ 审核批准
    resp = client.post(f"/api/knowledge/{s['id']}/versions/1/restore")
    assert resp.status_code == 202
    rid2 = _review_id(resp)
    assert client.post(f"/api/reviews/{rid2}/approve", json={}).status_code == 200
    rows = {r["target_title"]: r for r in _links(client, s["id"])}
    assert set(rows) == {"T"}  # 批准后同步移除 U
    assert rows["T"]["target_id"] == t["id"]


# ---------------------------------------------------------------- MERGE（不降级）


def test_approve_merge_keeps_bindings_no_demote(client: TestClient, settings: Settings):
    """MERGE 归档审核源条目（非删除）：源出链与指向源的反链绑定均保留，不降级。

    _apply_merge 归档的是审核单 item_id（源 S），合并入 payload.target_id（D）；
    归档 ≠ 删除，K1 不得降级其链接（降级仅属 DELETE）。
    """
    t = _create(client, "T", "目标")
    s = _create(client, "S", "参见 [[T]]")  # 源，出链 S→T
    r = _create(client, "R", "参见 [[S]]")  # 反链 R→S
    d = _create(client, "D", "合并目标")
    assert _links(client, s["id"])[0]["target_id"] == t["id"]
    assert _links(client, r["id"])[0]["target_id"] == s["id"]

    resp = client.post(
        "/api/reviews",
        json={
            "item_id": s["id"],
            "action": "merge_duplicate",
            "payload": {"target_id": d["id"]},
        },
    )
    assert resp.status_code == 201  # MERGE 恒重要 → pending 审核单
    rid = _review_id(resp)
    assert client.post(f"/api/reviews/{rid}/approve", json={}).status_code == 200

    # 源 S 被归档（仍存在），出链 S→T 保留（不降级）
    assert client.get(f"/api/knowledge/{s['id']}").json()["status"] == "archived"
    s_row = _links(client, s["id"])[0]
    assert s_row["target_id"] == t["id"] and s_row["resolution"] == "resolved"
    # 反链 R→S 保留（写侧列仍 resolved + 绑定，未被降级）
    raw = _raw_links(settings, r["id"])
    assert len(raw) == 1
    assert raw[0]["resolution"] == "resolved"
    assert raw[0]["target_item_id"] == s["id"]
    # 合并目标 D 存活（未归档）
    assert client.get(f"/api/knowledge/{d['id']}").json()["status"] != "archived"


# ---------------------------------------------------------------- 409 零写入


def test_approve_update_409_zero_write(client: TestClient, settings: Settings):
    """批准 active 编辑时同步遇版本异写 → 409，审核单仍 pending、正文与链接零写入。"""
    t = _create(client, "T", "目标")
    s = _create(client, "S", "参见 [[T]]")
    _publish(client, s["id"])
    rid = _review_id(
        client.patch(f"/api/knowledge/{s['id']}", json={"content": "参见 [[T]] [[U]]"})
    )
    _inject_version_row(settings, s["id"])  # 构造版本窗口

    resp = client.post(f"/api/reviews/{rid}/approve", json={})
    assert resp.status_code == 409
    assert resp.json() == {"detail": "link_version_mismatch"}  # 只回稳定码

    # 整请求零写入：审核单仍 pending、正文未变、批准动作未产生 U 链接
    # （注入的 Z 异版本行是故障夹具，独立提交，预期留存）
    pending = client.get("/api/reviews", params={"status": "pending"}).json()
    assert rid in {r["id"] for r in pending}
    assert client.get(f"/api/knowledge/{s['id']}").json()["content"] == "参见 [[T]]"
    links_now = {r["target_title"]: r for r in _links(client, s["id"])}
    assert "U" not in links_now
    assert links_now["T"]["target_id"] == t["id"]  # 既有绑定零写入保留


def test_submit_draft_update_409_zero_write(client: TestClient, settings: Settings):
    """草稿直改同步遇版本异写 → 409，正文零写入。"""
    _create(client, "T", "目标")
    s = _create(client, "S", "参见 [[T]]")
    _inject_version_row(settings, s["id"])
    resp = client.post(
        "/api/reviews",
        json={"item_id": s["id"], "action": "update_item", "payload": {"content": "新 [[T]]"}},
    )
    assert resp.status_code == 409
    assert resp.json() == {"detail": "link_version_mismatch"}
    assert client.get(f"/api/knowledge/{s['id']}").json()["content"] == "参见 [[T]]"


def test_restore_draft_409_zero_write(client: TestClient, settings: Settings):
    """草稿回滚同步遇版本异写 → 409，正文零写入。"""
    _create(client, "T", "目标")
    s = _create(client, "S", "参见 [[T]]")
    client.patch(f"/api/knowledge/{s['id']}", json={"content": "参见 [[T]] [[U]]"})
    _inject_version_row(settings, s["id"])
    resp = client.post(f"/api/knowledge/{s['id']}/versions/1/restore")
    assert resp.status_code == 409
    assert resp.json() == {"detail": "link_version_mismatch"}
    assert client.get(f"/api/knowledge/{s['id']}").json()["content"] == "参见 [[T]] [[U]]"


def test_approve_delete_not_blocked_in_version_window(client: TestClient, settings: Settings):
    """DELETE 治理列豁免：版本窗口内批准删除仍成功，入链写侧降级 missing。"""
    t = _create(client, "T", "目标")
    _publish(client, t["id"])
    s = _create(client, "S", "参见 [[T]]")
    rid = _review_id(client.delete(f"/api/knowledge/{t['id']}"))
    _inject_version_row(settings, s["id"])  # 异版本行挂在引用方 S

    assert client.post(f"/api/reviews/{rid}/approve", json={}).status_code == 200
    assert client.get(f"/api/knowledge/{t['id']}").status_code == 404
    raw = _raw_links(settings, s["id"])
    b_row = next(r for r in raw if r["target_title"] == "T")
    assert b_row["resolution"] == "missing" and b_row["target_item_id"] is None


# ---------------------------------------------------------------- 路由守护


def test_governance_router_endpoint_set_unchanged():
    """K1 仅在既有端点内挂接，不新增/改变治理端点集合。"""
    from app.api.routes.governance import router as governance_router

    pairs = {
        (method, route.path) for route in governance_router.routes for method in route.methods
    }
    assert pairs == {
        ("GET", "/reviews"),
        ("POST", "/reviews"),
        ("POST", "/reviews/{review_id}/approve"),
        ("POST", "/reviews/{review_id}/reject"),
        ("GET", "/knowledge/{item_id}/versions"),
        ("POST", "/knowledge/{item_id}/versions/{version}/restore"),
        ("GET", "/knowledge/{item_id}/relations"),
        ("POST", "/knowledge/{item_id}/relations"),
        ("DELETE", "/relations/{relation_id}"),
        ("GET", "/knowledge/{item_id}/duplicates"),
        ("POST", "/knowledge/{item_id}/analyze"),
        ("POST", "/knowledge/{item_id}/sources"),
    }
    # K1 不得新增任何链接/重建写入口
    assert not any("links" in p or "rebuild" in p for _, p in pairs)