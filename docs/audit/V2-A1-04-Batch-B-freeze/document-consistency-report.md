# 冻结文档一致性核验

## 十份文件

| 文件 | 固化位置 |
|---|---|
| README.md | 正式状态、P1、关闭裁决、风险/验收数、冻结记录和 B1 交接 |
| architecture.md | §2/§4.2 的事务所有者、①/② 分界 |
| storage-and-lock-contract.md | §3/§6.1 的 F12 分类、no-clobber、锁内由外层提交 |
| attachment-lifecycle.md | §2.3/§5.2 的上传与删除事务、Repository flush |
| active-review-integration.md | §2/§5.2/§7 的 approve 两事务与 reject 提交所有者 |
| gc-and-orphan-recovery.md | §3 的认领短事务与外层提交责任 |
| api-contracts.md | §2.3 F12 既有错误映射、§6 F13 路由事务责任 |
| implementation-roadmap.md | §3 开发准入、B2/B4 事务同步、结束状态 |
| acceptance-plan.md | 53 条编号、名称和顺序保持；在旧条目补 F12/F13 断言 |
| risk-register.md | 50 条编号、名称和顺序保持；F12/F13 处置引用 |

## 冲突及收口

- **F12**：旧 storage §6 把所有 `OSError` 归为不支持，与错误分支和 no-clobber 保护相冲突。按最终裁决改为具体原因分类，同步存储步骤、API、路线图和 ATT-12。
- **F13**：旧生命周期伪代码、B2 上传箭头只写 commit，容易被读成服务提交。按最终裁决显式标注外层 Unit of Work、Repository flush 和两次提交边界。
- 十份文件均标识 Architecture Freeze Approved。P1 的八项编号保持关闭。既有错误码登记原文未变化；验收 53、风险 50 的编号、名称和顺序逐项比对。无新增架构决策。
- 本轮执行文件与静态一致性检查；真实 SQLite/PostgreSQL、Windows/POSIX 和故障注入属于实现验收。未修改业务代码、测试、迁移、依赖和里程碑。

## Git 只读核验

- 分支 `fix/m0-admission-and-m5-regressions`；HEAD `970c0d8ec05f0b8c68286839a56b14c74ea230c6`。
- 固化前与固化后，跟踪文件和暂存区 diff 均为空。十份冻结设计原来就未跟踪，本轮仍未跟踪。除本次冻结目录外，原有未跟踪路径集合保持一致。
- 对最终复审包中的十份原件校验后才固化。哈希清单记录冻后十份设计和四份交付文档，清单自身不列入。

固化前 `git status --short`：

~~~text
?? docs/acceptance/V2-A1-04-Batch-A/audit-round2/
?? docs/acceptance/V2-A1-04-Batch-A/final-remediation/final-review/
?? docs/audit/V2-A1-03-final-stage-audit/
?? docs/audit/V2-A1-04-Batch-A-format-check-report.md
?? docs/audit/V2-A1-04-Batch-B-final-review.zip
?? docs/audit/V2-A1-04-Batch-B-final-review/
?? docs/audit/V2-A1-04-Batch-B-freeze-review-package.zip
?? docs/audit/V2-A1-04-Batch-B-freeze-review-package/
?? docs/audit/V2-A1-04-Batch-B-preflight/
?? docs/audit/V2-A1-04-Batch-B-remediation-review.zip
?? docs/audit/V2-A1-04-Batch-B-remediation/
?? docs/audit/V2-A1-04-R1-independent-review.md
?? docs/audit/V2-A1-04-technical-verification.md
?? docs/plans/A1-04/
?? docs/plans/V2-A1-04-Batch-B/
~~~

固化后预期仅增加 `?? docs/audit/V2-A1-04-Batch-B-freeze/`；逐文件 Git 状态核验在生成清单后执行。
