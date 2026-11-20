# ExplainLab V2 A1-03 最终审计审查（K1–K4）

> **阶段**：A1-03（E1–E4）实现完成、独立审计待执行。本轮**只审查与方案设计，不修改任何业务代码**。
> **审查对象**：`715d9e7`（feat）+ `7e0582c`（docs），开工基线 `5d6dcf1`，分支 `fix/m0-admission-and-m5-regressions`（未 push）。
> **证据基础**：真实源码（下列 file:line 均本轮通读核实）+ 既有审计包 `docs/audit/V2-A1-03-audit-package/evidence/`（21 份真实命令输出）+ 既有测试函数。
> **日期**：2026-11-20。
> **结论标签**：每条结论标注 **【已验证事实】/【设计建议】/【尚待验证】/【潜在风险】**。不得把有条件完成描述成完全通过。
> **配套整改方案**：[`K1-governance-remediation-plan.md`](K1-governance-remediation-plan.md)、[`K2-concurrency-remediation-plan.md`](K2-concurrency-remediation-plan.md)。

## 0. 执行边界核验

本轮仅新增审查/方案文档（本文件 + K1/K2 两份方案）。**未修改业务代码、未新增测试文件、未安装依赖、未修改迁移、未修改 A1-01/A1-02、未提交、未推送、未进入 A1-04、未修改 MILESTONES.md**。所有结论引用真实源码位置、测试函数与现有证据；凡未实跑者一律标【尚待验证】，不写 PASS。

---

## 1. K1 — Governance 审核批准路径审查

### 1.1 链接挂接的真实分布（核心发现）

**【已验证事实】** 链接同步/降级挂接**只存在于 `knowledge.py` 路由**（围绕 `submit` 调用），**不在 Core `_apply_action` 内**。因此凡经 governance 路由应用变更的路径，全部绕过链接维护。源码核实：

- Core `ReviewService._apply_action`（`knowledge-core/src/knowledge_core/review/__init__.py:115–127`）：UPDATE→`_apply_update`、DELETE→`self._items.delete`、MERGE→`_apply_merge`、RESTORE→`self._versions.restore`。**四条路径均无任何链接调用**。
- `knowledge.py` 挂接（`backend/app/api/routes/knowledge.py`）：create（:82）、draft-PATCH（:127）、extract（:182–183）commit 前 `sync_links_or_conflict`；非 active DELETE（:148–149）submit 前 `demote_backlinks_on_delete`。

**【已验证事实】** governance 有**三个**应用变更但无链接挂接的入口（`backend/app/api/routes/governance.py`）：

| 入口 | 行 | 应用方式 | 链接挂接 | 检索索引挂接 |
|---|---|---|---|---|
| `approve_review` | :309–327 | `service.approve`（active 四动作） | **无** | `_sync_applied_action`（:323，仅索引） |
| `submit_review` | :238–276 | 草稿直改 `submit` 返回 None（UPDATE/DELETE/RESTORE） | **无** | `_sync_applied_action`（:274，仅索引） |
| `restore_version` | :180–203 | 草稿回滚 `submit` 直改 | **无** | `sync_index`（:201，仅索引） |

`_sync_applied_action`（:288–306）只同步**检索索引**（DELETE 移除 / MERGE 重算目标 / UPDATE·RESTORE 重算条目），**不触碰链接**。

> **结论**：缺口比「approve DELETE」更广——**四动作 × 三入口**均无链接维护。整改不得只修 DELETE（详见 K1 方案）。

### 1.2 四动作逐条分析

#### UPDATE_ITEM（`_apply_update`，review/__init__.py:129–143）

- **【已验证事实】** 行为：`create_version(item,"编辑前快照")` → 应用 title/content/status/space_id → `items.update`。无链接调用。
- **是否需要同步链接**：**需要（content 变更时）**。【已验证事实】`BindingFirstLinkSync.sync`（link_service.py:583）按 content 解析 wikilink：新键建行、消失键删行。content 改后未同步 → 出链与新内容不一致（新增 `[[X]]` 无链接、删除的 `[[Y]]` 链接残留）。
- **是否需要降级入链**：**不需要**（条目未删除）。
- **失效反向链接**：【已验证事实】title 改名 → 指向本条目的入链所存 `target_title` 字面量过期（绑定按 UUID 稳定不断链，`BacklinkQuery` link_service.py:835 按 target_id）。字面量刷新属 reresolve/rebuild 职责（后续里程碑），**非本轮 correctness bug**。space_id 改 → 既有出链 `cross_space` 不重算（绑定优先保留行，sync 不重解析既有行，acceptance §4.5）。
- **审核/版本/事务语义**：【已验证事实】先快照后应用（线性历史，test_governance.py:81–85 锁定 2 条版本）。【设计建议】链接同步须在 `items.update` 后、commit 前插入，保持同事务原子性，不破坏「快照先行」。
- **【潜在风险】** sync 触发全局版本守卫（save_link/update_link），版本窗口内抛 `LinkNormalizationVersionMismatch`；approve/submit/restore 路由**未捕获该异常**（仅 knowledge.py 的 `sync_links_or_conflict` 映射 409）→ 治理路径会 500。整改须处理 409 映射。

#### DELETE_ITEM（`_apply_action`:120 → `SQLAlchemyKnowledgeRepository.delete`，services/knowledge.py:114–120）

- **【已验证事实】** 行为：`session.get` → `session.delete(row)` → `session.flush()`。flush 即发 DELETE，外键在事务内立即生效：出链 `source_item_id` **CASCADE** 消失；入链 `target_item_id` **SET NULL**（models.py:316–321；迁移 0006:101–102 同口径）。`resolution` 列**不被外键改动**，仍为 resolved → NULL+resolved 非法组合。
- **是否需要同步链接**：出链随 CASCADE 自动清理，**无需 sync**。
- **是否需要降级入链**：**需要，且必须在 delete flush 之前**。【已验证事实】`demote_backlinks_on_delete`（services/links.py:215）先捕获入链再置 missing；knowledge.py 非 active DELETE 已在 submit 前调用（:148–149）。governance 路径无此调用。
- **失效反向链接**：【已验证事实】无 demote 时入链写侧停留 resolved+NULL；读取侧 `_to_entity`（services/links.py:67）D12 窄口径映射为 missing+False，读取安全（test_links_http.py `test_read_side_defensive_mapping_via_http` 锁定）。**写侧降级缺失**（acceptance §4.4 / 审计包 K1）。
- **审核/版本/事务语义**：【已验证事实】`approve`（review/__init__.py:85–96）**先 `update_review` 再 `_apply_action`**，注释明示：删除会 CASCADE 审核单自身（review.item_id 外键），先应用再更新审核单会失败。【设计建议】demote 须在 `update_review` 之后、`items.delete` 之前；demote 只写 knowledge_link 入链，与审核单行无冲突，顺序可行。
- **【潜在风险】** 若在 approve **之后**（post-delete）补 demote 则**太晚**：SET NULL 已触发、target 已消失，无法按 target_id 捕获入链。整改必须 pre-delete。

#### MERGE_DUPLICATE（`_apply_merge`，review/__init__.py:145–168）

- **【已验证事实】** 行为：`create_version(source,"合并前快照")` → 存 `DUPLICATE_OF` 关系（source→target，origin=DEDUP）→ `add_source_ref(target, …新 id)` → **`source.status=ARCHIVED`** → `items.update(source)`。**source 归档而非硬删**（test_governance.py:221 锁定 archived）。无链接调用。
- **是否需要同步链接**：【已验证事实】source/target 的 **content 均未改** → 双方出链按绑定优先无需 content 驱动 sync。
- **是否需要降级入链**：**不需要，且不应降级**。【已验证事实】source 仍存在（archived），指向 source 的入链是**对存在条目的合法绑定**；`binding_semantics`（link_service.py:411–420）明示 archived 不改 resolution/cross_space，只附 warning。 demote 为 missing 会**错误丢失合法绑定**。
- **失效反向链接**：【潜在风险】指向 source 的入链仍 bound 到 archived 重复条目；用户经反链导航落到 archived 源而非 canonical 目标。**是否把 source 入链重定向到 target 属产品/特性决策（合并链接归并），非 correctness bug**；当前未实现（见 K4）。
- **审核/版本/事务语义**：【已验证事实】MERGE 任何状态都进审核（ReviewPolicy:39–40），多写（version/relation/source_refs/update）同事务。【设计建议】若未来加链接归并，须同事务、且不得 demote archived 源。
- **【潜在风险】** 整改若误把 MERGE 当 DELETE 处理（demote source 入链）会破坏合法绑定；必须区分 archived≠deleted。

#### RESTORE_VERSION（`_apply_action`:124 → `RepositoryVersionService.restore`，versioning/service.py:45–59）

- **【已验证事实】** 行为：`create_version(current,"回滚前快照")` → `current.title/content = target.title/content` → `items.update`。无链接调用。
- **是否需要同步链接**：**需要**。【已验证事实】content 回滚到旧版本 → wikilink 集合变化 → 出链与回滚后内容不一致（同 UPDATE 机理）。
- **是否需要降级入链**：**不需要**（条目未删除）。
- **失效反向链接**：title 回滚 → 入链 target_title 字面量过期（同 UPDATE，绑定稳定）。
- **审核/版本/事务语义**：【已验证事实】先快照回滚前状态（线性历史，test_governance.py:137–142 锁定）。active 回滚进审核（:149–154），草稿直改（:138–140）。【设计建议】sync 在 restore 后、commit 前。
- **【潜在风险】** 同 UPDATE 的 409 未捕获风险；草稿回滚经 `restore_version` 路由（:180）直改，同样无链接挂接。

### 1.3 K1 测试覆盖现状

- **【已验证事实】** `backend/tests/test_governance.py` 覆盖审核/版本/状态语义：`test_active_update_gated_then_approve`(:59)、`test_active_delete_gated_then_approve`(:117)、`test_restore_draft_direct_and_active_gated`(:131)、`test_submit_review_direct_and_gated`(:162)、`test_merge_review_loop`(:198)。
- **【已验证事实】** 上述测试**无任何链接/反链断言**（grep `approve` 于 test_links*.py / test_markdown_link_service.py 无命中）。链接相关测试（test_links.py / test_links_http.py）只覆盖 knowledge.py 挂接路径与读取侧映射，**不覆盖 governance 应用后的链接状态**。
- **【尚待验证】** governance 四动作应用后的链接写侧状态（demote/sync）**无测试声称通过**。整改批次须补真实测试（本轮不新增测试文件）。

---

## 2. K2 — 链接重建并发窗口审查

### 2.1 两个窗口的区分

- **【已验证事实】** **窗口①（计划生成 → 应用）已被门禁 C 关闭**：`LinkKeyRebuild.plan`（link_service.py:906）只读 `list_all_links` 生成 frozen 快照；`apply_link_key_plan`（services/links.py:308）在**独占事务内步 3 重读当前全表**，步 5 `check_plan_freshness`（link_service.py:290）逐行比对快照 vs 重读（双向覆盖 + 6 字段原始等值 + 新键重算含 no-op）。窗口①内的数据变化 → 拒绝 + 零写入 + requires_replan。T22–T30 实跑通过（evidence/t22-t40-function-map.txt）。
- **【已验证事实】** **窗口②（应用事务内重读 → 最终提交）未关闭**：步 5 门禁 C 通过（基于步 3 重读快照）→ 步 7 批量写 → 步 9 提交之间，并发事务可修改链接行。步 7 为 **blind UPDATE `WHERE id=u.link_id`**（services/links.py:397–405），**无键/版本乐观前置条件**。

### 2.2 实际锁配置（硬证据）

- **【已验证事实】** `backend/app/db/session.py`：SQLite 引擎 `create_engine(url, connect_args={"check_same_thread":False})`，**未设 journal_mode / isolation_level / busy_timeout**；PG 引擎 `create_engine(url, pool_pre_ping=True)`，**未设 isolation_level**。`get_session`（:72）yield + finally close，`autoflush=False, expire_on_commit=False`。
- **【已验证事实】** grep `journal_mode|WAL|BEGIN IMMEDIATE|isolation_level|with_for_update|FOR UPDATE|LOCK TABLE|busy_timeout` 于 `backend/app/` + `backend/alembic/` → **空**。grep `concurrent|threading|Thread(|race|with_for_update` 于链接测试 → **空**。**无任何显式锁/隔离配置，无任何并发测试**。
- **【已验证事实】** 门禁 C **不比对** target_id/resolution/cross_space/created_at/updated_at（link_service.py:299–300，LinkRowState:136 注释「target_id 携带但不参与比对」）——治理列在窗口内合法变化不触发拒绝；但键/版本/title/alias/source/行数变化触发。

### 2.3 双方言锁行为分析

- **【设计建议 / 尚待验证】** 基于 SQLite/PG 文档化语义 + 上述「无配置」事实推断（**非实跑并发测试**，故标尚待验证）：
  - **SQLite**：默认 rollback-journal（非 WAL）、DEFERRED 事务。读持 SHARED，写升级 RESERVED，提交需 EXCLUSIVE（单写者）。重读（SHARED）→ 写升级之间，另一写者可提交 → 本事务快照过期；写升级时可能 `SQLITE_BUSY`。`BEGIN IMMEDIATE` 预先持 RESERVED 可串行化写者、关闭窗口②。
  - **PostgreSQL**：默认 READ COMMITTED。SELECT 不锁行；步 3 重读 → 步 9 提交之间，并发 UPDATE/INSERT 可提交。步 7 blind UPDATE 覆盖过期键；步 8 写后复核（services/links.py:407–425，同事务重读版本 DISTINCT/键唯一/治理列与条目基线）在 READ COMMITTED 下能看到并发已提交变化、提供**部分**兜底，但步 8 → 步 9 仍有窗口，且并发改 title（不改 version）可能绕过步 8 版本检查。`SELECT … FOR UPDATE` 锁既有行 + 表锁阻 INSERT，或 SERIALIZABLE（SSI）检测写偏斜。
- **【已验证事实】** 门禁保证边界：A=重读时全表版本同构（空表特例，link_service.py:114–130）；B=计划内部自洽（services/links.py:257，不查库）；C=计划匹配重读快照（关窗口①）；步 8=事务内写后不变量。**四者均不提供跨事务互斥/隔离**。
- **【尚待验证】** 真实并发交错（双会话/线程）下双方言的实际行为**无测试**；锁行为结论为语义推断，须整改批次以真实并发测试核实。
- **【潜在风险】** FOR UPDATE/表锁的死锁与阻塞；SQLite 争用 BUSY；SERIALIZABLE 串行化失败需重试；全表锁期间阻塞所有链接写入（性能）。详见 K2 方案。

---

## 3. K3 — 双数据库一致性审查

- **【已验证事实】** 链接业务代码**零方言分支**：预检/重读/批量写全为 SQLAlchemy 表达式（services/links.py 模块 docstring + AGENTS.md §5）；`test_links.py`（SQLite 91）与 `test_links_pg.py`（真实 PG 91）**同名同断言镜像**（evidence/t22-t40-function-map.txt 函数名逐一对应；evidence/pytest-links-modules.txt 各 91 passed）。相同业务操作（save/sync/demote/rebuild/gates）双方言断言一致通过。
- **【已验证事实】** 外键语义一致：迁移 0006（:101–102）source CASCADE / target SET NULL，方言无关 DDL；models.py:316–321 同口径。SQLite 经 `PRAGMA foreign_keys=ON`（session.py:33–37 per-connect 事件）强制；PG 默认强制。测试引擎经 `create_engine_from_url`（conftest.py:45）→ pragma 生效。
- **【已验证事实】** 时间归一 `_utc`（services/links.py:58）：SQLite naive→UTC、PG timestamptz→UTC，实体层 UTC-aware 双方言往返一致。布尔经 SQLAlchemy Boolean（SQLite 0/1、PG bool）。规范化在 Core Python（NFKC/casefold），方言无关。
- **【潜在风险 / 尚待验证】** **并发语义不一致**（K2 的直接后果）：同一「并发重建」操作，SQLite 单写者数据库锁（可能 BUSY）vs PG READ COMMITTED 行级（可能静默过期写）——**行为不同**。默认隔离级别未显式设定，双方言默认不同。须整改批次以真实并发测试核实语义对齐。
- **【潜在风险】** SQLite 外键依赖 per-connect pragma：若未来新增引擎路径绕过 `create_engine_from_url`，FK 静默关闭 → 孤儿数据；PG 无此隐患。属架构守护点（建议整改批次加守护断言）。
- **【已验证事实】** 检索方言差异（FTS5 vs tsvector，V1 ZIP-01）封装在 `app/db/fts.py` / `app/services/retrieval.py`，**与链接无关**；链接路径双方言均无 FTS5/MATCH/bm25/rowid（acceptance §2）。

---

## 4. K4 — 用户功能交付边界审查

### 4.1 已实现的 Core 能力（已验证，零 ORM/IO）

| 能力 | 源码 | 测试载体 |
|---|---|---|
| 规范化 v1 / 两派生键 / wikilink 解析 + 排除矩阵 | markdown/links.py | test_markdown_links.py（41） |
| 自动解析 resolve / auto_candidates（排除 archived、精确空间） | link_service.py:491–528 | test_markdown_link_service.py（86） |
| 只读候选发现 find_candidates（含 archived/跨空间） | link_service.py:530–539 | 同上 + HTTP |
| **显式绑定 bind_explicit**（允许 archived/跨空间） | link_service.py:541–567 | 同上（场景 J/L） |
| 绑定优先同步 sync（不重解析既有行） | link_service.py:583–627 | test_links.py / test_links_http.py |
| 导入绑定恢复 restore | link_service.py:643 | 场景 D/M |
| 反链查询 backlinks（稳定 target_id） | link_service.py:835–842 | HTTP backlinks |
| **显式重解析 reresolve**（只重试 missing/ambiguous） | link_service.py:845–892 | Core 测试 |
| 键重建计划 plan（只算不写，碰撞/混合拒绝） | link_service.py:906–1021 | 场景 F/G、T1–T12 |
| 全局同构 / 计划新鲜度纯函数 | link_service.py:114 / 290 | T13–T40 |

### 4.2 已提供的 HTTP API

- **【已验证事实】** 链接 router **仅 3 只读 GET**（routes/links.py:48/74/86；`test_links_router_is_exactly_three_gets` 锁定）：`/knowledge/links/resolve-candidates`、`/knowledge/{id}/links`、`/knowledge/{id}/backlinks`。
- **【已验证事实】** knowledge CRUD 挂接同步（create/draft-PATCH/extract/非 active DELETE）；governance approve/submit/restore 同步**检索索引**（不同步链接，K1）。

### 4.3 尚无 HTTP 写入口的能力（Core 已验证，未交付用户功能）

- **【已验证事实】** `bind_explicit`（显式绑定 archived/跨空间）、`reresolve`（重解析）、`plan`+`apply_link_key_plan`（键重建）、`restore`（导入路径）**均无 HTTP 写端点**。守护断言 app 中无 `links/resolve` / `links/reresolve` / `rebuild-keys` 写路径（test_links_http.py）。HTTP 测试中的绑定经**仓库层夹具** `_bind_via_repository_fixture`（update_link）建立，**非 HTTP 写入口**。
- **措辞纪律**：写成「Core 层规则已验证（A1-03 无 HTTP 写入口）」，**不**写成「用户可显式绑定/重解析/重建」。

### 4.4 尚未完成的前端交互

- **【已验证事实】** 本轮**零前端改动**；前端 72 用例 + 构建 index 256.45 kB 与基线一致（evidence/frontend-build-full.txt）。链接编辑/预览/反链/绑定 UI 属 A2，**未实现**。

---

## 5. 跨切面风险与整改指向

| 风险 | 类别 | 指向 |
|---|---|---|
| governance 四动作×三入口无链接维护 | 有条件（K1） | K1 方案：四路径全覆盖，DELETE pre-demote、UPDATE/RESTORE post-sync、MERGE 不 demote（archived≠deleted） |
| 治理路径 sync 触发 409 未捕获 → 500 | 潜在风险（K1） | K1 方案：409 稳定码映射 + 事务零写入 |
| 重建窗口②跨事务无互斥 | 有条件/延后（K2） | K2 方案：双方言并发控制（PG FOR UPDATE+表锁 / SQLite BEGIN IMMEDIATE，或乐观锁），backend 适配层封装 |
| 双方言并发语义不一致 | 潜在风险（K3） | K2 方案统一隔离/锁策略 + 真实并发测试 |
| governance 链接状态无测试 | 尚待验证（K1） | 整改批次补真实测试（本轮不新增） |
| 并发互斥无测试 | 尚待验证（K2） | 整改批次补真实双会话并发测试（本轮不新增） |
| 显式绑定/重解析/重建无 HTTP 写入口、前端 UI 未做 | 延后（K4） | A1-04 / A2 |

---

## 6. 结论与停止点

- **【已验证事实】** A1-03 核心机制（四层分离、全局版本同构守卫、门禁 A/B/C、绑定优先同步、双方言镜像零写入、T22–T40、读取侧 D12 防御映射）经真实运行验证（SQLite 887 / PG 1019 / A1-02 293 / ruff / 前端 72，evidence/）。
- **【已验证事实】** K1 缺口真实存在且广于「approve DELETE」：四动作×三入口无链接维护；读取侧安全（DELETE 入链），写侧降级/同步缺失；MERGE 归档不删、不应 demote。
- **【尚待验证】** K2 窗口②的并发互斥、K3 并发语义对齐、K1 governance 链接写侧状态——**均无测试声称通过**，锁/并发结论为语义推断。
- **【设计建议】** 整改方案见 K1/K2 两份文档；均须另批审批后实施（涉及 governance.py / 可能的端口签名 / 锁策略），**本轮不实施**。
- **【潜在风险】** 不得把上述有条件/尚待验证项描述为完全通过。

**停止点**：本轮审查与方案设计完成即**停止，等待进一步指令**。不修改业务代码、不新增测试、不提交、不推送、不进入 A1-04、不改 MILESTONES.md。审计批准前不进入下一里程碑。