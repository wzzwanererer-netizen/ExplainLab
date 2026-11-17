# ExplainLab V1.0 — M0 准入修复与 M5 回归修复 验收报告

- **日期**：2026-11-15
- **依据**：《ExplainLab M0 独立技术审计报告》（2026-11-15）+ 本轮修复任务书
- **分支**：`fix/m0-admission-and-m5-regressions`
- **基线提交**：`59068e2`（M5，V1.0 七能力完成态，即审计 ZIP 对应代码）
- **M0 初始提交**：`2d2b634`（**完整保留，未重写历史**）
- **范围**：仅修复 / 测试 / 文档同步（M0-01–07 准入项 + ZIP-01–04 回归项）。**未进入 M1 之后任何新里程碑开发。**

---

## 结论（先行）

**本修复批次：全部通过。** M0-01–07 七项准入修复与 ZIP-01–04 四项回归修复全部完成，并以**真实运行**验证（真实 PostgreSQL 16.8 实例、干净副本从零锁定安装、真实浏览器懒加载实测）。存在两处**已如实记录的已知局限**（PostgreSQL 中文分词回退、elkjs 懒加载块体积警告），均非造假、不阻断本批次验收，详见第 14 节。

**审计移交声明**：本报告不自行宣布进入 M1。修复已完成，**停止并等待独立审计**。是否准入下一里程碑由独立审计裁定。

### 逐项状态总览

| 项 | 内容 | 状态 | 关键证据 |
|---|---|---|---|
| M0-01 | Alembic 百分号编码 URL | ✅ 已验证 | `test_alembic_url.py` 6 通过 |
| M0-02 | 健康接口脱敏 + SecretStr | ✅ 已验证 | `test_health.py` 6 通过 |
| M0-03 | Node 22.23.2 基线 | ✅ 已验证 | engines + README + development.md 一致 |
| M0-04 | Model Adapter 公共失败契约 | ✅ 已验证 | 契约 14 + 适配器 15 通过 |
| M0-05 | 锁定安装 + 干净副本 | ✅ 已验证 | 干净副本 `uv sync --locked`/`npm ci` 从零成功 |
| M0-06 | AGENTS.md + 核心文档分层 | ✅ 已验证 | AGENTS.md 新建；README/`__init__` 同步 |
| M0-07 | 配置路径与空值 | ✅ 已验证 | `test_config.py` 15 通过 |
| ZIP-01 | PG/SQLite 检索方言适配 | ✅ 已验证（附局限） | 真实 PG `test_retrieval_pg.py` 12 通过 |
| ZIP-02 | 根级 pytest 收集冲突 | ✅ 已验证 | 根级一次性收集 258+12 |
| ZIP-03 | 文档与真实架构同步 | ✅ 已验证 | architecture/development/README/AGENTS |
| ZIP-04 | 前端按需加载与包体积 | ✅ 已验证（附局限） | 初始 JS −86.8%；真实浏览器实测 |

---

## 1. 改动文件清单

本批次共 **32 个已跟踪文件修改 + 4 个新增源码/测试文件 + 本报告 + MILESTONES.md 更新**。`release/ExplainLab-V1.0-review.zip`（审计打包产物，3.1 MB）**不入库**；`backend/.env`、`*.db`、`node_modules/`、`.venv/` 均 gitignore，未提交。

### 后端（backend/）

| 文件 | 关联项 | 改动性质 |
|---|---|---|
| `alembic/env.py` | M0-01 | `set_main_option` 前 `%`→`%%` 转义；引擎/离线 SQL 用原始 URL；不打印密码 |
| `alembic/versions/0004_m3_retrieval.py` | ZIP-01 | 按方言分支：SQLite FTS5 虚表；PG 原生 `tsvector`+GIN+触发器+级联 |
| `app/api/routes/health.py` | M0-02 | 稳定错误码 `database_timeout`/`database_unavailable`；日志仅记异常类型名 |
| `app/core/config.py` | M0-02/07 | `SecretStr` 密钥；`BACKEND_DIR` 锚定；空串→None；相对 SQLite 路径锚定 |
| `app/db/fts.py` | ZIP-01 | 新增 `PG_FTS_DDL`（knowledge_fts 表/GIN/触发器函数） |
| `app/services/model.py` | M0-04 | 适配层装配遵守公共失败契约 |
| `app/services/retrieval.py` | ZIP-01 | `PostgresFullTextIndex`、`JsonVectorStore`、方言工厂、ILIKE 回退 JOIN 索引 |
| `tests/test_config.py` | M0-07 | 路径锚定/空值/掩码回归（15 用例） |
| `tests/test_health.py` | M0-02 | 脱敏/稳定码/超时回归（6 用例） |
| `tests/test_alembic_url.py` | M0-01 | **新增**：百分号 URL 离线迁移（6 用例） |
| `tests/test_retrieval_pg.py` | ZIP-01 | **新增**：真实 PG 门控集成测试（12 用例） |

### 知识核心（knowledge-core/）

| 文件 | 关联项 | 改动性质 |
|---|---|---|
| `src/knowledge_core/model_adapter/errors.py` | M0-04 | 公共失败契约（可重试/不可重试 + `is_retryable`） |
| `src/knowledge_core/model_adapter/base.py` | M0-04 | 能力枚举 + `ModelAdapter` ABC |
| `src/knowledge_core/model_adapter/__init__.py` | M0-04 | 契约导出 |
| `src/knowledge_core/model_adapter/providers/openai_compatible.py` | M0-04 | 底层故障→公共异常映射；`trust_env=False`；能力诚实 |
| `src/knowledge_core/ports.py` | ZIP-01/03 | `FullTextIndex`/`VectorStore` 端口文档同步双方言实现 |
| `src/knowledge_core/__init__.py` | M0-06 | 导出/文档 |
| `src/knowledge_core/{provenance,relations,retrieval,versioning}/__init__.py` | M0-06 | 抽象接口 vs 具体实现分层说明 |
| `tests/test_model_adapter_contract.py` | M0-04 | **新增**：假供应商故障契约（14 用例） |
| `tests/test_openai_adapter.py` | M0-04 | 故障映射/能力诚实/无代理回归（15 用例） |
| `README.md` | M0-06/ZIP-03 | V1.0 已实现模块表 + 测试命令 importlib |

### 前端（frontend/）

| 文件 | 关联项 | 改动性质 |
|---|---|---|
| `src/App.tsx` | ZIP-04 | `React.lazy`+`Suspense` 懒加载 KnowledgeMap / ExperimentsView |
| `package.json` | M0-03 | `engines.node >= 22.23.2` |
| `package-lock.json` | M0-03/05 | 与 package.json 一致（锁定） |

### 根 / 文档 / 脚本

| 文件 | 关联项 | 改动性质 |
|---|---|---|
| `AGENTS.md` | M0-06/ZIP-02/03 | **新增**工程规范；§5 检索现状、§7 importlib+PG 门控、§12 命令 |
| `pyproject.toml` | ZIP-02 | `--import-mode=importlib` + `pythonpath` + `testpaths` |
| `README.md` | ZIP-03 | 「规划」→「V1.0 已实现」；DB/AI 行同步 |
| `docs/architecture.md` | ZIP-03 | 全文重写为真实 V1.0 架构 |
| `docs/development.md` | ZIP-03 | 配置表/切换 PG/测试命令同步 |
| `scripts/setup.ps1` `setup.sh` `dev.ps1` `test.ps1` | M0-05 | 锁定安装；PS1 加 UTF-8 BOM 防中文乱码 |
| `MILESTONES.md` | 本轮 | 追加修复批次台账 |
| `docs/acceptance/M0-M5-REMEDIATION-REPORT.md` | 本轮 | **本报告（新增）** |

---

## 2. 逐项修复说明

### M0-01 · Alembic 百分号编码 URL

**问题**：Alembic `Config.set_main_option` 经 ConfigParser 插值，URL 中 `%`（如密码 `p%40ss`）被误解析，迁移报错。
**修复**：`backend/alembic/env.py` 在 `set_main_option("sqlalchemy.url", ...)` 前将 `%` 转义为 `%%`；传给 `create_engine`/离线 SQL 的 URL 用**原始值**；日志不输出含密码的 URL。
**验证**：`test_alembic_url.py` 6 用例——4 个 PG URL 变体（`pass`/`p%40ss`/`p%25ss`/`p%40%25ss`）离线迁移 + SQLite 离线迁移 + 百分号经 ConfigParser 往返。全部通过。

### M0-02 · 健康接口脱敏 + SecretStr

**问题**：健康检查对外回传 `str(exc)` 可能泄露主机/端口/密码/DSN。
**修复**：`health.py` 吞掉所有连接异常，对外只返回稳定码 `database_timeout`（`TimeoutError`/`PoolTimeoutError`）或 `database_unavailable`；服务端日志仅记 `type(exc).__name__`，不记消息文本。`config.py` 密钥用 `SecretStr`，序列化自动掩码。
**验证**：`test_health.py` 6 用例（正常/不可达/超时/已配置供应商/稳定码/不泄敏感）+ `test_config.py` 掩码用例。全部通过。

### M0-03 · Node 22.23.2 基线

**修复**：`frontend/package.json` 声明 `engines.node >= 22.23.2`；`README.md`「Node.js ≥ 22.23.2（审计复现基线 22.23.2）」；`docs/development.md` 基线表与兼容性说明一致。
**验证**：三处文本一致（grep 核验）；干净副本以该基线 `npm ci`+构建+测试通过。

### M0-04 · Model Adapter 公共失败契约

**修复**：`model_adapter/errors.py` 定义统一契约——基类 `ModelAdapterError(retryable=False)`；可重试 `ModelTimeoutError`/`ProviderUnavailableError`/`RateLimitError`；不可重试 `AuthenticationError`/`MalformedResponseError`/`CapabilityNotSupportedError`/`AdapterNotFoundError`/`AdapterAlreadyRegisteredError`；`is_retryable()` 统一判定。`OpenAICompatibleAdapter` 把底层 httpx/HTTP 故障映射到公共异常；`capabilities()` 仅声明 `GENERATE`+`EMBED`，**不虚假声明 STREAM**；`trust_env=False` 不读环境代理，`base_url` 原样直连。
**验证**：`test_model_adapter_contract.py` 14（假供应商：正常/超时/不可用/能力不支持/格式错误/STREAM 不声明/7 类重试分类/非适配异常）+ `test_openai_adapter.py` 15（请求形状/模型覆盖/HTTP 错误/格式错误/embed 排序/无代理/超时·网络·5xx·429·401·非法 JSON 映射/能力不声明 STREAM）。全部通过。

### M0-05 · 锁定安装 + 干净副本验证

**修复**：`scripts/setup.ps1`/`setup.sh` 用 `uv sync --locked` + `npm ci` + `alembic upgrade head`；`dev.ps1`/`test.ps1` 同步；PS1 加 UTF-8 BOM 防 PowerShell 5.1 GBK 乱码。
**验证**：见第 6、7 节——干净副本 `D:\ExplainLab-cleancheck`（删除预存 `.venv`/`node_modules`，同步最终源码）从零锁定安装成功并全量测试/构建通过。

### M0-06 · AGENTS.md + 核心文档分层

**修复**：新建根 `AGENTS.md`（仓库结构/技术栈/依赖方向/核心独立性/数据库策略/Model Adapter/测试/Git/安全/验收/架构红线/命令）。`knowledge-core/README.md` 与各服务 `__init__.py` 明确「`__init__.py` 抽象接口（ABC）vs 同包具体实现」分层，端口故意保持抽象（非未实现）。
**验证**：文档与真实代码一致；`test_interfaces.py` 守护接口不可实例化 + 核心无 Web 框架依赖。

### M0-07 · 配置路径与空值

**修复**：`config.py` `BACKEND_DIR=parents[2]`，`.env` 与默认 SQLite 数据文件锚定 backend 目录（绝对路径），无论从根或 backend 启动都加载同一 `.env`、指向同一库；空串/纯空白模型字段→None；`_normalize_database_url` 将相对 SQLite 路径锚定 backend，`:memory:`/绝对/非 SQLite 原样保留。
**验证**：`test_config.py` 15 用例（默认 SQLite/PG URL/env 覆盖/未配置/缓存/掩码/未设密钥/.env 锚定/绝对路径锚定/相对路径独立于 cwd/空模型串/空 DB URL 回退/memory 保留/绝对保留/引擎建数据目录）。全部通过。

### ZIP-01 · PostgreSQL/SQLite 检索方言适配（最重要）

**问题**：原 M3 检索仅 SQLite FTS5，PG 路径缺失/误用方言。
**修复**（方言差异全部封装在 backend 数据库适配层，业务服务与核心无方言 SQL）：
- `0004_m3_retrieval.py` 按方言分支：SQLite 建 FTS5 虚表（trigram）；PG 建 `knowledge_fts(item_id PK FK CASCADE, tsv tsvector)` + GIN 索引 `knowledge_fts_tsv_idx` + plpgsql 触发器函数 `knowledge_fts_sync()` + `AFTER INSERT/UPDATE OF title,content` 触发器；删除经外键级联。
- `app/db/fts.py` 新增 `PG_FTS_DDL`；`app/services/retrieval.py` 新增 `PostgresFullTextIndex`（`tsvector`/`plainto_tsquery`/`ts_rank`，rank 取负与 SQLite bm25 约定一致），`JsonVectorStore`（双方言通用 JSON+Python 余弦，不依赖 pgvector），`build_full_text_index`/`build_vector_store` 按 `dialect.name` 分派。
- **PG 路径不使用 `FTS5/MATCH/bm25/rowid`**。`simple` 分词不对无空格中文成词，此类查询无 tsvector 命中时回退 `ILIKE` 子串匹配，且 **JOIN `knowledge_fts` 限定已索引集合**（使 remove 后回退同样不再命中，与主路径成员资格语义一致）。
**验证**：真实 PG 16.8 实例 `test_retrieval_pg.py` 12 用例全过（见第 5 节）。**离线 SQL 不等同真实验证——本项以真实在线迁移与检索为准。**

### ZIP-02 · 根级 pytest 收集冲突

**问题**：`backend/tests` 与 `knowledge-core/tests` 同名模块在根级一次性收集时冲突。
**修复**：根 `pyproject.toml` 设 `addopts="-q --import-mode=importlib"`、`pythonpath=["knowledge-core/tests"]`（保留核心 `from helpers import`）、`testpaths=["backend/tests","knowledge-core/tests"]`。**未排除任何整个测试目录**，覆盖完整保留。
**验证**：根级 `uv run pytest -o addopts="--import-mode=importlib"` 一次性收集 258 通过 + 12 PG 门控跳过；含真实 PG 270 通过。**纠正了 AGENTS.md 中有害的 `-o addopts=""` 旧建议**（那会关闭 importlib 重新引发冲突）。

### ZIP-03 · 文档与真实架构同步

**修复**：`docs/architecture.md` 全文重写为真实 V1.0（七视图/懒加载/方言适配/核心具体服务/端口抽象/Model Adapter 契约/迁移 0001–0005/测试策略）；`docs/development.md`（配置表/切换 PG/百分号/方言自动分派/CJK 局限/测试命令）；`README.md`（「规划」→「V1.0 已实现」+ 状态注记）；`knowledge-core/README.md`；`AGENTS.md` §5/§7/§12。**不将规划写成已完成**；历史 M3-plan/M3-report 的 pg_trgm 记述作为历史记录保留，新文档如实记录最终 tsvector 选择。

### ZIP-04 · 前端按需加载与包体积

**修复**：`App.tsx` 用 `React.lazy`+动态 `import()` 懒加载 `KnowledgeMap`、`ExperimentsView`（命名导出经 `.then(m=>({default:m.X}))`），主内容包 `Suspense`（`role="status"` 加载提示）。ChatView/KnowledgeView/SearchView/ReviewQueue/HealthPanel 保持即时加载，七页签功能不减。
**验证**：初始 JS **1,937.83 kB → 256.45 kB（−86.8%）**，gzip **600.17 → 78.26 kB（−87.0%）**；真实浏览器实测（见第 6 节）。elkjs 自动拆为独立 `graphLayout` 懒加载块。

---

## 3. 迁移测试证据

- **SQLite**：`backend/tests/test_migrations.py::test_upgrade_head_creates_version_table` 通过；默认套件含真实 SQLite 在线迁移。
- **百分号 URL 离线迁移**：`test_alembic_url.py` 6 通过（M0-01）。
- **真实 PostgreSQL 在线迁移**：`test_retrieval_pg.py::test_pg_migration_creates_native_fts`（`information_schema` 断言 `tsv` 列 `data_type='tsvector'`、GIN 索引存在、向量表列就绪）+ `test_pg_migration_downgrade_and_upgrade`（真实 downgrade 至 `0003_m2_governance` 删除 fts/vector，再 upgrade head 恢复）。
- 迁移 0001→0005 在真实 PG 16.8 实跑 `command.upgrade(cfg,"head")`，up/down 均真实执行，**非离线 SQL 生成**。

## 4. SQLite 测试证据

- 默认根级套件（SQLite + FTS5 trigram/bm25/短查询 LIKE 回退）：**258 passed, 12 skipped**（跳过者为 PG 门控集成测试）。
- 检索方言分派 `test_pg_dialect_dispatch` 同时校验 SQLite 分支返回 `SQLiteFullTextIndex`。
- 向量 `JsonVectorStore` 双方言通用，SQLite 路径余弦检索随默认套件通过。

## 5. 真实 PostgreSQL 连接与迁移证据

- **实例**：本地便携 PostgreSQL **16.8**（`D:\ExplainLab-pg\pgsql`，数据 `D:\ExplainLab-pg\data`，端口 55432，库 `explainlab_test`，127.0.0.1，trust）。驱动 `psycopg 3.3.9`。
- **连通预检**：`psycopg.connect(...)` → `PostgreSQL 16.8, compiled by V...`（真实连接成功，**非虚报**）。
- **门控**：`EXPLAINLAB_PG_TEST_URL=postgresql+psycopg://postgres@127.0.0.1:55432/explainlab_test`；未设置时整模块跳过（默认 SQLite 套件不受影响）。
- **12 用例全过**：原生 FTS 迁移内省、downgrade/upgrade、INSERT 触发器+tsvector 检索、UPDATE 触发器刷新 tsv、DELETE 级联、upsert 索引重写（`tsv @@ plainto_tsquery` 布尔证明）+remove backfill、CJK 子串 ILIKE 回退、向量余弦、reindex 全量 backfill、sync_index/remove、hybrid 端到端、方言分派。
- **含真实 PG 全量**：根级 `uv run pytest -o addopts="--import-mode=importlib"` → **270 passed**（258 + 12 PG）。

## 6. 前端干净安装 + 构建证据

**干净副本**（`D:\ExplainLab-cleancheck`，删除预存 `node_modules`，同步最终源码，锁文件与主副本逐字节一致）：

- `npm ci`：`added 128 packages, audited 135 packages`，**found 0 vulnerabilities**，exit 0。
- `npm run test`（Vitest）：**72 passed（10 文件）**。
- `npm run build`（`tsc -b && vite build`，Vite 8.3.8 / rolldown）：

| 产物 | 大小 | gzip | 加载时机 |
|---|---|---|---|
| `index.html` | 0.48 kB | 0.30 kB | 初始 |
| `index-*.css` | 23.91 kB | 5.41 kB | 初始 |
| `rolldown-runtime-*.js` | 0.98 kB | 0.56 kB | 初始 |
| **`index-*.js`（初始入口）** | **256.45 kB** | **78.26 kB** | **初始** |
| `KnowledgeMap-*.css` | 15.41 kB | 2.56 kB | 懒（打开地图） |
| `KnowledgeMap-*.js` | 188.53 kB | 61.28 kB | 懒（打开地图） |
| `ExperimentsView-*.js` | 26.67 kB | 7.45 kB | 懒（打开实验） |
| `graphLayout-*.js`（elkjs） | 1,464.73 kB | 453.05 kB | 懒（打开地图） |

- **初始 JS 对比**：1,937.83 kB → **256.45 kB（−86.8%）**；gzip 600.17 → **78.26 kB（−87.0%）**。主副本与干净副本构建产物**同哈希一致**。
- **警告（如实记录）**：`graphLayout`（elkjs）块 >500 kB 警告仍在，但已落在**懒加载块**（仅打开知识地图时加载），**不在初始包**。详见第 14 节。
- **真实浏览器懒加载实测**（in-app Browser，`evaluate_script`+Performance API+`wait_for`+`take_snapshot`；面板隐藏 viewport 0×0 故无截图，以 Performance/DOM/a11y 取证）：初始 23 个资源**不含 elkjs/xyflow**；点击「地图」页签新增约 10 个资源（elkjs/xyflow/KnowledgeMap 块）并真实渲染 2 节点 1 边；点击「实验」加载其模块。功能未减。

## 7. Python 干净安装 + 测试证据

**干净副本**（删除预存 `.venv`，同步最终源码，`uv.lock` 与主副本逐字节一致）：

- `uv sync --locked`：从零创建 `.venv` 并安装全部锁定依赖（含 dev/test 组），exit 0。
- `uv run pytest -o addopts="--import-mode=importlib"`：**258 passed, 12 skipped**。
- `uv run ruff check`：**All checks passed!**
- 主副本本轮另以真实 PG 重跑全量：**270 passed**；核心单独 `knowledge-core/tests`：**136 passed**。

## 8. 根级 pytest 收集证据（ZIP-02）

- 命令：`uv run pytest -o addopts="--import-mode=importlib"`（保留 importlib，仅去 `-q` 取完整汇总）。
- 一次性收集 `backend/tests` + `knowledge-core/tests`，**无同名模块冲突**，**未排除任何整个测试目录**。
- 默认：**258 passed, 12 skipped**；含真实 PG：**270 passed**。
- `pythonpath=["knowledge-core/tests"]` 保留核心 `from helpers import` 顶层导入。
- **切勿用 `-o addopts=""`**（会关闭 importlib 重新引发冲突）——AGENTS.md §7/§12 已纠正。

## 9. Model Adapter 故障契约测试证据（M0-04）

- `knowledge-core/tests/test_model_adapter_contract.py`：**14 通过**（假供应商正常响应；超时→可重试；不可用→可重试；能力不支持→不可重试；格式错误→不可重试；STREAM 不声明；`ModelTimeoutError`/`ProviderUnavailableError`/`RateLimitError`=True、`AuthenticationError`/`MalformedResponseError`/`CapabilityNotSupportedError`/`ModelAdapterError`=False 分类；非适配异常不可重试）。
- `knowledge-core/tests/test_openai_adapter.py`：**15 通过**（请求形状/模型覆盖与 max_tokens/HTTP 错误/格式错误/embed 按 index 排序/空 embed/embed 模型/忽略环境代理与 IPv6 no_proxy/超时·网络·5xx·429·401·非法 JSON 映射/能力不声明 STREAM）。
- 业务代码只依赖 `ModelAdapter` 接口与公共异常契约，不依赖任何供应商 SDK。

## 10. 健康接口脱敏测试证据（M0-02）

- `backend/tests/test_health.py`：**6 通过**——`test_health_ok`、`test_health_degraded_when_db_unreachable`、`test_health_reports_configured_provider`、`test_health_timeout_returns_stable_code`、`test_health_unavailable_returns_stable_code`、`test_health_error_does_not_leak_sensitive_details`。
- 对外仅稳定码（`database_timeout`/`database_unavailable`），**不回传 `str(exc)`/主机/端口/密码/堆栈**；服务端日志仅记异常类型名。
- `test_config.py::test_secret_keys_masked_in_serialization`/`test_secret_keys_absent_when_unset` 验证 `SecretStr` 掩码。

## 11. Knowledge Core 独立性回归证据

- `knowledge-core/tests/test_interfaces.py`：**6 通过**——5 个服务接口不可实例化（`ExtractionService`/`RelationService`/`VersionService`/`ProvenanceService`/`RetrievalService`）+ **`test_core_has_no_web_framework_dependency`**（干净子进程导入全部核心模块，断言不含 `fastapi/starlette/flask/django`）。
- 守护测试**未删除、未弱化**；核心仅依赖标准库+Pydantic+httpx；外部能力经 `ports.py` Protocol 与 `ModelAdapter` 注入。
- 核心单独套件 **136 passed**。

## 12. 文档更新清单（ZIP-03 / M0-06）

| 文档 | 更新要点 |
|---|---|
| `AGENTS.md`（新建） | 工程规范全文；§5 检索现状（ZIP-01）、§7 importlib+PG 门控（ZIP-02）、§12 命令纠正 |
| `docs/architecture.md` | 全文重写为真实 V1.0：七视图/懒加载/方言适配层/核心具体服务/端口抽象/Model Adapter 契约/迁移 0001–0005/测试策略 |
| `docs/development.md` | 配置表（绝对锚定默认/SecretStr）、切换 PG（百分号/方言自动分派/无 FTS5·MATCH·bm25·rowid/CJK ILIKE 局限）、测试命令 |
| `README.md` | 「核心能力（规划）」→「V1.0 已实现」+ 审计状态注记；DB/AI 行同步真实实现 |
| `knowledge-core/README.md` | V1.0 已实现模块表、Model Adapter、端口抽象说明、importlib 测试命令 |
| 各服务 `__init__.py` / `ports.py` | 抽象接口 vs 具体实现分层；端口双方言实现文档 |
| `MILESTONES.md` | 追加 M0 准入 + M5 回归修复批次台账 |

**原则**：不将规划写成已完成；历史 M3-plan/report 的 pg_trgm 记述作为历史记录保留，新文档如实记录最终 tsvector 选择。

## 13. Git 提交与分支信息

- **分支**：`fix/m0-admission-and-m5-regressions`（专用修复分支）。
- **基线 HEAD**：`59068e2`（M5，审计 ZIP 对应代码）。
- **M0 初始提交**：`2d2b634` **完整保留**，未重写已推送历史，未修改 M0 初始提交。
- **提交内容**：32 修改 + 4 新增源码/测试 + 本报告 + MILESTONES.md，单批提交。
- **提交信息**：`fix: M0 准入修复（01–07）与 M5 回归修复（ZIP-01–04）`（语义清晰，附验收证据指向本报告）。
- **排除入库**：`release/ExplainLab-V1.0-review.zip`（审计产物）、`backend/.env`（真实密钥）、`*.db`、`node_modules/`、`.venv/`（均 gitignore 或显式不 add）。
- **修复批次提交**：`4557d2e`（38 文件，+1781/−174；含本报告与 MILESTONES 更新）。M0 初始提交 `2d2b634` 经 `git log` 核验完整保留，历史未重写。
- 未 `push --force`、未 `reset --hard`、未跳过 hooks。

## 14. 遗留问题与已知局限

1. **PostgreSQL 中文分词回退（已记录局限，非造假）**：PG `simple` 配置不对无空格中文成词，此类查询无 tsvector 命中时回退 `ILIKE` 子串匹配（真实匹配，JOIN 索引限定已索引集合）。功能可用但非真正中文全文分词。**后续建议**：引入 `zhparser`/`pg_jieba` 中文分词扩展（属新依赖，需独立审计批准，本轮不擅自增加）。
2. **elkjs 懒加载块体积警告（已记录）**：`graphLayout`（elkjs 布局引擎）块 1,464.73 kB >500 kB 警告仍在，但已**懒加载**（仅打开知识地图时加载），初始包不受影响。elkjs 体积为库固有，本轮以代码分割延迟加载而非消除。**后续建议**：如需进一步减小，可评估布局算法替换或 WASM 版 elk（属新依赖/重构，需批准）。
3. **向量存储为 JSON+Python 余弦（设计选择）**：`JsonVectorStore` 双方言通用，不依赖 pgvector。大规模向量场景性能有限。**后续建议**：生产大规模可评估 pgvector（需批准）。
4. **PG 验证环境**：真实验证基于本地便携 PG 16.8 实例（非生产部署）。生产 PostgreSQL 部署/鉴权/打包属 V1.0 之后工作，**不在本轮范围**。
5. **真实浏览器截图缺失**：in-app Browser 面板隐藏（viewport 0×0），懒加载以 Performance API/DOM/a11y 真实取证替代截图；构建产物与资源加载序列为客观证据。

**以上均为已如实记录的局限或范围外事项，不构成本修复批次的未通过项。**

---

## 审计移交声明

本批次（M0-01–07 + ZIP-01–04）已全部完成并经真实运行验证，结论**全部通过**（附第 14 节已记录局限）。

**不自行宣布进入 M1 或任何新里程碑。修复到此停止，等待独立审计裁定准入。** 架构保护红线全程遵守：未重写 Knowledge Core、未使其耦合 UI、核心无 FastAPI/React 依赖、业务逻辑无方言 SQL、未删除有效测试、未修改 M0 初始提交、未擅自增加大型依赖、未用假数据替代真实数据库测试、未虚报 PostgreSQL 成功、未将离线 SQL 当真实验证。

---

## 附录 A · 独立复审专项修复（2026-11-17）：迁移 0004 历史数据回填

> 本节为第一轮修复提交（`4557d2e`/`3c9b28b`）之后，针对**独立复审新发现缺陷**的专项修复。仅改 backend 全文索引基础设施与迁移，未开发 M1、未动无关模块、未改 Knowledge Core 上层检索接口。

### A.1 复审发现的缺陷

迁移 `0004_m3_retrieval` 创建全文索引表与同步触发器，但**未将迁移前已存在的 `knowledge_item` 回填进索引**。触发器只对「建索引之后」的 INSERT/UPDATE/DELETE 生效，故历史知识检索不到。**SQLite FTS5 与 PostgreSQL tsvector 两种实现均缺回填。**

### A.2 修复内容

- `backend/app/db/fts.py` 新增幂等回填常量（单一来源）：
  - `FTS_BACKFILL`（SQLite）：`INSERT INTO knowledge_fts(rowid,item_id,title,content) SELECT k.rowid,k.id,k.title,k.content FROM knowledge_item k WHERE NOT EXISTS (SELECT 1 FROM knowledge_fts f WHERE f.rowid=k.rowid)`——rowid 与源表对齐，`NOT EXISTS` 跳过已索引行。
  - `PG_FTS_BACKFILL`（PostgreSQL）：`INSERT INTO knowledge_fts(item_id,tsv) SELECT id, to_tsvector('simple', coalesce(title,'')||' '||coalesce(content,'')) FROM knowledge_item ON CONFLICT (item_id) DO UPDATE SET tsv=EXCLUDED.tsv`——tsv 表达式与 `knowledge_fts_sync()` 触发器**完全一致**，主键 `ON CONFLICT` 收敛。
- `create_fts()` 与迁移 `0004 upgrade()` 在建索引+触发器**之后**执行对应回填（两条建表路径共用）。回填直接写索引表，**不触发** `knowledge_item` 上的同步触发器。
- `downgrade()` 不变（删除索引表）；重新 `upgrade` 会再次回填，原有知识仍可检索。

### A.3 要求逐条核对

| 要求 | 落实 | 验证 |
|---|---|---|
| 1 SQLite 缺回填 | 已补 `FTS_BACKFILL` | `test_fts_backfill.py` |
| 2 PG 缺回填 | 已补 `PG_FTS_BACKFILL` | `test_retrieval_pg.py` 新增 5 用例 |
| 3 建索引+触发器后初始化历史 | upgrade/create_fts 末尾回填 | 先插数据再迁移即可检索 |
| 4 重复执行不产生重复索引 | `NOT EXISTS` / `ON CONFLICT` 幂等 | 重复回填后计数不变 |
| 5 downgrade→upgrade 仍可检索 | 删表后重升级再次回填 | down/up 后检索命中、计数无重复 |
| 6 不破坏 INSERT/UPDATE/DELETE 触发器 | 回填直写索引表，触发器未改 | 迁移后新增/改写/删除仍同步 |
| 7 不改 Core 上层检索接口 | 仅 backend `fts.py`/迁移；Core 零改动 | `FullTextIndex` 端口与 `HybridRetrievalService` 不变 |

### A.4 新增回归测试（先建记录→再迁移→不 reindex→直接检索）

- **SQLite** `backend/tests/test_fts_backfill.py`（4 用例，默认套件必跑）：库停 0003 插入历史知识（此时无 FTS 表/触发器）→ upgrade head → **不调用 reindex**，以 ≥3 字符查询走 FTS5 `MATCH` 直接命中历史；幂等（重复执行 `FTS_BACKFILL` 计数不变）；downgrade→upgrade 仍可检索；回填后 INSERT/UPDATE/DELETE 触发器仍同步。
- **PostgreSQL** `backend/tests/test_retrieval_pg.py` 追加 5 用例（`EXPLAINLAB_PG_TEST_URL` 门控，真实实例）：回填命中（原生 tsvector）、幂等（重复 `PG_FTS_BACKFILL`）、downgrade→upgrade 仍可检索、**历史中文**回填后 CJK 的 `ILIKE`（JOIN `knowledge_fts`）回退命中、回填后触发器/级联不破坏。

### A.5 真实运行证据（2026-11-17）

- SQLite 回填回归：**4 passed**。
- 真实 PostgreSQL 16.8 检索测试：**17 passed**（12 既有 + 5 新回填）。
- 全量含真实 PG：**279 passed**；默认无 PG：**262 passed, 17 skipped**；`ruff check`：**All checks passed!**
- 改动文件：`backend/app/db/fts.py`、`backend/alembic/versions/0004_m3_retrieval.py`、`backend/tests/test_fts_backfill.py`（新增）、`backend/tests/test_retrieval_pg.py`。前端与 Knowledge Core 未改动。

### A.6 状态

专项修复完成并经真实运行验证（SQLite + 真实 PostgreSQL 双方言）。**等待独立复审**；未进入 M1，未顺带开发无关功能。