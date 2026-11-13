"""会话路由：CRUD 与真实模型对话。

模型未配置时由依赖层返回 503；模型调用失败如实返回 502，
失败请求不落库（会话关闭即回滚），不产生半成品数据。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import (
    ChatRequest,
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    MessageOut,
)
from app.db.session import get_session
from app.dependencies import get_model_adapter
from app.services import conversations as conversation_service
from app.services.errors import NotFoundError
from knowledge_core.model_adapter import ModelAdapter, ModelAdapterError

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