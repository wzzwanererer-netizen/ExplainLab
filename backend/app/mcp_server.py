"""ExplainLab 本地 MCP Server（JSON-RPC 2.0 over stdio）。

让 Antigravity、Claude Desktop、Cursor、Codex、Windsurf、Cline 等任意支持 MCP 的
Agent 直接连接本地运行中的 ExplainLab 后端，实现：
- 检索用户已有知识库（混合 / 全文 / 向量）
- 将外部 Agent 的调研结论、踩坑经验、笔记自动记录进 ExplainLab（带来源追溯）
- 自动建立知识间语义关系（实时呈现在 Obsidian 知识星图中）
- 遵循 ExplainLab 审核门禁（对生效条目的修改自动进入审核队列）

运行方式：
    uv run --project d:\\ExplainLab python -m app.mcp_server
或通过环境变量指定后端地址：
    EXPLAINLAB_API_URL=http://127.0.0.1:8000
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import httpx

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {
    "name": "explainlab-mcp",
    "version": "1.0.0",
}

DEFAULT_API_URL = "http://127.0.0.1:8000"

TOOLS: list[dict[str, Any]] = [
    {
        "name": "explainlab_health",
        "description": "检查本地 ExplainLab 知识库后端运行状态、数据库与模型就绪情况。",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "explainlab_list_spaces",
        "description": "列出 ExplainLab 中的全部知识空间（个人总知识库及各项目空间）。",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "explainlab_create_space",
        "description": "在 ExplainLab 中创建一个新的项目知识空间。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "空间名称"},
                "description": {"type": "string", "description": "可选空间说明"},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "explainlab_search_knowledge",
        "description": (
            "在用户的 ExplainLab 知识库中执行混合检索（全文 + 语义向量）。"
            "建议在回答技术问题或开始新任务前先调用，复用用户已沉淀的知识。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索关键词或问题"},
                "space_id": {"type": "string", "description": "可选，限定知识空间 ID"},
                "mode": {
                    "type": "string",
                    "enum": ["hybrid", "fts", "vector"],
                    "description": "检索模式，默认 hybrid",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 30,
                    "description": "返回条数上限，默认 8",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "explainlab_list_knowledge",
        "description": "列出指定空间（或全部空间）中的知识条目摘要。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "space_id": {"type": "string", "description": "可选，知识空间 ID"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "explainlab_get_knowledge",
        "description": "读取某条知识的完整正文、来源引用、语义关系与双向链接。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "item_id": {"type": "string", "description": "知识条目 ID"},
            },
            "required": ["item_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "explainlab_record_knowledge",
        "description": (
            "将外部 Agent 产生的结论、经验、架构笔记或调研摘要记录到 ExplainLab 知识库。"
            "会自动附加来源追溯（记录是哪个 Agent 写入的），并可选建立与其他知识的关联。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "知识标题（简洁明确）"},
                "content": {"type": "string", "description": "知识正文（支持 Markdown）"},
                "space_id": {
                    "type": "string",
                    "description": (
                        "可选，目标知识空间 ID；填 'main' 表示写入个人总知识库（主库）；"
                        "不填且提供了 agent_name 时，会自动按该 Agent 名称归入/创建专属副库（如 'Agent · Cursor'）"
                    ),
                },
                "auto_agent_space": {
                    "type": "boolean",
                    "description": "未指定 space_id 时是否自动归入/创建该 Agent 专属副库，默认 true",
                },
                "agent_name": {
                    "type": "string",
                    "description": "写入该知识的 Agent 名称，如 Cursor / Claude / Antigravity / Codex",
                },
                "source_uri": {
                    "type": "string",
                    "description": "可选，来源链接或本地文件路径",
                },
                "excerpt": {
                    "type": "string",
                    "description": "可选，上下文摘录（说明该知识是如何得出的）",
                },
                "activate": {
                    "type": "boolean",
                    "description": "是否直接标记为生效（active）；默认 false（先存为草稿 draft）",
                },
                "related_to": {
                    "type": "array",
                    "description": "可选，同步建立与其他知识条目的语义关系",
                    "items": {
                        "type": "object",
                        "properties": {
                            "target_id": {"type": "string"},
                            "relation_type": {
                                "type": "string",
                                "enum": [
                                    "related",
                                    "depends_on",
                                    "refines",
                                    "duplicate_of",
                                    "contradicts",
                                ],
                            },
                        },
                        "required": ["target_id"],
                    },
                },
            },
            "required": ["title", "content"],
            "additionalProperties": False,
        },
    },
    {
        "name": "explainlab_update_knowledge",
        "description": (
            "更新已有知识条目的标题、正文或状态。"
            "注意：修改已生效（active）条目时，ExplainLab 会自动将其转入审核队列（HTTP 202）等待用户确认。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "item_id": {"type": "string", "description": "知识条目 ID"},
                "title": {"type": "string", "description": "可选，新标题"},
                "content": {"type": "string", "description": "可选，新正文"},
                "status": {
                    "type": "string",
                    "enum": ["draft", "active", "archived"],
                    "description": "可选，新状态",
                },
            },
            "required": ["item_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "explainlab_link_knowledge",
        "description": "在两条知识之间建立语义关系，实时反映在 ExplainLab 的知识星图中。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_id": {"type": "string", "description": "源知识条目 ID"},
                "target_id": {"type": "string", "description": "目标知识条目 ID"},
                "relation_type": {
                    "type": "string",
                    "enum": [
                        "related",
                        "depends_on",
                        "refines",
                        "duplicate_of",
                        "contradicts",
                    ],
                    "description": "关系类型，默认 related",
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "description": "置信度 0~1，默认 0.9",
                },
            },
            "required": ["source_id", "target_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "explainlab_get_graph",
        "description": "获取 ExplainLab 知识关系图谱的节点与边，帮助 Agent 理解知识拓扑结构。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "space_id": {"type": "string", "description": "可选，空间 ID"},
                "include_archived": {
                    "type": "boolean",
                    "description": "是否包含已归档条目，默认 false",
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "explainlab_list_reviews",
        "description": "查看 ExplainLab 审核队列中的待审核或已处理条目。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["pending", "approved", "rejected"],
                    "description": "可选，按审核状态筛选",
                },
            },
            "additionalProperties": False,
        },
    },
]

RESOURCES: list[dict[str, Any]] = [
    {
        "uri": "explainlab://spaces",
        "name": "ExplainLab Knowledge Spaces",
        "description": "全部知识空间列表（JSON）",
        "mimeType": "application/json",
    },
    {
        "uri": "explainlab://graph",
        "name": "ExplainLab Knowledge Graph",
        "description": "当前知识关系图谱快照（JSON）",
        "mimeType": "application/json",
    },
]


class ExplainLabBackendError(RuntimeError):
    """调用本地 ExplainLab 后端失败时抛出的结构化错误。"""


class ExplainLabMCPServer:
    """MCP JSON-RPC 2.0 处理器，解耦传输层便于单元测试。"""

    def __init__(
        self,
        api_url: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        base = (api_url or os.environ.get("EXPLAINLAB_API_URL") or DEFAULT_API_URL).rstrip("/")
        self.api_url = base
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=base,
            timeout=15.0,
            trust_env=False,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        try:
            resp = self._client.request(
                method,
                path,
                params=params,
                json=json_body,
            )
        except httpx.ConnectError as exc:
            raise ExplainLabBackendError(
                f"无法连接到本地 ExplainLab 后端 ({self.api_url})，请确认 ExplainLab 已启动。"
            ) from exc
        except httpx.TimeoutException as exc:
            raise ExplainLabBackendError(
                f"请求 ExplainLab 后端超时 ({self.api_url}{path})。"
            ) from exc

        if resp.status_code >= 400:
            detail = ""
            try:
                body = resp.json()
                if isinstance(body, dict) and isinstance(body.get("detail"), str):
                    detail = body["detail"]
            except Exception:
                detail = resp.text[:200]
            raise ExplainLabBackendError(
                f"ExplainLab API 错误 (HTTP {resp.status_code}): {detail or path}"
            )

        if resp.status_code == 204 or not resp.content:
            return resp.status_code, None
        return resp.status_code, resp.json()

    def _ensure_agent_space(self, agent_name: str) -> dict[str, Any]:
        """按 Agent 名称查找或动态创建专属知识副库（如 'Agent · Cursor'）。"""
        clean_name = agent_name.strip() or "External"
        target_name = (
            clean_name if clean_name.lower().startswith("agent ·") else f"Agent · {clean_name}"
        )
        _, spaces = self._request("GET", "/api/spaces")
        if isinstance(spaces, list):
            for sp in spaces:
                if (
                    isinstance(sp, dict)
                    and isinstance(sp.get("name"), str)
                    and sp["name"].strip().lower() == target_name.lower()
                ):
                    return sp
        _, created_space = self._request(
            "POST",
            "/api/spaces",
            json_body={
                "name": target_name,
                "description": f"由 {clean_name} 自动沉淀的专属知识副库（可独立查看知识与关系图，也可在全部空间中与主库联合查看）",
            },
        )
        return created_space

    def _call_tool(self, name: str, args: dict[str, Any]) -> Any:
        if name == "explainlab_health":
            _, data = self._request("GET", "/api/health")
            return data

        if name == "explainlab_list_spaces":
            _, data = self._request("GET", "/api/spaces")
            return data

        if name == "explainlab_create_space":
            _, data = self._request(
                "POST",
                "/api/spaces",
                json_body={
                    "name": args["name"],
                    "description": args.get("description"),
                },
            )
            return data

        if name == "explainlab_search_knowledge":
            params: dict[str, Any] = {"query": args["query"]}
            if args.get("space_id"):
                params["space_id"] = args["space_id"]
            if args.get("mode"):
                params["mode"] = args["mode"]
            params["limit"] = int(args.get("limit") or 8)
            _, data = self._request("GET", "/api/search", params=params)
            return data

        if name == "explainlab_list_knowledge":
            params = {}
            if args.get("space_id"):
                params["space_id"] = args["space_id"]
            _, data = self._request("GET", "/api/knowledge", params=params)
            return data

        if name == "explainlab_get_knowledge":
            item_id = args["item_id"]
            _, item = self._request("GET", f"/api/knowledge/{item_id}")
            _, relations = self._request("GET", f"/api/knowledge/{item_id}/relations")
            _, backlinks = self._request("GET", f"/api/knowledge/{item_id}/backlinks")
            return {
                "item": item,
                "relations": relations,
                "backlinks": backlinks,
            }

        if name == "explainlab_record_knowledge":
            agent_name = (args.get("agent_name") or "external-agent").strip()
            raw_space_id = args.get("space_id")
            auto_agent_space = args.get("auto_agent_space", True)

            resolved_space: dict[str, Any] | None = None
            target_space_id: str | None = None

            if isinstance(raw_space_id, str) and raw_space_id.strip():
                if raw_space_id.strip().lower() != "main":
                    target_space_id = raw_space_id.strip()
            elif auto_agent_space and args.get("agent_name"):
                resolved_space = self._ensure_agent_space(agent_name)
                target_space_id = resolved_space["id"]

            create_payload: dict[str, Any] = {
                "title": args["title"],
                "content": args["content"],
            }
            if target_space_id:
                create_payload["space_id"] = target_space_id

            _, created = self._request("POST", "/api/knowledge", json_body=create_payload)
            item_id = created["id"]

            source_uri = args.get("source_uri") or f"agent://{agent_name}"
            excerpt = args.get("excerpt") or f"由外部 Agent（{agent_name}）通过 MCP 自动记录"
            _, source_ref = self._request(
                "POST",
                f"/api/knowledge/{item_id}/sources",
                json_body={
                    "source_type": "import",
                    "uri": source_uri,
                    "excerpt": excerpt,
                },
            )

            activation: dict[str, Any] | None = None
            if args.get("activate"):
                status_code, patch_data = self._request(
                    "PATCH",
                    f"/api/knowledge/{item_id}",
                    json_body={"status": "active"},
                )
                if status_code == 202:
                    activation = {"state": "pending_review", "review": patch_data}
                else:
                    created = patch_data
                    activation = {"state": "active"}

            linked_relations: list[Any] = []
            for rel in args.get("related_to") or []:
                target_id = rel.get("target_id")
                if not target_id:
                    continue
                _, rel_data = self._request(
                    "POST",
                    f"/api/knowledge/{item_id}/relations",
                    json_body={
                        "target_id": target_id,
                        "relation_type": rel.get("relation_type") or "related",
                        "confidence": 0.9,
                    },
                )
                linked_relations.append(rel_data)

            return {
                "recorded": True,
                "space": resolved_space,
                "item": created,
                "source_ref": source_ref,
                "activation": activation,
                "relations_created": linked_relations,
            }

        if name == "explainlab_update_knowledge":
            item_id = args["item_id"]
            patch: dict[str, Any] = {}
            for key in ("title", "content", "status"):
                if key in args and args[key] is not None:
                    patch[key] = args[key]
            status_code, data = self._request(
                "PATCH",
                f"/api/knowledge/{item_id}",
                json_body=patch,
            )
            if status_code == 202:
                return {
                    "applied": False,
                    "submitted_for_review": True,
                    "review": data,
                }
            return {"applied": True, "item": data}

        if name == "explainlab_link_knowledge":
            _, data = self._request(
                "POST",
                f"/api/knowledge/{args['source_id']}/relations",
                json_body={
                    "target_id": args["target_id"],
                    "relation_type": args.get("relation_type") or "related",
                    "confidence": float(args.get("confidence", 0.9)),
                },
            )
            return data

        if name == "explainlab_get_graph":
            params = {}
            if args.get("space_id"):
                params["space_id"] = args["space_id"]
            if args.get("include_archived"):
                params["include_archived"] = "true"
            _, data = self._request("GET", "/api/graph", params=params)
            return data

        if name == "explainlab_list_reviews":
            params = {}
            if args.get("status"):
                params["status"] = args["status"]
            _, data = self._request("GET", "/api/reviews", params=params)
            return data

        raise ValueError(f"Unknown tool: {name}")

    def _read_resource(self, uri: str) -> dict[str, Any]:
        if uri == "explainlab://spaces":
            _, data = self._request("GET", "/api/spaces")
        elif uri == "explainlab://graph":
            _, data = self._request("GET", "/api/graph")
        else:
            raise ValueError(f"Unknown resource URI: {uri}")
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(data, ensure_ascii=False, indent=2),
                }
            ]
        }

    def handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """处理单条 JSON-RPC 2.0 消息；通知类消息返回 None。"""
        method = message.get("method")
        msg_id = message.get("id")
        params = message.get("params") or {}

        # 通知（无 id）不返回响应
        if msg_id is None:
            return None

        try:
            if method == "initialize":
                result: Any = {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {},
                        "resources": {},
                    },
                    "serverInfo": SERVER_INFO,
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                tool_name = params.get("name")
                tool_args = params.get("arguments") or {}
                if not isinstance(tool_name, str):
                    raise ValueError("Missing tool name")
                try:
                    output = self._call_tool(tool_name, tool_args)
                    result = {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(output, ensure_ascii=False, indent=2),
                            }
                        ],
                        "isError": False,
                    }
                except ExplainLabBackendError as exc:
                    result = {
                        "content": [{"type": "text", "text": str(exc)}],
                        "isError": True,
                    }
            elif method == "resources/list":
                result = {"resources": RESOURCES}
            elif method == "resources/read":
                uri = params.get("uri")
                if not isinstance(uri, str):
                    raise ValueError("Missing resource uri")
                result = self._read_resource(uri)
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }

            return {"jsonrpc": "2.0", "id": msg_id, "result": result}
        except ValueError as exc:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32602, "message": str(exc)},
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32603, "message": f"Internal error: {type(exc).__name__}"},
            }


def serve_stdio() -> None:
    """运行 MCP stdio 事件循环（newline-delimited JSON-RPC 2.0）。"""
    # Windows 下强制 UTF-8，避免中文知识标题/内容乱码
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    server = ExplainLabMCPServer()
    try:
        for raw_line in sys.stdin:
            line = raw_line.lstrip("\ufeff").strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                }
                sys.stdout.write(json.dumps(err_resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()
                continue

            if not isinstance(message, dict):
                continue

            response = server.handle_message(message)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()
    finally:
        server.close()


if __name__ == "__main__":
    serve_stdio()
