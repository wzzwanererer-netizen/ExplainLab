# B2 自测报告

**结论：B2 的 Windows + 真实 SQLite + tmp 文件系统路径已自测通过；真实 PostgreSQL HTTP 路径未执行。B2 未正式通过，待独立审核。**

## 1. 环境

| 项 | 值 |
|---|---|
| 日期 | 2026-11-24（北京时间） |
| 平台 | Windows 10.0.26300 x64 |
| Python | 3.11.9（uv workspace `.venv`） |
| SQLite | 3.45.1（真实文件库，非内存替身） |
| 数据库 | 每个测试 `tmp_path/test.db` + `tmp_path/data` 真实目录 |
| 文件系统 | `tmp_path` 真实分片目录、`.tmp`、`_quarantine` |
| PostgreSQL | **未配置** `EXPLAINLAB_PG_TEST_URL`，PG 用例整模块跳过 |
| 前端 | 未改动，未执行 |

## 2. 命令与结果

```bash
# B2 API 专项
uv run pytest backend/tests/test_attachment_api.py \
  -o addopts="--import-mode=importlib" -q
# 22 passed

# B1 附件存储/Windows 锁/GC + B2 API 合并回归
uv run pytest backend/tests/test_attachment_storage.py \
  backend/tests/test_attachment_windows.py \
  backend/tests/test_storage_lock_sqlite.py \
  backend/tests/test_attachment_gc.py \
  backend/tests/test_attachment_api.py \
  -o addopts="--import-mode=importlib" -q
# 184 passed, 3 skipped

# 全仓 backend + core
uv run pytest -o addopts="--import-mode=importlib" -q
# 1394 passed, 208 skipped

# Lint（只 check，不 format）
uv run ruff check backend knowledge-core
# All checks passed! EXIT=0
```

原始日志见 [`evidence/`](evidence/)。B1 定点回归数量曾出现 README/MILESTONES 的 184 与旧自测文本 182 的冲突，已按原始日志与复跑核验为 **184 passed, 3 skipped**，详见 [测试统计核验报告](test-count-verification.md)。全仓运行无失败、无 error、无超时中断；B2 测试未使用 `skip`、`xfail` 或 mock 数据库。

## 3. ATT-01…13 逐项状态

| 验收 | 状态 | 真实证据 |
|---|---|---|
| ATT-01 上传 201、分片路径、hash、无临时残留 | **已通过（SQLite）** | `test_upload_png_creates_row_blob_and_download_headers`：响应 201、`Location`、`storage_key==content_hash==SHA-256`、真实文件字节、`.tmp` 空、DB 1 行 |
| ATT-02 两 item 同内容共享物理一份、两行 | **已通过（SQLite）** | `test_same_content_two_items_shares_one_physical_blob`：分片目录仅 1 文件、COUNT=2；同 item 重复上传 200 同 id |
| ATT-03 超限/非法 Base64/空内容零写入 | **已通过（SQLite）** | `test_size_and_base64_limits_write_nothing`：413/400/400，DB 空、`.tmp` 空、正式根无文件 |
| ATT-04 magic/UTF-8/文本子类型 | **已通过（SQLite）** | `test_content_mismatch_svg_and_text_subtypes`、`test_pdf_is_accepted_and_declared_magic_is_checked`：二进制错配 415；文本伪装 PNG 415；`text/plain|markdown|csv` 保存各自声明 MIME |
| ATT-05 SVG 固定拒绝；文本 SVG 按文本 | **已通过（SQLite）** | 同左：`image/svg+xml` 415 `ATTACHMENT_MIME_UNSUPPORTED`；`text/plain` 的 SVG 内容 201 |
| ATT-06 文件名清洗/头安全 | **已通过（SQLite）** | `test_filename_is_sanitized_and_extra_fields_rejected`：`../../evil\r\n.png`→`evil.png`；Windows 路径 basename；`CON`→`_CON`；中文名 RFC 5987 且头 ASCII；额外字段 422 |
| ATT-07 下载字节/头/跨 item | **已通过（SQLite）** | `test_upload_png_creates_row_blob_and_download_headers` 六项头；`test_unknown_item_and_cross_item_do_not_leak` 跨 item 下载/删除 404 |
| ATT-08 删除最后引用入队、共享不入队 | **已通过（SQLite）** | `test_delete_last_reference_enqueues_gc_but_shared_reference_does_not`：共享 204 无 task、物理仍在；最后 204 一条 `pending`；`test_delete_does_not_duplicate_active_gc_task` 去重 |
| ATT-09 同句柄、损坏/缺失 503、不返回部分内容 | **部分通过（SQLite）**；真实 PG 未执行 | `test_download_streams_the_same_verified_handle` 断言路由只收到服务返回的句柄且流后关闭；`test_corrupted_and_missing_blob_return_503`；`test_upload_refuses_to_reuse_corrupted_blob` 不覆盖 |
| ATT-10 并发同 item / 跨 item | **已通过（SQLite）** | `test_concurrent_same_item_upload_reuses_one_reference`（200+201、同 id、1 行、1 文件）；`test_concurrent_different_items_share_one_physical_blob`（两 201、1 文件、2 行） |
| ATT-11 commit 失败清理 | **部分通过（SQLite）**；ORP 24h 未实现（B5） | `test_commit_failure_leaves_no_row_but_published_blob`：500、0 行、孤儿 blob、`.tmp` 空；`test_archive_committed_after_publish_leaves_zero_references`：竞态 409、0 行、0 临时；`test_archived_failure_releases_key_lock_after_rollback`：失败后 rollback 再释放锁，同 key 可立即重试 |
| ATT-12 F12 发布错误映射 | **已通过（B1 真实文件系统 + B2 映射）** | 复用 B1 `test_attachment_storage.py`、`test_attachment_windows.py`；B2 只做错误码到 HTTP 的映射，不重写 F12 分支 |
| ATT-13 列表隔离/排序/archived 策略/竞态 | **已通过（SQLite）** | `test_list_sorts_by_created_at_then_id`；`test_archived_blocks_upload_but_allows_list_download_delete`；`test_archive_committed_after_publish_leaves_zero_references` |

**未验证项**：

- B2 的 PostgreSQL HTTP 端到端（`FOR UPDATE` 归档保护、advisory 锁、路由 commit）——无真实 PG 实例，未执行；SQLite 结果不能替代。
- ATT-11 的 24h ORP 收敛（B5）。
- 共享引用并发删除的 ORP 兜底（B5）。
- 前端验收（B2 无前端改动）。

## 4. 跳过分类

- 定点回归 3 skip：Linux 真实挂载用例（Windows 不适用）、Windows 打开文件拒绝 rename 的句柄替换取证、Windows 无可写第二卷（跨卷分支未选）。
- 全仓 208 skip：均为既有门控；其中 PG 门控 44 项（附件仓储 13、StorageKeyLock 13、检索 18），平台 2 项，其余为既有跳过项。本报告不把跳过计为通过。
- 全仓运行没有 timeout、没有 error、没有因 B2 代码导致的跳过。

## 5. 静态核查

- `ruff check backend knowledge-core`：通过。
- 未修改 `knowledge-core`、Alembic、依赖、冻结文档。
- `git diff` 与 `git status` 见证据；B2 生产改动仅 `schemas.py`、`dependencies.py`、`main.py` 与两个新增生产文件；测试新增 1 个文件。
- 服务/仓储未调用 `commit`/`rollback`；路由提交后释放锁。
- 下载路由无 `FileResponse`、无按路径重开。

## 6. 结论

B2 在 Windows + 真实 SQLite + 真实 tmp 文件系统上完成冻结范围的 HTTP 功能与故障注入自测；ATT-01…13 的 SQLite 部分逐项有真实证据。PG HTTP 与 B5 ORP 按环境/阶段边界未执行或未实现，未以替代结果冒充。**B2 IMPLEMENTED / PENDING INDEPENDENT REVIEW。**