import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { ModelSettings, ModelTestResult } from "../api/types";

const PROVIDER_PRESETS = [
  {
    name: "DeepSeek",
    desc: "高性价比主力推理",
    baseUrl: "https://api.deepseek.com/v1",
    model: "deepseek-chat",
  },
  {
    name: "通义千问 Qwen",
    desc: "阿里云百炼兼容接口",
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    model: "qwen-plus",
  },
  {
    name: "智谱 GLM",
    desc: "GLM-4-Flash 免费/低价",
    baseUrl: "https://open.bigmodel.cn/api/paas/v4",
    model: "glm-4-flash",
  },
  {
    name: "Kimi (Moonshot)",
    desc: "长文本强项",
    baseUrl: "https://api.moonshot.cn/v1",
    model: "moonshot-v1-8k",
  },
  {
    name: "SiliconFlow 硅基流动",
    desc: "多开源模型 + 向量",
    baseUrl: "https://api.siliconflow.cn/v1",
    model: "Qwen/Qwen2.5-7B-Instruct",
  },
  {
    name: "本机 Ollama（免费离线）",
    desc: "0 费用 · 无需 API Key",
    baseUrl: "http://127.0.0.1:11434/v1",
    model: "qwen2.5:3b",
  },
] as const;

/**
 * 模型与 API Key 可视化设置页：
 * - 密钥仅写入本机 backend/.env，绝不明文回传前端；
 * - 保存后立即热生效，无需重启软件；
 * - 内置 6 家常用云端/本机 Ollama 一键预设与实时连通性测试。
 */
export function ModelSettingsView() {
  const [current, setCurrent] = useState<ModelSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  const [modelBaseUrl, setModelBaseUrl] = useState("");
  const [modelName, setModelName] = useState("");
  const [modelApiKey, setModelApiKey] = useState("");

  const [embedBaseUrl, setEmbedBaseUrl] = useState("");
  const [embedModel, setEmbedModel] = useState("");
  const [embedApiKey, setEmbedApiKey] = useState("");

  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<ModelTestResult | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const s = await api.getModelSettings();
      setCurrent(s);
      setModelBaseUrl(s.model_base_url ?? "");
      setModelName(s.model_name ?? "");
      setEmbedBaseUrl(s.embed_base_url ?? "");
      setEmbedModel(s.embed_model ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleSave() {
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const isLocal =
        modelBaseUrl.includes("127.0.0.1") || modelBaseUrl.includes("localhost");
      const updated = await api.updateModelSettings({
        model_base_url: modelBaseUrl.trim(),
        model_name: modelName.trim(),
        model_api_key: modelApiKey.trim() || (isLocal && !current?.model_api_key_set ? "ollama" : undefined),
        embed_base_url: embedBaseUrl.trim(),
        embed_model: embedModel.trim(),
        embed_api_key: embedApiKey.trim() || undefined,
      });
      setCurrent(updated);
      setModelApiKey("");
      setEmbedApiKey("");
      setNotice("模型配置已写入本地 backend/.env 并立即热生效，无需重启软件！");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleTest() {
    if (!modelBaseUrl.trim() || !modelName.trim()) {
      setError("请先填写对话模型的 Base URL 和模型名称。");
      return;
    }
    setTesting(true);
    setError(null);
    setTestResult(null);
    try {
      const res = await api.testModelConnection({
        base_url: modelBaseUrl.trim(),
        model_name: modelName.trim(),
        api_key: modelApiKey.trim() || null,
      });
      setTestResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setTesting(false);
    }
  }

  const fieldStyle = {
    background: "var(--nesti-surface-0)",
    borderColor: "var(--nesti-border-subtle)",
    color: "var(--nesti-text-primary)",
  };

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div
        className="space-y-1 border-b pb-5"
        style={{ borderColor: "var(--nesti-border-subtle)" }}
      >
        <div className="nf-eyebrow">
          <span className="nf-eyebrow-index">09</span>
          <span>MODEL ENGINE · 热更新配置</span>
        </div>
        <h2 className="text-xl font-semibold" style={{ color: "var(--nesti-text-primary)" }}>
          模型与 API Key 设置
        </h2>
        <p className="text-xs" style={{ color: "var(--nesti-text-tertiary)" }}>
          随时更换任意 OpenAI 兼容模型（DeepSeek / 通义 / 智谱 / Kimi / 本机 Ollama）。密钥仅保存在本机{" "}
          <code>backend/.env</code>，绝不上传、绝不明文回传前端，保存后立即生效。
        </p>
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
      {testResult && (
        <div
          className={`rounded-lg border p-3 text-xs ${
            testResult.ok
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
              : "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300"
          }`}
        >
          {testResult.message}
        </div>
      )}

      {loading ? (
        <p className="py-8 text-center text-xs opacity-65">正在读取本地模型配置…</p>
      ) : (
        <>
          {/* 一键供应商预设 */}
          <div
            className="space-y-2.5 rounded-xl border p-4"
            style={{
              background: "var(--nesti-surface-1)",
              borderColor: "var(--nesti-border-subtle)",
            }}
          >
            <div className="text-xs font-semibold" style={{ color: "var(--nesti-text-primary)" }}>
              一键填入常用模型供应商（点击后填上你的 API Key 即可）
            </div>
            <div className="grid gap-2 sm:grid-cols-3">
              {PROVIDER_PRESETS.map((p) => (
                <button
                  key={p.name}
                  type="button"
                  onClick={() => {
                    setModelBaseUrl(p.baseUrl);
                    setModelName(p.model);
                    setTestResult(null);
                  }}
                  className="rounded-xl border p-2.5 text-left"
                  style={{
                    background: "var(--nesti-surface-0)",
                    borderColor:
                      modelBaseUrl === p.baseUrl
                        ? "var(--nesti-accent)"
                        : "var(--nesti-border-subtle)",
                  }}
                >
                  <div className="text-xs font-semibold" style={{ color: "var(--nesti-text-primary)" }}>
                    {p.name}
                  </div>
                  <div className="mt-0.5 text-[11px] opacity-70">{p.desc}</div>
                </button>
              ))}
            </div>
          </div>

          {/* 1. 对话 / 生成主模型 */}
          <div
            className="space-y-3 rounded-xl border p-4"
            style={{
              background: "var(--nesti-surface-1)",
              borderColor: "var(--nesti-border-subtle)",
            }}
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold" style={{ color: "var(--nesti-text-primary)" }}>
                1. 对话与生成模型（研究对话 / 动态沙盒 / 对话吸尘）
              </h3>
              <span
                className="rounded-full px-2 py-0.5 text-[10px] font-medium"
                style={
                  current?.model_api_key_set
                    ? { background: "rgba(16,185,129,0.14)", color: "#059669" }
                    : { background: "rgba(245,158,11,0.14)", color: "#d97706" }
                }
              >
                {current?.model_api_key_set
                  ? `密钥已配置 (${current.model_api_key_masked})`
                  : "未配置密钥"}
              </span>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <label className="space-y-1 text-xs">
                <span className="opacity-75">API Base URL</span>
                <input
                  value={modelBaseUrl}
                  onChange={(e) => setModelBaseUrl(e.target.value)}
                  placeholder="https://api.deepseek.com/v1"
                  className="w-full rounded-lg border px-3 py-1.5 text-xs outline-none"
                  style={fieldStyle}
                />
              </label>
              <label className="space-y-1 text-xs">
                <span className="opacity-75">模型名称（Model Name）</span>
                <input
                  value={modelName}
                  onChange={(e) => setModelName(e.target.value)}
                  placeholder="deepseek-chat"
                  className="w-full rounded-lg border px-3 py-1.5 text-xs outline-none"
                  style={fieldStyle}
                />
              </label>
            </div>

            <label className="block space-y-1 text-xs">
              <span className="opacity-75">
                API Key（留空表示保持原有密钥不变；本机 Ollama 可留空）
              </span>
              <input
                type="password"
                autoComplete="off"
                value={modelApiKey}
                onChange={(e) => setModelApiKey(e.target.value)}
                placeholder={
                  current?.model_api_key_set
                    ? `已保存 ${current.model_api_key_masked}，如需更换请输入新密钥…`
                    : "sk-..."
                }
                className="w-full rounded-lg border px-3 py-1.5 font-mono text-xs outline-none"
                style={fieldStyle}
              />
            </label>

            <div className="flex flex-wrap items-center gap-2 pt-1">
              <button
                type="button"
                onClick={() => void handleTest()}
                disabled={testing || saving}
                className="rounded-lg border px-3 py-1.5 text-xs font-medium disabled:opacity-45"
                style={{
                  borderColor: "var(--nesti-border-strong)",
                  color: "var(--nesti-text-primary)",
                }}
              >
                {testing ? "正在测试连通性…" : "测试对话模型连接"}
              </button>
            </div>
          </div>

          {/* 2. 语义向量模型（可选） */}
          <div
            className="space-y-3 rounded-xl border p-4"
            style={{
              background: "var(--nesti-surface-1)",
              borderColor: "var(--nesti-border-subtle)",
            }}
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold" style={{ color: "var(--nesti-text-primary)" }}>
                2. 向量模型（可选 · 用于语义混合检索）
              </h3>
              <span
                className="rounded-full px-2 py-0.5 text-[10px] font-medium"
                style={
                  current?.embed_api_key_set
                    ? { background: "rgba(16,185,129,0.14)", color: "#059669" }
                    : { background: "rgba(148,163,184,0.18)", color: "#64748b" }
                }
              >
                {current?.embed_api_key_set
                  ? `密钥已配置 (${current.embed_api_key_masked})`
                  : "未配置（仅使用全文检索）"}
              </span>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <label className="space-y-1 text-xs">
                <span className="opacity-75">Embed Base URL</span>
                <input
                  value={embedBaseUrl}
                  onChange={(e) => setEmbedBaseUrl(e.target.value)}
                  placeholder="https://api.siliconflow.cn/v1"
                  className="w-full rounded-lg border px-3 py-1.5 text-xs outline-none"
                  style={fieldStyle}
                />
              </label>
              <label className="space-y-1 text-xs">
                <span className="opacity-75">向量模型名</span>
                <input
                  value={embedModel}
                  onChange={(e) => setEmbedModel(e.target.value)}
                  placeholder="BAAI/bge-m3"
                  className="w-full rounded-lg border px-3 py-1.5 text-xs outline-none"
                  style={fieldStyle}
                />
              </label>
            </div>

            <label className="block space-y-1 text-xs">
              <span className="opacity-75">Embed API Key（留空保持原有密钥不变）</span>
              <input
                type="password"
                autoComplete="off"
                value={embedApiKey}
                onChange={(e) => setEmbedApiKey(e.target.value)}
                placeholder={
                  current?.embed_api_key_set
                    ? `已保存 ${current.embed_api_key_masked}，如需更换请输入新密钥…`
                    : "sk-..."
                }
                className="w-full rounded-lg border px-3 py-1.5 font-mono text-xs outline-none"
                style={fieldStyle}
              />
            </label>
          </div>

          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => void handleSave()}
              disabled={saving}
              className="rounded-lg px-5 py-2 text-xs font-semibold text-white disabled:opacity-45"
              style={{ background: "var(--nesti-accent)" }}
            >
              {saving ? "正在保存…" : "保存配置并立即生效"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
