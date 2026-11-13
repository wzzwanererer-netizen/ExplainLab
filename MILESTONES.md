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

## M2 · 知识关系、去重与审核 ⬜

- 重复知识识别、知识关系推断
- 版本管理与来源追溯落地
- 重要知识变更审核流

## M3 · 跨会话混合检索 ⬜

- SQLite FTS5 全文检索 + 向量检索（PostgreSQL 阶段迁移方案）
- 跨会话、跨知识空间混合检索 API 与前端检索入口

## M4 · 动态知识地图 ⬜

- React Flow + ELK.js 知识地图渲染
- 地图与知识条目 / 关系实时联动

## M5 · 交互式知识实验 ⬜

- 基于知识库的实验式学习交互（测验、推演、对比等）

---

## 长期架构约束（所有里程碑必须遵守）

1. Knowledge Core 独立于 ExplainLab 前端，未来复用于 Nesti。
2. 知识提取、关系管理、版本管理、来源追溯、检索不依赖前端页面。
3. 模型供应商只能通过 Model Adapter 接口接入，可替换。
4. API Key 不进入前端。
5. 不以假数据冒充真实功能。