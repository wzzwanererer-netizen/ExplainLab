# V2 · A1-04 · Batch A 验收报告

- 日期：2026-11-22
- 代码基线：`784b124` + 未提交 Batch A 工作树
- 验收人：本次自动化实施（待独立审计）
- 结论：**SQLite 范围内通过；真实 PostgreSQL 未验证；整体为“有条件通过”**。未提交、未推送、未进入 Batch B/下一里程碑。

## 1. 环境

- OS：Windows 10.0.26300（x64）
- Python：3.11（uv workspace，`.venv`）
- Node：v24.22.1（项目基线要求 ≥22.23.2）
- 数据库：SQLite 文件 + FTS5；每测试独立临时库
- PostgreSQL：**不可用**（无 `EXPLAINLAB_PG_TEST_URL`、`psql`、`pg_isready`、`docker`）
- 真实文件系统：OS 锁、`source-instance-id`、Journal/archive 均使用临时真实目录

## 2. 命令与结果

| 命令 | 结果 | 证据 |
|---|---|---|
| `uv run pytest -o addopts="--import-mode=importlib"` | **1062 passed, 178 skipped** | `evidence/pytest-full-sqlite.txt` |
| 聚焦 Batch A 五个测试文件（同上 importlib） | **132 passed** | `evidence/pytest-batch-a.txt` |
| `uv run ruff check` | **All checks passed** | `evidence/ruff-check.txt` |
| `cd frontend && npm run test` | **10 files / 72 tests passed** | `evidence/frontend-regression.txt` |
| `cd frontend && npm run typecheck` | 通过 | 同上 |
| `cd frontend && npm run build` | 通过（仅 chunk >500 kB 警告） | 同上 |
| PostgreSQL 专项 | 未执行；相关模块整体 skip | `evidence/postgresql-unverified.txt` |

178 项 skip 以 PostgreSQL 门控模块为主（`test_*_pg.py`、`test_retrieval_pg.py` 等），完整清单见全量日志；未将 skip 计为通过。

## 3. 验收 ID 映射

状态说明：`PASS` 已验证；`PARTIAL` 仅覆盖部分输入/缺少指定入口；`N/A` 属其他批次；`UNVERIFIED` 环境缺失。

### 3.1 R1.2-ID

| ID | 状态 | 测试/证据 |
|---|---|---|
| R1.2-ID-01 | PASS | `TestExportImportRoundTrip::test_single_export_contains_identity_and_exporter`、`test_zip_export_manifest_and_documents`；`TestExporterHashDecoupling::test_import_persists_no_exporter_value_or_column`（PRAGMA 无 exporter 列） |
| R1.2-ID-02 | PASS | `TestRotate::test_rotate_materializes_2a_keeps_imported_identity_and_exporter`：导入来源 X 在 rotate 到 Z 后仍为 X，exporter=Z |
| R1.2-ID-03 | PARTIAL | 同上，服务层 ROTATE 后继承文档来源不改写；**未提供 `rotate-instance-id` CLI** |
| R1.2-ID-04 | PASS | `test_same_identity_versions_are_complete`；`test_multiple_origins_for_same_identity_are_ambiguous`；pending 复用/冲突用例 |
| R1.2-ID-05 | PASS | `TestLegacyIdentity` 四项：半身份、非字符串、无身份、显式 target 冲突 |
| R1.2-ID-06 | PASS | `test_half_identity_is_legacy_and_never_persisted`、`test_non_string_identity_is_legacy_and_stripped` |
| R1.2-ID-07 | N/A | Backup/Restore 属 Batch C；本批未实现、未宣称 |
| R1.2-ID-08 | PASS | `test_export_then_reimport_same_instance_updates_same_identity`、`test_zip_reimport_is_idempotent` |

### 3.2 R1.2-BAT

| ID | 状态 | 说明 |
|---|---|---|
| R1.2-BAT-01 | PASS | 单篇附件固定码拒绝、零写入；批量逐项 `UNSUPPORTED` |
| R1.2-BAT-02 | PASS | 导出含附件固定码 `ATTACHMENT_EXPORT_UNSUPPORTED` |
| R1.2-BAT-03 | PASS | 本报告与实施报告未宣称附件/GC/Backup 完成 |
| R1.2-BAT-04 | N/A | Batch B 附件 staging |
| R1.2-BAT-05 | PASS | 本批独立验收；未以其他批次代替 |
| R1.2-BAT-06 | PASS | 文档范围明确限定 Batch A |

### 3.3 R1.2-ASYNC

| ID | 状态 | 测试 |
|---|---|---|
| ASYNC-01 | PASS | `test_write_routes_are_sync_def`：import/batch/export/approve/reject 均为同步 `def` |
| ASYNC-02 | PASS | `test_s0_is_closed_before_lock_and_sessions_stay_on_one_thread`：Session 创建/关闭线程 ID 唯一 |
| ASYNC-03 | PASS | 同上：S0 close 先于 lock-enter；`_import_one` 顺序断言 |
| ASYNC-04 | PASS | `test_exception_rolls_back_closes_session_before_lock_release`：apply → rollback → close → lock-exit |
| ASYNC-05 | PASS | `test_single_import_lock_timeout_maps_to_409`、`test_batch_import_isolates_lock_timeout_per_item`、Coordinator 超时测试；默认 10s 断言 |
| ASYNC-06 | PASS | `test_no_async_lock_architecture`：AST 无 `AsyncFunctionDef`、无 `asyncio.Lock/Semaphore`；运行时只有 `threading.Lock` |
| ASYNC-07 | PASS | `test_same_identity_concurrent_requests_serialize`（1 item/1 origin）、`test_different_identities_concurrent_requests_both_succeed`（2/2）、Coordinator 同键/异键测试 |
| ASYNC-08 | PASS | `test_event_loop_stays_responsive_while_import_waits_on_lock`：锁等待期间 ticker ≥5 次 |

### 3.4 R1.3-HASH

| ID | 状态 | 测试/证据 |
|---|---|---|
| HASH-01 | PASS | `test_exporter_changes_text_but_not_hashes`：两 exporter 文本不同、content/payload Hash 相同 |
| HASH-02 | PASS | `test_import_strips_exporter_and_hash_matches_without_key`、`test_import_persists_no_exporter_value_or_column` |
| HASH-03 | PASS | 四类冲突：`test_duplicate_reserved_key_rejected_before_any_write`、`test_manifest_exporter_mismatch_rejected_zero_writes`、`test_db_metadata_reserved_key_rejected_zero_writes`、`test_nested_reserved_key_in_user_metadata_rejected_zero_writes`；均查 item/origin 未变 |
| HASH-04 | PASS | `TestExporterHashDecoupling` + `frozen-contracts.txt`：Core Hash/canonical/codec 与 schema 无改动 |

### 3.5 R1.3-ID

| ID | 状态 | 测试/证据 |
|---|---|---|
| ID-01 | PASS | `test_imported_item_state_1_uses_origin_identity`：来源取自 ImportOrigin，不用新 UUID/`item.id` |
| ID-02 | PARTIAL | `test_state_2a_first_export_materializes_once`、`test_restart_keeps_2b_and_hash_stable`、Journal PREPARED/COMMITTED/损坏/摘要/current+archive 用例；ImportOrigin 多记录 9 项。**未逐一注入全部归档临时文件/rename/目录同步崩溃点** |
| ID-03 | PASS | `test_state_4_without_committed_evidence_is_not_claimed`、`test_incomplete_origin_is_state_3_zero_claim`、`test_corrupt_current_blocks_import_before_any_write`、`test_checksum_mismatch_fails_closed_before_db_write`、冲突/重复/非法 origin 用例；导出不认领 |
| ID-04 | PASS | `test_multiple_origins_for_same_identity_are_ambiguous`：`SOURCE_IDENTITY_AMBIGUOUS`、零写入 |
| ID-05 | PARTIAL | 2a/2b/导入/状态 3/状态 4、两次 rotate、PREPARED 旧 ID/新 ID 恢复均通过；**CLI、归档临时文件/rename/目录同步逐点崩溃、POSIX 实机未覆盖** |

ImportOrigin 判别用例（ID-02/03/05 共同覆盖）：单条 complete、两条 duplicate、完整+残缺、两合法身份对 conflict、DB 实例不一致 conflict、同一身份多版本 complete、非法字段 invalid、原始字段变化导致摘要变化、孤儿 fail-closed。未用时间/ID/Hash 任选一条。

### 3.6 R1.1 Batch A 相关属性

| 组 | 状态 | 说明 |
|---|---|---|
| R1.1-IMP-25/26/27 | PASS（既有套件） | V1 GET/PATCH 与 MarkdownItemRepository 回归在全量套件中通过 |
| R1.1-IMP-28/29/30/31 | PASS | 首建/重启稳定/损坏 fail-closed/导出携带；跨进程并发创建同一 ID |
| R1.1-IMP-32/33/34/40 | PASS | 引用计数归零、同/异键、lifespan 单例 coordinator（`app.state` 断言） |
| R1.1-IMP-35/37 | PASS | 既有导入/review 并发与重读用例；S0→S1 变化检测 |
| R1.1-IMP-36/38/39 | PASS | approve hook 故障回滚、锁覆盖事务、异常路径先清理后释放 |
| R1.1-SQL-10 | PASS | ASYNC-08 event loop 探针 |
| R1.1-LOCK-09/11/13 | PASS | 绝对路径、同进程注册表、跨进程拒绝、崩溃释放 |
| R1.1-LOCK-10/12 | PARTIAL | 未执行真实 Uvicorn `--reload` 交接；多 worker 仅代码/启动守卫，未起实际多 worker |
| R1.1-LNK-14 | PASS（既有套件） | A1-03 链接回归全量通过 |

## 4. 零写入与故障注入证据

- D22 四类冲突：预检抛稳定码，测试查询条目数/来源数/元数据均未变。
- `SOURCE_IDENTITY_AMBIGUOUS`：导入报错，无新 item/origin。
- 锁超时：单篇 409，目标条目标题未变；批量另一篇仍成功。
- Journal：
  - PREPARED + DB 空 → 幂等补写后归档；
  - PREPARED + DB 其他值 → `SOURCE_IDENTITY_INCONSISTENT`，DB 不变、current 保留；
  - 损坏 JSON / 校验和不符 → `SOURCE_IDENTITY_JOURNAL_CORRUPT`，恢复前禁止导入/分类/写身份；
  - COMMITTED 未归档 → 只归档，`updated_at` 不变；
  - current+archive 同 operation_id 同内容 → 计一条；
  - 孤儿 ImportOrigin → `SOURCE_IDENTITY_ORPHAN`。
- 进程锁：真实子进程竞争被拒；子进程崩溃后 OS 释放；parent release 后子进程可获取。

## 5. PostgreSQL

**未验证，未伪造。**

检查结果：

```
EXPLAINLAB_PG_TEST_URL=<unset>
pg_isready=<not found>
psql=<not found>
docker=<not found>
```

相关 PG 模块全部 skip。Batch A 的写入/身份实现按 AGENTS 方言边界未引入 FTS5/MATCH/bm25/rowid；但“真实 PG 上执行迁移、导入导出、身份 Journal、并发锁”仍需在具备实例的环境补验。

## 6. 兼容性与冻结面

- `git status`：`pyproject.toml`、`uv.lock`、前端锁文件、`backend/alembic/` 无改动。
- Core `ports.py`、`ReviewService`、A1-02 `codec.py`/`canonical.py`、A1-03 `locking.py`/`links.py` 无改动。
- Core 独立性守护测试通过。
- V1 API/GET 行为未改；导入新增字段不进入 V1 响应模型。
- 未删改 M0 初始提交；未提交、未推送。

## 7. 验收结论

| 维度 | 结论 |
|---|---|
| Batch A 业务闭环（SQLite） | 通过（覆盖范围内） |
| Batch A 全量回归 | 通过：1062 passed |
| 前端回归 | 通过 |
| 真实 PostgreSQL | **未验证** |
| R1.3-ID-02/05 完整崩溃矩阵 | **部分覆盖** |
| `rotate-instance-id` CLI | **未实现/未验收** |
| 附件 | 按范围拒绝，未宣称完成 |

**整体：有条件通过，等待独立审计。** 未宣布进入 Batch B 或下一里程碑。