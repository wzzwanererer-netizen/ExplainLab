import { useEffect, useState } from "react";
import { api } from "../api/client";
import type {
  Conversation,
  ExperimentSession,
  HealthResponse,
  KnowledgeItem,
  ReviewRequest,
  Space,
} from "../api/types";
import { Icon } from "./Icons";

interface Props {
  onNavigate: (tab: "chat" | "knowledge" | "search" | "map" | "experiments" | "reviews" | "status" | "theme") => void;
}

export function DashboardView({ onNavigate }: Props) {
  const [knowledge, setKnowledge] = useState<KnowledgeItem[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [reviews, setReviews] = useState<ReviewRequest[]>([]);
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [experiments, setExperiments] = useState<ExperimentSession[]>([]);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      const [k, c, r, s, e, h] = await Promise.allSettled([
        api.listKnowledge(),
        api.listConversations(),
        api.listReviews("pending"),
        api.listSpaces(),
        api.listExperiments(),
        api.getHealth(),
      ]);
      if (k.status === "fulfilled") setKnowledge(k.value);
      if (c.status === "fulfilled") setConversations(c.value);
      if (r.status === "fulfilled") setReviews(r.value);
      if (s.status === "fulfilled") setSpaces(s.value);
      if (e.status === "fulfilled") setExperiments(e.value);
      if (h.status === "fulfilled") setHealth(h.value);
      setLoading(false);
    })();
  }, []);

  const cardStyle = {
    background: "var(--nf-bg-surface)",
    border: "1px solid var(--nf-border-subtle)",
    borderRadius: "var(--nf-radius-md)",
    boxShadow: "var(--nf-shadow-sm)",
  };

  return (
    <div className="space-y-4">
      <div
        className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"
        style={cardStyle}
      >
        <div>
          <h2 className="text-sm font-semibold" style={{ color: "var(--nf-text-primary)" }}>
            工作台 · Nesti Fluent
          </h2>
          <p className="text-xs" style={{ color: "var(--nf-text-muted)" }}>
            全部数据实时来自本地 ExplainLab V2 后端，无虚构统计。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => onNavigate("chat")}
            className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium"
            style={{
              background: "var(--nf-bg-surface-subtle)",
              border: "1px solid var(--nf-border-default)",
              color: "var(--nf-text-primary)",
            }}
          >
            <Icon name="chat" size={14} /> 研究对话
          </button>
          <button
            type="button"
            onClick={() => onNavigate("knowledge")}
            className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium"
            style={{
              background: "var(--nf-accent)",
              color: "var(--nf-text-on-accent)",
            }}
          >
            <Icon name="knowledge" size={14} /> 打开知识库 / 导入 ZIP
          </button>
        </div>
      </div>

      {loading ? (
        <p role="status" className="text-xs" style={{ color: "var(--nf-text-muted)" }}>
          正在加载工作台数据…
        </p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[1.35fr_1fr]">
          <div className="space-y-4">
            <section style={cardStyle} className="overflow-hidden">
              <div
                className="flex items-center justify-between px-4 py-2.5 text-xs font-semibold"
                style={{ borderBottom: "1px solid var(--nf-border-subtle)" }}
              >
                <span>最近知识（{knowledge.length}）</span>
                <button
                  type="button"
                  onClick={() => onNavigate("knowledge")}
                  className="text-xs font-medium"
                  style={{ color: "var(--nf-accent)" }}
                >
                  查看全部
                </button>
              </div>
              {knowledge.length === 0 ? (
                <p className="p-4 text-xs" style={{ color: "var(--nf-text-muted)" }}>
                  暂无知识条目。前往「知识库」新建、导入 Markdown/ZIP，或在「研究对话」中提取。
                </p>
              ) : (
                <ul className="divide-y" style={{ borderColor: "var(--nf-border-subtle)" }}>
                  {knowledge.slice(0, 6).map((item) => (
                    <li
                      key={item.id}
                      onClick={() => onNavigate("knowledge")}
                      className="flex cursor-pointer items-center justify-between gap-3 px-4 py-2.5 text-xs transition-colors hover:opacity-85"
                    >
                      <span className="truncate font-medium">{item.title}</span>
                      <span
                        className="shrink-0 rounded-full px-2 py-0.5 text-[11px]"
                        style={{
                          background: "var(--nf-accent-soft)",
                          color: "var(--nf-accent)",
                        }}
                      >
                        {item.status}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section style={cardStyle} className="overflow-hidden">
              <div
                className="flex items-center justify-between px-4 py-2.5 text-xs font-semibold"
                style={{ borderBottom: "1px solid var(--nf-border-subtle)" }}
              >
                <span>最近研究对话（{conversations.length}）</span>
                <button
                  type="button"
                  onClick={() => onNavigate("chat")}
                  className="text-xs font-medium"
                  style={{ color: "var(--nf-accent)" }}
                >
                  进入对话
                </button>
              </div>
              {conversations.length === 0 ? (
                <p className="p-4 text-xs" style={{ color: "var(--nf-text-muted)" }}>
                  暂无研究会话。
                </p>
              ) : (
                <ul className="divide-y" style={{ borderColor: "var(--nf-border-subtle)" }}>
                  {conversations.slice(0, 5).map((c) => (
                    <li
                      key={c.id}
                      onClick={() => onNavigate("chat")}
                      className="flex cursor-pointer items-center justify-between px-4 py-2.5 text-xs"
                    >
                      <span className="truncate font-medium">{c.title}</span>
                      <span style={{ color: "var(--nf-text-muted)" }}>
                        {new Date(c.updated_at).toLocaleDateString("zh-CN")}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>

          <div className="space-y-4">
            <section style={cardStyle} className="p-4">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-semibold">待审核事项</span>
                <span
                  className="rounded-full px-2 py-0.5 text-[11px] font-medium"
                  style={{
                    background: reviews.length ? "var(--nf-status-warning-bg)" : "var(--nf-status-success-bg)",
                    color: reviews.length ? "var(--nf-status-warning)" : "var(--nf-status-success)",
                  }}
                >
                  {reviews.length} 待处理
                </span>
              </div>
              {reviews.length === 0 ? (
                <p className="text-xs" style={{ color: "var(--nf-text-muted)" }}>
                  当前无待审核变更。
                </p>
              ) : (
                <div className="space-y-2">
                  {reviews.slice(0, 3).map((r) => (
                    <div
                      key={r.id}
                      className="rounded-md p-2 text-xs"
                      style={{ background: "var(--nf-bg-surface-subtle)", border: "1px solid var(--nf-border-subtle)" }}
                    >
                      <div className="font-medium">{r.action} · {r.item_id.slice(0, 8)}…</div>
                      {r.reason && <div style={{ color: "var(--nf-text-muted)" }}>{r.reason}</div>}
                    </div>
                  ))}
                  <button
                    type="button"
                    onClick={() => onNavigate("reviews")}
                    className="rounded-md px-3 py-1 text-xs font-medium"
                    style={{ background: "var(--nf-accent)", color: "var(--nf-text-on-accent)" }}
                  >
                    前往审核队列
                  </button>
                </div>
              )}
            </section>

            <section style={cardStyle} className="p-4">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-semibold">知识空间（{spaces.length}）与实验（{experiments.length}）</span>
                <button
                  type="button"
                  onClick={() => onNavigate("experiments")}
                  className="text-xs font-medium"
                  style={{ color: "var(--nf-accent)" }}
                >
                  进入实验
                </button>
              </div>
              <div className="space-y-1.5 text-xs">
                {spaces.map((s) => (
                  <div key={s.id} className="flex items-center justify-between">
                    <span>{s.name}</span>
                    <span style={{ color: "var(--nf-text-muted)" }}>{s.kind}</span>
                  </div>
                ))}
              </div>
            </section>

            <section style={cardStyle} className="p-4">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-semibold">本地后端运行态</span>
                <button
                  type="button"
                  onClick={() => onNavigate("status")}
                  className="text-xs font-medium"
                  style={{ color: "var(--nf-accent)" }}
                >
                  详情
                </button>
              </div>
              {health ? (
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <span style={{ color: "var(--nf-text-muted)" }}>数据库</span>
                    <div className="font-mono">{health.database.dialect} · {health.database.connected ? "已连接" : "断开"}</div>
                  </div>
                  <div>
                    <span style={{ color: "var(--nf-text-muted)" }}>模型适配层</span>
                    <div className="font-mono">{health.model_adapter}</div>
                  </div>
                  <div>
                    <span style={{ color: "var(--nf-text-muted)" }}>向量来源</span>
                    <div className="font-mono">{health.embed_adapter}</div>
                  </div>
                  <div>
                    <span style={{ color: "var(--nf-text-muted)" }}>版本</span>
                    <div className="font-mono">v{health.version}</div>
                  </div>
                </div>
              ) : (
                <p className="text-xs" style={{ color: "var(--nf-status-danger)" }}>
                  无法连接本地后端（127.0.0.1:8000）
                </p>
              )}
            </section>
          </div>
        </div>
      )}
    </div>
  );
}
