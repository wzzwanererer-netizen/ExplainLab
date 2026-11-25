# POSIX 原生 ext4 取证

系统为 Ubuntu 26.04.1 LTS / WSL2 内核 6.18.58.1-microsoft-standard-WSL2。验收副本和 pytest 临时目录均在 `/dev/sdd` 的 ext4 根挂载上。安装报告记录锁定安装命令、Python 3.11.9、SQLite 与 psycopg 导入和源码摘要复核。

附件、GC 和两组 Batch A 文件/进程测试共 **169 通过、0 失败、0 跳过、1 警告，退出 0**。覆盖真实文件发布和 no-clobber、隔离与恢复、同句柄读取及打开后替换、symlink/路径拒绝、真实 ProcessLock 跨进程竞争及进程终止后释放。目录 fsync 失败和 Journal 写失败为故障注入。真实普通进程终止证据限于 ProcessLock，未验证 GC/Journal 在指定断点终止或断电级持久性。也未执行真实不同挂载点上的跨卷矩阵。POSIX 权限位专项及完整目录持久性结论保留在矩阵中。

[安装与导入日志](evidence/acceptance.R3sYC6uE/environment.log) · [ext4 挂载与测试日志](evidence/acceptance.R3sYC6uE/posix-environment.log) · [JUnit](evidence/acceptance.R3sYC6uE/posix.xml) · [退出码](evidence/acceptance.R3sYC6uE/posix-exit.txt)

真实 POSIX 权限补测通过。存储、staging、quarantine、临时目录和发布分片目录为 0700，临时文件和正式对象为 0600。[原始日志](evidence/heartbeat-posix.ObKWO2Ft/probe.log)

真实跨文件系统的内核探针通过。ext4 和 /dev/shm 的 st_dev 不同，link 和 rename 均返回 EXDEV，源内容保持且目标未出现。该探针直接调用真实 syscall。应用在实际分离挂载下的完整配置与拒绝路径仍为 UNVERIFIED。[原始日志](evidence/release-filesystem.6qBa0AMA/probe.log)
