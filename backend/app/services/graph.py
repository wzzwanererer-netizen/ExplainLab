"""M4 知识地图服务装配。

图数据装配逻辑在 Knowledge Core（knowledge_core.graph），本层只做端口注入。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.governance import SQLAlchemyRelationRepository
from app.services.knowledge import SQLAlchemyKnowledgeRepository
from knowledge_core.graph import KnowledgeGraphService


def build_graph_service(session: Session) -> KnowledgeGraphService:
    return KnowledgeGraphService(
        SQLAlchemyKnowledgeRepository(session),
        SQLAlchemyRelationRepository(session),
    )