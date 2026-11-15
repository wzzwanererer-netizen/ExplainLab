# ExplainLab 开发指南

## 1. 前置要求

| 工具 | 版本 | 说明 |
|---|---|---|
| Node.js | **22.23.2**（基线，要求 ≥ 22.23.2） | 前端构建与测试的审计复现基线；`frontend/package.json` 已声明 `engines` |
| npm | ≥ 10 | 前端包管理（锁定安装用 `npm ci`） |
| Python | 3.11 | 后端与 Knowledge Core（uv 会自动选用，见根目录 `.python-version`） |
| uv | ≥ 0.5 | Python 工作区与虚拟环境管理（锁定安装用 `uv sync --locked`） |
| Git | ≥ 2.40 | 版本控制 |

> Node 兼容性：Vite 8（需 ≥ 22.12）、Vitest 5（需 ≥ 22）、jsdom 31（需 ≥ 20）、
> @vitejs/plugin-react 6（需 ≥ 22.12）、React 19（浏览器运行时）均与 Node 22.23.2 兼容。

> Windows 注意：`python3` 命令可能指向 Microsoft Store 占位别名，请使用 `python` 或直接使用 `uv run`。

## 2. 首次安装

```bash
bash scripts/setup.sh
# 或 PowerShell：
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
```

等价手动步骤：

```bash
uv sync                      # 创建 .venv 并安装 backend + knowledge-core 全部依赖
cd frontend && npm install   # 前端依赖
```

所有依赖均为项目本地（`.venv/`、`frontend/node_modules/`），不修改系统环境。

## 3. 数据库初始化

```bash
cd backend
uv run alembic upgrade head   # 在 backend/data/explainlab.db 建立 schema
uv run alembic current        # 查看当前迁移版本
```

## 4. 启动开发服务

```bash
bash scripts/dev.sh           # 或 scripts/dev.ps1
```

- 前端 http://localhost:5173（`/api` 自动代理到后端）
- 后端 http://127.0.0.1:8000，接口文档 http://127.0.0.1:8000/docs

手动启动：

```bash
# 终端 1
cd backend && uv run uvicorn app.main:app --reload --port 8000
# 终端 2
cd frontend && npm run dev
```

## 5. 配置

后端配置通过环境变量 / `backend/.env` 注入（参考 `backend/.env.example`）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `DATABASE_URL` | `sqlite:///<backend 绝对路径>/data/explainlab.db` | 数据库连接串；缺省锚定到 backend 目录（启动目录无关，M0-07），空值回退默认 |
| `CORS_ORIGINS` | `["http://localhost:5173","http://127.0.0.1:5173"]` | 允许的跨域源（JSON 数组） |
| `MODEL_PROVIDER` | 空 | 模型供应商标识（如 `deepseek`）；空视为未配置 |
| `MODEL_BASE_URL` | 空 | OpenAI 兼容生成端点 base_url，原样直连（禁代理替换） |
| `MODEL_API_KEY` | 空 | 生成密钥；`SecretStr` 承载，仅后端持有，序列化自动掩码，绝不写入前端 |
| `MODEL_NAME` | 空 | 生成模型名（如 `deepseek-chat`） |
| `EMBED_BASE_URL` | 空 | 向量端点 base_url（支持 `/embeddings`，如 SiliconFlow）；独立于聊天配置 |
| `EMBED_API_KEY` | 空 | 向量密钥；`SecretStr` 承载，仅后端持有 |
| `EMBED_MODEL` | 空 | 向量模型名；未配置时向量通道如实关闭（仅全文检索） |

> 空字符串 / 纯空白环境变量一律归一为「未配置」（None），避免空密钥被误判为已配置。
> 密钥读取须显式 `.get_secret_value()`；普通序列化（`model_dump_json` / `repr`）只输出掩码。

### 切换 PostgreSQL

1. 准备一个 PostgreSQL 实例（本地或远程；项目不自动安装）。
2. 在 `backend/.env` 设置（密码含特殊字符时按 URL 百分号编码，如 `@`→`%40`、`%`→`%25`；Alembic `env.py` 已处理 ConfigParser 的 `%` 插值，M0-01）：

   ```
   DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/explainlab
   ```

3. 重新执行 `uv run alembic upgrade head`（迁移同时支持 SQLite 与 PostgreSQL，`0004` 按方言建检索基础设施）。

切换无需改业务代码：引擎工厂按 URL 方言选择连接参数，检索适配层（`build_full_text_index`）按方言自动分派——SQLite 用 FTS5（trigram），PostgreSQL 用原生 `tsvector/tsquery` + GIN + 增改触发器、删除外键级联（**不使用 FTS5/MATCH/bm25/rowid**）。向量为双方言通用的 JSON 文本 + Python 余弦（不依赖 pgvector）。

> **PG 全文局限（如实记录）**：PostgreSQL `simple` 分词不对无空格中文成词，中文子串查询无 tsvector 命中时回退 `ILIKE` 子串匹配（JOIN 已索引集合，真实匹配，非造假）。如需 PG 中文分词级全文检索，可未来引入 `zhparser` / `pg_jieba` 等扩展，但非本轮必需依赖。
>
> **真实验证**：PG 迁移与检索须连真实实例验证（见 §6 的 `EXPLAINLAB_PG_TEST_URL`）；离线生成 SQL 不等同于真实数据库验证，不得虚报连接成功。

## 6. 测试与质量检查

```bash
bash scripts/test.sh          # 全部测试（Python + 前端）
```

手动：

```bash
uv run pytest                 # 后端 + knowledge-core（根 pyproject 已配 testpaths + importlib，一次性收集）
uv run pytest -o addopts="--import-mode=importlib"   # 需要完整汇总时（保留 importlib、仅去 -q；切勿用 -o addopts=""，会重新引发同名模块冲突）
uv run ruff check .           # Python lint（仅 check，严禁 ruff format）
cd frontend
npm run test                  # Vitest 单次运行
npm run build                 # 类型检查（tsc -b）+ 生产构建
```

### PostgreSQL 集成测试（真实实例）

`backend/tests/test_retrieval_pg.py` 经环境变量 `EXPLAINLAB_PG_TEST_URL` 门控：未设置时整模块跳过（默认 SQLite 套件不受影响）；设置后连真实 PG 执行真实在线迁移与检索验证。

```bash
# 示例：本地真实 PG（端口 / 库名按实际替换）
EXPLAINLAB_PG_TEST_URL="postgresql+psycopg://postgres@127.0.0.1:55432/explainlab_test" \
  uv run pytest backend/tests/test_retrieval_pg.py -o addopts="--import-mode=importlib" -v
```

覆盖迁移 up/down、原生 tsvector 表与 GIN 索引、增改触发器、删除级联、upsert/remove、CJK 回退、向量余弦、backfill、混合检索端到端、方言分派。**离线 SQL 不等同于真实数据库验证，不得虚报连接成功。**

## 7. 常见问题

- **端口占用**：后端 8000 / 前端 5173 被占用时，先关闭占用进程或修改启动参数与 `frontend/vite.config.ts` 代理目标。
- **FTS5 不可用**：运行 `uv run python -c "import sqlite3; c=sqlite3.connect(':memory:'); c.execute('CREATE VIRTUAL TABLE t USING fts5(x)')"` 验证；本项目开发库已实测通过。
- **uv 找不到 Python 3.11**：本机已安装于 `D:\Dev\Python\Python311`，可执行 `uv python list` 查看；必要时 `uv venv --python 3.11`。