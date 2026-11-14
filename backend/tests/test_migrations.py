"""Alembic 迁移测试：在临时 SQLite 上真实执行 upgrade head。"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command
from app.core.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_upgrade_head_creates_version_table(tmp_path, monkeypatch: pytest.MonkeyPatch):
    db_url = f"sqlite:///{tmp_path / 'migrate.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    try:
        cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        command.upgrade(cfg, "head")

        engine = create_engine(db_url)
        try:
            with engine.connect() as conn:
                version = conn.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
                tables = {
                    row[0]
                    for row in conn.execute(
                        text("SELECT name FROM sqlite_master WHERE type='table'")
                    )
                }
        finally:
            engine.dispose()
        assert version == "0004_m3_retrieval"
        assert {
            "knowledge_space",
            "conversation",
            "message",
            "knowledge_item",
            "source_ref",
            "knowledge_relation",
            "knowledge_version",
            "review_request",
            "knowledge_vector",
            "knowledge_fts",
        } <= tables
    finally:
        get_settings.cache_clear()