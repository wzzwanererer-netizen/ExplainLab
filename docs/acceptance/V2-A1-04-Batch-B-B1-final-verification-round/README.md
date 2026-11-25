# ExplainLab B1 · Final Verification Round

**2026-11-23（北京时间）｜本轮建议 `CONDITIONAL`，待 ChatGPT 最终独立裁决。** T01、T04、LCK-07 的定点实机用例均为 `PASS`。正式阶段状态沿用进入本轮时的 `BLOCKED`，直至独立裁决。

| 交付项 | 当前状态 | 验收结果 |
| --- | --- | --- |
| [T01 Windows 路径安全](T01-Windows.md) | PASS | 普通 PowerShell 4 通过、0 跳过，覆盖 3 个真实 junction 入口和 C/D 分卷。Linux 应用 ext4/tmpfs 同卷检查另有 1 通过 |
| [T04 真实 PG Repository](T04-PostgreSQL.md) | PASS | PostgreSQL 18.6，13 通过，0 跳过 |
| [LCK-07 真实 PG 客户端退出](LCK-07-PostgreSQL.md) | PASS | 1 通过，0 跳过。PG 锁回归另有 13 通过 |
| Windows B1 相关回归 | PASS | 默认临时目录 175 通过、5 跳过、5 未选中，受管 D 盘首轮失败另有记录 |
| Backend/Core Ruff | PASS | `ruff check backend knowledge-core` 退出 0 |

**PASS** 表示相应定点项目有真实执行及通过证据。**CONDITIONAL** 是本轮的验收建议，指定补测已完成，正式验收待独立审核确认。**BLOCKED** 是正式流程状态，B2 准入仍待授权。53 项矩阵计 32 项 B1 子项已验证、21 项按原冻结阶段取证。

## 回归证据

首次受管 Windows 回归使用 D 盘项目内的 pytest 临时目录，146 通过、29 失败、5 跳过。多数失败是受管路径上的真实文件操作返回拒绝访问。另有一项既有 SQLite GC 排序断言失败。控制探针确认两条记录的 `created_at` 相等时，仓储按 UUID 第二排序，结果可能与插入顺序相反。原失败日志未采集时间戳。恢复默认测试临时目录后，原测试未经改动，同组回归为 175 通过、5 跳过。更早的直接 pytest 入口未完成，后续受管运行使用既有 Proactor 轮询 launcher。

[最终 Windows 回归](evidence/windows-managed-165fd27e999e/b1-windows-regression.log) · [JUnit](evidence/windows-managed-165fd27e999e/b1-windows-regression.xml) · [初次 D 盘回归](evidence/windows-managed-c896cc7ea6d2/b1-windows-regression.log) · [初次 JUnit](evidence/windows-managed-c896cc7ea6d2/b1-windows-regression.xml) · [GC 排序诊断](evidence/gc-order-diagnostic.log) · [Backend/Core Ruff](evidence/windows-managed-165fd27e999e/ruff-backend-core.log)

历史全仓 Ruff 留有 5 项错误，均来自旧审计包的 `0006_v2_markdown_kb.py` 迁移副本。本轮只跑 Backend/Core Ruff。[全仓 Ruff 历史原始证据](../V2-A1-04-Batch-B-B1-remediation-round3/evidence/ruff-repo.txt) · [历史 Windows launcher](../V2-A1-04-Batch-B-B1-remediation-round3/evidence/pytest-windows-event-loop.py.txt)

[更新后的 53 项矩阵](../V2-A1-04-Batch-B-B1-environment-recovery/acceptance-matrix.md) · [环境恢复](../V2-A1-04-Batch-B-B1-environment-recovery/environment-recovery.md) · [未解决问题](../V2-A1-04-Batch-B-B1-environment-recovery/unresolved.md) · [Git 状态](git-state.md) · [SHA-256SUMS](SHA256SUMS)

请独立审核者依据冻结 B1-T01～T04，核对实际路径、真实事务、客户端退出、矩阵范围和上述证据边界，给出正式 B1 裁决。校验清单中的路径相对解压包根目录。
