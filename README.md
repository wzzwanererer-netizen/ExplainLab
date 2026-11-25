# ExplainLab V2 — 原生桌面 AI 知识工作区与多 Agent 共享外脑

![ExplainLab V2 Banner](docs/assets/explainlab-banner.png)

> **给所有 AI 装上共享外脑** · 面向学习与科研的本地 AI 知识管理、交互式学习与多 Agent MCP 外脑平台（2026 Qoder 高校创造力大赛 · StudyHack 赛道作品）。

- **在线交互体验（Qoder Sites）**：https://explainlab-t6omhu7gei6.qoder.zone
- **1080p 功能演示视频（B站）**：https://www.bilibili.com/video/BV1dgykzrE7h/

---

## 核心特性

1. **Markdown 双链知识库与严格知识治理**
   - 支持 **源码 / 预览 / 分屏** 实时写作、输入 `[[` 自动联想补全双链、点击跳转与 `#标签` 筛选；
   - 支持 `.md` / `.zip`（含附件）完整导入导出；
   - 内置 **审核门禁（Review Queue / HTTP 202）**、线性版本快照回滚、词面 + 模型查重合并与来源追溯（`source_refs`），防止 AI 幻觉污染主知识库。
2. **Obsidian 风格力导向知识星图**
   - 纯 TypeScript 零重依赖自研物理引擎（库仑斥力 + 弹簧引力 + 矩形标签防重叠碰撞），HiDPI Canvas 渲染；
   - 节点按连接度动态缩放、悬停聚光灯聚焦 1 跳邻居、物理拖拽弹性联动，支持 **全局 / 1 跳 / 2 跳局部图谱** 及 **主库与各 Agent 副库一键切换**。
3. **SSE 实时流式研究对话与引用溯源**
   - 提问前自动执行 **混合检索（SQLite FTS5 / PostgreSQL tsvector + 语义向量 RRF 融合排序）** 注入上下文；
   - 逐字流式作答，点击下方引用胶囊在右侧直接滑出原笔记对照；支持一键从对话提取知识。
4. **交互式知识实验（主动学习引擎）**
   - 自动将知识库转化为 **测验（Quiz）**、**概念对比（Compare）** 与 **先修学习路径（Chain）**。
5. **标准 MCP Server 多 Agent 共享外脑 + 动态独立副库**
   - 内置标准 JSON-RPC 2.0 over stdio MCP Server（11 个工具），无缝接入 **Qoder、DSH、Cursor、Claude、Codex、Trae、Kimi、WorkBuddy** 等 Agent；
   - 外部 Agent 首次写入时自动按名称动态创建专属副库（如 `Agent · Qoder`、`Agent · DSH`），与主库清晰隔离又可在全局星图中联合发现跨工具关联。
6. **Nesti Fluent 原生桌面端 & Theme Studio**
   - 基于 Electron 的独立 Windows 11 Mica 质感桌面窗口（无边框集成标题栏、多标签页条、`Ctrl+K` 命令面板），内置浅/深色模式与 6 套预设配色。

---

## 架构概览

```text
外部 Agent 生态 (Qoder / DSH / Cursor / Claude / Codex / Trae / Kimi)
        │  MCP (JSON-RPC 2.0 over stdio, 11 Tools)
        ▼
  ExplainLab MCP Server ──┐
                          ├──HTTP + SSE /api──▶ FastAPI Backend (SQLAlchemy 2 + Alembic + 双库方言适配)
  原生桌面端 (Electron) ───┘                              │  Protocol 端口注入
                                                         ▼
                                            knowledge-core (纯 Python 领域核心，零 Web/ORM 依赖)
                                                         │
                                                         ▼
                                      SQLite FTS5 (桌面默认) / PostgreSQL tsvector (部署目标)
```

---

## 快速开始（Windows / macOS / Linux）

### 环境要求
- Python `3.11+` + [uv](https://docs.astral.sh/uv/)
- Node.js `>= 22.23.2`

### 1. 安装依赖与初始化数据库
```bash
# 安装 Python 后端与独立核心依赖
uv sync --locked

# 复制配置模板（如需 AI 对话与向量检索，请填入你自己的 API Key）
cp backend/.env.example backend/.env

# 初始化本地 SQLite 数据库
cd backend && uv run alembic upgrade head
```

### 2. 启动后端与前端（开发模式）
```bash
# 终端 1：启动 FastAPI 后端（http://127.0.0.1:8000）
cd backend && uv run uvicorn app.main:app --reload

# 终端 2：启动前端（http://localhost:5173）
cd frontend && npm ci && npm run dev
```

### 3. 启动原生 Electron 桌面端（Windows）
```bash
cd frontend && npm run build
cd ../desktop && npm install && npm start
```

### 4. 接入外部 Agent（MCP）
详见 [docs/agent-mcp-setup.md](docs/agent-mcp-setup.md)，在任意支持 MCP 的 Agent 中配置 `scripts/explainlab-mcp.cmd` 即可。

---

## 测试与质量保障

```bash
# 后端 + knowledge-core 根级全量测试（1,520+ 项）
uv run pytest -o addopts="--import-mode=importlib"

# 代码检查
uv run ruff check

# 前端单元测试、类型检查与构建（79 项）
cd frontend && npm run test && npm run typecheck && npm run build
```

---

## License

本项目采用 [MIT License](LICENSE) 开源。
