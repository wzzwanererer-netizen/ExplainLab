"""LLMExtractionService 测试：假适配器返回预设输出，验证解析与来源追溯。"""

from __future__ import annotations

from helpers import FakeAdapter

from knowledge_core.domain.entities import KnowledgeStatus, SourceType
from knowledge_core.extraction.llm import LLMExtractionService
from knowledge_core.model_adapter import ModelMessage


def msgs() -> list[ModelMessage]:
    return [
        ModelMessage(role="user", content="什么是勾股定理？"),
        ModelMessage(role="assistant", content="直角三角形两直角边平方和等于斜边平方。"),
    ]


async def test_extract_plain_json():
    adapter = FakeAdapter('{"items": [{"title": "勾股定理", "content": "a²+b²=c²"}]}')
    service = LLMExtractionService(adapter)
    items = await service.extract(msgs(), space_id="sp1", conversation_id="conv1")

    assert len(items) == 1
    item = items[0]
    assert item.title == "勾股定理"
    assert item.content == "a²+b²=c²"
    assert item.status is KnowledgeStatus.DRAFT
    assert item.space_id == "sp1"
    assert item.source_refs[0].conversation_id == "conv1"
    assert item.source_refs[0].source_type is SourceType.CONVERSATION
    assert item.source_refs[0].excerpt


async def test_extract_code_fence():
    adapter = FakeAdapter('```json\n{"items": [{"title": "t", "content": "c"}]}\n```')
    items = await LLMExtractionService(adapter).extract(msgs())
    assert len(items) == 1 and items[0].title == "t"


async def test_extract_extra_prose():
    adapter = FakeAdapter('好的，结果如下：\n{"items": [{"title": "t", "content": "c"}]}\n希望有帮助')
    items = await LLMExtractionService(adapter).extract(msgs())
    assert len(items) == 1


async def test_extract_direct_list():
    adapter = FakeAdapter('[{"title": "t", "content": "c"}]')
    items = await LLMExtractionService(adapter).extract(msgs())
    assert len(items) == 1


async def test_extract_empty_items():
    adapter = FakeAdapter('{"items": []}')
    assert await LLMExtractionService(adapter).extract(msgs()) == []


async def test_extract_malformed_returns_empty():
    adapter = FakeAdapter("这不是 JSON")
    assert await LLMExtractionService(adapter).extract(msgs()) == []


async def test_extract_skips_invalid_entries():
    adapter = FakeAdapter(
        '{"items": [{"title": "", "content": "c"}, {"title": "t", "content": ""},'
        ' {"title": "ok", "content": "valid"}]}'
    )
    items = await LLMExtractionService(adapter).extract(msgs())
    assert len(items) == 1 and items[0].title == "ok"


async def test_extract_empty_messages_no_call():
    adapter = FakeAdapter('{"items": [{"title": "t", "content": "c"}]}')
    assert await LLMExtractionService(adapter).extract([]) == []
    assert adapter.last_request is None


async def test_extract_prompt_contains_transcript():
    adapter = FakeAdapter('{"items": []}')
    await LLMExtractionService(adapter).extract(msgs())
    assert adapter.last_request is not None
    user_msg = adapter.last_request.messages[-1]
    assert "勾股定理" in user_msg.content