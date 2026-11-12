"""数据库引擎工厂与 FTS5 能力测试。"""

from __future__ import annotations

from sqlalchemy import create_engine, text

from app.db.session import create_engine_from_url


def test_sqlite_engine_factory():
    engine = create_engine_from_url("sqlite:///:memory:")
    try:
        assert engine.dialect.name == "sqlite"
        with engine.connect() as conn:
            assert conn.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        engine.dispose()


def test_sqlite_file_engine_creates_parent_dir(tmp_path):
    db_file = tmp_path / "nested" / "dir" / "test.db"
    engine = create_engine_from_url(f"sqlite:///{db_file}")
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        assert db_file.exists()
    finally:
        engine.dispose()


def test_postgresql_engine_factory_without_connection():
    # 仅验证方言与驱动可装配，不建立真实连接（M0 不安装 PG 服务器）
    engine = create_engine_from_url("postgresql+psycopg://u:p@localhost:5432/explainlab")
    try:
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "psycopg"
    finally:
        engine.dispose()


def test_sqlite_fts5_capability():
    """开发阶段全文检索依赖 FTS5，此处实测其可用。"""
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE VIRTUAL TABLE fts_test USING fts5(content)"))
            conn.execute(
                text("INSERT INTO fts_test(content) VALUES ('ExplainLab knowledge management')")
            )
            conn.commit()
            rows = conn.execute(
                text("SELECT content FROM fts_test WHERE fts_test MATCH 'knowledge'")
            ).all()
        assert len(rows) == 1
    finally:
        engine.dispose()