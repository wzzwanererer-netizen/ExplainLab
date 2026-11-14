"""M5 交互式知识实验路由：测验 / 对比 / 学习路径。

POST /experiments/sessions 创建会话（quiz/compare 需模型，chain 确定性）；
GET 列表/详情返回对外视图（测验未完成时隐藏正确答案与解析）；
POST {id}/answer 单题即时判分；POST {id}/complete 汇总判分并标记完成；DELETE 删除。
模型未配置 503、调用失败 502、参数不合法 400、资源不存在 404。
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import (
    AnswerFeedbackOut,
    AttemptOut,
    ExperimentAnswer,
    ExperimentComplete,
    ExperimentCompleteResult,
    ExperimentCreate,
    ExperimentOut,
)
from app.db.session import get_session
from app.dependencies import get_model_adapter_optional
from app.services.experiments import (
    SQLAlchemyExperimentRepository,
    build_experiment_service,
)
from app.services.spaces import get_space
from knowledge_core.experiments import (
    ExperimentKind,
    ExperimentSession,
    InvalidExperimentError,
    ModelRequiredError,
)
from knowledge_core.experiments.errors import ExperimentNotFoundError
from knowledge_core.model_adapter import ModelAdapter, ModelAdapterError

router = APIRouter(tags=["experiments"])


def _get_session(session: Session, session_id: UUID) -> ExperimentSession:
    found = SQLAlchemyExperimentRepository(session).get_session(session_id)
    if found is None:
        raise HTTPException(status_code=404, detail=f"实验会话不存在: {session_id}")
    return found


@router.post("/experiments/sessions", response_model=ExperimentOut, status_code=201)
async def create_session(
    payload: ExperimentCreate,
    session: Annotated[Session, Depends(get_session)],
    adapter: Annotated[ModelAdapter | None, Depends(get_model_adapter_optional)],
) -> ExperimentOut:
    include_unassigned = False
    if payload.space_id is not None:
        space = get_space(session, payload.space_id)
        if space is None:
            raise HTTPException(status_code=404, detail=f"知识空间不存在: {payload.space_id}")
        include_unassigned = space.kind == "personal"
    service = build_experiment_service(session, adapter)
    try:
        created = await service.create(
            payload.kind,
            payload.item_ids,
            space_id=payload.space_id,
            include_unassigned=include_unassigned,
            count=payload.count,
            seed_id=payload.seed_id,
        )
    except ModelRequiredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ExperimentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidExperimentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ModelAdapterError as exc:
        raise HTTPException(status_code=502, detail=f"模型调用失败: {exc}") from exc
    session.commit()
    return ExperimentOut.model_validate(service.public_view(created))


@router.get("/experiments/sessions", response_model=list[ExperimentOut])
def list_sessions(
    session: Annotated[Session, Depends(get_session)],
    kind: ExperimentKind | None = None,
    space_id: str | None = None,
) -> list[ExperimentOut]:
    sessions = SQLAlchemyExperimentRepository(session).list_sessions(
        kind=kind, space_id=space_id
    )
    service = build_experiment_service(session, None)
    return [ExperimentOut.model_validate(service.public_view(s)) for s in sessions]


@router.get("/experiments/sessions/{session_id}", response_model=ExperimentOut)
def get_session_view(
    session_id: UUID,
    session: Annotated[Session, Depends(get_session)],
) -> ExperimentOut:
    found = _get_session(session, session_id)
    service = build_experiment_service(session, None)
    return ExperimentOut.model_validate(service.public_view(found))


@router.post(
    "/experiments/sessions/{session_id}/answer", response_model=AnswerFeedbackOut
)
def answer_question(
    session_id: UUID,
    payload: ExperimentAnswer,
    session: Annotated[Session, Depends(get_session)],
) -> AnswerFeedbackOut:
    found = _get_session(session, session_id)
    service = build_experiment_service(session, None)
    try:
        feedback = service.answer(found, payload.index, payload.value)
    except InvalidExperimentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AnswerFeedbackOut.model_validate(feedback)


@router.post(
    "/experiments/sessions/{session_id}/complete",
    response_model=ExperimentCompleteResult,
)
def complete_session(
    session_id: UUID,
    payload: ExperimentComplete,
    session: Annotated[Session, Depends(get_session)],
) -> ExperimentCompleteResult:
    found = _get_session(session, session_id)
    service = build_experiment_service(session, None)
    attempt = service.complete(found, [a.model_dump() for a in payload.answers])
    session.commit()
    updated = _get_session(session, session_id)
    return ExperimentCompleteResult(
        session=ExperimentOut.model_validate(service.public_view(updated)),
        attempt=AttemptOut.model_validate(attempt),
    )


@router.delete("/experiments/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: UUID,
    session: Annotated[Session, Depends(get_session)],
) -> None:
    if not SQLAlchemyExperimentRepository(session).delete_session(session_id):
        raise HTTPException(status_code=404, detail=f"实验会话不存在: {session_id}")
    session.commit()