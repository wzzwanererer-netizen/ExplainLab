"""链接只读路由（V2 A1-03，D8：仅 3 个只读 GET，本轮无任何写端点）。

- ``GET /knowledge/links/resolve-candidates``：静态字面路径，**必须先于**
  ``/knowledge/{item_id}`` 动态段声明/注册（R11，避免被当作 item_id）。
- ``GET /knowledge/{item_id}/links`` / ``backlinks``：出链/反链读模型。
- 人工显式绑定（archived/跨空间候选）**无 HTTP 写入口**（D8/E3）：
  显式绑定规则只在 Core 层定义与测试；本 router 只交付候选发现与读取。

另提供 ``sync_links_or_conflict()`` 装配助手供 knowledge.py 四处挂接复用：
``LinkNormalizationVersionMismatch`` → 409 稳定错误码 ``link_version_mismatch``
（只回稳定码，不回异常文本/版本明细，AGENTS.md §9）。本模块不含业务规则：
解析/绑定/守卫规则全部在 Core 服务与持久化适配层。
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.schemas import BacklinkOut, LinkOut, ResolveCandidateOut
from app.db.session import get_session
from app.services.knowledge import SQLAlchemyKnowledgeRepository
from app.services.links import SQLAlchemyLinkRepository, build_link_sync
from knowledge_core.domain.entities import KnowledgeItem
from knowledge_core.markdown.link_service import (
    LinkNormalizationVersionMismatch,
    RepositoryLinkResolver,
)

router = APIRouter(tags=["links"])


def sync_links_or_conflict(session: Session, item: KnowledgeItem) -> None:
    """绑定优先同步挂接助手（knowledge.py 四处调用）：变更已应用、commit 之前。

    全局版本异写时仓库抛 ``LinkNormalizationVersionMismatch`` → 映射为
    409 + 稳定码；调用方尚未 commit，整个请求零写入（fail-loud，不静默降级）。
    """
    try:
        build_link_sync(session).sync(item, item.content)
    except LinkNormalizationVersionMismatch as exc:
        raise HTTPException(status_code=409, detail="link_version_mismatch") from exc


@router.get("/knowledge/links/resolve-candidates", response_model=list[ResolveCandidateOut])
def resolve_candidates(
    session: Annotated[Session, Depends(get_session)],
    title: Annotated[str, Query(min_length=1, max_length=500)],
    space_id: str | None = None,
) -> list[ResolveCandidateOut]:
    """只读候选发现：全库标题键匹配，含 archived（带 status 标注）与跨空间候选。

    自动解析排除 archived 的规则在 Core 解析器；本端点只列出候选供用户
    显式选择（A1-03 无绑定写入口，D8）。cross_space 按查询 space_id 精确
    等值判定（None==None 同空间，§2.5）。
    """
    resolver = RepositoryLinkResolver(SQLAlchemyKnowledgeRepository(session))
    candidates = resolver.find_candidates(title)
    return [
        ResolveCandidateOut(
            id=c.id,
            title=c.title,
            space_id=c.space_id,
            status=c.status,
            cross_space=c.space_id != space_id,
        )
        for c in candidates
    ]


@router.get("/knowledge/{item_id}/links", response_model=list[LinkOut])
def list_item_links(
    item_id: UUID,
    session: Annotated[Session, Depends(get_session)],
) -> list[LinkOut]:
    item = SQLAlchemyKnowledgeRepository(session).get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"知识条目不存在: {item_id}")
    links = SQLAlchemyLinkRepository(session).list_links(item_id)
    return [LinkOut.model_validate(link) for link in links]


@router.get("/knowledge/{item_id}/backlinks", response_model=list[BacklinkOut])
def list_item_backlinks(
    item_id: UUID,
    session: Annotated[Session, Depends(get_session)],
) -> list[BacklinkOut]:
    item = SQLAlchemyKnowledgeRepository(session).get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"知识条目不存在: {item_id}")
    links = SQLAlchemyLinkRepository(session).list_backlinks(item_id)
    return [BacklinkOut.model_validate(link) for link in links]