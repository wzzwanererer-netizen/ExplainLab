"""M5 实验持久化与服务装配。

ExperimentRepository 端口的 SQLAlchemy 实现，以及实验编排服务的装配助手。
领域逻辑全部在 Knowledge Core（knowledge_core.experiments），本层只做映射与装配。
item_ids / payload / answers 以 JSON 文本存储，兼容 SQLite 与 PostgreSQL。
"""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ExperimentAttemptORM, ExperimentSessionORM
from app.services.errors import NotFoundError
from app.services.governance import SQLAlchemyRelationRepository
from app.services.knowledge import SQLAlchemyKnowledgeRepository
from knowledge_core.experiments import (
    ExperimentAttempt,
    ExperimentKind,
    ExperimentService,
    ExperimentSession,
    ExperimentStatus,
)
from knowledge_core.model_adapter import ModelAdapter


def _to_session(row: ExperimentSessionORM) -> ExperimentSession:
    return ExperimentSession(
        id=UUID(row.id),
        kind=ExperimentKind(row.kind),
        title=row.title,
        space_id=row.space_id,
        item_ids=[UUID(x) for x in json.loads(row.item_ids)],
        payload=json.loads(row.payload),
        status=ExperimentStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_attempt(row: ExperimentAttemptORM) -> ExperimentAttempt:
    return ExperimentAttempt(
        id=UUID(row.id),
        session_id=UUID(row.session_id),
        answers=json.loads(row.answers),
        correct_count=row.correct_count,
        total=row.total,
        score=row.score,
        created_at=row.created_at,
    )


class SQLAlchemyExperimentRepository:
    """ExperimentRepository 端口的 SQLAlchemy 实现。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save_session(self, session: ExperimentSession) -> ExperimentSession:
        row = ExperimentSessionORM(
            id=str(session.id),
            kind=session.kind.value,
            title=session.title,
            space_id=session.space_id,
            item_ids=json.dumps([str(x) for x in session.item_ids]),
            payload=json.dumps(session.payload, ensure_ascii=False),
            status=session.status.value,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )
        self._session.add(row)
        self._session.flush()
        return _to_session(row)

    def get_session(self, session_id: UUID) -> ExperimentSession | None:
        row = self._session.get(ExperimentSessionORM, str(session_id))
        return _to_session(row) if row is not None else None

    def list_sessions(
        self,
        *,
        kind: ExperimentKind | None = None,
        space_id: str | None = None,
    ) -> list[ExperimentSession]:
        stmt = select(ExperimentSessionORM).order_by(ExperimentSessionORM.created_at.desc())
        if kind is not None:
            stmt = stmt.where(ExperimentSessionORM.kind == kind.value)
        if space_id is not None:
            stmt = stmt.where(ExperimentSessionORM.space_id == space_id)
        return [_to_session(row) for row in self._session.scalars(stmt)]

    def update_session(self, session: ExperimentSession) -> ExperimentSession:
        row = self._session.get(ExperimentSessionORM, str(session.id))
        if row is None:
            raise NotFoundError(f"实验会话不存在: {session.id}")
        row.title = session.title
        row.status = session.status.value
        row.item_ids = json.dumps([str(x) for x in session.item_ids])
        row.payload = json.dumps(session.payload, ensure_ascii=False)
        row.updated_at = session.updated_at
        self._session.flush()
        return _to_session(row)

    def delete_session(self, session_id: UUID) -> bool:
        row = self._session.get(ExperimentSessionORM, str(session_id))
        if row is None:
            return False
        self._session.delete(row)
        self._session.flush()
        return True

    def save_attempt(self, attempt: ExperimentAttempt) -> ExperimentAttempt:
        row = ExperimentAttemptORM(
            id=str(attempt.id),
            session_id=str(attempt.session_id),
            answers=json.dumps(attempt.answers, ensure_ascii=False),
            correct_count=attempt.correct_count,
            total=attempt.total,
            score=attempt.score,
            created_at=attempt.created_at,
        )
        self._session.add(row)
        self._session.flush()
        return _to_attempt(row)

    def list_attempts(self, session_id: UUID) -> list[ExperimentAttempt]:
        stmt = (
            select(ExperimentAttemptORM)
            .where(ExperimentAttemptORM.session_id == str(session_id))
            .order_by(ExperimentAttemptORM.created_at)
        )
        return [_to_attempt(row) for row in self._session.scalars(stmt)]


def build_experiment_service(
    session: Session, adapter: ModelAdapter | None = None
) -> ExperimentService:
    """装配实验编排服务；adapter 为 None 时仅学习路径可用（测验/对比抛 ModelRequiredError）。"""
    return ExperimentService(
        SQLAlchemyKnowledgeRepository(session),
        SQLAlchemyRelationRepository(session),
        SQLAlchemyExperimentRepository(session),
        adapter,
    )