import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { api } from "./api/client";
import type { HealthResponse, Space } from "./api/types";
import { ChatView } from "./components/ChatView";
import { DashboardView } from "./components/DashboardView";
import { HealthPanel } from "./components/HealthPanel";
import { Icon } from "./components/Icons";
import { KnowledgeView } from "./components/KnowledgeView";
import { ReviewQueue } from "./components/ReviewQueue";
import { SearchView } from "./components/SearchView";
import { ThemeStudioView } from "./components/ThemeStudioView";
import { useNestiTheme } from "./theme/ThemeProvider";

const KnowledgeMap = lazy(() =>
  import("./components/KnowledgeMap").then((m) => ({ default: m.KnowledgeMap })),
);
const ExperimentsView = lazy(() =>
  import("./components/ExperimentsView").then((m) => ({ default: m.ExperimentsView })),
);

type Tab =
  | "dashboard"
  | "chat"
  | "knowledge"
  | "search"
  | "map"
  | "experiments"
  | "reviews"
  | "status"
  | "theme";

interface TabMeta {
  id: Tab;
  label: string;
  icon: string;
  shortcut?: string;
}

const NAV_TABS: TabMeta[] = [
  { id: "dashboard", label: "工作台", icon: "dashboard", shortcut: "Alt+1" },
  { id: "chat", label: "研究对话", icon: "chat", shortcut: "Alt+2" },
  { id: "knowledge", label: "知识库", icon: "knowledge", shortcut: "Alt+3" },
  { id: "search", label: "混合检索", icon: "search", shortcut: "Alt+4" },
  { id: "map", label: "知识星图", icon: "map", shortcut: "Alt+5" },
  { id: "experiments", label: "知识实验", icon: "experiments", shortcut: "Alt+6" },
  { id: "reviews", label: "审核队列", icon: "reviews", shortcut: "Alt+7" },
];

const SYSTEM_TABS: TabMeta[] = [
  { id: "status", label: "系统状态", icon: "status" },
  { id: "theme", label: "Theme Studio", icon: "palette" },
];

const ALL_TABS: TabMeta[] = [...NAV_TABS, ...SYSTEM_TABS];

export default function App() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [openTabs, setOpenTabs] = useState<Tab[]>(["dashboard", "knowledge", "map"]);
  const [subnavOpen, setSubnavOpen] = useState(true);
  const [commandOpen, setCommandOpen] = useState(false);
  const [commandQuery, setCommandQuery] = useState("");
  const [pendingCount, setPendingCount] = useState(0);
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const { config, resolvedTheme, update } = useNestiTheme();
  const isNativeDesktop =
    typeof window !== "undefined" &&
    Boolean((window as unknown as { explainlabDesktop?: { isDesktop?: boolean } }).explainlabDesktop?.isDesktop);

  useEffect(() => {
    const bridge = (
      window as unknown as { explainlabDesktop?: { setTheme?: (t: string) => void } }
    ).explainlabDesktop;
    bridge?.setTheme?.(resolvedTheme);
  }, [resolvedTheme]);

  const navigate = (next: Tab) => {
    setTab(next);
    setOpenTabs((prev) => (prev.includes(next) ? prev : [...prev, next]));
  };

  const closeTab = (target: Tab) => {
    setOpenTabs((prev) => {
      if (prev.length <= 1) return prev;
      const nextList = prev.filter((id) => id !== target);
      if (tab === target) {
        setTab(nextList[nextList.length - 1]);
      }
      return nextList;
    });
  };

  useEffect(() => {
    void (async () => {
      const [h, r, s] = await Promise.allSettled([
        api.getHealth(),
        api.listReviews("pending"),
        api.listSpaces(),
      ]);
      if (h.status === "fulfilled") setHealth(h.value);
      if (r.status === "fulfilled") setPendingCount(r.value.length);
      if (s.status === "fulfilled") setSpaces(s.value);
    })();
  }, [tab]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCommandQuery("");
        setCommandOpen((o) => !o);
      } else if (e.key === "Escape") {
        setCommandOpen(false);
      } else if (e.altKey && e.key >= "1" && e.key <= "7") {
        e.preventDefault();
        const target = NAV_TABS[Number(e.key) - 1];
        if (target) navigate(target.id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const filteredCommands = useMemo(() => {
    const q = commandQuery.trim().toLowerCase();
    if (!q) return ALL_TABS;
    return ALL_TABS.filter((item) => item.label.toLowerCase().includes(q));
  }, [commandQuery]);

  const personalSpaces = spaces.filter((s) => s.kind === "personal");
  const agentSpaces = spaces.filter((s) => s.name.startsWith("Agent ·"));
  const projectSpaces = spaces.filter(
    (s) => s.kind !== "personal" && !s.name.startsWith("Agent ·"),
  );

  // 星图与对话页面采用紧凑原生全画布边距，最大化桌面工作区利用率
  const isFullBleedTab = tab === "map" || tab === "chat";

  return (
    <div className="nf-shell flex h-screen w-screen flex-col overflow-hidden">
      {/* Windows 11 Mica 集成式桌面标题栏（支持原生窗口拖拽） */}
      <header
        className={`nf-drag-region flex h-10 shrink-0 items-center justify-between gap-3 pl-2.5 select-none ${
          isNativeDesktop ? "pr-[142px]" : "pr-2.5"
        }`}
      >
        <div className="nf-no-drag flex items-center gap-2">
          <button
            type="button"
            onClick={() => setSubnavOpen((o) => !o)}
            title="折叠/展开侧边资源栏"
            className="nf-icon-btn"
          >
            <Icon name="panelLeft" size={15} />
          </button>

          <div className="flex items-center gap-2 pl-0.5">
            <span
              data-slot="nesti-brand-logo"
              title="Nesti ExplainLab"
              className="inline-flex h-6 w-6 items-center justify-center rounded-md text-[11px] font-bold shadow-xs"
              style={{
                background:
                  "linear-gradient(145deg, var(--nf-accent) 0%, color-mix(in srgb, var(--nf-accent) 72%, #79caff) 100%)",
                color: "#ffffff",
              }}
            >
              N
            </span>
            <h1 className="flex items-center gap-1.5 text-[12.5px] font-semibold tracking-tight">
              <span>ExplainLab</span>
              <span
                className="rounded px-1.5 py-0.5 font-mono text-[10px] font-medium"
                style={{
                  background: "var(--nf-accent-soft)",
                  color: "var(--nf-accent)",
                }}
              >
                Desktop
              </span>
            </h1>
          </div>
        </div>

        {/* 居中内凹桌面命令面板入口 */}
        <button
          type="button"
          onClick={() => {
            setCommandQuery("");
            setCommandOpen(true);
          }}
          className="nf-no-drag hidden h-7 w-full max-w-md items-center gap-2 rounded-lg px-2.5 text-xs transition-colors sm:flex"
          style={{
            background: "var(--nf-bg-glass)",
            border: "1px solid var(--nf-border-default)",
            color: "var(--nf-text-muted)",
            boxShadow: "inset 0 1px 2px rgba(15, 23, 42, 0.04)",
          }}
        >
          <Icon name="search" size={13} />
          <span>搜索命令、切换模块或定位知识…</span>
          <span
            className="ml-auto rounded px-1.5 py-0.5 font-mono text-[10px]"
            style={{
              background: "var(--nf-bg-surface)",
              border: "1px solid var(--nf-border-subtle)",
              color: "var(--nf-text-secondary)",
            }}
          >
            Ctrl K
          </span>
        </button>

        {/* 右侧原生窗口工具按钮 */}
        <div className="nf-no-drag flex items-center gap-1">
          <button
            type="button"
            onClick={() =>
              update({ mode: resolvedTheme === "dark" ? "light" : "dark" })
            }
            title={resolvedTheme === "dark" ? "切换到浅色模式" : "切换到深色模式"}
            className="nf-icon-btn"
          >
            <Icon name={resolvedTheme === "dark" ? "sun" : "moon"} size={15} />
          </button>
          <button
            type="button"
            onClick={() => navigate("theme")}
            title="Theme Studio 外观设置"
            className="nf-icon-btn"
            style={
              tab === "theme"
                ? { background: "var(--nf-accent-soft)", color: "var(--nf-accent)" }
                : undefined
            }
          >
            <Icon name="palette" size={15} />
          </button>
          <button
            type="button"
            onClick={() => navigate("reviews")}
            title={`待审核队列（${pendingCount}）`}
            className="nf-icon-btn relative"
          >
            <Icon name="bell" size={15} />
            {pendingCount > 0 && (
              <span
                className="absolute top-1 right-1 h-1.5 w-1.5 rounded-full"
                style={{ background: "var(--nf-accent)" }}
              />
            )}
          </button>
        </div>
      </header>

      {/* 主桌面工作区容器 */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        {/* 最左侧 Activity Rail（类似 VS Code / Obsidian / Windows 11 应用栏） */}
        <nav
          aria-label="Nesti 主模块"
          className="flex w-12 shrink-0 flex-col items-center gap-1.5 px-1.5 py-2 select-none"
        >
          {(
            [
              ["dashboard", "dashboard", "工作台"],
              ["chat", "chat", "研究对话"],
              ["knowledge", "knowledge", "知识库"],
              ["map", "map", "知识星图"],
              ["search", "search", "混合检索"],
            ] as const
          ).map(([id, icon, title]) => (
            <button
              key={id}
              type="button"
              onClick={() => navigate(id)}
              title={title}
              data-active={tab === id}
              className="nf-rail-btn"
            >
              <Icon name={icon} size={17} />
            </button>
          ))}

          <div className="flex-1" />

          <button
            type="button"
            onClick={() => navigate("status")}
            title="系统状态"
            data-active={tab === "status"}
            className="nf-rail-btn"
          >
            <Icon name="status" size={16} />
          </button>
          <button
            type="button"
            onClick={() => navigate("theme")}
            title="Theme Studio"
            data-active={tab === "theme"}
            className="nf-rail-btn"
          >
            <Icon name="palette" size={16} />
          </button>
        </nav>

        {/* 可折叠 Mica 资源树导航侧边栏 */}
        {subnavOpen && (
          <aside
            aria-label="主导航"
            className="flex w-56 shrink-0 flex-col overflow-y-auto px-2 pb-2.5 pt-1 select-none"
          >
            <div
              className="px-2.5 pb-1 pt-1 text-[10.5px] font-semibold tracking-wider uppercase"
              style={{ color: "var(--nf-text-muted)" }}
            >
              工作区
            </div>
            <div className="space-y-0.5">
              {NAV_TABS.map((t) => {
                const active = tab === t.id;
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => navigate(t.id)}
                    aria-current={active ? "page" : undefined}
                    data-active={active}
                    className="nf-nav-item"
                  >
                    <Icon name={t.icon} size={15} />
                    <span className="truncate">{t.label}</span>
                    {t.id === "reviews" && pendingCount > 0 && (
                      <span
                        className="ml-auto rounded-full px-1.5 py-0.5 font-mono text-[10px]"
                        style={{
                          background: "var(--nf-accent)",
                          color: "var(--nf-text-on-accent)",
                        }}
                      >
                        {pendingCount}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>

            {/* 动态展示主库 + 各 Agent 副库资源树 */}
            {spaces.length > 0 && (
              <div
                className="mt-3 pt-2.5"
                style={{ borderTop: "1px solid var(--nf-border-subtle)" }}
              >
                <div
                  className="flex items-center justify-between px-2.5 pb-1 text-[10.5px] font-semibold tracking-wider uppercase"
                  style={{ color: "var(--nf-text-muted)" }}
                >
                  <span>知识库与副库</span>
                  <span className="font-mono text-[10px] opacity-80">
                    {spaces.length}
                  </span>
                </div>
                <div className="space-y-0.5">
                  {personalSpaces.map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => navigate("knowledge")}
                      className="nf-nav-item"
                      title="打开主知识库"
                    >
                      <span
                        className="inline-block h-2 w-2 shrink-0 rounded-full"
                        style={{ background: "var(--nf-accent)" }}
                      />
                      <span className="truncate">{s.name}</span>
                      <span
                        className="ml-auto text-[10px]"
                        style={{ color: "var(--nf-text-muted)" }}
                      >
                        主库
                      </span>
                    </button>
                  ))}
                  {agentSpaces.map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => navigate("map")}
                      className="nf-nav-item"
                      title="在星图中查看该 Agent 副库"
                    >
                      <span
                        className="inline-block h-2 w-2 shrink-0 rounded-full"
                        style={{ background: "var(--nf-status-success)" }}
                      />
                      <span className="truncate">
                        {s.name.replace(/^Agent\s*·\s*/i, "")}
                      </span>
                      <span
                        className="ml-auto rounded px-1 text-[9.5px]"
                        style={{
                          background: "var(--nf-accent-soft)",
                          color: "var(--nf-accent)",
                        }}
                      >
                        Agent
                      </span>
                    </button>
                  ))}
                  {projectSpaces.map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => navigate("knowledge")}
                      className="nf-nav-item"
                      title={s.name}
                    >
                      <span
                        className="inline-block h-2 w-2 shrink-0 rounded-full"
                        style={{ background: "var(--nf-text-muted)" }}
                      />
                      <span className="truncate">{s.name}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="flex-1" />

            {/* 底部系统与外观入口 */}
            <div
              className="mt-3 space-y-0.5 pt-2"
              style={{ borderTop: "1px solid var(--nf-border-subtle)" }}
            >
              {SYSTEM_TABS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => navigate(t.id)}
                  data-active={tab === t.id}
                  className="nf-nav-item"
                >
                  <Icon name={t.icon} size={15} />
                  <span>{t.label}</span>
                </button>
              ))}
            </div>
          </aside>
        )}

        {/* 右侧内嵌圆角主工作区（多标签页条 + 内容画布） */}
        <div className="nf-workspace-pane flex min-w-0 flex-1 flex-col overflow-hidden">
          {/* 原生桌面多标签页条 */}
          <div
            className="flex h-9 shrink-0 items-end gap-1 overflow-x-auto px-2.5 pt-1.5 select-none"
            style={{
              background: "var(--nf-bg-surface-subtle)",
              borderBottom: "1px solid var(--nf-border-subtle)",
            }}
          >
            {openTabs.map((id) => {
              const meta = ALL_TABS.find((t) => t.id === id) ?? NAV_TABS[0];
              const active = tab === id;
              return (
                <div
                  key={id}
                  data-active={active}
                  onClick={() => setTab(id)}
                  className="nf-doc-tab group"
                >
                  <Icon name={meta.icon} size={13} />
                  <span className="max-w-[120px] truncate">{meta.label}</span>
                  {openTabs.length > 1 && (
                    <button
                      type="button"
                      aria-label={`关闭标签 ${meta.label}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        closeTab(id);
                      }}
                      className="ml-0.5 flex h-4 w-4 items-center justify-center rounded text-[11px] opacity-0 transition-opacity hover:bg-[var(--nf-bg-surface-hover)] group-hover:opacity-80"
                      style={active ? { opacity: 0.7 } : undefined}
                    >
                      ×
                    </button>
                  )}
                </div>
              );
            })}
          </div>

          {/* 视图内容区 */}
          <main
            className={`nf-legacy-scope flex-1 overflow-y-auto ${
              isFullBleedTab ? "p-3" : "p-4"
            }`}
          >
            <Suspense
              fallback={
                <p
                  role="status"
                  className="p-4 text-xs"
                  style={{ color: "var(--nf-text-muted)" }}
                >
                  正在加载视图…
                </p>
              }
            >
              {tab === "dashboard" && <DashboardView onNavigate={navigate} />}
              {tab === "chat" && <ChatView />}
              {tab === "knowledge" && <KnowledgeView />}
              {tab === "search" && <SearchView />}
              {tab === "map" && <KnowledgeMap />}
              {tab === "experiments" && <ExperimentsView />}
              {tab === "reviews" && <ReviewQueue />}
              {tab === "theme" && <ThemeStudioView />}
              {tab === "status" && (
                <div className="max-w-3xl">
                  <HealthPanel />
                </div>
              )}
            </Suspense>
          </main>
        </div>
      </div>

      {/* 底部 24px 原生桌面状态栏 */}
      <footer
        className="flex h-6 shrink-0 items-center justify-between px-3 text-[11px] select-none"
        style={{
          borderTop: "1px solid var(--nf-border-subtle)",
          color: "var(--nf-text-secondary)",
        }}
      >
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate("status")}
            className="inline-flex items-center gap-1.5 hover:opacity-80"
          >
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{
                background:
                  health?.status === "ok"
                    ? "var(--nf-status-success)"
                    : "var(--nf-status-warning)",
              }}
            />
            <span>
              {health
                ? `${health.database.dialect.toUpperCase()} · 已就绪`
                : "连接本地引擎中…"}
            </span>
          </button>
          {health && (
            <span
              className="hidden font-mono text-[10.5px] md:inline"
              style={{ color: "var(--nf-text-muted)" }}
            >
              Model: {health.model_adapter} · Embed: {health.embed_adapter}
            </span>
          )}
          {agentSpaces.length > 0 && (
            <span
              className="hidden text-[10.5px] sm:inline"
              style={{ color: "var(--nf-text-muted)" }}
            >
              · Agent 副库 {agentSpaces.length} 个
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={() => navigate("theme")}
          className="font-mono text-[10.5px] hover:underline"
          style={{ color: "var(--nf-text-muted)" }}
        >
          Nesti Fluent · {config.preset} ({resolvedTheme})
        </button>
      </footer>

      {/* Ctrl+K 桌面级命令面板（支持实时输入过滤） */}
      {commandOpen && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center pt-20 backdrop-blur-[2px]"
          style={{ background: "var(--nf-bg-overlay)" }}
          onClick={() => setCommandOpen(false)}
        >
          <div
            className="w-full max-w-lg overflow-hidden rounded-xl p-2"
            style={{
              background: "var(--nf-bg-surface)",
              border: "1px solid var(--nf-border-default)",
              boxShadow: "var(--nf-shadow-lg)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              className="mb-1.5 flex items-center gap-2 rounded-lg border px-2.5 py-1.5"
              style={{
                background: "var(--nf-bg-surface-subtle)",
                borderColor: "var(--nf-border-subtle)",
              }}
            >
              <Icon name="search" size={14} />
              <input
                autoFocus
                value={commandQuery}
                onChange={(e) => setCommandQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && filteredCommands[0]) {
                    navigate(filteredCommands[0].id);
                    setCommandOpen(false);
                  }
                }}
                placeholder="输入模块名称快速跳转…（ESC 关闭）"
                className="w-full bg-transparent text-xs outline-none"
                style={{ color: "var(--nf-text-primary)" }}
              />
            </div>
            <div className="max-h-72 space-y-0.5 overflow-y-auto">
              {filteredCommands.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    navigate(item.id);
                    setCommandOpen(false);
                  }}
                  className="nf-nav-item"
                >
                  <Icon name={item.icon} size={14} />
                  <span>{item.label}</span>
                  {item.shortcut && (
                    <span
                      className="ml-auto font-mono text-[10px]"
                      style={{ color: "var(--nf-text-muted)" }}
                    >
                      {item.shortcut}
                    </span>
                  )}
                </button>
              ))}
              {filteredCommands.length === 0 && (
                <p
                  className="px-3 py-4 text-center text-xs"
                  style={{ color: "var(--nf-text-muted)" }}
                >
                  无匹配命令
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
