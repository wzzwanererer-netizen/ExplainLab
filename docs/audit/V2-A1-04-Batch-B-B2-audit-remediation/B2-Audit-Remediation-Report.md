# ExplainLab B2 · 独立审核整改与最终验收准备

**处于 B2 Audit Remediation，等待 ChatGPT 再次独立复审。** 原始裁决为 `CONDITIONAL PASS`，正式批准暂缓。

- **B2-AUDIT-01**。真实路由与生产发布路径执行完毕。Windows 的 link 和 rename 底层 I/O 故障注入分别通过，HTTP 503、稳定错误码和库盘零残留均有断言。
- **B2-AUDIT-02**。受管环境曾记录 `BLOCKED / ENVIRONMENT UNAVAILABLE`。随后普通 PowerShell 完成真实 PostgreSQL 18.6 补测，HTTP 5 项与 PG 锁及仓储回归 18 项通过。运行结束查询到 0 个已授予 advisory lock。[PostgreSQL HTTP 验收](PostgreSQL-HTTP.md)
- **审核基线**。原版 [ExplainLab-B2-Audit-Package.zip](../V2-A1-04-Batch-B-B2/ExplainLab-B2-Audit-Package.zip) 已校验内部清单。新增内容限于 B2 HTTP 验收测试、执行入口和审核证据。B1 实现及测试、B2 生产实现、冻结设计、Knowledge Core、迁移和依赖清单保持原样。

[ATT-12 证据](ATT-12-evidence.md) · [ATT-01～13 映射](acceptance-mapping.md) · [Git 摘要](Git-change-summary.md) · [源码 SHA-256](SOURCE-SHA256SUMS) · [审核包清单](SHA256SUMS)

## 回归和退出码

每条命令及 UTC 起止时间保存在原始日志，JUnit 中保留逐项状态。Windows 使用历史受管会话的 Proactor 轮询入口。

| 范围 | 通过 | 跳过 | 失败 | 退出码 |
| --- | ---: | ---: | ---: | ---: |
| [ATT-12 Windows](evidence/att12-windows.log) | 2 | 0 | 0 | 0 |
| [B2 API Windows](evidence/b2-api-windows.log) | 24 | 5 | 0 | 0 |
| [B1 附件、锁、GC Windows](evidence/b1-targeted-windows.log) | 175 | 37 | 0 | 0 |
| [Backend + Knowledge Core 根级全量](evidence/backend-core-full-windows.log) | 1,389 | 220 | 0 | 0 |
| [ATT-12 WSL ext4](evidence/pg-http.V7CaM83E/att12-posix.log) | 1 | 1（Windows rename） | 0 | 0 |
| [PostgreSQL HTTP WSL 实机](evidence/pg-http.V7CaM83E/postgresql-http.log) | 5 | 0 | 0 | 0 |
| [PostgreSQL 锁及仓储 WSL 回归](evidence/pg-http.V7CaM83E/postgresql-advisory.log) | 18 | 0 | 0 | 0 |
| [Backend/Core Ruff](evidence/ruff-backend-core.log) | 通过 | — | 0 | 0 |
| [全仓 Ruff](evidence/ruff-repository.log) | — | — | 历史归档 8 项 | 1 |

B1 定点的 37 项跳过包括 27 项真实 PG 门控和 10 项 Windows 权限或平台能力门控。全量的 220 项跳过包括 210 项真实 PG 门控和相同的 10 项平台或权限门控。全仓 Ruff 的 8 项均来自旧迁移审计副本和 B1 取证脚本。[跳过明细](evidence/skip-reasons.txt)

本报告只提交 B2 审核整改证据。ATT-11 的 24h ORP 收敛继续归 B5，B2 正式裁决等待独立复审。
