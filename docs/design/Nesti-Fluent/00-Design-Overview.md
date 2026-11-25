# 00 · Nesti Fluent — ExplainLab Desktop Design Overview

**当前阶段**：`NESTI FLUENT DESIGN / READY FOR DESIGN REVIEW`  
**设计体系**：Nesti Fluent（Modern Desktop Productivity Workspace）  
**适用产品**：ExplainLab V2（未来 Nesti 个人计算工作区的首个正式桌面应用模块）

## 1. 设计目标与产品定位

本设计为 ExplainLab V2 建立面向 Windows 桌面环境的专业知识工作区视觉系统，彻底摆脱通用 AI SaaS 模板与旧版单暗色网页管理后台形态，转向 **Windows 11 Fluent / Obsidian / Linear / JetBrains** 级别的多面板、高信息密度桌面软件体验。

## 2. 基于真实前端盘点与后端契约的设计原则

1. **零虚构交互与零虚假指标**：全部 7 个页面均严格对应 [Backend-API-Mapping.md](../../frontend-reconnaissance/Backend-API-Mapping.md) 中的真实后端路由（共 47 条端点），包含 V2 新增的附件（JSON Base64 8 类 MIME 白名单）、Markdown/ZIP 导入导出、双链只读视图与 Active ZIP 导入审核单（`__a1_import` envelope）。
2. **Nesti 品牌资产诚实声明**：经全仓检索 `D:\ExplainLab`，**当前工作区尚未包含原版 Nesti 蓝白图标文件（`.svg`/`.png`/`.ico`）**。按要求严禁自行重绘或使用相似图标替代；原型与规范中统一预留受保护的官方资产槽位（`data-slot="nesti-brand-logo"`），待官方原图落位即可零改动替换。
3. **双形态原生兼容**：设计同时覆盖 **Standalone（独立桌面运行）** 与 **Embedded（嵌入未来 Nesti Workspace Shell）**，保持现有 React 19 + TypeScript 7 + Vite 8 + Tailwind CSS v4 技术栈，不强制引入微前端框架，未来桌面宿主优先评估 Tauri 2。

## 3. 交付物导航

- **品牌与令牌**：[01-Brand-Identity.md](01-Brand-Identity.md) · [02-Design-Tokens.md](02-Design-Tokens.md)
- **桌面外壳**：[03-Workspace-Shell.md](03-Workspace-Shell.md)
- **七大业务页面**：[04-Dashboard.md](04-Dashboard.md) · [05-Chat.md](05-Chat.md) · [06-Knowledge.md](06-Knowledge.md) · [07-Search.md](07-Search.md) · [08-Knowledge-Map.md](08-Knowledge-Map.md) · [09-Experiments.md](09-Experiments.md) · [10-Reviews.md](10-Reviews.md)
- **主题与组件**：[11-Theme-Studio.md](11-Theme-Studio.md) · [12-Component-Library.md](12-Component-Library.md)
- **交互、桌面与整合**：[13-Interaction-Spec.md](13-Interaction-Spec.md) · [14-Desktop-Experience.md](14-Desktop-Experience.md) · [15-Nesti-Integration.md](15-Nesti-Integration.md)
- **自审与视觉验收**：[16-Visual-Acceptance.md](16-Visual-Acceptance.md)
- **可交互高保真原型**：[prototype/index.html](prototype/index.html)（独立隔离目录，零生产依赖，可直接双击或静态服务打开体验全部 7 页 + Theme Studio + 6 套主题 + 浅/深模式 + 10 态组件矩阵）
- **实机渲染高保真截图（`1440×900`）**：`screenshots/01-dashboard-light.png` … `15-components-states.png`（共 15 张）
