"""模型适配器装配。

从后端配置构建 ModelAdapter；base_url 原样取自配置（用户 .env 的真实地址），
不替换任何代理。未配置时返回 None，由依赖层翻译为 503。
"""

from __future__ import annotations

from app.core.config import Settings
from knowledge_core.model_adapter import ModelAdapter, OpenAICompatibleAdapter


def build_model_adapter(settings: Settings) -> ModelAdapter | None:
    """按配置构建适配器；当前支持 openai-compatible。"""
    if (
        settings.model_provider == "openai-compatible"
        and settings.model_base_url
        and settings.model_api_key
        and settings.model_name
    ):
        return OpenAICompatibleAdapter(
            base_url=settings.model_base_url,
            api_key=settings.model_api_key,
            default_model=settings.model_name,
            provider_name=settings.model_provider,
        )
    return None


def build_embed_adapter(settings: Settings) -> ModelAdapter | None:
    """M3 向量适配器：独立 EMBED_* 配置，复用 OpenAI 兼容适配器（embed_model 注入）。

    未配置返回 None，向量通道如实关闭；base_url 原样使用，不替换代理。
    """
    if settings.embed_base_url and settings.embed_api_key and settings.embed_model:
        return OpenAICompatibleAdapter(
            base_url=settings.embed_base_url,
            api_key=settings.embed_api_key,
            default_model=settings.embed_model,
            embed_model=settings.embed_model,
            provider_name="embed",
        )
    return None