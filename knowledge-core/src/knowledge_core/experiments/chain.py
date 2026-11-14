"""确定性学习路径装配（M5，无模型调用）。

以一条知识为终点（seed），沿 depends_on / refines 关系回溯先修知识，
按「先修优先」拓扑排序输出学习路径；visited 防环，排序键确定（标题 + id），
保证同一输入产出同一路径。仅依赖传入的条目与关系，不绑定数据库与 Web 框架。
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from knowledge_core.domain.entities import KnowledgeItem, KnowledgeRelation, RelationType
from knowledge_core.experiments.entities import ChainStep

# 视为「先修」的关系：source depends_on / refines target => target 应先学。
_PREREQ_TYPES = {RelationType.DEPENDS_ON, RelationType.REFINES}


class ChainService:
    """从知识关系装配先修优先的学习路径。"""

    def __init__(
        self,
        items: Sequence[KnowledgeItem],
        relations: Sequence[KnowledgeRelation],
    ) -> None:
        self._by_id = {i.id: i for i in items}
        self._relations = list(relations)

    def _prereqs(self, node_id: UUID) -> list[UUID]:
        """node 的先修知识 id（去重，仅保留池内条目）。"""
        found: dict[UUID, None] = {}
        for rel in self._relations:
            if (
                rel.source_id == node_id
                and rel.relation_type in _PREREQ_TYPES
                and rel.target_id in self._by_id
                and rel.target_id != node_id
            ):
                found.setdefault(rel.target_id, None)
        return list(found)

    def _relation_between(self, a: UUID, b: UUID) -> RelationType | None:
        """a 相对 b 的关系类型（优先先修语义），无则 None。"""
        fallback: RelationType | None = None
        for rel in self._relations:
            if rel.source_id == a and rel.target_id == b:
                if rel.relation_type in _PREREQ_TYPES:
                    return rel.relation_type
                fallback = fallback or rel.relation_type
        return fallback

    def build(self, seed_id: UUID, max_steps: int = 8) -> list[ChainStep]:
        """装配以 seed 为终点的学习路径；先修在前，seed 在后，至多 max_steps 步。"""
        if seed_id not in self._by_id or max_steps <= 0:
            return []
        order: list[UUID] = []
        visiting: set[UUID] = set()
        visited: set[UUID] = set()

        def dfs(node_id: UUID) -> None:
            if node_id in visited or node_id in visiting or node_id not in self._by_id:
                return
            visiting.add(node_id)
            prereqs = sorted(
                self._prereqs(node_id),
                key=lambda x: (self._by_id[x].title, str(x)),
            )
            for prereq in prereqs:
                dfs(prereq)
            visiting.discard(node_id)
            visited.add(node_id)
            order.append(node_id)

        dfs(seed_id)
        # 先修优先、seed 末位；超长时保留靠近终点的 max_steps 步。
        order = order[-max_steps:]
        steps: list[ChainStep] = []
        for position, item_id in enumerate(order):
            relation_from_prev = (
                self._relation_between(item_id, order[position - 1]) if position > 0 else None
            )
            steps.append(
                ChainStep(
                    item_id=item_id,
                    title=self._by_id[item_id].title,
                    relation_from_prev=relation_from_prev,
                    position=position,
                )
            )
        return steps
