"""SSE 流式对话与知识库引用拼装单元测试。"""

from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.services.conversations import (
    build_chat_messages_with_citations,
    stream_openai_chat,
)


def test_build_chat_messages_with_citations_injects_context() -> None:
    msgs = build_chat_messages_with_citations(
        [],
        user_content="什么是知识图谱？",
        citations=[
            {
                "item_id": "k1",
                "title": "知识图谱定义",
                "snippet": "以实体-关系-实体组织知识",
                "score": 0.92,
                "status": "active",
            }
        ],
    )
    assert msgs[0]["role"] == "system"
    assert "《知识图谱定义》" in msgs[0]["content"]
    assert msgs[-1] == {"role": "user", "content": "什么是知识图谱？"}


@pytest.mark.asyncio
async def test_stream_openai_chat_yields_sse_deltas() -> None:
    sse_body = (
        'data: {"choices":[{"delta":{"content":"你好，"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"ExplainLab！"}}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/chat/completions")
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            content=sse_body.encode("utf-8"),
        )

    settings = Settings(
        model_base_url="https://api.example.com/v1",
        model_api_key=SecretStr("test-secret-key"),
        model_name="test-model",
    )
    chunks: list[str] = []
    async for piece in stream_openai_chat(
        settings,
        [{"role": "user", "content": "hi"}],
        transport=httpx.MockTransport(handler),
    ):
        chunks.append(piece)

    assert chunks == ["你好，", "ExplainLab！"]
