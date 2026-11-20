# V2 K1+K2 整改批验收报告

> **阶段**：A1-03 独立审计放行后的 **K1+K2 整改批**（治理审核批准路径链接维护 + 链接重建并发窗口控制）。
> **执行模式**：阶段级自主开发（计划确认 → 开发 → 真实运行 → 验收 + 提交）。
> **分支**：`fix/m0-admission-and-m5-regressions`；**基线 HEAD**：`7e0582c`（A1-03 验收）。
> **日期**：2026-11-20。
> **边界**：不改 Core / 端口签名 / 迁移 / 依赖 / A1-01/A1-02 / 前端源码 / MILESTONES.md；不进入 A1-04；**不推送远程**。
> **诚实声明**：下文严格区分【已验证】/【有条件】/【未通过】/【已知局限】。所有测试数字来自真实运行的原始输出（`evidence/`），未执行者不描述为通过。

---

## 1. 阶段功能完成清单

| 编号 | 功能 | 状态 | 证据 |
|---|---|---|---|
| K1-1 | `approve_review` 四动作链接维护（DELETE 预降级 / UPDATE·RESTORE 应用后同步 / MERGE 不降级不同步） | 【已验证】 | `test_governance_links.py` / `_pg.py` approve 系列 |
| K1-2 | `submit_review` 草稿直改链接维护（DELETE 预降级 / UPDATE·RESTORE 同步） | 【已验证】 | `test_submit_draft_*` |
| K1-3 | `restore_version` 草稿直改回滚同步出链 | 【已验证】 | `test_restore_draft_syncs_links_removes_stale` |
| K1-4 | DELETE 写侧降级（原始列 resolution=missing + target NULL，非仅读取侧 D12 映射） | 【已验证】 | `test_*_delete_demotes_backlinks_write_side`（独立连接读原始列） |
| K1-5 | MERGE 归档源**不**降级入链/反链（归档≠删除） | 【已验证】 | `test_approve_merge_keeps_bindings_no_demote` |
| K1-6 | 治理同步 409 `link_version_mismatch` 稳定码 + 整事务零写入（审核单仍 pending） | 【已验证】 | `test_*_409_zero_write` |
| K1-7 | DELETE 治理列豁免：版本窗口内删除不被 409 阻断 | 【已验证】 | `test_approve_delete_not_blocked_in_version_window` |
| K1-8 | 治理端点集合不变（仅挂接，无新增链接/重建写入口） | 【已验证】 | `test_governance_router_endpoint_set_unchanged` |
| K2-1 | PG 重建写锁（`LOCK TABLE … SHARE ROW EXCLUSIVE` + `FOR UPDATE`，持锁至提交） | 【已验证】 | `test_pg_rebuild_lock_blocks_concurrent_update` / `_insert_phantom` / `_serializes_second_rebuild` |
| K2-2 | P2 乐观前置（双方言）：步 7 `WHERE old_key+old_version` + rowcount 校验，失配整体回滚零写入 | 【已验证】 | `test_p2_key_drift_*` / `test_p2_version_drift_*`（SQLite+PG） |
| K2-3 | P2 控制组：无漂移 rowcount 恒 1，重建正常（不误报） | 【已验证】 | `test_p2_no_drift_rebuilds_successfully` |
| K2-4 | phantom INSERT 碰撞 → 写被拒（DB UNIQUE 于步 7，步 8 后备）回滚零写入 | 【已验证】 | `test_phantom_insert_collision_post_write_rolls_back` |
| K2-5 | SQLite `busy_timeout=5000`（liveness） | 【已验证】 | `test_sqlite_busy_timeout_pragma_is_5000` |
| K2-6 | SQLite 锁语义实测固化（写阶段阻并发提交；读阶段不阻 → P2 兜底） | 【已验证】 | `test_sqlite_write_phase_blocks_concurrent_commit` / `test_sqlite_read_phase_not_lock_protected` |
| K2-7 | PG T39 顺序守护更新：取锁先于门禁 A（更强守护） | 【已验证】 | `test_links_pg.py::test_t39_order_guard_success` / `_no_update_after_gate_failure` |

**未完成/延期**：见 §8。

## 2. 架构与调用链说明

依赖方向不变：`frontend → backend → knowledge-core`。本批**全部改动落在 backend 适配层与路由层**，Core 零改动（K1 选项 A）。

### 2.1 K1 治理链接维护调用链

```
HTTP POST /api/reviews/{id}/approve
  └ governance.approve_review
      ├ _pending_review(...)                         # 取 pending（含 item_id/action）
      ├ _demote_backlinks_before_delete(...)         # DELETE：approve 前预降级（删除 flush 前）
      │    └ services.links.demote_backlinks_on_delete   # 治理列-only：target NULL + missing + cross_space False
      ├ ReviewService.approve(...)                   # Core：update_review → _apply_action（DELETE CASCADE 审核单自身）
      ├ _sync_links_after_content_change(...)        # UPDATE/RESTORE：approve 后、commit 前同步出链
      │    └ routes.links.sync_links_or_conflict     # 版本异写 → HTTPException 409 link_version_mismatch
      │         └ services.links.build_link_sync → Core BindingFirstLinkSync.sync（绑定优先）
      └ session.commit()                             # 409 抛出时未 commit → close() 回滚整事务（零写入）
```

`submit_review`（草稿直改）与 `restore_version`（草稿直改）同口径：非重要变更直接应用前预降级 DELETE / 应用后（`review is None`）同步 UPDATE·RESTORE，均在 `session.commit()` 前。MERGE 恒进审核（`ReviewPolicy.is_important` 恒 True），归档源不降级、双方 content 未改不同步。

**关键序约束**：DELETE 降级必须在删除 flush **之前**（先按 target_id 捕获入链再置 missing+NULL）；approve 内部先 `update_review` 再 `_apply_action`，故预降级置于 `service.approve` 调用之前。

### 2.2 K2 重建并发控制调用链

```
services.links.apply_link_key_plan(plan, session)
  └ with session.begin():                            # 步 1 独占事务
      ├ db.locking.acquire_rebuild_write_lock(session)   # 步 1b（K2）
      │    ├ PG:  LOCK TABLE knowledge_link IN SHARE ROW EXCLUSIVE MODE
      │    │      + SELECT id … FOR UPDATE            # 持锁至提交，阻并发写（含 phantom）
      │    └ SQLite: 无操作（读阶段不锁保护，见 §9 修正）
      ├ 步 2 门禁 A（全表版本同构）
      ├ 步 3 六列重读 + 步 3b 治理/条目基线
      ├ 步 4 门禁 B / 步 5 门禁 C（Core check_plan_freshness）
      ├ 步 6 新键唯一性
      ├ 步 7（K2 P2）UPDATE … WHERE id AND old_key AND old_version
      │    └ rowcount != 1 → LinkRebuildPostWriteError → 整体回滚零写入
      └ 步 8 写后复核（版本同构 / 键对唯一 / 治理基线 / 条目基线）
  └ 步 9 提交
```

方言差异封装在 `app/db/locking.py`（适配层），业务服务/Core 无方言 SQL（AGENTS.md §5/§11）。

## 3. 修改文件和 Git 提交清单

**修改（tracked）**：
- `backend/app/api/routes/governance.py` — K1 三入口挂接 + 两 helper + imports。
- `backend/app/db/session.py` — K2 SQLite `busy_timeout=5000` + 注释。
- `backend/app/services/links.py` — K2 步 1b 加锁 + 步 7 P2 乐观前置 + docstring/注释实测修正。
- `backend/tests/test_links_pg.py` — `_QueryCounter` 增 `lock` 分类；T39 顺序守护断言取锁先于门禁 A。

**新增（untracked → 本批提交）**：
- `backend/app/db/locking.py` — K2 方言写锁适配。
- `backend/tests/test_governance_links.py` — K1 SQLite（12 测试）。
- `backend/tests/test_governance_links_pg.py` — K1 真实 PG（11 测试）。
- `backend/tests/test_links_concurrency.py` — K2 SQLite（7 测试）。
- `backend/tests/test_links_concurrency_pg.py` — K2 真实 PG（7 测试）。
- `docs/acceptance/V2-K1K2-remediation/` — 本报告 + `evidence/` 原始输出。
- `docs/audit/V2-A1-03-audit-package/` — Request C 设计文档（A1-03-final-review / K1 / K2 方案 / known-issues 等，此前未提交）+ K1/K2 方案 §9 实施状态追加。

**零改动（git diff 为空，已核验）**：`knowledge-core/**`、`knowledge_core/ports.py`、`backend/alembic/**`、`pyproject.toml`、`uv.lock`、`frontend/package.json`、`frontend/package-lock.json`、`frontend/src/**`、`MILESTONES.md`。

**提交**：本批次提交于分支 `fix/m0-admission-and-m5-regressions`（含代码 + 测试 + 证据 + 设计文档 + 本报告）；**未推送**。提交哈希见交付汇报与 `git log`。

## 4. 完整测试结果与原始输出

| 套件 | 命令 | 结果 | 原始输出 |
|---|---|---|---|
| 全量 SQLite | `uv run pytest -o addopts="--import-mode=importlib"` | **906 passed, 150 skipped** | `evidence/sqlite-full.txt` |
| 全量真实 PG | `EXPLAINLAB_PG_TEST_URL=… uv run pytest -o addopts="--import-mode=importlib"` | **1056 passed, 0 skipped** | `evidence/pg-full.txt` |
| 新增 K1+K2（SQLite） | `pytest test_governance_links.py test_links_concurrency.py` | **19 passed** | `evidence/new-tests-sqlite.txt` |
| 新增 K1+K2（PG） | `pytest test_governance_links_pg.py test_links_concurrency_pg.py` | **18 passed** | `evidence/new-tests-pg.txt` |
| Core 独立性守护 | `pytest knowledge-core/tests/test_interfaces.py` | **14 passed** | `evidence/core-independence-guard.txt` |
| A1-02 frozen | `pytest test_markdown_canonical/codec/frontmatter.py` | **291 passed** | `evidence/a1-02-frozen.txt` |
| Lint | `uv run ruff check` | **All checks passed!** | `evidence/ruff.txt` |
| 前端测试 | `npm run test` | **72 passed (10 files)** | `evidence/frontend-test.txt` |
| 前端类型 | `npm run typecheck` | **tsc -b 无错误** | `evidence/frontend-typecheck.txt` |
| 前端构建 | `npm run build` | **built（index 256.45 kB / gzip 78.26 kB）** | `evidence/frontend-build.txt` |

**基线对照**：SQLite 887→906（+19 新 SQLite 侧）；skipped 132→150（+18 新 PG 门控模块未设环境时跳过）；PG 1019→1056（+19 SQLite 侧 +18 PG 侧）。A1-02 frozen 291 全过（本批零改 A1-02）。前端 72/构建尺寸与基线一致。

## 5. SQLite 和真实 PostgreSQL 验证

- **SQLite**：默认临时文件库，`create_engine_from_url` + `PRAGMA foreign_keys=ON` + `busy_timeout=5000`。全量 906 过。
- **真实 PostgreSQL**：`EXPLAINLAB_PG_TEST_URL="postgresql+psycopg://postgres@127.0.0.1:5432/explainlab_test"`，PG 16.8 真实实例（`pg_ctl status` running）。PG 测试模块经**真实在线 Alembic `command.upgrade(head)`** 建表（非离线 SQL），真实 TestClient / 真实双连接 SQL。全量 1056 过 / 0 跳过。
- **PG 锁排除实证**：双连接，A 持 `acquire_rebuild_write_lock`，B `SET lock_timeout='500ms'` 后 UPDATE / INSERT / 再次取锁均被阻（`canceling statement due to lock timeout`），A 释放后 B 可写。非离线推断。
- **写侧降级实证**：K1 DELETE 测试以**独立连接**读同一库原始列 `resolution='missing'` + `target_item_id IS NULL`，区别于读取侧 D12 映射（HTTP GET 无法区分二者）。
- 未虚报 PG 成功；未以 SQLite 结果冒充 PG；未以离线 SQL 冒充真实库验证。

## 6. 迁移、依赖、接口变化

- **迁移**：**无变更**（`backend/alembic/**` git diff 空，无新增 version）。PG 测试夹具真实在线 `upgrade head` 成功，既有迁移双方言可用。
- **依赖**：**无变更**（`pyproject.toml`/`uv.lock`/`package.json`/`package-lock.json` git diff 空）。未新增任何第三方依赖（`locking.py` 仅用 SQLAlchemy `text`/`select`）。
- **接口/端口**：**Core 端口签名零变更**（`knowledge_core/ports.py` 未改）；HTTP API 端点集合不变（治理路由守护测试核实）；`apply_link_key_plan` 函数签名不变（内部步 1b/步 7 增强）。
- **新增 backend 内部接口**：`app/db/locking.py::acquire_rebuild_write_lock(session)`（适配层，非 Core 端口）；`governance.py` 两私有 helper。

## 7. 故障注入和边界测试

| 测试 | 注入/边界 | 断言 | 方言 |
|---|---|---|---|
| `test_p2_key_drift_after_reread_rolls_back` | 门禁 C 后同事务改 r1 键（窗口②漂移） | rowcount=0 → `LinkRebuildPostWriteError` → 全表逐列零写入 | SQLite+PG |
| `test_p2_version_drift_after_reread_rolls_back` | 门禁 C 后改 r2 版本=99 | old_version 前置失配 → 回滚零写入 | SQLite+PG |
| `test_p2_no_drift_rebuilds_successfully` | 无注入（控制组） | rebuilt，updated=3，版本同构 {2} | SQLite+PG |
| `test_phantom_insert_collision_post_write_rolls_back` | 门禁 C 后插入碰撞新键行 | DB UNIQUE 于步 7 拒写（步 8 后备）→ 回滚零写入 | SQLite+PG |
| `test_approve_update_409_zero_write` | 注入异版本行 → 批准 active 编辑 | 409 稳定码；审核单仍 pending；正文/链接零写入 | SQLite+PG |
| `test_submit_draft_update_409_zero_write` / `test_restore_draft_409_zero_write` | 异版本行 → 草稿直改/回滚 | 409；正文零写入 | SQLite+PG |
| `test_approve_delete_not_blocked_in_version_window` | 异版本行挂引用方 → 批准删除 | DELETE 治理列豁免，200；入链写侧降级 | SQLite+PG |
| `test_pg_rebuild_lock_blocks_concurrent_update` | 双连接，B lock_timeout=500ms | B UPDATE 被锁阻；A 释放后可写 | PG |
| `test_pg_rebuild_lock_blocks_concurrent_insert_phantom` | 双连接 phantom INSERT | SHARE ROW EXCLUSIVE 阻 INSERT | PG |
| `test_pg_rebuild_lock_serializes_second_rebuild` | 双重建取锁 | 第二取锁被阻；释放后可取 | PG |
| `test_sqlite_write_phase_blocks_concurrent_commit` | A 写阶段持锁，B busy_timeout=0 | B 提交 `database is locked`；释放后可写 | SQLite |
| `test_sqlite_read_phase_not_lock_protected` | A 读阶段，B busy_timeout=0 | B 可写提交（固化真实局限，驱动 P2 兜底） | SQLite |
| `test_*_delete_demotes_backlinks_write_side` | 删除目标 | 原始列 resolution=missing + target NULL + 字面留存 | SQLite+PG |
| `test_approve_merge_keeps_bindings_no_demote` | MERGE 归档源 | 源出链/反链写侧仍 resolved+绑定（不降级） | SQLite+PG |

故障注入经 monkeypatch 门禁 C 在重读快照后、写之前于**同一事务**注入变更，确定性复现窗口②漂移（非线程竞态，不 flaky）；PG 锁排除经**真实双连接** + `lock_timeout` 确定性触发。

## 8. 已知问题和未完成事项

- **【已知局限 / 已验证】SQLite 读阶段窗口②不锁保护**：实测 `isolation_level=None`/`journal_mode=delete` 下，重建重读（SELECT）至写之前不阻并发提交。窗口②安全由 **P2 乐观前置**保证（已故障注入实证），写阶段 RESERVED 锁 + busy_timeout 补充。详见 §9。
- **【延期】SQLite BEGIN IMMEDIATE**：需全局事务控制管线改动（`isolation_level=None` + begin 事件钩子）， blast radius 大，本轮不做；不宣称已消除 SQLITE_BUSY（争用下重建以零写入回滚须重试）。
- **【延期】K1 选项 B（Core 内挂接）**：需改 A1-01 冻结端口签名，未获审批，本轮采用选项 A（路由层）。Core `ReviewService._apply_action` 仍无链接 hook（治理链接维护集中在路由层）。
- **【已知局限】phantom 碰撞由 DB UNIQUE 于步 7 拒写**：步 8 写后键对复核为同口径后备（DB 约束已先拒）；二者均整体回滚零写入。
- **【未完成】A1-04 及后续里程碑**：本批仅 K1+K2 整改，不进入 A1-04。
- **【待办】独立审计**：本批完成后停止，等待 ChatGPT 阶段级独立审计 + 用户批准。
- **【说明】A1-02 frozen 计数**：本批真实运行 291 过（canonical/codec/frontmatter 三文件）；此前记忆中的 293 为约数，以真实输出 291 为准。本批零改 A1-02，无回归。

## 9. 设计偏离记录

1. **K1 选项 A 而非 B**：K1 方案推荐选项 A（路由层挂接，Core 零改动）；选项 B 需 A1-01 冻结端口变更审批，未获批 → 选 A。符合红线（不改冻结契约）。**无功能偏离**：四动作 × 三入口链接维护全覆盖。
2. **K2 SQLite 锁语义实测修正（重要）**：K2 方案 §3 推断「SQLite 自重读起持 SHARED 锁直至提交、写侧安全已由锁保证」。**实测推翻**：读阶段不持阻塞写者的锁（`test_sqlite_read_phase_not_lock_protected` 固化）。修正后：SQLite 窗口②「重读 → 写」由 **P2 乐观前置**兜底（非锁），写阶段 RESERVED 锁 + busy_timeout 补充。**安全性不降级**：P2 故障注入实证漂移即回滚零写入。已同步修正 `locking.py`/`services/links.py`/`session.py` 注释与 K2 方案 §9 追加。BEGIN IMMEDIATE 仍延期。
3. **K2 P2 定位调整**：原方案视 P2 为「纵深防御」；实测后在 SQLite 上 P2 是窗口②**主防御**（读阶段无锁），PG 上 P2 为表锁之外的纵深防御。已据此更新注释。
4. **PG T39 顺序守护更新（非弱化）**：`_QueryCounter` 增 `lock` 分类，T39 断言取锁（LOCK TABLE + FOR UPDATE）**先于门禁 A**——较原守护**更强**（新增锁序验证），非删除/弱化断言。SQLite T39 因 acquire 无操作保持不变。
5. **phantom 测试期望修正**：原拟断言步 8 `LinkRebuildPostWriteError`；实测 DB UNIQUE 约束于步 7 即抛 `IntegrityError`（更早拒写）。测试改为接受 `(LinkRebuildPostWriteError, IntegrityError)` 并断言零写入——如实反映真实拒写点。

## 10. 从干净环境复现指南

```bash
# 0. 基线：Python 3.11.9 / uv 0.13.6 / Node 22.23.2 / SQLite 3.45.1 / PG 16.8
#    干净副本（不含预存 .venv / node_modules）从零安装：
uv sync --locked                       # 后端 + 核心（含 dev/test 组）
cd frontend && npm ci && cd ..         # 前端（package-lock 与 package.json 一致）

# 1. Lint
uv run ruff check                      # 期望 All checks passed!

# 2. 全量 SQLite（无需 PG）
uv run pytest -o addopts="--import-mode=importlib"
# 期望 906 passed, 150 skipped（PG 门控模块跳过）

# 3. 真实 PostgreSQL（须先起真实实例并设环境变量）
#    起库示例（本机路径）：
#    "D:/ExplainLab-pg/pgsql/bin/pg_ctl.exe" -D "D:/ExplainLab-pg/data" -l "D:/ExplainLab-pg/data/logfile" start
export EXPLAINLAB_PG_TEST_URL="postgresql+psycopg://postgres@127.0.0.1:5432/explainlab_test"
uv run pytest -o addopts="--import-mode=importlib"
# 期望 1056 passed, 0 skipped（PG 模块经真实在线 Alembic upgrade head 建表）

# 4. 新增测试聚焦
uv run pytest backend/tests/test_governance_links.py backend/tests/test_links_concurrency.py -o addopts="--import-mode=importlib"   # 19 passed
uv run pytest backend/tests/test_governance_links_pg.py backend/tests/test_links_concurrency_pg.py -o addopts="--import-mode=importlib"  # 18 passed（须 PG env）

# 5. Core 独立性守护 / A1-02 frozen
uv run pytest knowledge-core/tests/test_interfaces.py -o addopts="--import-mode=importlib"   # 14 passed
uv run pytest knowledge-core/tests/test_markdown_canonical.py knowledge-core/tests/test_markdown_codec.py knowledge-core/tests/test_markdown_frontmatter.py -o addopts="--import-mode=importlib"  # 291 passed

# 6. 前端
cd frontend && npm run test && npm run typecheck && npm run build
# 期望 72 passed (10 files) / tsc 无错误 / built（index 256.45 kB, gzip 78.26 kB）
```

**注意**：`pytest` 必须保留 `--import-mode=importlib`（切勿 `-o addopts=""`，会引发同名模块收集冲突）；`ruff` 仅 `check`（禁 `format`）；Windows 终端设 `PYTHONIOENCODING=utf-8` 避免 GBK 编码错误。PG 未设环境变量时相关模块整模块跳过（默认 SQLite 套件不受影响），**不得以 SQLite 结果冒充 PG**。

---

**停止点**：本批 K1+K2 全部任务完成并真实验证。停止，等待 ChatGPT 阶段级独立审计与用户批准。不自动进入 A1-04，不推送远程仓库。