# B2 独立审核重点定位

**状态：B2 IMPLEMENTED / PENDING INDEPENDENT REVIEW。**
本文件只给出审核定位与上下文，不是审核结论，也不代表任何一项已由独立方通过。
行号基于本包 `production-current/` 中的完整源码副本；工作树文件与副本一致（SHA-256 见
`B2-files.sha256`）。B1 已验收实现（`attachment_storage.py`、`storage_lock.py`）
不属 B2 本轮改动，仅列出被调用位置，便于核对边界。

## 0. 前置入口

- 上传路由：`backend/app/api/routes/attachments.py::upload_attachment`（第 57–104 行）
- 附件服务：`backend/app/services/attachments.py::AttachmentService.upload`（第 269–385 行）
- 下载路由：`backend/app/api/routes/attachments.py::download_attachment`（第 130–161 行）
- 删除路由：`backend/app/api/routes/attachments.py::delete_attachment`（第 168–190 行）
- 冻结契约：`docs/plans/V2-A1-04-Batch-B/architecture.md` §4、`api-contracts.md`、
  `attachment-lifecycle.md`、`storage-and-lock-contract.md`
- 事务模型：服务与 Repository 只 flush；HTTP 路由外层唯一 commit/rollback；存储锁在
  commit 或 rollback 之后释放。

## 1. 上传快速去重（同 item + 同 storage_key）

**位置**：`backend/app/services/attachments.py` 第 295–311 行。

```python
storage_key = sha256_bytes(validated.data)

# 3. 快速路径：已有同 item+key 引用且正式 blob 可验证 → 200，不重写。
with self.session_factory() as probe:
    existing = self._find_reference(probe, item_id, storage_key)
if existing is not None:
    try:
        verify_blob(self.layout, storage_key, expected_size=existing.size)
    except AttachmentStorageError as exc:
        if exc.code == ATTACHMENT_BLOB_MISSING:
            existing = None  # 在锁内重新发布后再复用引用。
        elif exc.code == ATTACHMENT_BLOB_CORRUPTED:
            raise AttachmentServiceError(ATTACHMENT_KEY_COLLISION, 409) from None
        else:
            raise _storage_service_error(exc) from None
    if existing is not None:
        return AttachmentUploadResult(existing, False, None)
```

**审核要点**：

1. 快速路径只读，不写数据库、不取锁、不写临时文件，返回 `created=False`（HTTP 200）。
2. 只有 `verify_blob` 通过才复用引用；blob 缺失时置空，后续在 key 锁内重新发布；
   blob 损坏时直接 409，绝不覆盖损坏文件。
3. 该路径不持有存储锁，因此结果只代表“检查瞬间”的 blob 状态；并发删除/GC 由
   B1 文件系统与 B5 GC 的约束处理，B2 不声称消除 TOCTOU。此风险已在
   `unresolved.md` 记录。
4. 相关测试：`test_same_content_two_items_shares_one_physical_blob`（第 140 行）、
   `test_upload_repairs_missing_blob_for_existing_reference`（第 432 行）、
   `test_upload_refuses_to_reuse_corrupted_blob`（第 444 行）。

## 2. storage_key 锁的获取与释放

**获取位置**：`backend/app/services/attachments.py` 第 322–339 行。

```python
guard = self.storage_lock.acquire_many(
    [storage_key],
    new_owner(),
    ttl_seconds=self.lock_ttl_seconds,
    wait_seconds=self.lock_wait_seconds,
    heartbeat_seconds=self.lock_heartbeat_seconds,
)
```

- `guard is None` → `STORAGE_LOCK_TIMEOUT`（409）；`StorageLockTransient` →
  `STORAGE_LOCK_UNAVAILABLE`（503）；`StorageLockError` 按其稳定码映射 503。
- 获取失败路径先 `_discard_temp(temp)`，不留下临时文件（第 331–339 行）。

**释放位置**：

- 成功：路由 commit 之后调用 `result.release()`（`routes/attachments.py` 第 95 行），
  最终进入 `release_storage_guard`（`attachments.py` 第 188–199 行）。
- 业务失败：服务把 guard 挂到异常 `exc.attachment_guard`（第 379–385 行），路由先
  `session.rollback()`，再 `release_storage_guard`（`routes/attachments.py` 第 72–83 行），
  符合“先回滚业务事务、再释放锁”的冻结顺序（architecture §4.4 / F13）。
- commit 失败：路由 rollback 后 `result.release()`（`routes/attachments.py` 第 88–94 行）。
- 锁释放失败只记录稳定事件 `STORAGE_LOCK_RELEASE_FAILED`，不改变已提交业务结果，
  不输出路径/文件名/异常文本。

**审核要点**：确认任何异常分支都不会在 rollback 之前释放锁，也不会漏释放；
确认释放日志不含敏感内容。相关测试：
`test_archived_failure_releases_key_lock_after_rollback`（第 479 行）、
`test_storage_lock_timeout_returns_409_and_writes_nothing`（第 458 行）、
`test_commit_failure_leaves_no_row_but_published_blob`（第 507 行）。

## 3. no-clobber 发布

**调用位置**：`backend/app/services/attachments.py` 第 341–351 行。

```python
publish_no_clobber(self.layout, temp, storage_key, lock_guard=guard)
```

**实现位置（B1 已验收，不属 B2）**：
`backend/app/services/attachment_storage.py::publish_no_clobber` 第 703 行起。
B1 契约：目标存在时不覆盖；同卷原子发布；Windows 文件系统差异（F12）由 B1 真实
文件系统测试取证；发布期间校验 `lock_guard.verify_all()`（第 612 行）。

**审核要点**：

1. B2 是否只在取得 key 锁之后调用发布；
2. 是否将 B1 的 `StorageLeaseLost` / `AttachmentStorageError` / `StorageLockError`
   映射为稳定业务码，而不是泄漏异常文本；
3. 发布失败时临时文件是否被清理（服务在 `except` 分支通过 `_release_after_failure`
   或异常携带 guard 交给路由，临时文件由 B1 发布失败路径处理；请对照 B1 实现）；
4. B2 未重写、未修改 `publish_no_clobber`。

## 4. SQLite 归档保护的“条件更新”

**位置**：`backend/app/services/attachments.py::_guard_writable_item` 第 396–408 行。

```python
elif dialect == "sqlite":
    session.execute(
        update(KnowledgeItemORM)
        .where(
            KnowledgeItemORM.id == str(item_id),
            KnowledgeItemORM.status != KnowledgeStatus.ARCHIVED.value,
        )
        .values(
            status=KnowledgeItemORM.status,
            updated_at=KnowledgeItemORM.updated_at,
        )
        .execution_options(synchronize_session=False)
    )
```

随后第 412–418 行用 `session.get(..., populate_existing=True)` 重新读取并判定：
不存在 → `ITEM_NOT_FOUND` 404；已归档 → `ATTACHMENT_ITEM_ARCHIVED` 409。

**审核要点**：

1. 该 UPDATE 是“有条件的空更新”，只为在 SQLite 写事务中取得写锁并对归档状态做
   原子条件检查，不改变字段值；`updated_at` 赋自身，避免副作用。
2. SQLite 没有行级 `FOR UPDATE`；此写法依赖 SQLite 单写者语义，属于已记录局限，
   不是 PG 行锁的等价替代。B2 未声称 SQLite 提供与 PG 相同的并发保证。
3. 归档早拒（第 279 行 `_require_upload_target`）发生在解码/临时写之前；
   发布后、提交前再次检查（本节），覆盖“发布后归档”的竞态。
4. 相关测试：`test_archived_blocks_upload_but_allows_list_download_delete`（第 363 行）、
   `test_archive_committed_after_publish_leaves_zero_references`（第 388 行）。

## 5. PostgreSQL `SELECT ... FOR UPDATE`

**位置**：`backend/app/services/attachments.py` 第 390–395 行。

```python
if dialect == "postgresql":
    session.execute(
        select(KnowledgeItemORM)
        .where(KnowledgeItemORM.id == str(item_id))
        .with_for_update()
    )
```

**审核要点**：

1. 行锁在业务写事务内获取，锁住目标 item 行，阻止并发归档与附件写入交错；
2. 该分支只做方言分派，SQL 留在 backend 服务层；Knowledge Core 不含此 SQL；
3. **未验证**：本机无真实 PostgreSQL，B2 的 PG HTTP 路径（上传/共享引用/归档保护）
   未执行。不能以 SQLite 结果替代，也不能把本段代码视为 PG 已通过。见
   `unresolved.md` 与 `self-verification-report.md`。

## 6. 提交前末次 fencing：`guard.verify_all(session)`

**位置**：`backend/app/services/attachments.py` 第 369 行（在 `_guard_writable_item`、
引用查询/写入之后，返回结果给路由 commit 之前）。

```python
# 与将执行 commit 的同一 session 做末次 fencing。
guard.verify_all(session)
```

**实现（B1）**：`backend/app/db/storage_lock.py::LockGuard.verify_all` 第 267 行起；
它校验锁租约仍属于当前 owner、未过期，并在传入 session 时结合业务事务做末次确认。

**审核要点**：

1. fencing 使用的是**将要 commit 的同一 session**，不是 probe session；
2. `StorageLeaseLost` 被映射为 503，`StorageLockError` 映射为稳定码；
3. 若 fencing 失败，服务抛出异常，路由 rollback 后释放锁，不提交附件行；
4. 这是 B2 在 commit 前对“锁已丢失”的最后一道保护，但不消除 B1 已记录的
   外部原地改写/TOCTOU 风险。

## 7. 事务唯一提交/回滚边界（路由）

**上传**：`backend/app/api/routes/attachments.py` 第 64–104 行。

- 服务抛 `AttachmentServiceError`：`session.rollback()` → 释放 guard → 稳定 HTTP 错误；
- 服务抛其他异常：`session.rollback()` → 释放 guard → 记录异常类型 → 500
  `ATTACHMENT_FAILED`；
- 成功：`session.commit()` 一次；commit 失败：`session.rollback()` → `result.release()`
  → 500；commit 成功后 `result.release()`；
- 201 与 `Location` 仅在 `created=True` 时设置，重复上传同一 item+内容返回 200。

**删除**：同文件第 174–190 行。服务成功 → `session.commit()` 一次 → 204；
服务异常/commit 失败 → `session.rollback()` → 稳定错误；删除路径不持有存储锁。

**列表/下载**：只读，不 commit。

**审核要点**：

1. 服务与 Repository 内没有任何 `commit()` / `rollback()`（可全文检索确认）；
2. 每个写路由恰好一次 commit；异常分支先 rollback 再释放锁；
3. 下载不使用 `FileResponse` 或重新打开路径，见第 8 项。

## 8. 下载：`open_verified_blob` 与同一句柄流式输出

**服务**：`backend/app/services/attachments.py::download` 第 426–444 行。

```python
handle = open_verified_blob(
    self.layout,
    attachment.storage_key,
    expected_size=attachment.size,
)
```

`open_verified_blob` 实现（B1）在
`backend/app/services/attachment_storage.py` 第 753 行起：一次打开、在同一句柄上校验
大小与 SHA-256、`seek(0)` 后返回；不会先校验路径再重开。

**路由**：`backend/app/api/routes/attachments.py` 第 144–161 行。

```python
def stream():
    try:
        yield from iter_file(handle)
    finally:
        handle.close()
```

响应头包含 `Content-Type`、`Content-Length`、RFC 5987/6266 `Content-Disposition`、
`ETag`（storage_key）、`Cache-Control: private, max-age=0, must-revalidate`、
`X-Content-Type-Options: nosniff`；`media_type=None` 避免覆盖显式头。

**审核要点**：

1. 服务返回的 `handle` 与路由流式读取的是同一对象；没有 `FileResponse`/路径重开；
2. 生成器 `finally` 关闭句柄；客户端断开时也走关闭路径；
3. 跨 item 访问按 404 处理，不泄漏附件是否存在（先校验 item，再校验 attachment
   归属）；
4. 已知局限：同句柄校验不能消除其他进程在校验后原地改写文件的 TOCTOU 风险
   （B1 已记录）；B2 不声称更强保证；
5. 相关测试：`test_download_streams_the_same_verified_handle`（第 573 行）、
   `test_large_text_download_is_streamed_from_verified_handle`（第 560 行）、
   `test_corrupted_and_missing_blob_return_503`（第 408 行）。

## 9. 删除引用 + `gc_task` 入队

**位置**：`backend/app/services/attachments.py::delete` 第 446–464 行；
`_ensure_gc_task` 第 466–481 行。

流程：

1. item 不存在 / attachment 不存在 / 不属于该 item → 404 `ATTACHMENT_NOT_FOUND`；
2. `delete_attachment` 删除引用行（Repository 只 flush；返回 False → 404）；
3. `count_references(storage_key) != 0` → 直接返回，**共享引用不入队**；
4. 最后引用：`_ensure_gc_task` 查同 key 任务：
   - `PENDING` / `RUNNING` / `FAILED_RETRYABLE`（活动）→ 不重复入队；
   - `FAILED_PERMANENT` / `NEEDS_MANUAL`（阻塞）→ 记录稳定告警，不入队；
   - 否则写入 `GcTask(status=PENDING)`；
5. 数据库异常 → `ATTACHMENT_MAINTENANCE_UNAVAILABLE` 503，路由 rollback；
6. **物理文件不在 B2 删除**，留给 B5 GC/ORP worker；B2 只落 GC 任务。

**审核要点**：

1. “最后引用才入队”是否在删除同一事务内完成（是，服务只 flush，路由唯一 commit）；
2. 活动任务去重与阻塞任务不覆盖的策略；
3. 物理删除缺失属 B5，不能据此认为附件已彻底清理；
4. 相关测试：`test_delete_last_reference_enqueues_gc_but_shared_reference_does_not`
   （第 315 行）、`test_delete_does_not_duplicate_active_gc_task`（第 347 行）。

## 10. 并发上传 / 删除的处理

**并发上传（同 item 同内容）**：

- 两侧都在锁外写临时文件 → 竞争同一 `storage_key` 锁；
- 只有一侧取得锁并发布；另一侧等待后发布时命中已存在文件（no-clobber），
  随后 `_find_reference` 重查，复用已有引用；
- 最终物理 blob 一份、引用一行（同 item）。
- 测试：`test_concurrent_same_item_upload_reuses_one_reference`（第 526 行）。

**并发上传（不同 item 同内容）**：

- 同一 key 锁串行化发布；两侧各自写入自己的 item 引用；
- 最终物理一份、两行、`COUNT=2`。
- 测试：`test_concurrent_different_items_share_one_physical_blob`（第 542 行）。

**并发上传 / 删除**：

- 删除路径不取存储锁；它只删除引用并（若最后引用）入队 GC；
- B2 **没有**实现共享引用并发删除 + GC 执行时的 ORP（对象再引用保护）闭环；
  该能力属 B5。若删除最后引用的同时另一上传正在复用同一 `storage_key`，
  B2 的快速路径/重查可减少误删窗口，但**不能声称已解决并发删除与 GC 的竞态**。
  此局限已记录在 `unresolved.md`。
- B2 有顺序删除测试（最后引用入队、共享引用不入队），**没有**“共享引用并发删除”
  的真实并发测试；不得把顺序测试当作并发 ORP 证据。

**归档竞态**：

- 早拒发生在解码前；发布后在业务事务内再次检查（SQLite 条件更新 / PG 行锁）；
- 测试 `test_archive_committed_after_publish_leaves_zero_references`（第 388 行）
  模拟“发布完成后归档”，验证零引用、blob 孤儿、无临时残留；B5 ORP 收敛未实现。

## 11. 审核时不应误读的点

- B2 的 22 项测试是 **SQLite 文件库 + `tmp_path` 真实文件系统**，不是 PostgreSQL。
- `test_attachment_pg.py` / `test_storage_lock_pg*.py` 在无 `EXPLAINLAB_PG_TEST_URL` 时
  整模块跳过；跳过不等于通过。
- B1 的存储/锁实现是已验收依赖，B2 只调用；若审核发现问题，应区分 B1 责任与
  B2 调用/映射责任。
- 本包不修改任何业务代码；所有工作树变更在审核前保持未提交。