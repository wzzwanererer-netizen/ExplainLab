"""M3 Core 混合检索测试：RRF 融合、双通道、空间过滤、archived 排除、模式。"""

from __future__ import annotations

from uuid import uuid4

import pytest
from helpers import (
    FakeEmbedder,
    InMemoryFullTextIndex,
    InMemoryKnowledgeRepository,
    InMemoryVectorStore,
)

from knowledge_core.domain.entities import KnowledgeItem, KnowledgeStatus
from knowledge_core.retrieval.hybrid import HybridRetrievalService, rrf_fuse


def _item(title: str, content: str, **kw) -> KnowledgeItem:
    return KnowledgeItem(title=title, content=content, **kw)


def test_rrf_fuse_prefers_multi_channel():
    a, b, c = uuid4(), uuid4(), uuid4()
    scores = rrf_fuse({"fts": [a, b], "vector": [b, c]})
    assert scores[b] > scores[a]
    assert scores[b] > scores[c]
    assert scores[a] == pytest.approx(1 / 61)


async def test_hybrid_multi_channel_item_ranks_first():
    items = InMemoryKnowledgeRepository()
    fts = InMemoryFullTextIndex()
    vec = InMemoryVectorStore()
    both = _item("知识图谱", "知识图谱是网络结构")
    only_fts = _item("知识图谱用途", "知识图谱用于问答")
    only_vec = _item("无关标题", "无关内容")
    for it in (both, only_fts, only_vec):
        items.save(it)
        fts.upsert(it.id, it.title, it.content)
    # both 与 only_vec 向量接近查询向量；only_fts 向量远
    vec.upsert(both.id, [1.0, 0.0], "m")
    vec.upsert(only_vec.id, [0.9, 0.1], "m")
    vec.upsert(only_fts.id, [0.0, 1.0], "m")
    svc = HybridRetrievalService(items, fts, vec, FakeEmbedder([1.0, 0.0]))

    results = await svc.search("知识图谱")
    assert results[0].item_id == both.id  # 双通道命中排第一
    assert {r.item_id for r in results} == {both.id, only_fts.id, only_vec.id}
    assert set(results[0].channels) == {"fts", "vector"}


async def test_archived_excluded():
    items = InMemoryKnowledgeRepository()
    fts = InMemoryFullTextIndex()
    vec = InMemoryVectorStore()
    archived = _item("知识图谱", "内容", status=KnowledgeStatus.ARCHIVED)
    items.save(archived)
    fts.upsert(archived.id, archived.title, archived.content)
    svc = HybridRetrievalService(items, fts, vec, FakeEmbedder())
    assert await svc.search("知识图谱") == []


async def test_space_filter_and_personal_unassigned():
    items = InMemoryKnowledgeRepository()
    fts = InMemoryFullTextIndex()
    vec = InMemoryVectorStore()
    in_p = _item("知识图谱甲", "内容", space_id="p")
    unassigned = _item("知识图谱乙", "内容", space_id=None)
    other = _item("知识图谱丙", "内容", space_id="s2")
    for it in (in_p, unassigned, other):
        items.save(it)
        fts.upsert(it.id, it.title, it.content)
    svc = HybridRetrievalService(items, fts, vec, personal_space_id="p")

    personal = await svc.search("知识图谱", space_id="p")
    assert {r.item_id for r in personal} == {in_p.id, unassigned.id}
    project = await svc.search("知识图谱", space_id="s2")
    assert {r.item_id for r in project} == {other.id}
    cross = await svc.search("知识图谱")
    assert len(cross) == 3


async def test_modes_and_no_embedder():
    items = InMemoryKnowledgeRepository()
    fts = InMemoryFullTextIndex()
    vec = InMemoryVectorStore()
    it = _item("知识图谱", "内容")
    items.save(it)
    fts.upsert(it.id, it.title, it.content)
    vec.upsert(it.id, [1.0, 0.0], "m")

    fts_only = HybridRetrievalService(items, fts, vec, FakeEmbedder())
    r = await fts_only.search("知识图谱", mode="fts")
    assert set(r[0].channels) == {"fts"}
    r = await fts_only.search("知识图谱", mode="vector")
    assert set(r[0].channels) == {"vector"}

    no_embed = HybridRetrievalService(items, fts, vec, None)
    r = await no_embed.search("知识图谱")
    assert set(r[0].channels) == {"fts"}


async def test_empty_query_and_limit():
    items = InMemoryKnowledgeRepository()
    fts = InMemoryFullTextIndex()
    vec = InMemoryVectorStore()
    for i in range(5):
        it = _item(f"知识图谱{i}", "内容")
        items.save(it)
        fts.upsert(it.id, it.title, it.content)
    svc = HybridRetrievalService(items, fts, vec)
    assert await svc.search("  ") == []
    assert len(await svc.search("知识图谱", limit=2)) == 2