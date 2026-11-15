"""配置解析测试：SQLite 默认、PostgreSQL 切换、环境变量覆盖、路径一致性与空值处理。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import BACKEND_DIR, DEFAULT_DATABASE_URL, Settings, get_settings


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


def test_secret_keys_masked_in_serialization():
    """M0-02：敏感配置用 SecretStr，普通序列化/repr 不暴露真实密钥。"""
    settings = Settings(
        model_api_key="sk-model-real-secret",
        embed_api_key="sk-embed-real-secret",
        _env_file=None,
    )
    # 取值须显式 get_secret_value
    assert settings.model_api_key is not None
    assert settings.model_api_key.get_secret_value() == "sk-model-real-secret"
    assert settings.embed_api_key is not None
    assert settings.embed_api_key.get_secret_value() == "sk-embed-real-secret"
    # JSON 序列化与 repr 均不得出现真实密钥
    dumped = settings.model_dump_json()
    assert "sk-model-real-secret" not in dumped
    assert "sk-embed-real-secret" not in dumped
    assert "sk-model-real-secret" not in repr(settings)
    assert "sk-embed-real-secret" not in repr(settings)


def test_secret_keys_absent_when_unset():
    settings = Settings(_env_file=None)
    assert settings.model_api_key is None
    assert settings.embed_api_key is None


# --- M0-07：路径一致性与空值处理 ---


def test_env_file_anchored_to_backend_dir():
    """.env 路径锚定 backend 目录（绝对），与启动 cwd 无关。"""
    env_file = Settings.model_config["env_file"]
    assert Path(env_file).is_absolute()
    assert Path(env_file) == BACKEND_DIR / ".env"


def test_default_sqlite_path_is_absolute_and_anchored(monkeypatch: pytest.MonkeyPatch):
    """默认 SQLite 数据文件是 backend/data 下的绝对路径，不随 cwd 漂移。"""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.is_sqlite
    path_part = settings.database_url.removeprefix("sqlite:///")
    assert Path(path_part).is_absolute()
    assert Path(path_part) == BACKEND_DIR / "data" / "explainlab.db"


def test_relative_sqlite_url_independent_of_cwd(monkeypatch: pytest.MonkeyPatch):
    """相对 SQLite URL 锚定 backend：从仓库根目录与 backend 目录构造结果一致。

    这是「不得因启动目录不同创建多个数据库」的核心回归。
    """
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/explainlab.db")
    monkeypatch.chdir(BACKEND_DIR)
    from_backend = Settings(_env_file=None)
    monkeypatch.chdir(BACKEND_DIR.parent)  # 仓库根目录
    from_root = Settings(_env_file=None)
    assert from_backend.database_url == from_root.database_url
    path_part = from_backend.database_url.removeprefix("sqlite:///")
    assert Path(path_part).is_absolute()
    assert Path(path_part) == BACKEND_DIR / "data" / "explainlab.db"


def test_empty_model_env_treated_as_unconfigured(monkeypatch: pytest.MonkeyPatch):
    """空字符串 / 纯空白的模型与向量环境变量视为未配置（None）。"""
    monkeypatch.setenv("MODEL_PROVIDER", "")
    monkeypatch.setenv("MODEL_BASE_URL", "   ")
    monkeypatch.setenv("MODEL_API_KEY", "")
    monkeypatch.setenv("MODEL_NAME", "")
    monkeypatch.setenv("EMBED_BASE_URL", "")
    monkeypatch.setenv("EMBED_API_KEY", "")
    monkeypatch.setenv("EMBED_MODEL", "")
    settings = Settings(_env_file=None)
    assert settings.model_provider is None
    assert settings.model_base_url is None
    assert settings.model_api_key is None
    assert settings.model_name is None
    assert settings.embed_base_url is None
    assert settings.embed_api_key is None
    assert settings.embed_model is None


def test_empty_database_url_falls_back_to_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", "")
    settings = Settings(_env_file=None)
    assert settings.database_url == DEFAULT_DATABASE_URL
    assert settings.is_sqlite


def test_memory_sqlite_url_preserved(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    assert Settings(_env_file=None).database_url == "sqlite:///:memory:"


def test_absolute_sqlite_url_preserved(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    url = f"sqlite:///{(tmp_path / 'abs.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    assert Settings(_env_file=None).database_url == url


def test_engine_creates_data_dir_for_absolute_sqlite(tmp_path: Path):
    """数据目录创建：绝对 SQLite 路径的父目录被自动创建，与 cwd 无关。"""
    from app.db.session import create_engine_from_url

    db_file = tmp_path / "nested" / "data" / "x.db"
    engine = create_engine_from_url(f"sqlite:///{db_file.as_posix()}")
    try:
        assert db_file.parent.is_dir()
    finally:
        engine.dispose()