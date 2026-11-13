"""会话服务：CRUD 与真实对话。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Conversation, Message
from app.services.errors import NotFoundError
from knowledge_core.domain.entities import utcnow
from knowledge_core.model_adapter import ModelAdapter, ModelMessage, ModelRequest

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