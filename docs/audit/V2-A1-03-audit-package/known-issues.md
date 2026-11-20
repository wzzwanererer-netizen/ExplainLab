# A1-03 已知缺陷 / 未完成事项 / 风险清单

> 本清单如实登记 A1-03（E1–E4）的**有条件项 / 延后项 / 设计口径**，供独立审计裁决。
> 状态三态：**有条件**（部分验证、存在已知缺口）/ **延后**（本轮范围外，留待后续批次）/ **设计口径**（非缺陷，职责分离说明）。
> **不得把有条件完成描述成完全通过。** 每项附源码定位、影响、已验证部分与审计核验点。
> 权威来源：`docs/acceptance/V2-A1-03-link-services-and-version-guard.md` §4/§6；本清单与主包 §11 一致。

---

## K1 — governance.py 审核批准路径未挂接链接 demote / sync【有条件】

- **状态**：有条件（读取安全已验证；写侧降级/重同步缺失）。
- **源码定位**：
  - 批准路由 `backend/app/api/routes/governance.py:309`（`POST /reviews/{review_id}/approve`）。
  - Core `ReviewService.approve` → `_apply_action`（`knowledge-core/src/knowledge_core/review/__init__.py:85/113`）：UPDATE_ITEM / DELETE_ITEM / MERGE_DUPLICATE / RESTORE_VERSION 四条应用路径**均未调用** `demote_backlinks_on_delete` 或 `sync_links_or_conflict`。
  - 外键 `backend/app/models.py:316–321`：source CASCADE / target SET NULL。
- **影响**：
  - **active 删除经批准**：条目删除后入链 `target_item_id` 被数据库 SET NULL，但 `resolution` 列仍为 resolved（NULL+resolved 非法组合）；**写侧未降级**。
  - **active 编辑经批准**：内容应用后链接**未在该路径重新同步**。
  - MERGE / RESTORE 同样无链接同步。
- **已验证部分（读取侧安全）**：`_to_entity`（`services/links.py:67`）D12 窄口径映射把 NULL+resolved/cross_space 降级为 missing+False，读取不抛异常；`test_read_side_defensive_mapping_via_http` 同时断言读取降级与实体校验器拒绝（校验器未弱化）。
- **为何本轮不修**：计划 §4.2 修改清单仅含 knowledge.py 四处，governance.py 不在清单内，且「任何 V1 服务一律不动」。按用户「只报告不扩范围」约束，本轮不触碰 governance.py。与计划 R9「批准后才应用并同步」存在张力，**如实记录供审计裁决是否另批挂接**。
- **延后批次**：governance 挂接批次（审计批准后另批）。
- **审计核验点**：批准 active 删除后直查 DB `knowledge_link.resolution`（应 resolved + NULL target，证明写侧未降级）；再经 GET backlinks 读取（应 missing，证明读取侧映射生效）。

## K2 — 门禁 C 残余并发窗口（apply 重读 → 提交）【有条件 / 延后】

- **状态**：有条件（过期拒绝 + 零写入已验证；并发互斥未实现）。
- **源码定位**：`apply_link_key_plan`（`backend/app/services/links.py:308`）步 3 重读 → 步 5 `check_plan_freshness` → 步 9 提交；计划 §8.4.8 第 2 条 `SELECT … FOR UPDATE` / 表锁【待审批】。
- **影响**：步 5 重读 → 步 9 提交之间，另一并发事务理论上可修改链接行使计划过期。本轮**未加行锁/表锁**。
- **已验证部分**：T22–T30（过期拒绝 + 全表逐列零写入）、T32（commit 后重新预检）、T33（rollback 后重新预检）、T39（故障注入整体回滚）实跑通过。门禁 A + C + 步 8 写后复核构成**本事务视角**纵深防御。
- **措辞纪律**：**只声称「过期计划被拒绝 + 零写入已验证」**；**不声称「重建并发安全 / 已实现互斥 / 计划不可能过期」**。
- **延后批次**：并发互斥（FOR UPDATE / 表锁）待审批后另批。
- **审计核验点**：T32/T33/T39 实跑；并发互斥本身**本轮无测试声称通过**。

## K3 — 人工显式绑定无 HTTP 写入口【延后，D8 交付边界】

- **状态**：延后（Core 规则已验证；用户功能未交付）。
- **源码定位**：`backend/app/api/routes/links.py` 仅 3 只读 GET；`test_links_router_is_exactly_three_gets` 锁定；app 无 `links/resolve` / `links/reresolve` / `rebuild-keys` 写路径。
- **影响**：用户**尚不能经 HTTP 显式绑定** archived / 跨空间候选；绑定写端点与前端交互属后续里程碑。
- **已验证部分**：Core `RepositoryLinkResolver.resolve` / `binding_semantics`（`link_service.py:411/503`）显式绑定规则经测试（场景 J/L、H17/L④）；HTTP 读取测试经**仓库层夹具** `_bind_via_repository_fixture`（`update_link`）建立绑定后验证读取——**不是 HTTP 写入口**。
- **措辞纪律**：写成「**Core 层显式绑定规则已验证（A1-03 无 HTTP 写入口）**」，**不**写成「用户可显式绑定 archived/跨空间候选」。
- **延后批次**：A1-04 / A2（绑定写端点 + 前端交互）。
- **审计核验点**：路由守护测试；确认无写端点；Core 绑定规则测试载体。

## K4 — v2 规范化规则尚未正式发布【延后】

- **状态**：延后（仅测试夹具，生产未发布）。
- **源码定位**：`knowledge-core/src/knowledge_core/domain/entities.py` `LINK_NORMALIZATION_VERSION = 1`；`markdown/links.py` `LINK_KEY_RULES = {1: v1}`。v2 经 `v2_registry` / monkeypatch 注入激活。
- **影响**：生产路径所有链接键按 v1 规范化；全局守卫要求全表同构于常量 1。**v2 未上线，未执行真实全量重建**。
- **已验证部分**：T15/T17/T27/T36/T37 用 v2 夹具验证版本漂移拒绝/混合拒绝/新键重算/不支持版本逻辑（**机制正确**）；T38 守护计划 frozen + 确定性序列化 + 无摘要。
- **措辞纪律**：不声称「v2 规范化已发布 / 已升级生产数据」。真实升级须走计划 §8.4.7 运维协议。
- **延后批次**：v2 发布与真实全量重建（运维协议，另批审批）。
- **审计核验点**：生产常量 = 1；注册表仅 v1；v2 仅夹具注入。

## K5 — 读取侧防御映射 vs 写侧状态降级【设计口径，非缺陷】

- **状态**：设计口径（职责分离说明，非缺陷；但与 K1 相关）。
- **区别**（详见主包 §11.5 表）：
  - **读取侧防御映射**（`_to_entity`，`services/links.py:67`）：每次读取时把 NULL+resolved/cross_space 非法组合映射为 missing+False；**不改库**、**不弱化实体校验器**；合法 NULL（missing/ambiguous/conflict）resolution 原样保留；覆盖所有读取路径。
  - **写侧状态降级**（`demote_backlinks_on_delete`，`services/links.py:215`）：删除目标条目前同事务把入链 target 置 NULL/resolution=missing/cross_space=False/updated_at 刷新；**改库**、键与版本不变（治理列-only 豁免守卫）；**仅** knowledge.py 非 active DELETE 挂接。
- **关键结论**：两者**不可互相替代**。读取侧是兜底安全网（不改库），写侧是主动状态维护（改库）。**当前写侧降级只在非 active DELETE 挂接**；active 删除经 governance 批准后写侧未降级，靠读取侧映射保证读取安全（K1）。
- **审计核验点**：分别核验读取侧（GET 返回 missing + 实体校验器仍拒绝非法构造）与写侧（非 active DELETE 后 DB resolution=missing）。

## K6 — 设计文档措辞同步（§2.4 / §2.9）【延后另批】

- **状态**：延后（本轮未改设计文档措辞）。
- **影响**：`docs/plans/V2-batch-A-design.md` §2.4（碰撞→整体拒绝、导入空间重算）/ §2.9 措辞与实现口径的同步留待另批审批后修改。
- **本轮纪律**：硬约束「本轮不改设计文档措辞」遵守；实现决定（D12 窄口径等）记录在验收报告与代码 docstring，**未擅自改设计文档**。
- **延后批次**：设计文档同步批次（另批审批）。

## K7 — 后续里程碑功能（本轮范围外）【延后】

- **状态**：延后。
- **项**：完整导入幂等 / 附件生命周期 / GC / 提案防覆盖 / 前端链接 UI / 重解析（reresolve）HTTP 入口。
- **延后批次**：A1-04 / A1-05 / A2 / A1-06。
- **说明**：`LinkImportRestorer.restore` / `LinkReresolve` 已在 Core 定义并经测试，但**无 HTTP 写入口**（A1-04 导入路径预留）；`build_link_restorer` 装配助手本轮 Core/测试消费。

---

## 风险评级与审计建议

| 项 | 类型 | 读取安全 | 写侧完整 | 建议 |
|---|---|---|---|---|
| K1 | 有条件 | ✅ 已验证 | ❌ 批准路径缺失 | 审计裁决是否另批挂接 governance demote/sync |
| K2 | 有条件/延后 | ✅ 过期拒绝+零写入 | ⚠️ 并发互斥未实现 | FOR UPDATE/表锁审批后另批；不声称并发安全 |
| K3 | 延后 | ✅ 只读 GET | — 无写入口（D8） | A1-04/A2 交付绑定写端点 |
| K4 | 延后 | ✅ 生产 v1 | — v2 未发布 | 运维协议审批后真实重建 |
| K5 | 设计口径 | ✅ | ⚠️ 仅非 active DELETE | 与 K1 合并裁决 |
| K6 | 延后 | — | — | 另批审批改设计文档 |
| K7 | 延后 | — | — | 后续里程碑 |

**总体**：A1-03 核心机制（四层分离、全局版本同构守卫、门禁 A/B/C、绑定优先同步、双方言零写入、T22–T40）**已真实验证**；上表有条件/延后项**均如实登记，不描述为完全通过**。审计批准前不进入 A1-04。