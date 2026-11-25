"""会话路由：CRUD 与真实模型对话。

模型未配置时由依赖层返回 503；模型调用失败如实返回 502，
失败请求不落库（会话关闭即回滚），不产生半成品数据。
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    ChatRequest,
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    MessageOut,
)
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.dependencies import get_embedder, get_model_adapter
from app.models import Message
from app.services import conversations as conversation_service
from app.services.errors import NotFoundError
from knowledge_core.domain.entities import utcnow
from knowledge_core.model_adapter import ModelAdapter, ModelAdapterError
from knowledge_core.ports import Embedder

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    session: Annotated[Session, Depends(get_session)],
    space_id: str | None = None,
) -> list[ConversationOut]:
    rows = conversation_service.list_conversations(session, space_id=space_id)
    return [ConversationOut.model_validate(c) for c in rows]


@router.post("", response_model=ConversationDetail, status_code=201)
def create_conversation(
    payload: ConversationCreate,
    session: Annotated[Session, Depends(get_session)],
) -> ConversationDetail:
    conv = conversation_service.create_conversation(
        session, title=payload.title, space_id=payload.space_id
    )
    session.commit()
    return ConversationDetail.model_validate(conv)


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ConversationDetail:
    conv = conversation_service.get_conversation(session, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail=f"会话不存在: {conversation_id}")
    return ConversationDetail.model_validate(conv)


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> None:
    deleted = conversation_service.delete_conversation(session, conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"会话不存在: {conversation_id}")
    session.commit()


@router.post("/{conversation_id}/chat", response_model=MessageOut)
async def chat(
    conversation_id: str,
    payload: ChatRequest,
    session: Annotated[Session, Depends(get_session)],
    adapter: Annotated[ModelAdapter, Depends(get_model_adapter)],
) -> MessageOut:
    try:
        message = await conversation_service.chat(
            session, adapter, conversation_id, content=payload.content
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ModelAdapterError as exc:
        raise HTTPException(status_code=502, detail=f"模型调用失败: {exc}") from exc
    session.commit()
    return MessageOut.model_validate(message)


@router.post("/{conversation_id}/chat/stream")
async def chat_stream(
    conversation_id: str,
    payload: ChatRequest,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    embedder: Annotated[Embedder | None, Depends(get_embedder)],
) -> StreamingResponse:
    """SSE 流式对话：先推送知识库引用溯源，再逐字流式推送模型回复，完成后原子落库。"""
    if (
        not settings.model_base_url
        or not settings.model_api_key
        or not settings.model_name
    ):
        raise HTTPException(
            status_code=503,
            detail=(
                "模型未配置：请在 backend/.env 设置 "
                "MODEL_PROVIDER、MODEL_BASE_URL、MODEL_API_KEY、MODEL_NAME"
            ),
        )

    conv = conversation_service.get_conversation(session, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail=f"会话不存在: {conversation_id}")

    history_rows = list(
        session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        ).all()
    )
    citations = await conversation_service.retrieve_chat_citations(
        session,
        embedder,
        query=payload.content,
        space_id=conv.space_id,
        limit=4,
    )
    messages = conversation_service.build_chat_messages_with_citations(
        history_rows,
        user_content=payload.content,
        citations=citations,
    )

    def _sse(event: dict) -> str:
        return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    async def event_generator():
        yield _sse({"type": "citations", "citations": citations})
        chunks: list[str] = []
        try:
            async for piece in conversation_service.stream_openai_chat(
                settings, messages
            ):
                chunks.append(piece)
                yield _sse({"type": "delta", "content": piece})

            full_reply = "".join(chunks).strip()
            if not full_reply:
                raise RuntimeError("模型未返回有效文本内容")

            conversation_service.append_message(
                session, conversation_id, role="user", content=payload.content
            )
            assistant = conversation_service.append_message(
                session, conversation_id, role="assistant", content=full_reply
            )
            conv.updated_at = utcnow()
            session.commit()
            yield _sse(
                {
                    "type": "done",
                    "message": MessageOut.model_validate(assistant).model_dump(
                        mode="json"
                    ),
                }
            )
        except Exception as exc:
            session.rollback()
            detail = (
                str(exc)
                if isinstance(exc, RuntimeError)
                else f"模型流式调用失败: {type(exc).__name__}"
            )
            yield _sse({"type": "error", "detail": detail})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )