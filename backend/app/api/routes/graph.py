"""M4 知识地图路由：节点 + 边只读视图。

GET /api/graph：装配 Knowledge Core 图服务（空间过滤 + 归档开关）。
图是现有 knowledge_item + knowledge_relation 的视图，无新增表 / 迁移。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import GraphEdgeOut, GraphNodeOut, GraphOut
from app.db.session import get_session
from app.services.graph import build_graph_service
from app.services.spaces import get_space

router = APIRouter(tags=["graph"])


@router.get("/graph", response_model=GraphOut)
def get_graph(
    session: Annotated[Session, Depends(get_session)],
    space_id: str | None = None,
    include_archived: bool = False,
) -> GraphOut:
    include_unassigned = False
    if space_id is not None:
        space = get_space(session, space_id)
        if space is None:
            raise HTTPException(status_code=404, detail=f"知识空间不存在: {space_id}")
        include_unassigned = space.kind == "personal"
    graph = build_graph_service(session).build_graph(
        space_id=space_id,
        include_unassigned=include_unassigned,
        include_archived=include_archived,
    )
    return GraphOut(
        nodes=[GraphNodeOut.model_validate(n) for n in graph.nodes],
        edges=[GraphEdgeOut.model_validate(e) for e in graph.edges],
    )