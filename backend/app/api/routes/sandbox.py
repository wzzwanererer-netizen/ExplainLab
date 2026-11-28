"""交互式动态原理沙盒路由（GET / POST generate / DELETE）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.dependencies import get_model_adapter
from app.models import KnowledgeItemORM
from app.services import sandbox as sandbox_service
from knowledge_core.model_adapter import ModelAdapter, ModelAdapterError

router = APIRouter(prefix="/knowledge", tags=["sandbox"])


class SandboxGenerateRequest(BaseModel):
    instruction: str | None = Field(default=None, max_length=500)


class SandboxOut(BaseModel):
    item_id: str
    exists: bool
    html: str | None
    updated_at: str | None


def _require_item(session: Session, item_id: str) -> KnowledgeItemORM:
    item = session.get(KnowledgeItemORM, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"知识条目不存在: {item_id}")
    return item


@router.get("/{item_id}/sandbox", response_model=SandboxOut)
def get_item_sandbox(
    item_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SandboxOut:
    _require_item(session, item_id)
    rec = sandbox_service.get_sandbox(settings.data_dir, item_id)
    return SandboxOut(
        item_id=rec.item_id,
        exists=rec.exists,
        html=rec.html,
        updated_at=rec.updated_at,
    )


@router.post("/{item_id}/sandbox/generate", response_model=SandboxOut)
async def generate_item_sandbox(
    item_id: str,
    payload: SandboxGenerateRequest,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    adapter: Annotated[ModelAdapter, Depends(get_model_adapter)],
) -> SandboxOut:
    item = _require_item(session, item_id)
    try:
        rec = await sandbox_service.generate_sandbox(
            adapter,
            data_dir=settings.data_dir,
            item_id=item.id,
            title=item.title,
            content=item.content,
            instruction=payload.instruction,
        )
    except (ModelAdapterError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"动态沙盒生成失败: {exc}") from exc
    return SandboxOut(
        item_id=rec.item_id,
        exists=rec.exists,
        html=rec.html,
        updated_at=rec.updated_at,
    )


@router.delete("/{item_id}/sandbox", status_code=204)
def delete_item_sandbox(
    item_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    _require_item(session, item_id)
    sandbox_service.delete_sandbox(settings.data_dir, item_id)
