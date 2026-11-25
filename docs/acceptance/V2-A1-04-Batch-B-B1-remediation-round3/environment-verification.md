# 环境验证

| 环境 | 证据 | B1 裁决 |
| --- | --- | --- |
| Windows / SQLite | 真实文件数据库、独占写事务、连接池耗尽、提交前 ORM 刷新和回滚。实际文件测试覆盖普通 hard link、临时文件、no-clobber 与原生占用。 | 按最终测试日志记录 |
| Windows 目录链接 | 受限环境无法创建 junction/symlink。reparse 属性故障注入覆盖预检拒绝及无副作用。 | 真实创建用例在本环境跳过 |
| PostgreSQL | `EXPLAINLAB_PG_TEST_URL` 未设置，环境无 psql、pg_ctl 或 Docker 命令。回环 5432 探测返回 PermissionError，WSL 返回 Wsl/E_ACCESSDENIED。独立的 PG 实机套件保留现有门控。 | **BLOCKED** |
| POSIX | Windows 运行，无法使用 WSL。目录 fsync 错误注入结果独立于 POSIX 实机验收。同句柄路径替换由平台门控跳过。 | **BLOCKED** |

PostgreSQL 实机尚需覆盖双连接 advisory、TTL 不授权接管、断连接管、双连接仓储并发、行锁等待与 heartbeat、有界传输等待，以及真实业务事务结束后释放错误保真。POSIX 实机尚需覆盖专用根、硬链接、不覆盖、目录 fsync、同句柄路径替换和持久性行为。

环境命令、版本及退出码见 [environment.txt](evidence/environment.txt)。Windows 测试使用已有会话适配器以 5ms 轮询实现 Proactor 跨线程唤醒，因为本环境无法完成本地 TCP socketpair 初始化。测试断言及应用、数据库和文件系统的生产调用照常执行。
