"""统一模型适配层抽象接口。

所有模型供应商必须实现 ModelAdapter 才能接入 ExplainLab / Nesti。
业务代码只依赖本接口，不依赖任何供应商 SDK。
M0 不提供具体供应商实现；API Key 由实现方从后端环境变量读取。
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