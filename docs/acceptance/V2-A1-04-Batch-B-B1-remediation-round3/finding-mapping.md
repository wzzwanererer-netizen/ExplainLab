# 第二轮发现与本轮修复映射

| 发现 | 冻结契约 | 实际生产入口 | 直接回归 |
| --- | --- | --- | --- |
| IR2-01 | storage §4.4、§4.6 | `storage_lock.py` 的批量 acquire、`_verify_leases`、逆序清理 | `test_batch_discards_first_lease_when_second_outlives_it`，真实文件库与再次接管 token |
| IR2-02 | storage §4.4、§4.6 | `session.py` 的 per-call checkout、`sqlite_connection_budget`、`sqlite_fence_session`，`storage_lock.py` 的单次批量核验 | `test_independent_fencing_is_bounded_under_sqlite_exclusive_writer`、`test_sqlite_pool_checkout_obeys_budget_for_write_and_business_fence`，保留缓存刷新及失败回滚测试 |
| IR2-03 | storage §4.3、§4.6 | `LockGuard` 的 timed join 与序列化，`PostgresStorageKeyLock`、`_PostgresGuardState` 与 psycopg 传输预算 | `test_pg_client_deadline_bounds_driver_call_and_late_cleanup`、`test_pg_drain_deadline_does_not_reuse_connection_with_stalled_heartbeat`，保留晚到建连、断连与正常排空测试 |
| IR2-04 | storage §7 | `LockGuard.__exit__`、专用会话释放和关闭错误处理 | `test_pg_context_release_failure_preserves_business_result`、`test_pg_close_failure_invalidates_session_and_preserves_result`，保留显式 SQL 错误及幂等释放测试 |
| IR2-05 | storage §3.1、§6.1 | `attachment_storage.py` 的 `_mutate` 与 `_link_or_rename` | `test_f12_only_link_syscall_may_authorize_fallback`，五种失败或降级场景分别断言 syscall 次数与源/目标内容 |
| IR2-06 | storage §1、B1-T01 | `config.py` 的配置路径锚定，`main.py` 已有 lifespan 预检，`attachment_storage.py` 的预留冲突检查 | `test_lifespan_rejects_missing_sqlite_db_path_as_storage_root`、合法独立目录、junction/symlink 及 reparse 注入 |

上述前两项使用 SQLite 文件库。PG 故障注入使用连接替身。F12 使用实际临时文件和 SQLite guard，原生错误号为注入。真实 PostgreSQL 和 POSIX 验收状态见 [environment-verification.md](environment-verification.md)。
