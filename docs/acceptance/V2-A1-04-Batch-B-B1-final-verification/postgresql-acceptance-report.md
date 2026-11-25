# PostgreSQL 实测状态

**BLOCKED，真 PostgreSQL 套件未运行。** 本轮没有 PostgreSQL 真机通过项，没有新增测试跳过记录。Round 3 的既有日志记录 17 项因环境门控跳过。

待执行命令为：

```bash
uv run --locked --no-sync pytest -o addopts=--import-mode=importlib -ra \
  backend/tests/test_storage_lock_pg.py backend/tests/test_attachment_pg.py
```

| 冻结要求 | 本轮状态 |
| --- | --- |
| 双 backend advisory lock 与 TTL 不授权接管 | 未实测 |
| 真实断连接管、token 单调、旧 guard 拒写 | 未实测 |
| 100 key 单连接及部分获取失败清理 | 未实测，需与现有真机用例逐项比对并补证据 |
| heartbeat 与 verify/release 交错 | 未实测 |
| SQL 等待预算 | 未实测 |
| 实际 release 及物理连接清理 | 未实测 |
| Attachment 与 GC 仓储的真实双连接事务 | 未实测 |

Round 3 PostgreSQL 故障注入及 SQLite 证据按其原始类型保留。双真实 backend PID 与专用数据库安全核验是上述命令的执行前置。
