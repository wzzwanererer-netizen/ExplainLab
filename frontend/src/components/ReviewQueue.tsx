import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { ReviewAction, ReviewRequest, ReviewStatus } from "../api/types";

const ACTION_LABEL: Record<ReviewAction, string> = {
  update_item: "编辑知识",
  delete_item: "删除知识",
  merge_duplicate: "合并重复",
  restore_version: "回滚版本",
};

const STATUS_LABEL: Record<ReviewStatus, string> = {
  pending: "待审核",
  approved: "已批准",
  rejected: "已驳回",
};

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

function payloadSummary(review: ReviewRequest): string {
  const p = review.payload;
  switch (review.action) {
    case "update_item": {
      const parts: string[] = [];
      if (typeof p.title === "string") parts.push(`标题→「${p.title}」`);
      if (typeof p.content === "string") {
        parts.push(`内容→「${p.content.slice(0, 40)}${p.content.length > 40 ? "…" : ""}」`);
      }
      if (typeof p.status === "string") parts.push(`状态→${p.status}`);
      return parts.join("；") || "（无字段变更）";
    }
    case "merge_duplicate":
      return `并入目标 ${String(p.target_id ?? "").slice(0, 8)}…`;
    case "restore_version":
      return `恢复至 v${String(p.version ?? "?")}`;
    case "delete_item":
      return "删除该条目（批准后执行）";
  }
}

/**
 * 审核页签（M2）：重要变更的 pending 队列，支持批准 / 驳回。
 * 批准才应用变更；驳回不改动数据。全部来自后端真实 API。
 */
export function ReviewQueue() {
  const [reviews, setReviews] = useState<ReviewRequest[]>([]);
  const [filter, setFilter] = useState<ReviewStatus | "all">("pending");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});

  const load = useCallback(async (status: ReviewStatus | "all") => {
    setLoading(true);
    try {
      setReviews(await api.listReviews(status === "all" ? undefined : status));
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(filter);
  }, [filter, load]);

  async function handleResolve(id: string, approve: boolean) {
    setError(null);
    const note = notes[id]?.trim() || undefined;
    try {
      if (approve) {
        await api.approveReview(id, note);
        setNotice("已批准并应用变更。");
      } else {
        await api.rejectReview(id, note);
        setNotice("已驳回，数据未改动。");
      }
      await load(filter);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <div className="max-w-3xl space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-sm font-medium text-slate-300">重要变更审核</h2>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value as ReviewStatus | "all")}
          aria-label="审核状态筛选"
          className="rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm outline-none focus:border-slate-500"
        >
          <option value="pending">待审核</option>
          <option value="approved">已批准</option>
          <option value="rejected">已驳回</option>
          <option value="all">全部</option>
        </select>
        <p className="text-xs text-slate-500">
          生效知识的编辑 / 删除 / 回滚与任何合并重复都会进入此队列；批准后才应用。
        </p>
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

      {loading ? (
        <p role="status" className="text-sm text-slate-400">
          正在加载审核单…
        </p>
      ) : reviews.length === 0 ? (
        <p className="rounded-xl border border-slate-800 bg-slate-900 p-6 text-sm text-slate-500">
          当前筛选下没有审核单。
        </p>
      ) : (
        reviews.map((r) => (
          <article
            key={r.id}
            className="rounded-xl border border-slate-800 bg-slate-900 p-4"
          >
            <div className="mb-2 flex items-start justify-between gap-3">
              <h3 className="text-sm font-medium">
                {ACTION_LABEL[r.action]}
                <span className="ml-2 text-xs text-slate-500">
                  条目 {r.item_id.slice(0, 8)}…
                </span>
              </h3>
              <span
                className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs ${
                  r.status === "pending"
                    ? "bg-amber-950/60 text-amber-300"
                    : r.status === "approved"
                      ? "bg-emerald-950/60 text-emerald-300"
                      : "bg-slate-800 text-slate-400"
                }`}
              >
                {STATUS_LABEL[r.status]}
              </span>
            </div>
            <p className="text-sm text-slate-300">{payloadSummary(r)}</p>
            {Boolean(r.payload?.__a1_import) && (
              <div className="mt-2 rounded-md border border-slate-800 bg-slate-950/60 p-2 text-xs text-slate-400">
                <div className="font-medium text-slate-300">V2 Active ZIP 导入清单</div>
                {Array.isArray((r.payload.__a1_import as { attachments?: unknown[] }).attachments) && (
                  <p className="mt-1">
                    待发布附件：{((r.payload.__a1_import as { attachments?: unknown[] }).attachments ?? []).length} 个
                  </p>
                )}
              </div>
            )}
            {r.reason && <p className="mt-1 text-xs text-slate-500">理由：{r.reason}</p>}
            {r.resolution_note && (
              <p className="mt-1 text-xs text-slate-500">备注：{r.resolution_note}</p>
            )}
            {r.status === "pending" && (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <input
                  value={notes[r.id] ?? ""}
                  onChange={(e) => setNotes((prev) => ({ ...prev, [r.id]: e.target.value }))}
                  placeholder="可选审批备注…"
                  aria-label="审批备注"
                  className="min-w-44 flex-1 rounded-md border border-slate-700 bg-slate-950 px-2.5 py-1 text-xs outline-none focus:border-slate-500"
                />
                <button
                  type="button"
                  onClick={() => void handleResolve(r.id, true)}
                  className="rounded-md bg-slate-100 px-3 py-1 text-xs font-medium text-slate-900 hover:bg-white"
                >
                  批准
                </button>
                <button
                  type="button"
                  onClick={() => void handleResolve(r.id, false)}
                  className="rounded-md border border-slate-700 px-3 py-1 text-xs text-red-400 hover:bg-red-950/40"
                >
                  驳回
                </button>
              </div>
            )}
          </article>
        ))
      )}
    </div>
  );
}