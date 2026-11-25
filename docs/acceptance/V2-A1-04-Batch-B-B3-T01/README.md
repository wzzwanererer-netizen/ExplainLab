# ExplainLab V2 · Batch B · B3-T01 验收材料

**状态：B3-T01 IMPLEMENTED（含独立审计整改）/ PENDING INDEPENDENT REVIEW**

本目录记录 B3-T01（Manifest Schema 与 Staging Service）的实现、首轮独立审计缺陷整改与真实运行证据。B3-T02、B4、B5 未实现，也不在本轮声明范围。

- 基线：`970c0d8ec05f0b8c68286839a56b14c74ea230c6`
- 分支：`fix/m0-admission-and-m5-regressions`
- 工作树包含此前未提交的 B1/B2 已验收实现；本轮只改 B3-T01 文件。
- 未提交、未推送。
- B3-T01 专项测试 54 passed；Backend + Core 全量 1450 passed / 213 skipped（skip 全部为 PostgreSQL 或平台门控）。
- Windows 真实 tmp 文件系统 + 真实 SQLite；无 mock FS/DB。

## 文档索引

| 文件 | 内容 |
|---|---|
| [B3-T01-implementation-report.md](B3-T01-implementation-report.md) | 初版实现范围、关键决策、运行结果 |
| [B3-T01-remediation-report.md](B3-T01-remediation-report.md) | **本轮审计整改**：P1-01/P1-02/P2-01/P2-02/P2-03 与 ZIP 边界 |
| [guard-lifetime-proof.md](guard-lifetime-proof.md) | P1-01 Staging Guard 生命周期与事务边界证明 |
| [posix-durability.md](posix-durability.md) | P1-02 目录级 fsync 顺序、失败语义、Windows 边界 |
| [empty-attachment-rejection.md](empty-attachment-rejection.md) | P2-01 零字节附件稳定拒绝 |
| [corrupt-zip-mapping.md](corrupt-zip-mapping.md) | P2-02 损坏 ZIP 异常到 400 的映射 |
| [pending-fail-closed.md](pending-fail-closed.md) | P2-03 Pending 查询 fail-closed |
| [file-change-list.md](file-change-list.md) | 新增/修改/未修改文件清单 |
| [manifest-field-mapping.md](manifest-field-mapping.md) | Manifest 字段与冻结设计逐项对应 |
| [zip-security.md](zip-security.md) | ZIP 路径、归属、压缩炸弹与有界读取 |
| [staging-lifecycle.md](staging-lifecycle.md) | `.creating/.activity/.complete` 与活动时间 |
| [data-flow-and-transactions.md](data-flow-and-transactions.md) | 数据流、锁序与事务边界 |
| [acceptance-mapping.md](acceptance-mapping.md) | IMP-19 / R1 / R1.1 / ATT / ORP 映射 |
| [test-evidence-index.md](test-evidence-index.md) | 测试与原始日志索引 |
| [ruff.md](ruff.md) | Ruff 原始结果 |
| [git-diff-summary.md](git-diff-summary.md) | Git 状态、B3 差异与禁止项核对 |
| [unresolved.md](unresolved.md) | 未解决、未验证与明确不做项 |
| [SOURCE-SHA256SUMS](SOURCE-SHA256SUMS) | B3 源码与测试 SHA-256 |
| [SHA256SUMS](SHA256SUMS) | 本目录全部文件 SHA-256 |

原始日志位于 [evidence/](evidence/)，本轮整改日志位于
[evidence/remediation/](evidence/remediation/)；独立审计材料位于
`docs/audit/V2-A1-04-Batch-B-B3-T01/`。