# 整改验收映射

53 个编号与原候选顺序、集合一致。所有条目 **待验证**。子场景并入既有编号，继承项只做映射。

| 审计项 | 既有验收 | 必须观察的结果 |
|---|---|---|
| F06 · PostgreSQL advisory 锁 | LCK-02/03/06/10，继承 R1-LOCK-08 | 连接建立 → 获取唯一锁 → token 短事务 → guard 有效 → unlock/关闭。部分失败撤销；断连旧 guard 不复活；新 owner 要完成 token 提交才能动文件。 |
| F07 · SQLite 文件与业务事务 | LCK-04/05/07/08，R1-IMP-08/09，横切 §8.1 | 恢复→取锁→预发布→S1→fencing→①。预发布失败无业务写，①失败 rollback 后释放且保留原件，已发布未引用交 ORP。 |
| F08 · 目录隔离 | ATT-01/06/12，ORP-02，R1.1-IMP-42 | 部署启动验证→操作前复核；根重叠拒绝启动，运行期链接/越界/跨卷保留源并报告。 |
| F01 · 归档竞争 | ATT-13，IMP-19，R1.1-IMP-38 | 归档先提交：拒绝并保留 archived、零新引用。新增先提交：后续归档保留引用。预发布留下的孤儿由 ORP 回收。 |
| F02 · ZIP 归属和幂等 | IMP-19，R1-IMP-05/14/37，继承 R1-IMP-07 | 合法请求→已满足 SKIPPED / 相等 REUSED_PENDING / 新 pending 或 Draft。归属歧义、集合冲突、缺文件和 Active 附件-only 各有稳定失败，原 pending 保全。 |
| F03 · staging 写入与清扫 | R1.1-IMP-41/42，R1-IMP-10/11，ORP-05 | 创建→完成→pending 或正常清理；孤儿→隔离→等待→清除；看到 pending 恢复或保留，损坏归属 fail-closed。 |
| F04 · 审核决议竞争 | R1-IMP-08/10/11/14/37，横切 §8.1 | PENDING→APPROVED 或 REJECTED，仅一个终态；后到者既有 409，失败回滚维持 pending，不提前清理。 |
| F05 · GC 重复任务与物理代次 | GC-02–10，ORP-04/05/06，继承 R1-LOCK-07 | 隔离后缺记录重新等待 24h；旧槽 purge 后崩溃可完成并交接新正式代次。引用回升校验并恢复；坏 Hash、无安全证据保留现场。 |

## 继承验收

- **R1-IMP-07 → IMP-19 / R1-IMP-05**：同来源不同文档 Hash 或附件集合冲突时原 pending/manifest/staging 保持。
- **R1-LOCK-07 → ATT-10 / ORP-06**：在发布后和业务提交前触发 GC/ORP，进一步验证持锁复查。
- **R1-LOCK-08 → LCK-10**：真实 PostgreSQL 双连接；同投影碰撞、跨批顺序、百 key 单专用会话、部分失败与断连均须取证。
- **D22/D23 → B4-T02 与横切 §8.1/8.5**：既有 Batch A 回归，含合法 PREPARED MATERIALIZE 的恢复先截止再进入附件锁；**D24 → Batch D**。

取证使用真实 SQLite 文件库、PostgreSQL、Windows/NTFS 和 POSIX。Windows 占用/重解析点、POSIX 文件发布与目录同步以及进程 kill 按对应平台验收。注入可控制时序，不代表真实环境已经通过。
