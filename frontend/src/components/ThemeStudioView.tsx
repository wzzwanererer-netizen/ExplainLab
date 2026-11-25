import { useState } from "react";
import {
  THEME_PRESETS,
  useNestiTheme,
  type ThemeDensity,
  type ThemeMode,
  type ThemeRadius,
  type ThemeShadow,
} from "../theme/ThemeProvider";
import { Icon } from "./Icons";

export function ThemeStudioView() {
  const { config, resolvedTheme, update, reset, importJson } = useNestiTheme();
  const [importText, setImportText] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  const cardStyle = {
    background: "var(--nf-bg-surface)",
    border: "1px solid var(--nf-border-subtle)",
    borderRadius: "var(--nf-radius-md)",
    boxShadow: "var(--nf-shadow-sm)",
  };

  function handleExport() {
    const json = JSON.stringify(config, null, 2);
    void navigator.clipboard?.writeText(json);
    setNotice("已复制主题 JSON 到剪贴板（nesti.fluent.theme/v1）。");
  }

  function handleImport() {
    if (importJson(importText)) {
      setNotice("已导入自定义主题配置。");
      setImportText("");
    } else {
      setNotice("主题 JSON 格式无效，请检查后重试。");
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3" style={cardStyle}>
        <div>
          <h2 className="text-sm font-semibold">Theme Studio · Nesti Fluent</h2>
          <p className="text-xs" style={{ color: "var(--nf-text-muted)" }}>
            实时切换浅/深模式、六套官方预设、自定义强调色与界面密度，配置自动保存至本地。
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={handleExport}
            className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium"
            style={{ background: "var(--nf-bg-surface-subtle)", border: "1px solid var(--nf-border-default)" }}
          >
            <Icon name="download" size={14} /> 导出 JSON
          </button>
          <button
            type="button"
            onClick={() => {
              reset();
              setNotice("已恢复 Glacier Blue 默认主题。");
            }}
            className="rounded-md px-3 py-1.5 text-xs font-medium"
            style={{ background: "var(--nf-bg-surface-subtle)", border: "1px solid var(--nf-border-default)" }}
          >
            恢复默认
          </button>
        </div>
      </div>

      {notice && (
        <div
          role="status"
          className="rounded-md px-3 py-2 text-xs"
          style={{ background: "var(--nf-accent-soft)", color: "var(--nf-accent)", border: "1px solid var(--nf-accent-border)" }}
        >
          {notice}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
        <div className="space-y-4">
          <section style={cardStyle} className="space-y-4 p-4">
            <div>
              <h3 className="mb-2 text-xs font-semibold">外观模式（当前：{resolvedTheme}）</h3>
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
              <h3 className="mb-2 text-xs font-semibold">六套官方预设主题</h3>
              <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
                {THEME_PRESETS.map((p) => {
                  const selected = config.preset === p.id;
                  return (
                    <button
                      key={p.id}
                      type="button"
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

            <div className="flex items-center gap-3 pt-2" style={{ borderTop: "1px solid var(--nf-border-subtle)" }}>
              <span className="text-xs font-semibold">自定义强调色</span>
              <input
                type="color"
                value={config.customAccent}
                onChange={(e) => update({ customAccent: e.target.value, preset: "custom" })}
                className="h-7 w-9 cursor-pointer rounded border bg-transparent"
                style={{ borderColor: "var(--nf-border-default)" }}
              />
              <span className="font-mono text-xs" style={{ color: "var(--nf-text-muted)" }}>
                {config.preset === "custom" ? config.customAccent : `预设：${config.preset}`}
              </span>
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
            <h3 className="text-xs font-semibold">导入主题 JSON</h3>
            <textarea
              rows={4}
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              placeholder='粘贴 nesti.fluent.theme/v1 JSON…'
              className="w-full rounded-md p-2 font-mono text-xs outline-none"
              style={{ background: "var(--nf-bg-surface-subtle)", border: "1px solid var(--nf-border-default)" }}
            />
            <button
              type="button"
              onClick={handleImport}
              disabled={!importText.trim()}
              className="rounded-md px-3 py-1.5 text-xs font-medium disabled:opacity-40"
              style={{ background: "var(--nf-accent)", color: "var(--nf-text-on-accent)" }}
            >
              应用 JSON 主题
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
