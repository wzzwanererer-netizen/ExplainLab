# ExplainLab V2 可行性评估与里程碑拆解计划

> 文档性质：**规划 / 可行性评估（Planning Only）**，不是开发成果，不代表已进入任何新里程碑。
> 编写日期：2026-11-17 ｜ 基线：V1.0（M0–M5）+ 回填修复提交 `6d91718`
> 状态：**待用户确认 + 待独立复审**。当前迁移 0004 历史数据回填修复仍在等待独立复审。

---

## 0. 门禁与边界（先读这一节）

按仓库 `AGENTS.md` §10/§11 与既定执行规则：

- ExplainLab 现处「修复 + 等待独立复审」阶段，**未经独立审计批准不得进入 M1 之后的新里程碑开发**。
- 本文件**只做规划与可行性评估**：不写实现代码、不改 Core / 无关模块、不新增依赖、不执行迁移、不提交、不宣布进入 V2 开发。
- V2 是一次完整产品升级，体量相当于多个新里程碑，**必须拆批、先规划确认、再逐批真实验证**。
- 启动任何 V2 批次的前置条件（批次 0）：① 当前回填修复独立复审通过；② 本规划经用户确认；③ 涉及的新大型依赖逐项获用户批准（§11.4 红线）；④ 用户明确解除/批准越过审计门禁。

**通俗摘要（给产品负责人）**：V1.0 的「对话提取知识、去重关系、审核、检索、地图、实验」这套底座可以继承。V2 真正要新做的是：把知识正文变成开放的 Markdown 笔记（可编辑、可导入导出、双向链接）、Obsidian 式图谱、四个外部采集入口（浏览器扩展 / MCP / 导入 / 剪贴板）、自动知识流水线 + 收件箱。这些不是一次能做完的，建议**先落地「开放 Markdown 知识库」**作为数据底座，再按批次推进。下面每一批都标了「复用什么 / 新做什么 / 要你批准什么 / 怎么算验收通过」。

---

## 1. V2 与 V1.0 的关系：继承 vs 新增

### 1.1 可直接继承的底座（已验证存在）

| 能力 | 现有落点（文件证据） | V2 复用方式 |
|---|---|---|
| 领域实体 | `knowledge-core/src/knowledge_core/domain/entities.py`：`KnowledgeItem`/`SourceRef`/`KnowledgeRelation`/`KnowledgeVersion`/`ReviewRequest` | 扩展字段，不重写 |
| 端口注入 | `knowledge_core/ports.py`：`KnowledgeRepository`/`RelationRepository`/`VersionRepository`/`ReviewRepository`/`ExperimentRepository`/`FullTextIndex`/`VectorStore`/`Embedder` | 新增端口走同一模式 |
| 知识提取 | `extraction/llm.py` `LLMExtractionService` + `services.py` `KnowledgeService` | 接入 Pipeline |
| 去重 / 关系 | `relations/llm.py` `LLMRelationService`；`RelationType` 含 `duplicate_of`/`contradicts`；`RelationOrigin` 含 `manual`/`llm`/`dedup` | 去重/冲突/关系识别复用；origin 正好支撑「AI 推测 vs 已确认」视觉区分 |
| 版本 | `versioning/service.py` `RepositoryVersionService`（create/list/restore，restore 先建回滚前快照） | 版本追溯复用；diff/merge UI 新增 |
| 审核门禁 | `review/` `ReviewService` + `ReviewAction`（update/delete/merge/restore） | Inbox 审核复用 |
| 来源追溯 | `provenance/service.py` `RepositoryProvenanceService`（attach/trace） | 扩展来源字段 |
| 混合检索 | `retrieval/hybrid.py` `HybridRetrievalService`（FTS + 向量 RRF）；backend `app/services/retrieval.py` 双方言适配 | 检索增强复用 |
| 图数据装配 | `graph/service.py` `KnowledgeGraphService`（节点+边，无坐标，仅依赖端口） | 全局/局部图数据底座 |
| 实验 | `experiments/`（quiz/compare/chain） | 降级为「知识探索」扩展模块 |
| Model Adapter | `model_adapter/`（OpenAI 兼容，公共失败契约，GENERATE+EMBED） | 所有 AI 调用统一入口 |
| 持久化 / 迁移 | backend `app/models.py` + Alembic `0001–0005`；双方言（SQLite/PG） | 新增迁移 `0006+` |
| 前端骨架 | React 19 + Vite 8 + Tailwind v4；`App.tsx` 七页签；`KnowledgeMap`（@xyflow/react + elkjs）；React.lazy 懒加载（ZIP-04） | 导航重构 + 新视图 |

### 1.2 V2 需要新增 / 重做的（已验证「当前不存在」）

- **Markdown 开放存储**：正文现为 DB `Text`（`KnowledgeItemORM.content`），前端纯 `<textarea>` 编辑、`whitespace-pre-wrap` 纯文本展示（`frontend/src/components/KnowledgeView.tsx`）。全仓 grep 无 `markdown/remark/rehype/katex/codemirror/monaco/frontmatter/backlink`。→ 编辑器、预览、导入导出、双向链接/反链、frontmatter、附件**全部新增**。
- **知识组织字段**：`KnowledgeItem` 无 `tags`、无分类（9 类）、无验证状态、无文件夹、无附件。→ 实体/表/服务/UI 新增。
- **对话来源字段**：`Conversation`（title/space_id/时间）、`Message`（role/content/created_at）**缺**平台来源、来源链接、原始数据、附件信息、采集时间（V2 §5）。→ schema 扩展。
- **来源元数据**：`SourceRef`（source_type/uri/conversation_id/excerpt/created_at）**缺**来源平台、来源消息 id、提取模型、提取时间、验证状态（V2 §10）。→ 扩展。
- **导航**：现为 对话/知识库/检索/地图/实验/审核/系统状态 七页签；V2 要 Overview/Conversations/Knowledge/Graph/Search/Inbox/Settings，且实验降级。→ 重构；Overview/Inbox/完整 Settings **新增**（现「系统状态」偏健康展示，非模型/渠道/存储配置）。
- **图谱**：现 React Flow + elkjs 分层布局、全量平铺图。V2 全局力导向图、局部图（深度/方向/数量限制）、过滤、聚类、推荐、冲突提示、节点详情面板。→ 布局/交互/智能探索新增；全局力导向图可能需新图库（依赖待批准）。
- **外部采集**：浏览器扩展、MCP Server、Import（MD/JSON/TXT/HTML/PDF/ChatGPT 导出）、Clipboard 快捷采集。→ **四个全新子系统**（扩展是独立代码库/平台）。
- **自动 Pipeline**：12 段统一编排；重要性判断、实体识别、分类、冲突检测、保存策略（自动 vs 审核）。→ 部分复用提取/去重/关系/版本/审核/索引，编排与新增阶段需建。
- **安全/权限**：跨空间搜索授权策略、重要操作审计日志、删除原始对话+关联知识、数据导出。→ 新增（space_id 隔离已有基础）。

---

## 2. 关键架构决策与风险（ hardest parts ）

### 决策 A：Markdown 开放存储模型（§6.3，优先落地的核心）

PRD 明确「内部数据库可以继续使用 PostgreSQL，但不得让知识正文只能通过私有数据库格式读取」。据此有两条路线：

- **路线 1（推荐）：DB 为权威存储 + 无损 Markdown 往返（导入/导出适配器）。**
  - 正文仍存 DB（继承现有持久化/检索/版本/审核），但保证「导出为标准 `.md`（YAML frontmatter + Markdown 正文）→ 任何工具可读 → 再导入无损还原」。
  - frontmatter 承载：稳定 ID（现有 UUID）、title、tags、space、status、来源元数据（平台/会话/消息/uri/采集时间/提取模型+时间）、验证状态、version、created/updated。
  - 新增**纯 Core 序列化器**（entity ↔ markdown 文本，无 DB/无 Web）+ backend **vault 文件系统适配**（导出/批量导出/附件导出/导入）。
  - 优点：改动可控、不牺牲稳定性（§2 原则）、Core 独立性易守、满足开放性。缺点：不是「文件即权威」的 Obsidian 原生 vault。
- **路线 2（备选，未来演进）：文件系统 Markdown vault 为权威 + DB 仅索引。**
  - 更贴近 Obsidian，但引入文件监听/同步/冲突/一致性复杂度，稳定性风险高，本轮不建议。

> **建议先走路线 1**，把「开放交换格式 + 稳定 ID + 无损往返」做扎实；路线 2 列为后续可选演进。**此决策需用户拍板**（见 §6 开放决策）。

### 决策 B：双向链接 / 反向引用语法与解析

- 推荐：正文用 `[[标题]]` 书写，保存时解析为**稳定 ID 锚定**的链接（标题可改、链接不断），渲染显示标题。
- 反链 = 链接的反向索引。链接可落为专用 `knowledge_link` 表，或复用 `KnowledgeRelation`（origin=manual）。**需定夺**：独立链接表 vs 复用关系表（影响图谱与检索口径）。
- 链接解析/反链计算放**纯 Core 服务**（仅依赖端口），持久化在 backend。

### 决策 C：新大型依赖（§11.4 红线 —— 逐项待用户批准，现在不加）

| 用途 | 候选 | 说明 / 权衡 |
|---|---|---|
| Markdown 编辑器 | CodeMirror 6 / Monaco / 轻量 textarea+工具栏 | CodeMirror 6 体积适中、可扩展；Monaco 偏重 |
| Markdown 渲染 | marked / remark+rehype（+ DOMPurify 消毒） | 需 XSS 消毒；安全 §13 |
| 数学公式 | KaTeX | 仅在需要公式时引入 |
| 全局力导向图 | d3-force / cytoscape / sigma.js | 现 elkjs 是分层布局，非力导向；全局图需新引擎或自研 |
| MCP Server | 官方 MCP SDK | 新服务依赖 |
| 浏览器扩展 | MV3（平台原生，无重型框架） | 独立代码库；最小权限 |
| PDF/HTML 解析 | pypdf / selectolax 等 | Import 子系统按需 |

> 以上**全部标记「待批准」**。未获批准前不得 `npm install` / 加 `pyproject` 依赖。每项批准须记录到 MILESTONES/验收。

### 决策 D：Core 独立性守护（验收 #12，Nesti 复用）

- 所有新增 Core 模块（markdown 序列化、链接解析、分类/重要性/冲突、Pipeline 编排、图探索）必须**纯 Python + Pydantic + httpx**，经端口注入持久化/模型，不得 import FastAPI/SQLAlchemy/前端。
- 每批改动后 `knowledge-core/tests/test_interfaces.py::test_core_has_no_web_framework_dependency` 必须通过，且守护范围扩展到新增模块；不得删除/弱化。
- 文件系统 vault、MCP 传输、扩展通信等 I/O 细节放 backend/独立适配层，不进 Core。

### 决策 E：双方言与迁移护栏

- 新增 schema 走 Alembic `0006+`，必须可 upgrade/downgrade，同时支持 SQLite 与 PG；UUID `String(36)`、时间 UTC、JSON 负载以 Text 存。
- 方言差异（全文/向量/类型）继续封装在 `app/db/`、`app/services/retrieval.py`；业务服务与 Core 不出现方言 SQL；PG 路径不得用 FTS5/MATCH/bm25/rowid。
- 涉及 DB 的功能用真实数据库测试（SQLite 必测；PG 连真实实例，门控 `EXPLAINLAB_PG_TEST_URL`）。不得离线 SQL 冒充真实验证、不得虚报 PG 成功。

### 主要风险

1. **范围过大**：V2 ≈ 多个里程碑；一次性铺开必然牺牲稳定性。→ 严格拆批、每批真实验收。
2. **存储模型改动牵一发动全身**：Markdown/标签/链接影响检索、版本、图谱、审核。→ 路线 1 增量扩展，先做无损往返回归。
3. **新依赖红线**：编辑器/图库/MCP SDK 均属大型依赖。→ 先批准清单，再动手。
4. **外部采集合规**：扩展须遵循平台 ToS、用户主动触发、最小权限、不隐蔽抓取（§8.1/§13/§14）。→ 不承诺访问所有私有会话。
5. **AI 置信度 ≠ 真实性**：自动保存策略须保留来源 + 验证状态，重要变更/冲突进审核（§9）。→ 复用审核门禁，不自动覆盖。
6. **审计门禁**：未批准不得进入开发。→ 批次 0 把关。

---

## 3. 里程碑拆解（建议批次，优先 Markdown 知识库）

> 命名为「V2 批次 A–F」（建议里程碑 V2-M1…），与旧 M0–M5 区分。**实际编号与启动须经用户 + 独立审计批准，并届时更新 MILESTONES；本文件不宣布进入。** 每批遵循：计划确认 → 开发 → 真实运行 → 验收报告 + MILESTONES + 提交。

### 批次 0 · 前置（非开发，门禁）

- 完成当前回填修复独立复审；本规划经用户确认；产出「依赖批准清单」逐项获批；用户明确批准启动 V2。
- 产出：确认记录 + 依赖批准清单 + 起始批次范围。**不写代码。**

### 批次 A · 开放 Markdown 知识库底座（优先，建议拆 A1/A2）

**目标**：把知识正文升级为开放 Markdown 笔记，可编辑、可无损导入导出、双向链接/反链正确、稳定 ID、来源/标签元数据保留。覆盖 PRD §6.1/§6.3 核心与验收 #2/#3。

- **A1（Core + backend 存储/交换）**
  - 实体扩展：`KnowledgeItem` 增 `tags`、（可选）分类/验证状态；新增链接/反链领域逻辑（纯 Core）。
  - 新增纯 Core `MarkdownCodec`（entity ↔ frontmatter+正文，无损）+ 链接解析/反链服务（仅依赖端口）。
  - 新增端口：vault 导入导出（Core 定义 Protocol，backend 文件系统适配）。
  - 迁移 `0006`：tags（表或 Text JSON）、links（表或复用关系）、attachments、source_ref/conversation/message 来源字段扩展（与批次 D 协调，避免重复迁移）。
  - backend 服务 + API：Markdown 导入/导出/批量导出/附件导出、链接/反链查询、标签。
  - **真实验收**：导出→导入 round-trip 无损（id/tags/links/来源元数据一致）；批量导出含附件；稳定 ID 不变；双方言迁移 up/down；Core 独立性守护通过；真实 DB 测试（SQLite + 真实 PG）。
- **A2（frontend 编辑体验）**
  - Markdown 编辑器 + 实时预览（依赖待批准）、双向链接自动补全、反链面板、标签编辑、导入/导出 UI、frontmatter 展示。
  - **真实验收**：浏览器实测编辑/预览/链接跳转/反链正确/导入导出可用；页面无内容溢出（验收 #1）；Vitest + typecheck + build 通过；懒加载不退化。
- **复用**：现有持久化/检索/版本/审核/来源；`KnowledgeView`/`KnowledgeDetail` 渐进改造。
- **待批准依赖**：Markdown 编辑器、渲染（+消毒）、（可选）KaTeX。
- **护栏**：Core 纯净化；方言 SQL 仅在适配层；不牺牲稳定性；密钥仅后端。

### 批次 B · 知识组织与导航重构

**目标**：V2 信息架构（§3）+ 知识组织（§6.2）。Overview/Conversations/Knowledge/Graph/Search/Inbox/Settings 七导航；实验降级为「知识探索」扩展模块。

- 新增 Overview（日常入口：最近采集/新增知识/待审核/最近空间/增长统计/最近关联/快速搜索/快速采集），Inbox 骨架，完整 Settings（模型/渠道/存储/系统）。
- 标签管理、文件夹管理、搜索过滤、知识移动/合并/归档（合并/归档复用 M2 闭环）。
- **真实验收**：导航可达、各视图真实 API 数据、无溢出、实验作为扩展模块可用；前端测试 + 构建。
- **复用**：M2 合并/归档/审核；现七页签组件迁移重组。

### 批次 C · 图谱升级与智能探索

**目标**：PRD §7（全局/局部/智能探索/节点详情），验收 #4。

- 全局力导向图（拖动/缩放/搜索/高亮/颜色分类/标签·空间·关系类型过滤/孤立节点/数量控制/全屏）——图库依赖待批准。
- 局部图（围绕当前节点，一级/多级、方向、深度、数量限制、双向链接展示）——扩展 `KnowledgeGraphService`（纯 Core，深度受限遍历）。
- 智能探索：相关推荐/潜在关联/冲突提示/未关联发现/主题聚类/跨空间建议；**AI 推测与已确认关系视觉区分**（复用 `RelationOrigin`）。
- 节点详情面板（标题/正文/标签/空间/来源/关联/历史版本/编辑入口/审核状态）。
- **真实验收**：全局/局部图真实交互（浏览器实测）；过滤/深度/数量正确；AI vs 确认区分可见；推荐/冲突基于真实数据；Core 独立性。
- **待批准依赖**：力导向图库（d3-force/cytoscape/sigma）。

### 批次 D · 来源/版本增强 + 自动知识 Pipeline + Inbox

**目标**：PRD §9/§10/§12，验收 #9/#10/#11。

- 来源扩展：平台/会话/消息/采集时间/提取模型/提取时间/验证状态（`SourceRef` + `Conversation`/`Message` schema）。
- 版本：diff 查看、恢复（已有）、人工合并 UI。
- Pipeline 12 段统一编排：接收→解析→重要性→提取→实体→查重→关系→冲突→保存策略→版本→图谱→索引。复用提取/去重/关系/版本/审核/索引；新增重要性/实体/分类（9 类）/冲突检测/保存策略。
- 保存策略：低风险自动保存；重要修改/覆盖/删除/明显冲突进审核队列（复用 `ReviewService`）。置信度 ≠ 真实性，保留来源 + 验证状态。
- Inbox：新采集/待提取/待审核/重复/冲突/关联建议/失败任务/异常统一展示 + 批量审核处理。
- **真实验收**：真实模型端到端 Pipeline（提取保留来源）；重复/冲突识别真实命中；版本可追溯/diff/restore；重要变更进审核、批准应用/驳回无副作用；批量审核；真实 DB + 模型联调。
- **护栏**：模型失败不丢原始采集内容（§13）；不向外部模型发送未授权知识。

### 批次 E · 外部采集系统（建议拆 E1/E2/E3）

**目标**：PRD §8，验收 #5/#6/#7/#8。全新子系统，工作量最大。

- **E1 Import + Clipboard**：Import（MD/JSON/TXT/HTML/PDF/ChatGPT 导出/适配格式），批量导入/格式校验/重复检测/导入报告；Clipboard 用户主动快捷键采集（复制→快捷键→接收→预览→选空间→保存/提取），**不持续监控剪贴板**。
- **E2 MCP Server**：ExplainLab MCP 服务，6 工具（save_conversation/save_knowledge/search_knowledge/get_knowledge/get_related_knowledge/list_knowledge_spaces），供支持 MCP 的客户端主动调用；空间权限边界；MCP SDK 依赖待批准。
- **E3 Browser Extension**：MV3 扩展，首批 ChatGPT/Claude/Gemini；保存当前回答/选定消息/完整对话、选空间、查看采集结果、手动触发提取；最小权限、用户主动触发、遵循平台 ToS、不隐蔽后台抓取、不承诺访问所有私有会话；backend 采集 API + 授权令牌。
- **真实验收**：对话文件批量导入真实成功 + 报告；剪贴板快捷采集真实可用；MCP 客户端真实保存/检索；扩展在真实平台页面用户触发采集成功（浏览器实测）；原始对话保留、提取不覆盖原始。
- **待批准依赖**：MCP SDK、PDF/HTML 解析库、扩展平台工具链。

### 批次 F · 检索增强 + 安全/隐私收尾 + 全量验收

**目标**：PRD §11/§13 + §15 全量 12 条验收。

- 检索增强：全文/语义/标签/空间/来源/关系扩展/排序/来源追溯；默认遵守当前空间权限，跨空间搜索符合授权策略。
- 安全：API Key 仅后端；扩展最小权限；采集用户触发；删除原始对话+关联知识；数据导出；空间隔离；重要操作审计日志；不向外部模型发送未授权知识；模型失败不丢原始内容。
- **真实验收**：PRD §15 全 12 条逐条真实测试通过（见 §4 映射），不允许静态演示页冒充；全量 backend+core+frontend+ruff+build；干净副本从零锁定安装验证；真实 PG 验证。

---

## 4. PRD §15 验收目标 → 批次映射（全部须真实测试）

| # | 验收目标 | 主责批次 | 真实验证方式 |
|---|---|---|---|
| 1 | 页面不发生内容溢出 | A2/B/C/F | 浏览器多视口实测 |
| 2 | Markdown 笔记可编辑和导出 | A1/A2 | round-trip + 浏览器编辑/导出 |
| 3 | 双向链接和反向引用正确 | A1/A2 | 链接解析/反链真实断言 + UI 跳转 |
| 4 | 全局和局部图谱可以交互 | C | 浏览器真实交互 |
| 5 | 浏览器采集可正常使用 | E3 | 真实平台页面用户触发采集 |
| 6 | MCP 客户端能保存和检索知识 | E2 | 真实 MCP 客户端调用 |
| 7 | 对话文件能够批量导入 | E1 | 真实文件批量导入 + 报告 |
| 8 | 剪贴板快捷采集可用 | E1 | 真实快捷键流程 |
| 9 | 自动知识提取保留来源 | D | 真实模型端到端 + 来源断言 |
| 10 | 重复与冲突能够识别 | D | 真实数据查重/冲突命中 |
| 11 | 知识版本可以追溯 | D | 真实版本 diff/restore |
| 12 | Knowledge Core 仍可独立被 Nesti 调用 | 每批 | 独立性守护测试 + 纯端口复用 |

---

## 5. 红线与护栏清单（每批必须遵守，源自 AGENTS.md）

1. 未经独立审计批准 + 用户确认，不进入 V2 任何开发批次；不自行宣布进入下一里程碑。
2. 不重写 Knowledge Core；Core 不耦合 UI/DB/Web；新模块过独立性守护测试，不删除/弱化它。
3. 业务逻辑与 Core 不写方言 SQL；方言差异封装在 backend 适配层；PG 不用 FTS5/MATCH/bm25/rowid。
4. 不擅自增加大型技术依赖；§2 决策 C 清单逐项获用户批准后方可引入。
5. 不用假数据替代真实数据库/模型测试；不虚报 PG 成功；不把离线 SQL 当真实验证。
6. 不删除已有有效测试；不为凑通过弱化断言；不修改 M0 初始提交；不重写已推送历史。
7. API Key 仅存 backend `.env`（SecretStr），绝不暴露给聊天/前端/日志；模型直连真实 base_url，严禁代理替换。
8. 采集用户主动触发、最小权限、遵循平台 ToS；不隐蔽抓取；模型失败不丢原始内容；不发送未授权知识给外部模型。
9. 每批：真实运行 → 验收报告（docs/acceptance/）+ 更新 MILESTONES + 提交（经用户授权）；如实区分已验证/有条件/未通过。
10. 锁定安装（uv sync --locked / npm ci）+ 干净副本从零验证；ruff 仅 check（禁 format）；根级 pytest 保留 importlib。

---

## 6. 待用户 / 独立复审决策点（开放问题）

1. **Markdown 存储路线**：路线 1（DB 权威 + 无损 Markdown 往返，推荐）还是路线 2（文件 vault 权威）？
2. **双向链接语法/落库**：`[[标题]]`→稳定 ID 锚定是否认可？链接用独立 `knowledge_link` 表还是复用 `KnowledgeRelation`？
3. **依赖批准清单**（§2 决策 C）：Markdown 编辑器/渲染、KaTeX、力导向图库、MCP SDK、PDF/HTML 解析、扩展工具链——逐项批准或指定替代。
4. **批次顺序与起始范围**：是否按 A→B→C→D→E→F？A 是否拆 A1/A2 先行？首批是否只做 A1（存储/交换底座）？
5. **门禁解除**：当前回填修复复审通过后，是否明确批准启动 V2 批次 A？
6. **扩展平台优先级**：ChatGPT/Claude/Gemini 首批顺序与授权方式。
7. **MCP 授权/空间边界**：令牌模型与跨空间访问策略。
8. **分类/验证状态字段**：9 类分类与验证状态是否纳入实体（影响迁移与检索口径）。

> 以上决策确定前，本规划停留在「待确认」，不进入开发。

---

## 7. 估算与声明

- 本文件中的批次划分、依赖候选、工作量判断均为**规划估算与建议**，不是承诺工期，也不是已完成成果。
- 「现状盘点」（§1）基于真实代码与文件证据（已验证）；「V2 新增/重做」与「批次范围」为**规划提议**（未实现）。
- 本轮**未写任何 V2 实现代码、未改 Core/无关模块、未新增依赖、未执行迁移、未提交**。
- 下一步：等待用户对 §6 决策点拍板 + 当前回填修复独立复审结论；获批后再按批次 0→A 启动，并届时更新 MILESTONES 与验收报告。