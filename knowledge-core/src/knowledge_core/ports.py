"""仓库端口（Protocol）。

Knowledge Core 通过端口依赖持久化能力，具体实现由应用层（如 backend 的 SQLAlchemy）注入。
这保证核心不绑定任何数据库，可复用于 Nesti。M1 方法为同步（适配 SQLAlchemy 同步会话）。
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from knowledge_core.domain.entities import KnowledgeItem


class KnowledgeRepository(Protocol):
    """知识条目持久化端口。"""

    def save(self, item: KnowledgeItem) -> KnowledgeItem:
        """新增一条知识（含来源），返回持久化后的条目。"""
        ...

    def get(self, item_id: UUID) -> KnowledgeItem | None:
        """按 ID 获取；不存在返回 None。"""
        ...

    def list(
        self, *, space_id: str | None = None, include_unassigned: bool = False
    ) -> list[KnowledgeItem]:
        """列出知识。

        Args:
            space_id: 限定知识空间；None 时返回全部空间。
            include_unassigned: 仅在指定 space_id 时生效。为 True 时同时返回
                space_id 为 None 的条目（领域语义中 None 即个人总知识库），
                供个人总知识库视图聚合「未显式归属」的条目。
        """
        ...

    def update(self, item: KnowledgeItem) -> KnowledgeItem:
        """更新一条知识，返回更新后的条目。"""
        ...

    def delete(self, item_id: UUID) -> bool:
        """删除一条知识；返回是否删除成功。"""
        ...