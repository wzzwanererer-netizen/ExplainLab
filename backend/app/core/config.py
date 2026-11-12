"""应用配置：全部来自环境变量 / backend/.env，密钥绝不进入前端。"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ExplainLab"
    version: str = "0.1.0"
    environment: str = "development"

    database_url: str = "sqlite:///./data/explainlab.db"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # 模型适配层：M0 不接入具体供应商，仅保留配置位
    model_provider: str | None = None
    model_api_key: str | None = None

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()