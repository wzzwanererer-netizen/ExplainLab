"""M3 retrieval: knowledge_fts (FTS5 trigram) + sync triggers + knowledge_vector

Revision ID: 0004_m3_retrieval
Revises: 0003_m2_governance
Create Date: 2026-11-14

全文索引为 FTS5 虚表（trigram 分词，中文子串可命中），用触发器与
knowledge_item 保持同步（rowid 对齐，删除按 rowid）。虚表不在 ORM metadata，
env.py 已将其及影子表排除出 autogenerate。向量表为标准 ORM 表。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.fts import FTS_DDL

revision: str = "0004_m3_retrieval"
down_revision: Union[str, None] = "0003_m2_governance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_vector",
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("vector", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["knowledge_item.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("item_id"),
    )
    # FTS5 虚表（trigram 分词，中文子串可命中）+ rowid 对齐同步触发器。
    # DDL 与 create_all 兜底共用 app.db.fts.FTS_DDL（单一来源，幂等）。
    for statement in FTS_DDL:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS knowledge_item_ad")
    op.execute("DROP TRIGGER IF EXISTS knowledge_item_au")
    op.execute("DROP TRIGGER IF EXISTS knowledge_item_ai")
    op.execute("DROP TABLE IF EXISTS knowledge_fts")
    op.drop_table("knowledge_vector")