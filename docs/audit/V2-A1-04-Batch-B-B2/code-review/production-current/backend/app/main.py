"""FastAPI 应用工厂。

backend 只做 API 层；知识业务逻辑全部在 knowledge-core。
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes.attachments import router as attachments_router
from app.api.routes.conversations import router as conversations_router
from app.api.routes.experiments import router as experiments_router
from app.api.routes.governance import router as governance_router
from app.api.routes.graph import router as graph_router
from app.api.routes.health import router as health_router
from app.api.routes.import_export import router as import_export_router
from app.api.routes.knowledge import router as knowledge_router
from app.api.routes.links import router as links_router
from app.api.routes.search import router as search_router
from app.api.routes.spaces import router as spaces_router
from app.core.config import Settings, get_settings
from app.db.process_lock import ProcessLock
from app.db.session import (
    dispose_db,
    get_session_factory,
    init_db,
    run_short_write,
    session_scope,
)
from app.db.storage_lock import build_storage_lock
from app.services.attachment_storage import preflight_storage_roots, validate_storage_roots
from app.services.attachments import AttachmentService
from app.services.import_coordinator import ImportCoordinator
from app.services.markdown import MarkdownService
from app.services.repositories_v2 import SQLAlchemyGcTaskRepository
from app.services.source_identity import SourceIdentityService
from app.services.source_instance_id import SourceInstanceIdStore
from app.services.spaces import ensure_default_space

logger = logging.getLogger(__name__)


def _configured_workers() -> int:
    """尽力识别多 worker 启动；A1-04 仅允许单 Backend 单 worker。"""
    candidates: list[str] = []
    args = sys.argv[1:]
    for index, arg in enumerate(args):
        if arg == "--workers" and index + 1 < len(args):
            candidates.append(args[index + 1])
        elif arg.startswith("--workers="):
            candidates.append(arg.split("=", 1)[1])
    for key in ("WEB_CONCURRENCY", "UVICORN_WORKERS"):
        value = os.environ.get(key)
        if value:
            candidates.append(value)
    for value in candidates:
        try:
            if int(value) > 1:
                return int(value)
        except ValueError:
            continue
    return 1


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if _configured_workers() > 1:
            raise RuntimeError("MULTI_WORKER_UNSUPPORTED")
        preflight_storage_roots(settings)
        init_db(settings)
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        # 单实例 OS 锁必须先于 source-instance-id 生成与任何导入/身份写操作。
        lock = ProcessLock(settings.data_dir)
        lock.acquire()
        try:
            # Batch B：附件根必须真实存在、互不重叠、非链接且同卷；失败拒绝启动。
            attachment_storage = validate_storage_roots(settings)
            application.state.attachment_storage = attachment_storage
            # 方言装配：SQLite 租约锁 / PostgreSQL advisory 锁（不提交业务事务）。
            storage_key_lock = build_storage_lock(settings)
            application.state.storage_key_lock = storage_key_lock
            application.state.attachment_service = AttachmentService(
                session_factory=get_session_factory(),
                layout=attachment_storage,
                storage_lock=storage_key_lock,
                max_bytes=settings.attachment_max_bytes,
                mime_allowlist=settings.attachment_mime_allowlist,
                lock_ttl_seconds=settings.storage_lock_ttl_seconds,
                lock_wait_seconds=settings.storage_lock_wait_seconds,
                lock_heartbeat_seconds=settings.storage_lock_heartbeat_seconds,
                gc_max_attempts=settings.gc_max_attempts,
                gc_quarantine_seconds=settings.gc_quarantine_seconds,
            )
            application.state.gc_task_repository_factory = partial(
                SQLAlchemyGcTaskRepository, max_attempts=settings.gc_max_attempts,
                quarantine_seconds=settings.gc_quarantine_seconds,
            )
            application.state.gc_task_write_transaction = partial(
                run_short_write, get_session_factory(), is_sqlite=settings.is_sqlite,
            )
            instance_store = SourceInstanceIdStore(settings.data_dir)
            instance_store.ensure()
            coordinator = ImportCoordinator(
                wait_seconds=settings.import_lock_wait_seconds
            )
            identity = SourceIdentityService(
                get_session_factory(), settings.data_dir, instance_store
            )
            # 启动即过 Journal 恢复门；数据库暂不可达时保持 503，导入入口会再次恢复。
            try:
                identity.recover_if_needed()
            except SQLAlchemyError:
                logger.warning("启动时数据库不可达，身份 Journal 恢复延后")
            markdown_service = MarkdownService(
                get_session_factory(), coordinator, identity, instance_store
            )
            application.state.process_lock = lock
            application.state.import_coordinator = coordinator
            application.state.source_identity = identity
            application.state.source_instance_store = instance_store
            application.state.markdown_service = markdown_service
            try:
                with session_scope() as session:
                    ensure_default_space(session)
            except Exception:
                # 数据库暂不可达时不阻断启动；/api/health 会如实报告 degraded，
                # 默认空间在数据库恢复后的下次启动时幂等补建。
                logger.warning("默认知识空间初始化失败，将在下次启动时重试", exc_info=True)
            yield
        finally:
            dispose_db()
            lock.release()

    application = FastAPI(
        title=settings.app_name,
        version=settings.version,
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health_router, prefix="/api")
    application.include_router(spaces_router, prefix="/api")
    application.include_router(conversations_router, prefix="/api")
    # A1-03（R11）：links 静态字面路径须先于 knowledge 的 {item_id} 动态段注册。
    application.include_router(links_router, prefix="/api")
    # A1-04：/knowledge/import、/knowledge/export 静态段亦须先于 {item_id}。
    application.include_router(import_export_router, prefix="/api")
    application.include_router(attachments_router, prefix="/api")
    application.include_router(knowledge_router, prefix="/api")
    application.include_router(governance_router, prefix="/api")
    application.include_router(search_router, prefix="/api")
    application.include_router(graph_router, prefix="/api")
    application.include_router(experiments_router, prefix="/api")
    # 允许测试注入独立配置
    application.dependency_overrides[get_settings] = lambda: settings
    return application


app = create_app()