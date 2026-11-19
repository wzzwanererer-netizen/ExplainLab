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
        assert version == "0006_v2_markdown_kb"
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
            "experiment_session",
            "experiment_attempt",
            # V2 A1（迁移 0006，additive）
            "tag",
            "item_tag",
            "knowledge_link",
            "attachment",
            "tag_change_log",
            "gc_task",
            "import_origin",
            "storage_lock",
        } <= tables
    finally:
        get_settings.cache_clear()


def test_upgrade_head_adds_v2_item_columns(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """0006 为 knowledge_item 增 extra_metadata（默认 '{}'）与来源身份列，旧列不变。"""
    db_url = f"sqlite:///{tmp_path / 'migrate_cols.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    try:
        cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        command.upgrade(cfg, "head")
        engine = create_engine(db_url)
        try:
            with engine.connect() as conn:
                columns = {
                    row[1]: row
                    for row in conn.execute(text("PRAGMA table_info(knowledge_item)"))
                }
        finally:
            engine.dispose()
        assert {
            "id",
            "space_id",
            "title",
            "content",
            "status",
            "created_at",
            "updated_at",
            "extra_metadata",
            "source_payload_hash",
            "source_content_hash",
            "source_instance_id",
        } <= set(columns)
        # extra_metadata NOT NULL 且默认 '{}'（旧行无损）
        assert columns["extra_metadata"][3] == 1  # notnull
        assert "'{}'" in str(columns["extra_metadata"][4])
        for name in ("source_payload_hash", "source_content_hash", "source_instance_id"):
            assert columns[name][3] == 0  # nullable
    finally:
        get_settings.cache_clear()


def test_downgrade_to_0005_and_upgrade_again(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """0006 可 downgrade（删表+删列）再 upgrade；FTS5 触发器与 rowid 对齐不被破坏。

    刻意验证原生 DROP COLUMN 路径：batch 重建表会丢失 M3 触发器并重排 rowid。
    """
    db_url = f"sqlite:///{tmp_path / 'migrate_roundtrip.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    try:
        cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        command.upgrade(cfg, "head")
        engine = create_engine(db_url)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO knowledge_item (id, title, content, status, created_at, updated_at) "
                        "VALUES ('item-1', 'knowledge graph', 'network structure', 'active', "
                        "'2026-11-18 00:00:00', '2026-11-18 00:00:00')"
                    )
                )
            with engine.connect() as conn:
                triggers_before = {
                    row[0]
                    for row in conn.execute(
                        text("SELECT name FROM sqlite_master WHERE type='trigger'")
                    )
                }
                rowid_before = conn.execute(
                    text("SELECT rowid FROM knowledge_item WHERE id='item-1'")
                ).scalar_one()
                fts_before = conn.execute(
                    text("SELECT count(*) FROM knowledge_fts WHERE knowledge_fts MATCH 'graph'")
                ).scalar_one()
            assert {"knowledge_item_ai", "knowledge_item_au", "knowledge_item_ad"} <= triggers_before
            assert fts_before == 1

            command.downgrade(cfg, "0005_m5_experiments")
            with engine.connect() as conn:
                tables = {
                    row[0]
                    for row in conn.execute(
                        text("SELECT name FROM sqlite_master WHERE type='table'")
                    )
                }
                columns = {
                    row[1] for row in conn.execute(text("PRAGMA table_info(knowledge_item)"))
                }
                triggers_after = {
                    row[0]
                    for row in conn.execute(
                        text("SELECT name FROM sqlite_master WHERE type='trigger'")
                    )
                }
                rowid_after = conn.execute(
                    text("SELECT rowid FROM knowledge_item WHERE id='item-1'")
                ).scalar_one()
                version = conn.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
            assert version == "0005_m5_experiments"
            assert not {
                "tag",
                "item_tag",
                "knowledge_link",
                "attachment",
                "tag_change_log",
                "gc_task",
                "import_origin",
                "storage_lock",
            } & tables
            assert not {
                "extra_metadata",
                "source_payload_hash",
                "source_content_hash",
                "source_instance_id",
            } & columns
            # 关键：触发器与 rowid 均未因降级而丢失/重排
            assert triggers_after == triggers_before
            assert rowid_after == rowid_before

            command.upgrade(cfg, "head")
            with engine.connect() as conn:
                columns = {
                    row[1] for row in conn.execute(text("PRAGMA table_info(knowledge_item)"))
                }
                extra = conn.execute(
                    text("SELECT extra_metadata FROM knowledge_item WHERE id='item-1'")
                ).scalar_one()
                fts_hits = conn.execute(
                    text("SELECT count(*) FROM knowledge_fts WHERE knowledge_fts MATCH 'graph'")
                ).scalar_one()
                # 降级期间触发器仍在：新增条目继续入索引
                conn.execute(
                    text(
                        "INSERT INTO knowledge_item (id, title, content, status, created_at, updated_at) "
                        "VALUES ('item-2', 'search engine', 'semantic understanding', 'active', "
                        "'2026-11-18 00:00:00', '2026-11-18 00:00:00')"
                    )
                )
                fts_new = conn.execute(
                    text("SELECT count(*) FROM knowledge_fts WHERE knowledge_fts MATCH 'semantic'")
                ).scalar_one()
            assert "extra_metadata" in columns
            assert extra == "{}"  # 旧行无损回填
            assert fts_hits == 1
            assert fts_new == 1
        finally:
            engine.dispose()
    finally:
        get_settings.cache_clear()