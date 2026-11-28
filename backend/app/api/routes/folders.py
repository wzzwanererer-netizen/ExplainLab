"""乱文件夹哨兵（Folder Watcher）HTTP 路由。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.dependencies import get_model_adapter
from app.services import folder_watcher
from knowledge_core.model_adapter import ModelAdapter

router = APIRouter(prefix="/folders", tags=["folders"])


class FolderPresetOut(BaseModel):
    label: str
    path: str


class WatchedFolderOut(BaseModel):
    id: str
    name: str
    path: str
    space_id: str
    space_name: str
    enabled: bool
    use_ai_summary: bool
    file_count: int
    indexed_count: int
    last_scan_at: str | None
    created_at: str


class WatchedFolderAddIn(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    name: str | None = Field(default=None, max_length=64)
    space_id: str | None = None
    use_ai_summary: bool = False


class WatchedFolderPatchIn(BaseModel):
    enabled: bool | None = None
    use_ai_summary: bool | None = None


class FolderScanIn(BaseModel):
    max_files: int = Field(default=60, ge=1, le=2000)


class FolderScanItemOut(BaseModel):
    id: str
    title: str
    file_path: str
    kind: str


class FolderScanReportOut(BaseModel):
    folder_id: str
    scanned_files: int
    skipped_files: int
    created_items: list[FolderScanItemOut]
    errors: list[str]


class RevealPathIn(BaseModel):
    path: str = Field(min_length=1, max_length=500)


def _to_out(f: folder_watcher.WatchedFolder) -> WatchedFolderOut:
    return WatchedFolderOut(
        id=f.id,
        name=f.name,
        path=f.path,
        space_id=f.space_id,
        space_name=f.space_name,
        enabled=f.enabled,
        use_ai_summary=f.use_ai_summary,
        file_count=f.file_count,
        indexed_count=f.indexed_count,
        last_scan_at=f.last_scan_at,
        created_at=f.created_at,
    )


@router.get("/presets", response_model=list[FolderPresetOut])
def list_folder_presets() -> list[FolderPresetOut]:
    return [FolderPresetOut(**p) for p in folder_watcher.get_preset_folders()]


@router.get("", response_model=list[WatchedFolderOut])
def list_folders(
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[WatchedFolderOut]:
    return [_to_out(f) for f in folder_watcher.list_watched_folders(settings.data_dir)]


@router.post("", response_model=WatchedFolderOut, status_code=201)
def add_folder(
    payload: WatchedFolderAddIn,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WatchedFolderOut:
    try:
        created = folder_watcher.add_watched_folder(
            session,
            settings.data_dir,
            path=payload.path,
            name=payload.name,
            space_id=payload.space_id,
            use_ai_summary=payload.use_ai_summary,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_out(created)


@router.patch("/{folder_id}", response_model=WatchedFolderOut)
def patch_folder(
    folder_id: str,
    payload: WatchedFolderPatchIn,
    settings: Annotated[Settings, Depends(get_settings)],
) -> WatchedFolderOut:
    updated = folder_watcher.update_watched_folder(
        settings.data_dir,
        folder_id,
        enabled=payload.enabled,
        use_ai_summary=payload.use_ai_summary,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="监控文件夹不存在")
    return _to_out(updated)


@router.delete("/{folder_id}", status_code=204)
def remove_folder(
    folder_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    if not folder_watcher.delete_watched_folder(settings.data_dir, folder_id):
        raise HTTPException(status_code=404, detail="监控文件夹不存在")


@router.post("/{folder_id}/scan", response_model=FolderScanReportOut)
async def scan_folder(
    folder_id: str,
    payload: FolderScanIn,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    adapter: Annotated[ModelAdapter, Depends(get_model_adapter)],
) -> FolderScanReportOut:
    try:
        report = await folder_watcher.scan_watched_folder(
            session,
            adapter,
            data_dir=settings.data_dir,
            folder_id=folder_id,
            max_files=payload.max_files,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FolderScanReportOut(
        folder_id=report.folder_id,
        scanned_files=report.scanned_files,
        skipped_files=report.skipped_files,
        created_items=[
            FolderScanItemOut(
                id=it.id,
                title=it.title,
                file_path=it.file_path,
                kind=it.kind,
            )
            for it in report.created_items
        ],
        errors=report.errors,
    )


@router.post("/reveal", status_code=204)
def reveal_file(
    payload: RevealPathIn,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    try:
        folder_watcher.reveal_in_file_manager(settings.data_dir, payload.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
