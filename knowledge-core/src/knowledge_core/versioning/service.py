"""知识版本管理实现（M2）。

基于 VersionRepository + KnowledgeRepository 端口，不绑定数据库与 Web 框架。
回滚前先为「回滚前」状态建快照，保持版本历史线性可追溯。
"""

from __future__ import annotations

from uuid import UUID

from knowledge_core.domain.entities import KnowledgeItem, KnowledgeVersion, utcnow
from knowledge_core.ports import KnowledgeRepository, VersionRepository
from knowledge_core.versioning import VersionService


class RepositoryVersionService(VersionService):
    """以仓库端口为后端的版本创建、查询与回滚。"""

    def __init__(
        self, versions: VersionRepository, items: KnowledgeRepository
    ) -> None:
        self._versions = versions
        self._items = items

    async def create_version(
        self,
        item: KnowledgeItem,
        *,
        change_summary: str | None = None,
    ) -> KnowledgeVersion:
        existing = self._versions.list_versions(item.id)
        next_version = max((v.version for v in existing), default=0) + 1
        snapshot = KnowledgeVersion(
            item_id=item.id,
            version=next_version,
            title=item.title,
            content=item.content,
            change_summary=change_summary,
        )
        return self._versions.save_version(snapshot)

    async def list_versions(self, item_id: UUID) -> list[KnowledgeVersion]:
        return self._versions.list_versions(item_id)

    async def restore(self, item_id: UUID, version: int) -> KnowledgeItem:
        current = self._items.get(item_id)
        if current is None:
            raise ValueError(f"知识条目不存在: {item_id}")
        target = self._versions.get_version(item_id, version)
        if target is None:
            raise ValueError(f"版本不存在: item={item_id} version={version}")
        # 先快照回滚前状态，保持历史线性
        await self.create_version(
            current, change_summary=f"回滚前快照（恢复至 v{version}）"
        )
        current.title = target.title
        current.content = target.content
        current.updated_at = utcnow()
        return self._items.update(current)