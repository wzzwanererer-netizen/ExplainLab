# 环境与证据复核

| 能力 | 本次证据 | 证据边界 |
| --- | --- | --- |
| SQLite 文件库 | 现行 GC、锁测试复跑，且有独立真实库探针 | 使用实际 SQLite 写锁和 SQLAlchemy 会话池 |
| Windows 文件系统 | 提交 B1 日志有真实占用、junction、no-clobber。独立子集的 Windows 占用通过 | 受限环境的 junction 自建跳过。真实双卷证明来自提交探针，能确认 Win32 17 及源保留，启动多卷拓扑仍是注入 |
| Windows 错误映射 | 当前文件系统与 DB guard 上注入预检 Win32 50 | 证实生产代码路径，错误来源为注入 |
| POSIX | 目录打开和 fsync 注入 | 真实权限、同句柄替换、link 与持久性仍未实测 |
| PG 替身 | 10 项复跑通过，独立执行 deadline 和 release 异常交错探针 | 本轮未连接真实 PostgreSQL，会话和传输行为仍待真实环境 |
| 真 PG | 当前 `EXPLAINLAB_PG_TEST_URL` 未设置，提交日志同样 gated | 无真实 advisory lock、TTL、断连/接管或双连接仓库结果 |
| 进程崩溃 | 提交的 `round2-final-sqlite-crash.txt` 与脚本显示真实 LCK-07 SQLite 子进程被终止 | SQLite 过期前拒绝接管，过期后 token 递增。PG 进程及 GC 隔离文件崩溃场景未覆盖 |

### 独立探针输出

以下记录来自一次性临时目录、临时库与可控替身，审计未加入或修改仓库测试。

```text
SQLite, actual database
sqlite_verification OperationalError elapsed_s 7.391 wait_s 0.15
sqlite_batch_handoff True elapsed_s 0.390
sqlite_batch_immediate_verify StorageLeaseLost
production_pool QueuePool checkout_timeout_s 30.0
sqlite_pool_probe TimeoutError elapsed_s 0.359 budget_s 0.04

Windows, actual temporary paths
reserved_db_probe accepted True db_path_exists_preflight False
reserved_db_probe db_path_became_directory True storage_initialized True

Windows, actual paths with a one-shot Win32 50 metadata failure
F12_preflight_fault {'temp_checks': 4, 'link': 0, 'rename': 1} published True

PG driver substitute
pg_fake_budget advisory acquisition deadline elapsed_s 0.203 wait_s 0.04 physical_fake_closed True
pg_fake_context_exit PostgresLockFailure phase release primary_context OperationalError physical_fake_closed True
```

上一节中的 PG 释放例先抛业务 ValueError，再由驱动替身注入释放 SQL 错误。表中 `primary_context` 是最终异常的直接上下文，原业务 ValueError 在其下层异常链中。结果验证的是传播顺序。具体步骤见 [finding-register.md](finding-register.md)。
