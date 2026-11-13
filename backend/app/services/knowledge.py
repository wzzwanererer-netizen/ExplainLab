"""知识持久化与提取装配。

SQLAlchemyKnowledgeRepository 实现 knowledge_core.ports.KnowledgeRepository 端口，
负责领域实体与 ORM 的映射。提取工作流复用 Knowledge Core 的 KnowledgeService。
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Conversation, KnowledgeItemORM, SourceRefORM
from app.services.errors import NotFoundError
from knowledge_core.domain.entities import (
    KnowledgeItem,
    KnowledgeStatus,
    SourceRef,
    SourceType,
    utcnow,
)
from knowledge_core.extraction.llm import LLMExtractionService
from knowledge_core.model_adapter import ModelAdapter, ModelMessage
from knowledge_core.services import KnowledgeService


def _to_entity(row: KnowledgeItemORM) -> KnowledgeItem:
    return KnowledgeItem(
        id=UUID(row.id),
        title=row.title,
        content=row.content,
        status=KnowledgeStatus(row.status),
        space_id=row.space_id,
        source_refs=[
            SourceRef(
                id=UUID(s.id),
                source_type=SourceType(s.source_type),
                uri=s.uri,
                conversation_id=s.conversation_id,
                excerpt=s.excerpt,
                created_at=s.created_at,
            )
            for s in row.source_refs
        ],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SQLAlchemyKnowledgeRepository:
    """KnowledgeRepository 端口的 SQLAlchemy 实现。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, item: KnowledgeItem) -> KnowledgeItem:
        row = KnowledgeItemORM(
            id=str(item.id),
            space_id=item.space_id,
            title=item.title,
            content=item.content,
            status=item.status.value,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        row.source_refs = [
            SourceRefORM(
                id=str(s.id),
                source_type=s.source_type.value,
                uri=s.uri,
                conversation_id=s.conversation_id,
                excerpt=s.excerpt,
                created_at=s.created_at,
            )
            for s in item.source_refs
        ]
        self._session.add(row)
        self._session.flush()
        return _to_entity(row)

    def get(self, item_id: UUID) -> KnowledgeItem | None:
        row = self._session.get(KnowledgeItemORM, str(item_id))
        return _to_entity(row) if row is not None else None

    def list(
        self, *, space_id: str | None = None, include_unassigned: bool = False
    ) -> list[KnowledgeItem]:
        stmt = select(KnowledgeItemORM).order_by(KnowledgeItemORM.created_at.desc())
        if space_id is not None:
            if include_unassigned:
                stmt = stmt.where(
                    or_(
                        KnowledgeItemORM.space_id == space_id,
                        KnowledgeItemORM.space_id.is_(None),
                    )
                )
            else:
                stmt = stmt.where(KnowledgeItemORM.space_id == space_id)
        return [_to_entity(row) for row in self._session.scalars(stmt)]

    def update(self, item: KnowledgeItem) -> KnowledgeItem:
        row = self._session.get(KnowledgeItemORM, str(item.id))
        if row is None:
            raise NotFoundError(f"知识条目不存在: {item.id}")
        row.title = item.title
        row.content = item.content
        row.status = item.status.value
        row.space_id = item.space_id
        row.updated_at = utcnow()
        self._session.flush()
        return _to_entity(row)

    def delete(self, item_id: UUID) -> bool:
        row = self._session.get(KnowledgeItemORM, str(item_id))
        if row is None:
            return False
        self._session.delete(row)
        self._session.flush()
        return True


async def extract_conversation_knowledge(
    session: Session,
    adapter: ModelAdapter,
    conversation_id: str,
    *,
    space_id: str | None = None,
) -> list[KnowledgeItem]:
    """从会话提取知识并入库，返回已持久化条目。"""
    conv = session.get(Conversation, conversation_id)
    if conv is None:
        raise NotFoundError(f"会话不存在: {conversation_id}")
    messages = [ModelMessage(role=m.role, content=m.content) for m in conv.messages]
    target_space = space_id if space_id is not None else conv.space_id
    repository = SQLAlchemyKnowledgeRepository(session)
    service = KnowledgeService(LLMExtractionService(adapter), repository)
    return await service.extract_and_store(
        messages,
        space_id=target_space,
        conversation_id=conversation_id,
    )