# M4 实施计划 · 动态知识地图（细化稿，待确认）

- 日期：2026-11-14
- 状态：**待用户「确认 开始T1」**。确认后按「计划确认 → 开发 → 实跑 → 验收报告 + MILESTONES + 提交」执行。
- 上游：M0 ✅、M1 ✅（`a2a8e01`）、M2 ✅（`4dcf61b`）、M3 ✅（`872db27`）。
- 定位：M4 = **可视化层**。把 M2 治理产出的「知识条目 + 关系」渲染为可交互知识地图（React Flow + ELK.js），并与条目/关系实时联动。不新增业务治理逻辑。

## 0. 范围边界（做什么 / 不做什么）

做：Core 图数据装配服务（节点+边，经端口）、`GET /api/graph` 检索式图 API、前端「地图」页签（React Flow 渲染 + ELK 自动布局 + 节点点击治理详情 + 归档开关 + 刷新/联动）、全量测试与真实浏览器联调。

不做（严禁提前）：
- M5 交互式知识实验。
- 不新增数据库表 / 迁移（图是现有 `knowledge_item` + `knowledge_relation` 的视图，无 schema 变更）。
- 不铺全量页面；前端只加一个「地图」页签。
- 不做 WebSocket 推送 / 大规模图虚拟化 / 图编辑拖拽建关系（V1 只读地图 + 点击详情）。

## 1. 架构对齐

- **图数据装配落在 Knowledge Core**（新模块 `knowledge_core/graph/`，仅 Pydantic + 纯 Python），经端口读条目与关系，不依赖前端 / Web 框架 / ORM（独立性闭包测试继续守护并扩展到 M4）。
- **布局落在前端**：ELK.js 是 JS 库，属渲染层职责；Core 只产出「节点+边」结构化数据，不含坐标。符合「Core 独立、可复用于 Nesti」（Nesti 可自带渲染器）。
- 复用现有端口：`KnowledgeRepository.list(space_id, include_unassigned)`；**新增** `RelationRepository.list_all_relations() -> list[KnowledgeRelation]`（现有端口只有按条目 `list_relations(item_id)`，无法一次取全图边）。同步更新 SQLAlchemy 实现与测试 InMemory 件。
- 关系类型沿用 M2 `RelationType`：`related / depends_on / duplicate_of / refines / contradicts`；origin：`manual / llm / dedup`。不自环（领域已校验）、三元组唯一（DB UNIQUE）。

## 2. Core 图服务（`knowledge_core/graph/`）

- 纯 Pydantic 视图模型：`GraphNode(id, title, status, space_id)`、`GraphEdge(id, source_id, target_id, relation_type, confidence, origin)`、`KnowledgeGraph(nodes, edges)`。
- `KnowledgeGraphService(knowledge_repo, relation_repo).build_graph(*, space_id=None, include_unassigned=False, include_archived=False) -> KnowledgeGraph`：
  1. `nodes = knowledge_repo.list(space_id=..., include_unassigned=...)`；默认过滤 `status=archived`（与 M3 检索口径一致）。
  2. `edges = relation_repo.list_all_relations()`，仅保留**两端都在 node 集合**的边（隐藏归档时自动丢弃指向归档的边，避免悬空）。
  3. `include_archived=True` 时保留归档节点（前端灰显）与相应边（可看到 merge 的 `duplicate_of` 闭环）。
  4. 边按 `(source, target, relation_type)` 去重兜底；跳过自环（领域已禁止）。
- 空间语义沿用 M1/M3：`space_id=None` 跨全部空间；个人总知识库聚合 `space_id=None` 条目（`include_unassigned`）。
- 无模型调用、无网络：图是纯数据装配，可单测（InMemory 双件）。

## 3. Backend API

新增（`app/api/routes/graph.py`，tags=graph）：

- `GET /api/graph?space_id=&include_archived=`：返回 `GraphOut{nodes[], edges[]}`；未知 space 404（复用 `get_space`）；`include_archived` 默认 false。装配 `build_graph_service(session)`（与 M2/M3 服务装配同风格）。
- DTO（`schemas.py`）：`GraphNodeOut(id,title,status,space_id)`、`GraphEdgeOut(id,source_id,target_id,relation_type,confidence,origin)`、`GraphOut(nodes,edges)`，`from_attributes`。
- **无迁移**：`alembic check` 保持无漂移（head 仍 `0004_m3_retrieval`）。
- SQLAlchemy `RelationRepository` 增加 `list_all_relations()`（全表 select，转领域模型）。

## 4. Frontend「地图」页签

依赖已就绪（M0 安装）：`@xyflow/react ^12`、`elkjs ^0.12`。不新增依赖。

- `api/types.ts` + `api/client.ts`：`GraphNode/GraphEdge/GraphResponse`、`getGraph({space_id, include_archived})`。
- `lib/graphLayout.ts`（**纯函数，可单测**）：
  - `toFlowElements(graph)`：把 Core 图映射为 React Flow `nodes/edges`——节点 custom type `knowledge`（标题+状态徽章），边 label=关系中文标签+置信度、按类型着色/线型（`duplicate_of` 红虚线、`contradicts` 红、`depends_on`/`refines` 带箭头、`related` 灰）。
  - `layoutWithElk(graph)`：`import ELK from "elkjs/lib/elk.bundled.js"`（bundled 免 Web Worker 配置），algorithm=`layered`、direction=`DOWN`、节点间距/边间距常量；异步返回坐标后合并进 nodes。空图/单节点直接返回不布局。
- `components/KnowledgeMap.tsx`：
  - 工具条：空间筛选（全部/个人/项目，沿用检索页语义）+「显示归档」checkbox +「刷新」按钮 + 图例（状态/关系类型）。
  - `<ReactFlow nodes edges nodeTypes fitView>` + `Controls` + `Background`（`MiniMap` 可选）；引入 `@xyflow/react/dist/style.css`。
  - **节点点击 → 侧栏治理详情**：复用 M2 `KnowledgeDetail`（关系/版本/来源/查重/回滚）；`onChanged` 回调 → 重新 `getGraph`（实时联动）。
  - 空图/加载/错误如实提示（无假数据）；归档节点灰显+「归档」徽章。
  - **实时联动**：页签切换即重挂载重 fetch；「刷新」手动重 fetch；详情内任何治理变更（改标题/合并/回滚等）经 `onChanged` 重 fetch。不引入 WebSocket（V1 足够）。
- `App.tsx`：Tab 增加 `map`（label「地图」），badge 改「M4 · 知识地图」；条件渲染 `<KnowledgeMap />`。

## 5. 测试与验证

- Core：`build_graph` 空间过滤 / include_unassigned / 默认排除 archived / include_archived 保留 / 边两端过滤（悬空边丢弃）/ 去重 / 空图；独立性闭包扩展到 `graph/`。
- Backend：`list_all_relations` 实现；`GET /api/graph` 三态（全部/限定 space/未知 404）+ include_archived 开关 + 边集合正确；无漂移。
- Frontend：`graphLayout` 纯函数（映射/标签/线型/归档灰显/空图）；`KnowledgeMap` 组件（mock `getGraph`，断言节点标题/边数/空态/归档开关/点击详情）；client `getGraph`。
  - **jsdom 适配**：在现有 `frontend/src/test/setup.ts` 补 `ResizeObserver`（及必要时 `DOMMatrixReadOnly`）polyfill，供 React Flow 渲染。若 React Flow 在 jsdom 仍不稳定，退而重点测纯 `graphLayout` + 自定义节点组件，画布集成以真实浏览器验收为准（如实记录，不造假）。
- 全量：pytest + ruff + vitest + build + alembic 无漂移 + Core 独立性。

## 6. 真实联调（无需模型）

图是纯数据视图，联调不调用聊天/embed。用现有开发库真实数据：3 条知识（定义 active / 用途 draft / 概念 archived）+ 2 条关系（`related` origin=llm、`duplicate_of` origin=dedup）。

- 默认（隐藏归档）：地图 2 节点 + 1 边（related）。
- 开「显示归档」：3 节点 + 2 边，`duplicate_of` 红虚线可见 → 直观呈现 M2 合并闭环。
- 点击节点 → 侧栏治理详情（关系/版本/来源）真实渲染。
- 实时联动：在详情里改 draft 标题（draft 直连无需审核）→ 地图节点标题即时更新；「刷新」/切页签重 fetch 一致。
- 留存干净 UTF-8 证据（`GET /api/graph` 两态 JSON）+ 浏览器截图（默认态 / 归档态 / 详情侧栏）。

## 7. 任务拆分与依赖

| # | 任务 | 依赖 |
|---|---|---|
| T1 | Core graph 视图模型 + `list_all_relations` 端口 + KnowledgeGraphService + 独立性守护 | — |
| T2 | Backend SQLAlchemy `list_all_relations` + graph 路由 + DTO + 装配 + API 测试 | T1 |
| T3 | Frontend types/client `getGraph` + `graphLayout` 纯模块 + 单测 | T2 |
| T4 | Frontend KnowledgeMap（React Flow + ELK + 详情联动 + 归档开关）+ App 页签 | T3 |
| T5 | Frontend 组件/布局/client 测试 + setup polyfill | T4 |
| T6 | 全量测试 + lint + 构建 + 无漂移 + 独立性 | T5 |
| T7 | 真实浏览器联调 + 截图 + UTF-8 证据 | T6 |
| T8 | 验收报告 + MILESTONES M4✅ + Git 提交 | T7 |

## 8. 风险与决策

1. **React Flow × jsdom**：需 ResizeObserver polyfill；若仍不稳定按 §5 退化策略，画布以浏览器验收为准。
2. **ELK 导入**：用 `elkjs/lib/elk.bundled.js` 免 Worker；构建期验证 Vite 打包与类型（elkjs 自带 d.ts）。
3. **悬空边**：隐藏归档时丢弃指向归档的边（Core 保证），前端不出现无端点边。
4. **图规模**：开发期个位数节点，ELK layered 足够；大规模虚拟化/分页留待后续，不提前做。
5. **端口变更面**：新增 `list_all_relations` 需同步 SQLAlchemy 实现 + 测试 InMemory 件，避免 Protocol 缺方法。
6. 不新增迁移、不新增依赖、不提前做 M5。

## 9. 验收标准（M4 完成定义）

- [ ] Core 图服务独立（仅端口），独立性闭包守护扩展到 M4；`build_graph` 空间/归档/边过滤正确。
- [ ] `GET /api/graph` 真实可用：space 过滤、include_archived 开关、未知 space 404、边仅含现存端点。
- [ ] 前端「地图」页签真实渲染节点+边（ELK 布局）、状态徽章/关系图例、节点点击治理详情、归档开关、刷新。
- [ ] 实时联动：切页签/刷新/治理变更后地图与 DB 一致；归档态可见 merge 的 duplicate_of 闭环。
- [ ] 全量测试 + ruff + 构建 + 无漂移（无新迁移）+ Core 独立性通过。
- [ ] 真实浏览器联调证据 + 截图；验收报告；MILESTONES M4 ✅；Git 提交。

---

回复「确认 开始T1」后，我按 T1→T8 开始开发（本阶段无需你提供密钥或安装依赖）。