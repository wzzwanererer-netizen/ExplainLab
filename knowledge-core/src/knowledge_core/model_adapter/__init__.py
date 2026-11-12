"""统一模型适配层：接口、类型、注册工厂。

M0 仅建立接口，不接入具体供应商。
"""

from knowledge_core.model_adapter.base import ModelAdapter
from knowledge_core.model_adapter.errors import (
    AdapterAlreadyRegisteredError,
    AdapterNotFoundError,
    CapabilityNotSupportedError,
    ModelAdapterError,
)
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
    "TokenUsage",
]