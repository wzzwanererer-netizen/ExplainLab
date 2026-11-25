"""会话服务：CRUD、真实对话与 SSE 流式对话（含知识库引用溯源）。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Conversation, Message
from app.services.errors import NotFoundError
from app.services.retrieval import build_retrieval_service
from app.services.spaces import get_personal_space
from knowledge_core.domain.entities import utcnow
from knowledge_core.model_adapter import ModelAdapter, ModelAdapterError, ModelMessage, ModelRequest
from knowledge_core.ports import Embedder

_CHAT_SYSTEM_PROMPT = (
    "你是 ExplainLab 的学习助手，帮助用户理解知识、深入思考。回答准确、简洁、有条理。"
)


def create_conversation(
    session: Session, *, title: str, space_id: str | None
) -> Conversation:
    conv = Conversation(title=title, space_id=space_id)
    session.add(conv)
    session.flush()
    return conv


def list_conversations(
    session: Session, *, space_id: str | None = None
) -> list[Conversation]:
    stmt = select(Conversation).order_by(Conversation.updated_at.desc())
    if space_id is not None:
        stmt = stmt.where(Conversation.space_id == space_id)
    return list(session.scalars(stmt))


def get_conversation(session: Session, conversation_id: str) -> Conversation | None:
    return session.get(Conversation, conversation_id)


def delete_conversation(session: Session, conversation_id: str) -> bool:
    conv = session.get(Conversation, conversation_id)
    if conv is None:
        return False
    session.delete(conv)
    session.flush()
    return True


def append_message(
    session: Session, conversation_id: str, *, role: str, content: str
) -> Message:
    message = Message(conversation_id=conversation_id, role=role, content=content)
    session.add(message)
    session.flush()
    return message


async def chat(
    session: Session,
    adapter: ModelAdapter,
    conversation_id: str,
    *,
    content: str,
) -> Message:
    """追加用户消息，调用模型生成回复并落库，返回助手消息。"""
    conv = session.get(Conversation, conversation_id)
    if conv is None:
        raise NotFoundError(f"会话不存在: {conversation_id}")

    append_message(session, conversation_id, role="user", content=content)
    session.flush()

    rows = session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    ).all()
    history = [ModelMessage(role="system", content=_CHAT_SYSTEM_PROMPT)]
    history += [ModelMessage(role=m.role, content=m.content) for m in rows]

    response = await adapter.generate(ModelRequest(messages=history))
    assistant = append_message(
        session, conversation_id, role="assistant", content=response.content
    )
    conv.updated_at = utcnow()
    session.flush()
    return assistant


async def retrieve_chat_citations(
    session: Session,
    embedder: Embedder | None,
    *,
    query: str,
    space_id: str | None,
    limit: int = 4,
) -> list[dict[str, Any]]:
    """对话前检索用户知识库，返回可点击溯源的真实引用列表。"""
    personal = get_personal_space(session)
    service = build_retrieval_service(
        session,
        embedder,
        personal_space_id=personal.id if personal else None,
    )
    mode = "hybrid" if embedder is not None else "fts"
    try:
        hits = await service.search(query, space_id=space_id, limit=limit, mode=mode)
    except ModelAdapterError:
        hits = await service.search(query, space_id=space_id, limit=limit, mode="fts")
    return [
        {
            "item_id": h.item_id,
            "title": h.title,
            "snippet": h.snippet,
            "score": round(float(h.score), 4),
            "status": h.status,
        }
        for h in hits
    ]


def build_chat_messages_with_citations(
    history_rows: list[Message],
    *,
    user_content: str,
    citations: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """拼装带知识库引用的 OpenAI 兼容 messages 数组。"""
    system_prompt = _CHAT_SYSTEM_PROMPT
    if citations:
        refs = "\n".join(
            f"[{idx + 1}] 《{c['title']}》：{c['snippet']}"
            for idx, c in enumerate(citations)
        )
        system_prompt += (
            "\n\n以下是用户 ExplainLab 知识库中与本次问题相关的已有笔记，"
            "请优先结合这些内容作答，并在需要时指出参考了哪条笔记：\n" + refs
        )
    msgs: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for m in history_rows:
        msgs.append({"role": m.role, "content": m.content})
    msgs.append({"role": "user", "content": user_content})
    return msgs


async def stream_openai_chat(
    settings: Settings,
    messages: list[dict[str, str]],
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AsyncIterator[str]:
    """直连用户配置的 OpenAI 兼容端点，逐块产出 delta 文本。"""
    base_url = (settings.model_base_url or "").rstrip("/")
    api_key = settings.model_api_key.get_secret_value() if settings.model_api_key else ""
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.model_name,
        "messages": messages,
        "stream": True,
    }
    client_kwargs: dict[str, Any] = {
        "timeout": httpx.Timeout(60.0, connect=15.0),
        "trust_env": False,
    }
    if transport is not None:
        client_kwargs["transport"] = transport

    async with (
        httpx.AsyncClient(**client_kwargs) as client,
        client.stream("POST", url, headers=headers, json=payload) as resp,
    ):
        if resp.status_code >= 400:
            raise RuntimeError(f"模型流式请求失败（HTTP {resp.status_code}）")
        async for line in resp.aiter_lines():
            trimmed = line.strip()
            if not trimmed or not trimmed.startswith("data:"):
                continue
            data_str = trimmed[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            piece = delta.get("content")
            if isinstance(piece, str) and piece:
                yield piece