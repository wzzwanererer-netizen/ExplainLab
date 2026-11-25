# LCK-07 · 客户端进程终止

**PASS。** Ubuntu WSL2，真实 PostgreSQL 18.6。定点用例 1 通过、0 跳过、退出 0，既有 PG 锁回归另有 13 通过、0 跳过、退出 0。

1. Python 子进程 PID 536 通过生产 `PostgresStorageKeyLock` 获取并验证 guard。它的专用 PG backend 为 539。
2. 父进程通过真实 `pg_locks` 查到该 PID 对指定 key 的已授予独占 advisory lock，并在此期间验证另一客户端获取失败。
3. 父进程终止的是 Python 客户端。退出码 `-9`，随后验证 PG backend 消失、原 advisory lock 计数归零。
4. 第二客户端接管成功，token 从 1 增至 2。通过旧租约值的 verify、release 均被拒绝，新租约仍有效，数据库记录保留新 owner/token。

终止后，旧进程中的 guard 对象随进程消失。第 4 步直接验证遗留租约凭证无法恢复。原 guard 对象在专用连接失效后的拒绝由既有 `test_lck05_pg_old_guard_aborts_after_takeover` 回归关联覆盖。历史 `pg_terminate_backend` 有独立日志。

[定点原始日志](evidence/wsl-final.g8LQ7isi/lck07-postgresql.log) · [JUnit](evidence/wsl-final.g8LQ7isi/lck07-postgresql.xml) · [PG 锁回归](evidence/wsl-final.g8LQ7isi/pg-lock-regression.log) · [历史服务端终止探针](../V2-A1-04-Batch-B-B1-environment-recovery/evidence/pg-probe.OL0D7vGW/probe.log)
