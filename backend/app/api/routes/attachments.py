"""附件 HTTP 路由（V2 A1-04 Batch B，B2-T02）。

四条 item 作用域路由：上传（JSON Base64）、元数据列表、下载、删除。
全部同步 ``def``（D20）；事务由本层外层 Unit of Work 提交一次，附件服务与
Repository 不提交。下载使用服务返回的**已打开并校验的同一句柄**流式输出。
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.schemas import AttachmentOut, AttachmentUploadIn
from app.db.session import get_session
from app.dependencies import get_attachment_service
from app.services.attachment_storage import iter_file
from app.services.attachments import (
    ATTACHMENT_FAILED,
    AttachmentService,
    AttachmentServiceError,
    attachment_content_disposition,
    release_storage_guard,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["attachments"])


def _http_error(exc: AttachmentServiceError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail=exc.code,
        headers=exc.headers,
    )


def _log_failure(operation: str, exc: BaseException) -> None:
    # 只记录异常类型；不记录路径、文件名、异常文本或字节内容。
    logger.warning("attachment %s failed: %s", operation, type(exc).__name__)


def _release_failed_guard(exc: BaseException) -> None:
    release_storage_guard(getattr(exc, "attachment_guard", None))


@router.post(
    "/knowledge/{item_id}/attachments",
    response_model=AttachmentOut,
    status_code=201,
)
def upload_attachment(
    item_id: UUID,
    payload: AttachmentUploadIn,
    session: Annotated[Session, Depends(get_session)],
    service: Annotated[AttachmentService, Depends(get_attachment_service)],
    response: Response,
) -> AttachmentOut:
    try:
        result = service.upload(
            session,
            item_id,
            filename=payload.filename,
            mime=payload.mime,
            content_base64=payload.content_base64,
        )
    except AttachmentServiceError as exc:
        try:
            session.rollback()
        finally:
            _release_failed_guard(exc)
        raise _http_error(exc) from None
    except Exception as exc:  # noqa: BLE001 - stable code only
        try:
            session.rollback()
        finally:
            _release_failed_guard(exc)
        _log_failure("upload", exc)
        raise HTTPException(status_code=500, detail=ATTACHMENT_FAILED) from None

    try:
        session.commit()
    except Exception as exc:  # noqa: BLE001 - commit owner is this route
        try:
            session.rollback()
        finally:
            result.release()
        _log_failure("upload-commit", exc)
        raise HTTPException(status_code=500, detail=ATTACHMENT_FAILED) from None
    result.release()

    if result.created:
        response.status_code = 201
        response.headers["Location"] = (
            f"/api/knowledge/{item_id}/attachments/{result.attachment.id}"
        )
    else:
        response.status_code = 200
    return AttachmentOut.model_validate(result.attachment)


@router.get(
    "/knowledge/{item_id}/attachments",
    response_model=list[AttachmentOut],
)
def list_attachments(
    item_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    service: Annotated[AttachmentService, Depends(get_attachment_service)],
) -> list[AttachmentOut]:
    try:
        attachments = service.list(session, item_id)
    except AttachmentServiceError as exc:
        raise _http_error(exc) from None
    except Exception as exc:  # noqa: BLE001 - stable code only
        _log_failure("list", exc)
        raise HTTPException(status_code=500, detail=ATTACHMENT_FAILED) from None
    return [AttachmentOut.model_validate(item) for item in attachments]


@router.get(
    "/knowledge/{item_id}/attachments/{attachment_id}",
    response_model=None,
)
def download_attachment(
    item_id: UUID,
    attachment_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    service: Annotated[AttachmentService, Depends(get_attachment_service)],
) -> StreamingResponse:
    try:
        download = service.download(session, item_id, attachment_id)
    except AttachmentServiceError as exc:
        raise _http_error(exc) from None
    except Exception as exc:  # noqa: BLE001 - stable code only
        _log_failure("download", exc)
        raise HTTPException(status_code=500, detail=ATTACHMENT_FAILED) from None

    attachment = download.attachment
    handle = download.handle

    def stream():
        try:
            yield from iter_file(handle)
        finally:
            handle.close()

    headers = {
        "Content-Type": attachment.mime,
        "Content-Length": str(attachment.size),
        "Content-Disposition": attachment_content_disposition(attachment.filename),
        "ETag": f'"{attachment.storage_key}"',
        "Cache-Control": "private, max-age=0, must-revalidate",
        "X-Content-Type-Options": "nosniff",
    }
    return StreamingResponse(stream(), headers=headers, media_type=None)


@router.delete(
    "/knowledge/{item_id}/attachments/{attachment_id}",
    status_code=204,
)
def delete_attachment(
    item_id: UUID,
    attachment_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    service: Annotated[AttachmentService, Depends(get_attachment_service)],
) -> Response:
    try:
        service.delete(session, item_id, attachment_id)
    except AttachmentServiceError as exc:
        session.rollback()
        raise _http_error(exc) from None
    except Exception as exc:  # noqa: BLE001 - stable code only
        session.rollback()
        _log_failure("delete", exc)
        raise HTTPException(status_code=500, detail=ATTACHMENT_FAILED) from None

    try:
        session.commit()
    except Exception as exc:  # noqa: BLE001 - commit owner is this route
        session.rollback()
        _log_failure("delete-commit", exc)
        raise HTTPException(status_code=500, detail=ATTACHMENT_FAILED) from None
    return Response(status_code=204)