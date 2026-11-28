import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { DocPreviewResponse, MediaItem } from "../api/types";
import { MarkdownContent } from "./MarkdownContent";

interface Props {
  media: MediaItem | null;
  onClose: () => void;
  onNotice?: (msg: string) => void;
  onError?: (msg: string) => void;
}

const KIND_BADGE: Record<string, { label: string; color: string }> = {
  word: { label: "Word 文档", color: "#2563eb" },
  excel: { label: "Excel 表格", color: "#059669" },
  ppt: { label: "PPT 幻灯片", color: "#ea580c" },
  pdf: { label: "PDF 文档", color: "#dc2626" },
  archive: { label: "ZIP 压缩包", color: "#9333ea" },
  markdown: { label: "Markdown", color: "#0f766e" },
  html: { label: "HTML 网页", color: "#e11d48" },
  code: { label: "代码 / 配置", color: "#334155" },
  image: { label: "图片", color: "#7c3aed" },
  audio: { label: "音频", color: "#0891b2" },
  video: { label: "视频", color: "#0284c7" },
  file: { label: "文档", color: "#475569" },
};

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

/**
 * ExplainLab 内置多格式通用文档阅读器：
 * 支持 PDF 原生内嵌阅读、Word 富文档（标题/表格/内嵌图）、Excel 多 Sheet 表格搜索、
 * PPT 16:9 幻灯片键盘翻页与备注、以及图片/音视频原位播放。
 */
export function DocumentReaderModal({ media, onClose, onNotice, onError }: Props) {
  const [preview, setPreview] = useState<DocPreviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [sheetIdx, setSheetIdx] = useState(0);
  const [sheetFilter, setSheetFilter] = useState("");
  const [zipFilter, setZipFilter] = useState("");
  const [showRawSource, setShowRawSource] = useState(false);
  const [slideIdx, setSlideIdx] = useState(0);

  useEffect(() => {
    if (!media) return;
    setPreview(null);
    setSheetIdx(0);
    setSheetFilter("");
    setZipFilter("");
    setShowRawSource(false);
    setSlideIdx(0);
    setLoading(true);
    void (async () => {
      try {
        const res = await api.previewItemMedia(media.item_id, media.id);
        setPreview(res);
      } catch (err) {
        onError?.(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    })();
  }, [media, onError]);

  useEffect(() => {
    if (!media) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      } else if (preview?.kind === "ppt" && preview.slides && preview.slides.length > 0) {
        if (e.key === "ArrowRight" || e.key === "PageDown") {
          setSlideIdx((i) => Math.min(preview.slides!.length - 1, i + 1));
        } else if (e.key === "ArrowLeft" || e.key === "PageUp") {
          setSlideIdx((i) => Math.max(0, i - 1));
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [media, preview, onClose]);

  const activeSheet = preview?.sheets?.[sheetIdx] ?? null;
  const filteredSheetRows = useMemo(() => {
    if (!activeSheet) return [];
    const q = sheetFilter.trim().toLowerCase();
    if (!q) return activeSheet.rows;
    const [head, ...rest] = activeSheet.rows;
    const matched = rest.filter((r) => r.some((c) => c.toLowerCase().includes(q)));
    return head ? [head, ...matched] : matched;
  }, [activeSheet, sheetFilter]);

  if (!media) return null;

  const badge = KIND_BADGE[media.kind] ?? KIND_BADGE.file;
  const activeSlide = preview?.slides?.[slideIdx] ?? null;

  async function handleReveal() {
    if (!media) return;
    try {
      await api.revealItemMedia(media.item_id, media.id);
      onNotice?.("已在系统资源管理器中定位该文件。");
    } catch (err) {
      onError?.(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`文档阅读器 - ${media.filename}`}
      className="fixed inset-0 z-[75] flex items-center justify-center bg-black/55 p-3 backdrop-blur-xs"
      onClick={onClose}
    >
      <div
        className={`flex flex-col overflow-hidden rounded-2xl border shadow-2xl ${
          fullscreen ? "h-[96vh] w-[96vw]" : "h-[86vh] w-full max-w-5xl"
        }`}
        style={{
          background: "var(--nesti-surface-1, #ffffff)",
          borderColor: "var(--nesti-border-strong, #cbd5e1)",
          color: "var(--nesti-text-primary, #0f172a)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* 顶部阅读器工具栏 */}
        <div
          className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2.5"
          style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
        >
          <div className="flex min-w-0 items-center gap-2">
            <span
              className="shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-semibold text-white"
              style={{ background: badge.color }}
            >
              {badge.label}
            </span>
            <h2 className="truncate text-sm font-semibold" title={media.filename}>
              {media.filename}
            </h2>
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={() => void handleReveal()}
              className="rounded-lg border px-2.5 py-1 text-xs"
              style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
            >
              在资源管理器中打开
            </button>
            <a
              href={media.url}
              target="_blank"
              rel="noreferrer"
              className="rounded-lg border px-2.5 py-1 text-xs"
              style={{
                borderColor: "var(--nesti-border-subtle, #e2e8f0)",
                color: "var(--nesti-accent, #2463eb)",
              }}
            >
              下载原文件
            </a>
            <button
              type="button"
              onClick={() => setFullscreen((v) => !v)}
              className="rounded-lg border px-2.5 py-1 text-xs"
              style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
            >
              {fullscreen ? "退出全屏" : "全屏阅读"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border px-2.5 py-1 text-xs"
              style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
            >
              关闭
            </button>
          </div>
        </div>

        {/* 主体阅读舞台 */}
        <div
          className="min-h-0 flex-1 overflow-y-auto p-4"
          style={{ background: "var(--nesti-surface-0, #f8fafc)" }}
        >
          {loading ? (
            <p className="py-16 text-center text-sm opacity-70">正在解析文档内容…</p>
          ) : !preview ? (
            <p className="py-16 text-center text-sm opacity-70">无法加载预览内容。</p>
          ) : preview.warning ? (
            <div className="mx-auto max-w-xl rounded-xl border border-amber-500/30 bg-amber-500/10 p-5 text-sm text-amber-700 dark:text-amber-300">
              {preview.warning}
            </div>
          ) : preview.kind === "pdf" ? (
            <iframe
              title={media.filename}
              src={preview.stream_url || media.url}
              className="h-full min-h-[70vh] w-full rounded-xl border bg-white"
              style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
            />
          ) : preview.kind === "word" ? (
            <div
              className="mx-auto max-w-3xl space-y-3 rounded-2xl border p-6 shadow-xs"
              style={{
                background: "var(--nesti-surface-1, #ffffff)",
                borderColor: "var(--nesti-border-subtle, #e2e8f0)",
              }}
            >
              {(preview.blocks ?? []).length === 0 ? (
                <p className="py-8 text-center text-xs opacity-65">文档正文为空。</p>
              ) : (
                (preview.blocks ?? []).map((blk, i) => {
                  if (blk.type === "heading") {
                    const cls =
                      blk.level === 1
                        ? "text-xl font-bold pt-2"
                        : blk.level === 2
                          ? "text-base font-semibold pt-2"
                          : "text-sm font-semibold pt-1";
                    return (
                      <div key={i} className={cls}>
                        {blk.text}
                      </div>
                    );
                  }
                  if (blk.type === "image" && blk.src) {
                    return (
                      <img
                        key={i}
                        src={blk.src}
                        alt="文档插图"
                        className="my-2 max-h-96 rounded-xl border object-contain"
                        style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
                      />
                    );
                  }
                  if (blk.type === "table" && blk.rows && blk.rows.length > 0) {
                    const [head, ...body] = blk.rows;
                    return (
                      <div
                        key={i}
                        className="my-3 overflow-x-auto rounded-lg border"
                        style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
                      >
                        <table className="w-full border-collapse text-left text-xs">
                          <thead>
                            <tr style={{ background: "var(--nesti-surface-2, #f1f5f9)" }}>
                              {head.map((c, ci) => (
                                <th
                                  key={ci}
                                  className="border-b px-3 py-2 font-semibold"
                                  style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
                                >
                                  {c}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {body.map((r, ri) => (
                              <tr
                                key={ri}
                                className="border-b last:border-b-0"
                                style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
                              >
                                {r.map((c, ci) => (
                                  <td key={ci} className="px-3 py-1.5">
                                    {c}
                                  </td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    );
                  }
                  return (
                    <p key={i} className="text-sm leading-relaxed opacity-90">
                      {blk.text}
                    </p>
                  );
                })
              )}
            </div>
          ) : preview.kind === "excel" ? (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-1.5">
                  {(preview.sheets ?? []).map((sh, idx) => (
                    <button
                      key={sh.name + idx}
                      type="button"
                      onClick={() => {
                        setSheetIdx(idx);
                        setSheetFilter("");
                      }}
                      className="rounded-lg border px-3 py-1 text-xs font-medium"
                      style={
                        sheetIdx === idx
                          ? {
                              background: "var(--nesti-accent, #2463eb)",
                              borderColor: "var(--nesti-accent, #2463eb)",
                              color: "#ffffff",
                            }
                          : {
                              background: "var(--nesti-surface-1, #ffffff)",
                              borderColor: "var(--nesti-border-subtle, #e2e8f0)",
                            }
                      }
                    >
                      {sh.name} ({sh.total_rows}行)
                    </button>
                  ))}
                </div>
                <input
                  value={sheetFilter}
                  onChange={(e) => setSheetFilter(e.target.value)}
                  placeholder="在当前表格中筛选关键词…"
                  className="w-56 rounded-lg border px-2.5 py-1 text-xs outline-none"
                  style={{
                    background: "var(--nesti-surface-1, #ffffff)",
                    borderColor: "var(--nesti-border-subtle, #e2e8f0)",
                  }}
                />
              </div>

              {activeSheet && filteredSheetRows.length > 0 ? (
                <div
                  className="max-h-[66vh] overflow-auto rounded-xl border"
                  style={{
                    background: "var(--nesti-surface-1, #ffffff)",
                    borderColor: "var(--nesti-border-subtle, #e2e8f0)",
                  }}
                >
                  <table className="w-full border-collapse text-left text-xs">
                    <thead className="sticky top-0 z-10">
                      <tr style={{ background: "var(--nesti-surface-2, #f1f5f9)" }}>
                        <th
                          className="border-b border-r px-2 py-2 text-center font-mono text-[10px] opacity-60"
                          style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
                        >
                          #
                        </th>
                        {filteredSheetRows[0].map((cell, ci) => (
                          <th
                            key={ci}
                            className="border-b border-r px-3 py-2 font-semibold last:border-r-0"
                            style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
                          >
                            {cell || `列 ${ci + 1}`}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {filteredSheetRows.slice(1).map((row, ri) => (
                        <tr
                          key={ri}
                          className="border-b last:border-b-0 hover:bg-[var(--nesti-surface-hover,rgba(148,163,184,0.1))]"
                          style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
                        >
                          <td
                            className="border-r px-2 py-1.5 text-center font-mono text-[10px] opacity-55"
                            style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
                          >
                            {ri + 1}
                          </td>
                          {row.map((cell, ci) => (
                            <td
                              key={ci}
                              className="border-r px-3 py-1.5 last:border-r-0"
                              style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
                            >
                              {cell}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="py-12 text-center text-xs opacity-65">当前表格没有匹配数据。</p>
              )}
              {activeSheet?.truncated && (
                <p className="text-[11px] opacity-65">
                  注：大表格仅预览前 400 行（共 {activeSheet.total_rows} 行），完整数据请点右上角「在资源管理器中打开」。
                </p>
              )}
            </div>
          ) : preview.kind === "ppt" ? (
            <div className="mx-auto max-w-4xl space-y-3">
              {activeSlide ? (
                <>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium opacity-75">
                      第 {activeSlide.index} / {preview.slides?.length ?? 0} 页（支持键盘 ← / → 翻页）
                    </span>
                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        disabled={slideIdx <= 0}
                        onClick={() => setSlideIdx((i) => Math.max(0, i - 1))}
                        className="rounded-lg border px-3 py-1 text-xs disabled:opacity-40"
                        style={{
                          background: "var(--nesti-surface-1, #ffffff)",
                          borderColor: "var(--nesti-border-subtle, #e2e8f0)",
                        }}
                      >
                        ← 上一页
                      </button>
                      <button
                        type="button"
                        disabled={slideIdx >= (preview.slides?.length ?? 1) - 1}
                        onClick={() =>
                          setSlideIdx((i) =>
                            Math.min((preview.slides?.length ?? 1) - 1, i + 1),
                          )
                        }
                        className="rounded-lg px-3 py-1 text-xs font-medium text-white disabled:opacity-40"
                        style={{ background: "var(--nesti-accent, #2463eb)" }}
                      >
                        下一页 →
                      </button>
                    </div>
                  </div>

                  {/* 16:9 幻灯片演示舞台 */}
                  <div
                    className="flex min-h-[420px] flex-col justify-between rounded-2xl border p-7 shadow-sm"
                    style={{
                      background: "var(--nesti-surface-1, #ffffff)",
                      borderColor: "var(--nesti-border-strong, #cbd5e1)",
                    }}
                  >
                    <div className="space-y-4">
                      <h3
                        className="border-b pb-3 text-xl font-bold"
                        style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
                      >
                        {activeSlide.title}
                      </h3>

                      {activeSlide.bullets.length > 0 && (
                        <ul className="list-disc space-y-2 pl-5 text-sm leading-relaxed">
                          {activeSlide.bullets.map((b, bi) => (
                            <li key={bi}>{b}</li>
                          ))}
                        </ul>
                      )}

                      {activeSlide.tables.map((tbl, ti) => (
                        <div
                          key={ti}
                          className="overflow-x-auto rounded-lg border"
                          style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
                        >
                          <table className="w-full border-collapse text-left text-xs">
                            <tbody>
                              {tbl.map((r, ri) => (
                                <tr
                                  key={ri}
                                  className="border-b last:border-b-0"
                                  style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
                                >
                                  {r.map((c, ci) => (
                                    <td
                                      key={ci}
                                      className={`px-2.5 py-1.5 ${ri === 0 ? "font-semibold" : ""}`}
                                    >
                                      {c}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ))}

                      {activeSlide.images.length > 0 && (
                        <div className="grid grid-cols-2 gap-3 pt-2">
                          {activeSlide.images.map((src, ii) => (
                            <img
                              key={ii}
                              src={src}
                              alt={`幻灯片插图 ${ii + 1}`}
                              className="max-h-56 w-full rounded-xl border object-contain"
                              style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
                            />
                          ))}
                        </div>
                      )}
                    </div>

                    {activeSlide.notes && (
                      <div
                        className="mt-5 rounded-xl border p-3 text-xs opacity-80"
                        style={{
                          background: "var(--nesti-surface-0, #f8fafc)",
                          borderColor: "var(--nesti-border-subtle, #e2e8f0)",
                        }}
                      >
                        <strong>演讲者备注：</strong>
                        {activeSlide.notes}
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <p className="py-12 text-center text-xs opacity-65">未解析到幻灯片页面。</p>
              )}
            </div>
          ) : preview.kind === "archive" ? (
            <div className="mx-auto max-w-4xl space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <span className="opacity-75">
                  共 {preview.total_entries ?? 0} 个条目 · 解压后约{" "}
                  {fmtBytes(preview.total_size_bytes ?? 0)}
                </span>
                <input
                  value={zipFilter}
                  onChange={(e) => setZipFilter(e.target.value)}
                  placeholder="筛选压缩包内文件名…"
                  className="w-56 rounded-lg border px-2.5 py-1 text-xs outline-none"
                  style={{
                    background: "var(--nesti-surface-1, #ffffff)",
                    borderColor: "var(--nesti-border-subtle, #e2e8f0)",
                  }}
                />
              </div>
              <div
                className="max-h-[66vh] overflow-auto rounded-xl border"
                style={{
                  background: "var(--nesti-surface-1, #ffffff)",
                  borderColor: "var(--nesti-border-subtle, #e2e8f0)",
                }}
              >
                <table className="w-full border-collapse text-left text-xs">
                  <thead className="sticky top-0">
                    <tr style={{ background: "var(--nesti-surface-2, #f1f5f9)" }}>
                      <th className="border-b px-3 py-2 font-semibold" style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}>
                        压缩包内路径
                      </th>
                      <th className="border-b px-3 py-2 text-right font-semibold" style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}>
                        原始大小
                      </th>
                      <th className="border-b px-3 py-2 text-right font-semibold" style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}>
                        压缩后
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {(preview.entries ?? [])
                      .filter(
                        (en) =>
                          !zipFilter.trim() ||
                          en.name.toLowerCase().includes(zipFilter.trim().toLowerCase()),
                      )
                      .map((en, idx) => (
                        <tr
                          key={en.name + idx}
                          className="border-b last:border-b-0"
                          style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
                        >
                          <td className="px-3 py-1.5 font-mono text-[11px]">
                            {en.is_dir ? "📁 " : "📄 "}
                            {en.name}
                          </td>
                          <td className="px-3 py-1.5 text-right font-mono text-[11px] opacity-70">
                            {en.is_dir ? "—" : fmtBytes(en.size_bytes)}
                          </td>
                          <td className="px-3 py-1.5 text-right font-mono text-[11px] opacity-70">
                            {en.is_dir ? "—" : fmtBytes(en.compressed_bytes)}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : preview.kind === "markdown" ? (
            <div className="mx-auto max-w-3xl space-y-2.5">
              <div className="flex items-center justify-end gap-1.5">
                <button
                  type="button"
                  onClick={() => setShowRawSource((v) => !v)}
                  className="rounded-lg border px-2.5 py-1 text-xs"
                  style={{
                    background: "var(--nesti-surface-1, #ffffff)",
                    borderColor: "var(--nesti-border-subtle, #e2e8f0)",
                  }}
                >
                  {showRawSource ? "切到富文本渲染" : "查看 Markdown 源码"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    void navigator.clipboard?.writeText(preview.text ?? "");
                    onNotice?.("已复制 Markdown 全文。");
                  }}
                  className="rounded-lg border px-2.5 py-1 text-xs"
                  style={{
                    background: "var(--nesti-surface-1, #ffffff)",
                    borderColor: "var(--nesti-border-subtle, #e2e8f0)",
                  }}
                >
                  一键复制
                </button>
              </div>
              <div
                className="rounded-2xl border p-6 shadow-xs"
                style={{
                  background: "var(--nesti-surface-1, #ffffff)",
                  borderColor: "var(--nesti-border-subtle, #e2e8f0)",
                }}
              >
                {showRawSource ? (
                  <pre className="overflow-auto font-mono text-xs leading-relaxed">
                    {preview.text}
                  </pre>
                ) : (
                  <MarkdownContent content={preview.text ?? ""} />
                )}
              </div>
            </div>
          ) : preview.kind === "html" ? (
            <div className="flex h-full flex-col gap-2">
              <div className="flex items-center justify-between text-xs">
                <span className="opacity-70">HTML 网页快照在隔离沙盒中运行，安全离线预览。</span>
                <button
                  type="button"
                  onClick={() => setShowRawSource((v) => !v)}
                  className="rounded-lg border px-2.5 py-1 text-xs"
                  style={{
                    background: "var(--nesti-surface-1, #ffffff)",
                    borderColor: "var(--nesti-border-subtle, #e2e8f0)",
                  }}
                >
                  {showRawSource ? "返回沙盒渲染" : "查看 HTML 源码"}
                </button>
              </div>
              {showRawSource ? (
                <pre
                  className="flex-1 overflow-auto rounded-xl border p-4 font-mono text-xs leading-relaxed"
                  style={{
                    background: "var(--nesti-surface-1, #ffffff)",
                    borderColor: "var(--nesti-border-subtle, #e2e8f0)",
                  }}
                >
                  {preview.text}
                </pre>
              ) : (
                <iframe
                  title={media.filename}
                  sandbox="allow-scripts"
                  srcDoc={preview.html ?? ""}
                  className="min-h-[68vh] w-full flex-1 rounded-xl border bg-white"
                  style={{ borderColor: "var(--nesti-border-subtle, #e2e8f0)" }}
                />
              )}
            </div>
          ) : preview.kind === "code" ? (
            <div className="mx-auto max-w-5xl space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-mono uppercase opacity-70">
                  {preview.language || "code"} · {(preview.text ?? "").split("\n").length} 行
                </span>
                <button
                  type="button"
                  onClick={() => {
                    void navigator.clipboard?.writeText(preview.text ?? "");
                    onNotice?.("已复制代码全文。");
                  }}
                  className="rounded-lg border px-2.5 py-1 text-xs"
                  style={{
                    background: "var(--nesti-surface-1, #ffffff)",
                    borderColor: "var(--nesti-border-subtle, #e2e8f0)",
                  }}
                >
                  一键复制代码
                </button>
              </div>
              <div
                className="max-h-[68vh] overflow-auto rounded-xl border p-3 font-mono text-xs leading-relaxed"
                style={{
                  background: "var(--nesti-surface-1, #ffffff)",
                  borderColor: "var(--nesti-border-subtle, #e2e8f0)",
                }}
              >
                {(preview.text ?? "").split("\n").map((ln, li) => (
                  <div key={li} className="flex gap-3">
                    <span className="w-9 shrink-0 select-none text-right opacity-45">
                      {li + 1}
                    </span>
                    <span className="whitespace-pre">{ln || " "}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : preview.kind === "image" ? (
            <div className="flex h-full items-center justify-center">
              <img
                src={preview.stream_url || media.url}
                alt={media.filename}
                className="max-h-[75vh] max-w-full rounded-xl object-contain shadow-md"
              />
            </div>
          ) : preview.kind === "video" ? (
            <div className="flex h-full items-center justify-center">
              <video
                controls
                autoPlay
                src={preview.stream_url || media.url}
                className="max-h-[75vh] w-full max-w-4xl rounded-xl bg-black"
              />
            </div>
          ) : preview.kind === "audio" ? (
            <div className="mx-auto max-w-xl py-16">
              <audio
                controls
                autoPlay
                src={preview.stream_url || media.url}
                className="w-full"
              />
            </div>
          ) : (
            <pre
              className="mx-auto max-w-4xl overflow-auto rounded-xl border p-4 font-mono text-xs leading-relaxed"
              style={{
                background: "var(--nesti-surface-1, #ffffff)",
                borderColor: "var(--nesti-border-subtle, #e2e8f0)",
              }}
            >
              {preview.text || "（该二进制文件不支持纯文本预览，请点击右上角在资源管理器中打开或下载）"}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
