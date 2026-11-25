# B3-T01 实施报告

**状态：已实现，待独立审核。** 依据冻结的 Batch B 设计、B1 正式 PASS、B2 正式 PASS 与 B3 READY FOR DEVELOPMENT。

## 1. 范围

B3-T01 完成：

- `AttachmentManifestItem` 严格 schema；
- ZIP-only 附件解析、路径安全、单篇归属与有界读取；
- `<data_dir>/import-staging/<staging_id>/` staging 创建；
- `.creating`、逐附件刷新 `.activity`、最后原子写 `.complete`；
- manifest/目录/文件/size/hash/MIME 校验；
- `discard_committed`、`discard_rejected`、`sweep_candidate`；
- 与现有 Markdown 导入的 Active pending 集成；
- JSON 单篇 400、批量逐篇 unsupported、附件 ZIP 归档目标 400、Active 附件-only 400、零文档附件-only 分流；
- pending 逻辑附件集合复用/冲突、已应用附件满足检查。

未实现：

- B3-T02 的 Draft 附件正式发布与导入响应清理；
- B4 approve/reject 附件引用写入；
- B5 GC/ORP worker 与物理 staging 隔离/清除；
- 前端、迁移、依赖清单。

B3-T01 对 Draft/新文档携带物理附件明确返回 400 `ATTACHMENT_IMPORT_UNSUPPORTED`，不创建 staging，不静默丢弃。Draft 发布属于 B3-T02。

## 2. 实现结构

新增 `backend/app/services/attachment_staging.py`：

- `AttachmentManifestItem`：Pydantic `extra="forbid"`，严格 int/str，UUIDv4、ordinal、blob、filename、MIME、size、SHA-256 约束；
- `parse_import_zip` / `inspect_zip`：全路径先校验，再有界读取；
- `AttachmentStagingService.create_from_zip`；
- `validate_manifest`；
- `staging_activity_at`；
- `discard_committed` / `discard_rejected` / `sweep_candidate`；
- `pending_staging_ids`：读取真实 pending review envelope，manifest 损坏时 fail-closed。

修改 `backend/app/services/markdown.py`：

- `MarkdownImportDocument.attachment_source` 传递服务端 ZIP 解析结果；
- `PreparedDocument` 携带 manifest、staging_id、staging 目录；
- `_read_state` 解析 pending envelope 附件并纳入签名；
- `_attachment_context` 在早返回前完成目标/归档/Active/内容变化检查；
- `_skipped_result` 检查已应用附件的正式引用与 blob；
- `_reuse_pending` 比较排序无关的逻辑集合并验证 staging `.complete`；
- `_envelope` 使用真实 manifest，不再硬编码 `attachments=[]`；
- 保持 `classify_changes(current_attachments=[])` 与 Core `ImportReport` 不变。

修改 `backend/app/api/routes/import_export.py`：

- 使用 B1 已装配的 `app.state.attachment_storage` 惰性构造 staging service，不改 `main.py`/`dependencies.py`；
- ZIP 先完整解析与归属，再进入 MarkdownService；
- 单篇 JSON 附件 400；批量 JSON 逐篇 unsupported；ZIP 顶层 JSON 附件字段整包 400；
- 归档目标、Active 附件-only、零文档附件-only 由服务端稳定码返回；
- `AttachmentStagingError` 映射到冻结 HTTP 状态与错误码。

## 3. 关键行为

### 3.1 Active 内容变更

只有在来源/身份锁与 S1 复核后，且目标为 Active、title/content 发生变化时，才创建 staging 并生成 pending。

- staging 创建位于 DB 业务写事务之外；
- pending envelope 写入完整 attachments；
- `context_digest` 由 Core 现有 `ImportEnvelope` 计算，覆盖 attachments；
- `ReviewService.submit` 后由既有 session 唯一提交；
- `attachment` 表零新增行；
- item 不变。

### 3.2 Active 附件-only

无 title/content 变化且附件未满足时返回 400 `ATTACHMENT_ONLY_IMPORT_UNSUPPORTED`，零 staging、零 pending、零业务写。

### 3.3 已应用同 Hash

如果同 payload 已应用：

- 每个请求 storage_key 已有该 item 正式引用，且正式 blob 能验证 → 返回 SKIPPED，warning `attachments_already_satisfied`；
- 缺引用且 Active → 400 `ATTACHMENT_ONLY_IMPORT_UNSUPPORTED`；
- 文件缺失/损坏 → 稳定存储错误，不静默成功。

### 3.4 Pending 复用

逻辑集合为排序无关的 `(storage_key, filename, mime, size)`：

- 完全相等且既有 staging `.complete` 验证通过 → `reused_pending`，不建第二份 staging；
- 集合不同（含一侧为空）→ 409 `SOURCE_HAS_PENDING_IMPORT`，不建第二份 staging；
- 集合相等但 staging 缺失/损坏 → 409 staging 稳定错误，fail-closed。

### 3.5 失败与清理

- ZIP 任何路径、大小、MIME、hash 校验失败发生在 staging 创建之前；
- staging 创建失败会删除 `.complete` 并尽力清理未完成目录（整改后在 guard 内清理）；
- 已知的提交前失败在仍持 guard 时删除本次 staging（整改后语义，详见 remediation 报告）；
- commit 抛异常（提交结果不明确）保留 staging，释放 guard，交 ORP（B5）；
- `discard_*` 在 pending 引用存在时拒绝删除。

## 4. 实际运行结果（初版，整改前）

> 下表是初版实现的运行快照。独立审计整改后的最新结果为
> **B3-T01 54 passed；全量 1450 passed / 213 skipped**，见
> [B3-T01-remediation-report.md](B3-T01-remediation-report.md) 与
> [test-evidence-index.md](test-evidence-index.md)。

| 质量门 | 命令 | 结果 |
|---|---|---|
| B3-T01 | `uv run pytest -q backend/tests/test_attachment_staging.py -o addopts=""` | **34 passed / 0 failed / 0 skipped / exit 0**（初版） |
| B1/B2 回归 | B2 API + B1 storage/validation/GC/lock SQLite | **243 passed / 7 skipped / 0 failed / exit 0** |
| Batch A 回归 | import/export + conflict + identity | **84 passed / 0 failed / 0 skipped / exit 0** |
| 全量 backend+core | `uv run pytest -o addopts="--import-mode=importlib" -q` | **1430 passed / 213 skipped / 0 failed / exit 0** |
| Ruff | `uv run ruff check backend knowledge-core` | **All checks passed / exit 0** |
| Git diff check | `git diff --check` | **exit 0** |

213 项 skip 必须区分：**210 项真实 PostgreSQL 环境门控** + **3 项平台/卷门控**。skip 不是 pass；本轮没有真实 PostgreSQL 实例，不声明 PG 验证通过。

B1/B2 的 7 项 skip 为真实 PG/Windows 平台门控，不是通过。

## 5. 禁止项核对

- 未修改 Knowledge Core、`ReviewService`、Core `ImportReport`；
- 未修改 B1/B2 已验收生产文件；B2 `SOURCE-SHA256SUMS` 六项生产文件哈希重新核对一致；
- 未新增迁移、表、列、索引；
- 未修改 `pyproject.toml`、`uv.lock`、`package.json`、`package-lock.json`；
- 未实现 B3-T02、B4、B5；
- 未 commit、未 push。

## 6. 结论

B3-T01 实现与 B3-T01 范围内真实 SQLite/Windows 文件系统测试完成，等待独立审核。

不声明 Batch B 通过；不自行进入 B3-T02/B4/B5。