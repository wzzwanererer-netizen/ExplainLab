import { useMemo, useState } from "react";
import { api } from "../api/client";
import {
  THEME_PRESETS,
  useNestiTheme,
  type ThemeDensity,
  type ThemeMode,
  type ThemeRadius,
  type ThemeShadow,
} from "../theme/ThemeProvider";
import {
  buildStylePluginFromDraft,
  DEFAULT_SKIN_ID,
  type StyleBuilderDraft,
  type StyleCanvasTexture,
  type StyleCornerStyle,
  type StyleFontMood,
  type UIStylePlugin,
} from "../theme/stylePlugins";
import { Icon } from "./Icons";

const AI_STYLE_PRESETS = [
  "千与千寻汤屋暖红与流金古风",
  "京都雨后抹茶手账风，柔和护眼",
  "深海亚特兰蒂斯幽蓝极客终端",
  "王家卫花样年华复古霓虹胶片",
];

function PluginPreviewThumbnail({ plugin }: { plugin: UIStylePlugin }) {
  const p = plugin.preview;
  const isCyber = plugin.id === "cyber-neon";
  const isLibrary = plugin.id === "vintage-library";
  const hasGrid = isCyber || Boolean(plugin.customCss?.includes("linear-gradient"));
  const hasDots = isLibrary || Boolean(plugin.customCss?.includes("radial-gradient"));
  return (
    <div
      className="relative mb-3 h-24 w-full overflow-hidden rounded-lg border"
      style={{
        background: p.windowBg,
        borderColor: p.border,
      }}
    >
      <div className="flex h-full">
        <div
          className="flex w-14 shrink-0 flex-col gap-1.5 border-r p-2"
          style={{ background: p.sidebarBg, borderColor: p.border }}
        >
          <div className="h-2 w-7 rounded-full" style={{ background: p.accent }} />
          <div className="h-1.5 w-9 rounded-full opacity-45" style={{ background: p.text }} />
          <div className="h-1.5 w-8 rounded-full opacity-30" style={{ background: p.text }} />
          <div className="h-1.5 w-9 rounded-full opacity-30" style={{ background: p.text }} />
        </div>
        <div
          className="flex flex-1 flex-col justify-between p-2.5"
          style={{
            background: p.canvasBg,
            backgroundImage: hasGrid
              ? "linear-gradient(rgba(125,211,252,0.12) 1px, transparent 1px), linear-gradient(90deg, rgba(125,211,252,0.12) 1px, transparent 1px)"
              : hasDots
                ? "radial-gradient(rgba(140,108,66,0.16) 1px, transparent 0)"
                : undefined,
            backgroundSize: hasGrid ? "12px 12px" : hasDots ? "10px 10px" : undefined,
          }}
        >
          <div className="flex items-center justify-between">
            <div className="h-2 w-16 rounded-full" style={{ background: p.text, opacity: 0.8 }} />
            <span
              className="inline-block h-2.5 w-8 rounded-full"
              style={{
                background: p.accent,
                boxShadow: isCyber ? `0 0 8px ${p.accent}` : undefined,
              }}
            />
          </div>
          <div className="grid grid-cols-2 gap-1.5">
            <div
              className="rounded border p-1.5"
              style={{ background: p.cardBg, borderColor: p.border }}
            >
              <div className="mb-1 h-1.5 w-10 rounded-full" style={{ background: p.accent }} />
              <div className="h-1 w-full rounded-full opacity-35" style={{ background: p.text }} />
            </div>
            <div
              className="rounded border p-1.5"
              style={{ background: p.cardBg, borderColor: p.border }}
            >
              <div className="mb-1 h-1.5 w-8 rounded-full" style={{ background: p.secondary }} />
              <div className="h-1 w-full rounded-full opacity-35" style={{ background: p.text }} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function downloadJsonFile(filename: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function ThemeStudioView() {
  const {
    config,
    resolvedTheme,
    stylePlugins,
    activePlugin,
    isPluginLocked,
    setSkin,
    addStylePlugin,
    installStylePlugin,
    removeStylePlugin,
    update,
    reset,
    importJson,
  } = useNestiTheme();
  const [importText, setImportText] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // AI 一句话生成风格
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiLoading, setAiLoading] = useState(false);

  // 可视化风格制作器
  const [builderOpen, setBuilderOpen] = useState(false);
  const [draft, setDraft] = useState<StyleBuilderDraft>({
    name: "我的专属风格",
    englishName: "My Atelier",
    description: "通过 Nesti 可视化风格制作器定制的专属界面皮肤。",
    mode: "dark",
    canvasBg: "#0f172a",
    cardBg: "#1e293b",
    accent: "#38bdf8",
    secondary: "#f472b6",
    fontMood: "sans",
    texture: "aurora",
    cornerStyle: "balanced",
  });

  const draftPreviewPlugin = useMemo(() => buildStylePluginFromDraft(draft), [draft]);

  const cardStyle = {
    background: "var(--nf-bg-surface)",
    border: "1px solid var(--nf-border-subtle)",
    borderRadius: "var(--nf-radius-md)",
    boxShadow: "var(--nf-shadow-sm)",
  };

  function handleExport() {
    const json = JSON.stringify(config, null, 2);
    void navigator.clipboard?.writeText(json);
    setNotice("已复制当前主题配置 JSON 到剪贴板。");
  }

  function handleImportRaw(rawInput: string) {
    const raw = rawInput.trim();
    if (!raw) return;
    setError(null);
    try {
      const parsed = JSON.parse(raw) as { schema?: string };
      if (parsed.schema === "nesti.style.plugin/v1") {
        const res = installStylePlugin(raw);
        if (res.ok && res.plugin) {
          setNotice(`已安装并启用 UI 风格插件「${res.plugin.name}」。`);
          setImportText("");
          return;
        }
      }
    } catch {
      // fall through
    }
    if (importJson(raw)) {
      setNotice("已导入自定义主题配置。");
      setImportText("");
    } else {
      setError("JSON 格式无效，请粘贴或选择有效的 nesti.style.plugin/v1 插件文件。");
    }
  }

  async function handleAiGenerateStyle(promptText?: string) {
    const p = (promptText ?? aiPrompt).trim();
    if (!p || aiLoading) return;
    setAiLoading(true);
    setError(null);
    setNotice(null);
    try {
      const generated = await api.generateStylePlugin(p);
      const plugin = buildStylePluginFromDraft({
        ...generated,
        author: "Nesti AI",
      });
      addStylePlugin(plugin);
      setAiPrompt("");
      setNotice(
        `AI 已生成并启用风格插件「${plugin.name}」（系统模式与主题颜色已由插件锁定接管）。`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setAiLoading(false);
    }
  }

  function handleSaveBuilderPlugin() {
    const plugin = buildStylePluginFromDraft(draft);
    addStylePlugin(plugin);
    setBuilderOpen(false);
    setNotice(`已创建并启用个人风格插件「${plugin.name}」！你也可以导出 .json 分享给朋友。`);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3" style={cardStyle}>
        <div>
          <div
            className="text-[10.5px] font-semibold tracking-[0.14em] uppercase"
            style={{ color: "var(--nf-accent)" }}
          >
            THEME STUDIO 2.0 · UI 风格插件生态
          </div>
          <h2 className="mt-0.5 text-sm font-semibold">
            当前风格：{activePlugin.name}
            <span className="ml-2 font-mono text-[11px] font-normal" style={{ color: "var(--nf-text-muted)" }}>
              v{activePlugin.version}
            </span>
          </h2>
          <p className="text-xs" style={{ color: "var(--nf-text-muted)" }}>
            内置 6 套精选风格，支持 AI 一句话造皮肤、可视化风格制作器与 .json 风格插件导入分享。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setBuilderOpen((v) => !v)}
            className="rounded-md px-3 py-1.5 text-xs font-semibold"
            style={{
              background: "var(--nf-accent)",
              color: "var(--nf-text-on-accent)",
            }}
          >
            {builderOpen ? "收起风格制作器" : "+ 创作我的风格"}
          </button>
          <label
            className="cursor-pointer rounded-md px-3 py-1.5 text-xs font-medium"
            style={{ background: "var(--nf-bg-surface-subtle)", border: "1px solid var(--nf-border-default)" }}
          >
            导入 .json 插件
            <input
              type="file"
              accept=".json"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) {
                  void file.text().then((txt) => handleImportRaw(txt));
                }
                e.target.value = "";
              }}
            />
          </label>
          <button
            type="button"
            onClick={handleExport}
            className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium"
            style={{ background: "var(--nf-bg-surface-subtle)", border: "1px solid var(--nf-border-default)" }}
          >
            <Icon name="download" size={14} /> 复制配置
          </button>
          <button
            type="button"
            onClick={() => {
              reset();
              setNotice("已恢复 Nesti Fluent 官方默认风格。");
            }}
            className="rounded-md px-3 py-1.5 text-xs font-medium"
            style={{ background: "var(--nf-bg-surface-subtle)", border: "1px solid var(--nf-border-default)" }}
          >
            恢复默认
          </button>
        </div>
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-md border border-red-400/40 bg-red-500/10 px-3 py-2 text-xs text-red-500"
        >
          {error}
        </div>
      )}

      {notice && (
        <div
          role="status"
          className="rounded-md px-3 py-2 text-xs"
          style={{
            background: "var(--nf-accent-soft)",
            color: "var(--nf-accent)",
            border: "1px solid var(--nf-accent-border)",
          }}
        >
          {notice}
        </div>
      )}

      {/* AI 一句话生成风格 */}
      <section style={cardStyle} className="space-y-2.5 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-xs font-semibold">✦ AI 一句话生成专属 UI 风格</h3>
            <p className="text-[11px]" style={{ color: "var(--nf-text-muted)" }}>
              输入任何电影、动漫、建筑或色彩灵感，自动调用已配置的大模型生成并安装为独立风格插件。
            </p>
          </div>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void handleAiGenerateStyle();
          }}
          className="flex flex-wrap items-center gap-2"
        >
          <input
            value={aiPrompt}
            onChange={(e) => setAiPrompt(e.target.value)}
            placeholder="例如：千与千寻汤屋暖红金风格 / 赛博银翼杀手雨夜 / 京都樱花手账…"
            aria-label="AI 风格灵感描述"
            className="min-w-64 flex-1 rounded-md px-3 py-1.5 text-xs outline-none"
            style={{
              background: "var(--nf-bg-surface-subtle)",
              border: "1px solid var(--nf-border-default)",
              color: "var(--nf-text-primary)",
            }}
          />
          <button
            type="submit"
            disabled={!aiPrompt.trim() || aiLoading}
            className="rounded-md px-4 py-1.5 text-xs font-semibold disabled:opacity-45"
            style={{
              background: "var(--nf-accent)",
              color: "var(--nf-text-on-accent)",
            }}
          >
            {aiLoading ? "AI 设计配色中…" : "AI 生成并启用"}
          </button>
        </form>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[10.5px]" style={{ color: "var(--nf-text-muted)" }}>
            试试灵感：
          </span>
          {AI_STYLE_PRESETS.map((sample) => (
            <button
              key={sample}
              type="button"
              disabled={aiLoading}
              onClick={() => {
                setAiPrompt(sample);
                void handleAiGenerateStyle(sample);
              }}
              className="rounded-full px-2.5 py-0.5 text-[10.5px] transition-colors"
              style={{
                background: "var(--nf-bg-surface-subtle)",
                color: "var(--nf-text-secondary)",
                border: "1px solid var(--nf-border-subtle)",
              }}
            >
              {sample}
            </button>
          ))}
        </div>
      </section>

      {/* 可视化风格制作器（零代码捏皮肤） */}
      {builderOpen && (
        <section style={cardStyle} className="space-y-4 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="text-xs font-semibold">可视化风格制作器（Style Builder）</h3>
              <p className="text-[11px]" style={{ color: "var(--nf-text-muted)" }}>
                零代码自创皮肤：挑选底色、强调色、字体与画布纹理，自动计算全站可读性与对比度。
              </p>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => {
                  downloadJsonFile(`${draftPreviewPlugin.id}.nesti-style.json`, draftPreviewPlugin);
                  setNotice(`已导出风格插件文件：${draftPreviewPlugin.id}.nesti-style.json`);
                }}
                className="rounded-md px-3 py-1.5 text-xs font-medium"
                style={{
                  background: "var(--nf-bg-surface-subtle)",
                  border: "1px solid var(--nf-border-default)",
                }}
              >
                导出 .json 文件
              </button>
              <button
                type="button"
                onClick={handleSaveBuilderPlugin}
                className="rounded-md px-3.5 py-1.5 text-xs font-semibold"
                style={{
                  background: "var(--nf-accent)",
                  color: "var(--nf-text-on-accent)",
                }}
              >
                保存并立即启用
              </button>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
            <div className="space-y-3">
              <div className="grid gap-2.5 sm:grid-cols-2">
                <label className="space-y-1 text-xs">
                  <span className="font-medium">风格名称</span>
                  <input
                    value={draft.name}
                    onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
                    className="w-full rounded-md px-2.5 py-1.5 text-xs outline-none"
                    style={{
                      background: "var(--nf-bg-surface-subtle)",
                      border: "1px solid var(--nf-border-default)",
                    }}
                  />
                </label>
                <div className="space-y-1 text-xs">
                  <span className="block font-medium">基准明暗</span>
                  <div className="inline-flex gap-1 rounded-md p-0.5" style={{ background: "var(--nf-bg-surface-subtle)" }}>
                    {(
                      [
                        ["light", "浅色基底"],
                        ["dark", "深色基底"],
                      ] as const
                    ).map(([m, label]) => (
                      <button
                        key={m}
                        type="button"
                        onClick={() =>
                          setDraft((d) => ({
                            ...d,
                            mode: m,
                            canvasBg: m === "dark" ? "#0f172a" : "#f7f6f2",
                            cardBg: m === "dark" ? "#1e293b" : "#ffffff",
                          }))
                        }
                        className="rounded px-3 py-1 text-xs font-medium"
                        style={
                          draft.mode === m
                            ? { background: "var(--nf-accent)", color: "var(--nf-text-on-accent)" }
                            : { color: "var(--nf-text-secondary)" }
                        }
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
                {(
                  [
                    ["canvasBg", "画布底色"],
                    ["cardBg", "卡片底色"],
                    ["accent", "核心强调色"],
                    ["secondary", "辅助点缀色"],
                  ] as const
                ).map(([key, label]) => (
                  <label
                    key={key}
                    className="flex items-center gap-2 rounded-lg border p-2 text-xs"
                    style={{
                      background: "var(--nf-bg-surface-subtle)",
                      borderColor: "var(--nf-border-subtle)",
                    }}
                  >
                    <input
                      type="color"
                      value={draft[key]}
                      onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
                      className="h-6 w-7 shrink-0 cursor-pointer rounded border-0 bg-transparent"
                    />
                    <span className="min-w-0 truncate">
                      <span className="block text-[11px] font-medium">{label}</span>
                      <span className="font-mono text-[10px]" style={{ color: "var(--nf-text-muted)" }}>
                        {draft[key]}
                      </span>
                    </span>
                  </label>
                ))}
              </div>

              <div className="grid gap-3 sm:grid-cols-3">
                <div className="space-y-1 text-xs">
                  <span className="block font-medium">字体气质</span>
                  <div className="flex flex-wrap gap-1">
                    {(
                      [
                        ["sans", "现代无衬线"],
                        ["serif", "复古衬线"],
                        ["mono", "极客等宽"],
                      ] as [StyleFontMood, string][]
                    ).map(([f, label]) => (
                      <button
                        key={f}
                        type="button"
                        onClick={() => setDraft((d) => ({ ...d, fontMood: f }))}
                        className="rounded px-2 py-1 text-[11px]"
                        style={
                          draft.fontMood === f
                            ? { background: "var(--nf-accent-soft)", color: "var(--nf-accent)" }
                            : { background: "var(--nf-bg-surface-subtle)", color: "var(--nf-text-secondary)" }
                        }
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="space-y-1 text-xs">
                  <span className="block font-medium">画布纹理</span>
                  <div className="flex flex-wrap gap-1">
                    {(
                      [
                        ["none", "纯净"],
                        ["grid", "赛博网格"],
                        ["dots", "纸张微点"],
                        ["aurora", "柔光渐变"],
                      ] as [StyleCanvasTexture, string][]
                    ).map(([t, label]) => (
                      <button
                        key={t}
                        type="button"
                        onClick={() => setDraft((d) => ({ ...d, texture: t }))}
                        className="rounded px-2 py-1 text-[11px]"
                        style={
                          draft.texture === t
                            ? { background: "var(--nf-accent-soft)", color: "var(--nf-accent)" }
                            : { background: "var(--nf-bg-surface-subtle)", color: "var(--nf-text-secondary)" }
                        }
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="space-y-1 text-xs">
                  <span className="block font-medium">边框圆角</span>
                  <div className="flex flex-wrap gap-1">
                    {(
                      [
                        ["sharp", "锐利"],
                        ["balanced", "均衡"],
                        ["soft", "柔和"],
                      ] as [StyleCornerStyle, string][]
                    ).map(([c, label]) => (
                      <button
                        key={c}
                        type="button"
                        onClick={() => setDraft((d) => ({ ...d, cornerStyle: c }))}
                        className="rounded px-2 py-1 text-[11px]"
                        style={
                          draft.cornerStyle === c
                            ? { background: "var(--nf-accent-soft)", color: "var(--nf-accent)" }
                            : { background: "var(--nf-bg-surface-subtle)", color: "var(--nf-text-secondary)" }
                        }
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            <div
              className="flex flex-col justify-center rounded-xl border p-3"
              style={{
                background: "var(--nf-bg-surface-subtle)",
                borderColor: "var(--nf-border-subtle)",
              }}
            >
              <div className="mb-1.5 text-[11px] font-medium" style={{ color: "var(--nf-text-muted)" }}>
                实时效果预览
              </div>
              <PluginPreviewThumbnail plugin={draftPreviewPlugin} />
              <div className="text-xs font-semibold">{draftPreviewPlugin.name}</div>
              <div className="mt-0.5 text-[11px]" style={{ color: "var(--nf-text-muted)" }}>
                {draft.mode === "dark" ? "深色基底" : "浅色基底"} · {draft.fontMood} · {draft.texture}
              </div>
            </div>
          </div>
        </section>
      )}

      {/* UI 风格插件画廊 */}
      <section style={cardStyle} className="space-y-3 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-xs font-semibold">UI 风格插件画廊（Style Plugins）</h3>
            <p className="text-[11px]" style={{ color: "var(--nf-text-muted)" }}>
              点击卡片即可热切换全站视觉风格；加载非默认风格插件后，系统模式与主题颜色由插件统一接管。
            </p>
          </div>
          <span
            className="rounded-full px-2.5 py-0.5 font-mono text-[10.5px]"
            style={{
              background: "var(--nf-bg-surface-subtle)",
              color: "var(--nf-text-secondary)",
              border: "1px solid var(--nf-border-subtle)",
            }}
          >
            已加载 {stylePlugins.length} 套风格
          </span>
        </div>

        <div className="grid gap-3 md:grid-cols-3">
          {stylePlugins.map((plugin) => {
            const selected = activePlugin.id === plugin.id;
            return (
              <div
                key={plugin.id}
                role="button"
                tabIndex={0}
                onClick={() => {
                  setSkin(plugin.id);
                  setNotice(
                    plugin.id === DEFAULT_SKIN_ID
                      ? "已切回 Nesti Fluent 官方默认风格，现可自由切换系统模式与主题颜色。"
                      : `已加载 UI 风格插件「${plugin.name}」，系统模式与主题颜色已由插件锁定接管。`,
                  );
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setSkin(plugin.id);
                  }
                }}
                className="flex flex-col rounded-xl p-3 text-left transition-all"
                style={{
                  background: selected ? "var(--nf-accent-soft)" : "var(--nf-bg-surface-subtle)",
                  border: `1.5px solid ${selected ? "var(--nf-accent)" : "var(--nf-border-subtle)"}`,
                  boxShadow: selected ? "0 0 0 2px var(--nf-accent-border)" : undefined,
                }}
              >
                <PluginPreviewThumbnail plugin={plugin} />
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="text-xs font-semibold">{plugin.name}</div>
                    <div className="font-mono text-[10px]" style={{ color: "var(--nf-text-muted)" }}>
                      {plugin.englishName} · {plugin.author}
                    </div>
                  </div>
                  {selected ? (
                    <span
                      className="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold"
                      style={{
                        background: "var(--nf-accent)",
                        color: "var(--nf-text-on-accent)",
                      }}
                    >
                      使用中
                    </span>
                  ) : (
                    <span
                      className="shrink-0 rounded-full px-2 py-0.5 text-[10px]"
                      style={{
                        background: "var(--nf-bg-surface)",
                        color: "var(--nf-text-secondary)",
                        border: "1px solid var(--nf-border-subtle)",
                      }}
                    >
                      点击启用
                    </span>
                  )}
                </div>
                <p
                  className="mt-1.5 flex-1 text-[11px] leading-relaxed"
                  style={{ color: "var(--nf-text-secondary)" }}
                >
                  {plugin.description}
                </p>
                <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                  {plugin.tags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded px-1.5 py-0.5 text-[10px]"
                      style={{
                        background: "var(--nf-bg-surface)",
                        color: "var(--nf-text-muted)",
                        border: "1px solid var(--nf-border-subtle)",
                      }}
                    >
                      {tag}
                    </span>
                  ))}
                  {!plugin.builtin && (
                    <div className="ml-auto flex items-center gap-2">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          downloadJsonFile(`${plugin.id}.nesti-style.json`, plugin);
                          setNotice(`已导出风格插件「${plugin.name}」。`);
                        }}
                        className="text-[10px] hover:underline"
                        style={{ color: "var(--nf-accent)" }}
                      >
                        导出
                      </button>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          removeStylePlugin(plugin.id);
                          setNotice(`已卸载风格插件「${plugin.name}」。`);
                        }}
                        className="text-[10px] text-red-500 hover:underline"
                      >
                        卸载
                      </button>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
        <div className="space-y-4">
          <section style={cardStyle} className="space-y-4 p-4">
            {isPluginLocked && (
              <div
                role="note"
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg px-3 py-2.5 text-xs"
                style={{
                  background: "var(--nf-accent-soft)",
                  border: "1px solid var(--nf-accent-border)",
                  color: "var(--nf-text-primary)",
                }}
              >
                <span>
                  当前已加载风格插件「<strong>{activePlugin.name}</strong>」：
                  <strong>系统模式与主题颜色不可切换</strong>，已由插件自动接管。
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setSkin(DEFAULT_SKIN_ID);
                    setNotice("已切回 Nesti Fluent 官方默认风格，现可自由切换系统模式与主题颜色。");
                  }}
                  className="shrink-0 rounded px-2.5 py-1 text-[11px] font-semibold"
                  style={{
                    background: "var(--nf-accent)",
                    color: "var(--nf-text-on-accent)",
                  }}
                >
                  切回默认以解锁
                </button>
              </div>
            )}

            <div className={isPluginLocked ? "pointer-events-none opacity-45 select-none" : ""}>
              <div className="mb-4">
                <h3 className="mb-2 text-xs font-semibold">
                  系统模式（当前：{resolvedTheme}
                  {isPluginLocked ? " · 插件已锁定，不可切换" : ""}）
                </h3>
                <div className="inline-flex gap-1 rounded-md p-1" style={{ background: "var(--nf-bg-surface-hover)" }}>
                  {(
                    [
                      ["light", "浅色模式"],
                      ["dark", "深色模式"],
                      ["system", "跟随系统"],
                    ] as [ThemeMode, string][]
                  ).map(([m, label]) => (
                    <button
                      key={m}
                      type="button"
                      disabled={isPluginLocked}
                      onClick={() => update({ mode: m })}
                      className="rounded px-3 py-1 text-xs font-medium"
                      style={
                        config.mode === m
                          ? { background: "var(--nf-bg-surface)", color: "var(--nf-text-primary)", boxShadow: "var(--nf-shadow-sm)" }
                          : { color: "var(--nf-text-secondary)" }
                      }
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <h3 className="mb-2 text-xs font-semibold">
                  主题颜色预设{isPluginLocked ? "（插件已锁定，不可切换）" : ""}
                </h3>
                <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
                  {THEME_PRESETS.map((p) => {
                    const selected = config.preset === p.id;
                    return (
                      <button
                        key={p.id}
                        type="button"
                        disabled={isPluginLocked}
                        onClick={() => update({ preset: p.id })}
                        className="rounded-lg p-3 text-left transition-colors"
                        style={{
                          background: selected ? "var(--nf-accent-soft)" : "var(--nf-bg-surface-subtle)",
                          border: `1px solid ${selected ? "var(--nf-accent)" : "var(--nf-border-subtle)"}`,
                        }}
                      >
                        <div className="mb-1.5 flex items-center gap-1.5">
                          <span className="inline-block h-3.5 w-3.5 rounded-full" style={{ background: p.primary }} />
                          <span className="inline-block h-3.5 w-3.5 rounded-full" style={{ background: p.secondary }} />
                        </div>
                        <div className="text-xs font-semibold">{p.name}</div>
                        <div className="text-[11px]" style={{ color: "var(--nf-text-muted)" }}>
                          {p.desc}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="mt-4 flex items-center gap-3 pt-2" style={{ borderTop: "1px solid var(--nf-border-subtle)" }}>
                <span className="text-xs font-semibold">自定义强调色</span>
                <input
                  type="color"
                  disabled={isPluginLocked}
                  value={config.customAccent}
                  onChange={(e) => update({ customAccent: e.target.value, preset: "custom" })}
                  className="h-7 w-9 cursor-pointer rounded border bg-transparent"
                  style={{ borderColor: "var(--nf-border-default)" }}
                />
                <span className="font-mono text-xs" style={{ color: "var(--nf-text-muted)" }}>
                  {isPluginLocked
                    ? `由「${activePlugin.name}」插件控制`
                    : config.preset === "custom"
                      ? config.customAccent
                      : `预设：${config.preset}`}
                </span>
              </div>
            </div>
          </section>

          <section style={cardStyle} className="grid gap-3 p-4 sm:grid-cols-3">
            <div>
              <h3 className="mb-1.5 text-xs font-semibold">界面密度</h3>
              <div className="flex flex-wrap gap-1">
                {(["compact", "comfortable", "spacious"] as ThemeDensity[]).map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => update({ density: d })}
                    className="rounded px-2 py-1 text-xs"
                    style={{
                      background: config.density === d ? "var(--nf-accent-soft)" : "var(--nf-bg-surface-subtle)",
                      color: config.density === d ? "var(--nf-accent)" : "var(--nf-text-secondary)",
                    }}
                  >
                    {d === "compact" ? "紧凑" : d === "comfortable" ? "标准" : "宽松"}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <h3 className="mb-1.5 text-xs font-semibold">圆角风格</h3>
              <div className="flex flex-wrap gap-1">
                {(["sharp", "balanced", "soft"] as ThemeRadius[]).map((r) => (
                  <button
                    key={r}
                    type="button"
                    onClick={() => update({ radius: r })}
                    className="rounded px-2 py-1 text-xs"
                    style={{
                      background: config.radius === r ? "var(--nf-accent-soft)" : "var(--nf-bg-surface-subtle)",
                      color: config.radius === r ? "var(--nf-accent)" : "var(--nf-text-secondary)",
                    }}
                  >
                    {r === "sharp" ? "锐利" : r === "balanced" ? "均衡" : "柔和"}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <h3 className="mb-1.5 text-xs font-semibold">阴影层级</h3>
              <div className="flex flex-wrap gap-1">
                {(["none", "subtle", "elevated"] as ThemeShadow[]).map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => update({ shadow: s })}
                    className="rounded px-2 py-1 text-xs"
                    style={{
                      background: config.shadow === s ? "var(--nf-accent-soft)" : "var(--nf-bg-surface-subtle)",
                      color: config.shadow === s ? "var(--nf-accent)" : "var(--nf-text-secondary)",
                    }}
                  >
                    {s === "none" ? "扁平" : s === "subtle" ? "克制" : "立体"}
                  </button>
                ))}
              </div>
            </div>
          </section>
        </div>

        <div className="space-y-4">
          <section style={cardStyle} className="space-y-3 p-4">
            <h3 className="text-xs font-semibold">粘贴导入风格插件 / 主题 JSON</h3>
            <textarea
              rows={4}
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              placeholder='粘贴 nesti.style.plugin/v1 风格插件或 nesti.fluent.theme/v1 JSON…'
              className="w-full rounded-md p-2 font-mono text-xs outline-none"
              style={{ background: "var(--nf-bg-surface-subtle)", border: "1px solid var(--nf-border-default)" }}
            />
            <button
              type="button"
              onClick={() => handleImportRaw(importText)}
              disabled={!importText.trim()}
              className="rounded-md px-3 py-1.5 text-xs font-medium disabled:opacity-40"
              style={{ background: "var(--nf-accent)", color: "var(--nf-text-on-accent)" }}
            >
              安装并应用
            </button>
          </section>

          <section style={cardStyle} className="p-4">
            <h3 className="mb-2 text-xs font-semibold">当前生效配置</h3>
            <pre
              className="overflow-x-auto rounded-md p-3 font-mono text-[11px]"
              style={{ background: "var(--nf-bg-surface-subtle)", color: "var(--nf-text-secondary)" }}
            >
              {JSON.stringify(config, null, 2)}
            </pre>
          </section>
        </div>
      </div>
    </div>
  );
}
