"""全文索引基础设施（M3 / ZIP-01）：按方言提供 DDL 单一来源 + create_all 兜底。

SQLite：knowledge_fts 为 FTS5 虚表（trigram 分词，中文子串可命中），用触发器与
knowledge_item 保持同步（rowid 对齐，删除按 rowid）。

PostgreSQL：knowledge_fts 为普通表（item_id + tsvector），GIN 索引；触发器以
to_tsvector('simple', title||content) 维护 tsv，删除经外键 ON DELETE CASCADE 级联。
全程使用原生 tsvector / tsquery，不使用 FTS5 / MATCH / bm25 / rowid。

两种方言的索引表均不在 ORM metadata，env.py 已将 knowledge_fts* 排除出 autogenerate。
两条建表路径共用同一份方言 DDL：
- Alembic 迁移 0004 按方言显式执行（生产 / 迁移测试）；
- Base.metadata.create_all（API 测试夹具）经 after_create 事件按方言兜底创建，
  保证不经迁移的测试库同样具备全文索引与触发器。
DDL 均带 IF NOT EXISTS / OR REPLACE / DROP IF EXISTS，重复执行安全。
"""

from __future__ import annotations

from sqlalchemy import Connection, event

from app.db.base import Base

# --- SQLite：FTS5 trigram 虚表 + rowid 对齐同步触发器 ---
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

# --- PostgreSQL：原生 tsvector 表 + GIN 索引 + 触发器（删除经外键级联）---
PG_FTS_DDL: tuple[str, ...] = (
    "CREATE TABLE IF NOT EXISTS knowledge_fts ("
    "item_id VARCHAR(36) PRIMARY KEY "
    "REFERENCES knowledge_item(id) ON DELETE CASCADE, "
    "tsv tsvector)",
    "CREATE INDEX IF NOT EXISTS knowledge_fts_tsv_idx ON knowledge_fts USING gin(tsv)",
    "CREATE OR REPLACE FUNCTION knowledge_fts_sync() RETURNS trigger AS $$ "
    "BEGIN "
    "INSERT INTO knowledge_fts(item_id, tsv) "
    "VALUES (NEW.id, to_tsvector('simple', coalesce(NEW.title, '') || ' ' || coalesce(NEW.content, ''))) "
    "ON CONFLICT (item_id) DO UPDATE SET tsv = EXCLUDED.tsv; "
    "RETURN NEW; "
    "END; "
    "$$ LANGUAGE plpgsql",
    "DROP TRIGGER IF EXISTS knowledge_item_ai ON knowledge_item",
    "CREATE TRIGGER knowledge_item_ai AFTER INSERT ON knowledge_item "
    "FOR EACH ROW EXECUTE FUNCTION knowledge_fts_sync()",
    "DROP TRIGGER IF EXISTS knowledge_item_au ON knowledge_item",
    "CREATE TRIGGER knowledge_item_au AFTER UPDATE OF title, content ON knowledge_item "
    "FOR EACH ROW EXECUTE FUNCTION knowledge_fts_sync()",
)


def create_fts(connection: Connection) -> None:
    """按方言在给定连接上创建全文索引与同步机制（幂等）。"""
    dialect = connection.dialect.name
    if dialect == "postgresql":
        ddl = PG_FTS_DDL
    elif dialect == "sqlite":
        ddl = FTS_DDL
    else:
        raise ValueError(f"不支持的数据库方言: {dialect}")
    for statement in ddl:
        connection.exec_driver_sql(statement)


@event.listens_for(Base.metadata, "after_create")
def _create_fts_after_create(target, connection: Connection, **_kw) -> None:
    """create_all 完成后按方言兜底创建全文索引（target 为 MetaData，整体触发一次）。

    迁移路径使用 Alembic 自有的 MetaData，不会触发 Base.metadata 的此事件，
    故无重复创建之虞；DDL 亦带幂等保护。
    """
    if "knowledge_item" in target.tables:
        create_fts(connection)