"""知识工作流编排（M1 + M2）。

提取 → 持久化（M1）；条目分析（去重 + 关系推断，M2）。
可脱离前端与 HTTP 服务，以纯 Python 方式调用，未来复用于 Nesti。
"""

from __future__ import annotations

from collections.abc import Sequence

from knowledge_core.domain.entities import KnowledgeItem, KnowledgeRelation
from knowledge_core.extraction import ExtractionService
from knowledge_core.model_adapter.types import ModelMessage
from knowledge_core.ports import KnowledgeRepository, RelationRepository
from knowledge_core.relations import DuplicateMatch, RelationService


class KnowledgeService:
    """组合提取服务与知识仓库，完成「从对话到入库」与「条目分析」工作流。"""

    def __init__(
        self,
        extraction: ExtractionService,
        repository: KnowledgeRepository,
        *,
        relation_service: RelationService | None = None,
        relation_repository: RelationRepository | None = None,
    ) -> None:
        self._extraction = extraction
        self._repository = repository
        self._relation_service = relation_service
        self._relation_repository = relation_repository

    async def extract_and_store(
        self,
        messages: Sequence[ModelMessage],
        *,
        space_id: str | None = None,
        conversation_id: str | None = None,
    ) -> list[KnowledgeItem]:
        """从对话提取知识并逐条持久化，返回已入库的条目。"""
        items = await self._extraction.extract(
            messages,
            space_id=space_id,
            conversation_id=conversation_id,
        )
        return [self._repository.save(item) for item in items]

    async def analyze_item(self, item: KnowledgeItem) -> dict:
        """对条目做去重候选判定与关系推断，持久化新关系，返回分析结果。"""
        if self._relation_service is None or self._relation_repository is None:
            raise ValueError("未配置关系服务或关系仓库，无法分析")
        candidates = self._repository.list(
            space_id=item.space_id, include_unassigned=True
        )
        duplicates: list[DuplicateMatch] = await self._relation_service.find_duplicates(
            item, candidates
        )
        relations: list[KnowledgeRelation] = await self._relation_service.infer_relations(
            item, candidates
        )
        for rel in relations:
            existing = self._relation_repository.find_relation(
                rel.source_id, rel.target_id, rel.relation_type
            )
            if existing is None:
                self._relation_repository.save_relation(rel)
        return {"duplicates": duplicates, "relations": relations}