"""模型与 API Key 设置接口单元测试（验证脱敏与 .env 安全热更新）。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_model_settings_masks_secret_and_hot_reloads(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("# 初始配置\nMODEL_PROVIDER=openai-compatible\n", encoding="utf-8")
    settings = Settings(
        _env_file=str(env_file),  # type: ignore[call-arg]
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        data_dir=tmp_path / "data",
    )
    app = create_app(settings)
    app.state.env_file_path = env_file

    with TestClient(app) as client:
        r0 = client.get("/api/settings/models")
        assert r0.status_code == 200
        assert r0.json()["model_api_key_set"] is False

        secret_key = "sk-test-secret-9876543210abcd"
        r1 = client.put(
            "/api/settings/models",
            json={
                "model_base_url": "https://api.deepseek.com/v1",
                "model_name": "deepseek-chat",
                "model_api_key": secret_key,
            },
        )
        assert r1.status_code == 200
        body = r1.json()
        assert body["model_api_key_set"] is True
        assert body["model_api_key_masked"] == "sk-t****abcd"
        # 绝不向前端回传明文密钥
        assert secret_key not in r1.text
        assert "# 初始配置" in env_file.read_text(encoding="utf-8")

        # 留空 Key 更新模型名，原有密钥必须保留
        r2 = client.put(
            "/api/settings/models",
            json={"model_name": "deepseek-reasoner"},
        )
        assert r2.status_code == 200
        assert r2.json()["model_name"] == "deepseek-reasoner"
        assert r2.json()["model_api_key_set"] is True
        assert r2.json()["model_api_key_masked"] == "sk-t****abcd"
