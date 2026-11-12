"""SQLAlchemy 声明基类。

M0 暂无业务表；M1 起的 ORM 模型统一继承 Base，
Alembic 通过 Base.metadata 自动生成迁移。
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass