# ORP-01 · DB Commit 失败导致物理孤儿恢复专项报告

**状态**：实机验证通过（待独立审计最终裁决）  
**测试环境**：
- Windows 真实文件系统 + SQLite（[closure-windows-gc-orp.log](evidence/closure-windows-gc-orp.log)）
- WSL2 Ubuntu `ext4` + SQLite（[closure-posix-sqlite.log](evidence/closure-posix-pg.SqauvYgo/closure-posix-sqlite.log)）
- WSL2 Ubuntu `ext4` + 真实 PostgreSQL 18.6（[closure-pg-orp01.log](evidence/closure-posix-pg.SqauvYgo/closure-pg-orp01.log) · [JUnit](evidence/closure-posix-pg.SqauvYgo/closure-pg-orp01.xml)）

**测试代码**：[test_v2_closure_gc_orp.py](file:///D:/ExplainLab/backend/tests/test_v2_closure_gc_orp.py)（`test_orp01_full_chain_sqlite` / `test_pg_orp01_full_chain`）

## 1. 完整 8 步恢复链路实证

以下以真实 PostgreSQL 18.6（`db=explainlab_closure_orp01_dpfif21x`）与 Windows SQLite 同步实测数据为准：

1. **参照物建立**：先正常上传并提交受引用附件 `protected`（`attachment` 行已落库，正式文件落盘）。
2. **DB Commit 失败注入（`DB Commit Failure → Physical Orphan`）**：
   - 通过真实 HTTP `POST /api/knowledge/{item}/attachments` 上传孤儿内容 `KEY = 17a4d4a044d6ca26bfb2d8082141feaea7f137ce0ff51d45d806e1b17780570f`。
   - 在物理 blob 发布落盘后、SQLAlchemy `Session.before_commit` 注入 `RuntimeError`。
   - 响应返回 HTTP 500；实测物理文件存在于 `17/a4/<KEY>` 且 SHA-256 吻合；DB 状态 `pg_orp01_after_commit_failure` 显示 `attachment_refs=0`、`tasks=[]`（无 `gc_task`）。
3. **24h 宽限期内扫描保护**：
   - 立即执行 `OrphanRecovery.scan_once()`：一致性报告记录 `formal_blobs=2, orphan_blobs=1, attachment_rows=1, referenced_keys=1`，仅识别孤儿 `KEY`（未误报受引用文件），且因 mtime 未满 24h **不创建 `gc_task`**（`tasks=[]`）。
4. **超 24h 孤儿扫描入队（`Orphan Scanner → GC Task Creation`）**：
   - 将孤儿与受引用文件的磁盘 `mtime` 均推进至 25h 前，执行 `scan_once()`。
   - 仅孤儿创建 `gc_task`（PG task `75d1d405-e5a5-41f9-95f6-0ee95fc1edda`，`status=pending, attempts=0, lease_token=0`）；受引用文件零任务。
5. **持锁复核与隔离（`StorageKeyLock Recheck → Quarantine`）**：
   - `GcWorker.run_due()` 认领任务、获取 `StorageKeyLock`（PG advisory lock）、复核 `COUNT(attachment)==0`，将正式孤儿移至 `_quarantine/<KEY>.<task_id>`。
   - DB 状态 `pg_orp01_after_quarantine`：`status=running, attempts=1, lease_token=1`，`next_retry_at - quarantined_at == 24h`；正式路径已消失，隔离槽 SHA-256 校验一致。
6. **隔离等待期强制保护（`Retention Period`）**：
   - 24h 到期前再次调用 `gc.run_due()`，任务不执行清除，`attempts` 维持 `1`，隔离槽完好。
7. **到期安全清除（`Purge`）**：
   - 推进 `quarantined_at`、`next_retry_at` 与槽文件 `mtime` 满 24h 后调用 `gc.run_due()`，再次持锁复核引用为 0 后删除隔离槽。
   - DB 状态 `pg_orp01_after_purge`：`status=done, attempts=2, lease_token=2`；孤儿正式路径与隔离槽均已彻底清除。
8. **受引用文件与锁清理核验**：
   - 受引用文件 `protected` 的正式文件字节 SHA-256 与 DB `attachment` 记录均完好无损。
   - PostgreSQL `pg_locks` advisory 锁数量为 `0`。

## 2. 退出码汇总

- Windows SQLite：`exit=0`（`test_orp01_full_chain_sqlite` PASSED）
- WSL2 ext4 SQLite：`exit=0`（`test_orp01_full_chain_sqlite` PASSED）
- WSL2 ext4 PostgreSQL 18.6：`exit=0`（`test_pg_orp01_full_chain` PASSED）
