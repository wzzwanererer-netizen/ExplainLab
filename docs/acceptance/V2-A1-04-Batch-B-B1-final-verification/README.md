# ExplainLab B1 PostgreSQL 与 POSIX 双环境验收

**当前结论：BLOCKED。** 本轮已获准搭建和验收，但当前执行会话无法进入 Linux guest。环境和验收报告均据实标记未执行的项目。

- Windows 已确认 WSL 3.0.5.0 已安装，宿主可见 `D:\wsl2\Ubuntu\ext4.vhdx`。发行版列表及 guest 命令均返回 `Wsl/E_ACCESSDENIED`。
- VirtualBox 的运行与注册列表无法查询。VMware 实际返回 0 台运行中 VM。当前没有验证过的 Linux 登录目标。
- 已准备 Linux 导入包，使用 Batch A HEAD、13 个 Round 3 源码及测试覆盖和十份冻结设计。包内有 232 项文件哈希。环境阶段仍需在真实 guest 的 ext4 上解包、核验并安装。

| 文件 | 内容 |
| --- | --- |
| [linux-environment-report.md](linux-environment-report.md) | WSL、VHDX、VM 与副本结果 |
| [postgresql-environment-report.md](postgresql-environment-report.md) | 实例、账号、DSN 与前置核对状态 |
| [posix-acceptance-report.md](posix-acceptance-report.md) | 原生 POSIX 证据状态 |
| [postgresql-acceptance-report.md](postgresql-acceptance-report.md) | 17 项真测试和补测状态 |
| [acceptance-matrix.md](acceptance-matrix.md) | 53 项冻结矩阵与本轮状态 |
| [remaining-risks.md](remaining-risks.md) | 权限边界与解除条件 |
| [git-state.md](git-state.md) | 工作树与变更范围 |
| [SHA256SUMS](SHA256SUMS) | 交付内容校验，路径相对项目根 |

原始记录位于 `evidence/`。Linux 导入包为项目内的 `docs/acceptance/ExplainLab-B1-Round3-Linux-Input.zip`，随交付 ZIP 附上。
