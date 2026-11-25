# 本轮新运行的测试证据

所有文件均为 2026-11-22 03:56 之后**重新运行**，文件头记录命令与开始时间，文件尾记录退出码。
未复用 `../remediation/evidence/` 或更早运行的历史结果。

| 证据文件 | 范围 | 本轮结果 | 退出码 |
| --- | --- | --- | ---: |
| `23-new-tests.txt` | P1 10 项 + P2 13 项 | 23 passed | 0 |
| `batch-a-focus.txt` | Batch A 六个聚焦文件 | 155 passed | 0 |
| `frozen-and-v1.txt` | A1-02/A1-03/V1 冻结回归 | 605 passed | 0 |
| `pytest-full-sqlite.txt` | 根级 SQLite/Core 全量 | 1085 passed, 178 skipped | 0 |
| `ruff.txt` | `uv run ruff check` | All checks passed | 0 |
| `frontend.txt` | Vitest + typecheck + build | 72 tests passed；typecheck/build 通过 | 0 |

`178 skipped` 与 PG 门控模块收集数一致；本机无 `EXPLAINLAB_PG_TEST_URL`，见
`../06-unverified/postgresql-environment.txt`。**不等同于 PostgreSQL 验证通过。**

## 23 项新增测试映射

### P1：ImportOrigin + MATERIALIZE 并存（10 项）

文件：`backend/tests/test_markdown_batch_a_identity.py::TestMaterializeOriginConflict`

| 测试 | 场景 | 核心断言 |
| --- | --- | --- |
| `test_single_materialize_plus_single_complete_origin` | 单条完整 origin + 单条 MATERIALIZE | 状态 3；complete 也不得状态 1 |
| `test_single_materialize_plus_multiple_complete_origins` | 多条完整 origin + MATERIALIZE | 状态 3；原始 origin 保留 |
| `test_materialize_plus_incomplete_origin` | 残缺 origin + MATERIALIZE | 状态 3 |
| `test_materialize_plus_duplicate_origin` | 重复 origin + MATERIALIZE | 状态 3 |
| `test_materialize_plus_multiple_legal_identity_pairs` | 多合法身份对 + MATERIALIZE | 状态 3；不选可信对 |
| `test_materialize_and_origin_same_instance_id` | 同实例 ID | 状态 3；不因 ID 相同而认领 |
| `test_materialize_and_origin_different_instance_id` | 异实例 ID | 状态 3 |
| `test_multiple_materialize_records_plus_origin_still_conflict` | 多条 MATERIALIZE + origin | 状态 3；归档条数不变 |
| `test_control_normal_import_without_materialize_is_state_1` | 正常导入控制组 | 状态 1；无归档 |
| `test_control_local_materialize_without_origin_is_state_2b` | 正常本地物化控制组 | 状态 2b；无 origin |

冲突测试共用 `_assert_record_conflict_readonly`，逐项断言：

- 分类为状态 3，`source_instance_id` / `source_document_id` 为 `None`；
- 单篇导出返回 200，但不带来源头、正文不含 `source_instance_id`；
- `ensure_local_export_identity` 与 `materialize` 均抛 `SOURCE_DOCUMENT_UNMATERIALIZED`；
- 审计摘要、快照、ImportOrigin、item 的 `source_instance_id`、归档条数均不变；
- current Journal 不存在（零身份写入、零自动覆盖）。

### P2：完整写入与故障注入（13 项）

文件：`backend/tests/test_batch_a_file_write.py`

| 测试 | 注入点 | 核心断言 |
| --- | --- | --- |
| `TestWriteAll::test_partial_then_complete` | 首次短写，余量续写 | 最终字节完整 |
| `TestWriteAll::test_many_one_byte_writes` | 每次只写 1 字节 | 循环直到写完 |
| `TestWriteAll::test_zero_write_fails` | 返回 0 | 抛 `OSError(EIO)` |
| `TestWriteAll::test_exception_propagates_without_remaining_write` | 中途异常 | 原异常传播，不再写 |
| `TestWriteAll::test_empty_payload_is_noop` | 空 payload | 不调用写、不报错 |
| `TestJournalWriteFailure::test_current_write_failure_publishes_nothing` | current 写异常 | 无 current 发布、无 COMMITTED |
| `TestJournalWriteFailure::test_current_half_write_is_not_renamed_into_place` | current 半写后失败 | 临时文件不 rename，正式 current 不存在 |
| `TestJournalWriteFailure::test_archive_write_failure_keeps_committed_current_then_recovers` | archive 写异常 | 保留有效 COMMITTED current；重启补归档 |
| `TestInstanceIdWriteFailure::test_create_write_failure_publishes_no_id` | 创建写异常 | 无正式 ID、无临时残留 |
| `TestInstanceIdWriteFailure::test_create_half_write_is_not_linked_into_place` | 创建半写 | 不 link 为正式 ID |
| `TestInstanceIdWriteFailure::test_create_fallback_half_write_removes_partial_formal_file` | 无硬链接 + fallback 半写 | 删除半成品正式文件 |
| `TestInstanceIdWriteFailure::test_replace_write_failure_preserves_old_id` | 替换写异常 | 旧 ID 完整保留 |
| `TestInstanceIdWriteFailure::test_replace_half_write_preserves_old_id` | 替换半写 | 旧 ID 完整保留，不发布截断 ID |

## 回归范围说明

- `batch-a-focus.txt`：`test_batch_a_canonical.py`、`test_markdown_batch_a_import_export.py`、
  `test_markdown_batch_a_identity.py`、`test_batch_a_process_and_identity.py`、
  `test_batch_a_file_write.py`、`knowledge-core/tests/test_markdown_service.py`。
- `frozen-and-v1.txt`：Core Markdown canonical/codec/frontmatter/service/links/link_service、
  Core 独立性守护 `test_interfaces.py`，以及 backend 链接/治理/知识 V1 回归。
- `pytest-full-sqlite.txt`：根 `pytest` 一次性收集 `backend/tests` 与 `knowledge-core/tests`，
  保留 `--import-mode=importlib`；未使用 `-o addopts=""`。
- `frontend.txt`：`npm run test`（10 文件 / 72 测试）、`npm run typecheck`、`npm run build`。

## 边界

- 测试只使用 SQLite 临时库与本地故障注入；未连接真实 PostgreSQL。
- 未注入真实 `ENOSPC`、`fsync`/`close` 失败、断电或 POSIX 文件系统。
- 未在 Uvicorn `--reload` / 多 worker / Windows ACL 场景下运行。
- 未提交、未推送。