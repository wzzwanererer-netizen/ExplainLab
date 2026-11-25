# B2 · ATT-01…13 验收映射（基于真实日志与真实测试）

**状态：B2 IMPLEMENTED / PENDING INDEPENDENT REVIEW。**
本映射只陈述已经发生的真实执行结果；`PostgreSQL HTTP 路径` 未执行，不能以 SQLite
结果替代。所有测试均使用**真实 SQLite 文件库 + `tmp_path` 真实文件系统**，不 mock
数据库或文件系统。

## 1. 总表

| 验收 | 冻结要求摘要 | B2 证据（测试/文件） | 当前状态 |
|---|---|---|---|
| ATT-01 | 上传成功、行/分片 blob/哈希/无临时残留，下载头正确 | `test_upload_png_creates_row_blob_and_download_headers`（`test_attachment_api.py:92`） | SQLite + 真实文件系统已验证；PG HTTP 未验证 |
| ATT-02 | 同内容同 item 幂等；跨 item 共享一份物理 blob | `test_same_content_two_items_shares_one_physical_blob`（:140）；`test_concurrent_same_item_upload_reuses_one_reference`（:526）；`test_concurrent_different_items_share_one_physical_blob`（:542） | SQLite + 真实文件系统已验证；PG HTTP 未验证 |
| ATT-03 | 超限/非法 Base64/空内容拒绝且零写入 | `test_size_and_base64_limits_write_nothing`（:165） | SQLite + 真实文件系统已验证；PG HTTP 未验证 |
| ATT-04 | 二进制 magic 校验；文本 UTF-8；文本子类型 | `test_content_mismatch_svg_and_text_subtypes`（:190）；`test_pdf_is_accepted_and_declared_magic_is_checked`（:130） | SQLite + 真实文件系统已验证；PG HTTP 未验证 |
| ATT-05 | SVG 拒绝；文本 SVG 按文本保存 | `test_content_mismatch_svg_and_text_subtypes`（:190） | SQLite + 真实文件系统已验证；PG HTTP 未验证 |
| ATT-06 | 文件名清洗（路径/控制字符/Windows 保留名/RFC 5987） | `test_filename_is_sanitized_and_extra_fields_rejected`（:233） | SQLite + 真实文件系统已验证；PG HTTP 未验证 |
| ATT-07 | 下载内容/长度/头正确；跨 item 不泄漏 | `test_upload_png_creates_row_blob_and_download_headers`（:92）；`test_unknown_item_and_cross_item_do_not_leak`（:290） | SQLite + 真实文件系统已验证；PG HTTP 未验证 |
| ATT-08 | 删除最后引用入队 GC；共享引用不入队；物理文件保留 | `test_delete_last_reference_enqueues_gc_but_shared_reference_does_not`（:315）；`test_delete_does_not_duplicate_active_gc_task`（:347） | SQLite + 真实文件系统已验证；PG HTTP 未验证 |
| ATT-09 | 损坏/缺失 blob 稳定 503；下载同一已校验句柄；不覆盖损坏 | `test_corrupted_and_missing_blob_return_503`（:408）；`test_upload_repairs_missing_blob_for_existing_reference`（:432）；`test_upload_refuses_to_reuse_corrupted_blob`（:444）；`test_download_streams_the_same_verified_handle`（:573）；`test_large_text_download_is_streamed_from_verified_handle`（:560） | SQLite + 真实文件系统已验证；PG HTTP 未验证 |
| ATT-10 | 并发上传串行化、唯一物理文件、引用正确 | `test_concurrent_same_item_upload_reuses_one_reference`（:526）；`test_concurrent_different_items_share_one_physical_blob`（:542） | SQLite 真实并发已验证；PG HTTP 未验证 |
| ATT-11 | 提交失败/归档竞态零引用与残留边界 | `test_commit_failure_leaves_no_row_but_published_blob`（:507）；`test_archive_committed_after_publish_leaves_zero_references`（:388）；`test_archived_failure_releases_key_lock_after_rollback`（:479） | **部分**：提交失败与归档竞态已验证；**24h ORP 收敛未实现（B5），未验证** |
| ATT-12 | 发布/存储错误稳定码映射 | B1 真实文件系统测试（`test_attachment_storage.py`、`test_attachment_windows.py`）；B2 映射测试 `test_storage_lock_timeout_returns_409_and_writes_nothing`（:458）、`test_corrupted_and_missing_blob_return_503`（:408） | B1 真实文件系统已验证；B2 映射已验证；PG HTTP 未验证 |
| ATT-13 | 列表只读排序；archived 上传 409、列表/下载/删除允许；归档竞态零引用 | `test_list_sorts_by_created_at_then_id`（:595）；`test_archived_blocks_upload_but_allows_list_download_delete`（:363）；`test_archive_committed_after_publish_leaves_zero_references`（:388） | SQLite + 真实文件系统已验证；PG HTTP 未验证 |

## 2. 22 项 B2 API 测试与覆盖面

| # | 测试 | 覆盖 |
|---|---|---|
| 1 | `test_upload_png_creates_row_blob_and_download_headers` | 201、行、分片路径、sha256、下载头、无临时残留 |
| 2 | `test_pdf_is_accepted_and_declared_magic_is_checked` | PDF magic、声明 MIME 不一致 415 |
| 3 | `test_same_content_two_items_shares_one_physical_blob` | 跨 item 共享、物理一份、两行、同 item 200 幂等 |
| 4 | `test_size_and_base64_limits_write_nothing` | 413/400、零 DB/FS 写入 |
| 5 | `test_content_mismatch_svg_and_text_subtypes` | 文本/二进制 magic、SVG 拒绝、文本子类型、文本 SVG 允许 |
| 6 | `test_filename_is_sanitized_and_extra_fields_rejected` | 路径/控制字符/Windows 保留名/Unicode/RFC 5987/extra 422/缺字段 422 |
| 7 | `test_unknown_item_and_cross_item_do_not_leak` | 未知 item 404；跨 item 列表/下载/删除不泄漏 |
| 8 | `test_delete_last_reference_enqueues_gc_but_shared_reference_does_not` | 共享引用不入队；最后引用入队 pending；物理保留；重复删除 404 |
| 9 | `test_delete_does_not_duplicate_active_gc_task` | 活动 GC 任务去重 |
| 10 | `test_archived_blocks_upload_but_allows_list_download_delete` | archived 上传 409；列表/下载/删除允许；无临时残留 |
| 11 | `test_archive_committed_after_publish_leaves_zero_references` | 发布后归档：零引用、blob 孤儿、无临时残留 |
| 12 | `test_corrupted_and_missing_blob_return_503` | 损坏/缺失 blob 503；列表只读仍 200 |
| 13 | `test_upload_repairs_missing_blob_for_existing_reference` | 缺失 blob 在锁内重发并复用引用 |
| 14 | `test_upload_refuses_to_reuse_corrupted_blob` | 损坏 blob 不覆盖、409、无临时残留 |
| 15 | `test_storage_lock_timeout_returns_409_and_writes_nothing` | 锁等待超时 409、零写入 |
| 16 | `test_archived_failure_releases_key_lock_after_rollback` | 失败路径 rollback 后锁可再次获取 |
| 17 | `test_commit_failure_leaves_no_row_but_published_blob` | commit 失败 500、无行、blob 孤儿、无临时残留 |
| 18 | `test_concurrent_same_item_upload_reuses_one_reference` | 并发同 item：200/201、同一引用、唯一文件 |
| 19 | `test_concurrent_different_items_share_one_physical_blob` | 并发跨 item：两个 201、物理一份、两行 |
| 20 | `test_large_text_download_is_streamed_from_verified_handle` | >2 MiB 文本流式下载、长度正确 |
| 21 | `test_download_streams_the_same_verified_handle` | 路由使用同一服务句柄且关闭 |
| 22 | `test_list_sorts_by_created_at_then_id` | 列表按 created_at、id 排序 |

## 3. 未覆盖 / 未验证（不得写成 PASS）

1. **PostgreSQL HTTP 端到端**：本机未设置 `EXPLAINLAB_PG_TEST_URL`，上传/共享引用/
   归档保护均未在真实 PG 上执行。B2 代码中的 PG `SELECT ... FOR UPDATE` 分支存在，
   但未运行。不能以 SQLite 结果替代。
2. **ATT-11 的 24h ORP 收敛**：属 B5 GC/ORP worker，B2 未实现；B2 只证明提交失败
   与归档竞态下的当前状态（无行、blob 孤儿、无临时残留），不证明 24h 后自动收敛。
3. **共享引用并发删除 + GC 执行竞态**：B2 没有 ORP 闭环，也没有真实并发删除测试；
   顺序删除测试不能冒充并发 ORP 证据。
4. **POSIX/跨卷/进程崩溃/TOCTOU**：沿用 B1 环境边界；Windows 跳过项见
   `evidence/b1-only-regression-scope.log`。
5. **前端**：本包不覆盖前端，不声称前端验收。

## 4. 证据索引

- 原始输出：`evidence/b2-api.log`（22 passed，EXIT=0）。
- B1 定点回归：`evidence/b1-targeted-regression.log`（184 passed，3 skipped，EXIT=0）；
  复跑：`evidence/b1-targeted-regression-verification.log`。
- 全仓：`evidence/full-suite.log`（1394 passed，208 skipped，EXIT=0）。
- 跳过明细：`evidence/skip-summary.log`。
- Ruff：`evidence/ruff-backend-core.log`（All checks passed，EXIT=0）。
- 统计冲突核验：`test-count-verification.md`。