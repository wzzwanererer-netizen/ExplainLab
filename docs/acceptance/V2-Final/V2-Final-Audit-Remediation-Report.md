# ExplainLab V2 · Final Audit Remediation

**V2 IMPLEMENTED / PENDING FINAL INDEPENDENT REVIEW**

本轮基线为原独立审计 ZIP，SHA-256 为 `c05513582474020b856c98822e7f59d74792edc2094d5e031f0381fa6e76cc65`。按原包逐字节复核，整改范围为治理路由、索引日志脱敏、staging keyed lock 和三份测试文件。

## P1-01 与 P2

业务事务完成后，审批、草稿直办和版本恢复统一在独立 Session 同步索引。业务响应依据已提交结果。索引提交或调用失败记录稳定警告和异常类型。Staging keyed lock 的持有者和等待者从尝试进入注册表时计数，最后一人退出才回收条目。生产者、等待者、第三次竞争和 Sweep 的实际交错已复验。 [P1 说明](P1-01-Review-Index-Remediation.md)

## 六项验收补充

| 项目 | 核验 |
| --- | --- |
| GC-02 | 两个 task 和两个 Worker 竞争一个物理 key，隔离槽与代次等待期独立，最后均收敛。 |
| ORP-01 | 真实 HTTP 提交干预产生物理孤儿，同一次用例贯穿扫描、入队、隔离和清除。 |
| ORP-05 | 子进程在接收任务前后、槽转移前后和引用恢复中退出，重启验证新代次和不可信文件保留。 |
| ORP-07 | 同一次扫描的原始 JSON 同时呈现缺失、孤儿和哈希不符，不损坏引用与文件。 |
| R1.1-IMP-38 | 列出附件、标签、来源、链接和发布后归档的五个独立 PG 用例，状态以实际记录为准。 |
| R1.1-IMP-42 | Sweep 的活动时间最大值、空目录、链接安全、生产竞争、待审批回升、隔离恢复和正式根隔离。 |

| 复验 | 通过 | 失败 | 错误 | 跳过 | 证据 |
| --- | ---: | ---: | ---: | ---: | --- |
| P1 与日志隔离 | 13 | 0 | 0 | 0 | [日志](evidence/remediation-windows-logging-isolation.log) · [JUnit](evidence/remediation-windows-logging-isolation.xml) |
| GC 与 ORP 专项 | 8 | 0 | 0 | 0 | [日志](evidence/remediation-windows-gc-trace.log) · [JUnit](evidence/remediation-windows-gc-trace.xml) |
| Windows 受管附件回归 | 288 | 0 | 0 | 20 | [日志](evidence/remediation-windows-special.log) · [JUnit](evidence/remediation-windows-special.xml) |
| Windows 受管 Sweep | 7 | 0 | 0 | 1 | [日志](evidence/remediation-windows-sweep-managed.log) · [JUnit](evidence/remediation-windows-sweep-managed.xml) |
| Backend + Knowledge Core 根级回归 | 1504 | 0 | 0 | 230 | [日志](evidence/remediation-windows-full-final.log) · [JUnit](evidence/remediation-windows-full-final.xml) |
| 普通权限 Windows Sweep | 8 | 0 | 0 | 0 | [日志](evidence/remediation-windows-normal-cbd2945355bf/staging-sweep.log) · [JUnit](evidence/remediation-windows-normal-cbd2945355bf/staging-sweep.xml) |
| 普通权限 Windows 真实启动路径 | 4 | 0 | 0 | 0 | [日志](evidence/remediation-windows-normal-cbd2945355bf/t01-windows.log) · [JUnit](evidence/remediation-windows-normal-cbd2945355bf/t01-windows.xml) |
| Ubuntu / PostgreSQL final-pg-api | 5 | 0 | 0 | 0 | [日志](evidence/remediation-posix-pg.3XoAQbf0/final-pg-api.log) · [JUnit](evidence/remediation-posix-pg.3XoAQbf0/final-pg-api.xml) |
| Ubuntu / PostgreSQL final-pg-draft | 1 | 0 | 0 | 0 | [日志](evidence/remediation-posix-pg.3XoAQbf0/final-pg-draft.log) · [JUnit](evidence/remediation-posix-pg.3XoAQbf0/final-pg-draft.xml) |
| Ubuntu / PostgreSQL final-pg-e2e | 1 | 0 | 0 | 0 | [日志](evidence/remediation-posix-pg.3XoAQbf0/final-pg-e2e.log) · [JUnit](evidence/remediation-posix-pg.3XoAQbf0/final-pg-e2e.xml) |
| Ubuntu / PostgreSQL final-pg-regression | 205 | 0 | 0 | 0 | [日志](evidence/remediation-posix-pg.3XoAQbf0/final-pg-regression.log) · [JUnit](evidence/remediation-posix-pg.3XoAQbf0/final-pg-regression.xml) |
| Ubuntu / PostgreSQL final-pg-review | 6 | 0 | 0 | 0 | [日志](evidence/remediation-posix-pg.3XoAQbf0/final-pg-review.log) · [JUnit](evidence/remediation-posix-pg.3XoAQbf0/final-pg-review.xml) |
| Ubuntu / PostgreSQL final-posix | 218 | 0 | 0 | 2 | [日志](evidence/remediation-posix-pg.3XoAQbf0/final-posix.log) · [JUnit](evidence/remediation-posix-pg.3XoAQbf0/final-posix.xml) |

[PostgreSQL 集成终态](evidence/remediation-posix-pg.3XoAQbf0/db-after-e2e.log)

## 证据边界

- 六项补验均有对应实机证据，最终裁决由独立审计负责。
- Backend + Knowledge Core 源码 Ruff 和 Git diff --check 通过。仓库根 Ruff 仍记录 8 项历史归档错误。
- 初始根级运行曾暴露 Alembic 关闭预先载入 logger 的测试间干扰。日志验证夹具恢复所需 logger，正式迁移和历史失败日志保持原样。
- 24 小时边界以真实库时间和磁盘 mtime 控制验证。

[53 项矩阵](Acceptance-Matrix.md) · [Git 基线差异](evidence/remediation-from-audit.patch) · [基线核验](evidence/remediation-baseline-current.log) · [Git 状态](evidence/remediation-git-state.log) · [质量门](evidence/remediation-quality.log) · [复审包 SHA-256 清单](Remediation-SHA256SUMS)
