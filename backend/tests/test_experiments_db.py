"""M5 实验仓库 SQLAlchemy 实现测试：JSON 往返 / 过滤 / 更新 / 级联删除。"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

import app.models  # noqa: F401  确保 ORM 元数据注册
from app.db.base import Base
from app.db.session import create_engine_from_url
from app.models import KnowledgeSpace
from app.services.experiments import SQLAlchemyExperimentRepository
from knowledge_core.experiments import (
    ExperimentAttempt,
    ExperimentKind,
    ExperimentSession,
    ExperimentStatus,
)


@pytest.fixture
def session(tmp_path: Path):
    engine = create_engine_from_url(f"sqlite:///{tmp_path / 'exp.db'}")
    Base.metadata.create_all(engine)
    s = Session(engine)
    # 实验会话 space_id 受外键约束，先建两个真实空间供过滤测试引用。
    s.add(KnowledgeSpace(id="s1", name="空间一", kind="project"))
    s.add(KnowledgeSpace(id="s2", name="空间二", kind="project"))
    s.commit()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _session(kind: ExperimentKind = ExperimentKind.QUIZ, space_id: str | None = None):
    return ExperimentSession(
        kind=kind,
        title=f"实验 · {kind.value}",
        space_id=space_id,
        item_ids=[uuid4(), uuid4()],
        payload={"questions": [{"index": 0, "prompt": "Q", "correct_index": 1}]},
    )


def test_save_and_get_roundtrip(session):
    repo = SQLAlchemyExperimentRepository(session)
    original = _session(space_id="s1")
    repo.save_session(original)
    session.commit()

    loaded = repo.get_session(original.id)
    assert loaded is not None
    assert loaded.id == original.id
    assert loaded.kind == ExperimentKind.QUIZ
    assert loaded.space_id == "s1"
    assert loaded.item_ids == original.item_ids
    assert loaded.payload == original.payload
    assert loaded.status == ExperimentStatus.ACTIVE


def test_get_missing_returns_none(session):
    repo = SQLAlchemyExperimentRepository(session)
    assert repo.get_session(uuid4()) is None


def test_list_filters_and_order(session):
    repo = SQLAlchemyExperimentRepository(session)
    quiz = repo.save_session(_session(ExperimentKind.QUIZ, space_id="s1"))
    chain = repo.save_session(_session(ExperimentKind.CHAIN, space_id="s1"))
    repo.save_session(_session(ExperimentKind.QUIZ, space_id="s2"))
    session.commit()

    assert len(repo.list_sessions()) == 3
    assert {s.id for s in repo.list_sessions(kind=ExperimentKind.QUIZ)} == {
        quiz.id,
        repo.list_sessions(space_id="s2")[0].id,
    }
    assert {s.id for s in repo.list_sessions(space_id="s1")} == {quiz.id, chain.id}
    # 倒序：最新创建在前
    assert repo.list_sessions()[0].created_at >= repo.list_sessions()[-1].created_at


def test_update_session_status(session):
    repo = SQLAlchemyExperimentRepository(session)
    saved = repo.save_session(_session())
    session.commit()

    updated = saved.model_copy(update={"status": ExperimentStatus.COMPLETED})
    repo.update_session(updated)
    session.commit()
    assert repo.get_session(saved.id).status == ExperimentStatus.COMPLETED


def test_attempt_roundtrip_and_list(session):
    repo = SQLAlchemyExperimentRepository(session)
    saved = repo.save_session(_session())
    attempt = ExperimentAttempt(
        session_id=saved.id,
        answers=[{"index": 0, "value": 1, "correct": True}],
        correct_count=1,
        total=2,
        score=0.5,
    )
    repo.save_attempt(attempt)
    session.commit()

    attempts = repo.list_attempts(saved.id)
    assert len(attempts) == 1
    assert attempts[0].id == attempt.id
    assert attempts[0].answers == attempt.answers
    assert attempts[0].score == 0.5


def test_delete_session_cascades_attempts(session):
    repo = SQLAlchemyExperimentRepository(session)
    saved = repo.save_session(_session())
    repo.save_attempt(ExperimentAttempt(session_id=saved.id, total=1))
    session.commit()

    assert repo.delete_session(saved.id) is True
    session.commit()
    assert repo.get_session(saved.id) is None
    assert repo.list_attempts(saved.id) == []


def test_delete_missing_returns_false(session):
    repo = SQLAlchemyExperimentRepository(session)
    assert repo.delete_session(uuid4()) is False