"""知识路由：对话提取与知识条目 CRUD。

持久化经由 Knowledge Core 的 KnowledgeRepository 端口实现，
来源追溯随条目一并落库；提取结果为模型真实输出，解析失败时如实返回空列表。
M2：active 条目的改 / 删经 ReviewService 门禁，返回 202 + 审核单；草稿直接应用。
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.schemas import (
    ExtractRequest,
    ExtractResponse,
    KnowledgeCreate,
    KnowledgeOut,
    KnowledgeUpdate,
    ReviewOut,
)
from app.db.session import get_session
from app.dependencies import get_model_adapter
from app.services.errors import NotFoundError
from app.services.governance import build_review_service
from app.services.knowledge import (
    SQLAlchemyKnowledgeRepository,
    extract_conversation_knowledge,
)
from app.services.spaces import get_space
from knowledge_core.domain.entities import (
    KnowledgeItem,
    ReviewAction,
    SourceRef,
    SourceType,
)
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


@router.patch("/knowledge/{item_id}")
async def update_knowledge(
    item_id: UUID,
    payload: KnowledgeUpdate,
    session: Annotated[Session, Depends(get_session)],
    response: Response,
) -> KnowledgeOut | ReviewOut:
    repository = SQLAlchemyKnowledgeRepository(session)
    current = repository.get(item_id)
    if current is None:
        raise HTTPException(status_code=404, detail=f"知识条目不存在: {item_id}")
    # active 的编辑属重要变更：仅生成 pending 审核单（202），批准后才应用
    service = build_review_service(session)
    review = await service.submit(
        item_id,
        ReviewAction.UPDATE_ITEM,
        payload.model_dump(exclude_unset=True, mode="json"),
    )
    session.commit()
    if review is not None:
        response.status_code = 202
        return ReviewOut.model_validate(review)
    updated = repository.get(item_id)
    assert updated is not None
    return KnowledgeOut.model_validate(updated)


@router.delete("/knowledge/{item_id}")
async def delete_knowledge(
    item_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    response: Response,
) -> ReviewOut | None:
    repository = SQLAlchemyKnowledgeRepository(session)
    if repository.get(item_id) is None:
        raise HTTPException(status_code=404, detail=f"知识条目不存在: {item_id}")
    service = build_review_service(session)
    review = await service.submit(item_id, ReviewAction.DELETE_ITEM)
    session.commit()
    if review is not None:
        response.status_code = 202
        return ReviewOut.model_validate(review)
    response.status_code = 204
    return None


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