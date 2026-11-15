"""知识版本管理接口。

接口（VersionService ABC）在此定义；实现见
knowledge_core.versioning.service.RepositoryVersionService。
重要变更的审核流在接口之上由 review 模块编排。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from knowledge_core.domain.entities import KnowledgeItem, KnowledgeVersion


class VersionService(ABC):
    """知识条目的版本创建、查询与回滚。"""

    @abstractmethod
    async def create_version(
        self,
        item: KnowledgeItem,
        *,
        change_summary: str | None = None,
    ) -> KnowledgeVersion:
        """为条目当前内容创建一个新版本。"""
        raise NotImplementedError

    @abstractmethod
    async def list_versions(self, item_id: UUID) -> list[KnowledgeVersion]:
        """按版本号升序列出条目的全部历史版本。"""
        raise NotImplementedError

    @abstractmethod
    async def restore(self, item_id: UUID, version: int) -> KnowledgeItem:
        """将条目回滚到指定版本，返回回滚后的条目。"""
        raise NotImplementedError