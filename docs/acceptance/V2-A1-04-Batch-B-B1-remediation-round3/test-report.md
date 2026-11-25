# 测试结果

每份原始日志首行记录完整命令，末行记录退出码。根级全量按仓库配置一次收集 Backend 和 Core。冻结单列运行早于末次恢复 Windows busy 历史断言，新增恢复不涉及冻结回归覆盖的路径。最终根级全量覆盖交付源码。

| 验证 | 输出摘要 | 退出码 | 原始日志 |
| --- | --- | ---: | --- |
| 六项缺陷专项与相关原断言 | 32 passed, 1 skipped, 164 deselected, 1 warning in 7.76s | 0 | [pytest-round3-targeted.txt](evidence/pytest-round3-targeted.txt) |
| B1 全部专项 | 175 passed, 22 skipped, 1 warning in 43.73s | 0 | [pytest-b1-all.txt](evidence/pytest-b1-all.txt) |
| Batch A / A1-02 / A1-03 / V1 冻结回归 | 834 passed, 154 skipped, 1 warning in 238.56s (0:03:58) | 0 | [pytest-frozen.txt](evidence/pytest-frozen.txt) |
| SQLite/Core 根级全量 | 1299 passed, 200 skipped, 1 warning in 307.92s (0:05:07) | 0 | [pytest-sqlite-core-full.txt](evidence/pytest-sqlite-core-full.txt) |
| PostgreSQL 真实套件门控 | 17 skipped, 1 warning in 0.17s | 0 | [pytest-postgresql-real-gate.txt](evidence/pytest-postgresql-real-gate.txt) |
| POSIX 相关场景及 fsync 注入 | 2 passed, 1 skipped, 99 deselected, 1 warning in 0.57s | 0 | [pytest-posix-gate.txt](evidence/pytest-posix-gate.txt) |
| Ruff Backend/Core | All checks passed! | 0 | [ruff-code.txt](evidence/ruff-code.txt) |
| Ruff 全仓 | Found 5 errors. | 1 | [ruff-repo.txt](evidence/ruff-repo.txt) |

前端和依赖锁文件无变动，本轮未重跑前端构建或检查。Ruff 全仓的 5 项均位于旧审计归档内的迁移源码副本，实际迁移目录、Backend 和 Core 的 lint 检查结果见上。

## 真实 SQLite 计时

0.15 秒预算，真实 SQLite 文件库和生产连接池。原始命令、输出和退出码见 [sqlite-timing.txt](evidence/sqlite-timing.txt)。

```text
exclusive fence: StorageLeaseLost, elapsed=0.156s
saturated checkout: no guard, elapsed=0.156s
first lease exhausted in batch: no guard, elapsed=0.157s
retry after expiry: token=2
```

## 中间运行记录

保留初始与中间运行原始日志。首次专项选择表达式误带引号，随后的重跑去掉多余引号。早期 B1 发现 PostgreSQL 竞争等待接近 deadline 时返回分类错误，修复后保留返回 None 的断言。另一次并行 B1 运行暴露 SQLite checkout 调度开销及过短的退出清理时间，调整后保留原断言。修复过程中还更正了新 reparse 注入测试漏导入的问题。全量初跑发现 Alembic 迁移测试替换全局日志配置，导致四个新增 PG 释放日志断言收不到 record。新增替身测试在其 fixture 中直接捕获同一个生产 logger，仍断言稳定错误代码，迁移及生产日志配置保持原样。对迁移后紧接释放断言的运行记录见 [pytest-migration-log-isolation.txt](evidence/pytest-migration-log-isolation.txt)。部分旧日志由人工结束，尾端无 pytest 退出汇总，完成结果以表中最终日志为准。
