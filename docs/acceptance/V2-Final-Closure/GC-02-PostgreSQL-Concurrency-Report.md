# GC-02 · PostgreSQL 并发竞争专项报告

**状态**：实机验证通过（待独立审计最终裁决）  
**测试环境**：WSL2 Ubuntu 原生 `ext4` + 真实 PostgreSQL 18.6（`server_version_num=180006`）  
**数据库**：独立隔离库 `explainlab_closure_gc02_dpfif21x`  
**测试代码**：[test_v2_closure_gc_orp.py](file:///D:/ExplainLab/backend/tests/test_v2_closure_gc_orp.py)  
**原始日志与 JUnit**：[closure-pg-gc02.log](evidence/closure-posix-pg.SqauvYgo/closure-pg-gc02.log) · [closure-pg-gc02.xml](evidence/closure-posix-pg.SqauvYgo/closure-pg-gc02.xml)

## 1. 验证目标与执行配置

验证真实 PostgreSQL 18.6 + 真实 `ext4` 文件系统下，**两个真实 `GcWorker` 实例**（独立 `worker.owner`、独立 DB Session 与独立 PostgreSQL backend 连接）并发处理**指向同一物理 `storage_key`（`17a4d4a044d6ca26bfb2d8082141feaea7f137ce0ff51d45d806e1b17780570f`）的两个不同 `gc_task`** 时的串行化、槽隔离、代次保护、fencing 与最终收敛。

## 2. 实测执行轨迹（摘自原始日志）

### 用例 1：`test_pg_gc02_two_workers_compete_same_storage_key_different_tasks`

1. **竞争前状态（`pg_gc02_before_contention`）**：
   - `task_1`（`4204087f-74e0-4cb5-911b-09aed4958628`）：`status=running`，`attempts=1`，`lease_token=1`，隔离槽 `17a4d4...4204087f...` 已满 24h 等待期，待 purge。
   - `task_2`（`02a52eed-079b-42bc-a050-644bcc2cd3dc`）：`status=pending`，`attempts=0`，`lease_token=0`，指向同 key 重新发布并删除后的第 2 代正式文件。
   - `attachment_refs=0`。
2. **真实 PostgreSQL Advisory Lock 串行化**：
   - `worker_1` 进入 `_process` 时持有真实 PG advisory lock：`[(pid=873, classid=396678304, objid=1154927142, granted=True)]`。
   - `worker_2` 并发调用 `_run_task(task_2)` 竞争同一 `StorageKeyLock`，阻塞等待期间观测到 `locks_during_contention=[(873, 396678304, 1154927142, True)]`，`worker_2` 未进入 `_process`，`slot_1` 仍在且 `slot_2` 不存在。
   - `worker_1` 仅清除 `slot_1` 并提交 `task_1 -> done`（`attempts=2, lease_token=2`），未触碰第 2 代正式文件，释放 advisory lock。
   - `worker_2` 随后在**不同 PostgreSQL backend PID 880** 上取得同一 advisory lock：`[(pid=880, classid=396678304, objid=1154927142, granted=True)]`，确认 `slot_1` 已消失且正式文件 SHA-256 完整，将其隔离至独立槽 `slot_2`（`17a4d4...02a52eed...`），设置 24h 等待期（`status=running, attempts=1, lease_token=1`）。
3. **Fencing 与代次等待期保护**：
   - 构造过期 `expected_lease_token=0` 对 `task_2` 执行条件更新，返回 `None`，旧 Worker 无法覆盖新 Worker 状态。
   - 24h 等待期到期前再次执行 `run_due()`，`slot_2` 保留且 `attempts` 仍为 1。
4. **最终收敛（`pg_gc02_converged`）**：
   - 推进第 2 代隔离时间满 24h 后执行 `worker_2.run_due()`，两任务均收敛至 `status=done`（`attempts=2, lease_token=2`），`slot_1`、`slot_2` 与正式文件均不存在，`attachment_refs=0`，`pg_locks` advisory 锁数量为 `0`。

### 用例 2：`test_pg_gc02_two_workers_race_same_task`

- 两个真实 `GcWorker` 并发对同一 `pending` 任务调用 `run_due()`：仅一者成功认领并隔离（`attempts=1, lease_token=1`），无重复移动，结束后 `advisory_locks=0`。

## 3. 验收结论核对

- 无双重物理删除：已证实。
- 无错误恢复：已证实。
- 无跨任务隔离槽污染（`<key>.<task_1>` 与 `<key>.<task_2>` 严格隔离）：已证实。
- 无旧 Worker 覆盖新 Worker 状态（条件更新 token fencing）：已证实。
- 最终数据库与物理文件状态一致（`2 passed, 0 failed, exit=0`）：已证实。
