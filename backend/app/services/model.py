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