import { useState } from "react";
import { ChatView } from "./components/ChatView";
import { HealthPanel } from "./components/HealthPanel";
import { KnowledgeMap } from "./components/KnowledgeMap";
import { KnowledgeView } from "./components/KnowledgeView";
import { ReviewQueue } from "./components/ReviewQueue";
import { SearchView } from "./components/SearchView";

type Tab = "chat" | "knowledge" | "search" | "map" | "reviews" | "status";

const TABS: { id: Tab; label: string }[] = [
  { id: "chat", label: "对话" },
  { id: "knowledge", label: "知识库" },
  { id: "search", label: "检索" },
  { id: "map", label: "地图" },
  { id: "reviews", label: "审核" },
  { id: "status", label: "系统状态" },
];

/**
 * M4 首页：对话 / 知识库 / 检索 / 地图 / 审核 / 系统状态六个视图。
 * 所有数据来自后端真实 API；模型 / 向量未配置时如实提示，不以假数据冒充。
 */
export default function App() {
  const [tab, setTab] = useState<Tab>("chat");

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-6 py-4">
          <h1 className="text-xl font-semibold tracking-tight">ExplainLab</h1>
          <nav className="flex gap-1" aria-label="主导航">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                aria-current={tab === t.id ? "page" : undefined}
                className={`rounded-md px-4 py-1.5 text-sm transition-colors ${
                  tab === t.id
                    ? "bg-slate-800 text-slate-100"
                    : "text-slate-400 hover:bg-slate-900 hover:text-slate-200"
                }`}
              >
                {t.label}
              </button>
            ))}
          </nav>
          <span className="rounded-full border border-slate-700 px-3 py-1 text-xs text-slate-400">
            M4 · 知识地图
          </span>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">
        {tab === "chat" && <ChatView />}
        {tab === "knowledge" && <KnowledgeView />}
        {tab === "search" && <SearchView />}
        {tab === "map" && <KnowledgeMap />}
        {tab === "reviews" && <ReviewQueue />}
        {tab === "status" && (
          <div className="max-w-3xl">
            <p className="mb-6 text-sm text-slate-400">
              以下面板展示来自后端 API 的真实运行状态。
            </p>
            <HealthPanel />
          </div>
        )}
      </main>
    </div>
  );
}