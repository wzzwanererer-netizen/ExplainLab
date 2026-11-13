"""知识空间 API 测试：默认个人空间播种、项目空间 CRUD。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_default_personal_space_seeded(client: TestClient):
    spaces = client.get("/api/spaces").json()
    personal = [s for s in spaces if s["kind"] == "personal"]
    assert len(personal) == 1
    assert personal[0]["name"] == "个人总知识库"


def test_create_project_space(client: TestClient):
    resp = client.post("/api/spaces", json={"name": "项目A", "description": "测试空间"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["kind"] == "project"
    assert body["name"] == "项目A"
    assert body["description"] == "测试空间"
    spaces = client.get("/api/spaces").json()
    assert any(s["id"] == body["id"] for s in spaces)


def test_get_space(client: TestClient):
    created = client.post("/api/spaces", json={"name": "项目B"}).json()
    resp = client.get(f"/api/spaces/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "项目B"


def test_get_space_not_found(client: TestClient):
    assert client.get("/api/spaces/nonexistent-id").status_code == 404


def test_create_space_rejects_empty_name(client: TestClient):
    assert client.post("/api/spaces", json={"name": ""}).status_code == 422