import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { api } from "./api/client";
import type {
  CompletedTaskSuggestion,
  HealthResponse,
  KnowledgeItem,
  LibraryMediaItem,
  Space,
} from "./api/types";
import { AgentHubModal } from "./components/AgentHubModal";
import { ChatView } from "./components/ChatView";
import {
  ContextMenu,
  type ContextMenuItem,
  type ContextMenuState,
} from "./components/ContextMenu";
import { DashboardView } from "./components/DashboardView";
import { DocumentReaderModal } from "./components/DocumentReaderModal";
import { FilesLibraryView } from "./components/FilesLibraryView";
import { HealthPanel } from "./components/HealthPanel";
import { Icon } from "./components/Icons";
import { KnowledgeView } from "./components/KnowledgeView";
import { ModelSettingsView } from "./components/ModelSettingsView";
import { ReviewQueue } from "./components/ReviewQueue";
import { SearchView } from "./components/SearchView";
import { TaskCaptureToast } from "./components/TaskCaptureToast";
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
  | "files"
  | "search"
  | "map"
  | "experiments"
  | "reviews"
  | "models"
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
  { id: "files", label: "文件库", icon: "knowledge" },
  { id: "search", label: "混合检索", icon: "search", shortcut: "Alt+4" },
  { id: "map", label: "知识星图", icon: "map", shortcut: "Alt+5" },
  { id: "experiments", label: "知识实验", icon: "experiments", shortcut: "Alt+6" },
  { id: "reviews", label: "审核队列", icon: "reviews", shortcut: "Alt+7" },
];

const SYSTEM_TABS: TabMeta[] = [
  { id: "models", label: "模型与 Key 设置", icon: "experiments" },
  { id: "status", label: "系统状态", icon: "status" },
  { id: "theme", label: "Theme Studio", icon: "palette" },
];

const ALL_TABS: TabMeta[] = [...NAV_TABS, ...SYSTEM_TABS];

export default function App() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [subnavOpen, setSubnavOpen] = useState(true);
  const [commandOpen, setCommandOpen] = useState(false);
  const [commandQuery, setCommandQuery] = useState("");
  const [cmdItems, setCmdItems] = useState<KnowledgeItem[]>([]);
  const [cmdFiles, setCmdFiles] = useState<LibraryMediaItem[]>([]);
  const [cmdLoading, setCmdLoading] = useState(false);
  const [quickReadingFile, setQuickReadingFile] = useState<LibraryMediaItem | null>(null);
  const [pendingCount, setPendingCount] = useState(0);
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [activeSpaceId, setActiveSpaceId] = useState<string | undefined>(undefined);
  const [focusItemId, setFocusItemId] = useState<string | null>(null);
  const [focusToken, setFocusToken] = useState(0);
  const [agentHubOpen, setAgentHubOpen] = useState(false);
  const [agentHubMode, setAgentHubMode] = useState<"manage" | "picker">("manage");
  const [agentHubTarget, setAgentHubTarget] = useState<string | null>(null);
  const [sidebarMenu, setSidebarMenu] = useState<ContextMenuState | null>(null);
  const [spacesVersion, setSpacesVersion] = useState(0);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [taskCaptureEnabled, setTaskCaptureEnabled] = useState<boolean>(() => {
    try {
      return localStorage.getItem("explainlab_task_capture_enabled") !== "false";
    } catch {
      return true;
    }
  });
  const [toastSuggestion, setToastSuggestion] =
    useState<CompletedTaskSuggestion | null>(null);
  const [autoStartEnabled, setAutoStartEnabled] = useState(false);
  const { config, resolvedTheme, activePlugin, isPluginLocked, update } = useNestiTheme();
  const isNativeDesktop =
    typeof window !== "undefined" &&
    Boolean((window as unknown as { explainlabDesktop?: { isDesktop?: boolean } }).explainlabDesktop?.isDesktop);

  useEffect(() => {
    const bridge = (
      window as unknown as {
        explainlabDesktop?: {
          setTheme?: (t: string) => void;
          setTaskCaptureEnabled?: (v: boolean) => void;
        };
      }
    ).explainlabDesktop;
    bridge?.setTheme?.(resolvedTheme);
    bridge?.setTaskCaptureEnabled?.(taskCaptureEnabled);
  }, [resolvedTheme, taskCaptureEnabled]);

  useEffect(() => {
    try {
      localStorage.setItem(
        "explainlab_task_capture_enabled",
        taskCaptureEnabled ? "true" : "false",
      );
    } catch {
      // ignore
    }
  }, [taskCaptureEnabled]);

  // Electron 桌面版：读取与同步开机静默自启动状态
  useEffect(() => {
    const bridge = (
      window as unknown as {
        explainlabDesktop?: {
          getAutoStart?: () => Promise<boolean>;
          onAutoStartChanged?: (cb: (v: boolean) => void) => () => void;
        };
      }
    ).explainlabDesktop;
    if (!bridge?.getAutoStart) return;
    void bridge.getAutoStart().then((v) => setAutoStartEnabled(Boolean(v)));
    return bridge.onAutoStartChanged?.((v) => setAutoStartEnabled(Boolean(v)));
  }, []);

  const toggleAutoStart = async () => {
    const bridge = (
      window as unknown as {
        explainlabDesktop?: {
          setAutoStart?: (v: boolean) => Promise<boolean>;
        };
      }
    ).explainlabDesktop;
    if (!bridge?.setAutoStart) return;
    const actual = await bridge.setAutoStart(!autoStartEnabled);
    setAutoStartEnabled(Boolean(actual));
  };

  // Electron 桌面版点击临时弹窗的「去查看」时，切回主窗口并定位到对应空间
  useEffect(() => {
    const bridge = (
      window as unknown as {
        explainlabDesktop?: {
          onNavigateSpace?: (cb: (spaceId: string) => void) => () => void;
        };
      }
    ).explainlabDesktop;
    if (!bridge?.onNavigateSpace) return;
    return bridge.onNavigateSpace((spaceId) => {
      setSpacesVersion((v) => v + 1);
      if (spaceId) {
        setActiveSpaceId(spaceId);
      }
      navigate("knowledge");
    });
  }, []);

  // 非 Electron 浏览器环境下，轮询已完成任务并在右下角弹出临时悬浮窗
  useEffect(() => {
    if (isNativeDesktop || !taskCaptureEnabled) return;
    let active = true;
    const tick = async () => {
      try {
        const list = await api.getCompletedSuggestions(false);
        if (active && list.length > 0) {
          setToastSuggestion((prev) => prev ?? list[0]);
        }
      } catch {
        // 静默跳过
      }
    };
    const timer = window.setInterval(() => void tick(), 12000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [isNativeDesktop, taskCaptureEnabled]);

  const triggerTestCapturePopup = async () => {
    const bridge = (
      window as unknown as {
        explainlabDesktop?: { testTaskCapturePopup?: () => void };
      }
    ).explainlabDesktop;
    if (bridge?.testTaskCapturePopup) {
      bridge.testTaskCapturePopup();
      return;
    }
    try {
      const list = await api.getCompletedSuggestions(true);
      if (list.length > 0) {
        setToastSuggestion(list[0]);
      }
    } catch {
      // ignore
    }
  };

  const navigate = (next: Tab) => {
    setTab(next);
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
  }, [tab, spacesVersion]);

  const openSpaceInKnowledge = (id: string) => {
    setActiveSpaceId(id);
    setFocusItemId(null);
    navigate("knowledge");
  };

  const openItemInKnowledge = (spaceId: string | null | undefined, itemId: string) => {
    if (spaceId) {
      setActiveSpaceId(spaceId);
    } else {
      const personal = spaces.find((s) => s.kind === "personal");
      if (personal) setActiveSpaceId(personal.id);
    }
    setFocusItemId(itemId);
    setFocusToken((t) => t + 1);
    navigate("knowledge");
  };

  const openAgentHub = (mode: "manage" | "picker" = "manage", agentName?: string | null) => {
    setAgentHubMode(mode);
    setAgentHubTarget(agentName ?? null);
    setAgentHubOpen(true);
  };

  const openSpaceContextMenu = (e: React.MouseEvent, s: Space) => {
    e.preventDefault();
    const isAgent = s.name.startsWith("Agent ·");
    const agentLabel = isAgent ? s.name.replace(/^Agent\s*·\s*/i, "").trim() : null;
    const items: ContextMenuItem[] = [
      {
        id: "open",
        label: "打开该知识库",
        onClick: () => openSpaceInKnowledge(s.id),
      },
      {
        id: "map",
        label: "在知识星图中查看",
        onClick: () => navigate("map"),
      },
    ];
    if (isAgent && agentLabel) {
      items.push(
        {
          id: "picker",
          label: `自选 ${agentLabel} 对话吸尘`,
          dividerBefore: true,
          onClick: () => openAgentHub("picker", agentLabel),
        },
        {
          id: "manage",
          label: "管理 AI 助手与自动吸尘",
          onClick: () => openAgentHub("manage", agentLabel),
        },
      );
    }
    setSidebarMenu({ x: e.clientX, y: e.clientY, items });
  };

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

  useEffect(() => {
    if (!commandOpen) return;
    let cancelled = false;
    setCmdLoading(true);
    void (async () => {
      const [k, f] = await Promise.allSettled([
        api.listKnowledge(),
        api.listMediaLibrary(),
      ]);
      if (cancelled) return;
      if (k.status === "fulfilled") setCmdItems(k.value);
      if (f.status === "fulfilled") setCmdFiles(f.value);
      setCmdLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [commandOpen]);

  const filteredCommands = useMemo(() => {
    const q = commandQuery.trim().toLowerCase();
    if (!q) return ALL_TABS;
    return ALL_TABS.filter((item) => item.label.toLowerCase().includes(q));
  }, [commandQuery]);

  const filteredKnowledge = useMemo(() => {
    const q = commandQuery.trim().toLowerCase();
    if (!q) return cmdItems.slice(0, 4);
    return cmdItems
      .filter(
        (item) =>
          item.title.toLowerCase().includes(q) ||
          item.content.toLowerCase().includes(q),
      )
      .slice(0, 6);
  }, [cmdItems, commandQuery]);

  const filteredFiles = useMemo(() => {
    const q = commandQuery.trim().toLowerCase();
    if (!q) return cmdFiles.slice(0, 4);
    return cmdFiles
      .filter(
        (f) =>
          f.filename.toLowerCase().includes(q) ||
          f.item_title.toLowerCase().includes(q) ||
          (f.space_name ?? "").toLowerCase().includes(q),
      )
      .slice(0, 6);
  }, [cmdFiles, commandQuery]);

  const personalSpaces = spaces.filter((s) => s.kind === "personal");
  const agentSpaces = spaces.filter((s) => s.name.startsWith("Agent ·"));
  const projectSpaces = spaces.filter(
    (s) => s.kind !== "personal" && !s.name.startsWith("Agent ·"),
  );

  // 星图与对话页面采用紧凑原生全画布边距，最大化桌面工作区利用率
  const isFullBleedTab = tab === "map" || tab === "chat";
  const currentTabMeta = ALL_TABS.find((t) => t.id === tab) ?? NAV_TABS[0];
  const currentTabIndex = String(
    Math.max(1, ALL_TABS.findIndex((t) => t.id === tab) + 1),
  ).padStart(2, "0");

  return (
    <div className="nf-shell flex h-screen w-screen flex-col overflow-hidden">
      {/* 主桌面双栏工作区：单一通透 Nesti 冰雾侧栏 + 全高瓷白主画布 */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        {subnavOpen && (
          <aside
            aria-label="主导航"
            className="flex w-[238px] shrink-0 flex-col overflow-y-auto px-3 pb-3 pt-2.5 select-none"
          >
            {/* 顶部 Nesti 品牌标识（支持拖拽窗口） */}
            <div className="nf-drag-region mb-3 flex items-center justify-between gap-2 px-1 pt-0.5">
              <div className="nf-no-drag flex items-center gap-2.5">
                <img
                  data-slot="nesti-brand-logo"
                  src="/nesti-logo.png"
                  alt="Nesti"
                  title="Nesti · AI 工作空间"
                  className="h-7 w-7 shrink-0 rounded-[7px] object-contain select-none"
                  draggable={false}
                />
                <div className="leading-tight">
                  <div className="text-[13.5px] font-semibold tracking-tight">
                    Nesti
                  </div>
                  <div
                    className="font-mono text-[9.5px] tracking-[0.14em] uppercase"
                    style={{ color: "var(--nf-text-muted)" }}
                  >
                    AI WORKSPACE
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setSubnavOpen(false)}
                title="折叠侧边栏"
                className="nf-no-drag nf-icon-btn"
              >
                <Icon name="panelLeft" size={14} />
              </button>
            </div>

            {/* 侧栏内嵌 Spotlight 搜索入口 */}
            <button
              type="button"
              onClick={() => {
                setCommandQuery("");
                setCommandOpen(true);
              }}
              className="mb-4 flex h-8 w-full items-center gap-2 rounded-[9px] px-2.5 text-xs transition-colors"
              style={{
                background: "var(--nf-bg-glass)",
                border: "1px solid var(--nf-border-subtle)",
                color: "var(--nf-text-muted)",
              }}
            >
              <Icon name="search" size={13} />
              <span className="truncate">全局瞬搜…</span>
              <span
                className="ml-auto rounded px-1.5 py-0.5 font-mono text-[9.5px]"
                style={{
                  background: "var(--nf-bg-surface)",
                  border: "1px solid var(--nf-border-subtle)",
                  color: "var(--nf-text-secondary)",
                }}
              >
                ⌘K
              </span>
            </button>

            <div className="nf-eyebrow px-2.5 pb-1.5">
              <span className="nf-eyebrow-index">01</span>
              <span>工作空间</span>
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

            {/* 清晰三分组：我的主库 / AI 助手副库 / 专题分类 */}
            {spaces.length > 0 && (
              <div
                className="mt-4 space-y-3.5 pt-3.5"
                style={{ borderTop: "1px solid var(--nf-border-subtle)" }}
              >
                <div>
                  <div className="nf-eyebrow px-2.5 pb-1.5">
                    <span className="nf-eyebrow-index">02</span>
                    <span>我的主库</span>
                  </div>
                  <div className="space-y-0.5">
                    {personalSpaces.map((s) => (
                      <button
                        key={s.id}
                        type="button"
                        onClick={() => openSpaceInKnowledge(s.id)}
                        onContextMenu={(e) => openSpaceContextMenu(e, s)}
                        data-active={tab === "knowledge" && activeSpaceId === s.id}
                        className="nf-nav-item"
                        title="左键打开 · 右键更多操作"
                      >
                        <span
                          className="inline-block h-1.5 w-1.5 shrink-0 rounded-full"
                          style={{ background: "var(--nf-accent)" }}
                        />
                        <span className="truncate">{s.name}</span>
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <div className="nf-eyebrow justify-between px-2.5 pb-1.5">
                    <span className="flex items-center gap-[7px]">
                      <span className="nf-eyebrow-index">03</span>
                      <span>AI 助手副库 · {agentSpaces.length}</span>
                    </span>
                    <button
                      type="button"
                      onClick={() => openAgentHub("manage")}
                      className="rounded px-1 py-0.5 font-sans text-[10.5px] font-medium tracking-normal normal-case transition-colors hover:underline"
                      style={{ color: "var(--nf-accent)" }}
                      title="添加 AI 助手或吸尘本地新对话"
                    >
                      + 添加
                    </button>
                  </div>
                  <div className="space-y-0.5">
                    {agentSpaces.length === 0 ? (
                      <button
                        type="button"
                        onClick={() => openAgentHub("manage")}
                        className="nf-nav-item text-[11px] opacity-75"
                      >
                        <span>+ 接入第一个 AI 助手…</span>
                      </button>
                    ) : (
                      agentSpaces.map((s) => (
                        <button
                          key={s.id}
                          type="button"
                          onClick={() => openSpaceInKnowledge(s.id)}
                          onContextMenu={(e) => openSpaceContextMenu(e, s)}
                          data-active={tab === "knowledge" && activeSpaceId === s.id}
                          className="nf-nav-item"
                          title={`左键打开 ${s.name} · 右键自选吸尘/更多`}
                        >
                          <span
                            className="inline-block h-1.5 w-1.5 shrink-0 rounded-full"
                            style={{ background: "var(--nf-brand-glacier)" }}
                          />
                          <span className="truncate">
                            {s.name.replace(/^Agent\s*·\s*/i, "")}
                          </span>
                        </button>
                      ))
                    )}
                  </div>
                </div>

                {projectSpaces.length > 0 && (
                  <div>
                    <div className="nf-eyebrow px-2.5 pb-1.5">
                      <span className="nf-eyebrow-index">04</span>
                      <span>专题分类 · {projectSpaces.length}</span>
                    </div>
                    <div className="space-y-0.5">
                      {projectSpaces.map((s) => (
                        <button
                          key={s.id}
                          type="button"
                          onClick={() => openSpaceInKnowledge(s.id)}
                          onContextMenu={(e) => openSpaceContextMenu(e, s)}
                          data-active={tab === "knowledge" && activeSpaceId === s.id}
                          className="nf-nav-item"
                          title={`左键打开专题：${s.name} · 右键更多操作`}
                        >
                          <span
                            className="inline-block h-1.5 w-1.5 shrink-0 rounded-full"
                            style={{ background: "var(--nf-text-muted)" }}
                          />
                          <span className="truncate">{s.name}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            <div className="flex-1" />

            {/* 底部系统与外观入口 */}
            <div
              className="mt-4 space-y-0.5 pt-3"
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

        {/* 右侧全高主工作画布（顶部与原生标题栏齐平，避免边框压到右上角最小化/最大化/关闭按钮） */}
        <div className="nf-workspace-pane flex min-w-0 flex-1 flex-col overflow-hidden">
          {/* 极简 44px 顶部面包屑与窗口拖拽栏 */}
          <header
            className={`nf-drag-region flex h-11 shrink-0 items-center justify-between gap-3 pl-5 select-none ${
              isNativeDesktop ? "pr-[146px]" : "pr-5"
            }`}
            style={{ borderBottom: "1px solid var(--nf-border-subtle)" }}
          >
            <div className="nf-no-drag flex items-center gap-3">
              {!subnavOpen && (
                <button
                  type="button"
                  onClick={() => setSubnavOpen(true)}
                  title="展开侧边栏"
                  className="nf-icon-btn"
                >
                  <Icon name="panelLeft" size={15} />
                </button>
              )}
              <div className="flex items-center gap-2.5">
                <span
                  className="font-mono text-[10.5px] font-semibold tracking-[0.14em]"
                  style={{ color: "var(--nf-accent)" }}
                >
                  {currentTabIndex}
                </span>
                <span
                  className="h-3 w-px"
                  style={{ background: "var(--nf-border-default)" }}
                />
                <h1
                  className="text-[13px] font-semibold tracking-tight"
                  style={{ color: "var(--nf-text-primary)" }}
                >
                  {currentTabMeta.label}
                </h1>
              </div>
            </div>

            <div className="nf-no-drag flex items-center gap-1">
              <button
                type="button"
                onClick={() => {
                  setCommandQuery("");
                  setCommandOpen(true);
                }}
                title="全局搜索 (Ctrl+K)"
                className="nf-icon-btn"
              >
                <Icon name="search" size={14} />
              </button>
              <button
                type="button"
                disabled={isPluginLocked}
                onClick={() =>
                  update({ mode: resolvedTheme === "dark" ? "light" : "dark" })
                }
                title={
                  isPluginLocked
                    ? `已加载风格插件「${activePlugin.name}」，系统模式不可切换`
                    : resolvedTheme === "dark"
                      ? "切换到浅色晨雾模式"
                      : "切换到深色极夜模式"
                }
                className="nf-icon-btn disabled:opacity-40"
              >
                <Icon name={resolvedTheme === "dark" ? "sun" : "moon"} size={14} />
              </button>
              <button
                type="button"
                onClick={() => navigate("theme")}
                title="主题外观"
                className="nf-icon-btn"
                style={
                  tab === "theme"
                    ? { background: "var(--nf-accent-soft)", color: "var(--nf-accent)" }
                    : undefined
                }
              >
                <Icon name="palette" size={14} />
              </button>
              <button
                type="button"
                onClick={() => navigate("reviews")}
                title={`待审核队列（${pendingCount}）`}
                className="nf-icon-btn relative"
              >
                <Icon name="bell" size={14} />
                {pendingCount > 0 && (
                  <span
                    className="absolute top-1.5 right-1.5 h-1.5 w-1.5 rounded-full"
                    style={{ background: "var(--nf-accent)" }}
                  />
                )}
              </button>
            </div>
          </header>

          {/* 视图内容区 */}
          <main
            className={`nf-legacy-scope flex-1 overflow-y-auto ${
              isFullBleedTab ? "p-3" : "px-8 py-7"
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
              {tab === "dashboard" && (
                <DashboardView
                  onNavigate={navigate}
                  onOpenAgentHub={() => openAgentHub("picker")}
                  onJumpToItem={openItemInKnowledge}
                />
              )}
              {tab === "chat" && <ChatView />}
              {tab === "knowledge" && (
                <KnowledgeView
                  selectedSpaceId={activeSpaceId}
                  focusItemId={focusItemId}
                  focusToken={focusToken}
                  refreshKey={spacesVersion}
                  onSelectSpace={setActiveSpaceId}
                  onOpenAgentHub={(mode, agentName) => openAgentHub(mode, agentName)}
                  onSpacesChanged={() => setSpacesVersion((v) => v + 1)}
                />
              )}
              {tab === "files" && (
                <FilesLibraryView onJumpToSpace={openSpaceInKnowledge} />
              )}
              {tab === "search" && <SearchView />}
              {tab === "map" && (
                <KnowledgeMap onLocateInKnowledge={openItemInKnowledge} />
              )}
              {tab === "experiments" && <ExperimentsView />}
              {tab === "reviews" && <ReviewQueue />}
              {tab === "models" && <ModelSettingsView />}
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
      <AgentHubModal
        open={agentHubOpen}
        initialMode={agentHubMode}
        initialAgentName={agentHubTarget}
        onClose={() => setAgentHubOpen(false)}
        onChanged={(nextSpaceId) => {
          setSpacesVersion((v) => v + 1);
          if (nextSpaceId) {
            openSpaceInKnowledge(nextSpaceId);
          }
        }}
      />
      <ContextMenu menu={sidebarMenu} onClose={() => setSidebarMenu(null)} />
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
            <button
              type="button"
              onClick={() => navigate("models")}
              title="点击配置 AI 模型与 API Key"
              className="hidden font-mono text-[10.5px] hover:underline md:inline"
              style={{ color: "var(--nf-text-muted)" }}
            >
              Model: {health.model_adapter} · Embed: {health.embed_adapter}
            </button>
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

        <div className="flex items-center gap-3">
          {isNativeDesktop && (
            <button
              type="button"
              onClick={() => void toggleAutoStart()}
              title="Windows 开机后静默进右下角系统托盘（不弹主窗口）"
              className="hidden items-center gap-1 text-[10.5px] hover:underline sm:inline-flex"
              style={{
                color: autoStartEnabled
                  ? "var(--nf-accent)"
                  : "var(--nf-text-muted)",
              }}
            >
              <span>开机自启：{autoStartEnabled ? "开" : "关"}</span>
            </button>
          )}
          <button
            type="button"
            onClick={() => setTaskCaptureEnabled((v) => !v)}
            title="Agent 完成任务后自动弹出临时入库悬浮窗（不常驻、自动消失）"
            className="hidden items-center gap-1 text-[10.5px] hover:underline sm:inline-flex"
            style={{
              color: taskCaptureEnabled
                ? "var(--nf-accent)"
                : "var(--nf-text-muted)",
            }}
          >
            <span>任务入库弹窗：{taskCaptureEnabled ? "开" : "关"}</span>
          </button>
          <button
            type="button"
            onClick={() => void triggerTestCapturePopup()}
            title="立即测试一次任务完成临时悬浮窗效果"
            className="hidden text-[10.5px] hover:underline sm:inline"
            style={{ color: "var(--nf-text-muted)" }}
          >
            测试弹窗
          </button>
          <button
            type="button"
            onClick={() => navigate("theme")}
            className="font-mono text-[10.5px] hover:underline"
            style={{ color: "var(--nf-text-muted)" }}
          >
            {isPluginLocked
              ? `风格插件 · ${activePlugin.name}`
              : `Nesti Fluent 2.0 · ${
                  config.preset === "glacier"
                    ? resolvedTheme === "dark"
                      ? "极夜"
                      : "晨雾"
                    : config.preset
                }`}
          </button>
        </div>
      </footer>

      {/* Ctrl+K 桌面级全局命令面板（模块 + 全库知识 + 文件库直达） */}
      {commandOpen && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center pt-16 backdrop-blur-[2px]"
          style={{ background: "var(--nf-bg-overlay)" }}
          onClick={() => setCommandOpen(false)}
        >
          <div
            className="w-full max-w-xl overflow-hidden rounded-xl p-2"
            style={{
              background: "var(--nf-bg-surface)",
              border: "1px solid var(--nf-border-default)",
              boxShadow: "var(--nf-shadow-lg)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              className="mb-1.5 flex items-center gap-2 rounded-lg border px-2.5 py-2"
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
                  if (e.key === "Enter") {
                    if (filteredCommands[0]) {
                      navigate(filteredCommands[0].id);
                      setCommandOpen(false);
                    } else if (filteredKnowledge[0]) {
                      const k = filteredKnowledge[0];
                      openItemInKnowledge(k.space_id, k.id);
                      setCommandOpen(false);
                    } else if (filteredFiles[0]) {
                      setQuickReadingFile(filteredFiles[0]);
                      setCommandOpen(false);
                    }
                  }
                }}
                placeholder="搜模块、知识标题/正文、或 Word/PDF/Excel 文件名…（ESC 关闭）"
                className="w-full bg-transparent text-xs outline-none"
                style={{ color: "var(--nf-text-primary)" }}
              />
              {cmdLoading && (
                <span
                  className="shrink-0 text-[10px]"
                  style={{ color: "var(--nf-text-muted)" }}
                >
                  索引中…
                </span>
              )}
            </div>
            <div className="max-h-96 space-y-2 overflow-y-auto px-0.5">
              {filteredCommands.length > 0 && (
                <div>
                  <div
                    className="px-2 py-1 text-[10px] font-semibold tracking-wider uppercase"
                    style={{ color: "var(--nf-text-muted)" }}
                  >
                    功能模块
                  </div>
                  <div className="space-y-0.5">
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
                  </div>
                </div>
              )}

              {filteredKnowledge.length > 0 && (
                <div>
                  <div
                    className="px-2 py-1 text-[10px] font-semibold tracking-wider uppercase"
                    style={{ color: "var(--nf-text-muted)" }}
                  >
                    知识条目 ({filteredKnowledge.length})
                  </div>
                  <div className="space-y-0.5">
                    {filteredKnowledge.map((k) => {
                      const spName = spaces.find((s) => s.id === k.space_id)?.name;
                      return (
                        <button
                          key={k.id}
                          type="button"
                          onClick={() => {
                            openItemInKnowledge(k.space_id, k.id);
                            setCommandOpen(false);
                          }}
                          className="nf-nav-item"
                        >
                          <Icon name="knowledge" size={14} />
                          <span className="truncate">{k.title}</span>
                          {spName && (
                            <span
                              className="ml-auto shrink-0 rounded px-1.5 py-0.5 text-[10px]"
                              style={{
                                background: "var(--nf-accent-soft)",
                                color: "var(--nf-accent)",
                              }}
                            >
                              {spName.replace(/^Agent\s*·\s*/i, "")}
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              {filteredFiles.length > 0 && (
                <div>
                  <div
                    className="px-2 py-1 text-[10px] font-semibold tracking-wider uppercase"
                    style={{ color: "var(--nf-text-muted)" }}
                  >
                    文件库文档 · 点击原位阅读 ({filteredFiles.length})
                  </div>
                  <div className="space-y-0.5">
                    {filteredFiles.map((f) => (
                      <button
                        key={`${f.item_id}-${f.id}`}
                        type="button"
                        onClick={() => {
                          setQuickReadingFile(f);
                          setCommandOpen(false);
                        }}
                        className="nf-nav-item"
                      >
                        <span
                          className="shrink-0 rounded px-1.5 py-0.5 font-mono text-[9.5px] font-bold uppercase"
                          style={{
                            background: "var(--nf-accent-soft)",
                            color: "var(--nf-accent)",
                          }}
                        >
                          {f.kind}
                        </span>
                        <span className="truncate">{f.filename}</span>
                        <span
                          className="ml-auto max-w-[120px] shrink-0 truncate text-[10px]"
                          style={{ color: "var(--nf-text-muted)" }}
                        >
                          {f.space_name || f.item_title}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {filteredCommands.length === 0 &&
                filteredKnowledge.length === 0 &&
                filteredFiles.length === 0 && (
                  <p
                    className="px-3 py-6 text-center text-xs"
                    style={{ color: "var(--nf-text-muted)" }}
                  >
                    未找到匹配的模块、知识或文件
                  </p>
                )}
            </div>
          </div>
        </div>
      )}

      <DocumentReaderModal
        media={quickReadingFile}
        onClose={() => setQuickReadingFile(null)}
      />

      <TaskCaptureToast
        suggestion={toastSuggestion}
        onClose={() => setToastSuggestion(null)}
        onAccepted={() => setSpacesVersion((v) => v + 1)}
        onJumpToSpace={openSpaceInKnowledge}
      />
    </div>
  );
}
