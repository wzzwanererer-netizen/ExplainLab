import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type {
  ExperimentCompleteResult,
  ExperimentKind,
  ExperimentSession,
  KnowledgeItem,
  Space,
} from "../api/types";
import {
  canGenerate,
  MODE_META,
  MODE_ORDER,
  selectionHint,
} from "../lib/experiments";
import { STATUS_LABEL } from "../lib/graphLayout";
import { KnowledgeDetail } from "./KnowledgeDetail";
import { ChainRunner } from "./experiments/ChainRunner";
import { CompareRunner } from "./experiments/CompareRunner";
import { ExperimentHistory } from "./experiments/ExperimentHistory";
import { QuizRunner } from "./experiments/QuizRunner";

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

const DEFAULT_COUNT: Record<ExperimentKind, number> = { quiz: 5, compare: 2, chain: 8 };
const COUNT_RANGE: Record<ExperimentKind, { min: number; max: number; label: string }> = {
  quiz: { min: 1, max: 20, label: "题目数量" },
  compare: { min: 2, max: 2, label: "" },
  chain: { min: 2, max: 12, label: "最大步数" },
};

/** 模式选择卡片：选中态以强调色描边 + 底色，呈现约束与是否需模型。 */
function ModeCard({
  kind,
  selected,
  onSelect,
}: {
  kind: ExperimentKind;
  selected: boolean;
  onSelect: () => void;
}) {
  const meta = MODE_META[kind];
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className="flex flex-col gap-1 rounded-[14px] border p-4 text-left transition-all"
      style={
        selected
          ? {
              borderColor: "var(--nesti-accent)",
              background: "color-mix(in srgb, var(--nesti-accent) 10%, var(--nesti-surface-1))",
              boxShadow: "0 0 0 1px color-mix(in srgb, var(--nesti-accent) 30%, transparent)",
            }
          : {
              borderColor: "var(--nesti-border-subtle)",
              background: "var(--nesti-surface-1)",
            }
      }
    >
      <div className="flex items-center justify-between gap-2">
        <span
          className="text-base font-semibold"
          style={{ color: selected ? "var(--nesti-accent)" : "var(--nesti-text-primary)" }}
        >
          {meta.label}
        </span>
        <span
          className="rounded-full px-2.5 py-0.5 text-xs font-medium"
          style={
            meta.needsModel
              ? {
                  background: "var(--nesti-surface-2)",
                  color: "var(--nesti-text-secondary)",
                  border: "1px solid var(--nesti-border-subtle)",
                }
              : {
                  background: "color-mix(in srgb, var(--nf-status-success) 14%, transparent)",
                  color: "var(--nf-status-success)",
                }
          }
        >
          {meta.needsModel ? "需模型" : "确定性"}
        </span>
      </div>
      <span className="text-xs" style={{ color: "var(--nesti-text-tertiary)" }}>
        {meta.tagline}
      </span>
      <span
        className="mt-1 text-sm leading-relaxed"
        style={{ color: "var(--nesti-text-secondary)" }}
      >
        {meta.description}
      </span>
      <span
        className="mt-1 text-xs font-medium"
        style={{ color: selected ? "var(--nesti-accent)" : "var(--nesti-text-tertiary)" }}
      >
        {meta.requirement}
      </span>
    </button>
  );
}

/**
 * M5 交互式知识实验编排页：模式卡片 + 知识选择 + 生成控制 + 三模式 Runner + 历史。
 * 测验 / 对比经真实模型生成（未配置时如实报 503）；学习路径确定性推导。
 * 点击知识可打开治理详情抽屉，复用 M2 治理组件。全部数据来自真实 API。
 */
export function ExperimentsView() {
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [spaceId, setSpaceId] = useState("");
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [itemsLoading, setItemsLoading] = useState(true);
  const [mode, setMode] = useState<ExperimentKind>("quiz");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [count, setCount] = useState(DEFAULT_COUNT.quiz);
  const [generating, setGenerating] = useState(false);
  const [session, setSession] = useState<ExperimentSession | null>(null);
  const [history, setHistory] = useState<ExperimentSession[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [detailItem, setDetailItem] = useState<KnowledgeItem | null>(null);

  const meta = MODE_META[mode];
  const range = COUNT_RANGE[mode];

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      setHistory(await api.listExperiments());
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        setSpaces(await api.listSpaces());
      } catch (err) {
        setError(errorMessage(err));
      }
    })();
    void loadHistory();
  }, [loadHistory]);

  useEffect(() => {
    setSelectedIds([]);
    setItemsLoading(true);
    void (async () => {
      try {
        setItems(await api.listKnowledge(spaceId || undefined));
      } catch (err) {
        setError(errorMessage(err));
      } finally {
        setItemsLoading(false);
      }
    })();
  }, [spaceId]);

  function selectMode(next: ExperimentKind) {
    setMode(next);
    setSelectedIds([]);
    setCount(DEFAULT_COUNT[next]);
    setSession(null);
    setError(null);
    setNotice(null);
  }

  function toggleItem(id: string) {
    setError(null);
    setSelectedIds((prev) => {
      if (mode === "chain") return prev.includes(id) ? [] : [id];
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (meta.max !== null && prev.length >= meta.max) return prev;
      return [...prev, id];
    });
  }

  const ready = canGenerate(mode, selectedIds.length);
  const hint = selectionHint(mode, selectedIds.length);

  async function handleGenerate() {
    if (!ready || generating) return;
    setGenerating(true);
    setError(null);
    setNotice(null);
    try {
      const created = await api.createExperiment({
        kind: mode,
        item_ids: selectedIds,
        space_id: spaceId || null,
        count,
        seed_id: mode === "chain" ? selectedIds[0] : null,
      });
      setSession(created);
      setHistory((prev) => [created, ...prev.filter((s) => s.id !== created.id)]);
      setNotice(`已生成${meta.label}。`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setGenerating(false);
    }
  }

  async function handleRetry(orig: ExperimentSession) {
    setGenerating(true);
    setError(null);
    try {
      const created = await api.createExperiment({
        kind: orig.kind,
        item_ids: orig.item_ids,
        space_id: orig.space_id,
        count,
        seed_id: orig.kind === "chain" ? orig.item_ids[0] : null,
      });
      setSession(created);
      setHistory((prev) => [created, ...prev.filter((s) => s.id !== created.id)]);
      setNotice("已重新生成，可再次作答。");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setGenerating(false);
    }
  }

  function handleCompleted(result: ExperimentCompleteResult) {
    setSession(result.session);
    setHistory((prev) => prev.map((s) => (s.id === result.session.id ? result.session : s)));
  }

  function handleReopen(s: ExperimentSession) {
    setSession(s);
    setMode(s.kind);
    setError(null);
    setNotice(null);
  }

  async function handleDelete(id: string) {
    try {
      await api.deleteExperiment(id);
      setHistory((prev) => prev.filter((s) => s.id !== id));
      if (session?.id === id) setSession(null);
      setNotice("已删除实验。");
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  const openDetail = useCallback(async (itemId: string) => {
    setError(null);
    try {
      setDetailItem(await api.getKnowledge(itemId));
    } catch (err) {
      setError(errorMessage(err));
    }
  }, []);

  const handleDetailChanged = useCallback(async () => {
    if (!detailItem) return;
    try {
      setDetailItem(await api.getKnowledge(detailItem.id));
    } catch {
      setDetailItem(null);
    }
    try {
      setItems(await api.listKnowledge(spaceId || undefined));
    } catch {
      // 列表刷新失败不阻断详情操作
    }
  }, [detailItem, spaceId]);

  const selectedItems = useMemo(
    () => items.filter((i) => selectedIds.includes(i.id)),
    [items, selectedIds],
  );

  const fieldStyle = {
    background: "var(--nesti-surface-0)",
    borderColor: "var(--nesti-border-subtle)",
    color: "var(--nesti-text-primary)",
  };

  return (
    <div className="space-y-5">
      <header className="space-y-1">
        <div
          className="text-[10.5px] font-semibold tracking-[0.14em] uppercase"
          style={{ color: "var(--nesti-accent)" }}
        >
          KNOWLEDGE LAB · 知识实验
        </div>
        <h2
          className="text-lg font-semibold tracking-tight"
          style={{ color: "var(--nesti-text-primary)" }}
        >
          交互式知识实验
        </h2>
        <p className="text-xs" style={{ color: "var(--nesti-text-secondary)" }}>
          围绕你的知识库主动学习：出题测验、对比辨析、编排先修路径。
          测验与对比由真实模型生成，学习路径由知识关系确定性推导。
        </p>
      </header>

      <div className="grid gap-3 sm:grid-cols-3">
        {MODE_ORDER.map((kind) => (
          <ModeCard
            key={kind}
            kind={kind}
            selected={mode === kind}
            onSelect={() => selectMode(kind)}
          />
        ))}
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-xl border border-red-400/40 bg-red-500/10 p-3 text-sm text-red-500"
        >
          {error}
        </div>
      )}
      {notice && (
        <div
          role="status"
          className="rounded-xl border border-emerald-500/35 bg-emerald-500/10 p-3 text-sm text-emerald-600"
        >
          {notice}
        </div>
      )}

      <div className="flex flex-col gap-4 lg:flex-row">
        <div
          className="w-full shrink-0 space-y-3 rounded-[14px] border p-4 shadow-xs lg:w-96"
          style={{
            background: "var(--nesti-surface-1)",
            borderColor: "var(--nesti-border-subtle)",
          }}
        >
          <div className="flex items-center justify-between gap-2">
            <h3
              className="text-sm font-semibold"
              style={{ color: "var(--nesti-text-primary)" }}
            >
              选择知识
            </h3>
            <select
              value={spaceId}
              onChange={(e) => setSpaceId(e.target.value)}
              aria-label="知识空间"
              className="rounded-lg border px-3 py-1.5 text-sm outline-none"
              style={fieldStyle}
            >
              <option value="">全部空间</option>
              {spaces.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                  {s.kind === "personal" ? "（个人）" : ""}
                </option>
              ))}
            </select>
          </div>

          <div className="max-h-72 space-y-1.5 overflow-auto pr-1" role="group" aria-label="知识列表">
            {itemsLoading ? (
              <p role="status" className="text-sm" style={{ color: "var(--nesti-text-secondary)" }}>
                正在加载知识…
              </p>
            ) : items.length === 0 ? (
              <p className="text-sm" style={{ color: "var(--nesti-text-secondary)" }}>
                当前空间暂无知识。可在「对话」提取或「知识库」新增。
              </p>
            ) : (
              items.map((item) => {
                const checked = selectedIds.includes(item.id);
                const blocked =
                  !checked && meta.max !== null && selectedIds.length >= meta.max && mode !== "chain";
                return (
                  <label
                    key={item.id}
                    className={`flex cursor-pointer items-start gap-2 rounded-lg border px-2.5 py-2 text-sm transition-colors ${
                      blocked ? "cursor-not-allowed opacity-40" : ""
                    }`}
                    style={
                      checked
                        ? {
                            borderColor: "var(--nesti-accent)",
                            background: "color-mix(in srgb, var(--nesti-accent) 9%, transparent)",
                          }
                        : {
                            borderColor: "var(--nesti-border-subtle)",
                            background: "var(--nesti-surface-0)",
                          }
                    }
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={blocked}
                      onChange={() => toggleItem(item.id)}
                      className="mt-0.5 h-4 w-4 shrink-0"
                      style={{ accentColor: meta.accent.hex }}
                      aria-label={item.title}
                    />
                    <span className="min-w-0 flex-1">
                      <span
                        className="block truncate font-medium"
                        style={{ color: "var(--nesti-text-primary)" }}
                        title={item.title}
                      >
                        {item.title}
                      </span>
                      <span className="text-xs" style={{ color: "var(--nesti-text-tertiary)" }}>
                        {STATUS_LABEL[item.status]}
                        {mode === "chain" && checked ? " · 目标知识" : ""}
                      </span>
                    </span>
                  </label>
                );
              })
            )}
          </div>

          {mode !== "compare" && (
            <div
              className="space-y-1.5 rounded-lg border p-3"
              style={{
                background: "var(--nesti-surface-0)",
                borderColor: "var(--nesti-border-subtle)",
              }}
            >
              <div
                className="flex items-center justify-between text-xs"
                style={{ color: "var(--nesti-text-secondary)" }}
              >
                <span>{range.label}</span>
                <span className="font-semibold" style={{ color: "var(--nesti-accent)" }}>
                  {count}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setCount((c) => Math.max(range.min, c - 1))}
                  disabled={count <= range.min}
                  aria-label="减少"
                  className="h-7 w-7 shrink-0 rounded-md border disabled:opacity-40"
                  style={{
                    borderColor: "var(--nesti-border-strong)",
                    color: "var(--nesti-text-primary)",
                  }}
                >
                  −
                </button>
                <input
                  type="range"
                  min={range.min}
                  max={range.max}
                  value={count}
                  onChange={(e) => setCount(Number(e.target.value))}
                  aria-label={range.label}
                  className="h-1.5 flex-1 cursor-pointer"
                  style={{ accentColor: meta.accent.hex }}
                />
                <button
                  type="button"
                  onClick={() => setCount((c) => Math.min(range.max, c + 1))}
                  disabled={count >= range.max}
                  aria-label="增加"
                  className="h-7 w-7 shrink-0 rounded-md border disabled:opacity-40"
                  style={{
                    borderColor: "var(--nesti-border-strong)",
                    color: "var(--nesti-text-primary)",
                  }}
                >
                  +
                </button>
              </div>
            </div>
          )}

          <div
            className="flex items-center justify-between text-xs"
            style={{ color: "var(--nesti-text-tertiary)" }}
          >
            <span>
              已选 {selectedIds.length} 条
              {selectedItems.length > 0 && mode === "compare"
                ? ` · ${selectedItems.map((i) => i.title).join(" ↔ ")}`
                : ""}
            </span>
          </div>
          {hint && <p className="text-xs text-amber-600">{hint}</p>}

          <button
            type="button"
            onClick={() => void handleGenerate()}
            disabled={!ready || generating}
            className="w-full rounded-[9px] px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
            style={{ background: "var(--nesti-accent)" }}
          >
            {generating ? "生成中…" : `生成${meta.label}`}
          </button>
          {!ready && (
            <p className="text-center text-xs" style={{ color: "var(--nesti-text-tertiary)" }}>
              {meta.requirement}
            </p>
          )}
        </div>

        <div className="min-w-0 flex-1 space-y-4">
          {session ? (
            <div className="space-y-4">
              <div
                className="flex flex-wrap items-center gap-2 rounded-[14px] border p-3"
                style={{
                  background: "var(--nesti-surface-1)",
                  borderColor: "var(--nesti-border-subtle)",
                }}
              >
                <span
                  className="rounded-full px-2.5 py-0.5 text-xs font-medium"
                  style={{
                    background: "color-mix(in srgb, var(--nesti-accent) 12%, transparent)",
                    color: "var(--nesti-accent)",
                  }}
                >
                  {MODE_META[session.kind].label}
                </span>
                <span
                  className="min-w-0 flex-1 truncate text-sm font-medium"
                  style={{ color: "var(--nesti-text-primary)" }}
                  title={session.title}
                >
                  {session.title}
                </span>
                <button
                  type="button"
                  onClick={() => setSession(null)}
                  className="shrink-0 rounded-lg border px-3 py-1 text-xs font-medium"
                  style={{
                    borderColor: "var(--nesti-border-strong)",
                    color: "var(--nesti-text-primary)",
                  }}
                >
                  关闭
                </button>
              </div>
              {session.kind === "quiz" && (
                <QuizRunner
                  session={session}
                  onOpenItem={(id) => void openDetail(id)}
                  onCompleted={handleCompleted}
                  onRetry={(s) => void handleRetry(s)}
                  onError={setError}
                />
              )}
              {session.kind === "compare" && (
                <CompareRunner
                  session={session}
                  onOpenItem={(id) => void openDetail(id)}
                  onError={setError}
                />
              )}
              {session.kind === "chain" && (
                <ChainRunner session={session} onOpenItem={(id) => void openDetail(id)} />
              )}
            </div>
          ) : (
            <div
              className="flex h-full min-h-64 flex-col items-center justify-center rounded-[14px] border border-dashed p-8 text-center"
              style={{
                background: "var(--nesti-surface-1)",
                borderColor: "var(--nesti-border-strong)",
              }}
            >
              <span className="text-3xl" style={{ color: "var(--nesti-accent)" }}>
                ✦
              </span>
              <p className="mt-3 text-sm font-medium" style={{ color: "var(--nesti-text-primary)" }}>
                选择「{meta.label}」模式与知识，点击生成开始实验。
              </p>
              <p className="mt-1 text-xs" style={{ color: "var(--nesti-text-secondary)" }}>
                {meta.description}
              </p>
            </div>
          )}

          <ExperimentHistory
            sessions={history}
            loading={historyLoading}
            activeId={session?.id ?? null}
            onReopen={handleReopen}
            onDelete={(id) => void handleDelete(id)}
          />
        </div>
      </div>

      {detailItem && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div
            className="absolute inset-0 bg-slate-950/40 backdrop-blur-[2px]"
            onClick={() => setDetailItem(null)}
            aria-hidden
          />
          <aside
            className="exp-fade-in relative z-10 h-full w-full max-w-md overflow-auto border-l p-5 shadow-xl"
            style={{
              background: "var(--nesti-surface-1)",
              borderColor: "var(--nesti-border-subtle)",
            }}
          >
            <div className="flex items-start justify-between gap-2">
              <h3
                className="text-base font-semibold"
                style={{ color: "var(--nesti-text-primary)" }}
              >
                {detailItem.title}
              </h3>
              <button
                type="button"
                onClick={() => setDetailItem(null)}
                className="shrink-0 rounded-lg border px-2.5 py-1 text-xs font-medium"
                style={{
                  borderColor: "var(--nesti-border-strong)",
                  color: "var(--nesti-text-primary)",
                }}
              >
                关闭
              </button>
            </div>
            <p
              className="mt-2 whitespace-pre-wrap text-sm leading-relaxed"
              style={{ color: "var(--nesti-text-secondary)" }}
            >
              {detailItem.content}
            </p>
            <KnowledgeDetail
              item={detailItem}
              onNotice={setNotice}
              onError={setError}
              onChanged={() => void handleDetailChanged()}
            />
          </aside>
        </div>
      )}
    </div>
  );
}