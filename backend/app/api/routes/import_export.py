"""Markdown 导入/导出路由（V2 A1-04 Batch A，非附件）。

写入口全部为同步 ``def``（D20）：FastAPI 在线程池执行，``MarkdownService``
在同一线程内自建 S0/S1 会话并持有同步身份锁。路由不触碰业务规则，
只做入参拼装、稳定错误码映射与 commit 后索引同步。
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import io
import json
import logging
import zipfile
from typing import Annotated, Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.schemas import MarkdownExportIn, MarkdownImportIn
from app.dependencies import get_embedder, get_markdown_service
from app.services.import_coordinator import IMPORT_LOCK_TIMEOUT
from app.services.markdown import (
    ATTACHMENT_EXPORT_UNSUPPORTED,
    MarkdownImportDocument,
    MarkdownService,
    MarkdownServiceError,
)
from app.services.retrieval import sync_index
from app.services.source_identity import SourceIdentityError
from knowledge_core.markdown.service import ExporterMetadataError
from knowledge_core.ports import Embedder

logger = logging.getLogger(__name__)

router = APIRouter(tags=["import-export"])


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, MarkdownServiceError):
        return HTTPException(status_code=exc.status_code, detail=exc.code)
    if isinstance(exc, SourceIdentityError):
        return HTTPException(status_code=409, detail=exc.code)
    if isinstance(exc, ExporterMetadataError):
        return HTTPException(status_code=409, detail=exc.code)
    return HTTPException(status_code=500, detail="IMPORT_FAILED")


def _to_document(
    *,
    content: str,
    filename: str | None,
    target_item_id: UUID | None,
    frontmatter_resolution: str | None,
    attachments_requested: bool = False,
) -> MarkdownImportDocument:
    return MarkdownImportDocument(
        content=content,
        filename=filename,
        target_item_id=target_item_id,
        frontmatter_resolution=frontmatter_resolution,
        attachments_requested=attachments_requested,
    )


def _from_archive(encoded: str) -> tuple[list[MarkdownImportDocument], dict[str, Any] | None]:
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise MarkdownServiceError("IMPORT_ARCHIVE_INVALID", "ZIP base64 非法") from exc
    documents: list[MarkdownImportDocument] = []
    manifest: dict[str, Any] | None = None
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                name = info.filename.replace("\\", "/").split("/")[-1]
                if not name:
                    continue
                data = archive.read(info)
                if name == "manifest.json":
                    try:
                        loaded = json.loads(data.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raise MarkdownServiceError(
                            "IMPORT_ARCHIVE_INVALID", "manifest.json 非法"
                        ) from exc
                    if not isinstance(loaded, dict):
                        raise MarkdownServiceError(
                            "IMPORT_ARCHIVE_INVALID", "manifest.json 非对象"
                        )
                    manifest = loaded
                    continue
                if not name.lower().endswith((".md", ".markdown")):
                    continue
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise MarkdownServiceError(
                        "IMPORT_ARCHIVE_INVALID", "ZIP 内 Markdown 非 UTF-8"
                    ) from exc
                documents.append(
                    _to_document(
                        content=text,
                        filename=name,
                        target_item_id=None,
                        frontmatter_resolution=None,
                    )
                )
    except zipfile.BadZipFile as exc:
        raise MarkdownServiceError("IMPORT_ARCHIVE_INVALID", "ZIP 结构非法") from exc
    return documents, manifest


def _collect_documents(
    body: MarkdownImportIn,
) -> tuple[list[MarkdownImportDocument], dict[str, Any] | None]:
    manifest = body.manifest
    documents: list[MarkdownImportDocument] = []
    if body.archive_base64:
        documents, archive_manifest = _from_archive(body.archive_base64)
        if archive_manifest is not None:
            manifest = archive_manifest
    elif body.documents is not None:
        documents = [
            _to_document(
                content=doc.content,
                filename=doc.filename,
                target_item_id=doc.target_item_id,
                frontmatter_resolution=doc.frontmatter_resolution,
                attachments_requested=bool(doc.attachments),
            )
            for doc in body.documents
        ]
    elif body.content is not None:
        documents = [
            _to_document(
                content=body.content,
                filename=body.filename,
                target_item_id=body.target_item_id,
                frontmatter_resolution=body.frontmatter_resolution,
                attachments_requested=bool(body.attachments),
            )
        ]
    if not documents:
        raise MarkdownServiceError("IMPORT_EMPTY", "no documents")
    return documents, manifest


def _sync_indexes(session_factory, index_ids: list[UUID], embedder: Embedder | None) -> str:
    if not index_ids:
        return "ok"
    session: Session = session_factory()
    try:
        asyncio.run(sync_index(session, embedder, index_ids=index_ids))
        session.commit()
        return "ok"
    except Exception as exc:  # noqa: BLE001 - 提交后同步失败只告警，不回滚业务数据
        session.rollback()
        logger.warning("导入后索引同步失败: %s", type(exc).__name__)
        return "failed"
    finally:
        session.close()


def _import_response(
    service: MarkdownService,
    documents: list[MarkdownImportDocument],
    *,
    space_id: str | None,
    manifest: dict[str, Any] | None,
    batch_id: str | None,
    embedder: Embedder | None,
    reject_attachments: bool,
    response: Response,
    single: bool,
) -> dict[str, Any]:
    try:
        outcome = service.import_documents(
            documents,
            space_id=space_id,
            manifest=manifest,
            batch_id=batch_id,
            reject_attachments=reject_attachments,
        )
    except (MarkdownServiceError, SourceIdentityError, ExporterMetadataError) as exc:
        raise _http_error(exc) from exc
    index_state = _sync_indexes(service.session_factory, outcome.index_ids, embedder)
    body = outcome.report.model_dump(mode="json")
    body["index_sync"] = index_state
    if single and outcome.report.items:
        first = outcome.report.items[0]
        if first.status.value == "error" and IMPORT_LOCK_TIMEOUT in first.errors:
            raise HTTPException(status_code=409, detail=IMPORT_LOCK_TIMEOUT)
        if first.status.value == "pending_review":
            response.status_code = 202
        elif first.status.value == "created":
            response.status_code = 201
    return body


@router.post("/knowledge/import")
def import_markdown(
    body: MarkdownImportIn,
    response: Response,
    service: Annotated[MarkdownService, Depends(get_markdown_service)],
    embedder: Annotated[Embedder | None, Depends(get_embedder)],
) -> dict[str, Any]:
    documents, manifest = _collect_documents(body)
    return _import_response(
        service,
        documents,
        space_id=body.space_id,
        manifest=manifest,
        batch_id=body.batch_id,
        embedder=embedder,
        reject_attachments=True,
        response=response,
        single=True,
    )


@router.post("/knowledge/import/batch")
def import_markdown_batch(
    body: MarkdownImportIn,
    response: Response,
    service: Annotated[MarkdownService, Depends(get_markdown_service)],
    embedder: Annotated[Embedder | None, Depends(get_embedder)],
) -> dict[str, Any]:
    documents, manifest = _collect_documents(body)
    return _import_response(
        service,
        documents,
        space_id=body.space_id,
        manifest=manifest,
        batch_id=body.batch_id,
        embedder=embedder,
        reject_attachments=False,
        response=response,
        single=False,
    )


@router.post("/knowledge/export")
def export_markdown(
    body: MarkdownExportIn,
    service: Annotated[MarkdownService, Depends(get_markdown_service)],
) -> Response:
    if body.include_attachments:
        raise HTTPException(status_code=400, detail=ATTACHMENT_EXPORT_UNSUPPORTED)
    try:
        payload, _ = service.export_documents(
            body.ids,
            space_id=body.space_id,
            include_attachments=False,
        )
    except (MarkdownServiceError, SourceIdentityError, ExporterMetadataError) as exc:
        raise _http_error(exc) from exc
    return Response(
        content=payload,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="explainlab-export.zip"',
        },
    )


@router.get("/knowledge/{item_id}/markdown")
def export_single_markdown(
    item_id: UUID,
    service: Annotated[MarkdownService, Depends(get_markdown_service)],
) -> Response:
    try:
        outcome = service.export_single(item_id)
    except (MarkdownServiceError, SourceIdentityError, ExporterMetadataError) as exc:
        raise _http_error(exc) from exc
    disposition = f"attachment; filename*=UTF-8''{quote(outcome.filename)}"
    headers = {
        "Content-Disposition": disposition,
        "X-ExplainLab-Item-Id": str(outcome.item_id),
        "X-ExplainLab-Document-Content-Hash": outcome.content_hash,
        "X-ExplainLab-Document-Payload-Hash": outcome.payload_hash,
        "X-ExplainLab-Exporter-Instance-Id": service.exporter_instance_id,
    }
    if outcome.source_instance_id:
        headers["X-ExplainLab-Source-Instance-Id"] = outcome.source_instance_id
    if outcome.source_document_id:
        headers["X-ExplainLab-Source-Document-Id"] = outcome.source_document_id
    return Response(
        content=outcome.text.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers=headers,
    )