"""M3 检索路由：跨会话 / 跨空间混合检索 + 索引重建（backfill）。

GET /api/search：全文 + 向量混合（RRF），mode=hybrid|fts|vector。
向量来源未配置时如实降级为仅全文（embed_capability=not_configured）；
配置但端点不可用时降级并上报 unsupported，绝不以假数据冒充向量能力。
POST /api/search/reindex：为存量条目重建全文 + 向量索引（管理入口）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.schemas import (
    ReindexResponse,
    SearchHitOut,
    SearchMode,
    SearchResponse,
)
from app.db.session import get_session
from app.dependencies import get_embedder
from app.services.retrieval import (
    RetrievalIndexer,
    build_retrieval_service,
    probe_embed_capability,
)
from app.services.spaces import get_personal_space, get_space
from knowledge_core.model_adapter import ModelAdapterError
from knowledge_core.ports import Embedder

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
async def search(
    session: Annotated[Session, Depends(get_session)],
    embedder: Annotated[Embedder | None, Depends(get_embedder)],
    query: Annotated[str, Query(min_length=1)],
    space_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    mode: SearchMode = "hybrid",
) -> SearchResponse:
    if space_id is not None and get_space(session, space_id) is None:
        raise HTTPException(status_code=404, detail=f"知识空间不存在: {space_id}")
    personal = get_personal_space(session)
    service = build_retrieval_service(
        session, embedder, personal_space_id=personal.id if personal else None
    )
    capability = "not_configured" if embedder is None else "configured"
    effective_mode = mode
    if embedder is None and mode in ("hybrid", "vector"):
        # 向量通道如实关闭：未配置 embed 时仅全文检索
        effective_mode = "fts"
    try:
        results = await service.search(
            query, space_id=space_id, limit=limit, mode=effective_mode
        )
    except ModelAdapterError:
        # embed 端点不可用（如 DeepSeek 无 /embeddings）：如实降级为仅全文
        capability = "unsupported"
        effective_mode = "fts"
        results = await service.search(query, space_id=space_id, limit=limit, mode="fts")
    else:
        if embedder is not None and effective_mode in ("hybrid", "vector"):
            capability = "supported"
    return SearchResponse(
        query=query,
        mode=effective_mode,
        count=len(results),
        embed_capability=capability,
        results=[SearchHitOut.model_validate(r) for r in results],
    )


@router.post("/search/reindex", response_model=ReindexResponse)
async def reindex(
    session: Annotated[Session, Depends(get_session)],
    embedder: Annotated[Embedder | None, Depends(get_embedder)],
) -> ReindexResponse:
    capability = await probe_embed_capability(embedder)
    model = getattr(embedder, "default_model", "none") if embedder else "none"
    indexer = RetrievalIndexer(session, embedder, model=model)
    count = await indexer.reindex_all()
    session.commit()
    return ReindexResponse(indexed=count, embed_capability=capability)