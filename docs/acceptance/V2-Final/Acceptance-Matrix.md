# ExplainLab V2 · 53 项验收映射

编号与顺序沿用冻结验收计划。PASS 表示有实机或已批准阶段证据，PARTIAL 表示指定子场景或第二平台证据待补。最终裁决由独立审计负责。 [冻结验收计划](../../plans/V2-A1-04-Batch-B/acceptance-plan.md)

| 编号 | 验收项 | 证据状态 | 观测及证据 |
| --- | --- | --- | --- |
| ATT-01 | 合法 PNG/PDF/TXT（≤10 MiB，白名单） | PASS | 已批准，最终 Windows 与 PostgreSQL HTTP 复验。 [B2 批准依据与整改映射](../../audit/V2-A1-04-Batch-B-B2-audit-remediation/acceptance-mapping.md) |
| ATT-02 | 相同内容上传到两个 item | PASS | 已批准，最终 Windows 与 PostgreSQL HTTP 复验。 [B2 批准依据与整改映射](../../audit/V2-A1-04-Batch-B-B2-audit-remediation/acceptance-mapping.md) |
| ATT-03 | >10 MiB 文件；非法 Base64 | PASS | 已批准，最终 Windows 与 PostgreSQL HTTP 复验。 [B2 批准依据与整改映射](../../audit/V2-A1-04-Batch-B-B2-audit-remediation/acceptance-mapping.md) |
| ATT-04 | 声明 `image/png`，实际 JPEG/文本；或声明 `text/plain`，实际 PNG；文本子类型交叉（TXT/MD/CSV） | PASS | 已批准，最终 Windows 与 PostgreSQL HTTP 复验。 [B2 批准依据与整改映射](../../audit/V2-A1-04-Batch-B-B2-audit-remediation/acceptance-mapping.md) |
| ATT-05 | 声明 `image/svg+xml`；另以文本 MIME 提供合法 UTF-8 SVG 字符串 | PASS | 已批准，最终 Windows 与 PostgreSQL HTTP 复验。 [B2 批准依据与整改映射](../../audit/V2-A1-04-Batch-B-B2-audit-remediation/acceptance-mapping.md) |
| ATT-06 | 文件名 `../../evil.png`、`C:\x.png`、含 CR/LF/控制字符 | PASS | 已批准，最终 Windows 与 PostgreSQL HTTP 复验。 [B2 批准依据与整改映射](../../audit/V2-A1-04-Batch-B-B2-audit-remediation/acceptance-mapping.md) |
| ATT-07 | 正常下载；跨 item 猜测 id；用户传路径 | PASS | 已批准，最终 Windows 与 PostgreSQL HTTP 复验。 [B2 批准依据与整改映射](../../audit/V2-A1-04-Batch-B-B2-audit-remediation/acceptance-mapping.md) |
| ATT-08 | 删除引用（独享/共享） | PASS | 已批准，最终 Windows 与 PostgreSQL HTTP 复验。 [B2 批准依据与整改映射](../../audit/V2-A1-04-Batch-B-B2-audit-remediation/acceptance-mapping.md) |
| ATT-09 | 上传后篡改物理字节；上传后重算；校验后路径替换 | PASS | 已批准，最终 Windows 与 PostgreSQL HTTP 复验。 [B2 批准依据与整改映射](../../audit/V2-A1-04-Batch-B-B2-audit-remediation/acceptance-mapping.md) |
| ATT-10 | 两请求并发上传同内容 | PASS | 已批准，最终 Windows 与 PostgreSQL HTTP 复验。 [B2 批准依据与整改映射](../../audit/V2-A1-04-Batch-B-B2-audit-remediation/acceptance-mapping.md) |
| ATT-11 | 发布成功后 DB commit 失败 | PASS | 已批准，最终 Windows 与 PostgreSQL HTTP 复验。 [B2 批准依据与整改映射](../../audit/V2-A1-04-Batch-B-B2-audit-remediation/acceptance-mapping.md) |
| ATT-12 | 发布 rename/link 失败 | PASS | 已批准，最终 Windows 与 PostgreSQL HTTP 复验。 [B2 批准依据与整改映射](../../audit/V2-A1-04-Batch-B-B2-audit-remediation/acceptance-mapping.md) |
| ATT-13 | 元数据列表 + archived 策略（O-B04/O-B06） | PASS | 已批准，最终 Windows 与 PostgreSQL HTTP 复验。 [B2 批准依据与整改映射](../../audit/V2-A1-04-Batch-B-B2-audit-remediation/acceptance-mapping.md) |
| LCK-01 | 新 key acquire | PASS | 已批准，最终真实 PostgreSQL 锁回归及 Windows 受管回归。 [B1 最终证据](../V2-A1-04-Batch-B-B1-final-verification-round/README.md) |
| LCK-02 | 两 owner 同 key | PASS | 已批准，最终真实 PostgreSQL 锁回归及 Windows 受管回归。 [B1 最终证据](../V2-A1-04-Batch-B-B1-final-verification-round/README.md) |
| LCK-03 | 租约过期后接管 | PASS | 已批准，最终真实 PostgreSQL 锁回归及 Windows 受管回归。 [B1 最终证据](../V2-A1-04-Batch-B-B1-final-verification-round/README.md) |
| LCK-04 | renew 匹配 | PASS | 已批准，最终真实 PostgreSQL 锁回归及 Windows 受管回归。 [B1 最终证据](../V2-A1-04-Batch-B-B1-final-verification-round/README.md) |
| LCK-05 | renew 失配（旧 token/被接管） | PASS | 已批准，最终真实 PostgreSQL 锁回归及 Windows 受管回归。 [B1 最终证据](../V2-A1-04-Batch-B-B1-final-verification-round/README.md) |
| LCK-06 | release 匹配/失配 | PASS | 已批准，最终真实 PostgreSQL 锁回归及 Windows 受管回归。 [B1 最终证据](../V2-A1-04-Batch-B-B1-final-verification-round/README.md) |
| LCK-07 | 持锁进程崩溃 | PASS | 已批准，最终真实 PostgreSQL 锁回归及 Windows 受管回归。 [B1 最终证据](../V2-A1-04-Batch-B-B1-final-verification-round/README.md) |
| LCK-08 | 锁与物理间隙 TOCTOU | PASS | 已批准，最终真实 PostgreSQL 锁回归及 Windows 受管回归。 [B1 最终证据](../V2-A1-04-Batch-B-B1-final-verification-round/README.md) |
| LCK-09 | 严格互斥降级（D-04） | PASS | 已批准，最终真实 PostgreSQL 锁回归及 Windows 受管回归。 [B1 最终证据](../V2-A1-04-Batch-B-B1-final-verification-round/README.md) |
| LCK-10 | PG 行 TTL 过期但 advisory 仍存活（O-B03/D-B02） | PASS | 已批准，最终真实 PostgreSQL 锁回归及 Windows 受管回归。 [B1 最终证据](../V2-A1-04-Batch-B-B1-final-verification-round/README.md) |
| GC-01 | enqueue pending + worker 认领 | PASS | 最后引用入队、任务认领、token 和 attempts，SQLite 与 PostgreSQL。 [B5 实施报告](B5-Implementation.md) |
| GC-02 | 双 Worker 同 task | PASS | 两个不同任务由两个 Worker 竞争同一真实 StorageKeyLock。各自槽位独立，旧代次清除后新代次另行等待 24 小时，最终两任务均收敛。 [Windows SQL 与文件系统专项](evidence/remediation-windows-gc-trace.log) |
| GC-03 | 持锁复核引用>0 | PASS | 共享引用保留正式文件，隔离候选有引用时恢复。 [B5 实施报告](B5-Implementation.md) |
| GC-04 | 引用==0 | PASS | 真实同卷隔离，任务记录和正式路径检查。 [B5 实施报告](B5-Implementation.md) |
| GC-05 | 安全期后 purge | PASS | SQLite 与 PG 真实文件和库；以调整隔离时间和 mtime 复验 24h。 [B5 实施报告](B5-Implementation.md) |
| GC-06 | purge 前引用回升 | PASS | 隔离副本恢复，正式副本验证前保留唯一有效源。 [B5 实施报告](B5-Implementation.md) |
| GC-07 | quarantine 后崩溃 | PASS | 两个真实 GC 子进程在隔离后和清除后退出；重发正式代次保留。 [Windows 故障复验](evidence/v2-windows-fault-addendum.log) |
| GC-08 | 瞬时失败 attempts<8 | PASS | 真实 key 争锁与 Windows 共享冲突触发退避。 [B5 实施报告](B5-Implementation.md) |
| GC-09 | 持续失败 attempts≥8/不可重试 | PASS | 8 次真实竞争与终态，完成后无下次调度。 [B5 实施报告](B5-Implementation.md) |
| GC-10 | 旧 worker token 被接管 | PASS | 实际任务 token 漂移阻止文件操作；旧锁 PG 会话终止后 token 增长。 [B5 实施报告](B5-Implementation.md) |
| GC-11 | needs_manual 人工恢复 | PASS | 损坏槽保留，显式操作进入人工及重试，禁止自动复位。 [B5 实施报告](B5-Implementation.md) |
| GC-12 | 引用数派生 | PASS | 真实 SQLite/PG COUNT 与共享引用检查，schema 沿用。 [B5 实施报告](B5-Implementation.md) |
| ORP-01 | DB 事务失败遗留物理孤儿（无 gc_task） | PASS | 真实 HTTP 上传发布后提交失败，从无记录、无任务的物理孤儿开始，经 ORP 入队、Worker 隔离和到期清除。带引用的文件及记录保持。 [Windows SQL 与文件系统专项](evidence/remediation-windows-gc-trace.log) |
| ORP-02 | 上传临时文件 | PASS | 临时残留只计数并保留，不计入正式路径。 [B5 实施报告](B5-Implementation.md) |
| ORP-03 | 安全等待期内文件 | PASS | 新孤儿不入队，24h 边界前后验证。 [B5 实施报告](B5-Implementation.md) |
| ORP-04 | DB 有引用、原始缺失、quarantine 存在 | PASS | 真实隔离副本校验并恢复被引用文件，引用保持。 [B5 实施报告](B5-Implementation.md) |
| ORP-05 | quarantine 残留（崩溃后） | PASS | 五个真实子进程退出点验证接收事务前后、槽转移前后与引用恢复。重启后保留不可信文件和新正式代次。 [Windows SQL 与文件系统专项](evidence/remediation-windows-gc-trace.log) |
| ORP-06 | ORP 与 GC 并发同 key | PASS | 真实同键 GC 和 ORP 竞争后只保留一个有效隔离槽；PG 领导权和 key 锁分项验证。 [Windows 故障复验](evidence/v2-windows-fault-addendum.log) |
| ORP-07 | DB↔物理一致性 | PASS | 同一实际 JSON 报告包含缺失、孤儿、哈希不匹配。验证原文件、数据库引用及脱敏。 [Windows SQL 与文件系统专项](evidence/remediation-windows-gc-trace.log) |
| IMP-19 | 导入含附件清单（ZIP-only） | PASS | Windows、Ubuntu/SQLite、真实 PG，ZIP-only、幂等、共享、pending 与归档分流。 [B3-T01](B3-T01-Closure.md) · [B3-T02](B3-T02-Implementation.md) |
| R1-IMP-05 | Active 导入提交 pending | PASS | 真实 pending envelope 包含附件和摘要，正式引用未写。 [B3-T01](B3-T01-Closure.md) · [B3-T02](B3-T02-Implementation.md) |
| R1-IMP-08 | Approve 导入 ReviewRequest | PASS | 业务提交与索引同步均按统一协调入口分离。本轮复验有/无附件批准、普通审核批准、草稿直办、版本恢复及模型异常日志。 [P1 复验说明](P1-01-Review-Index-Remediation.md) |
| R1-IMP-09 | Approve hook 写 tags 后故障 | PASS | 标签写后故障使审核和业务记录回滚；PG 在附件 flush 后独立复验。 [Windows 故障复验](evidence/v2-windows-fault-addendum.log) |
| R1-IMP-10 | Reject active 导入 | PASS | 拒绝保持条目和正式存储，损坏 envelope 与并发冲突均有实际 HTTP 证据。 [B4 实施报告](B4-Implementation.md) |
| R1-IMP-11 | Reject staging 清理失败 | PASS | 真实 Windows 句柄拒绝删除时审核仍已拒绝，文件转 ORP。 [Windows 实际占用](evidence/b4-windows-handle.log) |
| R1-IMP-14 | envelope digest/schema 不匹配 | PASS | 损坏摘要和完结标记 fail-closed；schema 校验由 B3 staging 专项覆盖。 [B4 实施报告](B4-Implementation.md) |
| R1-IMP-37 | approve 预检后 envelope 改动 | PASS | 真实二次会话修改 payload，S1 阻断业务写。 [B4 实施报告](B4-Implementation.md) |
| R1.1-IMP-38 | approve hook 任一点故障 | PASS | PostgreSQL 18.6 五个独立用例覆盖附件、标签、来源、链接和发布后归档。审批回滚，保留 staging，已有正式 Blob 保持。 [PG JUnit](evidence/remediation-posix-pg.3XoAQbf0/final-pg-review.xml) |
| R1.1-IMP-41 | staging 仍被 PENDING 引用 | PASS | 实际 pending staging 的保存、隔离后恢复、畸形 manifest fail-closed。 [B5 实施报告](B5-Implementation.md) |
| R1.1-IMP-42 | staging 无 pending 且超 grace | PASS | 普通权限 Windows 与 ext4 都执行 mtime 最大值、空目录、生产者与 Sweep 交错、搬移/清除边界的 pending 回升及隔离恢复。Windows junction/reparse、Ubuntu symlink 和实际启动路径有实机证据。 [Windows JUnit](evidence/remediation-windows-normal-cbd2945355bf/staging-sweep.xml) · [ext4 JUnit](evidence/remediation-posix-pg.3XoAQbf0/final-posix.xml) |
