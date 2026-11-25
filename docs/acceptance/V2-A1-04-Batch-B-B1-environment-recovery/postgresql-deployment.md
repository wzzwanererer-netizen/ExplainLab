# PostgreSQL 部署与测试报告

2026-11-23，北京时间。Ubuntu 26.04.1 LTS / WSL2 ext4，以 Ubuntu 软件包解压在验收目录中，未调用系统安装。PostgreSQL 18.6，回环 `127.0.0.1:59927`，独立数据目录位于 `/home/wzz/explainlab-b1.u4iXLEhT/acceptance.R3sYC6uE/pg-data`。本地管理套接字使用 peer，TCP 规则为 SCRAM。专用数据库为 `explainlab_b1_acceptance`，测试角色为 `explainlab_b1_runner`，两个真实 TCP backend PID 为 868、869。测试后停止实例。

B1 的两个真实 PG 模块共 **17 通过、0 失败、0 跳过、1 警告，退出 0**。覆盖 advisory lock 互斥、TTL 不授权接管、实际关闭持锁连接后重新获取和 token 增量、旧 guard verify 拒绝、同投影竞争、两 key 批量、真实 SQL 锁等待预算、释放路径、附件共享计数和并发 GC claim/fencing。关闭专用连接证明真实会话结束释放，不等同于服务端强制终止或网络故障。续租测试及真实 SQL 等待覆盖不构成 heartbeat 与 verify/release 强制交错证据。

[部署/清理日志](evidence/acceptance.R3sYC6uE/postgresql-environment.log) · [服务端日志](evidence/acceptance.R3sYC6uE/postgresql-server.log) · [测试原始输出](evidence/acceptance.R3sYC6uE/postgresql-pytest.log) · [JUnit](evidence/acceptance.R3sYC6uE/postgresql.xml) · [退出码](evidence/acceptance.R3sYC6uE/postgresql-exit.txt)

LCK-10 补测均通过，脚本退出 0，专用实例再次正常停止。100 个 advisory 锁由单一 PID 497 持有；部分获取遇到竞争时先取得的 advisory 锁已释放，未写 token；服务端在批次中实际终止 PID 528 后，另一批次能接管且 token 保持原子语义。[原始日志](evidence/pg-probe.OL0D7vGW/probe.log) · [服务端日志](evidence/pg-probe.OL0D7vGW/server.log)

真实 heartbeat 交错补测通过。行锁实际阻塞 heartbeat backend 504、517，分别观察到 verify、release 等待。解除阻塞后调用正常完成，专用 backend 均未出现在 pg_stat_activity，实例退出 0 并正常停止。[原始日志](evidence/heartbeat-posix.ObKWO2Ft/probe.log)

真实行锁触发释放超时的两条补测通过。探针让已运行的 heartbeat 继续使用它原有的预算，再将独立 release 预算设为 250 ms。原异常 traceback 与已提交业务结果分别保留，稳定错误日志被记录，随后原 backend 508/525 均关闭，同 key 可重新获取。专用实例正常停止，探针退出 0。底层物理 close 抛异常仍仅有故障注入证据。[探针日志](evidence/release-filesystem.6qBa0AMA/probe.log) · [服务端日志](evidence/release-filesystem.6qBa0AMA/server.log)
