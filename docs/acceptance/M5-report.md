# ExplainLab M5 验收报告 · 交互式知识实验

- 里程碑：M5 · 交互式知识实验
- 验收日期：2026-11-15
- 结论：**通过**，V1.0 七大核心能力全部落地
- 证据底稿：[assets/m5-evidence.txt](assets/m5-evidence.txt)
- 截图：[assets/m5-experiments-home.png](assets/m5-experiments-home.png) / [assets/m5-quiz-active.png](assets/m5-quiz-active.png) / [assets/m5-quiz-score.png](assets/m5-quiz-score.png) / [assets/m5-compare.png](assets/m5-compare.png) / [assets/m5-chain.png](assets/m5-chain.png) / [assets/m5-detail-drawer.png](assets/m5-detail-drawer.png)

---

## 1. 概述

M5 在 M1 提取 / M2 治理 / M3 检索 / M4 地图之上补齐**主动学习层**：围绕已有知识库提供三种
交互式实验——**知识测验**（出题检验理解）、**知识对比**（辨析异同关系）、**学习路径**（先修优先编排）。
测验与对比由真实模型生成，学习路径由知识关系**确定性**推导。实验编排逻辑全部落在独立
Knowledge Core，经端口持久化，**可复用于 Nesti**。

核心能力落地：

- 测验：模型出题（单选 / 判断），正确答案与解析**服务端持有**，作答前不下发；逐题即时判分 +
  解析 + 来源跳转；完成后汇总得分（得分环）+ 逐题回顾 + 再测一次。
- 对比：并排两条知识 + 结构化相同点 / 不同点 + 关系判定徽章（模型给出，可能为空，如实呈现）。
- 学习路径：沿「依赖 / 细化」关系回溯先修，确定性 DFS 编排竖向步进器，末步为目标知识。
- 历史实验列表：重新打开 / 删除；点击任意知识打开 M2 治理详情抽屉（关系 / 版本 / 来源）。

## 2. 范围与架构（遵守长期约束）

| 层 | 职责 | 关键文件 |
| --- | --- | --- |
| Knowledge Core | 实验实体 + 编排服务 + quiz/compare/chain 子服务，**仅依赖端口，不绑定 Web/DB** | `knowledge-core/src/knowledge_core/experiments/` |
| Backend | 实验 ORM + 迁移 0005 + 仓库 + API + DTO + 装配 | `backend/app/models.py`、`backend/alembic/versions/0005_m5_experiments.py`、`backend/app/services/experiments.py`、`backend/app/api/routes/experiments.py` |
| Frontend | 模式元数据（纯模块）+ 三 Runner + 历史 + 编排页 + 治理抽屉 | `frontend/src/lib/experiments.ts`、`frontend/src/components/experiments/`、`frontend/src/components/ExperimentsView.tsx` |

- Core 仅依赖 `KnowledgeRepository` / `RelationRepository` / `ExperimentRepository` 端口与
  `ModelAdapter` 接口；新增 `ExperimentRepository` 端口（save/get/list/update/delete_session +
  save/list_attempt）。Core 独立性守护测试（`test_interfaces.py`）扩展到
  `knowledge_core.experiments`（entities/errors/quiz/compare/chain/service），子进程导入闭包验证通过。
- **循环导入规避**：`ports.py` 对实验实体的 import 置于 `if TYPE_CHECKING:`（注解经
  `from __future__ import annotations` 字符串化），避免 ports→experiments→service→ports 循环。
- 模型可选：quiz/compare 需 `ModelAdapter`，未配置抛 `ModelRequiredError`（应用层映射 **503**）；
  chain 纯确定性无需模型。后端 `get_model_adapter_optional` 返回 `None` 而非在依赖层 503。
- ORM JSON 字段以 **Text** 存储（`json.dumps/loads`），与 M2/M3 一致，规避 SQLite/PG autogenerate 漂移。

## 3. Knowledge Core 实验服务

`ExperimentService(items, relations, experiments, adapter=None)`：

- `create(kind, item_ids, *, space_id, include_unassigned, count, seed_id)`：校验模式 → 取条目
  （缺失抛 `ExperimentNotFoundError`）→ 分派 quiz/compare/chain → 持久化会话。
- **quiz**（`LLMQuizService`）：strict-JSON 提示 → `adapter.generate` → `extract_json` 解析；
  逐题校验（非法跳过）、顺序编号、`source_index` 映射到条目 id；解析失败**诚实返回空**（→ 400）。
- **compare**（`LLMCompareService`）：解析 `{similarities, differences, relationship, relation_type}`；
  已有关系作为提示注入；非法 relation_type → None；解析失败 → 仅含两条 id 的空结果。
- **chain**（`ChainService`）：先修边 = `source depends_on/refines target`；DFS 后序 + visiting/visited
  防环；邻居按 `(title, str(id))` 排序保证确定性；`order[-max_steps:]` 保留目标在末位。
- `public_view(session)`：测验未完成时**剥离** `correct_index` / `explanation`，完成后揭示。
- `answer(session, index, value)`：仅测验，序号 / 选项越界校验 → `AnswerFeedback`（即时判分，无状态）。
- `complete(session, answers)`：测验按索引比对判分 → `ExperimentAttempt`（score=correct/total），
  其余模式仅标记完成；持久化作答记录 + 会话置 COMPLETED。

单测 `knowledge-core/tests/test_experiments.py` **32 例**：实体校验 / quiz 生成·计数·非法·跳过·空·判分 /
compare 解析·非法类型·失败·提示 / chain 先修序·防环·确定性·max_steps·缺失种子·单点 /
service 创建三模式 + 503/400/404 + answer/complete/public_view 揭示。

## 4. Backend 实验 API

迁移 `0005_m5_experiments`（down_revision=0004）：`experiment_session` + `experiment_attempt`
两表（Text JSON 列、UUID String(36)、外键级联）。`alembic check` = No new upgrade operations detected。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/experiments/sessions` | 创建（201）；模型未配置 503 / 调用失败 502 / 参数非法 400 / 资源缺失 404 |
| GET | `/api/experiments/sessions` | 列表（kind / space_id 过滤），对外视图 |
| GET | `/api/experiments/sessions/{id}` | 详情，对外视图（测验未完成隐藏答案） |
| POST | `/api/experiments/sessions/{id}/answer` | 单题即时判分（越界 400） |
| POST | `/api/experiments/sessions/{id}/complete` | 汇总判分 + 标记完成，返回 session + attempt |
| DELETE | `/api/experiments/sessions/{id}` | 删除（204，缺失 404，级联删作答） |

后端单测：`test_experiments_db.py` **7 例**（往返 / 缺失 / 列表过滤排序 / 更新 / 作答往返 / 级联删除 /
删除缺失）+ `test_experiments_api.py` **17 例**（quiz 隐藏答案 / 503 / 502 / 400-空 / compare /
错误条数 400 / chain 无模型有序 / 未知模式 422 / 缺失条目 404 / 未知空间 404 / answer 判分·校验·
非测验 400 / complete 判分+揭示 / 列表+过滤 / 详情+删除 / 缺失 404）。

## 5. Frontend 实验页

- `lib/experiments.ts`（纯模块）：`MODE_META`（三模式标签 / 说明 / 选择约束 / 是否需模型 / 强调色族，
  完整 Tailwind 类名字面量确保 v4 扫描）、`MODE_ORDER`、`minItems` / `canGenerate` / `selectionHint` /
  `scoreTone`（≥0.8 翡翠 / ≥0.5 琥珀 / 其余红，颜色+文字双重表达）/ `percent`。
- `ExperimentsView.tsx`：模式卡片（测验=琥珀 / 对比=天蓝 / 路径=翡翠）+ 知识选择（空间筛选 + 复选，
  对比限 2、路径单选目标）+ 数量滑杆（测验题数 / 路径步数，−/+ 步进）+ 生成 + 三 Runner 分派 +
  历史 + 治理详情抽屉（复用 M2 `KnowledgeDetail`）。
- `QuizRunner`：进度条 + 题卡 + 选项即时判分（正确绿 / 错选红）+ 反馈解析 + 来源跳转 + 完成得分环
  （SVG 描边动画）+ 逐题回顾 + 再测一次；已完成会话重开进入回顾模式。
- `CompareRunner`：并排两条知识（标题 / 状态 / 正文 / 治理详情）+ 关系判定徽章 + 相同点 / 不同点分区。
- `ChainRunner`：竖向步进器（编号圆 + 连接线 + 与上一步关系徽章 + 目标徽章）。
- `ExperimentHistory`：按模式着色，重新打开 / 删除。
- 动效：`index.css` 增 `exp-fade-in` / `exp-pop` / `exp-ring`，`prefers-reduced-motion` 降级。
- 暗色 slate 体系 + 三模式强调色；窄视口列模式 / `lg` 行模式响应式（与 M3/M4 一致）。

前端单测：`lib/experiments.test.ts` **7 例** + `ExperimentsView.test.tsx` **6 例**（三模式卡片 /
测验完整闭环 / 对比异同 / 路径步进 / 模型未配置报错 / 历史删除）+ `client.test.ts` 增 M5 **7 例**。

## 6. 自动化验证（全量）

| 项 | 结果 |
| --- | --- |
| knowledge-core pytest | 115 passed（含独立性守护 + test_experiments 32） |
| backend pytest | 103 passed（含 test_experiments_db 7 + test_experiments_api 17） |
| frontend vitest | 72 passed（10 文件） |
| ruff check（全仓） | All checks passed |
| frontend tsc -b | 通过 |
| frontend vite build | 成功（单 chunk ~1938 kB，分包警告为已知项） |
| alembic check | No new upgrade operations detected |

Python 合计 **218 通过**；前端 **72 通过**。

## 7. 真实模型联调（证据底稿）

后端重启加载 `/api/experiments`（`model_adapter=openai-compatible` 真实 DeepSeek，`embed_adapter=configured`）。
为演示多步学习路径，先建立一条**真实先修关系**：典型用途 `depends_on` 定义（201，origin=manual）。

- **测验**（真实出题，count=3）：3 题（单选 + 判断 + 单选），**作答前正确答案 / 解析全部隐藏=True**；
  逐题即时判分返回解析；完成 **得分 1.00（3/3）**，**完成后答案揭示=True**，会话状态 completed。
- **对比**（真实辨析：定义 ↔ 典型用途）：**相同点 2 / 不同点 3**，关系类型 `depends_on`，
  关系说明「B 所描述的典型用途以 A 所定义的知识图谱数据模型为基础。」（与所建先修关系一致）。
- **学习路径**（确定性，seed=典型用途）：**2 步**「知识图谱的定义 → 知识图谱的典型用途」，
  第二步 `relation_from_prev=depends_on`，**末步为目标知识=True**。
- **列表**：三会话全部落库（chain active / compare active / quiz completed）。

## 8. 真实浏览器联调（截图读回验证）

内置浏览器（`http://[::1]:5173/`）「实验」页签实测，控制台**零错误零警告**（仅 Vite/DevTools info）：

- **首页**：三模式卡片（琥珀 / 天蓝 / 翡翠）+ 知识选择 + 题数滑杆 + 历史（3 会话）。
- **测验作答**：生成 5 题（真实模型），进度条「第 1 / 5 题」，选项 A 判对绿显 + 翡翠反馈解析 + 来源跳转。
- **测验得分**：完成 **100%（5/5）**，翡翠得分环「掌握良好」+ 逐题回顾（正确答案揭示）+ 再测一次。
- **对比**：并排两条知识 + 天蓝「依赖」关系徽章 + 相同点（2）/ 不同点（3）。
- **学习路径**：翡翠步进器，定义（先修，步骤 1）→ 典型用途（目标，步骤 2，「依赖上一步」徽章）。
- **治理抽屉**：点击路径步骤 → 右侧抽屉显示「知识图谱的定义」关系（3）/ 版本（2）/ 来源（3，对话+手动+文档），
  M5→M2 跨功能集成真实可用。

完整交互闭环（生成→作答→判分→完成→回顾→历史→治理）在真实浏览器跑通，重复操作稳定，无运行时错误。

## 9. 已知限制与后续

- 单 chunk ~1938 kB（React Flow + ELK 既有体积）：分包 / 懒加载留待后续优化，非功能缺陷。
- 浏览器验收在内置面板窄视口（列模式）完成；宽视口行模式沿用 M3/M4 已验证的响应式断点
  （`lg:flex-row` / `sm:grid-cols-3` / `md:grid-cols-2`）。
- 学习路径多步演示依赖先修关系存在；本次联调建立了一条真实 `depends_on` 关系（非假数据）。
  无先修关系时路径退化为单点（目标自身），如实呈现。
- 测验 / 对比需模型；未配置时如实返回 503（单测 + 集成测试覆盖），不以假数据冒充。
- 组件单测中取数用确定性 fetch 替身；真实模型与画布渲染以浏览器验收为准（本报告 §7–8）。

## 10. 结论

M5 全部验收标准通过：Core 实验编排独立可复用、实验 API 口径与判分 / 揭示正确、前端三模式真实交互
（测验得分环 / 对比异同 / 路径步进）且与治理联动、全量测试 / lint / 构建 / 无漂移通过、真实 DeepSeek
联调与六张截图齐备、控制台零错误。**M5 验收通过，ExplainLab V1.0 七大核心能力全部落地。**