"""交互式知识实验领域实体（M5）。

纯 Pydantic 模型，不绑定数据库 ORM 与 Web 框架。实验会话承载生成内容
（测验题目 / 对比结果 / 学习路径），作答记录独立成 attempt，判分在服务端。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from knowledge_core.domain.entities import RelationType, utcnow


class ExperimentKind(StrEnum):
    """实验模式。"""

    QUIZ = "quiz"
    COMPARE = "compare"
    CHAIN = "chain"


class QuizQuestionKind(StrEnum):
    """测验题型（自动判分，不依赖模型阅卷）。"""

    SINGLE_CHOICE = "single_choice"
    TRUE_FALSE = "true_false"


class ExperimentStatus(StrEnum):
    """实验会话生命周期。"""

    ACTIVE = "active"
    COMPLETED = "completed"


class QuizQuestion(BaseModel):
    """一道测验题。correct_index / explanation 服务端持有，未作答不下发。"""

    index: int = Field(ge=0)
    prompt: str = Field(min_length=1)
    kind: QuizQuestionKind = QuizQuestionKind.SINGLE_CHOICE
    options: list[str] = Field(min_length=2)
    correct_index: int = Field(ge=0)
    explanation: str = ""
    source_item_id: UUID

    @model_validator(mode="after")
    def _correct_in_range(self) -> QuizQuestion:
        if self.correct_index >= len(self.options):
            raise ValueError("correct_index 越界")
        return self


class CompareResult(BaseModel):
    """两条知识的结构化对比。"""

    item_a_id: UUID
    item_b_id: UUID
    similarities: list[str] = Field(default_factory=list)
    differences: list[str] = Field(default_factory=list)
    relationship: str = ""
    relation_type: RelationType | None = None


class ChainStep(BaseModel):
    """学习路径中的一步（先修优先）。"""

    item_id: UUID
    title: str
    relation_from_prev: RelationType | None = None
    position: int = Field(ge=0)


class ExperimentSession(BaseModel):
    """一次实验会话。payload 承载生成内容（questions / compare / steps）。"""

    id: UUID = Field(default_factory=uuid4)
    kind: ExperimentKind
    title: str = Field(min_length=1)
    space_id: str | None = None
    item_ids: list[UUID] = Field(default_factory=list)
    payload: dict = Field(default_factory=dict)
    status: ExperimentStatus = ExperimentStatus.ACTIVE
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ExperimentAttempt(BaseModel):
    """一次作答记录（服务端判分汇总）。"""

    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    answers: list[dict] = Field(default_factory=list)
    correct_count: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=utcnow)


class AnswerFeedback(BaseModel):
    """单题作答的即时反馈（服务端判分后返回）。"""

    correct: bool
    correct_value: int
    explanation: str = ""
