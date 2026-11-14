"""SQLAlchemy ORM 模型（M1 + M2）。

UUID 以 String(36) 存储，兼容 SQLite 与 PostgreSQL。
领域实体（knowledge_core.domain）与 ORM 的映射由仓库层负责。
M2 引入关系 / 版本 / 审核三张治理表。
M3 引入向量表 knowledge_vector（全文 FTS5 虚表 knowledge_fts 由迁移 raw SQL 创建）。
M5 引入实验会话 experiment_session 与作答记录 experiment_attempt（JSON 字段以 Text 存储）。
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import fts as _fts  # noqa: F401  注册 FTS create_all 兜底事件（M3）
from app.db.base import Base
from knowledge_core.domain.entities import utcnow


def _uuid() -> str:
    return str(uuid4())


class KnowledgeSpace(Base):
    """知识空间：personal（个人总知识库）或 project（项目空间）。"""

    __tablename__ = "knowledge_space"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Conversation(Base):
    """一次持续对话。"""

    __tablename__ = "conversation"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    space_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge_space.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Message.created_at",
    )


class Message(Base):
    """对话中的一条消息。"""

    __tablename__ = "message"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class KnowledgeItemORM(Base):
    """知识条目持久化记录。"""

    __tablename__ = "knowledge_item"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    space_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge_space.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    source_refs: Mapped[list[SourceRefORM]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class SourceRefORM(Base):
    """知识来源追溯记录。"""

    __tablename__ = "source_ref"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_item.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(20))
    uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    item: Mapped[KnowledgeItemORM] = relationship(back_populates="source_refs")


class KnowledgeRelationORM(Base):
    """两条知识之间的关系（M2）。"""

    __tablename__ = "knowledge_relation"
    __table_args__ = (
        UniqueConstraint("source_id", "target_id", "relation_type", name="uq_relation_triple"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_item.id", ondelete="CASCADE"), nullable=False
    )
    target_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_item.id", ondelete="CASCADE"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    origin: Mapped[str] = mapped_column(String(20), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeVersionORM(Base):
    """知识条目的历史版本快照（M2）。"""

    __tablename__ = "knowledge_version"
    __table_args__ = (
        UniqueConstraint("item_id", "version", name="uq_version_item_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_item.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReviewRequestORM(Base):
    """重要变更审核单（M2）。payload 以 JSON 文本存储。"""

    __tablename__ = "review_request"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_item.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(30))
    payload: Mapped[str] = mapped_column(Text, default="{}")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class KnowledgeVectorORM(Base):
    """知识向量（M3）。vector 以 JSON 文本存储，开发期余弦在 Python 计算。

    全文索引 knowledge_fts 为 FTS5 虚表，由迁移 raw SQL 创建、触发器同步，
    不在 ORM  metadata 中（env.py 已将其排除出 autogenerate）。
    """

    __tablename__ = "knowledge_vector"

    item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_item.id", ondelete="CASCADE"), primary_key=True
    )
    model: Mapped[str] = mapped_column(String(100))
    dim: Mapped[int] = mapped_column(Integer)
    vector: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExperimentSessionORM(Base):
    """交互式知识实验会话（M5）。item_ids / payload 以 JSON 文本存储。"""

    __tablename__ = "experiment_session"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(500))
    space_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge_space.id", ondelete="SET NULL"), nullable=True
    )
    item_ids: Mapped[str] = mapped_column(Text, default="[]")
    payload: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    attempts: Mapped[list[ExperimentAttemptORM]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ExperimentAttemptORM.created_at",
    )


class ExperimentAttemptORM(Base):
    """实验作答记录（M5）。answers 以 JSON 文本存储，判分汇总在服务端。"""

    __tablename__ = "experiment_attempt"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("experiment_session.id", ondelete="CASCADE"), nullable=False
    )
    answers: Mapped[str] = mapped_column(Text, default="[]")
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[ExperimentSessionORM] = relationship(back_populates="attempts")