"""知识 API 测试：手动 CRUD、空间过滤、对话提取与来源追溯。"""

from __future__ import annotations

from fastapi.testclient import TestClient

_MISSING_UUID = "00000000-0000-0000-0000-000000000000"


def test_create_manual_knowledge(client: TestClient):
    resp = client.post("/api/knowledge", json={"title": "手动知识", "content": "内容"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "draft"
    assert body["source_refs"][0]["source_type"] == "manual"


def test_list_and_filter_by_space(client: TestClient):
    space = client.post("/api/spaces", json={"name": "项目"}).json()
    client.post(
        "/api/knowledge", json={"title": "A", "content": "a", "space_id": space["id"]}
    )
    client.post("/api/knowledge", json={"title": "B", "content": "b"})
    assert len(client.get("/api/knowledge").json()) == 2
    filtered = client.get(f"/api/knowledge?space_id={space['id']}").json()
    assert len(filtered) == 1
    assert filtered[0]["title"] == "A"


def test_personal_space_includes_unassigned_items(client: TestClient):
    """个人总知识库视图须包含 space_id 为 None 的条目（如無空间会话提取所得）。"""
    spaces = client.get("/api/spaces").json()
    personal = next(s for s in spaces if s["kind"] == "personal")
    project = client.post("/api/spaces", json={"name": "项目X"}).json()

    # 一条未显式归属（None，语义上属于个人总知识库），一条归属项目空间
    client.post("/api/knowledge", json={"title": "个人条目", "content": "p"})
    client.post(
        "/api/knowledge",
        json={"title": "项目条目", "content": "x", "space_id": project["id"]},
    )

    personal_items = client.get(f"/api/knowledge?space_id={personal['id']}").json()
    titles = {i["title"] for i in personal_items}
    assert "个人条目" in titles  # None 条目被个人视图聚合
    assert "项目条目" not in titles  # 项目条目不串入个人视图

    # 项目空间视图不应包含 None 条目
    project_items = client.get(f"/api/knowledge?space_id={project['id']}").json()
    assert {i["title"] for i in project_items} == {"项目条目"}


def test_update_knowledge_partial(client: TestClient):
    item = client.post("/api/knowledge", json={"title": "A", "content": "a"}).json()
    resp = client.patch(
        f"/api/knowledge/{item['id']}", json={"title": "A2", "status": "active"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "A2"
    assert body["status"] == "active"
    assert body["content"] == "a"  # 未提供字段保持不变


def test_delete_knowledge(client: TestClient):
    item = client.post("/api/knowledge", json={"title": "A", "content": "a"}).json()
    assert client.delete(f"/api/knowledge/{item['id']}").status_code == 204
    assert client.get(f"/api/knowledge/{item['id']}").status_code == 404


def test_get_knowledge_not_found(client: TestClient):
    assert client.get(f"/api/knowledge/{_MISSING_UUID}").status_code == 404


def test_extract_without_model_config_returns_503(client: TestClient):
    conv = client.post("/api/conversations", json={"title": "A"}).json()
    resp = client.post(f"/api/conversations/{conv['id']}/extract", json={})
    assert resp.status_code == 503


def test_extract_persists_with_source_trace(model_client: TestClient, stub_adapter):
    stub_adapter.content = '{"items": [{"title": "知识点", "content": "提取的内容"}]}'
    conv = model_client.post("/api/conversations", json={"title": "A"}).json()
    model_client.post(f"/api/conversations/{conv['id']}/chat", json={"content": "讲讲知识点"})

    resp = model_client.post(f"/api/conversations/{conv['id']}/extract", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    item = body["items"][0]
    assert item["title"] == "知识点"
    assert item["status"] == "draft"
    assert item["source_refs"][0]["source_type"] == "conversation"
    assert item["source_refs"][0]["conversation_id"] == conv["id"]
    assert item["source_refs"][0]["excerpt"]

    listed = model_client.get("/api/knowledge").json()
    assert any(i["id"] == item["id"] for i in listed)


def test_extract_empty_when_no_knowledge(model_client: TestClient, stub_adapter):
    stub_adapter.content = '{"items": []}'
    conv = model_client.post("/api/conversations", json={"title": "A"}).json()
    model_client.post(f"/api/conversations/{conv['id']}/chat", json={"content": "你好"})
    resp = model_client.post(f"/api/conversations/{conv['id']}/extract", json={})
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


def test_extract_conversation_not_found(model_client: TestClient):
    resp = model_client.post("/api/conversations/missing/extract", json={})
    assert resp.status_code == 404