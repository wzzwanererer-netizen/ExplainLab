"""M2 治理路由：查重 / 分析 / 关系 / 版本 / 来源 / 审核。

重要变更（active 的改删回滚、任何合并）经 Knowledge Core ReviewService：
被门禁拦截时返回 202 + 审核单；草稿保持直接应用。模型未配置 503、调用失败 502。
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
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
from app.db.session import get_session
from app.dependencies import get_embedder, get_model_adapter
from app.services.governance import (
    SQLAlchemyRelationRepository,
    SQLAlchemyReviewRepository,
    SQLAlchemyVersionRepository,
    build_analysis_service,
    build_provenance_service,
    build_review_service,
)
from app.services.knowledge import SQLAlchemyKnowledgeRepository
from app.services.links import demote_backlinks_on_delete
from app.services.retrieval import sync_index
from knowledge_core.domain.entities import (
    KnowledgeItem,
    KnowledgeRelation,
    RelationOrigin,
    ReviewAction,
    ReviewRequest,
    ReviewStatus,
    SourceRef,
)
from knowledge_core.model_adapter import ModelAdapter, ModelAdapterError
from knowledge_core.ports import Embedder
from knowledge_core.relations import DuplicateMatch
from knowledge_core.relations.llm import LLMRelationService
from knowledge_core.review import ReviewPolicy

router = APIRouter(tags=["governance"])


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
    if review is None:
        _sync_links_after_content_change(session, item.id, ReviewAction.RESTORE_VERSION)
    session.commit()
    if review is not None:
        response.status_code = 202
        return ReviewOut.model_validate(review)
    restored = SQLAlchemyKnowledgeRepository(session).get(item.id)
    assert restored is not None
    await sync_index(session, embedder, index_ids=[item.id])
    session.commit()
    return KnowledgeOut.model_validate(restored)


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
    await _sync_applied_action(session, embedder, payload.item_id, payload.action, payload.payload)
    session.commit()
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


@router.post("/reviews/{review_id}/approve", response_model=ReviewOut)
async def approve_review(
    review_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    embedder: Annotated[Embedder | None, Depends(get_embedder)],
    payload: ReviewResolve | None = None,
) -> ReviewOut:
    pending = _pending_review(session, review_id)
    service = build_review_service(session)
    # K1：DELETE 预降级。approve 内部先 update_review 再 _apply_action（删除会
    # CASCADE 审核单自身），入链降级须在 delete flush 前、同事务完成。
    _demote_backlinks_before_delete(session, pending.item_id, pending.action)
    try:
        review = await service.approve(review_id, payload.note if payload else None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # K1：UPDATE/RESTORE 应用后同步出链（commit 前，同事务；409 整事务零写入）。
    _sync_links_after_content_change(session, review.item_id, review.action)
    session.commit()
    await _sync_applied_action(
        session, embedder, review.item_id, review.action, review.payload
    )
    session.commit()
    return ReviewOut.model_validate(review)


@router.post("/reviews/{review_id}/reject", response_model=ReviewOut)
async def reject_review(
    review_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    payload: ReviewResolve | None = None,
) -> ReviewOut:
    _pending_review(session, review_id)
    service = build_review_service(session)
    try:
        review = await service.reject(review_id, payload.note if payload else None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    return ReviewOut.model_validate(review)