"""FastAPI 依赖：模型适配器注入。

未配置时如实返回 503，绝不以假数据冒充模型能力。
base_url 原样来自用户 .env 配置，不替换任何代理地址。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from app.core.config import Settings, get_settings
from app.services.markdown import MarkdownService
from app.services.model import build_embed_adapter, build_model_adapter
from app.services.source_identity import SourceIdentityService
from knowledge_core.model_adapter import ModelAdapter
from knowledge_core.ports import Embedder


def get_model_adapter(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ModelAdapter:
    adapter = build_model_adapter(settings)
    if adapter is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "模型未配置：请在 backend/.env 设置 "
                "MODEL_PROVIDER、MODEL_BASE_URL、MODEL_API_KEY、MODEL_NAME"
            ),
        )
    return adapter


def get_embedder(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Embedder | None:
    """M3 向量化器（可选）。未配置返回 None，向量通道如实关闭，不报 503。"""
    return build_embed_adapter(settings)


def get_model_adapter_optional(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ModelAdapter | None:
    """M5 实验用可选适配器。未配置返回 None：学习路径仍可用，
    测验/对比由 Core 抛 ModelRequiredError，路由层翻译为 503。"""
    return build_model_adapter(settings)

def get_identity_service(request: Request) -> SourceIdentityService:
    service = getattr(request.app.state, "source_identity", None)
    if service is None:
        raise HTTPException(status_code=503, detail="identity_service_unavailable")
    return service


def get_markdown_service(request: Request) -> MarkdownService:
    service = getattr(request.app.state, "markdown_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="markdown_service_unavailable")
    return service
