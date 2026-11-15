"""知识来源追溯接口。

接口（ProvenanceService ABC）在此定义；实现见
knowledge_core.provenance.service.RepositoryProvenanceService。
每条知识必须能追溯到产生它的对话或文档。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from knowledge_core.domain.entities import SourceRef


class ProvenanceService(ABC):
    """知识来源的挂载与追溯。"""

    @abstractmethod
    async def attach_source(self, item_id: UUID, source: SourceRef) -> None:
        """为知识条目挂载一个来源。"""
        raise NotImplementedError

    @abstractmethod
    async def trace(self, item_id: UUID) -> list[SourceRef]:
        """返回条目的全部来源（含对话定位与原文摘录）。"""
        raise NotImplementedError