# PostgreSQL 环境状态

| 要求 | 本轮实测状态 |
| --- | --- |
| Linux guest 可用 | 当前无可用 guest，部署没能开始 |
| 独立数据目录、独立库与受限账号 | 未创建 |
| 仅回环、SCRAM | 未配置 |
| PostgreSQL 客户端 | 本会话 PATH 无 `psql` 或 `pg_ctl` |
| 实际连接 | Windows 127.0.0.1:5432 探测返回 WinError 10013。探测不能判定宿主是否已有服务或数据库 |
| 真实 DSN | `EXPLAINLAB_PG_TEST_URL` 未设置，未生成测试凭据 |
| 安全核验 | 数据库名、角色、服务端版本、端口、实际 data_directory 和两个 backend PID 均无真实连接可查 |

Windows psycopg 3.3.9 导入成功，仅用于说明驱动在本会话可导入。试验前须先核对独占的测试实例和数据库，现有 pytest fixture 会清理表数据。待执行的隔离设计见 [预检方案](../../audit/V2-A1-04-Batch-B-final-environment-preflight/postgresql-setup-plan.md)。
