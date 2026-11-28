import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { MediaItem } from "../api/types";
import { ContextMenu, type ContextMenuState } from "./ContextMenu";
import { DocumentReaderModal } from "./DocumentReaderModal";

interface Props {
  itemId: string;
  onNotice: (msg: string) => void;
  onError: (msg: string) => void;
  onChanged?: () => void;
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

/**
 * 知识条目多模态媒体附件面板：
 * 支持拖拽/点击上传图片、音频、视频、PDF 与通用文件；
 * 卡片内直接原位看图（点击灯箱放大）、听音频、播视频（Range 流式拖动进度条）与下载文档。
 */
export function MediaAttachmentsPanel({ itemId, onNotice, onError, onChanged }: Props) {
  const [items, setItems] = useState<MediaItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [reading, setReading] = useState<MediaItem | null>(null);
  const [ctxMenu, setCtxMenu] = useState<ContextMenuState | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await api.listItemMedia(itemId));
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [itemId, onError]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleFiles(fileList: FileList | File[]) {
    const files = Array.from(fileList);
    if (files.length === 0) return;
    setUploading(true);
    try {
      for (const f of files) {
        await api.uploadItemMedia(itemId, f);
      }
      await load();
      onChanged?.();
      onNotice(`已上传 ${files.length} 个多模态附件。`);
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    } finally {
      setUploading(false);
    }
  }

  async function handleReveal(m: MediaItem) {
    try {
      await api.revealItemMedia(itemId, m.id);
      onNotice(`已在资源管理器中定位「${m.filename}」。`);
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleDelete(m: MediaItem) {
    if (!window.confirm(`确认删除附件「${m.filename}」？`)) return;
    try {
      await api.deleteItemMedia(itemId, m.id);
      setItems((prev) => prev.filter((x) => x.id !== m.id));
      onChanged?.();
      onNotice(`已删除附件「${m.filename}」。`);
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    }
  }

  function openMediaMenu(e: React.MouseEvent, m: MediaItem) {
    e.preventDefault();
    setCtxMenu({
      x: e.clientX,
      y: e.clientY,
      items: [
        { id: "read", label: "原位阅读 / 预览", onClick: () => setReading(m) },
        { id: "reveal", label: "在资源管理器中打开", onClick: () => void handleReveal(m) },
        {
          id: "download",
          label: "下载原文件",
          onClick: () => window.open(m.url, "_blank", "noreferrer"),
        },
        {
          id: "delete",
          label: "删除该附件",
          danger: true,
          dividerBefore: true,
          onClick: () => void handleDelete(m),
        },
      ],
    });
  }

  const images = items.filter((m) => m.kind === "image");
  const others = items.filter((m) => m.kind !== "image");

  return (
    <div
      className="mt-3 space-y-3 rounded-xl border p-3"
      style={{
        background: "var(--nesti-surface-0)",
        borderColor: dragOver ? "var(--nesti-accent)" : "var(--nesti-border-strong)",
      }}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        if (e.dataTransfer.files?.length) {
          void handleFiles(e.dataTransfer.files);
        }
      }}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span
            className="rounded-full px-2 py-0.5 text-[11px] font-semibold"
            style={{
              background: "color-mix(in srgb, var(--nesti-accent) 14%, transparent)",
              color: "var(--nesti-accent)",
            }}
          >
            多模态附件库
          </span>
          <span className="text-xs" style={{ color: "var(--nesti-text-tertiary)" }}>
            支持拖拽或上传 Word / Excel / PPT / PDF / 图片 / 音视频，原位阅读与右键定位
          </span>
        </div>

        <label
          className="cursor-pointer rounded-lg px-3 py-1 text-xs font-medium text-white transition-opacity hover:opacity-90"
          style={{ background: "var(--nesti-accent)" }}
        >
          {uploading ? "上传中…" : "+ 上传文档 / 图片 / 音视频"}
          <input
            type="file"
            multiple
            accept="image/*,audio/*,video/*,.pdf,.doc,.docx,.xls,.xlsx,.csv,.ppt,.pptx,.txt,.md,.zip"
            className="hidden"
            disabled={uploading}
            onChange={(e) => {
              if (e.target.files?.length) void handleFiles(e.target.files);
              e.target.value = "";
            }}
          />
        </label>
      </div>

      {loading ? (
        <p className="py-3 text-center text-xs" style={{ color: "var(--nesti-text-tertiary)" }}>
          正在读取附件列表…
        </p>
      ) : items.length === 0 ? (
        <div
          className="rounded-lg border border-dashed py-5 text-center text-xs"
          style={{
            borderColor: "var(--nesti-border-strong)",
            color: "var(--nesti-text-tertiary)",
          }}
        >
          把图片、录音（MP3/WAV）、视频（MP4/WebM）或 PDF 直接拖到这里，即可和这条知识绑定保存。
        </div>
      ) : (
        <div className="space-y-3">
          {images.length > 0 && (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {images.map((img) => (
                <div
                  key={img.id}
                  onContextMenu={(e) => openMediaMenu(e, img)}
                  className="group relative overflow-hidden rounded-lg border"
                  style={{
                    background: "var(--nesti-surface-1)",
                    borderColor: "var(--nesti-border-subtle)",
                  }}
                >
                  <img
                    src={img.url}
                    alt={img.filename}
                    loading="lazy"
                    onClick={() => setReading(img)}
                    className="h-28 w-full cursor-zoom-in object-cover transition-transform group-hover:scale-[1.03]"
                  />
                  <div className="flex items-center justify-between gap-1 px-2 py-1 text-[11px]">
                    <span className="truncate" title={img.filename}>
                      {img.filename}
                    </span>
                    <button
                      type="button"
                      onClick={() => void handleDelete(img)}
                      className="shrink-0 text-red-500 hover:underline"
                    >
                      删
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {others.map((m) => (
            <div
              key={m.id}
              onContextMenu={(e) => openMediaMenu(e, m)}
              className="space-y-2 rounded-lg border p-2.5"
              style={{
                background: "var(--nesti-surface-1)",
                borderColor: "var(--nesti-border-subtle)",
              }}
            >
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <div className="flex min-w-0 items-center gap-2">
                  <span
                    className="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase"
                    style={{
                      background: "var(--nesti-surface-2)",
                      color: "var(--nesti-accent)",
                    }}
                  >
                    {m.kind}
                  </span>
                  <button
                    type="button"
                    onClick={() => setReading(m)}
                    className="truncate text-left font-medium hover:underline"
                    title={m.filename}
                  >
                    {m.filename}
                  </button>
                  <span className="shrink-0 text-[11px] opacity-60">{fmtSize(m.size_bytes)}</span>
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => setReading(m)}
                    className="rounded-md px-2 py-0.5 text-[11px] font-medium text-white"
                    style={{ background: "var(--nesti-accent)" }}
                  >
                    原位阅读
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleReveal(m)}
                    className="rounded-md border px-2 py-0.5 text-[11px]"
                    style={{ borderColor: "var(--nesti-border-subtle)" }}
                  >
                    资源管理器打开
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleDelete(m)}
                    className="text-[11px] text-red-500 hover:underline"
                  >
                    删除
                  </button>
                </div>
              </div>

              {m.kind === "audio" && (
                <audio controls preload="metadata" src={m.url} className="h-9 w-full" />
              )}
              {m.kind === "video" && (
                <video
                  controls
                  preload="metadata"
                  src={m.url}
                  className="max-h-72 w-full rounded-lg bg-black"
                />
              )}
            </div>
          ))}
        </div>
      )}

      <DocumentReaderModal
        media={reading}
        onClose={() => setReading(null)}
        onNotice={onNotice}
        onError={onError}
      />
      <ContextMenu menu={ctxMenu} onClose={() => setCtxMenu(null)} />
    </div>
  );
}
