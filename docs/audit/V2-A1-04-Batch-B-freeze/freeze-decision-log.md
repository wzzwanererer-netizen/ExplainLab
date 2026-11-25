# Batch B 最终冻结裁决台账

最终独立复审裁决确认 F01–F08 的整改通过静态复审。下表保留原编号，运行期证据在冻结的验收矩阵中取得。

| 原编号 | 冻结口径 | 现有取证入口 |
|---|---|---|
| F01 | 附件写前保护 archived 状态。PG 行锁、SQLite 条件写前置，approve 在 Core 改写前检查。 | ATT-13、IMP-19、R1.1-IMP-38 |
| F02 | 含附件 ZIP 限单篇，严格归属，同来源重试对照逻辑附件集合。批量 JSON 沿用逐篇行为。 | IMP-19、R1-IMP-05/14/37 |
| F03 | staging 创建、提交、清扫与恢复持同 staging_id guard；先复查 pending。 | R1.1-IMP-41/42、R1-IMP-10/11 |
| F04 | 同 review_id 的 approve/reject 决议串行。不可证实 staging 归属时仍允许 reject，清理交 ORP。 | R1-IMP-08/10/11/14/37 |
| F05 | GC 隔离槽与新正式文件代次分开管理。崩溃恢复重新核验引用、Hash 和隔离期。 | GC-02～10、ORP-04/05/06 |
| F06 | PG 单 guard 单专用物理会话；按实际 advisory 身份去重排序，完整 key 保留独立 token；断连失效。 | LCK-02/03/06/10 |
| F07 | D23 恢复与内部事务完成后取锁。物理预发布早于 S1 写，业务①与索引②分开。 | LCK-04/05/07/08、R1-IMP-08/09 |
| F08 | 启动和运行时校验目录身份、隔离、链接/重解析点及同卷，异常保留源目录。 | ATT-01/06/12、ORP-02、R1.1-IMP-42 |

## F12 与 F13

- **F12**。目标已存在须校验原文件大小与 SHA-256；跨卷直接报错；Windows sharing/lock violation 按既定退避重试；权限拒绝直接失败；未知 I/O 失败不降级。只有明确不支持 hard link 才可用 Windows 同卷 no-clobber rename，目标已存在时绝不覆盖。POSIX 保持原失败路径。规范见 storage §3.1/§6.1，验收见 ATT-12。
- **F13**。附件服务和 Hook 编排操作，Repository 读写与 flush，外层 Unit of Work 独占 commit/rollback，避免隐式或重复提交。Active approve 的业务①和索引②各有单独边界，②异常只回滚②。规范见 architecture §2/§4.2、review §2/§5.2 和 lifecycle §2.3/§5.2，执行见 roadmap B1-T04、B2-T02 和 B4。

D-B01～D-B16、O-B01～O-B11 的关闭结果以冻结 README 为索引。A1-02 Hash、A1-03 LinkKeyRebuild、D22–D24、身份 Journal、Batch A 冻结实现、schema 与依赖沿用原基线。本轮未登记新架构裁决。

[原始审计](../V2-A1-04-Batch-B-final-review/architecture-findings.md) · [整改证据](../V2-A1-04-Batch-B-remediation/remediation-report.md) · [验收映射](../V2-A1-04-Batch-B-remediation/updated-acceptance-mapping.md)
