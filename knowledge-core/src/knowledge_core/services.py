"""知识工作流编排（M1）。

提取 → 持久化。可脱离前端与 HTTP 服务，以纯 Python 方式调用，未来复用于 Nesti。
关系 / 版本 / 审核等编排自 M2 起在此扩展。
"""

from __future__ import annotations

from collections.abc import Sequence

from knowledge_core.domain.entities import KnowledgeItem
from knowledge_core.extraction import ExtractionService
from knowledge_core.model_adapter.types import ModelMessage
from knowledge_core.ports import KnowledgeRepository


class KnowledgeService:
    """组合提取服务与知识仓库，完成「从对话到入库」的工作流。"""

    def __init__(
        self,
        extraction: ExtractionService,
        repository: KnowledgeRepository,
    ) -> None:
        self._extraction = extraction
        self._repository = repository

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