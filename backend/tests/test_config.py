"""配置解析测试：SQLite 默认、PostgreSQL 切换、环境变量覆盖。"""

from __future__ import annotations

import pytest

from app.core.config import Settings, get_settings


def test_default_is_sqlite(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.is_sqlite
    assert settings.database_url.startswith("sqlite")


def test_postgresql_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/explainlab"
    )
    settings = Settings(_env_file=None)
    assert not settings.is_sqlite
    assert settings.database_url.startswith("postgresql+psycopg://")


def test_env_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MODEL_PROVIDER", "some-provider")
    monkeypatch.setenv("ENVIRONMENT", "testing")
    settings = Settings(_env_file=None)
    assert settings.model_provider == "some-provider"
    assert settings.environment == "testing"


def test_model_adapter_unconfigured_by_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    settings = Settings(_env_file=None)
    assert settings.model_provider is None


def test_get_settings_cached():
    get_settings.cache_clear()
    try:
        assert get_settings() is get_settings()
    finally:
        get_settings.cache_clear()