# ExplainLab V2 · Nesti Integration Assessment

**状态**：`RECONNAISSANCE COMPLETED / WAITING FOR DESIGN FREEZE`  
**设计目标**：Nesti Fluent（冰蓝 / 钴蓝 / 乳白色、柔和材质与空间层次、适量渐变与圆角、专业桌面软件体验），支持独立运行与未来嵌入 Nesti（Desktop Hub / Agent Center）。

## 1. 七项整合能力就绪度评估

| 未来能力 | 当前就绪度 | 现状分析 | 架构适配建议（待设计冻结后实施） |
| --- | --- | --- | --- |
| **1. 全局 Design Tokens** | 未就绪（极易引入） | Tailwind v4 已到位，无遗留 `tailwind.config.js` 包袱 | 建立独立 `@nesti/tokens` 或 `src/theme/tokens.css`，以 CSS Custom Properties 定义冰蓝/钴蓝/乳白材质层、圆角、阴影与语义色，供 Tailwind v4 `@theme` 映射 |
| **2. 浅色与深色主题** | 未就绪（需全量去硬编码） | 全站硬编码暗色 `slate-950/900` + 若干内联 Hex（React Flow / SVG） | 以 `data-theme="light" \| "dark"` 挂载根节点（或嵌入容器根节点，避免污染宿主 `<html>`），同步替换所有 `slate-*` 与内联 Hex |
| **3. 自定义品牌强调色** | 未就绪（极易引入） | 无强调色变量，按钮为固定白底黑字 | 通过 `--nesti-accent` / `--nesti-accent-soft` / `--nesti-accent-hover`（支持 OKLCH 色阶派生）注入，默认钴蓝/冰蓝，允许宿主或用户覆盖 |
| **4. 动态主题切换** | 未就绪（低成本） | 无状态层 | 提供轻量 `ThemeProvider`：独立运行时读写 `localStorage` + `prefers-color-scheme`；嵌入 Nesti 时改为受控模式（接受宿主传入的 `theme` 与 `accentColor` props） |
| **5. 模块图标颜色联动** | 未就绪（空白可规范起步） | 当前无图标库（仅 Unicode 符号） | 引入统一 SVG 图标体系（如 `lucide-react` 或 Nesti 自定义图标集），图标统一使用 `currentColor` 或 `var(--nesti-module-accent)`，随品牌强调色实时联动 |
| **6. 独立运行与 Nesti 内嵌运行** | **高耦合外壳，核心视图已较干净** | `App.tsx` 同时承担外壳（Header/Nav）与 7 视图切换；`client.ts` 硬编码相对路径 `/api/...`；`index.css` 对全局 `*` 设置了滚动条样式 | ① 拆分 `ExplainLabShell`（独立桌面壳）与 `ExplainLabModule`（可嵌入组件，接收 `apiBaseUrl`、`theme`、`embedded`、`initialRoute`）；② `client.ts` 支持可配置 `baseUrl` / 自定义 `fetcher`；③ 样式作用域化（避免 `*` 全局选择器污染 Nesti 宿主） |
| **7. 与 Desktop Hub / Agent Center 一致性** | 架构边界天然对齐 | `knowledge-core` 已 100% 独立于 Web/前端；前端无全局状态库冲突 | 采用共享 Nesti Fluent 侧边栏/工作区布局规范（左导航 rail + 中央工作区 + 右侧检查器/详情抽屉），与 Desktop Hub / Agent Center 统一视觉语言与快捷键规范 |

## 2. 关键风险与前置注意事项

1. **React Flow 与第三方样式隔离**：`@xyflow/react/dist/style.css` 与 `index.css` 中的 `.react-flow__*` 规则需要全部改为消费语义 Token，否则浅色模式下地图控件/边标签会出现对比度反转。
2. **无客户端路由导致嵌入导航受限**：若未来嵌入 Nesti，建议使用受控视图状态或内存路由适配器（Memory / Hash / Path 可切换），避免直接抢占 Nesti 宿主的 `window.location.pathname`。
3. **跨页状态与 API 缓存**：当前每次切页都会重新请求 `/api/spaces` 并丢失草稿；重构时应引入轻量共享数据层（按需缓存空间列表、待审核计数与当前选中空间），同时保证嵌入卸载时可干净释放。
