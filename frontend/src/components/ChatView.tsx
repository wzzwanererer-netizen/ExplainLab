import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type {
  ChatCitation,
  Conversation,
  ConversationDetail,
  KnowledgeItem,
  Space,
} from "../api/types";
import { KnowledgeDetail } from "./KnowledgeDetail";
import { MarkdownContent } from "./MarkdownContent";

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/**
 * 研究对话视图：多会话管理 + SSE 逐字流式输出 + 知识库引用溯源抽屉 + 知识提取。
 * 全部采用 Nesti Fluent 浅/深色主题变量，所有回复与引用来自真实后端。
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
  const [streamingUserText, setStreamingUserText] = useState<string | null>(null);
  const [streamingReply, setStreamingReply] = useState("");
  const [streamingCitations, setStreamingCitations] = useState<ChatCitation[]>([]);
  const [citationsByMsgId, setCitationsByMsgId] = useState<
    Record<string, ChatCitation[]>
  >({});

  // 右侧引用溯源抽屉状态
  const [inspectingItem, setInspectingItem] = useState<KnowledgeItem | null>(null);
  const [loadingInspect, setLoadingInspect] = useState(false);

  const [extracting, setExtracting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

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

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [thread?.messages.length, streamingReply]);

  const openConversation = useCallback(async (id: string) => {
    setSelectedId(id);
    setNotice(null);
    setError(null);
    setInspectingItem(null);
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
        setInspectingItem(null);
      }
      await loadConversations();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function openCitation(itemId: string) {
    setLoadingInspect(true);
    setError(null);
    try {
      setInspectingItem(await api.getKnowledge(itemId));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoadingInspect(false);
    }
  }

  async function handleSend() {
    const content = draft.trim();
    if (!content || !selectedId || sending) return;
    setSending(true);
    setError(null);
    setNotice(null);
    setStreamingUserText(content);
    setStreamingReply("");
    setStreamingCitations([]);

    let capturedCitations: ChatCitation[] = [];
    try {
      const savedMsg = await api.chatStream(selectedId, content, {
        onCitations: (cits) => {
          capturedCitations = cits;
          setStreamingCitations(cits);
        },
        onDelta: (piece) => {
          setStreamingReply((prev) => prev + piece);
        },
      });
      if (capturedCitations.length > 0 && savedMsg?.id) {
        setCitationsByMsgId((prev) => ({
          ...prev,
          [savedMsg.id]: capturedCitations,
        }));
      }
      setDraft("");
      // 重新拉取完整线程，确保展示的是后端真实落库的消息
      setThread(await api.getConversation(selectedId));
      await loadConversations();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSending(false);
      setStreamingUserText(null);
      setStreamingReply("");
      setStreamingCitations([]);
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

  const fieldStyle = {
    background: "var(--nesti-surface-0)",
    borderColor: "var(--nesti-border-subtle)",
    color: "var(--nesti-text-primary)",
  };

  return (
    <div className="flex h-full flex-col gap-4 lg:flex-row">
      {/* 左侧会话列表 */}
      <aside
        className="w-full shrink-0 rounded-xl border p-4 shadow-xs lg:w-72"
        style={{
          background: "var(--nesti-surface-1)",
          borderColor: "var(--nesti-border-subtle)",
        }}
      >
        <h2
          className="mb-3 text-sm font-semibold"
          style={{ color: "var(--nesti-text-primary)" }}
        >
          会话
        </h2>
        <div className="mb-4 space-y-2">
          <input
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="新会话标题"
            aria-label="新会话标题"
            className="w-full rounded-lg border px-3 py-1.5 text-sm outline-none"
            style={fieldStyle}
          />
          <select
            value={newSpaceId}
            onChange={(e) => setNewSpaceId(e.target.value)}
            aria-label="所属知识空间"
            className="w-full rounded-lg border px-3 py-1.5 text-sm outline-none"
            style={fieldStyle}
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
            className="w-full rounded-lg px-3 py-1.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
            style={{ background: "var(--nesti-accent)" }}
          >
            创建会话
          </button>
        </div>
        <ul className="space-y-1">
          {conversations.map((c) => {
            const active = selectedId === c.id;
            return (
              <li key={c.id} className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => void openConversation(c.id)}
                  className="flex-1 truncate rounded-lg px-3 py-2 text-left text-sm transition-colors"
                  style={
                    active
                      ? {
                          background:
                            "color-mix(in srgb, var(--nesti-accent) 14%, transparent)",
                          color: "var(--nesti-accent)",
                          fontWeight: 600,
                        }
                      : { color: "var(--nesti-text-secondary)" }
                  }
                >
                  {c.title}
                </button>
                <button
                  type="button"
                  onClick={() => void handleDelete(c.id)}
                  aria-label={`删除会话 ${c.title}`}
                  className="rounded px-1.5 text-sm opacity-55 hover:text-red-500 hover:opacity-100"
                  style={{ color: "var(--nesti-text-tertiary)" }}
                >
                  ×
                </button>
              </li>
            );
          })}
          {conversations.length === 0 && (
            <li
              className="px-3 py-2 text-xs"
              style={{ color: "var(--nesti-text-tertiary)" }}
            >
              暂无会话，先创建一个。
            </li>
          )}
        </ul>
      </aside>

      {/* 中间对话工作区 */}
      <section
        className="flex min-h-[540px] flex-1 flex-col rounded-xl border p-4 shadow-xs"
        style={{
          background: "var(--nesti-surface-1)",
          borderColor: "var(--nesti-border-subtle)",
        }}
      >
        {error && (
          <div
            role="alert"
            className="mb-3 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-500"
          >
            {error}
          </div>
        )}
        {notice && (
          <div
            role="status"
            className="mb-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-600 dark:text-emerald-400"
          >
            {notice}
          </div>
        )}

        {!thread ? (
          <p
            className="m-auto text-sm"
            style={{ color: "var(--nesti-text-tertiary)" }}
          >
            选择或创建一个会话开始对话。
          </p>
        ) : (
          <>
            <div
              className="mb-3 flex items-center justify-between border-b pb-3"
              style={{ borderColor: "var(--nesti-border-subtle)" }}
            >
              <div>
                <h2
                  className="text-sm font-semibold"
                  style={{ color: "var(--nesti-text-primary)" }}
                >
                  {thread.title}
                </h2>
                <p
                  className="text-[11px]"
                  style={{ color: "var(--nesti-text-tertiary)" }}
                >
                  已开启实时流式输出与知识库引用溯源
                </p>
              </div>
              <button
                type="button"
                onClick={() => void handleExtract()}
                disabled={extracting || thread.messages.length === 0}
                className="rounded-lg border px-3 py-1 text-xs font-medium transition-colors hover:bg-[var(--nesti-surface-hover)] disabled:opacity-40"
                style={{
                  borderColor: "var(--nesti-border-subtle)",
                  color: "var(--nesti-text-secondary)",
                }}
              >
                {extracting ? "提取中…" : "提取知识"}
              </button>
            </div>

            <div className="flex-1 space-y-3 overflow-y-auto pr-1">
              {thread.messages.map((m) => {
                const msgCitations = citationsByMsgId[m.id] ?? [];
                const isUser = m.role === "user";
                return (
                  <div
                    key={m.id}
                    className={`rounded-xl border p-3.5 text-sm ${
                      isUser ? "ml-10" : "mr-6"
                    }`}
                    style={
                      isUser
                        ? {
                            background:
                              "color-mix(in srgb, var(--nesti-accent) 12%, var(--nesti-surface-0))",
                            borderColor:
                              "color-mix(in srgb, var(--nesti-accent) 28%, transparent)",
                            color: "var(--nesti-text-primary)",
                          }
                        : {
                            background: "var(--nesti-surface-0)",
                            borderColor: "var(--nesti-border-subtle)",
                            color: "var(--nesti-text-primary)",
                          }
                    }
                  >
                    <p
                      className="mb-1.5 text-[11px] font-semibold"
                      style={{ color: "var(--nesti-text-tertiary)" }}
                    >
                      {isUser ? "我" : "助手"}
                    </p>
                    {isUser ? (
                      <div className="whitespace-pre-wrap">{m.content}</div>
                    ) : (
                      <MarkdownContent content={m.content} />
                    )}

                    {/* 可点击引用来源胶囊 */}
                    {msgCitations.length > 0 && (
                      <div
                        className="mt-3 border-t pt-2"
                        style={{ borderColor: "var(--nesti-border-subtle)" }}
                      >
                        <div
                          className="mb-1.5 text-[11px] font-medium"
                          style={{ color: "var(--nesti-text-tertiary)" }}
                        >
                          参考知识库（点击右侧溯源）：
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {msgCitations.map((c, idx) => (
                            <button
                              key={c.item_id}
                              type="button"
                              onClick={() => void openCitation(c.item_id)}
                              className="inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors hover:opacity-85"
                              style={{
                                background:
                                  "color-mix(in srgb, var(--nesti-accent) 10%, transparent)",
                                borderColor:
                                  "color-mix(in srgb, var(--nesti-accent) 30%, transparent)",
                                color: "var(--nesti-accent)",
                              }}
                            >
                              <span>[{idx + 1}]</span>
                              <span className="max-w-[180px] truncate">{c.title}</span>
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}

              {/* 实时流式输出气泡 */}
              {sending && streamingUserText && (
                <>
                  <div
                    className="ml-10 rounded-xl border p-3.5 text-sm"
                    style={{
                      background:
                        "color-mix(in srgb, var(--nesti-accent) 12%, var(--nesti-surface-0))",
                      borderColor:
                        "color-mix(in srgb, var(--nesti-accent) 28%, transparent)",
                      color: "var(--nesti-text-primary)",
                    }}
                  >
                    <p
                      className="mb-1.5 text-[11px] font-semibold"
                      style={{ color: "var(--nesti-text-tertiary)" }}
                    >
                      我
                    </p>
                    <div className="whitespace-pre-wrap">{streamingUserText}</div>
                  </div>

                  <div
                    className="mr-6 rounded-xl border p-3.5 text-sm"
                    style={{
                      background: "var(--nesti-surface-0)",
                      borderColor: "var(--nesti-accent)",
                      color: "var(--nesti-text-primary)",
                    }}
                  >
                    <div className="mb-1.5 flex items-center justify-between">
                      <span
                        className="text-[11px] font-semibold"
                        style={{ color: "var(--nesti-accent)" }}
                      >
                        助手 · 实时生成中
                      </span>
                      {streamingCitations.length > 0 && (
                        <span
                          className="text-[11px]"
                          style={{ color: "var(--nesti-text-tertiary)" }}
                        >
                          已命中 {streamingCitations.length} 条知识引用
                        </span>
                      )}
                    </div>

                    {streamingReply ? (
                      <div>
                        <MarkdownContent content={streamingReply} />
                        <span
                          className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse align-middle"
                          style={{ background: "var(--nesti-accent)" }}
                        />
                      </div>
                    ) : (
                      <p
                        role="status"
                        className="text-xs"
                        style={{ color: "var(--nesti-text-tertiary)" }}
                      >
                        助手思考中…
                      </p>
                    )}

                    {streamingCitations.length > 0 && (
                      <div
                        className="mt-3 flex flex-wrap gap-1.5 border-t pt-2"
                        style={{ borderColor: "var(--nesti-border-subtle)" }}
                      >
                        {streamingCitations.map((c, idx) => (
                          <button
                            key={c.item_id}
                            type="button"
                            onClick={() => void openCitation(c.item_id)}
                            className="inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium"
                            style={{
                              background:
                                "color-mix(in srgb, var(--nesti-accent) 10%, transparent)",
                              borderColor:
                                "color-mix(in srgb, var(--nesti-accent) 30%, transparent)",
                              color: "var(--nesti-accent)",
                            }}
                          >
                            <span>[{idx + 1}]</span>
                            <span className="max-w-[180px] truncate">{c.title}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </>
              )}

              {thread.messages.length === 0 && !sending && (
                <p
                  className="text-xs"
                  style={{ color: "var(--nesti-text-tertiary)" }}
                >
                  还没有消息，发送第一条开始（Enter 发送，Shift+Enter 换行）。
                </p>
              )}
              <div ref={bottomRef} />
            </div>

            <div
              className="mt-3 flex gap-2 border-t pt-3"
              style={{ borderColor: "var(--nesti-border-subtle)" }}
            >
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void handleSend();
                  }
                }}
                rows={2}
                placeholder="输入问题…（自动检索你的知识库并流式回答，Enter 发送）"
                aria-label="消息输入"
                className="flex-1 resize-none rounded-lg border px-3 py-2 text-sm outline-none"
                style={fieldStyle}
              />
              <button
                type="button"
                onClick={() => void handleSend()}
                disabled={sending || !draft.trim()}
                className="self-end rounded-lg px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
                style={{ background: "var(--nesti-accent)" }}
              >
                {sending ? "生成中…" : "发送"}
              </button>
            </div>
          </>
        )}
      </section>

      {/* 右侧：引用知识溯源抽屉 */}
      {(inspectingItem || loadingInspect) && (
        <aside
          className="w-full shrink-0 space-y-3 overflow-y-auto rounded-xl border p-4 shadow-xs lg:w-96"
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
              引用知识溯源
            </h3>
            <button
              type="button"
              onClick={() => setInspectingItem(null)}
              className="rounded-md border px-2 py-0.5 text-xs transition-colors hover:bg-[var(--nesti-surface-hover)]"
              style={{
                borderColor: "var(--nesti-border-subtle)",
                color: "var(--nesti-text-secondary)",
              }}
            >
              关闭
            </button>
          </div>
          {loadingInspect ? (
            <p className="text-xs" style={{ color: "var(--nesti-text-tertiary)" }}>
              正在加载原笔记…
            </p>
          ) : inspectingItem ? (
            <div className="space-y-3">
              <div
                className="rounded-lg border p-3"
                style={{
                  background: "var(--nesti-surface-0)",
                  borderColor: "var(--nesti-border-subtle)",
                }}
              >
                <h4
                  className="mb-2 text-sm font-semibold"
                  style={{ color: "var(--nesti-text-primary)" }}
                >
                  {inspectingItem.title}
                </h4>
                <MarkdownContent content={inspectingItem.content} />
              </div>
              <KnowledgeDetail
                item={inspectingItem}
                onNotice={setNotice}
                onError={setError}
                onChanged={() => {
                  void openCitation(inspectingItem.id);
                }}
              />
            </div>
          ) : null}
        </aside>
      )}
    </div>
  );
}
