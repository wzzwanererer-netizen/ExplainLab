# K1 整改方案 — Governance 审核批准路径接入链接维护

> **性质**：**设计建议（待审批后实施）**。本轮只设计方案，**不修改业务代码、不新增测试文件**。
> **依据**：[`A1-03-final-review.md`](A1-03-final-review.md) §1；真实源码 file:line；既有测试函数。
> **范围红线**：不重写 Knowledge Core；不使其耦合 UI；不改 A1-01/A1-02 已冻结端口签名（除非另批审批）；不改迁移；不删除/弱化已有测试；方言差异封装在 backend 适配层。
> **标签**：每条标注 **【已验证事实】/【设计建议】/【尚待验证】/【潜在风险】**。

## 1. 问题陈述（已验证事实）

**【已验证事实】** 链接维护挂接只在 `knowledge.py` 路由（create :82 / draft-PATCH :127 / 非 active DELETE demote :149 / extract :183），**不在 Core `ReviewService._apply_action`**（review/__init__.py:115–127）。governance 的三个应用入口（`approve_review` :310 / `submit_review` 草稿直改 :239 / `restore_version` 草稿直改 :181）**均无链接挂接**，仅 `_sync_applied_action`（:288）同步检索索引。

**【已验证事实】** 四动作 Core 实现均无链接调用：UPDATE（`_apply_update` :129）、DELETE（`_items.delete` :121 → services/knowledge.py:114 flush）、MERGE（`_apply_merge` :145，source 归档非删）、RESTORE（`_versions.restore` :125 → versioning/service.py:45）。

**【已验证事实】** `test_governance.py` 全部审核/版本/合并测试**无链接断言**；链接测试只覆盖 knowledge.py 路径与读取侧映射。governance 应用后的链接写侧状态**无测试声称通过**。

> 整改必须覆盖 **四动作 × 三入口**，不得只修 DELETE。

## 2. 逐动作整改需求矩阵

| 动作 | 同步出链 sync | 降级入链 demote | 入链失效性质 | 关键约束 |
|---|---|---|---|---|
| UPDATE_ITEM | **需要**（content 变 → wikilink 集合变） | 不需要（未删） | title 改名 → 入链 target_title 字面量过期（UUID 绑定稳定，非断链） | sync 在 `items.update` 后、commit 前；先快照后应用顺序不变 |
| DELETE_ITEM | 不需要（出链 CASCADE 自动清） | **需要，pre-delete** | 无 demote → 入链写侧 resolved+NULL（读侧 D12 映射安全） | demote 须在 `update_review` 后、`items.delete` flush 前 |
| MERGE_DUPLICATE | 不需要（双方 content 未改） | **不需要且不应**（source 归档≠删，入链合法） | 入链仍 bound 到 archived 源（导航落点问题，非断链） | 严禁 demote archived 源；链接归并属特性决策（K4） |
| RESTORE_VERSION | **需要**（content 回滚 → wikilink 集合变） | 不需要（未删） | title 回滚 → 入链字面量过期（同 UPDATE） | sync 在 restore 后、commit 前；先快照后回滚顺序不变 |

**【已验证事实】** 矩阵依据：`BindingFirstLinkSync.sync`（link_service.py:583）按 content 解析；`demote_backlinks_on_delete`（services/links.py:215）先捕获入链再置 missing；`binding_semantics`（link_service.py:411–420）archived 不改 resolution 只附 warning；FK source CASCADE / target SET NULL（models.py:316–321）。

**【设计建议】** title 改名/回滚导致的入链 `target_title` 字面量过期，**不在本轮 correctness 整改范围**——绑定按 UUID 稳定，字面量刷新属 reresolve/rebuild（后续里程碑）。本轮只保证：出链与内容一致（UPDATE/RESTORE sync）、入链写侧不残留非法 resolved+NULL（DELETE demote）、MERGE 不误降级。

## 3. 三个应用入口的挂接点

### 3.1 approve_review（active 四动作，governance.py:310–327）

**【已验证事实】** 现序：`_pending_review` → `service.approve(review_id, note)`（内部先 `update_review` :94 再 `_apply_action`）→ `session.commit()` → `_sync_applied_action`（仅索引）→ `session.commit()`。

**【设计建议】** 按动作分流插入链接维护，**与 `_apply_action` 同事务**（在 `service.approve` 内或其紧邻、commit 前）：
- **DELETE**：demote 必须在 `_apply_action` 的 `items.delete` **之前**。因 `approve` 先 `update_review` 后 `_apply_action`（删除 CASCADE 审核单自身），可行序为 `update_review` → **demote_backlinks_on_delete(item_id)** → `_apply_action`(delete)。
- **UPDATE / RESTORE**：在 `_apply_action`（items.update / restore）**之后**、commit 前 `sync_links_or_conflict(session, item)`。
- **MERGE**：**不做 demote、不做 content sync**（source 归档、content 未改）。可选：记录 archived warning（已有 binding_semantics 语义），链接归并留待特性决策。

### 3.2 submit_review 草稿直改（governance.py:239–276）

**【已验证事实】** 草稿 UPDATE/DELETE/RESTORE 经 `submit` 返回 None 直接应用（ReviewPolicy:38 非 important），随后 `_sync_applied_action`（:274，仅索引）→ commit。MERGE 任何状态进审核（返回 review，不在此直改）。

**【设计建议】** 在 `submit` 直改分支、`_sync_applied_action` 同事务内补链接维护：DELETE pre-demote（submit 内部 delete 前）、UPDATE/RESTORE post-sync。草稿直改与 active approve 共用同一套按动作分流逻辑（见 §4 实现选项）。

### 3.3 restore_version 草稿直改（governance.py:181–203）

**【已验证事实】** 草稿回滚 `submit`（:192）直改 → `sync_index`（:201，仅索引）→ commit；active 回滚进审核（返回 202，走 approve）。

**【设计建议】** 草稿直改分支在 restore 后、commit 前 `sync_links_or_conflict(session, restored_item)`。active 回滚经 approve（§3.1 RESTORE 分支）覆盖。

## 4. 实现选项（设计建议，须审批择一）

### 选项 A — backend 路由层挂接（推荐，零 Core/端口改动）

**【设计建议】** 在 governance.py 三入口按动作分流，复用既有 backend 适配层函数 `demote_backlinks_on_delete`（services/links.py:215）与 `sync_links_or_conflict`（routes/links.py:36）。
- **DELETE pre-demote 的时序难点**：`approve` 把 `update_review`+`_apply_action` 封在 Core 内，路由层无法在二者之间插 demote。两种可行做法：
  - **A1（路由预 demote）**：在调用 `service.approve` **之前**，对 DELETE 动作先 `demote_backlinks_on_delete(session, item_id)`（同 session/同事务），再 approve。demote 只写 knowledge_link 入链，先于 `update_review` 与 delete 均安全（入链行不依赖审核单）。**【已验证事实】** demote 按 target_id 捕获入链（services/links.py:215），此时条目尚未删、入链 target_id 仍在 → 可捕获。
  - **A2（Core 暴露应用前钩子）**：需改 Core approve 签名/回调 → 触及 A1-01 冻结面，**不推荐**（见选项 B）。
- **UPDATE/RESTORE post-sync**：approve/submit/restore 在 Core 应用后、commit 前，路由层取回条目 `sync_links_or_conflict`。
- **优点**：不改 Core、不改端口签名、不改迁移；与 knowledge.py 既有挂接风格一致（§4.2 backend 只做装配）。
- **缺点**：挂接分散在三入口，须保证四动作分流一致；Core `_apply_action` 仍无链接语义（未来若新增非 HTTP 调用方仍会漏）。
- **【潜在风险】** A1 预 demote 后若 approve 因其它原因失败回滚，demote 随同事务回滚（零写入语义保持）；须确认 demote 与 approve 共用同一 session 事务边界。

### 选项 B — Core `_apply_action` 集中挂接（持久，但改冻结端口）

**【设计建议】** 在 Core `_apply_action` 四分支内集中调用链接维护，经**新增端口方法**（如 `LinkRepository.demote_backlinks` / 注入 `LinkSyncService`）驱动，backend 实现端口。
- **优点**：链接语义内聚于 Core，任何调用方（HTTP/脚本/未来 Nesti）都自动维护；杜绝分散漏挂。
- **缺点 / 红线**：须在 `knowledge_core.ports` 增端口方法或改 `ReviewService` 构造签名 → **触及 A1-01/A1-02 冻结面**，按 AGENTS.md §11 与本轮边界**须另批独立审批**；Core 须保持零 ORM/IO（经端口注入，不得 import backend）。
- **【潜在风险】** 改冻结签名影响 A1-02 既有 293 测试与端口指纹（fingerprint manifest ports.py）；须重跑独立性守护与全量回归。**本轮不实施**。

**【设计建议】** 推荐 **选项 A（A1 预 demote + post-sync）** 作为本轮整改最小可行面；选项 B 作为后续架构演进单独提案审批。

## 5. 409 / 异常映射策略（设计建议）

**【已验证事实】** `sync_links_or_conflict`（routes/links.py:36）捕获 `LinkNormalizationVersionMismatch` → 409 `link_version_mismatch`；governance 三入口**未捕获**该异常。sync 内 save_link/update_link 触发全局版本守卫（services/links.py:96 `_precheck_global_version`）。

**【设计建议】** governance 接入 sync 后，须把 `LinkNormalizationVersionMismatch` 映射为**稳定错误码 409**（复用 `link_version_mismatch`），不得回传 `str(exc)`/堆栈（AGENTS.md §9）。映射点：
- 在 governance 路由对 sync 调用包同一 409 转换（或抽公共 helper 供 knowledge.py / governance.py 共用）。
- 409 须**零写入**：sync 抛异常 → 同事务回滚（含已应用的 items.update / demote）。**【潜在风险】** approve 已 `update_review`（审核单置 approved）后 sync 抛 409 → 须确认整事务回滚使审核单决议一并撤销，避免「审核已批准但变更未应用」的不一致。get_session（session.py:72）finally close 回滚未提交事务 → 满足零写入；须测试核实。

**【尚待验证】** 409 触发时 approve 事务整体回滚（含 update_review）的真实行为，须整改批次以真实测试核实（本轮不新增测试）。

## 6. 事务与审核/版本语义保护（设计建议）

- **【已验证事实】** approve 先 `update_review` 后 `_apply_action`（DELETE CASCADE 审核单自身）；`_apply_update`/`restore` 先 `create_version` 快照后应用（线性历史）。
- **【设计建议】** 链接维护插入不得打乱：
  - DELETE：demote 在 delete flush 前（A1 在 approve 前，或 update_review 后 _apply_action 前）。
  - UPDATE/RESTORE：sync 在 items.update/restore 后、commit 前；快照先行顺序不变。
  - MERGE：不 demote、不 content sync；多写（version/relation/source_refs/update）同事务不变。
- **【设计建议】** 所有链接维护与 Core 应用**同事务**，保证原子性：要么变更+链接一起提交，要么一起回滚（零写入）。

## 7. 未来测试计划（仅提案，本轮不新增测试文件）

**【设计建议】** 整改批次须补真实测试（SQLite 必测 + PG 镜像），覆盖四动作×三入口：
1. **DELETE approve**：建 active 条目 + 入链（resolved）→ approve 删除 → 断言入链写侧 `resolution=missing`、`target_id=NULL`（demote 生效，非仅读侧映射）；出链 CASCADE 消失；审核单决议与删除同事务。
2. **DELETE 草稿直改**（submit_review / 非 active）：同上 demote 断言。
3. **UPDATE approve / 草稿直改**：content 增删 wikilink → approve/submit → 断言出链同步（新键建行、消失键删行）；版本快照先行（2 条）不变。
4. **RESTORE approve / 草稿直改**：回滚旧 content → 断言出链与回滚内容一致；回滚前快照保留。
5. **MERGE approve**：source 归档 → 断言 source 入链**仍 resolved/bound**（未误 demote）、target_id 仍指 source；duplicate_of 关系 + source_refs 并入不变。
6. **409 零写入**：构造版本窗口 → governance sync 抛 `LinkNormalizationVersionMismatch` → 断言 409 稳定码 + 条目/审核单/链接整事务回滚（无部分写入）。
7. **双方言镜像**：上述断言在 `test_links_pg.py` 同名镜像（真实 PG，EXPLAINLAB_PG_TEST_URL 门控）。
8. **回归**：A1-02 293 + 全量 SQLite/PG + ruff + 独立性守护不回归。

**【尚待验证】** 上述测试**尚未编写/运行**，本轮仅提案。不得把提案写成已通过。

## 8. 实施边界与停止点

- **【设计建议】** 本方案须**另批审批**后实施（涉及 governance.py 挂接、409 映射、可能的事务序调整）。选项 B 另需 A1-01 端口签名变更审批。
- **本轮不实施**：不修改业务代码、不新增测试、不改迁移、不改 A1-01/A1-02、不提交、不推送、不进入 A1-04、不改 MILESTONES.md。
- **【潜在风险】** 整改若误把 MERGE 当 DELETE demote、或 DELETE post-delete 补 demote（太晚）、或 sync 409 未映射致 500 / 部分写入，均会引入新缺陷——须按 §2/§3/§5/§6 约束实施并以 §7 真实测试核实。

**停止点**：方案设计完成即停止，等待审批与进一步指令。

---

## 9. 实施状态（K1+K2 整改批，2026-11-20 追加）

> 本节为整改批**实施后**追加。验收详见
> [`docs/acceptance/V2-K1K2-remediation/V2-K1K2-remediation-report.md`](../../acceptance/V2-K1K2-remediation/V2-K1K2-remediation-report.md)。

- **【已验证事实】** 采用**选项 A**（路由层挂接，Core `ReviewService` 零改动）；选项 B（Core 内挂接）因需改 A1-01 冻结端口签名、未获审批而**延期**。
- **【已验证事实】** `governance.py` 三处应用点 × 四动作已挂接：
  - `approve_review`：DELETE 于 `service.approve` **前**预降级入链（删除 flush 前）；UPDATE/RESTORE 于 approve **后**、`session.commit()` **前**同步出链；MERGE 不降级不同步。
  - `submit_review`（草稿直改）：非重要变更 DELETE 于 submit 前预降级；`review is None`（直接应用）时 UPDATE/RESTORE 同步出链。
  - `restore_version`（草稿直改）：`review is None` 时 RESTORE 同步出链。
  - 新增 helper `_demote_backlinks_before_delete` / `_sync_links_after_content_change`；复用 `demote_backlinks_on_delete`（D12 写侧）与 `sync_links_or_conflict`（409 稳定码映射）。
- **【已验证事实】** 409 零写入：治理同步遇版本异写 → `link_version_mismatch`，整事务回滚（审核决议一并回滚，审核单仍 pending、条目正文/链接不变）。
- **【已验证事实】** 新增测试：`test_governance_links.py`（SQLite 12）+ `test_governance_links_pg.py`（真实 PG 11），含 DELETE **写侧原始列**降级断言（独立连接读 resolution/target_item_id，区别于读取侧 D12 映射）、MERGE 归档不降级、UPDATE/RESTORE 同步、409 零写入。
- **【已验证事实】** 治理端点集合不变（守护测试）；Core 独立性守护 14 过；全量 SQLite 906 / 真实 PG 1056 通过。