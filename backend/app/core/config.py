"""应用配置：全部来自环境变量 / backend/.env，密钥绝不进入前端。

路径一致性（M0-07）：.env 与默认 SQLite 数据文件均锚定到 backend 目录，
无论从仓库根目录还是 backend 目录启动，都加载同一份 .env、指向同一个数据库，
不会因启动目录不同而创建多个数据库。空字符串环境变量视为未配置。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py 位于 backend/app/core/config.py，parents[2] 即 backend 目录。
BACKEND_DIR = Path(__file__).resolve().parents[2]
# 默认 SQLite 数据文件用绝对路径，避免相对 cwd 解析导致多库。
DEFAULT_DATABASE_URL = f"sqlite:///{(BACKEND_DIR / 'data' / 'explainlab.db').as_posix()}"

# 可选模型/向量字段：空字符串须归一为 None，避免空密钥被误判为已配置。
_OPTIONAL_MODEL_FIELDS = (
    "model_provider",
    "model_base_url",
    "model_api_key",
    "model_name",
    "embed_base_url",
    "embed_api_key",
    "embed_model",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ExplainLab"
    version: str = "0.1.0"
    environment: str = "development"

    database_url: str = DEFAULT_DATABASE_URL
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # 模型适配层：M1 接入 OpenAI 兼容供应商；密钥仅后端持有，绝不进入前端。
    # 敏感字段用 SecretStr：普通序列化（model_dump_json / repr）只输出掩码，
    # 取值须显式 .get_secret_value()，避免密钥意外进入日志或响应。
    model_provider: str | None = None
    model_base_url: str | None = None
    model_api_key: SecretStr | None = None
    model_name: str | None = None

    # M3 向量来源（独立于聊天配置）：支持 /embeddings 的 OpenAI 兼容端点。
    # 未配置时向量通道如实关闭（仅全文检索），不造假。
    embed_base_url: str | None = None
    embed_api_key: SecretStr | None = None
    embed_model: str | None = None

    @field_validator(*_OPTIONAL_MODEL_FIELDS, mode="before")
    @classmethod
    def _empty_string_to_none(cls, value: object) -> object:
        """空字符串 / 纯空白视为未配置（None）。"""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: object) -> str:
        """空值回退默认；SQLite 相对文件路径锚定到 backend 目录。

        绝对路径（POSIX 以 / 开头或 Windows 含盘符）、:memory: 与非 SQLite URL 原样保留。
        """
        if not isinstance(value, str) or not value.strip():
            return DEFAULT_DATABASE_URL
        url = value.strip()
        prefix = "sqlite:///"
        if url.startswith(prefix) and ":memory:" not in url:
            path_part = url[len(prefix) :]
            if not path_part.startswith("/") and not Path(path_part).is_absolute():
                anchored = (BACKEND_DIR / path_part).resolve()
                return f"{prefix}{anchored.as_posix()}"
        return url

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()