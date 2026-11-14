"""M4 Core 图装配测试：空间过滤 / 归档口径 / 悬空边 / 去重。"""

from __future__ import annotations

from helpers import InMemoryKnowledgeRepository, InMemoryRelationRepository

from knowledge_core.domain.entities import (
    KnowledgeItem,
    KnowledgeRelation,
    KnowledgeStatus,
    RelationOrigin,
    RelationType,
)
from knowledge_core.graph import KnowledgeGraphService


def _item(
    title: str,
    status: KnowledgeStatus = KnowledgeStatus.ACTIVE,
    space_id: str | None = None,
) -> KnowledgeItem:
    return KnowledgeItem(
        title=title, content=f"{title} 内容", status=status, space_id=space_id
    )


def _build():
    items = InMemoryKnowledgeRepository()
    relations = InMemoryRelationRepository()
    return items, relations, KnowledgeGraphService(items, relations)


def test_empty_graph():
    _, _, service = _build()
    graph = service.build_graph()
    assert graph.nodes == []
    assert graph.edges == []


def test_nodes_and_edges_basic():
    items, relations, service = _build()
    a = items.save(_item("定义"))
    b = items.save(_item("用途", status=KnowledgeStatus.DRAFT))
    relations.save_relation(
        KnowledgeRelation(
            source_id=a.id,
            target_id=b.id,
            relation_type=RelationType.RELATED,
            confidence=0.9,
            origin=RelationOrigin.LLM,
        )
    )
    graph = service.build_graph()
    assert {n.id for n in graph.nodes} == {a.id, b.id}  # draft 也入图
    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert edge.source_id == a.id
    assert edge.target_id == b.id
    assert edge.relation_type == RelationType.RELATED
    assert edge.confidence == 0.9
    assert edge.origin == RelationOrigin.LLM


def test_archived_excluded_by_default_drops_dangling_edge():
    items, relations, service = _build()
    a = items.save(_item("定义"))
    archived = items.save(_item("概念", status=KnowledgeStatus.ARCHIVED))
    relations.save_relation(
        KnowledgeRelation(
            source_id=archived.id,
            target_id=a.id,
            relation_type=RelationType.DUPLICATE_OF,
            origin=RelationOrigin.DEDUP,
        )
    )
    graph = service.build_graph()
    assert {n.id for n in graph.nodes} == {a.id}
    assert graph.edges == []  # 指向归档的边被丢弃，不悬空


def test_include_archived_keeps_node_and_edge():
    items, relations, service = _build()
    a = items.save(_item("定义"))
    archived = items.save(_item("概念", status=KnowledgeStatus.ARCHIVED))
    relations.save_relation(
        KnowledgeRelation(
            source_id=archived.id,
            target_id=a.id,
            relation_type=RelationType.DUPLICATE_OF,
            origin=RelationOrigin.DEDUP,
        )
    )
    graph = service.build_graph(include_archived=True)
    assert {n.id for n in graph.nodes} == {a.id, archived.id}
    assert len(graph.edges) == 1
    assert graph.edges[0].relation_type == RelationType.DUPLICATE_OF
    archived_node = next(n for n in graph.nodes if n.id == archived.id)
    assert archived_node.status == KnowledgeStatus.ARCHIVED


def test_space_filter_drops_cross_space_edge():
    items, relations, service = _build()
    a = items.save(_item("A", space_id="s1"))
    b = items.save(_item("B", space_id="s2"))
    relations.save_relation(
        KnowledgeRelation(source_id=a.id, target_id=b.id, relation_type=RelationType.RELATED)
    )
    graph = service.build_graph(space_id="s1")
    assert {n.id for n in graph.nodes} == {a.id}
    assert graph.edges == []


def test_include_unassigned_aggregates_personal():
    items, relations, service = _build()
    a = items.save(_item("A", space_id="s1"))
    unassigned = items.save(_item("U", space_id=None))
    relations.save_relation(
        KnowledgeRelation(source_id=a.id, target_id=unassigned.id, relation_type=RelationType.REFINES)
    )
    without = service.build_graph(space_id="s1")
    assert {n.id for n in without.nodes} == {a.id}
    assert without.edges == []
    with_unassigned = service.build_graph(space_id="s1", include_unassigned=True)
    assert {n.id for n in with_unassigned.nodes} == {a.id, unassigned.id}
    assert len(with_unassigned.edges) == 1


def test_edge_dedup_same_triple():
    items, relations, service = _build()
    a = items.save(_item("A"))
    b = items.save(_item("B"))
    for _ in range(2):
        relations.save_relation(
            KnowledgeRelation(
                source_id=a.id, target_id=b.id, relation_type=RelationType.RELATED
            )
        )
    graph = service.build_graph()
    assert len(graph.edges) == 1  # (source,target,type) 去重兜底


def test_cross_space_all_spaces_includes_edge():
    items, relations, service = _build()
    a = items.save(_item("A", space_id="s1"))
    b = items.save(_item("B", space_id="s2"))
    relations.save_relation(
        KnowledgeRelation(source_id=a.id, target_id=b.id, relation_type=RelationType.DEPENDS_ON)
    )
    graph = service.build_graph()  # space_id=None 跨全部空间
    assert {n.id for n in graph.nodes} == {a.id, b.id}
    assert len(graph.edges) == 1
    assert graph.edges[0].relation_type == RelationType.DEPENDS_ON