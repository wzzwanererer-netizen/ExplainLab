"""数据库引擎与会话管理。

开发默认 SQLite，部署通过 DATABASE_URL 切换 PostgreSQL，
业务代码不感知方言差异。
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


def create_engine_from_url(database_url: str) -> Engine:
    """按方言创建引擎。SQLite 文件库自动创建父目录。"""
    if database_url.startswith("sqlite"):
        if database_url.startswith("sqlite:///") and ":memory:" not in database_url:
            db_path = database_url.removeprefix("sqlite:///")
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
    return create_engine(database_url, pool_pre_ping=True)


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def init_db(settings: Settings | None = None) -> Engine:
    """初始化引擎与会话工厂（应用启动时调用）。"""
    global _engine, _session_factory
    settings = settings if settings is not None else get_settings()
    _engine = create_engine_from_url(settings.database_url)
    _session_factory = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def dispose_db() -> None:
    """释放连接池并重置全局状态（应用关闭 / 测试隔离时调用）。"""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def get_engine() -> Engine:
    if _engine is None:
        init_db()
    assert _engine is not None
    return _engine


def get_session() -> Generator[Session, None, None]:
    """FastAPI 依赖：每个请求一个会话。"""
    if _session_factory is None:
        init_db()
    assert _session_factory is not None
    session = _session_factory()
    try:
        yield session
    finally:
        session.close()