# ExplainLab V2 · Frontend Architecture Reconnaissance

**状态**：`RECONNAISSANCE COMPLETED / WAITING FOR DESIGN FREEZE`  
**盘点范围**：`D:\ExplainLab\frontend`（只读盘点，零生产代码改动）

## 1. 技术栈与版本基线

摘自 [frontend/package.json](file:///D:/ExplainLab/frontend/package.json)：

| 类别 | 包名 / 运行时 | 版本约束 | 说明 |
| --- | --- | --- | --- |
| Node / npm | `engines.node` / `engines.npm` | `>=22.23.2` / `>=10` | 与仓库根目录与 M0-03 基线一致 |
| UI 框架 | `react` / `react-dom` | `^19.3.1` | React 19 + `StrictMode`（[main.tsx](file:///D:/ExplainLab/frontend/src/main.tsx)） |
| 语言 | `typescript` | `^7.0.2` | `tsc -b` 严格类型检查，当前 `exit=0` |
| 构建工具 | `vite` + `@vitejs/plugin-react` | `^8.3.8` / `^6.3.0` | dev 端口 `5173`，`/api` 代理至 `http://127.0.0.1:8000` |
| 样式 | `tailwindcss` + `@tailwindcss/vite` | `^4.3.5` | Tailwind CSS v4（`@import "tailwindcss";`），无 `tailwind.config.*` |
| 知识地图 | `@xyflow/react` + `elkjs` | `^12.12.1` / `^0.12.1` | 通过 `React.lazy` 懒加载拆包（ZIP-04） |
| 测试 | `vitest` + `jsdom` + `@testing-library/react` + `@testing-library/jest-dom` | `^5.1.0` / `^31.0.0` / `^16.3.3` / `^7.0.1` | 10 个测试文件，**72 passed / 0 failed**（`exit=0`） |

## 2. 路由与页面外壳

- **无客户端路由器**（未引入 `react-router` / `tanstack-router`）：[App.tsx](file:///D:/ExplainLab/frontend/src/App.tsx) 仅以局部 `useState<Tab>("chat")` 切换 7 个顶级页签（`chat` / `knowledge` / `search` / `map` / `experiments` / `reviews` / `status`）。
- **URL 与历史栈**：切换页签不改变 URL，刷新页面恒回退至「对话」，无法通过 URL 深链到特定知识条目、审核单或实验会话。
- **按需加载（ZIP-04）**：`KnowledgeMap` 与 `ExperimentsView` 经 `React.lazy` + `Suspense` 拆分为异步 chunk；其余 5 个视图为首屏同步加载。
- **顶部版本标签滞后**：Header 右侧徽章硬编码为 `M5 · 知识实验`，尚未反映 V2（Markdown 导入导出、双链、附件管理）。

## 3. 组件与目录结构

```text
frontend/src/
├─ main.tsx                      # React 19 StrictMode 挂载入口
├─ App.tsx                       # 7 页签顶栏壳层（max-w-6xl）
├─ index.css                     # Tailwind v4 入口 + React Flow 暗色覆写 + 滚动条 + M5 动效
├─ api/
│  ├─ client.ts                  # 统一 fetch 封装（ApiError、202 MutationResult）
│  └─ types.ts                   # M0–M5 DTO 类型定义（尚未包含 V2 附件/双链/导入导出类型）
├─ lib/
│  ├─ graphLayout.ts             # ELK layered 纯布局模块 + 关系边颜色/标签
│  └─ experiments.ts             # 实验三模式元数据、约束校验、得分色调
└─ components/
   ├─ ChatView.tsx               # 对话与知识提取
   ├─ KnowledgeView.tsx          # 空间切换 + 知识 CRUD
   ├─ KnowledgeDetail.tsx        # 复用型治理详情（关系/版本/来源/查重合并）
   ├─ SearchView.tsx             # 跨会话混合检索 + 索引重建
   ├─ KnowledgeMap.tsx           # React Flow + ELK 知识地图 + 侧栏详情
   ├─ ReviewQueue.tsx            # 重要变更审核队列
   ├─ HealthPanel.tsx            # /api/health 系统状态面板
   └─ experiments/               # QuizRunner / CompareRunner / ChainRunner / ExperimentHistory
```

## 4. API Client 与状态管理

- **API Client（[client.ts](file:///D:/ExplainLab/frontend/src/api/client.ts)）**：
  - 统一使用原生 `fetch` 调相对路径 `/api/...`（开发态由 Vite 代理至 `127.0.0.1:8000`），前端不持有任何密钥。
  - 统一将非 2xx 响应解析为 `ApiError(status, detail)`；对 `PATCH/DELETE /api/knowledge/{id}` 和 `POST .../restore` 支持 HTTP `202` → `MutationResult`（`applied` vs `review`）。
  - **缺口**：仅封装了 M0–M5 共 29 个端点，完全未封装 V2 的附件 4 端点、双链 3 端点、Markdown 导入/批量导入/导出 4 端点；且 `send()` 默认固定 `Content-Type: application/json`，不直接支持二进制流下载（附件下载 / ZIP 导出需另做 Blob/Response 处理）。
- **状态管理**：
  - 全应用无全局 Store（无 Zustand / Redux / React Query / Context）。每个页面组件独立使用 `useState` + `useEffect` 拉取 `/api/spaces` 与自身数据。
  - 切换页签会卸载旧视图并重新挂载新视图，导致 `spaces` 列表、表单输入、当前选中的会话/搜索词在切换页签时全部丢失。

## 5. 图标、响应式与测试体系

- **图标体系**：**无图标库**（未安装 `lucide-react` 等）。界面仅使用纯 Unicode 符号（`×`、`→`、`←`、`✦`、`−`、`+`、`↔`）与 1 处手写 SVG（`QuizRunner` 得分环 `ScoreRing`）。
- **响应式布局**：
  - 外壳统一 `max-w-6xl mx-auto px-6`，顶部导航 `flex-wrap`；`ChatView` / `KnowledgeView` / `KnowledgeMap` / `ExperimentsView` 在 `lg`（1024px）断点采用左右双栏，窄屏自动堆叠。
  - `ReviewQueue` 与 `HealthPanel` 限制为 `max-w-3xl` 且左对齐，在宽屏桌面端右侧留白较大。
- **测试体系**：
  - `vitest run`（10 文件，72 用例）与 `tsc -b` 全部通过（`exit=0`）；测试覆盖所有 7 个视图与纯逻辑模块，采用 `vi.spyOn(globalThis, "fetch")` 模拟网络，无真实浏览器 E2E 自动化。
