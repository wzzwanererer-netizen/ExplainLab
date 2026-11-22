# POSIX 验证状态

## 1. 环境与方法

- 环境：WSL2 Ubuntu（真实 Linux 内核；发行版标识见 `evidence/postgresql-probe.txt` 的 `Ubuntu`）。
- 探针：`evidence/posix_probe.py`，仅用标准库，直接导入仓库真实模块：
  - `backend/app/services/file_write.py`
  - `backend/app/services/source_instance_id.py`
  - `backend/app/db/process_lock.py`
- 命令（原始输出见 `evidence/posix-probe-run.txt`）：

```bash
wsl.exe -e bash -lc "cd /mnt/d/ExplainLab/docs/acceptance/V2-A1-04-Batch-A/final-remediation/evidence && PYTHONPATH=/mnt/d/ExplainLab/backend python3 posix_probe.py"
```

- 结果：9 PASS / 1 UNVERIFIED，退出码 0。
- stderr：仅 WSL 关于 localhost 转发的环境提示（`evidence/posix-probe-stderr.txt`），与探针无关。

## 2. 已通过（真实 Linux 原语）

| 检查 | 结果 | 说明 |
| --- | --- | --- |
| `id_create_mode_0600` | PASS | 新建实例 ID 文件权限 `0o600` |
| `id_ensure_idempotent` | PASS | 重复 `ensure()` 返回同一 ID |
| `id_concurrent_ensure` | PASS | 并发 `ensure()` 只产生一个 ID 文件、内容唯一 |
| `id_fallback_exclusive_create` | PASS | 模拟硬链接不可用时，`O_EXCL` 回退创建且权限 `0o600` |
| `posix_dir_fsync_called` | PASS | 目录 fsync 被真实调用 1 次（Windows 为空操作） |
| `id_replace_atomic` | PASS | `os.replace` 替换后读取为新 ID，无中间态 |
| `write_all_eintr_retry` | PASS | `InterruptedError` 后重试（2 次写调用完成） |
| `process_lock_cross_process_contention` | PASS | 跨进程竞争时子进程返回 2 / `BACKEND_ALREADY_RUNNING` |
| `process_lock_release_allows_child` | PASS | 释放后子进程成功获取锁（`0o600`） |

## 3. 未验证

| 检查 | 状态 | 原因 |
| --- | --- | --- |
| `journal_store_full_import` | UNVERIFIED | WSL Ubuntu 的 Python 3.14 无 pip / SQLAlchemy，无法导入 JournalStore 与完整后端 |
| Linux 全量 pytest | 未执行 | 同上；未用 Windows 结果顶替 |
| PG on Linux | 未执行 | 无 PostgreSQL 客户端/服务 |

**这些未验证项没有被计为通过。**

## 4. 覆盖与缺口对应

- P2-03（close 失败）与 P2-05（`os.link` FileExistsError）在 POSIX 探针中的覆盖为间接：`id_fallback_exclusive_create` 与 `id_replace_atomic` 验证了真实原语，但 close/link 异常注入仍在 Windows pytest 中完成；Linux 下的异常注入未执行。
- P2-06 归档发布依赖 `os.link` 优先、`O_EXCL` 回退；POSIX 探针验证了回退创建，未在 Linux 上重放归档竞态测试。
- 结论：POSIX 原语层面可用且行为符合预期；完整后端链路在 Linux 上仍需独立环境复验。见 `final-known-issues.md` §A.2。