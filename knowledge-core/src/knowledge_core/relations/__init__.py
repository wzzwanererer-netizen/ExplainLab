"""知识关系与去重接口。

接口（RelationService ABC + DuplicateMatch）在此定义；实现见
knowledge_core.relations.llm.LLMRelationService（模型判定）与
knowledge_core.relations.lexical（词面召回纯函数）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from pydantic import BaseModel, Field

from knowledge_core.domain.entities import KnowledgeItem, KnowledgeRelation


class DuplicateMatch(BaseModel):
    """重复知识候选。"""

    item_id: UUID
    score: float = Field(ge=0.0, le=1.0)


class RelationService(ABC):
    """重复识别与关系推断。"""

    @abstractmethod
    async def find_duplicates(
        self,
        item: KnowledgeItem,
        candidates: Sequence[KnowledgeItem],
    ) -> list[DuplicateMatch]:
        """在候选集合中找出与 item 重复或高度相似的条目。"""
        raise NotImplementedError

    @abstractmethod
    async def infer_relations(
        self,
        item: KnowledgeItem,
        candidates: Sequence[KnowledgeItem],
    ) -> list[KnowledgeRelation]:
        """推断 item 与候选条目之间的关系。"""
        raise NotImplementedError