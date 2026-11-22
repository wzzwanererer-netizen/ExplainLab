# V2 · A1-04 · Batch A 实施报告

- 日期：2026-11-22
- 范围：非附件 Markdown 导入/导出、本地文档身份初始化、同步导入锁、审核 hook、Journal 恢复/归档/ROTATE
- 基线：`784b124`（A1-03 最终审计补充）；工作树未提交
- 结论：Batch A 业务闭环已实现并通过 SQLite 全量回归；真实 PostgreSQL 未验证；未提交、未推送

## 1. 交付范围

| 能力 | 状态 | 主要实现 |
|---|---|---|
| OS 单实例锁 | 已实现 | `backend/app/db/process_lock.py`，`msvcrt`/`fcntl`，有界重试，稳定码 `BACKEND_ALREADY_RUNNING` |
| `source-instance-id` 生命周期 | 已实现 | `backend/app/services/source_instance_id.py`，原子非覆盖创建、严格校验、ROTATE 替换 |
| `MarkdownItemRepository` / Tag / ImportOrigin 仓库 | 已实现 | `markdown_item_repository.py`、`repositories_v2.py` |
| 同步身份锁 `ImportCoordinator` | 已实现 | 每键一把 `threading.Lock`，引用计数回收，超时 `IMPORT_LOCK_TIMEOUT` |
| S0/S1 重读与幂等 | 已实现 | `MarkdownService._import_one`：S0 只读关闭 → 获锁 → S1 重读 → 写事务 → commit/rollback/close → 释放 |
| 单篇/批量非附件导入 | 已实现 | `POST /api/knowledge/import`、`/api/knowledge/import/batch`，同步 `def` |
| 单篇/ZIP 导出 | 已实现 | `GET /api/knowledge/{item_id}/markdown`、`POST /api/knowledge/export` |
| `ImportReport` | 已实现 | Core `knowledge_core/markdown/import_report.py`，逐项状态/错误/冲突/重复 |
| Draft 导入 + Active Review envelope | 已实现 | envelope `payload.__a1_import`，Core 只应用四字段，hook 同事务补齐 |
| approve/reject hook | 已实现 | `import_review_hook.py`，失败整体回滚、审核保持 PENDING |
| 链接恢复 | 已实现 | 复用 A1-03 `build_link_restorer`，导入 envelope 内恢复 |
| 导入后索引同步 | 已实现 | 路由 commit 后 `sync_index`，报告 `index_sync` |
| 本地身份 MATERIALIZE Journal | 已实现 | `source_identity.py`：PREPARED → 条件写 DB → 重读/摘要校验 → COMMITTED → archive |
| ROTATE / 恢复 / 归档 / 多轮 | 已实现（服务层） | 2a 先逐条物化；PREPARED 旧/新 ID 恢复；COMMITTED 只补归档；支持第二次独立 rotate |
| exporter 传输元数据与四个 Hash 解耦 | 已实现 | D22 剥离/注入、四类冲突零写入、DB 无 exporter 列/值 |
| 附件 | 按范围拒绝 | 固定码 `ATTACHMENT_IMPORT_UNSUPPORTED`、`ATTACHMENT_EXPORT_UNSUPPORTED`、`ATTACHMENT_REVIEW_UNSUPPORTED` |

## 2. 文件清单

新增：

| 文件 | 行数 | 说明 |
|---|---:|---|
| `backend/app/db/process_lock.py` | 158 | 进程级单实例锁 |
| `backend/app/services/import_coordinator.py` | 74 | 同步身份键锁 |
| `backend/app/services/source_instance_id.py` | 160 | 实例 ID 文件生命周期 |
| `backend/app/services/source_identity.py` | 970 | 身份审计、Journal、恢复、MATERIALIZE/ROTATE |
| `backend/app/services/journal_canonical.py` | 150 | Canonical JSON v1 / SHA-256 |
| `backend/app/services/markdown.py` | 1231 | 导入/导出编排、D22 预检、S0/S1、审核 envelope |
| `backend/app/services/markdown_item_repository.py` | 200 | 条目/来源读取与字段更新 |
| `backend/app/services/repositories_v2.py` | 236 | Tag / ImportOrigin / TagChangeLog 仓库 |
| `backend/app/services/import_review_hook.py` | 183 | 导入审核同事务补齐 |
| `backend/app/api/routes/import_export.py` | 297 | 导入/导出 HTTP 入口 |
| `knowledge-core/src/knowledge_core/markdown/service.py` | 187 | D22 原语、来源身份拆分（Core，无 Web/ORM 依赖） |
| `knowledge-core/src/knowledge_core/markdown/import_report.py` | 279 | 导入报告/Envelope |

修改：

| 文件 | 变更 |
|---|---|
| `backend/app/api/schemas.py` | 导入顶层 `attachments` 字段，单篇不得静默忽略 |
| `backend/app/core/config.py` | `data_dir`、`import_lock_wait_seconds` |
| `backend/app/db/session.py` | `get_session_factory` / `create_session` |
| `backend/app/dependencies.py` | 注入 identity / markdown service |
| `backend/app/main.py` | lifespan：锁 → ID → coordinator → identity 恢复门 → service |
| `backend/app/api/routes/governance.py` | 导入审核 approve/reject 接 hook 与身份锁 |
| `backend/tests/conftest.py`、`test_health.py` | `data_dir` 隔离 |

新增测试：

| 文件 | 用例数（当前） |
|---|---:|
| `backend/tests/test_batch_a_canonical.py` | 16 项（8 固定向量 + 严格解析，参数化展开） |
| `backend/tests/test_markdown_batch_a_import_export.py` | 32 |
| `backend/tests/test_markdown_batch_a_identity.py` | 26 |
| `backend/tests/test_batch_a_process_and_identity.py` | 30 |
| `knowledge-core/tests/test_markdown_service.py` | 28 |

## 3. 业务调用链

### 3.1 导入

```
POST /api/knowledge/import[/batch]（同步 def，线程池）
  → MarkdownService.import_documents
  → SourceIdentityService.recover_if_needed（恢复门）
  → _preflight：D22 冲突 / 来源身份拆分 / 附件边界（零 DB 写）
  → 逐篇 _import_one
       S0 短只读会话：读取既有来源/条目 → 关闭
       ImportCoordinator.keyed(身份键 / target / 匿名内容)
         S1 全新会话重读 → 幂等/变化/pending/ambiguous 判定
         _apply_import（item/tags/origin/metadata/links）
         commit / rollback → close
       释放锁
  → 路由 commit 后同步索引
  → ImportReport
```

### 3.2 审核

```
POST /api/reviews/{id}/approve（同步 def）
  → 预检 envelope → 身份锁
  → S1 重读审核与条目
  → Core ReviewService.approve（title/content/status/space）
  → ImportReviewHook.apply_approved（同事务：tags/metadata/ImportOrigin/links）
  → commit；任一点失败 rollback，review 保持 PENDING
```

### 3.3 本地身份与 Journal

```
GET 单篇导出
  → recover_if_needed
  → classify 1/2a/2b/3/4
  → 2a: materialize
       PREPARED 持久化 → 条件写 source_instance_id（保持 updated_at）
       → 重读 DB + 全库身份摘要 → COMMITTED → archive → 移除 current
  → 生成前端 Hash（不含 exporter）→ 注入 exporter_instance_id → 返回
```

## 4. 关键决策落实

- **D20 单一线程模型**：所有写入口为同步 `def`；只有 `ImportCoordinator` 一套同步锁；Session 在请求实际执行线程内创建/使用/关闭；S0 关闭后才获锁。测试用线程 ID、Session close 顺序、event loop ticker 验证。
- **D22 exporter 传输元数据**：导入先扫描重复保留键（YAML 折叠前），再剥离顶层保留键；导出先算 Hash、后注入。四类冲突均在任何 DB 写之前返回 `EXPORTER_METADATA_RESERVED_CONFLICT`；DB 无 exporter 列/值。
- **D23 身份与 Journal**：状态 1/2a/2b/3/4 互斥；2b 只由“恰好一条 COMMITTED MATERIALIZE”证明；ImportOrigin 状态优先级 `conflict > invalid > incomplete > duplicate > complete > none`；审计摘要覆盖全部 item 与全部原始 ImportOrigin 行；孤儿 fail-closed；PREPARED 恢复按 DB 空/等于/其他分流；COMMITTED 只补归档；current/archive 同 operation_id 同内容去重。
- **范围边界**：无新迁移/表/列/索引/依赖；未改 A1-02 Hash/canonical/codec、A1-03 链接契约、Core ReviewService、V1 API/GET 行为；附件、Backup/Restore、Batch D 未实现。

## 5. 本轮发现并修复的缺陷

1. 非法/半来源身份剥离后把原键放回 metadata → 现移除全部来源身份键并标 `legacy`。
2. 批量含附件被整批拒绝、单篇附件被静默忽略 → 逐篇 `UNSUPPORTED`；单篇显式固定码拒绝。
3. exporter ID 在服务初始化时缓存，ROTATE 后仍用旧值 → 改为每次读取当前 ID。
4. `ImportLockTimeout` 被归入通用 `IMPORT_FAILED` → 单篇 409 `IMPORT_LOCK_TIMEOUT`，批量逐项隔离。
5. 中文文件名/标题被 ASCII 白名单替换成 `_` → 改为仅替换非法文件系统字符，保留 Unicode。
6. `ExporterMetadataError` 逃出预检 → 包装为稳定码 `MarkdownServiceError`。
7. 保留键值为 `null` 时与“键不存在”混淆 → 按“键存在且值非法”拒绝。
8. 扫描器把孤立代理项键当作重复键 → 留给 codec 按非法构造处理。

## 6. 兼容性

- Python 全量回归：`1062 passed, 178 skipped`（SQLite；skip 主要为 PostgreSQL 门控模块）。
- 前端：72 项 Vitest 通过，`tsc -b` 通过，`vite build` 通过。
- `ruff check` 全仓通过；未运行 `ruff format`。
- `pyproject.toml`、`uv.lock`、`frontend/package.json`、`package-lock.json`、`backend/alembic/` 无改动。
- Core 独立性守护测试仍通过；核心 Markdown 模块无 FastAPI/Starlette/SQLAlchemy import。
- V1 GET/PATCH 回归包含在既有套件中通过；导出增加的来源/传输字段不影响 V1 schema。

## 7. 未完成/限制

- 真实 PostgreSQL 未执行：环境无 `EXPLAINLAB_PG_TEST_URL`、`psql`、`pg_isready`、`docker`。
- 未提供 `rotate-instance-id` CLI 入口；ROTATE 以服务层真实 DB/FS 测试验证，CLI 验收项未覆盖。
- Journal 崩溃矩阵覆盖“DB 后 COMMITTED 前”“ID 替换前/后”“current/archive 并存/损坏/摘要不符”；归档临时文件/rename/目录同步的逐点崩溃未逐一注入。
- Windows 目录 fsync 为 best-effort；不宣称断电持久。
- 附件导入/导出/审核按 Batch A 范围明确拒绝。

详见 `Batch-A-known-issues.md`。