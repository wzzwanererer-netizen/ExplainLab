# ExplainLab 里程碑

> 状态标记：✅ 已完成 / 🚧 进行中 / ⬜ 未开始。里程碑内容可能随验收反馈调整。

## M0 · 项目初始化与工程规范建立 ✅

**目标**：建立可运行、可测试、可扩展的工程骨架，不开发业务功能。

验收标准（2026-11-12 全部通过）：

- [x] 工作区检查完成，无已有文件被破坏
- [x] 前端工程初始化（React + TS + Vite + Tailwind，React Flow / ELK.js 依赖就绪）
- [x] 后端工程初始化（FastAPI + SQLAlchemy + Alembic + Pydantic）
- [x] Knowledge Core 独立模块骨架（不依赖前端与 Web 框架）
- [x] Model Adapter 统一接口（无具体供应商实现）
- [x] SQLite 配置完成（FTS5 能力实测通过）
- [x] PostgreSQL 连接支持（驱动 + 配置切换，未安装 PG 服务器）
- [x] Alembic 配置完成并实际执行迁移
- [x] 前后端通信打通（Vite proxy + CORS，真实请求验证）
- [x] 健康检查 API（真实数据库探测）
- [x] Git 配置与初始提交
- [x] 项目文档（README / 架构 / 开发指南）
- [x] 基础测试（后端 / Knowledge Core / 前端）全部通过
- [x] 本地启动脚本（setup / dev / test，PowerShell + Bash）

验收证据见 [docs/acceptance/M0-report.md](docs/acceptance/M0-report.md)（含真实运行输出与首页截图）。

## M1 · 对话与知识提取基础 ✅

**目标**：打通真实模型对话与知识提取持久化，建立知识空间数据模型与基本 CRUD。

验收标准（2026-11-13 全部通过）：

- [x] 会话模型与对话 API（接入首个供应商 DeepSeek，通过 Model Adapter，真实回复落库）
- [x] Knowledge Core：知识提取服务实现（LLMExtractionService + KnowledgeService）
- [x] 知识条目持久化（KnowledgeRepository 端口 + SQLAlchemy 实现，来源追溯随条目落库）
- [x] 个人总知识库 / 项目知识空间数据模型与基本 CRUD
- [x] 数据迁移 0002_m1_core（5 张表，无漂移）
- [x] 前端对话视图与知识库视图（真实 API，无假数据）
- [x] 全量测试（Python 80 通过 + 前端 15 通过 + ruff 通过 + 构建通过）
- [x] 真实模型端到端联调（对话 + 提取 2 条知识并落库，来源可追溯）
- [x] API Key 仅存 backend/.env，不进入前端；模型请求直连真实 base_url，无代理替换

验收证据见 [docs/acceptance/M1-report.md](docs/acceptance/M1-report.md)（含真实运行输出、真实模型对话与三视图截图）。

## M2 · 知识关系、去重与审核 ✅

**目标**：在 M1 提取与持久化之上补齐知识治理层——去重、关系推断、版本管理、来源追溯落地、重要变更审核流，治理逻辑全部落在独立 Knowledge Core。

验收标准（2026-11-14 全部通过）：

- [x] 迁移 0003_m2_governance 实跑、无漂移；三张治理表就绪（knowledge_relation / knowledge_version / review_request）
- [x] 去重（词面 char-bigram 召回 + LLM 同一知识判定）与关系推断可用且落库，origin（manual/llm/dedup）可追溯
- [x] 版本 create/list/restore 可用；restore 先建回滚前快照，保留线性历史
- [x] 重要变更按审核矩阵进审核；批准应用、驳回无副作用；merge 闭环（归档 + DUPLICATE_OF + 来源并入，不硬删）
- [x] 来源追溯 attach/trace 落地
- [x] 前端最小界面（详情关系/版本/来源、查重合并、审核队列、202 提示）真实可用
- [x] 全量测试（Python 117 通过 + 前端 27 通过）+ ruff + 构建 + 无漂移通过；Core 独立性守护扩展到 M2 模块
- [x] 真实 DeepSeek 联调（仅 generate，无 embed）：查重 0.98、关系落库、合并闭环、生效编辑门禁
- [x] 联调发现并修复 2 个真实缺陷（合并来源主键冲突；SQLite 外键级联 + 删除批准自毁），均补回归测试

验收证据见 [docs/acceptance/M2-report.md](docs/acceptance/M2-report.md)（含真实运行输出、真实模型治理闭环证据与界面截图）。

## M3 · 跨会话混合检索 ✅

**目标**：在 M2 治理之上提供检索层——SQLite FTS5 全文 + 真实语义向量 + RRF 融合排序，跨会话/跨知识空间检索 API 与前端检索入口，检索编排落在独立 Knowledge Core。

验收标准（2026-11-14 全部通过）：

- [x] 迁移 0004_m3_retrieval 实跑、无漂移；FTS 虚表（trigram）+ 向量表就绪，触发器同步生效
- [x] 中文全文检索（trigram + 短查询 LIKE 回退）与向量检索可用，混合 RRF（k=60）排序正确
- [x] 跨会话/跨空间检索 API 与前端「检索」页签真实可用；space 过滤与 archived 排除正确
- [x] 索引随治理变更同步；backfill（reindex）可用；embed 能力如实上报/降级（not_configured/supported/unsupported）
- [x] 全量测试（Python 149 通过 + 前端 36 通过）+ ruff + 构建 + 无漂移通过；Core 独立性守护扩展到 M3
- [x] 真实 embed 联调（SiliconFlow BAAI/bge-m3，1024 维）：3 条知识建向量，hybrid 双通道命中 + 融合排序，干净 UTF-8 证据
- [x] 向量来源独立 EMBED_* 配置（方案 A），密钥仅 backend/.env，不进入前端；直连真实 base_url 无代理

验收证据见 [docs/acceptance/M3-report.md](docs/acceptance/M3-report.md)（含真实运行输出、真实 embed 双通道证据与检索/系统状态截图）。

## M4 · 动态知识地图 ✅

**目标**：在 M2 关系 / M3 检索之上提供可视化层——Knowledge Core 装配「节点 + 边」图结构，后端只读图 API，前端 React Flow + ELK 自动布局渲染，地图与知识条目 / 关系实时联动。

验收标准（2026-11-15 全部通过）：

- [x] Knowledge Core 图服务（graph/，纯数据装配、无坐标、仅依赖端口）+ RelationRepository.list_all_relations 端口；独立性守护扩展到 M4
- [x] GET /api/graph（space_id 过滤 + include_archived 开关 + 个人空间聚合未归属 + 未知空间 404）；无新增迁移、alembic 无漂移
- [x] 图装配口径：archived 默认不入图、悬空边丢弃、自环跳过、(source,target,type) 去重
- [x] 前端「地图」页签（React Flow + ELK 分层自动布局）：节点 / 边 / 图例 / 计数 / 空间筛选 / 显示归档 / 刷新
- [x] 边视觉语义（related 灰无箭头 / depends_on 蓝 / refines 绿 / duplicate_of 红虚线箭头 / contradicts 红箭头）；归档节点灰显虚线
- [x] 点击节点→治理详情（关系 / 版本 / 来源）；切页签 / 刷新 / 治理变更重取，实时联动实测（改标题→地图同步）
- [x] 全量测试（Python 162 通过 + 前端 52 通过）+ ruff + 构建 + 无漂移通过
- [x] 真实浏览器联调 + 三张验收截图；联调发现并修复 3 个真实缺陷（自定义节点缺 Handle / 窄视口画布塌缩 / 默认白色控件与暗色冲突），均复验

验收证据见 [docs/acceptance/M4-report.md](docs/acceptance/M4-report.md)（含真实图 API 输出、边视觉语义实测与默认 / 含归档 / 详情三张截图）。

## M5 · 交互式知识实验 ⬜

- 基于知识库的实验式学习交互（测验、推演、对比等）

---

## 长期架构约束（所有里程碑必须遵守）

1. Knowledge Core 独立于 ExplainLab 前端，未来复用于 Nesti。
2. 知识提取、关系管理、版本管理、来源追溯、检索不依赖前端页面。
3. 模型供应商只能通过 Model Adapter 接口接入，可替换。
4. API Key 不进入前端。
5. 不以假数据冒充真实功能。