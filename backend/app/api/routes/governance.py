"""M2 治理路由：查重 / 分析 / 关系 / 版本 / 来源 / 审核。

重要变更（active 的改删回滚、任何合并）经 Knowledge Core ReviewService：
被门禁拦截时返回 202 + 审核单；草稿保持直接应用。模型未配置 503、调用失败 502。
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import ExitStack
from contextlib import nullcontext as _null_context
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.api.routes.links import sync_links_or_conflict
from app.api.schemas import (
    AnalyzeResponse,
    DuplicateOut,
    KnowledgeOut,
    RelationCreate,
    RelationOut,
    ReviewOut,
    ReviewResolve,
    ReviewSubmit,
    ReviewSubmitResult,
    SourceAttach,
    SourceRefOut,
    VersionOut,
)
from app.db.session import create_session, get_session
from app.db.storage_lock import LockGuard
from app.dependencies import get_embedder, get_model_adapter
from app.services.attachment_promotion import publish_staged
from app.services.attachment_staging import (
    ATTACHMENT_MANIFEST_CORRUPTED,
    AttachmentManifestItem,
    AttachmentStagingError,
    AttachmentStagingService,
    coerce_manifest_items,
)
from app.services.attachment_storage import AttachmentStorageError
from app.services.governance import (
    SQLAlchemyRelationRepository,
    SQLAlchemyReviewRepository,
    SQLAlchemyVersionRepository,
    build_analysis_service,
    build_provenance_service,
    build_review_service,
)
from app.services.import_coordinator import ImportCoordinator, ImportLockTimeout
from app.services.import_review_hook import (
    ImportReviewHook,
    ReviewAttachmentPlan,
    envelope_from_review,
    review_is_import,
)
from app.services.journal_canonical import sha256_canonical
from app.services.knowledge import SQLAlchemyKnowledgeRepository
from app.services.links import demote_backlinks_on_delete
from app.services.markdown import (
    ATTACHMENT_REVIEW_UNSUPPORTED,
    IMPORT_ENVELOPE_INVALID,
    MarkdownServiceError,
)
from app.services.markdown_item_repository import MarkdownItemRepository
from app.services.retrieval import sync_index
from app.services.source_identity import SourceIdentityError, SourceIdentityService
from knowledge_core.domain.entities import (
    KnowledgeItem,
    KnowledgeRelation,
    KnowledgeStatus,
    RelationOrigin,
    ReviewAction,
    ReviewRequest,
    ReviewStatus,
    SourceRef,
)
from knowledge_core.markdown.import_report import IMPORT_ENVELOPE_KEY, ImportEnvelope
from knowledge_core.markdown.service import ExporterMetadataError
from knowledge_core.model_adapter import ModelAdapter, ModelAdapterError
from knowledge_core.ports import Embedder
from knowledge_core.relations import DuplicateMatch
from knowledge_core.relations.llm import LLMRelationService
from knowledge_core.review import ReviewPolicy

router = APIRouter(tags=["governance"])
logger = logging.getLogger(__name__)


def _get_item(session: Session, item_id: UUID) -> KnowledgeItem:
    item = SQLAlchemyKnowledgeRepository(session).get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"知识条目不存在: {item_id}")
    return item


def _candidates(session: Session, item: KnowledgeItem) -> list[KnowledgeItem]:
    return SQLAlchemyKnowledgeRepository(session).list(
        space_id=item.space_id, include_unassigned=True
    )


def _duplicates_out(
    matches: list[DuplicateMatch], candidates: list[KnowledgeItem]
) -> list[DuplicateOut]:
    titles = {str(c.id): c.title for c in candidates}
    return [
        DuplicateOut(
            item_id=m.item_id,
            score=m.score,
            title=titles.get(str(m.item_id), ""),
        )
        for m in matches
    ]


@router.get("/knowledge/{item_id}/duplicates", response_model=list[DuplicateOut])
async def find_duplicates(
    item_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    adapter: Annotated[ModelAdapter, Depends(get_model_adapter)],
) -> list[DuplicateOut]:
    item = _get_item(session, item_id)
    candidates = _candidates(session, item)
    try:
        matches = await LLMRelationService(adapter).find_duplicates(item, candidates)
    except ModelAdapterError as exc:
        raise HTTPException(status_code=502, detail=f"模型调用失败: {exc}") from exc
    return _duplicates_out(matches, candidates)


@router.post("/knowledge/{item_id}/analyze", response_model=AnalyzeResponse)
async def analyze_item(
    item_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    adapter: Annotated[ModelAdapter, Depends(get_model_adapter)],
) -> AnalyzeResponse:
    item = _get_item(session, item_id)
    service = build_analysis_service(session, adapter)
    try:
        result = await service.analyze_item(item)
    except ModelAdapterError as exc:
        raise HTTPException(status_code=502, detail=f"模型调用失败: {exc}") from exc
    session.commit()
    candidates = _candidates(session, item)
    return AnalyzeResponse(
        duplicates=_duplicates_out(result["duplicates"], candidates),
        relations=[RelationOut.model_validate(r) for r in result["relations"]],
    )


@router.get("/knowledge/{item_id}/relations", response_model=list[RelationOut])
def list_relations(
    item_id: UUID,
    session: Annotated[Session, Depends(get_session)],
) -> list[RelationOut]:
    _get_item(session, item_id)
    relations = SQLAlchemyRelationRepository(session).list_relations(item_id)
    return [RelationOut.model_validate(r) for r in relations]


@router.post(
    "/knowledge/{item_id}/relations", response_model=RelationOut, status_code=201
)
def create_relation(
    item_id: UUID,
    payload: RelationCreate,
    session: Annotated[Session, Depends(get_session)],
) -> RelationOut:
    _get_item(session, item_id)
    if payload.target_id == item_id:
        raise HTTPException(status_code=400, detail="知识关系不允许指向自身")
    repository = SQLAlchemyKnowledgeRepository(session)
    if repository.get(payload.target_id) is None:
        raise HTTPException(status_code=404, detail=f"目标条目不存在: {payload.target_id}")
    relations = SQLAlchemyRelationRepository(session)
    if relations.find_relation(item_id, payload.target_id, payload.relation_type):
        raise HTTPException(status_code=409, detail="相同关系已存在")
    saved = relations.save_relation(
        KnowledgeRelation(
            source_id=item_id,
            target_id=payload.target_id,
            relation_type=payload.relation_type,
            confidence=payload.confidence,
            origin=RelationOrigin.MANUAL,
        )
    )
    session.commit()
    return RelationOut.model_validate(saved)


@router.delete("/relations/{relation_id}", status_code=204)
def delete_relation(
    relation_id: UUID,
    session: Annotated[Session, Depends(get_session)],
) -> None:
    if not SQLAlchemyRelationRepository(session).delete_relation(relation_id):
        raise HTTPException(status_code=404, detail=f"关系不存在: {relation_id}")
    session.commit()


@router.get("/knowledge/{item_id}/versions", response_model=list[VersionOut])
def list_versions(
    item_id: UUID,
    session: Annotated[Session, Depends(get_session)],
) -> list[VersionOut]:
    _get_item(session, item_id)
    versions = SQLAlchemyVersionRepository(session).list_versions(item_id)
    return [VersionOut.model_validate(v) for v in versions]


@router.post("/knowledge/{item_id}/versions/{version}/restore")
async def restore_version(
    item_id: UUID,
    version: int,
    session: Annotated[Session, Depends(get_session)],
    response: Response,
    embedder: Annotated[Embedder | None, Depends(get_embedder)],
) -> KnowledgeOut | ReviewOut:
    item = _get_item(session, item_id)
    if SQLAlchemyVersionRepository(session).get_version(item_id, version) is None:
        raise HTTPException(status_code=404, detail=f"版本不存在: v{version}")
    service = build_review_service(session)
    review = await service.submit(
        item_id, ReviewAction.RESTORE_VERSION, payload={"version": version}
    )
    # K1：草稿直改回滚应用后同步出链（commit 前，同事务；409 零写入）。
    # active 回滚进审核（review 非 None），其同步在 approve 路径完成。
    restored_result = None
    if review is None:
        _sync_links_after_content_change(session, item.id, ReviewAction.RESTORE_VERSION)
        restored = SQLAlchemyKnowledgeRepository(session).get(item.id)
        assert restored is not None
        restored_result = KnowledgeOut.model_validate(restored)
    session.commit()
    if review is not None:
        response.status_code = 202
        return ReviewOut.model_validate(review)
    await _sync_after_commit(embedder, item.id, ReviewAction.RESTORE_VERSION, {})
    assert restored_result is not None
    return restored_result


@router.post(
    "/knowledge/{item_id}/sources", response_model=SourceRefOut, status_code=201
)
async def attach_source(
    item_id: UUID,
    payload: SourceAttach,
    session: Annotated[Session, Depends(get_session)],
) -> SourceRefOut:
    service = build_provenance_service(session)
    source = SourceRef(
        source_type=payload.source_type,
        uri=payload.uri,
        conversation_id=payload.conversation_id,
        excerpt=payload.excerpt,
    )
    try:
        await service.attach_source(item_id, source)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    session.commit()
    return SourceRefOut.model_validate(source)


@router.get("/reviews", response_model=list[ReviewOut])
def list_reviews(
    session: Annotated[Session, Depends(get_session)],
    status: ReviewStatus | None = None,
) -> list[ReviewOut]:
    reviews = SQLAlchemyReviewRepository(session).list_reviews(status)
    return [ReviewOut.model_validate(r) for r in reviews]


@router.post("/reviews", response_model=ReviewSubmitResult)
async def submit_review(
    payload: ReviewSubmit,
    session: Annotated[Session, Depends(get_session)],
    response: Response,
    embedder: Annotated[Embedder | None, Depends(get_embedder)],
) -> ReviewSubmitResult:
    if IMPORT_ENVELOPE_KEY in payload.payload:
        raise HTTPException(status_code=400, detail=IMPORT_ENVELOPE_INVALID)
    repository = SQLAlchemyKnowledgeRepository(session)
    item = repository.get(payload.item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"知识条目不存在: {payload.item_id}")
    if payload.action == ReviewAction.MERGE_DUPLICATE:
        raw_target = payload.payload.get("target_id")
        try:
            target_id = UUID(str(raw_target))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="合并需要有效的 target_id") from exc
        if repository.get(target_id) is None:
            raise HTTPException(status_code=404, detail=f"合并目标不存在: {target_id}")
    elif payload.action == ReviewAction.RESTORE_VERSION:
        version = payload.payload.get("version")
        if not isinstance(version, int) or (
            SQLAlchemyVersionRepository(session).get_version(payload.item_id, version)
            is None
        ):
            raise HTTPException(status_code=404, detail=f"版本不存在: {version}")
    service = build_review_service(session)
    # K1：草稿直改 DELETE 预降级——仅当非重要变更（将直接应用）时；active DELETE
    # 进审核（不在此应用），其降级在 approve 路径完成。MERGE 任何状态都进审核。
    if not ReviewPolicy.is_important(payload.action, item.status):
        _demote_backlinks_before_delete(session, payload.item_id, payload.action)
    try:
        review = await service.submit(
            payload.item_id, payload.action, payload.payload, payload.reason
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # K1：草稿直改 UPDATE/RESTORE 应用后同步出链（commit 前，同事务；409 零写入）。
    if review is None:
        _sync_links_after_content_change(session, payload.item_id, payload.action)
    session.commit()
    if review is not None:
        response.status_code = 201
        return ReviewSubmitResult(applied=False, review=ReviewOut.model_validate(review))
    await _sync_after_commit(embedder, payload.item_id, payload.action, payload.payload)
    return ReviewSubmitResult(applied=True)


def _pending_review(session: Session, review_id: UUID) -> ReviewRequest:
    review = SQLAlchemyReviewRepository(session).get_review(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail=f"审核单不存在: {review_id}")
    if review.status != ReviewStatus.PENDING:
        raise HTTPException(status_code=409, detail=f"审核单已处理: {review.status}")
    return review


async def _sync_applied_action(
    session: Session,
    embedder: Embedder | None,
    item_id: UUID,
    action: ReviewAction,
    payload: dict,
) -> None:
    """变更已应用（草稿直改或审核批准）后同步检索索引。

    删除→移除索引；合并→重算目标索引（源转 archived，查询期过滤，与 backfill 一致）；
    编辑 / 回滚→重算该条目索引。
    """
    if action == ReviewAction.DELETE_ITEM:
        await sync_index(session, embedder, remove_ids=[item_id])
    elif action == ReviewAction.MERGE_DUPLICATE:
        target_id = UUID(str(payload["target_id"]))
        await sync_index(session, embedder, index_ids=[target_id])
    else:  # UPDATE_ITEM / RESTORE_VERSION
        await sync_index(session, embedder, index_ids=[item_id])


async def _sync_after_commit(
    embedder: Embedder | None, item_id: UUID, action: ReviewAction, payload: dict,
) -> None:
    """Synchronize the index after the business transaction has committed."""
    try:
        with create_session() as index_session:
            await _sync_applied_action(index_session, embedder, item_id, action, payload)
            index_session.commit()
    except Exception as exc:  # noqa: BLE001 - independent index transaction
        logger.warning("REVIEW_INDEX_SYNC_FAILED: %s", type(exc).__name__)


def _demote_backlinks_before_delete(
    session: Session, item_id: UUID, action: ReviewAction
) -> None:
    """K1：DELETE 应用前同事务降级入链（D12 写侧）。

    必须在条目删除 flush **之前**调用（先按 target_id 捕获入链，再置 missing+NULL）；
    只改治理列、键/版本不变 → 不触发全局版本守卫，版本窗口内 DELETE 不被 409 阻断。
    MERGE 归档而非删除（入链是对存在条目的合法绑定），**不在此降级**。
    """
    if action == ReviewAction.DELETE_ITEM:
        demote_backlinks_on_delete(session, item_id)


def _sync_links_after_content_change(
    session: Session, item_id: UUID, action: ReviewAction
) -> None:
    """K1：UPDATE / RESTORE 应用后、commit 前同步出链（绑定优先）。

    content 变更 → wikilink 集合变化，须同步出链；DELETE 出链随 CASCADE 清理、
    MERGE 双方 content 未改，均不在此同步。版本异写时 ``sync_links_or_conflict``
    映射 409 稳定码；调用方尚未 commit → 整事务零写入（含审核决议回滚）。
    """
    if action in (ReviewAction.UPDATE_ITEM, ReviewAction.RESTORE_VERSION):
        item = SQLAlchemyKnowledgeRepository(session).get(item_id)
        if item is not None:
            sync_links_or_conflict(session, item)


def _import_http_error(exc: Exception) -> HTTPException:
    code = getattr(exc, "code", IMPORT_ENVELOPE_INVALID)
    status = getattr(exc, "status_code", 409)
    return HTTPException(status_code=status, detail=code)


def _review_lock_key(envelope, item_id: UUID) -> str:
    if envelope is not None and envelope.source_instance_id and envelope.source_document_id:
        return "identity:" + sha256_canonical(
            {
                "source_instance_id": envelope.source_instance_id,
                "source_document_id": envelope.source_document_id,
            }
        )
    return f"target-item:{item_id}"


def _payload_digest(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class _ReviewSnapshot:
    review: ReviewRequest
    envelope: ImportEnvelope | None
    manifest: tuple[AttachmentManifestItem, ...] = ()

    @property
    def staging_id(self) -> UUID | None:
        return UUID(self.manifest[0].staging_id) if self.manifest else None


def _review_snapshot(
    session: Session, review_id: UUID, *, rejecting: bool = False,
) -> _ReviewSnapshot:
    review = _pending_review(session, review_id)
    if not review_is_import(review):
        return _ReviewSnapshot(review, None)
    try:
        envelope = envelope_from_review(review)
        if envelope is None or review.action != ReviewAction.UPDATE_ITEM:
            raise MarkdownServiceError(IMPORT_ENVELOPE_INVALID, status_code=409)
        if envelope.target_item_id is not None and str(envelope.target_item_id) != str(
            review.item_id
        ):
            raise MarkdownServiceError(IMPORT_ENVELOPE_INVALID, status_code=409)
        try:
            manifest = coerce_manifest_items(envelope.attachments) if envelope.attachments else ()
        except AttachmentStagingError:
            raise MarkdownServiceError(ATTACHMENT_MANIFEST_CORRUPTED, status_code=409) from None
    except MarkdownServiceError:
        if not rejecting:
            raise
        return _ReviewSnapshot(review, None)
    return _ReviewSnapshot(review, envelope, manifest)


def _recheck_review(session: Session, initial: _ReviewSnapshot) -> _ReviewSnapshot:
    pending = _pending_review(session, initial.review.id)
    if (
        pending.item_id != initial.review.item_id
        or pending.action != initial.review.action
        or _payload_digest(pending.payload) != _payload_digest(initial.review.payload)
    ):
        raise MarkdownServiceError(IMPORT_ENVELOPE_INVALID, status_code=409)
    return _ReviewSnapshot(pending, initial.envelope, initial.manifest)


def _require_attachment_target(session: Session, review: ReviewRequest) -> None:
    item = MarkdownItemRepository(session).get(review.item_id)
    if item is None:
        raise MarkdownServiceError("IMPORT_FAILED", status_code=409)
    if item.status == KnowledgeStatus.ARCHIVED:
        raise MarkdownServiceError("ATTACHMENT_ITEM_ARCHIVED", status_code=409)


def _approve_business(
    session: Session,
    snapshot: _ReviewSnapshot,
    identity: SourceIdentityService,
    note: str | None,
    *,
    plan: ReviewAttachmentPlan | None = None,
    guard: LockGuard | None = None,
) -> ReviewRequest:
    pending = snapshot.review
    if plan is not None:
        assert snapshot.envelope is not None and guard is not None
        plan.require_match(pending, snapshot.envelope)
        if set(guard.keys) != {entry.storage_key for entry in plan.published.manifest}:
            raise MarkdownServiceError(IMPORT_ENVELOPE_INVALID, status_code=409)
    _demote_backlinks_before_delete(session, pending.item_id, pending.action)
    try:
        review = asyncio.run(build_review_service(session).approve(pending.id, note))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if snapshot.envelope is None:
        _sync_links_after_content_change(session, review.item_id, review.action)
    else:
        hook = ImportReviewHook(session, identity)
        if plan is None:
            hook.apply_approved(review, snapshot.envelope)
        else:
            hook.apply_approved(review, snapshot.envelope, plan)
    if guard is not None:
        guard.verify_all(session)
    session.commit()
    return review


def _discard_review_staging(staging: AttachmentStagingService, staging_id: UUID) -> None:
    try:
        if not staging.discard_locked(staging_id):
            logger.warning("REVIEW_STAGING_DISCARD_DEFERRED")
    except Exception:  # noqa: BLE001 - already committed; ORP will retry
        logger.warning("REVIEW_STAGING_DISCARD_DEFERRED")


def _approve_with_attachments(
    request: Request, snapshot: _ReviewSnapshot, identity: SourceIdentityService,
    note: str | None,
) -> ReviewRequest:
    staging: AttachmentStagingService | None = getattr(
        request.app.state, "attachment_staging_service", None
    )
    markdown = getattr(request.app.state, "markdown_service", None)
    if staging is None or markdown is None:
        raise MarkdownServiceError(ATTACHMENT_REVIEW_UNSUPPORTED, status_code=400)
    staging_id = snapshot.staging_id
    envelope = snapshot.envelope
    assert staging_id is not None and envelope is not None
    keys = [entry.storage_key for entry in snapshot.manifest]
    with staging.staging_guard(staging_id):
        with markdown.attachment_keys(keys) as guard:
            with create_session() as probe:
                pending = _recheck_review(probe, snapshot).review
                _require_attachment_target(probe, pending)
                ImportReviewHook(probe, identity).validate_target(
                    pending, envelope, attachments=True,
                )
            published = publish_staged(staging, staging_id, snapshot.manifest, pending.item_id, guard)
            plan = ReviewAttachmentPlan(pending.id, envelope.context_digest, published)
            with create_session() as session:
                try:
                    MarkdownItemRepository(session).lock_for_import(pending.item_id)
                    fresh = _recheck_review(session, snapshot)
                    _require_attachment_target(session, fresh.review)
                    review = _approve_business(session, fresh, identity, note, plan=plan, guard=guard)
                except BaseException:
                    session.rollback()
                    raise
        _discard_review_staging(staging, staging_id)
    return review


@router.post("/reviews/{review_id}/approve", response_model=ReviewOut)
def approve_review(
    review_id: UUID,
    request: Request,
    embedder: Annotated[Embedder | None, Depends(get_embedder)],
    payload: ReviewResolve | None = None,
) -> ReviewOut:
    coordinator: ImportCoordinator = request.app.state.import_coordinator
    identity = getattr(request.app.state, "source_identity", None)
    if identity is None:
        raise HTTPException(status_code=503, detail="identity_service_unavailable")
    note = payload.note if payload else None
    try:
        with create_session() as probe:
            snapshot = _review_snapshot(probe, review_id)
        source = (
            coordinator.keyed(_review_lock_key(snapshot.envelope, snapshot.review.item_id))
            if snapshot.envelope is not None else _null_context()
        )
        with coordinator.keyed(f"review:{review_id}"), source, identity.identity_guard():
            if snapshot.manifest:
                review = _approve_with_attachments(request, snapshot, identity, note)
            else:
                with create_session() as session:
                    try:
                        fresh = _recheck_review(session, snapshot)
                        review = _approve_business(session, fresh, identity, note)
                    except BaseException:
                        session.rollback()
                        raise
    except (
        MarkdownServiceError, AttachmentStagingError, SourceIdentityError, ExporterMetadataError,
    ) as exc:
        raise _import_http_error(exc) from exc
    except AttachmentStorageError as exc:
        raise HTTPException(status_code=503, detail=exc.code) from None
    except ImportLockTimeout as exc:
        raise HTTPException(status_code=409, detail=exc.code) from None

    result = ReviewOut.model_validate(review)
    asyncio.run(_sync_after_commit(embedder, review.item_id, review.action, review.payload))
    return result


@router.post("/reviews/{review_id}/reject", response_model=ReviewOut)
def reject_review(
    review_id: UUID,
    request: Request,
    payload: ReviewResolve | None = None,
) -> ReviewOut:
    coordinator: ImportCoordinator = request.app.state.import_coordinator
    identity = getattr(request.app.state, "source_identity", None)
    if identity is None:
        raise HTTPException(status_code=503, detail="identity_service_unavailable")
    note = payload.note if payload else None
    try:
        with create_session() as probe:
            initial = _review_snapshot(probe, review_id, rejecting=True)
        source = coordinator.keyed(_review_lock_key(initial.envelope, initial.review.item_id))
        with coordinator.keyed(f"review:{review_id}"), source, ExitStack() as guards:
            with create_session() as probe:
                current = _review_snapshot(probe, review_id, rejecting=True)
            staging: AttachmentStagingService | None = getattr(
                request.app.state, "attachment_staging_service", None
            )
            staging_id = current.staging_id
            cleanup = False
            if (
                staging is not None
                and staging_id is not None
                and current.review.payload == initial.review.payload
            ):
                try:
                    guards.enter_context(staging.staging_guard(staging_id))
                    staging.validate_manifest_locked(staging_id, current.manifest)
                    cleanup = True
                except AttachmentStagingError:
                    logger.warning("REVIEW_STAGING_DISCARD_DEFERRED")
            with create_session() as session:
                try:
                    pending = _pending_review(session, review_id)
                    try:
                        review = asyncio.run(build_review_service(session).reject(review_id, note))
                    except ValueError as exc:
                        raise HTTPException(status_code=400, detail=str(exc)) from exc
                    if review_is_import(review):
                        ImportReviewHook(session, identity).apply_rejected(review)
                    session.commit()
                except BaseException:
                    session.rollback()
                    raise
            if cleanup and pending.payload == current.review.payload:
                assert staging is not None and staging_id is not None
                _discard_review_staging(staging, staging_id)
            return ReviewOut.model_validate(review)
    except ImportLockTimeout as exc:
        raise HTTPException(status_code=409, detail=exc.code) from None
