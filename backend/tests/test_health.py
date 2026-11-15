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


def test_health_timeout_returns_stable_code(client: TestClient):
    """M0-02：数据库连接超时 → 稳定错误码 database_timeout，不外泄异常文本。"""
    from types import SimpleNamespace

    from app.db.session import get_session

    class _TimeoutSession:
        bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

        def execute(self, *args, **kwargs):
            raise TimeoutError("connection timed out")

    client.app.dependency_overrides[get_session] = lambda: _TimeoutSession()  # type: ignore[attr-defined]
    try:
        body = client.get("/api/health").json()
    finally:
        client.app.dependency_overrides.pop(get_session, None)  # type: ignore[attr-defined]
    assert body["status"] == "degraded"
    assert body["database"]["connected"] is False
    assert body["database"]["error"] == "database_timeout"
    assert "timed out" not in client.get("/api/health").text


def test_health_unavailable_returns_stable_code():
    """M0-02：数据库不可用 → 稳定错误码 database_unavailable（非 str(exc)）。"""
    settings = Settings(
        database_url="postgresql+psycopg://u:p@127.0.0.1:1/nodb?connect_timeout=1",
        _env_file=None,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        body = client.get("/api/health").json()
    assert body["status"] == "degraded"
    assert body["database"]["error"] == "database_unavailable"


def test_health_error_does_not_leak_sensitive_details():
    """M0-02：响应不得包含主机、端口、密码、用户名或底层异常文本。"""
    settings = Settings(
        database_url=(
            "postgresql+psycopg://secretuser:SuperSecret123@127.0.0.1:1/nodb"
            "?connect_timeout=1"
        ),
        _env_file=None,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        resp = client.get("/api/health")
    assert resp.status_code == 200
    text = resp.text
    body = resp.json()
    assert body["database"]["error"] == "database_unavailable"
    for leak in (
        "SuperSecret123",  # 密码
        "secretuser",  # 用户名
        "127.0.0.1",  # 主机
        "127.0.0.1:1",  # 主机:端口
        "OperationalError",  # 底层异常类型
        "could not connect",  # 底层异常文本
        "Traceback",
    ):
        assert leak not in text, f"健康响应泄露敏感信息: {leak}"