# ExplainLab V2 · Backend Final Closure Report

**当前项目状态**：`V2 BACKEND REMEDIATION COMPLETED / READY FOR FINAL INDEPENDENT REVIEW`

> 说明：本报告记录最后一轮后端审计遗留证据缺口的整改与实机取证。**完成整改不等于独立审计通过**；最终 `PASS` 裁决仍由独立审计 Agent 负责。

## 1. 基线与保护范围核验

- **Git 分支 / HEAD**：`fix/m0-admission-and-m5-regressions` / `970c0d8ec05f0b8c68286839a56b14c74ea230c6`（未 commit、未 push、未改写历史）。
- **既有审计材料核验**：
  - 原独立审计包 `docs/acceptance/V2-Final/ExplainLab-V2-Final-Independent-Audit.zip` SHA-256 = `c05513582474020b856c98822e7f59d74792edc2094d5e031f0381fa6e76cc65`（一致）。
  - 上轮整改包 `docs/acceptance/V2-Final/ExplainLab-V2-Final-Audit-Remediation.zip` SHA-256 = `bef78a0bca4688463cfe003c969ca5283ce8f7c52c0196140aa387c6beaba807`（一致）。
- **生产代码零漂移**：逐字节核验 `backend/app/` 全部 **20 个生产文件**与上轮整改基线完全一致（`MISMATCHES=0`）。P1-01 及 B1–B5 业务代码、Knowledge Core、Alembic 迁移、前端与依赖清单均零修改。

## 2. 四项最终独立审计遗留缺口收尾结果

| 缺口项 | 实机验证环境 | 通过 / 失败 / 跳过 | 退出码 | 专项报告与原始证据 |
| --- | --- | ---: | ---: | --- |
| **GC-02**（PG 双 Worker 竞争同物理 key 不同任务） | WSL2 Ubuntu `ext4` + PostgreSQL 18.6 | **2 / 0 / 0** | `0` | [GC-02 报告](GC-02-PostgreSQL-Concurrency-Report.md) · [日志](evidence/closure-posix-pg.SqauvYgo/closure-pg-gc02.log) |
| **ORP-01**（DB Commit 失败 → 孤儿 → 扫描 → GC → 24h → Purge） | Windows SQLite / ext4 SQLite / PostgreSQL 18.6 | **1/0/0** · **1/0/0** · **1/0/0** | `0` | [ORP-01 报告](ORP-01-Orphan-Recovery-Report.md) · [PG 日志](evidence/closure-posix-pg.SqauvYgo/closure-pg-orp01.log) |
| **ORP-05**（终态任务残留 + 真实子进程崩溃接管 + 活跃/未知槽保护） | Windows SQLite / ext4 SQLite / PostgreSQL 18.6 | **6/0/0** · **6/0/0** · **6/0/0** | `0` | [ORP-05 报告](ORP-05-Crash-Recovery-Report.md) · [PG 日志](evidence/closure-posix-pg.SqauvYgo/closure-pg-orp05.log) |
| **PostgreSQL 索引提交故障注入**（attachment / tags / origin / links / archive + TX1 vs TX2 + P1-01 + embedder） | WSL2 Ubuntu `ext4` + PostgreSQL 18.6 | **10 / 0 / 0** | `0` | [PG 索引故障报告](PostgreSQL-Index-Failure-Injection-Report.md) · [日志](evidence/closure-posix-pg.SqauvYgo/closure-pg-index-faults.log) |

## 3. 全量回归与质量门汇总

| 套件 | 环境 | 通过 | 失败 | 跳过 | 退出码 | 原始证据 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| WSL2 ext4 + PostgreSQL 18.6 总驱动（8 套件全套） | Ubuntu ext4 + PG 18.6 | **238** | **0** | **0** | `0` | [driver.log](evidence/closure-posix-pg.SqauvYgo/driver.log) · [exit.txt](evidence/closure-posix-pg.SqauvYgo/exit.txt) |
| 其中：`closure-pg-review`（含 R1.1-IMP-38 五断点） | Ubuntu ext4 + PG 18.6 | 6 | 0 | 0 | `0` | [日志](evidence/closure-posix-pg.SqauvYgo/closure-pg-review.log) |
| 其中：`closure-pg-e2e`（`attachments=0, advisory_locks=0`） | Ubuntu ext4 + PG 18.6 | 1 | 0 | 0 | `0` | [日志](evidence/closure-posix-pg.SqauvYgo/closure-pg-e2e.log) · [终态](evidence/closure-posix-pg.SqauvYgo/db-after-e2e.log) |
| 其中：`closure-pg-regression`（`backend/tests/*_pg.py`） | Ubuntu ext4 + PG 18.6 | 205 | 0 | 0 | `0` | [日志](evidence/closure-posix-pg.SqauvYgo/closure-pg-regression.log) |
| Windows 新增收尾专项（`test_v2_closure_*`） | Windows SQLite | 7 | 0 | 19（PG 门控） | `0` | [日志](evidence/closure-windows-gc-orp.log) |
| Windows 根级全量回归（历史首轮，与 WSL2 PG 并发跑，LCK-05 0.2s 墙钟偶发 1 败，原样保留） | Windows SQLite | 1519 | 1 | 240 | `1` | [日志](evidence/closure-windows-full.log) |
| Windows `test_storage_lock_sqlite.py` 独立复跑 | Windows SQLite | **28** | **0** | **0** | `0` | [日志](evidence/closure-windows-lck-recheck.log) |
| **Windows 根级全量回归（无并行任务独享复验 Addendum）** | Windows SQLite | **1520** | **0** | **240** | **`0`** | [日志](evidence/closure-windows-full-clean.log) · [JUnit](evidence/closure-windows-full-clean.xml) |
| `ruff check backend knowledge-core` | Windows | — | 0 | — | `0` | [质量门日志](evidence/closure-quality-and-git.log) |
| `git diff --check` | Windows | — | 0 | — | `0` | [质量门日志](evidence/closure-quality-and-git.log) |
| 全仓 `ruff check`（如实记录 8 项历史归档错误） | Windows | — | 8（历史归档） | — | `1` | [质量门日志](evidence/closure-quality-and-git.log) |

## 4. 交付物清单

所有报告与原始证据均位于 `docs/acceptance/V2-Final-Closure/`，并归档至独立审计包 `ExplainLab-V2-Backend-Final-Closure.zip`：

1. [Backend-Final-Closure-Report.md](Backend-Final-Closure-Report.md)
2. [Audit-Gap-Remediation-Mapping.md](Audit-Gap-Remediation-Mapping.md)
3. [GC-02-PostgreSQL-Concurrency-Report.md](GC-02-PostgreSQL-Concurrency-Report.md)
4. [ORP-01-Orphan-Recovery-Report.md](ORP-01-Orphan-Recovery-Report.md)
5. [ORP-05-Crash-Recovery-Report.md](ORP-05-Crash-Recovery-Report.md)
6. [PostgreSQL-Index-Failure-Injection-Report.md](PostgreSQL-Index-Failure-Injection-Report.md)
7. [Test-Evidence-Index.md](Test-Evidence-Index.md)
8. [Unresolved.md](Unresolved.md)
9. [Git-State.md](Git-State.md)
10. [SHA256SUMS](SHA256SUMS)
