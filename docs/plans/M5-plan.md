# ExplainLab M5 实施计划 · 交互式知识实验

> 状态：待确认。确认后按 T1→T8 执行；每阶段实跑验证，最后真实联调 + 验收报告 + MILESTONES + Git 提交。
> 上游：M0✅ M1✅ M2✅ M3✅ M4✅（commit d6b29e7）。M5 为 V1.0 第七项核心能力「交互式知识实验」。

## 0. 目标与边界

把已积累的知识变成**可操作的学习实验**，而非只读浏览。提供三种实验模式，全部基于真实知识条目与关系：

1. **测验（quiz）**：LLM 从选定知识生成单选 / 判断题 → 逐题作答 → 服务端判分 → 即时反馈 + 解析 + 来源引用 → 汇总得分 → 可重做。
2. **对比（compare）**：选两条知识 → LLM 结构化对比（相同点 / 不同点 / 关系结论）+ 既有关系徽章 → 双栏并排呈现。
3. **推演 / 学习路径（chain）**：从种子知识沿 `depends_on` / `refines` 关系**确定性** traversals 生成先修学习路径 → 逐步步进。**不依赖模型**（模型未配置仍可用）。

边界（遵守长期约束）：

- 实验编排落在独立 **Knowledge Core**（`knowledge_core/experiments/`），仅依赖端口 + ModelAdapter，不绑定 Web/DB/前端，可复用于 Nesti。
- 不新增假数据：题目 / 对比来自真实 LLM（generate），解析失败如实返回空 / 502；路径来自真实关系。
- 模型未配置：quiz / compare 如实 503；chain 仍可用（不依赖模型）。
- API Key 仅 backend/.env；前端不持有密钥；base_url 原样直连，无代理替换。
- 答案与解析**服务端持有**，前端在未作答前拿不到 correct / explanation（防泄题）。
- 不提前开发 M5 之外的业务功能；不一次性铺所有页面（单一「实验」页签内模式切换）。

## 1. 架构与复用

| 层 | 新增 | 复用 |
| --- | --- | --- |
| Core | `experiments/`（entities/ports/quiz/compare/chain/service） | ModelAdapter.generate、parsing.extract_json、KnowledgeRepository、RelationRepository |
| Backend | 迁移 0005、ORM、SQLAlchemyExperimentRepository、routes/experiments.py、schemas | dependencies.get_session / get_model_adapter(503) / 新增 optional adapter、services.model |
| Frontend | types/client 实验方法、ExperimentsView + 三个 Runner + History、App 页签 | api.client 请求封装、KnowledgeDetail 来源引用风格、全局暗色滚动条 |

LLM 调用模式镜像 `relations/llm.py`：system+user 严格 JSON prompt → `adapter.generate` → `extract_json` → 校验字段 → 失败如实空。

## 2. Core 设计（knowledge_core/experiments/）

### 2.1 实体（entities.py，Pydantic）

- `ExperimentKind(StrEnum)`: quiz / compare / chain
- `QuizQuestion`: index:int、prompt:str、kind:`single_choice|true_false`、options:list[str]、correct_index:int、explanation:str、source_item_id:UUID
- `CompareResult`: item_a_id、item_b_id、similarities:list[str]、differences:list[str]、relationship:str、relation_type:RelationType|None（既有关系徽章）
- `ChainStep`: item_id:UUID、title:str、relation_from_prev:RelationType|None、position:int
- `ExperimentSession`: id:UUID、kind、title:str、space_id:str|None、item_ids:list[UUID]、payload:dict（quiz=questions / compare=CompareResult / chain=steps）、status:`active|completed`、created_at、updated_at
- `ExperimentAttempt`: id:UUID、session_id:UUID、answers:list[dict{index,value,correct}]、correct_count:int、total:int、score:float、created_at
- `AnswerFeedback`: correct:bool、correct_value:object、explanation:str

### 2.2 端口（ports.py 增 ExperimentRepository）

save_session / get_session / list_sessions(*, kind=None, space_id=None) / update_session / delete_session / save_attempt / list_attempts(session_id)。

### 2.3 服务

- `quiz.py LLMQuizService(adapter)`：`generate(items, count)` → 严格 JSON `{"questions":[{prompt,kind,options,correct_index,explanation,source_index}]}`；校验 options 非空、correct_index 越界丢弃、source_index 映射回 item；`grade(question, value)` 确定性判分。
- `compare.py LLMCompareService(adapter)`：`compare(a, b, existing_relation)` → JSON `{similarities,differences,relationship}`；失败如实抛 / 空。
- `chain.py ChainService(items, relations)`：`build(seed_id, max_steps)` 确定性：先修优先（depends_on 反向 / refines 向上），visited 防环，输出有序 ChainStep；无模型。
- `service.py ExperimentService(items, relations, experiments, adapter|None)`：
  - `create(kind, item_ids, space_id, count)`：quiz/compare 需 adapter（None 时抛 CapabilityError→503）；chain 不需要；落库 session。
  - `public_view(session)`：quiz 剥离 correct_index/explanation 后返回。
  - `answer(session, index, value)`→AnswerFeedback（服务端判分）。
  - `complete(session, answers)`→Attempt（汇总 score，status=completed，落库）。

### 2.4 独立性守护

`test_interfaces.py` 导入闭包增加 `knowledge_core.experiments` 及子模块；子进程验证无 Web/DB 依赖。

## 3. Backend 设计

### 3.1 迁移 0005_m5_experiments（无漂移要求）

- `experiment_session`: id PK(uuid)、kind str、title str、space_id str null、item_ids JSON、payload JSON、status str、created_at、updated_at
- `experiment_attempt`: id PK(uuid)、session_id FK→experiment_session、answers JSON、correct_count int、total int、score float、created_at
- JSON 列用 SQLAlchemy `JSON`（SQLite/PG 通用）。

### 3.2 ORM + 仓库

`db/models.py` 增 ExperimentSessionORM / ExperimentAttemptORM；`services/experiments.py` SQLAlchemyExperimentRepository + `build_experiment_service(session, adapter)`。

### 3.3 API（routes/experiments.py，prefix /api）

- `POST /experiments/sessions` {kind, item_ids, space_id?, count?} → 创建并生成；quiz/compare 无模型 503、LLM 失败 502；chain 无需模型。返回 public_view。
- `GET /experiments/sessions?kind=&space_id=` → 历史列表（含 score 摘要）。
- `GET /experiments/sessions/{id}` → public_view；未知 404。
- `POST /experiments/sessions/{id}/answer` {index, value} → AnswerFeedback。
- `POST /experiments/sessions/{id}/complete` {answers:[{index,value}]} → Attempt + 汇总。
- `DELETE /experiments/sessions/{id}` → 204。
- dependencies 增 `get_model_adapter_optional`（镜像 get_embedder，返回 None 不 503），create 路由内对 quiz/compare 手动 503。

### 3.4 schemas

CreateExperimentIn / ExperimentSessionOut(quiz 剥离) / AnswerIn / AnswerOut / AttemptOut / SessionListItem。

## 4. Frontend 设计

### 4.1 types + client

ExperimentKind / QuizQuestionPublic(无 correct/explanation) / CompareResult / ChainStep / ExperimentSession / Attempt / AnswerFeedback / CreateExperimentInput；client：createExperiment / listExperiments / getExperiment / answerExperiment / completeExperiment / deleteExperiment。

### 4.2 ExperimentsView（单一「实验」页签）

- **模式选择**：三张模式卡（测验=amber、对比=blue、推演=green），含说明与所需知识数；选中高亮。
- **知识选择器**：quiz 多选（≥1）、compare 恰选 2、chain 单选种子；来自真实 /api/knowledge；显示状态徽章。
- **生成**：按钮调用 create；loading / 503 / 502 如实提示。
- **QuizRunner**：进度条 + 题卡；选项按钮；作答→answer→即时对错着色 + 解析 + 来源链接；下一题；末题→complete→得分环 + 逐题回顾 + 重做。
- **CompareRunner**：双栏并排（A/B 标题+内容摘要）+ 相同点 / 不同点列表 + 关系结论 + 既有关系徽章。
- **ChainRunner**：学习路径 stepper（position + 关系标签 + 标题），上一步 / 下一步，来源链接；无模型提示「本模式不依赖模型」。
- **HistoryList**：历史 session（kind 徽章 / 标题 / 得分 / 时间），重开（getExperiment）与删除（deleteExperiment，确认）。
- 视觉：延续 slate 暗色 + 模式 accent；作答反馈色 + 轻动画；得分环；全局暗色滚动条已就绪；窄视口单列、宽视口双栏。

### 4.3 App

Tab 增 `experiments`，TABS 增 {id:"experiments", label:"实验"}（置于地图后），徽标改「M5 · 知识实验」。

## 5. 任务拆分

- **T1** Core experiments 实体 + ExperimentRepository 端口 + 独立性守护扩展。
- **T2** Core quiz / compare / chain / service 实现 + 单测（fake adapter：合法 JSON / 畸形→空、判分、chain 防环、create/answer/complete）。
- **T3** Backend 迁移 0005 + ORM + SQLAlchemyExperimentRepository + 无漂移验证。
- **T4** Backend schemas + routes + dependencies optional adapter + main 装配 + API 测试（503/502/404/判分/汇总/删除）。
- **T5** Frontend types + client + client 单测。
- **T6** Frontend ExperimentsView + 三 Runner + History + App 页签 + 组件单测（mock fetch）。
- **T7** 全量测试 + ruff + tsc + build + alembic 无漂移 + Core 独立性。
- **T8** 真实联调（DeepSeek generate 测验 + 对比；chain 确定性）+ 浏览器截图 + UTF-8 证据 + M5-report.md + MILESTONES M5✅ + Git 提交。

## 6. 验收标准

- [ ] 三种模式真实可用：quiz 生成→作答→判分→反馈→汇总→重做闭环；compare 双栏结构化；chain 确定性路径步进。
- [ ] 答案 / 解析服务端持有，未作答前端不可见；判分与汇总服务端计算。
- [ ] 模型未配置：quiz/compare 503 如实提示，chain 仍可用；LLM 解析失败如实空 / 502，不造假。
- [ ] 历史 session 持久化（迁移 0005 实跑、无漂移），可重开 / 删除。
- [ ] Core 独立性守护覆盖 experiments；不绑定 Web/DB/前端。
- [ ] 全量测试（Core+Backend+Frontend）+ ruff + tsc + build + 无漂移通过。
- [ ] 真实浏览器联调 + 截图（测验作答反馈 / 对比双栏 / 推演步进 / 历史）+ 干净 UTF-8 证据。
- [ ] 窄 / 宽视口无塌缩 / 溢出 / 不可达控件；暗色主题一致。

## 7. 风险与对策

- **LLM JSON 畸形**：extract_json + 字段校验，失败如实空 / 502；quiz 生成 0 题时前端提示重试，不造假题。
- **泄题**：public_view 剥离 correct/explanation；answer 才返回。
- **chain 环**：visited 集合防环；max_steps 上限。
- **模型未配置**：optional adapter + 路由内按 kind 503；chain 不依赖。
- **JSON 列跨库**：SQLAlchemy JSON 通用类型；迁移实跑 + alembic check。
- **quiz 重做状态**：Runner 以 session id + attempt 重置本地答题状态，避免串题。
- **后端旧进程缺新路由**：T8 前重启后端加载 /api/experiments（同 M4 经验）。