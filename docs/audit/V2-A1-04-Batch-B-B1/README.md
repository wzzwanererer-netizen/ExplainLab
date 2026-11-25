# V2 A1-04 Batch B · B1 交付证据包

- 基线：`970c0d8ec05f0b8c68286839a56b14c74ea230c6`
- 分支：`fix/m0-admission-and-m5-regressions`
- 状态：B1-T01…T04 实现完成；SQLite + 真实 Windows 文件系统已验证；PostgreSQL 阻塞、POSIX/进程 kill/TOCTOU 未验证；**未提交**。
- 停止点：按指令停在 B1，未进入 B2，未更新 `MILESTONES.md`，未 push。

## 文件

| 文件 | 内容 |
|---|---|
| `b1-implementation-report.md` | 任务状态、实际修改文件与原因、关键实现口径、契约核对 |
| `b1-acceptance-report.md` | 测试输出/退出码、验收编号映射、未验证清单、判定 |
| `known-issues-and-risks.md` | 阻塞项、未执行场景、审计关注点、不得声称 |
| `SHA256SUMS.txt` | B1 代码/测试/报告/原始证据的 SHA-256 清单 |
| `raw/` | 原始测试输出、环境、PG 可用性、git 状态 |

## 原始证据索引

| 文件 | 说明 |
|---|---|
| `raw/environment.txt` | Python 3.11.9 / Windows 10.0.26300 / SQLite 3.45.1 |
| `raw/pg-availability.txt` | `EXPLAINLAB_PG_TEST_URL` 未设置、无 PG 工具/监听 |
| `raw/pytest-t01-t02-storage-windows.txt` | 44 passed, 1 skipped（POSIX-only） |
| `raw/pytest-t02-windows-real.txt` | Windows 真机专项 6 passed |
| `raw/pytest-t03-lock-sqlite.txt` | SQLite 锁 20 passed |
| `raw/pytest-t03-t04-pg-skipped.txt` | PG 门控 15 skipped（未验证） |
| `raw/pytest-t04-repository-sqlite.txt` | 仓储 16 passed |
| `raw/pytest-full.txt` | 根级全量 1204 passed, 194 skipped |
| `raw/ruff-code.txt` | `ruff check backend knowledge-core` 通过 |
| `raw/ruff-check.txt` | 仓库全量：5 errors 均在未跟踪审阅快照，非 B1 代码 |
| `raw/git-status.txt` | 未提交工作区状态与 HEAD |

## 复核命令

```bash
cd docs/audit/V2-A1-04-Batch-B-B1
sha256sum -c SHA256SUMS.txt
```

## 结论

B1 可提交独立代码审查；但 **B1 验收未完成**：真实 PostgreSQL、POSIX、真实跨卷、进程崩溃与 TOCTOU 窗口均未取证。任何“B1 通过 / Batch B 通过”的表述都不成立。