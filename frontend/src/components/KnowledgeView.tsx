import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { KnowledgeItem, KnowledgeStatus, Space } from "../api/types";
import {
  extractTags,
  getActiveWikilinkQuery,
  type WikilinkQuery,
} from "../lib/markdownUtils";
import { KnowledgeDetail } from "./KnowledgeDetail";
import { MarkdownContent } from "./MarkdownContent";

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

type EditorMode = "edit" | "preview" | "split";

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/**
 * 知识库视图：空间切换（主库 + 动态 Agent 副库）+ Markdown 富文本编辑/分屏预览
 * + [[双链]] 自动补全与跳转 + #标签 筛选闭环 + MD/ZIP 导入导出。
 */
export function KnowledgeView() {
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [spaceId, setSpaceId] = useState("");
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // 编辑表单状态
  const [editingId, setEditingId] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [highlightedId, setHighlightedId] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [status, setStatus] = useState<KnowledgeStatus>("draft");
  const [newSpaceName, setNewSpaceName] = useState("");
  const [editorMode, setEditorMode] = useState<EditorMode>("edit");

  // 筛选与标签状态
  const [activeTag, setActiveTag] = useState<string | null>(null);
  const [filterText, setFilterText] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | KnowledgeStatus>("all");

  // [[双链]] 自动补全状态
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [wikilinkQuery, setWikilinkQuery] = useState<WikilinkQuery | null>(null);
  const [suggestionIdx, setSuggestionIdx] = useState(0);

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

  // 统计当前空间全部 #标签（按频次排序）
  const tagCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of items) {
      for (const tag of extractTags(item.content)) {
        counts.set(tag, (counts.get(tag) ?? 0) + 1);
      }
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  }, [items]);

  // 应用标签 + 关键词 + 状态筛选
  const filteredItems = useMemo(() => {
    const q = filterText.trim().toLowerCase();
    return items.filter((item) => {
      if (statusFilter !== "all" && item.status !== statusFilter) return false;
      if (activeTag && !extractTags(item.content).includes(activeTag)) return false;
      if (
        q &&
        !item.title.toLowerCase().includes(q) &&
        !item.content.toLowerCase().includes(q)
      ) {
        return false;
      }
      return true;
    });
  }, [items, activeTag, filterText, statusFilter]);

  // [[双链]] 补全候选列表
  const wikilinkCandidates = useMemo(() => {
    if (!wikilinkQuery) return [];
    const q = wikilinkQuery.query.toLowerCase();
    return items
      .filter((it) => it.id !== editingId && (!q || it.title.toLowerCase().includes(q)))
      .slice(0, 6);
  }, [wikilinkQuery, items, editingId]);

  function resetForm() {
    setEditingId(null);
    setTitle("");
    setContent("");
    setStatus("draft");
    setWikilinkQuery(null);
  }

  async function handleSwitchSpace(id: string) {
    setSpaceId(id);
    setActiveTag(null);
    setFilterText("");
    setHighlightedId(null);
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
        const result = await api.updateKnowledge(editingId, { title: t, content: c, status });
        if (result.kind === "review") {
          setNotice("已提交审核，可在「审核」页签处理。");
        } else {
          setNotice("已更新知识条目。");
        }
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
    setWikilinkQuery(null);
  }

  async function handleDelete(id: string) {
    if (!window.confirm("确认删除该知识条目？")) return;
    setError(null);
    try {
      const result = await api.deleteKnowledge(id);
      if (result.kind === "review") {
        setNotice("已提交删除审核，可在「审核」页签处理。");
      }
      if (editingId === id) {
        resetForm();
      }
      await loadItems(spaceId);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleImportFile(file: File) {
    setError(null);
    try {
      if (file.name.toLowerCase().endsWith(".zip")) {
        const buf = await file.arrayBuffer();
        let binary = "";
        const bytes = new Uint8Array(buf);
        for (let i = 0; i < bytes.length; i += 0x8000) {
          binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
        }
        const report = await api.importMarkdown({
          archive_base64: btoa(binary),
          space_id: spaceId || null,
        });
        const first = report.items?.[0];
        setNotice(
          first?.status === "pending_review"
            ? "ZIP 导入已提交审核队列（含暂存附件），请前往「审核队列」批准。"
            : `ZIP 导入完成（状态：${first?.status ?? "ok"}）。`,
        );
      } else {
        const text = await file.text();
        const report = await api.importMarkdown({
          content: text,
          filename: file.name,
          space_id: spaceId || null,
        });
        const first = report.items?.[0];
        setNotice(
          first?.status === "pending_review"
            ? "Markdown 导入已提交审核队列。"
            : `已导入 Markdown：${file.name}（${first?.status ?? "ok"}）。`,
        );
      }
      await loadItems(spaceId);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleExportZip() {
    setError(null);
    try {
      const blob = await api.exportMarkdownZip(spaceId || null);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "explainlab-export.zip";
      a.click();
      URL.revokeObjectURL(url);
      setNotice("已导出当前空间 Markdown ZIP。");
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  // 在光标处插入 Markdown 快捷片段
  function insertSnippet(before: string, after = "") {
    const el = textareaRef.current;
    if (!el) {
      setContent((prev) => `${prev}${before}${after}`);
      return;
    }
    const start = el.selectionStart ?? content.length;
    const end = el.selectionEnd ?? content.length;
    const selected = content.slice(start, end);
    const next = `${content.slice(0, start)}${before}${selected}${after}${content.slice(end)}`;
    const nextCursor = start + before.length + selected.length;
    setContent(next);
    const active = getActiveWikilinkQuery(next, nextCursor);
    setWikilinkQuery(active);
    setSuggestionIdx(0);
    window.requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(nextCursor, nextCursor);
    });
  }

  function applyWikilinkCandidate(targetTitle: string) {
    if (!wikilinkQuery) return;
    const inserted = `[[${targetTitle}]]`;
    const next =
      content.slice(0, wikilinkQuery.start) +
      inserted +
      content.slice(wikilinkQuery.end);
    const nextCursor = wikilinkQuery.start + inserted.length;
    setContent(next);
    setWikilinkQuery(null);
    setSuggestionIdx(0);
    window.requestAnimationFrame(() => {
      const el = textareaRef.current;
      if (el) {
        el.focus();
        el.setSelectionRange(nextCursor, nextCursor);
      }
    });
  }

  function handleContentChange(nextVal: string, cursorPos: number | null) {
    setContent(nextVal);
    if (cursorPos !== null) {
      const active = getActiveWikilinkQuery(nextVal, cursorPos);
      setWikilinkQuery(active);
      setSuggestionIdx(0);
    } else {
      setWikilinkQuery(null);
    }
  }

  // 点击渲染正文中的 [[双链]]：定位已有条目，或预填新条目
  function handleWikilinkClick(targetTitle: string) {
    const match = items.find(
      (it) => it.title.trim().toLowerCase() === targetTitle.trim().toLowerCase(),
    );
    if (match) {
      setActiveTag(null);
      setFilterText("");
      setStatusFilter("all");
      setHighlightedId(match.id);
      setExpandedId(match.id);
      setNotice(`已定位双链知识：${match.title}`);
      const card = document.getElementById(`knowledge-card-${match.id}`);
      card?.scrollIntoView?.({ behavior: "smooth", block: "center" });
    } else {
      setEditingId(null);
      setTitle(targetTitle);
      setNotice(`当前空间尚无「${targetTitle}」，已为你预填标题，可在左侧直接创建。`);
    }
  }

  const fieldStyle = {
    background: "var(--nesti-surface-0)",
    borderColor: "var(--nesti-border-subtle)",
    color: "var(--nesti-text-primary)",
  };

  return (
    <div className="space-y-4">
      {/* 顶部空间与导入导出栏 */}
      <div
        className="flex flex-wrap items-center gap-3 rounded-xl border p-3.5 shadow-xs"
        style={{
          background: "var(--nesti-surface-1)",
          borderColor: "var(--nesti-border-subtle)",
        }}
      >
        <label
          className="text-sm font-medium"
          style={{ color: "var(--nesti-text-secondary)" }}
          htmlFor="space-select"
        >
          知识空间
        </label>
        <select
          id="space-select"
          value={spaceId}
          onChange={(e) => void handleSwitchSpace(e.target.value)}
          className="rounded-lg border px-3 py-1.5 text-sm outline-none"
          style={fieldStyle}
        >
          {spaces.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
              {s.kind === "personal" ? "（个人）" : ""}
            </option>
          ))}
        </select>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <input
            value={newSpaceName}
            onChange={(e) => setNewSpaceName(e.target.value)}
            placeholder="新项目空间名称"
            aria-label="新项目空间名称"
            className="w-40 rounded-lg border px-3 py-1.5 text-sm outline-none"
            style={fieldStyle}
          />
          <button
            type="button"
            onClick={() => void handleCreateSpace()}
            disabled={!newSpaceName.trim()}
            className="rounded-lg border px-3 py-1.5 text-sm transition-colors hover:bg-[var(--nesti-surface-hover)] disabled:opacity-40"
            style={{
              borderColor: "var(--nesti-border-subtle)",
              color: "var(--nesti-text-secondary)",
            }}
          >
            新建空间
          </button>
          <label
            className="cursor-pointer rounded-lg border px-3 py-1.5 text-sm transition-colors hover:bg-[var(--nesti-surface-hover)]"
            style={{
              borderColor: "var(--nesti-border-subtle)",
              color: "var(--nesti-text-secondary)",
            }}
          >
            导入 MD/ZIP
            <input
              type="file"
              accept=".md,.markdown,.zip"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void handleImportFile(f);
                e.target.value = "";
              }}
            />
          </label>
          <button
            type="button"
            onClick={() => void handleExportZip()}
            className="rounded-lg border px-3 py-1.5 text-sm transition-colors hover:bg-[var(--nesti-surface-hover)]"
            style={{
              borderColor: "var(--nesti-border-subtle)",
              color: "var(--nesti-text-secondary)",
            }}
          >
            导出 ZIP
          </button>
        </div>
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-500"
        >
          {error}
        </div>
      )}
      {notice && (
        <div
          role="status"
          className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-600 dark:text-emerald-400"
        >
          {notice}
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-[380px_1fr]">
        {/* 左侧：Markdown 富编辑器（支持编辑 / 预览 / 分屏 & [[双链]] 自动补全） */}
        <section
          className="h-fit space-y-3 rounded-xl border p-4 shadow-xs"
          style={{
            background: "var(--nesti-surface-1)",
            borderColor: "var(--nesti-border-subtle)",
          }}
        >
          <div className="flex items-center justify-between gap-2">
            <h2
              className="text-sm font-semibold"
              style={{ color: "var(--nesti-text-primary)" }}
            >
              {editingId ? "编辑知识条目" : "新建知识条目"}
            </h2>
            <div
              className="inline-flex rounded-lg border p-0.5 text-[11px]"
              style={{
                background: "var(--nesti-surface-0)",
                borderColor: "var(--nesti-border-subtle)",
              }}
            >
              {(
                [
                  ["edit", "源码"],
                  ["preview", "预览"],
                  ["split", "分屏"],
                ] as const
              ).map(([mode, label]) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setEditorMode(mode)}
                  className="rounded-md px-2 py-0.5 font-medium transition-colors"
                  style={
                    editorMode === mode
                      ? { background: "var(--nesti-accent)", color: "#ffffff" }
                      : { color: "var(--nesti-text-secondary)" }
                  }
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-2.5">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="标题"
              aria-label="知识标题"
              className="w-full rounded-lg border px-3 py-1.5 text-sm outline-none"
              style={fieldStyle}
            />

            {/* Markdown 快捷格式条 */}
            {editorMode !== "preview" && (
              <div className="flex flex-wrap items-center gap-1 text-[11px]">
                {[
                  { label: "H2", run: () => insertSnippet("## ") },
                  { label: "加粗", run: () => insertSnippet("**", "**") },
                  { label: "代码", run: () => insertSnippet("`", "`") },
                  { label: "列表", run: () => insertSnippet("- ") },
                  { label: "[[双链]]", run: () => insertSnippet("[[") },
                  { label: "#标签", run: () => insertSnippet("#") },
                ].map((btn) => (
                  <button
                    key={btn.label}
                    type="button"
                    onClick={btn.run}
                    className="rounded border px-2 py-0.5 font-medium transition-colors hover:bg-[var(--nesti-surface-hover)]"
                    style={{
                      background: "var(--nesti-surface-0)",
                      borderColor: "var(--nesti-border-subtle)",
                      color: "var(--nesti-text-secondary)",
                    }}
                  >
                    {btn.label}
                  </button>
                ))}
              </div>
            )}

            {/* 编辑区 / 预览区 / 分屏区 */}
            <div className={editorMode === "split" ? "space-y-2" : ""}>
              {editorMode !== "preview" && (
                <div className="relative">
                  <textarea
                    ref={textareaRef}
                    value={content}
                    onChange={(e) =>
                      handleContentChange(e.target.value, e.target.selectionStart)
                    }
                    onKeyDown={(e) => {
                      if (wikilinkCandidates.length === 0) return;
                      if (e.key === "ArrowDown") {
                        e.preventDefault();
                        setSuggestionIdx((i) => (i + 1) % wikilinkCandidates.length);
                      } else if (e.key === "ArrowUp") {
                        e.preventDefault();
                        setSuggestionIdx(
                          (i) =>
                            (i - 1 + wikilinkCandidates.length) %
                            wikilinkCandidates.length,
                        );
                      } else if (e.key === "Enter" || e.key === "Tab") {
                        e.preventDefault();
                        applyWikilinkCandidate(
                          wikilinkCandidates[suggestionIdx]?.title ??
                            wikilinkCandidates[0].title,
                        );
                      } else if (e.key === "Escape") {
                        setWikilinkQuery(null);
                      }
                    }}
                    rows={editorMode === "split" ? 6 : 8}
                    placeholder="支持 Markdown、[[双链]] 自动补全、#标签（输入 [[ 触发联想）"
                    aria-label="知识内容"
                    className="w-full resize-y rounded-lg border px-3 py-2 font-mono text-xs leading-relaxed outline-none"
                    style={fieldStyle}
                  />

                  {/* [[双链]] 自动补全弹窗 */}
                  {wikilinkCandidates.length > 0 && (
                    <div
                      role="listbox"
                      aria-label="双链候选"
                      className="absolute left-0 right-0 z-20 mt-1 overflow-hidden rounded-lg border shadow-lg"
                      style={{
                        background: "var(--nesti-surface-1)",
                        borderColor: "var(--nesti-border-strong)",
                      }}
                    >
                      <div
                        className="border-b px-2.5 py-1 text-[10px] font-medium"
                        style={{
                          borderColor: "var(--nesti-border-subtle)",
                          color: "var(--nesti-text-tertiary)",
                        }}
                      >
                        插入 [[双链]]（Enter / 点击选择）
                      </div>
                      {wikilinkCandidates.map((cand, idx) => (
                        <button
                          key={cand.id}
                          type="button"
                          onMouseDown={(e) => {
                            e.preventDefault();
                            applyWikilinkCandidate(cand.title);
                          }}
                          className="flex w-full items-center justify-between px-2.5 py-1.5 text-left text-xs transition-colors"
                          style={
                            idx === suggestionIdx
                              ? {
                                  background:
                                    "color-mix(in srgb, var(--nesti-accent) 14%, transparent)",
                                  color: "var(--nesti-accent)",
                                }
                              : { color: "var(--nesti-text-primary)" }
                          }
                        >
                          <span className="truncate font-medium">{cand.title}</span>
                          <span className="ml-2 shrink-0 text-[10px] opacity-70">
                            {STATUS_LABEL[cand.status]}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {editorMode !== "edit" && (
                <div
                  className="min-h-[140px] rounded-lg border p-3"
                  style={{
                    background: "var(--nesti-surface-0)",
                    borderColor: "var(--nesti-border-subtle)",
                  }}
                >
                  {content.trim() ? (
                    <MarkdownContent
                      content={content}
                      onWikilinkClick={handleWikilinkClick}
                      onTagClick={(tag) => setActiveTag(tag)}
                    />
                  ) : (
                    <p
                      className="text-xs"
                      style={{ color: "var(--nesti-text-tertiary)" }}
                    >
                      输入 Markdown 内容后可实时预览排版、代码块、表格、[[双链]] 与 #标签。
                    </p>
                  )}
                </div>
              )}
            </div>

            {editingId && (
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value as KnowledgeStatus)}
                aria-label="知识状态"
                className="w-full rounded-lg border px-3 py-1.5 text-sm outline-none"
                style={fieldStyle}
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
                className="flex-1 rounded-lg px-3 py-1.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
                style={{ background: "var(--nesti-accent)" }}
              >
                {editingId ? "保存修改" : "创建"}
              </button>
              {editingId && (
                <button
                  type="button"
                  onClick={resetForm}
                  className="rounded-lg border px-3 py-1.5 text-sm transition-colors hover:bg-[var(--nesti-surface-hover)]"
                  style={{
                    borderColor: "var(--nesti-border-subtle)",
                    color: "var(--nesti-text-secondary)",
                  }}
                >
                  取消
                </button>
              )}
            </div>
          </div>

          {/* 左侧底部：当前空间 #标签 筛选器 */}
          {tagCounts.length > 0 && (
            <div
              className="space-y-2 border-t pt-3"
              style={{ borderColor: "var(--nesti-border-subtle)" }}
            >
              <div className="flex items-center justify-between text-xs">
                <span
                  className="font-semibold"
                  style={{ color: "var(--nesti-text-primary)" }}
                >
                  标签筛选（{tagCounts.length}）
                </span>
                {activeTag && (
                  <button
                    type="button"
                    onClick={() => setActiveTag(null)}
                    className="text-[11px] hover:underline"
                    style={{ color: "var(--nesti-accent)" }}
                  >
                    清除筛选
                  </button>
                )}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {tagCounts.map(([tag, count]) => {
                  const selected = activeTag === tag;
                  return (
                    <button
                      key={tag}
                      type="button"
                      onClick={() => setActiveTag(selected ? null : tag)}
                      className="rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors"
                      style={
                        selected
                          ? {
                              background: "var(--nesti-accent)",
                              borderColor: "var(--nesti-accent)",
                              color: "#ffffff",
                            }
                          : {
                              background: "var(--nesti-surface-0)",
                              borderColor: "var(--nesti-border-subtle)",
                              color: "var(--nesti-text-secondary)",
                            }
                      }
                    >
                      #{tag} <span className="opacity-70">{count}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </section>

        {/* 右侧：筛选栏 + Markdown 富渲染知识卡片列表 */}
        <section className="space-y-3">
          {items.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              <input
                type="search"
                value={filterText}
                onChange={(e) => setFilterText(e.target.value)}
                placeholder="筛选当前空间标题或正文…"
                aria-label="筛选知识条目"
                className="min-w-[200px] flex-1 rounded-lg border px-3 py-1.5 text-xs outline-none"
                style={fieldStyle}
              />
              <div
                className="inline-flex rounded-lg border p-0.5 text-xs"
                style={{
                  background: "var(--nesti-surface-1)",
                  borderColor: "var(--nesti-border-subtle)",
                }}
              >
                {(
                  [
                    ["all", "全部"],
                    ["active", "生效"],
                    ["draft", "草稿"],
                    ["archived", "归档"],
                  ] as const
                ).map(([st, label]) => (
                  <button
                    key={st}
                    type="button"
                    onClick={() => setStatusFilter(st)}
                    className="rounded-md px-2.5 py-1 font-medium transition-colors"
                    style={
                      statusFilter === st
                        ? { background: "var(--nesti-accent)", color: "#ffffff" }
                        : { color: "var(--nesti-text-secondary)" }
                    }
                  >
                    {label}
                  </button>
                ))}
              </div>
              {activeTag && (
                <span
                  className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium text-white"
                  style={{ background: "var(--nesti-accent)" }}
                >
                  #{activeTag}
                  <button
                    type="button"
                    onClick={() => setActiveTag(null)}
                    aria-label="移除标签筛选"
                    className="ml-0.5 opacity-80 hover:opacity-100"
                  >
                    ×
                  </button>
                </span>
              )}
            </div>
          )}

          {loading ? (
            <p
              role="status"
              className="text-sm"
              style={{ color: "var(--nesti-text-secondary)" }}
            >
              正在加载知识条目…
            </p>
          ) : items.length === 0 ? (
            <p
              className="rounded-xl border p-6 text-sm"
              style={{
                background: "var(--nesti-surface-1)",
                borderColor: "var(--nesti-border-subtle)",
                color: "var(--nesti-text-secondary)",
              }}
            >
              该空间暂无知识条目。可在左侧手动创建，或在「对话」中提取。
            </p>
          ) : filteredItems.length === 0 ? (
            <p
              className="rounded-xl border p-6 text-sm"
              style={{
                background: "var(--nesti-surface-1)",
                borderColor: "var(--nesti-border-subtle)",
                color: "var(--nesti-text-secondary)",
              }}
            >
              当前筛选条件下没有匹配的知识条目。
            </p>
          ) : (
            filteredItems.map((item) => {
              const isHighlighted = highlightedId === item.id;
              const itemTags = extractTags(item.content);
              return (
                <article
                  key={item.id}
                  id={`knowledge-card-${item.id}`}
                  className="rounded-xl border p-4 shadow-xs transition-all"
                  style={{
                    background: "var(--nesti-surface-1)",
                    borderColor: isHighlighted
                      ? "var(--nesti-accent)"
                      : "var(--nesti-border-subtle)",
                    boxShadow: isHighlighted
                      ? "0 0 0 2px color-mix(in srgb, var(--nesti-accent) 25%, transparent)"
                      : undefined,
                  }}
                >
                  <div className="mb-2.5 flex items-start justify-between gap-3">
                    <div className="min-w-0 space-y-1">
                      <h3
                        className="text-base font-semibold"
                        style={{ color: "var(--nesti-text-primary)" }}
                      >
                        {item.title}
                      </h3>
                      {itemTags.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {itemTags.map((tag) => (
                            <button
                              key={tag}
                              type="button"
                              onClick={() => setActiveTag(tag)}
                              className="rounded-full px-2 py-0.5 text-[11px] font-medium"
                              style={{
                                background: "var(--nesti-surface-2)",
                                color: "var(--nesti-text-secondary)",
                              }}
                            >
                              #{tag}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                    <span
                      className="shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium"
                      style={{
                        background: "var(--nesti-surface-2)",
                        color: "var(--nesti-text-secondary)",
                      }}
                    >
                      {STATUS_LABEL[item.status]}
                    </span>
                  </div>

                  {/* Markdown 富文本渲染（含可点击 [[双链]] 与 #标签） */}
                  <MarkdownContent
                    content={item.content}
                    onWikilinkClick={handleWikilinkClick}
                    onTagClick={(tag) => setActiveTag(tag)}
                  />

                  {item.source_refs.length > 0 && (
                    <div
                      className="mt-3 space-y-1 border-t pt-2"
                      style={{ borderColor: "var(--nesti-border-subtle)" }}
                    >
                      {item.source_refs.map((s) => (
                        <p
                          key={s.id}
                          className="text-xs"
                          style={{ color: "var(--nesti-text-tertiary)" }}
                        >
                          来源：{SOURCE_LABEL[s.source_type] ?? s.source_type}
                          {s.conversation_id &&
                            ` · 会话 ${s.conversation_id.slice(0, 8)}…`}
                          {s.uri && ` · ${s.uri}`}
                          {s.excerpt && (
                            <span className="mt-0.5 block truncate opacity-80">
                              {s.excerpt}
                            </span>
                          )}
                        </p>
                      ))}
                    </div>
                  )}

                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => startEdit(item)}
                      className="rounded-lg border px-3 py-1 text-xs font-medium transition-colors hover:bg-[var(--nesti-surface-hover)]"
                      style={{
                        borderColor: "var(--nesti-border-subtle)",
                        color: "var(--nesti-text-secondary)",
                      }}
                    >
                      编辑
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleDelete(item.id)}
                      className="rounded-lg border px-3 py-1 text-xs font-medium text-red-500 transition-colors hover:bg-red-500/10"
                      style={{ borderColor: "var(--nesti-border-subtle)" }}
                    >
                      删除
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        setExpandedId(expandedId === item.id ? null : item.id)
                      }
                      aria-expanded={expandedId === item.id}
                      className="rounded-lg border px-3 py-1 text-xs font-medium transition-colors hover:bg-[var(--nesti-surface-hover)]"
                      style={{
                        borderColor: "var(--nesti-border-subtle)",
                        color: "var(--nesti-text-secondary)",
                      }}
                    >
                      {expandedId === item.id ? "收起详情" : "治理详情"}
                    </button>
                  </div>

                  {expandedId === item.id && (
                    <KnowledgeDetail
                      item={item}
                      onNotice={setNotice}
                      onError={setError}
                      onChanged={() => void loadItems(spaceId)}
                    />
                  )}
                </article>
              );
            })
          )}
        </section>
      </div>
    </div>
  );
}
