# ExplainLab M4 验收报告 · 动态知识地图

- 里程碑：M4 · 动态知识地图
- 验收日期：2026-11-15
- 结论：**通过**，进入 M5（交互式知识实验）
- 证据底稿：[assets/m4-evidence.txt](assets/m4-evidence.txt)
- 截图：[assets/m4-map-default.png](assets/m4-map-default.png) / [assets/m4-map-archived.png](assets/m4-map-archived.png) / [assets/m4-map-detail.png](assets/m4-map-detail.png)

---

## 1. 概述

M4 在 M2 关系治理与 M3 检索之上补齐**可视化层**：把已有的 `knowledge_item` 与 `knowledge_relation`
装配为「节点 + 边」图结构，经只读 API 暴露，前端用 React Flow + ELK.js 自动布局渲染，
并与知识条目 / 关系保持实时联动。图是现有数据的**视图**，不新增表、不新增迁移。

核心能力落地：

- 跨空间 / 空间过滤的知识地图，归档可选显示；
- 关系边按类型着色 / 虚线 / 箭头，归档节点灰显，呈现 merge 的 `duplicate_of` 闭环；
- 点击节点打开治理详情（关系 / 版本 / 来源），地图与治理双向联动；
- 切页签 / 刷新 / 治理变更后重取，保证与数据库一致。

## 2. 范围与架构（遵守长期约束）

| 层 | 职责 | 关键文件 |
| --- | --- | --- |
| Knowledge Core | 纯数据装配图（节点 + 边），**无坐标、无模型调用、无网络、不绑定 Web/DB** | `knowledge-core/src/knowledge_core/graph/service.py` |
| Backend | 只读图 API + DTO + 仓库装配 | `backend/app/api/routes/graph.py`、`backend/app/services/graph.py`、`backend/app/api/schemas.py` |
| Frontend | ELK 布局（纯模块）+ React Flow 渲染 + 详情联动 | `frontend/src/lib/graphLayout.ts`、`frontend/src/components/KnowledgeMap.tsx` |

- Core 仅依赖 `KnowledgeRepository` / `RelationRepository` 端口，渲染器由应用层自带，**可复用于 Nesti**。
- 新增端口 `RelationRepository.list_all_relations()`；Core 独立性守护测试（`test_interfaces.py`）
  扩展到 `knowledge_core.graph` / `knowledge_core.graph.service`，子进程导入闭包验证通过。
- 布局与渲染完全在前端：`graphLayout.ts` 为**纯模块**（只 import ELK bundled + 类型，不 import React Flow
  运行时），可在 jsdom 单测；React Flow 节点 / 边转换在 `KnowledgeMap.tsx`。
- 无新增迁移；`alembic check` = No new upgrade operations detected。

## 3. Knowledge Core 图服务

`KnowledgeGraphService.build_graph(*, space_id=None, include_unassigned=False, include_archived=False)`：

- `space_id=None` 跨全部空间；限定个人空间时 `include_unassigned=True` 聚合 `space_id=None` 条目（与 M1/M3 语义一致）。
- `include_archived=False`（默认）排除归档节点，与检索口径一致。
- 边仅保留**两端都在节点集合**者（隐藏归档时丢弃悬空边）；跳过自环；按 `(source, target, type)` 去重。
- 输出 `KnowledgeGraph(nodes, edges)`，节点含 `id/title/status/space_id`，边含
  `id/source_id/target_id/relation_type/confidence/origin`，**不含坐标**。

单测 `knowledge-core/tests/test_graph.py` 8 例：空图 / 基本 / 归档排除+悬空丢弃 / include_archived /
空间过滤 / include_unassigned / 去重 / 跨空间全量。

## 4. Backend 图 API

`GET /api/graph?space_id=&include_archived=`：

- 给定 `space_id` 不存在 → 404（中文 detail）；个人空间 → `include_unassigned=True`。
- DTO `GraphOut/GraphNodeOut/GraphEdgeOut`（`from_attributes`）。
- 装配 `build_graph_service(session)` = Core 服务 + SQLAlchemy 仓库。

实测（真实数据，见证据底稿 §1–4）：

- 默认：**2 节点 / 0 边**（active 定义、draft 典型用途；两条关系都连归档节点，隐藏归档丢悬空边）。
- `include_archived=true`：**3 节点 / 2 边**（related 定义→概念 0.98 llm；duplicate_of 概念→定义 1.0 dedup）。
- 个人空间 + 归档：与上同（三条知识 `space_id=null` 被个人库聚合）。
- 未知空间：404 `知识空间不存在: does-not-exist`。

后端单测 `backend/tests/test_graph.py` 5 例：空 / 节点+边 / 归档排除+开关 / 空间过滤+个人 / 未知 404。

## 5. Frontend 地图

- `graphLayout.ts`（纯模块）：`RELATION_LABEL` / `STATUS_LABEL`、`NODE_WIDTH=220` / `NODE_HEIGHT=64`、
  `edgeVisual(type)`、`toMapElements(graph)`（边标签 = `${类型} ${round(confidence*100)}%`）、
  `layoutWithElk(graph)`（ELK layered DOWN，spacing 40/60，空图直接返回）。
- `KnowledgeMap.tsx`：自定义节点（标题 + 状态徽章，归档灰显虚线，含 `<Handle>` target=Top / source=Bottom）；
  工具条（空间筛选 / 显示归档 / 刷新 / 计数）；图例（相关·依赖·重复虚线·细化·矛盾）；
  React Flow 画布（fitView、minZoom 0.2、maxZoom 2）；点击节点→右侧治理详情。
- 边视觉语义实测（getComputedStyle）：
  - related：灰 `#94a3b8`、实线、无箭头；
  - duplicate_of：红 `#f87171`、虚线 `6px,3px`、红色 arrowclosed 箭头；
  - depends_on 蓝 / refines 绿 / contradicts 红（图例与 edgeVisual 一致）。
- 归档节点：opacity 0.5 + 虚线框。
- 响应式：列模式（窄视口）画布 `w-full + h-[480px]`，仅 `lg` 行模式 `lg:flex-1`，避免 flex-basis:0 塌缩。
- 暗色主题：`index.css` 覆盖 React Flow Controls / attribution 为 slate 暗色，全局暗色滚动条。

前端单测：`graphLayout.test.ts` 8 例 + `KnowledgeMap.test.tsx` 5 例（画布用确定性替身，真实画布以浏览器验收为准）
+ `client.test.ts` 增 getGraph 3 例。

## 6. 实时联动

- 切页签重挂载 → 重取；「刷新」按钮重取；空间 / 归档开关变化重取；治理变更 `onChanged` 重取。
- 实测：在「知识库」编辑草稿标题 → 直接应用（提示「已更新知识条目。」，非审核）→ 切回「地图」
  节点标签同步为新标题；验证后复原标题。证明地图与数据库实时一致。

## 7. 自动化验证（全量）

| 项 | 结果 |
| --- | --- |
| backend pytest | 79 passed |
| knowledge-core pytest | 83 passed（含独立性守护 + test_graph 8） |
| frontend vitest | 52 passed（8 文件） |
| ruff check backend knowledge-core | All checks passed |
| frontend tsc -b | 通过 |
| frontend vite build | 成功（单 chunk ~1910 kB，分包警告为已知项） |
| alembic check | No new upgrade operations detected |

Python 合计 162 通过；前端 52 通过。

## 8. 真实浏览器联调

内置浏览器（`http://[::1]:5173/`）实测，截图读回验证：

- 默认地图：2 节点 0 边、暗色 Controls、图例、计数「节点 2 · 边 0」。
- 含归档：3 节点 2 边、duplicate_of 红虚线箭头、归档灰显虚线、计数「节点 3 · 边 2」、fitView 自动缩放。
- 节点详情：点击「定义」→ 关系（2）/ 版本（2）/ 来源（3，对话+手动+文档），来源追溯完整。
- 联动：改标题→地图同步（见 §6）。

## 9. 联调发现并修复的真实缺陷（均复验）

1. **自定义节点缺 `<Handle>`**：React Flow 自定义节点必须显式提供连接点，否则边无法连接。
   补 target=Top / source=Bottom（契合 ELK 自上而下），边渲染恢复。
2. **窄视口画布塌缩**：外层 `flex-col` 时画布 `flex-1`(flex-basis:0) 覆盖 `h-[480px]` 致高度 0。
   改为列模式固定高+满宽、仅 `lg` 行模式 `flex-1`；窄视口画布恢复 461×479。
3. **默认白色控件与暗色冲突**：React Flow 默认 Controls 白块 / attribution 灰块。
   `index.css` 暗色覆盖 + 全局暗色滚动条。

修复后复跑 typecheck / 52 测试 / build 全过，浏览器复验边渲染与三张截图干净。

## 10. 已知限制与后续

- 单 chunk ~1910 kB（React Flow + ELK）：分包 / 懒加载留待后续优化，非功能缺陷。
- 互为反向的两条边（定义↔概念）在顶/底 handle 下路径部分重叠：可读（标签区分），
  后续可为反向边改用侧向 handle 提升美观，非阻塞。
- 组件单测中画布用确定性替身；真实画布渲染以浏览器验收为准（本报告 §8）。
- M4 不新增迁移；图仅为现有数据视图。

## 11. 结论

M4 全部验收标准通过：Core 图装配独立可复用、只读图 API 口径正确、前端地图真实渲染且视觉语义准确、
详情与实时联动可用、全量测试 / lint / 构建 / 无漂移通过、真实浏览器联调与截图齐备、联调缺陷已修复复验。
**M4 验收通过，进入 M5（交互式知识实验）。**