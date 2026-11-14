import type { ExperimentSession } from "../../api/types";
import { MODE_META } from "../../lib/experiments";
import { RELATION_LABEL } from "../../lib/graphLayout";

interface Props {
  session: ExperimentSession;
  onOpenItem: (itemId: string) => void;
}

/**
 * 学习路径 Runner：确定性先修编排的竖向步进器。
 * 每一步标注与上一步的关系（依赖 / 细化），末步为目标知识（seed）。
 * 无模型参与，路径完全由知识关系推导。
 */
export function ChainRunner({ session, onOpenItem }: Props) {
  const steps = session.payload.steps ?? [];
  const accent = MODE_META.chain.accent;

  if (steps.length === 0) {
    return (
      <p className="text-sm text-slate-500">
        暂无可编排的路径。目标知识可能没有先修（依赖 / 细化）关系。
      </p>
    );
  }

  return (
    <div className="exp-fade-in space-y-4">
      <div className={`rounded-xl border p-4 ${accent.border} ${accent.bg}`}>
        <p className="text-sm text-slate-200">
          沿「依赖 / 细化」关系回溯先修知识，共 {steps.length} 步。建议自上而下学习，
          最后掌握目标知识。
        </p>
      </div>

      <ol className="space-y-0">
        {steps.map((step, i) => {
          const isLast = i === steps.length - 1;
          const isGoal = isLast;
          return (
            <li key={step.item_id} className="relative flex gap-4 pb-5 last:pb-0">
              {!isLast && (
                <span
                  className="absolute left-[15px] top-8 h-[calc(100%-1rem)] w-0.5"
                  style={{ backgroundColor: "#1e293b" }}
                  aria-hidden
                />
              )}
              <span
                className={`z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-sm font-semibold ${
                  isGoal
                    ? `${accent.border} ${accent.text} ${accent.bg}`
                    : "border-slate-700 bg-slate-900 text-slate-300"
                }`}
              >
                {step.position + 1}
              </span>
              <div className="min-w-0 flex-1">
                {step.relation_from_prev && (
                  <span className="mb-1 inline-block rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-400">
                    {RELATION_LABEL[step.relation_from_prev]}上一步
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => onOpenItem(step.item_id)}
                  className="block w-full rounded-lg border border-slate-800 bg-slate-900 px-4 py-3 text-left hover:border-slate-600"
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-medium text-slate-100">
                      {step.title}
                    </span>
                    {isGoal && (
                      <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${accent.badge}`}>
                        目标
                      </span>
                    )}
                  </span>
                  <span className="mt-0.5 block text-xs text-slate-500">
                    {isGoal ? "终点知识 · 点击查看" : "先修知识 · 点击查看"}
                  </span>
                </button>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}