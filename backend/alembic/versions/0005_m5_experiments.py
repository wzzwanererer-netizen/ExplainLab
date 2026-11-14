"""M5 experiments: experiment_session + experiment_attempt

Revision ID: 0005_m5_experiments
Revises: 0004_m3_retrieval
Create Date: 2026-11-15

实验会话承载生成内容（item_ids / payload 以 JSON 文本存储，兼容 SQLite 与 PostgreSQL）；
作答记录独立成表，外键级联删除。判分汇总在服务端，正确答案未作答不下发。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_m5_experiments"
down_revision: Union[str, None] = "0004_m3_retrieval"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "experiment_session",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("space_id", sa.String(length=36), nullable=True),
        sa.Column("item_ids", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["space_id"], ["knowledge_space.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "experiment_attempt",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("answers", sa.Text(), nullable=False),
        sa.Column("correct_count", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["experiment_session.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("experiment_attempt")
    op.drop_table("experiment_session")