"""适配器注册工厂：按名称注册 / 解析 ModelAdapter。

支持未来更换模型供应商而不修改业务代码。
"""

from __future__ import annotations

from knowledge_core.model_adapter.base import ModelAdapter
from knowledge_core.model_adapter.errors import (
    AdapterAlreadyRegisteredError,
    AdapterNotFoundError,
)


class AdapterRegistry:
    """进程内适配器注册表。"""

    def __init__(self) -> None:
        self._adapters: dict[str, ModelAdapter] = {}

    def register(self, adapter: ModelAdapter, *, name: str | None = None) -> None:
        """注册适配器；默认以 provider 作为名称。"""
        key = name if name is not None else adapter.provider
        if key in self._adapters:
            raise AdapterAlreadyRegisteredError(f"适配器已注册: {key}")
        self._adapters[key] = adapter

    def resolve(self, name: str) -> ModelAdapter:
        """按名称解析适配器；未注册时抛出 AdapterNotFoundError。"""
        try:
            return self._adapters[name]
        except KeyError:
            raise AdapterNotFoundError(f"适配器未注册: {name}") from None

    def unregister(self, name: str) -> None:
        """移除适配器；不存在时静默忽略。"""
        self._adapters.pop(name, None)

    def names(self) -> list[str]:
        """已注册名称列表（有序）。"""
        return list(self._adapters)

    def __contains__(self, name: object) -> bool:
        return name in self._adapters

    def __len__(self) -> int:
        return len(self._adapters)