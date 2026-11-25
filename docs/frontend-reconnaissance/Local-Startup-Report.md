# ExplainLab V2 · Local Startup & Live Browser Report

**状态**：`RECONNAISSANCE COMPLETED / WAITING FOR DESIGN FREEZE`  
**验证日期**：2026-11-25（本地时间 12:42–12:46）

## 1. 本地脚本与配置盘点

| 检查项 | 路径 | 实测现状 |
| --- | --- | --- |
| 首次安装脚本 | [scripts/setup.ps1](file:///D:/ExplainLab/scripts/setup.ps1) | 依次执行 `uv sync --locked` → `npm ci` → `uv run alembic upgrade head`，逻辑清晰 |
| 本地启动脚本 | [scripts/dev.ps1](file:///D:/ExplainLab/scripts/dev.ps1) | 弹两个 PowerShell 窗口：后端 `uv run uvicorn app.main:app --reload --port 8000`，前端 `npm run dev`（端口 `5173`） |
| 前端配置与代理 | [frontend/vite.config.ts](file:///D:/ExplainLab/frontend/vite.config.ts) | Vite `8.3.8`，端口 `5173`，`/api` 代理至 `http://127.0.0.1:8000`（`changeOrigin: true`） |
| 后端配置与入口 | [backend/app/core/config.py](file:///D:/ExplainLab/backend/app/core/config.py) · [backend/app/main.py](file:///D:/ExplainLab/backend/app/main.py) | `.env` 与默认 SQLite 锚定至 `backend/`；启动执行 `preflight_storage_roots` → `ProcessLock` → `validate_storage_roots` → `SourceInstanceIdStore` → `recover_if_needed` → `ensure_default_space` → 启动 `AttachmentMaintenance` |
| 环境示例 | [backend/.env.example](file:///D:/ExplainLab/backend/.env.example) | 完整记录 `DATABASE_URL`、`CORS_ORIGINS`、`MODEL_*`、`EMBED_*`；本机已存在 `backend/.env`（未读取/未暴露密钥） |
| 前端依赖与测试 | [frontend/package.json](file:///D:/ExplainLab/frontend/package.json) | `node_modules` 已就绪；`npm run test` **72 passed (10 files), exit=0**；`npm run typecheck` **exit=0** |

## 2. 重要发现：既有 `backend/data/explainlab.db` 迁移状态异常

为严守「不覆盖用户数据」原则，本轮先将 `backend/data/explainlab.db` 复制到临时隔离目录后再测试 `alembic upgrade head`，实测发现：
- 原 `backend/data/explainlab.db` 的 `alembic_version` 停留在 `0005_m5_experiments`，但库中**已存在 `tag` 表**，执行 `alembic upgrade head` 升级至 `0006_v2_markdown_kb` 时报错：
  `sqlite3.OperationalError: table tag already exists`
- **结论**：用户原 `backend/data/explainlab.db` 未被改动；但在后续本地联调前，需提醒用户确认该旧库是否需要备份后重建或人工核对迁移版本（本轮严禁修改原数据库）。

## 3. 隔离干净库实机启动与浏览器实测

使用全新隔离临时目录（`scratch/recon-clean/`）完成完整启动验证：
1. **数据库迁移**：`alembic upgrade head` 依次执行 `0001_baseline → 0006_v2_markdown_kb`，`exit=0`。
2. **后端启动**：`uvicorn app.main:app --host 127.0.0.1 --port 8000` 成功完成 lifespan 启动（`Application startup complete.`）。
3. **前端启动**：`npm run dev -- --port 5173` 在 `280 ms` 内就绪（`http://localhost:5173/`）。
4. **真实浏览器实测（`1280×800`）**：
   - 访问 `http://localhost:5173/`，零控制台错误、零 4xx/5xx 网络错误。
   - `/api/health` 真实返回：`status: "ok"`、`database: sqlite · 已连接`、`model_adapter: openai-compatible`、`embed_adapter: configured`、`ExplainLab v0.1.0（development）`。
   - 懒加载 chunk（`KnowledgeMap`、`ExperimentsView`）均正常加载渲染。
   - 实测结束后已停止临时前后端进程，释放 8000 / 5173 端口，未改动仓库代码或用户数据。

## 4. 实时浏览器截图清单（`Screenshots/`）

1. [01-chat.png](Screenshots/01-chat.png) — 对话视图
2. [02-knowledge.png](Screenshots/02-knowledge.png) — 知识库视图
3. [03-search.png](Screenshots/03-search.png) — 检索视图
4. [04-map.png](Screenshots/04-map.png) — 知识地图视图（懒加载）
5. [05-experiments.png](Screenshots/05-experiments.png) — 交互式知识实验视图（懒加载）
6. [06-reviews.png](Screenshots/06-reviews.png) — 重要变更审核队列
7. [07-status.png](Screenshots/07-status.png) — 系统状态（`/api/health` 实连）
