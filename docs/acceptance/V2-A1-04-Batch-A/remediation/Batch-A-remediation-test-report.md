# V2 · A1-04 · Batch A 整改测试报告

- 日期：2026-11-22
- 基线 HEAD：`784b1248065424e07273b272d6016cc121bc606c`
- 工作树：未提交；未推送
- 结论：P1/P2 专项与 SQLite 全量通过；真实 PostgreSQL 未验证

## 1. 命令结果

| # | 命令 | 结果 | 原始输出 |
|---|---|---|---|
| 1 | `uv run pytest -o addopts="--import-mode=importlib"` | **1085 passed, 178 skipped** | `evidence/01-pytest-full-sqlite.txt` |
| 2 | Batch A 聚焦（6 文件，含新增 P2 测试） | **155 passed** | `evidence/02-pytest-batch-a-focus.txt` |
| 3 | A1-02/A1-03/V1 冻结集合 | **605 passed** | `evidence/03-frozen-and-v1.txt` |
| 4 | P1 并存冲突专项 | **10 passed** | `evidence/07-p1-conflict-tests.txt` |
| 5 | P2 短写故障注入专项 | **13 passed** | `evidence/08-p2-write-fault-tests.txt` |
| 6 | `uv run ruff check` | All checks passed | `evidence/04-ruff.txt` |
| 7 | 前端 `npm run test && npm run typecheck && npm run build` | 72 passed；通过；通过 | `evidence/05-frontend.txt` |
| 8 | PostgreSQL 环境检查 | 不可用；PG 模块 skip | `evidence/06-postgresql-unverified.txt` |

全量用例数较整改前 `1062` 增加 **23**：P1 10 项、P2 13 项。

## 2. 测试文件

| 文件 | 总用例 | 本次新增 |
|---|---:|---:|
| `backend/tests/test_markdown_batch_a_identity.py` | 36 | 10（`TestMaterializeOriginConflict`） |
| `backend/tests/test_batch_a_file_write.py` | 13 | 13（新文件） |
| 其他 Batch A/Core 聚焦文件 | 106 | 0 |

## 3. P1 覆盖映射

| 审计要求 | 测试 | 结果 |
|---|---|---|
| 单条 MATERIALIZE + 单条完整 ImportOrigin | `test_single_materialize_plus_single_complete_origin` | PASS |
| 单条 MATERIALIZE + 多条完整 ImportOrigin | `test_single_materialize_plus_multiple_complete_origins` | PASS |
| MATERIALIZE + 残缺 ImportOrigin | `test_materialize_plus_incomplete_origin` | PASS |
| MATERIALIZE + 重复 ImportOrigin | `test_materialize_plus_duplicate_origin` | PASS |
| MATERIALIZE + 多个不同合法身份对 | `test_materialize_plus_multiple_legal_identity_pairs` | PASS |
| 同实例 ID | `test_materialize_and_origin_same_instance_id` | PASS |
| 不同实例 ID | `test_materialize_and_origin_different_instance_id` | PASS |
| 多条 MATERIALIZE 记录 + ImportOrigin | `test_multiple_materialize_records_plus_origin_still_conflict` | PASS |
| 无 MATERIALIZE 的正常导入控制组 | `test_control_normal_import_without_materialize_is_state_1` | PASS |
| 无 ImportOrigin 的正常本地物化控制组 | `test_control_local_materialize_without_origin_is_state_2b` | PASS |

每个冲突用例统一调用 `_assert_record_conflict_readonly`，断言：

1. `classify` 返回状态 **3**，`source_instance_id/source_document_id` 均为 `None`；
2. 单篇导出 200，但不写来源身份头，正文不含 `source_instance_id`；
3. `ensure_local_export_identity` 与 `materialize` 均抛稳定码 `SOURCE_DOCUMENT_UNMATERIALIZED`；
4. `identity_audit_digest` 前后完全一致；
5. 完整身份快照（含每条 ImportOrigin 原始字段、状态、数量）前后完全一致；
6. `knowledge_item.source_instance_id` 不变；
7. Journal archive 数量不变，current 不存在；
8. 不删除、不合并、不覆盖任何身份记录。

## 4. P2 覆盖映射

### 4.1 统一写入封装

| 要求 | 测试 | 结果 |
|---|---|---|
| 第一次只写一半，第二次完成 | `TestWriteAll::test_partial_then_complete` | PASS |
| 连续多次部分写入 | `TestWriteAll::test_many_one_byte_writes` | PASS |
| 返回 0 必须失败 | `TestWriteAll::test_zero_write_fails` | PASS |
| 写入异常传播且停止后续写 | `TestWriteAll::test_exception_propagates_without_remaining_write` | PASS |
| 空负载 no-op | `TestWriteAll::test_empty_payload_is_noop` | PASS |

### 4.2 集成故障注入

| 要求 | 测试 | 结果 |
|---|---|---|
| current Journal 写入失败不发布 | `test_current_write_failure_publishes_nothing` | PASS |
| current 半写不得 rename 发布 | `test_current_half_write_is_not_renamed_into_place` | PASS |
| archive 写入失败不误标/不发布 | `test_archive_write_failure_keeps_committed_current_then_recovers` | PASS |
| 实例 ID 首次创建写入失败 | `test_create_write_failure_publishes_no_id` | PASS |
| 实例 ID 创建半写不得 link 发布 | `test_create_half_write_is_not_linked_into_place` | PASS |
| 无硬链接 fallback 半写清理半成品 | `test_create_fallback_half_write_removes_partial_formal_file` | PASS |
| 实例 ID 替换写入失败保留旧 ID | `test_replace_write_failure_preserves_old_id` | PASS |
| 实例 ID 替换半写保留旧 ID | `test_replace_half_write_preserves_old_id` | PASS |

关键断言：

- current 失败：DB `source_instance_id` 仍为空；无 current；无 archive；无 `.tmp` 残留。
- current 半写：target 不存在；临时文件清理。
- archive 失败：DB 已写、current 为合法 COMMITTED；archive 为空；无 archive `.tmp`；
  monkeypatch 解除后重启恢复成功归档，current 移除。
- 实例 ID 创建/替换/fallback 失败：正式 ID 文件不存在或保持旧值；无 `.tmp` 残留。

## 5. 回归范围

全量套件覆盖：

- Batch A 导入/导出、D22 冲突、legacy、审核 hook、附件边界；
- 身份 1/2a/2b/3/4、ImportOrigin 多记录、Journal 恢复/归档、ROTATE；
- 进程锁、coordinator、同步线程模型、并发、event loop；
- Canonical JSON v1 八组向量与重复键；
- A1-02 Markdown codec/frontmatter/canonical；
- A1-03 链接/治理/并发/phantom/no-op；
- V1 knowledge/governance/health 等既有回归。

`A1-02/A1-03/V1 冻结集合` 单列结果：**605 passed**。

## 6. PostgreSQL

- `EXPLAINLAB_PG_TEST_URL` 未设置；
- `pg_isready`、`psql`、`docker` 均不存在；
- PG 门控模块全部 skip；
- 未执行真实 PG 迁移/导入导出/身份 Journal/并发锁；
- 未把 SQLite 结果写成 PG 通过。

## 7. 冻结面检查

`evidence/11-frozen-and-files.txt`：

- `pyproject.toml`、`uv.lock`、前端锁文件、`backend/alembic`：无改动；
- Core `ports.py`、`ReviewService`、A1-02 `codec.py`/`canonical.py`、A1-03 `locking.py`/`links.py`：无改动；
- 本次仅新增 `file_write.py` 与两个测试改动。

## 8. 结论

| 项 | 状态 |
|---|---|
| P1 专项 | 已验证 |
| P2 专项 | 已验证 |
| SQLite 全量 | 已验证 |
| Core/A1-02/A1-03/V1 回归 | 已验证 |
| 前端回归 | 已验证 |
| 真实 PostgreSQL | **未验证** |
| 提交/推送 | 未执行 |

等待第二轮独立审计。