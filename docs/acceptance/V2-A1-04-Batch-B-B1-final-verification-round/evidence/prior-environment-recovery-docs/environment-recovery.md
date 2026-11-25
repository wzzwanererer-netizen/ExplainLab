# Windows / WSL 恢复报告

| 观察 | 结果 | 证据编号 |
| --- | --- | --- |
| 当前 Windows 身份 | 本地 wzz。进程低完整性 S-1-16-4096，Administrators 在当前令牌仅用于拒绝 | 01 |
| WSL 安装与版本 | `wsl --version` 成功，WSL 3.0.5.0，报告内核组件 6.18.58.1-1、Windows 10.0.26300.9974 | 02 |
| 默认状态、发行版枚举、运行中枚举 | 均返回 `Wsl/E_ACCESSDENIED`，进程退出 4294967295（按有符号读取为 -1）。E_ACCESSDENIED 对应 0x80070005，具体内部调用点未知 | 03–05 |
| 当前用户发行版注册表 | Access is denied，注册与默认发行版未知 | 06 |
| 服务 | WslService、vmcompute、hns 的 OpenService 返回 5。旧 LxssManager 查询返回 1060。服务运行状态未知 | 07–10 |
| 虚拟化功能和 hypervisor | CIM 查询受阻，功能状态未知 | 15、21 |
| 事件日志 | 日志通道枚举和 System 的 Hyper-V-Compute 查询均拒绝访问，未获取失败事件 | 12–13 |
| Ubuntu 候选盘 | `D:\wsl2\Ubuntu\ext4.vhdx`，2,714,763,264 字节，最后修改 2026-11-23 01:40:56.2245908 UTC。ACL 查询显示 wzz 和 Administrators 全控制。磁盘注册关系、WSL 服务的实际访问和来宾启动均未验证 | 11、20 |

交互会话复核显示普通 PowerShell 可以枚举发行版。用户截图记录 `Ubuntu  Stopped  2`，默认标记为 `*`，退出码为 `0`。当前证据将枚举拒绝缩小到受管执行环境，具体内部权限检查点仍未知。交互会话随后成功启动 Ubuntu，findmnt 显示 /dev/sdd ext4 /。受管终端复跑列表与直接调用仍得到 Wsl/E_ACCESSDENIED。VHDX 注册路径绑定及项目副本挂载仍未验证。

交互会话复验命令为 `wsl -d Ubuntu --exec findmnt -T / -o SOURCE,FSTYPE,TARGET`。截图未显示该次退出码。

证据来源见 [用户交互会话记录](evidence/interactive-wsl-list.md)。

用户交互会话进一步确认家目录位于原生 ext4，默认 Python 为 3.14.4，当前 PATH 未找到 uv、psql、pg_config。详见 [用户与家目录探测](evidence/interactive-wsl-home.md)。Windows 侧已复核 Linux 输入包的 232 条内嵌 SHA-256。尚未在 Ubuntu 解包或安装依赖。

现已由用户交互会话执行并回写原始日志。运行目录为 /home/wzz/explainlab-b1.u4iXLEhT，项目与 pytest 临时目录为 ext4。Python 3.11.9 锁定安装、导入和清单复核成功。WSL 受管会话仍被拒绝，来宾的原 VHDX 注册路径绑定未检查。
