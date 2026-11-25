# ExplainLab B1 环境恢复与专项结果

**B1 整体：BLOCKED。** 两套专项已在 Ubuntu WSL2 的 ext4 上实测通过。冻结计划中仍有未获证据的 B1 项。

| 证据 | 结果 |
| --- | --- |
| 安装与完整性 | Python 3.11.9，锁定依赖与四类导入检查通过；安装后包内文件摘要复核通过 |
| POSIX/Linux 套件 | 169 通过，0 跳过，1 警告，退出 0 |
| 真实 PostgreSQL 18.6 套件 | 17 通过，0 跳过，1 警告，退出 0 |
| PostgreSQL LCK-10 补测 | 100 key 单会话、部分获取失败清理、批次中途强制终止 backend 均通过，退出 0 |
| Heartbeat / POSIX 权限补测 | 两种真实 PG 排空交错与 ext4 权限断言均通过，退出 0 |
| 释放异常与 EXDEV 补测 | 原异常 traceback、已提交结果、随后接管及内核跨文件系统拒绝均通过，退出 0 |
| PostgreSQL 实例 | 专用实例正常关闭，服务端日志已归档 |

[恢复报告](environment-recovery.md) · [POSIX 证据](posix-environment.md) · [PostgreSQL 证据](postgresql-deployment.md) · [验收矩阵](acceptance-matrix.md) · [未解决项](unresolved.md) · [Git 范围](git-state.md) · [SHA-256](SHA256SUMS)
