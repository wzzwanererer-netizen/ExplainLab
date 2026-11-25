# Ubuntu 用户与家目录探测

来源为用户提交的普通 PowerShell 截图，无截图内时间戳。

- id 显示 wzz，UID 和 GID 均为 1000，属于 sudo 组。未验证 sudo 认证。
- uname -r 显示 6.18.58.1-microsoft-standard-WSL2。
- findmnt -T ~ -o SOURCE,FSTYPE,TARGET 显示 /dev/sdd ext4 /。
- python3 --version 显示 Python 3.14.4。
- command -v 未返回 uv、psql、pg_config 的路径。这不排除 PATH 以外的安装。
- 整体 WSL 退出码为 0，末尾的 true 保证整体探测结束成功。工具是否存在根据各命令的输出判断。
- WSL 报告 NAT 模式下未镜像宿主 localhost 代理。联网尚未测试。
