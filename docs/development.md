# ExplainLab 开发指南

## 1. 前置要求

| 工具 | 版本 | 说明 |
|---|---|---|
| Node.js | ≥ 20 | 前端构建 |
| npm | ≥ 10 | 前端包管理 |
| Python | 3.11 | 后端与 Knowledge Core（uv 会自动选用，见根目录 `.python-version`） |
| uv | ≥ 0.5 | Python 工作区与虚拟环境管理 |
| Git | ≥ 2.40 | 版本控制 |

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
| `DATABASE_URL` | `sqlite:///./data/explainlab.db` | 数据库连接串 |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | 允许的跨域源（JSON 数组） |
| `MODEL_PROVIDER` | 空 | 模型供应商标识；M0 不接入具体供应商 |
| `MODEL_API_KEY` | 空 | 仅后端持有，绝不写入前端 |

### 切换 PostgreSQL

1. 准备一个 PostgreSQL 实例（本地或远程，M0 不自动安装）。
2. 在 `backend/.env` 设置：

   ```
   DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/explainlab
   ```

3. 重新执行 `uv run alembic upgrade head`。

代码无需改动：引擎工厂按 URL 方言自动选择连接参数。

## 6. 测试与质量检查

```bash
bash scripts/test.sh          # 全部测试（Python + 前端）
```

手动：

```bash
uv run pytest                 # 后端 + knowledge-core（根 pyproject 已配置 testpaths）
uv run ruff check .           # Python lint
cd frontend
npm run test                  # Vitest 单次运行
npm run build                 # 类型检查 + 生产构建
```

## 7. 常见问题

- **端口占用**：后端 8000 / 前端 5173 被占用时，先关闭占用进程或修改启动参数与 `frontend/vite.config.ts` 代理目标。
- **FTS5 不可用**：运行 `uv run python -c "import sqlite3; c=sqlite3.connect(':memory:'); c.execute('CREATE VIRTUAL TABLE t USING fts5(x)')"` 验证；本项目开发库已实测通过。
- **uv 找不到 Python 3.11**：本机已安装于 `D:\Dev\Python\Python311`，可执行 `uv python list` 查看；必要时 `uv venv --python 3.11`。