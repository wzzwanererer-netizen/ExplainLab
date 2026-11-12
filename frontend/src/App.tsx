import { HealthPanel } from "./components/HealthPanel";

/**
 * M0 最小首页：仅展示真实后端健康状态。
 * 业务页面（对话 / 知识库 / 地图 / 实验）自 M1 起逐步建设。
 */
export default function App() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-6 py-4">
          <h1 className="text-xl font-semibold tracking-tight">ExplainLab</h1>
          <span className="rounded-full border border-slate-700 px-3 py-1 text-xs text-slate-400">
            M0 · 工程骨架
          </span>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-6 py-10">
        <p className="mb-6 text-sm text-slate-400">
          基于持续对话的 AI 知识管理与交互式学习平台。当前为 M0
          阶段，以下面板展示来自后端 API 的真实运行状态。
        </p>
        <HealthPanel />
      </main>
    </div>
  );
}