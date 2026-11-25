# 15 · Nesti Integration（独立运行与内嵌 Nesti 架构规范）

## 1. 双运行形态边界（不引入微前端框架）

保持现有 **React 19 + TypeScript + Vite + Tailwind CSS v4** 技术栈，通过清晰的 React 组合边界支持两种形态：

- **Standalone（独立桌面应用）**：入口挂载 `<NestiStandaloneShell>`（渲染 Titlebar、Primary Rail、Status Bar、本地 `ThemeProvider`）包裹 `<ExplainLabModule />`。
- **Embedded（内嵌 Nesti Workspace）**：由未来 Nesti 宿主提供 Titlebar、Primary Rail、全局 `Ctrl+K`、通知中心与受控 `ThemeProvider`，ExplainLab 仅导出 `<ExplainLabModule />` 挂载至宿主主工作区插槽。

## 2. 六大集成接口契约

```ts
export interface ExplainLabModuleProps {
  /** 运行形态：独立运行或嵌入 Nesti 宿主 */
  mode: "standalone" | "embedded";
  /** 可配置 API 根地址（独立开发默认 "/api"，桌面/内嵌可注入 "http://127.0.0.1:8000/api"） */
  apiBaseUrl: string;
  /** 受控主题配置（embedded 态由 Nesti 宿主下发，standalone 态由本地 ThemeProvider 管理） */
  theme?: NestiThemeConfig;
  /** 导航同步回调（不强占宿主 window.location.pathname） */
  initialView?: "dashboard" | "chat" | "knowledge" | "search" | "map" | "experiments" | "reviews";
  onNavigate?: (view: string, params?: Record<string, string>) => void;
  /** 模块元数据注册（供 Nesti Primary Rail 渲染图标与待审核角标） */
  onBadgeChange?: (pendingReviews: number) => void;
}
```

1. **Shell 与业务边界**：业务组件严禁依赖 `window.location` 或全局 `*` CSS 选择器；所有主题变量均挂载于模块根容器 `[data-nesti-scope]` 或 `<html>`，确保零样式污染。
2. **API Client 注入**：`createExplainLabClient({ baseUrl, fetcher })` 工厂化改造（待开发阶段实施），支持 JSON 请求与二进制流（附件下载、ZIP 导出）两条通道。
3. **与 Desktop Hub / Agent Center 一致性**：共享 `tokens.css`、Primary Rail `52px`、Subnav `212px`、Inspector `320px` 与 Status Bar `26px` 空间网格，确保跨模块切换零视觉跳变。
