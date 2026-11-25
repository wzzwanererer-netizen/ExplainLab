# Implementation Roadmap

本文件是**开发路线**，不是已完成声明。只有 ChatGPT 批准 Architecture Freeze 后才可进入 B1；本轮不写代码。

## 1. 约束

- 无新迁移/表/列/索引；复用 `0006_v2_markdown_kb.py` 的 `attachment/gc_task/storage_lock`。
- 无新第三方依赖；仅标准库 + 现有 FastAPI/SQLAlchemy/Pydantic。
- 不改 Core `ReviewService`、端口签名、A1-02 Hash、A1-03 `LinkKeyRebuild`、Core `ImportReport`（D-B12）。
- 不改 Batch A 冻结语义；附件导出继续 400。
- 每个任务结束必须跑：相关 pytest、根级 `uv run pytest -o addopts="--import-mode=importlib"`、`uv run ruff check`；前端仅在受影响时跑。
- 每个任务只做本任务范围；不得顺手重构。
- 不在 B1–B5 中声明 Batch B 通过；B6 只产出证据，最终由独立审计裁决。

## 2. 任务依赖

```text
B1 基础（配置/存储/锁/仓库）
 ├─▶ B2 上传/列表/下载/删除 API
 ├─▶ B3 staging + 导入 manifest（ZIP-only）
 │     └─▶ B4 approve/reject 集成（依赖 B1/B3）
 └─▶ B5 GC/ORP（依赖 B1/B2；可与 B4 并行，但须在 B4 后做联合测试）
        └─▶ B6 验收取证（依赖 B2/B4/B5）
```

- B1 必须先完成；B2 与 B3 可在 B2-T01 的公用校验接口明确后并行；B4 必须在 B3 后；B5 的删除入队依赖 B2，物理 GC 依赖 B1。
- O-B01/D-B01/D-B02/O-B08/O-B09/O-B10 已裁决；B3/B4 可按冻结的 ZIP-only、`staging_id`、PG advisory 与 Active 附件-only 拒绝实现。若最终签发改变任一裁决，先更新设计文档再改代码。

## 3. B1：基础层

### B1-T01 配置与启动校验

- 修改 `backend/app/core/config.py`：新增 `architecture.md` §5 字段；默认值；`data_dir` 解析。固定默认：单文件 10 MiB、单次导入 100 个/100 MiB、staging 宽限 86400s。
- 新增启动校验函数（建议 `backend/app/services/attachment_storage.py::validate_storage_roots`）。
- 修改 `backend/app/main.py`：lifespan 中创建/校验根；失败抛出并阻止启动；保存到 `app.state`。
- 测试：默认路径、创建失败、实际根重叠/路径别名、symlink/junction、跨卷（注入及平台实测）、越界和不可写目录；断言固定上限/宽限默认值，防止漂移。
- 退出：配置单元测试通过；不启动 worker。

### B1-T02 内容寻址存储

- 新增 `backend/app/services/attachment_storage.py`：
  - `sha256_file` / `sha256_stream`；
  - `temp_path`、`final_path`（校验 64hex、分片）；
  - `write_temp`（`xb`、`write_all`、fsync）；
  - `publish_no_clobber`（**调用方必须已持锁**；link 优先 / Windows no-clobber `os.rename` 降级 / POSIX 无 link 则失败 / 同 hash 复用 / 冲突 / 发布后校验；禁止覆盖式 `os.replace`）；
  - `read_stream`、`verify_blob`、`move_to_quarantine`、`restore_from_quarantine`、`delete_blob`；
  - 下载路径提供“打开一次 → 同句柄 size/hash 校验 → `seek(0)` → 流式输出”的辅助；不得按路径重复 open；
  - `retry_windows_busy`。
- 复用 `backend/app/services/file_write.py::write_all`；如需 fsync 辅助，可在本文件实现，不改其签名。
- 测试：并发发布同 key、已存在同/异 hash、link 不可用降级、临时残留、fsync 失败、路径穿越、Windows 占用（win32）、校验后同句柄读出的字节一致。
- 退出：真实文件系统测试通过；无 DB 依赖。

### B1-T03 SQLite/PG StorageKeyLock

- 新增 `backend/app/db/storage_lock.py`：
  - `SQLiteStorageKeyLock`：`storage_lock` 条件 UPDATE + INSERT 竞争、renew/verify/release、不删行；
  - `PostgresStorageKeyLock`：每 guard 一个专用物理连接，按去重的实际 advisory 二元组排序，按完整 key UPSERT token；串行 heartbeat/verify/release，部分失败逆序 unlock 并物理关闭；
  - `LockGuard`：按实际冲突域排序/逆序释放、获取全流程统一 10s deadline、每 guard 一份心跳调度、幂等 release、abort 标志、`verify_all()`（commit 前 fencing 校验）。
- 修改 `backend/app/main.py`：按 `settings.database_url` 方言构造并挂 `app.state`。
- 测试：
  - `test_storage_lock_sqlite.py`：并发线程仅一成功、过期接管 token+1、旧 token renew/verify/release 失败、release 保留 token、不重入、busy 与失配区分；
  - `test_storage_lock_pg.py`：`EXPLAINLAB_PG_TEST_URL` 门控；真实 PG 两连接互斥、token 单调、连接关闭释放、过期行不绕过 advisory；**LCK-10：行 TTL 过期但原会话仍持有 Advisory Lock 时，第二连接不得接管**；断开第一连接后才可接管。另验同投影 key 批内去重、跨批排序、100 key 一个 guard 会话、部分获取失败清退、旧 guard 不复活。
  - 多 key 排序无死锁（超时路径）。
- 退出：SQLite 必过；PG 必须真实实例通过（无 PG 则报告阻塞，不得伪造）。

### B1-T04 SQLAlchemy 仓库

- 修改 `backend/app/services/repositories_v2.py`：
  - `SQLAlchemyAttachmentRepository`：7 个端口方法；flush 不 commit；`list_storage_keys` 用 DISTINCT；`count_references` 用 `ix_attachment_storage_key`。
  - `SQLAlchemyGcTaskRepository`：save/get/list/claim/update；claim 支持 pending + 过期 running；PG 条件更新/`SKIP LOCKED` 仅用于候选选择；终态不可覆盖；条件写核对 owner/token/租约/状态及到期和 attempts 预算；确定性隔离槽规则见 GC §5。
- 测试：真实 SQLite 事务；SQLite 条件认领并发；PG 并发两 worker 仅一 claim（gated）；终态保护；token 失配返回 None。
- 退出：仓库测试通过；不改模型。

## 4. B2：附件 API

### B2-T01 MIME/大小/文件名校验

- 新增 `backend/app/services/attachment_validation.py`（或并入 `attachments.py`）：
  - 白名单、magic 检测、严格 UTF-8、SVG 拒绝、10 MiB、文件名清洗/保留名。
  - 二进制按 magic 判定；文本只做严格 UTF-8 + 无 NUL，不声称区分 `text/plain`/`text/markdown`/`text/csv`，以声明 MIME 为准。
- 测试：全部允许类型、伪扩展名、SVG、空文件、非法 Base64、11 MiB、非法 UTF-8、NUL、文本声明含二进制 magic、保留名、路径分隔符、Unicode 文件名；断言文本子类型不因内容不同被区分。
- 退出：纯函数测试通过；无 I/O 副作用。

### B2-T02 上传/下载/删除服务与路由

- 新增 `backend/app/services/attachments.py`：
  - `upload(item_id, filename, declared_mime, data: bytes)`：早拒 archived 后解码/校验/写临时→关闭预检会话→storage guard + 发布→业务事务内 archive 防护及同 item 去重→fencing→commit→release；
  - `list(item_id)`：只读元数据，稳定排序，不取锁；
  - `download(item_id, attachment_id)`：校验归属→**打开一次**→同句柄 size/hash→`seek(0)`→流；
  - `delete(item_id, attachment_id)`：删行+refs+ensure_gc_task 同事务（archived 允许）；
  - `AttachmentServiceError` 与稳定码映射。
- 新增 `backend/app/api/routes/attachments.py`：4 路由（上传/列表/下载/删除）；同步 `def`。
- 修改 `backend/app/api/schemas.py`：`AttachmentUploadIn`（`extra="forbid"`）、`AttachmentOut`。
- 修改 `backend/app/dependencies.py`：`get_attachment_service`。
- 修改 `backend/app/main.py`：构造 service；注册 router `/api`。
- 修改 `backend/app/api/routes/import_export.py`：仅错误映射扩展（如需要），不改既有导入导出语义。
- 测试：真实 SQLite + tmp 文件系统；201/200/204；列表 200/排序/跨 item；archived 上传 409 但下载/列表/删除允许；404 跨 item；锁超时；DB commit 失败清理；删除最后引用入队；共享引用不入队；下载头/流/同句柄；大文件不整读。
- 退出：API 验收 ATT-01…13 通过（ATT-13 覆盖列表与 archived）。

## 5. B3：staging 与导入 manifest

> 前置：O-B01/D-B01 已裁决。按 ZIP-only + `staging_id` 实现；如最终签发改变，先改设计。

### B3-T01 manifest schema 与 staging 服务

- 新增 `backend/app/services/attachment_staging.py`：
  - `AttachmentManifestItem`（Pydantic，extra=forbid，字段约束）；
  - `create_from_zip`（ZIP-only）；
  - `validate_manifest`（路径/hash/size/mime/重复/数量/总字节）；
  - staging 标记：创建写 `.creating`，每个 blob 写入后刷新 `.activity`，全部完成后写 `.complete`；`staging_activity_at` 取标记与普通文件 mtime 的最大值，禁止用目录根 mtime；
  - `discard_committed/discard_rejected/sweep_candidate`；
  - `staging_id` 生成与目录命名。
- 修改 `backend/app/services/markdown.py`：
  - `MarkdownImportDocument` 和 `PreparedDocument` 传递服务端附件数据/manifest（backend dataclass，非 Core）；
  - `_envelope` 使用 manifest，不再硬编码 `attachments=[]`；
  - 仅有合法 manifest 时不再标 `ATTACHMENT_IMPORT_UNSUPPORTED`；
  - 在早返回前完成附件归属、pending 逻辑集合和已应用结果检查。Active 无 title/content 变化且附件未满足返回 400，保持 Core 分类器；
  - `classify_changes.current_attachments` 保持现状，不把 staging/DB 附件行当作 Active 触发条件。
- 修改 `backend/app/api/routes/import_export.py`：ZIP 先完整路径识别与有界读取，再按单篇归属规则进入服务；单篇 JSON 400、批量 JSON 逐篇 unsupported；含附件 ZIP 的 archived 目标 400。
- 测试：manifest round-trip、未知字段、重复 key、路径穿越、缺失文件、hash 不符、`.complete` 缺失、marks/activity、pending 零正式引用、同来源相同 pending 复用 、不同 集合拒绝并且均不创建新 staging、Active 附件-only 400 且零 staging。
- 退出：pending 创建后 `attachment` 行数为 0；`__a1_import.attachments` 完整且摘要稳定；Active 附件-only 明确拒绝。

### B3-T02 导入响应与清理

- `MarkdownService` 取得 staging_id guard 后才建目录，覆盖写入、pending/Draft 提交或失败处置。已提交 pending 保留；确认未提交才清自己的目录；不明确交 ORP。
- 若 Draft 导入携带附件：必须在开启文档/附件引用的 DB 写事务之前完成 StorageKeyLock 获取与正式发布（SQLite 单写者约束）；新事务复核目标及归档约束，commit 前 `verify_all`。
- 测试：导入失败/挂起/成功；staging 存在性；无孤儿（立即路径）；Draft 写事务前已持锁/已发布；`.complete` 未写时 approve fail-closed。
- 退出：IMP-19 通过（ZIP-only）；附件-only 拒绝项单独有真实证据。

## 6. B4：Active approve/reject

### B4-T01 审核决议与 DB Hook

- `governance.py`：共享 `review_id` 决议锁，与来源/身份/staging/storage 全局顺序一致。S0 严格预检、D23 恢复与关闭、持锁预发布、S1 受保护的归档状态复核 → Core → Hook → commit ①。
- `import_review_hook.py`：已有 origin/tags/links 的 DB 规则保持；只消费不可变发布计划并写附件引用，不在 Hook 加锁、复制、重读 Hash、发布、commit 或 release。
- ① 完成后释放 storage guard，清理 staging 后退出全部业务 guard，再执行独立索引②。②失败只告警。reject 轻量预检，损坏时保留逃生通道并跳过未证实 staging 清理。两条路由在同一 review 决议锁内重读及提交；清理失败不改变决议。
- 专项测试：合法 PREPARED MATERIALIZE 的恢复事务先结束、SQLite 发布时无业务写、guard 固定与末次 fencing；归档屏障、S0/S1 漂移、失败回滚、①/② 分界、不同来源键竞争只一终态。
- 退出：附件审核行为按 R1-IMP-08/09/10/11/14/37、R1.1-IMP-38 以及 LCK-07/08 取证。

### B4-T02 兼容与契约测试

- 测试既有 Batch A 无附件导入/审核不回归；`ATTACHMENT_REVIEW_UNSUPPORTED` 仅在能力关闭时返回。
- 根级 pytest 全量；ruff。
- 退出：Batch A 冻结测试全部通过。

## 7. B5：GC / ORP

### B5-T01 GC worker 与七态

- 新增 `backend/app/services/attachment_maintenance.py`：
  - `GcWorker`：due task 选择、claim、StorageKeyLock、引用复核、quarantine、24h、purge、退避、最大 8 次；
  - 状态迁移与物理代次严格按 GC §4–5，记录前/清除后崩溃、后继任务、引用回升及重复任务需可恢复；
  - 任务/存储双心跳；失配中止；
  - Windows 重试。
- 修改 `main.py`：lifespan 启动/停止 worker；单实例。
- 测试：七态每一条迁移、引用>0 cancel、同 key 双 worker、token 失配、24h 未到不删、24h 到删、hash 不符 manual、8 次永久、退避时间、Windows 占用；**claim 短事务提交后再取 StorageKeyLock** 的顺序断言；PG 行 TTL 过期但 advisory 存活时不得接管（LCK-10）。
- 退出：GC-01…12 通过（PG 另测）。

### B5-T02 ORP / staging sweep / 报告

- 同文件实现：
  - 300s 周期 + 启动一次；
  - 正式 blob 扫描、quarantine 残留、`.tmp`、staging 清扫；
  - staging 动作持共同 staging_id guard 并与 pending 提交串行，活动取标记/文件 mtime，空目录按标记前半成品分支，pending 引用始终优先；
  - pending manifest 引用集合；malformed fail-closed；
  - 一致性报告 JSON 原子写、保留 30 份（含 `staging_incomplete` 计数）；
  - PG 独立物理会话的扫描领导权；worker 停止、解锁/关闭先于 DB/ProcessLock 释放。
- 测试：孤儿 24h 入队、未满不删、共享引用不删、pending staging 不删、rejected staging 清理、`.complete` 缺失但无 pending 可清理、malformed manifest 跳过整轮、报告字段/脱敏、时钟未来 mtime、DB 不可用不删；断言不会以 staging 根的 mtime 判断子目录活动；验证活跃生产、隔离后 pending 恢复、终态及无任务隔离副本交接。
- 退出：ORP-01…07 通过；报告可作为验收证据。

## 8. B6：验收取证

- 在 Windows 真实环境跑完整套件；保存真实输出/截图/日志（不含密钥）。
- SQLite 全量；PostgreSQL 真实实例（`EXPLAINLAB_PG_TEST_URL`）迁移 up/down、锁、GC claim、检索回归。
- 并发：多线程上传同 key、双 GC worker、approve 与删除、ORP 与 pending。
- 故障注入：DB 断连、文件占用、跨卷、进程 kill、hash 损坏、manifest 篡改。
- 输出 `docs/acceptance/V2-A1-04-Batch-B/` 报告；逐项标注“已验证/有条件/未通过”，不得预填通过。
- 更新 `MILESTONES.md` **仅在 ChatGPT 明确批准后**；本轮禁止。
- 退出：Batch B 独立验收报告完成；等待独立审计，不自动进入 Batch C/BAK。

## 9. 文件改动清单（预估）

### 新增

```text
backend/app/services/attachment_storage.py
backend/app/services/attachment_validation.py
backend/app/services/attachments.py
backend/app/services/attachment_staging.py
backend/app/services/attachment_maintenance.py
backend/app/db/storage_lock.py
backend/app/api/routes/attachments.py
backend/tests/test_attachment_storage.py
backend/tests/test_attachment_validation.py
backend/tests/test_attachment_api.py
backend/tests/test_attachment_staging.py
backend/tests/test_attachment_review.py
backend/tests/test_attachment_gc.py
backend/tests/test_attachment_orp.py
backend/tests/test_storage_lock_sqlite.py
backend/tests/test_storage_lock_pg.py          # EXPLAINLAB_PG_TEST_URL 门控
backend/tests/test_attachment_pg.py            # 门控
backend/tests/test_attachment_windows.py       # win32 门控
```

### 修改

```text
backend/app/core/config.py
backend/app/main.py
backend/app/dependencies.py
backend/app/api/schemas.py
backend/app/api/routes/import_export.py
backend/app/api/routes/governance.py
backend/app/services/markdown.py
backend/app/services/import_review_hook.py
backend/app/services/repositories_v2.py
```

### 明确不修改

```text
knowledge-core/**                 # 实体/端口/ReviewService/A1-02/A1-03
backend/alembic/**                # 无新迁移
frontend/**                       # 无强制改动
MILESTONES.md                     # 本轮禁止
AGENTS.md
```

## 10. 每任务质量门

1. 只改本任务文件；`git diff --stat` 自查。
2. 相关测试真实运行；不得 mock 文件系统/数据库替代集成验收。
3. `uv run ruff check` 通过；不得 `ruff format`。
4. 根级 pytest 收集无冲突；不得排除整个目录。
5. PG/Windows 项未跑时明确标“未验证”，不得写成通过。
6. 每批结束记录真实输出到验收材料；不提交、不推送，除非用户另行授权。

## 11. 停止点

B1–B6 是路线，不是本轮执行项。Architecture Freeze 复审通过前，**不开始 B1**；本轮不修改任何业务代码/测试/迁移/MILESTONES，不执行 git add/commit/push。
