# 【StudyHack 赛道】ExplainLab V2：面向学习与科研的本地 AI 知识工作区与多 Agent 共享外脑

> **参赛团队**：爱吃大土豆（团队 ID：`1404554`）  
> **Qoder 账号**：`qwenwork-ei3p8051`  
> **参赛赛道**：StudyHack（学习科研）  
> **Qoder Sites 在线交互体验**：https://explainlab-t6omhu7gei6.qoder.zone  
> **1080p 演示视频（B站）**：https://www.bilibili.com/video/BV1dgykzrE7h/

---

## 一、我们要解决什么痛点？

大学生和科研党每天都在各种 AI 助手、论文和代码库之间来回切换，却普遍遇到三个核心痛点：

1. **只存不用、知识腐化**：普通笔记软件越记越乱，重复碎片越来越多，记完就再也没翻过；
2. **多 Agent 记忆割裂**：在 Qoder 写代码踩的坑、在别的 AI 助手查的论文结论，换一个工具就全忘了，不得不反复复述上下文；
3. **只读不练、缺乏内化**：AI 回答看着很懂，合上屏幕就忘，缺少把沉淀的知识转化为主动测验与学习路径的闭环。

因此，我们基于 **Qoder** 打造了 **ExplainLab V2**——一款集 **「对话式知识沉淀 + 严格知识治理 + Obsidian 风格力导向星图 + 交互式知识实验 + 多 Agent MCP 共享外脑」** 于一体的原生桌面级学习科研工作区。

---

## 二、核心功能与创新亮点

### 1. 真正的「知识治理」闭环（不止是存笔记）
- 支持 **Markdown 源码 / 预览 / 分屏编辑**，输入 `[[` 自动联想补全双链、点击直接跳转，`#标签` 自动汇总筛选，支持 `.md` / `.zip`（含附件）完整导入导出。
- 独创 **审核门禁机制（Review Queue）**：AI 从对话提取的候选知识、Active ZIP 导入包以及对「已生效」核心条目的修改，会自动进入审核队列（HTTP 202），防止幻觉或误操作污染主知识库。
- 完整支持 **线性版本快照回滚**、**词面 + 模型查重合并** 与 **来源追溯（`source_refs`）**。

### 2. Obsidian 风格力导向知识星图（零重依赖自研物理引擎）
- 纯 TypeScript 自研库仑斥力 + 胡克弹簧引力 + 矩形标签防重叠碰撞引擎，配合 HiDPI Canvas 渲染。
- 节点按连接度动态缩放，悬停自动聚光灯聚焦 1 跳邻居，支持物理拖拽弹性联动、**全局 / 1 跳 / 2 跳局部图谱**、5 类语义关系独立筛选，以及 **主库与各 Agent 副库星图一键切换**。

### 3. 研究对话（SSE 实时流式 + 知识库引用溯源）
- 提问前自动执行 **混合检索（FTS5/tsvector 全文 + 语义向量 RRF 融合排序）**，把用户已有笔记注入上下文；
- 通过 SSE 逐字流式回复，并在回答下方生成可点击的 **「参考知识库」引用胶囊**，一键在右侧滑出原笔记对照；
- 支持一键把整段对话提取为结构化知识条目。

### 4. 交互式知识实验（把「资料柜」变成「学习引擎」）
- 基于个人知识库自动编排三类主动学习实验：
  - **测验（Quiz）**：模型出题、服务端隐藏答案、作答后即时判分解析；
  - **概念对比（Compare）**：结构化对比两条知识的异同与语义关系；
  - **先修学习路径（Chain）**：沿 `depends_on` / `refines` 关系确定性 DFS 编排，零幻觉。

### 5. 多 Agent MCP 共享外脑 + 动态独立副库（杀手级差异化）
- 内置标准 **MCP Server（JSON-RPC 2.0 over stdio）**，暴露 11 个知识检索与读写工具，可无缝接入 **Qoder、DSH、Cursor、Claude、Codex、Trae、Kimi、WorkBuddy** 等主流 Agent。
- **动态按需副库**：外部 Agent 首次写入时，自动按 Agent 名称创建专属副库（如 `Agent · Qoder`、`Agent · DSH`），与主库清晰隔离，又能在全局星图中联合发现跨工具知识关联。

### 6. Nesti Fluent 原生桌面体验 & Theme Studio
- 采用 **Windows 11 Mica 材质外壳 + 原生集成标题栏 + 多标签页条 + `Ctrl+K` 命令面板**，提供独立 Electron 原生桌面端；
- 内置 **Theme Studio**：支持浅色 / 深色 / 跟随系统 + 6 套预设配色 + 自定义强调色与密度圆角调节。

---

## 三、技术架构与 Qoder 工作过程复盘

```text
外部 Agent 生态 (Qoder / DSH / Cursor / Claude / Codex)
        │  MCP (JSON-RPC 2.0 over stdio, 11 个工具)
        ▼
  ExplainLab MCP Server ──┐
                          ├──HTTP + SSE /api──▶ FastAPI Backend (SQLAlchemy 2 + Alembic + 双库方言适配)
  原生桌面端 (Electron) ───┘                              │  Protocol 端口注入
                                                         ▼
                                            knowledge-core (纯 Python 领域核心，零 Web/ORM 依赖)
                                                         │
                                                         ▼
                                      SQLite FTS5 (本地桌面默认) / PostgreSQL tsvector (部署目标)
```

### 我们如何用 Qoder 完成全流程工程化开发？

本项目不是一次性的单页 Prompt 生成，而是借助 **Qoder** 按真实软件工程里程碑（M0 → M5 → V2）迭代完成的完整系统：

1. **阶段一 · 需求拆解与架构边界确立（M0–M1）**
   - 在 Qoder 中先确立工程红线与 `frontend → backend → knowledge-core` 单向依赖规范，让 `knowledge-core` 保持纯 Python 零 Web/ORM 耦合，并生成架构独立性守护测试。
   - 通过 Qoder 快速搭建 FastAPI + SQLAlchemy 2 + Alembic 迁移骨架、统一 `ModelAdapter` 抽象层与多空间数据模型。

2. **阶段二 · 知识治理、混合检索与交互实验（M2–M5）**
   - 利用 Qoder 逐步实现词面 + LLM 查重合并、审核门禁（HTTP 202）、线性版本快照与来源追溯；
   - 依托 Qoder 完成 **SQLite FTS5 trigram** 与 **PostgreSQL 原生 `tsvector + GIN`** 双数据库方言适配，业务层零方言 SQL；
   - 落地测验 / 概念对比 / 先修学习路径三类主动学习实验引擎。

3. **阶段三 · V2 工程加固与 1,520+ 自动化回归（V2）**
   - 通过 Qoder 补齐 Markdown/ZIP 导入导出、附件存储与并发锁、孤儿清理与崩溃恢复机制，并对每一项修复编写针对性回归测试；
   - 最终沉淀 **1,520+ 项后端与核心自动化测试** 及 **79 项前端测试**，做到真库实测、零假数据冒充。

4. **阶段四 · 桌面体验打磨与 Qoder Sites 发布**
   - 升级 Obsidian 风格力导向知识星图、Markdown 双链补全、SSE 流式对话溯源与 MCP 多 Agent 独立副库，并封装独立原生桌面端；
   - 通过 Qoder 内置 `@sites` 一键将在线体验版部署到 **Qoder Sites**（https://explainlab-t6omhu7gei6.qoder.zone）并验证 Public 公开访问。

---

## 四、Qoder 工作过程与产品界面实录

（以下附上 Qoder 后端工程审计/冻结截图、`@sites` 一键发布截图，以及 ExplainLab 在线体验界面截图）

---

## 五、在线体验说明

点击顶部 **Qoder Sites 链接**（https://explainlab-t6omhu7gei6.qoder.zone）即可无需登录直接在浏览器中交互体验 **ExplainLab V2（预置 StudyHack 科研演示知识库）**；完整本地原生桌面版支持直连真实大模型与多 Agent MCP 外脑，欢迎评委与同学们体验交流！
