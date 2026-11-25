# ExplainLab MCP 接入指南（美国 4 家 + 中国 6 家 Agent）

ExplainLab 内置了标准 **MCP Server（Model Context Protocol, JSON-RPC 2.0 over stdio）**，启动入口为：

```text
D:\ExplainLab\scripts\explainlab-mcp.cmd
```

前提：确保本地 ExplainLab 正在运行（双击桌面 **ExplainLab** 快捷方式即可，默认后端地址 `http://127.0.0.1:8000`）。

---

## 通用标准 JSON 配置（适用于绝大多数支持 MCP 的客户端）

```json
{
  "mcpServers": {
    "explainlab": {
      "command": "D:\\ExplainLab\\scripts\\explainlab-mcp.cmd",
      "env": {
        "EXPLAINLAB_API_URL": "http://127.0.0.1:8000"
      }
    }
  }
}
```

---

## 一、美国四家 Agent

### 1. Anthropic（Claude Desktop / Claude Code）
- **Claude Desktop** 配置文件：`%APPDATA%\Claude\claude_desktop_config.json`
  将上方 `explainlab` 写入 `mcpServers` 后重启 Claude。
- **Claude Code CLI** 一键命令：
  ```powershell
  claude mcp add explainlab -- D:\ExplainLab\scripts\explainlab-mcp.cmd
  ```

### 2. OpenAI（Codex）
- 配置文件：`C:\Users\wzz\.codex\config.toml`（本机已检测到）
- 追加以下段落：
  ```toml
  [mcp_servers.explainlab]
  command = "D:\\ExplainLab\\scripts\\explainlab-mcp.cmd"
  env = { EXPLAINLAB_API_URL = "http://127.0.0.1:8000" }
  ```

### 3. Google（Antigravity / Gemini）
- 配置文件：`C:\Users\wzz\.gemini\config\mcp_config.json`（本机已检测到）
- 将上方 `explainlab` 合并到 `mcpServers` 中并刷新 MCP 连接。

### 4. Cursor
- 配置文件：`C:\Users\wzz\.cursor\mcp.json`（或在 Cursor 内打开 `Settings → MCP → + Add new global MCP server`）
- 粘贴通用 JSON 配置后刷新即可看到 11 个 `explainlab_*` 工具。

---

## 二、中国六家 Agent

### 5. WorkBuddy（腾讯）
- 配置文件：`C:\Users\wzz\.workbuddy\connectors\default\mcp.json`（本机已检测到）
- 也可在 WorkBuddy 客户端 `连接器 / MCP → 添加自定义 MCP` 中粘贴通用 JSON。

### 6. Trae（字节跳动 Trae CN）
- 入口：打开 Trae CN → 右上角设置 → `MCP → 添加 MCP Server → 手动配置`（JSON 配置位于 `%APPDATA%\Trae CN\User\mcp.json`）
- 粘贴通用 JSON 配置保存即可。

### 7. Qoder / Qoder CN（阿里）
- 配置文件：`C:\Users\wzz\.qoder\mcp.json`（本机已检测到）
- 也可在 Qoder / Qoder CN 客户端 `设置 → MCP → 添加服务器` 中粘贴通用 JSON。

### 8. ZCode（智谱）
- 入口：打开 ZCode → `设置 → MCP → 添加自定义 MCP（stdio）`
- 命令填 `D:\ExplainLab\scripts\explainlab-mcp.cmd`，环境变量 `EXPLAINLAB_API_URL=http://127.0.0.1:8000`（或直接粘贴通用 JSON）。

### 9. DSH（DeepSeek AI DSH Desktop）
- 入口：打开 DSH 桌面端 → `设置 → MCP 工具 / 扩展 → 新增 stdio MCP`
- 命令填 `D:\ExplainLab\scripts\explainlab-mcp.cmd`，环境变量 `EXPLAINLAB_API_URL=http://127.0.0.1:8000`。

### 10. Kimi（Kimi Code / Kimi Desktop）
- **Kimi Code CLI**：可在 `C:\Users\wzz\.kimi-code\mcp.json` 配置通用 JSON，或通过 `kimi mcp add` 添加 stdio 服务器。
- **Kimi Desktop**：在桌面端 `设置 → MCP / 工具连接` 中添加 `D:\ExplainLab\scripts\explainlab-mcp.cmd`。

---

## 一键检测 / 自动写入脚本

项目已附带安全配置脚本 `D:\ExplainLab\scripts\connect-agents.ps1`：

```powershell
# 1. 先只读预览将要配置哪些 Agent（不修改任何文件）
powershell -ExecutionPolicy Bypass -File D:\ExplainLab\scripts\connect-agents.ps1

# 2. 确认无误后一键写入（修改前会自动为每个原配置文件生成 .bak-explainlab 备份）
powershell -ExecutionPolicy Bypass -File D:\ExplainLab\scripts\connect-agents.ps1 -Apply
```

---

## 可用工具清单（11 个工具 + 2 个只读资源）

| 工具名 | 作用 |
| --- | --- |
| `explainlab_health` | 检查本地 ExplainLab 后端与数据库/模型状态 |
| `explainlab_list_spaces` | 列出所有知识空间（个人总知识库 / 项目空间） |
| `explainlab_create_space` | 新建项目知识空间 |
| `explainlab_search_knowledge` | 混合检索（全文 FTS + 语义向量）已有知识 |
| `explainlab_list_knowledge` | 列出指定空间的知识条目 |
| `explainlab_get_knowledge` | 读取知识全文、关系与反向链接 |
| `explainlab_record_knowledge` | **记录新知识**（自动附带 `agent://<名称>` 来源追溯，支持同时建立关联） |
| `explainlab_update_knowledge` | 更新知识（修改已生效条目会自动进审核队列） |
| `explainlab_link_knowledge` | 在两条知识之间建立语义关系（同步反映到知识星图） |
| `explainlab_get_graph` | 读取知识图谱节点与边 |
| `explainlab_list_reviews` | 查看审核队列状态 |

---

## 推荐给各个 Agent 的口令

在以上任意一个 Agent 里，你可以直接说：

- *“先用 explainlab 搜一下我之前记过的关于 XXX 的笔记。”*
- *“把刚才排查这个问题的根因和解决方案用 explainlab_record_knowledge 记到我的知识库，agent_name 写 Trae（或 Cursor / Qoder / Kimi / WorkBuddy 等），并关联到相关旧笔记。”*
- *“看看我 ExplainLab 审核队列里还有哪些待审条目。”*
