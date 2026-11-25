# Linux 环境与验收副本

| 状态判别 | 证据与结论 |
| --- | --- |
| WSL 是否安装 | `wsl.exe --version` 退出 0，输出 3.0.5.0、内核组件 6.18.58.1-1。该内核号来自 WSL 组件输出，尚无运行中 guest 的 `uname` 结果。 |
| 当前权限 | 当前令牌 Administrators 检查为 False。WSL 状态、列举、`uname` 均拒绝访问。服务查询 `WslService` 返回 5。结果描述本会话的访问边界。 |
| 发行版是否注册/启动 | 找到 `D:\wsl2\Ubuntu\ext4.vhdx`。当前用户 HKCU 枚举未返回可确认的发行版条目，WSL 列表命令本身失败。无法确认该磁盘对应发行版的注册、WSL 代际或运行状态。 |
| Linux VM 是否可登录 | VirtualBox 存在，`list vms` 和 `list runningvms` 均为 E_ACCESSDENIED。VMware `vmrun list` 退出 0，报告无运行中的 VM。无经过验证的可登录 Linux guest。 |
| ext4 与用户身份 | 未进入 guest，未执行 `findmnt`、`uname`、`id`。可见 VHDX 只是磁盘文件存在证据。 |
| Python 与依赖 | Windows 实际成功导入 Backend、Core、SQLite、psycopg。Linux 安装及导入未执行。 |

原始命令、时间、输出、退出码见 [host-probe.txt](evidence/host-probe.txt) 与 [hypervisors.txt](evidence/hypervisors.txt)。发行版运行态应通过获准会话中的 WSL 列表验证。见 [Microsoft WSL 命令](https://learn.microsoft.com/en-us/windows/wsl/basic-commands)。

## 已完成的副本准备

用 Git read-only archive 读取 Batch A `970c0d8ec05f0b8c68286839a56b14c74ea230c6`。为了保持提交字节，打包命令使用一次性的 `-c core.autocrlf=false -c core.eol=lf`。Round 3 ZIP 的 74 项与工作树一致，选取 13 个源码和测试及十份冻结设计叠加。保留承诺的锁文件、迁移、前后端与 Core，排除历史审计副本和项目数据。导入包 232 项内容有 SHA-256。见 [source-preparation.txt](evidence/source-preparation.txt)。

本次仅生成待传入的归档。取得 guest 后，在专用空目录逐一确认原生 ext4，再解包、运行 `sha256sum -c SHA256SUMS` 和 `uv sync --locked --python 3.11.9`。套件的工作目录、pytest 临时目录与附件根必须实际落在 Linux 原生 ext4。
