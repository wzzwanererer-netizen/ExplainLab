# Windows / WSL 恢复报告

| 观察 | 结果 | 证据编号 |
| --- | --- | --- |
| 当前 Windows 身份 | 本地 wzz。进程低完整性 S-1-16-4096，Administrators 在当前令牌仅用于拒绝 | 01 |
| WSL 安装与版本 | `wsl --version` 成功，WSL 3.0.5.0，报告内核组件 6.18.58.1-1、Windows 10.0.26300.9974 | 02 |
| 默认状态、发行版枚举、运行中枚举 | 均返回 `Wsl/E_ACCESSDENIED`，进程退出 4294967295（按有符号读取为 -1）。E_ACCESSDENIED 对应 0x80070005，具体内部调用点未知 | 03–05 |
| 受管会话查询用户发行版注册表 | Access is denied，注册路径未知，默认发行版后来由普通会话确认 | 06 |
| 服务 | WslService、vmcompute、hns 的 OpenService 返回 5。旧 LxssManager 查询返回 1060。服务运行状态未知 | 07–10 |
| 虚拟化功能和 hypervisor | CIM 查询受阻，功能状态未知 | 15、21 |
| 事件日志 | 日志通道枚举和 System 的 Hyper-V-Compute 查询均拒绝访问，未获取失败事件 | 12–13 |
| Ubuntu 候选盘 | `D:\wsl2\Ubuntu\ext4.vhdx`，2,714,763,264 字节，最后修改 2026-11-23 01:40:56.2245908 UTC。ACL 查询显示 wzz 和 Administrators 全控制。候选 VHDX 与实际 guest 的注册绑定未核验 | 11、20 |

交互会话复核显示普通 PowerShell 可以枚举发行版。用户截图记录 `Ubuntu  Stopped  2`，默认标记为 `*`，退出码为 `0`。普通会话成功启动 Ubuntu，`findmnt` 显示 `/dev/sdd ext4 /`。受管终端复跑列表与直接调用仍得到 `Wsl/E_ACCESSDENIED`，具体检查点未知。

交互会话复验命令为 `wsl -d Ubuntu --exec findmnt -T / -o SOURCE,FSTYPE,TARGET`。截图未显示该次退出码。

证据来源见 [用户交互会话记录](evidence/interactive-wsl-list.md)。

交互会话预检确认家目录位于原生 ext4，系统默认 Python 为 3.14.4，当时 PATH 未找到 uv、psql、pg_config。后续在 Ubuntu 解包，核验输入包 232 条 SHA-256，以 Python 3.11.9 完成锁定安装和导入检查。项目与 pytest 临时目录均位于 ext4。[用户与家目录探测](evidence/interactive-wsl-home.md) · [安装日志](evidence/acceptance.R3sYC6uE/environment.log)

最终定点验收再次由普通 PowerShell 启动 WSL。新 ext4 源码副本通过输入包校验，覆盖 4 个测试文件后逐文件比对摘要，并确认实际 import 来自该副本。沿用已锁定的 Python 3.11.9 运行环境与专用 PostgreSQL 18.6。本轮 Linux 应用跨挂载测试、T04、LCK-07 和 PG 锁回归均退出 0，PG 已正常停止。[最终 WSL 驱动日志](../V2-A1-04-Batch-B-B1-final-verification-round/evidence/wsl-final.g8LQ7isi/driver.log) · [受管重试原始输出](../V2-A1-04-Batch-B-B1-final-verification-round/evidence/managed-wsl.log)

普通 Windows PowerShell 随后用原生 Python 执行 T01。真实 junction 在 DB 祖先、附件根、staging 根三个入口均被拒绝，C/D 跨盘入口也被拒绝。4 通过、0 跳过、退出 0。受管令牌此前拒绝创建 junction 的日志继续保留。[普通 Windows 原始日志](../V2-A1-04-Batch-B-B1-final-verification-round/evidence/windows-normal-cbf67966e623/t01-windows.log)
