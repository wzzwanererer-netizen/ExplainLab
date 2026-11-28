import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type {
  EmbedCapability,
  KnowledgeItem,
  KnowledgeStatus,
  SearchMode,
  SearchResponse,
  Space,
} from "../api/types";
import { KnowledgeDetail } from "./KnowledgeDetail";

const STATUS_LABEL: Record<KnowledgeStatus, string> = {
  draft: "草稿",
  active: "生效",
  archived: "归档",
};

const MODE_LABEL: Record<SearchMode, string> = {
  hybrid: "混合（全文 + 向量）",
  fts: "仅全文",
  vector: "仅向量",
};

const CHANNEL_LABEL: Record<string, string> = {
  fts: "全文",
  vector: "向量",
};

const CAPABILITY_HINT: Record<EmbedCapability, string> = {
  not_configured: "向量通道未配置：当前仅全文检索。在 backend/.env 配置 EMBED_* 后启用语义向量。",
  configured: "向量来源已配置。",
  supported: "全文 + 向量双通道混合检索（RRF 融合排序）。",
  unsupported: "向量端点不可用：已如实降级为仅全文检索，不以假数据冒充向量能力。",
};

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/**
 * M3 检索视图：跨会话 / 跨空间混合检索。
 * 查询框 + 空间筛选 + 模式选择 + 索引重建；结果展示标题 / 摘要 / 分数 / 通道，
 * 点击展开知识详情（含来源追溯）。所有数据来自后端真实 API，向量能力如实上报。
 */
export function SearchView() {
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [spaceId, setSpaceId] = useState("");
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<SearchMode>("hybrid");
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reindexing, setReindexing] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [expandedItem, setExpandedItem] = useState<KnowledgeItem | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        setSpaces(await api.listSpaces());
      } catch (err) {
        setError(errorMessage(err));
      }
    })();
  }, []);

  const runSearch = useCallback(
    async (q: string, targetSpace: string, targetMode: SearchMode) => {
      const trimmed = q.trim();
      if (!trimmed) return;
      setLoading(true);
      setError(null);
      setNotice(null);
      setExpandedId(null);
      setExpandedItem(null);
      try {
        setResult(
          await api.search(trimmed, {
            spaceId: targetSpace || null,
            mode: targetMode,
          }),
        );
      } catch (err) {
        setError(errorMessage(err));
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  async function handleReindex() {
    setReindexing(true);
    setError(null);
    try {
      const res = await api.reindex();
      setNotice(`已重建 ${res.indexed} 条知识索引（向量能力：${res.embed_capability}）。`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setReindexing(false);
    }
  }

  async function toggleDetail(itemId: string) {
    if (expandedId === itemId) {
      setExpandedId(null);
      setExpandedItem(null);
      return;
    }
    setError(null);
    try {
      const item = await api.getKnowledge(itemId);
      setExpandedId(itemId);
      setExpandedItem(item);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

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
          HYBRID RETRIEVAL · 混合检索
        </div>
        <h2
          className="text-lg font-semibold tracking-tight"
          style={{ color: "var(--nesti-text-primary)" }}
        >
          跨会话与全库语义检索
        </h2>
        <p className="text-xs" style={{ color: "var(--nesti-text-secondary)" }}>
          结合 FTS5 关键词召回与语义向量召回，一键直达任意知识条目与原始出处。
        </p>
      </header>

      <form
        className="flex flex-wrap items-center gap-3 rounded-[14px] border p-4 shadow-xs"
        style={{
          background: "var(--nesti-surface-1)",
          borderColor: "var(--nesti-border-subtle)",
        }}
        onSubmit={(e) => {
          e.preventDefault();
          void runSearch(query, spaceId, mode);
        }}
      >
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="输入关键词，跨会话检索知识…"
          aria-label="检索关键词"
          className="min-w-64 flex-1 rounded-lg border px-3 py-1.5 text-sm outline-none"
          style={fieldStyle}
        />
        <select
          value={spaceId}
          onChange={(e) => setSpaceId(e.target.value)}
          aria-label="检索空间"
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
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value as SearchMode)}
          aria-label="检索模式"
          className="rounded-lg border px-3 py-1.5 text-sm outline-none"
          style={fieldStyle}
        >
          {(Object.keys(MODE_LABEL) as SearchMode[]).map((m) => (
            <option key={m} value={m}>
              {MODE_LABEL[m]}
            </option>
          ))}
        </select>
        <button
          type="submit"
          disabled={!query.trim() || loading}
          className="rounded-[9px] px-4 py-1.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-40"
          style={{ background: "var(--nesti-accent)" }}
        >
          {loading ? "检索中…" : "检索"}
        </button>
        <button
          type="button"
          onClick={() => void handleReindex()}
          disabled={reindexing}
          className="rounded-[9px] border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-[var(--nesti-surface-hover)] disabled:opacity-40"
          style={{
            borderColor: "var(--nesti-border-strong)",
            color: "var(--nesti-text-primary)",
          }}
        >
          {reindexing ? "重建中…" : "重建索引"}
        </button>
      </form>

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

      {result && (
        <div
          role="status"
          className="rounded-xl border px-3.5 py-2.5 text-xs"
          style={{
            background: "var(--nesti-surface-1)",
            borderColor: "var(--nesti-border-subtle)",
            color: "var(--nesti-text-secondary)",
          }}
        >
          <span
            className="mr-2 rounded-full px-2.5 py-0.5 font-medium"
            style={{
              background: "color-mix(in srgb, var(--nesti-accent) 12%, transparent)",
              color: "var(--nesti-accent)",
            }}
          >
            实际模式：{MODE_LABEL[result.mode]}
          </span>
          {CAPABILITY_HINT[result.embed_capability]}
        </div>
      )}

      <section className="space-y-3">
        {loading ? (
          <p role="status" className="text-sm" style={{ color: "var(--nesti-text-secondary)" }}>
            正在检索…
          </p>
        ) : !result ? (
          <p
            className="rounded-[14px] border p-6 text-sm"
            style={{
              background: "var(--nesti-surface-1)",
              borderColor: "var(--nesti-border-subtle)",
              color: "var(--nesti-text-secondary)",
            }}
          >
            输入关键词开始跨会话检索。可在「知识库」或「对话」中积累知识后再检索。
          </p>
        ) : result.count === 0 ? (
          <p
            className="rounded-[14px] border p-6 text-sm"
            style={{
              background: "var(--nesti-surface-1)",
              borderColor: "var(--nesti-border-subtle)",
              color: "var(--nesti-text-secondary)",
            }}
          >
            未检索到匹配知识。可尝试更换关键词，或点击「重建索引」为存量知识建立索引。
          </p>
        ) : (
          result.results.map((hit) => (
            <article
              key={hit.item_id}
              className="rounded-[14px] border p-4 shadow-xs transition-colors"
              style={{
                background: "var(--nesti-surface-1)",
                borderColor: "var(--nesti-border-subtle)",
              }}
            >
              <div className="mb-2 flex items-start justify-between gap-3">
                <h3
                  className="text-[15px] font-semibold"
                  style={{ color: "var(--nesti-text-primary)" }}
                >
                  {hit.title}
                </h3>
                <span
                  className="shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium"
                  style={{
                    background: "var(--nesti-surface-2)",
                    color: "var(--nesti-text-secondary)",
                  }}
                >
                  {STATUS_LABEL[hit.status]}
                </span>
              </div>
              <p
                className="whitespace-pre-wrap text-sm leading-relaxed"
                style={{ color: "var(--nesti-text-secondary)" }}
              >
                {hit.snippet}
              </p>
              <div
                className="mt-3 flex flex-wrap items-center gap-2 text-xs"
                style={{ color: "var(--nesti-text-tertiary)" }}
              >
                <span
                  className="rounded-full px-2.5 py-0.5 font-medium"
                  style={{
                    background: "color-mix(in srgb, var(--nesti-accent) 10%, transparent)",
                    color: "var(--nesti-accent)",
                  }}
                >
                  融合分 {hit.score.toFixed(4)}
                </span>
                {Object.entries(hit.channels).map(([ch, value]) => (
                  <span
                    key={ch}
                    className="rounded-full border px-2.5 py-0.5"
                    style={{ borderColor: "var(--nesti-border-subtle)" }}
                  >
                    {CHANNEL_LABEL[ch] ?? ch} {value.toFixed(4)}
                  </span>
                ))}
                <button
                  type="button"
                  onClick={() => void toggleDetail(hit.item_id)}
                  aria-expanded={expandedId === hit.item_id}
                  className="ml-auto rounded-lg border px-3 py-1 text-xs font-medium transition-colors hover:bg-[var(--nesti-surface-hover)]"
                  style={{
                    borderColor: "var(--nesti-border-strong)",
                    color: "var(--nesti-text-primary)",
                  }}
                >
                  {expandedId === hit.item_id ? "收起详情" : "查看详情"}
                </button>
              </div>
              {expandedId === hit.item_id && expandedItem && (
                <KnowledgeDetail
                  item={expandedItem}
                  onNotice={setNotice}
                  onError={setError}
                  onChanged={() => void runSearch(query, spaceId, mode)}
                />
              )}
            </article>
          ))
        )}
      </section>
    </div>
  );
}