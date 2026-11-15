"""M3 retrieval: knowledge_fts（按方言）+ 同步机制 + knowledge_vector

Revision ID: 0004_m3_retrieval
Revises: 0003_m2_governance
Create Date: 2026-11-14

全文索引按方言创建（ZIP-01）：
- SQLite：FTS5 虚表（trigram 分词，中文子串可命中）+ rowid 对齐同步触发器；
- PostgreSQL：原生 tsvector 表 + GIN 索引 + 触发器维护 tsv，删除经外键级联。
索引表不在 ORM metadata，env.py 已将其排除出 autogenerate。向量表为标准 ORM 表，
双方言通用。DDL 与 create_all 兜底共用 app.db.fts 的方言 DDL（单一来源，幂等）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.fts import FTS_DDL, PG_FTS_DDL

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
    # 按方言创建全文索引（DDL 单一来源，幂等）。
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        for statement in PG_FTS_DDL:
            op.execute(statement)
    elif dialect == "sqlite":
        for statement in FTS_DDL:
            op.execute(statement)
    else:
        raise ValueError(f"不支持的数据库方言: {dialect}")


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS knowledge_item_au ON knowledge_item")
        op.execute("DROP TRIGGER IF EXISTS knowledge_item_ai ON knowledge_item")
        op.execute("DROP FUNCTION IF EXISTS knowledge_fts_sync()")
        op.execute("DROP TABLE IF EXISTS knowledge_fts")
    elif dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS knowledge_item_ad")
        op.execute("DROP TRIGGER IF EXISTS knowledge_item_au")
        op.execute("DROP TRIGGER IF EXISTS knowledge_item_ai")
        op.execute("DROP TABLE IF EXISTS knowledge_fts")
    op.drop_table("knowledge_vector")