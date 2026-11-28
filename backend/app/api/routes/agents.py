"""AI 助手副库管理与本地会话吸尘器路由。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.dependencies import get_model_adapter
from app.services import agent_hub
from knowledge_core.model_adapter import ModelAdapter

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentStatusOut(BaseModel):
    id: str
    name: str
    description: str
    space_name: str
    space_id: str | None
    installed: bool
    connected: bool
    item_count: int
    session_dir: str | None
    session_files_count: int
    unprocessed_count: int
    rule_installed: bool
    last_vacuum_at: str | None
    is_custom: bool


class AgentAddIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=200)
    session_dir: str | None = Field(default=None, max_length=500)
    write_rule: bool = True


class SessionFilePreviewOut(BaseModel):
    file_path: str
    label: str
    preview: str
    updated_at: str
    size_kb: float
    processed: bool
    created_count: int = 0


class VacuumRequestIn(BaseModel):
    agent_name: str | None = Field(default=None, max_length=64)
    max_sessions: int = Field(default=3, ge=1, le=10)
    session_files: list[str] | None = Field(default=None, max_length=20)


class VacuumCreatedItemOut(BaseModel):
    id: str
    agent_name: str
    space_id: str
    title: str
    source_file: str


class VacuumReportOut(BaseModel):
    scanned_sessions: int
    skipped_sessions: int
    created_items: list[VacuumCreatedItemOut]
    errors: list[str]


class CompletedTaskSuggestionOut(BaseModel):
    suggestion_id: str
    agent_id: str
    agent_name: str
    space_id: str | None
    file_path: str
    signature: str
    label: str
    preview: str
    updated_at: str


class DismissSuggestionIn(BaseModel):
    file_path: str = Field(min_length=1, max_length=1000)
    signature: str = Field(min_length=1, max_length=128)


class HandoffSessionSummaryOut(BaseModel):
    agent_id: str
    agent_name: str
    label: str
    preview: str
    updated_at: str
    size_kb: float
    file_path: str


class HandoffReadIn(BaseModel):
    file_path: str = Field(min_length=1, max_length=1000)
    max_chars: int = Field(default=12000, ge=1000, le=30000)


class HandoffSessionContentOut(BaseModel):
    agent_id: str
    agent_name: str
    label: str
    updated_at: str
    file_path: str
    dialogue: str
    truncated: bool


def _to_out(item: agent_hub.AgentStatus) -> AgentStatusOut:
    return AgentStatusOut(
        id=item.id,
        name=item.name,
        description=item.description,
        space_name=item.space_name,
        space_id=item.space_id,
        installed=item.installed,
        connected=item.connected,
        item_count=item.item_count,
        session_dir=item.session_dir,
        session_files_count=item.session_files_count,
        unprocessed_count=item.unprocessed_count,
        rule_installed=item.rule_installed,
        last_vacuum_at=item.last_vacuum_at,
        is_custom=item.is_custom,
    )


@router.get("/discover", response_model=list[AgentStatusOut])
def discover_agents_route(
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[AgentStatusOut]:
    return [_to_out(a) for a in agent_hub.discover_agents(session, settings.data_dir)]


@router.post("/add", response_model=AgentStatusOut)
def add_agent_route(
    payload: AgentAddIn,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AgentStatusOut:
    try:
        status = agent_hub.add_or_connect_agent(
            session,
            settings.data_dir,
            name=payload.name,
            description=payload.description,
            session_dir=payload.session_dir,
            write_rule=payload.write_rule,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_out(status)


@router.get("/media/{filename}")
def get_vacuum_media_route(
    filename: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    path = agent_hub.resolve_vacuum_media_path(settings.data_dir, filename)
    if path is None:
        raise HTTPException(status_code=404, detail="媒体文件不存在")
    return FileResponse(path)


@router.get("/handoff/sessions", response_model=list[HandoffSessionSummaryOut])
def list_handoff_sessions_route(
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    agent_name: str | None = None,
    keyword: str | None = None,
    limit: int = 12,
) -> list[HandoffSessionSummaryOut]:
    rows = agent_hub.list_handoff_sessions(
        session,
        settings.data_dir,
        agent_name=agent_name,
        keyword=keyword,
        limit=limit,
    )
    return [
        HandoffSessionSummaryOut(
            agent_id=r.agent_id,
            agent_name=r.agent_name,
            label=r.label,
            preview=r.preview,
            updated_at=r.updated_at,
            size_kb=r.size_kb,
            file_path=r.file_path,
        )
        for r in rows
    ]


@router.post("/handoff/read", response_model=HandoffSessionContentOut)
def read_handoff_session_route(
    payload: HandoffReadIn,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> HandoffSessionContentOut:
    try:
        res = agent_hub.read_handoff_session(
            session,
            settings.data_dir,
            file_path=payload.file_path,
            max_chars=payload.max_chars,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return HandoffSessionContentOut(
        agent_id=res.agent_id,
        agent_name=res.agent_name,
        label=res.label,
        updated_at=res.updated_at,
        file_path=res.file_path,
        dialogue=res.dialogue,
        truncated=res.truncated,
    )


@router.get("/{agent_id}/sessions", response_model=list[SessionFilePreviewOut])
def list_agent_sessions_route(
    agent_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[SessionFilePreviewOut]:
    rows = agent_hub.list_agent_sessions(session, settings.data_dir, agent_id)
    return [
        SessionFilePreviewOut(
            file_path=r.file_path,
            label=r.label,
            preview=r.preview,
            updated_at=r.updated_at,
            size_kb=r.size_kb,
            processed=r.processed,
            created_count=r.created_count,
        )
        for r in rows
    ]


@router.post("/vacuum", response_model=VacuumReportOut)
async def vacuum_agents_route(
    payload: VacuumRequestIn,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    adapter: Annotated[ModelAdapter, Depends(get_model_adapter)],
) -> VacuumReportOut:
    report = await agent_hub.vacuum_agent_sessions(
        session,
        adapter,
        data_dir=settings.data_dir,
        agent_name=payload.agent_name,
        max_sessions=payload.max_sessions,
        session_files=payload.session_files,
    )
    return VacuumReportOut(
        scanned_sessions=report.scanned_sessions,
        skipped_sessions=report.skipped_sessions,
        created_items=[
            VacuumCreatedItemOut(
                id=it.id,
                agent_name=it.agent_name,
                space_id=it.space_id,
                title=it.title,
                source_file=it.source_file,
            )
            for it in report.created_items
        ],
        errors=report.errors,
    )


@router.get("/completed-suggestions", response_model=list[CompletedTaskSuggestionOut])
def completed_suggestions_route(
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    include_latest: bool = False,
    idle_seconds: float = 45.0,
) -> list[CompletedTaskSuggestionOut]:
    rows = agent_hub.detect_completed_agent_tasks(
        session,
        settings.data_dir,
        idle_seconds=idle_seconds,
        include_latest=include_latest,
        mark_notified=not include_latest,
    )
    return [
        CompletedTaskSuggestionOut(
            suggestion_id=r.suggestion_id,
            agent_id=r.agent_id,
            agent_name=r.agent_name,
            space_id=r.space_id,
            file_path=r.file_path,
            signature=r.signature,
            label=r.label,
            preview=r.preview,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.post("/dismiss-suggestion")
def dismiss_suggestion_route(
    payload: DismissSuggestionIn,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, bool]:
    agent_hub.dismiss_task_suggestion(
        settings.data_dir,
        file_path=payload.file_path,
        signature=payload.signature,
    )
    return {"ok": True}
