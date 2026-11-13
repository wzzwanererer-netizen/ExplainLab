"""知识路由：对话提取与知识条目 CRUD。

持久化经由 Knowledge Core 的 KnowledgeRepository 端口实现，
来源追溯随条目一并落库；提取结果为模型真实输出，解析失败时如实返回空列表。
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import (
    ExtractRequest,
    ExtractResponse,
    KnowledgeCreate,
    KnowledgeOut,
    KnowledgeUpdate,
)
from app.db.session import get_session
from app.dependencies import get_model_adapter
from app.services.errors import NotFoundError
from app.services.knowledge import (
    SQLAlchemyKnowledgeRepository,
    extract_conversation_knowledge,
)
from app.services.spaces import get_space
from knowledge_core.domain.entities import KnowledgeItem, SourceRef, SourceType
from knowledge_core.model_adapter import ModelAdapter, ModelAdapterError

router = APIRouter(tags=["knowledge"])


@router.get("/knowledge", response_model=list[KnowledgeOut])
def list_knowledge(
    session: Annotated[Session, Depends(get_session)],
    space_id: str | None = None,
) -> list[KnowledgeOut]:
    # 个人总知识库视图需聚合 space_id 为 None 的条目（领域语义中 None 即个人总知识库），
    # 否则从无空间会话提取的知识不会出现在个人视图里。
    include_unassigned = False
    if space_id is not None:
        space = get_space(session, space_id)
        include_unassigned = space is not None and space.kind == "personal"
    items = SQLAlchemyKnowledgeRepository(session).list(
        space_id=space_id, include_unassigned=include_unassigned
    )
    return [KnowledgeOut.model_validate(i) for i in items]


@router.post("/knowledge", response_model=KnowledgeOut, status_code=201)
def create_knowledge(
    payload: KnowledgeCreate,
    session: Annotated[Session, Depends(get_session)],
) -> KnowledgeOut:
    item = KnowledgeItem(
        title=payload.title,
        content=payload.content,
        space_id=payload.space_id,
        source_refs=[SourceRef(source_type=SourceType.MANUAL)],
    )
    saved = SQLAlchemyKnowledgeRepository(session).save(item)
    session.commit()
    return KnowledgeOut.model_validate(saved)


@router.get("/knowledge/{item_id}", response_model=KnowledgeOut)
def get_knowledge(
    item_id: UUID,
    session: Annotated[Session, Depends(get_session)],
) -> KnowledgeOut:
    item = SQLAlchemyKnowledgeRepository(session).get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"知识条目不存在: {item_id}")
    return KnowledgeOut.model_validate(item)


@router.patch("/knowledge/{item_id}", response_model=KnowledgeOut)
def update_knowledge(
    item_id: UUID,
    payload: KnowledgeUpdate,
    session: Annotated[Session, Depends(get_session)],
) -> KnowledgeOut:
    repository = SQLAlchemyKnowledgeRepository(session)
    current = repository.get(item_id)
    if current is None:
        raise HTTPException(status_code=404, detail=f"知识条目不存在: {item_id}")
    updated = current.model_copy(update=payload.model_dump(exclude_unset=True))
    saved = repository.update(updated)
    session.commit()
    return KnowledgeOut.model_validate(saved)


@router.delete("/knowledge/{item_id}", status_code=204)
def delete_knowledge(
    item_id: UUID,
    session: Annotated[Session, Depends(get_session)],
) -> None:
    deleted = SQLAlchemyKnowledgeRepository(session).delete(item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"知识条目不存在: {item_id}")
    session.commit()


@router.post(
    "/conversations/{conversation_id}/extract",
    response_model=ExtractResponse,
)
async def extract_knowledge(
    conversation_id: str,
    payload: ExtractRequest,
    session: Annotated[Session, Depends(get_session)],
    adapter: Annotated[ModelAdapter, Depends(get_model_adapter)],
) -> ExtractResponse:
    try:
        items = await extract_conversation_knowledge(
            session, adapter, conversation_id, space_id=payload.space_id
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ModelAdapterError as exc:
        raise HTTPException(status_code=502, detail=f"模型调用失败: {exc}") from exc
    session.commit()
    return ExtractResponse(
        count=len(items),
        items=[KnowledgeOut.model_validate(i) for i in items],
    )