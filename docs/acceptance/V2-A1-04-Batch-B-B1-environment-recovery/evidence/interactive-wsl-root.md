# 用户交互会话启动证据

来源为本轮普通 PowerShell 截图。启动命令为 wsl -d Ubuntu --exec findmnt -T / -o SOURCE,FSTYPE,TARGET。输出列 SOURCE、FSTYPE、TARGET，对应结果 /dev/sdd、ext4、/。截图显示 NAT 模式未镜像 Windows localhost 代理的提示。截图末尾已输入 $LASTEXITCODE，但尚未显示执行值。截图上面的 0 属于先前的发行版列表命令。证据仅确认 Ubuntu 可启动及根挂载类型。尚无验收工作目录挂载或 Linux 网络连通性证据。

用户下一张截图显示 findmnt 后拼接的 PowerShell 命令发生解析错误，随后单独执行 $LASTEXITCODE 返回 0。其间无新的原生命令执行。
