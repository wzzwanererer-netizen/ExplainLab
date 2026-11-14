"""M3 迁移 0004 检索基础设施测试：FTS5 trigram 中文命中 + 触发器同步。"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command
from app.core.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture()
def engine(tmp_path, monkeypatch: pytest.MonkeyPatch):
    db_url = f"sqlite:///{tmp_path / 'retrieval.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")
    eng = create_engine(db_url)
    try:
        yield eng
    finally:
        eng.dispose()
        get_settings.cache_clear()


def _insert_item(conn, item_id: str, title: str, content: str) -> None:
    conn.execute(
        text(
            "INSERT INTO knowledge_item(id, title, content, status, created_at, updated_at) "
            "VALUES (:id, :t, :c, 'draft', '2026-11-14 00:00:00', '2026-11-14 00:00:00')"
        ),
        {"id": item_id, "t": title, "c": content},
    )
    conn.commit()


def _fts_match(conn, query: str) -> list[str]:
    rows = conn.execute(
        text("SELECT item_id FROM knowledge_fts WHERE knowledge_fts MATCH :q"),
        {"q": query},
    ).all()
    return [r[0] for r in rows]


def test_fts_trigram_chinese_and_trigger_sync(engine):
    with engine.connect() as conn:
        _insert_item(conn, "item-1", "知识图谱的定义", "知识图谱是一种网络结构数据模型")
        # 插入触发器 + trigram 中文子串命中
        assert _fts_match(conn, "知识图谱") == ["item-1"]

        # 更新触发器：title/content 同改后旧词消失、新词命中
        conn.execute(
            text("UPDATE knowledge_item SET title='搜索引擎', content='语义理解与智能问答' WHERE id='item-1'")
        )
        conn.commit()
        assert _fts_match(conn, "知识图谱") == []
        assert _fts_match(conn, "智能问答") == ["item-1"]

        # 删除触发器：rowid 对齐删除
        conn.execute(text("DELETE FROM knowledge_item WHERE id='item-1'"))
        conn.commit()
        assert _fts_match(conn, "智能问答") == []


def test_vector_table_present(engine):
    with engine.connect() as conn:
        cols = {
            r[1]
            for r in conn.execute(text("PRAGMA table_info(knowledge_vector)"))
        }
    assert {"item_id", "model", "dim", "vector", "updated_at"} <= cols