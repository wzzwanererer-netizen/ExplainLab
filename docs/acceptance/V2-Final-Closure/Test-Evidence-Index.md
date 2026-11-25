# ExplainLab V2 · Backend Final Closure 测试与原始证据索引

## 1. 新增专项测试源码

- [backend/tests/test_v2_closure_gc_orp.py](file:///D:/ExplainLab/backend/tests/test_v2_closure_gc_orp.py)
- [backend/tests/test_v2_closure_pg_index_faults.py](file:///D:/ExplainLab/backend/tests/test_v2_closure_pg_index_faults.py)

## 2. WSL2 Ubuntu ext4 + PostgreSQL 18.6 终态证据（`closure-posix-pg.SqauvYgo`，`exit=0`）

- 驱动脚本：[evidence/run-closure-posix-pg.sh](evidence/run-closure-posix-pg.sh)
- 驱动总日志与退出码：[driver.log](evidence/closure-posix-pg.SqauvYgo/driver.log) · [exit.txt](evidence/closure-posix-pg.SqauvYgo/exit.txt)
- 源码覆盖 SHA-256 核验：[source-overlays.sha256](evidence/closure-posix-pg.SqauvYgo/source-overlays.sha256)
- PostgreSQL 18.6 服务端日志与 E2E 后库终态：[postgresql-server.log](evidence/closure-posix-pg.SqauvYgo/postgresql-server.log) · [db-after-e2e.log](evidence/closure-posix-pg.SqauvYgo/db-after-e2e.log)
- 各套件原始日志与 JUnit XML：
  - `closure-posix-sqlite`（7 passed, exit=0）：[log](evidence/closure-posix-pg.SqauvYgo/closure-posix-sqlite.log) · [xml](evidence/closure-posix-pg.SqauvYgo/closure-posix-sqlite.xml)
  - `closure-pg-gc02`（2 passed, exit=0）：[log](evidence/closure-posix-pg.SqauvYgo/closure-pg-gc02.log) · [xml](evidence/closure-posix-pg.SqauvYgo/closure-pg-gc02.xml)
  - `closure-pg-orp01`（1 passed, exit=0）：[log](evidence/closure-posix-pg.SqauvYgo/closure-pg-orp01.log) · [xml](evidence/closure-posix-pg.SqauvYgo/closure-pg-orp01.xml)
  - `closure-pg-orp05`（6 passed, exit=0）：[log](evidence/closure-posix-pg.SqauvYgo/closure-pg-orp05.log) · [xml](evidence/closure-posix-pg.SqauvYgo/closure-pg-orp05.xml)
  - `closure-pg-index-faults`（10 passed, exit=0）：[log](evidence/closure-posix-pg.SqauvYgo/closure-pg-index-faults.log) · [xml](evidence/closure-posix-pg.SqauvYgo/closure-pg-index-faults.xml)
  - `closure-pg-review`（6 passed, exit=0）：[log](evidence/closure-posix-pg.SqauvYgo/closure-pg-review.log) · [xml](evidence/closure-posix-pg.SqauvYgo/closure-pg-review.xml)
  - `closure-pg-e2e`（1 passed, exit=0）：[log](evidence/closure-posix-pg.SqauvYgo/closure-pg-e2e.log) · [xml](evidence/closure-posix-pg.SqauvYgo/closure-pg-e2e.xml)
  - `closure-pg-regression`（205 passed, exit=0）：[log](evidence/closure-posix-pg.SqauvYgo/closure-pg-regression.log) · [xml](evidence/closure-posix-pg.SqauvYgo/closure-pg-regression.xml)

> 注：首轮测试目录 `evidence/closure-posix-pg.3sULgHrw/`（因 Alembic `fileConfig` 夹具顺序导致 `caplog` 为空）按原样保留备查，未删除历史日志。

## 3. Windows 实机测试与质量门证据

- Windows 收尾专项（7 passed / 19 PG-skipped, exit=0）：[closure-windows-gc-orp.log](evidence/closure-windows-gc-orp.log) · [xml](evidence/closure-windows-gc-orp.xml)
- Windows 根级全量（历史首轮，与 WSL2 PG 并发跑，1519 passed / 1 transient LCK-05 0.2s TTL fail / 240 skipped, exit=1，原样保留）：[closure-windows-full.log](evidence/closure-windows-full.log) · [xml](evidence/closure-windows-full.xml)
- Windows `test_storage_lock_sqlite.py` 独立复跑（28 passed / 0 failed, exit=0）：[closure-windows-lck-recheck.log](evidence/closure-windows-lck-recheck.log) · [xml](evidence/closure-windows-lck-recheck.xml)
- **Windows 根级全量独享复验 Addendum（无并行任务，1520 passed / 0 failed / 240 skipped, exit=0）**：[closure-windows-full-clean.log](evidence/closure-windows-full-clean.log) · [xml](evidence/closure-windows-full-clean.xml)
- 质量门与 Git 边界快照：[closure-quality-and-git.log](evidence/closure-quality-and-git.log)

## 4. 继承的 V2-Final 原始基线材料

- [V2-Final 整改报告](../V2-Final/V2-Final-Audit-Remediation-Report.md)
- [V2-Final 53 项验收矩阵](../V2-Final/Acceptance-Matrix.md)
- [V2-Final P1-01 说明](../V2-Final/P1-01-Review-Index-Remediation.md)
- [V2-Final 测试报告](../V2-Final/V2-Test-Report.md)
