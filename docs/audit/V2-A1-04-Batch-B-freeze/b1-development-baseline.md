# Qoder B1 开发交接基线

**准入状态：Architecture Freeze Approved。B1 实现及取证尚未开始。**

以 `970c0d8ec05f0b8c68286839a56b14c74ea230c6` 的 Batch A 和 [冻结十份设计](../../plans/V2-A1-04-Batch-B/README.md) 为输入。十份文件在本轮尚未跟踪，交接时应让 Qoder 读取本工作区的文件，或给它同一冻结快照；单独检出该 commit 不会带上 Batch B 文件。可用 [SHA-256SUMS](SHA-256SUMS) 在仓库根核对。

| B1 任务 | 输出 | 准入与验收 |
|---|---|---|
| B1-T01 | 配置、启动阶段路径、根目录、同卷与链接校验 | ATT-01/06、ORP-02、R1.1-IMP-42 的隔离前置；不启动 worker |
| B1-T02 | 内容寻址、Hash、同句柄读取、原子 no-clobber 发布及存储辅助 | ATT-01/02/06/09/10/12、ORP-02 的存储部分，按 F12 分支取证 |
| B1-T03 | SQLite/PG StorageKeyLock，与启动方言装配 | LCK-01～10；真实 SQLite 与 PostgreSQL，包含断连、实际锁身份碰撞和 token fencing |
| B1-T04 | SQLAlchemy AttachmentRepository 与 GcTaskRepository | ATT-08/11、GC-01/02/09/10/12 的仓库与 fencing 部分；F13 外层事务协调 |

每个任务的设计章节、文件范围、实现要求、单元测试、故障注入、验收映射和完成判定在 [implementation-roadmap.md §3](../../plans/V2-A1-04-Batch-B/implementation-roadmap.md)。按路线图 §10 留证。真实 PostgreSQL 用 `EXPLAINLAB_PG_TEST_URL` 配置；缺真实 PG 则 B1 验收阻塞。相关 HTTP、审核与 worker 的端到端证据在原阶段补齐。

B1 边界止于存储、锁、配置和仓库，之后按路线图交接。实现若与冻结约定冲突，先记录差异并走正式审批。
