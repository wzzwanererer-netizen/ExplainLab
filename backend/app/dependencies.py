"""FastAPI 依赖：模型适配器注入。

未配置时如实返回 503，绝不以假数据冒充模型能力。
base_url 原样来自用户 .env 配置，不替换任何代理地址。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException

from app.core.config import Settings, get_settings
from app.services.model import build_embed_adapter, build_model_adapter
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