# B1-T04 · PostgreSQL Repository 定点验收

**PASS。** PostgreSQL 18.6 独立数据库，原有 Alembic 迁移路径，真实 TCP 会话。13 通过，0 失败，0 跳过，退出 0。9 个新增用例，加上 4 个既有用例。

| 断言 | 真实证据 |
| --- | --- |
| 附件 save/flush 归属外层事务 | 写入 Session 可读，第二 Session 在提交前不可读，外层 rollback 后全新 Session 查不到记录 |
| 附件外键与回滚 | 不存在的 item_id 触发 PostgreSQL SQLSTATE `23503`。rollback 后新 Session 看不到非法附件，也看不到同一事务中已 flush 的合法附件 |
| 共享引用、删除与 DISTINCT | 沿用同一 key 的两条真实引用用例，COUNT 为 2 时 `list_storage_keys()` 只返回一个 key，删除后 COUNT 为 1 |
| pending → running 与过期接管 | 首次认领 token/attempts 为 1/1。未过期认领拒绝，过期后通过且为 2/2。新 Session 复核最终状态 |
| 不可认领 | 实际运行未到期、隔离等待、pending/running 的 attempts 耗尽，以及 DONE、CANCELLED、FAILED_PERMANENT、NEEDS_MANUAL 均拒绝，拒绝后保留原状态或原计数 |
| worker 写回 | 调用方故意改动实体 attempts，通过合法状态写回后，数据库保持原 attempts。旧 token 与不合法重写仍拒绝 |
| 并发认领 | 保留原双 Session 行锁竞争用例，只有一个认领成功，最终 token/attempts 为 1/1 |

本轮只修改既有 PG 测试文件，Repository 语义沿用基线后的 B1 工作树。历史 SQLite 排序断言的偶发性单独列入回归记录。

[pytest 原始日志](evidence/wsl-final.g8LQ7isi/t04-postgresql.log) · [JUnit](evidence/wsl-final.g8LQ7isi/t04-postgresql.xml) · [PG 服务端日志](evidence/wsl-final.g8LQ7isi/postgresql-server.log)
