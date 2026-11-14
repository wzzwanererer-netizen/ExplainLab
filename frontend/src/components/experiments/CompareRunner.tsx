import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import type { ExperimentSession, KnowledgeItem } from "../../api/types";
import { MODE_META } from "../../lib/experiments";
import { RELATION_LABEL, STATUS_LABEL } from "../../lib/graphLayout";

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

interface Props {
  session: ExperimentSession;
  onOpenItem: (itemId: string) => void;
  onError: (message: string) => void;
}

/** 单侧知识卡片：标题 / 状态 / 正文，可点开治理详情。 */
function ItemColumn({
  item,
  loading,
  onOpen,
}: {
  item: KnowledgeItem | null;
  loading: boolean;
  onOpen: () => void;
}) {
  if (loading) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-4 text-sm text-slate-500">
        正在加载知识…
      </div>
    );
  }
  if (!item) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-4 text-sm text-slate-500">
        知识不可用（可能已被删除或归档）。
      </div>
    );
  }
  return (
    <div className="flex flex-col rounded-xl border border-slate-800 bg-slate-900 p-4">
      <div className="mb-2 flex items-start justify-between gap-2">
        <h4 className="text-sm font-semibold text-slate-100">{item.title}</h4>
        <span className="shrink-0 rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-400">
          {STATUS_LABEL[item.status]}
        </span>
      </div>
      <p className="max-h-52 overflow-auto whitespace-pre-wrap text-sm leading-relaxed text-slate-300">
        {item.content}
      </p>
      <button
        type="button"
        onClick={onOpen}
        className="mt-3 w-fit rounded-md border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-800"
      >
        治理详情
      </button>
    </div>
  );
}

/** 结构化列表分区（相同点 / 不同点），空时如实提示。 */
function ListSection({
  title,
  items,
  dotClass,
}: {
  title: string;
  items: string[];
  dotClass: string;
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <h4 className="mb-2 text-xs font-medium text-slate-400">
        {title}（{items.length}）
      </h4>
      {items.length === 0 ? (
        <p className="text-sm text-slate-500">模型未给出{title}。</p>
      ) : (
        <ul className="space-y-1.5">
          {items.map((t, i) => (
            <li key={i} className="flex gap-2 text-sm text-slate-300">
              <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${dotClass}`} />
              {t}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * 对比 Runner：并排呈现两条知识 + 结构化相同点 / 不同点 + 关系判定徽章。
 * 关系判定由模型给出（可能为空），如实呈现，不臆造。
 */
export function CompareRunner({ session, onOpenItem, onError }: Props) {
  const compare = session.payload.compare;
  const accent = MODE_META.compare.accent;
  const [itemA, setItemA] = useState<KnowledgeItem | null>(null);
  const [itemB, setItemB] = useState<KnowledgeItem | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!compare) {
      setLoading(false);
      return;
    }
    setLoading(true);
    const [a, b] = await Promise.allSettled([
      api.getKnowledge(compare.item_a_id),
      api.getKnowledge(compare.item_b_id),
    ]);
    if (a.status === "fulfilled") setItemA(a.value);
    else onError(errorMessage(a.reason));
    if (b.status === "fulfilled") setItemB(b.value);
    else onError(errorMessage(b.reason));
    setLoading(false);
  }, [compare, onError]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!compare) {
    return <p className="text-sm text-slate-500">本次对比暂无结果。</p>;
  }

  return (
    <div className="exp-fade-in space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        <ItemColumn
          item={itemA}
          loading={loading}
          onOpen={() => onOpenItem(compare.item_a_id)}
        />
        <ItemColumn
          item={itemB}
          loading={loading}
          onOpen={() => onOpenItem(compare.item_b_id)}
        />
      </div>

      <div className={`rounded-xl border p-4 ${accent.border} ${accent.bg}`}>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium text-slate-400">关系判定</span>
          {compare.relation_type ? (
            <span className={`rounded-full px-2.5 py-0.5 text-xs ${accent.badge}`}>
              {RELATION_LABEL[compare.relation_type]}
            </span>
          ) : (
            <span className="rounded-full bg-slate-800 px-2.5 py-0.5 text-xs text-slate-400">
              未判定明确关系
            </span>
          )}
        </div>
        {compare.relationship ? (
          <p className="mt-2 text-sm text-slate-200">{compare.relationship}</p>
        ) : (
          <p className="mt-2 text-sm text-slate-500">模型未给出关系说明。</p>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <ListSection title="相同点" items={compare.similarities} dotClass="bg-sky-400" />
        <ListSection title="不同点" items={compare.differences} dotClass="bg-amber-400" />
      </div>
    </div>
  );
}