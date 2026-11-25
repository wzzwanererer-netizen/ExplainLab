# ExplainLab Batch B Architecture Freeze 最终独立复审材料

基线：`970c0d8ec05f0b8c68286839a56b14c74ea230c6`。包中 Batch B 原文来自创建前的当前工作区。R1.3 与源码取自基线提交。原审计及整改目录按原文件归档。

| 内容 | 入口 |
|---|---|
| 十份当前设计 | [Batch B README](design-documents/docs/plans/V2-A1-04-Batch-B/README.md) |
| Batch A R1.3 与 D22–D24 | [R1.3 索引](design-documents/batch-a-r1.3/docs/plans/README-A1-04-R1.3.md) · [设计 §22](design-documents/batch-a-r1.3/docs/plans/V2-A1-04-implementation-plan.md) · [决策 §L](design-documents/batch-a-r1.3/docs/plans/V2-A1-04-open-decisions.md) |
| 八项 P1 | [原始发现](original-audit/docs/audit/V2-A1-04-Batch-B-final-review/architecture-findings.md) · [整改报告](remediation/docs/audit/V2-A1-04-Batch-B-remediation/remediation-report.md) |
| 重点证据 | [PG](source-evidence/01-postgresql-advisory-lock.md) · [SQLite](source-evidence/02-sqlite-review-sequence.md) · [Staging](source-evidence/03-staging-lock-boundaries.md) · [Windows](source-evidence/04-windows-roots-and-toctou.md) |
| 验收与风险 | [验收与风险索引](acceptance-and-risks/coverage-and-residuals.md) · [错误码](acceptance-and-risks/stable-error-code-register.md) |
| 完整性 | [清单](manifest.md) · [SHA-256](SHA-256SUMS) · [Git 状态](git-state.md) |

原件按类别保存原仓库相对路径。少数原文的跨目录链接仍以仓库根布局为前提，可经本页定位归档副本。

## 缺失和取证边界

- 所称 39 个错误码的独立清单未取得。可验证的旧登记有 47 个、当前有 48 个，均按原顺序附上。
- 四项重点均有设计原文和对应基线源码。Batch B 新能力未取得实现源码或运行证据。53 项验收仍待执行。本轮未运行数据库、故障注入或平台文件系统试验。
- 本包用于独立复审，Architecture Freeze 与 Qoder B1 仍等待签发。
