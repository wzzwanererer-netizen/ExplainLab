# B2-AUDIT-02 · PostgreSQL HTTP 验收

**实机补测通过，等待独立复审。** 2026-11-24 普通 PowerShell 在 WSL2 原生 ext4 上启动 PostgreSQL 18.6 和本轮独立测试库。B2 HTTP 专项 5 通过，PG 锁及仓储回归 18 通过，两组均无失败、无跳过，退出 0。此前受管会话的环境门控保留在回归记录中。

## 受管环境预检

受管 Windows 未配置 `EXPLAINLAB_PG_TEST_URL`。回环 5432/59927 的 TCP 探测被拒绝。WSL 发行版枚举与 Ubuntu 启动探针均返回 `Wsl/E_ACCESSDENIED`。这些结果表明受管会话无法完成连接验证。历史 B1 已验证可从普通 PowerShell 启动 WSL 内的 PostgreSQL 18.6。

[环境探测日志](evidence/pg-environment.log)

## 已运行定点用例

| 测试 | 验收断言 |
| --- | --- |
| `test_pg_http_upload_download_and_shared_reference` | 真实 HTTP 上传 201、下载内容和 ETag，与新连接查得的两条跨 item 引用及一份物理 blob 一致。删除一条引用后不入 GC 队列 |
| `test_pg_http_archive_update_blocks_upload_select_for_update` | 真实双连接，`pg_blocking_pids` 证明上传事务的 `SELECT FOR UPDATE` 等待归档事务。提交归档后上传返回 409，零新引用、无临时残留，保留已发布 blob |
| `test_pg_http_concurrent_uploads_wait_on_distinct_advisory_sessions` | 两个真实并发 HTTP 请求使用不同 PostgreSQL backend。首个请求事务尚未提交时仅其 advisory 已授予，独立 Session 查不到引用。提交并释放后第二请求复用相同引用，得到 201/200 |
| `test_pg_http_finishes_transaction_before_advisory_release[commit/rollback]` | 探针在释放前查询真实 advisory 和独立 Session 可见性。成功提交与真实 PG 错误导致的回滚分别发生在 release 前。之后同 key 可再次获得 |
| 既有 B1 PG 专项 | StorageKeyLock 14 项，包括 advisory、fencing 和客户端退出。仓储 4 项来自 WSL 执行入口采用的历史输入包，该入口仅覆盖更新了锁测试文件。此前 B1 已批准的 13 项仓储证据另行保留 |

HTTP 运行记录显示归档事务 PID 591 阻塞上传 PID 594。并发上传使用 PID 612 和 624，提交前只有前者持有锁。提交和回滚分别先于释放。HTTP 专项结束后，独立 SQL 查询记录 3 条附件引用、0 个已授予 advisory lock。执行入口清理了本轮临时库并停实例，驱动退出 0。

[执行入口](evidence/run-pg-http-wsl.sh) · [HTTP 日志](evidence/pg-http.V7CaM83E/postgresql-http.log) · [HTTP JUnit](evidence/pg-http.V7CaM83E/postgresql-http.xml) · [PG 回归](evidence/pg-http.V7CaM83E/postgresql-advisory.log) · [PG 回归 JUnit](evidence/pg-http.V7CaM83E/postgresql-advisory.xml) · [数据库状态](evidence/pg-http.V7CaM83E/db-after-http.log) · [执行总日志](evidence/pg-http.V7CaM83E/driver.log) · [受测覆盖文件 SHA-256](evidence/pg-http.V7CaM83E/source-overlays.sha256)
