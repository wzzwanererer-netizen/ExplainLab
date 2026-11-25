"""ExplainLab 本地 MCP Server 单元测试（不依赖外部网络，用 MockTransport 验证完整协议）。"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.mcp_server import ExplainLabMCPServer


def _make_server(
    handler: Any,
) -> ExplainLabMCPServer:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(base_url="http://explainlab.local", transport=transport)
    return ExplainLabMCPServer(api_url="http://explainlab.local", client=client)


def test_mcp_initialize_and_tools_list() -> None:
    server = _make_server(lambda req: httpx.Response(200, json={}))
    init_resp = server.handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    )
    assert init_resp is not None
    assert init_resp["result"]["serverInfo"]["name"] == "explainlab-mcp"
    assert "tools" in init_resp["result"]["capabilities"]

    # notifications/initialized 无 id，不应返回响应
    assert (
        server.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"})
        is None
    )

    tools_resp = server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert tools_resp is not None
    names = {t["name"] for t in tools_resp["result"]["tools"]}
    assert "explainlab_record_knowledge" in names
    assert "explainlab_search_knowledge" in names
    assert "explainlab_link_knowledge" in names


def test_mcp_record_knowledge_creates_agent_space_item_source_and_relation() -> None:
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content.decode("utf-8")) if req.content else None
        calls.append((req.method, req.url.path, body))
        if req.method == "GET" and req.url.path == "/api/spaces":
            return httpx.Response(
                200,
                json=[{"id": "sp-main", "name": "个人总知识库", "kind": "personal"}],
            )
        if req.method == "POST" and req.url.path == "/api/spaces":
            return httpx.Response(
                201,
                json={"id": "sp-cursor", "name": body["name"], "kind": "project"},
            )
        if req.method == "POST" and req.url.path == "/api/knowledge":
            assert body["space_id"] == "sp-cursor"
            return httpx.Response(
                201,
                json={
                    "id": "k-new",
                    "space_id": body["space_id"],
                    "title": body["title"],
                    "content": body["content"],
                    "status": "draft",
                },
            )
        if req.method == "POST" and req.url.path == "/api/knowledge/k-new/sources":
            return httpx.Response(201, json={"id": "src-1", **body})
        if req.method == "PATCH" and req.url.path == "/api/knowledge/k-new":
            return httpx.Response(
                200,
                json={
                    "id": "k-new",
                    "space_id": "sp-cursor",
                    "title": "MCP 测试笔记",
                    "content": "内容",
                    "status": "active",
                },
            )
        if req.method == "POST" and req.url.path == "/api/knowledge/k-new/relations":
            return httpx.Response(201, json={"id": "rel-1", **body})
        return httpx.Response(404)

    server = _make_server(handler)
    resp = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {
                "name": "explainlab_record_knowledge",
                "arguments": {
                    "title": "MCP 测试笔记",
                    "content": "由 Cursor 总结的踩坑记录",
                    "agent_name": "Cursor",
                    "activate": True,
                    "related_to": [{"target_id": "k-old", "relation_type": "depends_on"}],
                },
            },
        }
    )
    assert resp is not None
    assert resp["result"]["isError"] is False
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["recorded"] is True
    assert payload["space"]["name"] == "Agent · Cursor"
    assert payload["item"]["space_id"] == "sp-cursor"
    assert payload["item"]["status"] == "active"
    assert payload["source_ref"]["uri"] == "agent://Cursor"
    assert len(payload["relations_created"]) == 1
    assert [c[1] for c in calls] == [
        "/api/spaces",
        "/api/spaces",
        "/api/knowledge",
        "/api/knowledge/k-new/sources",
        "/api/knowledge/k-new",
        "/api/knowledge/k-new/relations",
    ]


def test_mcp_update_knowledge_respects_review_gate_202() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "PATCH" and req.url.path == "/api/knowledge/k-active":
            return httpx.Response(
                202,
                json={"id": "rev-1", "item_id": "k-active", "status": "pending"},
            )
        return httpx.Response(404)

    server = _make_server(handler)
    resp = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {
                "name": "explainlab_update_knowledge",
                "arguments": {"item_id": "k-active", "title": "修改后标题"},
            },
        }
    )
    assert resp is not None
    assert resp["result"]["isError"] is False
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["applied"] is False
    assert payload["submitted_for_review"] is True
    assert payload["review"]["id"] == "rev-1"


def test_mcp_search_and_backend_unreachable_error() -> None:
    def ok_handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/search":
            assert req.url.params["query"] == "知识图谱"
            return httpx.Response(200, json={"hits": [{"item_id": "k1", "title": "知识图谱"}]})
        return httpx.Response(404)

    server = _make_server(ok_handler)
    resp = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {
                "name": "explainlab_search_knowledge",
                "arguments": {"query": "知识图谱", "mode": "hybrid"},
            },
        }
    )
    assert resp is not None
    assert resp["result"]["isError"] is False
    assert "知识图谱" in resp["result"]["content"][0]["text"]

    # 后端不可达时优雅返回 isError=True，不崩溃
    def fail_handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=req)

    down_server = _make_server(fail_handler)
    down_resp = down_server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 13,
            "method": "tools/call",
            "params": {"name": "explainlab_health", "arguments": {}},
        }
    )
    assert down_resp is not None
    assert down_resp["result"]["isError"] is True
    assert "无法连接" in down_resp["result"]["content"][0]["text"]
