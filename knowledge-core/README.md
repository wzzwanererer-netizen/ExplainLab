# knowledge-core

ExplainLab 的独立知识核心包。V1.0（M0–M5）已落地完整业务实现，可脱离 Web 服务与前端纯 Python 调用，未来复用于 Nesti。

## 独立性约束

- 不依赖 FastAPI / Starlette 等 Web 框架，不依赖前端。
- 仅依赖 Python 标准库、Pydantic 与 httpx（httpx 仅用于 Model Adapter 的 OpenAI 兼容 HTTP 调用）。
- 外部能力（数据库持久化、模型供应商）通过 `ports.py` 的 Protocol 端口与 `model_adapter` 接口注入，核心不绑定任何具体数据库或供应商 SDK。
- 知识提取、关系管理、版本管理、来源追溯、审核、检索、知识地图、交互式实验均可纯 Python 调用。
- 禁止引入 ExplainLab 特有概念（如具体页面、HTTP 路由、前端组件）。
- 独立性由 `tests/test_interfaces.py::test_core_has_no_web_framework_dependency` 守护：在干净子进程中导入全部核心模块，断言不含 `fastapi/starlette/flask/django`。

## 分层约定：抽象接口 vs 具体实现

各服务模块遵循统一分层——`__init__.py` 定义抽象接口（ABC），同包内的实现文件提供具体类。接口不可直接实例化（由 `tests/test_interfaces.py` 契约测试守护），应用层注入具体实现：

| 模块 | 抽象接口 | 具体实现 | 状态 |
|---|---|---|---|
| `domain` | —（纯 Pydantic 领域实体） | `entities.py`：KnowledgeItem / KnowledgeRelation / KnowledgeVersion / SourceRef / ReviewRequest 等 | 已实现 |
| `extraction` | `ExtractionService` | `llm.LLMExtractionService`（经 Model Adapter 提取） | 已实现 |
| `relations` | `RelationService` + `DuplicateMatch` | `llm.LLMRelationService`（模型判定）+ `lexical`（词面召回纯函数） | 已实现 |
| `versioning` | `VersionService` | `service.RepositoryVersionService`（基于仓库端口） | 已实现 |
| `provenance` | `ProvenanceService` | `service.RepositoryProvenanceService`（基于仓库端口） | 已实现 |
| `review` | —（具体编排） | `ReviewPolicy`（重要变更判定）+ `ReviewService`（提交/批准/驳回） | 已实现 |
| `retrieval` | `RetrievalService` + `SearchResult` | `hybrid.HybridRetrievalService`（全文+向量双通道，RRF 融合） | 已实现 |
| `graph` | —（具体服务） | `service.KnowledgeGraphService`（产出无坐标图数据，布局交前端） | 已实现 |
| `experiments` | —（具体服务 + 实体） | `ExperimentService` / `LLMQuizService` / `LLMCompareService` / `ChainService`（测验/对比/学习路径，服务端判分） | 已实现 |
| `model_adapter` | `ModelAdapter`（ABC）+ 公共失败契约 | `providers.OpenAICompatibleAdapter` + `AdapterRegistry`（注册工厂） | 已实现 |
| `services` | —（门面） | `KnowledgeService`（提取入库 + 条目分析编排） | 已实现 |
| `parsing` | —（共享工具） | `strip_fence` / `extract_json`（模型输出健壮解析，失败返回 None 不造假） | 已实现 |
| `ports` | Protocol 端口（设计即抽象） | 由应用层（backend SQLAlchemy 等）实现注入 | 接口 |

`ports.py` 定义的端口：`KnowledgeRepository`、`RelationRepository`、`VersionRepository`、`ReviewRepository`、`ExperimentRepository`、`FullTextIndex`、`VectorStore`、`Embedder`。这些端口是核心与持久化/模型能力的唯一边界，**故意保持抽象**，不属于"未实现"。

## Model Adapter

- 业务代码只依赖 `ModelAdapter` 接口与公共异常契约，不依赖任何供应商 SDK。
- 已实现 `OpenAICompatibleAdapter`，适配 DeepSeek / 通义 / Kimi / 智谱 / OpenAI 等 OpenAI 兼容服务；`base_url` 原样直连，`trust_env=False` 不读取环境代理。
- 公共失败契约（`model_adapter/errors.py`）：`ModelTimeoutError` / `ProviderUnavailableError` / `RateLimitError` 可重试；`AuthenticationError` / `MalformedResponseError` / `CapabilityNotSupportedError` 不可重试；`is_retryable()` 统一判定。
- 能力声明诚实：当前 `capabilities()` 仅声明 `GENERATE` 与 `EMBED`，未实现 `STREAM` 不得虚假声明。
- 密钥仅由应用层后端注入，核心不持有、不序列化任何真实密钥。

## 测试

```bash
uv run pytest knowledge-core/tests -o addopts="--import-mode=importlib"
```

覆盖领域实体、各服务接口契约与实现、Model Adapter 失败契约、混合检索、图装配、实验判分，以及核心独立性守护。详见仓库根目录 `AGENTS.md` 与 `MILESTONES.md`。