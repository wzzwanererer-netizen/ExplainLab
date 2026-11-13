# M2 实施计划 · 知识关系、去重与审核（细化稿，待确认）

- 日期：2026-11-14
- 状态：**待用户确认**。确认后才开始开发（沿用「计划确认 → 开发 → 实跑 → 验收报告 + MILESTONES + 提交」）。
- 上游：M0 ✅（2026-11-12）、M1 ✅（2026-11-13，commit `a2a8e01`）。
- 定位：M2 = **知识治理层**。在 M1「提取 + 持久化 + 空间」之上，补齐去重、关系、版本、审核四大治理能力。

## 0. 范围边界（做什么 / 不做什么）

做：重复识别、关系推断、版本管理、来源追溯落地、重要变更审核流，及其最小 API 与前端界面。

不做（严禁提前）：
- M3 的 FTS5 全文索引 / 向量存储 / 混合检索 API 与检索 UI。M2 去重的候选召回用**纯 Python 词面相似度**（不建检索索引），语义向量去重留到 M3。
- M4 知识地图（React Flow / ELK.js）、M5 交互实验。
- 不铺全量页面；前端只加 M2 必需的最小界面。

关键供应商约束：**DeepSeek 的 OpenAI 兼容端点不提供 `/embeddings`**。M2 所有模型调用只用 `generate`（去重判定、关系推断）。开发前先以只读方式探测供应商能力，不臆断；适配器保持可替换，M3 可换支持 embed 的供应商或本地向量。

## 1. 架构对齐

- 全部治理逻辑落在 **Knowledge Core**（独立包，仅 Pydantic + httpx），通过端口依赖持久化，可复用于 Nesti；不依赖前端 / Web 框架（独立性测试继续守护）。
- 复用 M0 已定义的抽象：`relations.RelationService`（`find_duplicates` / `infer_relations`）、`versioning.VersionService`（`create_version` / `list_versions` / `restore`）、`provenance.ProvenanceService`（`attach_source` / `trace`）。M2 给出实现，不改接口签名。
- 复用已有领域实体：`KnowledgeRelation`（含 `RelationType.DUPLICATE_OF/REFINES/CONTRADICTS/...`）、`KnowledgeVersion`、`SourceRef`。
- 审核编排放在 Core（`review/` 新包），便于 Nesti 复用；Backend 只做装配与 HTTP。

## 2. 数据模型与迁移

### 2.1 领域新增（core/domain/entities.py）

- `ReviewStatus(StrEnum)`：`pending / approved / rejected`。
- `ReviewAction(StrEnum)`：`update_item / delete_item / merge_duplicate / restore_version`。
- `ReviewRequest(BaseModel)`：`id, item_id, action, payload(dict), reason, status=pending, created_at, resolved_at|None, resolution_note|None`。`payload` 承载拟变更内容（新 title/content/status、合并目标 id、回滚版本号等）。
- `RelationOrigin(StrEnum)`：`manual / llm / dedup`；给 `KnowledgeRelation` 增加 `origin` 字段（默认 manual），区分人工 / 模型推断 / 去重产生。
- `KnowledgeVersion` 沿用现有字段（item_id, version, title, content, change_summary）。

### 2.2 ORM 新表（backend/app/models.py）+ 迁移 `0003_m2_governance`

表名单数，与 M1 一致（knowledge_item / source_ref ...）：

| 表 | 主要列 | 约束 |
|---|---|---|
| knowledge_relation | id, source_id→knowledge_item, target_id→knowledge_item, relation_type, confidence, origin, created_at | FK CASCADE；UNIQUE(source_id,target_id,relation_type) |
| knowledge_version | id, item_id→knowledge_item, version, title, content, change_summary, created_at | FK CASCADE；UNIQUE(item_id,version) |
| review_request | id, item_id→knowledge_item, action, payload(JSON Text), reason, status, created_at, resolved_at, resolution_note | FK CASCADE |

SQLite 用 `render_as_batch`；`alembic upgrade head` 实跑 + `alembic check` 无漂移。

### 2.3 端口新增（core/ports.py，Protocol，向后兼容）

- `RelationRepository`：save_relation / list_relations(item_id) / delete_relation / find_relation(source,target,type)。
- `VersionRepository`：save_version / list_versions(item_id) / get_version(item_id,version)。
- `ReviewRepository`：save_review / get_review / list_reviews(status) / update_review。

Backend 以 SQLAlchemy 实现（`app/services/governance.py`），与 M1 `SQLAlchemyKnowledgeRepository` 同风格。

## 3. Core 服务实现

### 3.1 去重 + 关系（relations/）

- `relations/lexical.py`（纯函数，无模型，可单测）：规范化（小写、去标点空白）+ 标题重叠 + 内容 char-bigram 余弦 / Jaccard，产出候选相似度。
- `relations/llm.py` `LLMRelationService(RelationService)`：
  - `find_duplicates(item, candidates)`：① 词面召回 top-K（阈值过滤）→ ② 对候选用 `generate` 让模型判定「是否同一知识」+ 置信度（JSON）→ ③ 返回确认的 `DuplicateMatch(score)`。解析失败如实返回空，不造假。
  - `infer_relations(item, candidates)`：`generate` 推断关系类型（RelationType 子集）+ 置信度 → 构造 `KnowledgeRelation(origin=llm)`，校验不自环。
- 候选集合由调用方传入（Backend 用 `repository.list(space)`），Core 不建检索索引。

### 3.2 版本（versioning/service.py）

`RepositoryVersionService(VersionService)`：
- `create_version`：读当前条目，version=max+1，快照 title/content。
- `list_versions`：升序。
- `restore`：先为「回滚前」状态建一个新版本（保持历史线性），再把条目 title/content 设为目标版本内容，bump updated_at，返回条目。

### 3.3 来源追溯落地（provenance/service.py）

`RepositoryProvenanceService(ProvenanceService)`：`attach_source` 追加 SourceRef；`trace` 返回条目全部来源（含 conversation_id + excerpt）。M1 已随条目落库来源，M2 补齐独立挂载 / 追溯接口实现。

### 3.4 审核（review/ 新包）

- `ReviewPolicy`：判定「重要变更」。矩阵（见 §4）。
- `ReviewService`：`submit(change)` / `approve(id)` / `reject(id)`，组合 ReviewRepository + KnowledgeRepository + VersionService + RelationRepository。
  - submit：重要 → 建 pending 审核单、**不应用**；非重要 → 直接应用。
  - approve：应用 payload；update/merge/restore 先建版本快照；置 approved。
  - reject：置 rejected，不改动数据。
  - merge_duplicate：源条目置 archived（不硬删，保留追溯）+ 建 `DUPLICATE_OF` 关系（origin=dedup）+ 源 source_refs 并入目标。

### 3.5 编排（services.py 扩展）

`KnowledgeService.analyze_item(item)`：对条目跑 find_duplicates + infer_relations（候选=同空间条目），持久化关系，返回 `{duplicates, relations}`。M1 `extract_and_store` 契约不变；分析走独立入口，避免改 M1 提取响应。

## 4. 重要变更审核矩阵（决策，需确认）

| 操作 | 条目当前状态 | 是否进审核 |
|---|---|---|
| 编辑（update） | draft | 否，直接应用 |
| 编辑（update） | active | **是** |
| 删除（delete） | draft | 否，直接删除 |
| 删除（delete） | active | **是** |
| 合并重复（merge） | 任意 | **是** |
| 回滚版本（restore） | active | **是** |
| 回滚版本（restore） | draft | 否 |
| draft→active（发布） | draft | 否（发布自己的草稿） |

理由：草稿是 scratch，直接改删保持 M1 体验与测试兼容；生效知识的改 / 删 / 合并 / 回滚才属「重要变更」。被审核拦截时 API 返回 **202 + 审核单**，前端提示「已提交审核」。

## 5. Backend API（新增 / 调整）

新增：
- `GET /api/knowledge/{id}/duplicates`：查重候选（词面+LLM）。
- `POST /api/knowledge/{id}/analyze`：去重+关系推断并落库，返回 duplicates/relations。
- `GET/POST /api/knowledge/{id}/relations`、`DELETE /api/relations/{rid}`：关系查看/人工增删。
- `GET /api/knowledge/{id}/versions`、`POST /api/knowledge/{id}/versions/{v}/restore`：版本列表/回滚（active 走审核）。
- `POST /api/knowledge/{id}/sources`：挂载来源（trace 复用条目 source_refs）。
- `GET /api/reviews?status=`、`POST /api/reviews`、`POST /api/reviews/{id}/approve`、`POST /api/reviews/{id}/reject`。

调整（行为变化，需同步前端与测试）：
- `PATCH /api/knowledge/{id}`、`DELETE /api/knowledge/{id}` 经 ReviewService：active 的改/删返回 202+审核单；draft 保持 M1 的 200/204。

模型未配置 503、调用失败 502 回滚，沿用 M1 依赖层。

## 6. Frontend 最小界面（M2）

- KnowledgeView 条目详情：关系 / 版本 / 来源 三个分区；按钮「查重分析」「回滚」。
- 查重候选提示条：analyze 返回重复时展示候选 + 「合并」（提交 merge 审核）。
- 新增「审核」页签：pending 队列（操作摘要 + 批准 / 驳回）。
- 处理 202：提示「已提交审核，可在审核页签处理」。
- 不新增 M3+ 页面。

## 7. 测试与验证

- Core：词面相似度单测；LLMRelationService（FakeAdapter：判定/关系解析、畸形→空）；VersionService create/list/restore；ReviewPolicy 矩阵；ReviewService submit/approve/reject/merge（InMemory 仓库）；Provenance attach/trace；独立性闭包测试继续通过。
- Backend：迁移 0003 表存在；duplicates/analyze/relations/versions/restore/reviews API；active 改/删 202 门禁、draft 直连；approve 应用+建版本、reject 无副作用；merge 归档+关系+来源并入。
- Frontend：审核队列批准/驳回；详情关系/版本渲染；202 提示。
- 全量：pytest + ruff + vitest + build + alembic 无漂移。

## 8. 真实模型联调

用真实 DeepSeek `generate`：对 M1 现有 2 条 + 人工新增 1 条近似重复条目，跑查重判定与关系推断，确认关系/重复落库；经 API 走一次 merge 审核（提交→批准）验证治理闭环。**不调用 embed**。留存干净 UTF-8 证据。

## 9. 任务拆分与依赖

| # | 任务 | 依赖 |
|---|---|---|
| T1 | 领域新增 + 端口 + ORM + 迁移 0003 | — |
| T2 | Core 词面 + LLMRelationService | T1 |
| T3 | Core VersionService + ProvenanceService | T1 |
| T4 | Core ReviewPolicy + ReviewService | T1 |
| T5 | Backend 仓库实现 + 服务装配 + API | T2,T3,T4 |
| T6 | Frontend 最小界面 | T5 |
| T7 | 全量测试 + lint + 构建 + 无漂移 | T6 |
| T8 | 真实模型联调 + 验收报告 + MILESTONES + 提交 | T7 |

T2/T3/T4 可在 T1 后并行；每阶段实跑验证后再进下一步。

## 10. 风险与决策

1. DeepSeek 无 embed → 仅 generate；先只读探测能力；向量语义去重留 M3。
2. LLM JSON 解析失败 → 如实返回空 / 跳过，不造假。
3. active 改/删改走 202 审核 → 前端与 M1 相关测试同步更新；draft 不变保兼容。
4. merge 采用「归档 + DUPLICATE_OF + 来源并入」，不硬删，保追溯。
5. 审核策略放 Core，Nesti 可复用；不绑定 Web。
6. 不提前建 FTS/向量/检索 UI（M3）、地图（M4）、实验（M5）。

## 11. 验收标准（M2 完成定义）

- [ ] 迁移 0003 实跑、无漂移；三张治理表就绪。
- [ ] 去重（词面+LLM）与关系推断可用且落库，来源/origin 可追溯。
- [ ] 版本 create/list/restore 可用；restore 保留线性历史。
- [ ] 重要变更按矩阵进审核；批准应用、驳回无副作用；merge 闭环。
- [ ] 来源追溯 attach/trace 落地。
- [ ] 前端最小界面（详情关系/版本/来源、查重合并、审核队列）真实可用。
- [ ] 全量测试 + ruff + 构建 + 无漂移通过；Core 独立性守护通过。
- [ ] 真实 DeepSeek 联调证据；验收报告 + 截图；MILESTONES M2 ✅；Git 提交。

---

确认本计划（尤其 §4 审核矩阵与 §5 的 202 行为变化）后，我按 T1→T8 开始开发。