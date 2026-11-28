import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { KnowledgeItem, KnowledgeStatus, MediaItem, Space } from "../api/types";
import {
  extractTags,
  getActiveWikilinkQuery,
  type WikilinkQuery,
} from "../lib/markdownUtils";
import { AgentHubModal } from "./AgentHubModal";
import { ContextMenu, type ContextMenuState } from "./ContextMenu";
import { DocumentReaderModal } from "./DocumentReaderModal";
import { FolderWatcherModal } from "./FolderWatcherModal";
import { KnowledgeDetail } from "./KnowledgeDetail";
import { LiveSandboxPanel } from "./LiveSandboxPanel";
import { MarkdownContent } from "./MarkdownContent";
import { MediaAttachmentsPanel } from "./MediaAttachmentsPanel";

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

interface KnowledgeViewProps {
  selectedSpaceId?: string;
  focusItemId?: string | null;
  focusToken?: number;
  refreshKey?: number;
  onSelectSpace?: (id: string) => void;
  onOpenAgentHub?: (mode?: "manage" | "picker", agentName?: string | null) => void;
  onSpacesChanged?: () => void;
}

/** 将图片文件缩放压缩为轻量 DataURL，方便直接内嵌在知识卡片中离线呈现。 */
function compressImageToDataUrl(file: File, maxWidth = 960): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("读取图片失败"));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => resolve(String(reader.result));
      img.onload = () => {
        const scale = img.width > maxWidth ? maxWidth / img.width : 1;
        const w = Math.max(1, Math.round(img.width * scale));
        const h = Math.max(1, Math.round(img.height * scale));
        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          resolve(String(reader.result));
          return;
        }
        ctx.drawImage(img, 0, 0, w, h);
        try {
          resolve(canvas.toDataURL("image/webp", 0.84));
        } catch {
          resolve(canvas.toDataURL("image/png"));
        }
      };
      img.src = String(reader.result);
    };
    reader.readAsDataURL(file);
  });
}

/**
 * 知识库视图：清晰三分组（主库 / AI 助手副库 / 专题分类）+ 一键添加 AI 助手与自动/自选吸尘
 * + 原生右键菜单 + ChatGPT 风格图文卡片/表格/截图粘贴 + [[双链]] 自动补全。
 */
export function KnowledgeView({
  selectedSpaceId,
  focusItemId = null,
  focusToken = 0,
  refreshKey = 0,
  onSelectSpace,
  onOpenAgentHub,
  onSpacesChanged,
}: KnowledgeViewProps = {}) {
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [spaceId, setSpaceId] = useState("");
  const [localAgentHubOpen, setLocalAgentHubOpen] = useState(false);
  const [localAgentHubMode, setLocalAgentHubMode] = useState<"manage" | "picker">("manage");
  const [folderModalOpen, setFolderModalOpen] = useState(false);
  const [cardMenu, setCardMenu] = useState<ContextMenuState | null>(null);
  const [vacuuming, setVacuuming] = useState(false);
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [lastSavedPath, setLastSavedPath] = useState<string | null>(null);
  const [clipOpen, setClipOpen] = useState(false);
  const [clipUrl, setClipUrl] = useState("");
  const [clipping, setClipping] = useState(false);
  const [batchMode, setBatchMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [batchMoveSpaceId, setBatchMoveSpaceId] = useState("");
  const [batchBusy, setBatchBusy] = useState(false);
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // 编辑表单状态
  const [editingId, setEditingId] = useState<string | null>(null);
  const [composerOpen, setComposerOpen] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [sandboxId, setSandboxId] = useState<string | null>(null);
  const [mediaId, setMediaId] = useState<string | null>(null);
  const [mediaByItem, setMediaByItem] = useState<Record<string, MediaItem[]>>({});
  const [readingMedia, setReadingMedia] = useState<MediaItem | null>(null);
  const [highlightedId, setHighlightedId] = useState<string | null>(null);
  const [pendingFocusId, setPendingFocusId] = useState<string | null>(null);
  const [navHistory, setNavHistory] = useState<
    { spaceId: string; itemId: string; title: string }[]
  >([]);
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

  const loadMediaIndex = useCallback(async () => {
    try {
      const all = await api.listMediaLibrary();
      const grouped: Record<string, MediaItem[]> = {};
      for (const m of all) {
        (grouped[m.item_id] ??= []).push(m);
      }
      setMediaByItem(grouped);
    } catch {
      // 忽略单测或离线未启用文件库接口时的静默回退
    }
  }, []);

  const loadItems = useCallback(async (targetSpaceId: string) => {
    setLoading(true);
    try {
      setItems(await api.listKnowledge(targetSpaceId || undefined));
      setError(null);
      void loadMediaIndex();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [loadMediaIndex]);

  useEffect(() => {
    void (async () => {
      try {
        const rows = await api.listSpaces();
        setSpaces(rows);
        const preferred =
          (selectedSpaceId ? rows.find((s) => s.id === selectedSpaceId) : undefined) ??
          rows.find((s) => s.kind === "personal") ??
          rows[0];
        if (preferred) {
          setSpaceId(preferred.id);
          await loadItems(preferred.id);
        } else {
          setLoading(false);
        }
      } catch (err) {
        setError(errorMessage(err));
        setLoading(false);
      }
    })();
  }, [loadItems, selectedSpaceId, refreshKey]);

  const personalSpaces = useMemo(
    () => spaces.filter((s) => s.kind === "personal"),
    [spaces],
  );
  const agentSpaces = useMemo(
    () => spaces.filter((s) => s.name.startsWith("Agent ·")),
    [spaces],
  );
  const topicSpaces = useMemo(
    () => spaces.filter((s) => s.kind !== "personal" && !s.name.startsWith("Agent ·")),
    [spaces],
  );
  const currentSpace = useMemo(
    () => spaces.find((s) => s.id === spaceId) ?? null,
    [spaces, spaceId],
  );
  const currentAgentName = useMemo(() => {
    if (!currentSpace || !currentSpace.name.startsWith("Agent ·")) return null;
    return currentSpace.name.replace(/^Agent\s*·\s*/i, "").trim();
  }, [currentSpace]);

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
    onSelectSpace?.(id);
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
      onSpacesChanged?.();
      await handleSwitchSpace(space.id);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleInsertImageFile(file: File) {
    try {
      const dataUrl = await compressImageToDataUrl(file);
      const label = file.name.replace(/\.[^.]+$/, "") || "截图";
      insertSnippet(`\n![${label}](${dataUrl})\n`);
      setNotice(`已插入图片「${label}」（切到预览或分屏可即时查看图文效果）。`);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleQuickToggleStatus(item: KnowledgeItem) {
    const nextStatus: KnowledgeStatus = item.status === "active" ? "draft" : "active";
    setError(null);
    try {
      const res = await api.updateKnowledge(item.id, {
        title: item.title,
        content: item.content,
        status: nextStatus,
      });
      if (res.kind === "review") {
        setNotice("状态变更已提交至「审核队列」。");
      } else {
        setNotice(`已将「${item.title}」切换为「${STATUS_LABEL[nextStatus]}」。`);
      }
      await loadItems(spaceId);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  function openItemContextMenu(e: React.MouseEvent, item: KnowledgeItem) {
    e.preventDefault();
    setCardMenu({
      x: e.clientX,
      y: e.clientY,
      items: [
        {
          id: "edit",
          label: "编辑这条知识",
          onClick: () => startEdit(item),
        },
        {
          id: "toggle-status",
          label: item.status === "active" ? "切回草稿状态" : "设为生效状态",
          onClick: () => void handleQuickToggleStatus(item),
        },
        {
          id: "sandbox",
          label: sandboxId === item.id ? "收起动态沙盒" : "打开动态沙盒",
          dividerBefore: true,
          onClick: () => setSandboxId((prev) => (prev === item.id ? null : item.id)),
        },
        {
          id: "media",
          label: mediaId === item.id ? "收起附件 / 音视频" : "管理附件 / 音视频",
          onClick: () => setMediaId((prev) => (prev === item.id ? null : item.id)),
        },
        {
          id: "detail",
          label: expandedId === item.id ? "收起治理详情" : "查看治理详情",
          onClick: () => setExpandedId((prev) => (prev === item.id ? null : item.id)),
        },
        {
          id: "copy",
          label: "复制 Markdown 原文",
          onClick: () => {
            void navigator.clipboard?.writeText(`# ${item.title}\n\n${item.content}`);
            setNotice(`已复制「${item.title}」的 Markdown 原文。`);
          },
        },
        {
          id: "export-pdf",
          label: "导出单篇总结 PDF…",
          dividerBefore: true,
          onClick: () => void handleGenerateDeliverable("pdf", item.id),
        },
        {
          id: "export-docx",
          label: "导出单篇 Word (.docx)…",
          onClick: () => void handleGenerateDeliverable("docx", item.id),
        },
        {
          id: "export-pptx",
          label: "导出单篇 PPT (.pptx)…",
          onClick: () => void handleGenerateDeliverable("pptx", item.id),
        },
        {
          id: "export-card",
          label: "导出高清知识卡片长图 (.png)…",
          onClick: () => void handleGenerateDeliverable("card", item.id),
        },
        {
          id: "delete",
          label: "删除条目",
          danger: true,
          dividerBefore: true,
          onClick: () => void handleDelete(item.id),
        },
      ],
    });
  }

  async function handleGenerateDeliverable(
    format: "pdf" | "pptx" | "docx" | "card",
    itemId?: string,
  ) {
    setExportMenuOpen(false);
    setExporting(true);
    setError(null);
    setLastSavedPath(null);
    const labelMap = {
      pdf: "总结报告 PDF",
      pptx: "汇报演示 PPT",
      docx: "可编辑 Word 文档",
      card: "高清知识卡片长图",
    } as const;
    try {
      const res = await api.generateDeliverable(format, {
        space_id: itemId ? null : spaceId || null,
        item_id: itemId ?? null,
      });
      if (res.canceled) {
        setNotice("已取消保存。");
      } else {
        setLastSavedPath(res.path ?? null);
        setNotice(
          res.path
            ? `已生成${labelMap[format]}并保存至：${res.path}`
            : `已生成${labelMap[format]}（${res.filename}）。`,
        );
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setExporting(false);
    }
  }

  async function handleClipUrl() {
    const raw = clipUrl.trim();
    if (!raw || clipping) return;
    setClipping(true);
    setError(null);
    setNotice(null);
    try {
      const created = await api.clipUrl(raw, spaceId || null);
      setClipUrl("");
      setClipOpen(false);
      await loadItems(spaceId);
      setHighlightedId(created.id);
      setNotice(`已一键剪藏网页「${created.title}」并存入当前知识库。`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setClipping(false);
    }
  }

  function toggleSelectItem(id: string) {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  function handleToggleSelectAll() {
    const visibleIds = filteredItems.map((it) => it.id);
    const allSelected =
      visibleIds.length > 0 && visibleIds.every((id) => selectedIds.includes(id));
    setSelectedIds(allSelected ? [] : visibleIds);
  }

  async function handleBatchActivate() {
    if (selectedIds.length === 0 || batchBusy) return;
    setBatchBusy(true);
    setError(null);
    try {
      let applied = 0;
      let queued = 0;
      for (const id of selectedIds) {
        const target = items.find((it) => it.id === id);
        if (!target || target.status === "active") continue;
        const res = await api.updateKnowledge(id, {
          title: target.title,
          content: target.content,
          status: "active",
        });
        if (res.kind === "review") queued += 1;
        else applied += 1;
      }
      setSelectedIds([]);
      await loadItems(spaceId);
      setNotice(
        queued > 0
          ? `批量生效完成：${applied} 条已生效，${queued} 条已提交审核队列。`
          : `已批量将 ${applied} 条知识设为生效状态。`,
      );
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBatchBusy(false);
    }
  }

  async function handleBatchMove() {
    if (selectedIds.length === 0 || !batchMoveSpaceId || batchBusy) return;
    setBatchBusy(true);
    setError(null);
    try {
      let moved = 0;
      let queued = 0;
      for (const id of selectedIds) {
        const res = await api.updateKnowledge(id, { space_id: batchMoveSpaceId });
        if (res.kind === "review") queued += 1;
        else moved += 1;
      }
      const targetName =
        spaces.find((s) => s.id === batchMoveSpaceId)?.name ?? "目标空间";
      setSelectedIds([]);
      await loadItems(spaceId);
      onSpacesChanged?.();
      setNotice(
        queued > 0
          ? `已移动 ${moved} 条至「${targetName}」，另有 ${queued} 条生效知识已提交审核。`
          : `已将 ${moved} 条知识移动至「${targetName}」。`,
      );
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBatchBusy(false);
    }
  }

  async function handleBatchDelete() {
    if (selectedIds.length === 0 || batchBusy) return;
    if (!window.confirm(`确认批量删除选中的 ${selectedIds.length} 条知识？`)) return;
    setBatchBusy(true);
    setError(null);
    try {
      let deleted = 0;
      let queued = 0;
      for (const id of selectedIds) {
        const res = await api.deleteKnowledge(id);
        if (res.kind === "review") queued += 1;
        else deleted += 1;
      }
      setSelectedIds([]);
      await loadItems(spaceId);
      onSpacesChanged?.();
      setNotice(
        queued > 0
          ? `已删除 ${deleted} 条，另有 ${queued} 条生效知识已提交删除审核。`
          : `已批量删除 ${deleted} 条知识条目。`,
      );
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBatchBusy(false);
    }
  }

  async function handleQuickVacuum() {
    setVacuuming(true);
    setError(null);
    setNotice(null);
    try {
      const res = await api.vacuumAgents(currentAgentName, 3);
      await loadItems(spaceId);
      onSpacesChanged?.();
      if (res.created_items.length > 0) {
        setNotice(
          `吸尘完成：从 ${res.scanned_sessions} 份本地对话中提炼入库了 ${res.created_items.length} 条新知识！`,
        );
      } else if (res.scanned_sessions === 0) {
        setNotice("当前没有未处理的新本地对话，已经是最新的啦。");
      } else {
        setNotice(`已扫描 ${res.scanned_sessions} 份对话，均为闲聊或过程日志，已自动过滤。`);
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setVacuuming(false);
    }
  }

  function deriveAutoTitle(rawContent: string): string {
    const cleaned = rawContent
      .replace(/!\[[^\]]*\]\([^)]+\)/g, "")
      .split(/\r?\n/)
      .map((line) => line.replace(/^[#>*\-\s\d.]+/, "").trim())
      .find((line) => line.length > 0);
    if (cleaned) {
      return cleaned.length > 28 ? `${cleaned.slice(0, 28)}…` : cleaned;
    }
    const now = new Date();
    const ymd = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
    return `图文笔记 ${ymd}`;
  }

  function formatDisplayUri(uri: string): string {
    const stripped = uri.replace(/^file:\/\/\/?/i, "");
    try {
      return decodeURIComponent(stripped);
    } catch {
      return stripped;
    }
  }

  async function handleSave() {
    const c = content.trim();
    if (!c) return;
    const t = title.trim() || deriveAutoTitle(c);
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
        setNotice(title.trim() ? "已创建知识条目。" : `已自动生成标题「${t}」并创建知识条目。`);
      }
      resetForm();
      await loadItems(spaceId);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  function startEdit(item: KnowledgeItem) {
    setComposerOpen(true);
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

  // 外部传入 focusItemId（如星图、工作台、Ctrl+K 跳转）时，等待该空间条目加载完毕后自动平滑滚动并高亮
  useEffect(() => {
    if (focusItemId) {
      setPendingFocusId(focusItemId);
    }
  }, [focusItemId, focusToken]);

  useEffect(() => {
    if (!pendingFocusId || loading) return;
    const found = items.find((it) => it.id === pendingFocusId);
    if (!found) return;
    setActiveTag(null);
    setFilterText("");
    setStatusFilter("all");
    setHighlightedId(found.id);
    setPendingFocusId(null);
    window.requestAnimationFrame(() => {
      const card = document.getElementById(`knowledge-card-${found.id}`);
      card?.scrollIntoView?.({ behavior: "smooth", block: "center" });
    });
    const timer = window.setTimeout(() => {
      setHighlightedId((curr) => (curr === found.id ? null : curr));
    }, 2800);
    return () => window.clearTimeout(timer);
  }, [pendingFocusId, items, loading]);

  async function focusOrJumpToItem(
    target: KnowledgeItem,
    fromItem?: KnowledgeItem,
  ) {
    if (fromItem && fromItem.id !== target.id) {
      setNavHistory((prev) => [
        ...prev.slice(-9),
        { spaceId, itemId: fromItem.id, title: fromItem.title },
      ]);
    }
    const targetSpace =
      target.space_id ||
      spaces.find((s) => s.kind === "personal")?.id ||
      spaceId;
    if (targetSpace && targetSpace !== spaceId) {
      setPendingFocusId(target.id);
      await handleSwitchSpace(targetSpace);
      setNotice(`已跨空间定位到：${target.title}`);
    } else {
      setActiveTag(null);
      setFilterText("");
      setStatusFilter("all");
      setHighlightedId(target.id);
      setNotice(`已定位知识：${target.title}`);
      window.requestAnimationFrame(() => {
        const card = document.getElementById(`knowledge-card-${target.id}`);
        card?.scrollIntoView?.({ behavior: "smooth", block: "center" });
      });
    }
  }

  async function jumpToItemById(targetId: string, fromItem?: KnowledgeItem) {
    const local = items.find((it) => it.id === targetId);
    if (local) {
      await focusOrJumpToItem(local, fromItem);
      return;
    }
    try {
      const remote = await api.getKnowledge(targetId);
      await focusOrJumpToItem(remote, fromItem);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleGoBack() {
    const last = navHistory[navHistory.length - 1];
    if (!last) return;
    setNavHistory((prev) => prev.slice(0, -1));
    setPendingFocusId(last.itemId);
    if (last.spaceId && last.spaceId !== spaceId) {
      await handleSwitchSpace(last.spaceId);
    }
  }

  // 点击渲染正文中的 [[双链]]：支持当前空间与跨空间自动跳转定位，找不到时预填新建
  async function handleWikilinkClick(targetTitle: string) {
    const normalized = targetTitle.trim().toLowerCase();
    const localMatch = items.find(
      (it) => it.title.trim().toLowerCase() === normalized,
    );
    if (localMatch) {
      setExpandedId(localMatch.id);
      await focusOrJumpToItem(localMatch);
      return;
    }
    try {
      const all = await api.listKnowledge();
      const crossMatch = all.find(
        (it) => it.title.trim().toLowerCase() === normalized,
      );
      if (crossMatch) {
        setExpandedId(crossMatch.id);
        await focusOrJumpToItem(crossMatch);
        return;
      }
    } catch {
      // 回退到预填新建
    }
    setComposerOpen(true);
    setEditingId(null);
    setTitle(targetTitle);
    setNotice(`全库尚无「${targetTitle}」，已为你打开编辑器并预填标题。`);
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
        <div className="flex flex-wrap items-center gap-2">
          <label
            className="text-sm font-medium"
            style={{ color: "var(--nesti-text-secondary)" }}
            htmlFor="space-select"
          >
            当前知识库
          </label>
          <select
            id="space-select"
            value={spaceId}
            onChange={(e) => void handleSwitchSpace(e.target.value)}
            className="rounded-lg border px-3 py-1.5 text-sm outline-none"
            style={fieldStyle}
          >
            {personalSpaces.length > 0 && (
              <optgroup label="我的主知识库">
                {personalSpaces.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}（主库）
                  </option>
                ))}
              </optgroup>
            )}
            {agentSpaces.length > 0 && (
              <optgroup label="AI 助手副库（每个助手独享）">
                {agentSpaces.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name.replace(/^Agent\s*·\s*/i, "")}（AI 助手副库）
                  </option>
                ))}
              </optgroup>
            )}
            {topicSpaces.length > 0 && (
              <optgroup label="我的专题分类（自定义笔记本）">
                {topicSpaces.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}（专题）
                  </option>
                ))}
              </optgroup>
            )}
          </select>

          <button
            type="button"
            onClick={() => setComposerOpen((v) => !v)}
            className="rounded-[9px] px-3.5 py-1.5 text-xs font-semibold text-white transition-opacity hover:opacity-90"
            style={{ background: "var(--nesti-accent)" }}
          >
            {composerOpen || items.length === 0 ? "收起编辑器" : "+ 新建笔记"}
          </button>

          <button
            type="button"
            onClick={() => {
              if (onOpenAgentHub) {
                onOpenAgentHub("manage", currentAgentName);
              } else {
                setLocalAgentHubMode("manage");
                setLocalAgentHubOpen(true);
              }
            }}
            className="rounded-[9px] border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-[var(--nesti-surface-hover)]"
            style={{
              borderColor: "var(--nesti-border-strong)",
              color: "var(--nesti-text-primary)",
            }}
          >
            + AI 助手
          </button>

          <button
            type="button"
            onClick={() => void handleQuickVacuum()}
            disabled={vacuuming}
            title="自动扫描本机 AI 助手未处理的新聊天记录，提炼有价值的知识存进来"
            className="rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-[var(--nesti-surface-hover)] disabled:opacity-45"
            style={{
              borderColor: "var(--nesti-border-strong)",
              color: "var(--nesti-text-primary)",
            }}
          >
            {vacuuming
              ? "自动吸尘中…"
              : currentAgentName
                ? `自动吸尘 ${currentAgentName}`
                : "自动吸尘新对话"}
          </button>

          <button
            type="button"
            onClick={() => {
              if (onOpenAgentHub) {
                onOpenAgentHub("picker", currentAgentName);
              } else {
                setLocalAgentHubMode("picker");
                setLocalAgentHubOpen(true);
              }
            }}
            title="查看全部本地聊天条目，自己勾选想存入知识库的对话"
            className="rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-[var(--nesti-surface-hover)]"
            style={{
              borderColor: "var(--nesti-accent)",
              color: "var(--nesti-accent)",
            }}
          >
            自选对话吸尘
          </button>

          <button
            type="button"
            onClick={() => setFolderModalOpen(true)}
            title="监控本机杂乱文件夹（桌面/下载/资料库），自动收编文档、图片与音视频"
            className="rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-[var(--nesti-surface-hover)]"
            style={{
              borderColor: "var(--nesti-border-strong)",
              color: "var(--nesti-text-primary)",
            }}
          >
            文件夹哨兵
          </button>

          <button
            type="button"
            onClick={() => setClipOpen((v) => !v)}
            title="粘贴文章、文档或 GitHub 链接，自动抓取正文转为干净 Markdown 知识卡片"
            className="rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-[var(--nesti-surface-hover)]"
            style={
              clipOpen
                ? {
                    borderColor: "var(--nesti-accent)",
                    background: "color-mix(in srgb, var(--nesti-accent) 12%, transparent)",
                    color: "var(--nesti-accent)",
                  }
                : {
                    borderColor: "var(--nesti-border-strong)",
                    color: "var(--nesti-text-primary)",
                  }
            }
          >
            网址剪藏
          </button>
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <input
            value={newSpaceName}
            onChange={(e) => setNewSpaceName(e.target.value)}
            placeholder="新专题名称，如：华为云网安"
            aria-label="新项目空间名称"
            className="w-44 rounded-lg border px-3 py-1.5 text-xs outline-none"
            style={fieldStyle}
          />
          <button
            type="button"
            onClick={() => void handleCreateSpace()}
            disabled={!newSpaceName.trim()}
            className="rounded-lg border px-3 py-1.5 text-xs transition-colors hover:bg-[var(--nesti-surface-hover)] disabled:opacity-40"
            style={{
              borderColor: "var(--nesti-border-subtle)",
              color: "var(--nesti-text-secondary)",
            }}
          >
            + 新建专题
          </button>
          <label
            className="cursor-pointer rounded-lg border px-3 py-1.5 text-xs transition-colors hover:bg-[var(--nesti-surface-hover)]"
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
          <div className="relative">
            <button
              type="button"
              disabled={exporting || items.length === 0}
              onClick={() => setExportMenuOpen((v) => !v)}
              className="rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-[var(--nesti-surface-hover)] disabled:opacity-45"
              style={{
                borderColor: "var(--nesti-accent)",
                color: "var(--nesti-accent)",
              }}
            >
              {exporting ? "生成中…" : "一键生成 ▾"}
            </button>
            {exportMenuOpen && (
              <div
                className="absolute right-0 z-30 mt-1.5 w-48 overflow-hidden rounded-xl border p-1 shadow-lg"
                style={{
                  background: "var(--nesti-surface-1)",
                  borderColor: "var(--nesti-border-strong)",
                }}
              >
                {(
                  [
                    ["pdf", "总结报告 PDF (.pdf)"],
                    ["pptx", "汇报演示 PPT (.pptx)"],
                    ["docx", "可编辑 Word (.docx)"],
                    ["card", "高清知识卡片长图 (.png)"],
                  ] as const
                ).map(([fmt, text]) => (
                  <button
                    key={fmt}
                    type="button"
                    onClick={() => void handleGenerateDeliverable(fmt)}
                    className="flex w-full items-center rounded-lg px-3 py-2 text-left text-xs transition-colors hover:bg-[var(--nesti-surface-hover)]"
                    style={{ color: "var(--nesti-text-primary)" }}
                  >
                    {text}
                  </button>
                ))}
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={() => void handleExportZip()}
            className="rounded-lg border px-3 py-1.5 text-xs transition-colors hover:bg-[var(--nesti-surface-hover)]"
            style={{
              borderColor: "var(--nesti-border-subtle)",
              color: "var(--nesti-text-secondary)",
            }}
          >
            导出 ZIP
          </button>
        </div>
      </div>

      {/* 小白向大白话分类说明条 */}
      {currentSpace && (
        <div
          className="flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3.5 py-2 text-xs"
          style={{
            background: "var(--nesti-surface-0)",
            borderColor: "var(--nesti-border-subtle)",
            color: "var(--nesti-text-secondary)",
          }}
        >
          <span>
            {currentSpace.kind === "personal" ? (
              <>
                <strong style={{ color: "var(--nesti-text-primary)" }}>主知识库</strong>
                ：存放你日常自己记录和整理的总笔记。
              </>
            ) : currentAgentName ? (
              <>
                <strong style={{ color: "var(--nesti-accent)" }}>
                  {currentAgentName} 专属副库
                </strong>
                ：专门收纳你和 {currentAgentName} 聊出来的知识；点上方「吸尘 {currentAgentName} 新对话」可自动从本地聊天记录里提炼干货。
              </>
            ) : (
              <>
                <strong style={{ color: "var(--nesti-text-primary)" }}>
                  专题分类 · {currentSpace.name}
                </strong>
                ：你自己建的独立笔记本，用来按项目或学科归类知识。
              </>
            )}
          </span>
          <span style={{ color: "var(--nesti-text-tertiary)" }}>
            共 {items.length} 条知识
          </span>
        </div>
      )}

      {!onOpenAgentHub && (
        <AgentHubModal
          open={localAgentHubOpen}
          initialMode={localAgentHubMode}
          initialAgentName={currentAgentName}
          onClose={() => setLocalAgentHubOpen(false)}
          onChanged={(nextSpaceId) => {
            void (async () => {
              const rows = await api.listSpaces();
              setSpaces(rows);
              onSpacesChanged?.();
              if (nextSpaceId) {
                await handleSwitchSpace(nextSpaceId);
              } else {
                await loadItems(spaceId);
              }
            })();
          }}
        />
      )}
      <FolderWatcherModal
        open={folderModalOpen}
        onClose={() => setFolderModalOpen(false)}
        onChanged={(nextSpaceId) => {
          void (async () => {
            const rows = await api.listSpaces();
            setSpaces(rows);
            onSpacesChanged?.();
            if (nextSpaceId) {
              await handleSwitchSpace(nextSpaceId);
            } else {
              await loadItems(spaceId);
            }
          })();
        }}
      />
      <DocumentReaderModal
        media={readingMedia}
        onClose={() => setReadingMedia(null)}
        onNotice={setNotice}
        onError={setError}
      />
      <ContextMenu menu={cardMenu} onClose={() => setCardMenu(null)} />

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
          className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-600 dark:text-emerald-400"
        >
          <span>{notice}</span>
          {lastSavedPath && (
            <button
              type="button"
              onClick={() => {
                const bridge = (
                  window as unknown as {
                    explainlabDesktop?: { showItemInFolder?: (p: string) => void };
                  }
                ).explainlabDesktop;
                if (bridge?.showItemInFolder) {
                  bridge.showItemInFolder(lastSavedPath);
                } else {
                  void api.revealLocalPath(lastSavedPath);
                }
              }}
              className="shrink-0 rounded-md border border-emerald-500/40 px-2.5 py-1 text-xs font-medium hover:bg-emerald-500/15"
            >
              在资源管理器中定位
            </button>
          )}
        </div>
      )}

      <div
        className={
          composerOpen || items.length === 0 || editingId
            ? "grid gap-6 lg:grid-cols-[380px_1fr]"
            : "space-y-4"
        }
      >
        {/* 左侧：Markdown 富编辑器（有内容时默认收起释放全宽阅读画布，点「+ 新建笔记」或「编辑」即展开） */}
        {(composerOpen || items.length === 0 || editingId) && (
        <section
          className="h-fit space-y-3 rounded-[14px] border p-5"
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
                      ? {
                          background: "var(--nesti-surface-1)",
                          color: "var(--nesti-text-primary)",
                          boxShadow: "var(--nf-shadow-sm)",
                        }
                      : { color: "var(--nesti-text-tertiary)" }
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
                  {
                    label: "表格",
                    run: () =>
                      insertSnippet(
                        "\n| 维度 | 说明 | 备注 |\n| --- | --- | --- |\n| 要点1 | 详细说明 | 核心 |\n",
                      ),
                  },
                  {
                    label: "图文卡片",
                    run: () =>
                      insertSnippet(
                        "\n![模块示意图](请粘贴截图或图片链接)\n**1. 模块名称**\n- 核心功能要点一\n- 核心功能要点二\n> 知识点：关键技术栈说明\n",
                      ),
                  },
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
                <label
                  className="cursor-pointer rounded border px-2 py-0.5 font-medium transition-colors hover:bg-[var(--nesti-surface-hover)]"
                  style={{
                    background: "var(--nesti-surface-0)",
                    borderColor: "var(--nesti-border-subtle)",
                    color: "var(--nesti-accent)",
                  }}
                  title="选择本地图片插入，或直接在下方输入框按 Ctrl+V 粘贴截图"
                >
                  + 插图
                  <input
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) void handleInsertImageFile(f);
                      e.target.value = "";
                    }}
                  />
                </label>
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
                    onPaste={(e) => {
                      const itemsList = e.clipboardData?.items;
                      if (!itemsList) return;
                      for (let idx = 0; idx < itemsList.length; idx += 1) {
                        const clip = itemsList[idx];
                        if (clip.type.startsWith("image/")) {
                          const imgFile = clip.getAsFile();
                          if (imgFile) {
                            e.preventDefault();
                            void handleInsertImageFile(imgFile);
                            return;
                          }
                        }
                      }
                    }}
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
                    placeholder="支持 Markdown、表格、直接 Ctrl+V 粘贴截图、[[双链]] 自动补全、#标签"
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

            {content.trim() && !title.trim() && (
              <p
                className="text-[11px]"
                style={{ color: "var(--nesti-text-tertiary)" }}
              >
                未填标题时，点击「{editingId ? "保存修改" : "创建"}」将自动按正文首行生成标题。
              </p>
            )}

            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => void handleSave()}
                disabled={!content.trim()}
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
        )}

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
              <button
                type="button"
                onClick={() => {
                  setBatchMode((prev) => {
                    if (prev) setSelectedIds([]);
                    return !prev;
                  });
                }}
                className="ml-auto rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-[var(--nesti-surface-hover)]"
                style={
                  batchMode
                    ? {
                        borderColor: "var(--nesti-accent)",
                        background: "color-mix(in srgb, var(--nesti-accent) 12%, transparent)",
                        color: "var(--nesti-accent)",
                      }
                    : {
                        borderColor: "var(--nesti-border-subtle)",
                        color: "var(--nesti-text-secondary)",
                      }
                }
              >
                {batchMode ? "退出批量" : "批量管理"}
              </button>
            </div>
          )}

          {clipOpen && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void handleClipUrl();
              }}
              className="flex flex-wrap items-center gap-2 rounded-xl border p-3 shadow-xs"
              style={{
                background: "var(--nesti-surface-1)",
                borderColor: "var(--nesti-accent)",
              }}
            >
              <span
                className="text-xs font-semibold"
                style={{ color: "var(--nesti-accent)" }}
              >
                网址一键剪藏
              </span>
              <input
                type="url"
                value={clipUrl}
                onChange={(e) => setClipUrl(e.target.value)}
                placeholder="粘贴 https:// 文章、文档或 GitHub 链接，自动抓取正文入库…"
                aria-label="剪藏网页链接"
                className="min-w-60 flex-1 rounded-lg border px-3 py-1.5 text-xs outline-none"
                style={fieldStyle}
              />
              <button
                type="submit"
                disabled={!clipUrl.trim() || clipping}
                className="rounded-lg px-3.5 py-1.5 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-45"
                style={{ background: "var(--nesti-accent)" }}
              >
                {clipping ? "抓取解析中…" : "一键剪藏入库"}
              </button>
              <button
                type="button"
                onClick={() => setClipOpen(false)}
                className="rounded-lg border px-2.5 py-1.5 text-xs"
                style={{
                  borderColor: "var(--nesti-border-subtle)",
                  color: "var(--nesti-text-secondary)",
                }}
              >
                取消
              </button>
            </form>
          )}

          {batchMode && items.length > 0 && (
            <div
              className="flex flex-wrap items-center gap-2 rounded-xl border px-3.5 py-2.5 text-xs"
              style={{
                background: "color-mix(in srgb, var(--nesti-accent) 6%, var(--nesti-surface-1))",
                borderColor: "color-mix(in srgb, var(--nesti-accent) 30%, var(--nesti-border-subtle))",
              }}
            >
              <span className="font-semibold" style={{ color: "var(--nesti-text-primary)" }}>
                已选 {selectedIds.length} / {filteredItems.length} 条
              </span>
              <button
                type="button"
                onClick={handleToggleSelectAll}
                className="rounded-md border px-2.5 py-1 font-medium"
                style={{
                  borderColor: "var(--nesti-border-subtle)",
                  background: "var(--nesti-surface-1)",
                  color: "var(--nesti-text-primary)",
                }}
              >
                {filteredItems.length > 0 &&
                filteredItems.every((it) => selectedIds.includes(it.id))
                  ? "取消全选"
                  : "全选当前"}
              </button>
              <button
                type="button"
                disabled={selectedIds.length === 0 || batchBusy}
                onClick={() => void handleBatchActivate()}
                className="rounded-md px-2.5 py-1 font-medium text-white disabled:opacity-40"
                style={{ background: "var(--nesti-accent)" }}
              >
                批量设为生效
              </button>
              <div className="flex items-center gap-1.5">
                <select
                  value={batchMoveSpaceId}
                  onChange={(e) => setBatchMoveSpaceId(e.target.value)}
                  aria-label="批量移动目标空间"
                  className="rounded-md border px-2 py-1 text-xs outline-none"
                  style={fieldStyle}
                >
                  <option value="">选择目标空间…</option>
                  {spaces.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  disabled={selectedIds.length === 0 || !batchMoveSpaceId || batchBusy}
                  onClick={() => void handleBatchMove()}
                  className="rounded-md border px-2.5 py-1 font-medium disabled:opacity-40"
                  style={{
                    borderColor: "var(--nesti-border-strong)",
                    background: "var(--nesti-surface-1)",
                    color: "var(--nesti-text-primary)",
                  }}
                >
                  批量移动
                </button>
              </div>
              <button
                type="button"
                disabled={selectedIds.length === 0 || batchBusy}
                onClick={() => void handleBatchDelete()}
                className="ml-auto rounded-md border border-red-400/50 px-2.5 py-1 font-medium text-red-500 hover:bg-red-500/10 disabled:opacity-40"
              >
                {batchBusy ? "处理中…" : "批量删除"}
              </button>
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
              const isSelected = batchMode && selectedIds.includes(item.id);
              const itemTags = extractTags(item.content);
              return (
                <article
                  key={item.id}
                  id={`knowledge-card-${item.id}`}
                  onContextMenu={(e) => openItemContextMenu(e, item)}
                  title="右键点击卡片可快速编辑、切换状态、打开沙盒或删除"
                  className="rounded-[14px] border px-5 py-4 transition-all"
                  style={{
                    background: "var(--nesti-surface-1)",
                    borderColor:
                      isHighlighted || isSelected
                        ? "var(--nesti-accent)"
                        : "var(--nesti-border-subtle)",
                    boxShadow:
                      isHighlighted || isSelected
                        ? "0 0 0 3px color-mix(in srgb, var(--nesti-accent) 16%, transparent)"
                        : undefined,
                  }}
                >
                  <div className="mb-3 flex items-start justify-between gap-3">
                    <div className="flex min-w-0 items-start gap-2.5">
                      {batchMode && (
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleSelectItem(item.id)}
                          aria-label={`选择知识 ${item.title}`}
                          className="mt-1 h-4 w-4 shrink-0 cursor-pointer accent-[var(--nesti-accent)]"
                        />
                      )}
                      <div className="min-w-0 space-y-1.5">
                      <h3
                        className="text-[15px] leading-snug font-semibold"
                        style={{ color: "var(--nesti-text-primary)" }}
                      >
                        {item.title}
                      </h3>
                      {itemTags.length > 0 && (
                        <div className="flex flex-wrap gap-x-2.5 gap-y-0.5">
                          {itemTags.map((tag) => (
                            <button
                              key={tag}
                              type="button"
                              onClick={() => setActiveTag(tag)}
                              className="text-[11px] font-medium hover:underline"
                              style={{
                                color: "var(--nesti-text-tertiary)",
                              }}
                            >
                              #{tag}
                            </button>
                          ))}
                        </div>
                      )}
                      </div>
                    </div>
                    <span
                      className="inline-flex shrink-0 items-center gap-1.5 pt-0.5 text-[11px]"
                      style={{ color: "var(--nesti-text-tertiary)" }}
                    >
                      <span
                        className="h-1.5 w-1.5 rounded-full"
                        style={{
                          background:
                            item.status === "active"
                              ? "var(--nf-status-success)"
                              : item.status === "draft"
                                ? "var(--nesti-accent)"
                                : "var(--nesti-text-tertiary)",
                        }}
                      />
                      {STATUS_LABEL[item.status]}
                    </span>
                  </div>

                  {/* Markdown 富文本渲染（含可点击 [[双链]] 与 #标签） */}
                  <MarkdownContent
                    content={item.content}
                    onWikilinkClick={(t) => void handleWikilinkClick(t)}
                    onTagClick={(tag) => setActiveTag(tag)}
                  />

                  {/* 卡片内联文件芯片条：无需展开即可一眼看见该知识包含的 Word/Excel/PPT/PDF/ZIP/音视频/图片 */}
                  {(mediaByItem[item.id]?.length ?? 0) > 0 && (
                    <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                      {mediaByItem[item.id].map((m) => {
                        const badgeColors: Record<string, { bg: string; fg: string; label: string }> = {
                          word: { bg: "rgba(37,99,235,0.14)", fg: "#2563eb", label: "WORD" },
                          excel: { bg: "rgba(5,150,105,0.14)", fg: "#059669", label: "EXCEL" },
                          ppt: { bg: "rgba(234,88,12,0.14)", fg: "#ea580c", label: "PPT" },
                          pdf: { bg: "rgba(220,38,38,0.14)", fg: "#dc2626", label: "PDF" },
                          archive: { bg: "rgba(147,51,234,0.14)", fg: "#9333ea", label: "ZIP" },
                          image: { bg: "rgba(124,58,237,0.14)", fg: "#7c3aed", label: "图片" },
                          audio: { bg: "rgba(8,145,178,0.14)", fg: "#0891b2", label: "音频" },
                          video: { bg: "rgba(2,132,199,0.14)", fg: "#0284c7", label: "视频" },
                        };
                        const bc = {
                          bg: "var(--nesti-surface-2)",
                          fg: "var(--nesti-text-secondary)",
                          label: badgeColors[m.kind]?.label ?? m.kind.toUpperCase(),
                        };
                        return (
                          <button
                            key={m.id}
                            type="button"
                            onClick={() => setReadingMedia(m)}
                            onContextMenu={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              setCardMenu({
                                x: e.clientX,
                                y: e.clientY,
                                items: [
                                  {
                                    id: "read",
                                    label: "原位阅读 / 预览",
                                    onClick: () => setReadingMedia(m),
                                  },
                                  {
                                    id: "reveal",
                                    label: "在资源管理器中打开",
                                    onClick: () => {
                                      void api
                                        .revealItemMedia(item.id, m.id)
                                        .then(() =>
                                          setNotice(`已在资源管理器中定位「${m.filename}」。`),
                                        )
                                        .catch((err) => setError(errorMessage(err)));
                                    },
                                  },
                                  {
                                    id: "download",
                                    label: "下载原文件",
                                    onClick: () => window.open(m.url, "_blank", "noreferrer"),
                                  },
                                ],
                              });
                            }}
                            title="左键原位阅读 · 右键在资源管理器中打开"
                            className="inline-flex max-w-[270px] items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[11px] font-medium"
                            style={{
                              background: "var(--nesti-surface-0)",
                              borderColor: "var(--nesti-border-subtle)",
                              color: "var(--nesti-text-primary)",
                            }}
                          >
                            <span
                              className="shrink-0 rounded px-1.5 py-0.5 text-[9.5px] font-bold"
                              style={{ background: bc.bg, color: bc.fg }}
                            >
                              {bc.label}
                            </span>
                            <span className="truncate">{m.filename}</span>
                          </button>
                        );
                      })}
                    </div>
                  )}

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
                          {s.uri && ` · ${formatDisplayUri(s.uri)}`}
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
                      className="rounded-lg border px-3 py-1 text-xs font-medium transition-colors hover:bg-[var(--nf-status-danger-bg)]"
                      style={{
                        borderColor: "var(--nesti-border-subtle)",
                        color: "var(--nf-status-danger)",
                      }}
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
                    <button
                      type="button"
                      onClick={() =>
                        setSandboxId(sandboxId === item.id ? null : item.id)
                      }
                      aria-expanded={sandboxId === item.id}
                      className="rounded-lg border px-3 py-1 text-xs font-medium transition-colors hover:bg-[var(--nesti-surface-hover)]"
                      style={{
                        borderColor:
                          sandboxId === item.id
                            ? "var(--nesti-accent)"
                            : "var(--nesti-border-subtle)",
                        color:
                          sandboxId === item.id
                            ? "var(--nesti-accent)"
                            : "var(--nesti-text-secondary)",
                      }}
                    >
                      {sandboxId === item.id ? "收起沙盒" : "动态沙盒"}
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        setMediaId(mediaId === item.id ? null : item.id)
                      }
                      aria-expanded={mediaId === item.id}
                      className="rounded-lg border px-3 py-1 text-xs font-medium transition-colors hover:bg-[var(--nesti-surface-hover)]"
                      style={{
                        borderColor:
                          mediaId === item.id
                            ? "var(--nesti-accent)"
                            : "var(--nesti-border-subtle)",
                        color:
                          mediaId === item.id
                            ? "var(--nesti-accent)"
                            : "var(--nesti-text-secondary)",
                      }}
                    >
                      {mediaId === item.id ? "收起附件" : "附件 / 音视频"}
                    </button>
                  </div>

                  {sandboxId === item.id && (
                    <LiveSandboxPanel
                      item={item}
                      onNotice={setNotice}
                      onError={setError}
                    />
                  )}

                  {mediaId === item.id && (
                    <MediaAttachmentsPanel
                      itemId={item.id}
                      onNotice={setNotice}
                      onError={setError}
                      onChanged={() => void loadMediaIndex()}
                    />
                  )}

                  {expandedId === item.id && (
                    <KnowledgeDetail
                      item={item}
                      onNotice={setNotice}
                      onError={setError}
                      onChanged={() => void loadItems(spaceId)}
                      onNavigateItem={(otherId) => void jumpToItemById(otherId, item)}
                    />
                  )}
                </article>
              );
            })
          )}
        </section>
      </div>

      {navHistory.length > 0 && (
        <button
          type="button"
          onClick={() => void handleGoBack()}
          className="fixed right-6 bottom-10 z-30 rounded-full border px-3.5 py-1.5 text-xs font-medium shadow-md backdrop-blur-md transition-opacity hover:opacity-90"
          style={{
            background: "var(--nesti-surface-1)",
            borderColor: "var(--nesti-border-strong)",
            color: "var(--nesti-accent)",
          }}
        >
          ← 返回上一条（{navHistory[navHistory.length - 1].title.slice(0, 14)}）
        </button>
      )}
    </div>
  );
}
