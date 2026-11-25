# B3-T01 独立审核整改报告

**最终状态：B3-T01 IMPLEMENTED / PENDING INDEPENDENT REVIEW**

- 工作区：`D:\ExplainLab`
- 分支：`fix/m0-admission-and-m5-regressions`
- 基线 HEAD：`970c0d8ec05f0b8c68286839a56b14c74ea230c6`
- 触发材料：`ExplainLab-B3-T01-GPT-Review-Package.zip`（ChatGPT 独立审计，结论 CONDITIONAL PASS）
- 本轮性质：只修复已确认缺陷；不重新设计 B3，不进入 B3-T02 / B4 / B5。
- 未提交、未推送。

## 1. 整改项与结论

| 编号 | 审计缺陷 | 整改结论 | 证据 |
|---|---|---|---|
| P1-01 | staging guard 未覆盖完整生命周期 | 已修复 | [guard-lifetime-proof.md](guard-lifetime-proof.md) |
| P1-02 | 缺少 POSIX 目录级持久化 | 已实现，真实 POSIX 未验证 | [posix-durability.md](posix-durability.md) |
| P2-01 | 零字节附件未在 staging 前稳定拒绝 | 已修复 | [empty-attachment-rejection.md](empty-attachment-rejection.md) |
| P2-02 | 损坏 ZIP 压缩流可能映射为 500 | 已修复 | [corrupt-zip-mapping.md](corrupt-zip-mapping.md) |
| P2-03 | pending 查询失败时可能误删 staging | 已修复 | [pending-fail-closed.md](pending-fail-closed.md) |
| ZIP-01 | `ZipInfo.orig_filename` 原始 NUL 未检查 | 已修复 | 本文 §3.1 |
| ZIP-02 | 全 ZIP 压缩数据总量未纳入预算 | 已修复 | 本文 §3.2 |
| ZIP-03 | 根 `manifest.json` 未纳入资源预算 | 已修复 | 本文 §3.3 |
| ZIP-04 | 未选中条目的资源限制依据 | 已冻结并实现 | 本文 §3.4 |
| ZIP-05 | 100 MiB 上限 | 未放宽，真实大包取证 | 本文 §3.5 |

## 2. P1-01 staging guard 完整生命周期（实现）

`AttachmentStagingService.stage_from_zip`（`backend/app/services/attachment_staging.py`）：

1. 先完成纯内存 `parse_import_zip`（不创建任何目录、不写数据库）。
2. 计算 `staging_id` 后取得 `staging_guard(sid)`，**在 guard 内**检查目录不存在并创建 staging。
3. `.creating`、`blobs/`、每个 blob、`.activity`、`.complete`、manifest 校验全部处于同一 guard。
4. `with` 块交给调用方；`backend/app/services/markdown.py::_import_one` 在块内完成：
   ReviewRequest flush（pending 导入单）→ `session.commit()`。
5. 三态语义：
   - commit 成功：`lease.committed = True`，目录保留给 pending 审核；
   - commit 抛异常且已尝试提交（结果不明确）：`lease.keep_for_orp = True`，保留 staging 交 ORP；
   - 未提交的已知失败（例如构造 ReviewRequest 前抛错）：不设置标志，`stage_from_zip` 的 `finally` 在**仍持 guard** 时删除本次 staging。
6. `create_from_zip` 通过 `retain=True` 复用同一生命周期，不再在内部重复获取同一把非重入锁。
7. 锁顺序保持：review 决议锁（适用）→ ImportCoordinator 来源锁 → `identity_guard` → staging_id guard → `StorageKeyLock` → 业务 DB 写事务；`stage_from_zip` 位于来源锁/身份锁内部，未倒序。
8. pending 复用：`_reuse_pending` 在 `staging_guard` 内重新读取 pending 审核行（`_verify_pending_unchanged`，独立会话），并调用 `validate_manifest_locked` 验证物理 manifest；不再出现 S1 读状态到 guard 之间的漂移窗口。

## 3. ZIP 边界整改

### 3.1 原始 NUL 文件名

`_validate_zip_original_name` 在所有条目进入路径校验前检查 `info.orig_filename`；即使 `zipfile` 已将 `filename` 截断，原始中央目录名中的 `\x00` 仍被拒绝（400 `IMPORT_ARCHIVE_INVALID`）。

### 3.2 全 ZIP 压缩数据预算

遍历中央目录后先计算 `sum(info.compress_size for info, _ in validated) > max_total_bytes`，**所有条目（含未选中条目）**都计入压缩数据预算。未选中条目内容从不读取，但无法再用其压缩流绕过预算。

### 3.3 根 `manifest.json` 预算

`budgeted = selected + [manifest_info]`，文件大小与压缩大小均计入总预算；`manifest.json` 读取上限为 `max_total_bytes`。

### 3.4 未选中条目的冻结依据

- 未选中条目（既非 `attachments/`、也非 `.md`、根 `manifest.json`）**永不读取内容**，因此不可能触发解压放大写入内存；
- 其元数据仍受条目数、单条大小、压缩流总预算约束；
- 这是冻结设计允许的取舍，不是遗漏；审计可在 `parse_import_zip` 中逐行核对。

### 3.5 100 MiB 上限未放宽

- 常量仍为 `MAX_TOTAL_BYTES = 100 * 1024 * 1024`；
- 真实归档取证：构造 104 857 601 字节（100 MiB + 1）的真实 ZIP（`ZIP_STORED` 存储，文件 104 857 834 字节），解析器在元数据阶段拒绝为 `IMPORT_ARCHIVE_INVALID`；
- 原始输出：[evidence/remediation/real-100mib-boundary.log](evidence/remediation/real-100mib-boundary.log)，脚本：[evidence/remediation/real-100mib-boundary.py](evidence/remediation/real-100mib-boundary.py)。

## 4. 测试结果（真实运行）

| 套件 | 命令 | 结果 |
|---|---|---|
| B3-T01 专项 | `uv run pytest backend/tests/test_attachment_staging.py -o addopts="--import-mode=importlib" -rs` | 54 passed, 0 failed, 0 skipped |
| B1/B2 定向 | storage + validation + windows + api | 201 passed, 8 skipped（全部平台/PG 门控） |
| Batch A 定向 | 7 个 Batch A 模块 | 166 passed |
| 全量 backend+core | `uv run pytest -o addopts="--import-mode=importlib" -rs` | **1450 passed, 213 skipped** |
| Ruff（源码树） | `uv run ruff check backend knowledge-core` | All checks passed |
| Ruff（仓库根） | `uv run ruff check` | 8 个既有错误，全部位于**未跟踪的历史证据副本** `docs/acceptance/...B1-environment-recovery/evidence/*.py`、`docs/audit/...freeze-review-package/source-evidence/...`；不是本轮源码 |
| Git 空白检查 | `git diff --check` | exit 0（仅 CRLF 提示） |

原始日志：[evidence/remediation/](evidence/remediation/)。完整索引见 [test-evidence-index.md](test-evidence-index.md)。

B3 专项 54 项全部真实执行（Windows tmp 文件系统 + 真实 SQLite），无 mock FS/DB，无 skip 冒充通过。

## 5. 验证状态矩阵（不虚报）

| 项 | 状态 | 依据 |
|---|---|---|
| Windows + SQLite 真实行为 | **已验证** | 54 项 B3 测试；真实文件与数据库 |
| POSIX 目录 fsync 代码路径 | **已实现，未在真实 POSIX 运行** | Windows 主机无 Linux 依赖环境；Windows 分支明确 no-op |
| 真实 PostgreSQL | **未验证** | `EXPLAINLAB_PG_TEST_URL` 未设置；本机无 psql/pg_isready/docker 可用；213 项 PG 测试 skip |
| 100 MiB 大包 | **已验证解析器预算拒绝** | 真实 100 MiB + 1 ZIP；未执行完整 HTTP 导入（会在解析阶段拒绝） |
| 进程崩溃窗口 | **未验证** | 本轮未做写入中 kill 取证，不声明崩溃一致性 |

## 6. 约束遵守

- 未修改 B1/B2 生产代码：`attachment_storage.py`、`backend/app/db/storage_lock.py`、`attachment_validation.py`、`attachments.py`、`routes/attachments.py` 的当前 SHA-256 与 B2 审计记录逐项一致（见 [evidence/remediation/b1-b2-current-hashes.txt](evidence/remediation/b1-b2-current-hashes.txt)）；`test_attachment_api.py` 当前哈希与最初 B2 包不同，但其 mtime 为 11:29（早于本轮 16:38 起改），属此前 B2 整改，不是本轮改动。B1/B2 文件本轮 mtime 均早于本轮起始时间。
- 未修改 Knowledge Core、Core `ImportReport`、ReviewService/B4 事务骨架、数据库迁移、依赖清单、冻结设计。
- 未删除、跳过或弱化任何既有测试；B3 测试数由 34 增至 54。
- 未提交、未推送；未进入 B3-T02/B4/B5。
- 最终状态：**B3-T01 IMPLEMENTED / PENDING INDEPENDENT REVIEW**，等待 ChatGPT 最终审计。