"""M3-T5 检索 API 测试：三模式 / 空间过滤 / archived 排除 / 降级如实 / backfill / 健康上报。

使用 create_all 夹具（含 FTS 兜底事件），向量用本地 FakeEmbedder 注入，不发网络请求。
"""

from __future__ import annotations

from collections.abc import Sequence

from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.dependencies import get_embedder
from knowledge_core.model_adapter import ModelAdapterError


class FakeEmbedder:
    default_model = "fake-embed"

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


class FailingEmbedder:
    default_model = "fake-embed"

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise ModelAdapterError("模拟 embed 端点不可用")


def _create(client: TestClient, title: str, content: str, **kw) -> dict:
    resp = client.post("/api/knowledge", json={"title": title, "content": content, **kw})
    assert resp.status_code == 201
    return resp.json()


def test_search_fts_chinese_no_embed(client: TestClient):
    item = _create(client, "知识图谱的定义", "知识图谱是一种网络结构数据模型")
    body = client.get("/api/search", params={"query": "知识图谱"}).json()
    assert body["embed_capability"] == "not_configured"
    assert body["mode"] == "fts"  # 未配置 embed，hybrid 如实降级为仅全文
    assert body["count"] >= 1
    assert item["id"] in [r["item_id"] for r in body["results"]]
    assert "fts" in body["results"][0]["channels"]


def test_search_short_query_like_fallback(client: TestClient):
    item = _create(client, "图谱笔记", "知识图谱相关内容")
    body = client.get("/api/search", params={"query": "图谱"}).json()
    assert item["id"] in [r["item_id"] for r in body["results"]]


def test_search_empty_query_rejected(client: TestClient):
    assert client.get("/api/search", params={"query": ""}).status_code == 422


def test_search_space_filter_and_personal_aggregation(client: TestClient):
    personal = next(s for s in client.get("/api/spaces").json() if s["kind"] == "personal")
    project = client.post("/api/spaces", json={"name": "项目X"}).json()
    unassigned = _create(client, "知识图谱个人", "个人内容")
    proj_item = _create(client, "知识图谱项目", "项目内容", space_id=project["id"])

    proj_body = client.get(
        "/api/search", params={"query": "知识图谱", "space_id": project["id"]}
    ).json()
    proj_ids = {r["item_id"] for r in proj_body["results"]}
    assert proj_ids == {proj_item["id"]}

    personal_body = client.get(
        "/api/search", params={"query": "知识图谱", "space_id": personal["id"]}
    ).json()
    personal_ids = {r["item_id"] for r in personal_body["results"]}
    assert unassigned["id"] in personal_ids  # 个人视图聚合未归属条目
    assert proj_item["id"] not in personal_ids


def test_search_unknown_space_404(client: TestClient):
    resp = client.get(
        "/api/search",
        params={"query": "知识图谱", "space_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 404


def test_search_excludes_archived(client: TestClient):
    item = _create(client, "知识图谱归档", "归档内容")
    # 草稿改 archived 直接应用（非重要变更）
    assert client.patch(f"/api/knowledge/{item['id']}", json={"status": "archived"}).status_code == 200
    body = client.get("/api/search", params={"query": "知识图谱"}).json()
    assert item["id"] not in [r["item_id"] for r in body["results"]]


def test_search_mode_vector_without_embed_degrades(client: TestClient):
    _create(client, "知识图谱", "内容")
    body = client.get("/api/search", params={"query": "知识图谱", "mode": "vector"}).json()
    assert body["embed_capability"] == "not_configured"
    assert body["mode"] == "fts"


def test_reindex_backfill(client: TestClient):
    _create(client, "知识图谱甲", "内容甲")
    _create(client, "知识图谱乙", "内容乙")
    body = client.post("/api/search/reindex").json()
    assert body["indexed"] == 2
    assert body["embed_capability"] == "not_configured"
    search = client.get("/api/search", params={"query": "知识图谱"}).json()
    assert search["count"] == 2


def test_search_hybrid_with_embedder_supported(client: TestClient):
    client.app.dependency_overrides[get_embedder] = lambda: FakeEmbedder()
    try:
        item = _create(client, "知识图谱的定义", "知识图谱是一种网络结构数据模型")
        client.post("/api/search/reindex")
        body = client.get("/api/search", params={"query": "知识图谱", "mode": "hybrid"}).json()
        assert body["embed_capability"] == "supported"
        assert body["mode"] == "hybrid"
        hit = next(r for r in body["results"] if r["item_id"] == item["id"])
        assert "fts" in hit["channels"]
        assert "vector" in hit["channels"]
    finally:
        client.app.dependency_overrides.pop(get_embedder, None)


def test_search_embedder_unsupported_degrades(client: TestClient):
    client.app.dependency_overrides[get_embedder] = lambda: FailingEmbedder()
    try:
        item = _create(client, "知识图谱的定义", "知识图谱是一种网络结构数据模型")
        body = client.get("/api/search", params={"query": "知识图谱", "mode": "hybrid"}).json()
        # embed 端点不可用：如实降级仅全文，不造假
        assert body["embed_capability"] == "unsupported"
        assert body["mode"] == "fts"
        assert item["id"] in [r["item_id"] for r in body["results"]]
    finally:
        client.app.dependency_overrides.pop(get_embedder, None)


def test_health_reports_embed_adapter(client: TestClient):
    assert client.get("/api/health").json()["embed_adapter"] == "not_configured"
    settings = Settings(
        embed_base_url="https://api.example.com/v1",
        embed_api_key="k",
        embed_model="m",
        _env_file=None,
    )
    client.app.dependency_overrides[get_settings] = lambda: settings
    try:
        assert client.get("/api/health").json()["embed_adapter"] == "configured"
    finally:
        client.app.dependency_overrides.pop(get_settings, None)