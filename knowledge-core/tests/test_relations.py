"""M2 去重与关系推断测试：词面相似度纯函数 + LLM 服务（FakeAdapter，不发真实请求）。"""

from __future__ import annotations

from helpers import FakeAdapter

from knowledge_core.domain.entities import KnowledgeItem, RelationOrigin, RelationType
from knowledge_core.relations.lexical import (
    normalize,
    recall_candidates,
    text_similarity,
)
from knowledge_core.relations.llm import LLMRelationService


def _item(title: str, content: str) -> KnowledgeItem:
    return KnowledgeItem(title=title, content=content)


def test_normalize_strips_punct_and_lowercases():
    assert normalize("Hello, World! 你好，世界。") == "helloworld你好世界"


def test_text_similarity_identical_is_one():
    assert text_similarity("知识图谱", "实体关系网络", "知识图谱", "实体关系网络") == 1.0


def test_text_similarity_disjoint_is_low():
    score = text_similarity("知识图谱", "实体关系网络", "红烧肉做法", "五花肉焯水加糖色")
    assert score < 0.2


def test_recall_excludes_self_filters_and_sorts():
    item = _item("知识图谱的定义", "知识图谱是实体关系实体网络")
    near = _item("知识图谱定义", "知识图谱是实体关系实体的网络")
    far = _item("红烧肉", "五花肉焯水加糖色炖煮")
    recalled = recall_candidates(item, [item, near, far], threshold=0.3, top_k=5)
    assert [c.id for c, _ in recalled] == [near.id]
    assert recalled[0][1] >= 0.3


def test_recall_top_k_limits():
    item = _item("甲", "共同内容片段")
    cands = [_item(f"乙{i}", "共同内容片段") for i in range(6)]
    recalled = recall_candidates(item, cands, threshold=0.1, top_k=3)
    assert len(recalled) == 3


async def test_find_duplicates_confirmed_only():
    item = _item("知识图谱的定义", "知识图谱是实体关系实体网络")
    dup = _item("知识图谱定义", "知识图谱是实体关系实体的网络")
    other = _item("知识图谱的用途", "知识图谱支撑语义问答")
    adapter = FakeAdapter(
        '{"duplicates": [{"index": 0, "same": true, "confidence": 0.9},'
        ' {"index": 1, "same": false, "confidence": 0.2}]}'
    )
    service = LLMRelationService(adapter, recall_threshold=0.1)
    matches = await service.find_duplicates(item, [dup, other])
    assert len(matches) == 1
    assert matches[0].item_id == dup.id
    assert matches[0].score == 0.9


async def test_find_duplicates_malformed_returns_empty():
    item = _item("知识图谱的定义", "知识图谱是实体关系实体网络")
    dup = _item("知识图谱定义", "知识图谱是实体关系实体的网络")
    service = LLMRelationService(FakeAdapter("这不是 JSON"), recall_threshold=0.1)
    assert await service.find_duplicates(item, [dup]) == []


async def test_find_duplicates_no_candidates_skips_model():
    item = _item("甲", "内容")
    adapter = FakeAdapter('{"duplicates": []}')
    service = LLMRelationService(adapter)
    assert await service.find_duplicates(item, []) == []
    assert adapter.last_request is None  # 无候选不调用模型


async def test_infer_relations_parses_and_skips_invalid_type():
    item = _item("知识图谱的定义", "知识图谱是实体关系实体网络")
    cand = _item("知识图谱概览", "知识图谱是实体关系实体的网络结构")
    adapter = FakeAdapter(
        '{"relations": [{"index": 0, "type": "refines", "confidence": 0.8},'
        ' {"index": 0, "type": "bogus", "confidence": 0.9}]}'
    )
    service = LLMRelationService(adapter, recall_threshold=0.1)
    relations = await service.infer_relations(item, [cand])
    assert len(relations) == 1
    rel = relations[0]
    assert rel.source_id == item.id
    assert rel.target_id == cand.id
    assert rel.relation_type == RelationType.REFINES
    assert rel.confidence == 0.8
    assert rel.origin == RelationOrigin.LLM


async def test_infer_relations_malformed_returns_empty():
    item = _item("知识图谱的定义", "知识图谱是实体关系实体网络")
    cand = _item("知识图谱概览", "知识图谱是实体关系实体的网络结构")
    service = LLMRelationService(FakeAdapter("oops"), recall_threshold=0.1)
    assert await service.infer_relations(item, [cand]) == []