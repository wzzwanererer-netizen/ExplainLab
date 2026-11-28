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
    <div
      className="rounded-[14px] border p-4 shadow-xs"
      style={{
        background: "var(--nesti-surface-1)",
        borderColor: "var(--nesti-border-subtle)",
      }}
    >
      <h3
        className="mb-3 text-sm font-semibold"
        style={{ color: "var(--nesti-text-primary)" }}
      >
        历史实验（{sessions.length}）
      </h3>
      {loading ? (
        <p role="status" className="text-sm" style={{ color: "var(--nesti-text-secondary)" }}>
          正在加载历史…
        </p>
      ) : sessions.length === 0 ? (
        <p className="text-sm" style={{ color: "var(--nesti-text-secondary)" }}>
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
                className="flex items-center gap-3 rounded-lg border px-3 py-2"
                style={
                  isActive
                    ? {
                        borderColor: "var(--nesti-accent)",
                        background: "color-mix(in srgb, var(--nesti-accent) 10%, var(--nesti-surface-0))",
                      }
                    : {
                        borderColor: "var(--nesti-border-subtle)",
                        background: "var(--nesti-surface-0)",
                      }
                }
              >
                <span
                  className="shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium"
                  style={{
                    background: "color-mix(in srgb, var(--nesti-accent) 12%, transparent)",
                    color: "var(--nesti-accent)",
                  }}
                >
                  {meta.label}
                </span>
                <div className="min-w-0 flex-1">
                  <p
                    className="truncate text-sm font-medium"
                    style={{ color: "var(--nesti-text-primary)" }}
                    title={s.title}
                  >
                    {s.title}
                  </p>
                  <p className="text-xs" style={{ color: "var(--nesti-text-tertiary)" }}>
                    {EXPERIMENT_STATUS_LABEL[s.status]} · {s.item_ids.length} 条知识 ·{" "}
                    {formatDate(s.created_at)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => onReopen(s)}
                  className="shrink-0 rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors hover:bg-[var(--nesti-surface-hover)]"
                  style={{
                    borderColor: "var(--nesti-border-subtle)",
                    color: "var(--nesti-text-secondary)",
                  }}
                >
                  打开
                </button>
                <button
                  type="button"
                  onClick={() => onDelete(s.id)}
                  aria-label={`删除实验 ${s.title}`}
                  className="shrink-0 rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors hover:bg-[var(--nf-status-danger-bg)]"
                  style={{
                    borderColor: "var(--nesti-border-subtle)",
                    color: "var(--nf-status-danger)",
                  }}
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