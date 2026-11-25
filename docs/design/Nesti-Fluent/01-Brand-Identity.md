# 01 · Brand Identity — Nesti Fluent

## 1. 品牌定位

- **生态品牌**：Nesti — Personal Computing Workspace
- **首个正式模块**：ExplainLab — 对话式 AI 知识管理与交互式学习工作区
- **视觉性格**：冷静、克制、清晰、可靠。采用冰蓝、钴蓝与乳白色构建柔和的 Mica 空间层次，强调内容本身与专业桌面工具质感，拒绝高饱和霓虹发光与娱乐化渐变。

## 2. 原版 Nesti 品牌图标规范（重要声明）

- **现状核验记录**：经全面检索 `D:\ExplainLab`（含所有 `.svg` / `.png` / `.ico` 文件），**原版 Nesti 蓝白品牌图标文件当前不在本工作区内**。
- **严守纪律**：本轮未自行重绘、变形或用相似图标替代原版 Logo。
- **官方资产槽位契约**：
  - 资产落位路径：`frontend/src/assets/brand/nesti-logo.svg`（及 PNG/ICO 导出集 `24px / 32px / 64px / 256px`）。
  - 保护规则：保持原版形状、比例与蓝白识别特征；**永久免疫 Theme Studio 的动态主题染色**；周围保留至少 `4px` 净空（Titlebar `24×24` 槽位内居中呈现）。
  - 第三方应用图标（如未来 Desktop Hub 挂载的外部工具）默认保留原色，不强制染色。

## 3. 品牌色板与微调记录

| 角色 | 候选基准色 | 本轮采用色 | 调整原因说明 |
| --- | --- | --- | --- |
| Primary Cobalt Blue | `#2463EB` | 浅色 `#2463EB`（Hover `#1D4ED8`）；深色 `#4C82F7` | 浅色原样保留；深色背景 `#151E2E` 上 `#2463EB` 对比度仅 3.4:1，提亮至 `#4C82F7` 以满足 WCAG AA 正文/控件对比度（≥5.2:1） |
| Glacier Blue | `#79CAFF` | `#79CAFF`（原样保留） | 用于品牌次级高光、深色模式模块图标与 Glacier 预设副色 |
| Blue Violet | `#8785EF` | `#8785EF`（克制收敛） | 仅用于 `Iris Purple` 深色主题与极克制焦点高亮，禁止作为全页背景渐变 |
| Ice Blue | `#E5EDFA` | `#E5EDFA`（原样保留） | 浅色模式选中态底色与导航激活态柔和背景 |
| Off White | `#F5F8FC` | `#F5F8FC` + 窗口层 `#EEF3FA` + 表面 `#FFFFFF` | 建立三阶空间层次（Window `#EEF3FA` → Canvas `#F5F8FC` → Elevated Pane `#FFFFFF`），消除扁平感 |
| Deep Navy | `#243247` | `#243247`（原样保留） | 浅色模式主文本色，在 `#F5F8FC` 上对比度 `12.1:1`，较纯黑更柔和专业 |
