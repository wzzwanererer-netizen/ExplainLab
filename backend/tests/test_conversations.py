"""会话 API 测试：CRUD、真实对话落库、未配置 503、模型故障回滚。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_and_get_conversation(client: TestClient):
    resp = client.post("/api/conversations", json={"title": "学习会话"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "学习会话"
    assert body["messages"] == []
    detail = client.get(f"/api/conversations/{body['id']}").json()
    assert detail["id"] == body["id"]


def test_list_conversations(client: TestClient):
    client.post("/api/conversations", json={"title": "A"})
    client.post("/api/conversations", json={"title": "B"})
    rows = client.get("/api/conversations").json()
    assert len(rows) == 2


def test_delete_conversation(client: TestClient):
    conv = client.post("/api/conversations", json={"title": "A"}).json()
    assert client.delete(f"/api/conversations/{conv['id']}").status_code == 204
    assert client.get(f"/api/conversations/{conv['id']}").status_code == 404


def test_chat_without_model_config_returns_503(client: TestClient):
    conv = client.post("/api/conversations", json={"title": "A"}).json()
    resp = client.post(f"/api/conversations/{conv['id']}/chat", json={"content": "你好"})
    assert resp.status_code == 503
    assert "模型未配置" in resp.json()["detail"]


def test_chat_with_stub_persists_messages(model_client: TestClient, stub_adapter):
    stub_adapter.content = "这是助手回复"
    conv = model_client.post("/api/conversations", json={"title": "A"}).json()
    resp = model_client.post(
        f"/api/conversations/{conv['id']}/chat", json={"content": "你好"}
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "assistant"
    assert resp.json()["content"] == "这是助手回复"

    detail = model_client.get(f"/api/conversations/{conv['id']}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][0]["content"] == "你好"
    # 适配器确实收到系统提示 + 用户消息
    assert stub_adapter.requests[0].messages[0].role == "system"
    assert stub_adapter.requests[0].messages[-1].content == "你好"


def test_chat_model_failure_rolls_back(model_client: TestClient, stub_adapter):
    stub_adapter.fail = True
    conv = model_client.post("/api/conversations", json={"title": "A"}).json()
    resp = model_client.post(
        f"/api/conversations/{conv['id']}/chat", json={"content": "你好"}
    )
    assert resp.status_code == 502
    # 模型失败时用户消息不应落库（会话关闭即回滚）
    detail = model_client.get(f"/api/conversations/{conv['id']}").json()
    assert detail["messages"] == []


def test_chat_conversation_not_found(model_client: TestClient):
    resp = model_client.post("/api/conversations/missing/chat", json={"content": "你好"})
    assert resp.status_code == 404