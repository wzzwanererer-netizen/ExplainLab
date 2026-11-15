# AGENTS.md — ExplainLab 工程规范

本文件是 ExplainLab 仓库的代理/开发者工作规范。任何自动化代理或人工在本仓库改动代码前，必须先阅读并遵守本文件。规范与 `MILESTONES.md`、`docs/architecture.md`、`docs/development.md` 共同构成项目约束；如有冲突，以本文件的架构保护与安全约束为准。

ExplainLab 是「对话式 AI 知识管理 + 交互式学习」平台。V1.0（M0–M5）已完成七项核心能力。当前处于 M0 准入修复与 M5 回归修复阶段，**未经独立审计批准不得进入 M1 之后的新里程碑开发**。

## 1. 仓库结构

```
ExplainLab/
├─ AGENTS.md                 # 本规范
├─ MILESTONES.md             # 里程碑台账
├─ pyproject.toml            # uv workspace 虚拟根 + 共享 ruff/pytest 配置
├─ uv.lock                   # Python 锁定文件（必须提交、保持一致）
├─ knowledge-core/           # 独立知识核心（纯 Python 包，可复用于 Nesti）
│  ├─ src/knowledge_core/
│  └─ tests/
├─ backend/                  # FastAPI API 层 + SQLAlchemy 持久化 + Alembic 迁移
│  ├─ app/
│  ├─ alembic/
│  ├─ tests/
│  └─ data/                  # SQLite 数据文件（gitignore，不提交）
├─ frontend/                 # React + Vite 单页应用
│  ├─ src/
│  └─ package-lock.json      # npm 锁定文件（必须提交、保持一致）
├─ docs/                     # architecture / development / plans / acceptance
└─ scripts/                  # setup.sh / setup.ps1 等本地启动脚本
```

## 2. 技术栈

- **Python**：3.11（审计基线 3.11.9）。包/环境管理用 **uv**（workspace，共享 `.venv`）。
- **后端**：FastAPI + Uvicorn + SQLAlchemy 2.x + Alembic + Pydantic v2 / pydantic-settings；PostgreSQL 驱动 `psycopg[binary]` 3.x（已在依赖中）。
- **知识核心**：纯 Python，仅依赖标准库 + Pydantic + httpx。
- **前端**：React 19 + TypeScript 7 + Vite 8 + Tailwind CSS v4；知识地图用 `@xyflow/react`（React Flow）+ `elkjs` 布局；测试用 Vitest + jsdom + Testing Library。
- **Node 基线**：**22.23.2**（`frontend/package.json` 的 `engines.node >= 22.23.2`）。README 与 docs 的 Node 版本须与此一致。
- **数据库**：开发默认 SQLite + FTS5；部署目标 PostgreSQL（见 §5）。
- **AI 模型**：经统一 Model Adapter 调用 OpenAI 兼容服务（生成 DeepSeek、向量 SiliconFlow 等），密钥仅存后端 `.env`。

## 3. 模块依赖方向（强制）

```
frontend  ──HTTP /api──▶  backend  ──Python import──▶  knowledge-core
```

- 依赖只能自上而下：`frontend → backend → knowledge-core`。**严禁反向依赖**。
- `knowledge-core` 不得 import `backend`、`frontend`、FastAPI、Starlette、SQLAlchemy 或任何 Web/ORM/前端库。
- `backend` 通过实现 `knowledge_core.ports` 的 Protocol 端口（SQLAlchemy 仓库）与注入 `ModelAdapter` 来驱动核心；核心业务逻辑不得搬到 backend，backend 只做 API/持久化/装配。
- `frontend` 只经 HTTP 与 backend 通信，不得直接引用 Python 核心。

## 4. Knowledge Core 独立性（强制）

- 核心是独立可复用包（未来用于 Nesti），不绑定 ExplainLab 特有概念（页面、路由、前端组件）。
- 外部能力一律经端口注入：持久化用 `ports.py` 的 `KnowledgeRepository / RelationRepository / VersionRepository / ReviewRepository / ExperimentRepository / FullTextIndex / VectorStore / Embedder`；模型用 `model_adapter.ModelAdapter`。
- 服务分层：`__init__.py` 定义抽象接口（ABC），同包实现文件提供具体类（如 `extraction.llm.LLMExtractionService`、`retrieval.hybrid.HybridRetrievalService`）。接口不可实例化。
- **独立性守护测试**：`knowledge-core/tests/test_interfaces.py::test_core_has_no_web_framework_dependency` 在干净子进程导入全部核心模块，断言不含 `fastapi/starlette/flask/django`。任何改动后此测试必须通过；不得删除或弱化它。
- 不得为图省事把数据库方言 SQL、HTTP 细节或前端逻辑写进核心。

## 5. 数据库开发与部署策略

- **开发默认**：SQLite，数据文件 `backend/data/explainlab.db`，全文检索用 FTS5（trigram）。`DATABASE_URL` 缺省即 SQLite。
- **部署目标**：PostgreSQL，经 `DATABASE_URL`（`postgresql+psycopg://...`）切换；Alembic 迁移须同时支持 SQLite 与 PostgreSQL。
- **方言边界（强制）**：SQLite 与 PostgreSQL 的差异（全文检索 FTS5 vs 原生 `tsvector/tsquery`、向量存储、类型映射）必须封装在 **backend 数据库适配层**（`app/db/`、`app/services/retrieval.py` 的方言实现）。**业务服务与核心不得出现方言特定 SQL**；PostgreSQL 路径不得使用 `FTS5 / MATCH / bm25 / rowid`。
- **检索实现现状（ZIP-01）**：SQLite 用 FTS5（trigram，bm25 排名，短查询 LIKE 回退）；PostgreSQL 用原生 `tsvector/tsquery` + GIN 索引 + 增改触发器、删除外键级联（`app/db/fts.py` 的 `PG_FTS_DDL`、`app/services/retrieval.py` 的 `PostgresFullTextIndex`），由 `build_full_text_index` 按方言分派。PG 的 `simple` 分词不对无空格中文成词，此类查询无 tsvector 命中时回退 `ILIKE` 子串匹配（真实匹配，**已记录局限**，非造假）。向量存储为双方言通用的 JSON 文本 + Python 余弦（`JsonVectorStore`，不依赖 pgvector）。
- **迁移**：所有 schema 变更走 Alembic（`backend/alembic/versions/`），必须可 `upgrade` 与 `downgrade`。Alembic `env.py` 写入 `sqlalchemy.url` 前须对 `%` 转义为 `%%`（ConfigParser 插值），但传给引擎/离线 SQL 的 URL 用原始值。
- **类型约定**：UUID 存 `String(36)`；时间用 UTC；JSON 负载以 Text 存储以兼容双方言；SQLite 连接须 `PRAGMA foreign_keys=ON`。
- **真实验证**：涉及数据库的功能必须用真实数据库测试（SQLite 必测；PostgreSQL 须连真实实例验证迁移与检索）。**离线生成 SQL 不等同于真实数据库验证；不得用假数据替代真实数据库测试；不得虚报 PostgreSQL 连接成功。** 若环境无 PostgreSQL，先报告并等待批准，不得伪造通过。

## 6. Model Adapter 规范

- 业务代码只依赖 `ModelAdapter` 接口与公共异常契约，**不依赖任何供应商 SDK**。
- 已实现 `OpenAICompatibleAdapter`（DeepSeek/通义/Kimi/智谱/OpenAI 等）。`base_url` **原样直连**，`trust_env=False`，**严禁替换为 routify 等任何临时代理地址**；每次调用须重新核对目标 URL 来源。
- **公共失败契约**（`model_adapter/errors.py`，所有供应商适配器统一遵守）：
  - 可重试：`ModelTimeoutError`、`ProviderUnavailableError`、`RateLimitError`。
  - 不可重试：`AuthenticationError`、`MalformedResponseError`、`CapabilityNotSupportedError`、基类 `ModelAdapterError`。
  - 全部继承 `ModelAdapterError`；`is_retryable(exc)` 统一判定。
- **能力声明诚实**：`capabilities()` 只声明真正支持的能力。当前为 `GENERATE` + `EMBED`；`STREAM` 未实现，不得虚假声明。
- **密钥安全**：API Key 仅存后端 `.env`，经 `SecretStr` 配置注入；核心与前端不得持有/序列化/打印真实密钥；日志不得输出密钥或完整异常文本（见 §9）。

## 7. 测试规则

- **Python**：`pytest`（backend + knowledge-core）。根 `pyproject.toml` 已设 `testpaths=["backend/tests","knowledge-core/tests"]`、`asyncio_mode="auto"`。
  - 根目录 `pytest` 必须能一次性收集并通过两个测试目录；**不得用排除整个测试目录的方式掩盖收集冲突**。ZIP-02 已用 `--import-mode=importlib` 通用化解 `backend/tests` 与 `knowledge-core/tests` 的同名模块冲突，并以 `pythonpath=["knowledge-core/tests"]` 保留核心测试的 `from helpers import` 顶层导入。
  - 根 `addopts="-q --import-mode=importlib"`。**需要完整汇总时用 `uv run pytest -o addopts="--import-mode=importlib"`（保留 importlib、仅去掉 `-q`）；切勿用 `-o addopts=""`——那会关闭 importlib 并重新引发同名模块收集冲突。**
  - **PostgreSQL 集成测试**：`backend/tests/test_retrieval_pg.py` 经 `EXPLAINLAB_PG_TEST_URL` 门控——未设置时整模块跳过（默认 SQLite 套件不受影响）；设置后连真实 PG 实例执行真实在线迁移与检索验证（迁移 up/down、tsvector/触发器/级联、CJK 回退、向量、混合检索）。
- **前端**：`npm run test`（Vitest）、`npm run typecheck`（`tsc -b`）、`npm run build`。
- **Lint**：`uv run ruff check`。**只允许 `ruff check`（含 `--fix` 修 import 排序 I001），严禁 `ruff format`**——format 会重排已提交文件造成无关漂移。
- **锁定安装**：后端 `uv sync --locked`（默认含 dev/test 依赖组），前端 `npm ci`（要求 `package-lock.json` 与 `package.json` 一致）。`uv.lock` 与 `package-lock.json` 必须提交并保持同步。
- **干净副本验证**：宣称安装/构建通过前，须在不含预存 `node_modules`/`.venv` 的干净副本中从零安装验证，不得只复用现有环境。
- **不得删除已有有效测试**；不得为凑通过而弱化断言。真实功能用真实数据/真实模型/真实数据库验证，禁止假数据冒充。
- 每批改动后运行相关测试（backend + core + frontend + ruff），发现回归立即修复。

## 8. Git 工作规则

- **不得修改 M0 初始提交**，不得重写已推送历史。修复在专用分支进行（如 `fix/m0-admission-and-m5-regressions`）。
- 提交前确认工作树状态；**不得覆盖未提交的他人改动**；发现与审计目标不一致先报告。
- 提交信息遵循仓库既有风格（里程碑/修复语义清晰）。按里程碑或修复批次提交，附验收证据。
- **严禁提交敏感文件**：`backend/.env`（含真实密钥）、`*.db` 数据文件、`node_modules/`、`.venv/` 均 gitignore，不得入库。
- 不擅自 `push --force`、`reset --hard`、`checkout --` 等破坏性操作；不跳过 hooks（`--no-verify`）；未经用户明确要求不提交、不推送。

## 9. 安全与脱敏（强制）

- 真实密钥（DeepSeek `MODEL_API_KEY`、SiliconFlow `EMBED_API_KEY` 等）仅存 `backend/.env`，**绝不**向用户/聊天/前端/日志暴露其值。
- 配置用 `SecretStr` 承载密钥，序列化（`model_dump_json`/`repr`）自动掩码；读取用 `.get_secret_value()`。
- 对外错误响应（如健康检查）只返回**稳定错误码**（如 `database_unavailable`/`database_timeout`），不得回传 `str(exc)`、主机/端口/密码/异常堆栈文本；服务端日志只记异常类型等脱敏信息。
- 模型请求直连调用方真实 `base_url`，不做任何代理替换。

## 10. 里程碑验收规则

- 执行方法：**计划确认 → 开发 → 真实运行 → 验收报告 + 更新 MILESTONES + 提交**。
- 每个里程碑/修复批次须产出可核验证据：真实测试输出、真实模型联调、必要时浏览器截图（in-app Browser：bringToFront、fullPage 超时则 viewport+重试、urllib UTF-8 取证）。
- 验收报告落 `docs/acceptance/`，如实区分「已验证 / 有条件 / 未通过」，不得把规划写成已完成，不得把离线 SQL 等同于真实数据库验证。
- **不得自行宣布进入下一里程碑**；修复完成后停止并等待独立审计。

## 11. 架构保护红线（本轮修复）

1. 不重写 Knowledge Core；不使其耦合 UI；核心不依赖 FastAPI/React。
2. 业务逻辑不写数据库方言 SQL；方言差异封装在数据库适配层。
3. 不删除已有有效测试；不修改 M0 初始提交。
4. 不擅自增加大型技术依赖（PostgreSQL 驱动 psycopg 已在依赖中）。
5. 不用假数据替代真实数据库测试；不虚报 PostgreSQL 成功；不把离线 SQL 当真实验证。
6. 不进入 M1 之后的新里程碑开发；本轮只做修复/测试/文档同步。

## 12. 常用命令

```bash
# 安装（锁定）
uv sync --locked                 # 后端 + 核心，含 dev/test 组
cd frontend && npm ci            # 前端

# 测试与检查
uv run pytest -o addopts="--import-mode=importlib"   # 根级一次性收集 backend + core（完整汇总，保留 importlib）
uv run ruff check                # 仅 check，禁止 format
cd frontend && npm run test && npm run typecheck && npm run build

# 本地启动（见 scripts/ 与 docs/development.md）
# 后端：uv run uvicorn app.main:app --reload   （在 backend/ 下）
# 前端：npm run dev                            （在 frontend/ 下，http://localhost:5173）

# 迁移（在 backend/ 下）
uv run alembic upgrade head
```