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
  const a = meta.accent;
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`flex flex-col gap-1 rounded-xl border p-4 text-left transition-colors ${
        selected ? `${a.border} ${a.bg}` : "border-slate-800 bg-slate-900 hover:border-slate-600"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className={`text-base font-semibold ${selected ? a.text : "text-slate-100"}`}>
          {meta.label}
        </span>
        <span
          className={`rounded-full px-2 py-0.5 text-xs ${
            meta.needsModel ? "bg-slate-800 text-slate-400" : a.badge
          }`}
        >
          {meta.needsModel ? "需模型" : "确定性"}
        </span>
      </div>
      <span className="text-xs text-slate-400">{meta.tagline}</span>
      <span className="mt-1 text-sm leading-relaxed text-slate-300">{meta.description}</span>
      <span className={`mt-1 text-xs ${selected ? a.text : "text-slate-500"}`}>
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

  const inputClass =
    "rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm outline-none focus:border-slate-500";

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
        <h2 className="text-lg font-semibold text-slate-100">交互式知识实验</h2>
        <p className="mt-1 text-sm text-slate-400">
          围绕你的知识库主动学习：出题测验、对比辨析、编排先修路径。
          测验与对比由真实模型生成，学习路径由知识关系确定性推导。
        </p>
      </div>

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
          className="rounded-md border border-red-900 bg-red-950/50 p-3 text-sm text-red-300"
        >
          {error}
        </div>
      )}
      {notice && (
        <div
          role="status"
          className="rounded-md border border-emerald-900 bg-emerald-950/40 p-3 text-sm text-emerald-300"
        >
          {notice}
        </div>
      )}

      <div className="flex flex-col gap-4 lg:flex-row">
        <div className="w-full shrink-0 space-y-3 rounded-xl border border-slate-800 bg-slate-900 p-4 lg:w-96">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-sm font-medium text-slate-300">选择知识</h3>
            <select
              value={spaceId}
              onChange={(e) => setSpaceId(e.target.value)}
              aria-label="知识空间"
              className={inputClass}
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

          <div className="max-h-72 space-y-1 overflow-auto pr-1" role="group" aria-label="知识列表">
            {itemsLoading ? (
              <p role="status" className="text-sm text-slate-500">
                正在加载知识…
              </p>
            ) : items.length === 0 ? (
              <p className="text-sm text-slate-500">
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
                    className={`flex cursor-pointer items-start gap-2 rounded-md border px-2.5 py-2 text-sm transition-colors ${
                      checked
                        ? `${meta.accent.border} ${meta.accent.bg}`
                        : "border-slate-800 bg-slate-950/60 hover:border-slate-600"
                    } ${blocked ? "cursor-not-allowed opacity-40" : ""}`}
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
                      <span className="block truncate text-slate-200" title={item.title}>
                        {item.title}
                      </span>
                      <span className="text-xs text-slate-500">
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
            <div className="space-y-1.5 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span>{range.label}</span>
                <span className={`font-semibold ${meta.accent.text}`}>{count}</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setCount((c) => Math.max(range.min, c - 1))}
                  disabled={count <= range.min}
                  aria-label="减少"
                  className="h-7 w-7 shrink-0 rounded-md border border-slate-700 text-slate-300 hover:bg-slate-800 disabled:opacity-40"
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
                  className="h-7 w-7 shrink-0 rounded-md border border-slate-700 text-slate-300 hover:bg-slate-800 disabled:opacity-40"
                >
                  +
                </button>
              </div>
            </div>
          )}

          <div className="flex items-center justify-between text-xs text-slate-500">
            <span>
              已选 {selectedIds.length} 条
              {selectedItems.length > 0 && mode === "compare"
                ? ` · ${selectedItems.map((i) => i.title).join(" ↔ ")}`
                : ""}
            </span>
          </div>
          {hint && <p className="text-xs text-amber-300">{hint}</p>}

          <button
            type="button"
            onClick={() => void handleGenerate()}
            disabled={!ready || generating}
            className={`w-full rounded-md px-4 py-2 text-sm font-medium text-slate-900 transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
              mode === "quiz"
                ? "bg-amber-300 hover:bg-amber-200"
                : mode === "compare"
                  ? "bg-sky-300 hover:bg-sky-200"
                  : "bg-emerald-300 hover:bg-emerald-200"
            }`}
          >
            {generating ? "生成中…" : `生成${meta.label}`}
          </button>
          {!ready && (
            <p className="text-center text-xs text-slate-500">{meta.requirement}</p>
          )}
        </div>

        <div className="min-w-0 flex-1 space-y-4">
          {session ? (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-800 bg-slate-900 p-3">
                <span className={`rounded-full px-2.5 py-0.5 text-xs ${MODE_META[session.kind].accent.badge}`}>
                  {MODE_META[session.kind].label}
                </span>
                <span className="min-w-0 flex-1 truncate text-sm text-slate-200" title={session.title}>
                  {session.title}
                </span>
                <button
                  type="button"
                  onClick={() => setSession(null)}
                  className="shrink-0 rounded-md border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-800"
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
            <div className="flex h-full min-h-64 flex-col items-center justify-center rounded-xl border border-dashed border-slate-800 bg-slate-900/40 p-8 text-center">
              <span className={`text-3xl ${meta.accent.text}`}>✦</span>
              <p className="mt-3 text-sm text-slate-300">
                选择「{meta.label}」模式与知识，点击生成开始实验。
              </p>
              <p className="mt-1 text-xs text-slate-500">{meta.description}</p>
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
            className="absolute inset-0 bg-slate-950/70"
            onClick={() => setDetailItem(null)}
            aria-hidden
          />
          <aside className="exp-fade-in relative z-10 h-full w-full max-w-md overflow-auto border-l border-slate-800 bg-slate-900 p-4">
            <div className="flex items-start justify-between gap-2">
              <h3 className="text-base font-semibold text-slate-100">{detailItem.title}</h3>
              <button
                type="button"
                onClick={() => setDetailItem(null)}
                className="shrink-0 rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
              >
                关闭
              </button>
            </div>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-slate-300">
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