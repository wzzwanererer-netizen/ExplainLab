# ExplainLab V2 A1-03 独立技术审计材料包

> **用途**：供独立审计核验 A1-03（E1–E4）的实现、测试与边界遵守。本包**只汇总证据，不修改任何业务代码**。
> **审计对象提交**：`715d9e7`（feat：四层实现 + 测试）、`7e0582c`（docs：验收记录 + 计划状态）。
> **A1-03 开工基线**：`5d6dcf1`（A1-01/A1-02 已提交后的 HEAD）。
> **分支**：`fix/m0-admission-and-m5-regressions`（未切换、**未 push**）。
> **编制日期**：2026-11-20。
> **环境（实测）**：Python 3.11.9 / uv 0.13.6 / SQLite 3.45.1 / 真实 PostgreSQL 16.8（`127.0.0.1:5432`，库 `explainlab_test`）/ Node 22.23.2。Windows 控制台 GBK，命令统一加 `PYTHONIOENCODING=utf-8`（数据本身始终 UTF-8）。

## 0. 诚实性前置声明（审计必读）

本包严格区分三态，**不得把有条件完成描述成完全通过**：

- **已验证**：真实命令实跑通过，附原始输出（`evidence/` 目录）。
- **有条件**：设计预期但本轮范围未覆盖、或存在已知残余风险，明确标注缺口与读取侧/写侧区别。
- **未验证 / 延后**：本轮未跑或留待后续批次，一律不写 PASS。

A1-03 的**五项重点审计问题**（governance 批准路径未挂接、门禁 C 残余并发窗口、人工绑定无 HTTP 写入口、v2 规则未发布、读取侧防御映射 vs 写侧状态降级）在 **§11 单独逐条说明**，并在 `known-issues.md` 登记。这些是**有条件项 / 延后项**，不是「完全通过」。

**本包编制边界核验**：编制全程仅新增 `docs/audit/V2-A1-03-audit-package/` 下的审计材料文件；`git status --porcelain` 仅显示该新目录为 untracked，**无任何业务代码、依赖、迁移、A1-01/A1-02 文件、已有提交、MILESTONES.md 被修改**（见 §9 与 §12）。

---

## 1. 材料①：A1-01 / A1-02 / A1-03 Git 提交关系

完整提交链（`evidence/git-commit-chain.txt`，`git log --format="%h parent=%p %ad %s" --date=short -8`）：

```
7e0582c  parent=715d9e7  docs: V2 A1-03 验收记录 + 计划 T22–T40 状态由【待验证】更新为【已验证】
715d9e7  parent=5d6dcf1  feat: V2 A1-03 稳定链接与反链四层实现 + 全局版本同构守卫 + 计划新鲜度门禁 C
5d6dcf1  parent=41ff761  chore: gitignore 忽略 release/ 审计交接构建产物
41ff761  parent=f847e4f  docs: V2 规划与批次 A 设计、A1-01/A1-02 验收记录、独立复审报告与 A1-03 计划归档
f847e4f  parent=6d91718  feat: V2 A1-01/A1-02 开放 Markdown 知识库底座（实体/端口 + 迁移 0006 + MarkdownCodec 与三 Hash）
6d91718  parent=3c9b28b  fix: 迁移 0004 回填历史 knowledge_item 到全文索引（SQLite FTS5 + PG tsvector）
```

线性父子关系（无合并、无重写）：

```
6d91718 (M0/M5 修复尾，A1-03 计划文档记载的历史基线 HEAD)
   └─ f847e4f  A1-01 + A1-02 功能（实体/端口/迁移 0006/MarkdownCodec/三 Hash）
        └─ 41ff761  V2 规划与 A1 设计/验收/复审/A1-03 计划归档（docs）
             └─ 5d6dcf1  release/ gitignore（chore）  ←★ A1-03 开工基线
                  └─ 715d9e7  A1-03 功能 + 测试（feat，16 文件 +8517/−6）
                       └─ 7e0582c  A1-03 验收记录 + 计划状态（docs，2 文件 +286/−21）  ←★ 当前 HEAD
```

要点：

- **A1-01 与 A1-02 同在一个 feat 提交 `f847e4f`**（底座：实体/端口 + 迁移 0006 + MarkdownCodec 与三 Hash），其验收记录在 `41ff761` 归档。两者均**早于** A1-03 开工基线 `5d6dcf1`，本批未触碰。
- **A1-03 = `715d9e7`（代码）+ `7e0582c`（文档）**，父提交分别为 `5d6dcf1` 与 `715d9e7`。
- 计划文档 `docs/audit/V2-A1-03-implementation-plan.md` 记载的「开工 HEAD `6d91718`」是**设计轮历史基线**（当时 A1-01/A1-02 尚未提交）；实施轮实际开工基线是 `5d6dcf1`。两者差异 = A1-01/A1-02 的提交 + 规划归档 + gitignore，**均非 A1-03 代码改动**。
- 提交统计原始输出：`evidence/git-feat-commit-715d9e7-stat.txt`、`evidence/git-docs-commit-7e0582c-stat.txt`。

---

## 2. 材料②：A1-03 开工基线 → 当前提交的完整 diff

**完整 diff 已落盘**：[`evidence/a1-03-full.diff`](evidence/a1-03-full.diff)（9118 行，430 KB），即 `git diff 5d6dcf1..7e0582c`（含代码 + 验收文档 + 计划状态）。

可复现命令（审计方可自行重算比对）：

```bash
# 完整 A1-03 delta（代码 + 文档），等价于 evidence/a1-03-full.diff
git diff 5d6dcf1..7e0582c

# 仅代码（feat 提交，不含验收文档/计划状态）
git diff 5d6dcf1..715d9e7

# 逐提交查看
git show 715d9e7      # feat：四层实现 + 测试（16 文件）
git show 7e0582c      # docs：验收记录 + 计划【待验证】→【已验证】（2 文件）

# 文件级摘要
git diff --stat 5d6dcf1..7e0582c        # → evidence/a1-03-diff-stat.txt
git diff --name-status 5d6dcf1..7e0582c # → evidence/a1-03-name-status.txt
```

> 完整性核验：`evidence/a1-03-full.diff` 由上述命令直接重定向生成，审计方可用 `git diff 5d6dcf1..7e0582c | cmp - evidence/a1-03-full.diff` 复算（应无差异）。

---

## 3. 材料③：新增 / 修改文件清单

`git diff --name-status 5d6dcf1..7e0582c`（`evidence/a1-03-name-status.txt`）：**18 文件 = 10 新增（A）+ 8 修改（M）**。

### 3.1 新增文件（10）

| 层 | 文件 | 行数 | 职责 |
|---|---|---|---|
| ① 纯文本 | `knowledge-core/src/knowledge_core/markdown/links.py` | 414 | 规范化 v1、两派生键、wikilink 解析 + 排除矩阵、同键合并、提示聚合、版本化规则注册表。零 IO。 |
| ② 领域服务 | `knowledge-core/src/knowledge_core/markdown/link_service.py` | 1021 | 4 服务实现 + 2 纯函数 + frozen 值类型/报告模型。只经端口取数，零 ORM。 |
| ③ 持久化 | `backend/app/services/links.py` | 464 | `SQLAlchemyLinkRepository`（10 端口方法）、全局守卫权威点、`apply_link_key_plan`、`demote_backlinks_on_delete`、`persist_rebuild_report`。唯一含 ORM/方言/文件 IO 层。 |
| ④ API | `backend/app/api/routes/links.py` | 95 | 3 只读 GET + `sync_links_or_conflict` 助手。无业务规则。 |
| 测试 | `knowledge-core/tests/test_markdown_links.py` | 331 | 层① 41 用例。 |
| 测试 | `knowledge-core/tests/test_markdown_link_service.py` | 1545 | 层② 86 用例（含 D3 签名守护、T38）。 |
| 测试 | `backend/tests/test_links.py` | 1965 | 层③ SQLite 91 用例。 |
| 测试 | `backend/tests/test_links_pg.py` | 2004 | 层③ 真实 PG 91 用例（门控）。 |
| 测试 | `backend/tests/test_links_http.py` | 345 | 层④ TestClient 19 用例（含路由守护）。 |
| 文档 | `docs/acceptance/V2-A1-03-link-services-and-version-guard.md` | 256 | 验收记录（本包多处引用）。 |

### 3.2 修改文件（8）

| 文件 | 改动性质 | 约束核验 |
|---|---|---|
| `backend/app/api/routes/knowledge.py` | 四处挂接（create / draft-PATCH / extract commit 前同步；DELETE 直接应用前降级）；active PATCH 202 不同步 | V1 端点集合守护通过（§8）。 |
| `backend/app/api/schemas.py` | 追加 `LinkOut` / `BacklinkOut` / `ResolveCandidateOut` | 既有 schema 不动。 |
| `backend/app/main.py` | 注册 links router（先于 knowledge router，R11 静态字面优先） | 既有注册顺序保留。 |
| `knowledge-core/src/knowledge_core/markdown/__init__.py` | 尾部追加 6 链接服务 ABC + `__all__` | A1-02 代码逐字不动（仅文末补换行）；293 用例全通过。 |
| `knowledge-core/src/knowledge_core/ports.py` | **仅 docstring** 澄清 `delete_links_of_item`（D3） | 10 端口签名零改动（§9，`evidence/ports-py-diff.txt`）。 |
| `knowledge-core/tests/helpers.py` | 追加 `InMemoryLinkRepository`（+105/−1） | 调用同一 Core 纯函数（单一事实来源）。 |
| `knowledge-core/tests/test_interfaces.py` | 守护扩展：子进程导入新增 2 模块；SERVICES 6→12 ABC | 独立性守护未弱化。 |
| `docs/audit/V2-A1-03-implementation-plan.md` | 实施轮注记 + 19 处【待验证】→【已验证】 | 设计轮历史措辞作为审计轨迹保留。 |

> **`governance.py` 不在修改清单**（本轮未触碰）；审核批准路径缺口见 §11.1。

---

## 4. 材料④：四层架构与模块依赖

依赖方向严格自上而下（AGENTS.md §3）：`frontend ──HTTP /api──▶ backend ──Python import──▶ knowledge-core`，**严禁反向**。

```
┌─ ④ API 装配层（backend/app/api）─────────────────────────────────────────┐
│  routes/links.py     : 3 只读 GET + sync_links_or_conflict()（409 稳定码） │
│  routes/knowledge.py : create/draft-PATCH/extract/DELETE 四处挂接          │
│  routes/governance.py: /reviews/{id}/approve（V1，本轮未改，无链接挂接）   │
│  schemas.py          : LinkOut / BacklinkOut / ResolveCandidateOut         │
│  main.py             : links router 先于 knowledge router 注册（R11）      │
└───────────────────────────────┬──────────────────────────────────────────┘
                                 │ import（装配/调用，不含业务规则）
┌─ ③ 持久化适配层（backend/app/services/links.py）──唯一 ORM/方言/文件 IO ─┐
│  SQLAlchemyLinkRepository : 10 端口方法（flush-only，vars=={"_session"}）  │
│  _precheck_global_version : 单列 SELECT DISTINCT，无缓存（权威执行点）     │
│  apply_link_key_plan      : 十步独占单事务（门禁 A→B→C→唯一性→写→复核）    │
│  demote_backlinks_on_delete : 治理列-only 降级（豁免守卫）                 │
│  _to_entity               : D12 读取侧防御映射（窄口径）                   │
│  persist_rebuild_report   : 报告落盘（backend 侧 IO）                      │
│  build_link_sync / build_link_restorer : 装配助手                          │
└───────────────────────────────┬──────────────────────────────────────────┘
                                 │ import（实现端口 / 调用纯函数）
┌─ ② 领域服务层（knowledge-core/markdown/link_service.py）──零 ORM ────────┐
│  RepositoryLinkResolver(LinkResolver)   : resolve / find_candidates        │
│  BindingFirstLinkSync(LinkSyncService)  : sync（绑定优先，不重解析既有行） │
│  LinkImportRestorer(LinkRestoreService) : restore（A1-04 导入预留）        │
│  LinkKeyRebuild(LinkRebuildService)     : plan（生成重建计划）             │
│  BacklinkQuery / LinkReresolve          : 反链查询 / 重解析（后续里程碑）  │
│  check_global_version_homogeneity()     : 纯函数（全局同构判定）           │
│  check_plan_freshness()                 : 纯函数（门禁 C 逐行新鲜度）      │
│  frozen 值类型：LinkRowState/LinkKeyUpdate/LinkRebuildPlan/Report…         │
└───────────────────────────────┬──────────────────────────────────────────┘
                                 │ import（纯文本规则）
┌─ ① 纯文本层（knowledge-core/markdown/links.py）──零 IO ──────────────────┐
│  normalize_link_text_v1 : NFKC→strip→空白折叠→casefold                     │
│  normalized_link_key_v1(title, alias) / 两派生键                           │
│  LINK_KEY_RULES={1:v1} / link_key_for_version（版本化注册表）              │
│  WikilinkParser.parse : [[标题|别名]] 解析 + 排除矩阵                      │
│  merge_same_key / group_hints_by_title_key                                 │
└──────────────────────────────────────────────────────────────────────────┘
```

**架构守护（实跑通过，`evidence/pytest-a1-02-interfaces-ruff-env.txt`）**：

- `test_core_has_no_web_framework_dependency`：干净子进程导入全部核心模块（含新增 `markdown.links` / `markdown.link_service`），断言无 `fastapi/starlette/flask/django`。
- `test_markdown_package_adds_no_new_third_party_dependency`：markdown 全包非标准库顶层白名单核对（仅 stdlib + Pydantic 栈），零新增依赖。
- `test_service_is_abstract`（参数化 12 项）：6 新 ABC + 6 既有 ABC 均不可实例化。
- 单一事实来源：`InMemoryLinkRepository`（helpers.py）与 backend 预检调用**同一** `check_global_version_homogeneity`（源码守护断言）。
- 事务所有权：仓库只 `flush()`，不 commit/rollback/begin_nested；`apply_link_key_plan` 恰一个 `session.begin()`（T39/T40 AST 守护）。

---

## 5. 材料⑤：核心服务 / 仓库 / API 调用链

### 5.1 写入同步链（create / draft-PATCH / extract）

```
HTTP POST /knowledge（或 draft PATCH / extract）
  └─ routes/knowledge.py：repository.save(item) / submit 直接应用
       └─ sync_links_or_conflict(session, item)            [routes/links.py:36]
            └─ build_link_sync(session).sync(item, item.content)   [services/links.py:453]
                 └─ BindingFirstLinkSync.sync()            [Core link_service.py:583]
                      1. links.list_links(item.id)         → SQLAlchemyLinkRepository.list_links
                      2. Core 局部守卫：既有行版本 != 常量 → raise LinkNormalizationVersionMismatch(scope="local")
                      3. WikilinkParser.parse(body) → merge_same_key
                      4. resolver.auto_candidates(item)
                      5. 既有键 → kept（原样保留，不重解析、不 churn id/时间戳）
                         新键 → resolver.resolve() → _assert_link_invariants → links.save_link()
                           └─ save_link 内 _precheck_global_version()  [全局权威预检，单列 DISTINCT，无缓存]
                                └─ check_global_version_homogeneity(versions, 常量)  [Core 纯函数]
                      6. 消失键 → links.delete_link()
                      7. 返回 LinkSyncReport
            └─ 捕获 LinkNormalizationVersionMismatch → HTTPException(409, "link_version_mismatch")
       └─ session.commit()（同步在 commit 前；409 时未 commit → 整请求零写入）
       └─ await sync_index(...)（全文/向量索引）→ session.commit()
```

**409 双触发点**（HTTP 测试实测响应体恰为 `{"detail":"link_version_mismatch"}`，见 `backend/tests/test_links_http.py`）：① Core 局部守卫（sync 检查条目自身既有行版本，纵深防御）；② backend 全局预检（`save_link` 每次 / `update_link` 仅改键改版本时）。两者均映射 409 稳定码，不回异常文本/版本明细（AGENTS.md §9）。

### 5.2 删除降级链（非 active DELETE，D12 写侧）

```
HTTP DELETE /knowledge/{id}
  └─ routes/knowledge.py：current = repository.get(id)（404 校验）
       └─ if not ReviewPolicy.is_important(DELETE_ITEM, current.status):   [非 active]
            └─ demote_backlinks_on_delete(session, id)        [services/links.py:215]
                 └─ 捕获入链（target_item_id==id）→ 置 target=NULL/resolution=missing/cross_space=False/updated_at
                    （治理列-only，键与版本不变 → 豁免全局守卫 → 版本窗口内 DELETE 不被 409 阻断）
       └─ build_review_service(session).submit(DELETE_ITEM)   [非 active 直接应用删除]
       └─ session.commit() → sync_index(remove_ids) → 204
```

> **active DELETE 走审核（202 未应用）→ 不提前降级**；批准时经 governance 路径应用删除，**该路径未挂接 demote**（§11.1）。

### 5.3 只读链（3 GET，D8）

```
GET /knowledge/links/resolve-candidates?title=&space_id=   [静态字面，先注册 R11]
  └─ RepositoryLinkResolver.find_candidates(title) → ResolveCandidateOut(cross_space = c.space_id != space_id)
GET /knowledge/{id}/links      → SQLAlchemyLinkRepository.list_links(id) → LinkOut（含 key/version）
GET /knowledge/{id}/backlinks  → SQLAlchemyLinkRepository.list_backlinks(id) → BacklinkOut（无 key/version）
  （两者 item 不存在 → 404；读取经 _to_entity 的 D12 防御映射）
```

### 5.4 键重建链（Core plan + backend apply；A1-03 无 HTTP 写入口）

```
LinkKeyRebuild.plan(target_version)        [Core link_service.py:906，生成 frozen 计划]
  └─ apply_link_key_plan(plan, session)    [services/links.py:308，唯一执行入口，十步独占单事务]
       步1 session.begin()（要求无活动事务，否则 InvalidRequestError 零写入）
       步2 门禁 A：全表 DISTINCT == {plan.source_version}（空表仅当 observed_row_count==0 放行）
       步3 重读全表 6 列 + 步3b 治理列/knowledge_item 全列基线
       步4 门禁 B：_gate_b（计划内部覆盖 + 新键无重复，不查数据库）
       步5 门禁 C：check_plan_freshness(plan, current)（Core 纯函数，双向覆盖 + 逐字段原始比对 + 新键重算）
       步6 新键唯一性再验（代入当前全表，含 no-op）
       步7 批量只写 3 列（key/version/updated_at）
       步8 写后复核（版本同构/无重复键/治理列与条目基线不变；不符 → LinkRebuildPostWriteError → 整体回滚）
       步9 with 正常退出即提交；步10 任何异常整体回滚
       拒绝一律 _refusal_report（updated=0、requires_replan=True、零写入）
  └─ persist_rebuild_report(report, ops_dir)  [backend 侧 IO，落 backend/data/ops/，gitignore]
```

> 优先级 **A→B→C**；门禁 B 只查计划内部，门禁 C 才查当前数据库（§11.2 残余窗口在步 5 重读→步 9 提交之间）。

---

## 6. 材料⑥：SQLite / PostgreSQL 测试命令与原始结果

完整命令、原始输出与逐文件索引见 **[`test-evidence-index.md`](test-evidence-index.md)**。汇总（全部本轮真实重跑，原始输出落盘 `evidence/`）：

| 套件 | 命令 | 结果 | 证据文件 |
|---|---|---|---|
| 全量 SQLite | `uv run pytest -o addopts="--import-mode=importlib"` | **887 passed / 132 skipped / 0 failed**（124.49s） | `pytest-sqlite-full.txt` |
| 全量真实 PG 16.8 | `EXPLAINLAB_PG_TEST_URL="postgresql+psycopg://postgres@127.0.0.1:5432/explainlab_test" uv run pytest -o addopts="--import-mode=importlib"` | **1019 passed / 0 skipped / 0 failed**（124.03s） | `pytest-pg-full.txt` |
| PG 链接模块单独 | 同上 URL + `backend/tests/test_links_pg.py` | **91 passed / 0 skipped** | `pytest-links-modules.txt` |
| A1-02 冻结子集 | 三冻结文件 + 2 markdown 守护 | **293 passed** | `pytest-a1-02-interfaces-ruff-env.txt` |
| 接口/独立性守护 | `knowledge-core/tests/test_interfaces.py` | **14 passed** | 同上 |
| D3 端口签名守护 | `test_markdown_link_service.py::test_d3_link_repository_signatures_frozen` | **1 passed** | 同上 |
| Lint | `uv run ruff check`（**仅 check，未 format**） | **All checks passed!** | 同上 |
| 前端 | `npm run test && npm run typecheck && npm run build` | **72 用例 / 10 文件**；tsc -b 无错；index **256.45 kB**（gzip 78.26 kB） | `frontend-test-typecheck-build.txt` / `frontend-build-full.txt` |

**关键口径**：

- 132 skipped **全部**为 `EXPLAINLAB_PG_TEST_URL` 门控（`test_links_pg.py` 91 + `test_retrieval_pg.py` 18 + `test_v2_models_pg.py` 23 = 132），`-rs` 逐条核实跳过原因均为「未配置 EXPLAINLAB_PG_TEST_URL」，**无意外跳过**（`evidence/pytest-sqlite-pg-gated-skips.txt`）。
- **净增 334 用例**（实际收集数）：Core 纯文本 41 + Core 服务 86 + SQLite 链接 91 + PG 链接 91 + HTTP 19 + 独立性守护扩展 6 = 334。对照 A1-02 基线 685（PG）→ 1019；SQLite 644 + 243 = 887。**V1 与 A1-01/A1-02 零回归**。计划 §7.8 估算 ~580 偏高，**以实际收集数为准，不虚报**。
- **未用 SQLite 结果冒充 PG，未虚报 PG 连接成功**：PG 实测 `SELECT version()` = `PostgreSQL 16.8, compiled by Visual C++ build 1942, 64-bit`（`evidence/pg-version.txt`），执行真实在线迁移与检索/链接验证。
- 命令纪律：根级 pytest **保留 `--import-mode=importlib`**（切勿 `-o addopts=""`，会引发同名模块收集冲突）；ruff **仅 check**（禁 format）。

---

## 7. 材料⑦：T22–T40 测试文件 / 函数 / 实际覆盖

函数级映射原始 grep 见 `evidence/t22-t40-function-map.txt`。**19 个编号全部实跑通过**；载体分三类：Core 纯函数（`test_markdown_link_service.py`）、SQLite DB（`test_links.py`）、真实 PG DB（`test_links_pg.py`，与 SQLite **同名同断言镜像**）。

| 编号 | 要求 | Core 纯函数 | SQLite / PG DB（镜像同名） | 状态 |
|---|---|---|---|---|
| T22 | plan 后 target_title 改 → 拒绝 | `test_t22_target_title_changed` | `test_t22_target_title_changed` | ✅ |
| T23 | alias 四变体精确比对（不规范化） | `test_t23_alias_four_variants_exact_compare` | `test_t23_alias_changed_raw_compare`（参数化 old/new_alias） | ✅ |
| T24 | 新增行 → 拒绝 | `test_t24_row_added` | `test_t24_row_added` | ✅ |
| T25 | 删除 update/no-op 行 → 拒绝 | `test_t25_row_deleted_update_and_noop` | `test_t25_row_deleted` | ✅ |
| T26 | 键改（含改成 new_key）→ 拒绝 | `test_t26_key_changed_incl_changed_to_new_key` | `test_t26_key_changed_incl_to_new_key` | ✅ |
| T27 | 版本漂移优先级 + unsupported | `test_t27_version_changed_and_unsupported_registry` | `test_t27_version_drift_precedence_and_unsupported` | ✅ |
| T28 | 覆盖不完整三构造 | `test_t28_incomplete_coverage_three_constructions` | `test_t28_incomplete_coverage_three_constructions` | ✅ |
| T29 | 重复 link_id 归 C / 重复键归 B | `test_t29_duplicate_link_id_in_plan` | `test_t29_duplicate_link_id_belongs_to_c` | ✅ |
| T30 | 拒绝后全表逐列 + 三 Hash + 导出字节不变（最强零写入） | —（DB-only） | `test_t30_strongest_zero_write_matrix`（参数化 mutation 覆盖 T22–T29） | ✅ |
| **T31** | 关键过期计划测试 SQLite 与 PG 各跑一遍同断言 | — | **无单独命名 `test_t31`**；由镜像套件满足（见下） | ✅ |
| T32 | commit 后新事务重新预检 | —（DB-only） | `test_t32_commit_then_external_change` | ✅ |
| T33 | rollback 后重新预检（含撤销自身写入） | —（DB-only） | `test_t33_rollback_then_reprecheck` + `test_t33_rollback_no_external_change_passes` | ✅ |
| T34 | 无缓存权威计数（k=1/5/20）+ 豁免 + 结构守护 | 无缓存源码守护 | `test_t34_no_cache_k_writes`（参数化 k）+ `test_t34_exempt_zero_precheck` + `test_t34_apply_counts_and_structure` | ✅ |
| T35 | source_id 改 → 拒绝 | `test_t35_source_id_changed` | `test_t35_source_id_changed` | ✅ |
| T36 | 计划篡改矩阵（新键重算） | `test_t36_tamper_new_key_new_version_status` | `test_t36_tamper_matrix` | ✅ |
| T37 | no-op 盲区反证 + 不误拒 | `test_t37_noop_blindspot_closed_and_no_false_refusal` | `test_t37_noop_blindspot_and_no_false_refusal` | ✅ |
| **T38** | frozen + tuple + 确定性序列化 + 无摘要 | `test_t38_frozen_tuple_deterministic_no_digest`（**Core-only**） | — | ✅ |
| T39 | 十步顺序 + 写后复核 + 故障注入 + 事务所有权 | —（DB-only） | `test_t39_order_guard_success` / `_no_update_after_gate_failure`（参数化 gate）/ `_post_write_governance_and_items` / `_fault_injection_runtime_error`（参数化 fail_at）/ `_fault_injection_integrity_error` / `_transaction_ownership`（6 例） | ✅ |
| T40 | savepoint/nested 边界 + 仓库源码守护 | —（DB-only） | `test_t40_nested_precheck_lifecycle` + `test_t40_repo_source_guard` | ✅ |

**T31 满足方式（诚实记录）**：T31 是**覆盖性要求**而非单点用例——`test_links.py`（SQLite）与 `test_links_pg.py`（真实 PG）含**同一套 T22–T30 断言**，重读 SQL 为同一 SQLAlchemy 表达式（**零方言分支**），两文件各 91 用例均实跑通过（PG 0 skipped）。已核实两文件 T22–T40 函数名逐一对应（`evidence/t22-t40-function-map.txt`）。**无单独命名为 `test_t31` 的用例**，由镜像结构 + 双方言实跑共同保证。

辅助纯函数用例（层②）：`test_freshness_ok_when_unchanged`、`test_freshness_pure_functions_no_io`、`test_freshness_raw_unicode_no_normalization_before_compare`、`test_single_source_of_truth_homogeneity_and_freshness`。

> 层① `test_markdown_links.py` 含 **0** 个 T22–T40 标记（其覆盖 T1–T12 解析/规范化区），已 grep 核实。

---

## 8. 材料⑧：V1 API 兼容性证据

**V1 端点方法/路径/状态码集合不变**，由守护测试 + 全量回归双重保证：

1. **路由守护测试（实跑通过，`evidence/v1-route-guard-tests.txt`）**：
   - `test_links_router_is_exactly_three_gets`：links router 恰为 3 个 GET（`/knowledge/{item_id}/links`、`/knowledge/{item_id}/backlinks`、`/knowledge/links/resolve-candidates`），**无任何写端点**。
   - `test_knowledge_router_endpoint_set_unchanged`：knowledge router 恰为 V1 的 6 端点集合（list/create/get/patch/delete/extract），方法/路径不变。
   - 另断言 app 中**不存在** `rebuild-keys` / `links/resolve` / `links/reresolve` 写路径。
2. **全量回归零回归**：SQLite 887 / PG 1019 全通过，V1 知识/审核/检索/空间/对话/实验 API 用例全部在内（§6）。A1-02 冻结 293 用例全通过。
3. **挂接不改 V1 语义**：knowledge.py 仅在 commit 前插入链接同步；active PATCH 仍 202（审核单），非 active DELETE 仍 204，404 行为不变。409 是**新增**的版本异写拒绝（V1 无此场景），不影响 V1 既有响应。
4. **前端零改动**：72 用例 + 构建 index 256.45 kB 与基线完全一致（§6）。

> 兼容性边界：新增 3 个只读 GET 与 409 稳定码是**增量**，不修改 V1 既有端点契约。`schemas.py` 仅追加新 schema，既有 schema 不动。

---

## 9. 材料⑨：依赖 / 迁移 / 端口签名未变化证据

| 项 | 证据 | 结论 |
|---|---|---|
| **依赖零新增** | `git diff --name-only 5d6dcf1..7e0582c -- uv.lock frontend/package-lock.json frontend/package.json pyproject.toml backend/pyproject.toml knowledge-core/pyproject.toml` → **空**（`evidence/dependency-file-changes.txt`）；`git status --porcelain uv.lock frontend/package-lock.json` → **空**；markdown 子进程白名单守护通过 | ✅ 锁定文件与依赖声明零漂移 |
| **迁移零新增** | `git diff --name-only 5d6dcf1..7e0582c -- backend/alembic/` → **空**（`evidence/migration-changes.txt`）；`ls backend/alembic/versions/*.py` = 0001–0006（`evidence/alembic-versions-list.txt`），0006 来自 A1-01（`f847e4f`），**无 0007** | ✅ 复用 A1-01 迁移 0006，本批无 schema 变更 |
| **10 端口签名零改动** | `evidence/ports-py-diff.txt`：ports.py 唯一差异是 `delete_links_of_item` 的 **docstring**（D3 澄清），签名 `def delete_links_of_item(self, source_id: UUID) -> int:` 逐字不变；`test_d3_link_repository_signatures_frozen` **1 passed** | ✅ 仅 docstring，签名冻结 |
| **基线指纹** | `sha256sum -c docs/audit/V2-A1-03-baseline/manifest.sha256`（**从仓库根运行**）→ **18 OK + 3 FAILED**（`evidence/fingerprint-manifest-check.txt`） | ✅ 3 项变化恰为 §4.2 允许文件 |

**指纹 3 项 FAILED 恰为计划允许修改的文件**（其余 18 项逐字节不变）：

```
knowledge-core/src/knowledge_core/ports.py: FAILED            # 仅 docstring（D3 允许）
knowledge-core/tests/test_interfaces.py: FAILED               # 守护追加（允许）
knowledge-core/src/knowledge_core/markdown/__init__.py: FAILED # 仅追加 ABC（允许）
```

**A1-02 六个冻结文件全部 OK**：`markdown/canonical.py` / `frontmatter.py` / `codec.py` + 三测试文件。`helpers.py` 为 §4.2 允许修改但不在 21 文件清单内的跟踪文件（追加 `InMemoryLinkRepository`）。

> **基线 cmp 口径（诚实记录）**：计划 §1.6/§15.5 的 `git-status.txt` / `a1-01-a1-02-tracked.patch` 逐字节 `cmp` 是**开工前（HEAD `6d91718`，A1-01/A1-02 未提交）工作树快照**。A1-01/A1-02 提交后工作树基线合法移动，这两项 byte-cmp 是设计轮历史工件，**提交后不可复现，本包不声称 `PATCH_CMP_IDENTICAL`**。提交态下权威且可复算的完整性核验是 **SHA-256 manifest**（校验文件内容，与是否提交无关），结果如上。
>
> **指纹复算注意**：manifest 内路径相对**仓库根**，必须从根运行 `sha256sum -c docs/audit/V2-A1-03-baseline/manifest.sha256`；若 `cd` 进 baseline 目录再运行会因路径不匹配全部报 `FAILED open or read`（编制过程中曾出现此 cwd 假阳性，已纠正，落盘证据为从根运行的正确结果）。

---

## 10. 材料⑩：已知缺陷 / 未完成事项 / 风险清单

完整清单见 **[`known-issues.md`](known-issues.md)**（含每项的状态、影响、读取侧/写侧区别、延后批次）。摘要：

| # | 项 | 状态 | 影响 |
|---|---|---|---|
| K1 | governance.py 审核批准路径未挂接链接 demote/sync | **有条件** | active 删除/编辑经批准后，入链写侧未降级/未重同步；读取侧防御映射保证读取安全（§11.1） |
| K2 | 门禁 C 残余并发窗口（apply 重读→提交） | **有条件 / 延后** | 过期计划被拒绝 + 零写入已验证；**并发安全/互斥未声称**，`FOR UPDATE`/表锁待审批（§11.2） |
| K3 | 人工显式绑定无 HTTP 写入口 | **延后（D8）** | Core 绑定规则已验证；用户尚不能经 HTTP 显式绑定 archived/跨空间候选（§11.3） |
| K4 | v2 规范化规则未正式发布 | **延后** | v2 仅测试夹具（注册表注入），生产 `LINK_NORMALIZATION_VERSION=1`；真实升级须走运维协议（§11.4） |
| K5 | 读取侧防御映射 vs 写侧状态降级 | **设计口径（非缺陷）** | 两者职责不同，读取侧不弱化实体校验器；写侧降级仅在 knowledge.py 非 active DELETE 挂接（§11.5） |
| K6 | 设计文档措辞同步（§2.4/§2.9） | **延后另批** | 本轮未改设计文档措辞 |
| K7 | 完整导入幂等/附件生命周期/GC/提案防覆盖/前端链接 UI | **延后** | A1-04 / A1-05 / A2 / A1-06 |

---

## 11. 五项重点审计问题（单独逐条说明）

### 11.1 governance.py 审核批准路径未接入链接同步【有条件】

**事实链（源码核实）**：

- 批准路由：`backend/app/api/routes/governance.py:309` `POST /reviews/{review_id}/approve` → `service.approve(review_id, note)`。
- Core `ReviewService.approve`（`knowledge-core/src/knowledge_core/review/__init__.py:85`）→ `_apply_action`：
  - `UPDATE_ITEM` → `_apply_update`（建版本快照 + 应用 title/content）；
  - `DELETE_ITEM` → `self._items.delete(item_id)`；
  - `MERGE_DUPLICATE` → `_apply_merge`；`RESTORE_VERSION` → `_versions.restore`。
  - **以上四条应用路径均未调用 `demote_backlinks_on_delete` 或 `sync_links_or_conflict`**。
- 链接外键（`backend/app/models.py:316–321`）：`source_item_id` → `knowledge_item.id` **ON DELETE CASCADE**；`target_item_id` → `knowledge_item.id` **ON DELETE SET NULL**。

**后果（active 删除经批准）**：条目删除时，出链随 CASCADE 消失；入链 `target_item_id` 被数据库置 NULL，但 `resolution` 列**仍为 resolved**（NULL + resolved 是非法组合）。**写侧 demote 在批准路径缺失**。

**读取侧为何仍安全**：`_to_entity`（`services/links.py:67`）的 D12 窄口径防御映射把「NULL + resolved/cross_space」降级为 `missing + cross_space=False`，不抛异常。HTTP 测试 `test_read_side_defensive_mapping_via_http` 同时断言读取降级与实体校验器拒绝（`KnowledgeLink(resolution=resolved, target_id=None)` 仍抛 `ValidationError`）。**读取安全已验证；写侧降级延后**。

**为何本轮不修**：计划 §4.2 修改清单**仅含 knowledge.py 四处**，governance.py 不在清单内，且计划明确「任何 V1 服务一律不动」。按用户「遇到真正阻塞只报告不扩范围」约束，**本轮不擅自触碰 governance.py**，记录在此供审计裁决是否另批挂接。此缺口与计划 R9「批准后才应用并同步」原则存在张力，**如实记录为有条件项，不写成完全通过**。

**审计建议核验点**：批准 active 删除后直查数据库 `knowledge_link.resolution`（应为 resolved + NULL target，证明写侧未降级），再经 GET backlinks 读取（应为 missing，证明读取侧映射生效）。

### 11.2 门禁 C 的残余并发窗口【有条件 / 延后】

**已验证**：过期计划被拒绝 + 数据库零写入。`apply_link_key_plan` 在**同一事务内**重读当前全表 6 列（步 3）→ 门禁 C `check_plan_freshness`（步 5，逐行原始 5 字段比对 + 双向覆盖 + 新键重算，含 no-op 行）→ 任一不符 `_refusal_report`（updated=0、requires_replan=True、零写入）。T22–T30 + T32/T33（commit/rollback 后重新预检）实跑通过。

**未关闭的残余窗口**：步 5 重读 → 步 9 提交之间，**另一并发事务**理论上可修改链接行使计划过期。本轮**未加 `SELECT … FOR UPDATE` / 表锁**（计划 §8.4.8 第 2 条，仍【待审批】）。因此：

- **只声称「过期计划被拒绝 + 零写入已验证」**；
- **不声称「重建并发安全 / 已实现互斥 / 计划不可能过期」**。

**缓解现状**：门禁 A（全表版本同构）+ 门禁 C（逐行新鲜度）+ 步 8 写后复核（版本同构/无重复键/治理列与条目基线不变，不符整体回滚）构成纵深防御，单事务内重读保证**本事务视角**的一致性；残余窗口是**跨事务并发**层面，需行锁/表锁关闭，待审批后另批实现。

**审计建议核验点**：T32（commit 后外部改动 → 新事务重新预检拒绝）、T33（rollback 后重新预检）、T39 故障注入（步 7 后抛错 → 整体回滚零写入）。并发互斥本身**本轮无测试声称通过**。

### 11.3 人工绑定没有 HTTP 写入口【延后，D8 交付边界】

**事实**：A1-03 链接 router **仅 3 个只读 GET**（`test_links_router_is_exactly_three_gets` 锁定），**无任何写端点**；app 中不存在 `links/resolve` / `links/reresolve` / `rebuild-keys` 写路径（守护断言）。

**已验证 vs 未交付**：

- **Core 层显式绑定规则已验证**：`RepositoryLinkResolver.resolve` / `binding_semantics`（`link_service.py:411/503`）对 archived/跨空间候选的显式绑定规则在 Core 定义并经测试（场景 J/L、H17/L④ HTTP 读取测试经**仓库层夹具**建立绑定后验证读取）。
- **未交付用户功能**：用户**尚不能经 HTTP 显式绑定** archived/跨空间候选；`POST links/resolve` / `/reresolve` / `/rebuild-keys` 与前端绑定交互属后续里程碑。

**措辞纪律**：写成「**Core 层显式绑定规则已验证（A1-03 无 HTTP 写入口）**」，**不**写成「用户可显式绑定 archived/跨空间候选」这类已交付用户功能。HTTP 测试中的绑定经 `_bind_via_repository_fixture`（仓库层 `update_link`）建立，**不是 HTTP 写入口**。

### 11.4 v2 规范化规则尚未正式发布【延后】

**事实**：`knowledge-core/src/knowledge_core/domain/entities.py` 的生产常量 `LINK_NORMALIZATION_VERSION = 1`；`LINK_KEY_RULES = {1: v1}`（`links.py`）。**v2 规则仅作测试夹具**，经注册表注入（`v2_registry` / monkeypatch）激活，**不在生产注册表发布**。

**含义**：

- 生产路径所有链接键按 v1 规范化；全局守卫要求全表同构于常量 1。
- T15/T17/T27/T36/T37 等用 v2 夹具验证「版本漂移拒绝 / 混合拒绝 / 新键重算 / 不支持版本」逻辑，**证明机制正确**，但**不代表 v2 已上线**。
- 真实 v2 升级须走计划 §8.4.7 运维协议（全量重建 + 门禁 + 报告），**本轮未执行真实全量重建**。

**措辞纪律**：不声称「v2 规范化已发布 / 已升级生产数据」。`test_t38` 等守护确保计划 frozen + 确定性序列化 + 无摘要字段，为未来升级提供可审计基础。

### 11.5 读取侧防御映射 与 写侧状态降级 的区别【设计口径，非缺陷】

两者**职责不同、触发点不同、不可互相替代**：

| 维度 | 读取侧防御映射（D12 read-side） | 写侧状态降级（D12 write-side） |
|---|---|---|
| 位置 | `_to_entity`（`services/links.py:67`），ORM→实体读取时 | `demote_backlinks_on_delete`（`services/links.py:215`），删除目标条目前 |
| 触发 | **每次读取**链接行（list_links/list_backlinks/get_link 等） | **仅** knowledge.py 非 active DELETE 路径、submit 应用删除**之前**同事务调用 |
| 作用 | 把「NULL target + resolved/cross_space」**非法组合**映射为 `missing + cross_space=False`；合法 NULL（missing/ambiguous/conflict）resolution 原样保留 | 把入链 `target_item_id` 置 NULL、`resolution` 改为 missing、`cross_space=False`、`updated_at` 刷新；**键与版本不变**（治理列-only，豁免全局守卫） |
| 是否改库 | **否**（只改返回实体，数据库列原样） | **是**（同事务写库，flush） |
| 实体校验器 | **不弱化**：`KnowledgeLink(resolution=resolved, target_id=None)` 仍抛 `ValidationError` | 降级后写入的是合法 missing + NULL，校验通过 |
| 覆盖范围 | 所有读取路径（含 governance 批准删除后的脏数据） | **仅** knowledge.py 非 active DELETE；**governance 批准路径未挂接**（§11.1） |

**关键结论**：读取侧映射是**兜底安全网**（保证任何来源的 NULL+resolved 脏数据读取不抛异常、语义为 missing），写侧降级是**主动状态维护**（删除时把入链正式降级落库）。**当前写侧降级只在非 active DELETE 挂接**；active 删除经 governance 批准后，写侧未降级，**靠读取侧映射保证读取安全**（§11.1 有条件项）。两者**不是同一机制的两种说法**：读取侧不改库、不弱化校验器；写侧改库、治理列豁免守卫。审计应分别核验。

---

## 12. 审计复现指南（只读命令）

审计方可在仓库根（`D:/ExplainLab`，分支 `fix/m0-admission-and-m5-regressions`）按序复算：

```bash
# 0) 工作树状态（应仅审计包目录 untracked，无业务代码改动）
git status --porcelain
git log --format="%h parent=%p %s" -8

# 1) 完整 diff 复算比对
git diff 5d6dcf1..7e0582c | cmp - docs/audit/V2-A1-03-audit-package/evidence/a1-03-full.diff
git diff --name-status 5d6dcf1..7e0582c

# 2) 未变化证据
git diff 5d6dcf1..7e0582c -- knowledge-core/src/knowledge_core/ports.py   # 仅 docstring
git diff --name-only 5d6dcf1..7e0582c -- backend/alembic/                  # 空
git diff --name-only 5d6dcf1..7e0582c -- uv.lock frontend/package-lock.json frontend/package.json pyproject.toml backend/pyproject.toml knowledge-core/pyproject.toml  # 空
sha256sum -c docs/audit/V2-A1-03-baseline/manifest.sha256                  # 从根运行：18 OK + 3 允许 FAILED

# 3) 测试（Windows 加 PYTHONIOENCODING=utf-8）
uv run ruff check
uv run pytest -o addopts="--import-mode=importlib"                       # SQLite 887/132 skip
# 启动 PG（便携 16.8，端口 5432）：
#   "D:/ExplainLab-pg/pgsql/bin/pg_ctl.exe" -D "D:/ExplainLab-pg/data" -l "D:/ExplainLab-pg/data/logfile" start
EXPLAINLAB_PG_TEST_URL="postgresql+psycopg://postgres@127.0.0.1:5432/explainlab_test" \
  uv run pytest -o addopts="--import-mode=importlib"                     # PG 1019/0 skip
uv run pytest knowledge-core/tests/test_interfaces.py -o addopts="--import-mode=importlib"  # 14
uv run pytest "knowledge-core/tests/test_markdown_link_service.py::test_d3_link_repository_signatures_frozen" -o addopts="--import-mode=importlib"  # 1

# 4) 前端
cd frontend && npm run test && npm run typecheck && npm run build && cd ..

# 5) T22–T40 函数映射
grep -nE "^def test_t(2[2-9]|3[0-9]|40)" backend/tests/test_links.py backend/tests/test_links_pg.py knowledge-core/tests/test_markdown_link_service.py
```

> **PG 端口口径**：计划文本写 55432，**实际便携实例验证为 5432**（`evidence/pg-version.txt` 实测连接成功）。审计以实际 5432 为准。
> **命令纪律**：pytest 保留 `--import-mode=importlib`（切勿 `-o addopts=""`）；ruff 仅 check（禁 format）。

---

## 13. 结论与停止点

**A1-03（E1–E4）实现经真实运行验证**：ruff 通过；SQLite 887 / 真实 PG 16.8 1019 全通过（0 failed）；A1-02 293 冻结用例全通过；21 文件指纹 18 OK + 3 允许变化 + 6 冻结全 OK；依赖/迁移/端口签名零变化；前端 72 用例 + 构建 256.45 kB 不退化；T22–T40 全部实跑通过；净增 334 用例，V1 与 A1-01/A1-02 零回归。

**五项重点问题均为有条件项 / 延后项 / 设计口径**（§11），**不描述为完全通过**：governance 批准路径写侧 demote/sync 缺失（读取侧安全已验证）、门禁 C 残余并发窗口未关闭（互斥待审批）、人工绑定无 HTTP 写入口（Core 规则已验证）、v2 规则未发布（仅夹具）、读取侧映射与写侧降级职责分离。

**停止点**：本包编制完成即**停止，等待独立审计**。审计批准前**不进入 A1-04**，不自行宣布下一里程碑。MILESTONES.md 按批次安排留到 A1-06，本批不动。

**编制纪律核验**：本包仅新增审计材料文件，**未修改业务代码、未新增依赖、未修改迁移、未修改 A1-01/A1-02、未修改已有提交、未 push、未进入 A1-04、未修改 MILESTONES.md**。本包文件当前为 **untracked（未提交）**——本轮任务未要求提交，按 AGENTS.md §8「未经用户明确要求不提交」留待用户决定是否入库。

---

## 附：本包文件清单

```
docs/audit/V2-A1-03-audit-package/
├─ A1-03-independent-audit-package.md   ← 本文件（10 项材料 + 5 重点问题 + 复现指南）
├─ test-evidence-index.md               ← 测试证据索引（命令 + 原始输出文件 + 结果）
├─ known-issues.md                      ← 已知缺陷 / 未完成 / 风险清单
└─ evidence/                            ← 真实命令原始输出（21+ 文件）
   ├─ git-commit-chain.txt / git-feat-commit-715d9e7-stat.txt / git-docs-commit-7e0582c-stat.txt
   ├─ a1-03-full.diff（9118 行）/ a1-03-name-status.txt / a1-03-diff-stat.txt
   ├─ ports-py-diff.txt / migration-changes.txt（空）/ alembic-versions-list.txt / dependency-file-changes.txt（空）
   ├─ fingerprint-manifest-check.txt（18 OK + 3 FAILED）
   ├─ pytest-sqlite-full.txt（887/132）/ pytest-pg-full.txt（1019/0）/ pytest-sqlite-pg-gated-skips.txt（132 全 PG 门控）
   ├─ pytest-links-modules.txt（41/86/91/19/91）/ pytest-a1-02-interfaces-ruff-env.txt（293/14/1/ruff/env）
   ├─ v1-route-guard-tests.txt / t22-t40-function-map.txt
   ├─ frontend-test-typecheck-build.txt / frontend-build-full.txt（index 256.45 kB）/ pg-version.txt（16.8）
```