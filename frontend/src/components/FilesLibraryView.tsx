import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { LibraryMediaItem } from "../api/types";
import { ContextMenu, type ContextMenuState } from "./ContextMenu";
import { DocumentReaderModal } from "./DocumentReaderModal";

interface Props {
  onJumpToSpace?: (spaceId: string) => void;
}

const FILTERS = [
  { id: "all", label: "全部文件" },
  { id: "word", label: "Word" },
  { id: "excel", label: "Excel / CSV" },
  { id: "ppt", label: "PPT" },
  { id: "pdf", label: "PDF" },
  { id: "archive", label: "ZIP 压缩包" },
  { id: "markdown", label: "Markdown" },
  { id: "html", label: "HTML 网页" },
  { id: "code", label: "代码 / JSON" },
  { id: "image", label: "图片" },
  { id: "audio", label: "音频" },
  { id: "video", label: "视频" },
] as const;

const KIND_LABEL: Record<string, string> = {
  word: "WORD",
  excel: "EXCEL",
  ppt: "PPT",
  pdf: "PDF",
  archive: "ZIP",
  markdown: "MD",
  html: "HTML",
  code: "CODE",
  image: "图片",
  audio: "音频",
  video: "视频",
  file: "文件",
};

function safeDecodeLabel(text: string): string {
  try {
    return decodeURIComponent(text);
  } catch {
    return text;
  }
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

/**
 * 独立「文件资产库」视图：
 * 集中按类型管理全库所有 Word / Excel / PPT / PDF / 图片 / 音视频，
 * 不脱离它们原本所属的知识条目与主库，支持一键原位阅读、跳转所属知识与右键资源管理器打开。
 */
export function FilesLibraryView({ onJumpToSpace }: Props) {
  const [files, setFiles] = useState<LibraryMediaItem[]>([]);
  const [kindFilter, setKindFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reading, setReading] = useState<LibraryMediaItem | null>(null);
  const [ctxMenu, setCtxMenu] = useState<ContextMenuState | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setFiles(await api.listMediaLibrary());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const totalBytes = useMemo(
    () => files.reduce((sum, f) => sum + (f.size_bytes || 0), 0),
    [files],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return files.filter((f) => {
      if (kindFilter !== "all" && f.kind !== kindFilter) return false;
      if (
        q &&
        !f.filename.toLowerCase().includes(q) &&
        !f.item_title.toLowerCase().includes(q) &&
        !(f.space_name ?? "").toLowerCase().includes(q)
      ) {
        return false;
      }
      return true;
    });
  }, [files, kindFilter, query]);

  async function handleReveal(f: LibraryMediaItem) {
    try {
      await api.revealItemMedia(f.item_id, f.id);
      setNotice(`已在资源管理器中定位「${f.filename}」。`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleDelete(f: LibraryMediaItem) {
    if (!window.confirm(`确认删除附件「${f.filename}」？（所属知识卡片正文不受影响）`)) return;
    try {
      await api.deleteItemMedia(f.item_id, f.id);
      setFiles((prev) => prev.filter((x) => !(x.id === f.id && x.item_id === f.item_id)));
      setNotice(`已删除「${f.filename}」。`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  function openMenu(e: React.MouseEvent, f: LibraryMediaItem) {
    e.preventDefault();
    setCtxMenu({
      x: e.clientX,
      y: e.clientY,
      items: [
        { id: "read", label: "原位阅读 / 预览", onClick: () => setReading(f) },
        {
          id: "reveal",
          label: "在资源管理器中打开",
          onClick: () => void handleReveal(f),
        },
        ...(f.space_id && onJumpToSpace
          ? [
              {
                id: "jump",
                label: `定位到所属库（${f.space_name || "知识库"}）`,
                dividerBefore: true,
                onClick: () => onJumpToSpace(f.space_id!),
              },
            ]
          : []),
        {
          id: "download",
          label: "下载原文件",
          onClick: () => window.open(f.url, "_blank", "noreferrer"),
        },
        {
          id: "delete",
          label: "删除该附件",
          danger: true,
          dividerBefore: true,
          onClick: () => void handleDelete(f),
        },
      ],
    });
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <div
        className="flex flex-wrap items-end justify-between gap-4 border-b pb-5"
        style={{ borderColor: "var(--nesti-border-subtle)" }}
      >
        <div className="space-y-1">
          <div className="nf-eyebrow">
            <span className="nf-eyebrow-index">04</span>
            <span>FILE ARCHIVE · 本地文档集中阅览</span>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-xl font-semibold" style={{ color: "var(--nesti-text-primary)" }}>
              本地文件库
            </h2>
            {!loading && (
              <span
                className="font-mono text-xs tabular-nums"
                style={{ color: "var(--nesti-text-tertiary)" }}
              >
                {files.length} 个文件 · {fmtSize(totalBytes)}
              </span>
            )}
          </div>
          <p className="text-xs" style={{ color: "var(--nesti-text-tertiary)" }}>
            聚合全库所有挂载的 Word / Excel / PPT / PDF / ZIP 与音视频，左键原位阅读，右键在资源管理器中定位。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索文件名、所属知识或空间…"
            className="w-60 rounded-lg border px-3 py-1.5 text-xs outline-none"
            style={{
              background: "var(--nesti-surface-0)",
              borderColor: "var(--nesti-border-subtle)",
              color: "var(--nesti-text-primary)",
            }}
          />
          <button
            type="button"
            onClick={() => void load()}
            className="rounded-lg border px-3 py-1.5 text-xs"
            style={{
              borderColor: "var(--nesti-border-subtle)",
              color: "var(--nesti-text-secondary)",
            }}
          >
            刷新
          </button>
        </div>
      </div>

      {/* 类型筛选药丸 */}
      <div className="flex flex-wrap items-center gap-1.5">
        {FILTERS.map((fl) => {
          const active = kindFilter === fl.id;
          const cnt =
            fl.id === "all" ? files.length : files.filter((x) => x.kind === fl.id).length;
          return (
            <button
              key={fl.id}
              type="button"
              onClick={() => setKindFilter(fl.id)}
              className="rounded-full border px-3 py-1 text-xs font-medium"
              style={
                active
                  ? {
                      background: "var(--nesti-accent)",
                      borderColor: "var(--nesti-accent)",
                      color: "#ffffff",
                    }
                  : {
                      background: "var(--nesti-surface-1)",
                      borderColor: "var(--nesti-border-subtle)",
                      color: "var(--nesti-text-secondary)",
                    }
              }
            >
              {fl.label} <span className="opacity-75">({cnt})</span>
            </button>
          );
        })}
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-500">
          {error}
        </div>
      )}
      {notice && (
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-700 dark:text-emerald-400">
          {notice}
        </div>
      )}

      {loading ? (
        <p className="py-12 text-center text-xs opacity-65">正在加载全库文件…</p>
      ) : filtered.length === 0 ? (
        <div
          className="rounded-xl border border-dashed py-12 text-center text-xs opacity-70"
          style={{ borderColor: "var(--nesti-border-strong)" }}
        >
          当前分类下暂无文件。你可以在任意知识卡片下点「附件 / 音视频」上传 Word / Excel / PPT / PDF，或用「文件夹哨兵」批量收编！
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((f) => {
            const badgeLabel = KIND_LABEL[f.kind] ?? KIND_LABEL.file;
            const displayTitle = safeDecodeLabel(f.item_title);
            const displayFilename = safeDecodeLabel(f.filename);
            return (
              <article
                key={`${f.item_id}-${f.id}`}
                onContextMenu={(e) => openMenu(e, f)}
                className="flex min-w-0 flex-col justify-between gap-2.5 overflow-hidden rounded-xl border p-3.5 shadow-xs"
                style={{
                  background: "var(--nesti-surface-1)",
                  borderColor: "var(--nesti-border-subtle)",
                }}
              >
                <div className="min-w-0 space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <span
                      className="rounded border px-2 py-0.5 font-mono text-[10px] font-semibold tracking-wider"
                      style={{
                        background: "var(--nesti-surface-2)",
                        borderColor: "var(--nesti-border-subtle)",
                        color: "var(--nesti-accent)",
                      }}
                    >
                      {badgeLabel}
                    </span>
                    <span
                      className="font-mono text-[10px]"
                      style={{ color: "var(--nesti-text-tertiary)" }}
                    >
                      {fmtSize(f.size_bytes)}
                    </span>
                  </div>

                  {f.kind === "image" && (
                    <img
                      src={f.url}
                      alt={displayFilename}
                      loading="lazy"
                      onClick={() => setReading(f)}
                      className="h-28 w-full cursor-zoom-in rounded-lg border object-cover"
                      style={{ borderColor: "var(--nesti-border-subtle)" }}
                    />
                  )}

                  <button
                    type="button"
                    onClick={() => setReading(f)}
                    className="block w-full truncate text-left text-sm font-semibold hover:underline"
                    style={{ color: "var(--nesti-text-primary)" }}
                    title={displayFilename}
                  >
                    {displayFilename}
                  </button>

                  <div
                    className="line-clamp-2 break-all text-[11px]"
                    style={{ color: "var(--nesti-text-secondary)" }}
                  >
                    所属知识：
                    <button
                      type="button"
                      onClick={() => {
                        if (f.space_id) onJumpToSpace?.(f.space_id);
                      }}
                      className="underline decoration-dotted hover:opacity-100"
                      style={{ color: "var(--nesti-accent)" }}
                    >
                      {displayTitle}
                    </button>
                    {f.space_name && (
                      <span className="ml-1 opacity-75">（{f.space_name}）</span>
                    )}
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-1.5 pt-1">
                  <button
                    type="button"
                    onClick={() => setReading(f)}
                    className="rounded-lg px-2.5 py-1 text-xs font-medium text-white"
                    style={{ background: "var(--nesti-accent)" }}
                  >
                    原位阅读
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleReveal(f)}
                    className="rounded-lg border px-2.5 py-1 text-xs"
                    style={{
                      borderColor: "var(--nesti-border-subtle)",
                      color: "var(--nesti-text-secondary)",
                    }}
                  >
                    资源管理器打开
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}

      <DocumentReaderModal
        media={reading}
        onClose={() => setReading(null)}
        onNotice={setNotice}
        onError={setError}
      />
      <ContextMenu menu={ctxMenu} onClose={() => setCtxMenu(null)} />
    </div>
  );
}
