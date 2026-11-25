# B2 实施报告

**状态：已实现，待独立审核。** 依据冻结的 `docs/plans/V2-A1-04-Batch-B/implementation-roadmap.md`、`acceptance-plan.md`、`api-contracts.md`、`attachment-lifecycle.md`、`architecture.md` 与 `storage-and-lock-contract.md`。B1 已正式 PASS，B2 复用其存储、锁、仓储与 GC 任务表。

## 1. 实现范围

B2 提供 item 作用域的四条同步 HTTP 路由：

| 方法 | 路径 | 行为 |
|---|---|---|
| `POST` | `/api/knowledge/{item_id}/attachments` | JSON Base64 上传；新引用 201，同 item+key 已存在 200；201 附 `Location` |
| `GET` | `/api/knowledge/{item_id}/attachments` | DB 元数据列表；`created_at ASC, id ASC`；不校验 hash、不取 key 锁 |
| `GET` | `/api/knowledge/{item_id}/attachments/{attachment_id}` | 同句柄校验后流式下载；冻结响应头 |
| `DELETE` | `/api/knowledge/{item_id}/attachments/{attachment_id}` | 删除引用；最后引用入队 `gc_task pending`；物理文件不由本层删除 |

未实现：B3 staging/import manifest、B4 审核集成、B5 GC/ORP worker、GC 管理 HTTP 端点、Range/HEAD、前端页面。

## 2. 文件

### 新增

| 文件 | 职责 |
|---|---|
| `backend/app/services/attachment_validation.py` | B2-T01 纯函数：Base64/大小/MIME/magic/UTF-8/SVG/文件名清洗 |
| `backend/app/services/attachments.py` | `AttachmentService`：上传编排、列表、下载句柄、删除与 GC 入队、稳定错误映射 |
| `backend/app/api/routes/attachments.py` | 四条路由；外层事务提交/回滚；下载流关闭；稳定码 HTTPException |
| `backend/tests/test_attachment_validation.py` | B2-T01 纯函数专项 |
| `backend/tests/test_attachment_api.py` | B2-T02 真实 SQLite + tmp 文件系统 HTTP 验收 |

### 修改

| 文件 | 修改 |
|---|---|
| `backend/app/api/schemas.py` | 新增 `AttachmentUploadIn(extra="forbid")`、`AttachmentOut(from_attributes=True)` |
| `backend/app/dependencies.py` | 新增 `get_attachment_service`（未装配时 503 `ATTACHMENT_STORAGE_UNAVAILABLE`） |
| `backend/app/main.py` | 启动期构造 `AttachmentService`；注册 attachments router（位于 `{item_id}` 动态段之前） |

**B2 未修改**：`attachment_storage.py`、`storage_lock.py`、`repositories_v2.py`、`knowledge-core`、`alembic/`、依赖清单、冻结计划文档。工作树中 `config.py`/`session.py`/`repositories_v2.py` 的未提交差异来自 B1-final 修复，不属于 B2-T02；B2 只调用其已验收接口。

## 3. 上传顺序与事务边界

1. **archived 早拒**：独立 probe session 读取 item；不存在 404 `ITEM_NOT_FOUND`，已归档 409 `ATTACHMENT_ITEM_ARCHIVED`。此步在解码与写临时文件之前，probe 在取锁前关闭。
2. **纯函数校验**：Base64 严格解码、10 MiB、MIME 白名单（SVG 固定拒绝）、二进制 magic、文本 UTF-8、文件名清洗。
3. **服务端 hash**：`storage_key = SHA-256(实际字节)`，`content_hash` 同值。
4. **快速路径**：独立 probe 查同 item+key 引用；blob 可验证则 200，不重写、不取锁。blob 缺失则在锁内重新发布并复用引用；blob 损坏则 409 `ATTACHMENT_KEY_COLLISION`，绝不覆盖。
5. **临时文件**：写 `.tmp/<uuid>.part` 并重读 hash；不进入正式分片根。
6. **存储锁**：`acquire_many([key], new_owner(), ttl/wait/heartbeat)`；超时 409 `STORAGE_LOCK_TIMEOUT`，租约丢失 503 `STORAGE_LEASE_LOST`，瞬时不可用 503。
7. **no-clobber 发布**：`publish_no_clobber(..., lock_guard=guard)`；复用 B1 的 F12 分支与同卷检查。
8. **受保护 item 写入**：PG `SELECT ... FOR UPDATE`；SQLite 条件 `UPDATE ... WHERE status != archived`，再 `populate_existing` 重读。缺失 404、归档 409。
9. **同 item 去重**：在将提交的同一 session 中重查 `(item_id, key)`；存在则复用行（200），不存在则 `save_attachment`（flush-only）。
10. **末次 fencing**：`guard.verify_all(session)`。
11. **路由唯一提交/回滚**：成功 `commit()` 后释放存储锁；commit 失败 `rollback()` 后释放锁并返回 500 `ATTACHMENT_FAILED`。锁已获取后的业务失败，由服务把 guard 交给异常、路由先 `rollback()` 再释放；服务不自行 rollback/commit。

服务与 Repository 不 `commit`/`rollback`；锁不在业务事务内提前释放。发布成功但业务失败时保留孤儿 blob（ATT-11），不由 B2 删除；24h ORP 收敛属 B5。

## 4. 下载

- item 或 attachment 不存在、跨 item 一律 404 `ATTACHMENT_NOT_FOUND`，不泄露存在性。
- `open_verified_blob(layout, key, expected_size=row.size)` 只打开一次，在同一句柄上校验 inode/常规文件/大小/SHA-256，`seek(0)` 后返回。
- 路由仅把该句柄交给 `iter_file` 的 `StreamingResponse`；不使用 `FileResponse`，不按路径重开。异常或流结束均关闭句柄。
- 缺失 503 `ATTACHMENT_BLOB_MISSING`；大小/hash 不符 503 `ATTACHMENT_BLOB_CORRUPTED`；其他 I/O 503 `ATTACHMENT_STORAGE_UNAVAILABLE`。
- 响应头固定为：DB MIME、DB size、RFC 5987 `Content-Disposition`、`ETag: "<storage_key>"`、`Cache-Control: private, max-age=0, must-revalidate`、`X-Content-Type-Options: nosniff`。

## 5. 删除

- item 不存在或 attachment 不属于 item → 404 `ATTACHMENT_NOT_FOUND`（删除对 item 不存在也使用附件码）。
- 删除行并 flush；`COUNT(storage_key) != 0` 直接返回，不入队。
- 最后引用：查 `gc_task`；`pending/running/failed_retryable` 已存在则不重复入队；`failed_permanent/needs_manual` 记脱敏 warning 不覆盖；否则保存 `pending`。
- 路由唯一 commit；GC 表写入失败映射 503 `ATTACHMENT_MAINTENANCE_UNAVAILABLE`。
- 物理文件保留，由 B5 worker 处理；B2 不提供 GC HTTP。

## 6. 错误映射

| HTTP | 稳定码 | 来源 |
|---|---|---|
| 404 | `ITEM_NOT_FOUND` | 上传/列表 item 不存在 |
| 404 | `ATTACHMENT_NOT_FOUND` | 下载/删除 item 或附件不存在、跨 item |
| 409 | `ATTACHMENT_ITEM_ARCHIVED` | 上传目标已归档（早拒或事务内竞态） |
| 409 | `STORAGE_LOCK_TIMEOUT` | key 锁等待超时 |
| 409 | `ATTACHMENT_KEY_COLLISION` | 正式 key 存在但 blob 损坏/不可复用 |
| 400 | `ATTACHMENT_EMPTY` / `ATTACHMENT_BASE64_INVALID` / `ATTACHMENT_FILENAME_INVALID` | 纯函数校验 |
| 413 | `ATTACHMENT_TOO_LARGE` | > 10 MiB |
| 415 | `ATTACHMENT_MIME_UNSUPPORTED` / `ATTACHMENT_CONTENT_MISMATCH` | 白名单/SVG/magic/UTF-8 |
| 422 | `ATTACHMENT_HASH_MISMATCH` | 临时文件重读 hash 不一致 |
| 503 | `ATTACHMENT_WRITE_FAILED` / `ATTACHMENT_WRITE_CORRUPTED` / `ATTACHMENT_WRITE_BUSY` / `ATTACHMENT_STORAGE_UNAVAILABLE` / `ATTACHMENT_STORAGE_CROSS_VOLUME` / `STORAGE_LEASE_LOST` / `ATTACHMENT_BLOB_MISSING` / `ATTACHMENT_BLOB_CORRUPTED` | B1 存储/锁异常映射；`WRITE_BUSY` 附 `Retry-After: 1` |
| 500 | `ATTACHMENT_FAILED` | 未预期异常；日志只记操作与异常类型 |

## 7. 日志与安全

- 不记录附件内容、物理路径、用户文件名、hash 全文或异常文本。
- 日志仅含操作名、异常类型；GC 阻塞 warning 仅使用 key 前 8 位。
- 错误响应只含冻结稳定码。

## 8. 已知未完成/未验证

- **PG HTTP 端到端未执行**：本机无真实 PostgreSQL 实例（`EXPLAINLAB_PG_TEST_URL` 未设置）。B2 的 PG 分支（`FOR UPDATE` 归档保护 + advisory 存储锁 + 路由提交）只有代码审阅，无真实运行证据；不以 SQLite 结果替代。
- **ATT-11 的 24h ORP 收敛**：B5 范围，未提前实现；B2 只验证 commit 失败后的“无行 + 孤儿 blob + 无临时残留”。
- **共享引用并发删除**可能因两侧均看到非零引用而不入队；冻结计划允许 ORP 兜底，B5 未实现。
- 前端未改动、未执行前端测试。
- 全仓 Ruff 的既有历史问题（旧审计包迁移副本）不在本轮修复范围；本轮只声明 `backend knowledge-core` 通过。