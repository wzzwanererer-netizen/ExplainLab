"""Alembic 迁移环境。

数据库 URL 与方言参数统一来自应用配置，保证迁移与运行时一致。
SQLite 下启用 batch 模式以兼容 ALTER TABLE。
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import Connection

from alembic import context
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import create_engine_from_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def _configure(connection: Connection | None = None, *, url: str | None = None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        render_as_batch=settings.is_sqlite,
        compare_type=True,
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