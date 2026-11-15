"""统一模型适配层抽象接口与公共失败契约。

所有模型供应商必须实现 ModelAdapter 才能接入 ExplainLab / Nesti。
业务代码只依赖本接口，不依赖任何供应商 SDK。已实现 OpenAI 兼容适配器。

失败契约（所有供应商一致，详见 errors.py）：
- 请求超时 → ModelTimeoutError（可重试）
- 供应商不可用 / 网络故障 / 5xx → ProviderUnavailableError（可重试）
- 限流 429 → RateLimitError（可重试）
- 鉴权失败 401/403 → AuthenticationError（不可重试）
- 响应格式错误（非法 JSON / 缺字段）→ MalformedResponseError（不可重试）
- 不支持所请求能力 → CapabilityNotSupportedError（不可重试）
- STREAM 未实现时不得在 capabilities() 声明 STREAM，也不得虚假返回成功。

API Key 由实现方从后端环境变量读取，绝不进入前端与 Git。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from knowledge_core.model_adapter.types import (
    ModelCapability,
    ModelRequest,
    ModelResponse,
)


class ModelAdapter(ABC):
    """模型供应商统一接口。"""

    @property
    @abstractmethod
    def provider(self) -> str:
        """供应商标识，如 "openai" / "anthropic" / "local"。"""
        raise NotImplementedError

    @property
    @abstractmethod
    def default_model(self) -> str:
        """默认模型名。"""
        raise NotImplementedError

    @abstractmethod
    def capabilities(self) -> set[ModelCapability]:
        """声明本适配器支持的能力。"""
        raise NotImplementedError

    @abstractmethod
    async def generate(self, request: ModelRequest) -> ModelResponse:
        """文本生成。不支持时应抛出 CapabilityNotSupportedError。"""
        raise NotImplementedError

    @abstractmethod
    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """文本向量化，返回与输入等长的向量列表。"""
        raise NotImplementedError