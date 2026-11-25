# ORP-05 · 隔离槽恢复与真实子进程崩溃接管专项报告

**状态**：实机验证通过（待独立审计最终裁决）  
**测试环境**：
- Windows 真实文件系统 + SQLite（[closure-windows-gc-orp.log](evidence/closure-windows-gc-orp.log)）
- WSL2 Ubuntu `ext4` + SQLite（[closure-posix-sqlite.log](evidence/closure-posix-pg.SqauvYgo/closure-posix-sqlite.log)）
- WSL2 Ubuntu `ext4` + 真实 PostgreSQL 18.6（[closure-pg-orp05.log](evidence/closure-posix-pg.SqauvYgo/closure-pg-orp05.log) · [JUnit](evidence/closure-posix-pg.SqauvYgo/closure-pg-orp05.xml)）

**测试代码**：[test_v2_closure_gc_orp.py](file:///D:/ExplainLab/backend/tests/test_v2_closure_gc_orp.py)

## 1. 真实子进程崩溃注入点与恢复结果

所有故障均通过独立 Python 子进程调用 `os._exit(code)` 强制终止，无任何进程内异常模拟：

| 崩溃窗口 / 场景 | 故障注入点 | 子进程退出码 | 重启/新 Worker 接管行为 | 最终 DB 与物理文件状态 | 结果（Win / ext4 / PG 18.6） |
| --- | --- | ---: | --- | --- | --- |
| **终态 `DONE` 任务残留 · `before_receiver`** | 创建接收 `gc_task` 之前 | `31` | PG advisory lock 随子进程连接断开自动释放；重启后 `scan_once` 识别原槽并入队接收任务，`GcWorker` 采纳并重算 24h 等待期 | 终态任务保持 `done`，接收任务 24h 后 `done` 并清槽；未知文件与损坏槽保留 | PASS / PASS / PASS |
| **终态 `DONE` 任务残留 · `after_receiver`** | 接收 `gc_task` 提交后、转移槽前 | `32` | 空接收任务安全结束为 `done`；后续扫描重新接管原槽并重算 24h 等待期 | 所有任务收敛为 `done`，原槽清除，未知文件与损坏槽保留 | PASS / PASS / PASS |
| **终态 `DONE` 任务残留 · `before_transfer`** | 物理槽转移调用前 | `33` | 同上，未发生半转移或误删，重启扫描重新建立接收任务并完成 24h 隔离清除 | 任务收敛 `done`，未知文件与损坏槽保留 | PASS / PASS / PASS |
| **终态 `DONE` 任务残留 · `after_transfer`** | 物理槽已转移至新槽、扫描返回前 | `33` | 重启 `GcWorker` 认领接收任务，发现目标槽已存在且无 `quarantined_at`，按冻结规则从接管时刻重新起算 24h | 24h 前不误删，满 24h 后 `done` 清槽；未知文件与损坏槽保留 | PASS / PASS / PASS |
| **有正式引用 · `during_restore`** | `restore_from_quarantine` 刚完成后 | `34` | 正式文件已无覆盖恢复且通过 HTTP 下载校验（200 + SHA-256 一致）；重启扫描不误删被引用文件 | 正式文件与 DB 引用完好，未知文件与损坏槽保留 | PASS / PASS / PASS |
| **物理移动完成、DB 状态未写回 + 活跃槽保护** | `GcWorker` 完成正式→隔离移动后、`_wait_quarantine` 写 DB 前 | `35` | 崩溃后 DB 为 `running` 且 `quarantined_at=None`；重启扫描识别活跃任务归属返回 `owned_slot_preserved` 不劫持；租约过期后新 Worker 接管（`attempts=2, token=2`），采纳隔离槽并从接管时刻重算 24h，满期安全 purge | 任务 `attempts=3, token=3, status=done`，隔离槽清除，未知命名文件保留，`advisory_locks=0` | PASS / PASS / PASS |

## 2. 五类冻结恢复规则逐项核验

1. **有正式引用**：安全恢复至正式路径并通过 HTTP 下载校验，绝不错误 purge。
2. **无正式引用且满足等待期**：必须经接收任务隔离并满足完整 24h 等待期后才允许 purge；24h 内绝不提前删除。
3. **未知命名或无法确认归属的文件**：测试在隔离目录同时放置 `unknown-residual-artifact.bin`（`unrecognized_slot`）与篡改内容的 `<key>.<uuid>`（`_UnsafeAttachment`），扫描仅记录报告，全程字节未改、未被删除。
4. **已有有效（活跃）GC Task 的隔离槽**：ORP 扫描返回 `owned_slot_preserved`，正确识别归属与代次，不与其他任务混淆。
5. **终态任务 / 无任务的隔离残留**：统一经接收任务移交并重新计时，绝不直接物理删除。
