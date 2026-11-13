import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Conversation, ConversationDetail, Space } from "../api/types";

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/**
 * 对话视图：会话列表 + 消息线程 + 真实模型对话 + 知识提取。
 * 对话与提取均调用后端真实接口；模型未配置时如实展示 503 指引。
 */
export function ChatView() {
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [thread, setThread] = useState<ConversationDetail | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [newSpaceId, setNewSpaceId] = useState("");
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadConversations = useCallback(async () => {
    setConversations(await api.listConversations());
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const [spaceRows] = await Promise.all([api.listSpaces(), loadConversations()]);
        setSpaces(spaceRows);
        const personal = spaceRows.find((s) => s.kind === "personal");
        if (personal) {
          setNewSpaceId(personal.id);
        }
      } catch (err) {
        setError(errorMessage(err));
      }
    })();
  }, [loadConversations]);

  const openConversation = useCallback(async (id: string) => {
    setSelectedId(id);
    setNotice(null);
    setError(null);
    try {
      setThread(await api.getConversation(id));
    } catch (err) {
      setError(errorMessage(err));
    }
  }, []);

  async function handleCreate() {
    const title = newTitle.trim();
    if (!title) return;
    setError(null);
    try {
      const conv = await api.createConversation(title, newSpaceId || null);
      setNewTitle("");
      await loadConversations();
      await openConversation(conv.id);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleDelete(id: string) {
    setError(null);
    try {
      await api.deleteConversation(id);
      if (selectedId === id) {
        setSelectedId(null);
        setThread(null);
      }
      await loadConversations();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleSend() {
    const content = draft.trim();
    if (!content || !selectedId || sending) return;
    setSending(true);
    setError(null);
    setNotice(null);
    try {
      await api.chat(selectedId, content);
      setDraft("");
      // 重新拉取完整线程，确保展示的是后端真实落库的消息
      setThread(await api.getConversation(selectedId));
      await loadConversations();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSending(false);
    }
  }

  async function handleExtract() {
    if (!selectedId || extracting) return;
    setExtracting(true);
    setError(null);
    setNotice(null);
    try {
      const result = await api.extractKnowledge(selectedId);
      setNotice(
        result.count > 0
          ? `已提取 ${result.count} 条知识，可在「知识库」查看。`
          : "模型未从本次对话中提取到知识条目。",
      );
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setExtracting(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
      <aside className="rounded-xl border border-slate-800 bg-slate-900 p-4">
        <h2 className="mb-3 text-sm font-medium text-slate-300">会话</h2>
        <div className="mb-4 space-y-2">
          <input
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="新会话标题"
            aria-label="新会话标题"
            className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm outline-none focus:border-slate-500"
          />
          <select
            value={newSpaceId}
            onChange={(e) => setNewSpaceId(e.target.value)}
            aria-label="所属知识空间"
            className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm outline-none focus:border-slate-500"
          >
            {spaces.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => void handleCreate()}
            disabled={!newTitle.trim()}
            className="w-full rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-900 hover:bg-white disabled:opacity-40"
          >
            创建会话
          </button>
        </div>
        <ul className="space-y-1">
          {conversations.map((c) => (
            <li key={c.id} className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => void openConversation(c.id)}
                className={`flex-1 truncate rounded-md px-3 py-2 text-left text-sm ${
                  selectedId === c.id
                    ? "bg-slate-800 text-slate-100"
                    : "text-slate-400 hover:bg-slate-800/60"
                }`}
              >
                {c.title}
              </button>
              <button
                type="button"
                onClick={() => void handleDelete(c.id)}
                aria-label={`删除会话 ${c.title}`}
                className="rounded px-1.5 text-slate-600 hover:text-red-400"
              >
                ×
              </button>
            </li>
          ))}
          {conversations.length === 0 && (
            <li className="px-3 py-2 text-xs text-slate-500">暂无会话，先创建一个。</li>
          )}
        </ul>
      </aside>

      <section className="flex min-h-[480px] flex-col rounded-xl border border-slate-800 bg-slate-900 p-4">
        {error && (
          <div
            role="alert"
            className="mb-3 rounded-md border border-red-900 bg-red-950/50 p-3 text-sm text-red-300"
          >
            {error}
          </div>
        )}
        {notice && (
          <div
            role="status"
            className="mb-3 rounded-md border border-emerald-900 bg-emerald-950/40 p-3 text-sm text-emerald-300"
          >
            {notice}
          </div>
        )}

        {!thread ? (
          <p className="m-auto text-sm text-slate-500">选择或创建一个会话开始对话。</p>
        ) : (
          <>
            <div className="mb-3 flex items-center justify-between border-b border-slate-800 pb-3">
              <h2 className="text-sm font-medium">{thread.title}</h2>
              <button
                type="button"
                onClick={() => void handleExtract()}
                disabled={extracting || thread.messages.length === 0}
                className="rounded-md border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-40"
              >
                {extracting ? "提取中…" : "提取知识"}
              </button>
            </div>
            <div className="flex-1 space-y-3 overflow-y-auto">
              {thread.messages.map((m) => (
                <div
                  key={m.id}
                  className={`whitespace-pre-wrap rounded-lg p-3 text-sm ${
                    m.role === "user"
                      ? "ml-8 bg-slate-800"
                      : "mr-8 border border-slate-800 bg-slate-950"
                  }`}
                >
                  <p className="mb-1 text-xs text-slate-500">
                    {m.role === "user" ? "我" : "助手"}
                  </p>
                  {m.content}
                </div>
              ))}
              {thread.messages.length === 0 && (
                <p className="text-xs text-slate-500">还没有消息，发送第一条开始。</p>
              )}
              {sending && (
                <p role="status" className="text-xs text-slate-400">
                  助手思考中…
                </p>
              )}
            </div>
            <div className="mt-3 flex gap-2 border-t border-slate-800 pt-3">
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                rows={2}
                placeholder="输入消息…"
                aria-label="消息输入"
                className="flex-1 resize-none rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-slate-500"
              />
              <button
                type="button"
                onClick={() => void handleSend()}
                disabled={sending || !draft.trim()}
                className="self-end rounded-md bg-slate-100 px-4 py-2 text-sm font-medium text-slate-900 hover:bg-white disabled:opacity-40"
              >
                {sending ? "发送中…" : "发送"}
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}