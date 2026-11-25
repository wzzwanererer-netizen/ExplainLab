# Current Code Inventory

## 1. Git 基线

| 项目 | 真实值 | 标签 |
|---|---|---|
| `git rev-parse HEAD` | `970c0d8ec05f0b8c68286839a56b14c74ea230c6` | 已实现 |
| `git branch --show-current` | `fix/m0-admission-and-m5-regressions` | 已实现 |
| HEAD 主题 | `feat(explainlab): complete A1-04 Batch A implementation` | 已实现 |
| Batch A 提交类型 | `commit` | 已实现 |
| 暂存文件数 | 0 | 已实现 |
| 已跟踪未暂存文件数 | 0 | 已实现 |
| 未跟踪文件数 | 107（盘点基线 101 + 本目录 6 份报告） | 已实现 |
| 未跟踪内容性质 | 审计/盘点/计划材料；未发现未提交业务代码 | 已实现 |
| Batch A 之后是否另有代码修改 | 未发现；HEAD 即 Batch A 提交 | 已实现 |

近期提交：

```text
970c0d8 feat(explainlab): complete A1-04 Batch A implementation
784b124 test: A1-03 最终审计补充 — phantom 非碰撞新增 ID 集合守护验证
9634ad1 fix: 专项审计修复 — 重建步8c 逐行复核补齐 no-op 行窗口②并发保护
b6c7e15 fix: 专项审计修复 — 重建步7 P2 乐观前置扩至门禁C同口径6字段
ccf6194 fix: V2 K1+K2 整改批 — 治理审核批准路径链接维护 + 重建并发窗口控制
```

**结论：基线干净，Batch A 提交未被后续代码覆盖。** 标签：已实现。

## 2. 数据层（schema 与 ORM）

| 模块 | 真实位置 | 现状 | 标签 |
|---|---|---|---|
| `AttachmentORM` | `backend/app/models.py:336-351` | `attachment` 表：id/item_id/filename/mime/size/storage_key/content_hash/created_at；`item_id` FK CASCADE；`storage_key` 普通索引 | 已实现 |
| `GcTaskORM` | `backend/app/models.py:379-407` | `gc_task` 表：status/lease_owner/lease_expires_at/lease_token/attempts/next_retry_at/quarantine_path/quarantined_at/created_at/updated_at；两个索引 | 已实现 |
| `StorageLockORM` | `backend/app/models.py:438-451` | `storage_lock` 表：storage_key PK、owner、lease_token、lease_expires_at、locked_at | 已实现 |
| Alembic `0006` | `backend/alembic/versions/0006_v2_markdown_kb.py:114-199`（创建）、`201+`（回滚） | 创建三张表、索引、FK；支持 upgrade/downgrade | 已实现 |
| ORM 关系 | `models.py` | 未给 `KnowledgeItemORM` 添加 attachment 关系；注释说明是刻意 additive，不改变 V1 关系 | 已实现 |
| `Attachment` 实体 | `knowledge-core/src/knowledge_core/domain/entities.py:206-216` | 纯 Pydantic 值对象，字段与 ORM 对齐 | 已实现 |
| `GcStatus` | `entities.py:238-247` | 7 态：pending/running/done/cancelled/failed_retryable/failed_permanent/needs_manual | 已实现 |
| `GcTask` 实体 | `entities.py:250-268` | 字段与 ORM 对齐；lease_token/attempts 非负 | 已实现 |
| `StorageLease` 实体 | `entities.py:271-282` | storage_key/owner/lease_token/lease_expires_at | 已实现 |
| 附件表索引 | `models.py:340`、`test_v2_models.py:478-480` | `ix_attachment_storage_key` 存在 | 已实现 |
| 引用数派生 | `test_v2_models.py:448-463` | 测试用 COUNT(storage_key) 验证共享引用；无计数器列 | 已实现 |
| 附件随 item 删除级联 | `test_v2_models.py:465-476` | DB FK CASCADE 清 attachment 行 | 已实现（仅 DB 行） |
| item 删除后的物理 blob GC 触发 | 无 | 级联删除 attachment 行不会自动 enqueue `gc_task`；需服务层或独立扫描处理 | 未实现 / 需要 ChatGPT 决策 |

### 2.1 关键 schema 事实

- `attachment` 没有 `(item_id, storage_key)` 唯一约束，也没有 `content_hash` 唯一约束；只有 `storage_key` 普通索引。相同内容共享由 `storage_key` 相同表达，引用行可多条。标签：部分实现（共享模型可表达，防重复策略未定义）。
- `attachment.storage_key` 与 `attachment.content_hash` 都是必填字符串，但没有数据库或 Pydantic 不变量强制二者相等；内容寻址的“storage_key=sha256(content)”目前只是设计约定。标签：未实现（不变量校验）。
- `attachment.size` 只有 `Integer NOT NULL`，无上限检查；`Attachment.size` 只有 `ge=0`。标签：未实现（大小上限）。
- `attachment.mime` 只有长度上限 200，无白名单；`Attachment.mime` 只有 `min_length=1`。标签：未实现（MIME 白名单）。
- `attachment.filename` 只有长度/非空；清洗逻辑不在模型中。标签：未实现（附件文件名清洗）。
- `gc_task.status` 是普通 `String(24)`，没有数据库 CHECK；状态合法性依赖应用层枚举。标签：部分实现。
- `storage_lock.lease_token` 是普通整数，没有 DB 自增；单调性需条件 UPDATE 维护。标签：部分实现。
- `storage_lock` 表只服务 SQLite 逻辑租约；PG 设计为 advisory lock，不落该表。标签：已实现（schema）/未实现（runtime）。

## 3. Core 端口

`knowledge-core/src/knowledge_core/ports.py`：

| 端口 | 方法 | 现状 | 标签 |
|---|---|---|---|
| `AttachmentRepository` | `save_attachment`、`get_attachment`、`list_attachments`、`find_by_hash`、`count_references`、`list_storage_keys`、`delete_attachment` | 7 个 Protocol 方法均有 docstring；无 backend 实现 | 端口已实现 / 实现未实现 |
| `GcTaskRepository` | `save_task`、`get_task`、`list_tasks`、`claim`、`update_task` | 明确要求原子条件更新 + lease_token fencing；无 backend 实现 | 端口已实现 / 实现未实现 |
| `StorageKeyLock` | `acquire`、`renew`、`verify`、`release` | 明确 SQLite 租约 / PG advisory；诚实声明“降低而非消除 TOCTOU”；无 backend 实现 | 端口已实现 / 实现未实现 |
| `ImportOriginRepository` | 已有完整实现 | `repositories_v2.py` | 已实现 |
| `TagRepository` / `TagChangeLogRepository` | 已有完整实现 | `repositories_v2.py` | 已实现 |

### 3.1 端口签名要点

- `AttachmentRepository.count_references(storage_key) -> int`：权威引用数为 `COUNT(attachment WHERE storage_key)`。
- `AttachmentRepository.list_storage_keys() -> list[str]`：孤儿扫描的 DB 侧引用集合。
- `GcTaskRepository.claim(task_id, *, owner, lease_ttl_seconds, now=None) -> GcTask | None`：仅 pending 或租约过期的 running 可认领；成功时 token 增加、attempts 增加。
- `GcTaskRepository.update_task(task, *, expected_lease_token) -> GcTask | None`：token 失配返回 `None`，调用方必须中止不可逆物理操作。
- `StorageKeyLock.acquire(storage_key, owner, *, ttl_seconds) -> StorageLease | None`：被占用返回 `None`。
- `renew` / `verify` / `release` 均以 owner+token 为 fencing 条件。

## 4. backend 仓库与服务实现

| 模块/文件 | 真实内容 | 现状 | 标签 |
|---|---|---|---|
| `backend/app/services/repositories_v2.py` | 仅 `SQLAlchemyTagRepository`、`SQLAlchemyTagChangeLogRepository`、`SQLAlchemyImportOriginRepository`、`list_all_import_origins` | 没有 Attachment/GcTask 仓库类；`__all__` 也不导出 | 部分实现 |
| `backend/app/services/markdown_item_repository.py` | Markdown 导入专用 item 仓库（V1 `KnowledgeRepository` 不改） | 可复用，但与附件无关 | 已实现 |
| `backend/app/services/markdown.py` | 导入/导出编排、S0/S1、身份锁、Journal 恢复门、附件拒绝 | 非附件 Batch A 完整；附件只拒绝 | 部分实现 |
| `backend/app/services/import_review_hook.py` | approve/reject 导入钩子；附件非空时抛 `ATTACHMENT_REVIEW_UNSUPPORTED` | Batch A 语义完整；附件整合不存在 | 部分实现 |
| `backend/app/services/import_coordinator.py` | 每身份键同步锁、10s 有界等待、引用计数回收 | 已实现，Batch B 可复用 | 已实现 |
| `backend/app/services/source_identity.py` | 身份分类、MATERIALIZE/ROTATE Journal、恢复门、identity_guard | Batch A 已实现；不是附件 GC Journal | 已实现 |
| `backend/app/services/source_instance_id.py` | `source-instance-id` 原子创建/读取/替换 | 已实现 | 已实现 |
| `backend/app/services/file_write.py` | `write_all` 完整写入循环 | 已实现，可作为存储写入原语 | 已实现 |
| `backend/app/db/locking.py` | A1-03 链接重建写锁（PG 表锁 / SQLite no-op） | **不是 StorageKeyLock**；不能误用 | 已实现（但非本任务） |
| `backend/app/db/storage_lock.py` | 不存在 | 需 Batch B 新建 | 未实现 |
| `backend/app/services/attachments.py` | 不存在 | 需 Batch B 新建 | 未实现 |
| `backend/app/services/gc.py` / `orphan_scan.py` | 不存在 | 需 Batch B 新建 | 未实现 |

### 4.1 附件相关调用链现状

- 导入入口只把 `attachments` 转为布尔 `attachments_requested`，不读取附件字节、不校验、不落盘。
- 单篇导入 `reject_attachments=True`：预检发现附件请求后直接抛 `ATTACHMENT_IMPORT_UNSUPPORTED`，零写入。
- 批量导入 `reject_attachments=False`：该篇标记 `ImportItemStatus.UNSUPPORTED`，其余篇继续。
- Active 内容变更生成 pending 时，`MarkdownService._envelope(...)` 固定 `attachments=[]`；因此当前不会产生含附件 manifest 的 pending。
- `ImportReviewHook.apply_approved()` 第一段逻辑若 `envelope.attachments` 非空，立即抛 `ATTACHMENT_REVIEW_UNSUPPORTED`，在任何 item/tags/origin/link 写入之前失败。
- `MarkdownService.export_documents()` / `export_single()` 遇 `include_attachments=True` 抛 `ATTACHMENT_EXPORT_UNSUPPORTED`；ZIP manifest 固定 `"attachment_export": "unsupported"`。

## 5. API 与 DTO

| 项 | 真实位置 | 现状 | 标签 |
|---|---|---|---|
| 附件路由 | `backend/app/api/routes/` | 无 `attachments.py`；无 `/attachments` 路由 | 未实现 |
| 导入路由 | `import_export.py:207-243` | 单篇/批量 Markdown 导入；附件请求识别与拒绝 | 已实现（Batch A） |
| 导出路由 | `import_export.py:246-270` | 批量 ZIP；`include_attachments` 拒绝 | 已实现（Batch A） |
| 单篇导出 | `import_export.py:273-297` | `text/markdown`；附件不导出 | 已实现（Batch A） |
| `MarkdownImportItemIn.attachments` | `schemas.py:364-374` | `list[dict[str, Any]]`，只用于识别请求 | 部分实现 |
| `MarkdownImportIn.attachments` | `schemas.py:377-389` | 同上 | 部分实现 |
| `MarkdownExportIn.include_attachments` | `schemas.py:392-395` | 默认 false；true 时拒绝 | 已实现 |
| `ReviewResolve` | `schemas.py:252-253` | 只有 `note`；无附件 manifest / staging 字段 | 未实现（附件需求） |
| `ReviewOut` / `ReviewSubmit` | `schemas.py:224-243` | payload 为自由 dict，可承载 `__a1_import` | 已实现 |
| `ImportEnvelope.attachments` | `knowledge-core/.../markdown/import_report.py:244` | `list[dict[str, Any]]`，当前由 backend 固定为空 | 部分实现 |

## 6. 配置、会话与装配

| 项 | 真实位置 | 现状 | 标签 |
|---|---|---|---|
| `Settings.data_dir` | `config.py:47` | 默认 `BACKEND_DIR/data`；可测试注入 | 已实现 |
| `Settings.import_lock_wait_seconds` | `config.py:49` | 默认 10.0；身份锁用 | 已实现 |
| 附件存储根 | `config.py` | 无 `attachment_storage_root` | 未实现 |
| 附件大小/MIME/SVG 策略 | `config.py` | 无字段 | 未实现 |
| 租约 TTL/心跳/GC/孤儿扫描参数 | `config.py` | 无字段 | 未实现 |
| DB 会话工厂 | `db/session.py` | SQLite FK、busy_timeout；`create_session`/`session_scope` | 已实现 |
| 应用 lifespan | `main.py:65-106` | 进程锁、source-instance-id、ImportCoordinator、SourceIdentityService、MarkdownService、默认空间 | 已实现 |
| GC/孤儿 worker 启动 | `main.py` | 无后台任务、无线程、无调度器 | 未实现 |
| 依赖注入 | `dependencies.py` | 仅 model/embedder/identity/markdown 服务 | 部分实现（无 attachment/storage 服务） |

## 7. 测试现状

| 测试文件 | 覆盖 | 与 Batch B 的关系 | 标签 |
|---|---|---|---|
| `backend/tests/test_v2_models.py` | attachment 共享 COUNT、级联、索引；GC 默认值/索引/cancelled/quarantine 字段；storage_lock PK/过期接管（直接 SQL） | 只验证 schema/约束，不验证仓库、锁、GC、物理文件 | 部分实现 |
| `backend/tests/test_v2_models_pg.py` | PG 侧 schema、类型、级联、storage_lock/gc_task 条件 UPDATE | 真 PG schema 验证；无服务体 | 部分实现 |
| `backend/tests/test_migrations.py` | 0006 up/down 与表集合 | schema 迁移已覆盖 | 已实现 |
| `backend/tests/test_markdown_batch_a_import_export.py::TestAttachmentBoundary` | 单篇拒绝、批量 unsupported、导出拒绝 | Batch A 附件边界 | 已实现 |
| `test_markdown_batch_a_import_export.py::TestActiveReviewFlow` | Active 变更 → pending → approve hook → 内容/标签/链接；Hook 失败回滚；reject 不写 | 非附件 approve 闭环 | 已实现 |
| `backend/tests/test_batch_a_process_and_identity.py` | 进程锁、instance-id、Coordinator、S0/S1、同步线程模型、取消 | 可复用的锁/线程基础 | 已实现 |
| `backend/tests/test_attachments.py` / `_pg.py` | 不存在 | 设计要求的上传/共享/穿越/MIME/大小/下载/删除未测试 | 未实现 |
| `backend/tests/test_gc.py` / `_pg.py` | 不存在 | 认领/双 Worker/quarantine/purge/退避未测试 | 未实现 |
| `backend/tests/test_orphan_scan.py` / `_pg.py` | 不存在 | 孤儿/隔离区/等待期/恢复未测试 | 未实现 |

## 8. 明确缺失的 Batch B 模块

以下文件当前在仓库中不存在（`find` 已核实）：

- `backend/app/db/storage_lock.py`
- `backend/app/services/attachments.py`
- `backend/app/services/gc.py`（或等价 GC worker）
- `backend/app/services/orphan_scan.py`（或等价扫描器）
- `backend/app/api/routes/attachments.py`
- `backend/tests/test_attachments.py` / `_pg.py`
- `backend/tests/test_gc.py` / `_pg.py`
- `backend/tests/test_orphan_scan.py` / `_pg.py`
- `backend/data/attachments/`（实际存储根不存在）
- `backend/data/import-staging/`（staging 根不存在）

标签：未实现。

## 9. 结论

**Batch B 可以直接复用的是：`0006` schema、Attachment/GcTask/StorageLease 实体、三个 Core 端口、ImportCoordinator、SourceIdentityService 的锁/事务纪律、`write_all` 与 Journal 的原子写入经验、现有 Active Review 非附件事务链。** 需要新建的是：附件仓库、StorageKeyLock、附件服务与路由、GC/隔离/孤儿扫描、staging、附件 manifest 校验与 approve 整合、配置与真实 FS 测试。标签：已实现 / 未实现。