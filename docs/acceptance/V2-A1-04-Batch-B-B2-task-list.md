# ExplainLab V2 · Batch B · B2 开发任务清单与验收映射

> 状态：B2-T01 纯函数校验已完成；B2-T02 HTTP 附件 API 已实现并完成
> 真实 SQLite + tmp 文件系统自测，**待独立审核**。PG HTTP 路径因本机无真实
> PostgreSQL 实例未执行，标记“未验证/环境受限”。
> 唯一架构依据：`docs/plans/V2-A1-04-Batch-B/` 冻结文档。B1 已正式 PASS，
> 本清单不修改冻结契约、不进入 B3/B4/B5。

## 1. 前置核对结论

- B1-T01～T04 与 LCK-07 已由 ChatGPT 正式批准；B1 证据包 SHA-256 与台账一致。
- B2 边界：JSON Base64 上传、元数据列表、下载、删除四路由；不使用 multipart。
- 复用 B1：`attachment_storage`（no-clobber/同句柄读取/F12）、`storage_lock`
  （SQLite 租约 / PG advisory）、`SQLAlchemyAttachmentRepository`、
  `SQLAlchemyGcTaskRepository`；不重写底层能力。
- 事务归属：附件服务与 Repository 只 flush，不 commit/rollback；路由外层
  Unit of Work 唯一提交或回滚；存储锁在业务 commit 后释放。
- 不新增迁移、依赖、表、列、索引；不改 Core、端口、Batch A/B1 已验收实现。

## 2. 任务清单

| 任务 | 文件 | 内容 | 退出条件 |
|---|---|---|---|
| B2-T01 | `backend/app/services/attachment_validation.py`、`backend/tests/test_attachment_validation.py` | Base64/大小/MIME/magic/UTF-8/SVG/文件名清洗 | 已完成：66 专项通过（历史记录见 B2-T01 验收记录） |
| B2-T02a | `backend/app/services/attachments.py` | `AttachmentService`：上传编排（早拒 archived→解码校验→临时写→取锁→发布→受保护 item 检查→同 item 去重→引用 flush）、列表、下载（同句柄）、删除（引用 + GC 入队）、稳定错误映射 | 已实现；服务不 commit；失败回滚由路由；锁在 commit 后释放 |
| B2-T02b | `backend/app/api/routes/attachments.py` | 4 条 item 作用域路由；同步 `def`；稳定错误码；下载头/流式响应清理 | 已实现；201/200/204、404/409/413/415/422/503 与冻结码一致 |
| B2-T02c | `backend/app/api/schemas.py` | `AttachmentUploadIn`（`extra="forbid"`）、`AttachmentOut` | 已实现；额外/缺失字段 422 |
| B2-T02d | `backend/app/dependencies.py`、`backend/app/main.py` | 构造 `AttachmentService` 并暴露 `get_attachment_service`；注册 router | 已实现；启动装配不写业务事务 |
| B2-T02e | `backend/tests/test_attachment_api.py` | 真实 SQLite + tmp 文件系统 API 测试：上传/幂等/共享/列表/下载/删除/归档/错误/并发/commit 失败/损坏/锁超时/归档竞态 | 已完成：22 项通过；ATT-01…13 的 HTTP 部分逐项有真实证据 |
| B2-T02f | 真实 PostgreSQL HTTP 验收 | 上传/共享引用/归档保护 | **未执行（环境受限）**：本机未配置 `EXPLAINLAB_PG_TEST_URL`，不以 SQLite 结果替代 |

## 3. 验收映射

| 验收 | B2 证据 | 说明 |
|---|---|---|
| ATT-01 | `test_upload_png_creates_row_blob_and_download_headers` | 201、行、分片路径、sha256、无临时残留 |
| ATT-02 | `test_same_content_two_items_shares_one_physical_blob` | 物理一份、两行、COUNT=2；同 item 重复上传 200 |
| ATT-03 | `test_size_and_base64_limits_write_nothing` | 413/400，无 DB/FS 残留 |
| ATT-04 | `test_content_mismatch_svg_and_text_subtypes`、`test_pdf_is_accepted_and_declared_magic_is_checked` | 二进制 magic、文本 UTF-8、文本子类型不区分 |
| ATT-05 | `test_content_mismatch_svg_and_text_subtypes` | SVG 415；文本 SVG 按文本保存 |
| ATT-06 | `test_filename_is_sanitized_and_extra_fields_rejected` | 路径分隔符/控制字符/Windows 保留名/RFC 5987 头 |
| ATT-07 | `test_upload_png_creates_row_blob_and_download_headers`、`test_unknown_item_and_cross_item_do_not_leak` | 200 字节/头；跨 item 404 |
| ATT-08 | `test_delete_last_reference_enqueues_gc_but_shared_reference_does_not`、`test_delete_does_not_duplicate_active_gc_task` | 204；独享入队、共享不入队；物理仍在；活动任务去重 |
| ATT-09 | `test_corrupted_and_missing_blob_return_503`、`test_download_streams_the_same_verified_handle`、`test_upload_refuses_to_reuse_corrupted_blob` | 损坏/缺失 503；路由只用服务返回的同一已校验句柄；损坏不覆盖 |
| ATT-10 | `test_concurrent_same_item_upload_reuses_one_reference`、`test_concurrent_different_items_share_one_physical_blob` | 锁串行、唯一文件、同 ID |
| ATT-11 | `test_commit_failure_leaves_no_row_but_published_blob`、`test_archive_committed_after_publish_leaves_zero_references` | 无行、blob 孤儿、无临时残留；ORP 24h 收敛属 B5，未提前实现 |
| ATT-12 | 复用 B1 `test_attachment_storage`/`test_attachment_windows`；API 映射测试 | 发布错误码逐分支由 B1 真实文件系统取证，B2 只做映射 |
| ATT-13 | `test_list_sorts_by_created_at_then_id`、`test_archived_blocks_upload_but_allows_list_download_delete`、`test_archive_committed_after_publish_leaves_zero_references` | 列表只读、排序；archived 上传 409/列表下载删除允许；竞态零引用 |

## 4. 明确不在本轮

- B3 staging/import manifest、B4 approve/reject 集成、B5 GC/ORP worker。
- 前端改动（Batch B 以 API 验收为主）。
- GC/ORP 管理 HTTP 端点。
- 新增依赖、迁移或数据库 schema 变更。

## 5. 环境边界

- 主验收：Windows 真机 + 真实 SQLite 文件库 + `tmp_path` 真实文件系统。
- PostgreSQL：仅在 `EXPLAINLAB_PG_TEST_URL` 存在时执行；缺失时相关项标
  “未验证/环境受限”，不以 SQLite 或 skip 冒充通过。
- 历史已知局限：PG 行 TTL 不授权接管、SQLite 租约为逻辑锁、下载同句柄
  不消除外部原地改写风险；均按冻结文档如实记录。