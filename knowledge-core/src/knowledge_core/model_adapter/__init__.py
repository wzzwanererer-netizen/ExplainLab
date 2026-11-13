"""统一模型适配层：接口、类型、注册工厂与具体供应商适配器。

M0 建立接口；M1 增加 OpenAI 兼容适配器。业务代码只依赖 ModelAdapter 接口。
"""

from knowledge_core.model_adapter.base import ModelAdapter
from knowledge_core.model_adapter.errors import (
    AdapterAlreadyRegisteredError,
    AdapterNotFoundError,
    CapabilityNotSupportedError,
    ModelAdapterError,
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
    "CapabilityNotSupportedError",
    "ModelAdapter",
    "ModelAdapterError",
    "ModelCapability",
    "ModelMessage",
    "ModelRequest",
    "ModelResponse",
    "OpenAICompatibleAdapter",
    "TokenUsage",
]