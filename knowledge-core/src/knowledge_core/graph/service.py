"""动态知识地图数据装配（M4）。

把知识条目与关系装配为「节点 + 边」图结构，供前端渲染（React Flow + ELK）。
仅依赖端口（KnowledgeRepository/RelationRepository），不含坐标、不绑定数据库
与 Web 框架，可复用于 Nesti（渲染器由应用层自带）。

space_id=None 跨全部空间；个人总知识库聚合未归属条目（与 M1/M3 语义一致）。
archived 默认不入图（与检索口径一致）；include_archived=True 时保留归档节点
与相应边（前端灰显，可呈现 merge 的 duplicate_of 闭环）。
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from knowledge_core.domain.entities import (
    KnowledgeStatus,
    RelationOrigin,
    RelationType,
)
from knowledge_core.ports import KnowledgeRepository, RelationRepository


class GraphNode(BaseModel):
    """地图节点：一条知识条目的可视化摘要。"""

    id: UUID
    title: str
    status: KnowledgeStatus
    space_id: str | None = None


class GraphEdge(BaseModel):
    """地图边：一条知识关系（含类型/置信度/来源）。"""

    id: UUID
    source_id: UUID
    target_id: UUID
    relation_type: RelationType
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    origin: RelationOrigin = RelationOrigin.MANUAL


class KnowledgeGraph(BaseModel):
    """节点 + 边的图结构（无坐标，布局由渲染层负责）。"""

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class KnowledgeGraphService:
    """经端口装配知识地图；纯数据、无模型调用、无网络。"""

    def __init__(
        self, items: KnowledgeRepository, relations: RelationRepository
    ) -> None:
        self._items = items
        self._relations = relations

    def build_graph(
        self,
        *,
        space_id: str | None = None,
        include_unassigned: bool = False,
        include_archived: bool = False,
    ) -> KnowledgeGraph:
        """装配图。

        Args:
            space_id: 限定知识空间；None 跨全部空间。
            include_unassigned: 限定空间时同时聚合 space_id=None 条目。
            include_archived: 是否保留归档节点与相应边（默认排除）。
        """
        items = self._items.list(
            space_id=space_id, include_unassigned=include_unassigned
        )
        if not include_archived:
            items = [i for i in items if i.status != KnowledgeStatus.ARCHIVED]
        node_ids = {i.id for i in items}
        nodes = [
            GraphNode(id=i.id, title=i.title, status=i.status, space_id=i.space_id)
            for i in items
        ]

        edges: list[GraphEdge] = []
        seen: set[tuple[UUID, UUID, RelationType]] = set()
        for relation in self._relations.list_all_relations():
            # 仅保留两端都在节点集合的边，避免隐藏归档时出现悬空边。
            if relation.source_id not in node_ids or relation.target_id not in node_ids:
                continue
            if relation.source_id == relation.target_id:
                continue
            key = (relation.source_id, relation.target_id, relation.relation_type)
            if key in seen:
                continue
            seen.add(key)
            edges.append(
                GraphEdge(
                    id=relation.id,
                    source_id=relation.source_id,
                    target_id=relation.target_id,
                    relation_type=relation.relation_type,
                    confidence=relation.confidence,
                    origin=relation.origin,
                )
            )
        return KnowledgeGraph(nodes=nodes, edges=edges)