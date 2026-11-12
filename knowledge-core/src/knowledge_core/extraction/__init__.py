"""知识提取接口：从对话内容中提取知识条目。

M0 仅定义接口；实现见 M1。实现方通过 Model Adapter 调用模型，
不得直接依赖任何具体供应商 SDK。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from knowledge_core.domain.entities import KnowledgeItem
from knowledge_core.model_adapter.types import ModelMessage


class ExtractionService(ABC):
    """从一段对话中抽取候选知识条目。"""

    @abstractmethod
    async def extract(
        self,
        messages: Sequence[ModelMessage],
        *,
        space_id: str | None = None,
    ) -> list[KnowledgeItem]:
        """提取知识条目（含来源追溯信息），不落库、不查重。

        Args:
            messages: 对话消息序列。
            space_id: 目标知识空间；None 表示个人总知识库。
        """
        raise NotImplementedError