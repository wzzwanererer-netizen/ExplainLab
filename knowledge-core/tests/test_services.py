"""KnowledgeService 编排测试：提取 → 持久化（内存仓库）。"""

from __future__ import annotations

from helpers import FakeAdapter, InMemoryKnowledgeRepository

from knowledge_core.extraction.llm import LLMExtractionService
from knowledge_core.model_adapter import ModelMessage
from knowledge_core.services import KnowledgeService


async def test_extract_and_store_persists_items():
    adapter = FakeAdapter('{"items": [{"title": "t1", "content": "c1"}, {"title": "t2", "content": "c2"}]}')
    repo = InMemoryKnowledgeRepository()
    service = KnowledgeService(LLMExtractionService(adapter), repo)

    stored = await service.extract_and_store(
        [ModelMessage(role="user", content="x")],
        space_id="s",
        conversation_id="c",
    )

    assert len(stored) == 2
    assert len(repo.items) == 2
    assert {i.title for i in repo.list(space_id="s")} == {"t1", "t2"}
    assert all(i.source_refs[0].conversation_id == "c" for i in stored)


async def test_extract_and_store_empty():
    adapter = FakeAdapter('{"items": []}')
    repo = InMemoryKnowledgeRepository()
    service = KnowledgeService(LLMExtractionService(adapter), repo)

    stored = await service.extract_and_store([ModelMessage(role="user", content="x")])
    assert stored == []
    assert len(repo.items) == 0


async def test_repository_port_crud():
    repo = InMemoryKnowledgeRepository()
    adapter = FakeAdapter('{"items": [{"title": "t", "content": "c"}]}')
    service = KnowledgeService(LLMExtractionService(adapter), repo)
    item = (await service.extract_and_store([ModelMessage(role="user", content="x")]))[0]

    assert repo.get(item.id) is not None
    item.title = "updated"
    repo.update(item)
    assert repo.get(item.id).title == "updated"
    assert repo.delete(item.id) is True
    assert repo.get(item.id) is None
    assert repo.delete(item.id) is False