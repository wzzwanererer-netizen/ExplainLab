# B1 最终定点复验矩阵

53 个冻结编号及其原顺序完整保留。末列为当前 B1 证据状态。后续阶段栏延续冻结范围。待独立审核的部分项显式标出。

[T01 路径安全](../V2-A1-04-Batch-B-B1-final-verification-round/T01-Windows.md) · [T04 PG 仓储](../V2-A1-04-Batch-B-B1-final-verification-round/T04-PostgreSQL.md) · [LCK-07 PG 客户端退出](../V2-A1-04-Batch-B-B1-final-verification-round/LCK-07-PostgreSQL.md)

| 编号 | 历史证据 | B1 原补证焦点 | 后续阶段 | 当前裁决与证据 |
| --- | --- | --- | --- | --- |
| ATT-01 | 真实 Windows 文件及 SQLite 存储，已有 hash/分片 | POSIX 根、权限、hash/同卷 | B2 上传 HTTP，PG 与 POSIX 完整路由 | B1 已验证。ext4 发布、hash/读写及实际权限位 |
| ATT-02 | 真实 Windows no-clobber/复用，SQLite 两引用 COUNT | PG 仓储 COUNT 与共享删除，POSIX hard link/复用 | B2 双条目上传，PG 与 POSIX 联调 | B1 已验证。ext4 发布/no-clobber；真实 PG 共享计数与删除 |
| ATT-03 | — | — | B2 Base64/大小，PG 与 POSIX | 后续阶段。按冻结路线执行。 |
| ATT-04 | — | — | B2 MIME 与魔数，PG 与 POSIX 真实上传 | 后续阶段。按冻结路线执行。 |
| ATT-05 | — | — | B2 SVG 拒绝及下载头，PG 与浏览器/文件侧 | 后续阶段。按冻结路线执行。 |
| ATT-06 | 真实 Windows 路径边界。Round 3 新 DB 路径 reparse 为注入 | POSIX symlink、权限、根越界；Windows 新 DB 祖先链接待真测 | B2 文件名与响应头 | B1 已验证。普通 PowerShell 三个真实 junction 入口在生产 lifespan 拒绝，数据库与 mkdir 未调用，目录内容和哈希保留。实际 Windows C/D 边界和 ext4 symlink/权限亦通过。 |
| ATT-07 | 真实 Windows `open_verified_blob` 同读取句柄辅助层 | POSIX 读取辅助层，和 ATT-09 同组 | B2 授权与下载流，PG 与 POSIX | B1 已验证。ext4 同句柄读取、关闭 |
| ATT-08 | 真实 SQLite 仓储共享/独享删除，未验完整 GC 队列 | PG 仓储删除/COUNT/FK，真实事务 | B2 DELETE；B5 GC 消费，PG 与 POSIX | B1 已验证。真实 PG 共享引用删除、外部事务回滚及 SQLSTATE 23503 外键拒绝，完整删除入口在 B2。 |
| ATT-09 | 真实 Windows 文件 hash/句柄，Windows 门控跳过替换 | POSIX 打开句柄后实际替换文件、hash/关闭 | B2 HTTP 流与取消，PG 与 POSIX | B1 已验证。ext4 打开后路径替换 |
| ATT-10 | 真实 Windows 存储发布并发与 SQLite key 锁 | PG 专用锁并发，POSIX 同 key 无覆盖 | B2 上传事务并发；B5 GC/ORP 屏障 | B1 已验证。真实 ext4 同 key 文件发布、真实 PG 专用连接互斥分别有证据，应用事务和物理发布联动沿冻结后续阶段取证。 |
| ATT-11 | 真 SQLite 仓储回滚。文件孤儿仍存的注入证据 | PG 真实仓储事务；POSIX 发布及异常保留可复用存储组 | B2 发布后 commit 故障；B5 ORP 收敛 | B1 已验证。真实 PG 外层 rollback 经新 Session 验证，ext4 注入目录同步失败保留文件，发布后事务失败及孤儿处理在 B2/B5 联调。 |
| ATT-12 | 真 Windows 占用、目标竞争。旧版真 EXDEV；当前 F12 分类含注入 | POSIX hard link/rename/no-clobber/fsync；真实跨挂载拒绝按可用挂载补 | B2 错误映射与引用副作用 | B1 已验证。Linux ext4/tmpfs 的生产 lifespan 同卷检查真实拒绝，保留源及哈希，目标无副作用。Windows C/D 实测配置和 lifespan 的路径边界拒绝，另有内核 EXDEV 及 F12 注入。 |
| ATT-13 | — | — | B2 archived 与列表及竞态。依赖 PG/文件真测，孤儿由 B5 收敛 | 后续阶段。按冻结路线执行。 |
| LCK-01 | 真 SQLite acquire/token | PG advisory+token，现有真机用例 | — | B1 已验证。真实 PG advisory 与 token 行 |
| LCK-02 | 真 SQLite 双 owner/双 manager | PG 双 backend 互斥与竞争 | — | B1 已验证。真实 PG 双会话互斥 |
| LCK-03 | 真 SQLite 过期接管、token 单调 | PG 断开前后与旧 guard，现有真机用例 | — | B1 已验证。真实关闭专用连接后的接管与 token 增量 |
| LCK-04 | 真 SQLite renew | PG 行心跳续约及真实 SQL 等待 | — | B1 已验证。真实 PG 续租、SQL 等待预算、heartbeat 与 verify/release 交错 |
| LCK-05 | 真 SQLite 失配；实际守卫和文件负例 | PG 失效及故障前后真实状态；POSIX 停止修改 | B5 工作者整链路确认 | B1 已验证。真实 PG 旧 guard verify 拒绝和 ext4 无效 guard 文件保护分别取证，跨层联动按 B5。 |
| LCK-06 | 真 SQLite 释放与 token 保留，PG 替身释放测试 | PG 幂等、unlock/close、异常保真 | — | B1 已验证。释放失配、幂等、heartbeat 排空、真实释放超时后保留原异常与已提交结果，连接随后关闭并可接管 |
| LCK-07 | Round 2 真 SQLite 子进程被杀，TTL 后接管 | PG 真实持锁子进程退出；Linux ext4 核验锁与重启边界 | B4 联调追踪；B5 GC-07 独立验证 | B1 已验证。Linux 客户端 SIGKILL 后 PG backend 消失、原 advisory 释放、重新取得 token 1→2，旧凭证 verify/release 拒绝。原主动关闭和服务端终止证据独立保留。 |
| LCK-08 | Windows 真文件操作有失配前置证据 | POSIX 检查失配后不改文件；PG 失配同样待实测 | B4 发布屏障，B5 隔离代次恢复窗口 | B1 已验证。真实 PG guard 失效及 ext4 文件改动保护分别通过，发布和物理隔离联动沿 B4/B5。 |
| LCK-09 | 冻结契约明确租约边界，现有 SQLite 行为证据 | PG 与 SQLite 边界分别记录，PG 用 LCK-10 | — | B1 已验证。真实 PG TTL 过期不授权接管 |
| LCK-10 | PG 替身有时序证据 | PG 双 PID、TTL、断连接管、相同投影与跨批、100 key 单连接和部分失败 | — | B1 已验证。TTL、关闭接管、投影竞争、双向顺序、100 key 单 PID、部分清理、批次中途真实终止 backend |
| GC-01 | 真 SQLite 条件认领/计数 | PG 任务状态、token、attempts 与隔离等待 | B5 入队和 worker 循环 | B1 已验证。真实 PG pending 首次认领、过期 running 接管、未到期及隔离期拒绝，token/attempts 递增，拒绝状态不漂移。 |
| GC-02 | 真 SQLite 两 session 同 task 只一成功 | PG 两真实 session 只一 claim | B5 不同任务的物理代次竞争，PG/POSIX | B1 已验证。真实 PG 双 session 只一个 claim 成功 |
| GC-03 | 真 SQLite 引用 COUNT 仓储，可复用 | — | B5 持锁复核、保留唯一副本，PG/POSIX | 后续阶段。按冻结路线执行。 |
| GC-04 | 真 Windows 隔离辅助层，真 SQLite 隔离等待规则 | POSIX 辅助层同卷移动/目录 fsync，PG 仓储等待 | B5 隔离与任务记录的联动 | B1 已验证。ext4 隔离、真实 PG 隔离前等待；故障注入单列 |
| GC-05 | 真 Windows slot 删除辅助层 | POSIX 删除辅助层，保护与 fsync | B5 24h 到期后的 PG/POSIX purge | B1 已验证。ext4 slot 删除；无断电级证据 |
| GC-06 | 真 Windows 恢复辅助层 | POSIX 恢复与 hash | B5 引用回升恢复/取消，PG/POSIX | B1 已验证。ext4 恢复与 hash |
| GC-07 | 无 GC 崩溃真实证据，LCK-07 单独登记 | — | B5 两个真实进程崩溃切点及 ORP/GC，PG/POSIX | 后续阶段。按冻结路线执行。 |
| GC-08 | 真 SQLite 重排和到期条件；故障为注入 | — | B5 完整退避、瞬时错误与占用，PG/POSIX | 后续阶段。按冻结路线执行。 |
| GC-09 | 真 SQLite attempts/终态/人工边界 | PG 终态与条件更新，和 GC-10 同组 | B5 实际八次重试和七态归档 | B1 已验证。真实 PG attempts 耗尽、终态拒认领、worker 写回不改 attempts，旧 token 与非法重写拒绝。八次运行全流程在 B5。 |
| GC-10 | 真 SQLite 过期、owner/token、状态写回保护 | PG token 拒绝旧任务，POSIX 文件 fencing 辅助层 | B5 接管后旧 worker 不删除 | B1 已验证。真实 PG token 拒绝与 ext4 文件 fencing 分别经专项执行 |
| GC-11 | 真 SQLite 人工转换仓储边界 | — | B5 授权、显式操作、原文件保留与审计日志 | 后续阶段。按冻结路线执行。 |
| GC-12 | 真 SQLite 附件 DISTINCT/COUNT，无物化计数 | PG 引用派生，ATT-02 同组 | B5 路径端到端保持权威 COUNT | B1 已验证。真实 PG 同 key 两记录的 DISTINCT、COUNT 和删除已有用例并复跑。B5 验证路径端到端。 |
| ORP-01 | 真实孤儿的 fsync 注入保留，未执行扫描 | — | B5 孤儿识别、入队、隔离/purge，PG/POSIX | 后续阶段。按冻结路线执行。 |
| ORP-02 | 真实 Windows `.tmp` 专用目录与独占文件 | POSIX 分区、路径安全、临时文件真实行为 | B5 扫描报告 temp_residual | B1 已验证。ext4 临时路径、独占清理及实际权限位 |
| ORP-03 | — | — | B5 24h 窗口与 mtime，PG/POSIX | 后续阶段。按冻结路线执行。 |
| ORP-04 | 真 Windows quarantine 恢复与 hash 辅助层 | POSIX 恢复基础语义 | B5 缺文件的引用恢复，PG/POSIX | B1 已验证。ext4 隔离后恢复 |
| ORP-05 | 真 Windows 无覆盖隔离辅助层 | POSIX 文件辅助层同卷及 fsync | B5 残留分类/交接、终止重启，PG/POSIX | B1 已验证。真实 ext4 同卷隔离/恢复，目录同步异常为注入。GC/ORP 指定切点的进程终止和恢复沿 B5。 |
| ORP-06 | 真 SQLite 逻辑锁、真 Windows 发布并发基础 | PG 真锁竞争，关联 LCK-02/10 | B5 ORP 与 GC 屏障/不双删，PG/POSIX | B1 已验证。真实 PG 专用连接互斥、批量清退及双 Session 单一 claim。GC/ORP 联动沿 B5。 |
| ORP-07 | — | — | B5 一致性扫描、报表与保守处置，PG/POSIX | 后续阶段。按冻结路线执行。 |
| IMP-19 | Batch A 导入回归可复用，附件 manifest 待验 | — | B3 ZIP/staging/传输；B4 Active 附件，PG/POSIX | 后续阶段。按冻结路线执行。 |
| R1-IMP-05 | Batch A Active 审核回归，附件新增语义待验 | — | B3/B4 pending manifest 与零正式引用，PG/POSIX | 后续阶段。按冻结路线执行。 |
| R1-IMP-08 | Batch A 审核与事务回归 | — | B4 附件发布与①/②，PG/POSIX；B5 孤儿收敛 | 后续阶段。按冻结路线执行。 |
| R1-IMP-09 | Batch A 审核回滚回归 | — | B4 附件 hook 真 DB 回滚及文件保留，PG/POSIX | 后续阶段。按冻结路线执行。 |
| R1-IMP-10 | Batch A 决议留痕回归 | — | B4 reject 与竞争终态，PG/POSIX；B5 未知归属 | 后续阶段。按冻结路线执行。 |
| R1-IMP-11 | 历史真 Windows 占用可复用系统层 | — | B4 reject 清理失败；B5 orphan 报告，PG/POSIX | 后续阶段。按冻结路线执行。 |
| R1-IMP-14 | Batch A envelope 基础回归 | — | B4 附件 manifest 字段与 digest，PG | 后续阶段。按冻结路线执行。 |
| R1-IMP-37 | Batch A 导入一致性回归 | — | B4 S0/S1 附件摘要并发与 fresh session，PG | 后续阶段。按冻结路线执行。 |
| R1.1-IMP-38 | Batch A Epoch/审核故障回归，附件 hook 未验 | — | B4 附件分步回滚及归档竞争，PG/POSIX | 后续阶段。按冻结路线执行。 |
| R1.1-IMP-41 | — | — | B5 pending 的 staging 保护，PG/POSIX | 后续阶段。按冻结路线执行。 |
| R1.1-IMP-42 | 真实 Windows 根重叠/隔离前置；当前 reparse 为注入 | POSIX 根与隔离路径，关联 ATT-06/ORP-02 | B5 staging 标记、扫描竞争、隔离/恢复/purge，PG/POSIX | B1 已验证。三个真实 Windows junction、ext4 路径隔离、临时文件、symlink 与实际权限位实测通过。 |
