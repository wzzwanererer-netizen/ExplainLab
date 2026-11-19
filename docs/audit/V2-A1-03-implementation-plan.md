# V2 Batch A1-03 稳定链接与反向链接 — 实施计划（修订版 R3.1，仅计划，未写业务代码）

> 日期：2026-11-18 ｜ 基线 HEAD：`6d91718` ｜ 分支：`fix/m0-admission-and-m5-regressions`
> 依据：`docs/plans/V2-batch-A-design.md` §2.4（双向链接）、§2.6.1/§2.6.2（三 Hash 与变化分类）、§2.9（规范化重建）、§8.1（测试场景）、§10（方言差异）、A1-T4
> 前置：A1-01（数据模型与迁移 0006）、A1-02（MarkdownCodec 与三 Hash）均已验收通过，**两者改动尚未提交 Git**
> **版次 R2（历史，已被 R3 取代）—— 第一轮独立审查意见已全部落实。D1–D12 已获用户裁决（§11）；审查指出的两个逻辑问题（重建碰撞、提示覆盖）已按裁决方案重写（§8.3 / §6.5）；场景 F 的三 Hash 口径已修正（§7.2）。逐条修订记录见 §15 REV-01–REV-15。**
> **版次 R3（上一轮，审查结论：E1/E2/E3/E5 已通过；E4 职责拆分已批准但须补门禁 C）—— 第二轮独立审查（最终审查）意见已落实：① 版本同构守卫由「按源条目局部检查」升级为「覆盖全表的全局预检」（§8.4 重写，权威执行点在 backend 持久化边界）；② 导入绑定的空间语义明确（§6.6 新增：跨空间恢复必须 `cross_space=True`，不得伪装成普通 resolved）；③ 人工绑定的交付边界明确（§6.7 新增：D8 只读 GET，Core 规则已定义但无 HTTP 写入口，不得写成已交付）。R2 主体设计保持不变；配套调整与新增测试见 §15 REV-16–REV-22。**
> **版次：R3.1（本轮，当前待最终批准稿）—— 只解决一个问题：`plan()` 与 `apply_link_key_plan()` 之间的「计划过期」。① 新增 **门禁 C：逐行计划新鲜度校验**（10 类不一致一律 `refused_stale_plan` + 零写入 + 禁止部分更新 + 必须重读全表重新生成计划，§8.3.6）；② 明确 **A/B/C 的十步执行顺序**（§8.3.7），并声明「计划生成阶段的检查不构成 apply 阶段的安全保证」；③ 计划快照字段与比较规则明确，**经论证不新增计划摘要/不新增任何 Hash 契约**（§8.3.8）；④ **事务缓存生命周期修订：撤回 R3 的「仓库实例级缓存」，改为无缓存——每次受守卫写入重新执行单列 `SELECT DISTINCT`**（§8.4.3，Session 生命周期 ≠ 事务生命周期，无法安全证明则取保守方案）；⑤ 新增 **T22–T40**（全部标注【待验证】），T20③ 的期望值按最终缓存策略修订。E1/E2/E3/E5 不重新设计，E5 批准状态不变。**
> **本轮状态：Design Only，只修订计划文档。未编写任何业务代码、未新增测试文件、未运行实现、未运行测试套件、未安装依赖、未修改迁移、未修改 Core/Backend/Frontend、未修改 A1-01/A1-02 既有实现、未修改 V2 主设计文档与依赖选择文档、未修改 lockfile、未提交/推送/reset/checkout/stash。**
> 完成后停止，等待**最终批准**。**不得开始 A1-03a。**

---

## 0. 本轮边界（先说清楚不做什么）

**做**：摸清现状、冻结工作区基线、给出可执行的 A1-03 实施方案、论证 `normalized_link_key` 与三 Hash 的关系、设计场景 A–E 连续测试、列出风险与决策。

**R2 轮额外做**：落实第一轮独立审查的 **D1–D12 全部裁决**；重写审查指出的**两个逻辑问题**（重建碰撞 → 整体拒绝；导入提示覆盖 → 先聚合再判定）；修正**场景 F 的三 Hash 测试口径**；补齐 **archived/自链接口径**、**Core 零文件 IO 职责**、**完整前后兼容性说明**；新增 **§15 审查修订记录**；重新核验 Git/基线/指纹/依赖漂移。

**R3 轮额外做**：落实第二轮（最终）独立审查的**两个阻塞项 + 一个交付边界项**——① **全局版本同构守卫**（覆盖整张 `knowledge_link` 表，空表允许初始化，拒绝返回 409 `link_version_mismatch`，检查与写入同一事务，权威执行点在 backend 装配/持久化层以避免 Core 每次同步全量加载，不改 A1-01 端口契约、不新增迁移）；② **导入绑定的空间语义**（同空间 `resolved`/`cross_space=False`；跨空间按当前空间关系重算 `cross_space=True`，不得伪装成普通 resolved；archived 与 D7 显式绑定一致；无效 UUID/目标不存在/空间不匹配三类语义分离）；③ **人工绑定交付边界**（保留 D8 三个只读 GET，明确 Core 规则已定义但**无 HTTP 写入口**，不得把未交付的人工绑定写成已交付功能）。配套新增 **§1.6 / §2.5⚠ / §6.6 / §6.7 / §8.3.5 / §8.4 重写（8.4.1–8.4.8）/ T13–T21 / H13–H20 / R20–R24 / REV-16–REV-22 / §15.4–15.6**，并重新核验 Git/基线/**21 指纹**/依赖漂移（真实输出见 §1.6 与 §15.5）。另如实报告两项自主处置：**E4 重建执行边界拆分**（§8.3.5，全局守卫下 R2 的「Core 逐行写入重建」会死锁）与 **E5 候选枚举空间过滤**（§2.5⚠，实测 `list(space_id=None)` 返回全库）。

**R3.1 轮额外做（本轮唯一目标）**：解决 `LinkKeyRebuild.plan()` 与 `apply_link_key_plan()` 之间的**计划过期**问题——① 新增**门禁 C 逐行计划新鲜度校验**（快照字段、10 类不一致、`refused_stale_plan`、零写入、禁止部分更新、必须重新生成计划）；② 明确 **A/B/C 十步执行顺序**与「plan 阶段检查 ≠ apply 阶段保证」；③ 论证**是否需要计划摘要**（结论：不新增，理由见 §8.3.8）；④ **修订事务缓存生命周期**（撤回实例级缓存，改无缓存保守方案）；⑤ 新增 **T22–T40**【待验证】并修订 T20③ 期望值；⑥ 同步 E4 台账（新增 E6）、§7、§12、§13、§15。新增 **§1.7 / §8.3.6 / §8.3.7 / §8.3.8 / §15.7–15.9 / REV-23–REV-26 / R25–R26**。**R3 已批准设计全部保留；E1/E2/E3 不重新设计；E5 不再讨论、批准状态不变。**

**不做**：不写 `markdown/links.py` 等业务代码；不新增测试文件；**不运行实现、不运行测试套件**；不装任何依赖；不改 0006 或新增迁移；不动 V1 服务/API/前端；**不改 Core/Backend/Frontend 任何实现**；**不改 A1-01/A1-02 既有实现**；**不改设计文档 `docs/plans/V2-*.md` 与依赖选择文档**；**不改 lockfile**；不 commit / push / reset / checkout -- / stash。**R2、R3 与 R3.1 轮唯一改动文件都是本计划文档**（§15.1 / §15.4 / §15.7）。**不得开始 A1-03a。**

**A1-03 实施阶段也不做**（属后续子任务）：导入导出服务与 ImportOrigin 幂等（A1-04）、附件生命周期与 GC（A1-04）、审核提案 hash 防覆盖与撤回（A1-05）、前端链接 UI（A2/A1-06）、Obsidian 全图/力导向图/AI Pipeline/MCP/Browser Extension（本轮明确排除）。

---

## 1. Git 与工作区基线保护（已开始执行，全部只读）

### 1.1 实测结果

```
$ git log --oneline -1
6d91718 fix: 迁移 0004 回填历史 knowledge_item 到全文索引（SQLite FTS5 + PG tsvector）

$ git branch --show-current
fix/m0-admission-and-m5-regressions

$ git stash list
（空）
```

M0 初始提交 `2d2b634` 未被触碰；HEAD 与 A1-01/A1-02 开工时一致，**期间无新提交**。

### 1.2 全部未提交改动（A1-01 + A1-02，共 8 改 13 增 = 21 个交付文件）

**已跟踪文件修改（8）**：

```
backend/app/models.py                                   | 216 +++++-
backend/tests/test_fts_backfill.py                      |  35 +-
backend/tests/test_migrations.py                        | 165 +++-
backend/tests/test_retrieval_pg.py                      |  38 +-
knowledge-core/src/knowledge_core/domain/__init__.py    |  20 +
knowledge-core/src/knowledge_core/domain/entities.py    | 159 +++-
knowledge-core/src/knowledge_core/ports.py              | 254 +++++
knowledge-core/tests/test_interfaces.py                 |  37 +
8 files changed, 910 insertions(+), 14 deletions(-)
```

**未跟踪新增（13，属 A1-01/A1-02 交付）**：
`backend/alembic/versions/0006_v2_markdown_kb.py`、`backend/tests/test_v2_models.py`、`backend/tests/test_v2_models_pg.py`、`knowledge-core/tests/test_v2_entities.py`、`knowledge-core/src/knowledge_core/markdown/{__init__,canonical,frontmatter,codec}.py`、`knowledge-core/tests/test_markdown_{canonical,frontmatter,codec}.py`、`docs/acceptance/V2-A1-01-*.md`、`docs/acceptance/V2-A1-02-*.md`。

**未跟踪但与 A1 交付无关（不得提交、不得修改）**：`docs/audit/M0-M5-independent-review.md`、`docs/plans/V2-batch-A-design.md`、`docs/plans/V2-dependency-selection.md`、`docs/plans/V2-plan.md`、`release/`。

**零漂移核对**：`git diff --name-only -- uv.lock frontend/package-lock.json pyproject.toml backend/pyproject.toml knowledge-core/pyproject.toml frontend/package.json` → **空**。

### 1.3 基线指纹与 diff 基线（已落盘，可复算）

**已保存的基线工件**（本轮唯一新增文件，均为文档/基线，非业务代码）：

| 工件 | 内容 |
|---|---|
| `docs/audit/V2-A1-03-baseline/a1-01-a1-02-tracked.patch` | `git diff` 全文（1173 行，8 个已跟踪文件的 910 增 / 14 删） |
| `docs/audit/V2-A1-03-baseline/manifest.sha256` | 21 个 A1-01/A1-02 交付文件的**完整 64 位 SHA-256** |
| `docs/audit/V2-A1-03-baseline/git-status.txt` | 开工时完整 `git status --short` |
| `docs/audit/V2-A1-03-baseline/head.txt` | 开工时 HEAD（`6d91718`） |

**复算校验已真实执行**：`sha256sum -c docs/audit/V2-A1-03-baseline/manifest.sha256` → **21/21 OK**。
实施阶段每步开工前后可重跑该命令；**A1-01/A1-02 交付文件的指纹只允许在「本计划明确列出的修改」处变化**，其余必须逐字节不变。

下表为便于阅读的前 16 位摘要（完整值见 `manifest.sha256`）：

| 文件 | SHA-256（前 16 位） |
|---|---|
| `backend/app/models.py` | `4b5abb23c3cfb83b` |
| `backend/tests/test_fts_backfill.py` | `669900c4985280e3` |
| `backend/tests/test_migrations.py` | `08c9148b2ab491e7` |
| `backend/tests/test_retrieval_pg.py` | `22bc0fda44c0e39d` |
| `knowledge-core/src/knowledge_core/domain/__init__.py` | `9ad2ba865ea1fcc5` |
| `knowledge-core/src/knowledge_core/domain/entities.py` | `ca7b7990c7644b1b` |
| `knowledge-core/src/knowledge_core/ports.py` | `ad7beed6f75fb525` |
| `knowledge-core/tests/test_interfaces.py` | `730687089bc78e51` |
| `backend/alembic/versions/0006_v2_markdown_kb.py` | `75c674e2df8ce468` |
| `backend/tests/test_v2_models.py` | `e26e83f47a09c6ef` |
| `backend/tests/test_v2_models_pg.py` | `9065cd3b4d89eb4f` |
| `knowledge-core/tests/test_v2_entities.py` | `06113e79664e0bd0` |
| `knowledge-core/src/knowledge_core/markdown/__init__.py` | `a9e885d4d02e5c76` |
| `knowledge-core/src/knowledge_core/markdown/canonical.py` | `b93f3a9a54f32b47` |
| `knowledge-core/src/knowledge_core/markdown/frontmatter.py` | `7e14f0107a68cf24` |
| `knowledge-core/src/knowledge_core/markdown/codec.py` | `c960a15e8b875e7a` |
| `knowledge-core/tests/test_markdown_canonical.py` | `99106e7eecbacc11` |
| `knowledge-core/tests/test_markdown_frontmatter.py` | `f80cdeaf8941d6b3` |
| `knowledge-core/tests/test_markdown_codec.py` | `feee43efa4b830c6` |
| `docs/acceptance/V2-A1-01-data-model-and-migration.md` | `545d45ff07d60108` |
| `docs/acceptance/V2-A1-02-markdown-codec-and-frontmatter.md` | `44c99999abe5220b` |

> **A1-02 指纹冻结清单（6 个文件，A1-03 全程必须逐字节不变）**：
> `markdown/canonical.py`、`markdown/frontmatter.py`、`markdown/codec.py`（三个核心实现文件）
> + `tests/test_markdown_canonical.py`、`tests/test_markdown_frontmatter.py`、`tests/test_markdown_codec.py`（其三个测试文件）。
> 每步实施前后重跑 `sha256sum -c`，这 6 项必须恒为 OK；另加守护测试断言 A1-02 的 293 个用例全通过。
>
> **`markdown/__init__.py` 不在上述冻结清单内，但只允许「追加」**：按 AGENTS.md §4「抽象接口（ABC）声明在包 `__init__.py`」的仓库强制惯例，6 个链接服务 ABC 必须落在此文件。既有 `MarkdownCodec` / `MarkdownDocument` / 三 Hash 函数 / `resolve_frontmatter_conflict` / `KNOWN_FRONTMATTER_KEYS` 等 A1-02 代码**逐字不动**，仅在文件尾部追加 ABC 与 `__all__` 条目。追加后 A1-02 全部用例必须仍通过（这是「只追加」的可核验证明）。
>
> `ports.py` 与 `test_interfaces.py` 允许变化，但仅限 §4.2 列明的增量（**D3 已裁决：仅 docstring 澄清** / 守护追加）。

### 1.4 工作区保护承诺

不执行 `git reset --hard` / `checkout --` / `clean -f` / `stash` / `push --force` / `commit --amend`；不覆盖未提交改动；实施阶段每步先 `git status` + `git diff --stat` 自检，发现与本计划不一致立即停止并报告。

### 1.5 R2 修订轮开工前复核（本轮真实执行，全部只读）

| 复核项 | 命令 | 实测结果 |
|---|---|---|
| Git HEAD | `git rev-parse HEAD` | `6d91718344ca1bccd3f3971f4fed7fd9576b670d`（= 基线 `6d91718`，**无新提交**） |
| 分支 | `git rev-parse --abbrev-ref HEAD` | `fix/m0-admission-and-m5-regressions`（未切换） |
| stash | `git stash list` | 空 |
| 全部未提交改动 | `git status --porcelain=v1` | 8 个 ` M` + 15 个 `??` 条目，与 `baseline/git-status.txt` 一致（`??` 中 `docs/audit/`、`knowledge-core/src/knowledge_core/markdown/` 为目录聚合条目） |
| 原始 baseline patch | `git diff > /tmp/current.diff` + `cmp` 对 `baseline/a1-01-a1-02-tracked.patch` | 两者均 **1173 行**，`cmp` 无差异 → **逐字节相同** |
| 21 个文件 SHA-256 | `sha256sum -c docs/audit/V2-A1-03-baseline/manifest.sha256` | **21/21 OK**（含 A1-02 三个核心实现文件与其三个测试文件） |
| 依赖与锁定文件漂移 | `git status --porcelain uv.lock frontend/package-lock.json pyproject.toml backend/pyproject.toml knowledge-core/pyproject.toml frontend/package.json` | **输出为空 → 零漂移** |

**结论**：A1-01/A1-02 的既有工作**未被本轮触碰**。R2 轮唯一改动文件是本计划文档 `docs/audit/V2-A1-03-implementation-plan.md`（属未跟踪的 `docs/audit/`，不在 21 个指纹清单内，故指纹全 OK 与本文档被修订并不矛盾）。

> 复核纪律说明：`sha256sum -c` 必须在**仓库根目录**执行（manifest 内路径为仓库根相对路径）；在子目录执行会因路径解析失败而报 `FAILED open or read`，那是**执行目录错误**而非文件被改，须重跑而非误判。

### 1.6 R3 修订轮复核（本轮真实执行，全部只读；开工前 + 收工后各一遍，结果一致）

| 复核项 | 命令 | **R3 实测结果** |
|---|---|---|
| Git HEAD | `git rev-parse HEAD` | `6d91718344ca1bccd3f3971f4fed7fd9576b670d`（= 基线 `6d91718`，**无新提交**） |
| 分支 | `git rev-parse --abbrev-ref HEAD` | `fix/m0-admission-and-m5-regressions`（未切换） |
| stash | `git stash list` | **空**（未 stash） |
| **M0 初始提交未被改写** | `git rev-parse 2d2b634` + `git merge-base --is-ancestor 2d2b634 HEAD` | `2d2b63443a3ba1290aafe03be5f5e3281ffa280f`；`M0_IS_ANCESTOR_OK` |
| 全部未提交改动 | `git status --porcelain > /tmp/r3-status.txt` + `cmp` 对 `baseline/git-status.txt` | **`STATUS_CMP_IDENTICAL`（逐字节相同）** → 8 改 13 增 = **21 个交付文件**集合未变 |
| 原始 baseline patch | `git diff > /tmp/r3-current.diff` + `cmp` 对 `baseline/a1-01-a1-02-tracked.patch` | **`PATCH_CMP_IDENTICAL`**，两者均 **1173 行** → **逐字节相同**（附 4 条 LF→CRLF 换行警告，不影响比对） |
| **21 个文件 SHA-256** | `sha256sum -c docs/audit/V2-A1-03-baseline/manifest.sha256`（**仓库根执行**） | **21/21 OK，0 FAILED**（manifest 共 21 行，`": OK"` 计数 = 21；逐行输出见 §15.5） |
| 依赖与锁定文件漂移 | `git status --porcelain` + `git diff --stat` 对 `uv.lock`/`frontend/package-lock.json`/根与两个子包 `pyproject.toml`/`frontend/package.json` | **两者输出均为空 → 零漂移**；**新增依赖 0** |
| 本轮改动文件数 | `git status --porcelain docs/audit/` | `?? docs/audit/`（仍未跟踪）→ **R3 唯一改动文件是本计划文档**，未入库 |
| 业务代码 / 测试 / 迁移 / 设计文档 | 由上述 status 与 patch 逐字节比对共同证明 | **零改动**；**未新增测试文件**；**未运行任何测试套件**；**未连接 PostgreSQL** |
| 本文档规模 | `wc -l < docs/audit/V2-A1-03-implementation-plan.md` | R2 = 1080 行 → **R3 = 1555 行**（净增 475 行，收工后实测值） |

**结论**：A1-01/A1-02 的既有工作**未被 R3 触碰**；M0 初始提交与已推送历史**未被改写**；工作区**未被重置/覆盖/stash**。R3 与 R2 一样，**唯一改动文件是本计划文档**（属未跟踪的 `docs/audit/`，不在 21 个指纹清单内，故「指纹全 OK」与「本文档被修订」并不矛盾）。

**诚实性边界**：上表全部为**只读核验**的真实结果。**本轮未运行 pytest / ruff / npm / alembic / 任何实现代码**，因此 §7.8 的用例规模（~520）与 §13.1 的全部验收项**均为估算或未验证**，**不得写成 PASS**；真实 PostgreSQL 连接须在 A1-03 实施阶段重新验证，不得沿用 A1-02 的旧结论。

### 1.7 R3.1 修订轮复核（本轮真实执行，全部只读；**开工前必须先核对，与基线不一致即停止**）

**开工前核对结果（真实执行，全部一致 → 允许继续修订文档）**：

| 复核项 | 命令 | **R3.1 开工前实测结果** |
|---|---|---|
| Git HEAD | `git rev-parse HEAD` | `6d91718344ca1bccd3f3971f4fed7fd9576b670d`（= 基线 `6d91718`，**无新提交**） |
| 分支 | `git rev-parse --abbrev-ref HEAD` | `fix/m0-admission-and-m5-regressions`（未切换） |
| stash | `git stash list` | **空** |
| M0 初始提交 | `git rev-parse 2d2b634` + `git merge-base --is-ancestor 2d2b634 HEAD` | `2d2b63443a3ba1290aafe03be5f5e3281ffa280f`；`M0_IS_ANCESTOR_OK`（未被改写） |
| **21 个交付文件 SHA-256** | `sha256sum -c docs/audit/V2-A1-03-baseline/manifest.sha256`（**仓库根执行**） | **21/21 OK，0 FAILED**（manifest 共 21 行，`": OK"` 计数 = 21） |
| 原始 baseline patch | `git diff > /tmp/r31-pre.diff` + `cmp` 对 `baseline/a1-01-a1-02-tracked.patch` | **`PATCH_IDENTICAL`（逐字节相同）**，两者均 **1173 行** |
| 工作区状态 | `git status --porcelain > /tmp/r31-pre-status.txt` + `cmp` 对 `baseline/git-status.txt` | **`STATUS_IDENTICAL`（逐字节相同）** → 8 改 13 增 = 21 个交付文件集合未变 |
| 锁定文件 / 配置漂移 | `git status --porcelain uv.lock frontend/package-lock.json pyproject.toml backend/pyproject.toml knowledge-core/pyproject.toml frontend/package.json` | **输出为空 → 零漂移** |
| 本文档规模（修订前） | `wc -l < docs/audit/V2-A1-03-implementation-plan.md` | **1555 行**（= R3 冻结稿） |

**结论**：工作区与基线**完全一致**，未发现任何不一致，**未覆盖任何内容**，允许按本轮范围只修订本计划文档。收工后复核结果见 **§15.8**。

**诚实性边界**：上表为**只读核验**的真实结果。**R3.1 未运行 pytest / ruff / npm / alembic / 任何实现代码、未连接 PostgreSQL**；§7.8 规模与 §13.1 全部验收项、以及新增 **T22–T40 一律为【待验证】**，**不得写成 PASS**。

---

## 2. 现有架构分析（实测代码，非推测）

### 2.1 依赖方向与分层（AGENTS.md §3 强制）

```
frontend ──HTTP /api──▶ backend ──Python import──▶ knowledge-core
```

Core 只依赖 stdlib + Pydantic + httpx；独立性守护在干净子进程导入全部 Core 模块，断言无 fastapi/starlette/flask/django。A1-02 另加「markdown 包非 stdlib 顶层模块白名单仅 Pydantic 栈」守护。

### 2.2 V1 知识写入与治理数据流（A1-03 必须挂接但不破坏的点）

`backend/app/api/routes/knowledge.py`（169 行，实测）：

| 端点 | 现有流程 | A1-03 挂接点 |
|---|---|---|
| `POST /knowledge` | `repo.save(item)` → `commit` → `sync_index` → `commit` | save 后、commit 前插入 **链接同步** |
| `PATCH /knowledge/{id}` | `build_review_service(session).submit(UPDATE_ITEM, payload)` → `commit`；active 返回 202 审核单（**不应用**），draft 直接应用 → `sync_index` | **仅当 submit 返回 None（已应用）** 时同步链接；202 分支不同步 |
| `DELETE /knowledge/{id}` | 审核门禁 → `sync_index(remove_ids=...)` | 删除应用后：出链 CASCADE 消失、入链 `target_id` SET NULL → 需把受影响入链降级为 missing |
| `POST /conversations/{id}/extract` | 提取 → 逐条 save → `commit` → `sync_index` | 每条新条目同步链接（正文可能含 wikilink） |

`knowledge_core/review/__init__.py`（167 行，实测）：`ReviewService.submit` 对非重要变更直接 `_apply_action`；`approve` 先写决议再 `_apply_action`（同事务，失败整体回滚）；`_apply_update` 会 `versions.create_version(item, "编辑前快照")` 再改 title/content/status/space_id 并 `items.update`。

**关键结论**：`ReviewService` 是 V1 已审计通过的 Core 类。**A1-03 不修改它**（不改构造签名、不改 `_apply_update`）。链接同步由 **backend 装配层**在「变更已应用」之后、`session.commit()` 之前调用 Core 的 `LinkSyncService`，与既有 `sync_index` 完全并列。这样：① Core 业务逻辑仍在 Core；② backend 只做装配；③ V1 审核行为零改动；④ 同一事务内失败可整体回滚。

### 2.3 A1-01 已落地的链接基础设施（实测，A1-03 直接复用，不重建）

`domain/entities.py`：

- `LinkResolution`：`resolved / missing / ambiguous / cross_space / conflict`（5 态）。
- `KnowledgeLink`：`id, source_id, target_id|None, target_title(1..500), alias|None, normalized_link_key(1..1024), link_normalization_version(≥1, 默认 1), resolution(默认 missing), cross_space(bool), created_at, updated_at`。
- **实体级校验器已存在**：`resolved` 必须有 `target_id`；有 `target_id` 不得标 `missing`。
- 常量 `LINK_NORMALIZATION_VERSION = 1`、`CANONICALIZATION_VERSION = 1`。

`ports.py::LinkRepository`（10 个方法，已定义）：`save_link / get_link / list_links(source_id) / list_backlinks(target_id) / find_by_key(source_id, key) / list_by_key(key) / list_all_links() / update_link / delete_link / delete_links_of_item(source_id)`。

`backend/app/models.py::KnowledgeLinkORM`（实测）：`UNIQUE(source_item_id, normalized_link_key)` 名 `uq_link_source_key`；`source_item_id` FK **CASCADE**；`target_item_id` FK **SET NULL**；索引 `ix_knowledge_link_target_item_id`、`ix_knowledge_link_normalized_link_key`；`normalized_link_key String(1024) NOT NULL`。

迁移 `0006` 已建表建索引（up/down 均已真实 SQLite + PG 验证）。`backend/app/db/session.py` 已对 SQLite 连接设 `PRAGMA foreign_keys=ON`。

> **⚠ 已发现一处端口文档与设计冲突（非签名冲突）→ D3 已裁决批准处置**：`delete_links_of_item` 的 docstring 实测原文为「删除某条知识的全部出链（**连续保存时先清后建**），返回删除条数。」这与 §2.4「绑定优先同步（按键匹配、保留 target_id、不重解析）」**直接矛盾**——先清后建会丢绑定、churn 链接 ID、破坏场景 C/E。
> **处置（D3 裁决：仅修改 docstring，不改变签名和行为）**：A1-03 **不使用**该方法做常规保存；它只用于「条目删除后的显式清理」或「用户主动全量重置」。拟把括号内文字改为「**仅供条目删除后的显式清理或用户主动全量重置；常规保存必须走绑定优先同步，不得先清后建**」，其余文字、方法签名、返回类型、参数一律不动。这是 A1-03 唯一允许触碰 `ports.py` 的改动。
> **守护**：`test_interfaces.py` 追加断言 `LinkRepository.delete_links_of_item` 的签名（参数名/顺序/注解/返回注解）与 A1-01 一致，防止「只改 docstring」被悄悄扩大为行为变更。

### 2.4 A1-02 已落地的编解码与 Hash（实测，A1-03 只消费不改）

- `MarkdownCodec.parse/dump`、`MarkdownDocument`（`links: list[dict]` 交换形态）、`FrontmatterState` 三态。
- `canonical.py::sort_links` 排序键实测为：
  `(_text(link.get("normalized_link_key")) or _text(link.get("title")), target_id, title, alias, resolution)`
  —— **用 `.get()`，键缺失回退 title，不丢弃任何未知子键**。
- 三 Hash：`document_content_hash`（只允许 title/content）、`document_payload_hash`（完整交换载荷）、`review_payload_hash`（只允许 title/content/status/space_id）。
- §2.2.3 交换示例中 `links` 子字段为 **`target_id / title / alias / resolution`**，**不含** `normalized_link_key`、**不含** `link_normalization_version`。这是第 5 节 Hash 论证的关键事实。

### 2.5 候选检索能力（实测）

`KnowledgeRepository.list(space_id=..., include_unassigned=...)` 返回完整 `KnowledgeItem` 列表；`space_id=None` 语义即「个人总知识库」，personal 空间视图需 `include_unassigned=True` 聚合未显式归属条目（V1 路由已如此处理）。

**A1-03 用它做解析候选枚举，规范化在 Core Python 内完成**——不新增端口方法、不改 A1-01 契约、不写任何方言 SQL。性能边界见 §9 风险 R3。

> **⚠ R3 实测发现（必须在实施中守住，否则会自动跨空间绑定）**：`SQLAlchemyKnowledgeRepository.list` 的实现是 **`if space_id is not None:` 才加 where 过滤**（`backend/app/services/knowledge.py` 实测）。因此 **`list(space_id=None, include_unassigned=True)` 返回的是全库所有条目（含各 project 空间的条目），不是「仅个人空间条目」**。V1 路由只在 `space_id` query 参数非 None 时才走 personal 聚合分支，故 V1 行为正确；但 A1-03 若按 R2 §6.4 伪代码直接对 `space_id=None` 的源条目调用 `repo.list(space_id=item.space_id, include_unassigned=True)`，**候选集合会混入其它空间条目 → 违反「不自动跨项目」**。
> **处置（R3 明确，属实现细节，不改端口/不改 V1）**：Core 侧在拿到 `repo.list(...)` 结果后**必须再做一次显式空间等值过滤** `candidate.space_id == item.space_id`（**`None == None` 视为同空间；`None` 与 `"p1"` 视为不同空间**），然后才做 archived 过滤与标题键索引。**不依赖仓库 `list` 在 `space_id=None` 时的返回范围**。该过滤与 archived 过滤一样在 **Core Python** 完成，零方言 SQL。
> **测试**：新增断言「源条目 `space_id=None`、库中另有 project 空间同名条目 → 自动解析**不得**绑定该 project 条目（应为 `missing` 或仅个人空间候选）」，Core + SQLite + PG 三层各验（见 §7.2 场景 J 扩展与 §6.6 空间判定表）。

### 2.6 ⚠ 已发现一处真实缺陷风险：FK SET NULL 与实体校验器互相矛盾（必须在 A1-03 处置）

实测两个事实放在一起会出问题：

1. `KnowledgeLinkORM.target_item_id` 的 FK 是 **`ondelete="SET NULL"`** —— 删除目标条目时，数据库**只把 `target_item_id` 置 NULL**，**不会**改 `resolution` 列（仍是 `'resolved'`）。
2. `KnowledgeLink` 实体校验器 `_resolution_matches_binding` 规定：**`resolution=resolved` 必须有 `target_id`**，否则 `ValueError`。

**后果**：目标被删除后，链接行变成 `target_id=NULL` + `resolution='resolved'` 的**非法组合**；仓库把该行映射成实体时会**抛异常**，导致「查 A 的出链/反链」直接失败——即**删除一条知识会让引用它的文档链接读取崩掉**。这不是假想，是 A1-01 已落地代码的必然结果，A1-03 必须处置。

**处置方案（D12 已裁决批准，按此实施）**：

- **写入侧修复（主）**：删除路径在**同一事务**内显式把受影响入链降级——`list_backlinks(deleted_id)` → 逐行 `resolution=missing`、`cross_space=False`、`target_id=None` → `update_link`。保留 `target_title` 原始字面作快照。
- **读取侧防御映射（辅）**：仓库 `_to_entity` 遇 `target_item_id IS NULL` 时，**一律把 resolution 映射为 `missing`**（不论列里存的是什么），避免历史数据/外部级联/迁移留下不可读行。这是**读取降级**，不弱化实体校验器。
- **不做**：❌ 不放宽 A1-01 实体校验器（不得弱化已有断言）；❌ 不加 DB 触发器改 resolution（方言特定 SQL，违反 §5 红线）；❌ 不改 FK 为 CASCADE（会丢链接与字面快照，违反 §2.4「删除保留未解析」）。
- **测试**：场景 I 必须断言「删除目标后，读取源文档出链/反链**不抛异常**且 `resolution=missing`、字面留存」，并在 **SQLite 与 PG 两边**各跑一遍（两边 FK 语义都要真实验证）。

> 这条同时说明：**A1-03 不能只写 Core 服务就收工**，删除路径的 backend 修复是正确性必需项，已列入 §12 的 A1-03e 门禁。

---

## 3. 目标数据流与模块职责（解析 / 解析服务 / 持久化 三层分离）

用户要求「不将链接解析与链接持久化混为一层」。A1-03 严格四层：

```
① 纯文本层（无端口、无 IO、可单测）
   knowledge_core/markdown/links.py
   ├ normalize_link_text(s) -> str            NFKC → strip → 空白折叠 → casefold
   ├ normalized_title_key(title) -> str       norm(title) + "\x1f" + ""      （D2：不持久化）
   ├ normalized_link_key(title, alias) -> str norm(title) + "\x1f" + norm(alias or "")
   ├ WikilinkParser.parse(body) -> list[ParsedWikilink] + list[LinkWarning]
   │   排除：围栏代码块 / 行内代码 / 转义 \[[ / 畸形（未闭合/空/嵌套/超长/控制字符/跨行）
   │   排除：![[X]] 嵌入语法（D6，留给 A1-04 附件）
   ├ merge_same_key(literals) -> 合并同键书写（保留首现字面）+ 冲突判定
   └ group_hints_by_title_key(hints) -> dict[title_key, list[Hint]]
       ★ 先聚合再判定（问题 B 修订）：绝不 last-write-wins，保留同键全部提示

② 领域服务层（端口注入，纯 Python，无 SQL、无 Web、无文件系统写入）
   knowledge_core/markdown/link_service.py
   ├ check_global_version_homogeneity(versions, expected) -> None   ★ R3：纯函数规则单一来源
   │                             空集合→允许；{expected}→允许；其它→抛 LinkNormalizationVersionMismatch
   │                             backend 仓库与 Core 测试替身**共用同一函数**，规则不重复实现
   ├ RepositoryLinkResolver      当前空间优先 / 唯一→resolved / 多→ambiguous / 无→missing
   │                             不自动跨项目；用户主动跨空间→cross_space
   │                             ★ 候选先按 space_id 精确等值过滤（含 None==None，§2.5⚠）
   │                             自动候选排除 archived（D7）；不排除源条目自身（自链接允许）
   ├ BindingFirstLinkSync        按键匹配既有行：保留绑定 / 维持未解析 / 新键解析 / 删键删行
   │                             ★ 局部版本守卫（per-source，defense-in-depth，§8.4.3）
   │                             ★ 全局同构由 backend 持久化边界权威保证（§8.4），Core 不做全表扫描
   ├ LinkImportRestorer          正文为存在性权威（D4）；提示先聚合再判定（§6.5）：
   │                             单一有效/多提示同 target→恢复；多有效 target 矛盾→conflict；
   │                             无有效目标→回退标题解析；孤儿提示→不建行+warning
   │                             ★ R3：恢复时按**当前** source/target 空间关系重算
   │                               resolution/cross_space（§6.6），跨空间不得伪装成 resolved
   ├ BacklinkQuery               按稳定 ID 查反链（改名不断）
   ├ LinkReresolve               只重试 missing/ambiguous，守同一套规则
   └ LinkKeyRebuild              ★ R3：**只算计划，不写库、不写文件**（§8.3.5）
                                 plan(target_version) -> LinkRebuildPlan
                                 全量预算新键 → 写前检测全部碰撞组 → 有碰撞则 status=refused_collision
                                 （零写入）→ 无碰撞则产出覆盖全表的 updates 计划
                                 ★ R3.1：计划另携带 row_snapshots（**覆盖全表每一行，含 no-op 行**，
                                 link_id/source_id/old_key/old_version/target_title/alias）+
                                 observed_row_count + requires_replan（§8.3.6，供门禁 C 校验）
                                 target_id/resolution 一律不动；写入由 backend 批量执行
   抽象接口（ABC）按仓库惯例声明在 knowledge_core/markdown/__init__.py（只追加）

③ 持久化适配层（backend，唯一允许出现 ORM/方言/文件 IO 的地方）
   backend/app/services/links.py
   ├ SQLAlchemyLinkRepository    实现 LinkRepository 10 方法（双方言同一套 SQLAlchemy 表达式）
   │                             读取侧防御映射：target_id 为 NULL → resolution 映射 missing（D12）
   │                             ★ R3 全局版本预检：save_link / update_link（改键或改版本时）
   │                               在**同一数据库事务**内执行单列 `SELECT DISTINCT
   │                               link_normalization_version`（不加载实体），调用 Core 纯函数判定；
   │                               空表允许；不同构 → 抛 LinkNormalizationVersionMismatch（零写入）
   │                               ★ R3.1：**无缓存**，每次受守卫写入都重新预检（撤回 R3 实例级缓存；
   │                               Session ≠ 事务，§8.4.3（1）–（6））
   ├ apply_link_key_plan(plan, session) -> LinkRebuildReport   ★ R3：重建写入的唯一执行入口
   │                             ★ R3.1：**独占单事务，十步顺序不得颠倒**（§8.3.7）
   │                             门禁 A 全表单一版本 == plan.source_version（同事务重读）
   │                             重读当前全表 6 列 → 门禁 B 计划覆盖全表行 + 无 (source_id,new_key) 重复
   │                             ★ R3.1 门禁 C：Core 纯函数 check_plan_freshness() 逐行比对快照
   │                               （10 类不一致 → refused_stale_plan + **零写入**，§8.3.6）
   │                             单事务只写 normalized_link_key / link_normalization_version / updated_at
   │                             写后复核全表同构 + 唯一 + 非键列与重读值相等；失败 → 整体回滚
   ├ persist_rebuild_report(report, ops_dir)  ★ D10：报告落盘由 backend 负责（gitignore 目录）
   └ build_link_sync_service(session) / build_link_resolver(session)  装配

④ API 装配层（backend，只做 HTTP 形状与事务边界）
   backend/app/api/routes/links.py（新增 router，**仅 3 个只读 GET**，D8；静态字面先于动态声明）
   backend/app/api/routes/knowledge.py（仅在既有流程插入同步调用 + 删除路径入链降级，不改 V1 语义）
   ★ R3：LinkNormalizationVersionMismatch → HTTPException(409, detail="link_version_mismatch")
     （只回稳定码，不回异常文本/版本明细，AGENTS.md §9；与既有 409 用法同形状）
   ★ R3：**人工绑定无 HTTP 写入口**（D8）；显式绑定规则只在 Core 层定义与测试（§6.7）
```

**层间契约**：① 不知道数据库存在；② 只经 `ports.py` Protocol 取数/写数，绝不 import SQLAlchemy；③ 不含业务规则（规则在 ②）；④ 不含业务规则。

**与 V1 `relations` 的关系**：`KnowledgeRelation`（M2 语义关系：duplicate_of/supports/…，由 LLM/词法推断）与 `KnowledgeLink`（V2 用户书写 wikilink）**是两套独立数据**，A1-03 **不合并、不互写、不改 V1 关系推断**。知识地图（M4）继续读 relations；链接/反链是新增能力。

---

## 4. 具体文件修改清单

### 4.1 新增（Core 2 + backend 2 + 测试 4 = 8）

| 文件 | 内容 | 依赖 |
|---|---|---|
| `knowledge-core/src/knowledge_core/markdown/links.py` | 纯文本规范化 + 两个键 + WikilinkParser + 排除矩阵 + 同键合并 + **提示按标题键聚合** + 长度/控制字符守卫 + `ParsedWikilink`/`LinkWarning`/`LinkWarningCode` 值类型 | stdlib(`unicodedata`,`re`) + Pydantic |
| `knowledge-core/src/knowledge_core/markdown/link_service.py` | 6 个具体服务类（见 §3②）+ **`LinkRebuildPlan`/`LinkKeyUpdate`/`LinkRebuildReport`/`LinkCollisionGroup`/`LinkCollisionEntry`/`LinkSyncReport`/`LinkRestoreReport` 结构化模型** + `LinkNormalizationVersionMismatch` 异常 + **`check_global_version_homogeneity()` 纯函数（R3：全局守卫规则单一来源，backend 与测试替身共用）** + **★ R3.1 追加：`LinkRowState`（只读快照值类型，`frozen=True`）/ `PlanFreshnessResult` / `LinkStaleReason` 值类型 + `check_plan_freshness()` 纯函数（门禁 C 规则单一来源，§8.3.6）** + **`LinkRebuildPlan` 追加 `row_snapshots`/`observed_row_count`/`requires_replan` 字段（§8.3.6）**。**零文件系统写入（D10）；`LinkKeyRebuild` 零数据库写入（R3，§8.3.5）**。**R3.1 不新增文件、不新增端口方法、不新增计划摘要字段（§8.3.8）** | Core ports + entities + links.py |
| `backend/app/services/links.py` | `SQLAlchemyLinkRepository`（含**读取侧防御映射**：`target_id` 为 NULL → resolution 映射 missing，D12；**含 R3 全局版本预检**：同一数据库事务内、写入之前执行单列 `SELECT DISTINCT link_normalization_version` + Core 纯函数判定 + **★ R3.1 无缓存：每次受守卫写入重新执行**（撤回 R3「事务内一次缓存」，§8.4.3（1）–（6）））+ **`apply_link_key_plan()` 重建批量执行入口（R3；**R3.1：四重门禁 A/B/C + 新键唯一性再验证 + 写后复核 + 独占单事务十步顺序**，§8.3.7；含**事务内重读当前全表 6 列**并调用 Core `check_plan_freshness()`）** + 装配函数 + **删除路径入链同事务降级修复**（§2.6/R13）+ **`persist_rebuild_report()` 报告落盘（D10，backend 侧 IO）** | SQLAlchemy + Core |
| `backend/app/api/routes/links.py` | `GET /knowledge/{item_id}/links`、`GET /knowledge/{item_id}/backlinks`、`GET /knowledge/links/resolve-candidates`（**只读 3 个，D8；本轮不加任何写端点**） | FastAPI + 装配 |

> **路径参数名口径（R3 实测澄清，属实现细节，不改契约）**：设计文档 §2.6 API 表写作 `/knowledge/{id}/links`，但 **V1 实测路由的参数名是 `{item_id}`**（`backend/app/api/routes/knowledge.py`：`@router.get("/knowledge/{item_id}")` / `patch` / `delete`）。A1-03 新增 router **沿用 `{item_id}`** 与 V1 保持一致；**本文其余各处出现的 `/knowledge/{id}` 均为同一端点的简写，不是第二条路径**。§6.7 的路由守护断言以 **`{item_id}` 形式**为准。静态字面 `/knowledge/links/resolve-candidates` 仍须**先于** `/knowledge/{item_id}` 声明（R11）。
| `knowledge-core/tests/test_markdown_links.py` | 纯文本层矩阵（规范化/解析排除/同键合并/键长守卫/**提示聚合分组**） | — |
| `knowledge-core/tests/test_markdown_link_service.py` | 服务层矩阵 + **场景 A–M（Core + InMemory 仓库）** + **重建碰撞/回滚专项（§7.5）** + **提示聚合专项（§7.6）** + Hash 不变性 + **Core 无文件 IO 行为守护** + **★ R3.1：门禁 C 纯函数专项（T22–T29 / T35–T38 的 Core 层部分，§7.5.1）+ 计划不可变与确定性序列化守护（T38）+ InMemory 无缓存口径对齐（T34⑤）** | helpers.py |
| `backend/tests/test_links.py` | 真实 SQLite：仓库契约 + 场景 A–M + 唯一约束（含**故意写重复键证明确实抛 IntegrityError**）+ FK CASCADE/SET NULL + 同步挂接 + **重建整体回滚（故障注入）** + 报告落盘往返 + **★ R3.1：T22–T31 / T35–T37 / T39 的 DB 级断言（过期计划真实拒绝 + 零写入 + 十步顺序守护）+ T32/T33/T34/T40 事务生命周期与预检计数** | — |
| `backend/tests/test_links_pg.py` | 真实 PostgreSQL 同上（`EXPLAINLAB_PG_TEST_URL` 门控）；**★ R3.1：T31 关键过期计划用例 + T39/T40 事务边界在 PG 侧各自真实验证** | — |

### 4.2 修改（7，全部增量，不改 V1 语义）

| 文件 | 改动 | 风险控制 |
|---|---|---|
| `knowledge-core/src/knowledge_core/markdown/__init__.py` | **仅在文件尾部追加** 6 个链接服务 ABC + 导出新值类型/报告模型/异常（**★ R3.1 追加导出 `LinkRowState`/`PlanFreshnessResult`/`LinkStaleReason` 与 `check_plan_freshness()`**）+ `__all__` 追加 | A1-02 既有代码逐字不动（`MarkdownCodec`/`MarkdownDocument`/三 Hash/`resolve_frontmatter_conflict`/`KNOWN_FRONTMATTER_KEYS`）；追加后 A1-02 的 293 用例必须仍全通过；**R3.1 不新增 ABC、不改 `plan()` 方法名** |
| `knowledge-core/src/knowledge_core/ports.py` | **仅** `delete_links_of_item` 一行 docstring 文字澄清（D3 已批准，见 §2.3⚠） | **签名/参数/返回类型/行为零变化**；追加签名不变守护断言；**R3.1 门禁 C 不新增任何端口方法**（§8.3.6 分层） |
| `knowledge-core/tests/helpers.py` | **追加** `InMemoryLinkRepository`（**★ R3.1：无缓存，每次受守卫写入重新扫描内存字典并调用同一纯函数**，§8.4.3（3）） | 既有 8 个 Fake/InMemory 类不动 |
| `knowledge-core/tests/test_interfaces.py` | 守护子进程追加 `markdown.links`、`markdown.link_service`；`SERVICES` 追加 6 个新 ABC；**★ R3.1 追加守护：新鲜度规则单一来源 / 无缓存 / 计划不可变 / apply 事务所有权 / Hash 契约零改动（§7.7）** | 既有断言只增不减 |
| `backend/app/api/routes/knowledge.py` | create/extract/draft-update/delete 四处插入链接同步调用（与 `sync_index` 并列，commit 前） | active 202 分支**不插入**；V1 响应形状/状态码不变 |
| `backend/app/api/schemas.py` | 追加 `LinkOut`/`BacklinkOut`/`ResolveCandidateOut` | 既有 schema 不动 |
| `backend/app/main.py` | 注册新 router | 既有 router 顺序不动；静态字面路由先于 `{item_id}` |

> **`backend/app/models.py`、`0006` 迁移、`canonical.py`、`frontmatter.py`、`codec.py`、A1-02 三个测试文件、任何 V1 服务/Core 服务类、前端任何文件：一律不动。**

### 4.3 明确不新增

- **不新增迁移**（0006 已含全部所需列/约束/索引，见 §8）。
- **不新增依赖**（`unicodedata`/`re` 均 stdlib；不装 PyYAML、不装任何解析库）。
- **不新增 ORM 表/列**。
- **不新增索引**（R3 全局预检用既有表的单列 `SELECT DISTINCT`，**不为 `link_normalization_version` 建索引**，以免动迁移；成本与优化见 §8.4.3）。
- **不新增端口方法、不改 A1-01 端口契约**（R3 全局守卫由 **backend 具体仓库类的内部预检** + **Core 纯函数规则** + **backend 非端口批量入口 `apply_link_key_plan()`** 实现；`ports.py::LinkRepository` 的 10 个方法签名/参数/返回类型**零变化**，唯一改动仍是 D3 批准的一行 docstring）。
- **不改 `uv.lock` / `package-lock.json` / 任何 `pyproject.toml` / `package.json`**。
- **不新增 HTTP 写端点**（D8；人工绑定写入口属后续里程碑，§6.7）。

---

## 5. 专节论证：`normalized_link_key` 与 Hash 的关系

> 用户要求逐项区分并回答 7 个问题；**若与设计冲突先报告，不擅自改 Hash 契约**。本节结论：**未发现设计冲突**。发现 1 处潜在耦合（§5.3，已给出不改 A1-02 代码的守住方案）与 1 处残留语义（§5.4，**D1 已裁决取方案 A，不改契约**）。R2 另按审查意见修正了 `review_payload_hash` 的测试口径（问 5 / 问 7 / §7.2 场景 F）。

### 5.1 六个概念的定性

| 概念 | 本质 | 存放位置 | 是否交换载荷 | 是否派生索引 |
|---|---|---|---|---|
| **用户书写 wikilink 字面**（`[[知识表示]]`、`[[本体论\|本体]]`） | 用户内容，正文的一部分 | `knowledge_item.content` 正文 | ✅ 是（作为 content 的一部分） | ❌ |
| **`target_id`** | 稳定 UUID 绑定 | `knowledge_link.target_item_id` + 交换 `links[].target_id` | ✅ 是（§2.2.3 示例含） | ❌（是身份，不是索引） |
| **`target_title`** | 用户书写的目标标题**原始字面**（不是目标当前标题） | `knowledge_link.target_title` + 交换 `links[].title` | ✅ 是 | ❌ |
| **`alias`** | 用户书写别名原始字面 | `knowledge_link.alias` + 交换 `links[].alias` | ✅ 是 | ❌ |
| **`normalized_link_key`** | 由 title+alias 经 NFKC 规则**计算**出的行身份键 | **仅** `knowledge_link.normalized_link_key` | ❌ **否**（§2.2.3 示例不含） | ✅ **是** |
| **`link_normalization_version`** | 计算该键所用规则版本 | **仅** `knowledge_link.link_normalization_version` | ❌ **否**（§2.2.3 示例不含） | ✅ **是** |
| （附）`resolution` | 解析结果状态 | `knowledge_link.resolution` + 交换 `links[].resolution` | ✅ 是（§2.2.3 示例含） | 半派生（见 §5.4） |
| （附）`cross_space` | 是否跨空间绑定 | 仅 DB 行 | ❌ 否 | ✅ 是 |
| （附）**`normalized_title_key`**（D2 新增） | 由 title 经同一 NFKC 规则计算的**解析匹配键**（不含 alias） | **不持久化**：仅 Core 内存即时计算 | ❌ **否** | ✅ **是**（纯派生，可随时重算，见 §5.5） |

**核心分界线**：**原始字面 + 稳定绑定 = 交换载荷（用户身份）；规范化键 + 规则版本 = 派生索引（内部可重建）**。

### 5.2 逐项回答用户 7 问

**问 1：哪些属于交换载荷？**
`content` 中的 wikilink 字面、`links[].target_id`、`links[].title`（原始字面）、`links[].alias`（原始字面）、`links[].resolution`。依据：设计 §2.2.3 示例逐字段列出。

**问 2：哪些属于派生索引数据？**
`normalized_link_key`、`link_normalization_version`、`cross_space`、以及「按标题规范化匹配候选」这一过程本身。它们**只存在于 DB 行与 Core 计算过程**，不写入交换文件。依据：§2.4「存于链接行」+ §2.2.3 示例不含。

**问 3：哪些参与 `document_payload_hash`？**
参与：正文（含 wikilink 字面）、`links[].target_id/title/alias/resolution`、以及 id/tags/space/status/version/timestamps/sources/attachments/extra_metadata（§2.6.1 覆盖字段表）。
**不参与**：`normalized_link_key`、`link_normalization_version`、`cross_space`——因为它们不在交换载荷里。

**问 4：哪些参与 `document_content_hash`？**
**只有 `title` + `content`**。因此：正文里的 wikilink **字面**参与 content_hash（它是正文文本）；`links[]` 清单整体**不参与**；规范化键/版本当然不参与。
→ **改别名显示名而不动正文**：content_hash 不变（正文没变），payload_hash 变（links 清单变了）。符合 §2.6.2「仅 links 变化（正文同）→ content 同、payload 异 → 非内容审核」。
→ **把 `[[Foo]]` 改写成 `[[Ｆｏｏ]]`**：正文字面变了 → **content_hash 变**（这是用户真实改写，不是索引重建），尽管两者规范化同键、绑定同一个 target_id。这一点必须向用户讲清楚：**规范化同键 ≠ 正文未变**。

**问 5：哪些参与 `review_payload_hash`？**
**只有实际提交审核的变更 payload：`title?/content?/status?/space_id?`**（§2.6.1）。`links`、`tags`、`normalized_link_key`、`link_normalization_version` **一律不参与**。

**A1-02 实现实测（`markdown/__init__.py`，本轮复核）**：
- `_REVIEW_KEYS = frozenset({"title", "content", "status", "space_id"})`；传入任何其它键 → `CanonicalizationError`。
- **`if not changes: raise CanonicalizationError("review_payload_hash 不接受空变更（无实际审核内容）")`** —— **空 payload 直接抛异常**。
- 因此 `review_payload_hash` **在定义上就不是「完整文档状态 Hash」**，而是**某一次审核提案的变更身份**。它**不能**由文档当前状态算出，也**不存在**「对整篇文档求 review_hash」这种用法。

→ 链接同步、键重建、反链变化**永不触发内容审核**，也不改变任何既有提案的身份。这与 §2.6.2「links 变化 → 绑定优先恢复/重解析（非内容审核）」一致。
→ **测试口径修正（审查意见三）**：场景 F 验证 review_hash 不变时，必须**构造一个固定的非空审核变更 payload**（例如 `{"title": "A′", "content": "新正文"}`），在重建前后各算一次并断言逐位相等；**不得**把它写成「文档状态 hash 不变」，也**不得**传空 dict（会抛异常）。详见 §7.2 场景 F。

**问 6：规范化版本升级时如何迁移？**
见 §8.3（R2 已按审查意见重写，R3 补 §8.3.5 执行边界，**R3.1 补 §8.3.6 门禁 C / §8.3.7 十步顺序 / §8.3.8 不新增摘要**）与 §8.4（版本同构性 + **全局守卫**）。要点：**全量预算新键 → 写前检测全部碰撞组 → 有碰撞则整体拒绝本次重建（零写入、原行/原键/原版本/原绑定全保留）+ 结构化碰撞报告 → 无碰撞才产出覆盖全表的计划，由 backend 在单事务内批量执行**；`target_id` 与 `resolution` **一律不动**；**交换文件不重写、三 Hash 不重算、`canonicalization_version` 不动**（两套版本号相互独立，§2.6.1 明文）。回滚 = 以旧版本号重跑同一流程，**同样受碰撞拒绝约束**（§8.3）。**★ R3.1 追加：计划可能过期**——backend 在**执行事务内重读当前全表 6 列**，经门禁 A（版本漂移）/ B（覆盖与唯一）/ **C（逐行快照新鲜度，10 类不一致）** 独立校验，任一不一致 → `refused_stale_plan` + **数据库零写入** + `requires_replan=True`，**必须重读全表重生成计划，不得重试旧计划、不得部分更新**；**plan 阶段的检查不构成 apply 阶段的安全保证**（§8.3.7）。

**问 7：重建链接索引是否会改变文档交换身份？**
**不会。R2 修订后这一结论比 R1 更强，因为重建被收窄为「只写两个非交换列」；R3 进一步把这两列的写入也移出 Core（§8.3.5），Core 在重建路径上零写入：**

1. 重建**只写** `normalized_link_key` 与 `link_normalization_version`（外加行维护时间 `updated_at`），且**只由 backend `apply_link_key_plan()` 在单事务内执行**。
2. 重建**绝不写** `target_id` / `target_title` / `alias` / `resolution` / `cross_space` / `created_at`，**绝不写** `knowledge_item` 的任何列，**绝不重解析**（重解析属 `LinkReresolve`，是另一个显式动作）。
3. 交换载荷 `links[]` 的子字段只有 `target_id/title/alias/resolution`（§2.2.3），**全部落在第 2 条的「绝不写」集合里** → 交换载荷逐字不变。
4. 正文 `content` 与 `title` 不变 → `document_content_hash` 不变；完整交换载荷不变 → `document_payload_hash` 不变（组件 `links_hash` 亦不变）。
5. `review_payload_hash` 是**某次提案变更 payload 的身份**，与链接行无任何输入交集 → 对同一固定非空 payload，重建前后必然逐位相等（见问 5 的实现实测）。
6. **有碰撞时整体拒绝、零写入** → 连那两个非交换列都不变，交换身份更不可能变。
7. **R3 补充**：导入恢复时按当前空间关系**重算 `resolution`**（§6.6）属**链接语义状态变化**，与 D1/§5.4 同一口径——它**不是索引重建**，因此「重建不改交换身份」的结论不受影响；但**跨空间布局的导入再导出确实可能改变 `payload_hash`**，这一点在 §6.6 与 H20 中如实断言，不掩盖。
8. **★ R3.1 补充（结论更强，且不新增任何 Hash 契约）**：计划过期时门禁 C **整个计划拒绝 + 数据库零写入**（T30 断言 `knowledge_link` 全列、`knowledge_item` 全列、三 Hash、导出文本字节**逐位不变**）→ 连那两个非交换列都不动。**同时明确：R3.1 不新增计划摘要 / 不新增任何 Hash 字段 / 不使用内置 `hash()` / 不改 `document_content_hash`·`document_payload_hash`·`review_payload_hash` 与 `canonicalization_version` 契约 / 计划摘要不进入交换载荷与子键白名单 / 不新增数据库字段**（§8.3.8、T38）。内部索引重建与文档交换身份**继续保持完全解耦**。

**A1-03 把这条写成硬测试**（§7.2 场景 F）：用**无碰撞**夹具执行一次**确实生效**的重建（断言键/版本真的变了，避免「因为没重建所以 hash 当然不变」的空洞通过），再断言三 Hash 逐位相等 + 导出文本字节相等 + 全部 `target_id` 保留 + 第 2 条六列逐行不变。

### 5.3 潜在耦合点（已识别，非设计冲突，需在实施中守住）

**耦合点**：A1-02 `canonical.py::sort_links` 的**首排序键**读 `link.get("normalized_link_key")`，缺失才回退 `title`。
**风险**：若 A1-03 导出器把 `normalized_link_key` 写进 `links[]`，则键重建会改变排序 → 改变 canonical JSON → **改变 payload_hash**，正好违反问 7。
**处置（不改 A1-02 代码）**：A1-03 导出**绝不**写入 `normalized_link_key`/`link_normalization_version`/`cross_space`。于是首键恒回退 `title`，排序与重建无关。
**补充事实**：若**用户自己的**入站文件在 `links[]` 里手写了 `normalized_link_key`，A1-02 编解码会把它当未知子键**原样保留**（实测 `sort_links` 不丢键）——那属于用户载荷，参与 hash 是正确的，不是我们的索引。
**守护测试**：`test_markdown_link_service.py` 断言「导出文本不含 `normalized_link_key`/`link_normalization_version` 字样」+「重建前后导出字节相同」。

### 5.4 残留语义：`resolution` 参与 payload_hash（**D1 已裁决：保留，不改 Hash 契约**）

**议题：`resolution` 是派生状态，却在交换载荷里参与 payload_hash。**
后果：目标条目被**创建**（原 missing → resolved）或**删除**（resolved → missing）时，**源文档正文一字未改**，但其 `links[].resolution` 变 → `document_payload_hash` 变。
设计立场：§2.6.2 明确把「仅 links 变化（正文同）」归为「content 同 / payload 异 / 非内容审核」，即**设计接受**这种 payload 变化；§2.6.3 又规定幂等权威是**入站源文件的持久化 source_payload_hash**，不是目标再生后的 hash，因此跨实例重导不会误判。
**结论：与用户「索引重建不得改变交换身份」的要求不冲突**——resolution 变化是**链接语义状态变化**，不是索引重建。
**裁决结果（D1，用户已批准）：取方案 A —— `resolution` 保留在交换载荷，不修改 Hash 契约。**

- **A（✅ 已采纳，设计原文）**：`resolution` 留在交换载荷。完全遵循 §2.2.3/§2.6.2，**零契约变更**、`canonicalization_version` 保持 v1、历史 hash 无需重算。已知代价：他人创建/删除条目会改变本文档 `payload_hash`（`content_hash` 与 `review_hash` 不变，**不触发审核**）——这是**链接语义状态变化**，不是索引重建，与用户核心要求不冲突。
- **B（❌ 不实施）**：把 `resolution` 移出交换载荷。属 **Hash 契约变更**，须 bump `canonicalization_version` 并重算全部历史 hash，且与 §2.2.3 示例不一致。**A1-03 不实施 B，也不悄悄实施 B**；若将来需要，另开变更批次并单独审批。

**落地守卫**：导出子字段白名单恒为 `target_id/title/alias/resolution`（R1）；测试断言 `canonicalization_version` 在 A1-03 全程保持 `1`，且 A1-02 的 hash 相关用例指纹与结果均不变。

### 5.5 另一个必须澄清的键区分（设计只命名了一个键）

设计 §2.4 只定义 `normalized_link_key = norm(title) + "\x1f" + norm(alias)`，同时要求「解析时当前空间多个**目标标题**规范化同键 → ambiguous」。这两处用的其实**不是同一个键**：

| 键 | 公式 | 用途 | 是否持久化 |
|---|---|---|---|
| `normalized_link_key` | `norm(title) + \x1f + norm(alias or "")` | **链接行身份**（同源唯一）；绑定优先同步按它匹配；别名变=键变 | ✅ DB 列（已建） |
| `normalized_title_key` | `norm(title) + \x1f + ""` | **解析匹配**（与条目标题比对，条目没有 alias）；碰撞检测 | ❌ 不持久化，Core 内计算 |

**为什么必须分开**：条目标题没有 alias，若拿含 alias 的完整键去匹配条目标题，`[[B|显示名]]` 永远匹配不上 B。
**这是实现必需，不是设计变更**：§2.4 的「标题规范化同键」本就指标题键。A1-03 将显式命名 `normalized_title_key` 并加测试锁定两者区别（`[[B]]` 与 `[[B|别名]]` → **两个不同行身份键**，但**同一个解析标题键**，都应绑定 B）。
**不新增 DB 列**（标题键即时计算，避免第二份派生索引与一致性负担）。

**D2 已裁决批准**：新增 `normalized_title_key`，作为 **Core 内部派生计算**，**不持久化**、**不进交换载荷**、**不参与任何 Hash**。它只在两处使用：① 解析时与候选条目标题比对；② 导入提示按标题键聚合（§6.5）。因此它同样是「可自由重算的内部索引」，不影响文档交换身份。

---

## 6. 规范化与碰撞处理

### 6.1 规范化算法（v1，严格按 §2.4 五步）

```
normalize_link_text(s):
  1. unicodedata.normalize("NFKC", s)      # 全角→半角、ﬁ→fi、①→1、㈱→(株)
  2. s.strip()                             # 去首尾空白
  3. re.sub(r"\s+", " ", s)                # 内部连续空白折叠为单空格
  4. s.casefold()                          # 大小写折叠（非 lower）
  5. 返回（可能为空串）
```

- alias 同规范化；**空 alias → 规范空串 `""`，不是 NULL**（保证键始终非空、唯一约束不因 NULL 失效）。
- `normalized_link_key` 始终非空：title 规范化后为空 → 该 wikilink 判**畸形**，不建行（§6.3）。
- **原始字面绝不覆盖**：`target_title`/`alias` 存用户原文，规范化只用于键。
- **hash 输入不做规范化**（§2.6.1）：规范化只服务于链接键，`canonical.py` 不受影响。

### 6.2 碰撞矩阵（不随机绑定）

| 情形 | 判定 | 行为 |
|---|---|---|
| 当前空间**多个条目标题**规范化同键（`ﬁle`/`file`、`Ｆｏｏ`/`Foo`、`①`/`1`） | `ambiguous` | `target_id=None`，返回全部候选（含原始标题+稳定 ID），等用户显式选择 |
| 同源**多个书写**规范化同键（`[[Foo]]` 与 `[[Ｆｏｏ]]`） | 合并为**单行** | 保留**首现**原始字面展示；唯一约束不冲突 |
| 同源同键但**意图指向不同目标**（导入提示中多个**有效** `target_id` 相互矛盾 / 人工指定与解析矛盾） | `conflict` | `target_id=None`，**保留矛盾双方全部信息** + warning，**不随机重绑**、**不 last-write-wins**（详见 §6.5） |
| 当前空间唯一匹配（**不含 archived**） | `resolved` | 绑定稳定 UUID |
| 当前空间无匹配 | `missing` | **不自动跨项目**；保留原文与字面 |
| **候选只有 archived 条目**（D7） | `missing` | **自动解析排除 archived**（多为合并后归档），不自动绑到已归档内容；archived 候选仍在 `resolve-candidates` 中**带 `status` 标注列出**，供用户显式选择 |
| **用户显式选择 archived 目标**（D7） | `resolved` / `cross_space` | **允许绑定**，不因 archived 而拒绝；「排除」只作用于**自动**解析，不禁止显式绑定。⚠ **A1-03 无 HTTP 写入口**（D8），该规则只在 Core 层定义并由测试直接调用验证（§6.7） |
| **自链接**（A 正文含 `[[A]]`，D7） | `resolved` | **允许正常解析并绑定自身稳定 ID**，不额外禁止、不降级为 missing；`list_backlinks(A.id)` 会含 A 自身（如实呈现，不特殊过滤） |
| 用户主动选其它空间目标 | `cross_space` | 绑定 + `cross_space=True`。⚠ 同上：**A1-03 无 HTTP 写入口**（§6.7） |
| **导入提示：有效 UUID，目标在另一空间**（R3 新增，§6.6） | `cross_space` | **恢复绑定** + **按当前空间关系重算 `cross_space=True`** + warning；**绝不**写成 `resolved` + `cross_space=False` |
| **导入提示：有效 UUID，目标已 archived**（R3 新增，§6.6） | `resolved` / `cross_space` | **恢复绑定**（与 D7 显式绑定同口径）+ archived warning；`cross_space` 只由空间关系决定，**与 archived 无关** |
| 目标被删除 | `missing` | FK **SET NULL** + **同事务显式降级**（D12/§2.6），`target_title` 原始字面留存（快照） |
| **键重建后新规则产生同键**（问题 A 修订） | **整体拒绝本次重建** | **零写入**：全部原行/旧键/旧版本/原绑定原样保留；返回结构化碰撞报告（`link_id/old_key/new_key/old_version/target_id`）；等用户处理碰撞后重跑。**不合并行、不覆盖、不静默删除、不随机重绑、不做部分/混合版本重建**（§8.3） |

**服务级不变量（实体校验器之外额外守住）**：`ambiguous`/`conflict` 行的 `target_id` 必须为 `None`，除非用户显式裁决（裁决后状态转 `resolved`/`cross_space`）。实体校验器只禁止「resolved 无 id」与「有 id 却 missing」，**不禁止 ambiguous 带 id**，故必须在服务层加断言 + 测试。

**D7 口径澄清（审查意见四.1）**：「排除 archived」**仅指自动解析的候选过滤**，**不是**禁止绑定 archived。用户显式选择 archived 目标时正常绑定并标 `resolved`（跨空间则 `cross_space`）。自链接同样**允许正常解析**，不再按 R1 稿的「排除自身→missing+warning」处理。

**⚠ 交付边界（R3，第二轮审查意见三）**：上表凡标「用户显式选择/用户主动」的行，都是 **Core 服务层规则**，**A1-03 不提供可供用户操作的 HTTP 写入口**（D8 只交付 3 个只读 GET）。详见 **§6.7**：这些规则**已定义、已由真实测试在 Core/DB 层验证**，但**不得描述为已交付的用户功能**。

### 6.3 书写边界与排除矩阵（`WikilinkParser`）

**接受**：`[[标题]]`、`[[标题|别名]]`（单行）。

**排除（不产生链接）**：

| 构造 | 例 | 处置 |
|---|---|---|
| 围栏代码块 | <code>\`\`\`python … [[X]] … \`\`\`</code>、`~~~` 围栏、带 info string、外层更长围栏嵌套 | 整块跳过 |
| 行内代码 | <code>\`[[X]]\`</code>、<code>\`\`[[X]]\`\`</code> | 跳过 |
| 转义 | `\[[X]]` | 跳过 |
| 未闭合 | `[[X` | 畸形 + warning |
| 空标题 | `[[]]`、`[[   ]]`、`[[\|别名]]` | 畸形 + warning |
| 嵌套 | `[[A[[B]]]]` | 畸形 + warning |
| 跨行 | `[[A\nB]]` | 畸形 + warning |
| 超长 | title/alias 原始字面 > 500 | 畸形 + warning（对齐实体 `max_length=500`） |
| **规范化后键超长** | NFKC 扩展致 key > 1024 | 畸形 + warning，**不建行**（对齐 DB `String(1024)`；见 §9 R4 方言一致性） |
| 控制字符 | 字面含 `\x1f`/`\x00` 等 | 畸形 + warning（**防键注入**：避免用户用分隔符伪造 title/alias 边界） |
| 嵌入语法 | `![[X]]` | **不作为知识链接**（**D6 已裁决**：排除出知识链接解析，保留给 A1-04 附件嵌入），记 warning |
| frontmatter 内的 `[[…]]` | — | 不参与解析（编解码已把 body 与 frontmatter 分离，只解析 body） |

**诚实边界（设计未要求，本轮不做，写入验收局限）**：
- **4 空格缩进代码块不排除**（§2.4 只列围栏/行内/转义）。在列表 continuation 中 4 空格缩进并非代码，强行排除会误杀真实链接，故取设计字面口径，如实记录「缩进代码块内的 `[[X]]` 会被解析为链接」。
- HTML 注释 `<!-- [[X]] -->` 不排除（设计未要求）。
- Markdown 普通链接 `[t](url)`、图片 `![](attachments/k)` 天然不是 wikilink，不受影响。

### 6.4 绑定优先同步算法（§2.4 原文落地）

```
sync_links(item, body):
  rows = repo.list_links(item.id)
  # ★ 局部版本守卫（per-source，defense-in-depth，§8.4.3）：本源任一行版本 ≠ 当前常量
  #   → 抛 LinkNormalizationVersionMismatch，拒绝本次同步（宁可失败也不静默丢绑定）。
  #   ⚠ R3 修正：all([]) == True，故本检查**不能证明全表同构**（源条目无链接行时恒通过）。
  #     全表同构由 **backend 持久化边界的全局预检**权威保证（§8.4.3），Core 不做全表扫描。
  assert all(r.link_normalization_version == LINK_NORMALIZATION_VERSION for r in rows)
  parsed   = WikilinkParser.parse(body)                  # ① 纯文本
  merged   = merge_same_key(parsed)                      # 同键合并，首现字面
  existing = {link.normalized_link_key: link for link in rows}
  # ★ R3：候选枚举必须显式按空间等值过滤（§2.5⚠ 实测 list(space_id=None) 返回全库）
  raw_candidates = repo.list(space_id=item.space_id,
                             include_unassigned=(item.space_id is None))
  same_space = [i for i in raw_candidates if i.space_id == item.space_id]   # None==None 同空间
  candidates = build_title_index(                        # 自动候选：排除 archived（D7）
      [i for i in same_space if i.status != KnowledgeStatus.ARCHIVED])
      # 不排除 item 自身（自链接允许，D7）
  for key, literal in merged:
      old = existing.get(key)
      if old is not None and old.target_id is not None:
          continue                        # ★ 键不变且已绑定 → 保留绑定，绝不重解析
      if old is not None:
          keep(old)                       # ★ 键不变未解析 → 维持（不 churn ID/updated_at）
      else:
          repo.save_link(resolve(literal, candidates, item.space_id))   # 新键 → 解析
          # ★ 全局预检在此写入点由 backend 仓库执行（同事务）；不同构 → 抛异常 → 整次同步回滚
  for key, old in existing.items():
      if key not in merged:
          repo.delete_link(old.id)        # 删键 → 删行（删除不破坏版本同构，§8.4.3）
  return LinkSyncReport(created/kept/removed/ambiguous/conflict/warnings)
```

> **注意**：`existing` 字典本身也是「按键聚合」，但它**不是** last-write-wins 隐患——因为 DB 的 `UNIQUE(source_item_id, normalized_link_key)` 保证同源同键**至多一行**，字典推导不可能覆盖。真正存在覆盖隐患的是**导入提示**（frontmatter `links[]` 无唯一约束），已在 §6.5 按审查意见改为先聚合再判定。

**不变量（全部写成测试）**：
1. 已绑定行在「键不变」时 **`id`、`target_id`、`created_at` 完全不变**，且不触发解析。
2. 同步**不创建 `knowledge_version` 行**、**不改 `knowledge_item.updated_at`**、**不动 FTS/向量索引**（索引同步仍由既有 `sync_index` 负责）。
3. 同步**不写 `KnowledgeRelation`**（V1 关系不受影响）。
4. 连续 N 次同正文保存 → 链接行集合与 ID **完全稳定**，无重复行（场景 E）。
5. 同事务内失败 → 整体回滚，不留半套链接。

### 6.5 导入 `target_id` 优先恢复（`LinkImportRestorer`）—— R2 按审查意见「问题 B」重写

**R1 稿的缺陷（原问题）**：`hints = {normalized_title_key(l.title): l for l in frontmatter_links}` 是**字典推导覆盖**，同一标题键的多个提示会 **last-write-wins**：前一个提示携带的 `target_id` 被静默丢弃，矛盾提示被掩盖，恢复结果依赖 frontmatter 中 `links[]` 的**书写顺序**（非确定性语义）。

**R2 修订方案：先聚合，再判定。** 聚合阶段**只分组、不选择**；判定阶段按「有效提示」集合的**基数**决定，与顺序无关。

```
restore(item, frontmatter_links, body):
  # ① 正文是链接存在性权威（D4 已裁决）
  literals = merge_same_key(WikilinkParser.parse(body))

  # ② 先聚合：同标题键的全部提示都保留，绝不覆盖（纯文本层 group_hints_by_title_key）
  groups = group_hints_by_title_key(frontmatter_links)   # dict[title_key, list[Hint]]

  for literal in literals:
      group = groups.get(normalized_title_key(literal.title), [])

      # ③ 逐条判定有效性（三类无效都记 warning，且保留原始信息，不静默丢弃）
      valid, invalid = [], []
      for h in group:
          if h.target_id is None:            invalid.append((h, "no_target_id"))
          elif not is_uuid(h.target_id):     invalid.append((h, "malformed_uuid"))
          elif repo.get(h.target_id) is None: invalid.append((h, "target_not_found"))
          else:                              valid.append(h)

      # ④ 按「有效提示的不同 target_id 基数」判定（顺序无关）
      distinct = {h.target_id for h in valid}
      if len(distinct) == 1:
          bind_with_current_spaces(the_single_target_id, item)   # ★ R3：空间语义见 §6.6
          #   同空间 → resolved + cross_space=False
          #   跨空间 → cross_space + cross_space=True + warning（绝不伪装成 resolved）
          #   目标 archived → 仍恢复（D7 显式绑定同口径）+ archived warning
          warn_if(invalid)                    #   被忽略的无效提示仍逐条记 warning
      elif len(distinct) > 1:
          resolution = CONFLICT; target_id = None
          warning(全部矛盾 target_id + 各自原始 title/alias 字面)   # ★ 保留冲突双方信息
          report.conflicts.append(...)        #   不随机选、不取首条、不取末条
      else:                                   # 无有效目标
          resolve_by_title(literal, candidates)   # ★ 回退标题解析（同一套 §6.2 规则）
          report.unresolved_links.append(...)     #   无效提示逐条记 warning

  # ⑤ 孤儿提示：标题键未在正文出现 → 不建行 + warning（D4）
  for title_key, group in groups.items():
      if title_key not in {normalized_title_key(l.title) for l in literals}:
          report.orphan_hints.extend(group); warn(...)

  return LinkRestoreReport(restored / conflicts / fallbacks / orphan_hints / invalid_hints / warnings)
```

**判定矩阵（审查意见二·问题 B 的四条要求逐条落地）**：

| 提示情形 | 判定 | 行为 |
|---|---|---|
| 单个有效提示 | 恢复 | 绑定该 `target_id`（标题已改名也恢复成功）；**resolution/cross_space 按当前空间关系重算（§6.6）** |
| 多个提示指向**同一** `target_id`（含同标题不同 alias 的重复提示） | 恢复 | 绑定该 `target_id`；**不产生重复行**（行身份仍由正文键决定）；空间语义同上 |
| 多个**有效**提示的 `target_id` **相互矛盾** | **conflict** | `target_id=None`、`resolution=conflict`；warning **列出全部矛盾 target_id 及其原始 title/alias**；报告留痕；**不随机绑定** |
| **无有效目标**（全部提示缺 id / UUID 非法 / 目标不存在） | 回退 | 走标题解析；逐条记 `invalid_hints` warning + `unresolved_links` |
| 有效提示 + 无效提示**混合** | 恢复 | 按唯一有效 target 绑定；无效提示**不被当作矛盾票**，但**必须**逐条 warning 保留（实现口径见下） |
| 提示标题键**不在正文** | 孤儿 | **不建行** + warning（D4） |

**「无效 ≠ 矛盾」的实现口径（本轮明确，供审查核验）**：矛盾投票**只在有效提示之间**进行。UUID 非法或目标不存在的提示**不构成一个候选绑定意图**（它根本没指向本实例的任何条目），因此不与有效提示形成 conflict，而是作为**数据质量问题**记 warning。理由：跨实例导入时 `target_id` 失效是 §2.4 明文预期的常态（「跨实例不存在→回退标题解析」），若把失效提示判为 conflict，会让**正常的跨实例导入**大面积进入冲突态，违背设计。此口径同时满足审查的四条要求（无 last-write-wins、矛盾进 conflict、无有效目标回退、保留双方信息）。

**确定性与信息保全（写成测试）**：
- **顺序无关**：把 frontmatter `links[]` 顺序颠倒 / 打乱，恢复结果（绑定、resolution、warning 集合）**完全一致**。
- **冲突双方信息不丢**：conflict 的 warning 与报告必须含**每一个**矛盾 `target_id` 及其原始 `title`/`alias` 字面，不得只留一个。
- **正文权威**：正文没有的 wikilink，即使 frontmatter 给了有效 `target_id`，也**不建行**（D4）。
- **同标题多别名**：正文 `[[B|别名1]]` 与 `[[B|别名2]]` 是**两个行身份键**、**同一个标题键** → 共用同一提示组；若该组唯一有效 target，则**两行都绑定 B**（§5.5 两键区分的直接后果）。

**正文权威口径（D4 已裁决批准）**：frontmatter `links[]` 只提供**绑定提示**；其键若不在正文出现 → **不建行** + warning + 记入报告（A1-04 的 ImportReport 承接）。理由：§2.4 绑定优先同步以正文解析为准，若允许 frontmatter 凭空造链接，会与「删键→删行」矛盾并产生不可见链接。

**跨实例**：`target_id` 在目标实例不存在 → 归入 `invalid_hints(target_not_found)` → 该组若无其它有效提示则回退标题解析 + `unresolved_links`（§2.4 原文）。A1-03 只实现「校验存在 + 回退」，**不实现** ImportOrigin/源 hash 幂等（A1-04）。

### 6.6 导入绑定的空间语义（R3 新增，第二轮审查意见二·阻塞项）

**原问题（R2 稿）**：§6.5 的有效性判定只检查 `repo.get(h.target_id) is None`，**完全没有检查目标条目与源条目的空间关系**。后果有两种，都不可接受：① 把跨空间绑定写成 `resolution=resolved` + `cross_space=False`（**把跨空间伪装成普通绑定**，违反审查要求 4）；② 或者反过来，一律拒绝跨空间恢复 → 正常的跨空间导出/导入无法恢复历史绑定。R2 对这两种后果都没有明确口径，属**实现正确性缺口**。

**R3 裁决采纳（用户建议口径，审查要求 3）**：**有效稳定 UUID 代表此前的历史显式绑定意图**；目标存在 → **恢复绑定**，并**按当前 source/target 的 `space_id` 重新计算 `resolution` 与 `cross_space`**；目标不存在 → 仍按原设计**回退标题解析**。

**为什么不采纳「不认可历史授权 → 进入待处理态」（审查要求 5 的另一分支）**：设计 §2.4 明文「frontmatter `target_id` 存在 → 校验目标存在 → **直接恢复绑定**」，跨空间导出/导入是设计明确支持的场景。若把跨空间恢复一律挂起为待处理态，而 **A1-03 又没有 HTTP 写入口（D8，§6.7）**，用户将**无处处置**这些挂起项 → 正常导入被大面积阻塞且无法解锁。故采纳「认可历史意图 + 强制重算 `cross_space` + warning」，**用显式标注代替静默挂起**，同时满足要求 4（绝不伪装）。

**空间判定表（精确等值，`None == None` 视为同空间）**：

| # | `source.space_id` | `target.space_id` | 目标状态 | `resolution` | `cross_space` | warning |
|---|---|---|---|---|---|---|
| 1 | `None` | `None` | 任意 | `resolved` | **False** | 无 |
| 2 | `"p1"` | `"p1"` | 任意 | `resolved` | **False** | 无 |
| 3 | `"p1"` | `"p2"` | 任意 | **`cross_space`** | **True** | `cross_space_binding_restored`（含双方 space_id + target_id + 原始 title/alias） |
| 4 | **`None`** | `"p1"` | 任意 | **`cross_space`** | **True** | 同上（**个人总知识库 → 项目空间也算跨空间**） |
| 5 | `"p1"` | **`None`** | 任意 | **`cross_space`** | **True** | 同上（反向亦然） |
| 6 | 任意 | 任意 | **archived** | **按 1–5 的空间关系决定** | **按 1–5 决定** | 额外 `archived_target_restored`；**archived 本身不改变 resolution/cross_space** |

**口径要点（逐条对应审查要求）**：

1. **同空间恢复** → `resolved` + `cross_space=False`（要求 1）。
2. **跨空间恢复** → 明确认可为**有效的历史显式绑定**（要求 2/3），`resolution=cross_space` + `cross_space=True`，**由当前空间关系重算，不沿用文件里的值**。
3. **绝不伪装**（要求 4）：`cross_space=True` 时 `resolution` **必须**是 `cross_space`，不得是 `resolved`；反之 `resolution=cross_space` 时 `cross_space` **必须**为 True。写成**服务层断言 + 测试**（实体校验器只管 resolved/missing 与 target_id 的关系，**不管 cross_space 一致性**，故必须在服务层加这条不变量）。
4. **archived 与 D7 一致**（要求 6）：有效 UUID 指向 archived 目标 → **恢复绑定**（等同历史显式绑定的延续），不因 archived 拒绝、不降级 missing；后续连续保存走绑定优先 → **不自动解绑**（场景 L④）。
5. **三类语义分离**（要求 7）：

| 情形 | 是否有效提示 | 参与矛盾投票 | resolution 结果 | warning / 报告字段 |
|---|---|---|---|---|
| **UUID 非法**（`"not-a-uuid"`/空串/数字） | ❌ 无效 | ❌ 不参与 | 组内无其它有效 → 回退标题解析（resolved/ambiguous/missing） | `invalid_hints(malformed_uuid)`，保留原始文本 |
| **目标不存在**（合法 UUID，本实例无此条目） | ❌ 无效 | ❌ 不参与 | 同上回退 + `unresolved_links` | `invalid_hints(target_not_found)` |
| **空间不匹配**（目标存在，但在另一空间） | ✅ **有效** | ✅ **参与** | **`cross_space` + `cross_space=True`** | `cross_space_binding_restored`（**不是 invalid、不是 conflict、不是 missing**） |

6. **空间比较用精确等值，不用聚合视图**：`include_unassigned=True` 的 personal 聚合语义**只用于自动候选枚举的仓库调用**，且 Core 侧仍按 §2.5⚠ 再做一次 `candidate.space_id == item.space_id` 精确过滤。**绑定恢复的空间判定绝不使用聚合视图**（否则「个人空间可看到未归属条目」会被误当成「同空间」）。
7. **自动解析与恢复的分界线**：**自动解析绝不跨空间**（无匹配 → `missing`，§6.2）；**只有携带有效稳定 UUID 的提示**才能建立跨空间绑定。这条分界线是「不自动跨项目」与「恢复历史显式绑定」并存的关键，写成测试（J + H14 对照）。
8. **`resolution` 不沿用文件值**：文件可能来自另一实例或另一空间布局，故 `resolution`/`cross_space` **一律由当前实例重算**。`cross_space` **不导出**（白名单只 `target_id/title/alias/resolution`，R1），`resolution` **导出**。

**Hash 诚实口径（必须如实断言，不掩盖）**：

- **同空间布局往返**（源文件与目标实例空间关系一致）→ 重算得到的 `resolution` 与文件相同 → `document_payload_hash` **不变**（场景 D 原有断言成立）。
- **跨空间布局导入**（文件里是 `resolved`，但本实例中目标在另一空间）→ 重算为 `cross_space` → **再导出的 `document_payload_hash` 相对源文件会变化**。这是**语义正确的结果**（链接语义状态变化，D1/§5.4 同一口径），**不是 Hash 契约变更**，也**不是索引重建**（§5.2 问 7 第 7 条）。`document_content_hash` **不变**（正文未改）。
- 测试 **H20** 对这两种情形**分别断言**，不得只测同空间情形就宣称「导入导出 hash 恒不变」。

**新增 warning 稳定码**（Core `LinkWarningCode` 追加，供 A1-04 ImportReport 消费）：`cross_space_binding_restored`、`archived_target_restored`。既有 `invalid_hints` 三类码不变。

**契约变更判定**：**无**。设计 §2.4 只写「校验目标存在→直接恢复绑定」，**未定义** `cross_space` 是否重算，属对设计**未定义处的口径明确**，且**用户本轮已给出建议口径并采纳**；不改交换字段集合、不改三 Hash 定义、不改 `canonicalization_version`、不改端口签名、不改表/列/约束。**本轮不修改设计文档**（建议实施后另批把「按当前空间关系重算 cross_space」补进 §2.4 措辞）。

**测试**：§7.6 **H13–H20**（同空间/跨空间/源无空间目标有空间/反向/archived/目标不存在/顺序无关/再导出 hash 口径），Core + 真实 SQLite + 真实 PG 三层各验适用部分。

### 6.7 人工绑定的交付边界（R3 新增，第二轮审查意见三）

**表面冲突**：**D7** 允许用户显式绑定 archived 与跨空间候选；**D8** 规定 A1-03 只交付 **3 个只读 GET**、不提前增加写操作 API。两者同时成立的唯一读法是：**D7 是 Core 语义规则的裁决，D8 是 HTTP 交付范围的裁决**。

**裁决（用户本轮明确）：保留 D8，不新增写 API。** A1-03 交付**候选发现与只读查询**；显式绑定规则**在 Core 设计中明确并被真实测试锁定**，但**没有可供用户操作的 HTTP 写入口**；人工绑定 API 与前端交互属**后续里程碑**；**不得把尚未通过 HTTP 实际执行的人工绑定描述为已交付功能**。

| 能力 | A1-03 交付状态 | 真实验证方式 |
|---|---|---|
| 候选发现（含 archived 带 `status` 标注、跨空间候选列出） | ✅ **交付** `GET /knowledge/links/resolve-candidates`（只读） | TestClient 真实调用 + 响应字段断言 |
| 出链 / 反链只读查询 | ✅ **交付** 2 个 GET | TestClient 真实调用（改名后反链仍命中） |
| 自动解析（同空间、排除 archived、允许自链接） | ✅ **交付**（保存路径自动触发） | HTTP create / draft-PATCH / extract 后断言链接状态 |
| 导入提示恢复（含跨空间 / archived UUID 恢复，§6.6） | ✅ **Core 服务交付**；⚠ **HTTP 导入端点属 A1-04** | Core + SQLite + PG 真实测试直接调用服务 |
| **人工显式绑定**（选择 archived / 跨空间 / 歧义候选） | ⚠ **Core 规则已定义 + 已测试；无 HTTP 写入口 → 未交付为用户功能** | 测试**直接调用 Core 服务/仓库**建立绑定 |
| 人工绑定写 API（`POST links/resolve`） | ❌ **后续里程碑**（A1-04 / A1-T11） | — |
| 前端绑定交互（候选选择器 / 歧义裁决 UI） | ❌ **A2 / A1-06** | — |
| `POST links/reresolve`、`POST links/rebuild-keys`、运维 CLI | ❌ **后续**（A1-T11 / A1-T14） | — |

**验收措辞纪律（强制）**：

- 场景 **L③**「用户显式选择 archived → 允许绑定」与场景 **J**「用户显式选择跨空间 → cross_space」，在验收报告中**必须**写成「**Core 层显式绑定规则已验证（A1-03 无 HTTP 写入口）**」，**不得**写成「用户可通过界面/接口显式绑定 archived/跨空间目标」＝已交付。
- 场景 **L④**「显式绑定后连续保存不被自动解绑」：绑定由**测试直接调用 Core 服务/仓库**建立（夹具），随后经**真实 HTTP PATCH** 验证**保留**行为。即 **HTTP 侧验证的是「保留既有绑定」，不是「建立绑定」**，两者不得混淆。
- §13.1 已按此标注；§13.2 明确列出「人工绑定 HTTP 写入口 + 前端交互」为**未交付项，不得写成 PASS**。

**为什么规则先行不算过度设计**：后续里程碑接上写入口时，Core 语义**已确定且已被测试锁定**，不需要回头改 Core 或重新裁决 D7；同时候选发现（只读）已交付，用户**能看到** archived/跨空间候选，只是**还不能点选绑定**——这一局限必须如实告知，不得暗示可用。

**守护测试（防止实施时顺手加写端点）**：断言 A1-03 新增 router 的**方法 + 路径集合**恰好等于 3 个 GET（`{("GET", "/knowledge/{item_id}/links"), ("GET", "/knowledge/{item_id}/backlinks"), ("GET", "/knowledge/links/resolve-candidates")}`），**任何 POST/PUT/PATCH/DELETE 出现在该 router 即测试失败**；并断言 `knowledge.py` 既有端点的方法/路径/状态码集合未变（V1 只增不改）。

---

## 7. 测试矩阵（含用户指定的场景 A–E 连续测试）

> 全部**真实运行**才算通过；未运行的一律标「未验证」。Core 层用 `helpers.py` 的 InMemory 仓库，backend 层用**真实 SQLite** 与**真实 PostgreSQL**（`EXPLAINLAB_PG_TEST_URL` 门控，实例 `127.0.0.1:55432`）。

### 7.1 用户指定连续场景（每个场景在 Core / SQLite / PG **三层各跑一遍**）

| 场景 | 步骤（连续，不重置夹具） | 断言 |
|---|---|---|
| **A 改名不断链** | 创建 A、B → A 正文 `[[B]]` 保存 → **B 改名**为 B′ → A 再次保存 → A 导出 | A 链接行 `target_id` 仍等于 B 的稳定 UUID；`resolution=resolved`；`target_title` 仍是原书写字面 `B`；反链 `list_backlinks(B.id)` 含 A；导出 `links[].target_id` == B.id；**A 的 content_hash 不变**（A 正文没改） |
| **B 规范化碰撞** | 创建 `ﬁle` 与 `file` 两条目（同空间）→ A 正文 `[[file]]` 保存 | `resolution=ambiguous`、`target_id is None`；候选返回**两条**（原始标题各自保留）；**绝不随机绑定**；再创建 `Ｆoo`/`Foo` 重复验证；`①`/`1` 同键验证 |
| **C 改其它正文不丢绑定** | A 已绑定 B（含人工裁决的 ambiguous→resolved）→ 修改 A 的**无关正文段落** → 保存 → 再改一次 → 再保存 | 链接行 `id`/`target_id`/`created_at` 不变；不重新解析；人工裁决结果不被覆盖；无重复行；`knowledge_version` 不因链接同步增长 |
| **D 导出→毁索引→导入恢复** | 导出 A（含 `links[].target_id`）→ **显式删除全部链接行**（`delete_links_of_item`，D3 允许的用途；注意**键重建不删行**，故毁索引必须用显式删除）→ 用 A1-02 codec 解析导出文件 → `LinkImportRestorer` **先聚合提示再判定**恢复（§6.5） | 依 **稳定 ID** 恢复绑定；即使 B 已改名也恢复成功；`target_id` 不存在时归 `invalid_hints` 并回退标题解析 + 记 `unresolved_links`；恢复后 `document_content_hash` 与 `document_payload_hash` 与导出前一致（resolution 未变时），**固定非空审核 payload** 的 `review_payload_hash` 一致（口径见 §7.2 F） |
| **E 重复导入不膨胀** | 同一链接文档连续导入/同步 **5 次** | 链接行数恒定、ID 集合恒定；无重复关系；`knowledge_version` 行数不变；`knowledge_item.updated_at` 不因同步而变；`KnowledgeRelation` 行数不变 |

> 场景 E 的**完整导入幂等（`skipped` + ImportOrigin 源 hash 比对）属 A1-04**。A1-03 只验证**链接层**不膨胀，验收报告须如实区分，不得写成「导入幂等已验证」。

### 7.2 追加场景 F–M（守住 Hash、稳定性与本轮裁决口径）

| 场景 | 断言 |
|---|---|
| **F 键重建不改交换身份**（R2 按审查意见三重写） | 夹具：含链接文档，**新规则下无碰撞**。① 重建前记录：`document_content_hash`（由 `title+content` 算）、`document_payload_hash`（由 `payload_fields()` 算）、**固定非空审核变更 payload**（如 `{"title":"A′","content":"新正文"}`）的 `review_payload_hash`、导出文本字节、全部链接行的 `target_id`。② 执行 `LinkKeyRebuild`，**先断言重建确实生效**（`normalized_link_key`/`link_normalization_version` 真的变了、报告 `status=rebuilt`、`updated>0`）——避免「没重建所以 hash 当然不变」的空洞通过。③ 重建后：**三个 hash 各自逐位相等**；**导出文本字节相等**；**全部 `target_id` 保留**；`target_title/alias/resolution/cross_space/created_at` 五列逐行不变；`knowledge_item` 全列不变；组件 `links_hash` 亦不变。**口径纪律**：`review_payload_hash` 是**该固定提案变更的身份**，**不得**描述为「完整文档状态 Hash」，**不得**传空 dict（A1-02 实现对空变更抛 `CanonicalizationError`，实测见 §5.2 问 5）。 |
| **G 重建碰撞 → 整体拒绝 + 零写入**（R2 按审查意见二·问题 A 重写） | 夹具：v1 下不同键、新规则下同键的两行（**含不同 `target_id`**）。执行重建 → 报告 `status=refused_collision`，列出**每个**碰撞组的 `link_id / old_key / new_key / old_version / target_id`；**数据库零写入**：全部链接行**所有列**与重建前逐字段相同（含 `normalized_link_key`、`link_normalization_version`、`target_id`、`updated_at`）；`knowledge_item` 不变；三 Hash 与导出字节不变；**无行被合并/覆盖/删除**；**无随机重绑**。专项矩阵见 §7.5。 |
| **H 别名变更**（D5 已裁决：不继承） | `[[B]]` → `[[B|别名]]`：行身份键变（旧行删、新行建），**严格按新键重新解析，不继承旧 `target_id`**；因解析标题键不变且 B 唯一 → 重解析结果仍绑定 B（**这是解析得来的，不是继承来的**，测试须区分：把 B 改名成歧义标题后，alias-only 变更应重新落入 `ambiguous` 而非沿用旧绑定）。`[[B|别名1]]` → `[[B|别名2]]` 同理；content_hash 变（正文改了）、review_hash 不受 links 影响。 |
| **I 删除目标**（D12） | 删除 B（draft 直接删 / active 经审核批准）→ A 的链接行 `target_id` 变 NULL、`resolution=missing`、`target_title` 字面留存；A 正文与 content_hash 不变；反链查询返回空；**删除后读取 A 的出链/反链不抛异常**（§2.6/R13 非法组合已修复）；**读取侧防御映射**单独验证：手工把行置为 `target_id=NULL` + `resolution='resolved'`（模拟外部级联/历史脏数据）→ 仓库读取仍返回 `missing` 且不抛异常，**实体校验器未被弱化**（直接构造该非法实体仍抛 `ValueError`）。SQLite + PG 各验一遍。 |
| **J 跨空间不自动绑定**（R3 扩展） | 目标只在另一空间 → **自动解析** `missing`（不自动跨项目）；候选接口可列出跨空间候选；**显式选择** → `cross_space` + `cross_space=True`（⚠ **Core 层验证，A1-03 无 HTTP 写入口**，§6.7）。**R3 新增断言**：① 源条目 `space_id=None`、库中另有 project 空间同名条目 → 自动解析**不得**绑定该 project 条目（§2.5⚠ 实测 `list(space_id=None)` 返回全库，必须 Core 侧精确过滤）；② 源 `"p1"`、目标 `None` → 自动解析同样不跨空间；③ **对照 H14**：同一对条目若由**有效 UUID 提示**恢复 → **必须** `cross_space=True`（证明「自动不跨空间」与「恢复历史跨空间绑定」的分界线真实存在）。 |
| **K 自链接允许**（D7 新增） | A 正文含 `[[A]]` → `resolution=resolved`、`target_id=A.id`（**不是 missing、不额外禁止**）；`list_backlinks(A.id)` 含 A 自身；A 改名后自链接仍绑定（键不变→保留绑定）；连续保存 ID 稳定；自链接不影响三 Hash 口径。 |
| **L archived 口径**（D7 新增；R3 标注交付边界） | ① 目标为 archived 且是唯一匹配 → **自动解析得 `missing`**（排除 archived）；② `resolve-candidates` **仍列出该 archived 候选并带 `status=archived` 标注**（**只读 GET，已交付**）；③ **显式选择该 archived 目标 → 允许绑定**，`resolution=resolved`（跨空间则 `cross_space`）——⚠ **Core 层规则验证，A1-03 无 HTTP 写入口，不得写成已交付用户功能**（§6.7）；④ 显式绑定（**夹具由 Core/仓库层建立**）后再经**真实 HTTP PATCH** 连续保存 → 绑定优先保留，不因 archived 被自动解绑（**HTTP 侧验证的是「保留」而非「建立」**）；⑤ 同空间同时存在 active 与 archived 同键标题 → 自动解析只看 active，唯一 active → `resolved`（不因 archived 存在而误判 ambiguous）。 |
| **M 导入提示聚合**（问题 B 新增） | 重复提示（同 title 同 target）→ 恢复且无重复行；同 title 不同 alias 的多提示同 target → 恢复；**矛盾提示（同 title 两个不同有效 target）→ `conflict` + `target_id=None` + warning 含双方全部信息**；无效 UUID → 回退标题解析 + warning；目标不存在 → 回退 + warning；孤儿提示 → 不建行 + warning；**提示顺序打乱结果不变**。专项矩阵见 §7.6。**R3：空间语义（同空间/跨空间/archived）见 §6.6 与 H13–H20**。 |

### 7.3 单元矩阵（纯文本层，`test_markdown_links.py`）

- **规范化**：NFKC 全角/半角、合字 ﬁ/ﬂ、圈码 ①/1、`㈱`/`(株)`、compat 分解；casefold vs lower（`ß`→`ss`、`Σ/ς/σ`）；空白折叠（多空格/tab/全角空格 U+3000/换行）；strip；空串；**NFC 反例**（证明 NFC 不合并全角，故必须 NFKC）。
- **键**：title+alias 组合、空 alias→`""` 非 NULL、`\x1f` 分隔、键始终非空、`normalized_title_key` 与 `normalized_link_key` 区别、键长 1024 边界与超限拒绝、控制字符拒绝。
- **解析排除**：§6.3 矩阵逐行参数化（围栏 ``` / ~~~ / info string / 嵌套围栏 / 行内单反引号 / 双反引号 / 转义 / 未闭合 / 空 / 嵌套 / 跨行 / 超长 / 控制字符 / `![[embed]]`）。
- **同键合并**：首现字面保留、多次出现合并为一、意图矛盾→conflict。
- **提示聚合分组（纯文本层，问题 B）**：`group_hints_by_title_key` 对同标题键的多提示**返回完整列表**（不是单值）；分组与输入顺序无关（组内保留原序供报告展示，但判定不依赖顺序）；空列表→空字典；alias 不同但 title 同→同一组；title 规范化同键（`Ｆoo`/`Foo`）→同一组。
- **确定性**：同输入多次解析结果字节一致；解析不修改输入正文。

### 7.4 持久化与方言矩阵（`test_links.py` / `test_links_pg.py`，两边同断言）

- 唯一约束：同源同 `normalized_link_key` 重复插入被拒（**含 alias 为 NULL 与非 NULL 两种**，证明非空键修复了 NULL≠NULL 问题）。
- 不同源同键**允许**（唯一约束是复合）。
- FK：删源条目 → 出链 **CASCADE** 消失；删目标条目 → 入链 `target_item_id` **SET NULL** 且行仍在。
- `list_backlinks` 按稳定 ID（改名后仍命中）；`list_by_key` 精确等值（**不用 LIKE/ILIKE**）；`list_links` 按创建时间升序。
- `update_link` 保留 `target_id` 仅改键/状态；`delete_link` 返回布尔；`find_by_key` 命中/未命中。
- 长键（1024 边界）双方言行为一致；超长在 **Core 层**就被拒（不依赖 DB 报错，见 §9 R4）。
- `cross_space` 布尔双方言往返一致；时间戳 UTC 一致。
- 同步挂接：`POST /knowledge`、`PATCH`（draft）、`DELETE`、`extract` 四条路径真实 TestClient 调用后链接状态正确；**active PATCH 返回 202 时链接不被同步**（审核未应用）。
- **键重建（DB 级，T1–T11 的真实数据库落地）**：无碰撞全量更新后逐列快照比对；碰撞拒绝后**全表逐列零变化**；**故障注入触发真实事务回滚**后全表逐列复原；重复键插入在**两边都真实抛 `IntegrityError`**（T7）；重建全程在**单事务**内，`SELECT` 全量与 `UPDATE` 之间不 commit。
- **全局版本同构守卫（DB 级，R3 重写）**：手工把**其它 source** 的某行 `link_normalization_version` 改成异值 → **当前 source 即使没有任何链接行**，新建链接仍抛 `LinkNormalizationVersionMismatch` 且**全表零变化**（审查反例，T16）；空表创建第一条链接**允许**（T13）；全表同版本且等于常量 → 正常写入（T14）；混合版本 → 任何 source 的任何链接写入全部拒绝（T17）；HTTP 层返回 **409 + `detail="link_version_mismatch"`**（不回传异常文本/版本明细，AGENTS.md §9）；**SQLite 与真实 PG 各自验证**（T18）。
- **预检事务性与成本（DB 级，R3 新增；**R3.1 修订为无缓存口径**）**：预检与写入在**同一数据库事务**内（仓库只 `flush`，commit 由路由持有 —— 实测既有仓库模式；**R3.1 明确：Session 生命周期 ≠ 事务生命周期**，§8.4.3（1）（2））；预检是**单列 `SELECT DISTINCT link_normalization_version`**，**不加载 ORM 实体**；**★ R3.1：无缓存 ⇒ 同一事务内 k 次受守卫写入 = k 次预检**（用 SQLAlchemy 事件/查询计数断言 **计数 == 受守卫写入次数**，T20③【断言修订】+ **T34 权威断言**）；**commit 后新事务重新预检（T32）/ rollback 后新事务重新预检（T33）/ savepoint 与 nested 边界（T40）**；豁免写入（治理列-only、删除）**0 次预检**（T20①②、T34）。
- **治理列写入豁免（DB 级，R3 新增）**：版本不同构窗口内，**D12 删除降级**（只改 `target_id/resolution/cross_space`，键与版本不变）**仍可执行** → `DELETE /knowledge/{id}` 不被 409 阻断；删除链接行不破坏同构（T20）。
- **导入空间语义（DB 级，R3 新增）**：跨空间 UUID 恢复后**数据库列**真实为 `resolution='cross_space'` + `cross_space=1/True`（双方言布尔往返一致）；同空间恢复为 `resolved` + `cross_space=0/False`；archived 目标恢复后行仍在且绑定保留；**服务层断言**「`cross_space=True` ⟺ `resolution=cross_space`」（实体校验器不管这条，必须服务层守）。
- **重建执行边界（DB 级，R3 新增；**R3.1 增补门禁 C**）**：`apply_link_key_plan()` 的门禁 A（同事务重读全表单一版本 == `plan.source_version`）与门禁 B（计划覆盖全表行 + 无重复新键）**各自真实触发拒绝**：手工在 plan 与 apply 之间插入一行/改一行版本 → **拒绝且零写入**（T21）。**★ R3.1：门禁 C 在 DB 层同样必须真实触发拒绝**——在 plan 与 apply 之间改 `target_title`/`alias`/`source_id`/`normalized_link_key`、**新增或删除链接行**（这些都不改变版本集合，A/B 均放行）→ **`refused_stale_plan` + `requires_replan=True` + `stale_reasons` 结构化原因 + 数据库零写入**（T22–T29、T35–T37）；拒绝后 **`knowledge_link` 全列 + `knowledge_item` 全列 + 三 Hash + 导出文本字节逐位不变**（T30）；**SQLite 与真实 PG 各一遍**（T31）；**十步顺序守护 + 任一门禁失败后不得出现 UPDATE + 写后非键列与第 3 步重读值逐列相等 + 故障注入整体回滚 + 事务所有权**（T39）。
- **报告落盘（backend 侧，D10）**：`persist_rebuild_report()` 写入 gitignore 的 `backend/data/ops/`（测试用 `tmp_path`），读回 JSON 与 Core 报告 `model_dump(mode="json")` 一致；**Core 侧零文件 IO + 零数据库写入**（T12）。

### 7.5 键重建碰撞、回滚、**全局版本同构守卫**与**计划新鲜度门禁 C** 专项矩阵（第一轮·问题 A + 第二轮·意见一 + **R3.1·门禁 C**）

> 每条都在 **Core（InMemory）/ 真实 SQLite / 真实 PG** 三层各跑一遍；标注「DB」的条目必须在真实数据库上断言**逐列**快照，不能只断言键。
> **R3 分层口径（因 §8.3.5 执行边界调整）**：**Core 层**断言 `LinkKeyRebuild.plan()` 的**计划内容与拒绝决策**（Core 在重建路径上**零数据库写入、零文件 IO**）；**SQLite/PG 层**断言 `apply_link_key_plan()` 的**真实写入、逐列快照、门禁拒绝与事务回滚**。两层断言对象不同但**同一套正确性要求**，不得只在 Core 层测计划就宣称重建已验证。
> **R3.1 追加口径**：**T1–T21 全部保留，编号、断言与文件位置不变**（唯一例外是 **T20③ 的期望值随「撤回事务内缓存」而更正**，见该条标注与 REV-25，属**断言修订而非删除/弱化**）。**门禁 C 与事务生命周期的新断言一律追加为新编号 T22–T40（§7.5.1）**，不得覆盖或改写既有编号。Core 层新增断言对象为**纯函数 `check_plan_freshness()`**（十类判定 + 新键重算 + no-op 行盲区）；DB 层新增断言对象为**真实过期计划的拒绝与零写入**、**commit/rollback/savepoint 后的重新预检**。

| # | 用例 | 断言 |
|---|---|---|
| **T1** | **无碰撞正常重建** | 报告 `status=rebuilt`；全部行 `normalized_link_key` 按新规则更新、`link_normalization_version=target_version`；`target_id`/`target_title`/`alias`/`resolution`/`cross_space`/`created_at` **逐行不变**；`knowledge_item` 全列不变；三 Hash + 导出字节不变（= 场景 F） |
| **T2** | **单组碰撞** | 恰好一组 `(source_id, new_key)` 有 ≥2 行 → `status=refused_collision`；报告含该组**全部**成员的 `link_id/old_key/new_key/old_version/target_id`；**DB 零写入**（全表逐列快照前后相同，含 `updated_at`） |
| **T3** | **多组碰撞** | 构造 3 个互不相干的碰撞组（不同 source 或不同 new_key）→ 报告**完整列出 3 组**，不漏报、不只报第一组；仍**整体拒绝**、零写入 |
| **T4** | **不同 `target_id` 碰撞** | 同 source 两行分别绑定 B1、B2（v1 键不同），新规则下同键 → 拒绝；**两个 `target_id` 都原样保留在各自原行上**；**绝不合并成一行**（合并必丢一个绑定）；**绝不随机选一个**；**绝不静默删除任一行** |
| **T5** | **碰撞导致重建整体回滚（事务级，DB）** | 两条路径都测：① **写前检测**命中碰撞 → 根本不开写，零写入；② **故障注入**：绕过/晚于预检，在第 N 行 `update_link` 时注入异常（或故意写入重复键触发真实 `IntegrityError`）→ **整个事务回滚**，全表逐列快照与重建前**完全一致**，无「半套新键」残留 |
| **T6** | **回滚前后数据库行与三 Hash 完全一致（DB）** | 对 T2/T3/T4/T5 每种情形，比对**全部链接行的全部列** + **全部 `knowledge_item` 行的全部列** + `document_content_hash` + `document_payload_hash` + **固定非空 payload 的** `review_payload_hash` + 导出文本字节 → **全部逐项相等** |
| **T7** | **唯一约束确实存在（DB，反证预检必要性）** | 直接向同 source 插入两行相同 `normalized_link_key` → **SQLite 与 PG 都抛 `IntegrityError`**（证明「保留两行 + 写同一新键」在物理上不可能，故必须写前拒绝，而不是靠 DB 报错兜底） |
| **T8** | **跨 source 同键不算碰撞** | 两个不同 source 在新规则下同键 → **不拒绝**，正常重建（唯一约束是复合 `(source_item_id, key)`） |
| **T9** | **幂等重跑** | 对已是 `target_version` 的全表再跑一次 → `status=rebuilt`、`updated=0`、`unchanged=N`；**不 churn `updated_at`**；行集合与 ID 恒定 |
| **T10** | **回滚 = 旧版本重跑，同受碰撞约束** | 成功重建到 v2 后以 `target_version=1` 重跑 → 确定性恢复旧键旧版本，`target_id` 全保留，三 Hash 不变；若旧键在新数据下碰撞 → **同样整体拒绝 + 报告**，保持 v2 现状，**不做部分回滚** |
| **T11** | **版本同构性 + 重建入口专用门禁（§8.4，R3 扩展）** | 成功重建后全表 `link_normalization_version` **同构于目标版本**；拒绝后全表版本**保持原值同构**；构造混合版本行 → **常规链接写入**抛 `LinkNormalizationVersionMismatch` 且**零写入**（不静默丢绑定）。**R3 新增**：全表 v1 + 代码常量 v2 时，**常规写拒绝**但**重建入口允许**（重建门禁是「全表同构于单一版本」而非「等于常量」，否则升级永远无法执行，§8.4.4）；混合 v1/v2 时**重建入口同样拒绝**（零写入） |
| **T12** | **报告/计划结构完整 + Core 零文件 IO + 零数据库写入（D10 / R3）** | 计划与报告可 `model_dump(mode="json")` 往返；碰撞条目字段齐全（`link_id/old_key/new_key/old_version/target_id` + `source_id/target_title/alias`）；**行为守护①**：monkeypatch `builtins.open` / `Path.write_text` / `Path.mkdir` 使其抛异常后执行 `plan()`，**仍成功返回计划**（证明 Core 不碰文件系统）；**行为守护②（R3 新增）**：把注入仓库的 `save_link`/`update_link`/`delete_link` 全部替换为抛异常，`plan()` **仍成功返回计划**（证明 Core 在重建路径上不写库）；backend `persist_rebuild_report()` 写 `tmp_path` 后读回 JSON 与报告一致 |
| **T13** | **空表创建第一条链接（R3，审查要求 9-1）** | `knowledge_link` 为空 → 预检 DISTINCT 结果为空集 → **允许初始化**；新行 `link_normalization_version == LINK_NORMALIZATION_VERSION`；不抛异常、不返回 409 |
| **T14** | **全表 v1 + 代码常量 v1 正常写入（R3，审查要求 9-2）** | 既有行全为 v1、常量 v1 → 新建链接/改键更新**正常成功**；写入后全表仍同构 v1；既有行逐列不变 |
| **T15** | **全表 v1 + 代码常量 v2 拒绝写入（R3，审查要求 9-3）** | 用测试夹具把常量置为 v2（**不发布 v2 生产规则**）→ 任何常规链接写入抛 `LinkNormalizationVersionMismatch`；HTTP **409 + `link_version_mismatch`**；**零写入** |
| **T16** | **★ 审查反例：当前 source 无链接行，其它 source 有 v1 行（R3，审查要求 9-4）** | 夹具：source A、B 各有 v1 链接行，**source C 没有任何链接行**，常量 v2。断言：① R2 的局部守卫 `all([]) == True` **确实通过**（证明漏洞真实存在，不是假想）；② **全局预检拒绝** C 创建 v2 链接；③ C 的保存整体失败且**全表零写入**；④ 把 A/B 的行重建到 v2 后，C 的写入**恢复正常** |
| **T17** | **混合 v1/v2 全部拒绝（R3，审查要求 9-5）** | 构造 v1 与 v2 行共存（手工改列模拟）→ **任何 source**（含无链接行的 source、含 v2 行的 source）的常规链接写入**全部拒绝**；重建入口亦拒绝（T11）；零写入 |
| **T18** | **SQLite 与真实 PG 各自验证（R3，审查要求 9-6）** | T13–T17 在**真实 SQLite** 与**真实 PostgreSQL**（`EXPLAINLAB_PG_TEST_URL`，实例 `127.0.0.1:55432`）**各跑一遍，同断言**；两边预检 SQL 为**同一 SQLAlchemy 表达式**（无方言分支）；两边异常类型与稳定错误码一致；**不得用 SQLite 结果冒充 PG** |
| **T19** | **拒绝后全表逐列零变化（R3，审查要求 9-7）** | 对 T15/T16/T17 每种拒绝情形，比对**全部链接行的全部列**（含 `normalized_link_key`/`link_normalization_version`/`target_id`/`resolution`/`cross_space`/`updated_at`）+ **全部 `knowledge_item` 行的全部列** + 三 Hash（含**固定非空 payload** 的 `review_payload_hash`）+ 导出文本字节 → **全部逐项相等**；`knowledge_version`/`KnowledgeRelation` 行数不变 |
| **T20** | **守卫边界、豁免与预检次数（R3 新增；**R3.1 修订 ③**）** | ① **治理列写入豁免**：不同构窗口内执行 D12 删除降级（只改 `target_id/resolution/cross_space`）→ **成功**，`DELETE /knowledge/{id}` 不被 409 阻断；② **删除行不破坏同构**：删掉部分行后剩余行仍同构，后续写入按剩余版本判定；③ **【R3.1 断言修订，非删除测试】预检次数 == 受守卫写入次数**：同一事务内连续创建 5 条链接 → DISTINCT 查询计数 **== 5**（事件监听断言）。~~R3 原期望值 `== 1`~~ 编码的是**已被撤回的「事务内缓存」方案**（§8.4.3（1）（6）），在新设计下属**错误规格**；修订后断言**更强**（要求每次都查）。**权威断言另见新增 T34**；④ **rollback 后重新预检**：事务回滚后新事务再次写入 → 重新执行预检（**无缓存 ⇒ 结构上不可能沿用旧结论**；生命周期专项见 T33）；⑤ 恢复同构后写入正常 |
| **T21** | **重建执行入口的漂移门禁（DB，R3 新增，§8.3.5）** | ① **门禁 A**：产出 plan 后、apply 前手工把某行版本改成异值（或插入一行新版本）→ apply **拒绝**（`refused_version_drift`）且**零写入**；② **门禁 B**：手工删掉 plan 中一条 update（模拟部分计划）→ apply **拒绝**（`refused_incomplete_plan`）且零写入；③ 手工构造含重复 `(source_id,new_key)` 的 plan → apply **拒绝**；④ 正常 plan → 单事务全量更新成功，写后复核全表同构 + 无重复键。**R3.1 说明**：本条只覆盖 A/B；**「版本集合不变但行内容/行集合已变」的过期情形由门禁 C 覆盖，见 T22–T40**（A/B 对这些情形**看不见**，§8.3.6 反例表） |

**明确不做**：❌ 不引入混合版本的部分重建；❌ 不做「碰撞行合并 + 保留首现字面」（会丢 `target_id`）；❌ 不做「碰撞行降级 ambiguous 后继续写入其余行」（部分更新 + 版本混合，无法证明同步/查询/唯一/回滚均正确）；❌ 不靠 DB `IntegrityError` 兜底代替写前预检；❌ **R3：不用「按源条目局部检查」冒充全局同构守卫**（`all([]) == True` 漏洞，T16 反证）；❌ **R3：不为版本预检新增索引/迁移/端口方法**；❌ **R3：不宣称数据库预检提供跨进程严格互斥**（仍须静默期/单写者运维限制）；❌ **R3.1：不用「只比较计划中已存在的行」冒充新鲜度校验**（必须双向覆盖全表，T24/T25/T28/T37 反证）；❌ **R3.1：不允许「忽略不一致行后继续执行」或任何部分更新分支**（T30 零写入反证）；❌ **R3.1：不允许拒绝后重试同一份旧计划**（必须 `requires_replan` → 重新读全表重生成，§8.4.7 步 3c）；❌ **R3.1：不新增确定性计划摘要 / 不使用 Python 内置 `hash()` / 不改三 Hash 契约 / 不新增数据库字段**（§8.3.8）；❌ **R3.1：不引入任何版本集合缓存**（§8.4.3（3））；❌ **R3.1：本轮不用 `SELECT … FOR UPDATE` / 表锁 / advisory lock 关闭残余窗口**（§8.4.8 第 2 条，**【待审批】**）。

### 7.5.1 门禁 C 与事务生命周期专项矩阵（**R3.1 新增 T22–T40，全部【待验证】**）

> **诚实性声明（强制）**：本节 **19 条全部为「计划中的测试」，本轮 Design Only 未编写任何测试文件、未运行任何测试**。每条状态一律 **【待验证】**，**不得写成 PASS、不得写成「已覆盖」、不得计入任何通过率**。编号 **紧接 T21 之后追加**，**不覆盖、不删除、不改号**既有 T1–T21（T20③ 为期望值修订，已单独标注）。
> **三层覆盖口径**：标注 **Core** 的断言在 `InMemoryLinkRepository` + 纯函数层验证判定规则；标注 **DB** 的断言必须在**真实 SQLite 与真实 PostgreSQL**（`EXPLAINLAB_PG_TEST_URL`，实例 `127.0.0.1:55432`）**各跑一遍、同断言**，不得用 SQLite 结果冒充 PG。
> **通用夹具**：`plan()` 产出 `ready` 计划后，用**直接 SQL/ORM 改列**或**真实仓库调用**制造「plan 之后数据库已变」的状态，再调 `apply_link_key_plan(plan, session)`；拒绝路径一律断言 **稳定状态码 + `requires_replan=True` + `stale_reasons` 内容 + 零写入**。

| # | 用例（对应用户 §六 的 13 项 + 6 项配套） | 断言 | 层 | 状态 |
|---|---|---|---|---|
| **T22** | **① plan 后 `target_title` 被改 → 拒绝** | 改某行 `target_title`（**治理列豁免写入，全局守卫不拦、版本集合不变 ⇒ 门禁 A 通过**）→ apply **`refused_stale_plan`**，`stale_reasons` 含 `reason_code=target_title_changed` + 该 `link_id` + `field=target_title` + `expected`（计划快照原值）/`actual`（当前值）；**零写入**；**同时断言门禁 A 确实放行**（证明 A 不足以发现此漂移） | Core + DB | **【待验证】** |
| **T23** | **② plan 后 `alias` 被改 → 拒绝** | 同 T22，字段换 `alias`（含 `None → ""`、`"" → None`、`"A" → "a"`、`"A" → " A "` 四种）→ **一律拒绝**（`alias_changed`）；**断言比对前不做 NFKC/casefold/空白折叠**（规范化后相等但原值不等 ⇒ 仍拒绝，保守口径）；零写入 | Core + DB | **【待验证】** |
| **T24** | **③ plan 后新增链接行 → 拒绝** | 插入一条**新链接行**（版本与全表同构 ⇒ **门禁 A 通过**；计划自身未变 ⇒ **门禁 B 的「计划内部覆盖」也通过**）→ apply **`refused_stale_plan`**，`reason_code=row_added`（新行不在 `row_snapshots` 中）+ `row_not_covered`；**零写入**；**断言新行原样保留、未被更新也未被删除** | Core + DB | **【待验证】** |
| **T25** | **④ plan 后删除链接行 → 拒绝** | 删掉计划中**某条 update 对应的行** → `refused_stale_plan` + `row_deleted`；另删掉**某条 no-op 行**（不在 `updates` 中）→ **同样拒绝**（证明快照覆盖全表而非只覆盖 updates）；**零写入**；断言其余行逐列不变 | Core + DB | **【待验证】** |
| **T26** | **⑤ plan 后 `normalized_link_key` 被改 → 拒绝** | 直接改某行键为另一字符串（版本不变 ⇒ A 通过）→ `refused_stale_plan` + `key_changed`；**另测「改成恰好等于计划 `new_key`」的情形**：此时 `old_key` 快照不符 ⇒ **仍拒绝**（不得因「结果看起来对」而放行）；零写入 | Core + DB | **【待验证】** |
| **T27** | **⑥ plan 后 `link_normalization_version` 被改 → 拒绝** | 改某行版本为异值 → **门禁 A 先拒**（`refused_version_drift`，状态优先级 A→B→C）；**另构造「A 看不见但 C 看得见」的版本变化**：把**全部行**版本统一改成另一个单一值 N'（集合仍同构但 ≠ `plan.source_version` ⇒ A 拒）；以及**计划内 `new_version` 与规则注册表不符** → `unsupported_target_version`；零写入 | Core + DB | **【待验证】** |
| **T28** | **⑦ 计划覆盖不完整 → 拒绝** | 三种构造：① `row_snapshots` 缺行（少于当前全表）；② `source_version ≠ target_version` 但 `updates` 未覆盖全部需变更行；③ `updates` 含**不在 `row_snapshots` 中**的 `link_id`（`update_row_not_in_plan`）→ 分别 **`refused_incomplete_plan`（①②）/ `refused_stale_plan`（③）**；**零写入**；断言 `observed_row_count` 与当前行数不符也被发现 | Core + DB | **【待验证】** |
| **T29** | **⑧ 计划内重复 `link_id` → 拒绝** | ① `row_snapshots` 中同一 `link_id` 出现两次；② `updates` 中同一 `link_id` 出现两次（即使 `new_key` 相同）→ **`refused_stale_plan` + `duplicate_link_id_in_plan`**（**归 C 而非 B**，§8.3.7 状态优先级）；零写入；**另断言 `(source_id,new_key)` 重复归 B（`refused_incomplete_plan`）**，两类不混淆 | Core + DB | **【待验证】** |
| **T30** | **⑨ 拒绝后全表逐列快照完全不变（DB，最强零写入断言）** | 对 **T22–T29 每一种拒绝情形**，比对：**全部 `knowledge_link` 行的全部列**（含 `normalized_link_key`/`link_normalization_version`/`target_id`/`target_title`/`alias`/`resolution`/`cross_space`/`created_at`/**`updated_at`**）+ **全部 `knowledge_item` 行的全部列** + `document_content_hash` + `document_payload_hash` + **固定非空 payload** 的 `review_payload_hash` + **导出文本字节** + `knowledge_version`/`KnowledgeRelation` 行数 → **全部逐项相等**；并断言 **`updated=0`、`unchanged=observed_row_count`**、**报告不含任何「已跳过行」清单**（证明无部分更新分支） | DB（双方言） | **【待验证】** |
| **T31** | **⑩ 真实 PostgreSQL 与 SQLite 分别执行关键过期计划测试** | T22–T30 在**真实 SQLite** 与**真实 PG**（`EXPLAINLAB_PG_TEST_URL`）**各跑一遍、同断言**；两边**重读 SQL 为同一 SQLAlchemy 表达式（零方言分支）**；两边稳定状态码与 `reason_code` 集合一致；两边 `IntegrityError`/唯一约束行为一致；**PG 未连接时整模块 skip 并如实报告，不得用 SQLite 结果冒充 PG，不得虚报 PG 连接成功** | DB（双方言） | **【待验证】** |
| **T32** | **⑪ commit 后新事务必须重新版本预检（DB）** | 同一 Session：事务 T1 内受守卫写入（记录 DISTINCT 查询计数 n1）→ `session.commit()` → **另一连接/进程把全表改成异版本或插入异版本行并提交** → 同一 Session 再次受守卫写入（autobegin T2）→ 断言：① **T2 内确实重新执行了 DISTINCT**（计数增加，**不是复用 T1 结论**）；② **本次写入被拒绝**（`LinkNormalizationVersionMismatch` / 409）且零写入；③ 断言 **Session 对象自始至终是同一个**（证明「Session 存在」不能作为缓存有效依据） | DB（双方言） | **【待验证】** |
| **T33** | **⑫ rollback 后新事务必须重新版本预检（DB）** | 同一 Session：T1 内写入 → `session.rollback()` → 期间外部提交版本变化 → 同一 Session 再次写入（autobegin T2）→ 断言 **重新预检 + 据当前真实状态判定**（该拒则拒、该通则通）；**另测「rollback 撤销了 T1 自己的写入」**：T1 插入 v2 行后 rollback，T2 预检读到的集合**不含被撤销的行**；零缓存复用 | DB（双方言） | **【待验证】** |
| **T34** | **⑬ 同一事务内多次写入的预检行为 == 最终策略（无缓存）（DB，权威断言）** | 用 SQLAlchemy 事件监听统计 `SELECT DISTINCT link_normalization_version` 执行次数：① 同一事务内 **k 次受守卫写入 → 计数 == k**（k=1/5/20 三组）；② **治理列-only 更新与删除 → 计数增加 0**（豁免不预检）；③ **`apply_link_key_plan` 批量更新 L 行 → 门禁 A 预检计数 == 1**（不逐行预检），另有 1 次 6 列重读 + 1 次写后复核；④ **断言仓库实例上不存在任何版本集合缓存属性**（结构守护）；⑤ Core `InMemoryLinkRepository` 同口径计数一致 | DB（双方言）+ Core | **【待验证】** |
| **T35** | **配套：plan 后 `source_id` 被改 → 拒绝** | 把某行 `source_item_id` 改成另一条目（**版本集合不变 ⇒ A 通过**）→ `refused_stale_plan` + `source_id_changed`；**另断言键空间归属变化被识别**：原 source 下少一行、新 source 下多一行，**双向覆盖都不成立**；零写入；两个 source 的 `knowledge_item` 全列不变 | Core + DB | **【待验证】** |
| **T36** | **配套：计划内容被篡改 → 拒绝（新键重算，§8.3.8 机制④）** | ① 改 `updates[i].new_key` 为**任意其它字符串**（快照未含 `new_key`，故字段比对看不见）→ **每行新键重算**发现 `expected_new_key ≠ new_key` → `refused_stale_plan` + `new_key_mismatch`；② 改 `new_version` 为规则注册表**存在但非目标**的版本 → `new_version_mismatch`；③ 改成注册表**不存在**的版本 → `unsupported_target_version`；④ **交换两条 update 的 `new_key`**（集合相同、逐行不同）→ **仍拒绝**（证明不是只比对集合）；⑤ 篡改 `plan.status`/`target_version`/`source_version` → `plan_not_ready` 或对应拒绝；**全部零写入** | Core + DB | **【待验证】** |
| **T37** | **★ 配套：no-op 行盲区（本轮关键漏洞反证）** | 构造「`source_version == target_version` 但某行键与新规则算出的键不一致」或「no-op 行的 `target_title`/`alias` 在 plan 后被改」：① 断言 **R3 的「只比对 `updates`」方案确实发现不了**（反证盲区真实存在，非假想）；② **R3.1 方案拒绝**：`row_snapshots` 覆盖该行 + **对 no-op 行也重算 `expected_new_key`** → `noop_row_requires_update` / `target_title_changed` / `alias_changed`；③ 零写入；④ **正常 no-op 行（键已等于重算值且快照一致）不得被误拒**（幂等重跑 T9 仍 `updated=0`） | Core + DB | **【待验证】** |
| **T38** | **配套：计划不可变性与确定性序列化（§8.3.8）** | ① `LinkRebuildPlan` / `LinkRowState` / `LinkRebuildUpdate` 均为 **frozen Pydantic 模型**：任何字段赋值抛异常（`ValidationError`/`TypeError`）；② 集合字段为 **`tuple` 而非 `list`**（`isinstance` 断言 + 尝试 `.append` 失败）；③ **apply 前后 `plan.model_dump(mode="json")` 的 JSON 字节完全相同**（证明 apply 不修改计划）；④ 同一输入两次 `plan()` 的 `model_dump` 字节相同（**确定性序列化**，排序稳定）；⑤ **断言模型中不存在任何摘要/digest 字段**，且**不使用内置 `hash()`**（源码守护）；⑥ **三 Hash 与 `canonicalization_version` 不变**、计划摘要**不出现在导出载荷/白名单** | Core | **【待验证】** |
| **T39** | **配套：十步执行顺序与写后非键列复核（DB）** | ① **顺序守护**：用事件/调用序列断言 apply 内实际顺序为 **开事务 → A 预检 → 6 列重读 → B → C（含重算）→ 新键唯一性再验证 → 批量 UPDATE → 写后复核 → 提交**；任一门禁失败时**其后步骤一律不执行**（尤其**不得出现任何 UPDATE 语句**）；② **写后复核**：成功后全表版本 == `target_version`、无重复 `(source_id,key)`，且**非键列（`target_id`/`target_title`/`alias`/`resolution`/`cross_space`/`created_at`）与第 3 步重读值逐列相等**（不是与 plan 生成时刻值比）；③ **故障注入**：在第 N 行 UPDATE 后注入异常 / 故意触发 `IntegrityError` → **整体回滚**，全表逐列快照与 apply 前完全一致；④ **事务所有权**：传入**已有活动事务**的 Session → 按约定拒绝/报错，**不得静默加入外部事务**；⑤ `knowledge_item` 全列 + 三 Hash + 导出字节不变 | DB（双方言） | **【待验证】** |
| **T40** | **配套：savepoint / nested transaction 边界（DB）** | ① `session.begin_nested()` 内受守卫写入 → **照常重新预检**（计数增加）；② savepoint 内插入异版本行后 `nested.rollback()` → 下一次写入预检**读到回滚后的真实集合**并据此判定；③ `nested.commit()`（RELEASE SAVEPOINT）**不结束外层事务**，外层后续写入仍重新预检；④ **`apply_link_key_plan` 不得在 savepoint 内调用**（按 §8.4.3（4）约定拒绝/报错），避免「以为整体回滚、实际只回滚到 savepoint」；⑤ 断言 **Session 生命周期内事务身份确实变化**（commit/rollback 后 autobegin），**仓库不主动 commit/rollback/begin_nested** | DB（双方言） | **【待验证】** |

**T22–T40 与用户 §六 13 项的对应关系（逐项可核对）**：①→T22 ②→T23 ③→T24 ④→T25 ⑤→T26 ⑥→T27 ⑦→T28 ⑧→T29 ⑨→T30 ⑩→T31 ⑪→T32 ⑫→T33 ⑬→T34。**13 项全部覆盖，无遗漏**；T35–T40 为落实 §二「10 类情况」与 §五「savepoint 边界」所必需的**配套追加**（`source_id` 变化、篡改检测、no-op 盲区、不可变性、十步顺序、nested 边界），**不扩大本轮实现范围，只是把已要求的规则测全**。

**明确不做（R3.1 追加）**：❌ 不新增测试文件之外的实现代码（本轮 Design Only，**T22–T40 尚未编写**）；❌ 不宣称任何一条已运行通过；❌ 不为让测试通过而弱化 T1–T21 的既有断言；❌ 不用 Core 层判定测试冒充 DB 层零写入验证；❌ 不在 PG 未连接时把 skip 写成 pass。

### 7.6 Frontmatter 提示聚合与**导入绑定空间语义**专项矩阵（第一轮审查·问题 B + 第二轮审查·意见二）

| # | 用例 | 断言 |
|---|---|---|
| **H1** | **重复提示**（同 title、同 target_id 出现 2 次） | 恢复绑定该 target；**只建一行**（行身份由正文键决定）；无重复关系；不因重复提示报错 |
| **H2** | **同 title 不同 alias 的多提示、同 target** | 归入同一标题键组 → 恢复；正文若含 `[[B|别名1]]`+`[[B|别名2]]` → **两行都绑定 B** |
| **H3** | **矛盾提示**（同 title、两个**不同且都存在**的 target_id） | `resolution=conflict`、`target_id=None`；warning **含两个 target_id 及各自原始 title/alias**；报告 `conflicts` 留痕；**不随机选、不取首/末条** |
| **H4** | **矛盾提示顺序无关** | 把 `links[]` 顺序颠倒/全排列打乱 → 绑定结果、resolution、warning 集合**完全一致**（证明无 last-write-wins） |
| **H5** | **无效 UUID**（`target_id: "not-a-uuid"` / 空串 / 数字） | 归 `invalid_hints(malformed_uuid)` + warning（保留原始文本）；该组无其它有效提示 → **回退标题解析**；不抛未处理异常 |
| **H6** | **目标不存在**（合法 UUID 但本实例无此条目，模拟跨实例） | 归 `invalid_hints(target_not_found)` + warning + `unresolved_links`；回退标题解析；**不判 conflict**（§6.5「无效≠矛盾」口径） |
| **H7** | **有效 + 无效混合** | 按唯一有效 target 恢复；无效提示**仍逐条 warning**，不被静默忽略 |
| **H8** | **三方矛盾** | 3 个互不相同的有效 target → conflict，warning 含**全部三个** |
| **H9** | **孤儿提示**（frontmatter 有、正文无） | **不建行** + warning + 报告 `orphan_hints`（D4） |
| **H10** | **提示缺 target_id**（只有 title/alias/resolution） | 归 `invalid_hints(no_target_id)`；回退标题解析；不建行凭提示 |
| **H11** | **空提示列表** | 全部走标题解析，行为与无 frontmatter links 一致 |
| **H12** | **三 Hash 不受提示聚合影响** | 恢复前后 `document_content_hash` 不变（正文未改）；`review_payload_hash`（固定非空 payload）不变；导出白名单子字段不含派生键 |
| **H13** | **同空间 UUID 恢复（R3，审查要求 1）** | source 与 target 同 `space_id`（含**双方都为 `None`**）→ `resolution=resolved`、**`cross_space=False`**；无 `cross_space_binding_restored` warning；DB 列真实为 `resolved`/`0`（双方言） |
| **H14** | **★ 跨空间 UUID 恢复（R3，审查要求 3/4）** | source `"p1"`、target `"p2"`，提示 UUID 有效且目标存在 → **恢复绑定**（`target_id` == 该 UUID）、**`resolution=cross_space`**、**`cross_space=True`** + warning 含双方 space_id/target_id/原始 title/alias；**断言绝不出现 `resolved` + `cross_space=False`**；**对照 J**：同一对条目在无提示时自动解析必为 `missing`（证明跨空间绑定只来自历史 UUID 意图） |
| **H15** | **源无空间、目标有空间（R3，审查要求测试 3）** | source `space_id=None`、target `"p1"` → **`cross_space=True` + `resolution=cross_space`**（`None` 与任何非 `None` 视为不同空间）；**不得**因「个人总知识库能看到全部条目」而误判同空间 |
| **H16** | **源有空间、目标无空间（R3 补充，反向）** | source `"p1"`、target `None` → **`cross_space=True` + `resolution=cross_space`**（反向亦然，判定对称） |
| **H17** | **目标 archived 但 UUID 有效（R3，审查要求 6）** | 恢复绑定成功（**不拒绝、不降级 missing**）；`resolution`/`cross_space` **只由空间关系决定**（同空间 archived → `resolved`+False；跨空间 archived → `cross_space`+True）+ `archived_target_restored` warning；随后**真实 HTTP PATCH** 连续保存 → 绑定保留、不被自动解绑（与 D7/L④ 一致；**HTTP 侧验证「保留」，建立由 Core 夹具完成**，§6.7） |
| **H18** | **目标不存在（R3，审查要求测试 5）** | 合法 UUID 但本实例无此条目 → `invalid_hints(target_not_found)` + warning + `unresolved_links` + **回退标题解析**；**不判 conflict、不判 cross_space、不建跨空间绑定**；与 H5（UUID 非法）语义分离且各自 warning 码不同 |
| **H19** | **★ 恢复结果与 `links[]` 顺序无关（R3，审查要求测试 6）** | 把含**同空间 + 跨空间 + archived + 无效 UUID + 不存在目标 + 矛盾提示**的混合 `links[]` 做**颠倒与多组打乱** → 每行的 `target_id`/`resolution`/`cross_space` 与 **warning 集合**完全一致（证明空间判定与聚合判定都不依赖书写顺序） |
| **H20** | **再导出 Hash 口径（R3，诚实断言两种情形）** | ① **同空间布局往返**：导入恢复后再导出 → `document_payload_hash` 与源文件**逐位相同**、`document_content_hash` 相同、导出字节相同（resolution 未变）；② **跨空间布局导入**：源文件 `links[].resolution=resolved` 但本实例目标在另一空间 → 恢复为 `cross_space` → 再导出 **`document_payload_hash` 相对源文件变化（预期，如实断言）**、**`document_content_hash` 不变**；③ 两种情形导出 `links[]` **只含白名单四子字段**，**不含 `cross_space`/派生键**；④ **固定非空 payload** 的 `review_payload_hash` 两种情形均不变 |

> **H13–H20 三层覆盖口径（审查要求「SQLite、PG 和 Core 三层验证适用的部分均应覆盖」）**：**Core 层**验证判定逻辑（空间等值、resolution/cross_space 重算、warning 码、顺序无关、服务层一致性断言）；**真实 SQLite 与真实 PG** 验证**数据库列真实落值**（`resolution` 字符串、`cross_space` 布尔往返）、恢复后经真实 HTTP 保存的保留行为、以及 H20 的导出字节与三 Hash。**纯判定类断言（如 warning 文案集合）在 Core 层验证即可，不要求在 DB 层重复**；凡涉及**持久化列值/事务/HTTP** 的断言**必须**双方言各跑一遍。

### 7.7 回归与守护

- 独立性守护子进程追加导入 `markdown.links`、`markdown.link_service`；零新增依赖白名单守护继续通过。
- 6 个新 ABC 不可实例化（加入 `SERVICES` 参数化）。
- **A1-02 六个冻结文件指纹不变**（§1.3）+ 其 293 个用例全通过；`markdown/__init__.py` 追加后 A1-02 公共 API 行为不变。
- **D3 守护**：`LinkRepository.delete_links_of_item` 签名与 A1-01 一致（只允许 docstring 变化）。**R3 扩展**：断言 `LinkRepository` 的**方法名集合恰好为 A1-01 的 10 个**（不得新增端口方法），且每个方法的参数名/顺序/注解/返回注解不变。
- **D10 守护**：Core 链接模块零文件系统写入（T12）。**R3 扩展**：`LinkKeyRebuild.plan()` 零数据库写入（T12 行为守护②）。
- **D1 守护**：`CANONICALIZATION_VERSION` 全程保持 `1`；导出 `links[]` 子字段白名单恒为 `target_id/title/alias/resolution`。
- **D8 守护（R3 新增）**：新增 router 的**方法 + 路径集合恰好等于 3 个 GET**，出现任何写方法即失败；`knowledge.py` 既有端点方法/路径/状态码集合未变（§6.7）。
- **R3 空间一致性守护**：服务层断言 `cross_space=True ⟺ resolution=cross_space`（实体校验器不覆盖这条）；断言自动解析候选**全部**满足 `candidate.space_id == item.space_id`（§2.5⚠）。
- **R3 守卫规则单一来源守护**：backend 仓库与 Core 测试替身**调用同一个** `check_global_version_homogeneity()`；断言不存在第二份规则实现（避免两边口径漂移）。
- **R3.1 新鲜度规则单一来源守护**：backend `apply_link_key_plan()` 与 Core 测试替身**调用同一个** `check_plan_freshness()`；断言 backend **没有自己另写一份逐行比对逻辑**（避免口径漂移）；断言该函数**无 IO、无 Session/端口参数、无模块级可变状态**（纯函数守护）。
- **R3.1 无缓存守护**：断言 `SQLAlchemyLinkRepository` / `InMemoryLinkRepository` **不存在任何版本集合缓存属性**（无 `_version_cache`/`lru_cache`/模块级字典/ContextVar）；断言受守卫写入路径**每次都执行单列 DISTINCT**（T34 查询计数）。
- **R3.1 计划不可变守护**：`LinkRebuildPlan`/`LinkRowState`/`LinkRebuildUpdate` 为 frozen + `tuple` 字段；**不存在摘要/digest 字段**；链接模块源码**不出现内置 `hash(`**（T38）。
- **R3.1 事务所有权守护**：`apply_link_key_plan` 内**只有一处** `session.begin()`；仓库实现内**不出现** `commit()`/`rollback()`/`begin_nested()`（与既有仓库只 `flush()` 的实测一致）。
- **R3.1 Hash 契约守护（延续 D1）**：`CANONICALIZATION_VERSION` 仍为 `1`；三 Hash 计算路径与导出白名单**零改动**；计划/快照/新鲜度结果**不进入任何交换载荷**。
- **V1 全量回归**：检索（SQLite FTS5 + PG tsvector）、审核、关系、版本、图、实验、前端既有功能。
- 命令：`uv run ruff check`（**禁 format**）、`uv run pytest -o addopts="--import-mode=importlib"`（默认 SQLite）、加 `EXPLAINLAB_PG_TEST_URL` 再跑一遍（真实 PG）。
- 基线对照：A1-02 后为 **SQLite 644 passed / 41 skipped**、**PG 685 passed / 0 skipped**；A1-03 后两者必须**只增不减**，skipped 在 PG 跑时仍为 0。

### 7.8 预估规模

纯文本层 ~95（含提示聚合分组）、服务层（场景 A–M + T1–T21 + H1–H20 + **T22–T40 的 Core 层部分**）~235、SQLite ~115、PG ~115、守护 +23 → **约 580 个新用例**（R1 估 ~310、R2 估 ~420、R3 估 ~520；**R3.1 因门禁 C 与事务生命周期专项 T22–T40（19 个编号、多子断言与参数化）+ 5 条新守护**而上调约 60）。**实施时以实际收集数为准，不虚报**；未真实运行的一律标「未验证」。**本轮（R3.1）未运行任何测试、未编写任何测试文件，以上全部为估算；T22–T40 全部为【待验证】。**

---

## 8. 数据模型、迁移与回滚

### 8.1 数据模型：完全复用 0006，**零新迁移**

`knowledge_link` 已具备 A1-03 所需全部列与约束（§2.3 实测）。逐项核对：

| A1-03 需要 | 0006 现状 | 是否需改 |
|---|---|---|
| 行身份键非空 + 同源唯一 | `String(1024) NOT NULL` + `uq_link_source_key` | ❌ 不需要 |
| 规则版本 | `link_normalization_version Integer NOT NULL default 1` | ❌ |
| 稳定绑定 + 删除降级 | `target_item_id` FK **SET NULL** | ❌ |
| 源删除清理 | `source_item_id` FK **CASCADE** | ❌ |
| 反链查询索引 | `ix_knowledge_link_target_item_id` | ❌ |
| 键查询/重建索引 | `ix_knowledge_link_normalized_link_key` | ❌ |
| 原始字面保留 | `target_title(500) NOT NULL`、`alias(500) NULL` | ❌ |
| 解析状态 / 跨空间 | `resolution(20)`、`cross_space Boolean` | ❌ |

**历史数据回填**：`knowledge_link` 是 0006 **新建表**，V1 无链接数据 → **无需回填**（§2.9 所述「回填按当前版本计算键」在本仓库为空操作，验收报告须如实说明这一点，不宣称做了回填）。

**「删除保留快照」的口径（D9 已裁决）**：快照 = **用户书写的 `target_title` 原始字面**（本就不随目标改名而变），**不新增「绑定时目标标题」数据库列**。因此**不需要 0007 迁移**，本轮不提议、不实施任何新列。

### 8.2 Schema 回滚

沿用 0006 既有 downgrade（已真实 SQLite + PG 验证）：删索引 → 删 `knowledge_link` 等 V2 表 → 删 `knowledge_item` 4 列。**属 Schema Rollback，丢 V2 数据非无损**（§2.9 口径），破坏性 downgrade 仍须走运维包装器门禁（备份+校验+确认+留痕），该包装器属 A1-T14，**不在 A1-03**。

### 8.3 规范化版本升级与键重建（`LinkKeyRebuild`）—— R2 按审查意见「问题 A」重写

#### 8.3.1 R1 稿的逻辑矛盾（原问题，必须先讲清楚）

R1 稿同时承诺了四件事：① 同源 `normalized_link_key` 唯一；② 碰撞行**全部保留**；③ 原有 `target_id` **全部保留**；④ 两行写入**相同的新键**。

**这四条在 `UNIQUE(source_item_id, normalized_link_key)` 下不可能同时成立**：④ 要求两行键相同，① 要求同源键唯一 → 两行必须合并成一行；而一行只有**一个** `target_item_id` 列 → 合并必然丢掉另一个 `target_id`，违反 ③；若坚持保留两行（②），则违反 ①，DB 直接抛 `IntegrityError`。**这是逻辑矛盾，不是实现难度问题**，靠「合并保留首现字面」或「降级 ambiguous 后继续写」都无法自洽（前者丢绑定，后者产生部分更新 + 混合版本）。

#### 8.3.2 修订方案：写前全量预检 + 有碰撞则整体拒绝（零写入）—— R2 提出，**R3 拆分为 Core `plan()` + backend `apply_link_key_plan()`**（§8.3.5）

```
# Core：只算计划，零写入、零文件 IO（R3，§8.3.5）
plan(target_version: int) -> LinkRebuildPlan:
  # 阶段 0：全表版本同构预检（重建专用门禁：单一版本，可 ≠ 代码常量，§8.4.4）
  rows = repo.list_all_links()                      # 只读
  versions = {r.link_normalization_version for r in rows}
  if len(versions) > 1:
      return LinkRebuildPlan(status="refused_mixed_version", updates=[], ...)   # 零写入
  source_version = versions.pop() if versions else target_version   # 空表 → 无需重建

  # 阶段 1：只读全量，计算完整新键映射（不写任何行）
  plan_entries = [(row, key_v(target_version, row.target_title, row.alias)) for row in rows]

  # 阶段 2：写前检测全部碰撞组（按 (source_id, new_key) 分组，跨 source 同键不算碰撞）
  groups = {(row.source_id, new_key): [entries...] for ...}
  collisions = [g for g in groups if len(g) >= 2]

  # 阶段 3：有碰撞 → 整体拒绝，零写入
  if collisions:
      return LinkRebuildPlan(
          status="refused_collision", source_version=..., target_version=...,
          updates=[], unchanged=len(rows),
          collision_groups=[LinkCollisionGroup(
              source_id=..., new_key=...,
              entries=[LinkCollisionEntry(link_id, old_key, new_key, old_version,
                                          target_id, target_title, alias) ...]) ...],
          warnings=[...])
      # ★ 全部原行、旧键、旧版本、原绑定原样保留；不合并、不覆盖、不删除、不重绑

  # 阶段 4：无碰撞 → 产出**覆盖全表**的可执行计划（Core 到此结束，不写库）
  updates = [LinkKeyUpdate(link_id, source_id, old_key, new_key,
                           old_version, new_version=target_version,
                           target_id, target_title, alias)
             for row, new_key in plan_entries
             if not (row.normalized_link_key == new_key
                     and row.link_normalization_version == target_version)]   # 幂等：跳过 no-op
  # ★ R3.1：快照必须覆盖**全表每一行（含 no-op 行）**，供 apply 阶段门禁 C 校验新鲜度（§8.3.6）
  row_snapshots = tuple(LinkRowState(link_id=r.id, source_id=r.source_id,
                                     normalized_link_key=r.normalized_link_key,
                                     link_normalization_version=r.link_normalization_version,
                                     target_title=r.target_title, alias=r.alias,
                                     target_id=r.target_id)          # target_id 携带但不参与比对
                        for r in rows)
  return LinkRebuildPlan(status="ready", source_version=..., target_version=...,
                         updates=updates, unchanged=len(rows) - len(updates),
                         row_snapshots=row_snapshots, observed_row_count=len(rows),
                         collision_groups=[], warnings=[...])

# backend：重建写入的唯一执行入口（R3 单事务；R3.1 增加门禁 C）
# ★ 完整十步顺序与伪代码见 §8.3.7（唯一权威版本，此处不重复以免两份漂移）：
#   1 开启事务 → 2 门禁 A（DISTINCT == {plan.source_version}，不要求等于常量）
#   → 3 重读当前全表 6 列 → 4 门禁 B（覆盖 100% + 新键无重复）
#   → 5 门禁 C（Core 纯函数 check_plan_freshness：双向覆盖 + link_id 唯一 + 6 字段精确比对
#              + 每行新键重算比对 + no-op 行校验）→ 6 新键唯一性再验
#   → 7 批量只写 3 列 → 8 写后复核 → 9 提交 → 10 任一失败整体回滚
#   拒绝状态：refused_version_drift(A) / refused_incomplete_plan(B) / refused_stale_plan(C、步 6)
#   所有拒绝一律**零写入**，且 requires_replan=True（必须重读全表重新生成计划）
```

**七条要求逐条对应（审查意见二·问题 A）**：

| 要求 | 落地 |
|---|---|
| 1 重建前计算完整新键映射 | 阶段 1：`list_all_links()` 全量 + 纯函数重算，**先算完再判**（阶段 0 先确认全表版本同构于单一值） |
| 2 写入前检测所有碰撞组 | 阶段 2：按 `(source_id, new_key)` 分组，**收集全部**碰撞组（不只第一个） |
| 3 有碰撞默认拒绝全量重建，事务不产生部分更新 | 阶段 3：`status=refused_collision`，**在产出任何 update 之前返回**；Core 全程零写入，backend 只在 `status=ready` 时才执行 → **零写入** |
| 4 结构化碰撞报告含 `link_id/旧键/新键/原版本/target_id` | `LinkCollisionEntry` 五字段齐全，另附 `source_id/target_title/alias` 便于人工处置 |
| 5 保留全部原始行、旧键、版本、绑定 | 零写入天然满足；测试 T2/T3/T4/T6 用**全表逐列快照**证明 |
| 6 等用户处理碰撞后重新执行 | 计划/报告交 backend 运维层落盘（D10）；用户改正文/改标题/显式裁决后重跑；**重跑仍是全量预检** |
| 7 不允许随机绑定、覆盖、静默删除 | 阶段 3 直接拒绝，代码路径中**不存在**选一个 target/合并行/删行的分支 |
| **R3 附加：不得部分应用计划** | backend 门禁 B：`source_version ≠ target_version` 时 `updates` **必须覆盖 100% 行**，否则 `refused_incomplete_plan` 零写入（T21） |
| **R3.1 附加：计划必须新鲜（门禁 C）** | backend 在**执行事务内重读当前全表 6 列**，交 Core 纯函数 `check_plan_freshness()` 做**双向覆盖 + `link_id` 唯一 + 6 字段精确比对 + 每行新键重算 + no-op 行校验**；任一不一致 → `refused_stale_plan` **零写入**、**禁止部分更新**、**禁止忽略不一致行继续**、`requires_replan=True`（§8.3.6 / T22–T40） |
| **R3.1 附加：plan 阶段检查 ≠ apply 阶段保证** | apply **独立重新执行 A/B/C**，不复用 plan 阶段结论；十步顺序见 §8.3.7 |

**不引入混合版本的部分重建**：本方案只有两种终态 —— **全表都到 `target_version`**（成功），或 **全表都保持原版本**（拒绝）。不存在「一部分行 v1、一部分行 v2」的中间态。理由与守卫见 §8.4。

**重建只写两个非交换列**：`normalized_link_key`、`link_normalization_version`（+ 行维护时间 `updated_at`）。**绝不重解析、绝不改 `resolution`**（重解析是 `LinkReresolve` 的显式动作）。这是 §5.2 问 7「交换身份不变」论证的前提，也是场景 F 的断言项。

> **⚠ 必须澄清的第三个列（R3 补充，否则 Hash 论证会被误读）**：这里写的 `updated_at` 是 **`knowledge_link` 行自己的维护时间**，**不是 `knowledge_item.updated_at`**。
> ① 交换载荷的 `timestamps` 取自**知识条目**（`KnowledgeItem.created_at/updated_at`），`links[]` 子对象的导出白名单只有 **`target_id/title/alias/resolution`**（R1），**不含链接行的 `created_at/updated_at/cross_space/normalized_link_key/link_normalization_version`**。因此写链接行的 `updated_at` **不进入任何交换字段**，`document_payload_hash` 不受影响。
> ② **重建绝不触碰 `knowledge_item` 的任何列**（包括 `updated_at`/`version`），否则 payload_hash 必然变化、且会误触发审核/索引同步。**这一点写成硬断言**：场景 F 与 T6/T19 除比对链接行外，**还须逐列比对受影响知识条目行在重建前后完全不变**。
> ③ 若实施中发现「链接行 `updated_at` 竟被某处导出」，那是**白名单被破坏**，属 R1 守卫失败，**必须修白名单而不是改 Hash 契约**。

#### 8.3.3 与设计原文的口径差异（如实报告，不擅自改设计文档）

设计 §2.4 / §2.9 原文写「重建产生的碰撞 → **ambiguous/conflict 报告**，不随机重绑定 → 校验唯一约束 → 旧版本键留痕」。按字面读，可能被理解为「把碰撞行写成 ambiguous/conflict 后继续重建其余行」。

**R2 采用用户本轮裁决的更严口径：碰撞 → 整体拒绝 + 零写入 + 报告**，不写任何 collision 行的 resolution。差异性质：

- **不涉及 Hash 契约变更**（`canonicalization_version` 不动，三 Hash 定义不动）。
- **不涉及数据模型/迁移契约变更**（不加列、不加表、不改约束）。
- 属对设计**未定义处**（碰撞时是否部分写入）的**口径收紧**，且**已由用户在本轮审查中明确裁决**，故不是擅自变更。
- **建议**：实施完成后另批同步设计 §2.4/§2.9 的措辞（把「碰撞→ambiguous/conflict 报告」明确为「碰撞→整体拒绝重建 + 结构化碰撞报告」）。**本轮不修改设计文档**（本轮只改计划文档）。

#### 8.3.4 回滚方案（无需新迁移、无需旧键列）

因为**原始字面永久保留**且规范化是纯函数，回滚 = **以旧版本号重跑同一流程**（R3 口径：`LinkKeyRebuild.plan(target_version=1)` 产出计划 → backend `apply_link_key_plan(plan, session)` 单事务原子执行），确定性恢复旧键旧版本，`target_id` 全保留。

**回滚同样受四重门禁约束（R3.1 增补门禁 C）**：① **碰撞拒绝**——若用户在 v2 期间编辑了正文/标题，使**旧规则下**出现同键碰撞，则 `plan()` 返回 `refused_collision`，回滚**整体拒绝 + 报告**，保持 v2 现状，**不做部分回滚**（测试 T10）；② **门禁 A 版本漂移**——执行前全表 `DISTINCT` 必须恰为 `{plan.source_version}`，否则 `refused_version_drift`（T21）；③ **门禁 B 计划完整性**——计划必须覆盖全部需变更行且新键无重复，否则 `refused_incomplete_plan`（T21）；④ **门禁 C 计划新鲜度（R3.1）**——apply 事务内重读当前全表 6 列，与 `plan.row_snapshots` 逐行逐项比对 + 每行新键重算，任一不一致 → `refused_stale_plan` **零写入**（§8.3.6 / T22–T40）。这一点必须向运维讲清楚：回滚不是无条件可用的「撤销键」，它和升级走**同一套正确性门禁与同一套十步执行顺序**（§8.3.5 / §8.3.7 / §8.4.4）。**回滚期间若有链接被增删或键字段被编辑，同样必须拒绝并要求重新生成回滚计划，不得忽略不一致行后继续。**

**留痕（D10 已裁决）**：`LinkKeyRebuild` **只返回结构化计划/报告对象**（Pydantic 模型，可 `model_dump(mode="json")`），**Core 不做任何文件系统写入，也不做任何数据库写入（R3，§8.3.5）**。报告落盘由 **backend 运维层** `persist_rebuild_report()` 负责，写 gitignore 的 `backend/data/ops/`（不入库）。报告即设计所说的「旧版本键留痕」载体：含每行 `old_key/old_version/new_key/new_version/target_id` 与全部碰撞组。
**本轮不提供** `python -m app.ops.rebuild_link_keys` CLI 与 `POST links/rebuild-keys` 端点（D8：属 A1-T11/A1-T14）；A1-03 只交付 Core 计划服务 + backend 批量执行入口与落盘助手，并由真实测试驱动验证。
**不新增迁移**（不加 `previous_link_key` 等列）：单事务 + 纯函数重算已可确定性回滚，新增列会引入第二份派生数据与一致性负担。

**重建期间失败**：单事务 → 整体回滚，无半套键（测试 T5 用**故障注入**真实验证，不只靠预检）。报告落盘失败不影响 DB 一致性（报告是旁路留痕，不是事务参与方）。

#### 8.3.5 重建写入的执行边界（R3 配套调整，全局守卫的必然结果）

**原问题（R2 稿）**：§8.3.2 阶段 4 让 **Core 逐行调用 `repo.update_link(row)`** 把版本从 N 改成 N+1。R3 引入**全局版本同构守卫**（§8.4：任何现存行版本 ≠ 代码常量 → 拒绝链接写入）后，这条路径**自相矛盾**：

- 升级场景：全表 v1、代码常量 v2。重建的第一行 `update_link` 就会被全局守卫拒绝（因为表里全是 v1 ≠ v2）→ **重建永远无法执行**，版本升级死锁。
- 若为重建给 `update_link` 开一个「绕过守卫」的开关，则**任何调用方都能用同一开关写出混合版本**（只改一部分行就 commit）→ 守卫形同虚设，正是审查要求杜绝的失效路径。
- 若给端口加一个批量方法或模式参数，则**改变 A1-01 端口契约**（本轮明令禁止）。

**R3 调整（必要配套，如实报告）**：把重建拆成**「Core 算计划」+「backend 原子执行」**两段：

| 段 | 归属 | 职责 | 门禁 |
|---|---|---|---|
| `LinkKeyRebuild.plan(target_version)` | **Core** | 只读全量 → 算新键 → 检测全部碰撞组 → 产出 `LinkRebuildPlan`（`ready` / `refused_collision` / `refused_mixed_version`）。**零数据库写入、零文件 IO**。**R3.1：计划必须携带覆盖全表每一行的只读快照 `row_snapshots`（含 no-op 行），供 apply 阶段做门禁 C 新鲜度校验（§8.3.6）** | 全表版本同构于**单一值**（可 ≠ 常量）+ 无碰撞 |
| `apply_link_key_plan(plan, session)` | **backend** | 在**单事务**内批量写入，**只写** `normalized_link_key`/`link_normalization_version`/`updated_at`（链接行自己的维护时间，**不碰 `knowledge_item`**）；返回 `LinkRebuildReport` | **门禁 A** 同事务重读全表 DISTINCT 版本 == `plan.source_version`；**门禁 B** 计划覆盖全表行 + 计划内 `link_id` 唯一 + 新键无重复；**门禁 C（R3.1 新增）逐行快照新鲜度校验 + 新键重算比对**（§8.3.6）；**写后复核**全表同构 + 唯一，失败整体回滚。**十步执行顺序见 §8.3.7** |

**为什么这样是正确的（可证明）**：

1. **常规写路径的守卫不被削弱**：`save_link`/`update_link`（改键或改版本）仍要求全表 == 常量，**没有任何绕过开关**。
2. **重建是「全表原子版本迁移」，不是常规链接写入**：它的门禁是「全表同构于单一版本」+「计划覆盖 100% 行」，因此**不可能提交出混合版本**——要么全表到 `target_version`，要么零写入（门禁拒绝或事务回滚）。
3. **不改端口契约**：`apply_link_key_plan()` 是 **backend 具体模块的函数**（不是 `LinkRepository` 的方法），`ports.py` 的 10 个方法签名零变化；Core 侧只新增**计划/快照/新鲜度结果模型**与 ABC 方法名（`plan()` 取代 R2 拟议的 `rebuild()`，该 ABC 尚未编写，故不构成契约破坏）。**R3.1 追加的 `LinkRowState` / `PlanFreshnessResult` / `check_plan_freshness()` 同样只是 Core 内部的值类型与纯函数，不新增任何端口方法**（§8.3.6 分层）。
4. **与 D10 同向**：D10 已裁决「Core 返回结构化报告、backend 负责持久化」；本调整把**重建写入**也归到 backend，Core 在该路径上**完全不碰存储**，独立性与 Nesti 可复用性更强。
5. **Hash 论证更强**：§5.2 问 7 的「只写 `normalized_link_key`/`link_normalization_version` 两个非交换列」不变（另加链接行自身的 `updated_at` 维护时间，同样不在导出白名单，且**绝不触碰 `knowledge_item`**），且 Core 侧连这些列都不写 → 交换身份不可能被 Core 重建逻辑改变。
6. **漂移防护（R3.1 加强）**：plan 与 apply 之间若有并发写入，**门禁 A/B 并不足够**——A 只看版本集合（改 `target_title`/`alias`/`normalized_link_key` 或增删行都不会改变版本集合），B 只看计划自身的覆盖与重复（**不与当前数据库比对**）。因此 R3.1 增加**门禁 C：在 apply 事务内重读当前全表必要字段，与计划快照逐行逐项比对**（§8.3.6），任何不一致 → `refused_stale_plan` + 零写入。**但这仍不是跨进程互斥**（§8.4.8）。
7. **plan 阶段的检查不构成 apply 阶段的安全保证（R3.1 明确）**：`plan()` 里的同构预检、碰撞检测、覆盖计算都是**生成时刻**的结论；数据库在其后可能已被其它请求/进程改变。**apply 必须独立重新验证 A/B/C，不得复用 plan 阶段的任何结论作为放行依据**（唯一可复用的是 plan 携带的**快照数据**，而它正是被校验的对象，不是校验的依据）。执行顺序见 §8.3.7。

**对测试分层的影响（如实说明，不降低覆盖）**：Core 层断言**计划内容与拒绝决策**（含碰撞组完整性、覆盖全表、幂等 no-op 跳过、**门禁 C 纯函数 `check_plan_freshness` 的十类判定**）；SQLite/PG 层断言**真实写入、逐列快照、门禁拒绝（含过期计划）、故障注入回滚**。T1–T21 的断言对象按此重新标注（§7.5 引言），**R3.1 在其后新增 T22–T40（§7.5.1），既有测试一律不覆盖、不删除**，正确性要求一条不减。

**契约变更判定**：**Hash 契约无变更、数据模型/迁移无变更、A1-01 端口签名无变更、V1 行为无变更**。属**实现职责分层调整**（Core↔backend 边界），由 R3 全局守卫的正确性要求直接推出。**E4 拆分已获独立审查批准**；R3.1 的门禁 C 为其**必须补充项**，同样不涉及任何契约变更（§8.3.6 / §8.3.8）。

> **R3.1 审查结论**：E4 的职责拆分**已获批准**，但必须补充**门禁 C（计划新鲜度）**。以下 §8.3.6 / §8.3.7 / §8.3.8 为 R3.1 新增，**不改变已批准的拆分本身**，只把「apply 阶段必须独立重新验证」落实为可执行、可测试的规则。

#### 8.3.6 门禁 C：逐行计划新鲜度校验（R3.1 新增，本轮唯一目标）

**原问题（R3 稿）**：R3 只有门禁 A（全表版本同构 + == `plan.source_version`）与门禁 B（计划覆盖全表 + 新键无重复）。**两者都不能发现「计划已过期」**：

| 并发变化 | 门禁 A 能否发现 | 门禁 B 能否发现 | 后果（若不加 C） |
|---|---|---|---|
| 某行 `target_title` 被改 | ❌ 版本集合不变 | ❌ 计划自身仍完整 | 按**旧标题**算出的 `new_key` 被写入 → 键与正文不一致，绑定优先同步后续失配 |
| 某行 `alias` 被改 | ❌ | ❌ | 同上（alias 参与键派生） |
| 某行 `normalized_link_key` 被改 | ❌ | ❌ | 计划记录的 `old_key` 与现实不符，覆盖/碰撞判断失效 |
| **新增**一条链接行 | ❌（同版本新行不改变版本集合） | ❌（B 只查计划内部，不查数据库） | 新行**不被重建** → 全表出现 v1/v2 混合，**直接破坏 §8.4 不变量** |
| **删除**一条链接行 | ❌（删除只缩小集合） | ❌ | 计划含已不存在的行 → 写入落空或报错，覆盖统计失真 |
| 计划被篡改（改 `new_key`） | ❌ | ❌（只要不产生重复） | **写入错误的键**，且 A/B 全绿 |

**结论**：必须增加**门禁 C**——在 **apply 的实际执行事务内重新读取当前数据库记录**，与计划快照**逐行逐项**比对。**只比较计划中已存在的行是不够的**：新增行、删除行、no-op 行的变化都必须能被发现。

**（1）计划必须携带的快照（Core 侧，`plan()` 生成时保留）**

新增值类型 `LinkRowState`（Core 纯值对象，Pydantic **frozen**，**同一个类型同时用作「计划快照」与「apply 时读到的当前行」**，避免两套字段定义漂移）：

| 字段 | 来源列 | 是否参与门禁 C 比对 | 说明 |
|---|---|---|---|
| `link_id` | `knowledge_link.id` | ✅ **身份键** | 用于建立计划↔当前行的双射 |
| `source_id` | `source_item_id` | ✅ | 情况 3 |
| `normalized_link_key` | 同名列 | ✅ | 情况 4（即 `old_key`） |
| `link_normalization_version` | 同名列 | ✅ | 情况 5（即 `old_version`） |
| `target_title` | 同名列 | ✅ | 情况 6，**用户书写原始字面** |
| `alias` | 同名列 | ✅ | 情况 7，**原样保留 NULL/空串区别** |
| `target_id` | `target_item_id` | ⛔ **不比对**（随快照携带） | 见下方「不比对字段的理由」 |

`LinkRebuildPlan` 在 R3 已有字段（`status` / `source_version` / `target_version` / `updates` / `unchanged` / `collision_groups` / `warnings`）之外，**R3.1 新增**：

- **`row_snapshots: tuple[LinkRowState, ...]`** —— **覆盖 `plan()` 读到的全表每一行，含 no-op 行**（这是发现「新增/删除/no-op 行变化」的前提；`updates` 因幂等跳过 no-op，**不能**充当全表清单）。
- `observed_row_count: int` —— 等于 `len(row_snapshots)`，冗余但便于报告与断言。
- `requires_replan: bool` —— 拒绝类报告置 True，明确「必须重读全表重新生成计划」。

**不比对字段的理由（必须写清，否则会被误当成漏检）**：`target_id` / `resolution` / `cross_space` / `created_at` / `updated_at` **不参与新鲜度判定**，因为 ① **重建根本不写这些列**；② **新键派生只依赖 `target_title`/`alias`/`target_version`**，与这些列无关；③ 治理路径（D12 降级、显式绑定）在窗口期内**合法地**修改它们（§8.4.3 豁免），若把它们纳入比对会**误拒合法并发**。
**但重建仍须证明自身没碰它们**：写后复核比对的是「**apply 事务内读到的值**」与「**写入后的值**」，而**不是**与 plan 时刻的值 —— 这样既不误拒治理并发，又能证明重建只写了 3 个列（T30/T39）。

**（2）比对规则（确定性、可证明）**

1. **按 `link_id` 建立双射**，不按列表顺序比对 → **顺序无关**。
2. **字符串按数据库存储原值精确比较**（Unicode 码点相等）：**比对前不做 NFKC/不 casefold/不折叠空白**（规范化只用于**派生新键**，不用于**判定是否变化**）；`None` 与 `""` **视为不同**（保守口径：宁可拒绝后重生成计划，也不引入「语义等价但字面不同」的判定分歧）。
3. **双向覆盖**：`set(plan.row_snapshots.link_id) == set(current.link_id)`，**两个方向都要查**（缺 → 删除/伪造；多 → 新增/未覆盖）。
4. **计划内 `link_id` 必须唯一**（`row_snapshots` 与 `updates` 各自都不得重复）。
5. **`updates` 的 `link_id` 必须是 `row_snapshots` 的子集**。
6. **新键重算比对（关键，覆盖「篡改」）**：对当前全表**每一行**用 **Core 同一个规范化纯函数**重算 `expected_new_key = normalized_link_key(target_version, target_title, alias)`：
   - 该行**在 `updates` 中** → 计划条目的 `new_key` 必须 == `expected_new_key`，`new_version` 必须 == `plan.target_version`，且 `old_key/old_version/source_id/target_title/alias` 必须与当前行逐项相等；
   - 该行**不在 `updates` 中**（no-op）→ 当前 `normalized_link_key` 必须 == `expected_new_key` **且** 当前 `link_normalization_version` 必须 == `target_version`；否则说明**计划漏掉了一条实际需要更新的行** → 拒绝。
7. **`target_version` 必须是 Core 规则注册表中存在的版本**（有对应规范化函数）；否则拒绝。**不要求 `target_version == 代码常量`**（否则回滚死锁，§8.4.4 已批准口径）；合法目标由运维协议决定（升级 = 新常量，回滚 = 旧版本）。

**（3）十类情况 → 稳定原因码（全部归入 `refused_stale_plan`）**

| # | 情况（审查列举） | 判定依据 | 稳定原因码 |
|---|---|---|---|
| 1 | 记录被删除 | 计划有该 `link_id`，当前全表无 | `row_deleted` |
| 2 | 新增了链接记录 | 当前全表有，计划快照无 | `row_added` |
| 3 | `source_id` 变化 | 逐项比对不等 | `source_id_changed` |
| 4 | `normalized_link_key` 变化 | 逐项比对不等 | `key_changed` |
| 5 | `link_normalization_version` 变化 | 逐项比对不等 | `version_changed` |
| 6 | `target_title` 变化 | 逐项比对不等（原值精确） | `target_title_changed` |
| 7 | `alias` 变化 | 逐项比对不等（含 NULL↔空串） | `alias_changed` |
| 8 | 数据库存在计划未覆盖的记录 | 双向覆盖失败 / no-op 行重算后仍需更新 | `row_not_covered` / `noop_row_requires_update` |
| 9 | 计划中出现重复 `link_id` | 计划自身唯一性 | `duplicate_link_id_in_plan` |
| 10 | 计划内容被意外修改或篡改 | 新键重算不一致 / `new_version` 不一致 / 快照与当前行不符 / 不可变模型被绕过 | `new_key_mismatch` / `new_version_mismatch` / 上述各项 |

**附加结构类拒绝（同属 C，零写入）**：`update_row_not_in_plan`（updates 含快照外 id）、`plan_not_ready`（`status != "ready"` 却调用 apply）、`unsupported_target_version`。

**（4）失败语义（强制，逐条对应审查要求）**

- **整个计划拒绝**，报告 `status = "refused_stale_plan"`（**稳定字符串**，与 `rebuilt` / `refused_collision` / `refused_mixed_version` / `refused_version_drift` / `refused_incomplete_plan` 并列）。
- **数据库零写入**：拒绝发生在**任何 UPDATE 之前**，不 `flush()` 任何重建变更；事务回滚/无变更提交 → **全表逐列快照完全不变**（T30）。
- **不允许部分更新**：不存在「跳过不一致行、继续更新其余行」的分支；代码路径中**没有** `continue`/`skip` 语义。
- **不允许自动忽略不一致行后继续执行**：不一致行**不降级、不重算后写入、不合并**，一律整体拒绝。
- **必须重新读取全表并重新生成计划**：报告置 `requires_replan=True`，并携带 `stale_reasons`（稳定原因码 + `link_id` + 字段名 + **计划值/当前值的脱敏摘要**）。运维处置 = **重跑 `plan()`**，**不得重试同一份旧计划**。
- **报告字段**：`stale_reasons: tuple[LinkStaleReason, ...]`（`reason_code` / `link_id` / `field` / `expected` / `actual`），`updated=0`，`unchanged=observed_row_count`。**不新增数据库字段**（报告只由 backend `persist_rebuild_report()` 落 gitignore 目录，D10）。
- **HTTP 口径**：A1-03 **无重建写端点（D8 保留）**，故 `refused_stale_plan` 是**报告状态**，**本轮不新增 HTTP 错误码映射**；常规链接写入路径的 `409 link_version_mismatch` 口径不变（§8.5.3）。未来 CLI/端点批次再决定其映射。

**（5）分层约束（与 §8.4.3 一致，不得破坏）**

- **Core 只提供纯函数**：`check_plan_freshness(plan, current_rows) -> PlanFreshnessResult`（输入是 plan 与 backend 读到的 `LinkRowState` 序列，**无 IO、无 Session、无 SQL**），内部调用**同一个**规范化纯函数重算新键。**判定规则单一事实来源**。
- **backend 只负责数据库查询与写入**：用**列选择**（`select(ORM.id, ORM.source_item_id, ORM.normalized_link_key, ORM.link_normalization_version, ORM.target_title, ORM.alias)`）重读全表 → 映射为 `LinkRowState` → 交 Core 纯函数判定 → 按结果执行或拒绝。**不构造全量 ORM 实体**（成本与 §8.4.3 同口径）。
- **`InMemoryLinkRepository` 测试替身调用同一纯函数** → Core 层也能真实验证拒绝语义（T22–T29 的纯判定部分），**DB 层验证真实零写入与逐列快照**。
- **不新增端口方法**：`check_plan_freshness` 是 Core 模块级纯函数，`apply_link_key_plan` 是 backend 模块级函数，**`LinkRepository` 的 10 个签名零变化**（D3 守护继续断言方法名集合）。

**（6）诚实限制**：门禁 C 把不一致窗口从「plan 生成 → apply 提交」**缩小到「apply 事务内重读 → 提交」**，但**不提供跨进程互斥**（§8.4.8）。在 PG READ COMMITTED 下，重读之后、提交之前若有其它事务提交变更，仍可能滑过；**本轮不引入 `SELECT … FOR UPDATE` 等方言相关行锁**（会引入方言分支与 SQLite 无效语义），**继续依赖静默期/单写者运维限制**（§8.4.7）。是否引入行锁属**后续批次待审批项**，本轮不实施、不宣称已解决。

#### 8.3.7 门禁执行顺序（R3.1 明确，十步，不得颠倒）

**强制口径**：**计划生成阶段（`plan()`）的任何检查都不构成 apply 阶段的安全保证。** apply 必须**在自己的事务内独立重新执行 A/B/C**；plan 携带的快照是**被校验的对象**，不是**校验的依据**。

| 步 | 动作 | 失败处置 |
|---|---|---|
| **1** | **开启事务**（apply 独占事务边界，见下方说明） | 无法开启 → 抛结构化异常，**零写入** |
| **2** | **门禁 A：全局版本同构检查**（重建专用口径）——单列 `SELECT DISTINCT link_normalization_version`，结果必须**恰为单一值且 == `plan.source_version`**；**不要求等于代码常量**（§8.4.4，否则升级/回滚死锁） | 混合或漂移 → `refused_version_drift`，**零写入** |
| **3** | **重新读取当前全表必要字段**（6 列列选择，映射为 `LinkRowState`；**不加载全量实体**） | 读取失败 → 异常 → 整体回滚 |
| **4** | **门禁 B：计划覆盖范围与唯一性**——`source_version ≠ target_version` 时 `updates` 必须覆盖 **100% 行**；计划内 **`(source_id, new_key)` 无重复**；`updates ⊆ row_snapshots` | `refused_incomplete_plan`，**零写入** |
| **5** | **门禁 C：逐行快照与当前数据库状态一致**（§8.3.6 全部规则：双向覆盖、`link_id` 唯一、6 字段精确比对、**每行新键重算比对**、no-op 行校验） | `refused_stale_plan`，**零写入** |
| **6** | **再次验证新键唯一性**——以「当前全表」为基准，把 `updates` 的新键代入后，**全表 `(source_id, key)` 不得重复**（含未更新的 no-op 行） | 重复 → `refused_stale_plan`（原因码 `new_key_mismatch`/`duplicate_new_key`），**零写入** |
| **7** | **执行批量更新**——单事务内**只写** `normalized_link_key` / `link_normalization_version` / `updated_at`（链接行自己的）；**绝不写** `target_id/resolution/cross_space/target_title/alias/created_at`，**绝不触碰 `knowledge_item` 任何列** | 任一行失败（含真实 `IntegrityError`）→ 整体回滚 |
| **8** | **写后验证**——全表版本 == `target_version` 且同构；全表 `(source_id, key)` 无重复；**每行 `target_id/resolution/cross_space/created_at` 与步骤 3 读到的值逐项相等**（证明重建没碰它们）；`knowledge_item` 全列不变 | 任一不符 → **整体回滚** |
| **9** | **全部通过后提交** | — |
| **10** | **任一环节失败，整体回滚**（含步骤 2/4/5/6 的「拒绝」——拒绝即不进入步骤 7，事务无变更结束） | 回滚后**全表逐列与拒绝前完全一致**（T30） |

**状态 precedence（避免歧义）**：按步骤顺序，**先命中者返回其状态**（A → `refused_version_drift`；B → `refused_incomplete_plan`；C 与步骤 6 → `refused_stale_plan`）。**所有拒绝一律零写入**。**明确划分**：B 的「唯一性」指**新键 `(source_id, new_key)` 重复**与**覆盖范围**；**计划内重复 `link_id` 归 C**（`duplicate_link_id_in_plan` → `refused_stale_plan`），以满足审查情况 9 的口径。

**事务归属（与既有仓库约定不同，必须写清）**：既有仓库只 `flush()`、`commit` 由路由持有（实测）。**`apply_link_key_plan()` 是运维批量入口，自己独占事务边界**（`with session.begin():`），因此：① **不得在已有活动事务的 Session 上调用**（SQLAlchemy 会拒绝开启新事务 → 抛错 → 零写入，不静默接管他人提交权）；② 本轮**无 HTTP/CLI 入口**（D8），调用方只有真实测试；③ 未来接 CLI/端点时须由该入口负责「干净 Session + 静默期确认 + 备份 + 留痕」门禁（A1-T11/A1-T14）。
> **【待验证】**：本节涉及 SQLAlchemy 具体行为的预期（`session.begin()` 在已有活动事务时抛错、Session autobegin 语义、步骤 8 的写后复核可见性）**均为设计预期，实施阶段必须以真实 SQLite + 真实 PG 测试验证**，本轮未运行任何代码。

**伪代码（apply 侧，R3.1 完整版）**：

```
apply_link_key_plan(plan, session) -> LinkRebuildReport:
  if plan.status != "ready":            return refused_stale_plan(plan_not_ready)      # 零写入
  if plan.target_version not in RULES:  return refused_stale_plan(unsupported_target_version)
  with session.begin():                                        # 步 1：独占事务
      S = SELECT DISTINCT link_normalization_version FROM knowledge_link   # 步 2：门禁 A
      if S != {plan.source_version}:    return refused_version_drift        # 零写入
      current = [LinkRowState(*r) for r in session.execute(                 # 步 3：重读全表 6 列
          select(ORM.id, ORM.source_item_id, ORM.normalized_link_key,
                 ORM.link_normalization_version, ORM.target_title, ORM.alias))]
      if not covers_all_rows(plan, current) or has_dup_new_key(plan):       # 步 4：门禁 B
          return refused_incomplete_plan                                    # 零写入
      freshness = check_plan_freshness(plan, current)   # 步 5：门禁 C（Core 纯函数，含新键重算）
      if not freshness.ok:              return refused_stale_plan(freshness.reasons)   # 零写入
      if has_dup_new_key_after_substitution(plan, current):                 # 步 6：新键唯一性再验
          return refused_stale_plan(duplicate_new_key)                      # 零写入
      for u in plan.updates:                                                # 步 7：只写 3 列
          UPDATE knowledge_link SET normalized_link_key=u.new_key,
                 link_normalization_version=u.new_version, updated_at=utcnow()
          WHERE id=u.link_id
      assert_post_write_invariants(session, current, plan.target_version)   # 步 8：写后复核
  return LinkRebuildReport(status="rebuilt", ...)                           # 步 9：提交
  # 步 10：任何异常/断言失败 → with 块退出即整体回滚
```

#### 8.3.8 计划快照与 Hash：是否需要确定性计划摘要（R3.1 论证）

**审查要求**：必须检查是否需要为 `LinkRebuildPlan` 增加确定性计划摘要；若增加须明确覆盖字段/确定性序列化/不用内置 `hash()`/不改三 Hash 契约/不进交换载荷/不新增 DB 字段；**若不可变结构 + 逐字段比较已能保证完整性，可以不增加，但必须解释原因**；**不得为加摘要而无必要地引入新 Hash 契约**。

**结论（本轮决定）：不新增计划摘要。** 理由如下，且**完整性由四道互相独立的机制保证，强于单一摘要**：

| 机制 | 能发现什么 | 为什么比摘要更强 |
|---|---|---|
| **① 不可变计划模型** | 进程内意外赋值/追加/删除（Pydantic `model_config = ConfigDict(frozen=True)`，序列字段一律 `tuple`，嵌套值对象同样 frozen） | 从源头阻止修改，而不是事后发现修改 |
| **② 全表双向覆盖 + `link_id` 唯一** | 新增行、删除行、未覆盖行、重复 `link_id`、伪造行 | 摘要只能证明「计划自生成后没变」，**不能证明「计划与当前数据库一致」**；数据库变了而计划没变时，摘要**完全无效** |
| **③ 6 字段逐项精确比对** | `source_id`/`old_key`/`old_version`/`target_title`/`alias` 的任何变化 | 直接以**当前现实**为基准，不依赖「生成时刻」的可信性 |
| **④ 每行新键重算比对** | **`new_key`/`new_version` 被篡改**、Core 计算与当前规则漂移、no-op 行漏更新 | 这是摘要**唯一可能补上的缺口**（快照字段不含 `new_key`），而**重算比对以纯函数重新派生**，既抓篡改也抓计算错误，**比摘要更强** |

**关键论证**：摘要的安全前提是「**生成时刻的计划是正确的**」。但本轮要解决的恰恰是「**生成时刻正确、执行时刻已过期**」——摘要对此**零帮助**。而情况 10（篡改）中唯一不被 ②③ 覆盖的字段是 `new_key`/`new_version`，已由 ④ **用确定性纯函数重算**覆盖。因此**四道机制合起来已覆盖审查列举的全部 10 类情况**（覆盖矩阵见 §8.3.6（3）与 T22–T40），**再加摘要属重复保障，且会引入一个新的、需要长期维护的确定性序列化契约**——违反「不得无必要引入新 Hash 契约」。

**明确不做（逐条对应审查约束）**：

- ❌ **不新增任何摘要字段**（`plan_digest` 之类一律不加）。
- ❌ **不使用 Python 内置 `hash()`**（进程间不稳定、受 `PYTHONHASHSEED` 影响）；本轮**根本不需要任何哈希**。
- ❌ **不改变** `document_content_hash` / `document_payload_hash` / `review_payload_hash` 的**定义、覆盖字段、`canonicalization_version`**（A1-02 六个冻结文件逐字节不变 + 293 用例全通过继续作为硬门禁）。
- ❌ **不把计划/快照/摘要混入文档交换载荷**：`LinkRebuildPlan`/`LinkRowState`/`LinkRebuildReport` **全部不在导出白名单内**，导出仍只含 `links[]` 的 `target_id/title/alias/resolution`（R1 白名单守卫继续断言）。
- ❌ **不新增数据库字段/表/索引/迁移**：快照只存在于**内存中的计划对象**与 backend 落盘的**报告 JSON**（gitignore，D10）。
- ✅ **保留确定性序列化**：报告/计划仍可 `model_dump(mode="json")` 往返（T12），用于**留痕与人工处置**，**与文档 Hash 契约无关**。

**不可变性的可测试要求（T38）**：① 对 frozen 计划/快照/报告字段赋值 → **抛 ValidationError/TypeError**；② `apply_link_key_plan()` 执行前后，传入 plan 的 `model_dump(mode="json")` **逐字节相同**（证明 apply 不修改计划）；③ 序列字段类型为 `tuple` 而非 `list`（防止外部 `.append()` 绕过 frozen）。

**未来边界（延后，不在本轮）**：若后续里程碑引入**跨进程/落盘重载计划**（例如 CLI 读取上次生成的计划再执行），则「生成时刻可信」这一前提不再成立，**该批次必须重新评估是否增加确定性计划摘要**（覆盖字段、确定性序列化、与三 Hash 隔离）。**本轮 A1-03 的计划只在同一进程内从 Core 传到 backend，且拒绝后强制重生成（`requires_replan=True`），不存在该威胁面**。**此项记为后续待审批，不在本轮实施。**

**契约变更判定（§8.3.6–8.3.8 合计）**：**Hash 契约无变更、数据模型/迁移无变更、端口签名无变更、V1 行为无变更、交换载荷无变更**。新增的只是**尚未编写的 Core 值类型/纯函数**与**backend 模块级函数的内部校验步骤**，属实现细节强化，**不新增任何契约**。

### 8.4 版本同构性与**全局**混合版本守卫（R2 新增；**R3 按第二轮审查意见一重写**）

#### 8.4.1 不变量

**运维窗口之外，整张 `knowledge_link` 表的 `link_normalization_version` 必须同构，且等于代码常量 `LINK_NORMALIZATION_VERSION`。** §8.3 的「全量成功 / 全量拒绝」两种终态正是为维持这条不变量。**空表视为满足不变量**（允许正常初始化）。

#### 8.4.2 ⚠ R2 守卫的漏洞（审查反例，逐步复现）

R2 §6.4 的守卫只检查 `repo.list_links(item.id)`，即**只覆盖当前源条目的出链**。审查给出的反例在本仓库**确实成立**：

| 步 | 状态 | R2 局部守卫的判定 |
|---|---|---|
| 1 | 代码常量 bump 到 **v2** | — |
| 2 | 旧 source **A、B 仍有 v1 链接行** | 与 C 无关，局部守卫看不到 |
| 3 | 新 source **C 没有任何链接行** | `rows = []` |
| 4 | `all(r.version == v2 for r in [])` | **`== True` → 通过** |
| 5 | C 保存正文含 `[[X]]` → `save_link(version=v2)` | **成功写入 v2 行** |
| 6 | 结果 | 全表变成 **v1（A、B）+ v2（C）混合** → **§8.4.1 不变量被破坏** |

**后果**：一旦混合，A/B 的绑定优先同步会按 §8.4.5 的三条路径**静默丢绑定或抛 IntegrityError**。**局部守卫在数学上不可能证明全局同构**（空集合恒真），因此 R2 的守卫**不充分**，必须升级为全局预检。

#### 8.4.3 R3 全局守卫：权威执行点、规则、豁免、成本；**R3.1 修订事务边界与缓存生命周期**

**权威执行点 = backend 持久化边界（审查要求 8）**。理由：① 只有 backend 能用**一条廉价的单列聚合查询**覆盖全表，而不必把全部链接实体加载进内存；② Core 每次同步都 `list_all_links()` 会造成**无意义的全量实体加载**（大库下 O(L) 次 ORM 对象构造），审查明确要求避免；③ 仓库与写入天然在**同一数据库事务**内（实测既有仓库只 `flush()`，`commit` 由路由持有），满足审查要求 5。**R3.1 措辞更正**：此处说的是「同一**事务**」，**不是「同一 Session」**——Session 生命周期与事务生命周期不等价，详见下文（3）。

**规则（单一来源，Core 纯函数）**：

```
# knowledge_core/markdown/link_service.py（纯函数，无 IO、无端口依赖）
check_global_version_homogeneity(versions: Iterable[int], expected: int) -> None:
    S = set(versions)
    if not S:            return          # ★ 空表 → 允许正常初始化（审查要求 2）
    if S == {expected}:  return          # ★ 全表同构且等于常量 → 允许
    raise LinkNormalizationVersionMismatch(observed_versions=sorted(S),
                                           current_version=expected, scope="global")
```

**backend 侧执行（`SQLAlchemyLinkRepository`）**：

```
# 单列 DISTINCT，不加载 ORM 实体、不构造 KnowledgeLink（审查要求 8）
SELECT DISTINCT link_normalization_version FROM knowledge_link
# 与本次写入在【同一数据库事务】内、写入之前执行；结果交 Core 纯函数判定
# ★ R3.1：无缓存。每一次受守卫的写入都重新执行上面这条查询（撤回 R3 的仓库实例级缓存）
# ★ 不得以「Session 对象还在」推断「上次预检结论仍有效」（见下文（3）（4））
```

**守卫范围（精确划定，附可证明的豁免理由）**：

| 写操作 | 是否受全局守卫 | 理由 |
|---|---|---|
| `save_link`（新建行） | ✅ **受守卫** | 新行携带版本，可能引入异值（审查反例正是这条） |
| `update_link`：**改 `normalized_link_key` 或 `link_normalization_version`** | ✅ **受守卫** | 改键/改版本会影响键空间与同构性 |
| `update_link`：**只改治理列**（`target_id`/`resolution`/`cross_space`/`target_title`/`alias`/`updated_at`，键与版本不变） | ⛔ **豁免** | **不新增行、不触碰版本列** → 全表版本集合**恒不变** → 不可能破坏同构。**这条豁免是必需的**：否则版本窗口内 **D12 删除降级**会被 409 阻断，连带 `DELETE /knowledge/{id}`（V1 功能）失败 |
| `delete_link` / `delete_links_of_item` | ⛔ **豁免** | 删除只能让版本集合**缩小**；同构集合的子集仍同构 → 不可能破坏不变量 |
| `apply_link_key_plan`（重建批量写） | ✅ **专用门禁 A/B/C**（§8.4.4 / §8.3.6 / §8.3.7） | 全表原子版本迁移，门禁是「单一版本 + 覆盖全表 + **逐行快照新鲜**」而非「等于常量」 |

> **R3.1 关键推论（豁免与门禁 C 的关系，必须讲清楚）**：上表的**治理列豁免是正确且必需的**（否则 D12 删除降级与 V1 `DELETE` 在版本窗口内会被 409 阻断），但它同时意味着——**在 `plan()` 与 `apply()` 之间，`target_title` / `alias` / `target_id` / `resolution` / `cross_space` 的合法写入不会被全局守卫拦住，新增/删除链接行也不会被拦住**。这些写入**不改变全表版本集合**（门禁 A 看不见）、**不改变计划自身**（门禁 B 看不见），却会**使计划算出的新键或覆盖范围失效**。这正是本轮必须补门禁 C 的根本原因：**豁免越宽，apply 阶段的独立重读与逐行比对就越不可省略**（§8.3.6 反例表）。豁免只针对「是否可能破坏版本同构」这一个问题，**绝不等于「这些列可以不被重建计划校验」**。

**失败语义（审查要求 3/4）**：抛 Core 结构化异常 `LinkNormalizationVersionMismatch`（携带 `observed_versions` / `current_version` / `scope`；局部守卫另带 `link_id`/`row_version`），**本次写入零生效**；异常穿过 Core 服务不被吞掉，由 backend 路由映射为 **`HTTPException(status_code=409, detail="link_version_mismatch")`**（与既有 409 用法同形状；**只回稳定码，不回异常文本、不回版本明细、不回 link_id**，AGENTS.md §9）。同步与条目写入同一事务 → **整次保存整体回滚**，不留半套链接。

**Core 侧局部守卫保留为 defense-in-depth**：§6.4 的 per-source 检查**不删除**（它能在更早阶段拒绝整次同步，避免无谓解析），但**必须明确它不证明全局同构**（`all([]) == True`）。**Core 常规同步路径不做全表扫描**（审查要求 8）。

**Core 测试替身对齐生产规则**：`helpers.py` 的 `InMemoryLinkRepository` 在 `save_link`/改键 `update_link` 上调用**同一个** `check_global_version_homogeneity()`（内存字典扫描，成本可忽略），使 **Core 层也能真实验证拒绝语义**（T15–T17 三层覆盖）。**这是测试替身对齐生产守卫，不是把全表扫描塞进 Core 生产路径。**

**成本（诚实口径，R3.1 修订）**：预检是 **O(链接行数) 的单列扫描**（不加载实体），比 `list_all_links()` 全量实体加载便宜得多，但**不是 O(1)**；**本轮不新增索引/迁移**（审查要求 7）。**R3.1 撤回 R3 的「同一事务内最多预检一次」缓存优化，改为无缓存**：k 次受守卫写入 → k 次单列 `SELECT DISTINCT`。理由与完整生命周期论证见下文（1）–（6）。**这是「不要为了省一次查询牺牲正确性」的直接落实。**

---

**（1）R3 缓存方案的原问题（本轮必须修订）**

R3 §8.4.3 原文写：「优化：**同一事务内最多预检一次**（仓库实例级缓存，实例生命周期 = 单个 Session/事务）……事务结束（commit/rollback）后实例丢弃，绝不跨事务复用缓存」。

该方案把 **「仓库实例生命周期」等同于「Session 生命周期」再等同于「数据库事务生命周期」**。这个等式**不成立**，因此缓存的失效条件无法被证明：

| R3 的隐含假设 | 实际情况 | 后果 |
|---|---|---|
| 一个仓库实例 = 一个 Session = 一个事务 | `SQLAlchemyKnowledgeRepository(session)` 只是**持有一个 Session 引用**；Session 可长期存活（请求级、进程级、测试 fixture 级） | 实例存活期内可能经历**多个**事务 |
| 事务结束后实例即被丢弃 | **调用方完全可以复用同一 Session**：`commit()` 后继续用、`rollback()` 后继续用 | 缓存跨事务复用**旧版本集合** |
| Session 存在 ⇒ 缓存有效 | Session 存在只说明**对象没被回收**，与「当前是否还是当初那个事务」无关 | **以对象存在性判断缓存有效性 = 不安全**（审查明令禁止） |

**具体失效路径（可复现，非假想）**：

```
repo = SQLAlchemyLinkRepository(session)          # 实例建立
repo.save_link(...)   # 事务 T1：预检 → S={1} → 缓存 {1} → 写入 v1 行
session.commit()      # T1 结束；缓存仍在 repo 实例上（R3 方案无失效钩子）
# —— 另一进程/另一请求在此期间把全表重建到 v2，或插入 v2 行 ——
repo.save_link(...)   # Session 自动 begin 新事务 T2；R3 方案命中缓存 {1}
                      # → 误判「全表仍同构于 1」→ 放行 → 写出混合版本
```

同理 `session.rollback()` 之后：T1 的写入被撤销、别的事务可能已提交，**缓存里的集合既不反映 T1 也不反映 T2**。

**（2）SQLAlchemy 的真实事务语义（本轮据此定策；行为断言标注【待验证】）**

- **Session ≠ 事务**。SQLAlchemy 2.x 的 Session 采用 **"commit as you go" / autobegin**：Session 在**第一次需要数据库连接的操作**时**隐式开启**一个事务；`commit()` / `rollback()` **结束该事务**，Session 回到「无活动事务」状态；**下一次数据库操作会再次 autobegin 一个新事务**。因此**同一个 Session 对象在其生命周期内会承载任意多个前后相继的事务**。
- `Session.begin()` 返回的 `SessionTransaction` 才是**事务对象**；它才有「活动 / 已提交 / 已回滚」状态。**仓库实例与 Session 都不携带这个身份。**
- **savepoint / nested**：`session.begin_nested()` 开启 **SAVEPOINT**，它**不是新的数据库事务**，而是当前事务内的子边界；`nested.commit()` 只 **RELEASE SAVEPOINT**（外层事务仍在），`nested.rollback()` 只回滚到该 savepoint（**外层事务仍在，且外层此前读到的版本集合可能已因 savepoint 内的写入而改变**）。此外 SQLAlchemy 的 "join transaction mode" 下 `session.begin()` 可能返回一个**依附于外部事务**的对象，`commit()` 不一定真正提交到数据库。
- **结论**：要安全缓存，必须能**唯一标识「当前数据库事务」**并在其结束/回滚/savepoint 边界上**精确失效**。可行手段是监听 `SessionEvents.after_transaction_create / after_transaction_end / after_rollback / after_soft_rollback` 并以事件携带的 transaction 对象为键——**但这引入事件钩子状态机、与外部事务管理（FastAPI 依赖、测试 fixture、`begin_nested`）的交互复杂度，本轮无法在不写实现代码的前提下证明其正确性**。

> **【待验证】** 上述 SQLAlchemy 语义为**设计依据与预期行为**，本轮 Design Only **未运行任何代码验证**。实施阶段必须由 **T32 / T33 / T40** 用真实 Session + 真实数据库（SQLite 与 PG 各一遍）**实测确认**：commit 后 autobegin、rollback 后 autobegin、`begin_nested` 的 commit/rollback 不结束外层事务。**若实测与预期不符，以实测为准并回报，不得按假设宣称通过。**

**（3）最终策略（本轮采纳）：无缓存 —— 每次受守卫写入重新执行单列预检**

按审查给出的保守口径执行：

| 项 | 最终规定 |
|---|---|
| 缓存建立时机 | **从不建立**。不存在任何版本集合缓存字段、实例属性、`lru_cache`、模块级字典或 ContextVar |
| 缓存失效时机 | **不适用**（无缓存即无失效问题，也就无跨事务复用风险） |
| 预检执行时机 | **每一次**受守卫写入（`save_link`、改键/改版本的 `update_link`）在**同一事务内、写入语句之前**执行一次 `SELECT DISTINCT link_normalization_version FROM knowledge_link` |
| 预检结果生命周期 | **仅限本次写入的判定调用栈**：查询 → 交 Core 纯函数 → 放行或抛异常 → **结果即丢弃**，不存储、不传递、不复用 |
| 事务边界归属 | 由**调用方**（路由 / `apply_link_key_plan` 的 `with session.begin():`）持有；仓库**只 `flush()`，不 `commit()`、不 `rollback()`、不 `begin_nested()`**（与实测既有仓库一致） |
| 判定有效性依据 | **「本次查询发生在本次写入所在的同一事务内」**——这是唯一依据。**不得**以 Session 对象是否存在、仓库实例是否复用、上次预检是否通过作为依据 |
| 豁免写入 | 治理列-only `update_link` 与删除**仍豁免**（§8.4.3 表，可证明不改变版本集合）→ **不触发预检**，因此无缓存也不会给它们增加成本 |
| 重建批量写 | `apply_link_key_plan` **不走仓库的逐行预检**，而是按 §8.3.7 十步顺序在**自己的事务内**执行门禁 A（一次 DISTINCT）+ B + C + 写后复核；**批量 UPDATE 不再逐行预检**（否则 O(L) 次全表扫描），其正确性由「全表覆盖 + 单一目标版本 + 写后复核」保证 |
| Core 测试替身 | `InMemoryLinkRepository` **同样每次受守卫写入重新扫描内存字典**，与生产策略**逐条对齐**（不得替身有缓存而生产无缓存，或反之） |

**正确性论证（无缓存为何一定安全）**：预检与写入在**同一事务**内且**预检紧邻写入之前**，因此「预检读到的版本集合」与「本次写入生效时的集合」之间**不存在本事务内的其它写入间隙**；跨事务的陈旧结论**在结构上不可能被复用**，因为根本没有存放结论的地方。**代价是查询次数，收益是无需证明任何缓存失效条件。**

**成本（诚实量化，不粉饰）**：一次保存含 k 条受守卫链接写入 → **k 次单列 DISTINCT 扫描**（R3 缓存方案声称 1 次）。单列扫描不构造 ORM 实体，SQLite 与 PG 均可走覆盖索引/顺序扫描；**本轮不新增索引**（审查要求 7）。若将来实测成为瓶颈，**另批提议**「事务身份键 + 事件钩子失效」的缓存或版本元数据表，**须单独审批 + 真实并发测试**，**本轮不做、不预先宣称可行**。

**（4）savepoint / nested transaction 的处理边界（明确写出）**

| 场景 | 无缓存策略下的行为 | 为什么安全 |
|---|---|---|
| 外层事务内 `begin_nested()` 后写入 | **照常重新预检**（读的是当前事务可见状态，含 savepoint 内未提交写入） | 每次读都是新鲜的，无需判断「是否还在同一事务」 |
| `nested.rollback()`（回滚到 savepoint） | 下一次写入**照常重新预检** | savepoint 回滚可能改变可见版本集合；无缓存 ⇒ 自动读到回滚后的真实状态 |
| `nested.commit()`（RELEASE SAVEPOINT） | 下一次写入**照常重新预检** | 外层事务未结束，但预检不依赖任何历史结论 |
| `session.commit()` 后继续用同一 Session | 下一次写入**照常重新预检**（此时已在新事务 T2 内） | **T32 专门断言**：新事务必须重新查询，不得复用 T1 结论 |
| `session.rollback()` 后继续用同一 Session | 下一次写入**照常重新预检** | **T33 专门断言** |
| 外部事务管理模式（`join_transaction_mode`）/ 嵌套 `session.begin()` | **仓库不主动开启或结束事务**，只在调用方给定的事务内查询与 `flush()` | 事务语义完全由调用方决定，仓库不做任何假设 |
| `apply_link_key_plan` | **要求传入的 Session 无活动事务**，由自己 `with session.begin():` 独占（§8.3.7）；**不支持在 savepoint 内调用**（本轮明确排除，避免「以为整体回滚、实际只回滚到 savepoint」的误判） | 事务所有权单一 ⇒ 十步顺序的第 1/9/10 步语义确定 |

**（5）分层约束保持不变（审查明确要求）**

- **Core 只提供纯函数**：`check_global_version_homogeneity(versions, expected)`（本节上文）与 **R3.1 新增** `check_plan_freshness(plan, current_rows)`（§8.3.6）。二者**无 IO、无 Session、无端口依赖、无缓存状态**，输入相同则输出相同。
- **backend 负责数据库查询**：单列 DISTINCT 预检、6 列全表重读、批量 UPDATE、写后复核，全部在 backend 具体实现内。
- **不新增端口方法**：`ports.py` 的 10 个签名零变化（D3 守护测试继续有效）。
- **不把方言 SQL 写进 Core 或业务服务**：预检与重读都用 **SQLAlchemy 表达式**（`select(...).distinct()` / `select(6 列)`），SQLite 与 PG **同一段代码、零方言分支**（§9）。

**（6）对既有测试的影响：T20③ 是断言修订，不是删除测试**

R3 的 **T20③** 原断言为「同一事务内连续创建 5 条链接 → DISTINCT 查询计数 **== 1**」，它**编码的正是被本轮撤回的缓存方案**，与无缓存策略**直接矛盾**。处理方式（严格遵守「不覆盖、不删除已有测试」）：

- **保留 T20 的编号、①②④⑤ 全部断言与测试文件位置**；
- **仅修订 ③ 的期望值**：`== 1` → **`== 受守卫写入次数`（该场景为 5）**，并在测试 docstring 与 §7.5 表内**显式标注「R3.1 断言修订：撤回事务内缓存，改为每次写入重新预检」**；
- **新增 T34** 作为该策略的**权威断言**（含豁免写入不计数、`apply` 批量写只 1 次门禁 A 预检），**T32 / T33 / T40** 覆盖 commit / rollback / savepoint 生命周期。
- **这是期望值随设计变更而更正，不是为了让测试通过而弱化断言**：修订后的断言**更强**（要求每次都查，而非允许少查），且**旧期望值在新设计下本就是错误规格**。修订记录见 **REV-25**。

#### 8.4.4 重建路径的专用门禁（为什么不能套用「等于常量」；R3.1 补门禁 C）

**若重建也要求「全表 == 常量」，升级将永远无法执行**：全表 v1、常量 v2 → 重建被自己的守卫拒绝 → 死锁（§8.3.5 已证明）。故重建入口的门禁是：

1. **全表版本同构于单一值 N**（N 可以 ≠ 常量；混合 → `refused_mixed_version`，零写入）——`plan()` 阶段；
2. **无碰撞**（§8.3.2 阶段 2–3）——`plan()` 阶段；
3. **门禁 A：apply 事务内重新预检**全表 `DISTINCT` 恰为 `{plan.source_version}`，否则 `refused_version_drift`（**不复用第 1 条的结论**）；
4. **门禁 B：计划覆盖全表行 + 计划内 `link_id` 唯一 + `(source_id, new_key)` 无重复**（`N ≠ target_version` 时 `updates` 必须含 100% 行），否则 `refused_incomplete_plan`；
5. **门禁 C（R3.1 新增）：逐行快照新鲜度**——apply 事务内重读当前全表 6 列，与 `plan.row_snapshots` **双向覆盖比对 + 6 字段精确比对 + 每行新键重算（含 no-op 行）**，任一不一致 → `refused_stale_plan` **零写入 + `requires_replan=True`**（§8.3.6）；
6. **新键唯一性再验证**（以当前数据库状态代入后仍无重复）；
7. **单事务执行 + 写后复核**（全表 == `target_version` 且无重复键，且**非键列与第 3 步重读值逐列一致**，否则整体回滚）。

**执行顺序不得颠倒，完整十步见 §8.3.7。** 第 1–2 条是**生成计划时的检查**，第 3–7 条是**执行计划时的独立验证**；**前者不构成后者的安全保证**（§8.3.5 第 7 点）。

**因此仍然只有两种终态**：全表到 `target_version`，或全表保持 N。**不存在可被提交的混合版本中间态，也不存在「部分行更新、部分行跳过」的中间态。**

#### 8.4.5 为什么混合版本危险（具体失效路径，不是假想）

绑定优先同步用**当前常量**算正文键，再与既有行的键做**字符串等值**匹配。若某行仍是 v1 键而常量已是 v2：

1. 同一书写字面在 v2 下算出的键 ≠ 该行存的 v1 键 → 匹配失败 → 被判为「新键」→ **重新解析**（丢原绑定，违反场景 A/C）；
2. 同时旧 v1 键「不在 merged 中」→ 触发「删键→删行」→ **原行被删**，`target_id` 与人工裁决结果一起消失；
3. 更糟：v1 行与 v2 行可能算出**相同字符串键**（两规则对该字面恰好一致）→ 同源同键两行 → **`IntegrityError`**。

#### 8.4.6 为什么本轮不采用「按行自身版本重算键来匹配」

该方案看似能跨版本保绑定，但无法证明第 3 条不发生（不同版本行共存时键字符串可能相等），也无法证明「删键→删行」在跨版本键空间下的语义正确。按审查意见「不引入混合版本的部分重建，除非能够完整证明同步、查询、唯一约束和回滚均正确」，**本轮不实施该方案**，改为**失败即报**的全局守卫。

#### 8.4.7 运维协议（可证明正确的升级/回滚顺序；R3 修正措辞，**R3.1 补门禁 C 与「拒绝后必须重生成计划」**）

| 步 | 动作 | 系统状态与守卫行为（**R3.1 精确表述**） |
|---|---|---|
| 1 | 发布新规则函数（**旧规则保留为可调用函数**）+ 常量 bump 到 N+1；进入维护窗口，**冻结链接写入** | DB 全表仍 N。**任何常规链接写入**（新建行 / 改键 / 改版本）被**全局守卫**拒绝（409 `link_version_mismatch`，零写入）——**包括那些自身没有链接行的 source**（审查反例已堵）。**治理列降级写入与删除行不受该门禁阻断**（§8.4.3 豁免），故 `DELETE /knowledge/{id}` 等 V1 路径在窗口内**仍可用**；但**正文保存**会因 Core 局部守卫 + 全局守卫而**整体 fail-loud**。**正因为豁免存在，窗口内仍可能发生 `target_title`/`alias` 编辑与链接增删 → 计划会过期 → 必须靠门禁 C 兜住** |
| 2 | 跑 `LinkKeyRebuild.plan(target_version=N+1)`（**只读**，Core 零写入） | 有碰撞 → `refused_collision` + 结构化报告；混合版本 → `refused_mixed_version`；`ready` 计划**携带覆盖全表每一行的 `row_snapshots` + `observed_row_count`**。DB 零写入，全表仍 N |
| 3a | 有碰撞：**停在这里**。用户处置碰撞后重跑；或**回退发布**（常量回 N） | 因 DB 全表仍 N，回退常量即恢复完整可用，**无需任何数据修复** |
| 3b | 无碰撞：backend `apply_link_key_plan()`（**独占单事务**，门禁 **A/B/C** + 新键唯一性再验证 + 写后复核，十步见 §8.3.7）→ 全表 N+1 = 常量 → 解除写入冻结 | 同构恢复，守卫不再触发。**任一门禁拒绝 → 零写入、全表仍 N** |
| 3c | **（R3.1 新增）apply 返回 `refused_stale_plan` / `refused_version_drift` / `refused_incomplete_plan`** | **禁止重试同一份旧计划**（重试必然同样失败，且掩盖真实漂移）。运维动作固定为：**① 读报告 `stale_reasons`（reason_code / link_id / field / expected / actual）定位变化 → ② 确认写入冻结是否真的生效 → ③ 重新读取全表、重新 `plan()` → ④ 用新计划再 apply**。`requires_replan=True` 即此含义。**不允许「忽略不一致行后继续」，也不允许人工挑行部分执行** |
| 4 | 回滚已成功的升级：`plan(target_version=N)` + `apply`（同受碰撞门禁 **与 A/B/C**）+ 常量回 N | 确定性恢复旧键；若旧键碰撞则拒绝并保持 N+1，需先处置；**若回滚计划过期同样 `refused_stale_plan` 零写入，必须重生成回滚计划** |
| 5 | **（R3.1 新增）事务边界纪律** | apply **必须拿到一个无活动事务的 Session**，由自己 `with session.begin():` 独占；**不得在已有事务或 savepoint 内调用**（否则「整体回滚」语义不成立）。本轮**不提供 HTTP / CLI 入口**（D8），未来 CLI 必须：干净 Session + 写入静默期 + 先备份 + 报告落盘留痕 |

> **R2 措辞修正说明（审查明确要求）**：R2 第 1 步写「**任何同步尝试**被守卫拒绝」，与 R3 的实际实现**不完全一致**——全局守卫的权威执行点在 **backend 写入边界**，且**治理列写入与删除行被证明性地豁免**。R3 改为上述精确表述：**常规链接写入全部拒绝（含无链接行的 source）；治理降级与删除不阻断；正文保存整体 fail-loud**。不再使用「任何同步尝试」这种可能被误读为「连删除条目都被阻断」的笼统说法。

#### 8.4.8 诚实限制（R3.1 扩为五条，不宣称超出实现的能力）

1. **不是跨进程严格互斥**（审查要求 6）：数据库预检 + 单事务**只能保证「检查与写入在同一事务内」**，**不能阻止另一进程在预检之后、提交之前插入异版本行**（SQLite 无行锁，PG 的 MVCC 下另一事务读到的仍是旧已提交状态）。因此**继续保留静默期 / 单写者部署的运维限制**（R5），**不宣称并发安全**。门禁 A/B/C 能发现 plan↔apply 之间的漂移并拒绝（T21 / T22–T40），但那是**漂移检测**，不是互斥。
2. **门禁 C 的检测窗口有明确边界（R3.1 新增，必须如实说明）**：C 把「计划过期可被提交」的窗口从 **plan→apply 全程**收窄到 **apply 事务内「第 3 步重读」→「第 9 步提交」之间**。**这个残余窗口本轮不关闭**：不使用 `SELECT … FOR UPDATE` 行锁、不使用表锁、不使用 advisory lock、不引入跨进程互斥。**若另一进程恰在该窗口内提交链接增删或键字段编辑，C 无法察觉**（PG 默认 READ COMMITTED 下第 3 步读到的是已提交快照；SQLite 写事务串行化程度不同，但同样不宣称等价于互斥）。**关闭该窗口需要行锁/表锁或单写者部署，属另批提议，标记【待审批】，本轮不实施、不宣称已解决。**
3. **Core 单独复用时的边界**：全局守卫的**权威执行点在 backend 持久化实现**。若将来 Core 被独立复用（如 Nesti）而**没有等价的 backend 预检与门禁 C 重读**，则全局不变量与计划新鲜度由**该调用方的持久化实现负责**；Core 自身只保证 per-source 局部守卫与**纯函数判定规则**。这是分层与成本取舍的**已知边界**，如实记录，不在本轮扩大范围。
4. **性能边界（R3.1 修订）**：预检为 O(链接行数) 单列扫描，**无缓存 ⇒ 每次受守卫写入各一次**（k 次写入 = k 次扫描，§8.4.3（3））；门禁 C 另需一次 **6 列全表重读**（O(L) 行、不构造 ORM 实体）+ 一次写后复核。**不新增索引**。若将来成为瓶颈，另批提议版本索引 / 元数据表 / 带事务身份键的缓存（须新迁移或事件钩子 + 单独审批 + 真实并发测试），**本轮不做**。
5. **计划摘要未引入的边界（R3.1，§8.3.8）**：本轮计划**只在同一进程内从 `plan()` 直接传给 `apply()`**，靠 frozen 模型 + 双向覆盖 + 精确比对 + 新键重算保证完整性，**不新增 Hash 契约**。**若将来计划需要跨进程传输或落盘后重载**（例如运维 CLI 读 JSON 计划文件），**该批次必须重新评估确定性计划摘要**（届时另批提议、单独审批）。**本轮不存在该威胁面，故不预先引入摘要。**

### 8.5 前后兼容性完整说明（R2 新增，审查意见四.4）

#### 8.5.1 数据层向后兼容（旧数据 / 旧代码读新数据）

| 对象 | 兼容性 | 依据 |
|---|---|---|
| V1 既有表与列（`knowledge_item` 原列 / `knowledge_relation` / `knowledge_version` / `review_request` / `experiment*` / FTS5 虚表 / 向量表） | **零改动** | A1-03 不改 `models.py`、不改 0006、不新增迁移（§4.3） |
| V1 历史知识条目 | **无损**，无需回填 | `knowledge_link` 是 0006 **新建表**，V1 无链接行（§8.1）；A1-03 不给旧条目凭空造链接（链接只来自正文解析） |
| A1-01 已写入的 V2 数据（tags/extra_metadata 等） | **不动** | A1-03 只读写 `knowledge_link`；`knowledge_item` 仅在既有 V1 流程中被读写，链接同步**不改其任何列**（§6.4 不变量 2） |
| V1 代码读 A1-03 之后的数据库 | **兼容** | V1 代码不感知 `knowledge_link`；新增行对 V1 查询不可见、不参与 V1 检索/审核/关系/图 |
| A1-03 代码读未 upgrade 的库 | **不适用** | 0006 未 upgrade 则无 `knowledge_link` 表；A1-03 依赖 0006 已 upgrade（与 A1-01/A1-02 同一前提），**不宣称支持未迁移库** |

#### 8.5.2 交换格式前后兼容（旧文件 / 新文件互读）

| 方向 | 兼容性 | 依据 |
|---|---|---|
| **V1 纯文本正文**（无 frontmatter）→ A1-03 解析 | ✅ | `split_frontmatter` 对无 `---` 起始的文本返回 `raw_block=None`、body 逐字（A1-02 实测）；正文里的 `[[X]]` 正常解析 |
| **A1-02 导出文件** → A1-03 读取 | ✅ 且 **hash 不变** | A1-03 不改 codec、不改 `canonicalization_version`（恒 1）、不改 `sort_links`；冻结 6 文件指纹保证 |
| **A1-03 导出文件** → 旧 A1-02 codec 读取 | ✅ | A1-03 **不新增 frontmatter 已知键**；`links[]` 仍只用 A1-02 已支持的 `target_id/title/alias/resolution` 四子字段；即使将来出现未知子键，A1-02 也**原样保留不丢**（实测 `sort_links` 不丢键） |
| **A1-03 导出文件** → 其它工具（Obsidian 等） | ✅ 语义可读 | frontmatter 由 A1-02 确定性 emitter 再生（流式集合、按需引号）；正文逐字保留 |
| **派生键不外泄** | ✅ 硬保证 | 导出白名单**绝不**写 `normalized_link_key`/`link_normalization_version`/`cross_space`/`normalized_title_key`（R1）→ 键重建不会让任何实例的 hash 分叉 |
| **字节级往返** | ⚠ **不宣称** | 沿用 A1-02 口径：**语义无损（正常态），字节级不保证**；冲突态不称完全无损 |

#### 8.5.3 API 兼容

- **只增不改**：新增 3 个只读 GET（D8）+ 新 router；V1 全部端点的**路径、方法、请求/响应模型、状态码语义一律不变**。**守护测试**断言新增 router 的方法+路径集合恰好为 3 个 GET（§6.7），防止实施时顺手加写端点。
- **新增错误路径（R3 精确化）**：`409 link_version_mismatch` 仅在**全表版本不同构**时触发（§8.4 全局守卫）。触发范围**仅限常规链接写入路径**（`POST /knowledge`、draft `PATCH`、`extract`、以及未来的导入路径）；**`DELETE /knowledge/{id}` 不被阻断**（其入链降级只写治理列，属证明性豁免，§8.4.3 / T20）。**V1 数据无链接行 → 空表允许初始化 → 永不触发** → V1 API 回归不受影响。**如实口径**：一旦进入版本升级窗口且尚未完成重建，**含链接的正文保存会整体 409 fail-loud**，这是「宁可失败也不静默丢绑定」的取舍，须在运维文档中告知，不宣称窗口内保存仍可用。
- **路由不冲突**：静态字面 `/knowledge/links/resolve-candidates` **先于** `/knowledge/{item_id}` 声明（设计 §2.6 路由口径 + R11），加路由匹配测试。
- **active 编辑门禁不变**：PATCH active 仍返回 202 + 审核单且**不同步链接**（R9）；审核批准后才应用并同步。
- **人工绑定无写入口（R3，§6.7）**：D7 的显式绑定规则**只在 Core 层定义与测试**，A1-03 **不提供** `POST links/resolve` 等写端点；**不得把人工绑定描述为已交付的用户功能**。
- **前端零改动**：本轮不动前端任何文件；新端点暂未被前端调用 → 既有 UI 行为与构建产物不变（§13.2 如实说明未重跑前端测试的理由）。

#### 8.5.4 版本与规则兼容

- `link_normalization_version`（链接键规则）与 `canonicalization_version`（hash 序列化规则）**相互独立**，互不触发（§2.6.1 明文）。A1-03 **只可能**动前者，且本轮实施保持 v1（v2 规则仅作为**测试夹具**存在，不发布为生产常量）。
- **旧规则函数永久保留为可调用函数**（如 `normalize_link_text_v1`），使「以旧版本重跑」成为确定性回滚（§8.3.4）。
- 混合版本由**全局守卫**失败即报，不静默降级（§8.4）；**局部（per-source）检查不足以证明全局同构**，R3 已升级为覆盖全表的预检。
- **导入恢复会重算 `resolution`/`cross_space`（R3，§6.6）**：同空间布局往返 hash 不变；跨空间布局导入后再导出 `payload_hash` **可能变化**（语义正确，D1 同口径），`content_hash` 不变。这不是版本规则变更，也不触发 `canonicalization_version` bump。

#### 8.5.5 降级与代码回滚兼容

| 回滚类型 | 效果 | 诚实口径 |
|---|---|---|
| **代码回滚**（撤掉 A1-03 新模块与挂接） | V1 功能与数据**完全不受影响**；已建 `knowledge_link` 行**留存但无人读写** | **不宣称自动清理**；如需清理须显式运维动作（`delete_links_of_item` 或 0006 downgrade） |
| **键版本回滚**（`plan(target_version=旧)` + `apply_link_key_plan`） | 确定性恢复旧键，绑定与三 Hash 不变 | **同受碰撞拒绝门禁 + 门禁 A/B/C（R3.1）**，不是无条件撤销（§8.3.4 / §8.3.7 / T10 / T21 / T22–T40）。**回滚计划过期同样 `refused_stale_plan` 零写入，必须重生成回滚计划，不得重试旧计划** |
| **Schema Rollback**（0006 downgrade） | 删 V2 表/列 | **丢 V2 数据，非无损**；破坏性 downgrade 须走运维包装器门禁（备份+校验+确认+留痕），属 **A1-T14，不在 A1-03** |
| **Data Rollback** | 依赖备份 | 本轮不实现备份/恢复（A1-T14） |

#### 8.5.6 兼容性验证清单（实施阶段必须真实跑；R2 六项 → R3 九项 → **R3.1 十二项**）

- [ ] V1 无 frontmatter 纯文本条目 → 同步链接正常，`content` 逐字不变。
- [ ] A1-02 导出文件在 A1-03 代码下解析 → 三 Hash 与 A1-02 当时记录**逐位相同**（冻结指纹 + 293 用例全通过共同保证）。
- [ ] A1-03 导出文件交回 A1-02 codec（同一冻结实现）解析 → 语义无损、未知子键不丢、不含派生键字样。
- [ ] V1 全量 API/检索/审核/关系/版本/图/实验回归零回归（SQLite + 真实 PG）。
- [ ] 0006 up/down 在 SQLite 与真实 PG 仍通过（A1-01 用例不改、不弱化）。
- [ ] **全局**版本不同构守卫触发时**零写入** + 409 稳定错误码；**含「当前 source 无链接行但其它 source 有旧版本行」的审查反例**（T16）；恢复同构后保存正常。
- [ ] **R3 新增**：版本窗口内 `DELETE /knowledge/{id}` 的入链降级**仍可执行**（治理列豁免，T20），删除后读取不抛异常。
- [ ] **R3 新增**：跨空间 UUID 恢复后 DB 列真实为 `cross_space`/`True`（双方言），**不存在 `resolved` + `cross_space=False` 的跨空间行**（H14–H16）。
- [ ] **R3 新增**：新增 router 只含 3 个 GET；`ports.py::LinkRepository` 方法集合仍为 10 个且签名不变（§7.7 守护）。
- [ ] **R3.1 新增（第 10 项）**：**过期计划零写入**——`plan()` 之后分别制造「改 `target_title` / 改 `alias` / 改 `source_id` / 改 `normalized_link_key` / 改版本 / 新增链接行 / 删除链接行 / 计划覆盖不全 / 计划内重复 `link_id` / 篡改 `new_key`」十类变化，`apply_link_key_plan()` **一律返回 `refused_stale_plan`（或对应 A/B 稳定状态）+ `requires_replan=True`**，且**全表逐列快照与拒绝前完全一致**（含 `knowledge_item` 全列、三 Hash、导出字节）——**SQLite 与真实 PG 各跑一遍**（T22–T31）。
- [ ] **R3.1 新增（第 11 项）**：**无缓存事务生命周期**——`session.commit()` 后的新事务、`session.rollback()` 后的新事务，**下一次受守卫写入必须重新执行单列 DISTINCT 预检**（查询计数断言，不得复用旧结论）；同一事务内 k 次受守卫写入 → **k 次预检**；治理豁免写入与删除 → **0 次预检**（T20③ 修订 / T32 / T33 / T34）。
- [ ] **R3.1 新增（第 12 项）**：**savepoint / nested 边界**——`begin_nested()` 内写入照常重新预检；`nested.rollback()` 后下一次写入读到回滚后的真实版本集合并据此判定；`nested.commit()` 不结束外层事务；`apply_link_key_plan` **拒绝在无活动事务之外/已有事务或 savepoint 内被调用**的约定由测试固定（T40）。**双方言各一遍。**

---

## 9. SQLite / PostgreSQL 差异与一致性保障

| 维度 | SQLite | PostgreSQL | A1-03 一致性策略 |
|---|---|---|---|
| 唯一约束 NULL | NULL 互不相等 | 同（不依赖 PG15 `NULLS NOT DISTINCT`） | **键非空**（空 alias→`""`），两边语义一致；两边都测 alias NULL/非 NULL |
| FK 行为 | 需 `PRAGMA foreign_keys=ON`（`session.py` 已设） | 原生 | CASCADE/SET NULL 两边**同断言**真实验证 |
| 字符串长度 | **不强制** VARCHAR 长度 | **强制** | **在 Core/Pydantic 层守卫**（title≤500、key≤1024），超长在进 DB 前就拒绝 → 两边行为一致（R4） |
| 文本等值/排序 | BINARY collation | 依赖数据库 collation | 键匹配**只用 `=` 精确等值**，**不用 LIKE/ILIKE/排序规则**；规范化全在 Python → 不受 collation 影响 |
| 规范化计算 | 无 NFKC 能力 | 无 NFKC 能力 | **一律 Core Python `unicodedata`**，绝不写进 SQL（方言边界红线） |
| 布尔 | INTEGER 0/1 | BOOLEAN | SQLAlchemy 类型映射，两边往返测试 |
| 时间 | DateTime(timezone=True) 存 UTC | 同 | 统一 `utcnow()` UTC |
| 写并发 | 库级写锁（短事务） | 行级锁 | 同步/重建都走**短事务**；重建单事务；不宣称跨进程严格互斥（R5） |
| 候选枚举 | `SELECT` 全量 | 同 | 同一 SQLAlchemy 表达式，无方言分支 |
| **唯一约束冲突** | `IntegrityError`（UNIQUE 原生生效） | `IntegrityError` | **写前全量预检**避免依赖 DB 报错兜底；T7 在**两边都真实插入重复键**证明约束确实存在 |
| **事务回滚** | 单事务 `rollback()` | 同 | T5 **故障注入**后两边都做**全表逐列快照**比对，证明无半套更新 |
| **archived 过滤** | Python 侧 `status != archived` | 同 | 过滤在 **Core Python** 完成，不写方言 SQL；两边候选集合一致（L 场景双验） |
| **空间等值过滤（R3）** | Python 侧 `candidate.space_id == item.space_id`（`None==None`） | 同 | 过滤在 **Core Python** 完成（§2.5⚠：`list(space_id=None)` 实测返回全库，必须再过滤）；两边候选集合与跨空间判定一致（J / H15 / H16 双验） |
| **全局版本预检（R3；R3.1 改无缓存）** | `SELECT DISTINCT link_normalization_version`（单列，无实体加载） | 同一 SQLAlchemy 表达式 | **零方言分支**；两边都真实验证空表允许 / 同构允许 / 异值拒绝 / 混合拒绝（T13–T18）；两边异常类型与 409 稳定码一致。**R3.1：每次受守卫写入各执行一次，无缓存**（T34） |
| ~~预检的事务内缓存（R3）~~ **→ R3.1 已撤回** | ~~同一 Session/事务一次~~ | ~~同~~ | **撤回理由：Session 生命周期 ≠ 事务生命周期**（commit/rollback 后 autobegin、savepoint 边界），缓存失效条件无法证明 → **改为无缓存，每次受守卫写入重新预检**（§8.4.3（1）–（6））。两边都用查询计数断言 **计数 == 受守卫写入次数** + **commit 后重新预检（T32）/ rollback 后重新预检（T33）/ savepoint 边界（T40）**；T20③ 期望值随之修订 |
| **门禁 C 的 6 列全表重读（R3.1 新增）** | `select(id, source_item_id, normalized_link_key, link_normalization_version, target_title, alias)` 全表 | **同一 SQLAlchemy 表达式** | **零方言分支、零原生 SQL、不构造 ORM 实体**；两边取回的字符串**按原始 Unicode 精确比对**（不依赖 collation，不做 NFKC/casefold）；`None` 与 `""` 两边都区分（SQLite TEXT 与 PG VARCHAR 均不混淆）；两边 `stale_reasons` 集合一致（T22–T31） |
| **门禁 C 的比对与重算（R3.1 新增）** | Core Python 纯函数 | 同 | **比对与新键重算全在 Core Python**（`check_plan_freshness`），**绝不写进 SQL**（方言边界红线）；两边只在 backend 侧做「重读 → 转 `LinkRowState`」的装配，判定逻辑单一来源 |
| **savepoint / nested（R3.1 新增）** | `begin_nested()` → SAVEPOINT（SQLAlchemy 统一语义） | 同 | 仓库**不主动开启/结束事务或 savepoint**；`apply_link_key_plan` **独占 `with session.begin():`，不得在已有事务或 savepoint 内调用**；两边都测 nested commit/rollback 后重新预检（T40）。**残余并发窗口不靠行锁关闭**（§8.4.8 第 2 条，【待审批】） |
| **cross_space 落值（R3）** | INTEGER 0/1 | BOOLEAN | 跨空间恢复后两边**列值真实**为 `resolution='cross_space'` + `cross_space` 真（H14–H17 双验） |

**封装位置**：全部 ORM 访问在 `backend/app/services/links.py`；Core 与业务服务**零方言 SQL**（AGENTS.md §5 红线）。A1-03 **不需要** `app/db/` 新增方言适配文件（无全文/向量/锁需求）。

**PG 验证纪律**：必须连真实实例（`D:\ExplainLab-pg\pgsql\bin`，port 55432，DB `explainlab_test`）。**离线生成 SQL 不算验证；无实例则报告并等待，不得用 SQLite 冒充 PG，不得虚报连接成功。**

---

## 10. 风险与降级策略

| # | 风险 | 影响 | 降级/收敛策略 |
|---|---|---|---|
| **R1** | 导出器误把 `normalized_link_key`/`version` 写进交换 `links[]` | 键重建改变 payload_hash，**违反用户核心要求** | 导出子字段**白名单**（只 target_id/title/alias/resolution）+ 场景 F 硬测试 + 「导出文本不含这两个键名」断言 |
| **R2** | 用 `delete_links_of_item` 先清后建做常规保存 | 丢绑定、churn ID、场景 C/E 失败 | 常规保存**只走按键匹配**；该方法限用于删除/显式重置；docstring 澄清（**D3 已批准**） |
| **R3** | 候选枚举 `list(space_id=…)` 为 O(N)，每次保存全量拉取 | 大库保存变慢 | 每次同步**只构建一次标题索引**（O(N+L) 而非 O(N×L)）；如实记录性能边界；**不新增端口/列**（避免动 A1-01 契约）。若将来成为瓶颈，另批提议派生标题键索引 + 迁移 |
| **R4** | NFKC 扩展使键超 1024；SQLite 不报长度错而 PG 报错 | **双方言行为分叉** | Core 层显式长度守卫 → 超长判畸形 + warning，两边一致拒绝；边界值 1024/1025 双方言测试 |
| **R5** | 重建「冻结写入」并非跨进程严格互斥（SQLite 无行锁；**R3.1：本轮也不使用 `SELECT … FOR UPDATE`**） | 重建期间并发写可能交错；**门禁 C 把窗口收窄到「apply 事务内重读→提交」，但该残余窗口本轮不关闭** | 单事务重建 + 短事务 + **门禁 A/B/C 漂移检测**（拒绝即零写入）；**明确降级口径：建议运维静默期/单写者部署，不宣称完全并发安全**（与 §8.4.8 第 1/2 条同口径）。PG 的 UPDATE 自身会锁住被改行，但**不阻止其它事务插入新行或改治理列**，故**不得据此宣称互斥**；行锁/表锁方案**【待审批】，另批提议** |
| **R6** | 别名变更按设计=新键→重解析，可能丢失人工裁决的绑定 | 用户改显示名后 ambiguous 重新出现 | **D5 已裁决：不继承旧 `target_id`，严格执行新键重新解析**。「alias-only 继承绑定」的可选扩展**不实施**；场景 H 用「把 B 改成歧义标题后 alias-only 变更应重新落入 ambiguous」证明是**重解析**而非继承 |
| **R7** | 缩进代码块/HTML 注释内的 `[[X]]` 被当链接 | 误建链接 | 取设计字面口径（只排除围栏/行内/转义），**如实写入验收局限**；不自行扩大排除范围以免误杀列表内真实链接 |
| **R8** | 在 `ReviewService` 内加链接钩子 | 改动 V1 已审计 Core 类 | **不改 ReviewService**；backend 装配层在「已应用」后调用 Core 同步服务（§2.2） |
| **R9** | active 编辑返回 202 时误同步链接 | 未批准的变更提前生效 | 只在 `submit` 返回 None（已应用）或 `approve` 之后同步；202 分支加测试断言链接未变 |
| **R10** | 链接同步失败导致条目保存半成功 | 数据不一致 | 同步与条目写入**同一事务**，失败整体回滚；测试注入失败验证回滚 |
| **R11** | 新 router 路径与 `{item_id}` 冲突 | 404/误匹配 | 静态字面 `/knowledge/links/resolve-candidates` **先于**动态声明（§2.6 路由口径）；加路由匹配测试 |
| **R12** | 规范化规则未来变更 | 历史键失效 | `link_normalization_version` 逐行留版本；重建从原始字面重算；回滚=旧版本重跑（§8.3）；**与 `canonicalization_version` 独立，互不触发** |
| **R13** | **FK SET NULL 后 `resolution='resolved'` + `target_id=NULL` 成非法组合** | 删除目标后**读取出链/反链抛 ValueError**（§2.6 实测论证） | 删除路径同事务显式降级为 missing（主）+ 仓库读取侧防御映射（辅）；**不弱化实体校验器、不加方言触发器、不改 FK**（D12 已裁决）；场景 I 双方言断言「删除后读取不抛异常」+「直接构造非法实体仍抛 ValueError」 |
| **R14** | **混合版本部分重建 / 局部守卫冒充全局**（R2 新增；**R3 升级**） | 键匹配失败→静默重解析+删旧行→丢绑定；或同源同键两行→`IntegrityError`；**R2 的 per-source 守卫在「源条目无链接行」时 `all([])==True` 恒通过，挡不住其它 source 的旧版本行** | **只有全量成功/全量拒绝两种终态**（§8.3）+ **覆盖全表的全局预检**（§8.4.3，backend 单列 DISTINCT + Core 纯函数规则）+ 重建专用门禁（§8.4.4）+ 运维协议；**不实施**「按行版本重算匹配」；**T13–T21 锁定（含审查反例 T16）** |
| **R15** | **碰撞导致版本升级停滞**（R2 新增） | 运维无法完成 bump，长期停在旧版本 | 拒绝时**DB 零写入**，故**回退发布即恢复可用**，无需数据修复；结构化碰撞报告交 backend 落盘（D10）供用户处置后重跑；**不擅自部分重建/合并/删行**；如实告知「升级可能被碰撞阻塞」是设计的正确行为而非缺陷 |
| **R16** | **导入提示 last-write-wins / 矛盾被掩盖**（R2 新增，问题 B） | 恢复结果依赖 frontmatter 书写顺序；矛盾绑定被静默丢弃 | **先聚合再判定**（§6.5）：同键保留全部提示；按**有效提示的不同 target 基数**判定；H1–H20 专项（R3 扩展）+ **顺序打乱结果不变**测试；冲突双方信息全部进 warning 与报告 |
| **R17** | **把无效提示当矛盾票**（R2 新增） | 跨实例导入（target 失效是常态）大面积误入 conflict，违背 §2.4「回退标题解析」 | 明确「**无效 ≠ 矛盾**」口径：矛盾投票只在**有效提示**间进行；UUID 非法/目标不存在归 `invalid_hints` + warning + 回退；H6/H7 锁定 |
| **R18** | **D7 口径误实施**（R2 新增；R1 稿曾主张「排除自身→missing」） | 自链接被误降级；archived 被误禁绑定 | **D7 已裁决**：archived **仅排除自动解析**、允许显式绑定；**自链接允许正常解析**；场景 K/L 五条断言锁定（含「显式绑定 archived 后连续保存不被自动解绑」） |
| **R19** | **Core 侧写文件破坏独立性与可复用性**（R2 新增，D10） | Core 绑定文件系统路径，无法复用于 Nesti；报告落盘位置不可控 | **Core 只返回结构化报告对象**，零文件 IO；落盘由 backend `persist_rebuild_report()` 负责；**T12 行为守护**：monkeypatch `open`/`Path.write_text`/`Path.mkdir` 抛异常后重建仍成功 |
| **R20** | **局部版本检查被误当全局守卫**（R3 新增，第二轮审查阻塞项一） | 源条目无链接行时 `all([])==True` 恒通过 → 在旧版本库中写入新版本行 → 全表混合 → 静默丢绑定 / IntegrityError | **全局预检覆盖整张表**（backend 单列 `SELECT DISTINCT` + Core 纯函数 `check_global_version_homogeneity`）；**空表允许初始化**；检查与写入**同一事务**；409 `link_version_mismatch`；**T16 专门复现审查反例**并断言局部守卫确实通过、全局守卫确实拒绝 |
| **R21** | **全局守卫误伤 V1 路径 / 重建死锁**（R3 新增） | ① 若守卫覆盖所有写入，版本窗口内 D12 删除降级被 409 阻断 → `DELETE /knowledge` 失败；② 若重建也要求「等于常量」，升级永远无法执行 | **精确豁免**：只改治理列的 `update_link` 与删除行**不受守卫**（附「版本集合恒不变/只缩小」的证明）；**重建走专用门禁**（全表单一版本 + 覆盖全表 + 单事务 + 写后复核），**不给 `update_link` 开绕过开关**；T20/T11/T21 锁定 |
| **R22** | **跨空间绑定被伪装成普通 resolved**（R3 新增，第二轮审查阻塞项二） | 导入恢复只校验目标存在、不校验空间 → 跨空间行写成 `resolved`+`cross_space=False` → 用户与后续治理误判为同空间绑定；或反向一律拒绝 → 正常跨空间导入无法恢复 | **采纳「有效 UUID = 历史显式绑定意图」**：目标存在即恢复，**按当前空间关系重算** `resolution`/`cross_space`；服务层不变量 `cross_space=True ⟺ resolution=cross_space`；**空间不匹配 ≠ 无效 ≠ 矛盾**（三类语义分离表）；archived 与 D7 一致；H13–H20 + 双方言列值断言 |
| **R23** | **人工绑定被误报为已交付**（R3 新增，第二轮审查意见三） | D7 允许显式绑定 archived/跨空间，但 D8 只交付只读 GET → 若验收写「用户可显式绑定」即虚报未交付功能 | **§6.7 交付边界表 + 验收措辞纪律**：Core 规则已定义已测试、**无 HTTP 写入口**；L③/J 标注「Core 层验证」；L④ 的 HTTP 侧只验证「保留」不验证「建立」；**路由方法集合守护**防止顺手加 POST；§13.2 明列未交付项 |
| **R24** | **候选枚举在 `space_id=None` 时返回全库**（R3 新增，实测发现） | 个人总知识库源条目的自动候选混入各 project 空间条目 → **自动跨空间绑定**，违反「不自动跨项目」 | Core 侧对 `repo.list(...)` 结果**再做精确空间等值过滤**（`None==None`），不依赖仓库返回范围；**不改 V1 仓库、不改端口**；场景 J 扩展断言 + H15/H16 对照（§2.5⚠） |
| **R25** | **★ 重建计划过期：门禁 A+B 不足以发现漂移**（**R3.1 新增，本轮唯一目标**） | `plan()` 与 `apply()` 之间若发生**链接增删**或 **`target_title`/`alias`/`source_id`/`normalized_link_key` 编辑**（其中治理列编辑与增删**被全局守卫合法豁免**），**版本集合不变 ⇒ A 看不见；计划自身不变 ⇒ B 看不见** → apply 会按**过期计划**写入：新键算错、覆盖漏行、no-op 行盲区、甚至把已删行的更新打到不存在的 ID 上 → **键空间与正文语义不一致 / 静默丢绑定 / IntegrityError** | **门禁 C（§8.3.6）**：`plan()` 携带**覆盖全表每一行（含 no-op）的 `row_snapshots`**；apply **在自己的事务内重读当前全表 6 列** → Core 纯函数 `check_plan_freshness()` 做**双向覆盖 + `link_id` 唯一 + 6 字段原始 Unicode 精确比对 + 每行新键重算（含 no-op 行）+ 篡改检测**；任一不一致 → **`refused_stale_plan` + 零写入 + `requires_replan=True` + `stale_reasons`**，**禁止部分更新、禁止忽略不一致行继续、禁止重试旧计划**（§8.4.7 步 3c）；**十步执行顺序固定**（§8.3.7）；**不新增摘要/Hash/字段**（§8.3.8）；**T22–T40 锁定（含 no-op 盲区反证 T37、篡改 T36、双方言 T31）**。**残余窗口（重读→提交）如实记录为未关闭，不宣称互斥**（§8.4.8 第 2 条，行锁方案【待审批】） |
| **R26** | **★ Session 生命周期 ≠ 事务生命周期 → 版本预检缓存跨事务复用**（**R3.1 新增，审查 §五**） | R3 的「仓库实例级缓存（实例 = Session = 事务）」假设不成立：SQLAlchemy 2.x **commit/rollback 后 autobegin 新事务**，同一 Session/仓库实例可承载多个事务；`begin_nested()` 的 savepoint 边界又不结束外层事务 → **缓存里的旧版本集合被当成当前状态** → 守卫误判放行 → **写出混合版本**（正是 E1 要杜绝的失效路径） | **撤回缓存，采用无缓存保守方案**（§8.4.3（1）–（6））：**每次受守卫写入重新执行单列 `SELECT DISTINCT`**，结果**仅存在于本次判定调用栈**，不存储不复用；**有效性唯一依据 = 「本次查询与本次写入在同一事务内」**，**不得以 Session 对象是否存在判断**；豁免写入不预检（成本不变）；`apply` 批量写只 1 次门禁 A 预检；**仓库不主动 commit/rollback/begin_nested**，apply **独占事务**；**Core 仍只提供纯函数、backend 负责查询**（分层不变、端口不变）；**T20③ 期望值修订 + T32/T33/T34/T40 锁定**；成本如实量化为 **k 次写入 = k 次单列扫描**，**不为省一次查询牺牲正确性** |

---

## 11. 裁决台账：D1–D12 + 第一轮 A/B + 第二轮 E1–E5 + **R3.1 E6**（用户已批准，R2/R3/R3.1 全部落实，不再开放）

> 第一轮独立审查已对 D1–D12 与问题 A/B 全部给出裁决；第二轮（最终）独立审查给出 E1（全局版本同构守卫）、E2（导入绑定空间语义）、E3（人工绑定交付边界）三项裁决。本节由「开放决策」改为「**已裁决 + 落实位置**」台账。实施阶段**严格按裁决执行**，不得回退到 R1/R2/R3 稿的旧取向，也不得擅自扩大。
> **E4/E5 不是新开放决策**：E4 是落实 E1 时暴露的 R2 内部自相矛盾所必需的**配套职责分层调整**；E5 是 R3 实测代码新发现的缺陷风险处置。两者均**不改任何契约**。
> **R3.1 轮审查结论（本轮据此修订，如实记录）**：**E1、E2、E3、E5 已通过**；**E4 的 Core plan / backend apply 职责拆分已批准，但必须补充门禁 C**。因此本轮：**E1/E2/E3 不重新设计**；**E5 不再重新讨论、批准状态不变**；**E4 拆分本身保留**，只新增 **E6（门禁 C + 十步顺序 + 不新增摘要 + 无缓存策略）** 作为其必须补充项。**R3 原有已批准设计全部保留。**

| # | 议题 | **裁决结果（已批准）** | 落实章节 | 设计契约变更 |
|---|---|---|---|---|
| **D1** | `resolution` 是否留在交换载荷参与 payload_hash | **保留**在交换载荷，**不修改 Hash 契约**；`canonicalization_version` 恒 1，历史 hash 不重算 | §5.4 / §5.2 问 5 / R1 守卫 | **无** |
| **D2** | 解析用标题键 | **新增 `normalized_title_key`**，作为 **Core 内部派生计算**，**不持久化**、不进交换载荷、不参与 Hash | §5.5 / §3① / §6.5 | **无**（设计「标题规范化同键」本就指标题键） |
| **D3** | `ports.py::delete_links_of_item` | **仅修改 docstring**，**不改变签名和行为**；另加签名不变守护断言 | §2.3⚠ / §4.2 / §7.7 | **无** |
| **D4** | 链接存在性权威 | **正文是权威**；Frontmatter `links` **仅提供绑定提示**；**孤儿提示不建行 + warning** | §6.5 / §3② / H9 | **无**（设计未定义处的口径明确） |
| **D5** | alias-only 变更 | **不继承旧 `target_id`**，**严格执行新键重新解析** | §6.2 / 场景 H / R6 | **无**（设计字面「别名变化视为键变化」） |
| **D6** | `![[X]]` | **排除**出知识链接解析，**保留给附件嵌入**（A1-04）+ warning | §6.3 / §3① | **无** |
| **D7** | archived 与自链接 | **自动解析排除 archived**，但**允许用户显式选择 archived**；**允许自链接，不额外禁止** | §6.2 / §6.4 / 场景 K、L / R18 | **无**（设计未定义处的口径明确） |
| **D8** | HTTP 端点范围 | **含 3 个只读 GET**（links / backlinks / resolve-candidates）；**不提前增加写操作 API** | §3④ / §4.1 / §8.5.3 | **无**（设计 API 清单的子集，写端点延后） |
| **D9** | 绑定时目标标题列 | **不新增**数据库列；快照 = 用户书写的 `target_title` 原始字面 | §8.1 | **无** |
| **D10** | 重建报告与留痕 | **Core 返回结构化重建报告**，**由 backend 运维层负责持久化**；**本轮不在 Core 自动写文件** | §8.3.4 / §3②③ / T12 / R19 | **无**（职责分层，不改数据契约） |
| **D11** | 模块落点 | **`markdown/links.py`（纯文本）+ `markdown/link_service.py`（端口服务）** 两层；ABC 在 `markdown/__init__.py` 追加 | §3 / §4.1 / §4.2 | **无**（实现细节，满足「解析与持久化分层」） |
| **D12** | FK SET NULL 非法组合 | **删除目标时同事务降级入链为 missing** + **仓库读取侧防御映射**；**不弱化实体校验器、不改 FK、不增加数据库触发器** | §2.6 / 场景 I / R13 | **无** |

**审查另要求的两个逻辑问题修订（不属 D 编号，同为已批准裁决）**：

| 问题 | 裁决方案 | 落实章节 | 设计契约变更 |
|---|---|---|---|
| **A 规范化键重建碰撞** | 写前全量预算 + 检测全部碰撞组 + **有碰撞默认拒绝全量重建（事务零部分更新）** + 结构化碰撞报告（`link_id/旧键/新键/原版本/target_id`）+ 保留全部原行原键原版本原绑定 + 等用户处置后重跑 + **不随机绑定/覆盖/静默删除** + **不引入混合版本部分重建** | §8.3.1–8.3.4 / §8.4 / §7.5 T1–T12 / R14、R15 | **Hash 契约无变更、数据模型无变更**；属对设计 §2.4/§2.9「碰撞→ambiguous/conflict 报告」**未定义处的口径收紧**（用户本轮已裁决）。差异如实记录于 §8.3.3，**建议实施后另批同步设计措辞，本轮不改设计文档** |
| **B Frontmatter 绑定提示覆盖** | **先聚合再判定**：单一有效→恢复；多提示同 target→恢复；多有效 target 矛盾→**conflict**；无有效目标→回退标题解析；**不允许 last-write-wins**；**保留冲突双方信息 + warning** | §6.5 / §3① / §7.6 H1–H12 / R16、R17 | **无**（设计「target_id 优先恢复 / 无效回退」的确定性化） |

**第二轮（最终）独立审查裁决 E1–E3 + R3 配套 E4/E5 + R3.1 必须补充项 E6（均已批准或已按要求落实，不再开放）**：

| # | 议题 | **裁决结果（已批准）** | 落实章节 | 设计契约变更 |
|---|---|---|---|---|
| **E1** | **全局版本同构守卫**（阻塞项） | 局部 `list_links(item.id)` 检查**不足以证明全表同构**（`all([])==True` 反例）。必须：① 预检**覆盖整张 `knowledge_link` 表**；② **空表允许初始化**；③ 任何现存行版本 ≠ 常量 → **拒绝本次链接写入**；④ **409 + 稳定码 `link_version_mismatch`**；⑤ **检查与写入同一事务边界**；⑥ **不宣称跨进程互斥**，保留静默期/单写者运维限制；⑦ **不新增迁移、不改 A1-01 端口契约**；⑧ **优先 backend 装配层实现**，避免 Core 每次同步全量加载；⑨ 七类新增测试（空表/同版本/异版本/**审查反例**/混合/双方言/拒绝后全表逐列零变化）。同时修正 §8.4「任何同步尝试被守卫拒绝」的笼统表述 | **§8.4.1–8.4.8（重写）** / §8.3.5 / §6.4 / §3②③④ / §7.5 **T13–T21** / §7.4 / §7.7 / §8.5.3 / §9 / R14、R20、R21 | **无**（Hash/表/列/约束/端口签名/V1 行为均不变；新增防御性预检与职责分层） |
| **E2** | **导入绑定的空间语义**（阻塞项） | 采纳建议口径：**有效稳定 UUID 代表历史绑定意图**；目标存在 → 恢复绑定并**按当前 source/target 空间关系重算 `cross_space`**；同空间 → `resolved`+False；跨空间 → **`cross_space`+True**，**不得伪装成普通 resolved**；archived 目标与 **D7 显式绑定**一致；目标不存在 → 回退标题解析；**无效 UUID / 目标不存在 / 空间不匹配三类语义分离**，各留清晰 warning 与 resolution。六类新增测试（同空间/跨空间/源无空间目标有空间/archived/不存在/**顺序无关**），Core+SQLite+PG 覆盖适用部分 | **§6.6（新增）** / §6.5 伪代码与矩阵 / §6.2 新增两行 / §3② / §7.6 **H13–H20** / §7.2 J 扩展 / §7.4 / §9 / R22 | **无**（设计 §2.4 未定义 `cross_space` 重算，属未定义处口径明确，用户已给建议并采纳；不改交换字段/Hash 定义/端口）。**建议实施后另批同步设计措辞，本轮不改设计文档** |
| **E3** | **人工绑定的交付边界** | **保留 D8，不新增写 API**。A1-03 交付**候选发现 + 只读查询**；显式绑定规则**可在 Core 明确并测试**，但**无可供用户操作的 HTTP 写入口**；人工绑定 API 与前端交互属**后续里程碑**；**不得把尚未通过 HTTP 实际执行的人工绑定描述为已交付功能** | **§6.7（新增）** / §6.2 交付边界注 / §7.2 L③④、J 标注 / §7.7 路由守护 / §8.5.3 / §13.1 / §13.2 / R23 | **无**（交付范围口径，不改任何契约） |
| **E4** | **R3 配套调整（**已获批准**；R3.1 补门禁 C）** | 全局守卫使 R2「Core 逐行 `update_link` 执行重建」自相矛盾（升级死锁 / 绕过开关 / 改端口三难）→ 重建拆为 **Core `plan()` 只算计划（零写入零文件 IO）+ backend `apply_link_key_plan()` 单事务原子执行**。**上一轮独立审查结论：职责拆分已批准，但必须补充门禁 C（计划新鲜度）** → R3.1 落实为 **门禁 A/B/C + 十步执行顺序 + 不新增计划摘要**（见 E6） | **§8.3.5** / **§8.3.6–8.3.8（R3.1 新增）** / §8.3.2 伪代码 / §8.3.4 / §8.4.4 / §5.2 问 6、问 7 / §3②③ / §4.1 / §7.5 分层口径 / T12、T21 / **T22–T40** | **无**（Hash/数据模型/端口签名/V1 行为均不变；属 Core↔backend 职责分层调整，与 D10 同向）。**拆分本身不再重新讨论** |
| **E5** | **R3 实测新发现（非审查指出；**已批准，本轮不再讨论**）** | `SQLAlchemyKnowledgeRepository.list` 在 `space_id=None` 时**不加 where 过滤 → 返回全库**；若直接用作个人空间源条目的候选集会**自动跨空间绑定**。处置：Core 侧**再做精确空间等值过滤**（`None==None`），不改 V1 仓库、不改端口 | **§2.5⚠** / §6.4 伪代码 / §7.2 J 扩展 / §9 / R24 | **无**（Core 侧过滤，V1 行为零改动）。**R3.1 不重新设计、不改变其批准状态** |
| **E6** | **★ R3.1 本轮唯一目标：重建计划新鲜度门禁 C + 事务缓存生命周期**（上一轮审查对 E4 的必须补充项 + §五 缓存修订） | ① **门禁 C**：`plan()` 携带覆盖**全表每一行（含 no-op）**的 `row_snapshots`（`link_id`/`source_id`/`old_key`/`old_version`/`target_title`/`alias`）；apply **在执行事务内重读当前全表 6 列**，交 Core 纯函数 `check_plan_freshness()` 逐项比对；**10 类不一致**（删除/新增/`source_id`/键/版本/`target_title`/`alias`/未覆盖/重复 `link_id`/篡改）任一命中 → **`refused_stale_plan` + 数据库零写入 + 不允许部分更新 + 不允许忽略不一致行继续 + `requires_replan=True` + 必须重读全表重生成计划**；② **十步执行顺序**（开事务→A→重读→B→C→新键唯一性→批量更新→写后复核→提交→任一失败整体回滚），**plan 阶段检查不得当作 apply 阶段安全保证**；③ **不新增确定性计划摘要**（frozen 模型 + 双向覆盖 + 精确比对 + **每行新键重算**四机制强于摘要；**不用内置 `hash()`**、不改三 Hash 契约、不进交换载荷、不新增数据库字段）；④ **撤回 R3 事务内缓存 → 无缓存**（Session ≠ 事务；commit/rollback 后 autobegin；savepoint 边界；**每次受守卫写入重新单列 DISTINCT**；Core 纯函数 / backend 查询分层不变）；⑤ **T22–T40 追加**（13 项要求全覆盖 + 6 项配套），**T20③ 期望值修订而非删除测试**，全部【待验证】 | **§8.3.6 / §8.3.7 / §8.3.8（新增）** / **§8.4.3（1）–（6）重写** / §8.3.4 / §8.3.5 / §8.4.4 / §8.4.7 / §8.4.8 / §8.5.5 / §8.5.6（9→12 项）/ **§7.5.1（新增 T22–T40）** / §7.7 / §7.8 / §9 / §10 **R25、R26** / §12 / §13 / §15 **REV-23–REV-26** / **§3②③ · §4.1 · §4.2 · §5.2 问 6·问 7 · §7.4（全文一致性清扫，REV-26）** | **无**（Hash 契约 / 数据模型 / 迁移 / A1-01 端口签名 / V1 行为**全部零变更**；新增 Core 内部值类型与纯函数 + backend 事务内重读，属正确性加固） |

---

## 12. 分步实施顺序（每步都有真实验证门禁，不一次性写完）

> 每步完成后：① `git status` + `git diff --stat` 自检 ② 核对 §1.3 指纹（不该变的必须不变）③ 跑对应测试 ④ 记录真实输出 ⑤ 才进入下一步。

| 步 | 内容 | 验证门禁 |
|---|---|---|
| **A1-03a** | 纯文本层 `markdown/links.py`：规范化 + 两个键（D2）+ WikilinkParser + 排除矩阵（含 `![[embed]]`，D6）+ 同键合并 + **`group_hints_by_title_key` 提示聚合（问题 B）** + 长度/控制字符守卫 | `test_markdown_links.py` 全通过（含 §7.3 提示聚合分组矩阵）；`ruff check`；独立性守护（此时还没接端口）；**6 个冻结文件指纹 OK** |
| **A1-03b** | ABC 声明（`markdown/__init__.py` **只追加**）+ `helpers.py` 追加 `InMemoryLinkRepository`（**无缓存，每次受守卫写入重新扫描**，§8.4.3（3））+ `link_service.py` 的 Resolver（**archived 排除 / 自链接允许**，D7；**候选精确空间等值过滤**，§2.5⚠/R24）/ BindingFirstSync（**Core 局部守卫作为纵深防御**，§8.4.3）/ BacklinkQuery / Reresolve + **全局同构判定纯函数 `check_global_version_homogeneity()`** + **R3.1 计划新鲜度判定纯函数 `check_plan_freshness(plan, current_rows)`**（含**每行新键重算**与 **no-op 行校验**）+ **值类型 `LinkRowState` / `PlanFreshnessResult` / `LinkStaleReason`**（frozen + tuple，§8.3.6/§8.3.8）。两个纯函数均为 **Core 单一事实来源**，backend 与 InMemory 双实现共用 | `test_markdown_link_service.py`：解析规则矩阵 + **场景 A/B/C/E/K/L**（Core 层）+ 同步不变量 + **T11 局部守卫（纵深防御口径）** + **T13/T14/T15/T16/T17 的纯判定部分**（含**审查反例**：source 无链接行但全表有 v1 → 纯函数返回拒绝）+ **T16 局部守卫确实放行而全局拒绝的双层对照** + **J 的 None 空间不得绑定 project 条目断言**；**R3.1：T22–T29 / T35–T38 的 Core 纯函数判定部分**（十类不一致 → 稳定 `reason_code`；双向覆盖；`link_id` 唯一；原始 Unicode 精确比对不做规范化；新键重算发现篡改；no-op 盲区反证；frozen 不可变 + 确定性序列化）；A1-02 全部 293 用例仍通过；**D3 签名守护（方法名集合恰为 A1-01 的 10 个 + 全部签名不变）**；**单一事实来源守护**（不得出现第二套同构判定或新鲜度判定实现）；**无缓存守护 + 纯函数无 IO 守护**；6 冻结指纹 OK |
| **A1-03c** | `LinkImportRestorer`（**先聚合再判定**，§6.5；**按当前空间关系重算 resolution/cross_space**，§6.6）+ `LinkKeyRebuild.plan()`（**只算计划、零数据库写入、零文件 IO**，§8.3.2/§8.3.5；**R3.1：产出覆盖全表每一行（含 no-op）的 `row_snapshots` + `observed_row_count` + `requires_replan`**）+ 结构化报告与计划模型（`LinkRebuildPlan`/`LinkKeyUpdate`/`LinkRebuildReport`，D10；**全部 frozen + tuple**） | **场景 D/F/G/H/I/J/M**（Core 层）；**§7.5 T1–T12 全矩阵的 Core 计划层部分**（含碰撞单组/多组/不同 target/幂等/计划完整性/报告结构/**T12 零文件 IO + 零数据库写入行为守护**）；**T21 计划层部分**（`refused_mixed_version` / `refused_collision` 均为计划终态，`plan()` 不触任何写方法）；**R3.1：T38 计划不可变性与确定性序列化 + `row_snapshots` 覆盖全表（含 no-op 行）断言 + 计划中不存在摘要字段、不使用内置 `hash()`**；**§7.6 H1–H20 全矩阵**（H13–H20 空间语义 + 顺序无关 + **H20 跨空间再导出 payload_hash 变化的诚实断言**）；**三 Hash 不变性硬测试（F 的固定非空 review payload 口径）**；导出文本不含派生键断言；**服务层不变量 `cross_space=True ⟺ resolution=cross_space`** |
| **A1-03d** | backend `SQLAlchemyLinkRepository`（含**读取侧防御映射**，D12；含**全局版本同构预检**：单列 `SELECT DISTINCT` + **同一事务内、写入之前** + **R3.1 无缓存：每次受守卫写入重新执行** + **可证明豁免**，§8.4.3）+ 装配 + **`apply_link_key_plan()` 独占单事务原子执行（十步顺序：开事务 → 门禁 A 版本漂移 → 重读当前全表 6 列 → 门禁 B 全覆盖与无重复新键 → **门禁 C 逐行新鲜度（调用 b 的纯函数）** → 新键唯一性再验证 → 批量更新 → 写后复核 → 提交 → 任一失败整体回滚）**，§8.3.5/§8.3.6/§8.3.7 + **`persist_rebuild_report()` 落盘助手**（D10） | `test_links.py`（真实 SQLite）：仓库契约 + 唯一约束（**T7 真实 IntegrityError**）+ FK + **场景 A–M 全套** + **T1–T12 DB 级逐列快照/故障注入回滚** + **T13–T21 全部 DB 级断言**（空表初始化 / 同版本放行 / 异版本拒绝 / **T16 审查反例真实拒绝且零写入** / 混合全拒 / **T19 拒绝后全表逐列 + 三 Hash + 导出字节零变化** / **T20 治理写入与 DELETE 豁免 + 【R3.1 修订】DISTINCT 查询次数 == 受守卫写入次数 + 回滚后重新预检** / **T21 门禁 A/B 真实拒绝**）+ **R3.1：T22–T31 / T35–T37 / T39 的 DB 级断言**（十类过期计划**真实拒绝 + 零写入**、`requires_replan`、`stale_reasons` 内容、**T30 全表逐列 + `knowledge_item` 全列 + 三 Hash + 导出字节零变化**、**T39 十步顺序守护 + 写后非键列与重读值逐列相等 + 故障注入整体回滚 + 事务所有权**）+ **T32/T33/T34/T40 事务生命周期**（commit 后重新预检 / rollback 后重新预检 / 预检计数 == 受守卫写入次数 / savepoint 边界）+ 报告落盘往返；`test_links_pg.py`（真实 PG）**同断言**（**T18 + T31 双方言各自验证**）；0006 up/down 仍通过；**V1 `DELETE /knowledge/{id}` 在版本窗口内不被误伤** |
| **A1-03e** | 同步挂接 `routes/knowledge.py` 四处 + **删除路径入链同事务显式降级修复（§2.6/R13/D12）** + **3 个只读 GET 端点（D8，不加写端点；**R3.1：`refused_stale_plan` 本轮不做 HTTP 映射**，§8.3.6）** + schemas + router 注册 + **409 `link_version_mismatch` 稳定错误码映射**（仅常规链接写入路径；**DELETE 不阻断**，§8.5.3） | TestClient 真实调用：create/draft-PATCH/DELETE/extract 后链接正确；**删除目标后读取出链/反链不抛异常且 resolution=missing**；**手工构造非法行验证读取侧防御映射，且实体校验器未被弱化**；**active PATCH 202 分支链接未变**；**H17 archived 绑定经真实 HTTP PATCH 保留（不是建立）**；**L④ 同口径**；路由无冲突（静态先于动态）；**路由守护：链接 router 的 (method, path) 集合恰等于 3 个 GET，`knowledge.py` 端点集合不变**（§6.7）；**R3.1：断言不存在重建/绑定的 HTTP 写入口，`refused_stale_plan` 只经结构化报告与测试断言验证**；V1 知识/审核/检索 API 回归全通过 |
| **A1-03f** | 守护扩展 + **§8.5.6 兼容性验证清单十二项（R3.1：9 → 12）** + 全量回归 + 验收报告 | 守护子进程含新模块；`ruff check`；根级 pytest **默认 SQLite** 与 **真实 PG** 各一遍（对照 644/685 基线只增不减、PG 0 skipped）；**6 冻结文件指纹 OK + A1-02 293 用例全通过**；**21 文件 SHA-256 全 OK + baseline patch `cmp` 逐字节相同 + 零锁定文件漂移**；**R3.1 守护：新鲜度规则单一来源 / 无缓存 / 计划 frozen 且无摘要字段 / 事务所有权（仓库不 commit/rollback/begin_nested）/ 三 Hash 与白名单零改动**；前端**未触碰**则说明未重跑理由；写 `docs/acceptance/V2-A1-03-*.md`（如实区分已验证/有条件/未验证，**未运行的一律不写 PASS**；**L③/J 的人工绑定必须写成「Core 层显式绑定规则已验证（A1-03 无 HTTP 写入口）」，不得写成已交付用户功能**，§6.7；**门禁 C 必须写成「过期计划拒绝 + 零写入已验证」，不得写成「并发安全/互斥已保证」**，§8.4.8） |

**停止点**：A1-03f 完成后**停止**，更新 MILESTONES 需与验收报告一并提交审查，**不自行宣布进入 A1-04**。

**R3 新增的顺序约束（不得颠倒；R3.1 追加 5–8）**：

1. **b 必须先于 d**：全局同构判定的**纯函数**在 Core（b）落地，backend 仓库预检（d）与 `InMemoryLinkRepository`（b）**调用同一个函数**；不得在 backend 里另写一套判定逻辑（§7.7 单一事实来源守护）。
2. **c 必须先于 d**：`plan()` 产出的 `LinkRebuildPlan` 是 `apply_link_key_plan()` 的唯一输入；**Core 侧不得先实现任何逐行写入版本**（§8.3.5），否则 d 阶段会被自己的守卫拒绝而形成死锁。
3. **d 必须先于 e**：409 映射依赖仓库真实抛出 `LinkNormalizationVersionMismatch`；不得先在路由层写死一个假的 409 分支。
4. **每步都不得为了让本步通过而临时关闭守卫**：不设「跳过版本检查」的开关/环境变量/参数（§8.4.4、R21）。若某步被守卫拒绝，说明该步实现有误，修实现而不是放宽守卫。
5. **（R3.1）新鲜度纯函数与快照模型必须先于 apply**：`check_plan_freshness()` + `LinkRowState`（b）与 `plan().row_snapshots`（c）**必须先落地并被 Core 层测试锁定**，d 阶段的 `apply_link_key_plan()` 才允许实现；**不得在 backend 内另写一份逐行比对逻辑**（§7.7 单一事实来源守护）。
6. **（R3.1）apply 必须独立重新验证，不得复用 plan 阶段结论**：d 阶段实现里**门禁 A/B/C 一律在执行事务内重新执行**；**不得把 `plan()` 的同构预检、碰撞检测、覆盖计算结果当作放行依据**（§8.3.5 第 7 点 / §8.3.7）。唯一可复用的是 plan 携带的**快照数据**，而它是**被校验的对象**。
7. **（R3.1）十步顺序不得颠倒、不得省略**：开事务 → A → 重读 6 列 → B → C → 新键唯一性再验证 → 批量更新 → 写后复核 → 提交 → 任一失败整体回滚（§8.3.7）。**任一门禁失败时其后步骤一律不执行，尤其不得出现任何 UPDATE 语句**（T39 顺序守护）。
8. **（R3.1）不得引入缓存、不得放宽比对、不得部分更新**：❌ 不为省查询而加回任何版本集合缓存（§8.4.3（3））；❌ 不在比对前做 NFKC/casefold/空白折叠（§8.3.6 规则 2）；❌ 不实现「忽略不一致行后继续」或「只更新一致行」的分支（T30 零写入反证）；❌ 不新增计划摘要/内置 `hash()`/数据库字段（§8.3.8）；❌ 本轮不加 `SELECT … FOR UPDATE`/表锁（§8.4.8，**【待审批】**）。若某步被门禁 C 拒绝，**修实现或重生成计划，而不是放宽门禁**。

---

## 13. 验收标准（可核验清单）

### 13.1 必须真实验证通过（A1-03 范围内）

> **诚实性前置声明**：本清单是**实施阶段的验收门槛**，**不是本轮（R3.1）的执行结果**。R3.1 只修订计划文档，**未写业务代码、未新增测试文件、未运行任何测试套件、未安装依赖、未改迁移**，因此下列每一项当前状态均为 **⏳ 未验证**，**不得写成 PASS**。§7.8 的用例规模（~580）同样全部为估算，**§7.5.1 的 T22–T40 全部为【待验证】**。
> **措辞纪律（E3）**：凡涉及「人工显式绑定」的条目，验收报告必须写成「**Core 层显式绑定规则已验证（A1-03 无 HTTP 写入口）**」，**不得**写成「用户可显式绑定 archived / 跨空间候选」这类已交付用户功能的表述（§6.7）。
> **措辞纪律（R3.1 · E6，新增）**：凡涉及门禁 C 的条目，验收报告必须写成「**过期计划被拒绝 + 数据库零写入已验证**」，**不得**写成「重建并发安全 / 已实现互斥 / 计划不可能过期」——**残余窗口（apply 事务内重读→提交）本轮未关闭**（§8.4.8 第 2 条）。凡涉及预检成本的条目，必须写成「**无缓存，每次受守卫写入各一次单列扫描**」，**不得**沿用 R3 的「每事务一次」表述。

- [ ] NFKC+casefold+空白折叠规范化：全角/半角、合字、圈码同键；**NFC 反例**证明必须 NFKC；原始字面未被覆盖。
- [ ] 两个键区分正确：`[[B]]` 与 `[[B|别名]]` 行身份键不同、解析标题键相同、都绑定 B。
- [ ] 解析排除矩阵逐行通过（围栏/行内/转义/未闭合/空/嵌套/跨行/超长/控制字符/`![[embed]]`）。
- [ ] 碰撞：多候选→`ambiguous` 且 `target_id is None`；同源同键合并保留首现字面；意图矛盾→`conflict`；**绝不随机绑定**。
- [ ] 解析规则：当前空间优先 / 唯一→resolved / 无→missing 不自动跨项目 / 用户主动→cross_space / 删除→SET NULL+missing+字面留存 / reresolve 守规则 / **自动候选排除 archived 但允许显式绑定（D7）** / **自链接允许（D7）** / **候选集在 Core 侧再做精确空间等值过滤：`space_id=None` 的源条目绝不把 project 条目纳入候选（§2.5⚠ / R24 / J 扩展）**。
- [ ] **场景 A**：B 改名后 A 仍绑定 B 稳定 ID，反链命中，导出 target_id 正确。
- [ ] **场景 B**：相似标题触发 ambiguous/conflict，不随机绑定。
- [ ] **场景 C**：改无关正文连续保存，绑定不丢、不重解析、ID 稳定。
- [ ] **场景 D**：导出→毁索引→导入，依稳定 ID 恢复；target_id 失效时回退标题解析 + unresolved_links。
- [ ] **场景 E**：连续 5 次同步/导入，链接行与 ID 恒定，无重复关系，**版本行数不增长**。
- [ ] **场景 F（R2 修正口径 + R3 补充）**：**无碰撞夹具**下执行**确实生效**的重建（先断言键/版本真的变了）→ `document_content_hash` 逐位相等、`document_payload_hash` 逐位相等、**固定非空审核变更 payload** 的 `review_payload_hash` 逐位相等；**导出文本字节相等**；**全部 `target_id` 保留**；`target_title/alias/resolution/cross_space/created_at` 逐行不变；**全部受影响 `knowledge_item` 行逐列完全不变（含 `updated_at`/`version`）——重建只写链接行的 `updated_at`，绝不触碰知识条目（§8.3.2 澄清）**。**不得**把 review_hash 描述为完整文档状态 Hash，**不得**传空 payload。
- [ ] **场景 G + §7.5 T1–T12（问题 A）**：无碰撞正常重建 / 单组碰撞 / 多组碰撞 / **不同 target_id 碰撞** / **碰撞导致整体回滚（含故障注入）** / **回滚前后 DB 全表逐列与三 Hash 完全一致** —— 全部真实通过；碰撞时**零写入**、报告含 `link_id/old_key/new_key/old_version/target_id`；**无合并/覆盖/静默删除/随机重绑**；**无混合版本部分重建**；T7 证明双方言重复键**真实抛 IntegrityError**。**R3 分层口径**：Core 断言 `plan()` 的终态与计划内容（零写入），DB 断言 `apply_link_key_plan()` 的真实写入/快照/回滚。
- [ ] **§7.6 H1–H12（问题 B）**：重复提示 / 矛盾提示 / 无效 UUID / 目标不存在 —— 全部真实通过；**先聚合再判定、无 last-write-wins**；矛盾进 `conflict` 且**双方信息全保留 + warning**；无有效目标回退标题解析；**提示顺序打乱结果不变**；孤儿提示不建行。
- [ ] **§7.6 H13–H20（R3 · E2 导入空间语义）**：同空间 UUID 恢复（含双方均 `None`）→ `resolved` + `cross_space=False`；**跨空间 UUID 恢复 → `cross_space` + `cross_space=True`，绝不出现 `resolved` + `False`**；源无空间/目标有空间、源有空间/目标无空间**双向**均判跨空间；**目标 archived 但 UUID 有效 → 按空间关系恢复 + archived warning（与 D7 一致）**；目标不存在 → 回退标题解析（**不是 conflict、不是 cross_space**）；**混合提示种类下顺序无关**；**H20 再导出 Hash 诚实口径**（同空间往返三 Hash 不变；跨空间导入后 `payload_hash` **允许变化**并如实断言，`content_hash` 不变）+ 导出白名单 + 固定非空 review payload。**服务层不变量 `cross_space=True ⟺ resolution=cross_space` 有硬断言**（实体校验器不覆盖此组合）。**持久化列值 / 事务 / HTTP 类断言在 SQLite 与真实 PG 各跑一遍**；纯判定类断言可只在 Core。
- [ ] **场景 K（D7 自链接）**：`[[A]]` 在 A 内正常解析为 `resolved` 并绑定自身稳定 ID，反链含自身，连续保存 ID 稳定。
- [ ] **场景 L（D7 archived）**：自动解析排除 archived（唯一 archived 候选→missing）；候选接口带 `status` 标注列出 archived；**L③「显式选择 archived 允许绑定」= Core 层规则已验证（A1-03 无 HTTP 写入口，不得写成已交付用户功能）**；**L④ 显式绑定由 Core/仓库夹具建立，再经真实 HTTP PATCH 验证「保留」而非「建立」**；显式绑定后连续保存不被自动解绑；active+archived 同键时不误判 ambiguous。
- [ ] **全局版本同构守卫（R3 · E1 / §8.4.1–8.4.8 / T13–T21；**R3.1 修订预检次数口径**）**：**空表允许创建第一条链接（T13）**；全表 v1 + 常量 v1 正常写入（T14）；全表 v1 + 常量 v2 **拒绝写入**（T15，v2 仅测试夹具）；**审查反例 T16：当前 source 无任何链接行、其他 source 存在 v1 行、常量 v2 → 局部守卫确实放行（`all([])==True`）而全局预检真实拒绝，零写入，重建后恢复**；**混合 v1/v2 全部拒绝（T17）**；**T18 SQLite 与真实 PG 各自验证**；**T19 拒绝后全表逐列 + 三 Hash + 导出字节零变化**；**T20 可证明豁免（治理写入不被误伤、DELETE 不阻断且保持同构）+ 【R3.1 断言修订】单列 DISTINCT 查询次数 == 受守卫写入次数（**无缓存**，撤回 R3 的「每事务一次」）+ 回滚后重新预检**；HTTP 返回 **409 + 稳定码 `link_version_mismatch`**（**不回传异常文本/版本明细/link_id**）；恢复同构后保存正常；**检查与写入同一事务边界**（仓库只 `flush()`，路由 `commit`）；**不宣称跨进程互斥**，静默期/单写者运维限制保留（§8.4.7/§8.4.8）。
- [ ] **重建执行边界（R3 · E4 / §8.3.5 / T12、T21；**R3.1 补门禁 C**）**：`LinkKeyRebuild.plan()` **零数据库写入 + 零文件 IO**（monkeypatch 写方法与 `open`/`Path.write_text`/`Path.mkdir` 后仍成功返回计划）；`apply_link_key_plan()` **门禁 A 版本漂移 → `refused_version_drift`**、**门禁 B 计划未全覆盖或新键重复 → `refused_incomplete_plan`**、**门禁 C 计划过期 → `refused_stale_plan`**，三者均**零写入**；正常路径**独占单事务只写 3 个非交换列** + **写后复核**失败整体回滚；**不存在任何「跳过守卫」开关**；**Core↔backend 职责分层不新增端口方法、不改 A1-01 的 10 个签名**。
- [ ] **★ 门禁 C：逐行计划新鲜度（R3.1 · E6 / §8.3.6 / T22–T31、T35–T37）**：`plan()` 携带**覆盖全表每一行（含 no-op 行）**的 `row_snapshots`（`link_id`/`source_id`/`old_key`/`old_version`/`target_title`/`alias`）+ `observed_row_count`；apply **在自己的执行事务内重读当前全表 6 列**并交 **Core 纯函数 `check_plan_freshness()`** 判定；**10 类情况全部真实拒绝**：① 记录被删除（`row_deleted`）② 新增链接记录（`row_added`）③ `source_id` 变化（`source_id_changed`）④ `normalized_link_key` 变化（`key_changed`）⑤ `link_normalization_version` 变化（`version_changed`）⑥ `target_title` 变化（`target_title_changed`）⑦ `alias` 变化（`alias_changed`）⑧ 存在计划未覆盖的记录（`row_not_covered` / `noop_row_requires_update`）⑨ 计划内重复 `link_id`（`duplicate_link_id_in_plan`）⑩ 计划被篡改（`new_key_mismatch` / `new_version_mismatch`，由**每行新键重算**发现）；**任一不一致 → 整个计划拒绝 + 稳定状态 `refused_stale_plan` + 数据库零写入 + `updated=0` + `requires_replan=True` + `stale_reasons`（reason_code/link_id/field/expected/actual）**；**不允许部分更新、不允许自动忽略不一致行后继续、不允许拒绝后重试旧计划**（必须重读全表重生成，§8.4.7 步 3c）；**比对为原始 Unicode 精确等值，比对前不做 NFKC/casefold/空白折叠，`None` ≠ `""`**；**双向覆盖（计划↔当前全表），不只比较计划中已存在的行**；**T30 拒绝后全表逐列 + `knowledge_item` 全列 + 三 Hash + 导出字节完全不变**；**T31 SQLite 与真实 PG 各跑一遍**；**T37 反证 no-op 行盲区真实存在且已被堵住**。
- [ ] **★ 十步执行顺序与事务所有权（R3.1 · E6 / §8.3.7 / T39）**：apply 内实际顺序为 **① 开启事务 → ② 门禁 A 全局版本同构 → ③ 重读当前全表必要字段 → ④ 门禁 B 覆盖范围与唯一性 → ⑤ 门禁 C 逐行快照一致 → ⑥ 新键唯一性再验证 → ⑦ 批量更新 → ⑧ 写后复核版本同构与唯一约束 → ⑨ 全部通过后提交 → ⑩ 任一环节失败整体回滚**，有**调用序列守护**；**任一门禁失败时其后步骤一律不执行，尤其不得出现任何 UPDATE 语句**；**状态优先级 A→B→C**（`refused_version_drift` / `refused_incomplete_plan` / `refused_stale_plan`），**`(source_id,new_key)` 重复归 B、重复 `link_id` 归 C**；**写后非键列与第 ③ 步重读值逐列相等**（不是与 plan 生成时刻值比）；**apply 独占 `with session.begin():`，不得在已有活动事务或 savepoint 内被调用**；**plan 阶段的检查未被当作 apply 阶段的安全保证**（A/B/C 全部独立重新执行）。
- [ ] **★ 不新增计划摘要（R3.1 · E6 / §8.3.8 / T38）**：`LinkRebuildPlan`/`LinkRowState`/`LinkKeyUpdate` 为 **frozen Pydantic 模型 + `tuple` 字段**（赋值抛异常、`.append` 失败）；**apply 前后 `plan.model_dump(mode="json")` 字节完全相同**；同一输入两次 `plan()` 序列化字节相同（**确定性**）；**模型中不存在任何摘要/digest 字段**、链接模块**不使用 Python 内置 `hash()`**；**`document_content_hash` / `document_payload_hash` / `review_payload_hash` 契约与 `canonicalization_version` 零变更**；**计划摘要不混入文档交换载荷/白名单**；**不新增数据库字段/表/索引/迁移**。完整性由**四机制**保证：frozen 不可变 + 双向全覆盖与 `link_id` 唯一 + 6 字段精确比对 + **每行新键重算**（**强于摘要**，因摘要无法发现「数据库已变而计划未变」）。
- [ ] **★ 事务缓存生命周期：无缓存策略（R3.1 · E6 / §8.4.3（1）–（6）/ T20③、T32、T33、T34、T40）**：**不存在任何版本集合缓存**（无实例属性/`lru_cache`/模块级字典/ContextVar，有结构守护）；**每次受守卫写入重新执行单列 `SELECT DISTINCT`**，**k 次写入 → k 次预检**（T34 计数断言，k=1/5/20）；**治理豁免写入与删除 → 0 次预检**；**`apply_link_key_plan` 批量写 → 门禁 A 预检恰 1 次**（不逐行预检）；**`session.commit()` 后的新事务必须重新预检**（T32，且断言 Session 对象自始至终同一个）；**`session.rollback()` 后的新事务必须重新预检**（T33，含「rollback 撤销本事务写入后集合不含被撤销行」）；**savepoint/nested 边界**（T40：`begin_nested()` 内照常重新预检、`nested.rollback()` 后读到回滚后真实集合、`nested.commit()` 不结束外层事务、apply 不得在 savepoint 内调用）；**不得仅以 Session 对象是否存在判断缓存有效性**；**Core 只提供纯函数、backend 负责数据库查询**的分层保持，**端口签名零变化**；**SQLite 与真实 PG 各跑一遍**；成本如实记录为 **k 次单列扫描**（§8.4.8 第 4 条）。
- [ ] **D10 Core 零文件 IO + 零数据库写入**：monkeypatch `open`/`Path.write_text`/`Path.mkdir` 抛异常后 `plan()` 仍成功返回报告/计划；backend `persist_rebuild_report()` 落盘读回与报告一致。
- [ ] **§8.5.6 前后兼容性清单十二项（R3.1：9 → 12）**全部真实通过（V1 纯文本 / A1-02 文件 hash 不变 / 新文件旧 codec 可读 / V1 全量回归 / 0006 up/down 双方言 / **全局**版本守卫含 T16 反例 / **DELETE 与治理写入豁免 T20** / **跨空间导入列值 H14–H16** / **路由与端口守护** / **R3.1 第 10 项：过期计划十类拒绝 + 零写入（T22–T31，双方言）** / **第 11 项：commit/rollback 后重新预检 + 预检计数 == 受守卫写入次数（T32–T34）** / **第 12 项：savepoint/nested 边界（T40）**）。
- [ ] **交付边界守护（R3 · E3 / §6.7）**：链接 router 的 `(method, path)` 集合**恰等于 3 个只读 GET**（links / backlinks / resolve-candidates），**无任何 POST/PATCH/PUT/DELETE**；`routes/knowledge.py` 端点集合与 V1 一致（仅内部挂接，不新增端点）；**A1-03 验收报告不得把人工绑定写成已交付功能**。
- [ ] 双方言唯一约束（含 alias NULL/非 NULL）、FK CASCADE/SET NULL、反链按稳定 ID、长键边界行为一致 —— **真实 SQLite + 真实 PG 各自跑通**。
- [ ] 同步挂接四条路径正确；**active 202 分支不同步**；同事务失败整体回滚。
- [ ] **删除目标后链接行可读**：`target_id=NULL` 时 `resolution=missing`（写入侧降级 + 读取侧防御映射），出链/反链查询**不抛 ValueError**，原始字面留存 —— SQLite + PG 各验一遍（§2.6 / R13 / D12）。
- [ ] Core 独立性守护 + 零新增依赖守护通过；6 个新 ABC 不可实例化（**R3：`LinkKeyRebuild` 的 ABC 方法名为 `plan()`，不再是 `rebuild()`**）；**全局同构判定纯函数单一事实来源守护**（backend 与 InMemory 调用同一函数，无第二套实现）；**空间一致性守护**（`cross_space=True ⟺ resolution=cross_space`）；**R3.1 追加守护**：① **新鲜度判定单一事实来源**（backend apply 与 InMemory 调用同一 `check_plan_freshness()`，无第二套逐行比对逻辑，且该函数无 IO/无 Session 参数/无模块级可变状态）；② **无缓存守护**（两个仓库实现均无版本集合缓存属性）；③ **计划不可变守护**（frozen + tuple + 无摘要字段 + 不使用内置 `hash()`）；④ **事务所有权守护**（apply 内只有一处 `session.begin()`；仓库实现内不出现 `commit()`/`rollback()`/`begin_nested()`）；⑤ **Hash 契约守护**（`CANONICALIZATION_VERSION` 恒 1、三 Hash 计算路径与导出白名单零改动、计划/快照/新鲜度结果不进任何交换载荷）。
- [ ] **A1-02 六个冻结文件指纹不变**（`canonical.py`/`frontmatter.py`/`codec.py` + 其三个测试文件）**+ 293 用例全通过**；`markdown/__init__.py` 仅追加且 A1-02 公共 API 行为不变；**D3 签名守护通过（`LinkRepository` 方法名集合恰为 A1-01 的 10 个、全部签名不变，仅 docstring 变化）**；**A1-01 迁移与模型用例全通过**；**V1 检索/审核/关系/版本/图/实验全量回归零回归**。
- [ ] **21 个交付文件 SHA-256 全 OK（`sha256sum -c` 在仓库根执行）+ baseline patch `cmp` 逐字节相同 + `git status --porcelain` 与基线一致**；HEAD 仍为 `6d91718`、M0 初始提交 `2d2b634` 未被改写、stash 为空。
- [ ] `ruff check` 全通过（未用 format）；`uv.lock`/`package-lock.json`/`pyproject.toml`/`package.json` **零漂移**；新增依赖 **0**（**PyYAML / KaTeX / DOMPurify / python-magic / CodeMirror 6 / react-markdown 一律未安装**）。
- [ ] 工作区未被重置/覆盖；未提交/未推送（除非用户明确指示）。

### 13.2 明确不在本轮验证（不得写成 PASS）

- ⏳ 完整导入幂等（`skipped` + ImportOrigin 持久化源 hash 比对）、跨实例默认 Draft、每文档事务/部分失败、ImportReport → **A1-04**。
- ⏳ 附件生命周期、StorageKeyLock 方言实现、GC 租约/隔离/孤儿扫描 → **A1-04**。
- ⏳ `review_payload_hash` 提案防覆盖、`proposal_version`、撤回、批准==应用校验、批准后索引同步 → **A1-05**。
- ⏳ `POST links/resolve`、`/reresolve`、`/rebuild-keys` 端点、`python -m app.ops.rebuild_link_keys` CLI 与运维包装器（备份/校验/确认/留痕门禁）→ **A1-04 / A1-T11 / A1-T14**。**D8 已裁决：本轮只交付 3 个只读 GET，不提前增加写操作 API**；**D10 已裁决：Core 只返回结构化报告，落盘助手在 backend，CLI/端点延后**；**R3/E4：Core 只产出 `LinkRebuildPlan`，真实执行由 backend `apply_link_key_plan()` 承担，其 HTTP/CLI 入口同样延后**。
- ⏳ **人工显式绑定的 HTTP 写入口（`POST /knowledge/{id}/links/resolve` 等）与前端绑定交互（候选选择面板、archived/跨空间确认对话框、冲突处置 UI）→ 后续里程碑（A1-04 写端点批次 / A2 / A1-06）**。**R3/E3 明确**：A1-03 只在 **Core 层定义并测试**显式绑定规则（D7），**没有任何可供用户操作的 HTTP 写入口**；因此「用户可显式绑定 archived / 跨空间候选」**不是 A1-03 的已交付功能**，验收报告**不得**如此表述（§6.7 交付边界表 + 措辞纪律）。L④/H17 中经真实 HTTP 验证的是**既有绑定的保留**，绑定本身由 Core/仓库夹具建立。
- ⏳ 生产环境 bump `LINK_NORMALIZATION_VERSION` 到 v2 并执行真实全量重建 → **本轮不发布 v2 规则**（v2 仅作**测试夹具**验证重建/回滚机制）；真实升级须走 §8.4.7 运维协议 + §8.4.4 重建专用门禁 + 碰撞门禁。
- ⏳ 设计文档措辞同步（两处，**均另批审批后修改，本轮不改设计文档**）：① §2.4/§2.9「碰撞→ambiguous/conflict 报告」明确为「碰撞→整体拒绝 + 结构化报告」（§8.3.3）；② **§2.4「导入 target_id 优先恢复」补充「按当前 source/target 空间关系重算 `resolution`/`cross_space`」**（§6.6，R3/E2 新增）。
- ⏳ 「按行自身版本重算键以跨版本保绑定」的增强 → **本轮不实施**（无法完整证明同步/查询/唯一约束/回滚均正确，§8.4.6 / R14）。
- ⏳ 碰撞的**用户处置 UI**（选择保留哪个绑定、编辑正文消歧）→ **A2 / A1-06**；本轮只交付结构化报告与只读候选查询。
- ⏳ 前端链接 UI、知识地图叠加 wikilink → **A2 / A1-06**。
- ⏳ 多进程严格互斥、跨平台原子操作 → 本轮不宣称（R5 诚实降级）。**R3/E1 再次明确：全局版本预检是同一事务内的防御性一致性检查，不提供跨进程互斥**；版本窗口期仍须遵守静默期/单写者运维限制（§8.4.8）。**R3.1/E6 进一步明确：门禁 C 只是漂移检测，把「过期计划可被提交」的窗口从 plan→apply 全程收窄到 apply 事务内「重读→提交」之间，该残余窗口本轮不关闭**（§8.4.8 第 2 条 / R25）。
- ⏳ **关闭门禁 C 残余窗口的行锁/表锁方案（`SELECT … FOR UPDATE`、`LOCK TABLE`、PG advisory lock、SQLite 写事务串行化依赖）→ 本轮不实施，标记【待审批】**：需要真实并发测试证明双方言语义一致且不引入死锁/长事务，属另批提议（§8.4.8 第 2 条）。**本轮不得宣称已解决并发过期问题。**
- ⏳ **确定性计划摘要（跨进程传输 / 落盘后重载计划）→ 本轮不引入，标记【待审批】**：本轮计划只在同一进程内从 `plan()` 直接传给 `apply()`，靠 frozen + 双向覆盖 + 精确比对 + **每行新键重算**四机制保证完整性，**不新增 Hash 契约**（§8.3.8）。**若将来计划需要跨进程/持久化重载，该批次必须重新评估摘要方案并单独审批**；本轮不存在该威胁面。
- ⏳ **全局预检的性能优化（版本列索引、物化视图、**带事务身份键的缓存**）→ 本轮不做，标记【待审批】**：不新增索引（§4.3）；**R3.1 已撤回 R3 的「仓库实例级事务内缓存」**（Session ≠ 事务，失效条件无法证明，§8.4.3（1）（2）），改为**无缓存、每次受守卫写入重新单列扫描**；O(L) × k 的成本如实记录于 §8.4.8 第 4 条。若未来链接规模成为瓶颈，另批评估「事件钩子 + 事务身份键」的缓存或版本元数据表，**须单独审批 + 真实并发测试**，**不得为省一次查询牺牲正确性**。
- ⏳ **`refused_stale_plan` 的 HTTP 错误码映射与运维 CLI 入口 → 本轮不做**（D8：只交付 3 个只读 GET；重建 HTTP/CLI 属 A1-T11/A1-T14）。门禁 C 的拒绝语义本轮**只经结构化报告 + 真实测试断言**验证（§8.3.6 / §8.4.7 步 5）。

---

## 14. 结论与等待事项（R3.1）

A1-03 的全部数据基础（表/列/约束/索引/实体/端口）在 A1-01 已就绪，编解码与三 Hash 在 A1-02 已就绪，**实施不需要新迁移、不需要新依赖、不需要修改 V1 任何服务类**。核心工作是：纯文本解析与规范化（Core）→ 端口驱动的解析/绑定优先同步/恢复/重建计划服务（Core）→ SQLAlchemy 仓库、全局版本预检与重建原子执行、装配挂接（backend）→ 三层真实测试。

**关于 Hash 问题，结论不变且更强**：设计**没有冲突**——`normalized_link_key` 与 `link_normalization_version` 本就只存在于链接行（派生索引），不在 §2.2.3 交换载荷中。R2 把重建收窄为**只写这两个非交换列、绝不重解析、绝不改 resolution**，并在有碰撞时**整体拒绝零写入**；R3 进一步把重建拆为 **Core `plan()` 零写入 + backend 单事务原子执行**；**R3.1 再补门禁 C（逐行计划新鲜度）与十步执行顺序，并论证不新增计划摘要**，因此**键重建在任何路径下都不会改变文档交换身份**，也不会留下混合版本或「部分行已更新」的中间态。这条由场景 F（无碰撞、确实生效的重建 + 三 Hash 逐位相等 + 导出字节相等）、场景 G/T1–T12（碰撞拒绝 + 全表逐列零变化）与 **T22–T40（过期计划拒绝 + 全表逐列零变化 + 计划不可变 + 三 Hash 契约零改动）**三向锁定，外加导出白名单守卫（R1）。`resolution` 参与 payload_hash 的残留语义按 **D1 裁决保留，不改 Hash 契约**；**R3.1 明确不引入任何新的 Hash 契约**（§8.3.8）。

**R3 对导入 Hash 口径的诚实补充（E2）**：跨空间 UUID 恢复会把 `resolution` 从文件里的字面重算为 `cross_space`，而 `resolution` 在交换载荷内（D1），因此**跨空间导入后再导出，`document_payload_hash` 允许变化**；`document_content_hash` 不变（正文未动）。同空间往返三 Hash 均不变。这一点由 **H20 双向如实断言**，**不宣称「任何导入往返 Hash 恒定」**（§5.2 问 7 第 7 点 / §6.6）。

**R1 稿的两处既有隐患处置已获裁决**：① `delete_links_of_item` docstring 与绑定优先矛盾 → **D3：仅改 docstring，签名行为不变**；② FK `SET NULL` 与实体校验器冲突导致删除目标后读取崩溃 → **D12：同事务降级 + 读取侧防御映射，不弱化校验器、不改 FK、不加触发器**。

**R2 修正的两个逻辑问题（第一轮审查指出）**：① **重建碰撞的四条承诺在唯一约束下逻辑矛盾** → 写前全量预检 + **有碰撞整体拒绝零写入** + 结构化报告 + 等用户处置后重跑（§8.3）；② **导入提示字典推导 last-write-wins** → **先聚合再判定**，矛盾进 conflict 且保留双方信息，顺序无关（§6.5）。

**R3 修正的两个实现正确性问题 + 一个交付边界问题（第二轮审查指出）**：

1. **E1 全局版本同构守卫（阻塞项，已修复；**审查结论：已通过**）**：R2 §6.4 只检查 `repo.list_links(item.id)`，`all([]) == True` 使**没有任何链接行的新 source 可以绕过守卫写入异版本键**，破坏 §8.4 全表同构不变量。R3 把权威检查移到 **backend 持久化边界**：单列 `SELECT DISTINCT link_normalization_version`（**同一事务内、写入之前**；**R3.1 撤回「每事务缓存一次」，改为无缓存、每次受守卫写入重新执行**，§8.4.3）→ 调用 **Core 纯函数 `check_global_version_homogeneity()`**（单一事实来源，InMemory 测试替身共用）→ 空表放行、任何异版本行**拒绝本次链接写入** → `LinkNormalizationVersionMismatch` → **HTTP 409 + 稳定码 `link_version_mismatch`**。**不新增迁移、不新增索引、不新增端口方法、不改 A1-01 的 10 个签名**；**不宣称跨进程互斥**，静默期/单写者限制保留。治理降级写入与 DELETE 属**可证明豁免**（不改变也不缩小版本集合），故 V1 删除路径与 D12 降级在版本窗口内不被误伤。§8.4 全节重写为 8.4.1–8.4.8，**「任何同步尝试被守卫拒绝」的笼统表述已按实际实现修正**（§8.4.7）。新增 **T13–T21**，其中 **T16 就是审查给出的反例**，并断言「局部守卫确实放行、全局确实拒绝」的双层对照。**R3.1 补充：豁免越宽，apply 阶段的独立重读与逐行比对越不可省略**（§8.4.3 关键推论 → 门禁 C）。
2. **E2 导入绑定的空间语义（阻塞项，已修复）**：R2 §6.5 只校验 target 是否存在，未定义空间关系。R3 采纳审查建议口径：**有效稳定 UUID 代表历史绑定意图**，目标存在即恢复，并**按当前 source/target 的 `space_id` 重算 `resolution`/`cross_space`**（`None==None` 视为同空间）；跨空间**必须**落 `cross_space` + `cross_space=True`，**绝不伪装成 `resolved` + `False`**；archived 目标与 **D7 显式绑定**一致；目标不存在仍回退标题解析。**无效 UUID / 目标不存在 / 空间不匹配三类语义严格分离**（前两类不参与投票，第三类是有效提示）。新增 **§6.6**（6 行空间判定表 + 8 条口径要点 + 服务层不变量 + 新 warning 码）与 **H13–H20**（含顺序无关与 Hash 诚实口径），Core/SQLite/PG 按断言性质分层覆盖。
3. **E3 人工绑定的交付边界（已明确）**：**保留 D8，不新增任何写 API**。A1-03 交付**候选发现 + 只读查询**；显式绑定规则**在 Core 明确并测试**，但**无可供用户操作的 HTTP 写入口**；人工绑定 API 与前端交互属后续里程碑。新增 **§6.7**（8 行交付边界表 + 验收措辞纪律 + 路由方法集合守护），**L③/J 一律写成「Core 层显式绑定规则已验证（A1-03 无 HTTP 写入口）」**，L④/H17 经真实 HTTP 验证的是**保留**而非**建立**。

**R3 如实报告的两项自主发现（非审查指出；**现均已获批准**）**：

- **E4 配套调整（**已获独立审查批准**；R3.1 按要求补门禁 C）**：字面执行「全表版本必须等于代码常量」的守卫会让 **R2 的「Core 逐行 `update_link` 执行重建」自相矛盾**——升级时第一行写入即被自己的守卫拒绝（死锁）；加「绕过开关」则任何人都能提交混合版本；改端口签名违反本轮约束。R3 的处置是把重建拆为 **Core `plan()`（只算计划，零数据库写入、零文件 IO）+ backend `apply_link_key_plan()`（单事务原子批量执行）**，详见 **§8.3.5** 的矛盾证明与 7 条正确性论证。**这不改 Hash 契约、不改数据模型、不改端口签名、不改 V1 行为**，属 Core↔backend 职责分层调整，与 D10 同向。**上一轮审查结论：拆分已批准，但必须补充门禁 C（计划新鲜度）** → R3.1 已落实为 **§8.3.6 / §8.3.7 / §8.3.8**（见下）。**拆分本身不再重新讨论。**
- **E5 实测缺陷风险（**已获批准，本轮不再讨论、批准状态不变**）**：`SQLAlchemyKnowledgeRepository.list` 在 `space_id=None` 时**不加 where 过滤 → 返回全库所有空间的条目**（实测代码，§2.5⚠）。V1 路由只在 query `space_id` 非 None 时走个人聚合分支，故 **V1 行为正确、无需修改**；但若 A1-03 直接把该返回值当作个人空间源条目的候选集，就会**自动跨空间绑定**，违反「不自动跨项目」。处置：**Core 侧再做精确空间等值过滤**（`candidate.space_id == item.space_id`，`None==None`），**不改 V1 仓库、不改端口**；新增 J 扩展断言与 R24。**R3.1 未重新设计此项。**

**R3.1 本轮唯一目标：重建计划新鲜度门禁 C（E6，落实上一轮审查对 E4 的必须补充项 + §五 缓存生命周期修订）**：

1. **原问题（真实正确性漏洞，非假想）**：`plan()` 与 `apply_link_key_plan()` 之间存在时间窗。**门禁 A 只看版本集合**——改 `target_title`/`alias`/`source_id`/`normalized_link_key`、增删链接行**都不改变版本集合**（其中治理列编辑与增删还被全局守卫**合法豁免**）；**门禁 B 只看计划自身**的覆盖与重复，**不与当前数据库比对**。因此**过期计划会被放行**：新键算错、覆盖漏行、no-op 行盲区、更新打到已删 ID。§8.3.6 给出 **6 行反例表**逐条证明 A/B 看不见。
2. **门禁 C（§8.3.6）**：`plan()` 必须携带**覆盖全表每一行（含 no-op 行）**的只读快照 `row_snapshots`（`link_id`/`source_id`/`old_key`/`old_version`/`target_title`/`alias`，另携带但不比对 `target_id`）+ `observed_row_count`；apply **在自己的执行事务内重读当前全表 6 列**，交 **Core 纯函数 `check_plan_freshness(plan, current_rows)`** 做**双向覆盖 + `link_id` 唯一 + 6 字段原始 Unicode 精确比对（比对前不做任何规范化，`None` ≠ `""`）+ 每行新键重算（update 行与 no-op 行都算）+ 篡改检测**。**10 类情况**（删除/新增/`source_id`/键/版本/`target_title`/`alias`/未覆盖/重复 `link_id`/篡改）任一命中 → **整个计划拒绝、稳定状态 `refused_stale_plan`、数据库零写入、`updated=0`、`requires_replan=True`、结构化 `stale_reasons`**；**不允许部分更新、不允许自动忽略不一致行后继续、不允许拒绝后重试旧计划**（必须重读全表重生成，§8.4.7 步 3c）。**不新增端口方法、不新增数据库字段。**
3. **十步执行顺序（§8.3.7，不得颠倒）**：① 开启事务 → ② 门禁 A 全局版本同构 → ③ 重读当前全表必要字段 → ④ 门禁 B 覆盖范围与唯一性 → ⑤ 门禁 C 逐行快照一致 → ⑥ 新键唯一性再验证 → ⑦ 批量更新 → ⑧ 写后复核版本同构与唯一约束 → ⑨ 全部通过后提交 → ⑩ 任一环节失败整体回滚。**状态优先级 A→B→C**；**`(source_id,new_key)` 重复归 B、重复 `link_id` 归 C**；**apply 独占 `with session.begin():`**。**plan 阶段的检查一律不构成 apply 阶段的安全保证**，A/B/C 全部独立重新执行。
4. **不新增计划摘要（§8.3.8，论证结论）**：**不增加**确定性计划摘要。四机制——**frozen Pydantic + tuple 不可变**、**双向全覆盖 + `link_id` 唯一**、**6 字段精确比对**、**每行新键重算**——**强于摘要**：摘要的前提是「计划在生成时正确」，而这恰恰是本轮失效的前提；**「数据库已变、计划未变」时摘要完全无用**，而逐行重读比对与新键重算能发现。**不使用 Python 内置 `hash()`**、**不改三 Hash 契约与 `canonicalization_version`**、**不混入文档交换载荷**、**不新增数据库字段/迁移**。仅保留确定性 `model_dump(mode="json")` 用于留痕。**跨进程/落盘重载计划的威胁面本轮不存在**，若将来出现，该批次须重新评估摘要（**【待审批】**）。
5. **事务缓存生命周期修订（§8.4.3（1）–（6），撤回 R3 方案）**：**SQLAlchemy Session 生命周期 ≠ 数据库事务生命周期**——2.x 的 autobegin 使 **commit 后 / rollback 后同一 Session 会开启新事务**，`begin_nested()` 的 **savepoint 又不结束外层事务**，`join_transaction_mode` 下 `begin()` 还可能依附外部事务。R3 的「仓库实例级缓存（实例 = Session = 事务）」**失效条件无法证明**，会**跨事务复用旧版本集合** → 守卫误判放行 → 写出混合版本。故**采用审查给出的保守方案：无缓存，每次受守卫写入重新执行单列 `SELECT DISTINCT`**；结果**仅存在于本次判定调用栈**；**有效性唯一依据 = 「本次查询与本次写入在同一事务内」**，**不得仅以 Session 对象是否存在判断**。**不为省一次查询牺牲正确性**；成本如实量化为 **k 次写入 = k 次单列扫描**（豁免写入 0 次、apply 批量写门禁 A 恰 1 次）。**Core 只提供纯函数、backend 负责数据库查询**的分层约束保持不变。**T20③ 期望值随之修订（`==1` → `==受守卫写入次数`），属断言修订而非删除测试**，权威断言另见 T34。
6. **测试补充（§7.5.1，T22–T40，全部【待验证】）**：在 **T13–T21 之后追加新编号**，**不覆盖、不删除已有测试**。用户 §六 的 **13 项逐项对应 T22–T34**，另加 **T35–T40** 六项配套（`source_id` 变化、篡改检测、**no-op 盲区反证**、计划不可变性与确定性序列化、**十步顺序与写后非键列复核**、**savepoint/nested 边界**）。**本轮未编写任何测试文件、未运行任何测试**，19 条一律标 **【待验证】**，**不得宣称已运行通过**。
7. **诚实限制（§8.4.8，扩为五条）**：门禁 C 是**漂移检测，不是互斥**；它把窗口收窄到 **apply 事务内「重读→提交」之间**，**该残余窗口本轮不关闭**（**不用 `SELECT … FOR UPDATE`/表锁/advisory lock**，方案**【待审批】**）；仍须静默期/单写者运维限制。**不得写成「并发安全已保证」。**

**等待**：**最终独立审查本 R3.1 计划 + 明确实施批准**。上一轮结论已记录在案：**E1、E2、E3、E5 已通过；E4 职责拆分已批准但须补门禁 C** —— 本轮**只补门禁 C 与事务缓存生命周期**，**R3 原有已批准设计全部保留**，**E5 不再讨论、E1/E2/E3 不重新设计**。D1–D12 与 E1–E6 已全部裁决或按要求落实，**无剩余开放决策**；**两项【待审批】的延后提议**（关闭残余窗口的行锁方案、跨进程计划摘要）与**一项【待审批】的性能优化**（带事务身份键的缓存/版本索引）已如实列于 §13.2，**本轮不实施**。收到实施批准前**不写任何业务代码、不新增测试文件、不运行实现或测试、不安装依赖、不改迁移、不改 Core/Backend/Frontend、不改 A1-01/A1-02 既有实现、不改 V2 主设计文档与依赖选型文档、不改 lockfile、不提交或推送 Git、不 reset/checkout/stash**，**不得开始 A1-03a**。

---

## 15. 审查修订记录（第一轮独立审查 → R2；第二轮最终审查 → R3；**R3.1 最终修订 → 门禁 C**）

> 逐条标记：**原问题 / 修订方案 / 对应章节 / 新增测试 / 是否涉及设计契约变更**。
> 「设计契约变更」判定口径：Hash 契约（三 Hash 定义/覆盖字段/`canonicalization_version`）、数据模型契约（表/列/约束/迁移）、端口签名契约、V1 已验证行为。**四类在 R2、R3 与 R3.1 均未变更**；两处是对设计**未定义处**的口径明确（REV-02 碰撞是否部分写入、REV-18 导入 `cross_space` 重算），均已由用户裁决或给出建议口径并采纳。**R3.1 另明确：不新增任何 Hash 契约（含计划摘要），不新增数据库字段/迁移，不改端口签名（REV-23–REV-26）。**
> **REV-01–REV-15 = 第一轮审查 → R2**（历史保留，不改写）；**REV-16–REV-22 = 第二轮最终审查 → R3**（历史保留，不改写）；**REV-23–REV-26 = R3.1 最终修订轮**（本轮新增）。

| 编号 | 原问题（R1 稿） | 修订方案（R2） | 对应章节 | 新增测试 | 设计契约变更 |
|---|---|---|---|---|---|
| **REV-01** | D1–D12 全部处于「待裁决/默认取向」状态，其中 **D7 默认「排除自身→自链接 missing+warning」**、**D10 默认「重建报告 JSON 由本服务落 `backend/data/ops/`」** 与用户裁决不一致 | 按裁决全部落地：**D7 改为「archived 仅排除自动解析、允许显式绑定；自链接允许正常解析」**；**D10 改为「Core 只返回结构化报告，backend 运维层负责持久化，Core 零文件 IO」**；D1/D2/D3/D4/D5/D6/D8/D9/D11/D12 与裁决一致，措辞由「默认/需确认」改为「已裁决批准」 | §11（改为裁决台账）/ §6.2 / §6.4 / §3②③ / §5.4 / §5.5 / §8.3.4 / §2.3 / §2.6 | **场景 K**（自链接 5 断言）、**场景 L**（archived 5 断言）、**T12**（Core 零文件 IO 行为守护 + backend 落盘往返）、**D3 签名不变守护** | **无** |
| **REV-02** | **问题 A：重建碰撞逻辑矛盾。** R1 §8.3 同时承诺「同源键唯一 + 碰撞行全部保留 + 原 target_id 全部保留 + 两行写相同新键」，并写「同源同键合并保留首现字面」——在 `UNIQUE(source_item_id, normalized_link_key)` 下**不可能同时成立**（合并必丢一个 target_id；保留两行必抛 IntegrityError） | **写前全量预算新键 → 检测全部碰撞组 → 有碰撞默认拒绝全量重建（事务零部分更新）→ 结构化碰撞报告（`link_id/old_key/new_key/old_version/target_id` + `source_id/target_title/alias`）→ 全部原行/旧键/旧版本/原绑定原样保留 → 等用户处置后重跑**。**不随机绑定、不覆盖、不静默删除、不合并行、不做部分/混合版本重建**。重建收窄为只写两个非交换列，**绝不重解析、绝不改 resolution** | §8.3.1（矛盾证明）/ §8.3.2（七条要求逐条对应 + 伪代码）/ §8.3.3（与设计原文差异如实报告）/ §6.2 末行 / §5.2 问 6、问 7 | **§7.5 T1–T12**：T1 无碰撞正常重建、T2 单组碰撞、T3 多组碰撞、T4 不同 target_id 碰撞、T5 碰撞整体回滚（**含故障注入真实事务回滚**）、T6 回滚前后 DB 全表逐列 + 三 Hash 完全一致、T7 双方言重复键真实抛 IntegrityError、T8 跨 source 同键不算碰撞、T9 幂等重跑、T10 回滚同受碰撞门禁、T11 版本同构、T12 报告结构 + 零文件 IO。**场景 G 重写** | **Hash 契约无变更、数据模型无变更、端口签名无变更**。属对设计 §2.4/§2.9「碰撞→ambiguous/conflict 报告」**未定义处（是否部分写入）的口径收紧**，**用户本轮已裁决批准**。建议实施后**另批**同步设计措辞；**本轮不改设计文档** |
| **REV-03** | **R1 未识别混合版本风险**：R1 允许「碰撞行降级后继续重建其余行」，会产生 v1/v2 行共存；绑定优先同步按当前常量算键做字符串等值匹配 → 旧行匹配失败被判新键 → **重解析 + 删旧行 → 静默丢绑定**；且不同版本行可能算出相同键字符串 → **IntegrityError** | 新增 **§8.4 版本同构性**：只有「全量成功/全量拒绝」两种终态；`BindingFirstLinkSync` **版本同构守卫 fail-loud 零写入**（`LinkNormalizationVersionMismatch` → HTTP **409 + 稳定错误码 `link_version_mismatch`**，不回传异常文本）；给出**可证明正确的升级/回滚运维协议**（拒绝时 DB 零写入 → 回退发布即恢复，无需数据修复）；**明确不实施**「按行自身版本重算匹配」（无法证明唯一约束/同步/查询/回滚均正确） | §8.4 / §6.4 伪代码首段 / §3② / §9 新增三行 / R14、R15 | **T11**（同构性 + 混合版本守卫零写入）、§7.4 DB 级版本守卫用例、§8.5.6 兼容性清单第 6 项 | **无**（新增防御性守卫与运维口径；不改表/列/约束/Hash） |
| **REV-04** | **问题 B：Frontmatter 提示覆盖。** R1 §6.5 `hints = {normalized_title_key(l.title): l for l in frontmatter_links}` 是字典推导 **last-write-wins**，同键前一个提示的 target_id 被静默丢弃，矛盾被掩盖，结果依赖书写顺序 | **先聚合再判定**：纯文本层 `group_hints_by_title_key` 返回**完整列表**；服务层逐条判有效性（`no_target_id`/`malformed_uuid`/`target_not_found`），按**有效提示的不同 target_id 基数**判定：1→恢复、>1→**conflict（target_id=None，warning 含全部矛盾 target 及原始 title/alias）**、0→回退标题解析。**明确「无效≠矛盾」口径**（避免跨实例导入大面积误入 conflict）。孤儿提示不建行 + warning（D4） | §6.5（全节重写 + 判定矩阵 + 确定性要求）/ §3①② / §7.3 新增分组 bullet | **§7.6 H1–H12**：H1 重复提示、H2 同 title 不同 alias 同 target、H3 矛盾提示、**H4 顺序打乱结果不变**、H5 无效 UUID、H6 目标不存在、H7 有效+无效混合、H8 三方矛盾、H9 孤儿提示、H10 缺 target_id、H11 空提示列表、H12 三 Hash 不受影响。**场景 M 新增** | **无**（设计「target_id 优先恢复 / 无效回退」的确定性化，不改交换字段） |
| **REV-05** | **场景 F 的 review_hash 口径错误**：R1 写「对同一文档计算三 Hash」，把 `review_payload_hash` 当作**完整文档状态 Hash**；且未规定 payload 非空。**实测 A1-02 实现 `if not changes: raise CanonicalizationError("review_payload_hash 不接受空变更")`**，按 R1 写法会直接抛异常或产生误导结论 | 场景 F 明确三项：① `document_content_hash` 同一文档重建前后逐位相等；② `document_payload_hash` 逐位相等；③ **`review_payload_hash` 使用固定的非空审核变更 payload**（如 `{"title":"A′","content":"新正文"}`）重建前后逐位相等。**明文禁止**把 review_hash 描述为完整文档状态 Hash、**禁止**传空 dict。另加**非空洞性断言**：先证明重建确实生效（键/版本真的变了）再比 hash。同时验证导出文本字节一致 + 全部 target_id 保留 + 五个非交换列逐行不变 | §7.2 场景 F（重写）/ §5.2 问 5（补实现实测）/ §5.2 问 7（六步论证）/ §13.1 F 项 | **场景 F 重写**（含固定非空 review payload、非空洞性断言、组件 `links_hash` 不变）；**T6** 把三 Hash 比对纳入碰撞回滚断言 | **无**（修正测试口径，Hash 定义与覆盖字段完全不动） |
| **REV-06** | **D7 archived 口径不清**：R1 只写「排除 archived」，未区分自动解析与显式绑定，可能被实施为「禁止绑定 archived」 | 明确 **「排除 archived」仅作用于自动解析候选过滤**；`resolve-candidates` **仍带 `status=archived` 标注列出**；**用户显式选择 archived → 允许绑定**（resolved/cross_space）；显式绑定后连续保存**不被自动解绑**；active+archived 同键时**不因 archived 存在而误判 ambiguous** | §6.2 新增三行 + D7 口径澄清段 / §6.4 候选过滤 / §3② / §9 archived 过滤行 / R18 | **场景 L 五条断言**（Core + SQLite + PG 三层） | **无** |
| **REV-07** | **自链接被 R1 默认禁止**（「排除自身→missing+warning」），与裁决「允许自链接，不额外禁止」相反 | 候选枚举**不排除源条目自身**；`[[A]]` 在 A 内正常解析为 `resolved` 并绑定自身稳定 ID；`list_backlinks(A.id)` **如实包含 A 自身**，不特殊过滤 | §6.2 自链接行 / §6.4 注释 / §3② / R18 | **场景 K**（解析结果、反链含自身、改名后仍绑定、连续保存 ID 稳定、Hash 口径不受影响） | **无** |
| **REV-08** | **D10 职责错位**：R1 把报告落盘写在 Core 侧流程里（「重建报告 JSON 落 `backend/data/ops/`」），会让 Core 绑定文件系统路径，破坏独立性与 Nesti 可复用性 | **Core 只返回结构化 Pydantic 报告对象**（`LinkRebuildReport`/`LinkCollisionGroup`/`LinkCollisionEntry`），**零文件系统写入**；落盘由 **backend `persist_rebuild_report()`** 负责（gitignore 目录）；本轮**不提供** CLI 与写端点（D8） | §3②③ / §8.3.4 / §4.1 / R19 | **T12 行为守护**：monkeypatch `builtins.open`/`Path.write_text`/`Path.mkdir` 抛异常后重建**仍成功返回报告**；backend 落盘 `tmp_path` 读回 JSON 与 `model_dump(mode="json")` 一致 | **无**（职责分层） |
| **REV-09** | **缺完整前后兼容性说明**（审查意见四.4） | 新增 **§8.5** 六小节：数据层向后兼容 / 交换格式前后兼容（旧文件↔新文件互读、派生键不外泄、字节级不宣称）/ API 兼容（只增不改、409 新错误路径永不影响 V1、路由不冲突、前端零改动）/ 版本与规则兼容（两套版本号独立、旧规则函数保留）/ 降级与代码回滚兼容（**代码回滚后链接行留存但无人读写，不宣称自动清理**）/ **兼容性验证清单 6 项** | §8.5.1–8.5.6 / §12 A1-03f 门禁 | §8.5.6 六项（V1 纯文本、A1-02 文件 hash 逐位不变、新文件旧 codec 可读、V1 全量回归、0006 up/down 双方言、版本守卫）；**R3 已扩至 9 项，见 REV-17** | **无** |
| **REV-10** | **A1-02 冻结清单表述含糊**：R1 只说「三个核心实现文件及其测试文件」，未明确 `markdown/__init__.py` 是否冻结，而 D11 又要求把 ABC 追加进该文件，存在自相矛盾风险 | 明确 **6 个冻结文件**（`canonical.py`/`frontmatter.py`/`codec.py` + 三个对应测试文件）**全程逐字节不变**；`markdown/__init__.py` **不在冻结清单**但**只允许尾部追加**（依据 AGENTS.md §4「ABC 声明在包 `__init__.py`」），A1-02 既有代码逐字不动，**追加后 293 用例必须仍全通过**作为可核验证明 | §1.3 冻结清单段 / §4.2 / §7.7 / §13.1 | 每步 `sha256sum -c` 6 项恒 OK；A1-02 293 用例全通过；`__init__.py` 追加后公共 API 行为不变断言 | **无** |
| **REV-11** | **场景 G 断言自相矛盾**：R1 写「唯一约束校验通过（**同源同键合并**/报告，不抛未处理 IntegrityError）」——「合并」与「保留全部 target_id」互斥（同 REV-02） | 场景 G 重写为 **「碰撞 → 整体拒绝 + 零写入 + 全表逐列快照相同 + 报告完整」**；删除「合并」措辞；新增 **T7 反证**：故意写重复键证明双方言**确实抛 IntegrityError**，从而证明写前预检是必需的而非可选优化 | §7.2 场景 G / §7.5 T2–T7 / §6.2 末行 | T2/T3/T4/T5/T6/T7 | **无** |
| **REV-12** | **场景 H 未区分「继承」与「重解析」**：R1 写「解析标题键不变 → 仍绑定 B」，无法证明 D5「不继承旧 target_id」被真正执行（继承也会得到同样结果） | 场景 H 增加**判别性断言**：把 B 改成歧义标题后再做 alias-only 变更，**应重新落入 `ambiguous`** 而非沿用旧绑定 → 证明走的是**严格新键重解析** | §7.2 场景 H / R6 | 场景 H 判别性用例（Core + SQLite + PG） | **无** |
| **REV-13** | **回滚被隐含当作无条件可用**：R1 §8.3 写「回滚 = 以旧版本号重跑，确定性恢复旧键」，未考虑旧键在新数据下也可能碰撞 | 明确 **回滚同受碰撞拒绝门禁**：旧键碰撞 → 同样整体拒绝 + 报告，保持现版本，**不做部分回滚**；并给出一旦拒绝的运维处置路径 | §8.3.4 / §8.4 协议第 4 步 / §8.5.5 | **T10**（成功回滚 + 回滚被拒两种分支） | **无** |
| **REV-14** | **测试编号与规模未随修订更新**：R1 估 ~310 用例、场景止于 J、§7.5/§7.6 为回归与规模 | 场景扩至 **A–M**；新增 **§7.5 T1–T12**、**§7.6 H1–H12** 两个专项矩阵；原 §7.5/§7.6 顺延为 **§7.7 回归与守护 / §7.8 预估规模**；规模上调至 **~420**（以实际收集数为准，不虚报） | §7.1–§7.8 / §12 各步门禁 / §13.1 | 见 REV-02/04/05/06/07/08 各行 | **无** |
| **REV-15** | **R2 轮基线复核未记录** | 新增 **§1.5**：本轮真实执行 HEAD / 分支 / stash / status / **baseline patch `cmp` 逐字节相同（1173 行）** / **21 个 SHA-256 全 OK** / **依赖与锁定文件零漂移**；并记录「`sha256sum -c` 必须在仓库根执行」的复核纪律（子目录执行会误报 FAILED） | §1.5 | 非测试，属只读核验证据 | **无** |

**第二轮（最终）独立审查 → R3 的修订记录（本轮新增，REV-16–REV-22）**：

| 编号 | 原问题（R2 稿） | 修订方案（R3） | 对应章节 | 新增测试 | 设计契约变更 |
|---|---|---|---|---|---|
| **REV-16** | **意见一（阻塞项）：全局版本同构守卫缺失。** R2 §6.4 的守卫只检查 `repo.list_links(item.id)`，即**只证明当前 source 的出链版本一致**。审查反例：代码常量 v2、旧 source A/B 仍有 v1 链接、**新 source C 没有任何链接行** → `all([]) == True` → C 通过守卫并创建 v2 链接 → **全表出现 v1/v2 混合，§8.4 同构不变量被破坏**。R2 把局部检查当成了全局保证 | **权威检查移到 backend 持久化边界**：`SQLAlchemyLinkRepository.save_link` 与「改键或改版本」的 `update_link` 在**同一 Session/同一事务**内执行**单列 `SELECT DISTINCT link_normalization_version`**（**不加载实体、不取全行**），把结果交给 **Core 纯函数 `check_global_version_homogeneity(versions, expected)`**（单一事实来源，`InMemoryLinkRepository` 测试替身调用同一函数）→ **空集放行（允许初始化）**、`versions == {expected}` 放行、否则抛 `LinkNormalizationVersionMismatch` → **HTTP 409 + 稳定码 `link_version_mismatch`**（不回传异常文本/版本明细/link_id）。**每事务缓存一次**预检结果（仓库只 `flush()`、路由 `commit`，已实测），回滚后缓存失效并重新预检。**不新增迁移、不新增索引、不新增端口方法、不改 A1-01 的 10 个签名**；**明确不宣称跨进程互斥**，静默期/单写者运维限制保留。Core 局部守卫**保留为纵深防御**并在伪代码中注明其局限 | **§8.4.1–8.4.8（全节重写）** / §8.4.3（权威执行点 + 纯函数 + 缓存正确性 + 成本）/ §6.4 伪代码 / §3②③④ / §4.1 / §4.3 / §7.4 / §7.7 / §8.5.3 / §9 / §12 b·d·e 门禁与顺序约束 / R14 重写、**R20、R21** | **T13** 空表创建第一条链接；**T14** 全表 v1 + 常量 v1 正常写入；**T15** 全表 v1 + 常量 v2 拒绝（v2 仅夹具）；**T16 审查反例**（断言局部守卫**确实放行** + 全局**确实拒绝** + 零写入 + 重建后恢复）；**T17** 混合 v1/v2 全部拒绝；**T18** SQLite 与真实 PG 各自验证；**T19** 拒绝后**全表逐列 + 三 Hash + 导出字节**零变化；**T20** 豁免与成本（治理写入成功 / DELETE 保持同构 / 5 条链接时 DISTINCT 查询次数 == 1 / 回滚后重新预检 / 恢复）；**T11 重写**为局部守卫纵深防御口径 | **无**（Hash 定义与覆盖字段、表/列/约束/迁移、端口签名、V1 已验证行为均不变；新增防御性预检与 Core↔backend 职责分层） |
| **REV-17** | **意见一附带要求：§8.4「任何同步尝试被守卫拒绝」的表述与实际实现不一致。** 字面上的「任何写入都拒绝」会**误伤 V1 删除路径与 D12 治理降级**（删除目标时同事务把入链降级为 missing），也会让「治理修复」自身被锁死；而 R2 未区分写入类别 | 给出**守卫作用域表 + 可证明豁免**：豁免仅限**不改变也不缩小版本集合**的写入——① 治理类只改 `resolution/target_id` 等非键非版本列的更新；② **DELETE**（删除只会缩小集合，不可能引入异版本）。每条豁免附**不变量证明**，并由 T20 真实断言。**§8.4.7 运维协议第 1 步措辞修正**为「**常规链接写入全部拒绝（含没有任何链接行的 source）**；治理降级与删除不阻断；正文保存在窗口期整体 fail-loud」，并附**R2 措辞修正说明**。**§8.4.8 三条诚实局限**（非跨进程互斥 / Core 独立复用边界 / O(L) 单列扫描成本）。**不设任何「跳过守卫」开关** | §8.4.3 作用域表 / **§8.4.7（措辞修正 + 说明）** / §8.4.8 / §8.5.3（409 作用域精确化）/ §8.5.6 第 7 项 / §13.2 / R21 | **T20**（治理写入豁免 + DELETE 豁免 + 同构保持）；**§8.5.6 清单由 6 项扩至 9 项**（新增 T16 反例、DELETE 豁免、跨空间列值、路由与端口守护）；V1 `DELETE /knowledge/{id}` 在版本窗口内不被误伤的回归断言 | **无** |
| **REV-18** | **意见二（阻塞项）：导入绑定的空间语义未定义。** R2 §6.5 只校验 `target_id` 是否存在，**未检查目标与源的空间关系**，可能把跨空间绑定落成普通 `resolved` + `cross_space=False`（伪装），或对 `space_id=None` 的个人条目与 project 条目之间的关系无口径；archived 目标的 UUID 恢复也未与 D7 对齐 | **采纳审查建议口径**：**有效稳定 UUID 代表历史显式绑定意图**；目标存在 → **恢复绑定**并**按当前 source/target 的 `space_id` 重算** `resolution`/`cross_space`（**精确等值，`None==None` 视为同空间**，不用聚合视图）。**6 行空间判定表**：None/None→resolved+False；p1/p1→resolved+False；p1/p2→**cross_space+True**；None/p1→cross_space+True；p1/None→cross_space+True；archived→**仅按空间判定 + 额外 archived warning**。**绝不出现 `resolved` + `cross_space=True` 或 `cross_space` + `False`**；新增**服务层不变量 `cross_space=True ⟺ resolution=cross_space`**（实测实体校验器 `_resolution_matches_binding` **不覆盖**此组合）。**三类语义严格分离**：`malformed_uuid`/`target_not_found` = 无效提示（不投票、回退标题解析）；**空间不匹配 = 有效提示（投票、→cross_space）**，不是 conflict。目标不存在仍按原设计回退标题解析 + `unresolved_links`。**新 warning 码** `cross_space_binding_restored` / `archived_target_restored`。**Hash 诚实口径**：同空间往返三 Hash 不变；**跨空间导入后再导出 `payload_hash` 允许变化**（`resolution` 在交换载荷内，D1），`content_hash` 不变。**不采纳「一律进待处理」方案**并给出理由（设计 §2.4 原文是「直接恢复绑定」，且 D8 下无 HTTP 写入口 → 用户无法清理待处理项 → 死锁） | **§6.6（新增全节）** / §6.5 步骤④改为 `bind_with_current_spaces()` + 矩阵行 1–2 注 / §6.2 新增两行 / §3② / §5.2 问 7 第 7 点 / §7.2 J 扩展、M 指向 / §7.4 / §9 / §13.1 / R22 | **H13** 同空间 UUID 恢复（含双方 None）；**H14** 跨空间恢复（断言**绝不** resolved+False，与 J 对照）；**H15** 源 None / 目标 p1；**H16** 反向；**H17** 目标 archived 但 UUID 有效（+ 真实 HTTP PATCH **保留**）；**H18** 目标不存在（**不是** conflict/cross_space）；**H19** 混合提示种类下**顺序无关**；**H20** 再导出 Hash 双向口径 + 白名单 + 固定非空 review payload。**三层覆盖口径**：纯判定断言可只在 Core；**持久化列值/事务/HTTP 断言 SQLite 与真实 PG 各跑一遍** | **无**（设计 §2.4 **未定义** `cross_space` 重算，属未定义处口径明确，**用户已给建议并采纳**；不改交换字段集合、不改 Hash 定义、不改端口）。**建议实施后另批同步设计 §2.4 措辞，本轮不改设计文档** |
| **REV-19** | **意见三：人工绑定的交付边界含糊。** D7 允许用户显式绑定 archived 与跨空间候选，D8 又规定 A1-03 只交付 3 个只读 GET。R2 的场景 L③/J 写成「用户显式选择 archived 允许绑定」，**读起来像已交付的用户功能**，而实际**没有任何 HTTP 写入口**可供用户操作 | **保留 D8，不新增写 API**。明确 **D7 = Core 语义规则**、**D8 = HTTP 交付范围**，二者不矛盾。新增 **8 行交付边界表**：候选发现 ✅（GET 已交付）/ links·backlinks ✅ / 自动解析 ✅ / 导入恢复 ✅（Core；HTTP 导入端点属 A1-04）/ **人工显式绑定 ⚠ Core 已定义并测试，但无 HTTP 写入口 → 不是已交付用户功能** / `POST links/resolve` ❌ 后续 / 前端绑定交互 ❌ A2·A1-06 / reresolve·rebuild-keys·CLI ❌ 后续。**验收措辞纪律**：L③/J 必须写成「**Core 层显式绑定规则已验证（A1-03 无 HTTP 写入口）**」；**L④/H17 的绑定由 Core/仓库夹具建立，再经真实 HTTP PATCH 验证「保留」而非「建立」**。新增**路由守护测试**：链接 router 的 `(method, path)` 集合**恰等于 3 个 GET**，`knowledge.py` 端点集合不变。并说明「规则先行」不是过度设计（导入恢复与绑定优先同步本身就依赖该规则） | **§6.7（新增全节）** / §6.2 交付边界注 + 显式绑定行标注 / §7.2 L③④、J 标注 / §7.7 路由守护 / §8.5.3 / §12 e·f 门禁 / §13.1 措辞纪律 + 交付边界守护项 / §13.2 新增延后项 / R23 | **路由方法集合守护**（恰为 3 个 GET，无写方法）；**`knowledge.py` 端点集合不变守护**；L④/H17 改为「夹具建立 + HTTP 验证保留」口径 | **无**（交付范围与验收措辞口径，不改任何契约） |
| **REV-20** | **R3 配套调整（自主发现，如实报告）：全局守卫使 R2 的重建执行方式自相矛盾。** R2 §8.3.2 让 **Core 逐行调用 `update_link` 执行重建**。一旦按 REV-16 加上「全表版本必须等于代码常量」的守卫：升级 v1→v2 时**第一行写入即被守卫拒绝**（因为其余行仍是 v1）→ **死锁**；若加「重建绕过守卫」开关 → **任何人都能提交混合版本**，守卫形同虚设；若改端口签名传入豁免参数 → **违反「不改 A1-01 端口契约」** | **重建拆为两段职责**：**Core `LinkKeyRebuild.plan(target_version) -> LinkRebuildPlan`**（阶段 0 单版本预检 → `refused_mixed_version`；阶段 1 只读映射；阶段 2 全部碰撞组；阶段 3 `refused_collision` 零写入；阶段 4 产出覆盖全部非 no-op 行的 `updates` → `status="ready"`）——**零数据库写入、零文件 IO**；**backend `apply_link_key_plan(plan, session) -> LinkRebuildReport`**——**门禁 A**（`DISTINCT == {plan.source_version}`，否则 `refused_version_drift`）、**门禁 B**（source≠target 时**计划 100% 覆盖** + **新键无重复**，否则 `refused_incomplete_plan`）、**单事务只写 3 个非交换列**、**写后复核**失败整体回滚。**仍只有「全量成功 / 全量拒绝」两种终态，绝不部分应用**。**6 条正确性论证**：守卫未被弱化 / 重建是原子全表迁移 / **不改端口契约**（`apply_link_key_plan` 是 backend 模块函数，非端口方法；ABC 方法由从未写过的 `rebuild()` 改名为 `plan()`）/ 与 D10 同向 / Hash 论证更强 / **漂移保护 ≠ 互斥**。**测试分层影响如实说明**：Core 断言计划与终态，DB 断言真实写入/快照/回滚 | **§8.3.5（新增全节：矛盾证明 + 职责表 + 6 条论证）** / §8.3.2 伪代码重写 + 七条要求表新增「不得部分应用计划」行 / §8.3.4 / §8.4.4 重建专用门禁 / §5.2 问 6、问 7 / §3②③ / §4.1 / §7.5 分层口径 / §7.7 D10 守护扩展 / §8.5.5 / §12 顺序约束 2 / §14 E4 | **T12 重写**（行为守护②：把 `save_link/update_link/delete_link` 换成抛异常的替身 → `plan()` **仍成功**，证明零数据库写入）；**T21 新增**（`refused_version_drift` / `refused_incomplete_plan` / 新键重复 / 正常成功四分支，门禁**真实拒绝**）；**T11 重写**（重建入口门禁：单一版本 ≠ 常量 → 重建也拒绝；混合 → 拒绝） | **无**（Hash/数据模型/端口签名/V1 行为均不变；属 Core↔backend **职责分层调整**）。**但它改变了 R2 已批准方案中「谁执行重建写入」，故在 §11 E4 与 §14 单独列出供最终审查确认，不隐藏** |
| **REV-21** | **R3 实测新发现（非审查指出）：候选枚举在 `space_id=None` 时返回全库。** 实测 `backend/app/services/knowledge.py::SQLAlchemyKnowledgeRepository.list` 的过滤写在 `if space_id is not None:` 之内 → **`list(space_id=None, include_unassigned=True)` 不加任何 where，返回所有空间的全部条目**。V1 路由只在 query `space_id` 非 None 时走个人聚合分支，故 **V1 正确**；但 R2 §6.4 伪代码直接把该返回值当候选集 → **个人空间（`space_id=None`）源条目会把 project 条目纳入候选并自动绑定**，违反「不自动跨项目」 | **Core 侧强制再做精确空间等值过滤**：`same_space = [i for i in raw_candidates if i.space_id == item.space_id]`（**`None==None` 同空间；`None` vs `"p1"` 不同空间**），**在 archived 过滤与标题索引之前**执行。**不改 V1 仓库、不改端口、不改 V1 路由**（避免触碰已验证功能）。与 §6.6 的导入空间重算形成对照：**自动解析绝不跨空间，UUID 恢复可以跨空间但必须如实标注** | **§2.5⚠（新增实测段）** / §6.4 伪代码 / §3② Resolver / §7.2 J 扩展 / §9 新增行 / §12 b 门禁 / §13.1 解析规则项 / **R24** | **J 扩展三条断言**：`space_id=None` 的源条目**不得**绑定 project 条目；`p1` 源**不得**绑定 `None` 目标；**与 H14（UUID 恢复可跨空间）形成判别性对照** | **无**（Core 侧过滤，V1 行为零改动） |
| **REV-22** | **R3 轮测试编号、规模、基线复核与诚实性声明未随修订更新**；R2 稿仍写 ~420 用例、T1–T12 / H1–H12、§8.5.6 六项、§14 结论止于 R2 | 场景仍为 A–M（J/L/M 扩展）；**§7.5 扩至 T1–T21**、**§7.6 扩至 H1–H20**；**§8.5.6 清单 6 → 9 项**；**§7.8 规模 ~420 → ~520**（纯文本 ~95 / 服务层 ~215 / SQLite ~95 / PG ~95 / 守护 +18），并**明文标注「本轮（R3）未运行任何测试，以上全部为估算」**；**§13.1 增加诚实性前置声明**（每项当前均为 ⏳ 未验证，不得写 PASS）；新增 **§1.6 R3 开工前/收工后真实复核表**、**§15.4 R3 改动文件清单**、**§15.5 R3 真实核验输出**、**§15.6 冻结声明**；§11 改为 **D1–D12 + A/B + E1–E5** 台账；§12 增加 **4 条顺序约束**（b→d 纯函数先行、c→d 计划先行、d→e 真实异常先行、**任何步骤不得临时关闭守卫**）；§10 新增 **R20–R24**、R14 重写、R2 陈旧「（需批准）」改为「（**D3 已批准**）」 | §1.6 / §7.5 / §7.6 / §7.7 / §7.8 / §8.5.6 / §10 / §11 / §12 / §13.1 / §13.2 / §14 / §15.4–15.6 | 非新增测试本身，属**编号/规模/门禁/核验证据**同步；T13–T21、H13–H20 见 REV-16/18/20 | **无** |

**R3.1 最终修订轮的修订记录（本轮新增，REV-23–REV-26）**：

> 依据：上一轮独立审查结论 **E1、E2、E3、E5 已通过；E4 的 Core plan / backend apply 职责拆分已批准，但必须补充门禁 C**。本轮**只修改本计划文档**，**不实现业务代码**，**不扩大范围**；**R3 原有已批准设计全部保留**，**E5 不再讨论、批准状态不变**，**E1/E2/E3 不重新设计**。

| 编号 | 原问题（R3 稿） | 修订方案（R3.1） | 对应章节 | 新增测试 | 设计契约变更 |
|---|---|---|---|---|---|
| **REV-23** | **★ 门禁 C 缺失：重建计划会过期，而门禁 A/B 发现不了（本轮唯一目标，审查对 E4 的必须补充项）。** A 只读**版本集合**——改 `target_title`/`alias`/`source_id`/`normalized_link_key`、**增删链接行**都不改变版本集合（治理列编辑与增删还被全局守卫**合法豁免**）；B 只检查**计划自身**的覆盖与重复，**不与当前数据库比对**。故 plan↔apply 之间的并发变化会让**过期计划被放行**：新键算错、覆盖漏行、**no-op 行盲区**（`updates` 不含 no-op 行，只比对 updates 就永远看不见它们）、更新打到已删 ID。另有**计划被篡改**（`new_key`/`new_version` 被改）而快照不含这些字段 ⇒ 字段比对也看不见 | **新增门禁 C（逐行计划新鲜度校验）**：① `plan()` 必须保留**覆盖全表每一行（含 no-op 行）**的只读快照 `row_snapshots: tuple[LinkRowState, ...]`（**至少含 `link_id`/`source_id`/`old_key`/`old_version`/`target_title`/`alias`**，另携带但不比对 `target_id`）+ `observed_row_count` + `requires_replan`；② backend `apply_link_key_plan()` **在实际执行事务中重新读取当前数据库全表 6 列**，交 **Core 纯函数 `check_plan_freshness(plan, current_rows)`** 逐项比较；③ **7 条比对规则**：`link_id` 双射且顺序无关 / **原始 Unicode 精确等值，比对前不做 NFKC·casefold·空白折叠，`None` ≠ `""`** / **双向覆盖（不只比较计划中已存在的行）** / 快照与 updates 内 `link_id` 均唯一 / `updates ⊆ snapshots` / **每行新键重算（update 行须等于计划值，no-op 行须已等于重算值）** / `target_version` 须在规则注册表中；④ **10 类情况 → 稳定 reason_code**：`row_deleted`/`row_added`/`source_id_changed`/`key_changed`/`version_changed`/`target_title_changed`/`alias_changed`/`row_not_covered`·`noop_row_requires_update`/`duplicate_link_id_in_plan`/`new_key_mismatch`·`new_version_mismatch`（另加 `update_row_not_in_plan`/`plan_not_ready`/`unsupported_target_version`）；⑤ **失败语义**：任一不一致 → **整个计划拒绝 / 稳定状态 `refused_stale_plan` / 数据库零写入 / `updated=0` / 不允许部分更新 / 不允许自动忽略不一致行后继续 / `requires_replan=True` + 结构化 `stale_reasons`（reason_code·link_id·field·expected·actual）/ 必须重新读取全表并重新生成计划**；⑥ **不比对 `target_id`/`resolution`/`cross_space`/`created_at`/`updated_at` 的理由逐条给出**（重建不写它们、键派生与之无关、治理写入合法），**写后复核改为与「第 3 步重读值」逐列比对**；⑦ **分层**：Core 纯函数 + backend 6 列 `select(...)` 装配，InMemory 调用同一函数，**不新增端口方法**（D3 10 签名守护继续有效）；⑧ **诚实限制**：窗口收窄到 apply 事务内「重读→提交」，**不宣称跨进程互斥**，**本轮不用 `SELECT … FOR UPDATE`**（【待审批】） | **§8.3.6（新增全节：反例表 + 快照字段表 + 7 规则 + 10 类 reason_code 表 + 失败语义 + 分层 + 限制）** / §8.3.5（职责表 + 第 6·7 点）/ §8.3.2 伪代码（产出 `row_snapshots`）/ §8.3.4（回滚四重门禁）/ §8.4.3（豁免与 C 的关系推论）/ §8.4.4（7 条门禁）/ §8.4.7（步 3c 拒绝后必须重生成）/ §8.4.8（第 2 条窗口）/ §8.5.5 / §8.5.6 第 10 项 / §9（+3 行）/ §10 **R25** / §11 **E4 更新 + E6** / §12 b·c·d·e·f + 约束 5·6·8 / §13.1 / §13.2 / §14 | **T22**（`target_title` 改）/ **T23**（`alias` 改，含 `None`↔`""` 与规范化后相等但原值不等）/ **T24**（新增行）/ **T25**（删除行，含删 no-op 行）/ **T26**（键改，含「改成恰好等于 new_key 仍拒绝」）/ **T27**（版本改，A 优先）/ **T28**（覆盖不全三构造）/ **T29**（重复 `link_id`，归 C）/ **T30**（拒绝后全表逐列 + `knowledge_item` 全列 + 三 Hash + 导出字节零变化）/ **T31**（SQLite 与真实 PG 各一遍）/ **T35**（`source_id` 改）/ **T36**（篡改 `new_key`/`new_version`，含交换两行新键）/ **T37**（**no-op 盲区反证** + 正常 no-op 不误拒）。**全部【待验证】** | **无**（Hash 契约 / 数据模型 / 迁移 / A1-01 端口签名 / V1 行为**全部零变更**；只新增 Core 内部值类型与纯函数 + backend 事务内重读） |
| **REV-24** | **门禁执行顺序未明确写出，且存在「把 plan 阶段检查当作 apply 阶段安全保证」的风险。** R3 §8.3.5 只列 A/B 两道门禁与写后复核，未规定**开事务/重读/判定/写入/复核/提交/回滚**的先后，也未规定**状态优先级**与**事务所有权**；§8.3.2 与 §8.3.5 各有一份 apply 伪代码，易分叉 | **新增 §8.3.7「门禁执行顺序（十步，不得颠倒）」**：**① 开启事务 → ② 检查全局版本同构（A）→ ③ 重新读取当前全表必要字段 → ④ 验证计划覆盖范围和唯一性（B）→ ⑤ 验证每行快照与当前数据库状态一致（C）→ ⑥ 再次验证新键唯一性 → ⑦ 执行批量更新 → ⑧ 写后验证版本同构与唯一约束 → ⑨ 全部通过后提交 → ⑩ 任一环节失败整体回滚**，逐步给出**失败处理**；**明文写出「不要把计划生成阶段的检查当作 apply 阶段的安全保证」**（§8.3.5 第 7 点同口径）；**状态优先级 A→B→C**（`refused_version_drift` / `refused_incomplete_plan` / `refused_stale_plan`），**`(source_id,new_key)` 重复归 B、重复 `link_id` 归 C**；**事务所有权**：apply **独占 `with session.begin():`**，**不得在已有活动事务或 savepoint 内调用**，本轮**无 HTTP/CLI 入口**（D8），未来 CLI 须干净 Session + 静默期 + 备份 + 留痕；**给出唯一权威 apply 伪代码**，§8.3.2 旧块改为**指向 §8.3.7 的指针**（消除两份分叉）；SQLAlchemy 行为预期标注**【待验证】** | **§8.3.7（新增全节）** / §8.3.2（伪代码改为指针）/ §8.3.5 第 7 点 / §8.4.4 / §8.4.7 步 5 / §12 约束 6·7 / §13.1（十步顺序验收项）/ §14 第 3 点 | **T39**（十步顺序调用序列守护 + 任一门禁失败后不得出现 UPDATE + 写后非键列与第 3 步重读值逐列相等 + 故障注入整体回滚 + 事务所有权）/ **T40④**（apply 不得在 savepoint 内调用）。**全部【待验证】** | **无**（执行顺序与事务所有权属实现纪律，不改任何契约） |
| **REV-25** | **① 计划摘要必要性未论证**（审查 §四 要求检查是否需要为 `LinkRebuildPlan` 增加确定性计划摘要，若不加必须解释原因，且不得无必要引入新 Hash 契约）；**② R3 的「事务内缓存」方案不安全**（审查 §五）：把「仓库实例生命周期 = Session 生命周期 = 数据库事务生命周期」当作前提，而 **SQLAlchemy 2.x autobegin 使 commit 后 / rollback 后同一 Session 开启新事务**，`begin_nested()` 的 **savepoint 又不结束外层事务**，`join_transaction_mode` 下 `begin()` 还可能依附外部事务 ⇒ **缓存失效条件无法证明**，会**跨事务复用旧版本集合** → 守卫误判放行 → 写出混合版本；**③ T20③ 的「DISTINCT 查询计数 == 1」编码的正是该被撤回的方案**，与保守方案直接矛盾 | **① 结论：不新增计划摘要（§8.3.8）**。四机制——**frozen Pydantic（`ConfigDict(frozen=True)`）+ `tuple` 字段**、**双向全覆盖 + `link_id` 唯一**、**6 字段精确比对**、**每行新键重算**——**强于摘要**：摘要的前提「计划在生成时正确」恰是本轮失效的前提，**「数据库已变、计划未变」时摘要完全无用**；摘要唯一能补的缺口（计划自身被篡改）已由**新键重算**覆盖且更强。明确 ❌ **不加摘要字段 / 不用内置 `hash()` / 不改三 Hash 与 `canonicalization_version` / 不进交换载荷与白名单 / 不新增数据库字段·表·索引·迁移**；✅ 保留确定性 `model_dump(mode="json")` 供留痕；**跨进程/落盘重载计划的威胁面本轮不存在**，将来出现须该批次重新评估（**【待审批】**）。**② 撤回缓存，采用无缓存保守方案（§8.4.3（1）–（6））**：给出 R3 假设的**三行反证表** + **可复现失效路径伪代码** + **SQLAlchemy 真实事务语义**（autobegin / `SessionTransaction` 才是事务对象 / savepoint 与 nested 边界 / join transaction mode，行为断言标**【待验证】**）+ **最终策略表**（缓存**从不建立**、失效**不适用**、**每次受守卫写入在同一事务内写入之前重新执行单列 DISTINCT**、结果**仅限本次判定调用栈**、事务由调用方持有、**有效性唯一依据 = 同一事务**、**不得仅以 Session 对象是否存在判断**、豁免写入不预检、apply 批量写门禁 A 恰 1 次、InMemory 同口径）+ **正确性论证** + **诚实成本量化（k 次写入 = k 次单列扫描）** + **savepoint/nested 七场景边界表** + **分层约束保持（Core 纯函数 / backend 查询 / 不新增端口方法 / 零方言分支）**。**③ T20③ 期望值修订**：`== 1` → **`== 受守卫写入次数`（该场景 5）**，**保留 T20 编号与 ①②④⑤ 全部断言**，显式标注「**R3.1 断言修订，非删除测试**」，**权威断言另见新增 T34**；修订后断言**更强**，旧期望值在新设计下属**错误规格** | **§8.3.8（新增全节）** / **§8.4.3（重写：标题 + 权威执行点措辞 + 代码注释 + 豁免推论 + 成本 + （1）–（6））** / §8.4.8 第 4·5 条 / §7.5 **T20③** / §7.7（无缓存 + 不可变 + 事务所有权守护）/ §7.8 / §9（缓存行改为已撤回 + 新增 savepoint 行）/ §10 **R26** + R5 修正 / §11 **E6** / §12 b·d + 约束 8 / §13.1（摘要与生命周期两项）/ §13.2（摘要与缓存优化均【待审批】）/ §14 第 4·5 点 | **T38**（frozen 赋值抛异常 + `tuple` 非 `list` + apply 前后 `model_dump` 字节相同 + 两次 plan 序列化字节相同 + 无摘要字段 + 不用内置 `hash()` + 三 Hash 与白名单零改动）/ **T32**（commit 后新事务重新预检，断言 Session 同一个）/ **T33**（rollback 后新事务重新预检，含撤销本事务写入）/ **T34**（**权威计数断言**：k 次写入 = k 次预检、豁免 0 次、apply 门禁 A 恰 1 次、无缓存属性结构守护、InMemory 同口径）/ **T40**（savepoint/nested 边界 + 事务身份变化 + 仓库不主动 commit/rollback/begin_nested）/ **T20③ 修订**。**全部【待验证】** | **无**。**特别明确：不新增任何 Hash 契约**（计划摘要被论证为不必要且更弱）；**不新增数据库字段/迁移**；**不改端口签名**；**Core 纯函数 / backend 查询分层不变** |
| **REV-26** | **R3.1 轮测试编号、规模、清单、台账、门禁、基线复核与诚实性声明需随修订同步**；R3 稿止于 T1–T21 / H1–H20 / ~520 用例 / §8.5.6 九项 / §11 E1–E5 / §12 四条约束 / §14 结论止于 R3 | **§7.5.1 新增 T22–T40（19 条，全部【待验证】）**，**紧接 T21 之后追加，不覆盖·不删除·不改号既有测试**；给出**与用户 §六 13 项的逐项对应表**（①→T22 … ⑬→T34）+ **T35–T40 六项配套理由**；**§7.8 规模 ~520 → ~580**（纯文本 ~95 / 服务层 ~235 / SQLite ~115 / PG ~115 / 守护 +23），明文标注「**本轮（R3.1）未运行任何测试、未编写任何测试文件，全部为估算**」；**§8.5.6 清单 9 → 12 项**（过期计划零写入 / commit·rollback 重新预检 / savepoint 边界）；**§7.7 新增 5 条 R3.1 守护**；**§10 新增 R25·R26 + R5 修正**；**§11 改为 D1–D12 + A/B + E1–E5 + E6 台账**（E4 标已批准 + 补 C，E5 标不再讨论）；**§12 b–f 门禁更新 + 顺序约束 4 → 8 条**；**§13.1 新增 4 项验收 + 修订 3 项 + R3.1 措辞纪律**（门禁 C 不得写成「并发安全/互斥已保证」）；**§13.2 新增 4 项延后（行锁方案 / 计划摘要 / 缓存优化 / `refused_stale_plan` 的 HTTP 映射，均【待审批】或属后续批次）**；**§14 结论重写为 R3.1（7 点 + 等待事项）**；新增 **§1.7 R3.1 开工前真实复核表**、**§15.7 改动文件清单**、**§15.8 真实核验输出**、**§15.9 冻结声明**；**§15.6 标为已被 §15.9 取代**；标题与版次改为 **R3.1（Design Only）**；**全文一致性清扫（消除与门禁 C / 无缓存策略矛盾的残留表述）**：**§3②③ 模块职责图**（`LinkKeyRebuild` 补 `row_snapshots`/`observed_row_count`/`requires_replan`；仓库预检由「同一事务内最多预检一次（实例级缓存）」改为「**无缓存，每次受守卫写入重新预检**」；apply 由 A/B 两门禁改为 **A/B/C + 新键唯一性再验证 + 十步顺序**）；**§4.1**（`link_service.py` 追加 `LinkRowState`/`PlanFreshnessResult`/`LinkStaleReason`/`check_plan_freshness()` 与计划新字段；`backend/app/services/links.py` 删除「事务内一次缓存」、把「双重门禁」改为「四重门禁 A/B/C + 写后复核 + 独占单事务十步顺序」；3 个测试文件补 T22–T40 范围）；**§4.2**（`markdown/__init__.py` 追加导出、`ports.py` 明示不新增端口方法、`helpers.py` 无缓存、`test_interfaces.py` +5 条守护）；**§5.2 问 6**（补门禁 C 与「plan 检查 ≠ apply 保证」）、**问 7 新增第 8 点**（过期拒绝零写入使结论更强 + **不新增任何 Hash 契约/摘要字段/内置 `hash()`/数据库字段**）；**§7.4**（「预检事务性与成本」由「同一 Session/事务、只预检一次」改为「**同一数据库事务、无缓存 ⇒ k 次写入 = k 次预检**」并指向 T20③/T32/T33/T34/T40；「重建执行边界 DB 级」补门禁 C 的真实拒绝与零写入断言 T22–T31/T35–T37/T39）。**历史章节（§1.6、§15.4–15.6、REV-01–REV-22）按原样保留，不回改历史记录** | §1.7 / §7.5 / **§7.5.1** / §7.7 / §7.8 / §8.5.6 / §9 / §10 / §11 / §12 / §13.1 / §13.2 / §14 / **§15.7–15.9** / 标题与版次 / §0 / **§3 / §4.1 / §4.2 / §5.2 / §7.4（一致性清扫）** | 非新增测试本身，属**编号/规模/门禁/台账/核验证据/全文一致性**同步；T22–T40 见 REV-23/24/25 | **无** |

### 15.1 本轮（R2）改动文件清单

| 文件 | 改动 | 是否业务代码 |
|---|---|---|
| `docs/audit/V2-A1-03-implementation-plan.md` | **本文件**：R1 → R2 修订（新增 §1.5 / §8.3.1–8.3.4 重写 / §8.4 / §8.5 / §7.5 / §7.6 / §15；改写 §11 为裁决台账；修正 §5.2 / §5.4 / §5.5 / §6.2 / §6.4 / §6.5 / §7.2 / §7.3 / §7.4 / §9 / §10 / §12 / §13 / §14） | ❌ 否（计划文档） |

**本轮未改动**：任何 `.py` 业务代码、任何测试文件、任何迁移、`models.py`、`ports.py`、`markdown/*`、前端任何文件、`uv.lock`/`package-lock.json`/任何 `pyproject.toml`/`package.json`、设计文档 `docs/plans/V2-*.md`、A1-01/A1-02 验收报告、`docs/audit/V2-A1-03-baseline/*` 四个基线工件。**未安装依赖、未运行实现、未运行测试套件、未 commit/push/reset/stash/checkout --。**

### 15.2 R2 轮真实核验输出（只读）

```
$ git rev-parse HEAD
6d91718344ca1bccd3f3971f4fed7fd9576b670d
$ git rev-parse --abbrev-ref HEAD
fix/m0-admission-and-m5-regressions
$ git stash list
（空）
$ sha256sum -c docs/audit/V2-A1-03-baseline/manifest.sha256
… 21 行全部 OK（backend/app/models.py … docs/acceptance/V2-A1-02-…md）
$ git diff > /tmp/current.diff && cmp /tmp/current.diff docs/audit/V2-A1-03-baseline/a1-01-a1-02-tracked.patch
（无输出 = 逐字节相同；两者均 1173 行）
$ git status --porcelain uv.lock frontend/package-lock.json pyproject.toml \
      backend/pyproject.toml knowledge-core/pyproject.toml frontend/package.json
（空 = 零漂移）
```

### 15.3 R2 冻结声明（历史保留，已被 §15.6 取代）

**本 R2 计划为待最终审查的冻结稿。** 收到最终独立审查通过 + 明确实施批准前，**不写任何业务代码、不运行实现、不安装依赖、不改迁移、不提交 Git**。实施阶段若发现本计划与代码现实存在**真正阻塞实现的矛盾**，只报告该阻塞问题并暂停，不擅自扩大改动、不重开宏大设计讨论。

> R2 稿经第二轮（最终）独立审查，指出两个实现正确性问题（全局版本守卫、导入空间语义）与一个交付边界问题（人工绑定）。**R3 已按裁决全部修订**，当前待审查稿为 **R3**，冻结声明见 **§15.6**。

### 15.4 本轮（R3）改动文件清单

| 文件 | 改动 | 是否业务代码 |
|---|---|---|
| `docs/audit/V2-A1-03-implementation-plan.md` | **本文件（R3 唯一改动文件）**：R2 → R3 修订。**新增** §1.6 / §2.5⚠ / **§6.6** / **§6.7** / **§8.3.5** / §15.4–15.6 / **T13–T21** / **H13–H20** / **R20–R24** / **REV-16–REV-22** / §11 的 **E1–E5** 台账 / §12 的 4 条顺序约束。**重写** §8.4（→ 8.4.1–8.4.8）/ §8.3.2 伪代码 / §14 结论 / §3 四层职责图 / §7.5 与 §7.6 标题及分层口径 / T11、T12。**修正** 标题与版次 / §0 / §4.1 / §4.3 / §5.2 问 6·问 7 / §6.2 / §6.4 / §6.5 / §7.2 J·L·M / §7.4 / §7.7 / §7.8（~420→~520，标注未运行）/ §8.3.4 / §8.5.3–8.5.6（清单 6→9 项）/ §9（+4 行）/ §10（R14 重写、R2 陈旧措辞）/ §11 标题 / §12 b–f 门禁 / §13.1（+诚实性前置声明与措辞纪律）/ §13.2 / §15 标题与口径 | ❌ 否（计划文档） |

**本轮未改动**：任何 `.py` 业务代码、**任何测试文件（未新增）**、任何迁移、`models.py`、`ports.py`、`markdown/*`、前端任何文件、`uv.lock`/`package-lock.json`/任何 `pyproject.toml`/`package.json`、**设计文档 `docs/plans/V2-*.md`**、A1-01/A1-02 验收报告、`docs/audit/V2-A1-03-baseline/*` 四个基线工件、`MILESTONES.md`、`AGENTS.md`。
**本轮未执行**：安装依赖、运行实现、**运行任何测试套件**、`ruff format`、commit / push / reset / stash / `checkout --` / `clean`。**未开始 A1-03a。**

### 15.5 R3 轮真实核验输出（只读，本轮真实执行）

```
$ git rev-parse HEAD
6d91718344ca1bccd3f3971f4fed7fd9576b670d
$ git rev-parse --abbrev-ref HEAD
fix/m0-admission-and-m5-regressions
$ git stash list
（空）
$ git rev-parse 2d2b634
2d2b63443a3ba1290aafe03be5f5e3281ffa280f
$ git merge-base --is-ancestor 2d2b634 HEAD && echo M0_IS_ANCESTOR_OK
M0_IS_ANCESTOR_OK                      # M0 初始提交未被改写

$ sha256sum -c docs/audit/V2-A1-03-baseline/manifest.sha256     # 必须在仓库根执行
backend/app/models.py: OK
backend/tests/test_fts_backfill.py: OK
backend/tests/test_migrations.py: OK
backend/tests/test_retrieval_pg.py: OK
knowledge-core/src/knowledge_core/domain/__init__.py: OK
knowledge-core/src/knowledge_core/domain/entities.py: OK
knowledge-core/src/knowledge_core/ports.py: OK
knowledge-core/tests/test_interfaces.py: OK
backend/alembic/versions/0006_v2_markdown_kb.py: OK
backend/tests/test_v2_models.py: OK
backend/tests/test_v2_models_pg.py: OK
knowledge-core/tests/test_v2_entities.py: OK
knowledge-core/src/knowledge_core/markdown/__init__.py: OK
knowledge-core/src/knowledge_core/markdown/canonical.py: OK
knowledge-core/src/knowledge_core/markdown/frontmatter.py: OK
knowledge-core/src/knowledge_core/markdown/codec.py: OK
knowledge-core/tests/test_markdown_canonical.py: OK
knowledge-core/tests/test_markdown_frontmatter.py: OK
knowledge-core/tests/test_markdown_codec.py: OK
docs/acceptance/V2-A1-01-data-model-and-migration.md: OK
docs/acceptance/V2-A1-02-markdown-codec-and-frontmatter.md: OK
# 统计：manifest 共 21 行，": OK" 计数 = 21 → 21/21 全 OK，0 FAILED

$ git diff > /tmp/r3-current.diff
$ cmp /tmp/r3-current.diff docs/audit/V2-A1-03-baseline/a1-01-a1-02-tracked.patch
PATCH_CMP_IDENTICAL                    # cmp 无差异输出
$ wc -l < /tmp/r3-current.diff                                  → 1173
$ wc -l < docs/audit/V2-A1-03-baseline/a1-01-a1-02-tracked.patch → 1173
# （git diff 附带 4 条 LF→CRLF 提示，属 Windows 换行警告，不影响字节比对结果）

$ git status --porcelain > /tmp/r3-status.txt
$ cmp /tmp/r3-status.txt docs/audit/V2-A1-03-baseline/git-status.txt
STATUS_CMP_IDENTICAL                   # 未提交改动集合与基线完全一致（8 改 13 增）

$ git status --porcelain uv.lock frontend/package-lock.json pyproject.toml \
      backend/pyproject.toml knowledge-core/pyproject.toml frontend/package.json
（空 = 零漂移）
$ git diff --stat -- <同上六个文件>
（空 = 零漂移）

$ git status --porcelain docs/audit/
?? docs/audit/                         # 计划文档与基线工件仍未跟踪，未入库
$ wc -l < docs/audit/V2-A1-03-implementation-plan.md
1555                                   # R2 为 1080 行，R3 净增 475 行（收工后实测）
```

> **收工后复跑（第二遍，结果一致）**：`git diff > /tmp/r3-final.diff` + `cmp` → `PATCH_IDENTICAL`；`git status --porcelain > /tmp/r3-final-status.txt` + `cmp` → `STATUS_IDENTICAL`；`sha256sum -c … | grep -c ": OK$"` → **21**；HEAD / 分支 / stash / 六个锁定与配置文件漂移 → 与上表完全一致。**两遍均为只读命令，未产生任何仓库写入。**

**核验结论（如实区分）**：

| 项 | 结果 |
|---|---|
| HEAD / 分支 / stash | ✅ 已验证：`6d91718…` / `fix/m0-admission-and-m5-regressions` / stash 空 |
| M0 初始提交 `2d2b634` | ✅ 已验证：存在且为 HEAD 祖先，未被改写 |
| 21 个交付文件 SHA-256 | ✅ 已验证：**21/21 OK，0 FAILED**（仓库根执行） |
| baseline patch 逐字节 | ✅ 已验证：`cmp` 无差异，两者均 **1173 行** |
| `git status --porcelain` | ✅ 已验证：与 `baseline/git-status.txt` **逐字节相同** |
| 锁定文件 / pyproject / package.json 漂移 | ✅ 已验证：**零漂移**（status 与 diff --stat 均空） |
| 本轮改动文件数 | ✅ 已验证：**仅 1 个**（本计划文档，未跟踪） |
| 业务代码 / 测试文件 / 迁移 / 设计文档 | ✅ 已验证：**零改动**（由 status 与 patch 比对共同证明） |
| 测试套件运行结果 | ⏳ **本轮未运行**（用户明确要求不运行实现或测试）。§7.8 的 ~520 用例**全部为估算**，§13.1 各项**全部为未验证**，**不得写成 PASS** |
| PostgreSQL 真实连接 | ⏳ **本轮未连接**（未运行测试）。真实 PG 16.8 便携实例（端口 55432）在 A1-02 已验证可用，**A1-03 实施阶段须重新真实连接验证**，不得沿用旧结论 |

### 15.6 R3 冻结声明（历史保留，**已被 §15.9 取代**）

> **R3.1 说明**：本节是 R3 稿的冻结声明，**保留以供追溯**。上一轮独立审查结论为 **E1/E2/E3/E5 已通过、E4 职责拆分已批准但须补门禁 C**，故 R3 稿**不再是当前待审查稿**；**当前待审查稿为 R3.1，冻结声明见 §15.9**。下文第 8 条的「4 条顺序约束」在 R3.1 已扩为 **8 条**（§12）。

**本 R3 计划为待最终独立审查的冻结稿。** 第二轮审查的三项意见（E1 全局版本同构守卫 / E2 导入绑定空间语义 / E3 人工绑定交付边界）**已全部按裁决落实**，并如实报告两项自主处置（**E4 §8.3.5 重建执行边界拆分**、**E5 §2.5⚠ Core 侧空间过滤**）供确认。

收到**最终独立审查通过 + 明确实施批准**前：

1. **不写任何业务代码**、**不新增任何测试文件**、**不运行实现或测试套件**、**不安装依赖**、**不改迁移**、**不改设计文档**、**不提交 / 不推送 / 不重置 / 不 stash**。
2. **不得开始 A1-03a**（乃至任何 A1-03 子步）。
3. 不删除或简化任何既有安全机制（三 Hash、`canonicalization_version`、`normalized_link_key`、`link_normalization_version`、ImportOrigin、源 hash、GC 隔离、租约/fencing、Manifest、`operation_id`、`generation_id`、`resource_version`）。
4. 不自行增加需审批的依赖（**PyYAML / KaTeX / DOMPurify / python-magic / CodeMirror 6 / react-markdown 一律不装**）。
5. 不擅自修改 V1 已验证功能；不把临时测试文件、数据库、日志、构建产物提交进 Git。
6. **对于尚未验证的内容，不得写成 PASS。**
7. 实施阶段若发现本计划与代码现实存在**真正阻塞实现的矛盾**，**只报告该阻塞问题并暂停**；若只是可在实现阶段确定的普通实现细节，按设计原则选择合理实现，**不重开宏大设计讨论**。
8. 严格按 **A1-03a → b → c → d → e → f** 顺序推进（含 §12 的 4 条顺序约束），**不一次性把 A1 全部写完**；A1-03f 完成后停止，**不自行宣布进入 A1-04**。

### 15.7 本轮（R3.1）改动文件清单

| 文件 | 改动 | 是否业务代码 |
|---|---|---|
| `docs/audit/V2-A1-03-implementation-plan.md` | **本文件（R3.1 唯一改动文件）**：R3 → R3.1 修订。**新增** **§1.7**（开工前真实复核）/ **§7.5.1（T22–T40，19 条，全部【待验证】）** / **§8.3.6（门禁 C 全节）** / **§8.3.7（十步执行顺序 + 状态优先级 + 事务所有权 + 唯一权威 apply 伪代码）** / **§8.3.8（不新增计划摘要的论证）** / **§8.4.3（1）–（6）（Session ≠ 事务、autobegin、savepoint 边界、无缓存最终策略、分层保持、T20③ 修订说明）** / **§10 R25·R26** / **§11 E6** / **§12 顺序约束 5–8** / **§15.7–15.9** / **REV-23–REV-26**。**重写** §8.4.3 标题·权威执行点措辞·backend 代码注释·成本段 / §8.4.4（4 → 7 条门禁）/ §8.4.7（+ 步 3c 拒绝后必须重生成、+ 步 5 事务纪律）/ §8.4.8（3 → 5 条诚实限制）/ §8.3.2 阶段 4 与 apply 块（产出 `row_snapshots`；apply 改为指向 §8.3.7 的指针）/ §14 结论（R3.1 七点 + 等待事项）。**修正** 标题与版次（R3.1，Design Only）/ §0 / §7.5 标题·引言·**T20③ 期望值**·T21 说明·明确不做 / §7.7（+5 条守护）/ §7.8（~520 → ~580，标注未运行）/ §8.3.4（三重 → 四重门禁）/ §8.3.5（职责表 + 第 3·5·6·7 点 + 测试范围 + 契约判定）/ §8.5.5 / §8.5.6（9 → 12 项）/ §9（缓存行改为已撤回 + 新增 3 行）/ §10 R5 / §11 标题·引言·E4·E5 / §12 b–f 门禁 / §13.1（前置声明 + R3.1 措辞纪律 + 4 项新验收 + 3 项修订）/ §13.2（+4 项延后，含【待审批】）/ §15 标题·口径 / §15.6（标为已被取代）/ **§3②③ 模块职责图（`LinkKeyRebuild` 产出 `row_snapshots`；仓库预检改无缓存；apply 改四重门禁 + 十步顺序）** / **§4.1（`link_service.py` 追加 R3.1 值类型与纯函数；`backend/app/services/links.py` 撤回「事务内一次缓存」、改「四重门禁 A/B/C」；3 个测试文件补 T22–T40 范围）** / **§4.2（`markdown/__init__.py` 追加导出、`ports.py` 不新增端口方法、`helpers.py` 无缓存、`test_interfaces.py` +5 条守护）** / **§5.2 问 6（补门禁 C 与十步顺序）、问 7（新增第 8 点：过期拒绝零写入 + 不新增任何 Hash 契约）** / **§7.4（预检事务性与成本改无缓存口径；重建执行边界 DB 级补门禁 C 与 T22–T40）** | ❌ 否（计划文档） |

**本轮未改动**：任何 `.py` 业务代码、**任何测试文件（未新增、未修改）**、任何迁移、`models.py`、`ports.py`、`markdown/*`、`backend/app/**`、`knowledge-core/src/**`、前端任何文件、`uv.lock`/`package-lock.json`/任何 `pyproject.toml`/`package.json`、**V2 主设计文档 `docs/plans/V2-*.md`**、**依赖选型文档**、A1-01/A1-02 既有实现与验收报告、`docs/audit/V2-A1-03-baseline/*` 四个基线工件、`MILESTONES.md`、`AGENTS.md`。
**本轮未执行**：编写业务代码、新增测试文件、运行实现代码或测试套件、安装依赖、修改数据库迁移、`ruff format`、commit / push / reset / stash / `checkout --` / clean。**未开始 A1-03a。**

### 15.8 R3.1 轮真实核验输出（只读，本轮真实执行；开工前 + 收工后各一遍）

```
$ git rev-parse HEAD
6d91718344ca1bccd3f3971f4fed7fd9576b670d
$ git rev-parse --abbrev-ref HEAD
fix/m0-admission-and-m5-regressions
$ git stash list
（空）
$ git rev-parse 2d2b634
2d2b63443a3ba1290aafe03be5f5e3281ffa280f
$ git merge-base --is-ancestor 2d2b634 HEAD && echo M0_IS_ANCESTOR_OK
M0_IS_ANCESTOR_OK                      # M0 初始提交未被改写

$ sha256sum -c docs/audit/V2-A1-03-baseline/manifest.sha256     # 必须在仓库根执行
backend/app/models.py: OK
backend/tests/test_fts_backfill.py: OK
backend/tests/test_migrations.py: OK
backend/tests/test_retrieval_pg.py: OK
knowledge-core/src/knowledge_core/domain/__init__.py: OK
knowledge-core/src/knowledge_core/domain/entities.py: OK
knowledge-core/src/knowledge_core/ports.py: OK
knowledge-core/tests/test_interfaces.py: OK
backend/alembic/versions/0006_v2_markdown_kb.py: OK
backend/tests/test_v2_models.py: OK
backend/tests/test_v2_models_pg.py: OK
knowledge-core/tests/test_v2_entities.py: OK
knowledge-core/src/knowledge_core/markdown/__init__.py: OK
knowledge-core/src/knowledge_core/markdown/canonical.py: OK
knowledge-core/src/knowledge_core/markdown/frontmatter.py: OK
knowledge-core/src/knowledge_core/markdown/codec.py: OK
knowledge-core/tests/test_markdown_canonical.py: OK
knowledge-core/tests/test_markdown_frontmatter.py: OK
knowledge-core/tests/test_markdown_codec.py: OK
docs/acceptance/V2-A1-01-data-model-and-migration.md: OK
docs/acceptance/V2-A1-02-markdown-codec-and-frontmatter.md: OK
$ sha256sum -c … | grep -c ": OK$"
21                                     # manifest 共 21 行 → 21/21 全 OK，0 FAILED

$ git diff > /tmp/r31-current.diff
$ cmp /tmp/r31-current.diff docs/audit/V2-A1-03-baseline/a1-01-a1-02-tracked.patch
PATCH_CMP_IDENTICAL                    # cmp 无差异输出
$ wc -l < /tmp/r31-current.diff                                  → 1173
$ wc -l < docs/audit/V2-A1-03-baseline/a1-01-a1-02-tracked.patch → 1173
# （git diff 附带 LF→CRLF 提示，属 Windows 换行警告，不影响字节比对结果）

$ git status --porcelain > /tmp/r31-status.txt
$ cmp /tmp/r31-status.txt docs/audit/V2-A1-03-baseline/git-status.txt
STATUS_CMP_IDENTICAL                   # 未提交改动集合与基线完全一致（8 改 13 增）

$ git status --porcelain uv.lock frontend/package-lock.json pyproject.toml \
      backend/pyproject.toml knowledge-core/pyproject.toml frontend/package.json
（空 = 零漂移）
$ git diff --stat -- <同上六个文件>
（空 = 零漂移）

$ git status --porcelain docs/audit/
?? docs/audit/                         # 计划文档与基线工件仍未跟踪，未入库
$ wc -l < docs/audit/V2-A1-03-implementation-plan.md
2049                                   # R3 为 1555 行，R3.1 净增 494 行（收工后实测）
```

**核验结论（如实区分事实 / 未验证）**：

| 项 | 结果 |
|---|---|
| HEAD / 分支 / stash | ✅ **事实（已验证）**：`6d91718344ca1bccd3f3971f4fed7fd9576b670d` / `fix/m0-admission-and-m5-regressions` / stash 空 |
| M0 初始提交 `2d2b634` | ✅ **事实（已验证）**：存在且为 HEAD 祖先，未被改写 |
| 21 个交付文件 SHA-256 | ✅ **事实（已验证）**：**21/21 OK，0 FAILED**（仓库根执行 `sha256sum -c`） |
| baseline patch 逐字节 | ✅ **事实（已验证）**：`cmp` 无差异（`PATCH_CMP_IDENTICAL`），两者均 **1173 行** |
| `git status --porcelain` | ✅ **事实（已验证）**：与 `baseline/git-status.txt` **逐字节相同**（`STATUS_CMP_IDENTICAL`） |
| 锁定文件 / pyproject / package.json 漂移 | ✅ **事实（已验证）**：**零漂移**（status 与 diff --stat 均空） |
| 本轮改动文件数 | ✅ **事实（已验证）**：**仅 1 个**（本计划文档，未跟踪） |
| 业务代码 / 测试文件 / 迁移 / Core / Backend / Frontend / 设计文档 / 依赖文档 | ✅ **事实（已验证）**：**零改动**（由 status 与 patch 逐字节比对共同证明） |
| 开工前基线一致性 | ✅ **事实（已验证）**：9 项全部与基线一致后才开始修改文档，**未覆盖任何内容**（§1.7） |
| 门禁 C / 十步顺序 / 无缓存策略的设计正确性 | ⏳ **待验证**：本轮为 Design Only，**未写实现、未跑测试**；论证见 §8.3.6–8.3.8 / §8.4.3，须由 **T22–T40** 在实施阶段真实验证 |
| 测试套件运行结果 | ⏳ **本轮未运行**（用户明令禁止）。§7.8 的 **~580 用例全部为估算**，**T22–T40 全部【待验证】**，§13.1 各项**全部未验证**，**不得写成 PASS** |
| SQLAlchemy autobegin / savepoint 行为 | ⏳ **待验证**：§8.4.3（2）为**设计依据与预期行为**，须由 **T32/T33/T40** 实测确认；若与预期不符以实测为准并回报 |
| PostgreSQL 真实连接 | ⏳ **本轮未连接**（未运行测试）。真实 PG 16.8 便携实例（端口 55432）在 A1-02 已验证可用，**A1-03 实施阶段须重新真实连接验证**，不得沿用旧结论，**不得虚报连接成功** |
| 残余并发窗口（apply 重读→提交） | ⏳ **本轮未关闭**（不用行锁/表锁），方案**【待审批】**；**不得宣称并发安全或互斥**（§8.4.8 第 2 条） |
| 跨进程计划摘要 / 带事务身份键的缓存 / 版本索引 | ⏳ **本轮不引入**，均**【待审批】**另批提议（§8.3.8 / §8.4.3（3）/ §13.2） |

### 15.9 R3.1 冻结声明（**当前待审查稿**）

**本 R3.1 计划为待最终批准的冻结稿。** 上一轮独立审查结论已按要求落实：**E1、E2、E3、E5 已通过（本轮不重新设计、E5 不再讨论、批准状态不变）**；**E4 的 Core plan / backend apply 职责拆分已批准，本轮补充其必须项——门禁 C**，并落实审查 §五 的**事务缓存生命周期修订**。新增台账编号 **E6**，修订记录 **REV-23–REV-26**，风险 **R25–R26**，测试 **T22–T40**。**R3 原有已批准设计全部保留。**

**本轮性质：Design Only（只修改本计划文档）。** 收到**最终批准**前：

1. **不编写业务代码**、**不新增测试文件**、**不运行实现代码或测试套件**、**不安装依赖**、**不修改数据库迁移**、**不修改 Core / Backend / Frontend**、**不修改 A1-01/A1-02 既有实现**、**不修改 V2 主设计文档**、**不修改依赖选择文档**、**不修改 lockfile**、**不提交或推送 Git**、**不 reset / checkout / stash**。
2. **不得开始 A1-03a**（乃至任何 A1-03 子步）。**本轮目标是形成可供最终批准的 R3.1 实施计划，不是提前实施功能。**
3. 不删除或简化任何既有安全机制（三 Hash、`canonicalization_version`、`normalized_link_key`、`link_normalization_version`、ImportOrigin、源 hash、GC 隔离、租约/fencing、Manifest、`operation_id`、`generation_id`、`resource_version`）；**不删除已有有效测试**（T20③ 为**期望值修订**，非删除）。
4. **不新增任何 Hash 契约**（含计划摘要）、**不使用 Python 内置 `hash()`**、**不新增数据库字段/表/索引/迁移**、**不改 A1-01 端口签名**。
5. 不自行增加需审批的依赖（**PyYAML / KaTeX / DOMPurify / python-magic / CodeMirror 6 / react-markdown 一律不装**）。
6. 不擅自修改 V1 已验证功能；不把临时测试文件、数据库、日志、构建产物提交进 Git。
7. **对于尚未验证的内容，不得写成 PASS**；**T22–T40 一律【待验证】**；**不得宣称 PostgreSQL 连接成功或测试通过**。
8. **不得把门禁 C 描述为「并发安全 / 互斥已保证」**；残余窗口如实记录为未关闭（§8.4.8）。**不得把人工绑定描述为已交付用户功能**（§6.7）。
9. 实施阶段若发现本计划与代码现实存在**真正阻塞实现的矛盾**，**只报告该阻塞问题并暂停**；若只是可在实现阶段确定的普通实现细节，按设计原则选择合理实现，**不重开宏大设计讨论**。
10. 严格按 **A1-03a → b → c → d → e → f** 顺序推进（含 §12 的 **8 条顺序约束**），**不一次性把 A1 全部写完**；A1-03f 完成后停止，**不自行宣布进入 A1-04**。
11. **【待审批】事项不得自行实施**：关闭残余窗口的行锁/表锁方案、跨进程计划摘要、带事务身份键的缓存或版本索引（§13.2）。