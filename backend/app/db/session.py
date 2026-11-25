"""数据库引擎与会话管理。

开发默认 SQLite，部署通过 DATABASE_URL 切换 PostgreSQL，
业务代码不感知方言差异。
"""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Callable, Generator, Iterator
from concurrent.futures import Future
from contextlib import contextmanager, suppress
from contextvars import ContextVar, copy_context
from pathlib import Path
from typing import TypeVar

from psycopg import Connection as PsycopgConnection
from psycopg.errors import _WaitTimeout as PsycopgWaitTimeout
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from app.core.config import Settings, get_settings

_checkout_deadline: ContextVar[float | None] = ContextVar("db_checkout_deadline", default=None)


class _BudgetQueuePool(QueuePool):
    """Keep SQLAlchemy's checkout algorithm with a per-call queue timeout."""

    @property
    def _timeout(self):
        deadline = _checkout_deadline.get()
        if deadline is None:
            return self._configured_timeout
        return min(self._configured_timeout, max(0.0, deadline - time.monotonic()))

    @_timeout.setter
    def _timeout(self, value):
        self._configured_timeout = value


class _CheckoutPsycopgConnection(PsycopgConnection):
    def wait(self, gen, interval=0.1, timeout=None):
        deadline = _checkout_deadline.get()
        if deadline is None:
            return super().wait(gen, interval=interval, timeout=timeout)
        remaining = max(0.0, deadline - time.monotonic())
        try:
            return super().wait(
                gen, interval=interval,
                timeout=remaining if timeout is None else min(remaining, timeout),
            )
        except PsycopgWaitTimeout:
            self.pgconn.finish()
            raise


@contextmanager
def checkout_budget(deadline: float):
    current = _checkout_deadline.get()
    token = _checkout_deadline.set(min(current, deadline) if current is not None else deadline)
    try:
        yield
    finally:
        _checkout_deadline.reset(token)


def create_engine_from_url(database_url: str) -> Engine:
    """按方言创建引擎。SQLite 文件库自动创建父目录。"""
    if database_url.startswith("sqlite"):
        url = make_url(database_url)
        db_path = url.database
        file_db = bool(db_path and ":memory:" not in db_path and url.query.get("mode") != "memory")
        if file_db and url.query.get("uri") != "true":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            **({"poolclass": _BudgetQueuePool} if file_db else {}),
        )

        # SQLite 默认不启用外键约束；显式开启后，模型声明的 ON DELETE CASCADE
        # 才会在删除知识条目时真正级联清理关系 / 版本 / 审核 / 来源，避免孤儿数据。
        # PostgreSQL 默认强制外键，无需此处理。
        # busy_timeout（K2）：写锁争用（重建写阶段 RESERVED→EXCLUSIVE 升级 / 并发写）
        # 时等待而非立即 SQLITE_BUSY，降低重建即失败概率；不改变事务隔离/日志模式等
        # 默认语义。SQLite 读阶段不持阻塞写者的锁，窗口②安全由步 7 P2 乐观前置保证。
        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

        return engine
    engine = create_engine(database_url, pool_pre_ping=True, poolclass=_BudgetQueuePool)
    configure_postgres_checkout(engine)
    return engine


def configure_postgres_checkout(engine: Engine) -> None:
    if engine.dialect.driver != "psycopg":
        return

    @event.listens_for(engine, "do_connect")
    def _connect_postgres(_dialect, _record, args, kwargs):
        deadline = _checkout_deadline.get()
        if deadline is None:
            return _CheckoutPsycopgConnection.connect(*args, **kwargs)
        return bounded_db_call(
            lambda: _CheckoutPsycopgConnection.connect(*args, **kwargs), deadline,
            on_abandon=_close_late_connection,
        )


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


def get_session_factory() -> sessionmaker[Session]:
    """返回会话工厂（V2 导入/身份服务需要在线程内自建多个短会话）。"""
    if _session_factory is None:
        init_db()
    assert _session_factory is not None
    return _session_factory


def create_session() -> Session:
    """创建独立会话（V2 导入协调器在锁内自建 S1，不共享请求会话）。"""
    if _session_factory is None:
        init_db()
    assert _session_factory is not None
    return _session_factory()


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


@contextmanager
def session_scope() -> Iterator[Session]:
    """非请求场景的事务上下文（启动初始化、脚本等）：自动提交 / 回滚。"""
    if _session_factory is None:
        init_db()
    assert _session_factory is not None
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

_T = TypeVar("_T")


class DatabaseDeadline(TimeoutError):
    """The database call did not finish within the caller's budget."""

    def __init__(self, *, started: bool = False):
        self.started = started


def bounded_db_call(
    operation: Callable[[], _T], deadline: float, *, on_abandon=None,
) -> _T:
    """Bound the caller's wait. Abandoned work retains resource ownership."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise DatabaseDeadline()
    result: Future[_T] = Future()
    context = copy_context()

    def run():
        try:
            result.set_result(context.run(operation))
        except BaseException as exc:
            result.set_exception(exc)

    threading.Thread(target=run, name="storage-db-call", daemon=True).start()
    try:
        return result.result(timeout=max(0.0, deadline - time.monotonic()))
    except BaseException as exc:
        # A timeout raised by the operation itself is kept in its original form.
        if isinstance(exc, TimeoutError) and result.done() and result.exception() is exc:
            raise
        if isinstance(exc, TimeoutError) or not isinstance(exc, Exception):
            if on_abandon is not None:
                result.add_done_callback(lambda done: threading.Thread(
                    target=on_abandon, args=(done,), name="storage-db-cleanup", daemon=True,
                ).start())
            if isinstance(exc, TimeoutError):
                raise DatabaseDeadline(started=True) from exc
        raise


def _close_late_connection(result: Future) -> None:
    if result.exception() is None:
        with suppress(Exception):
            result.result().close()


class SQLiteWriteTimeout(TimeoutError):
    """The caller's write transaction could not complete within its budget."""


def is_sqlite_busy(exc: OperationalError) -> bool:
    code = getattr(exc.orig, "sqlite_errorcode", None)
    if code is not None:
        return code & 0xFF in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
    message = str(exc.orig).lower()
    return "database is locked" in message or "database table is locked" in message


def _sqlite_remaining_ms(deadline: float) -> int:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise SQLiteWriteTimeout("SQLite write budget exhausted")
    return int(remaining * 1000)


@contextmanager
def sqlite_connection_budget(connection, deadline: float):
    previous_timeout = connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one()
    connection.exec_driver_sql(f"PRAGMA busy_timeout={_sqlite_remaining_ms(deadline)}")
    try:
        yield
    finally:
        connection.exec_driver_sql(f"PRAGMA busy_timeout={previous_timeout}")


@contextmanager
def _sqlite_checkout(engine, deadline: float):
    with checkout_budget(deadline):
        try:
            if isinstance(engine.pool, QueuePool) and not isinstance(engine.pool, _BudgetQueuePool):
                connection = bounded_db_call(
                    engine.connect, deadline, on_abandon=_close_late_connection,
                )
            else:
                connection = engine.connect()
        except (PoolTimeout, DatabaseDeadline) as exc:
            raise SQLiteWriteTimeout("SQLite connection checkout budget exhausted") from exc
        with connection:
            _sqlite_remaining_ms(deadline)
            yield connection


@contextmanager
def sqlite_fence_session(factory, session: Session | None, deadline: float):
    if session is None:
        with (
            _sqlite_checkout(factory.kw["bind"], deadline) as connection,
            factory(bind=connection) as reader,
            sqlite_connection_budget(connection, deadline),
        ):
            yield reader
        return
    try:
        with checkout_budget(deadline), sqlite_connection_budget(session.connection(), deadline):
            yield session
    except PoolTimeout as exc:
        raise SQLiteWriteTimeout("SQLite fencing checkout budget exhausted") from exc

def run_sqlite_write(
    factory: sessionmaker[Session],
    operation: Callable[[Session], _T],
    *,
    deadline: float,
    retry_busy: bool = True,
) -> _T:
    """Own and retry a short DB-only transaction. The callback must be replayable."""
    delay = 0.01
    while True:
        _sqlite_remaining_ms(deadline)
        try:
            with _sqlite_checkout(factory.kw["bind"], deadline) as connection:
                previous_timeout = connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one()
                try:
                    with factory(bind=connection) as session:
                        try:
                            session.connection()
                            wait_ms = _sqlite_remaining_ms(deadline) if retry_busy else 0
                            connection.exec_driver_sql(f"PRAGMA busy_timeout={wait_ms}")
                            connection.exec_driver_sql("BEGIN IMMEDIATE")
                            result = operation(session)
                            session.flush()
                            wait_ms = _sqlite_remaining_ms(deadline) if retry_busy else 0
                            connection.exec_driver_sql(f"PRAGMA busy_timeout={wait_ms}")
                            # The externally bound connection owns this transaction.
                            connection.commit()
                            return result
                        except BaseException:
                            session.rollback()
                            connection.rollback()
                            raise
                finally:
                    connection.exec_driver_sql(f"PRAGMA busy_timeout={previous_timeout}")
        except OperationalError as exc:
            if not is_sqlite_busy(exc):
                raise
            remaining = deadline - time.monotonic()
            if not retry_busy or remaining <= 0:
                raise SQLiteWriteTimeout("SQLite database remained busy") from exc
            time.sleep(min(delay, remaining))
            delay = min(delay * 2, 0.1)


def run_short_write(
    factory: sessionmaker[Session],
    operation: Callable[[Session], _T],
    *,
    is_sqlite: bool,
    deadline: float,
) -> _T:
    """Outer transaction entry point for GC database-only work."""
    if is_sqlite:
        return run_sqlite_write(factory, operation, deadline=deadline)
    with factory.begin() as session:
        return operation(session)
