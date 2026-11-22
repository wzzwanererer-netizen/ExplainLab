# Batch A 最终整改报告

- 基线：HEAD `784b1248065424e07273b272d6016cc121bc606c`，分支 `fix/m0-admission-and-m5-regressions`
- 上位材料：ChatGPT 第二轮独立审计（`docs/acceptance/V2-A1-04-Batch-A/audit-round2/`）
- 本轮性质：仅修复、测试与文档同步；未提交、未推送、未进入 Batch B
- 本轮新增测试：39 项（逐项映射见 §3）

## 1. 修改文件与 before/after

| 文件 | 类别 | before SHA-256 | after SHA-256 | diff |
| --- | --- | --- | --- | --- |
| `backend/app/services/source_identity.py` | 代码 | `1fd4e2e2d49246e82a71f38e88cbed4ca0fa192a7906b7225f912a8051ec43c1` | `9c017593179e5a2cc1621301e35cad553893af274bfb8e4ed506321ae51f895a` | `diffs/backend__app__services__source_identity.py.diff` |
| `backend/app/services/source_instance_id.py` | 代码 | `96ae5fe80c46115b95356aaed347865afaff15e5943676b4b65a69f5ddd8de3f` | `f41955ced1be52af02ec9ba5ce547c7895e32bab1c03aa47f29be0ecf3951e22` | `diffs/backend__app__services__source_instance_id.py.diff` |
| `backend/app/services/markdown.py` | 代码 | `aac4716bb7947aeaadbf3010a39566fab017659c7eae4f0288ac25e90704c6b5`（逆向重建） | `db1255bafbaffd3b3637818a3937274518ef832abdf2cd2a27328363f868e7ac` | `diffs/backend__app__services__markdown.py.diff` |
| `backend/app/services/import_review_hook.py` | 代码 | `edf6c1a5aeb1321328ceac1f9a3b28a794cf6d64f043c22efe016417a0505469`（逆向重建） | `cc2df0452469652cfa43f4a91990f48912f2aa2fb6651a55c919f5c11fa80c16` | `diffs/backend__app__services__import_review_hook.py.diff` |
| `backend/app/api/routes/governance.py` | 代码 | `d1822d5bc34d659b2589233e159796429407061cb015a7db039a926109d7fee1`（逆向重建） | `1537249912cc1f9d2a68105e6401aafb2e1f6e49ce4e3c62e4e5309e1c1bc722` | `diffs/backend__app__api__routes__governance.py.diff` |
| `backend/tests/test_markdown_batch_a_identity.py` | 测试 | `055b05a5de5ec743d713ef17a267c6e221b8225a6df52920f1b2be20ebaaf942` | `383d749ede40eaf3dbd8d01c0ef9ee3a86be5e8f5909ac263e9d110960193264` | `diffs/backend__tests__test_markdown_batch_a_identity.py.diff` |
| `backend/tests/test_markdown_batch_a_import_conflict.py` | 测试（新） | 不存在 | `e35518cc3702a01f47d5f076ddb109ac8e1223b67a02b47b5c396de3ba26c0ce` | 新文件 |
| `backend/tests/test_batch_a_fault_injection.py` | 测试（新） | 不存在 | `a0b7ccb6a737601f3e18f8d08b0ad4f1ec3c2d8720c0b77eae795dc6264c113d` | 新文件 |

- `before-sha256.tsv` 与 `before/` 为整改前快照；`source_identity.py`、`source_instance_id.py`、`test_markdown_batch_a_identity.py` 直接取第二轮审计快照（即本轮整改前状态）。
- `markdown.py`、`import_review_hook.py`、`governance.py` 无审计快照，由 `evidence/reconstruct_before.py` 逆向应用本轮编辑重建，每处替换强制“恰好 1 次”。
- `backend/app/services/file_write.py` 本轮**未修改**（SHA-256 `64dc50…bd04`，与第二轮审计快照逐字节一致）。
- `backend/tests/test_batch_a_file_write.py` 在本轮中途一度追加了与 `test_batch_a_fault_injection.py` 重复的 8 项测试；为避免重复覆盖，已移除重复类并恢复为第二轮审计状态（SHA-256 `a9cf54…e36d`，逐字节一致），最终**净修改为零**。

## 2. 逐项整改

### P1-01 — 空数据目录冲突不得写身份文件

**缺陷**：`materialize()` 在只读分类之前调用 `self._store.ensure()`；当数据目录为空且条目处于冲突态（ImportOrigin + COMMITTED MATERIALIZE）时，会先创建实例 ID 文件再失败，违反“恢复优先、冲突零身份写入”。

**实现**（`source_identity.py`）：

1. 保持 `with self._journal_lock: self._recover_locked()` 恢复门在最前，不绕过 Journal 恢复。
2. 先 `classify(session, item_id)` 只读分类：
   - 冲突态 / 非 2a：立即 `SourceIdentityError(SOURCE_DOCUMENT_UNMATERIALIZED)`，**不**调用 `ensure()`；
   - 2b：返回既有 `classified.source_instance_id`（`assert` 非空），不重写 ID；
   - 仅确认 2a 后才 `target = self._store.ensure()`。
3. 2b 报告不再依赖 `ensure()` 的返回值，避免“读 ID”副作用。

**测试**（7 项）：`TestMaterializeClassificationBeforeIdentityWrite`

- 冲突 + 既有 ID：ID 文件与 Journal 字节不变；
- 冲突 + 空身份目录：不产生任何 ID 文件；
- 空数据目录 + ImportOrigin + DB 实例 ID：不创建 ID；
- PREPARED Journal + 冲突：恢复不绕过、Journal 字节不变；
- 正常 2a：分类后创建并物化；
- 正常状态 1：物化不创建本地 ID；
- 正常 2b：不重建、不重写 ID。

### P1-02 — 导入不得制造身份冲突

**缺陷**：已物化（存在 COMMITTED MATERIALIZE）的条目仍可经“直接导入 / 批量导入 / 审核批准”追加 ImportOrigin，形成 §22.2 冲突态；且“导入检查”与“导出物化”之间无串行化，存在并发窗口。

**实现**：

1. `SourceIdentityService` 新增 `identity_guard()`：在同一把 Journal RLock 内先 `_recover_locked()`，再让调用方完成“分类校验 + DB 写入 + commit”；新增 `has_committed_materialize()` 读取 current+archive 的 COMMITTED MATERIALIZE 索引。
2. `markdown._import_one`：把 `self._coordinator.keyed(lock_key)` 与 `self._identity.identity_guard()` 合并为同一 `with`，覆盖 `_apply_import` 与 `session.commit()`。
3. `markdown._apply_import`：解析出既有条目后，若 `has_committed_materialize(existing.id)`，在写任何导入字段之前抛 `MarkdownServiceError(SOURCE_IDENTITY_CONFLICT, 409)`，按条目隔离，批次中其他文档继续。
4. `import_review_hook.ImportReviewHook(session, identity)`：`apply_approved` 在 Core approve 之后、任何导入字段写入之前做同一检查并 fail-closed；路由回滚整事务，审核单保持 PENDING。
5. `governance.approve_review`：`with context, identity.identity_guard():`，钩子注入 identity；`reject_review` 同样注入（reject 不写身份，保持零写入）。
6. 这是对冻结契约 §22.2 的**执行**而非变更：未新增/修改契约，未改 DB schema，未改状态定义。

**测试**（7 项）：`TestImportCannotCreateMaterializeConflict`

- 同身份导入已物化条目 → 拒绝，item/origin/link 计数、Journal 归档、ID、正文、实例字段零变化；
- 不同身份导入 → 拒绝且零写入；
- 已存在重复 origin 的物化条目 → 不追加、不覆盖；
- 批量导入：冲突项报错、无关新文档正常创建（事务按条目隔离）；
- Active 条目 → 在创建审核单之前拒绝；
- 审核待决期间被导出物化 → 批准返回 409 `SOURCE_IDENTITY_CONFLICT`，审核单仍 PENDING，正文/状态/身份不变；
- 不完整 ImportOrigin（`source_instance_id=NULL`）+ MATERIALIZE → 仍拒绝（§22.2 任意 ImportOrigin 即冲突）。

### P1-03 — ROTATE 冲突专项测试（不改语义）

**结论**：现有 `rotate()` 已按状态跳过冲突条目（state 3 不物化、不覆盖、不认领），state 4 明确阻断；本轮**未修改** D23/Journal/ROTATE 语义，仅补充共存场景测试。

**测试**（2 项）：`TestRotateMaterializeOriginConflict`

- 仅冲突条目：ROTATE 前记录 `(operation_id, item_id)` 集合，ROTATE 后集合不变（既有 MATERIALIZE 记录保留、不新增）；`materialization_items` 为空；冲突条目仍可识别（state 3）；审计摘要与 DB 快照一致；导出器替换为新实例；
- 冲突 + 合法 2a：仅 2a 被物化；冲突条目未被物化/覆盖；落盘 ROTATE 记录的审计摘要与 DB 计算值一致。

### P2-01 — InterruptedError

`file_write.write_all` 对 `InterruptedError` 重试；其他异常立即传播。测试 3 项：首次中断后成功、连续多次中断、先中断后 OSError（只保留已写前缀，不重复、不补齐、不死循环）。

### P2-02 — fsync 失败

各发布路径在 fsync 失败时不得发布不完整文件，既有有效文件保留，临时文件清理：Journal current、Journal archive、ID 创建、无硬链接回退、ID replace。测试 5 项。

### P2-03 — close 失败（发现并修复真实缺陷）

**缺陷**：`SourceInstanceIdStore.ensure()` 的回退路径（`os.link` 不受支持 → `O_EXCL` 直接写正式文件）中，`write_all` + `fsync` 已成功、随后 `os.close` 抛错时，旧的 `except BaseException` 会 `unlink(self.path)`，把**已完整落盘的有效正式 ID** 删除。

**修复**（`source_instance_id.py`）：引入 `write_ok`，仅在“写入/fsync 未成功”时移除半成品；fsync 成功后 close 失败只传播异常，不删除正式 ID。`os.close` 仍在 `finally` 中执行，无 fd 泄漏路径。

**测试**（5 项）：Journal current/archive close 失败、ID 创建 close 失败、ID replace close 失败、回退路径 close 失败保留完整有效 ID。

### P2-04 — os.replace 失败

- Journal current：replace 失败保留旧 current、清理 `.tmp`（Journal 恢复读取旧记录，行为不变）；
- ID replace：失败保留旧 ID、清理临时文件；
- 归档不再使用 `os.replace`：`archive_committed` 改走原子不覆盖发布，测试锁定“归档使用 link 而非 replace 覆盖”。
测试 3 项。

### P2-05 — os.link FileExistsError

`SourceInstanceIdStore.ensure()` 在 link 发现目标已存在时，重新读取并校验既有 ID：

- 合法 UUID → 直接返回既有值，不覆盖、不删除；
- 非法内容 → 抛 `SOURCE_INSTANCE_ID_INVALID`，**不删除**既有文件、不误入回退删除；
- 两种竞态均由 monkeypatch 在 `os.link` 调用瞬间创建目标模拟。测试 2 项。

### P2-06 — 归档竞态

**缺陷**：`archive_committed` 先 `target.exists()`，再 `os.replace(tmp, target)`；两次调用之间若他人创建了同 operation_id 归档，会被静默覆盖。

**实现**（`source_identity.py`）：新增 `_publish_archive_no_overwrite(tmp, target, payload)`：

1. 先 `os.link(tmp, target)`：原子且目标存在即 `FileExistsError`；
2. 不支持硬链接时退回 `os.open(O_CREAT|O_EXCL|O_WRONLY, 0o600)`；写入/fsync 失败则移除半成品；
3. 无论走哪条路径，最后**重新读取 target 逐字节比对 payload**，不一致抛 `JOURNAL_CORRUPT`，绝不覆盖。

保留同 operation_id 同内容的幂等短路。测试 5 项：不同 operation_id 均可归档、同 id 同内容幂等、同 id 不同内容 fail-closed、发布瞬间被写入冲突内容不覆盖、发布瞬间被写入相同内容接受且无 `.tmp` 残留。

## 3. 新增测试统计

| 项 | 测试类 | 数量 | 文件 |
| --- | --- | --- | --- |
| P1-01 | `TestMaterializeClassificationBeforeIdentityWrite` | 7 | `test_markdown_batch_a_identity.py` |
| P1-02 | `TestImportCannotCreateMaterializeConflict` | 7 | `test_markdown_batch_a_import_conflict.py` |
| P1-03 | `TestRotateMaterializeOriginConflict` | 2 | `test_markdown_batch_a_identity.py` |
| P2-01 | `TestWriteAllInterrupted` | 3 | `test_batch_a_fault_injection.py` |
| P2-02 | `TestFsyncFailure` | 5 | `test_batch_a_fault_injection.py` |
| P2-03 | `TestCloseFailure` | 5 | `test_batch_a_fault_injection.py` |
| P2-04 | `TestReplaceFailure` | 3 | `test_batch_a_fault_injection.py` |
| P2-05 | `TestLinkFileExists` | 2 | `test_batch_a_fault_injection.py` |
| P2-06 | `TestArchiveNoOverwrite` | 5 | `test_batch_a_fault_injection.py` |
| **合计** | | **39** | |

## 4. 设计取舍与并发说明

- **fail-closed 而非自动选边**：P1-02 选择拒绝并回滚，不替用户挑选“可信来源”，符合 §22.2“冲突不选记录”的冻结规则。
- **串行化粒度**：`identity_guard` 是全局 Journal 锁；导入/审核提交与 MATERIALIZE/ROTATE 互斥。代价是导入吞吐下降，但身份一致优先；本轮不引入更细粒度锁，避免扩大改动面。
- **锁顺序**：导入/审核固定“先 coordinator keyed 锁、后 Journal 锁”；MATERIALIZE/ROTATE 只取 Journal 锁，不存在反向获取路径，不构成锁环。Journal 锁为可重入锁，`has_committed_materialize` 在 guard 内重复获取安全。
- **审核拒绝路径**：reject 不写任何导入字段，保留 `context` 锁；仅注入 identity 以满足钩子签名，不额外持锁。
- **状态 1 → 导出 → 再导入** 仍允许：此时不存在 MATERIALIZE 记录，不是 2b；现有导入/导出测试继续通过。
- **未变更契约**：未动 Core Hash、V1、D22–D24、Canonical JSON、schema/迁移、ImportOrigin 审计规则。

## 5. 残余风险

见 `final-known-issues.md`。核心未闭环项：真实 PostgreSQL 未验证、POSIX 完整导入未验证；文件故障注入覆盖进程内异常，不覆盖真实断电/介质损坏。