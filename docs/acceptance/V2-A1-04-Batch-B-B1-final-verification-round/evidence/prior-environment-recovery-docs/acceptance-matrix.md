# B1 环境恢复复验矩阵

基于上一轮验收 ZIP 的逐项矩阵。最后一列为本轮新增状态。历史 Windows、SQLite 和注入证据沿用原记录。本轮新增真实 PostgreSQL 与 ext4 证据。已验证仅指本轮所列 B1 子项。部分项的未覆盖断言为 UNVERIFIED。

# 53 项冻结验收与本轮状态

本轮没有运行 PostgreSQL 或 POSIX 真机套件。以下矩阵继承经核验的预检和 Round 3 证据，当前列逐项标记本轮状态。历史真实证据的环境类型保持原登记。B1 对应冻结路线图 T01–T04，其他阶段沿冻结边界。

| 编号 | 可复用的真实证据 | B1 尚需证据 | 后续阶段 | 既有缺陷栏 | 本轮 | 本次实机复验 |
| --- | --- | --- | --- | --- | --- | --- |
| ATT-01 | 真实 Windows 文件及 SQLite 存储，已有 hash/分片 | POSIX 根、权限、hash/同卷 | B2 上传 HTTP，PG 与 POSIX 完整路由 | — | 未执行。B1 环境阻塞 | 已验证 B1 子项。ext4 发布、hash/读写及实际权限位 |
| ATT-02 | 真实 Windows no-clobber/复用，SQLite 两引用 COUNT | PG 仓储 COUNT 与共享删除，POSIX hard link/复用 | B2 双条目上传，PG 与 POSIX 联调 | — | 未执行。B1 环境阻塞 | 已验证 B1 子项。ext4 发布/no-clobber；真实 PG 共享计数与删除 |
| ATT-03 | — | — | B2 Base64/大小，PG 与 POSIX | — | 未执行。后续阶段 | UNVERIFIED（后续阶段） |
| ATT-04 | — | — | B2 MIME 与魔数，PG 与 POSIX 真实上传 | — | 未执行。后续阶段 | UNVERIFIED（后续阶段） |
| ATT-05 | — | — | B2 SVG 拒绝及下载头，PG 与浏览器/文件侧 | — | 未执行。后续阶段 | UNVERIFIED（后续阶段） |
| ATT-06 | 真实 Windows 路径边界。Round 3 新 DB 路径 reparse 为注入 | POSIX symlink、权限、根越界；Windows 新 DB 祖先链接待真测 | B2 文件名与响应头 | — | 未执行。B1 环境阻塞 | 部分。ext4 symlink、越界及路径替换通过；实际权限位通过；Windows 预留路径的真实 reparse 细项待测 |
| ATT-07 | 真实 Windows `open_verified_blob` 同读取句柄辅助层 | POSIX 读取辅助层，和 ATT-09 同组 | B2 授权与下载流，PG 与 POSIX | — | 未执行。B1 环境阻塞 | 已验证 B1 子项。ext4 同句柄读取、关闭 |
| ATT-08 | 真实 SQLite 仓储共享/独享删除，未验完整 GC 队列 | PG 仓储删除/COUNT/FK，真实事务 | B2 DELETE；B5 GC 消费，PG 与 POSIX | — | 未执行。B1 环境阻塞 | 部分。真实 PG 共享引用计数与删除通过；独立 FK 并发断言未单列 |
| ATT-09 | 真实 Windows 文件 hash/句柄，Windows 门控跳过替换 | POSIX 打开句柄后实际替换文件、hash/关闭 | B2 HTTP 流与取消，PG 与 POSIX | — | 未执行。B1 环境阻塞 | 已验证 B1 子项。ext4 打开后路径替换 |
| ATT-10 | 真实 Windows 存储发布并发与 SQLite key 锁 | PG 专用锁并发，POSIX 同 key 无覆盖 | B2 上传事务并发；B5 GC/ORP 屏障 | — | 未执行。B1 环境阻塞 | 部分。ext4 同 key 发布及 PG 专用会话互斥分别通过；组合场景未单列 |
| ATT-11 | 真 SQLite 仓储回滚。文件孤儿仍存的注入证据 | PG 真实仓储事务；POSIX 发布及异常保留可复用存储组 | B2 发布后 commit 故障；B5 ORP 收敛 | — | 未执行。B1 环境阻塞 | 部分。ext4 目录同步注入与对象保留通过；PG 事务失败同一发布流程待测 |
| ATT-12 | 真 Windows 占用、目标竞争。旧版真 EXDEV；当前 F12 分类含注入 | POSIX hard link/rename/no-clobber/fsync；真实跨挂载拒绝按可用挂载补 | B2 错误映射与引用副作用 | — | 未执行。B1 环境阻塞 | 部分。ext4 发布、隔离/恢复及不覆盖通过；真实跨文件系统 syscall 返回 EXDEV；应用在分离挂载上的拒绝和断电持久性待验证 |
| ATT-13 | — | — | B2 archived 与列表及竞态。依赖 PG/文件真测，孤儿由 B5 收敛 | — | 未执行。后续阶段 | UNVERIFIED（后续阶段） |
| LCK-01 | 真 SQLite acquire/token | PG advisory+token，现有真机用例 | — | — | 未执行。B1 环境阻塞 | 已验证 B1 子项。真实 PG advisory 与 token 行 |
| LCK-02 | 真 SQLite 双 owner/双 manager | PG 双 backend 互斥与竞争 | — | — | 未执行。B1 环境阻塞 | 已验证 B1 子项。真实 PG 双会话互斥 |
| LCK-03 | 真 SQLite 过期接管、token 单调 | PG 断开前后与旧 guard，现有真机用例 | — | — | 未执行。B1 环境阻塞 | 已验证 B1 子项。真实关闭专用连接后的接管与 token 增量 |
| LCK-04 | 真 SQLite renew | PG 行心跳续约及真实 SQL 等待 | — | — | 未执行。B1 环境阻塞 | 已验证 B1 子项。真实 PG 续租、SQL 等待预算、heartbeat 与 verify/release 交错 |
| LCK-05 | 真 SQLite 失配；实际守卫和文件负例 | PG 失效及故障前后真实状态；POSIX 停止修改 | B5 工作者整链路确认 | — | 未执行。B1 环境阻塞 | 部分。PG 旧 guard verify 拒绝，ext4 文件操作验证失效 guard；跨层联动待测 |
| LCK-06 | 真 SQLite 释放与 token 保留，PG 替身释放测试 | PG 幂等、unlock/close、异常保真 | — | — | 未执行。B1 环境阻塞 | 已验证 B1 子项。释放失配、幂等、heartbeat 排空、真实释放超时后保留原异常与已提交结果，连接随后关闭并可接管 |
| LCK-07 | Round 2 真 SQLite 子进程被杀，TTL 后接管 | PG 真实持锁子进程退出；Linux ext4 核验锁与重启边界 | B4 联调追踪；B5 GC-07 独立验证 | — | 未执行。B1 环境阻塞 | 部分。真实 PG 主动关闭连接后的接管和 ext4 ProcessLock 进程终止通过；另经服务端强制终止批次连接补测 |
| LCK-08 | Windows 真文件操作有失配前置证据 | POSIX 检查失配后不改文件；PG 失配同样待实测 | B4 发布屏障，B5 隔离代次恢复窗口 | — | 未执行。B1 环境阻塞 | 部分。ext4 文件改动保护通过，真实 PG guard 失效通过；PG 与文件操作端到端待测 |
| LCK-09 | 冻结契约明确租约边界，现有 SQLite 行为证据 | PG 与 SQLite 边界分别记录，PG 用 LCK-10 | — | — | 未执行。B1 环境阻塞 | 已验证 B1 子项。真实 PG TTL 过期不授权接管 |
| LCK-10 | PG 替身有时序证据 | PG 双 PID、TTL、断连接管、相同投影与跨批、100 key 单连接和部分失败 | — | — | 未执行。B1 环境阻塞 | 已验证 B1 子项。TTL、关闭接管、投影竞争、双向顺序、100 key 单 PID、部分清理、批次中途真实终止 backend |
| GC-01 | 真 SQLite 条件认领/计数 | PG 任务状态、token、attempts 与隔离等待 | B5 入队和 worker 循环 | — | 未执行。B1 环境阻塞 | 部分。真实 PG claim、token 和隔离等待通过；状态全矩阵未单列 |
| GC-02 | 真 SQLite 两 session 同 task 只一成功 | PG 两真实 session 只一 claim | B5 不同任务的物理代次竞争，PG/POSIX | — | 未执行。B1 环境阻塞 | 已验证 B1 子项。真实 PG 双 session 只一个 claim 成功 |
| GC-03 | 真 SQLite 引用 COUNT 仓储，可复用 | — | B5 持锁复核、保留唯一副本，PG/POSIX | — | 未执行。后续阶段 | UNVERIFIED（后续阶段） |
| GC-04 | 真 Windows 隔离辅助层，真 SQLite 隔离等待规则 | POSIX 辅助层同卷移动/目录 fsync，PG 仓储等待 | B5 隔离与任务记录的联动 | — | 未执行。B1 环境阻塞 | 已验证 B1 子项。ext4 隔离、真实 PG 隔离前等待；故障注入单列 |
| GC-05 | 真 Windows slot 删除辅助层 | POSIX 删除辅助层，保护与 fsync | B5 24h 到期后的 PG/POSIX purge | — | 未执行。B1 环境阻塞 | 已验证 B1 子项。ext4 slot 删除；无断电级证据 |
| GC-06 | 真 Windows 恢复辅助层 | POSIX 恢复与 hash | B5 引用回升恢复/取消，PG/POSIX | — | 未执行。B1 环境阻塞 | 已验证 B1 子项。ext4 恢复与 hash |
| GC-07 | 无 GC 崩溃真实证据，LCK-07 单独登记 | — | B5 两个真实进程崩溃切点及 ORP/GC，PG/POSIX | — | 未执行。后续阶段 | UNVERIFIED（后续阶段） |
| GC-08 | 真 SQLite 重排和到期条件；故障为注入 | — | B5 完整退避、瞬时错误与占用，PG/POSIX | — | 未执行。后续阶段 | UNVERIFIED（后续阶段） |
| GC-09 | 真 SQLite attempts/终态/人工边界 | PG 终态与条件更新，和 GC-10 同组 | B5 实际八次重试和七态归档 | — | 未执行。B1 环境阻塞 | 部分。真实 PG 更新和终态 fencing；PG 尝试次数全矩阵待测 |
| GC-10 | 真 SQLite 过期、owner/token、状态写回保护 | PG token 拒绝旧任务，POSIX 文件 fencing 辅助层 | B5 接管后旧 worker 不删除 | — | 未执行。B1 环境阻塞 | 已验证 B1 子项。真实 PG token 拒绝与 ext4 文件 fencing 分别经专项执行 |
| GC-11 | 真 SQLite 人工转换仓储边界 | — | B5 授权、显式操作、原文件保留与审计日志 | — | 未执行。后续阶段 | UNVERIFIED（后续阶段） |
| GC-12 | 真 SQLite 附件 DISTINCT/COUNT，无物化计数 | PG 引用派生，ATT-02 同组 | B5 路径端到端保持权威 COUNT | — | 未执行。B1 环境阻塞 | 部分。真实 PG 共享引用计数通过；单独 DISTINCT 并发断言未单列 |
| ORP-01 | 真实孤儿的 fsync 注入保留，未执行扫描 | — | B5 孤儿识别、入队、隔离/purge，PG/POSIX | — | 未执行。后续阶段 | UNVERIFIED（后续阶段） |
| ORP-02 | 真实 Windows `.tmp` 专用目录与独占文件 | POSIX 分区、路径安全、临时文件真实行为 | B5 扫描报告 temp_residual | — | 未执行。B1 环境阻塞 | 已验证 B1 子项。ext4 临时路径、独占清理及实际权限位 |
| ORP-03 | — | — | B5 24h 窗口与 mtime，PG/POSIX | — | 未执行。后续阶段 | UNVERIFIED（后续阶段） |
| ORP-04 | 真 Windows quarantine 恢复与 hash 辅助层 | POSIX 恢复基础语义 | B5 缺文件的引用恢复，PG/POSIX | — | 未执行。B1 环境阻塞 | 已验证 B1 子项。ext4 隔离后恢复 |
| ORP-05 | 真 Windows 无覆盖隔离辅助层 | POSIX 文件辅助层同卷及 fsync | B5 残留分类/交接、终止重启，PG/POSIX | — | 未执行。B1 环境阻塞 | 部分。ext4 同卷文件隔离/恢复通过；目录 fsync 故障注入，未测断电 |
| ORP-06 | 真 SQLite 逻辑锁、真 Windows 发布并发基础 | PG 真锁竞争，关联 LCK-02/10 | B5 ORP 与 GC 屏障/不双删，PG/POSIX | — | 未执行。B1 环境阻塞 | 部分。PG 互斥和双 session claim 通过；100 key 与部分获取失败补测通过；GC/ORP 端到端留待 B5 |
| ORP-07 | — | — | B5 一致性扫描、报表与保守处置，PG/POSIX | — | 未执行。后续阶段 | UNVERIFIED（后续阶段） |
| IMP-19 | Batch A 导入回归可复用，附件 manifest 待验 | — | B3 ZIP/staging/传输；B4 Active 附件，PG/POSIX | — | 未执行。后续阶段 | UNVERIFIED（后续阶段） |
| R1-IMP-05 | Batch A Active 审核回归，附件新增语义待验 | — | B3/B4 pending manifest 与零正式引用，PG/POSIX | — | 未执行。后续阶段 | UNVERIFIED（后续阶段） |
| R1-IMP-08 | Batch A 审核与事务回归 | — | B4 附件发布与①/②，PG/POSIX；B5 孤儿收敛 | — | 未执行。后续阶段 | UNVERIFIED（后续阶段） |
| R1-IMP-09 | Batch A 审核回滚回归 | — | B4 附件 hook 真 DB 回滚及文件保留，PG/POSIX | — | 未执行。后续阶段 | UNVERIFIED（后续阶段） |
| R1-IMP-10 | Batch A 决议留痕回归 | — | B4 reject 与竞争终态，PG/POSIX；B5 未知归属 | — | 未执行。后续阶段 | UNVERIFIED（后续阶段） |
| R1-IMP-11 | 历史真 Windows 占用可复用系统层 | — | B4 reject 清理失败；B5 orphan 报告，PG/POSIX | — | 未执行。后续阶段 | UNVERIFIED（后续阶段） |
| R1-IMP-14 | Batch A envelope 基础回归 | — | B4 附件 manifest 字段与 digest，PG | — | 未执行。后续阶段 | UNVERIFIED（后续阶段） |
| R1-IMP-37 | Batch A 导入一致性回归 | — | B4 S0/S1 附件摘要并发与 fresh session，PG | — | 未执行。后续阶段 | UNVERIFIED（后续阶段） |
| R1.1-IMP-38 | Batch A Epoch/审核故障回归，附件 hook 未验 | — | B4 附件分步回滚及归档竞争，PG/POSIX | — | 未执行。后续阶段 | UNVERIFIED（后续阶段） |
| R1.1-IMP-41 | — | — | B5 pending 的 staging 保护，PG/POSIX | — | 未执行。后续阶段 | UNVERIFIED（后续阶段） |
| R1.1-IMP-42 | 真实 Windows 根重叠/隔离前置；当前 reparse 为注入 | POSIX 根与隔离路径，关联 ATT-06/ORP-02 | B5 staging 标记、扫描竞争、隔离/恢复/purge，PG/POSIX | — | 未执行。B1 环境阻塞 | 已验证 B1 子项。ext4 路径隔离、临时文件、symlink 及实际权限位 |
