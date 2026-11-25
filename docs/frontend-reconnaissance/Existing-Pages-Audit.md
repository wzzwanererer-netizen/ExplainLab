# ExplainLab V2 · Existing Pages Audit

**状态**：`RECONNAISSANCE COMPLETED / WAITING FOR DESIGN FREEZE`  
**核验方式**：全量静态代码审查 + 本地真实前后端启动 + 真实浏览器 `1280×800` 逐页实测（零控制台错误、零网络错误）。

## 总览矩阵

| # | 页签 | 组件 | Mock 数据 | 可访问性 | 浏览器截图 |
| --- | --- | --- | --- | --- | --- |
| 1 | 对话 | `ChatView.tsx` | 无（全真实 API） | 可访问（默认页） | [01-chat.png](Screenshots/01-chat.png) |
| 2 | 知识库 | `KnowledgeView.tsx` + `KnowledgeDetail.tsx` | 无 | 可访问 | [02-knowledge.png](Screenshots/02-knowledge.png) |
| 3 | 检索 | `SearchView.tsx` + `KnowledgeDetail.tsx` | 无 | 可访问 | [03-search.png](Screenshots/03-search.png) |
| 4 | 地图 | `KnowledgeMap.tsx` + `KnowledgeDetail.tsx` | 无 | 可访问（懒加载） | [04-map.png](Screenshots/04-map.png) |
| 5 | 实验 | `ExperimentsView.tsx` + `experiments/*` + `KnowledgeDetail.tsx` | 无 | 可访问（懒加载） | [05-experiments.png](Screenshots/05-experiments.png) |
| 6 | 审核 | `ReviewQueue.tsx` | 无 | 可访问 | [06-reviews.png](Screenshots/06-reviews.png) |
| 7 | 系统状态 | `HealthPanel.tsx` | 无 | 可访问 | [07-status.png](Screenshots/07-status.png) |

---

## 逐页详细审计

### 1. 对话（`ChatView.tsx`）
- **当前功能与已实现交互**：左侧新建会话（标题 + 所属空间选择）、会话列表切换与删除（无二次确认）；右侧消息流展示、发送消息（真实模型回复）、一键「提取知识」并给出数量提示。
- **使用 API**：`listSpaces`, `listConversations`, `createConversation`, `getConversation`, `deleteConversation`, `chat`, `extractKnowledge`。
- **尚未实现功能**：不支持按空间筛选会话列表（后端 `GET /api/conversations?space_id=` 已支持，前端未传）；不支持 Markdown 渲染（仅 `whitespace-pre-wrap` 纯文本）；不支持流式输出；不支持回车快捷键发送；提取后的知识无法直接点击跳转详情。
- **已知 UI 问题**：删除会话按钮 `×` 无确认弹窗；切换页签后当前会话与草稿丢失。

### 2. 知识库（`KnowledgeView.tsx` + `KnowledgeDetail.tsx`）
- **当前功能与已实现交互**：顶部空间下拉切换与新建项目空间；左侧新建/编辑知识表单（标题、正文、编辑时可改状态）；右侧知识卡片列表（正文、来源摘要、编辑、删除含 `window.confirm`、展开 `KnowledgeDetail` 执行查重分析/合并提交审核/删除关系/查看与回滚版本）。
- **使用 API**：`listSpaces`, `createSpace`, `listKnowledge`, `createKnowledge`, `updateKnowledge`, `deleteKnowledge`；以及 `KnowledgeDetail` 内的 `listRelations`, `listVersions`, `analyzeKnowledge`, `submitReview`, `restoreVersion`, `deleteRelation`。
- **尚未实现功能**：
  - **V2 附件完全未接入**（上传、列表、下载、删除均缺失）。
  - **V2 Markdown 导入 / 批量导入 / ZIP 导入 / 单篇导出 / 批量导出完全未接入**。
  - **V2 双链（`[[wikilink]]` 出链、反链、候选解析）完全未接入**。
  - **标签（tags）** 与 `createRelation`（手动新建关系）、`attachSource`（手动挂接来源）均无 UI 入口（即使 `client.ts` 已封装了 `createRelation` / `attachSource`）。
  - 编辑条目时无法切换所属空间（`space_id`）；正文不支持 Markdown 富文本/预览。
- **已知 UI 问题**：使用浏览器原生 `window.confirm`；治理详情内嵌展开在条目较长时层级较深；关系仅显示目标 UUID 前 8 位而非标题。

### 3. 检索（`SearchView.tsx`）
- **当前功能与已实现交互**：关键词输入框、空间筛选、模式选择（混合/仅全文/仅向量）、执行检索、重建索引（`reindex`）；结果卡片展示融合分与通道分、向量能力如实提示、展开 `KnowledgeDetail`。
- **使用 API**：`listSpaces`, `search`, `reindex`, `getKnowledge`（+ `KnowledgeDetail` APIs）。
- **尚未实现功能**：结果 `limit` 未暴露；不支持高亮命中词；无检索历史。
- **已知 UI 问题**：`KnowledgeDetail` 在此页展开时无「编辑」入口（仅治理操作）。

### 4. 地图（`KnowledgeMap.tsx`）
- **当前功能与已实现交互**：空间筛选、「显示归档」开关、刷新按钮、节点/边计数、5 类关系颜色图例；React Flow + ELK 分层自动布局画布（缩放、拖拽、点击节点打开右侧 `KnowledgeDetail` 抽屉）。
- **使用 API**：`listSpaces`, `getGraph`, `getKnowledge`（+ `KnowledgeDetail` APIs）。
- **尚未实现功能**：不展示 V2 `knowledge_link` 双链边（当前后端 `/api/graph` 仅基于 M2 `knowledge_relation`）；图例交互过滤与节点搜索缺失。
- **已知 UI 问题（浏览器实测确认）**：
  - 图例中 `重复（虚线）` 色块使用了实心 `backgroundColor` 而非虚线边框，与文字描述不一致。
  - `显示归档` 使用浏览器原生 checkbox，在暗色工具栏中呈高亮白底，对比突兀。
  - 画布高度固定 `h-[480px]`，在宽屏桌面下未自适应视口高度。

### 5. 实验（`ExperimentsView.tsx` + `experiments/*`）
- **当前功能与已实现交互**：三模式卡片（测验/对比/学习路径，含琥珀/天蓝/翡翠三强调色）、空间筛选与多选知识列表、题数/步数滑块与步进按钮、三类 Runner（逐题判分+得分环+回顾、双栏对比+关系判定、先修步进器）、历史实验列表（打开/删除）、右侧 `KnowledgeDetail` 滑出抽屉。
- **使用 API**：`listSpaces`, `listKnowledge`, `listExperiments`, `createExperiment`, `answerExperiment`, `completeExperiment`, `deleteExperiment`, `getKnowledge`（+ `KnowledgeDetail` APIs）。
- **尚未实现功能**：历史列表未按空间或模式筛选（后端 `GET /api/experiments/sessions?kind=&space_id=` 已支持）；`getExperiment` 已封装但未在 UI 中调用（直接复用列表对象）。
- **已知 UI 问题（浏览器实测确认）**：在 `1280×800` 下「历史实验」区域落在首屏折线下方；重新打开已完成测验时仅展示题目与答案回顾，不显示历史作答得分（`reviewOnly` 分支注释已明示）。

### 6. 审核（`ReviewQueue.tsx`）
- **当前功能与已实现交互**：按状态筛选（待审核/已批准/已驳回/全部）；卡片展示动作类型、条目 UUID 前 8 位、变更摘要、理由/备注、批准与驳回按钮。
- **使用 API**：`listReviews`, `approveReview`, `rejectReview`。
- **尚未实现功能**：
  - **V2 Active Import 审核增强缺失**：后端已支持含 `__a1_import` envelope 与附件 manifest 的 Active ZIP 导入审核单，但前端 `payloadSummary()` 仅解析 `title/content/status`，完全不展示待发布附件清单、标签变更、来源身份或 diff 对比。
  - 批准/驳回不支持填写 `resolution_note`（后端 `ReviewResolve.note` 已支持）。
  - 无法点击条目 ID 预览原知识内容。
- **已知 UI 问题（浏览器实测确认）**：内容区 `max-w-3xl` 左对齐，在 `1280px` 桌面端右侧留白过大。

### 7. 系统状态（`HealthPanel.tsx`）
- **当前功能与已实现交互**：展示 `/api/health` 真实返回（后端状态、数据库方言与连接、模型适配层、向量来源配置态、版本号、检查时间）与刷新按钮。
- **使用 API**：`getHealth`。
- **尚未实现功能**：未展示向量真实探测状态（`supported/unsupported` 仅在检索/重建索引时可见）；未展示后端附件存储/维护状态。
- **已知 UI 问题**：同审核页，`max-w-3xl` 左对齐。

---

## 跨页共性问题汇总

1. **重复工具函数与常量**：
   - `errorMessage(err)` 在 7 个组件文件中重复定义了 7 遍（`ChatView`, `KnowledgeView`, `KnowledgeDetail`, `SearchView`, `KnowledgeMap`, `ReviewQueue`, `ExperimentsView`, `QuizRunner`, `CompareRunner` 共 9 处！）。
   - `STATUS_LABEL` 在 `KnowledgeView.tsx`、`SearchView.tsx`、`lib/graphLayout.ts` 重复定义 3 次；`RELATION_LABEL` 在 `KnowledgeDetail.tsx` 与 `lib/graphLayout.ts` 重复定义 2 次；`SOURCE_LABEL` 在 `KnowledgeView.tsx` 与 `KnowledgeDetail.tsx` 重复定义 2 次。
   - 表单样式串 `inputClass` 与错误/成功 Banner JSX 在多个视图中重复拷贝。
2. **不存在 Mock 数据，也不存在无法访问的孤立页面**。
