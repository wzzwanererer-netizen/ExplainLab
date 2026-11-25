# 测试证据索引

## 1. 环境

- Windows 10.0.26300 x64 真机
- Python 3.11.9（`uv run`）
- SQLite 3.45.1（真实临时文件库）
- 真实 `tmp_path` 文件系统
- 未设置 `EXPLAINLAB_PG_TEST_URL`
- 无 mock 文件系统/数据库

## 2. B3-T01 专项测试

`backend/tests/test_attachment_staging.py`：**54 passed / 0 failed / 0 skipped / exit 0**（整改前 34，本轮新增 20）。

覆盖矩阵（初版 34 项）：

| 要求区域 | 代表测试 |
|---|---|
| manifest round-trip、`.complete` | `test_manifest_round_trip_and_complete_marker` |
| 未知字段、严格类型/边界 | `test_unknown_fields_and_strict_bounds` |
| 重复 storage_key | `test_duplicate_storage_key_rejected_before_staging` |
| 重复 ordinal / staging_id | `test_validate_manifest_duplicate_ordinal_key_and_staging_id` |
| Zip Slip/绝对/UNC/ADS | `test_zip_traversal_absolute_unc_ads_backslash_rejected[...]` |
| 重复路径、大小写冲突 | `test_duplicate_exact_and_case_normalized_paths_rejected` |
| 归属歧义 | `test_ambiguous_ownership_is_rejected_whole` |
| 数量与 ZIP bomb | `test_attachment_count_and_zip_bomb_limits` |
| MIME 伪装 | `test_mime_mismatch_rejected_before_staging` |
| 缺文件、缺 `.complete` | `test_missing_blob_and_missing_complete_are_invalid` |
| hash 不符、额外文件 | `test_hash_mismatch_and_unexpected_file_are_invalid` |
| `.creating/.activity` 活动时间 | `test_activity_uses_marker_and_file_mtime_not_root` |
| symlink/junction | `test_symlink_or_junction_in_staging_rejected` |
| 额外空目录 | `test_empty_extra_directory_is_invalid` |
| 根重叠、非法 staging id | `test_overlapping_roots_and_invalid_ids_rejected` |
| Active 附件-only 零 staging | `test_active_attachment_only_rejected_with_zero_staging` |
| pending 完整 manifest、零正式引用 | `test_active_content_change_creates_pending_manifest_zero_formal_refs` |
| 同来源同集合复用 | `test_same_source_same_attachment_set_reuses_pending` |
| pending staging 损坏 fail-closed | `test_reuse_pending_with_invalid_staging_fails_closed` |
| 不同集合冲突 | `test_different_attachment_set_conflicts_without_new_staging` |
| 零文档附件-only/unsupported | `test_zero_document_attachment_zip_is_attachment_only_or_unsupported` |
| 已应用附件满足 | `test_already_applied_same_hash_with_satisfied_attachment_is_skipped` |
| pending 有附件、新请求空集合 | `test_pending_with_attachments_rejects_same_hash_empty_set` |
| 归档目标 | `test_archived_target_with_attachment_zip_rejected` |
| JSON 单篇/批量入口 | `test_single_and_batch_json_attachment_compatibility` |
| ZIP 借用 JSON 附件字段 | `test_attachment_zip_cannot_borrow_json_attachment_fields` |
| 无附件 ZIP 多篇 | `test_zip_without_attachments_still_supports_multiple_docs` |
| discard/sweep | `test_discard_respects_pending_and_sweep_activity` |
| 失败不留 `.complete` | `test_missing_staging_and_failed_complete_do_not_look_complete` |

整改新增 20 项（4 个文件/类，参数化展开后 20 个用例）：

| 要求 | 类 / 测试 | 结果 |
|---|---|---|
| P1-01 guard 覆盖创建、提交后释放 | `TestStagingGuardLifetime::test_guard_covers_creation_and_releases_after_commit` | pass |
| P1-01 业务 commit 期间 guard 被持有 | `TestStagingGuardLifetime::test_guard_held_during_business_commit` | pass |
| P1-01 已知提交前失败清理 | `TestStagingGuardLifetime::test_known_precommit_failure_cleans_staging` | pass |
| P1-01 提交结果不明确保留 staging | `TestStagingGuardLifetime::test_ambiguous_commit_keeps_staging_for_orp` | pass |
| P1-02 目录同步失败 503、无 pending | `TestDirectoryDurability::test_directory_sync_failure_rejects_without_pending` | pass |
| P1-02 平台显式语义 | `TestDirectoryDurability::test_directory_sync_is_platform_explicit` | pass |
| P2-01 零字节 .txt/.md/.csv | `TestEmptyAttachmentRejection::test_zero_byte_attachment_rejected_before_staging[...]` | 3 pass |
| P2-02 CRC 不匹配 | `TestCorruptZipMapping::test_crc_mismatch_maps_to_import_archive_invalid` | pass |
| P2-02 非法 Deflate | `TestCorruptZipMapping::test_invalid_deflate_stream_maps_to_import_archive_invalid` | pass |
| P2-02 截断 Deflate | `TestCorruptZipMapping::test_truncated_deflate_maps_to_import_archive_invalid` | pass |
| P2-03 无 factory discard fail-closed | `TestPendingFailClosed::test_missing_session_factory_discard_fails_closed` | pass |
| P2-03 无 factory sweep fail-closed | `TestPendingFailClosed::test_missing_session_factory_sweep_fails_closed` | pass |
| P2-03 查询异常保留 staging | `TestPendingFailClosed::test_pending_query_failure_preserves_staging` | pass |
| ZIP 原始文件名 NUL | `TestZipBudgetBoundaries::test_original_nul_filename_rejected` | pass |
| 全 ZIP 压缩预算含未选中项 | `TestZipBudgetBoundaries::test_whole_archive_compressed_budget_includes_unselected` | pass |
| 根 manifest 计入预算 | `TestZipBudgetBoundaries::test_root_manifest_is_included_in_budget` | pass |
| pending 复用 guard 内校验 | `TestPendingReuseGuard::test_reuse_validates_manifest_under_guard` | pass |
| pending 复用 guard 内重读 | `TestPendingReuseGuard::test_reuse_rereads_pending_under_guard` | pass |

## 3. 原始日志

### 3.1 整改后（本轮）

| 文件 | 结果 | exit |
|---|---|---:|
| `evidence/remediation/b3-t01-special.log` | 54 passed, 2 warnings | 0 |
| `evidence/remediation/b1-b2-regression.log` | 201 passed, 8 skipped | 0 |
| `evidence/remediation/batch-a-regression.log` | 166 passed | 0 |
| `evidence/remediation/full-regression.log` | 1450 passed, 213 skipped | 0 |
| `evidence/remediation/ruff-source.log` | All checks passed | 0 |
| `evidence/remediation/ruff-repo.log` | 8 errors，均为此前未跟踪文档证据副本，非源码 | 1 |
| `evidence/remediation/git-diff-check.log` | 仅 CRLF 提示 | 0 |
| `evidence/remediation/real-100mib-boundary.log` | 104 857 601 B ZIP 拒绝为 `IMPORT_ARCHIVE_INVALID` | 0 |

### 3.2 整改前（初版）

| 文件 | 结果 | exit |
|---|---|---:|
| `evidence/b3-staging-windows.log` | 34 passed, 2 warnings | 0 |
| `evidence/b1-b2-regression-windows.log` | 243 passed, 7 skipped | 0 |
| `evidence/batch-a-import-export-windows.log` | 84 passed | 0 |
| `evidence/backend-core-full-windows.log` | 1430 passed, 213 skipped | 0 |
| `evidence/backend-core-full-skip-reasons.log` | 同上，含 `-rs` skip 原因 | 0 |
| `evidence/ruff-backend-core.log` | All checks passed | 0 |
| `evidence/git-diff-check.txt` | 仅 CRLF 提示 | 0 |

## 4. Skip 说明

全量 213 skip：

- **210 项真实 PostgreSQL 环境门控**：`EXPLAINLAB_PG_TEST_URL` 未设置；
- **3 项平台/卷门控**：
  1. Linux real filesystem mount required；
  2. Windows 文件默认拒绝 rename 的路径替换取证；
  3. no writable second Windows volume selected。

**skip 不是 pass。** 本轮没有真实 PostgreSQL，不声明 PG/staging 路由验证通过；没有第二 Windows 卷，不声明真实跨卷通过；没有 POSIX 主机，不声明目录 fsync 真实验证通过。

B1/B2 定向回归 8 skip 同样为 PG/Windows 平台门控。

`ruff-repo.log` 的 8 个错误位于未跟踪的历史文档证据副本（B1-environment-recovery 证据脚本、freeze-review-package 的 0006 迁移副本），不在 `backend/` 与 `knowledge-core/` 源码；`ruff-source.log` 为源码实际检查结果。

## 5. 运行命令

```bash
# B3-T01 专项
uv run pytest -q backend/tests/test_attachment_staging.py -o addopts=""

# B1/B2 回归
uv run pytest -q backend/tests/test_attachment_api.py \
  backend/tests/test_attachment_storage.py \
  backend/tests/test_attachment_validation.py \
  backend/tests/test_attachment_gc.py \
  backend/tests/test_storage_lock_sqlite.py -o addopts=""

# Batch A 回归
uv run pytest -q backend/tests/test_markdown_batch_a_import_export.py \
  backend/tests/test_markdown_batch_a_import_conflict.py \
  backend/tests/test_markdown_batch_a_identity.py -o addopts=""

# Backend + Core 全量（保留 importlib，完整汇总）
uv run pytest -o addopts="--import-mode=importlib" -rs

# Lint 与空白检查
uv run ruff check backend knowledge-core
git diff --check
```

真实 100 MiB 边界脚本与日志：

```bash
uv run python docs/acceptance/V2-A1-04-Batch-B-B3-T01/evidence/remediation/real-100mib-boundary.py
```