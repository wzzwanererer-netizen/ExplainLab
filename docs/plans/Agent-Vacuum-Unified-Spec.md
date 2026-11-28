# ExplainLab · 全 Agent 统一识别、工作区解析与多模态吸尘架构方案

> 制定日期：2026-11-27  
> 目标：彻底告别「遇到一个 Agent 修一个补丁」的零散修补，建立一套覆盖本机 9 家主流 Agent 的**统一会话发现、工作区解析、流式抽取、多模态图片采集与前端兜底渲染**架构。

---

## 一、本机 9 家 Agent 真实存储结构全景盘点

经本机实盘审计，9 家 Agent 可归为 **4 大存储家族**（无需写 9 套零散逻辑）：

| 家族 | 覆盖 Agent | 会话正文位置与格式 | 项目工作区 (`cwd`) 解析来源 | 关联图片 / 附件位置 |
| :--- | :--- | :--- | :--- | :--- |
| **A. 压缩流家族** | **DSH** (`~/.dsh`) | `sessions/--<编码路径>--/session-*/session.v4.jsonl.zstd` | 1) 目录名 `--D-Projects-xxx--` 解码还原真实路径<br>2) JSONL 内 `cwd` | `~/.dsh/attachments/` + 解码出的项目 `cwd` |
| **B. Rollout + SQLite 家族** | **Codex** (`~/.codex`) | `sessions/YYYY/MM/DD/rollout-*.jsonl`（含 >250KB 截图行）+ `sqlite/codex.db` | 1) `codex.db` `local_thread_catalog.cwd` & `display_title`<br>2) JSONL 头部 `payload.cwd` | `~/.codex/generated_images/` + 项目 `cwd` |
| **C. Transcript / JSONL 家族** | **Antigravity**、**Claude**、**WorkBuddy**、**Kimi Code** | Antigravity: `brain/<id>/.system_generated/logs/transcript.jsonl`<br>Claude: `projects/<编码路径>/*.jsonl`<br>WorkBuddy / Kimi: `**/*.jsonl` | Antigravity: `workspaceUris` / `cwd`<br>Claude: 目录名 `d--ExplainLab` 解码 + JSONL `cwd`<br>WorkBuddy / Kimi: JSONL `cwd` | Antigravity: `brain/<id>/*.png|jpg`<br>其余：会话目录 + 项目 `cwd` |
| **D. VS Code 系 IDE 家族** | **Cursor**、**Qoder**、**Trae CN** | `%APPDATA%/<IDE>/User/workspaceStorage/<hash>/state.vscdb` + 用户目录 `.jsonl` | 同目录 `workspace.json` 的 `folder` URI 解码 | `workspace.json` 指向的项目目录 + IDE 缓存 |

---

## 二、统一修复与架构升级方案（五大根治项）

### 1. 统一 `SessionDescriptor` 抽象与工作区解析器
- 拆出独立、可单测的 `resolve_session_workspace(agent_id, session_file)`：
  - 统一处理 4 种 `cwd` 提取（`codex.db`、DSH `--D-xxx--` 编码目录解码、Claude `d--xxx` 解码、JSONL 头部 `cwd` 字段、VS Code `workspace.json`）。
  - 所有 Agent 在「自选对话吸尘」里都统一展示 **`[项目名] 真实对话标题`** + **`项目目录路径`**，不再出现乱码文件名或年份目录。

### 2. 统一安全流式读取器（杜绝百 MB 日志截断与卡死）
- 所有 `.jsonl` 与 `.jsonl.zstd` 统一逐行流式读取，跳过 `>250 KB` 的纯 Base64 截图/工具大包行，兼容 `USER_INPUT/PLANNER_RESPONSE`、`role/content`、`payload.role`、`event_msg` 四种消息结构。

### 3. 统一多模态图片采集 + **双通道兜底显示（彻底解决「图片不显示」）**
- 统一从 4 个位置发现真实图片（会话产物目录、会话同级目录、对话引用的绝对路径、解析出的项目 `cwd` 代表图，每子目录限 2 张、过滤 `node_modules/.git` 与极小图标碎片）。
- **双通道落库，确保 100% 看得见**：
  1. **正文嵌入**：交给模型在 Markdown 中以 `![图注](/api/agents/media/...)` 或 ChatGPT 风格左图右文卡片呈现；
  2. **自动挂载附件面板**：同步将发现的图片写入该知识条目的多模态附件库（`media/`），即使模型某次没把某张图写进正文，卡片下方「附件 / 音视频」也能 100% 看到；
  3. **前端行内图片渲染补齐**：升级 `markdownUtils.ts` + `MarkdownContent.tsx`，同时支持**独立行图片**与**列表/段落内嵌图片**，彻底杜绝任何 Markdown 写法下图片漏显。

### 4. 自定义重吸支持「更新/补图」（不再被同名静默跳过）
- 在自定义吸尘（用户手动勾选已扫描过的条目）时，若知识库里已存在同名草稿条目：
  - 自动更新其正文并补全最新发现的图片与附件（不再静默跳过导致用户以为「怎么还是没图」）。

### 5. 统一诚实状态与全量单元测试
- 状态栏如实区分：`已入库 N 条（含 M 图）` / `已扫描(0条入库)` / `未吸尘`。
- 为 4 大 Agent 家族的目录解码、流式防截断、图片双通道挂载、行内图片渲染补齐自动化单元测试。

---

## 三、实施顺序
1. 后端重构 `agent_hub.py`：引入 4 大家族统一工作区解析器 + 双通道图片落库（正文 + 附件面板）+ 自定义重吸支持更新同名草稿补图；
2. 前端补齐 `markdownUtils.ts` & `MarkdownContent.tsx` 行内图片渲染 + 卡片内显示附件数量角标（让用户一眼看出这条知识带了几张图/音视频）；
3. 跑全量前后端测试 + 重启后端 + 实测对 `D:\菲比桌宠`（Codex）执行一次重吸验证图片真实渲染。
