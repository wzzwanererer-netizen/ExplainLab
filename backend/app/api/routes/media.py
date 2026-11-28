"""知识条目多模态媒体附件路由（图片 / 音频 / 视频 Range 流式播放 / PDF）。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.models import KnowledgeItemORM, KnowledgeSpace
from app.services import doc_preview
from app.services import media as media_service

router = APIRouter(tags=["media"])


class MediaItemOut(BaseModel):
    id: str
    item_id: str
    filename: str
    kind: str
    mime: str
    size_bytes: int
    url: str
    created_at: str


class LibraryMediaItemOut(MediaItemOut):
    item_title: str
    space_id: str | None
    space_name: str | None


def _to_out(rec: media_service.MediaRecord) -> MediaItemOut:
    return MediaItemOut(
        id=rec.id,
        item_id=rec.item_id,
        filename=rec.filename,
        kind=rec.kind,
        mime=rec.mime,
        size_bytes=rec.size_bytes,
        url=f"/api/knowledge/{rec.item_id}/media/{rec.id}",
        created_at=rec.created_at,
    )


def _require_item(session: Session, item_id: str) -> KnowledgeItemORM:
    item = session.get(KnowledgeItemORM, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"知识条目不存在: {item_id}")
    return item


def _iter_file_range(path: Path, start: int, end: int, chunk_size: int = 65536) -> Iterator[bytes]:
    with path.open("rb") as fh:
        fh.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = fh.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


@router.get("/media/library", response_model=list[LibraryMediaItemOut])
def list_media_library(
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    kind: str | None = Query(default=None),
) -> list[LibraryMediaItemOut]:
    """独立文件库视图：聚合全库所有 Word/Excel/PPT/PDF/图片/音视频，保留所属知识条目与空间引用。"""
    records = media_service.list_all_media(settings.data_dir, kind=kind)
    if not records:
        return []
    item_ids = {r.item_id for r in records}
    items_map = {
        row.id: row
        for row in session.scalars(
            select(KnowledgeItemORM).where(KnowledgeItemORM.id.in_(item_ids))
        ).all()
    }
    spaces_map = {s.id: s.name for s in session.scalars(select(KnowledgeSpace)).all()}
    result: list[LibraryMediaItemOut] = []
    for r in records:
        owner = items_map.get(r.item_id)
        if owner is None:
            continue
        result.append(
            LibraryMediaItemOut(
                id=r.id,
                item_id=r.item_id,
                filename=r.filename,
                kind=r.kind,
                mime=r.mime,
                size_bytes=r.size_bytes,
                url=f"/api/knowledge/{r.item_id}/media/{r.id}",
                created_at=r.created_at,
                item_title=owner.title,
                space_id=owner.space_id,
                space_name=spaces_map.get(owner.space_id, "") if owner.space_id else None,
            )
        )
    return result


@router.get("/knowledge/{item_id}/media", response_model=list[MediaItemOut])
def list_item_media(
    item_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[MediaItemOut]:
    _require_item(session, item_id)
    rows = media_service.list_media(settings.data_dir, item_id)
    out: list[MediaItemOut] = []
    for r in rows:
        fixed_kind = media_service.classify_media_kind(r.filename, r.mime)
        out.append(
            MediaItemOut(
                id=r.id,
                item_id=r.item_id,
                filename=r.filename,
                kind=fixed_kind,
                mime=r.mime,
                size_bytes=r.size_bytes,
                url=f"/api/knowledge/{r.item_id}/media/{r.id}",
                created_at=r.created_at,
            )
        )
    return out


@router.post("/knowledge/{item_id}/media", response_model=MediaItemOut, status_code=201)
async def upload_item_media(
    item_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    filename: str = Query(default="file.bin", max_length=200),
) -> MediaItemOut:
    _require_item(session, item_id)
    body = await request.body()
    content_type = request.headers.get("content-type", "application/octet-stream")
    try:
        rec = media_service.save_media_bytes(
            settings.data_dir,
            item_id,
            filename=filename,
            content=body,
            mime=content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_out(rec)


@router.get("/knowledge/{item_id}/media/{media_id}/preview")
def preview_item_media(
    item_id: str,
    media_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    found = media_service.get_media_file(settings.data_dir, item_id, media_id)
    if found is None:
        raise HTTPException(status_code=404, detail="媒体附件不存在")
    rec, path = found
    fixed_kind = media_service.classify_media_kind(rec.filename, rec.mime)
    return doc_preview.build_document_preview(
        path,
        kind=fixed_kind,
        stream_url=f"/api/knowledge/{item_id}/media/{media_id}",
        data_dir=settings.data_dir,
    )


@router.post("/knowledge/{item_id}/media/{media_id}/reveal")
def reveal_item_media(
    item_id: str,
    media_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
    open_os: bool = True,
) -> dict[str, str]:
    try:
        resolved = media_service.reveal_media_in_file_manager(
            settings.data_dir, item_id, media_id, open_os=open_os
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"path": resolved}


@router.get("/knowledge/{item_id}/media/{media_id}")
def stream_item_media(
    item_id: str,
    media_id: str,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> StreamingResponse:
    found = media_service.get_media_file(settings.data_dir, item_id, media_id)
    if found is None:
        raise HTTPException(status_code=404, detail="媒体附件不存在")
    rec, path = found
    file_size = path.stat().st_size
    encoded_name = quote(rec.filename)
    base_headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": f"inline; filename*=UTF-8''{encoded_name}",
    }

    range_header = request.headers.get("range")
    if range_header:
        parsed = media_service.parse_byte_range(range_header, file_size)
        if parsed is None:
            raise HTTPException(
                status_code=416,
                detail="请求范围越界",
                headers={"Content-Range": f"bytes */{file_size}"},
            )
        start, end = parsed
        headers = {
            **base_headers,
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(end - start + 1),
        }
        return StreamingResponse(
            _iter_file_range(path, start, end),
            status_code=206,
            media_type=rec.mime,
            headers=headers,
        )

    headers = {**base_headers, "Content-Length": str(file_size)}
    return StreamingResponse(
        _iter_file_range(path, 0, max(0, file_size - 1)),
        status_code=200,
        media_type=rec.mime,
        headers=headers,
    )


@router.delete("/knowledge/{item_id}/media/{media_id}", status_code=204)
def delete_item_media(
    item_id: str,
    media_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    _require_item(session, item_id)
    media_service.delete_media(settings.data_dir, item_id, media_id)
