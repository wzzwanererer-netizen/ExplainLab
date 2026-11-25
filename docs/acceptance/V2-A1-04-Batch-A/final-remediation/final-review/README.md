# V2 · A1-04 Batch A · 最终独立审计材料

- 仓库：`D:\ExplainLab`
- 基线 HEAD：`784b1248065424e07273b272d6016cc121bc606c`
- 分支：`fix/m0-admission-and-m5-regressions`
- 材料目录：`docs/acceptance/V2-A1-04-Batch-A/final-remediation/final-review/`
- 材料性质：**只读审计准备**。本轮未修改业务代码、测试、设计文档、数据库、迁移、依赖、lockfile 或 `MILESTONES.md`；未执行任何 Git 写命令；未自行修复缺陷；未宣布通过。
- 既有证据：`../`（`final-remediation/`）的 41 个文件（40 个受既有 `SHA-256SUMS` 覆盖）原样保留，未删除、未覆盖、未重新生成。

## 目录

```
final-review/
├─ README.md                      # 本文件
├─ SHA-256SUMS                    # 本目录全部交付文件校验
├─ 01-git-state/
│  ├─ git-state.txt               # HEAD/分支/porcelain=v2/diff stat/stash
│  ├─ tracked-files.txt           # 8 个 tracked 修改 + Hash
│  ├─ untracked-files.txt         # 捕获时 176 条（含本目录 3 个）+ Batch A 子集 Hash
│  ├─ file-metadata.txt           # mtime/size/Hash，含冻结核对
│  └─ scope-classification.md     # 本轮 vs 早期 Batch A 分类
├─ 02-code-review/
│  ├─ source-identity-review.md   # P1-01 / 分类 / 恢复 / 零写入
│  ├─ identity-guard-review.md    # P1-02 全事务覆盖与旁路
│  ├─ rotate-review.md            # P1-03 状态 3/4 与共存
│  ├─ file-write-review.md        # P2-01…06 与验证类型
│  └─ frozen-contract-review.md   # 冻结契约逐项
├─ 03-diff/
│  ├─ diff-summary.md
│  └─ per-file/                   # 8 个文件 diff（6 既有 + 2 新文件）
├─ 04-test-evidence/
│  ├─ test-summary.md
│  └─ verification-gaps.md
└─ 05-risk-register/
   └─ known-risks.md
```

## 直接回答审计要求的 8 个问题

### 1. 本轮到底改了哪些文件？

**本轮（审计材料准备）没有改任何业务文件。** 仅新增本 `final-review/` 目录下的文档与 diff 副本。

工作树中的代码改动全部属于**上一轮最终整改**（2026-11-22 11:01–11:23），共 8 个文件：

- 生产 5：`source_identity.py`、`source_instance_id.py`、`markdown.py`、`import_review_hook.py`、`governance.py`
- 测试 3：`test_markdown_batch_a_identity.py`、`test_markdown_batch_a_import_conflict.py`（新）、`test_batch_a_fault_injection.py`（新）

另有 8 个 tracked 修改与 173 个历史 untracked 文件（Batch A 实现/测试与历史审计文档）属于更早工作，本轮未触碰。17:42 捕获清单为 176 条，其中 3 条是本目录当时已生成的文档；材料完成后本目录 24 个文件，仓库 untracked 合计 197。完整清单见 `01-git-state/tracked-files.txt`、`untracked-files.txt`。

### 2. 哪些是“本轮”的，哪些是更早 Batch A 的？

- **更早 Batch A**：mtime ≤ 11-22 02:00；tracked 的 `schemas.py`/`config.py`/`db/session.py`/`dependencies.py`/`main.py`/`conftest.py`/`test_health.py`，以及 `import_export.py`、`process_lock.py`、`file_write.py`、`import_coordinator.py`、`journal_canonical.py`、`markdown_item_repository.py`、`repositories_v2.py` 等。
- **上一轮最终整改**：上列 5 个生产 + 3 个测试，mtime 11:01–11:23，对应 P1-01/P1-02/P1-03/P2-01…06。
- **本次材料轮**：仅 `final-review/`。

划分依据：`01-git-state/file-metadata.txt` 的 mtime/size/Hash，以及 `evidence/scope-mtime.txt`（10:00 后修改文件清单，`knowledge-core`/`alembic` 为空）。

### 3. P1/P2 的真实证据是什么？

| 项 | 结果 | 证据 |
| --- | --- | --- |
| P1 专项（身份 + 导入冲突） | **52 passed** | `../evidence/pytest-p1-item-tests.txt` |
| P2 专项（write_all 13 + 故障注入 23） | **36 passed** | `../evidence/pytest-p2-fault-tests.txt` |
| Batch A 聚焦 | **166 passed** | `../evidence/pytest-batch-a-focus.txt` |
| 冻结契约套件 | **417 passed** | `../evidence/pytest-frozen-a1-a2-a3-v1.txt` |
| 完整套件 | **1124 passed, 178 skipped** | `../evidence/pytest-full.txt` |
| Ruff | All checks passed | `../evidence/ruff-check.txt` |
| 前端 | 72 passed；typecheck/build 退出 0 | `../evidence/frontend-*.txt` |

逐项映射与真实/注入/理论区分见 `02-code-review/` 与 `04-test-evidence/`。178 skipped 全部为 PG 门控。

### 4. `identity_guard` 是否覆盖“分类—写入—提交”全事务，是否有旁路？

- 实现：`source_identity.py:594–604`，RLock 内先 `_recover_locked()` 再 `yield`。
- 直接导入/批量导入共用 `markdown._import_one`：`with coordinator.keyed(...), identity.identity_guard():`（`markdown.py:648`），锁内执行 S1 重读（651）、`_apply_import`（726）、`session.commit()`（734）；异常 rollback（736–738）。
- 审核批准：`governance.py:430–433` 同持 coordinator + guard；锁内重读、Core approve、`ImportReviewHook.apply_approved`、第一次 commit 全部在 guard 内（434–476）。
- 拒绝：只调 `apply_rejected` 空操作，不写身份，故不持 guard（`governance.py:516`）。
- 旁路：`_apply_import` 与 `apply_approved` 全仓库各仅一个调用点，均在 guard 内；未发现第二条导入身份写入路径。
- 锁顺序固定 coordinator → Journal；MATERIALIZE/ROTATE/导出只取 Journal，无反向路径。

**限制**：guard 是线程锁，跨进程依赖单实例 `ProcessLock`；多 worker/多实例未验证（R-P1-01）。

详见 `02-code-review/identity-guard-review.md`。

### 5. 冻结契约有没有被改？

**未改。** 证据：

- A1-02 三 Hash / Canonical JSON v1：`canonical.py`、`codec.py`、`markdown/__init__.py` 对 HEAD 无 diff；相关 canonical/hash 测试包含在 417 项冻结套件中并全部通过。
- A1-03 链接：核心 `links.py`/`link_service.py`、后端 `links.py`/`routes/links.py` 对 HEAD 无 diff；链接测试全部通过。
- D22–D24：设计文档 mtime 11-21/11-18，早于整改窗口；未编辑。
- 状态 1/2a/2b/3/4 与 Journal schema_version 1 未改；本轮仅改调用顺序与锁。
- DB schema/Alembic、Core ReviewService、V1 API：无 schema/迁移/核心变更。
- 依赖/lockfile、`MILESTONES.md`：Git clean，Hash 已记录。

逐项见 `02-code-review/frozen-contract-review.md`。

### 6. PG / POSIX 还缺什么验证？

- **PostgreSQL：完全未验证。** 无实例/docker/podman/psql；`EXPLAINLAB_PG_TEST_URL` 未设置；178 项 skipped。迁移 up/down、tsvector/触发器/级联、CJK 回退、向量/混合检索均未执行。
- **POSIX：部分验证。** WSL 探针 9 PASS（0600、并发 ensure、O_EXCL、目录 fsync、replace、EINTR、进程锁争用/释放）；完整 Journal/导入事务 **UNVERIFIED**（WSL 缺 pip/SQLAlchemy）。
- 另外未验证：真实断电/介质损坏、Windows sharing violation、Uvicorn reload/多 worker、高并发压力、浏览器 E2E。

详见 `04-test-evidence/verification-gaps.md`。

### 7. 有没有新的 P0/P1？

- **新 P0：无。**
- **新 P1：无。** 残留 4 项 P1 均为既有环境/部署验证缺口：
  1. 跨进程互斥依赖单实例 ProcessLock（未实测多 worker）；
  2. PostgreSQL 未验证；
  3. POSIX 完整事务未验证；
  4. 真实断电/I/O 错误未验证。
- P2 6 项、P3 6 项均为本地可靠性/功能边界/改进项，不阻断当前范围。

详见 `05-risk-register/known-risks.md`。

### 8. 是否满足冻结/提交条件？

**不能由本材料宣布“满足”或“通过”。** 可核查事实：

- 代码与测试已就位，工作树 Hash 与上一轮整改交付一致；
- 当前环境（Windows + SQLite + 单进程）下 1124 passed / 178 skipped、Batch A 166、P1 52、P2 36、冻结 417、Ruff、前端均通过；
- 冻结契约未见改动；
- 但 PG、POSIX 完整事务、真实断电、多进程仍未验证（P1 残留）；
- 工作树有 8 个 tracked 修改与 197 个 untracked（含本目录 24 个），**未提交、未暂存、未推送**；`MILESTONES.md` 未改。

因此：

- 若冻结条件定义为“SQLite 单进程 Batch A 功能 + 冻结契约不回归”，材料层面可支撑，但**是否放行由 ChatGPT/用户裁决**；
- 若条件包含 PostgreSQL/Linux/断电/多进程，则**不满足**，需先补验证；
- 本次未执行 `git add/commit/push`，也未进入 Batch B。

## 证据可信度声明

- 测试数字来自整改期间真实运行输出，未重跑、未改写；本轮只新增文档。
- 6 个 per-file diff 复制自既有已验收 diff，复制后 `git apply --check --reverse` 6/6 通过；`markdown.py`/`import_review_hook.py`/`governance.py` 的 before 为逆向重建，**不是 Git 原始 blob**，已在 `03-diff/diff-summary.md` 标明。
- 新文件 diff 为 `git diff --no-index /dev/null` 生成。
- 未把未验证项写成已通过；未使用假数据冒充真实数据库/模型结果。

## 校验

```bash
cd docs/acceptance/V2-A1-04-Batch-A/final-remediation/final-review
sha256sum -c SHA-256SUMS
```

`SHA-256SUMS` 覆盖本目录除自身外的全部交付文件。生成后已实际执行校验：**23/23 OK**（2026-11-22）。既有 `../SHA-256SUMS` 亦复核为 **40/40 OK**，未被本轮改动。

## 停止声明

材料已整理完毕。按要求停止：不宣布 PASS、不进入 Batch B、不修改 `MILESTONES.md`、不 commit/push。如独立审计发现缺陷，请指出文件与行为；本轮不自行修复。