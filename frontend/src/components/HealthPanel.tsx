import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { HealthResponse } from "../api/types";

type PanelState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: HealthResponse };

function StatusBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
        ok ? "bg-emerald-500/15 text-emerald-400" : "bg-amber-500/15 text-amber-400"
      }`}
    >
      {label}
    </span>
  );
}

function Row({ name, children }: { name: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-800 py-3 last:border-b-0">
      <span className="text-sm text-slate-400">{name}</span>
      <span className="text-sm">{children}</span>
    </div>
  );
}

/** 系统状态面板：数据全部来自 GET /api/health 的真实响应。 */
export function HealthPanel() {
  const [state, setState] = useState<PanelState>({ kind: "loading" });

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const data = await api.getHealth();
      setState({ kind: "ready", data });
    } catch (err) {
      setState({
        kind: "error",
        message: err instanceof Error ? err.message : String(err),
      });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900 p-6">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-base font-medium">系统状态</h2>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-md border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-800"
        >
          刷新
        </button>
      </div>

      {state.kind === "loading" && (
        <p className="text-sm text-slate-400" role="status">
          正在连接后端…
        </p>
      )}

      {state.kind === "error" && (
        <div className="rounded-md border border-red-900 bg-red-950/50 p-4 text-sm text-red-300">
          <p className="font-medium">无法连接后端</p>
          <p className="mt-1 text-xs">{state.message}</p>
          <p className="mt-2 text-xs text-red-400/80">
            请确认后端已启动：cd backend &amp;&amp; uv run uvicorn app.main:app --port 8000
          </p>
        </div>
      )}

      {state.kind === "ready" && (
        <div>
          <Row name="后端状态">
            <StatusBadge
              ok={state.data.status === "ok"}
              label={state.data.status === "ok" ? "正常" : "降级"}
            />
          </Row>
          <Row name="数据库">
            <StatusBadge
              ok={state.data.database.connected}
              label={`${state.data.database.dialect} · ${
                state.data.database.connected ? "已连接" : "未连接"
              }`}
            />
          </Row>
          <Row name="模型适配层">
            {state.data.model_adapter === "not_configured" ? (
              <span className="text-slate-400">未配置（对话与提取不可用）</span>
            ) : (
              state.data.model_adapter
            )}
          </Row>
          <Row name="版本">
            {state.data.app} v{state.data.version}（{state.data.environment}）
          </Row>
          <Row name="检查时间">
            {new Date(state.data.timestamp).toLocaleString("zh-CN")}
          </Row>
        </div>
      )}
    </section>
  );
}