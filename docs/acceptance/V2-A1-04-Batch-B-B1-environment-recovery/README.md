# ExplainLab B1 环境恢复与专项结果

**B1 正式状态维持 BLOCKED，最终轮核验建议 CONDITIONAL。** 普通 PowerShell 的真实 Windows junction、真实 Linux 跨挂载保护、PG T04 与 LCK-07 均已通过，详见 [最终定点验收](../V2-A1-04-Batch-B-B1-final-verification-round/README.md)。

以下为环境恢复阶段留存结果。

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
