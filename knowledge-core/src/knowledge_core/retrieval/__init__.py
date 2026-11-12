"""跨会话混合检索接口。

M0 仅定义接口；实现见 M3（SQLite FTS5 + 向量检索，PostgreSQL 阶段迁移）。
检索不依赖前端页面，可纯 Python 调用。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    """一条检索命中。"""

    item_id: UUID
    score: float = Field(ge=0.0)
    snippet: str = ""


class RetrievalService(ABC):
    """跨会话、跨知识空间的混合检索。"""

    @abstractmethod
    async def search(
        self,
        query: str,
        *,
        space_id: str | None = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        """检索知识条目。

        Args:
            query: 自然语言查询。
            space_id: 限定知识空间；None 表示跨全部空间（含个人总知识库）。
            limit: 最大返回条数。
        """
        raise NotImplementedError