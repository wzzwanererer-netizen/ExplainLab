# V2 K1+K2 整改后专项审计报告 — SQLite 乐观并发控制（P2）字段覆盖完整性

> **审计对象**：K1+K2 整改批（提交 `ccf6194`）后，链接重建步 7 P2 乐观前置条件是否覆盖**全部影响重建计划正确性的字段**。
> **方法**：真实源码审查（file:line）+ 可复现故障注入测试（SQLite + 真实 PostgreSQL），修复前后对照取证。**不以理论推断代替实跑**。
> **日期**：2026-11-20。**分支**：`fix/m0-admission-and-m5-regressions`。
> **标签**：【已验证事实】/【发现的缺陷】/【修复内容】/【尚待验证】/【已知局限】。
> **边界**：不改 Core 纯函数/端口签名/数据模型/迁移/依赖；不删门禁/不弱化断言/不绕过异常；不进入 A1-04；不 push；不改 MILESTONES.md。

---

## 1. 审计范围与关键源码事实

【已验证事实】键计算与唯一域（`knowledge-core/src/knowledge_core/markdown/links.py:83–98`）：

```
normalized_link_key(title, alias) = norm(title) + "\x1f" + norm(alias or "")
```

- `target_title`、`alias` **均**派生 `new_key`；`source_id` **不**进入 `new_key`。
- 唯一约束 `uq_link_source_key = UNIQUE(source_item_id, normalized_link_key)`（`backend/app/models.py:310`）→ `source_id` 决定**唯一域**。
- 计划按 `(source_id, new_key)` 分组判碰撞（`link_service.py:947`）；`new_key = link_key_for_version(target_version, row.target_title, row.alias)`（`link_service.py:945`）。

【已验证事实】门禁 C（`check_plan_freshness`，`link_service.py:290–405`）比对 **6 字段**（link_id/source_id/normalized_link_key/link_normalization_version/target_title/alias，原始 Unicode 精确等值）**并按当前 title/alias 重算 new_key**（:373–377）。关闭**窗口①**（计划生成 → apply 重读）。

【已验证事实】步 7 P2 前置（**修复前**，`services/links.py:410–427`）仅 guard **3 字段**：`id + old_key + old_version`。`LinkKeyUpdate` 已携带 `source_id/target_title/alias`（`link_service.py:150–163, 992–1003`），但前置未用。

【已验证事实】步 8 写后复核（`services/links.py:429–447`）检查：版本同构于 target、`(source_id,key)` 唯一、**治理列基线**（target_id/resolution/cross_space/created_at）、knowledge_item 基线。**不**复核 `key == normalize(当前 title, alias)`，治理基线**不含** title/alias/source_id。

## 2. 逐项审查结论（七问）

| # | 问题 | 结论 | 证据 |
|---|---|---|---|
| 1 | source_id 影响新键计算或唯一性？ | 不影响 new_key；**影响唯一域** (source_id,key) 与碰撞分组 | links.py:83–98；models.py:310；link_service.py:947 |
| 2 | target_title 影响新键计算？ | **是**（norm(title) 为键首段） | links.py:91–95 |
| 3 | alias 影响新键计算？ | **是**（norm(alias) 为键次段） | links.py:94–95 |
| 4 | 并发改上述字段后 P2 仍可能 rowcount=1？ | **修复前：是**（键列/版本未同步改时）；**修复后：否** | before-fix-sqlite.txt（4×DID NOT RAISE）；after-fix-*（全拒绝） |
| 5 | rowcount=1 是否应用过期计划？ | **修复前：是**（title/alias 漂移→过期键提交）；**修复后：否** | diag-before-fix.txt（具体过期键） |
| 6 | PG 表锁完整覆盖这些并发写入？ | **是**（SHARE ROW EXCLUSIVE 字段无关，阻一切写） | test_pg_lock_blocks_concurrent_correctness_field_drift（真实双连接，3 字段均 lock timeout） |
| 7 | SQLite 是否有 P2 未覆盖的其他窗口？ | 修复后正确性字段窗口②全覆盖；写阶段→提交由 RESERVED 锁阻；治理列由步 8 兜底；phantom 由 DB UNIQUE/步 8 兜底。**残余为活性（BUSY）非正确性** | test_sqlite_write_phase_blocks_concurrent_commit；test_p2_governance_drift_rejected_by_step8_baseline；test_p2_phantom_insert_drift_after_reread_rejects |

## 3. 【发现的缺陷】根因与复现证据

**缺陷**：步 7 P2 前置（3 字段）**窄于**门禁 C 快照（6 字段）。窗口②（门禁 C 重读 → 步 7 写）内，若并发事务修改 `target_title`/`alias`（派生 new_key）或 `source_id`（唯一域）**而未同步修改存储键列与版本**，则 `old_key`/`old_version` 前置仍匹配 → **rowcount=1** → 写入按**旧字面**算出的 `new_key`。步 8 版本同构通过（全表已置 target），且**不复核 key-title 一致性** → **过期键被提交**，违反重建核心不变量 `key == normalize(当前 title, alias)`。

【已验证事实】**修复前真实复现**（SQLite，`evidence/before-fix-sqlite.txt`）：`test_p2_source_id_drift` / `test_p2_target_title_drift` / `test_p2_alias_drift` / `test_p2_combined_field_drift` 四项 **DID NOT RAISE LinkRebuildPostWriteError**（4 failed, 4 passed）——即过期计划被应用并提交，而非拒绝。

【已验证事实】**具体过期键取证**（`evidence/diag-before-fix.txt`，临时诊断，运行后已删除）：

```
report.status             = rebuilt          ← 已提交（未拒绝）
r1.target_title (current) = 'Drifted Title'  ← 窗口②并发漂移后的当前标题
r1.normalized_link_key    = 'targetone\x1f'  ← 按旧标题 "Target One" 算的过期键
key for CURRENT title     = 'driftedtitle\x1f' ← 当前标题应有的键
table versions            = {2}              ← 版本同构掩盖了 key-title 不一致
```

**根因定位**：`services/links.py` 步 7 `UPDATE … WHERE id AND old_key AND old_version`（修复前 :413–417）缺少 `source_id/target_title/alias` 前置；步 8 无 key-title 一致性复核。

**可达性界定（诚实）**：
- 经**应用路径** `update_link`（`services/links.py:175–194`）改 title/alias 时**同步重算键列** → 凡规范化不同的字面变化必改 `old_key` → 修复前 P2 亦能拒（rowcount=0）；规范化不变的字面变化（如大小写/空白折叠等价）则 new_key 本就相同，无过期。`update_link` **从不**改 `source_item_id`。
- 缺陷经**原始/不一致并发写**（改 title/alias/source 却不更新键列，违反 `key==normalize(title,alias)` 应用不变量）真实可达——已用同事务原始 UPDATE 故障注入复现。属**纵深防御缺口**：P2 字段覆盖应与门禁 C 对齐，不应依赖「所有写者都维护键列一致」这一外部假设。

## 4. 【修复内容】最小方言中立修复

**原则遵循**：优先方言中立乐观前置（审计 §4.3）；不删门禁/不弱化断言/不绕过异常；保留 Core 纯函数/端口/模型；零新增依赖/迁移。

**改动**（`evidence/fix.diff`，仅 backend 适配层，2 文件 +21/−9）：步 7 `UPDATE` 的 `WHERE` 由 3 字段扩至**门禁 C 同口径 6 字段**——追加 `source_item_id == str(u.source_id)`、`target_title == u.target_title`、`alias == u.alias`（取自计划 update 已携带、门禁 C 已校验等于重读快照的字段）。`rowcount != 1` → `LinkRebuildPostWriteError` → 整体回滚零写入（语义不变）。同步更新 `services/links.py` 与 `db/locking.py` docstring/注释/错误文案。

```python
update(KnowledgeLinkORM).where(
    KnowledgeLinkORM.id == str(u.link_id),
    KnowledgeLinkORM.source_item_id == str(u.source_id),   # 新增：唯一域
    KnowledgeLinkORM.normalized_link_key == u.old_key,
    KnowledgeLinkORM.link_normalization_version == u.old_version,
    KnowledgeLinkORM.target_title == u.target_title,        # 新增：派生 new_key
    KnowledgeLinkORM.alias == u.alias,                      # 新增：派生 new_key（None→IS NULL）
).values(normalized_link_key=u.new_key, link_normalization_version=u.new_version, updated_at=now)
```

**方言中立性**：纯 SQLAlchemy 表达式，SQLite/PG 同一段代码、零方言分支；`alias == None` 经 SQLAlchemy 生成 `IS NULL`，双方言一致（`uq_link_source_key` 已修复 NULL≠NULL 唯一失效）。**不新增 SQL 语句**（仍每行一条 UPDATE）→ T39 顺序守护语句计数不变。

**不破坏 K1/K2 既有行为**：
- 无漂移时 6 字段恒匹配 → rowcount=1（控制组实证，不误拒）。
- 重建只写 key/version/updated_at，**不写** title/alias/source_id → 正常重建中前置字段自洽。
- K1 降级（`demote_backlinks_on_delete`）只改治理列（target_id/resolution/cross_space/updated_at），**不触**前置 6 字段 → 不受影响（K1 治理 12+11 测试全过）。
- 门禁 A/B/C、步 6、步 8 **全部保留**；治理列窗口②变化仍由步 8 治理基线兜底（边界测试实证）。

## 5. 验证结果（修复前后对照 + 双方言 + 回归）

### 5.1 新增专项测试（每项断言：拒绝过期计划 + 整体回滚 + 零部分写入 + 版本同构 + 原始数据保留）

| 测试 | SQLite | 真实 PG |
|---|---|---|
| source_id 漂移拒绝 | 修复前 FAIL→修复后 PASS | PASS |
| target_title 漂移拒绝 | 修复前 FAIL→修复后 PASS | PASS |
| alias 漂移拒绝 | 修复前 FAIL→修复后 PASS | PASS |
| 组合漂移拒绝 | 修复前 FAIL→修复后 PASS | PASS |
| 无漂移控制组（重建+key-title 一致性） | PASS | PASS |
| 并发删除行拒绝（边界） | PASS | PASS |
| phantom 新增碰撞拒绝（边界） | PASS | PASS |
| 治理列漂移由步 8 拒绝（边界） | PASS | PASS |
| PG 表锁覆盖 3 正确性字段并发写（真实双连接） | — | PASS |

【已验证事实】SQLite 新增 8（`test_links_p2_coverage.py`）；真实 PG 新增 9（`test_links_p2_coverage_pg.py`，含锁排除）。原始输出：`before-fix-sqlite.txt` / `diag-before-fix.txt` / `after-fix-sqlite-focused.txt` / `after-fix-pg-coverage.txt` / `after-fix-pg-rest.txt`。

### 5.2 全量回归（修复后，真实运行）

| 套件 | 结果 | 证据 |
|---|---|---|
| 全量 SQLite | **914 passed, 159 skipped** | sqlite-full.txt |
| 全量真实 PG（16.8，在线 Alembic upgrade head） | **1073 passed, 0 skipped** | pg-full.txt |
| K1 治理（SQLite 12 / PG 11） | 全过 | after-fix-sqlite-focused.txt / after-fix-pg-rest.txt |
| K2 并发（SQLite 7 / PG 7） | 全过 | 同上 |
| T22–T40 门禁（test_links_pg.py 91，含 T39 顺序守护） | 全过 | after-fix-pg-rest.txt |
| Core 独立性守护（含 test_core_has_no_web_framework_dependency） | **14 passed** | core-independence-guard.txt |
| A1-02 冻结（canonical/codec/frontmatter） | **291 passed** | a1-02-frozen.txt |
| Ruff | **All checks passed!** | ruff.txt |
| 前端测试 / 类型 / 构建 | **72 passed (10 files)** / tsc 无错误 / built | frontend-test.txt / frontend-typecheck.txt / frontend-build.txt |

**基线对照**：SQLite 906→914（+8）；skipped 150→159（+9 PG 门控）；PG 1056→1073（+8 SQLite 侧 +9 PG 侧）。A1-02 291、Core 14、前端 72 与基线一致，零回归。

### 5.3 Git diff / 工作树 / 锁定文件

【已验证事实】改动仅 `backend/app/services/links.py`、`backend/app/db/locking.py`（修改）+ `backend/tests/test_links_p2_coverage.py`、`test_links_p2_coverage_pg.py`（新增）+ 本审计文档。**零改动**：`uv.lock`、`frontend/package-lock.json`、`frontend/package.json`、`pyproject.toml`、`knowledge-core/**`（含 ports.py）、`backend/alembic/**`、`MILESTONES.md`、`governance.py`、`session.py`、`test_links_pg.py`（git diff 核验为空）。无敏感文件入库。

## 6. 【尚待验证】

- **真实跨连接 SQLite 漂移竞态压力测试**：本审计沿用 K2 既有口径，以**同事务确定性故障注入**（monkeypatch 门禁 C 后注入）复现窗口②漂移，非多线程/多进程随机交错压力测试。SQLite 写阶段锁排除与读阶段不锁语义已以真实双连接固化（K2 既有测试）；PG 锁排除为真实双连接。跨连接 SQLite 漂移的时序竞态未做压力遍历（确定性注入已覆盖正确性判定路径）。
- **BEGIN IMMEDIATE 活性改进**：仍延期（需全局事务控制管线改动），未实装、未验证其消除 BUSY 的效果。

## 7. 【已知局限】

- **SQLite 读阶段不锁保护**（K2 既有实测结论不变）：窗口②「重读 → 写」正确性现由**6 字段 P2 乐观前置**保证（本审计补齐字段覆盖）；写阶段 RESERVED 锁 + busy_timeout 补充。**BEGIN IMMEDIATE 延期**，不宣称读阶段已锁保护、不宣称已消除 SQLITE_BUSY；争用下重建以零写入回滚须重试（**活性问题，非正确性缺口**）。
- **缺陷可达性**：经应用 `update_link` 的 title/alias 变化必同步改键列（修复前 P2 已能拒规范化不同的漂移）；本缺陷经**原始/不一致并发写**（违反 key==normalize(title,alias) 不变量）可达。修复属**纵深防御加固**，使 P2 不依赖外部写者一致性假设，与门禁 C 字段口径对齐。
- **治理列处理边界**：治理列（target_id/resolution/cross_space/created_at）不在 P2 前置内（重建不拥有它们）；其窗口②变化由**步 8 治理基线**拒绝（零写入），非 P2。本修复未改变该边界（边界测试实证）。
- **测试夹具修正（诚实记录）**：PG 锁排除测试初版在循环中复用连接，因「事务中止时会话级 `SET lock_timeout` 随之回滚」（PG 语义）致第二次尝试无限等待而挂起；已修正为**每轮尝试前重设 lock_timeout**，并清理挂起连接（`pg_terminate_backend`，0 残留）。此为测试 harness 修正，**非生产代码缺陷**；修正后 9 项 PG 测试 2.18s 全过。

## 8. 回归验收清单（审计 §5 逐项）

- [x] K1 治理路径测试（SQLite 12 / PG 11 全过）
- [x] K2 并发测试（SQLite 7 / PG 7 全过）
- [x] T22–T40 原有门禁（test_links_pg.py 91 全过，T39 顺序守护不变）
- [x] SQLite 全量（914 passed / 159 skipped）
- [x] 真实 PostgreSQL 全量（1073 passed / 0 skipped）
- [x] A1-02 冻结（291 passed）
- [x] Ruff（All checks passed!）
- [x] Core 独立性守护（14 passed）
- [x] 前端测试 / 类型检查 / 构建（72 / tsc 无错误 / built）
- [x] Git diff / 工作树 / 锁定文件（仅 2 源文件 + 2 测试 + 审计文档；锁定文件/Core/端口/迁移/MILESTONES 零改动）

## 9. 交付物与提交

- 本报告：`docs/acceptance/V2-P2-coverage-audit/V2-P2-coverage-audit-report.md`
- 完整 diff：`evidence/fix.diff`
- 测试原始输出：`evidence/`（before-fix-sqlite / diag-before-fix / after-fix-sqlite-focused / after-fix-pg-coverage / after-fix-pg-rest / sqlite-full / pg-full / core-independence-guard / a1-02-frozen / ruff / frontend-test / frontend-typecheck / frontend-build）
- 新增测试：`backend/tests/test_links_p2_coverage.py`（SQLite 8）、`backend/tests/test_links_p2_coverage_pg.py`（真实 PG 9）
- 修复：`backend/app/services/links.py`（步 7 六字段前置）、`backend/app/db/locking.py`（docstring）
- **提交**：本批次提交于分支 `fix/m0-admission-and-m5-regressions`（哈希见交付汇报 / git log）；**未推送**。

**停止点**：专项审计完成（缺陷已真实复现、最小修复已实施并双方言验证、全量回归零回归）。停止，等待 ChatGPT 阶段级独立复审与用户批准。不进入 A1-04，不 push，不改 MILESTONES.md。