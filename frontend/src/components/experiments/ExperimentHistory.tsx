import type { ExperimentSession } from "../../api/types";
import { EXPERIMENT_STATUS_LABEL, MODE_META } from "../../lib/experiments";

interface Props {
  sessions: ExperimentSession[];
  loading: boolean;
  activeId: string | null;
  onReopen: (session: ExperimentSession) => void;
  onDelete: (id: string) => void;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** 历史实验列表：按模式着色，支持重新打开与删除。 */
export function ExperimentHistory({
  sessions,
  loading,
  activeId,
  onReopen,
  onDelete,
}: Props) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <h3 className="mb-3 text-sm font-medium text-slate-300">
        历史实验（{sessions.length}）
      </h3>
      {loading ? (
        <p role="status" className="text-sm text-slate-500">
          正在加载历史…
        </p>
      ) : sessions.length === 0 ? (
        <p className="text-sm text-slate-500">
          暂无历史实验。选择模式与知识后生成第一个实验。
        </p>
      ) : (
        <ul className="space-y-2">
          {sessions.map((s) => {
            const meta = MODE_META[s.kind];
            const isActive = s.id === activeId;
            return (
              <li
                key={s.id}
                className={`flex items-center gap-3 rounded-lg border px-3 py-2 ${
                  isActive ? `${meta.accent.border} ${meta.accent.bg}` : "border-slate-800 bg-slate-950/60"
                }`}
              >
                <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${meta.accent.badge}`}>
                  {meta.label}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-slate-200" title={s.title}>
                    {s.title}
                  </p>
                  <p className="text-xs text-slate-500">
                    {EXPERIMENT_STATUS_LABEL[s.status]} · {s.item_ids.length} 条知识 ·{" "}
                    {formatDate(s.created_at)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => onReopen(s)}
                  className="shrink-0 rounded-md border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-800"
                >
                  打开
                </button>
                <button
                  type="button"
                  onClick={() => onDelete(s.id)}
                  aria-label={`删除实验 ${s.title}`}
                  className="shrink-0 rounded-md border border-slate-700 px-2.5 py-1 text-xs text-red-400 hover:bg-red-950/40"
                >
                  删除
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}