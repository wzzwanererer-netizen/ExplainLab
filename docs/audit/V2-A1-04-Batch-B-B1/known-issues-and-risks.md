# B1 已知问题与剩余风险

## A. 阻塞项

### A-1 真实 PostgreSQL 完全未运行

- 现状：`EXPLAINLAB_PG_TEST_URL` 未配置，本机无 PostgreSQL 服务（`raw/pg-availability.txt`）。
- 影响：以下代码路径只有静态审查与 SQLite 对照，**没有任何真实 PG 证据**：
  - `pg_try_advisory_lock` / `pg_advisory_unlock` 两 int32 身份与 `pg_locks` 校验；
  - `storage_lock` UPSERT `RETURNING lease_token`；
  - 行 TTL 过期但 advisory 存活时拒绝接管、断开专用连接后接管（LCK-10）；
  - 专用 `NullPool` 连接的物理关闭语义；
  - 两真实 session 并发 `claim` 的 `UPDATE` 条件重估；
  - `with_for_update()` 业务会话 fencing。
- 处置：不得以 SQLite 结果替代；需真实实例执行 `backend/tests/test_storage_lock_pg.py` 与 `test_attachment_pg.py` 后才可解除。

### A-2 POSIX 与真实跨卷未验证

- 本批所有真机运行均在 Windows 10 完成；POSIX 的 `os.link`/rename/权限/fsync 语义未实测。
- 跨卷分支仅通过 monkeypatch 注入，未在真实双卷环境取证。
- 处置：按验收计划在 Linux/POSIX 与双卷环境补跑，未跑前维持“未验证”。

## B. 未执行的验收场景

1. **进程 kill**（LCK-07、GC-07）：无子进程持锁/隔离中被 kill 的真实用例。SQLite 的“租约过期接管”已用逻辑时间验证，但不等价于真实进程死亡。
2. **TOCTOU 窗口**（LCK-08）：未在最终 verify 前/后暂停并让另一 owner 接管，未验证残余窗口的隔离/恢复表现。
3. **ATT-11/B5 联动**：仅验证仓储 flush/rollback；未验证“发布成功→DB commit 失败→正式 blob 成孤儿→ORP 24h 收敛”。
4. **GC worker 退避/8 次失败**：仓储拒绝 attempts≥8 已测；`min(60*2**(n-1),21600)` 的实际调度仍属 B5。

## C. 实现层面的审计关注点（非已确认缺陷）

1. **SQLite `claim` 不内置 busy 重试**：并发写竞争可能抛 `OperationalError`（busy_timeout 5s 内通常等待）。冻结要求 worker 把 busy 视为瞬时竞争重试；该重试尚未实现（B5），当前由调用方负责。
2. **PG `acquire_many` 捕获所有异常并返回 `None`**：可覆盖连接/授权失败，但也可能掩盖编程错误；建议独立审计评估是否收窄异常面。
3. **PG 心跳以行租约为准**：若专用连接暂停超过 TTL 导致行过期，`renew` 返回 False 并使 guard abort，即使 advisory 仍存活。保守中止符合“观察到失配立即停止”，但与“行 TTL 不释放 advisory”的展示语义存在解释空间，需审计确认。
4. **`claim` 对 pending 也要求 `next_retry_at` 到期**：属于保守实现；调度器把 `failed_retryable` 转 `pending` 时必须同时清理/到期 `next_retry_at`，否则无法认领。
5. **`update_task` 不校验状态机合法性**：只强制 token 匹配与终态保护；`running→failed_retryable→done` 等非法跃迁由服务层负责，B5 必须覆盖。
6. **`max_attempts` 仅在仓储构造参数**：默认 8 与冻结一致；B5 装配时须传入 `settings.gc_max_attempts`，避免配置与仓储不一致。
7. **`open_verified_blob` 只消除“按路径重开”**：外部进程在同一句柄打开后原地改写仍可能影响流式输出；冻结已明确不得宣称完全消除。
8. **Windows 路径长度**：仅记录 >240 字符告警，未在真实长路径环境验证。

## D. 工程与流程

1. **仓库全量 `ruff check` 非零**：5 个问题全部在未跟踪的冻结审阅快照 `docs/audit/V2-A1-04-Batch-B-freeze-review-package/source-evidence/.../0006_v2_markdown_kb.py`，不是 B1 代码；未修改、未加排除规避。B1 代码范围 lint 通过。
2. **未提交**：B1 改动与证据均为工作区未提交状态；按指令未 commit、未 push，等待独立审计后精确暂存。
3. **既有未跟踪文档**：工作区含此前阶段的审阅包 ZIP/目录，B1 未触碰。

## E. 明确不得声称

- 不得声称 B1 验收通过或 Batch B 通过。
- 不得声称 PostgreSQL、POSIX、真实跨卷、进程崩溃、TOCTOU 窗口已验证。
- 不得声称附件上传与 DB 原子、GC 已消除 TOCTOU。