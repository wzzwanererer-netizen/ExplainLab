"""知识空间路由：个人总知识库 + 项目空间。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import SpaceCreate, SpaceOut
from app.db.session import get_session
from app.services import spaces as space_service

router = APIRouter(prefix="/spaces", tags=["spaces"])


@router.get("", response_model=list[SpaceOut])
def list_spaces(session: Annotated[Session, Depends(get_session)]) -> list[SpaceOut]:
    return [SpaceOut.model_validate(s) for s in space_service.list_spaces(session)]


@router.post("", response_model=SpaceOut, status_code=201)
def create_space(
    payload: SpaceCreate,
    session: Annotated[Session, Depends(get_session)],
) -> SpaceOut:
    space = space_service.create_space(
        session, name=payload.name, description=payload.description
    )
    session.commit()
    return SpaceOut.model_validate(space)


@router.get("/{space_id}", response_model=SpaceOut)
def get_space(
    space_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> SpaceOut:
    space = space_service.get_space(session, space_id)
    if space is None:
        raise HTTPException(status_code=404, detail=f"知识空间不存在: {space_id}")
    return SpaceOut.model_validate(space)