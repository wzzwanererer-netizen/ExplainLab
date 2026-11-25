"""V2 A1: 开放 Markdown 知识库底座（additive，双方言）

Revision ID: 0006_v2_markdown_kb
Revises: 0005_m5_experiments
Create Date: 2026-11-18

设计依据：docs/plans/V2-batch-A-design.md §2.2.2（迁移 0006）。

新增内容（全部 additive，不改动 V1 既有表结构/约束/触发器）：
- knowledge_item 增 extra_metadata（Text JSON，NOT NULL DEFAULT '{}'，旧行无损）
  与来源身份冗余列 source_payload_hash / source_content_hash / source_instance_id；
- tag / item_tag：标签字典与多对多关联；
- knowledge_link：双向链接，normalized_link_key **非空** + UNIQUE(source_item_id,
  normalized_link_key) + link_normalization_version，修复原 (source,target_title,
  alias) 因 alias nullable 在 SQLite/PG 下 NULL≠NULL 导致唯一约束失效的问题；
  target_item_id 外键 SET NULL（目标删除后链接降级保留，不随源消失）；
- attachment：附件元数据，storage_key 内容寻址可共享，引用数由 COUNT 派生；
- tag_change_log：append-only 审计，item_id 可空 SET NULL + item_id_snapshot /
  item_title_snapshot 固化身份（口径 C：审计保留）；
- gc_task：租约认领（lease_owner/lease_expires_at/lease_token/attempts/
  next_retry_at）+ 持锁 quarantine（quarantine_path/quarantined_at），status 含
  cancelled；
- import_origin：跨实例来源身份持久化（源 hash 原样保存，不被目标再生覆盖）；
- storage_lock：SQLite 租约式逻辑锁表（PG 侧用 advisory lock，见 §10）。

方言边界：本迁移只做标准 DDL；唯一的方言分支是 downgrade 删除 knowledge_item
新增列——PostgreSQL 用 ALTER TABLE DROP COLUMN（op.drop_column），SQLite 用原生
ALTER TABLE DROP COLUMN（需 SQLite ≥ 3.35）。**刻意不用 batch_alter_table**：
batch 模式会重建 knowledge_item 表，从而丢失 M3 的 FTS5 同步触发器并可能重排
rowid（FTS5 索引按 rowid 对齐），造成检索损坏。原生 DROP COLUMN 保留触发器与
rowid（已用真实 SQLite 验证）。低于 3.35 时显式报错，不静默降级。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_v2_markdown_kb"
down_revision: Union[str, None] = "0005_m5_experiments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# downgrade 时需要删除的 knowledge_item 新增列（顺序无关，均未被索引/触发器引用）
_ITEM_NEW_COLUMNS = (
    "extra_metadata",
    "source_payload_hash",
    "source_content_hash",
    "source_instance_id",
)


def upgrade() -> None:
    # --- knowledge_item 增量列（旧数据无损：extra_metadata 以 '{}' 回填）---
    op.add_column(
        "knowledge_item",
        sa.Column("extra_metadata", sa.Text(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "knowledge_item", sa.Column("source_payload_hash", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "knowledge_item", sa.Column("source_content_hash", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "knowledge_item", sa.Column("source_instance_id", sa.String(length=64), nullable=True)
    )

    # --- 标签字典与关联 ---
    op.create_table(
        "tag",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_tag_name"),
    )
    op.create_table(
        "item_tag",
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("tag_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["knowledge_item.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tag.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("item_id", "tag_id"),
    )

    # --- 双向链接（非空规范化键 + 版本化）---
    op.create_table(
        "knowledge_link",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_item_id", sa.String(length=36), nullable=False),
        sa.Column("target_item_id", sa.String(length=36), nullable=True),
        sa.Column("target_title", sa.String(length=500), nullable=False),
        sa.Column("alias", sa.String(length=500), nullable=True),
        sa.Column("normalized_link_key", sa.String(length=1024), nullable=False),
        sa.Column("link_normalization_version", sa.Integer(), nullable=False),
        sa.Column("resolution", sa.String(length=20), nullable=False),
        sa.Column("cross_space", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_item_id"], ["knowledge_item.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_item_id"], ["knowledge_item.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_item_id", "normalized_link_key", name="uq_link_source_key"),
    )
    op.create_index(
        "ix_knowledge_link_target_item_id", "knowledge_link", ["target_item_id"]
    )
    op.create_index(
        "ix_knowledge_link_normalized_link_key", "knowledge_link", ["normalized_link_key"]
    )

    # --- 附件元数据 ---
    op.create_table(
        "attachment",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("mime", sa.String(length=200), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["knowledge_item.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_attachment_storage_key", "attachment", ["storage_key"])

    # --- 标签变更审计（append-only，删除后保身份快照）---
    op.create_table(
        "tag_change_log",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=True),
        sa.Column("item_id_snapshot", sa.String(length=36), nullable=False),
        sa.Column("item_title_snapshot", sa.String(length=500), nullable=False),
        sa.Column("old_tags", sa.Text(), nullable=False),
        sa.Column("new_tags", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=True),
        sa.Column("change_source", sa.String(length=50), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["knowledge_item.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tag_change_log_item_id_snapshot", "tag_change_log", ["item_id_snapshot"]
    )

    # --- GC 任务（租约 + fencing + quarantine）---
    op.create_table(
        "gc_task",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("storage_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("lease_owner", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quarantine_path", sa.String(length=512), nullable=True),
        sa.Column("quarantined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gc_task_status_next_retry_at", "gc_task", ["status", "next_retry_at"])
    op.create_index("ix_gc_task_storage_key", "gc_task", ["storage_key"])

    # --- 导入来源身份历史 ---
    op.create_table(
        "import_origin",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("source_payload_hash", sa.String(length=64), nullable=False),
        sa.Column("source_content_hash", sa.String(length=64), nullable=False),
        sa.Column("source_instance_id", sa.String(length=64), nullable=True),
        sa.Column("source_document_id", sa.String(length=36), nullable=False),
        sa.Column("source_canonicalization_version", sa.Integer(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("import_batch_id", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["item_id"], ["knowledge_item.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_origin_item_id", "import_origin", ["item_id"])
    op.create_index(
        "ix_import_origin_source_payload_hash", "import_origin", ["source_payload_hash"]
    )

    # --- storage_key 租约锁（SQLite 适配层；PG 用 advisory lock）---
    op.create_table(
        "storage_lock",
        sa.Column("storage_key", sa.String(length=64), nullable=False),
        sa.Column("owner", sa.String(length=64), nullable=False),
        sa.Column("lease_token", sa.Integer(), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("storage_key"),
    )


def downgrade() -> None:
    # 先删依赖表，再删字典表（item_tag 依赖 tag）
    op.drop_index("ix_import_origin_source_payload_hash", table_name="import_origin")
    op.drop_index("ix_import_origin_item_id", table_name="import_origin")
    op.drop_table("import_origin")
    op.drop_index("ix_gc_task_storage_key", table_name="gc_task")
    op.drop_index("ix_gc_task_status_next_retry_at", table_name="gc_task")
    op.drop_table("gc_task")
    op.drop_index("ix_tag_change_log_item_id_snapshot", table_name="tag_change_log")
    op.drop_table("tag_change_log")
    op.drop_index("ix_attachment_storage_key", table_name="attachment")
    op.drop_table("attachment")
    op.drop_index("ix_knowledge_link_normalized_link_key", table_name="knowledge_link")
    op.drop_index("ix_knowledge_link_target_item_id", table_name="knowledge_link")
    op.drop_table("knowledge_link")
    op.drop_table("item_tag")
    op.drop_table("storage_lock")
    op.drop_table("tag")

    # 删除 knowledge_item 增量列：保留 FTS 触发器与 rowid 对齐（见模块 docstring）
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        version = bind.exec_driver_sql("SELECT sqlite_version()").scalar_one()
        major, minor = (int(part) for part in str(version).split(".")[:2])
        if (major, minor) < (3, 35):
            raise RuntimeError(
                f"SQLite {version} 不支持 ALTER TABLE DROP COLUMN（需 ≥ 3.35）；"
                "拒绝以重建表方式降级，避免破坏 FTS5 触发器与 rowid 对齐"
            )
        for column in _ITEM_NEW_COLUMNS:
            op.execute(f"ALTER TABLE knowledge_item DROP COLUMN {column}")
    else:
        for column in _ITEM_NEW_COLUMNS:
            op.drop_column("knowledge_item", column)