"""知识空间服务。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgeSpace

PERSONAL_SPACE_NAME = "个人总知识库"


def ensure_default_space(session: Session) -> KnowledgeSpace:
    """幂等确保默认个人总知识库存在。"""
    space = session.scalar(select(KnowledgeSpace).where(KnowledgeSpace.kind == "personal"))
    if space is None:
        space = KnowledgeSpace(
            name=PERSONAL_SPACE_NAME,
            kind="personal",
            description="默认个人总知识库",
        )
        session.add(space)
        session.flush()
    return space


def list_spaces(session: Session) -> list[KnowledgeSpace]:
    return list(session.scalars(select(KnowledgeSpace).order_by(KnowledgeSpace.created_at)))


def create_space(
    session: Session, *, name: str, description: str | None = None
) -> KnowledgeSpace:
    space = KnowledgeSpace(name=name, kind="project", description=description)
    session.add(space)
    session.flush()
    return space


def get_space(session: Session, space_id: str) -> KnowledgeSpace | None:
    return session.get(KnowledgeSpace, space_id)


def get_personal_space(session: Session) -> KnowledgeSpace | None:
    """只读返回个人总知识库（不创建）；供检索聚合未归属条目时注入 personal_space_id。"""
    return session.scalar(select(KnowledgeSpace).where(KnowledgeSpace.kind == "personal"))