"""M0-01：Alembic 连接 URL 百分号编码处理与方言正确性（离线迁移）。

ConfigParser 会对 % 插值，含 %40 / %25 的 PostgreSQL URL 原样写入 env.py 的
set_main_option 会触发 InterpolationSyntaxError。修复后写入前转义 % -> %%。
本测试用真实 Alembic 离线迁移验证：普通 / 编码 URL 均成功，且 SQL 方言正确。
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command
from app.core.config import get_settings

BACKEND = Path(__file__).resolve().parents[1]


def _offline_sql(database_url: str, revision: str = "0003_m2_governance") -> str:
    """以给定 DATABASE_URL 跑离线迁移，返回生成的 SQL（不连接真实数据库）。"""
    os.environ["DATABASE_URL"] = database_url
    get_settings.cache_clear()
    try:
        cfg = Config(str(BACKEND / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND / "alembic"))
        buf = io.StringIO()
        cfg.output_buffer = buf
        command.upgrade(cfg, revision, sql=True)
        return buf.getvalue()
    finally:
        get_settings.cache_clear()
        os.environ.pop("DATABASE_URL", None)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://user:pass@localhost:5432/explainlab",
        "postgresql+psycopg://user:p%40ss@localhost:5432/explainlab",
        "postgresql+psycopg://user:p%25ss@localhost:5432/explainlab",
        "postgresql+psycopg://user:p%40%25ss@db.internal:5432/explainlab",
    ],
)
def test_pg_url_offline_migration(url: str) -> None:
    """普通与含百分号编码的 PG URL 都能离线迁移，且渲染 PG 方言。"""
    sql = _offline_sql(url)
    assert "CREATE TABLE" in sql
    assert "TIMESTAMP WITH TIME ZONE" in sql  # PostgreSQL 方言
    assert "DATETIME" not in sql  # 不得混入 SQLite 方言


def test_sqlite_url_offline_migration() -> None:
    """SQLite URL 离线迁移渲染 SQLite 方言。"""
    sql = _offline_sql("sqlite:///./data/m0_01_test.db")
    assert "CREATE TABLE" in sql
    assert "DATETIME" in sql  # SQLite 方言
    assert "TIMESTAMP WITH TIME ZONE" not in sql


def test_percent_url_roundtrips_through_configparser() -> None:
    """转义机制：%% 写入后 ConfigParser 读回应还原为原始 URL（含 %40/%25）。"""
    cfg = Config()
    url = "postgresql+psycopg://u:p%40%25ss@h:5432/db"
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    assert cfg.get_main_option("sqlalchemy.url") == url