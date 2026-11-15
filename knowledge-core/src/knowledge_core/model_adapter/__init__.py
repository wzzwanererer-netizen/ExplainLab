"""统一模型适配层：接口、类型、注册工厂、公共失败契约与具体供应商适配器。

业务代码只依赖 ModelAdapter 接口与公共异常契约，不依赖任何供应商 SDK。
已实现 OpenAI 兼容适配器（DeepSeek / 通义 / Kimi / 智谱 / OpenAI 等），可复用于 Nesti。
"""

from knowledge_core.model_adapter.base import ModelAdapter
from knowledge_core.model_adapter.errors import (
    AdapterAlreadyRegisteredError,
    AdapterNotFoundError,
    AuthenticationError,
    CapabilityNotSupportedError,
    MalformedResponseError,
    ModelAdapterError,
    ModelTimeoutError,
    ProviderUnavailableError,
    RateLimitError,
    is_retryable,
)
from knowledge_core.model_adapter.providers import OpenAICompatibleAdapter
from knowledge_core.model_adapter.registry import AdapterRegistry
from knowledge_core.model_adapter.types import (
    ModelCapability,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TokenUsage,
)

__all__ = [
    "AdapterAlreadyRegisteredError",
    "AdapterNotFoundError",
    "AdapterRegistry",
    "AuthenticationError",
    "CapabilityNotSupportedError",
    "MalformedResponseError",
    "ModelAdapter",
    "ModelAdapterError",
    "ModelCapability",
    "ModelMessage",
    "ModelRequest",
    "ModelResponse",
    "ModelTimeoutError",
    "OpenAICompatibleAdapter",
    "ProviderUnavailableError",
    "RateLimitError",
    "TokenUsage",
    "is_retryable",
]