# ExplainLab

基于持续对话的 AI 知识管理与交互式学习平台。

## 核心能力（V1.0 已实现）

1. AI 对话中自动提取知识
2. 个人总知识库与项目知识空间
3. 自动识别重复知识与知识关系
4. 重要知识变更进入审核
5. 跨会话混合检索
6. 动态知识地图
7. 交互式知识实验

> 状态：V1.0（M0–M5）七项能力均已落地并通过里程碑验收。当前已完成「M0 准入修复 + M5 回归修复」，详见 [修复验收报告](docs/acceptance/M0-M5-REMEDIATION-REPORT.md)；**等待独立审计，未自行进入后续新里程碑**。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | React + TypeScript + Vite + Tailwind CSS + React Flow (@xyflow/react) + ELK.js |
| 后端 | Python 3.11 + FastAPI + SQLAlchemy + Alembic + Pydantic |
| 数据库 | 开发：SQLite + FTS5（trigram）；部署：PostgreSQL 原生 `tsvector/tsquery` + GIN（方言封装在 backend 适配层） |
| AI | 统一 Model Adapter 适配层（已实现 `OpenAICompatibleAdapter`：生成 DeepSeek、向量 SiliconFlow 等；公共失败契约 + 能力诚实声明，供应商可替换） |
| 部署 | 本地部署 |

## 仓库结构

```
ExplainLab/
├── frontend/          # React 前端（不含任何 API Key）
├── backend/           # FastAPI API 层
├── knowledge-core/    # 独立知识核心包（不依赖前端 / Web 框架，可复用于 Nesti）
├── scripts/           # 本地 setup / dev / test 脚本（PowerShell + Bash）
└── docs/              # 架构、开发指南、验收报告
```

## 快速开始

前置要求：Node.js ≥ 22.23.2（审计复现基线 **22.23.2**）、Python 3.11、[uv](https://docs.astral.sh/uv/)、Git。

```bash
# 1. 安装依赖（前端 npm + Python uv workspace）
bash scripts/setup.sh        # Windows PowerShell: scripts/setup.ps1

# 2. 初始化数据库（Alembic 迁移）
cd backend && uv run alembic upgrade head && cd ..

# 3. 同时启动前后端
bash scripts/dev.sh          # Windows PowerShell: scripts/dev.ps1
```

- 前端：http://localhost:5173
- 后端 API：http://127.0.0.1:8000/api/health
- API 文档：http://127.0.0.1:8000/docs

## 测试

```bash
bash scripts/test.sh         # 或 scripts/test.ps1
```

## 文档

- [架构设计](docs/architecture.md)
- [开发指南](docs/development.md)
- [里程碑](MILESTONES.md)
- [M0 验收报告](docs/acceptance/M0-report.md)

## 安全约束

- API Key 只允许存在于后端环境变量（`.env`，不入库），前端绝不持有。
- Knowledge Core 不依赖前端页面与 Web 框架，知识提取 / 关系 / 版本 / 来源 / 检索均可脱离前端运行。