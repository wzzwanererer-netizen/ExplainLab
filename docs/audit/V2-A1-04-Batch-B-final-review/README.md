# ExplainLab Batch B Architecture Freeze 最终独立技术审计

**裁决建议 C · BLOCKED。当前候选不宜冻结，Qoder B1 暂缓，等待 ChatGPT 审核。** PostgreSQL 多 key 锁管理、Active approve 对归档的状态判断、ZIP 多文档的附件归属、staging 清理与 GC 恢复存在可复现的设计缺口。修正范围限于现有 Batch B 契约。

| 项目 | 审计依据 |
|---|---|
| 基线 | 当前 HEAD 与指定提交 `970c0d8ec05f0b8c68286839a56b14c74ea230c6` 一致。开始审计时对 HEAD 的跟踪文件 diff 为空。 |
| 候选 | 逐份阅读 `docs/plans/V2-A1-04-Batch-B/` 的 README、architecture、storage-and-lock-contract、attachment-lifecycle、active-review-integration、gc-and-orphan-recovery、api-contracts、implementation-roadmap、acceptance-plan、risk-register。十份文件均为审计开始前已存在的未跟踪文件。 |
| 冻结依据 | R1.3 implementation-plan §7、§12、§21、§22，open-decisions §L，acceptance-matrix R1/R1.1/R1.3 相关条目。 |
| 现有实现 | 对照治理路由、Markdown 导入路由与服务、附件审核 Hook、Core ReviewService/ImportEnvelope/ports、身份恢复与 ProcessLock 启动路径、ORM、0006 迁移、SQLite 连接配置及 Batch A 的附件兼容测试。 |
| 方法 | Git 状态与基线比较、代码检索、验收编号计数、事务与故障时序静态推演。 |
| 证据限制 | Batch B 53 个验收编号全部待验证。没有运行 SQLite/PG 集成、Windows/POSIX 文件系统专项或进程故障注入，也没有启动服务、迁移或 B1。 |

## 证据归类

- **当前代码证明**：0006/ORM 具备附件、GC 与锁行的基本字段。Approve 确实先提交业务、再提交索引。Core approve 先更新审核状态并应用 payload，Hook 在其后执行。S0 会话在返回前关闭。身份 guard 进入时先执行恢复，必要时可在内部短事务写 DB 并提交。ZIP 批量与单篇共用收集入口，现有 Batch A 批量对 JSON 附件逐篇报告 unsupported。
- **设计合理、待实现**：按内容寻址共享、独立引用、no-clobber 发布、pending 阶段零正式引用、两次提交的职责分离、reject 后尽力清理、下载同句柄、防止仅凭 PG 行 TTL 接管。
- **必须实测**：SQLite 锁行与业务事务竞争、PG 专用会话及连接数、NTFS/Windows 占用、POSIX 发布与目录持久化、服务退出、故障时序及 GC/ORP 恢复。文件系统语义以 Batch B 验收证据为准。
- **设计缺陷**：见下列报告。P1 表示能导致实质错误、数据/恢复风险或冻结后返工。P2/P3 为明确的非阻塞修订。没有认定 P0，也没有把设计反例写成已运行的失败用例。

## 报告

- [架构缺陷与风险](architecture-findings.md)
- [B1–B6 可实施性](implementation-readiness.md)
- [验收覆盖缺口](acceptance-gaps.md)
- [最终冻结建议](freeze-recommendation.md)
