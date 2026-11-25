# 审计裁决

**BLOCKED。** 当前 B1 有 **4 项 P1、2 项 P2** 代码发现。冻结的真实 PostgreSQL 和 POSIX 验证门槛尚未满足。

- **SQLite**。整批获取可能交付首个租约已经过期的 guard。fencing 查询仍走全局 5 秒 busy 配置，连接池 checkout 也没有使用调用剩余预算。独立探针在真实 SQLite 文件库分别复现。
- **PostgreSQL**。客户端 SQL、等待心跳退出和清理仍缺统一的有界等待。释放异常从 guard 上下文退出时改变调用方收到的异常。通过代码和可控驱动替身验证，真实 PG 验收仍未执行。
- **存储路径与 Windows 发布**。首次启动可把预留的 SQLite DB 文件位置建成目录。Windows 发布会从路径预检查错误走到 rename，即使 hard link 尚未调用。分别使用真实目录配置和故障注入验证。

解除阻塞需要复核 [代码发现](finding-register.md)，在真实 PostgreSQL 上执行锁、断连、双连接任务仓储和预算测试，并在 POSIX 上验证根、hard link、同句柄读取和目录持久性。依据见冻结 `implementation-roadmap.md:35–73` 和 `acceptance-plan.md:92–96`。GC worker/ORP 的崩溃恢复及完整 TOCTOU 收敛按冻结路线进入相应联调验收，见 [remaining-risks.md](remaining-risks.md)。

提交的 SQLite/Windows 全量日志为 1,278 通过、196 跳过。独立审计复跑了存储、锁和 GC 的高风险子集，并单独执行了边界探针。提交包清单 85/85，与工作树对应文件一致。
