"""测试基建：假适配器与内存仓库。

这些是测试专用替身，不是产品功能；产品代码不使用假数据。
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from knowledge_core.domain.entities import KnowledgeItem
from knowledge_core.model_adapter import (
    ModelAdapter,
    ModelCapability,
    ModelRequest,
    ModelResponse,
)


class FakeAdapter(ModelAdapter):
    """返回预设 content 的假适配器，用于提取/编排测试。"""

    def __init__(self, content: str = '{"items": []}') -> None:
        self._content = content
        self.last_request: ModelRequest | None = None

    @property
    def provider(self) -> str:
        return "fake"

    @property
    def default_model(self) -> str:
        return "fake-model"

    def capabilities(self) -> set[ModelCapability]:
        return {ModelCapability.GENERATE, ModelCapability.EMBED}

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.last_request = request
        return ModelResponse(content=self._content, model="fake-model", provider="fake")

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]


class InMemoryKnowledgeRepository:
    """内存知识仓库，实现 KnowledgeRepository 端口。"""

    def __init__(self) -> None:
        self.items: dict[UUID, KnowledgeItem] = {}

    def save(self, item: KnowledgeItem) -> KnowledgeItem:
        self.items[item.id] = item
        return item

    def get(self, item_id: UUID) -> KnowledgeItem | None:
        return self.items.get(item_id)

    def list(
        self, *, space_id: str | None = None, include_unassigned: bool = False
    ) -> list[KnowledgeItem]:
        return [
            item
            for item in self.items.values()
            if space_id is None
            or item.space_id == space_id
            or (include_unassigned and item.space_id is None)
        ]

    def update(self, item: KnowledgeItem) -> KnowledgeItem:
        self.items[item.id] = item
        return item

    def delete(self, item_id: UUID) -> bool:
        return self.items.pop(item_id, None) is not None