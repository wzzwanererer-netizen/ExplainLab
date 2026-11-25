# ExplainLab V2 · Theme System Audit

**状态**：`RECONNAISSANCE COMPLETED / WAITING FOR DESIGN FREEZE`

## 1. 当前样式与主题实现现状

- **无主题管理系统**：不存在 ThemeProvider、Theme Context、`localStorage` 持久化、`prefers-color-scheme` 监听、浅色模式或动态强调色机制。
- **全站硬编码单暗色 Slate 调色板**：
  - 全局底色固定 `bg-slate-950 text-slate-100`（[App.tsx](file:///D:/ExplainLab/frontend/src/App.tsx)），卡片固定 `bg-slate-900 border-slate-800`，输入控件固定 `bg-slate-950 border-slate-700`，主按钮固定反白 `bg-slate-100 text-slate-900`。
  - 未定义任何 CSS 自定义属性（`--color-*` / `--surface-*` / `--accent-*`）或 Tailwind v4 `@theme` 语义令牌。

## 2. 硬编码色值分布清点（迁移至 Design Tokens 时须全部替换）

| 位置 | 硬编码形式 | 具体色值 / 类名 | 迁移风险 |
| --- | --- | --- | --- |
| [index.css](file:///D:/ExplainLab/frontend/src/index.css) | 原生 CSS Hex | React Flow 控件 `#0f172a`、`#1e293b`、`#cbd5e1`、`#64748b`；全局滚动条 `#0f172a`、`#334155`、`#475569` | 中：需改为引用语义 CSS 变量（如 `var(--el-surface-elevated)`） |
| [KnowledgeMap.tsx](file:///D:/ExplainLab/frontend/src/components/KnowledgeMap.tsx) & [graphLayout.ts](file:///D:/ExplainLab/frontend/src/lib/graphLayout.ts) | JS 内联 Hex + SVG | 关系边色 `#f87171`、`#60a5fa`、`#34d399`、`#94a3b8`；节点 Handle `#64748b`；标签背景 `#0f172a` / 文字 `#cbd5e1`；画布网格 `<Background color="#1e293b" />` | 高：SVG/Canvas 属性无法直接用 Tailwind 暗色类，需从 CSS 变量读取或经主题 Hook 解析 |
| [experiments.ts](file:///D:/ExplainLab/frontend/src/lib/experiments.ts) & [QuizRunner.tsx](file:///D:/ExplainLab/frontend/src/components/experiments/QuizRunner.tsx) & [ChainRunner.tsx](file:///D:/ExplainLab/frontend/src/components/experiments/ChainRunner.tsx) | Tailwind 字面量 + Hex | 测验琥珀 `#fbbf24` / `amber-*`、对比天蓝 `#38bdf8` / `sky-*`、路径翡翠 `#34d399` / `emerald-*`；得分环底环 `#1e293b`；步进竖线 `#1e293b` | 中：需映射到语义状态色 Token（浅/深双主题下确保 WCAG AA 对比度） |
| 全部 7 个视图组件 | Tailwind 静态色阶 | 大量 `bg-slate-950` / `bg-slate-900` / `border-slate-800` / `text-slate-100..600`、`bg-red-950/50`、`bg-emerald-950/40` | 高（数量多但结构规整）：重构时统一收敛为语义 Token 类（`bg-surface`、`border-subtle`、`text-primary` 等） |

## 3. Tailwind CSS v4 接入评估

- 项目已升级至 **Tailwind CSS v4.3.5**（`@tailwindcss/vite`），原生支持 CSS-first `@theme` 指令与 `@custom-variant dark`，非常适合直接承载 **Nesti Fluent** 的双层 Token 架构（Primitive Palette → Semantic Tokens → Component Tokens）。
- `index.css` 已尊重 `prefers-reduced-motion: reduce`，动效无障碍习惯良好，可延续到新设计系统。
