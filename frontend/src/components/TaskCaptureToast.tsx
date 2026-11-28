import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { CompletedTaskSuggestion } from "../api/types";

interface Props {
  suggestion: CompletedTaskSuggestion | null;
  onClose: () => void;
  onAccepted?: (spaceId?: string | null) => void;
  onJumpToSpace?: (spaceId: string) => void;
}

const DURATION_MS = 12000;

/**
 * 浏览器模式下的右下角临时悬浮提醒窗（不常驻桌面，倒计时结束后自动消失）。
 * Electron 桌面版会由主进程直接弹出原生无边框跨窗口悬浮窗，此组件作为网页端无缝兜底。
 */
export function TaskCaptureToast({
  suggestion,
  onClose,
  onAccepted,
  onJumpToSpace,
}: Props) {
  const [remainingMs, setRemainingMs] = useState(DURATION_MS);
  const [paused, setPaused] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{
    ok: boolean;
    message: string;
    spaceId?: string | null;
  } | null>(null);

  useEffect(() => {
    if (!suggestion) return;
    setRemainingMs(DURATION_MS);
    setPaused(false);
    setBusy(false);
    setResult(null);
  }, [suggestion?.suggestion_id]);

  useEffect(() => {
    if (!suggestion) return;
    const id = window.setInterval(() => {
      if (paused || busy) return;
      setRemainingMs((prev) => {
        const next = prev - 100;
        if (next <= 0) {
          window.clearInterval(id);
          if (!result) {
            void api
              .dismissTaskSuggestion(suggestion.file_path, suggestion.signature)
              .catch(() => {});
          }
          onClose();
          return 0;
        }
        return next;
      });
    }, 100);
    return () => window.clearInterval(id);
  }, [suggestion, paused, busy, result, onClose]);

  if (!suggestion) return null;

  async function handleAccept() {
    if (!suggestion || busy) return;
    setBusy(true);
    try {
      const rep = await api.vacuumAgents(suggestion.agent_name, 1, [
        suggestion.file_path,
      ]);
      const cnt = rep.created_items.length;
      const targetSpace = rep.created_items[0]?.space_id ?? suggestion.space_id;
      setResult({
        ok: true,
        message: cnt > 0 ? `已入库 ${cnt} 条知识` : "已扫描（内容为闲聊或已存在）",
        spaceId: targetSpace,
      });
      setRemainingMs(3200);
      onAccepted?.(targetSpace);
    } catch (err) {
      setResult({
        ok: false,
        message: err instanceof Error ? err.message : "入库失败",
      });
      setRemainingMs(3500);
    } finally {
      setBusy(false);
    }
  }

  function handleDismiss() {
    if (suggestion && !result) {
      void api
        .dismissTaskSuggestion(suggestion.file_path, suggestion.signature)
        .catch(() => {});
    }
    onClose();
  }

  const totalMs = result ? 3200 : DURATION_MS;
  const pct = Math.max(0, Math.min(100, (remainingMs / totalMs) * 100));

  return (
    <div
      role="status"
      aria-live="polite"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      className="fixed right-4 bottom-9 z-50 w-[372px] max-w-[calc(100vw-2rem)] overflow-hidden rounded-2xl border p-3.5 shadow-2xl backdrop-blur-md transition-all"
      style={{
        background: "var(--nf-bg-surface)",
        borderColor: "var(--nf-border-default)",
        color: "var(--nf-text-primary)",
      }}
    >
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <img
            src="/nesti-logo.png"
            alt="Nesti"
            className="h-5 w-5 shrink-0 rounded-[5px] object-contain"
          />
          <span
            className="rounded-full px-2 py-0.5 text-[11px] font-semibold"
            style={{
              background: "var(--nf-accent-soft)",
              color: "var(--nf-accent)",
            }}
          >
            {suggestion.agent_name}
          </span>
          <span className="text-[11px]" style={{ color: "var(--nf-text-muted)" }}>
            刚完成一项任务
          </span>
        </div>
        <button
          type="button"
          onClick={handleDismiss}
          title="关闭"
          className="flex h-5 w-5 items-center justify-center rounded text-sm opacity-60 hover:opacity-100"
        >
          ×
        </button>
      </div>

      <p className="truncate text-xs font-semibold">{suggestion.label}</p>
      <p
        className="mt-0.5 line-clamp-2 text-[11.5px] leading-snug"
        style={{ color: "var(--nf-text-secondary)" }}
      >
        {suggestion.preview}
      </p>

      <div className="mt-2.5 flex items-center gap-2">
        {result ? (
          <>
            <span
              className="text-xs font-semibold"
              style={{
                color: result.ok
                  ? "var(--nf-status-success, #059669)"
                  : "#ef4444",
              }}
            >
              {result.message}
            </span>
            {result.ok && result.spaceId && onJumpToSpace && (
              <button
                type="button"
                onClick={() => {
                  onJumpToSpace(result.spaceId!);
                  onClose();
                }}
                className="ml-auto rounded-lg border px-2.5 py-1 text-xs font-medium"
                style={{ borderColor: "var(--nf-border-default)" }}
              >
                去查看
              </button>
            )}
          </>
        ) : (
          <>
            <button
              type="button"
              disabled={busy}
              onClick={() => void handleAccept()}
              className="flex-1 rounded-lg px-3 py-1.5 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-55"
              style={{ background: "var(--nf-accent)" }}
            >
              {busy ? "正在提炼入库…" : "加入知识库"}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={handleDismiss}
              className="rounded-lg border px-3 py-1.5 text-xs font-medium"
              style={{
                borderColor: "var(--nf-border-default)",
                color: "var(--nf-text-secondary)",
              }}
            >
              不加入
            </button>
            <span
              className="w-7 text-right font-mono text-[10.5px]"
              style={{ color: "var(--nf-text-muted)" }}
            >
              {Math.ceil(remainingMs / 1000)}s
            </span>
          </>
        )}
      </div>

      <div
        className="absolute right-0 bottom-0 left-0 h-[3px]"
        style={{ background: "var(--nf-border-subtle)" }}
      >
        <div
          className="h-full transition-[width] duration-100 ease-linear"
          style={{
            width: `${pct}%`,
            background: "var(--nf-accent)",
          }}
        />
      </div>
    </div>
  );
}
