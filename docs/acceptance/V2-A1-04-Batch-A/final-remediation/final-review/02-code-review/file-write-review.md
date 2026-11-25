# 02-D · 可靠写入与故障注入复核（P2-01…P2-06）

- 生产代码：
  - `backend/app/services/file_write.py`（本轮**未修改**）SHA-256 `64dc50…bd04`
  - `backend/app/services/source_instance_id.py` SHA-256 `f41955…1e22`
  - `backend/app/services/source_identity.py` SHA-256 `9c0175…f895a`（Journal 发布）
- 测试：
  - `backend/tests/test_batch_a_file_write.py`（13 项，第二轮审计状态，本轮净修改为零）
  - `backend/tests/test_batch_a_fault_injection.py`（23 项，本轮新增）
- P2 总计 36 项；下列“验证类型”严格区分：**真实文件系统执行**、**注入式故障**、**仅理论**。

## 1. `write_all`（P2-01）

实现（`file_write.py:20–31`）：

- 循环写直到 `offset == total`；`InterruptedError` 立即重试；返回 `<= 0` 抛 `OSError(EIO)`；其他异常原样传播。
- 不改打开模式、权限、fsync、replace/link 层级。

测试（`test_batch_a_file_write.py:32–100`，真实 fd + 临时目录）：

| 测试 | 注入 | 验证 |
| --- | --- | --- |
| `test_partial_then_complete` | `os.write` 只写一半 | 多次短写后字节完整 |
| `test_many_one_byte_writes` | 每次只写 1 字节 | 多轮后完整 |
| `test_zero_write_fails` | `os.write` 返回 0 | 抛 `EIO`，不无限循环，目标为空 |
| `test_exception_propagates_without_remaining_write` | 第一次写抛 OSError | 只调用一次、异常传播、目标为空 |
| `test_empty_payload_is_noop` | 无 | 空负载不调用写、文件为空 |

`test_batch_a_fault_injection.py::TestWriteAllInterrupted`（364–436，3 项）：首次 `InterruptedError` 后成功、连续多次中断、先中断后 OSError；断言已写前缀不重复、不补齐、不静默吞错。

## 2. fsync 失败（P2-02）

| 路径 | 测试 | 验证类型 | 断言 |
| --- | --- | --- | --- |
| Journal current | `test_journal_current_fsync_failure_preserves_old` | 注入 `os.fsync`，真实文件 | 旧 current 不变、无 `.tmp` |
| Journal archive | `test_journal_archive_fsync_failure_publishes_no_archive` | 注入 | 无归档、无 `.tmp`，current 保留 |
| ID 创建 | `test_id_create_fsync_failure_publishes_no_id` | 注入 | 无正式 ID、无 `.tmp` |
| ID 无 link 回退 | `test_id_fallback_fsync_failure_removes_partial` | 注入 + 模拟 link 不支持 | 回退路径不留截断正式文件 |
| ID replace | `test_id_replace_fsync_failure_preserves_old` | 注入 | 旧 ID 保持 |

所有发布路径均为“写临时文件 → `write_all` → fsync → close → 原子发布”；fsync 失败在发布前抛出，finally 清理 tmp。

## 3. close 失败（P2-03，发现并修复真实缺陷）

**缺陷**：`SourceInstanceIdStore.ensure()` 的 `os.link` 不可用回退分支中，若 `write_all` + fsync 已成功、随后 `os.close` 抛错，旧代码会 `unlink(self.path)`，删除已完整写入的**有效正式 ID**。

**修复**（`source_instance_id.py:131–151`）：引入 `write_ok`，仅在写入/fsync 未成功时删除半成品；fsync 成功后 close 失败只传播异常，正式 ID 保留。`os.close` 仍在 `finally`，无 fd 泄漏。

测试 5 项（`TestCloseFailure`，121–184）：Journal current、Journal archive、ID 创建、ID replace、回退路径。回退路径测试实际执行 `close` 后抛错，断言正式 ID 仍存在且可读（168–184）。

## 4. `os.replace` 失败（P2-04）

| 路径 | 测试 | 断言 |
| --- | --- | --- |
| Journal current | `test_journal_current_replace_failure_preserves_old` | 旧 current、无 tmp |
| ID replace | `test_id_replace_failure_preserves_old` | 旧 ID、无 tmp |
| 归档 | `test_archive_uses_no_overwrite_link_not_replace` | 即使 replace 被禁用，归档仍通过 link 发布成功 |

说明：归档自 P2-06 起**不再使用 replace**，因此 replace 失败不影响归档；该测试锁定此设计。

## 5. `os.link` 与 FileExistsError（P2-05）

`source_instance_id.py:125–134`：link 遇到目标已存在 → `FileExistsError` → `return self.read()`，严格校验既有内容；非法内容抛 `SOURCE_INSTANCE_ID_INVALID`，**不删除**既有文件。

测试（`TestLinkFileExists`，2 项）：在 link 调用瞬间写入合法/非法目标，分别验证“返回既有值不覆盖”和“fail-closed 不删除”。

## 6. Journal current/archive 发布

- current：`_atomic_write`（430–444）临时文件 + fsync + close + `os.replace`；失败保留旧 current，恢复门读取旧记录。
- archive：`archive_committed`（463–485）先做同 operation_id 同内容幂等短路；否则临时文件 → fsync → `_publish_archive_no_overwrite`。
- `_publish_archive_no_overwrite`（487–523）：
  1. `os.link(tmp, target)`；目标存在 → `FileExistsError` → 不覆盖；
  2. link 不支持 → `O_EXCL` 独占创建；写入/fsync 失败删除半成品；
  3. 最后**重新读取 target 逐字节比对**，缺失或不一致抛 `JOURNAL_CORRUPT`。
- 这消除了旧实现“`exists()` 检查 → `replace()`”之间的未验证竞态（P2-06）。

`TestArchiveNoOverwrite`（5 项）：不同 operation_id 均归档、同 id 同内容幂等、同 id 异内容 fail-closed、发布瞬间被写入冲突内容不覆盖、发布瞬间被写入相同内容接受且无 tmp。

## 7. 归档恢复与实例 ID 恢复

- Journal 恢复：`_recover_locked`（685–695）→ PREPARED MATERIALIZE/ROTATE 恢复或 COMMITTED 补归档；`_commit_and_archive`（723–737）前后各验一次审计摘要。
- ID 创建：临时文件 + link 不覆盖；link 不可用时 O_EXCL 正式文件 + `write_ok` 保护。
- ID replace：同一 data_dir 临时文件 + fsync + `os.replace`；失败保留旧 ID。
- 实例 ID 恢复（ROTATE）：`_recover_rotate` 对“ID 仍旧”完成 replace，对“ID 已新”只提交归档（801–814），测试两项均覆盖。

## 8. 验证类型与边界（重要）

| 项 | 状态 |
| --- | --- |
| Windows NTFS 真实文件、真实 fd、真实 link/replace/O_EXCL | **已执行**（默认测试套件，win32 Python 3.11.9） |
| 短写/零写/中断/fsync/close/replace/link 异常 | **注入式**，证明控制流与清理，不等同真实硬件错误 |
| POSIX 权限 0600、目录 fsync、EINTR、link 回退、进程锁争用 | WSL 探针 **9 PASS**（`evidence/posix-probe-run.txt`） |
| POSIX 完整 Journal/导入事务 | **UNVERIFIED**：WSL 缺 pip/SQLAlchemy，无法跑完整后端套件 |
| 真实断电/介质损坏/网络文件系统 | **未验证**，仅理论设计 |
| Windows ACL 是否等效 0o600 | **未验证**；Windows 不采用 POSIX 权限位 |
| Windows 目录 fsync | 代码显式 no-op（`source_identity.py:113–115`、`source_instance_id.py:53–56`），不宣称掉电持久 |
| 多进程/多 worker 同 data_dir | **未验证**；单实例 `ProcessLock` 排除 |

## 9. 结论

P2-01…P2-06 的缺陷均有对应代码修复与注入式回归；真实文件系统行为在 Windows 默认套件与 WSL 探针中部分验证。断电持久性、真实 I/O 错误、POSIX 完整事务仍属验证缺口，不应表述为已通过。