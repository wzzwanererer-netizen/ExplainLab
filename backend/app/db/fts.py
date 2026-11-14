"""FTS5 全文索引基础设施（M3）：DDL 单一来源 + create_all 兜底。

knowledge_fts 为 FTS5 虚表（trigram 分词，中文子串可命中），用触发器与
knowledge_item 保持同步（rowid 对齐）。虚表不在 ORM metadata，env.py 已将其
及影子表排除出 autogenerate。

两条建表路径共用同一份 DDL：
- Alembic 迁移 0004 显式执行 FTS_DDL（生产 / 迁移测试）；
- Base.metadata.create_all（API 测试夹具）经 after_create 事件兜底创建，
  保证不经迁移的测试库同样具备全文索引与触发器。
DDL 均带 IF NOT EXISTS，重复执行安全。
"""

from __future__ import annotations

from sqlalchemy import Connection, event

from app.db.base import Base

FTS_DDL: tuple[str, ...] = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5("
    "item_id UNINDEXED, title, content, tokenize='trigram')",
    "CREATE TRIGGER IF NOT EXISTS knowledge_item_ai AFTER INSERT ON knowledge_item BEGIN "
    "INSERT INTO knowledge_fts(rowid, item_id, title, content) "
    "VALUES (new.rowid, new.id, new.title, new.content); END",
    "CREATE TRIGGER IF NOT EXISTS knowledge_item_au "
    "AFTER UPDATE OF title, content ON knowledge_item BEGIN "
    "DELETE FROM knowledge_fts WHERE rowid = old.rowid; "
    "INSERT INTO knowledge_fts(rowid, item_id, title, content) "
    "VALUES (new.rowid, new.id, new.title, new.content); END",
    "CREATE TRIGGER IF NOT EXISTS knowledge_item_ad AFTER DELETE ON knowledge_item BEGIN "
    "DELETE FROM knowledge_fts WHERE rowid = old.rowid; END",
)


def create_fts(connection: Connection) -> None:
    """在给定连接上创建 FTS 虚表与同步触发器（幂等）。"""
    for statement in FTS_DDL:
        connection.exec_driver_sql(statement)


@event.listens_for(Base.metadata, "after_create")
def _create_fts_after_create(target, connection: Connection, **_kw) -> None:
    """create_all 完成后兜底创建 FTS（target 为 MetaData，整体触发一次）。

    迁移路径使用 Alembic 自有的 MetaData，不会触发 Base.metadata 的此事件，
    故无重复创建之虞；DDL 亦带 IF NOT EXISTS。
    """
    if "knowledge_item" in target.tables:
        create_fts(connection)