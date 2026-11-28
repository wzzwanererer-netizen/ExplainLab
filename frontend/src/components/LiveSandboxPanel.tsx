import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { KnowledgeItem, SandboxResponse } from "../api/types";

interface Props {
  item: KnowledgeItem;
  onNotice: (msg: string) => void;
  onError: (msg: string) => void;
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/**
 * V3 交互式动态原理沙盒（Live Explain Sandbox）。
 * 在严格隔离的 <iframe sandbox="allow-scripts"> 内运行单文件交互动画，
 * 让抽象知识不止停留在静态文字。
 */
export function LiveSandboxPanel({ item, onNotice, onError }: Props) {
  const [sandbox, setSandbox] = useState<SandboxResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [instruction, setInstruction] = useState("");
  const [fullscreen, setFullscreen] = useState(false);

  const loadSandbox = useCallback(async () => {
    setLoading(true);
    try {
      setSandbox(await api.getSandbox(item.id));
    } catch (err) {
      onError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [item.id, onError]);

  useEffect(() => {
    void loadSandbox();
  }, [loadSandbox]);

  async function handleGenerate() {
    setGenerating(true);
    try {
      const created = await api.generateSandbox(item.id, instruction);
      setSandbox(created);
      setInstruction("");
      onNotice(`已为「${item.title}」生成交互式动态原理沙盒。`);
    } catch (err) {
      onError(errorMessage(err));
    } finally {
      setGenerating(false);
    }
  }

  async function handleDelete() {
    if (!window.confirm("确认移除该知识的动态原理沙盒？")) return;
    try {
      await api.deleteSandbox(item.id);
      setSandbox({ item_id: item.id, exists: false, html: null, updated_at: null });
      setFullscreen(false);
      onNotice("已删除动态沙盒。");
    } catch (err) {
      onError(errorMessage(err));
    }
  }

  const containerClass = fullscreen
    ? "fixed inset-4 z-50 flex flex-col rounded-2xl border p-4 shadow-2xl"
    : "mt-3 space-y-2.5 rounded-xl border p-3";

  return (
    <div
      className={containerClass}
      style={{
        background: "var(--nesti-surface-0)",
        borderColor: "var(--nesti-border-strong)",
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
            Live Explain 交互沙盒
          </span>
          <span className="text-xs" style={{ color: "var(--nesti-text-tertiary)" }}>
            离线隔离运行 · 支持实时点击与参数实验
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          {sandbox?.exists && (
            <>
              <button
                type="button"
                onClick={() => setFullscreen((v) => !v)}
                className="rounded-md border px-2.5 py-1 text-xs transition-colors hover:bg-[var(--nesti-surface-hover)]"
                style={{
                  borderColor: "var(--nesti-border-subtle)",
                  color: "var(--nesti-text-secondary)",
                }}
              >
                {fullscreen ? "退出全屏" : "全屏交互"}
              </button>
              <button
                type="button"
                onClick={() => void handleDelete()}
                className="rounded-md border px-2.5 py-1 text-xs text-red-500 transition-colors hover:bg-red-500/10"
                style={{ borderColor: "var(--nesti-border-subtle)" }}
              >
                删除
              </button>
            </>
          )}
        </div>
      </div>

      {/* 生成 / 微调控制条 */}
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="可选交互要求，如：加入步进按钮、参数滑块或异常模拟…"
          aria-label="沙盒交互要求"
          className="min-w-[220px] flex-1 rounded-lg border px-2.5 py-1.5 text-xs outline-none"
          style={{
            background: "var(--nesti-surface-1)",
            borderColor: "var(--nesti-border-subtle)",
            color: "var(--nesti-text-primary)",
          }}
        />
        <button
          type="button"
          onClick={() => void handleGenerate()}
          disabled={generating}
          className="rounded-lg px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-45"
          style={{ background: "var(--nesti-accent)" }}
        >
          {generating
            ? "AI 正在编排动态沙盒…"
            : sandbox?.exists
              ? "重新生成沙盒"
              : "一键生成动态图解"}
        </button>
      </div>

      {loading ? (
        <p className="py-6 text-center text-xs" style={{ color: "var(--nesti-text-tertiary)" }}>
          正在检查已有动态沙盒…
        </p>
      ) : sandbox?.exists && sandbox.html ? (
        <iframe
          title={`${item.title} 动态原理沙盒`}
          sandbox="allow-scripts"
          srcDoc={sandbox.html}
          className={`w-full rounded-lg border bg-white ${
            fullscreen ? "flex-1 min-h-0" : "h-[520px]"
          }`}
          style={{ borderColor: "var(--nesti-border-subtle)" }}
        />
      ) : (
        <div
          className="rounded-lg border border-dashed p-5 text-center text-xs"
          style={{
            borderColor: "var(--nesti-border-strong)",
            color: "var(--nesti-text-tertiary)",
          }}
        >
          该知识条目尚未生成交互式动态沙盒。点击上方「一键生成动态图解」，把抽象概念变成可亲手操作的可视化实验！
        </div>
      )}
    </div>
  );
}
