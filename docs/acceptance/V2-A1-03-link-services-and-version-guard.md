# V2 A1-03 验收记录 — 链接服务四层 + 全局版本同构守卫 + 计划新鲜度门禁

> **批次**：V2 A1-03（实施轮，依据冻结稿 `docs/audit/V2-A1-03-implementation-plan.md` R3.1）
> **范围**：E1 全局版本同构守卫 / E2 导入绑定空间语义 / E3 人工绑定交付边界 / E4 门禁 C 逐行新鲜度 + 无缓存。**E5 批准状态不变，本轮未重新讨论。**
> **日期**：2026-11-20
> **分支**：`fix/m0-admission-and-m5-regressions`（未切换）
> **开工 HEAD**：`5d6dcf1`（A1-01/A1-02 已提交：`f847e4f` feat + `41ff761` docs + `5d6dcf1` chore）
> **环境**：Python 3.11.9 / uv 0.13.6 / SQLite 3.45.1 / 真实 PostgreSQL 16.8（`127.0.0.1:5432`，`explainlab_test`）/ Node 22.23.2
> Windows 控制台 GBK，命令统一加 `PYTHONIOENCODING=utf-8`（数据本身始终 UTF-8）。

---

## 0. 诚实性前置声明

本报告区分 **已验证 / 有条件 / 未验证** 三态。凡真实运行通过的写「已验证」并附实测输出；凡属设计预期但本轮未跑的写「未验证」，**一律不写 PASS**。措辞遵守计划 §6.7 / §13.1 纪律：

- **人工显式绑定（L③ / J）**：写成「**Core 层显式绑定规则已验证（A1-03 无 HTTP 写入口）**」，**不**写成「用户可显式绑定 archived / 跨空间候选」这类已交付用户功能。
- **门禁 C**：写成「**过期计划被拒绝 + 数据库零写入已验证**」，**不**写成「重建并发安全 / 已实现互斥 / 计划不可能过期」——残余窗口（apply 事务内重读→提交）本轮未关闭（§8.4.8 第 2 条，`SELECT … FOR UPDATE`/表锁仍【待审批】）。
- **预检成本**：写成「**无缓存，每次受守卫写入各一次单列扫描**」，不沿用 R3 的「每事务一次」。

---

## 1. 交付物（四层分离，依赖方向 frontend → backend → knowledge-core）

### 1.1 新增文件

| 层 | 文件 | 职责 |
|---|---|---|
| ① 纯文本 | `knowledge-core/src/knowledge_core/markdown/links.py` | 规范化 v1（NFKC→strip→空白折叠→casefold）、两个派生键、`[[标题\|别名]]` 解析 + 排除矩阵、同键合并、提示按标题键聚合、版本化规则注册表。**零持久化/网络/文件 IO**。 |
| ② 领域服务 | `knowledge-core/src/knowledge_core/markdown/link_service.py` | `RepositoryLinkResolver` / `BindingFirstLinkSync` / `LinkImportRestorer` / `LinkKeyRebuild.plan()`；两纯函数 `check_global_version_homogeneity` / `check_plan_freshness`；frozen 值类型与报告模型。**只经端口取数，零 ORM**。 |
| ③ 持久化适配 | `backend/app/services/links.py` | `SQLAlchemyLinkRepository`（10 端口方法）、全局守卫权威执行点（单列 `SELECT DISTINCT`，无缓存）、`apply_link_key_plan()`（十步独占单事务）、`demote_backlinks_on_delete()`、`persist_rebuild_report()`（backend 侧 IO）。**唯一含 ORM/方言/文件 IO 的层**。 |
| ④ API 装配 | `backend/app/api/routes/links.py` | **仅 3 个只读 GET**（D8）+ `sync_links_or_conflict()` 助手（409 稳定码映射）。**不含业务规则**。 |
| 测试 | `knowledge-core/tests/test_markdown_links.py`（41）/ `test_markdown_link_service.py`（86）/ `backend/tests/test_links.py`（91，SQLite）/ `test_links_pg.py`（91，真实 PG）/ `test_links_http.py`（19，TestClient） | 见 §3 实测。 |

### 1.2 修改文件（§4.2 清单内，append-only / 挂接）

| 文件 | 改动 | 约束核验 |
|---|---|---|
| `knowledge-core/src/knowledge_core/markdown/__init__.py` | 尾部追加 6 个链接服务 ABC + `__all__` 追加 | A1-02 代码逐字不动（唯一差异为文末补一个换行符以便追加）；293 用例全通过（§3.4）。 |
| `knowledge-core/src/knowledge_core/ports.py` | **仅 docstring 澄清** `delete_links_of_item`（D3：仅用于删除/显式重置，常规保存走绑定优先同步） | 10 个端口签名零改动（D3 守护测试锁定）。 |
| `knowledge-core/tests/helpers.py` | 追加 `InMemoryLinkRepository`（+105/−1） | 调用同一 Core 纯函数（单一事实来源守护）。 |
| `knowledge-core/tests/test_interfaces.py` | 守护扩展：子进程导入新增 `markdown.links` / `markdown.link_service`；SERVICES 追加 6 ABC | 独立性守护未弱化（§3.6）。 |
| `backend/app/api/routes/knowledge.py` | 四处挂接链接同步（create / draft-PATCH / extract commit 前；DELETE 直接应用前同事务降级入链）；active PATCH 202 不同步 | V1 端点方法/路径/状态码集合不变（守护测试锁定）。 |
| `backend/app/api/schemas.py` | 追加 `LinkOut` / `BacklinkOut` / `ResolveCandidateOut` | 既有 schema 不动。 |
| `backend/app/main.py` | 注册 links router（**先于** knowledge router，R11 静态字面优先） | 既有注册顺序保留。 |

> **governance.py 不在 §4.2 修改清单**，本轮未触碰（审核批准路径的链接同步缺口见 §4.4，如实记录为有条件项）。

---

## 2. 硬约束遵守核验

| 约束 | 核验结果 |
|---|---|
| 不新增大型依赖 | ✅ 零新增依赖；markdown 包仍仅 stdlib + Pydantic 栈（子进程白名单守护通过）。 |
| 不新增迁移 | ✅ `backend/alembic/versions/` 无新增；复用 A1-01 的 `0006_v2_markdown_kb.py`（指纹 OK）。 |
| 不改 A1-01 的 10 个端口签名 | ✅ D3 签名守护测试 `test_d3_link_repository_signatures_frozen` 通过；ports.py 仅 docstring。 |
| 不改 V1 已验收行为 | ✅ V1 知识/审核/检索/空间/对话/实验 API 回归全通过；knowledge.py 端点集合守护通过。 |
| 本轮不改设计文档措辞 | ✅ `docs/plans/V2-batch-A-design.md` 未触碰；§2.4 措辞同步留待另批（§6 未验证项）。 |
| 不重写 Knowledge Core / 不耦合 UI | ✅ 核心独立性守护（干净子进程导入全部核心模块，无 fastapi/starlette/flask/django）通过。 |
| 业务服务/核心不出现方言 SQL | ✅ 预检/重读/批量写全为 SQLAlchemy 表达式，SQLite 与 PG 同一段代码、零方言分支；PG 路径无 FTS5/MATCH/bm25/rowid。 |
| 密钥安全 / 稳定错误码 | ✅ 409 只回 `link_version_mismatch` 稳定码，不回异常文本/版本明细（实测响应体恰为 `{"detail": "link_version_mismatch"}`）。 |

---

## 3. 真实运行验证（已验证）

### 3.1 Lint

```
$ uv run ruff check
All checks passed!
```

全程仅 `ruff check`，**未使用 `ruff format`**。

### 3.2 全量回归 — 默认 SQLite（根级一次性收集 backend + core）

```
$ uv run pytest -o addopts="--import-mode=importlib"
=========== 887 passed, 132 skipped, 1 warning in 137.54s ===========
```

- **0 failed**。132 skipped 全部为 `EXPLAINLAB_PG_TEST_URL` 门控的 PG 模块（41 原有 PG + 91 新增 `test_links_pg.py`），`-rs` 逐条核实跳过原因均为「未配置 EXPLAINLAB_PG_TEST_URL」，**无意外跳过**。
- 对照 A1-02 基线 644 passed / 41 skipped：644 + 243（新增非 PG 用例）= **887**，**V1 与 A1-01/A1-02 用例零回归**。

### 3.3 全量回归 — 真实 PostgreSQL 16.8（0 skipped）

```
$ EXPLAINLAB_PG_TEST_URL="postgresql+psycopg://postgres@127.0.0.1:5432/explainlab_test" \
      uv run pytest -o addopts="--import-mode=importlib"
================= 1019 passed, 1 warning in 115.24s =================
```

- **1019 passed / 0 skipped / 0 failed**。连真实 PG 16.8 实例（`SELECT version()` 实测 `PostgreSQL 16.8, compiled by Visual C++ build 1942, 64-bit`），执行真实在线迁移（`alembic upgrade head`）与检索/链接验证。
- 对照 A1-02 基线 685 passed：685 + 334（本轮净增）= **1019**，零回归。
- PG 链接模块单独实跑：`test_links_pg.py` → **91 passed / 0 skipped**。
- **未用 SQLite 结果冒充 PG，未虚报 PG 连接成功**；PG 未连接时整模块 skip 并如实报告（§3.2 的 132 skipped 即此机制）。

> **净增 334 用例**（实际收集数，非估算）：Core 纯文本 41 + Core 服务 86 + SQLite 链接 91 + PG 链接 91 + HTTP 19 + 独立性守护扩展 6 = **334**。计划 §7.8 估算 ~580，**以实际收集数为准，不虚报**（估算偏高，如实记录）。

### 3.4 A1-02 冻结用例 293 全通过

```
$ uv run pytest knowledge-core/tests/test_markdown_canonical.py \
      knowledge-core/tests/test_markdown_frontmatter.py \
      knowledge-core/tests/test_markdown_codec.py \
      "knowledge-core/tests/test_interfaces.py::test_core_has_no_web_framework_dependency" \
      "knowledge-core/tests/test_interfaces.py::test_markdown_package_adds_no_new_third_party_dependency" \
      -o addopts="--import-mode=importlib"
============================= 293 passed in 0.86s =============================
```

293 = 291（三冻结文件 74+122+95）+ 2（test_interfaces 的两个 markdown 守护）。`markdown/__init__.py` 追加 ABC 后 A1-02 公共 API 行为不变。

### 3.5 基线指纹（21 文件 SHA-256）

```
$ sha256sum -c docs/audit/V2-A1-03-baseline/manifest.sha256
18 项 OK；3 项 FAILED（恰为 §4.2 允许修改的文件）：
  knowledge-core/src/knowledge_core/ports.py: FAILED        # 仅 docstring（D3 允许）
  knowledge-core/tests/test_interfaces.py: FAILED           # 守护追加（允许）
  knowledge-core/src/knowledge_core/markdown/__init__.py: FAILED  # 仅追加（允许）
```

- **18/21 逐字节不变**；3 项变化恰为计划明确列出的修改，其余无任何漂移。
- **A1-02 六个冻结文件全部 OK**：`markdown/canonical.py` / `frontmatter.py` / `codec.py` + 三测试文件。
- `helpers.py` 为 §4.2 允许修改但**不在 21 文件清单内**的跟踪文件（追加 `InMemoryLinkRepository`）。
- **依赖与锁定文件零漂移**：`git status --porcelain uv.lock frontend/package-lock.json pyproject.toml backend/pyproject.toml knowledge-core/pyproject.toml frontend/package.json` → **输出为空**。

> **基线 cmp 口径说明（诚实记录）**：计划 §1.6 / §15.5 的 `git-status.txt` / `a1-01-a1-02-tracked.patch` 逐字节 `cmp` 是**开工前（HEAD `6d91718`，A1-01/A1-02 尚未提交）工作树快照**。本批前置请求已将 A1-01/A1-02 提交（`f847e4f` 等），工作树基线已合法移动——原 1173 行 baseline patch 与当前 533 行 tracked diff 不再相同，**这两项 byte-cmp 是设计轮历史工件，提交后不可复现，本轮不声称 `PATCH_CMP_IDENTICAL`**。提交态下权威且可复算的完整性核验是 **SHA-256 manifest**（校验文件内容，与是否提交无关），结果如上：18 OK + 3 允许变化 + 6 冻结全 OK。

### 3.6 独立性 / 结构守护（已验证）

- `test_core_has_no_web_framework_dependency`：干净子进程导入全部核心模块（**含新增 `markdown.links` / `markdown.link_service`**），断言无 fastapi/starlette/flask/django → 通过。
- `test_markdown_package_adds_no_new_third_party_dependency`：markdown 全包（含新模块）非标准库顶层白名单核对 → 通过（零新增依赖）。
- 6 个新 ABC 不可实例化（`test_service_is_abstract` 参数化 12 项）→ 通过。
- **R3.1 结构守护**（既有测试，本轮实跑通过）：
  - 单一事实来源：`InMemoryLinkRepository` 与 backend 预检调用同一 `check_global_version_homogeneity`（源码守护断言）。
  - 无缓存：`test_inmemory_no_version_set_cache_attribute` + T34（k 次受守卫写入 → DISTINCT 计数 == k；豁免写入计数 +0；仓库实例 `vars == {"_session"}`）。
  - 计划 frozen 且无摘要字段：T38（frozen + tuple + 字段集合精确锁定 + 无 digest + 不用内置 `hash()`）。
  - 事务所有权：T39 / T40（AST 守护：仓库不 commit/rollback/begin_nested；apply 恰一个 `session.begin()`；已有活动事务 → `InvalidRequestError` 零写入）。
  - 三 Hash 与白名单零改动：场景 F / H20（`canonicalization_version` 恒 1；导出 links[] 白名单恒 `target_id/title/alias/resolution`）。

### 3.7 前端（未触碰，仍实跑确认不退化）

本轮**未修改任何前端文件**。按用户要求仍实跑确认不退化：

```
$ npm run test       → Test Files 10 passed (10) / Tests 72 passed (72)
$ npm run typecheck  → tsc -b 通过（无输出）
$ npm run build      → ✓ built in 620ms；dist/assets/index-*.js 256.45 kB（gzip 78.26 kB）
```

72 用例与构建产物 index **256.45 kB 与基线完全一致**（前端零改动，故无增量）。

---

## 4. 实现决定与口径（如实记录，供独立审计核验）

### 4.1 D12 读取侧防御映射——窄口径（计划内部矛盾的处置）

计划 §2.6 D12 字面「NULL 绑定一律映射 missing」与其自身场景 B/H/M（ambiguous/conflict **合法地** `target_id=None`）矛盾。本轮取**窄口径**：

- `target_id=NULL` 且存储 resolution 为 **resolved/cross_space**（**非法组合**，外部级联/历史脏数据）→ 降级 `missing` + `cross_space=False`，不抛异常。
- `target_id=NULL` 且存储 resolution 为 **missing/ambiguous/conflict**（合法 NULL 绑定）→ **resolution 原样保留**，`cross_space=False`。

**实体校验器未被弱化**：`KnowledgeLink(resolution=resolved, target_id=None)` 仍抛 `ValidationError`（HTTP 测试 `test_read_side_defensive_mapping_via_http` 同时断言读取降级与实体拒绝）。此处置已在本报告与代码 docstring 明示，**未擅自改设计文档措辞**。

### 4.2 门禁 B 口径——只查计划内部

门禁 B（`_gate_b`）**只查计划内部、不查数据库**：① `observed_row_count == len(row_snapshots)`；② `source≠target` 时快照 ⊆ updates（单向）；③ 计划内 `(source_id,new_key)` 无重复（**不同 link_id** 才算；重复 link_id 归门禁 C）。与当前数据库的双向覆盖/逐字段比对/新键重算一律是门禁 C（`check_plan_freshness`）职责。优先级 A→B→C。T24/T28/T29 锁定此口径。

### 4.3 UTC 时区归一（方言边界）

`_utc()`：SQLite DateTime 回读 naive（实际存 UTC）→ `replace(tzinfo=UTC)`；PG timestamptz 回读带会话时区（Asia/Shanghai +08:00）→ `astimezone(UTC)`。实体层时间一律 UTC-aware，双方言往返一致。属数据库适配层职责，核心不见方言。

### 4.4 审核批准路径未挂接链接同步（有条件项，诚实记录）

§4.2 修改清单**仅含 knowledge.py 四处**，`governance.py`（审核批准路由）不在清单内，且计划明确「任何 V1 服务一律不动」。因此：

- **草稿/非 active 删除**：在 knowledge.py DELETE 路径、submit 直接应用删除**之前**同事务降级入链（D12 写侧）→ 已验证。
- **active 删除经审核批准**（governance.py `approve_review`）：批准时应用删除，但**该路径未挂接 demote**；入链经 FK `SET NULL` 后存储 resolution 仍为 resolved + NULL target（非法组合），由 **§4.1 读取侧防御映射**保证读取为 missing、不抛异常。**写侧 demote 在批准路径缺失**，本轮如实记录为**有条件项**（读取安全已验证；写侧降级延后到 governance 挂接批次）。
- **active 编辑经审核批准**：批准后内容应用，但链接未在该路径重新同步（同样延后）。

> 此缺口与计划 R9「批准后才应用并同步」原则存在张力，但 §4.2 / A1-03e 门禁范围严格限定 knowledge.py 四处。**本轮不擅自扩大改动范围触碰 governance.py**，按用户「遇到真正阻塞只报告不扩范围」的约束，记录在此供审计裁决是否另批挂接。

### 4.5 绑定优先同步不重解析既有行

`BindingFirstLinkSync.sync()` 对既有行（含 missing）**原样保留、不重解析、不 churn id/时间戳**；仅新键解析建行、消失键删除。重解析（reresolve）属后续里程碑，**A1-03 无 HTTP 写入口**（D8）。HTTP 测试 `test_draft_patch_syncs_new_links_keeps_existing` 锁定此口径。

### 4.6 409 的双触发点

`link_version_mismatch` 可由两处真实抛出：① Core 局部守卫（`sync()` 检查条目自身既有行版本，纵深防御）；② backend 全局预检（`save_link`/改键改版本的 `update_link` 前单列 DISTINCT）。两者均映射 409 稳定码。DELETE 走治理列-only 降级（豁免预检）→ 版本窗口内不阻断（实测 204）。

### 4.7 resolve-candidates 的 cross_space 口径

只读候选端点 `cross_space` 按**查询给定的 `space_id`** 精确等值判定（`None==None` 同空间，§2.5）；含 archived 候选并带 `status` 标注（D7），跨空间候选列出。**自动解析排除 archived 的规则在 Core 解析器**，本端点只列候选供显式选择（无绑定写入口）。

### 4.8 T31 的满足方式

T31（关键过期计划测试在真实 SQLite 与真实 PG 各跑一遍）由**双方言镜像套件**满足：`test_links.py`（SQLite）与 `test_links_pg.py`（真实 PG）含**同一套 T22–T30 断言**，重读 SQL 为同一 SQLAlchemy 表达式（零方言分支）。两文件各 91 用例均实跑通过（PG 0 skipped）。**无单独命名为 `test_t31` 的用例**——T31 是覆盖性要求，由镜像结构 + 双方言实跑共同保证，如实记录。

---

## 5. T22–T40 实跑映射（已验证，清除【待验证】）

| 编号 | 要求 | 实测载体 | 状态 |
|---|---|---|---|
| T22 | plan 后 target_title 改 → 拒绝 | core `test_t22_target_title_changed` + SQLite/PG 同名 | ✅ 已验证 |
| T23 | alias 四变体精确比对（不规范化） | core + SQLite/PG `test_t23_*` | ✅ |
| T24 | 新增行 → 拒绝（A/B 放行证明） | core + SQLite/PG `test_t24_row_added` | ✅ |
| T25 | 删除 update/no-op 行 → 拒绝 | core + SQLite/PG `test_t25_*` | ✅ |
| T26 | 键改（含改成 new_key）→ 拒绝 | core + SQLite/PG `test_t26_*` | ✅ |
| T27 | 版本漂移优先级 + unsupported | core + SQLite/PG `test_t27_*` | ✅ |
| T28 | 覆盖不完整三构造 | core + SQLite/PG `test_t28_*` | ✅ |
| T29 | 重复 link_id 归 C / 重复键归 B | core + SQLite/PG `test_t29_*` | ✅ |
| T30 | 拒绝后全表逐列 + 三 Hash + 导出字节不变（最强零写入） | SQLite/PG `test_t30_strongest_zero_write_matrix`（参数化） | ✅ |
| T31 | 双方言各跑一遍同断言 | 镜像套件 test_links.py + test_links_pg.py（§4.8） | ✅ |
| T32 | commit 后新事务重新预检 | SQLite/PG `test_t32_commit_then_external_change` | ✅ |
| T33 | rollback 后重新预检（含撤销自身写入） | SQLite/PG `test_t33_*`（2 例） | ✅ |
| T34 | 无缓存权威计数（k=1/5/20）+ 豁免 + 结构守护 | SQLite/PG `test_t34_*`（3 例）+ core | ✅ |
| T35 | source_id 改 → 拒绝 | core + SQLite/PG `test_t35_*` | ✅ |
| T36 | 计划篡改矩阵（新键重算） | core + SQLite/PG `test_t36_tamper_matrix` | ✅ |
| T37 | no-op 盲区反证 + 不误拒 | core + SQLite/PG `test_t37_*` | ✅ |
| T38 | frozen + tuple + 确定性序列化 + 无摘要 | core `test_t38_frozen_tuple_deterministic_no_digest` | ✅ |
| T39 | 十步顺序 + 写后复核 + 故障注入 + 事务所有权 | SQLite/PG `test_t39_*`（5 例） | ✅ |
| T40 | savepoint/nested 边界 + 仓库源码守护 | SQLite/PG `test_t40_*`（2 例） | ✅ |

**19 个编号全部实跑通过**（Core 层 + SQLite + 真实 PG 各相应载体）。计划 §7.5.1 状态列由【待验证】更新为【已验证】（见计划文档实施轮注记）。

---

## 6. 未验证 / 延后项（诚实 ⏳，不写 PASS）

- ⏳ **门禁 C 残余并发窗口**（apply 事务内重读→提交）：本轮未关闭；`SELECT … FOR UPDATE`/表锁仍【待审批】（§8.4.8）。**只声称「过期计划被拒绝 + 零写入已验证」，不声称并发安全/互斥**。
- ⏳ **审核批准路径（governance.py）写侧 demote / 链接同步**：本轮未挂接（§4.4），读取侧防御映射保证读取安全；写侧降级延后另批。
- ⏳ **人工显式绑定 HTTP 写入口**（`POST links/resolve` / `/reresolve` / `/rebuild-keys`）与前端绑定交互 → 后续里程碑（D8：本轮只交付 3 只读 GET）。**Core 层显式绑定规则已验证（A1-03 无 HTTP 写入口）**。
- ⏳ **v2 生产规则发布与真实全量重建**：本轮 v2 仅作测试夹具（经注册表注入），**不发布**；真实升级须走 §8.4.7 运维协议。
- ⏳ **设计文档措辞同步**（§2.4/§2.9 碰撞→整体拒绝；§2.4 导入空间重算）：**另批审批后修改，本轮未改设计文档**。
- ⏳ 完整导入幂等 / 附件生命周期 / GC / 提案防覆盖 / 前端链接 UI → A1-04 / A1-05 / A2 / A1-06。

---

## 7. 结论与停止点

**A1-03（E1–E4）实施完成并经真实运行验证**：

- ruff check 通过；根级 pytest **SQLite 887 passed / 0 failed**、**真实 PG 16.8 1019 passed / 0 skipped / 0 failed**；A1-02 293 冻结用例全通过；21 文件指纹 18 OK + 3 允许变化 + 6 冻结全 OK；锁定文件零漂移；前端 72 用例 + 构建 256.45 kB 不退化。
- T22–T40 全部实跑通过；R3.1 结构守护（单一事实来源 / 无缓存 / frozen 无摘要 / 事务所有权 / 三 Hash 白名单）全通过。
- 净增 334 用例，V1 与 A1-01/A1-02 零回归。
- 实现决定（D12 窄口径 / 门禁 B 内部口径 / UTC 归一 / 批准路径缺口 / T31 镜像）已如实记录（§4）。

**停止点**：按 §12 与用户约束，A1-03f 完成后**停止**，**不自行宣布进入 A1-04**。MILESTONES.md 按批次安排留到 A1-06，本批不动。本报告与改动一并提交审查，**等待独立审计**；审计批准前不进入下一里程碑。

**提交纪律**：本批改动按用户要求提交，**不 push**；不改 M0 初始提交、不重写已推送历史、不提交敏感文件（`.env`/`*.db`/`node_modules`/`.venv`）。