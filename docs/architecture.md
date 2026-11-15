# ExplainLab 架构设计（V1.0）

> 本文描述 V1.0（M0–M5）已落地的真实架构。工程强制规范见根目录 [AGENTS.md](../AGENTS.md)，
> 核心模块「抽象接口 vs 具体实现」清单见 [knowledge-core/README.md](../knowledge-core/README.md)。

## 1. 总体结构

```
┌────────────────────────────────────────────────────────┐
│ frontend/  (React 19 + TS + Vite 8 + Tailwind v4)       │
│   七个视图：对话/知识库/检索/地图/实验/审核/系统状态     │
│   仅展示与交互；经 /api 访问后端；不持有任何 Key         │
│   地图(React Flow+ELK)与实验页经 React.lazy 按需加载     │
└──────────────────────────┬─────────────────────────────┘
                           │ HTTP (dev: Vite proxy)
┌──────────────────────────▼─────────────────────────────┐
│ backend/  (FastAPI)                                     │
│   API 层：路由、请求校验、依赖注入、配置、数据库会话      │
│   持久化：SQLAlchemy 仓库实现核心端口 + Alembic 迁移      │
│   数据库适配层：全文/向量按方言分派（SQLite / PostgreSQL）│
│   不包含知识业务逻辑                                     │
└──────────────────────────┬─────────────────────────────┘
                           │ Python import（进程内调用）
┌──────────────────────────▼─────────────────────────────┐
│ knowledge-core/  (独立 Python 包，可复用于 Nesti)        │
│   domain/        领域实体（纯 Pydantic 模型）            │
│   extraction/    LLMExtractionService（经 Model Adapter）│
│   relations/     LLMRelationService + 词面召回           │
│   versioning/    RepositoryVersionService               │
│   provenance/    RepositoryProvenanceService            │
│   review/        ReviewPolicy + ReviewService           │
│   retrieval/     HybridRetrievalService（RRF 融合）      │
│   graph/         KnowledgeGraphService（无坐标图数据）   │
│   experiments/   Experiment/Quiz/Compare/Chain 服务      │
│   model_adapter/ OpenAICompatibleAdapter + 失败契约      │
│   ports.py       Protocol 端口（持久化/模型能力边界）    │
└─────────────────────────────────────────────────────────┘
```

依赖方向强制自上而下：`frontend → backend → knowledge-core`，严禁反向。

## 2. Knowledge Core 独立性约束（长期要求）

Knowledge Core 未来将复用于 **Nesti**，因此：

1. **禁止依赖** FastAPI、Starlette、前端构建产物或任何 Web 框架。
2. **禁止依赖** ExplainLab 特有的页面状态、路由、UI 概念。
3. 只允许依赖 Python 标准库、Pydantic 与 httpx（httpx 仅用于 Model Adapter 的 OpenAI 兼容 HTTP 调用）；数据库 / 模型供应商等外部能力通过接口（Protocol / ABC）注入。
4. 知识提取、关系管理、版本管理、来源追溯、审核、检索、知识地图、交互式实验必须能在无前端、无 HTTP 服务的环境下以纯 Python 方式调用与测试。
5. backend 通过 uv workspace 以可编辑方式依赖 knowledge-core；反向依赖禁止。

V1.0（M0–M5）已落地完整业务实现：各服务模块 `__init__.py` 定义抽象接口（ABC），同包实现文件提供具体类，接口不可直接实例化。`ports.py` 的端口是核心与持久化/模型能力的唯一边界，**故意保持抽象**，由应用层注入实现，不属于「未实现」。独立性由 `knowledge-core/tests/test_interfaces.py::test_core_has_no_web_framework_dependency` 在干净子进程守护。

## 3. Model Adapter 统一模型适配层

位置：`knowledge_core/model_adapter/`。

- `ModelAdapter`（ABC）：统一抽象，定义 `generate()`、`embed()`、`capabilities()`。
- `ModelRequest / ModelResponse / ModelMessage`：与供应商无关的请求响应类型。
- `AdapterRegistry`：按名称注册 / 解析适配器，支持更换供应商而不改业务代码。
- **已实现** `providers.OpenAICompatibleAdapter`，适配 DeepSeek / 通义 / Kimi / 智谱 / OpenAI 等 OpenAI 兼容服务。`base_url` **原样直连**，`trust_env=False` 不读取环境代理，严禁替换为任何临时代理地址。
- **公共失败契约**（`errors.py`，所有适配器统一遵守）：可重试 `ModelTimeoutError` / `ProviderUnavailableError` / `RateLimitError`；不可重试 `AuthenticationError` / `MalformedResponseError` / `CapabilityNotSupportedError` / 基类 `ModelAdapterError`；`is_retryable()` 统一判定。
- **能力声明诚实**：`capabilities()` 当前仅声明 `GENERATE` 与 `EMBED`；`STREAM` 未实现，不得虚假声明。未配置供应商时系统如实报告 `not_configured`。
- API Key 只从后端环境变量经 `SecretStr` 注入，绝不进入前端与 Git，序列化自动掩码。

## 4. 数据层与检索方言适配

### 4.1 ORM / 持久化边界

- 核心不绑定数据库：`ports.py` 定义 `KnowledgeRepository / RelationRepository / VersionRepository / ReviewRepository / ExperimentRepository / FullTextIndex / VectorStore / Embedder`。
- backend 以 SQLAlchemy 实现这些端口（`app/services/`），负责领域实体 ↔ ORM 映射；UUID 存 `String(36)`、时间用 UTC、JSON 负载以 Text 存储以兼容双方言。
- 业务服务与核心**不得出现方言特定 SQL**；方言差异封装在 backend 数据库适配层。

### 4.2 数据库策略

- **开发默认**：SQLite（`backend/data/explainlab.db`，绝对路径锚定到 backend 目录，启动目录无关），全文检索用 FTS5（trigram）。
- **部署目标**：PostgreSQL，经 `DATABASE_URL`（`postgresql+psycopg://...`）切换，驱动 psycopg 3（已在依赖中）。
- 引擎工厂（`app/db/session.py`）按方言处理连接参数（SQLite `check_same_thread` + `PRAGMA foreign_keys=ON`；PG `pool_pre_ping`）。

### 4.3 全文检索方言实现（ZIP-01）

- **SQLite**：FTS5 trigram 虚表 `knowledge_fts` + 增改删触发器；`SQLiteFullTextIndex` 用 `MATCH` / `bm25` 排名，短查询（<3 字符）回退 LIKE。
- **PostgreSQL**：原生 `tsvector/tsquery` + GIN 索引；`knowledge_fts(item_id, tsv)` 普通表 + 增改触发器（`knowledge_fts_sync()`）、删除经外键 `ON DELETE CASCADE`；`PostgresFullTextIndex` 用 `ts_rank`（返回 `-ts_rank`，越小越相关，与 SQLite 契约一致）。**PG 路径不使用 `FTS5 / MATCH / bm25 / rowid`。**
- **CJK 局限（如实记录）**：PG `simple` 分词不对无空格中文成词，此类查询无 tsvector 命中时回退 `ILIKE` 子串匹配（JOIN `knowledge_fts` 限定已索引集合，真实匹配，非造假）。
- **向量存储**：`JsonVectorStore`（JSON 文本 + Python 余弦）双方言通用，不依赖 pgvector。
- **分派**：`build_full_text_index(session)` / `build_vector_store(session)` 按会话绑定方言选择实现；编排（`RetrievalIndexer` / `sync_index` / `build_retrieval_service`）不含方言 SQL。
- **混合检索**：核心 `HybridRetrievalService` 以 RRF 融合全文 + 向量双通道；embed 未配置或故障时向量通道如实关闭/降级，仅全文可用，不造假。

### 4.4 迁移

- 所有 schema 变更走 Alembic（`backend/alembic/versions/0001..0005`），均可 `upgrade` 与 `downgrade`。
- `0004_m3_retrieval` 按方言建检索基础设施（SQLite FTS5 虚表 / PG tsvector 表 + GIN + 触发器），`app/db/fts.py` 提供两套 DDL。
- `env.py` 写入 `sqlalchemy.url` 前对 `%` 转义为 `%%`（ConfigParser 插值，M0-01），传给引擎/离线 SQL 的 URL 用原始值；`_include_name` 将 `knowledge_fts*` 排除出 autogenerate（双方言均由 raw SQL 管理）。

## 5. 前后端通信与前端结构

- 开发：Vite dev server 将 `/api` 代理到 `http://127.0.0.1:8000`，前端无跨域问题；后端配置 CORS 允许开发源。
- 前端 API 客户端集中在 `frontend/src/api/`，类型与后端响应结构对应。
- **按需加载（ZIP-04）**：`App.tsx` 以 `React.lazy` + 动态 import 拆分知识地图（React Flow + ELK，体积最大）与实验页（三 Runner），`Suspense` 兜底；默认对话页保持 eager。重依赖（elkjs / @xyflow/react）仅在切到对应页签时加载，显著降低首屏初始 JS（详见修复验收报告）。地图布局纯模块 `lib/graphLayout.ts` 不引 React Flow 运行时，便于 jsdom 单测。

## 6. 测试策略

- **knowledge-core**：纯单元测试，验证领域模型、接口契约与实现、Model Adapter 失败契约、混合检索、图装配、实验判分，以及独立性守护，不需要数据库与网络。
- **backend**：pytest + FastAPI TestClient，默认临时 SQLite 库验证配置、迁移、健康检查、检索、各 API。
- **PostgreSQL 集成测试**：`backend/tests/test_retrieval_pg.py` 经 `EXPLAINLAB_PG_TEST_URL` 门控，连真实 PG 实例执行真实在线迁移与检索验证（迁移 up/down、tsvector/触发器/级联、CJK 回退、向量、backfill、混合检索、方言分派）；未配置时整模块跳过。**离线 SQL 不等同于真实数据库验证。**
- **根级收集**：根 `pyproject.toml` 设 `testpaths` + `--import-mode=importlib` + `pythonpath`，一次性收集 backend + core 两个目录并化解同名模块冲突（ZIP-02）。
- **frontend**：Vitest + Testing Library，mock fetch 属于测试基建，产品代码不使用假数据；`npm run build` 含 `tsc -b` 类型检查与生产构建。
- **Lint**：仅 `ruff check`（含 `--fix` 修 import 排序），严禁 `ruff format`。

## 7. 里程碑演进

见 [MILESTONES.md](../MILESTONES.md)。V1.0（M0–M5）已完成；当前为 M0 准入修复与 M5 回归修复阶段，后续每个里程碑都必须遵守第 2 节的独立性约束与 AGENTS.md 的架构保护红线。