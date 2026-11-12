"""健康检查 API 测试：真实数据库探测，非 mock。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_health_ok(client: TestClient):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["app"] == "ExplainLab"
    assert body["database"]["connected"] is True
    assert body["database"]["dialect"] == "sqlite"
    assert body["database"]["error"] is None
    assert body["model_adapter"] == "not_configured"
    assert body["timestamp"]


def test_health_degraded_when_db_unreachable():
    # 指向一个必然拒绝连接的地址（无需真实 PostgreSQL 服务器）
    settings = Settings(
        database_url="postgresql+psycopg://u:p@127.0.0.1:1/nodb?connect_timeout=1",
        _env_file=None,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["database"]["connected"] is False
    assert body["database"]["dialect"] == "postgresql"
    assert body["database"]["error"]


def test_health_reports_configured_provider(client: TestClient):
    # 通过依赖覆盖注入"已配置供应商"的真实配置路径
    from app.core.config import get_settings

    settings = Settings(model_provider="dummy-provider", _env_file=None)
    client.app.dependency_overrides[get_settings] = lambda: settings  # type: ignore[attr-defined]
    body = client.get("/api/health").json()
    assert body["model_adapter"] == "dummy-provider"