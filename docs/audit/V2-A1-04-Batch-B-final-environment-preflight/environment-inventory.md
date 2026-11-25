# 环境盘点与实测

| 项目 | 实际检查 | 结果 |
| --- | --- | --- |
| Windows 与项目卷 | OS API、版本注册表、C/D 盘格式查询 | Windows Professional 26H2，AMD64，NT 10.0.26300.9974，C/D 均为 NTFS。项目位于 D 盘。 |
| WSL2、内核与挂载 | 实际运行 `wsl --status`、`wsl -l -v`、`wsl -e uname -a` | 三条均失败，Windows 进程返回 4294967295（PowerShell 显示 -1），诊断为 `Wsl/E_ACCESSDENIED`。发行版状态、WSL 代际、内核及挂载无法确认。 |
| Linux 原生 ext4 | 检查可启动 WSL 和当前可观察的虚拟机工具/进程 | 本会话未取得可运行 Linux shell，因此无法执行 `findmnt` 或实际验证 ext4。宿主机是否已有可复用发行版或 VM 仍待授权环境核实。 |
| Windows Python 与依赖 | 运行项目 `.venv`，导入仓库 storage/lock 模块和依赖 | Python 3.11.9，SQLite 3.45.1，SQLAlchemy 2.1.8，FastAPI 0.162.5，pytest 9.2.0，Alembic 1.20.1。 |
| PostgreSQL 驱动 | 实际导入 psycopg，读取底层库 | psycopg 3.3.9，binary 实现，libpq 编码版本 180004。驱动导入成功。 |
| PostgreSQL 服务与连接 | 搜索命令，尝试读取服务状态和 TCP 连接 127.0.0.1:5432 | `psql`、`pg_ctl`、`postgres` 未在 PATH 解析。服务管理器访问受限。TCP 返回 PermissionError / WinError 10013，未完成服务端连接与认证。探测进程的 `EXPLAINLAB_PG_TEST_URL` 与 `DATABASE_URL` 均未设置。 |
| Docker / Podman / VM 工具 | 查命令、常见安装位置及进程，查 Docker engine 命名管道 | 未确认有可用运行时。Docker engine 管道查询为 False。未取得 Docker/Podman daemon、VM 运行实例或 guest shell 的证明。 |
| 锁定依赖与 Linux 安装 | Windows 执行 `uv lock --check --offline`，改用显式解释器和独立临时缓存重试 | 首次默认缓存写入失败，重试解析 41 个包，退出 0。Linux 的 `uv sync --locked` 和 Linux wheel/构建/导入均待实测。 |

本地 Round 3 ZIP SHA-256 为 `50e18afefa96f38743047312cfa17a20f887eaaf5c72d1665a5c0dfc00166af5`。ZIP CRC、74 项内容哈希与工作树的对应文件均核过。工作树有既有 B1 修改，暂存区为空。

WSL 结果只描述本次执行权限。下一步应在获批的宿主机交互会话核对现有发行版或 Linux guest，再选环境。原始输出见 [inventory-evidence.txt](inventory-evidence.txt)。
