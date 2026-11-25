# P2-03 · Pending 查询 fail-closed

## 1. 问题

旧行为在服务未注入 `session_factory`（或查询失败）时把 pending 引用当作空集，导致 `discard` / `sweep` 可能删除仍被 pending ReviewRequest 引用的 staging。

## 2. 新契约

`pending_staging_ids()`（L1152–1198）返回 `set[str] | None`：

| 情况 | 返回 |
|---|---|
| 正常查询到 pending 及其附件 manifest | `set[str]`（可能为空集） |
| 无 `session_factory` | `None` |
| session 创建/查询抛异常 | `None` |
| payload 非法 JSON、非对象 | `None` |
| 导入 envelope 无法解析 | `None` |
| 附件 manifest 无法强制转换 | `None` |
| 同一条 pending 出现多个 staging_id | `None` |

`None` 表示“无法证明未被引用”，调用方必须保守处理：

- `_discard`（L1539–1554）：`refs is None` → 返回 `False`，不删除；
- `sweep_candidate`（L1106–1150）：`refs is None` → `SweepDecision(False, "pending_manifest_malformed", None)`，不判定可清理；
- session 在 `finally` 中关闭。

路由侧仍注入真实 session factory；`None` 只会在外部构造/注入缺失时出现，属于保护性失败而非正常路径。

## 3. 验证

`backend/tests/test_attachment_staging.py::TestPendingFailClosed`

| 测试 | 场景 | 断言 |
|---|---|---|
| `test_missing_session_factory_discard_fails_closed` | `session_factory=None` | `pending_staging_ids() is None`；`discard_committed` 返回 `False`；目录仍存在 |
| `test_missing_session_factory_sweep_fails_closed` | `session_factory=None` | `candidate is False`，`reason == "pending_manifest_malformed"`；目录仍存在 |
| `test_pending_query_failure_preserves_staging` | factory 抛 `RuntimeError` | discard 返回 `False`，sweep 不可清理，目录仍存在 |

另由 `TestPendingReuseGuard` 覆盖复用路径：在 `staging_guard` 内重新读取 pending 并校验 manifest，若 pending 状态/内容漂移则 409，不静默复用（见 `guard-lifetime-proof.md`）。

原始日志：`evidence/remediation/b3-t01-special.log`（54 passed）。

## 4. 边界

- 这是**进程内**保守策略，不是跨进程分布式锁；
- `None` 时不会尝试任何“猜测性清理”，代价是可能留下待 ORP 处理的 staging（B5 范围）；
- 真实 PostgreSQL 下的 pending 查询未在本轮验证（`EXPLAINLAB_PG_TEST_URL` 未设置）。