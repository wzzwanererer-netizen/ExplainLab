"""Alembic 迁移环境。

数据库 URL 与方言参数统一来自应用配置，保证迁移与运行时一致。
SQLite 下启用 batch 模式以兼容 ALTER TABLE。
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import Connection

import app.models  # noqa: F401  # 注册 ORM 模型到 Base.metadata
from alembic import context
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import create_engine_from_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
# Alembic 的 Config 基于 ConfigParser，会对 % 做插值：含百分号编码（如 %40 / %25）
# 的 PostgreSQL URL 原样写入会触发 InterpolationSyntaxError。写入前转义 % -> %%，
# ConfigParser 读回时自动还原为原值；下方传给 configure / engine 的 URL 仍用原值，
# 不经 ConfigParser，不受影响。此处不记录 URL（可能含密码），避免敏感信息进入日志。
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

target_metadata = Base.metadata


def _include_name(name: str | None, type_: str, parent_names: dict) -> bool:
    """FTS5 虚表及其影子表由迁移 raw SQL 管理，不参与 autogenerate 比对。"""
    return not (type_ == "table" and name is not None and name.startswith("knowledge_fts"))


def _configure(connection: Connection | None = None, *, url: str | None = None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        render_as_batch=settings.is_sqlite,
        compare_type=True,
        include_name=_include_name,
    )


def run_migrations_offline() -> None:
    _configure(url=settings.database_url)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine_from_url(settings.database_url)
    try:
        with connectable.connect() as connection:
            _configure(connection=connection)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()