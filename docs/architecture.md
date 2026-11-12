# ExplainLab 架构设计（M0 基线）

## 1. 总体结构

```
┌────────────────────────────────────────────────────────┐
│ frontend/  (React + TS + Vite)                          │
│   仅负责展示与交互；通过 /api 访问后端；不持有任何 Key    │
└──────────────────────────┬─────────────────────────────┘
                           │ HTTP (dev: Vite proxy)
┌──────────────────────────▼─────────────────────────────┐
│ backend/  (FastAPI)                                     │
│   API 层：路由、请求校验、依赖注入、配置、数据库会话      │
│   不包含知识业务逻辑                                     │
└──────────────────────────┬─────────────────────────────┘
                           │ Python import（进程内调用）
┌──────────────────────────▼─────────────────────────────┐
│ knowledge-core/  (独立 Python 包)                       │
│   domain/        领域实体（纯 Pydantic 模型）            │
│   extraction/    知识提取接口                            │
│   relations/     关系与去重接口                          │
│   versioning/    版本管理接口                            │
│   provenance/    来源追溯接口                            │
│   retrieval/     检索接口                                │
│   model_adapter/ 统一模型适配层接口 + 注册工厂            │
└─────────────────────────────────────────────────────────┘
```

## 2. Knowledge Core 独立性约束（长期要求）

Knowledge Core 未来将复用于 **Nesti**，因此：

1. **禁止依赖** FastAPI、Starlette、前端构建产物或任何 Web 框架。
2. **禁止依赖** ExplainLab 特有的页面状态、路由、UI 概念。
3. 只允许依赖 Python 标准库与 Pydantic 这类通用基础库；数据库 / 模型供应商等外部能力通过接口（Protocol / ABC）注入。
4. 知识提取、关系管理、版本管理、来源追溯、检索必须能在无前端、无 HTTP 服务的环境下以纯 Python 方式调用与测试。
5. backend 通过 uv workspace 以可编辑方式依赖 knowledge-core；反向依赖禁止。

M0 阶段 core 只包含领域实体与接口定义，业务实现在 M1+ 逐步落地。

## 3. Model Adapter 统一模型适配层

位置：`knowledge_core/model_adapter/`。

- `ModelAdapter`（ABC）：统一抽象，定义 `generate()`、`embed()`、`capabilities()`。
- `ModelRequest / ModelResponse / ModelMessage`：与供应商无关的请求响应类型。
- `AdapterRegistry`：按名称注册 / 解析适配器，支持未来更换供应商而不改业务代码。
- M0 不实现任何具体供应商；未配置时系统如实报告 `not_configured`。
- API Key 只从后端环境变量读取，绝不进入前端与 Git。

## 4. 数据层策略

- 开发：SQLite（`backend/data/explainlab.db`），全文检索用 FTS5（M0 已实测能力）。
- 部署：PostgreSQL，通过 `DATABASE_URL` 切换，驱动为 psycopg 3。
- 引擎工厂对两种方言分别处理连接参数（SQLite `check_same_thread`、PG `pool_pre_ping`）。
- Alembic 迁移统一管理 schema；SQLite 下启用 batch 模式以兼容 ALTER。
- M0 仅建立 baseline 迁移，不提前创建业务表。

## 5. 前后端通信

- 开发：Vite dev server 将 `/api` 代理到 `http://127.0.0.1:8000`，前端无跨域问题。
- 后端同时配置 CORS 允许开发源，便于直连调试。
- 前端 API 客户端集中在 `frontend/src/api/`，类型与后端响应结构对应。

## 6. 测试策略

- knowledge-core：纯单元测试，验证领域模型与接口契约，不需要数据库与网络。
- backend：pytest + FastAPI TestClient，使用临时 SQLite 数据库，验证配置、迁移、健康检查。
- frontend：Vitest + Testing Library，mock fetch 属于测试基建，产品代码不使用假数据。

## 7. 里程碑演进

见 [MILESTONES.md](../MILESTONES.md)。后续每个里程碑都必须遵守第 2 节的独立性约束。