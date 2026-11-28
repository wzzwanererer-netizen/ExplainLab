import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type {
  AgentStatus,
  Conversation,
  ExperimentSession,
  HealthResponse,
  KnowledgeItem,
  LibraryMediaItem,
  ReviewRequest,
  Space,
} from "../api/types";
import { Icon } from "./Icons";

interface Props {
  onNavigate: (
    tab:
      | "chat"
      | "knowledge"
      | "files"
      | "search"
      | "map"
      | "experiments"
      | "reviews"
      | "models"
      | "status"
      | "theme",
  ) => void;
  onOpenAgentHub?: () => void;
  onJumpToItem?: (spaceId: string | null | undefined, itemId: string) => void;
}

function fmtBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const STATUS_ZH: Record<string, string> = {
  active: "已生效",
  draft: "草稿",
  archived: "已归档",
};

/**
 * Nesti · AI 工作空间首页（Airy Techwear Atelier · 对齐官方设定图视觉语言）
 */
export function DashboardView({ onNavigate, onOpenAgentHub, onJumpToItem }: Props) {
  const [knowledge, setKnowledge] = useState<KnowledgeItem[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [reviews, setReviews] = useState<ReviewRequest[]>([]);
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [experiments, setExperiments] = useState<ExperimentSession[]>([]);
  const [files, setFiles] = useState<LibraryMediaItem[]>([]);
  const [agents, setAgents] = useState<AgentStatus[]>([]);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [showMascot, setShowMascot] = useState<boolean>(() => {
    try {
      return localStorage.getItem("nesti_dashboard_mascot") !== "false";
    } catch {
      return true;
    }
  });

  useEffect(() => {
    void (async () => {
      setLoading(true);
      const [k, c, r, s, e, h, f, a] = await Promise.allSettled([
        api.listKnowledge(),
        api.listConversations(),
        api.listReviews("pending"),
        api.listSpaces(),
        api.listExperiments(),
        api.getHealth(),
        api.listMediaLibrary(),
        api.discoverAgents(),
      ]);
      if (k.status === "fulfilled") setKnowledge(k.value);
      if (c.status === "fulfilled") setConversations(c.value);
      if (r.status === "fulfilled") setReviews(r.value);
      if (s.status === "fulfilled") setSpaces(s.value);
      if (e.status === "fulfilled") setExperiments(e.value);
      if (h.status === "fulfilled") setHealth(h.value);
      if (f.status === "fulfilled") setFiles(f.value);
      if (a.status === "fulfilled") setAgents(a.value);
      setLoading(false);
    })();
  }, []);

  const totalFileBytes = useMemo(
    () => files.reduce((acc, f) => acc + (f.size_bytes || 0), 0),
    [files],
  );
  const connectedAgents = useMemo(
    () => agents.filter((a) => a.connected),
    [agents],
  );

  const toggleMascot = () => {
    setShowMascot((v) => {
      const next = !v;
      try {
        localStorage.setItem("nesti_dashboard_mascot", next ? "true" : "false");
      } catch {
        // ignore
      }
      return next;
    });
  };

  return (
    <div className="mx-auto max-w-6xl space-y-8 pb-8">
      {/* Nesti 官方设定图风格 Hero 画报舞台 */}
      <section
        className="relative overflow-hidden rounded-2xl border px-8 py-7"
        style={{
          background: "var(--nf-bg-surface)",
          borderColor: "var(--nf-border-subtle)",
        }}
      >
        {/* 设定图同款：右上斜切淡冰蓝光带 + 工程标尺细线 */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-y-0 right-0 w-[44%] opacity-80"
          style={{
            background:
              "linear-gradient(128deg, transparent 0%, color-mix(in srgb, var(--nf-accent) 7%, transparent) 46%, color-mix(in srgb, var(--nf-brand-glacier) 15%, transparent) 100%)",
            clipPath: "polygon(18% 0, 100% 0, 100% 100%, 0% 100%)",
          }}
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute top-5 right-5 bottom-5 hidden w-px lg:block"
          style={{ background: "var(--nf-border-subtle)" }}
        />

        <div className="relative flex items-center justify-between gap-6">
          <div className="max-w-xl space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <span
                className="font-mono text-[10.5px] font-semibold tracking-[0.2em] uppercase"
                style={{ color: "var(--nf-accent)" }}
              >
                NESTI · AI WORKSPACE
              </span>
              <span
                className="h-px w-10"
                style={{ background: "var(--nf-border-default)" }}
              />
              <span
                className="text-[11px] tracking-[0.22em]"
                style={{ color: "var(--nf-text-muted)" }}
              >
                效率 · 创作 · 项目 · 生活
              </span>
            </div>

            <div className="space-y-1.5">
              <h2
                className="text-[26px] leading-tight font-semibold tracking-tight"
                style={{ color: "var(--nf-text-primary)" }}
              >
                把想法，交给我们一起实现吧。
              </h2>
              <p
                className="text-[13px] leading-relaxed"
                style={{ color: "var(--nf-text-secondary)" }}
              >
                多 Agent 长期记忆中枢与本地文档工作台。随时按{" "}
                <kbd
                  className="rounded border px-1.5 py-0.5 text-[11px]"
                  style={{
                    background: "var(--nf-bg-surface-subtle)",
                    borderColor: "var(--nf-border-default)",
                  }}
                >
                  Ctrl K
                </kbd>{" "}
                瞬搜全库知识或直达本地文档。
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2.5 pt-1">
              <button
                type="button"
                onClick={() => onNavigate("knowledge")}
                className="inline-flex items-center gap-2 rounded-[10px] px-4 py-2 text-xs font-semibold"
                style={{
                  background: "var(--nf-accent)",
                  color: "var(--nf-text-on-accent)",
                }}
              >
                <Icon name="knowledge" size={14} /> 进入知识库
              </button>
              <button
                type="button"
                onClick={() => onNavigate("files")}
                className="inline-flex items-center gap-2 rounded-[10px] border px-4 py-2 text-xs font-medium"
                style={{
                  background: "var(--nf-bg-surface)",
                  borderColor: "var(--nf-border-default)",
                  color: "var(--nf-text-primary)",
                }}
              >
                本地文件库
              </button>
              {onOpenAgentHub && (
                <button
                  type="button"
                  onClick={onOpenAgentHub}
                  className="inline-flex items-center gap-2 rounded-[10px] border px-4 py-2 text-xs font-medium"
                  style={{
                    background: "var(--nf-bg-surface)",
                    borderColor: "var(--nf-border-default)",
                    color: "var(--nf-text-primary)",
                  }}
                >
                  自选对话吸尘
                </button>
              )}
              <button
                type="button"
                onClick={() => onNavigate("map")}
                className="px-2 py-2 text-xs font-medium hover:underline"
                style={{ color: "var(--nf-text-secondary)" }}
              >
                知识星图 →
              </button>
            </div>
          </div>

          {/* 官方 Nesti Q 版形象画报角标（严格保留原立绘，可一键开关） */}
          <div className="relative hidden shrink-0 items-end sm:flex">
            {showMascot && (
              <img
                src="/nesti-chibi.png"
                alt="Nesti"
                draggable={false}
                className="h-[168px] w-auto object-contain select-none drop-shadow-[0_10px_18px_rgba(59,116,232,0.12)]"
              />
            )}
            <button
              type="button"
              onClick={toggleMascot}
              title={showMascot ? "隐藏首页 Nesti 插画" : "显示首页 Nesti 插画"}
              className="absolute right-0 -bottom-4 font-mono text-[10px] opacity-50 transition-opacity hover:opacity-100"
              style={{ color: "var(--nf-text-muted)" }}
            >
              {showMascot ? "收起立绘" : "显示立绘"}
            </button>
          </div>
        </div>
      </section>

      {/* 一体化 4 列精密标尺指标条（告别 4 个沉重小方盒） */}
      <section
        className="grid grid-cols-2 divide-y overflow-hidden rounded-2xl border lg:grid-cols-4 lg:divide-x lg:divide-y-0"
        style={{
          background: "var(--nf-bg-surface)",
          borderColor: "var(--nf-border-subtle)",
        }}
      >
        {[
          {
            idx: "01",
            label: "知识条目",
            value: String(knowledge.length),
            sub: `${spaces.length} 个知识空间`,
            onClick: () => onNavigate("knowledge"),
          },
          {
            idx: "02",
            label: "收编文件",
            value: String(files.length),
            sub: `占盘 ${fmtBytes(totalFileBytes)}`,
            onClick: () => onNavigate("files"),
          },
          {
            idx: "03",
            label: "已接入 AI 助手",
            value: String(connectedAgents.length),
            sub: connectedAgents.length
              ? connectedAgents
                  .slice(0, 2)
                  .map((a) => a.name)
                  .join(" · ")
              : "点击接入助手",
            onClick: () =>
              onOpenAgentHub ? onOpenAgentHub() : onNavigate("knowledge"),
          },
          {
            idx: "04",
            label: reviews.length > 0 ? "待审核变更" : "学习实验",
            value: String(reviews.length > 0 ? reviews.length : experiments.length),
            sub: reviews.length > 0 ? "前往审核队列确认" : "知识内化测验记录",
            onClick: () =>
              onNavigate(reviews.length > 0 ? "reviews" : "experiments"),
          },
        ].map((metric) => (
          <button
            key={metric.idx}
            type="button"
            onClick={metric.onClick}
            className="flex flex-col items-start justify-between px-6 py-5 text-left transition-colors hover:bg-[var(--nf-bg-surface-subtle)]"
            style={{ borderColor: "var(--nf-border-subtle)" }}
          >
            <div className="flex w-full items-center justify-between">
              <span
                className="text-xs font-medium"
                style={{ color: "var(--nf-text-secondary)" }}
              >
                {metric.label}
              </span>
              <span
                className="font-mono text-[10px]"
                style={{ color: "var(--nf-accent)" }}
              >
                {metric.idx}
              </span>
            </div>
            <div
              className="mt-3 text-[28px] leading-none font-semibold tracking-tight tabular-nums"
              style={{ color: "var(--nf-text-primary)" }}
            >
              {loading ? "—" : metric.value}
            </div>
            <div
              className="mt-2 w-full truncate text-[11px]"
              style={{ color: "var(--nf-text-muted)" }}
            >
              {metric.sub}
            </div>
          </button>
        ))}
      </section>

      <div className="nf-ruler" />

      {/* 主内容编辑部双栏 */}
      {loading ? (
        <p role="status" className="py-6 text-xs" style={{ color: "var(--nf-text-muted)" }}>
          正在同步本地工作空间数据…
        </p>
      ) : (
        <div className="grid gap-8 lg:grid-cols-[1.5fr_1fr]">
          {/* 左列：最近沉淀的知识（极简列表流，无套娃边框） */}
          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="nf-eyebrow">
                <span className="nf-eyebrow-index">A</span>
                <span>最近沉淀 · {knowledge.length}</span>
              </div>
              <button
                type="button"
                onClick={() => onNavigate("knowledge")}
                className="text-xs font-medium hover:underline"
                style={{ color: "var(--nf-accent)" }}
              >
                查看全部 →
              </button>
            </div>

            <div
              className="overflow-hidden rounded-2xl border"
              style={{
                background: "var(--nf-bg-surface)",
                borderColor: "var(--nf-border-subtle)",
              }}
            >
              {knowledge.length === 0 ? (
                <p className="px-6 py-10 text-xs" style={{ color: "var(--nf-text-muted)" }}>
                  暂无知识条目。前往「知识库」新建图文笔记，或用「文件夹哨兵」一键收编桌面文档。
                </p>
              ) : (
                <ul className="divide-y" style={{ borderColor: "var(--nf-border-subtle)" }}>
                  {knowledge.slice(0, 7).map((item) => (
                    <li
                      key={item.id}
                      onClick={() =>
                        onJumpToItem
                          ? onJumpToItem(item.space_id, item.id)
                          : onNavigate("knowledge")
                      }
                      className="flex cursor-pointer items-center justify-between gap-4 px-5 py-3.5 text-[13px] transition-colors hover:bg-[var(--nf-bg-surface-subtle)]"
                    >
                      <div className="flex min-w-0 items-center gap-3">
                        <span
                          className="h-1.5 w-1.5 shrink-0 rounded-full"
                          style={{
                            background:
                              item.status === "active"
                                ? "var(--nf-status-success)"
                                : "var(--nf-accent)",
                          }}
                        />
                        <span className="truncate font-medium">{item.title}</span>
                      </div>
                      <span
                        className="shrink-0 text-[11px]"
                        style={{ color: "var(--nf-text-muted)" }}
                      >
                        {STATUS_ZH[item.status] ?? item.status}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>

          {/* 右列：最近研究对话 + 本地引擎心跳 */}
          <div className="space-y-6">
            <section className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="nf-eyebrow">
                  <span className="nf-eyebrow-index">B</span>
                  <span>研究对话 · {conversations.length}</span>
                </div>
                <button
                  type="button"
                  onClick={() => onNavigate("chat")}
                  className="text-xs font-medium hover:underline"
                  style={{ color: "var(--nf-accent)" }}
                >
                  开始对话 →
                </button>
              </div>
              <div
                className="overflow-hidden rounded-2xl border"
                style={{
                  background: "var(--nf-bg-surface)",
                  borderColor: "var(--nf-border-subtle)",
                }}
              >
                {conversations.length === 0 ? (
                  <p className="px-5 py-6 text-xs" style={{ color: "var(--nf-text-muted)" }}>
                    暂无研究会话。
                  </p>
                ) : (
                  <ul className="divide-y" style={{ borderColor: "var(--nf-border-subtle)" }}>
                    {conversations.slice(0, 4).map((c) => (
                      <li
                        key={c.id}
                        onClick={() => onNavigate("chat")}
                        className="flex cursor-pointer items-center justify-between gap-3 px-5 py-3 text-xs transition-colors hover:bg-[var(--nf-bg-surface-subtle)]"
                      >
                        <span className="truncate font-medium">{c.title}</span>
                        <span
                          className="shrink-0 font-mono text-[10.5px] tabular-nums"
                          style={{ color: "var(--nf-text-muted)" }}
                        >
                          {new Date(c.updated_at).toLocaleDateString("zh-CN")}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </section>

            <section className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="nf-eyebrow">
                  <span className="nf-eyebrow-index">C</span>
                  <span>本地引擎</span>
                </div>
                <button
                  type="button"
                  onClick={() => onNavigate("models")}
                  className="text-xs font-medium hover:underline"
                  style={{ color: "var(--nf-accent)" }}
                >
                  配置模型 →
                </button>
              </div>
              <div
                className="space-y-2.5 rounded-2xl border px-5 py-4 text-xs"
                style={{
                  background: "var(--nf-bg-surface)",
                  borderColor: "var(--nf-border-subtle)",
                }}
              >
                <div className="flex items-center justify-between">
                  <span style={{ color: "var(--nf-text-secondary)" }}>数据库</span>
                  <span className="inline-flex items-center gap-1.5 font-mono text-[11px]">
                    <span
                      className="h-1.5 w-1.5 rounded-full"
                      style={{
                        background:
                          health?.status === "ok"
                            ? "var(--nf-status-success)"
                            : "var(--nf-status-warning)",
                      }}
                    />
                    {health ? `${health.database.dialect.toUpperCase()} · 就绪` : "连接中"}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span style={{ color: "var(--nf-text-secondary)" }}>推理模型</span>
                  <span className="font-mono text-[11px]">
                    {health?.model_adapter ?? "未配置"}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span style={{ color: "var(--nf-text-secondary)" }}>向量检索</span>
                  <span className="font-mono text-[11px]">
                    {health?.embed_adapter ?? "仅全文"}
                  </span>
                </div>
              </div>
            </section>
          </div>
        </div>
      )}
    </div>
  );
}
