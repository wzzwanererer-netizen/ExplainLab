"""A1-03e HTTP 挂接测试（TestClient 真实调用，默认 SQLite）。

覆盖计划 §12 A1-03e 门禁清单：
- create / draft-PATCH / DELETE / extract 后链接正确（四处挂接）；
- active PATCH 202 分支链接未变；删除目标后读取出链/反链不抛异常且 missing；
- 手工非法行 → 读取侧防御映射（D12），实体校验器未被弱化；
- H17 / L④：archived 显式绑定**夹具由仓库层建立**，真实 HTTP PATCH 验证「保留」；
- 409 link_version_mismatch 稳定码（POST / draft-PATCH / extract；零写入）；
  DELETE 版本窗口内不阻断（治理列豁免）；
- resolve-candidates：archived 带 status 标注、跨空间列出、静态路由先于动态；
- 路由守护：links router 恰为 3 个 GET；knowledge.py 端点集合不变；
  无重建/绑定 HTTP 写入口（D8 / R3.1）。

审核批准路径（governance.py）不在 A1-03 修改清单（§4.2），其链接同步缺口
如实记录于验收报告，不在此伪测为已挂接。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.api.routes.knowledge import router as knowledge_router
from app.api.routes.links import router as links_router
from app.core.config import Settings
from app.db.session import create_engine_from_url
from app.services.links import SQLAlchemyLinkRepository
from knowledge_core.domain.entities import KnowledgeLink, LinkResolution, utcnow
from knowledge_core.markdown.links import normalized_link_key


def _create(client: TestClient, title: str, content: str, **kw) -> dict:
    resp = client.post("/api/knowledge", json={"title": title, "content": content, **kw})
    assert resp.status_code == 201
    return resp.json()


def _links(client: TestClient, item_id: str) -> list[dict]:
    resp = client.get(f"/api/knowledge/{item_id}/links")
    assert resp.status_code == 200
    return resp.json()


def _backlinks(client: TestClient, item_id: str) -> list[dict]:
    resp = client.get(f"/api/knowledge/{item_id}/backlinks")
    assert resp.status_code == 200
    return resp.json()


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


def _corrupt_to_illegal_null_resolved(settings: Settings, source_id: str) -> None:
    """手工构造非法组合：target NULL + resolution=resolved（模拟外部级联脏数据）。"""
    engine = create_engine_from_url(settings.database_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE knowledge_link SET target_item_id = NULL, resolution = 'resolved' "
                "WHERE source_item_id = :src"
            ),
            {"src": source_id},
        )
    engine.dispose()


def _bind_via_repository_fixture(settings: Settings, source_id: UUID, target_id: UUID) -> None:
    """H17/L④ 夹具：显式绑定经**仓库层**建立（A1-03 无 HTTP 写入口，D8）。"""
    engine = create_engine_from_url(settings.database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        repo = SQLAlchemyLinkRepository(session)
        link = repo.list_links(source_id)[0]
        bound = link.model_copy(
            update={
                "target_id": target_id,
                "resolution": LinkResolution.RESOLVED,
                "updated_at": utcnow(),
            }
        )
        repo.update_link(bound)
        session.commit()
    engine.dispose()


# ---------------------------------------------------------------- 四处挂接


def test_create_syncs_links_and_backlinks(client: TestClient):
    b = _create(client, "B", "目标正文")
    a = _create(client, "A", "参见 [[B]] 与 [[B|别名]]")
    rows = _links(client, a["id"])
    assert len(rows) == 2  # 两个行身份键（有无别名）
    assert all(r["target_id"] == b["id"] and r["resolution"] == "resolved" for r in rows)
    assert {r["target_title"] for r in rows} == {"B"}
    backs = _backlinks(client, b["id"])
    assert {r["source_id"] for r in backs} == {a["id"]}


def test_draft_patch_syncs_new_links_keeps_existing(client: TestClient):
    """绑定优先：新增字面建行解析；既有行（含 missing）原样保留不重解析
    （reresolve 属后续里程碑，D8 本轮无写入口）。"""
    a = _create(client, "A", "参见 [[B]]")
    assert _links(client, a["id"])[0]["resolution"] == "missing"
    _create(client, "B", "目标")
    c = _create(client, "C", "另一目标")
    resp = client.patch(f"/api/knowledge/{a['id']}", json={"content": "正文改 [[B]] [[C]]"})
    assert resp.status_code == 200
    rows = {r["target_title"]: r for r in _links(client, a["id"])}
    assert rows["B"]["resolution"] == "missing"  # 既有行保留，不重解析
    assert rows["C"]["resolution"] == "resolved" and rows["C"]["target_id"] == c["id"]


def test_active_patch_202_does_not_sync_links(client: TestClient):
    b = _create(client, "B", "目标")
    a = _create(client, "A", "参见 [[B]]")
    assert client.patch(f"/api/knowledge/{a['id']}", json={"status": "active"}).status_code == 200
    resp = client.patch(f"/api/knowledge/{a['id']}", json={"content": "参见 [[B]] [[C]]"})
    assert resp.status_code == 202
    assert resp.json()["status"] == "pending"
    rows = _links(client, a["id"])
    assert len(rows) == 1  # 未应用的变更不得产生 C 链接
    assert rows[0]["target_id"] == b["id"]


def test_delete_draft_target_demotes_backlinks(client: TestClient):
    b = _create(client, "B", "目标")
    a = _create(client, "A", "参见 [[B|别名]]")
    assert client.delete(f"/api/knowledge/{b['id']}").status_code == 204
    rows = _links(client, a["id"])  # 读取不抛异常
    assert len(rows) == 1
    assert rows[0]["resolution"] == "missing"
    assert rows[0]["target_id"] is None and rows[0]["cross_space"] is False
    assert rows[0]["target_title"] == "B" and rows[0]["alias"] == "别名"  # 字面留存
    assert client.get(f"/api/knowledge/{b['id']}/backlinks").status_code == 404


def test_delete_active_target_202_keeps_binding(client: TestClient):
    b = _create(client, "B", "目标")
    client.patch(f"/api/knowledge/{b['id']}", json={"status": "active"})
    a = _create(client, "A", "参见 [[B]]")
    assert client.delete(f"/api/knowledge/{b['id']}").status_code == 202
    rows = _links(client, a["id"])
    assert rows[0]["resolution"] == "resolved" and rows[0]["target_id"] == b["id"]


def test_extract_syncs_links(model_client: TestClient, stub_adapter):
    y = _create(model_client, "Y", "已有知识")
    stub_adapter.content = '{"items": [{"title": "X", "content": "要点参见 [[Y]]"}]}'
    conv = model_client.post("/api/conversations", json={"title": "会话"}).json()
    model_client.post(f"/api/conversations/{conv['id']}/chat", json={"content": "讲讲"})
    resp = model_client.post(f"/api/conversations/{conv['id']}/extract", json={})
    assert resp.status_code == 200
    x = resp.json()["items"][0]
    rows = _links(model_client, x["id"])
    assert len(rows) == 1
    assert rows[0]["resolution"] == "resolved" and rows[0]["target_id"] == y["id"]


def test_rename_target_keeps_binding_via_http(client: TestClient):
    """场景 A（HTTP 口径）：B 改名后 A 仍绑定稳定 ID，反链命中，字面留存。"""
    b = _create(client, "B", "目标")
    a = _create(client, "A", "参见 [[B]]")
    assert client.patch(f"/api/knowledge/{b['id']}", json={"title": "B2"}).status_code == 200
    row = _links(client, a["id"])[0]
    assert row["target_id"] == b["id"] and row["target_title"] == "B"
    assert _backlinks(client, b["id"])[0]["source_id"] == a["id"]


# ---------------------------------------------------------------- 409 稳定码


def test_create_409_link_version_mismatch_zero_write(client: TestClient, settings: Settings):
    a = _create(client, "A", "参见 [[B]]")
    _inject_version_row(settings, a["id"])
    before = client.get("/api/knowledge").json()
    resp = client.post("/api/knowledge", json={"title": "N", "content": "参见 [[B]]"})
    assert resp.status_code == 409
    assert resp.json() == {"detail": "link_version_mismatch"}  # 只回稳定码
    assert client.get("/api/knowledge").json() == before  # 整请求零写入


def test_draft_patch_409_link_version_mismatch_zero_write(client: TestClient, settings: Settings):
    a = _create(client, "A", "参见 [[B]]")
    _inject_version_row(settings, a["id"])
    resp = client.patch(f"/api/knowledge/{a['id']}", json={"content": "新正文 [[B]]"})
    assert resp.status_code == 409
    assert resp.json() == {"detail": "link_version_mismatch"}
    assert client.get(f"/api/knowledge/{a['id']}").json()["content"] == "参见 [[B]]"


def test_extract_409_link_version_mismatch_zero_write(
    model_client: TestClient, stub_adapter, settings: Settings
):
    a = _create(model_client, "A", "参见 [[B]]")
    _inject_version_row(settings, a["id"])
    stub_adapter.content = '{"items": [{"title": "X", "content": "参见 [[Y]]"}]}'
    conv = model_client.post("/api/conversations", json={"title": "会话"}).json()
    model_client.post(f"/api/conversations/{conv['id']}/chat", json={"content": "讲讲"})
    before = model_client.get("/api/knowledge").json()
    resp = model_client.post(f"/api/conversations/{conv['id']}/extract", json={})
    assert resp.status_code == 409
    assert resp.json() == {"detail": "link_version_mismatch"}
    assert model_client.get("/api/knowledge").json() == before


def test_delete_not_blocked_in_version_window(client: TestClient, settings: Settings):
    """DELETE 豁免（§8.5.3）：版本窗口内删除草稿目标仍 204，入链降级 missing。"""
    b = _create(client, "B", "目标")
    a = _create(client, "A", "参见 [[B]]")
    _inject_version_row(settings, a["id"])
    assert client.delete(f"/api/knowledge/{b['id']}").status_code == 204
    rows = _links(client, a["id"])
    b_row = next(r for r in rows if r["target_title"] == "B")
    assert b_row["resolution"] == "missing" and b_row["target_id"] is None


# ---------------------------------------------------------------- D12 读取侧


def test_read_side_defensive_mapping_via_http(client: TestClient, settings: Settings):
    _create(client, "B", "目标")
    a = _create(client, "A", "参见 [[B]]")
    _corrupt_to_illegal_null_resolved(settings, a["id"])
    rows = _links(client, a["id"])  # 非法组合不抛异常
    assert rows[0]["resolution"] == "missing"
    assert rows[0]["target_id"] is None and rows[0]["cross_space"] is False
    # 实体校验器未被弱化：同形状直接构造实体仍拒绝
    with pytest.raises(ValidationError):
        KnowledgeLink(
            source_id=UUID(a["id"]),
            target_id=None,
            target_title="B",
            normalized_link_key=normalized_link_key("B", None),
            resolution=LinkResolution.RESOLVED,
        )


# ---------------------------------------------------------------- H17 / L④


def test_h17_l4_archived_binding_retained_via_http_patch(client: TestClient, settings: Settings):
    """archived 显式绑定由仓库层夹具建立；真实 HTTP PATCH 验证「保留」而非「建立」。"""
    b = _create(client, "B", "目标")
    assert client.patch(f"/api/knowledge/{b['id']}", json={"status": "archived"}).status_code == 200
    a = _create(client, "A", "参见 [[B]]")
    assert _links(client, a["id"])[0]["resolution"] == "missing"  # 自动解析排除 archived
    _bind_via_repository_fixture(settings, UUID(a["id"]), UUID(b["id"]))
    for body in ("无关改动一 [[B]]", "无关改动二 [[B]]"):
        assert client.patch(f"/api/knowledge/{a['id']}", json={"content": body}).status_code == 200
        row = _links(client, a["id"])[0]
        assert row["target_id"] == b["id"] and row["resolution"] == "resolved"


# ---------------------------------------------------------------- 候选发现


def test_resolve_candidates_lists_archived_and_cross_space(client: TestClient):
    project = client.post("/api/spaces", json={"name": "项目"}).json()
    active = _create(client, "Beta", "a", space_id=project["id"])
    client.patch(f"/api/knowledge/{active['id']}", json={"status": "active"})
    archived = _create(client, "Beta", "b")  # 个人总知识库（None）
    client.patch(f"/api/knowledge/{archived['id']}", json={"status": "archived"})
    resp = client.get(
        "/api/knowledge/links/resolve-candidates",
        params={"title": "ｂｅｔａ", "space_id": project["id"]},  # NFKC+casefold 匹配
    )
    assert resp.status_code == 200  # 静态路由先于 {item_id} 动态段（R11）
    body = resp.json()
    assert len(body) == 2
    by_id = {c["id"]: c for c in body}
    assert by_id[active["id"]]["status"] == "active"
    assert by_id[active["id"]]["cross_space"] is False
    assert by_id[archived["id"]]["status"] == "archived"  # D7：带 status 标注列出
    assert by_id[archived["id"]]["cross_space"] is True


def test_resolve_candidates_empty_for_unknown_title(client: TestClient):
    resp = client.get("/api/knowledge/links/resolve-candidates", params={"title": "不存在"})
    assert resp.status_code == 200 and resp.json() == []


def test_links_and_backlinks_404_for_missing_item(client: TestClient):
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/knowledge/{missing}/links").status_code == 404
    assert client.get(f"/api/knowledge/{missing}/backlinks").status_code == 404


# ---------------------------------------------------------------- 路由守护（D8）


def test_links_router_is_exactly_three_gets():
    pairs = {(method, route.path) for route in links_router.routes for method in route.methods}
    assert pairs == {
        ("GET", "/knowledge/{item_id}/links"),
        ("GET", "/knowledge/{item_id}/backlinks"),
        ("GET", "/knowledge/links/resolve-candidates"),
    }


def test_knowledge_router_endpoint_set_unchanged():
    pairs = {(method, route.path) for route in knowledge_router.routes for method in route.methods}
    assert pairs == {
        ("GET", "/knowledge"),
        ("POST", "/knowledge"),
        ("GET", "/knowledge/{item_id}"),
        ("PATCH", "/knowledge/{item_id}"),
        ("DELETE", "/knowledge/{item_id}"),
        ("POST", "/conversations/{conversation_id}/extract"),
    }


def test_no_rebuild_or_binding_http_write_entry(client: TestClient):
    """R3.1 / D8：不存在重建/显式绑定/重解析的 HTTP 入口（写端点延后里程碑）。"""
    paths = {route.path for route in client.app.routes if hasattr(route, "methods")}
    assert not any(
        "rebuild-keys" in p or p.endswith("/links/resolve") or p.endswith("/links/reresolve")
        for p in paths
    )