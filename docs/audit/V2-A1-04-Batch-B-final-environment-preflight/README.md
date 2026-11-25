# ExplainLab V2 · Batch B · B1 最终双环境验收预检

**状态：B1 BLOCKED，等待批准搭建环境。**

本地 Round 3 交付 ZIP 的 74 项 SHA-256 均通过，并与当前工作树逐项一致。Batch A HEAD 为 `970c0d8ec05f0b8c68286839a56b14c74ea230c6`。冻结的 53 项是整个 Batch B 验收范围。B1 按冻结路线图只收口配置与存储、锁和仓储基础层。

优先复用一台可运行的现有 WSL2 发行版或 Linux 虚拟机，在 Linux 原生 ext4 上同时提供 POSIX 测试与独立 PostgreSQL 实例。当前会话的 WSL 和 PostgreSQL 回环探测受限，所以尚无可用 Linux shell、真实测试 DSN 或 Linux 安装结果。

| 文档 | 内容 |
| --- | --- |
| [environment-inventory.md](environment-inventory.md) | 实测环境和结论边界 |
| [postgresql-setup-plan.md](postgresql-setup-plan.md) | 隔离集群、账号、DSN、双连接和测试方案 |
| [posix-setup-plan.md](posix-setup-plan.md) | ext4 选择、项目安装和真实文件验证 |
| [acceptance-mapping.md](acceptance-mapping.md) | 53 项逐项映射及 B1 到后续阶段的边界 |
| [execution-plan.md](execution-plan.md) | 批准后执行顺序、失败分类和出证条件 |
| [known-blockers.md](known-blockers.md) | 当前阻塞与解除条件 |
| [inventory-evidence.txt](inventory-evidence.txt) | 当前会话探测输出 |

本轮已执行环境盘点与方案编制。环境部署和验收运行等待批准。
