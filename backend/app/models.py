"""SQLAlchemy ORM 模型（M1 + M2）。

UUID 以 String(36) 存储，兼容 SQLite 与 PostgreSQL。
领域实体（knowledge_core.domain）与 ORM 的映射由仓库层负责。
M2 引入关系 / 版本 / 审核三张治理表。
M3 引入向量表 knowledge_vector（全文 FTS5 虚表 knowledge_fts 由迁移 raw SQL 创建）。
M5 引入实验会话 experiment_session 与作答记录 experiment_attempt（JSON 字段以 Text 存储）。
V2 A1 引入 Markdown 知识库底座（additive，迁移 0006）：knowledge_item 增
extra_metadata 与来源身份冗余列；新增 tag/item_tag/knowledge_link/attachment/
tag_change_log/gc_task/import_origin/storage_lock。不改动 V1 既有表结构与关系。
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import fts as _fts  # noqa: F401  注册 FTS create_all 兜底事件（M3）
from app.db.base import Base
from knowledge_core.domain.entities import (
    CANONICALIZATION_VERSION,
    LINK_NORMALIZATION_VERSION,
    utcnow,
)


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
    # V2 A1：content 即 Markdown 正文（纯文本是合法 Markdown，旧数据零转换）。
    # extra_metadata 保留未知 frontmatter 字段（JSON 文本，双方言通用）。
    extra_metadata: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default="{}")
    # V2 A1：最新导入来源身份冗余列（快速判重；权威历史在 import_origin）。
    source_payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_instance_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
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


# --- V2 A1：开放 Markdown 知识库底座（迁移 0006，全部 additive）---
# 刻意不在 KnowledgeItemORM 上新增 relationship：V1 的删除/加载路径保持不变，
# 新表的清理一律由数据库外键 ON DELETE CASCADE / SET NULL 承担（SQLite 已开
# PRAGMA foreign_keys=ON），避免 ORM 级联改变既有行为。


class TagORM(Base):
    """标签字典（V2 A1）。name 唯一，大小写/规范化口径由服务层决定。"""

    __tablename__ = "tag"
    __table_args__ = (UniqueConstraint("name", name="uq_tag_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ItemTagORM(Base):
    """条目-标签多对多关联（V2 A1）。复合主键天然去重，两侧 FK CASCADE。"""

    __tablename__ = "item_tag"

    item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_item.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeLinkORM(Base):
    """Markdown 双向链接（V2 A1）。

    normalized_link_key 非空 + UNIQUE(source_item_id, normalized_link_key)，
    修复原 (source,target_title,alias) 因 alias nullable 导致 NULL≠NULL 的唯一失效。
    target_item_id 绑定稳定 UUID（删除置 NULL，链接降级为 missing 而非消失）；
    target_title/alias 保留原始书写字面，规范化绝不覆盖原文。
    """

    __tablename__ = "knowledge_link"
    __table_args__ = (
        UniqueConstraint("source_item_id", "normalized_link_key", name="uq_link_source_key"),
        Index("ix_knowledge_link_target_item_id", "target_item_id"),
        Index("ix_knowledge_link_normalized_link_key", "normalized_link_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_item.id", ondelete="CASCADE"), nullable=False
    )
    target_item_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge_item.id", ondelete="SET NULL"), nullable=True
    )
    target_title: Mapped[str] = mapped_column(String(500), nullable=False)
    alias: Mapped[str | None] = mapped_column(String(500), nullable=True)
    normalized_link_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    link_normalization_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=LINK_NORMALIZATION_VERSION
    )
    resolution: Mapped[str] = mapped_column(String(20), nullable=False, default="missing")
    cross_space: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AttachmentORM(Base):
    """附件元数据（V2 A1）。storage_key 内容寻址可共享，引用数由 COUNT 派生。"""

    __tablename__ = "attachment"
    __table_args__ = (Index("ix_attachment_storage_key", "storage_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_item.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    mime: Mapped[str] = mapped_column(String(200), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    storage_key: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TagChangeLogORM(Base):
    """标签变更审计（V2 A1，append-only）。

    item_id 可空（条目删除后 SET NULL 保留审计）；item_id_snapshot /
    item_title_snapshot 写入时固化，删除后仍可追溯身份与标题。
    仓库层只提供 append/list，不提供 update/delete。
    """

    __tablename__ = "tag_change_log"
    __table_args__ = (Index("ix_tag_change_log_item_id_snapshot", "item_id_snapshot"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    item_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge_item.id", ondelete="SET NULL"), nullable=True
    )
    item_id_snapshot: Mapped[str] = mapped_column(String(36), nullable=False)
    item_title_snapshot: Mapped[str] = mapped_column(String(500), nullable=False)
    old_tags: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    new_tags: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    actor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    change_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GcTaskORM(Base):
    """附件 GC 任务（V2 A1）：租约认领 + fencing token + 持锁 quarantine。

    status 含 cancelled（持锁复核发现引用>0，放弃回收，终态不删文件）。
    认领/流转走短事务条件更新（方言实现封装在 app/db/ 适配层）。
    """

    __tablename__ = "gc_task"
    __table_args__ = (
        Index("ix_gc_task_status_next_retry_at", "status", "next_retry_at"),
        Index("ix_gc_task_storage_key", "storage_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    storage_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lease_token: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    quarantine_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    quarantined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ImportOriginORM(Base):
    """导入来源身份历史（V2 A1，权威记录）。

    source_* hash 为源实例在其 source_canonicalization_version 下算出的值，
    原样持久化，不被目标实例再生覆盖；幂等判定比对源 hash。
    """

    __tablename__ = "import_origin"
    __table_args__ = (
        Index("ix_import_origin_item_id", "item_id"),
        Index("ix_import_origin_source_payload_hash", "source_payload_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_item.id", ondelete="CASCADE"), nullable=False
    )
    source_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_instance_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_document_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_canonicalization_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=CANONICALIZATION_VERSION
    )
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    import_batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class StorageLockORM(Base):
    """storage_key 租约锁表（V2 A1，SQLite 适配层用；PG 走 advisory lock）。

    租约式逻辑锁：短事务条件写入（新锁或过期接管）+ 单调 lease_token fencing +
    心跳续租；物理文件操作在 DB 写事务之外执行。非严格行级锁，不宣称完全并发安全。
    """

    __tablename__ = "storage_lock"

    storage_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner: Mapped[str] = mapped_column(String(64), nullable=False)
    lease_token: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)