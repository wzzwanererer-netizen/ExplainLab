"""健康检查：真实探测数据库连通性，如实报告模型适配层配置状态。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.services.model import build_embed_adapter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class DatabaseHealth(BaseModel):
    connected: bool
    dialect: str
    error: str | None = None


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    environment: str
    database: DatabaseHealth
    model_adapter: str
    # M3 向量来源配置态（与 model_adapter 同为配置态，不做每次网络探测）：
    # configured / not_configured。端点是否真正支持 /embeddings（supported/unsupported）
    # 由只读探测脚本 scripts/probe_embed.py、/api/search/reindex 与检索降级如实判定。
    embed_adapter: str
    timestamp: datetime


@router.get("/health", response_model=HealthResponse)
def health(
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthResponse:
    dialect = session.bind.dialect.name if session.bind is not None else "unknown"
    try:
        session.execute(text("SELECT 1"))
        database = DatabaseHealth(connected=True, dialect=dialect)
        status = "ok"
    except Exception as exc:  # noqa: BLE001 - 健康检查必须吞掉所有连接异常并如实上报
        # 对外只返回稳定、明确的错误码，绝不外泄 str(exc)（可能含主机/端口/密码/DSN）。
        # 服务端保留脱敏诊断日志：仅记录异常类型名，不记录可能含敏感信息的消息文本。
        if isinstance(exc, (TimeoutError, PoolTimeoutError)):
            error_code = "database_timeout"
        else:
            error_code = "database_unavailable"
        logger.warning("健康检查数据库探测失败（异常类型=%s）", type(exc).__name__)
        database = DatabaseHealth(connected=False, dialect=dialect, error=error_code)
        status = "degraded"

    return HealthResponse(
        status=status,
        app=settings.app_name,
        version=settings.version,
        environment=settings.environment,
        database=database,
        model_adapter=settings.model_provider or "not_configured",
        embed_adapter="configured" if build_embed_adapter(settings) else "not_configured",
        timestamp=datetime.now(UTC),
    )