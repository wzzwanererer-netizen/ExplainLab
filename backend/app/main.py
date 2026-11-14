"""FastAPI 应用工厂。

backend 只做 API 层；知识业务逻辑全部在 knowledge-core。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.conversations import router as conversations_router
from app.api.routes.experiments import router as experiments_router
from app.api.routes.governance import router as governance_router
from app.api.routes.graph import router as graph_router
from app.api.routes.health import router as health_router
from app.api.routes.knowledge import router as knowledge_router
from app.api.routes.search import router as search_router
from app.api.routes.spaces import router as spaces_router
from app.core.config import Settings, get_settings
from app.db.session import dispose_db, init_db, session_scope
from app.services.spaces import ensure_default_space

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        init_db(settings)
        try:
            with session_scope() as session:
                ensure_default_space(session)
        except Exception:
            # 数据库暂不可达时不阻断启动；/api/health 会如实报告 degraded，
            # 默认空间在数据库恢复后的下次启动时幂等补建。
            logger.warning("默认知识空间初始化失败，将在下次启动时重试", exc_info=True)
        yield
        dispose_db()

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
    application.include_router(knowledge_router, prefix="/api")
    application.include_router(governance_router, prefix="/api")
    application.include_router(search_router, prefix="/api")
    application.include_router(graph_router, prefix="/api")
    application.include_router(experiments_router, prefix="/api")
    # 允许测试注入独立配置
    application.dependency_overrides[get_settings] = lambda: settings
    return application


app = create_app()