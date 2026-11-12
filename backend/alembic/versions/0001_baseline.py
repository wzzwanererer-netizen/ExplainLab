"""baseline：M0 工程基线，建立迁移链起点，不创建业务表。

Revision ID: 0001_baseline
Revises:
Create Date: 2026-11-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """M0 基线：业务表自 M1 起通过后续迁移引入。"""


def downgrade() -> None:
    """基线无对象可回滚。"""