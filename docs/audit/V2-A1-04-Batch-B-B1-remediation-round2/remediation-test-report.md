# B1 第二轮测试报告

运行环境为 Windows 10.0.26300、Python 3.11.9、SQLite 3.45.1。完整命令、跳过范围和退出码见 `test-evidence/`。数据库功能使用实际 SQLite 文件库。

<!-- RESULTS -->

- test_attachment_gc.py 与 test_attachment_pg.py 原有断言曾将 failed_retryable → done 当作正确路径。按冻结 §4.2 改为拒绝并核对状态保留。另外新增合法到期重排、重新 claim 及成功 worker 写回。保留原 token mismatch、终态与并发断言。
- 文件操作旧用例改用真实 SQLite LockGuard。损坏测试实际注入发布后的字节变化；Windows 占用测试仍要求真实占用和句柄释放后的成功删除。POSIX 专项的故障模拟单独标注。
- PG 旧测试修正了把批 guard 传给单 lease release 的调用，改为 guard.release，并断言成功。PG 模拟只验证调用时序、异常分类和清理分支。
- PostgreSQL 故障注入独立复验 10 项通过，包含 release SQL 出错后抛出分类错误、关闭连接和再次释放。见 [pytest-pg-faults-current.txt](test-evidence/pytest-pg-faults-current.txt)。
- 第一次综合输出捕获中断，自动审批拒绝继续轮询该会话，理由为工具请求可能向未授权外部目标传输环境或测试遥测。保留的截断输出仅用于追溯。
- 受限执行环境中的一次直接运行停在 Python 3.11 Windows Proactor 创建本地 socketpair 的 `accept` 内，应用 lifespan 尚未执行。线程堆栈见 `pytest-full-current.txt`。第一版测试进程适配用 5 ms 轮询替代跨线程唤醒 socket，但遗漏主线程创建事件循环时的信号唤醒描述符，导致 5 个 Active 审核测试失败。修正适配后这 5 项全部重跑通过，见 [pytest-event-loop-adapter-regression.txt](test-evidence/pytest-event-loop-adapter-regression.txt)。表中正式结果来自原生命令。
- 现有 Starlette TestClient 的 httpx 弃用告警保留。
