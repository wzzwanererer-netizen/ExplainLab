import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { KnowledgeItem, KnowledgeStatus, Space } from "../api/types";

const STATUS_LABEL: Record<KnowledgeStatus, string> = {
  draft: "草稿",
  active: "生效",
  archived: "归档",
};

const SOURCE_LABEL: Record<string, string> = {
  conversation: "对话",
  document: "文档",
  manual: "手动",
  import: "导入",
};

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/**
 * 知识库视图：空间切换 / 新建项目空间 + 知识条目 CRUD + 来源追溯展示。
 * 默认选中个人总知识库；所有数据来自后端真实 API。
 */
export function KnowledgeView() {
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [spaceId, setSpaceId] = useState("");
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [status, setStatus] = useState<KnowledgeStatus>("draft");
  const [newSpaceName, setNewSpaceName] = useState("");

  const loadItems = useCallback(async (targetSpaceId: string) => {
    setLoading(true);
    try {
      setItems(await api.listKnowledge(targetSpaceId || undefined));
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const rows = await api.listSpaces();
        setSpaces(rows);
        const personal = rows.find((s) => s.kind === "personal") ?? rows[0];
        if (personal) {
          setSpaceId(personal.id);
          await loadItems(personal.id);
        } else {
          setLoading(false);
        }
      } catch (err) {
        setError(errorMessage(err));
        setLoading(false);
      }
    })();
  }, [loadItems]);

  function resetForm() {
    setEditingId(null);
    setTitle("");
    setContent("");
    setStatus("draft");
  }

  async function handleSwitchSpace(id: string) {
    setSpaceId(id);
    resetForm();
    setNotice(null);
    await loadItems(id);
  }

  async function handleCreateSpace() {
    const name = newSpaceName.trim();
    if (!name) return;
    setError(null);
    try {
      const space = await api.createSpace(name);
      setNewSpaceName("");
      setSpaces(await api.listSpaces());
      await handleSwitchSpace(space.id);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleSave() {
    const t = title.trim();
    const c = content.trim();
    if (!t || !c) return;
    setError(null);
    try {
      if (editingId) {
        await api.updateKnowledge(editingId, { title: t, content: c, status });
        setNotice("已更新知识条目。");
      } else {
        await api.createKnowledge({ title: t, content: c, space_id: spaceId || null });
        setNotice("已创建知识条目。");
      }
      resetForm();
      await loadItems(spaceId);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  function startEdit(item: KnowledgeItem) {
    setEditingId(item.id);
    setTitle(item.title);
    setContent(item.content);
    setStatus(item.status);
    setNotice(null);
  }

  async function handleDelete(id: string) {
    if (!window.confirm("确认删除该知识条目？")) return;
    setError(null);
    try {
      await api.deleteKnowledge(id);
      if (editingId === id) {
        resetForm();
      }
      await loadItems(spaceId);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  const inputClass =
    "w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm outline-none focus:border-slate-500";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-800 bg-slate-900 p-4">
        <label className="text-sm text-slate-400" htmlFor="space-select">
          知识空间
        </label>
        <select
          id="space-select"
          value={spaceId}
          onChange={(e) => void handleSwitchSpace(e.target.value)}
          className="rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm outline-none focus:border-slate-500"
        >
          {spaces.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
              {s.kind === "personal" ? "（个人）" : ""}
            </option>
          ))}
        </select>
        <div className="ml-auto flex items-center gap-2">
          <input
            value={newSpaceName}
            onChange={(e) => setNewSpaceName(e.target.value)}
            placeholder="新项目空间名称"
            aria-label="新项目空间名称"
            className="rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm outline-none focus:border-slate-500"
          />
          <button
            type="button"
            onClick={() => void handleCreateSpace()}
            disabled={!newSpaceName.trim()}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800 disabled:opacity-40"
          >
            新建空间
          </button>
        </div>
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

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <section className="h-fit rounded-xl border border-slate-800 bg-slate-900 p-4">
          <h2 className="mb-3 text-sm font-medium text-slate-300">
            {editingId ? "编辑知识条目" : "新建知识条目"}
          </h2>
          <div className="space-y-2">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="标题"
              aria-label="知识标题"
              className={inputClass}
            />
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={5}
              placeholder="内容"
              aria-label="知识内容"
              className={`${inputClass} resize-y`}
            />
            {editingId && (
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value as KnowledgeStatus)}
                aria-label="知识状态"
                className={inputClass}
              >
                {(Object.keys(STATUS_LABEL) as KnowledgeStatus[]).map((s) => (
                  <option key={s} value={s}>
                    {STATUS_LABEL[s]}
                  </option>
                ))}
              </select>
            )}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => void handleSave()}
                disabled={!title.trim() || !content.trim()}
                className="flex-1 rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-900 hover:bg-white disabled:opacity-40"
              >
                {editingId ? "保存修改" : "创建"}
              </button>
              {editingId && (
                <button
                  type="button"
                  onClick={resetForm}
                  className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800"
                >
                  取消
                </button>
              )}
            </div>
          </div>
        </section>

        <section className="space-y-3">
          {loading ? (
            <p role="status" className="text-sm text-slate-400">
              正在加载知识条目…
            </p>
          ) : items.length === 0 ? (
            <p className="rounded-xl border border-slate-800 bg-slate-900 p-6 text-sm text-slate-500">
              该空间暂无知识条目。可在左侧手动创建，或在「对话」中提取。
            </p>
          ) : (
            items.map((item) => (
              <article
                key={item.id}
                className="rounded-xl border border-slate-800 bg-slate-900 p-4"
              >
                <div className="mb-2 flex items-start justify-between gap-3">
                  <h3 className="text-sm font-medium">{item.title}</h3>
                  <span className="shrink-0 rounded-full bg-slate-800 px-2.5 py-0.5 text-xs text-slate-400">
                    {STATUS_LABEL[item.status]}
                  </span>
                </div>
                <p className="whitespace-pre-wrap text-sm text-slate-300">{item.content}</p>
                {item.source_refs.length > 0 && (
                  <div className="mt-3 space-y-1 border-t border-slate-800 pt-2">
                    {item.source_refs.map((s) => (
                      <p key={s.id} className="text-xs text-slate-500">
                        来源：{SOURCE_LABEL[s.source_type] ?? s.source_type}
                        {s.conversation_id && ` · 会话 ${s.conversation_id.slice(0, 8)}…`}
                        {s.excerpt && (
                          <span className="mt-0.5 block truncate text-slate-600">
                            {s.excerpt}
                          </span>
                        )}
                      </p>
                    ))}
                  </div>
                )}
                <div className="mt-3 flex gap-2">
                  <button
                    type="button"
                    onClick={() => startEdit(item)}
                    className="rounded-md border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-800"
                  >
                    编辑
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleDelete(item.id)}
                    className="rounded-md border border-slate-700 px-3 py-1 text-xs text-red-400 hover:bg-red-950/40"
                  >
                    删除
                  </button>
                </div>
              </article>
            ))
          )}
        </section>
      </div>
    </div>
  );
}