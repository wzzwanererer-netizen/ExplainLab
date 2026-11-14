"""M4-T2 知识地图 API 测试：节点/边装配 / 空间过滤 / 归档开关 / 404。

使用 create_all 夹具；图是现有条目+关系的只读视图，无新增表。
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _create(client: TestClient, title: str, **kw) -> dict:
    resp = client.post("/api/knowledge", json={"title": title, "content": f"{title} 内容", **kw})
    assert resp.status_code == 201
    return resp.json()


def _relate(client: TestClient, source: str, target: str, relation_type: str = "related") -> dict:
    resp = client.post(
        f"/api/knowledge/{source}/relations",
        json={"target_id": target, "relation_type": relation_type},
    )
    assert resp.status_code == 201
    return resp.json()


def test_graph_empty(client: TestClient):
    body = client.get("/api/graph").json()
    assert body["nodes"] == []
    assert body["edges"] == []


def test_graph_nodes_and_edges(client: TestClient):
    a = _create(client, "定义")
    b = _create(client, "用途")
    _relate(client, a["id"], b["id"], "related")
    body = client.get("/api/graph").json()
    assert {n["id"] for n in body["nodes"]} == {a["id"], b["id"]}
    assert len(body["edges"]) == 1
    edge = body["edges"][0]
    assert edge["source_id"] == a["id"]
    assert edge["target_id"] == b["id"]
    assert edge["relation_type"] == "related"
    assert edge["origin"] == "manual"


def test_graph_archived_excluded_and_toggle(client: TestClient):
    a = _create(client, "定义")
    b = _create(client, "概念")
    _relate(client, b["id"], a["id"], "duplicate_of")
    assert client.patch(f"/api/knowledge/{b['id']}", json={"status": "archived"}).status_code == 200

    default = client.get("/api/graph").json()
    assert {n["id"] for n in default["nodes"]} == {a["id"]}
    assert default["edges"] == []  # 指向归档的边不悬空

    included = client.get("/api/graph", params={"include_archived": True}).json()
    assert {n["id"] for n in included["nodes"]} == {a["id"], b["id"]}
    assert len(included["edges"]) == 1
    assert included["edges"][0]["relation_type"] == "duplicate_of"
    archived_node = next(n for n in included["nodes"] if n["id"] == b["id"])
    assert archived_node["status"] == "archived"


def test_graph_space_filter_and_personal_aggregation(client: TestClient):
    personal = next(s for s in client.get("/api/spaces").json() if s["kind"] == "personal")
    project = client.post("/api/spaces", json={"name": "项目X"}).json()
    unassigned = _create(client, "个人知识")
    proj_item = _create(client, "项目知识", space_id=project["id"])
    _relate(client, unassigned["id"], proj_item["id"], "depends_on")

    proj = client.get("/api/graph", params={"space_id": project["id"]}).json()
    assert {n["id"] for n in proj["nodes"]} == {proj_item["id"]}
    assert proj["edges"] == []

    pers = client.get("/api/graph", params={"space_id": personal["id"]}).json()
    assert {n["id"] for n in pers["nodes"]} == {unassigned["id"]}
    assert pers["edges"] == []

    all_spaces = client.get("/api/graph").json()
    assert {n["id"] for n in all_spaces["nodes"]} == {unassigned["id"], proj_item["id"]}
    assert len(all_spaces["edges"]) == 1


def test_graph_unknown_space_404(client: TestClient):
    resp = client.get("/api/graph", params={"space_id": "no-such-space"})
    assert resp.status_code == 404