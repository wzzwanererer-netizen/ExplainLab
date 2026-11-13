"""知识来源追溯实现（M2）。

基于 KnowledgeRepository 端口挂载与读取来源，不绑定数据库与 Web 框架。
每条知识可追溯到产生它的对话 / 文档 / 手动录入（含原文摘录）。
"""

from __future__ import annotations

from uuid import UUID

from knowledge_core.domain.entities import SourceRef
from knowledge_core.ports import KnowledgeRepository
from knowledge_core.provenance import ProvenanceService


class RepositoryProvenanceService(ProvenanceService):
    """以知识仓库为后端的来源挂载与追溯。"""

    def __init__(self, items: KnowledgeRepository) -> None:
        self._items = items

    async def attach_source(self, item_id: UUID, source: SourceRef) -> None:
        if self._items.get(item_id) is None:
            raise ValueError(f"知识条目不存在: {item_id}")
        self._items.add_source_ref(item_id, source)

    async def trace(self, item_id: UUID) -> list[SourceRef]:
        item = self._items.get(item_id)
        if item is None:
            raise ValueError(f"知识条目不存在: {item_id}")
        return list(item.source_refs)