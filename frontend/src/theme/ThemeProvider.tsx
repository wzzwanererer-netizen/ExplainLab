import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  BUILTIN_STYLE_PLUGINS,
  DEFAULT_SKIN_ID,
  loadCustomStylePlugins,
  parseExternalStylePlugin,
  saveCustomStylePlugins,
  type UIStylePlugin,
} from "./stylePlugins";

export type ThemeMode = "light" | "dark" | "system";
export type ThemePreset = "glacier" | "iris" | "emerald" | "amber" | "graphite" | "sakura" | "custom";
export type ThemeDensity = "compact" | "comfortable" | "spacious";
export type ThemeRadius = "sharp" | "balanced" | "soft";
export type ThemeShadow = "none" | "subtle" | "elevated";

export interface NestiThemeConfig {
  schema: "nesti.fluent.theme/v1";
  skinId: string;
  mode: ThemeMode;
  preset: ThemePreset;
  customAccent: string;
  density: ThemeDensity;
  radius: ThemeRadius;
  shadow: ThemeShadow;
}

export const DEFAULT_THEME: NestiThemeConfig = {
  schema: "nesti.fluent.theme/v1",
  skinId: DEFAULT_SKIN_ID,
  mode: "light",
  preset: "glacier",
  customAccent: "#3b74e8",
  density: "comfortable",
  radius: "balanced",
  shadow: "subtle",
};

export const THEME_PRESETS: {
  id: Exclude<ThemePreset, "custom">;
  name: string;
  desc: string;
  primary: string;
  secondary: string;
}[] = [
  { id: "glacier", name: "Nesti Cobalt", desc: "Nesti 官方钴蓝（默认）", primary: "#3B74E8", secondary: "#7BB8FF" },
  { id: "iris", name: "Iris Purple", desc: "鸢尾蓝紫", primary: "#6D5CE7", secondary: "#A79BFF" },
  { id: "emerald", name: "Emerald Green", desc: "翡翠青绿", primary: "#0F9D75", secondary: "#6EE7B7" },
  { id: "amber", name: "Amber Orange", desc: "琥珀暖橙", primary: "#D97706", secondary: "#FCD34D" },
  { id: "graphite", name: "Graphite", desc: "石墨中性", primary: "#475569", secondary: "#94A3B8" },
  { id: "sakura", name: "Sakura Pink", desc: "樱粉柔调", primary: "#DB4B7D", secondary: "#F9A8D4" },
];

const STORAGE_KEY = "explainlab.nesti.theme.v1";
const CUSTOM_SKIN_STYLE_ID = "nesti-custom-skin-style";

function loadStoredTheme(): NestiThemeConfig {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_THEME;
    const parsed = JSON.parse(raw) as Partial<NestiThemeConfig>;
    return {
      ...DEFAULT_THEME,
      ...parsed,
      skinId: typeof parsed.skinId === "string" && parsed.skinId ? parsed.skinId : DEFAULT_SKIN_ID,
      schema: "nesti.fluent.theme/v1",
    };
  } catch {
    return DEFAULT_THEME;
  }
}

interface ThemeContextValue {
  config: NestiThemeConfig;
  resolvedTheme: "light" | "dark";
  stylePlugins: UIStylePlugin[];
  activePlugin: UIStylePlugin;
  isPluginLocked: boolean;
  setSkin: (skinId: string) => void;
  addStylePlugin: (plugin: UIStylePlugin) => void;
  installStylePlugin: (rawJson: string) => { ok: boolean; plugin?: UIStylePlugin };
  removeStylePlugin: (pluginId: string) => void;
  update: (patch: Partial<NestiThemeConfig>) => void;
  reset: () => void;
  importJson: (raw: string) => boolean;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<NestiThemeConfig>(() => loadStoredTheme());
  const [customPlugins, setCustomPlugins] = useState<UIStylePlugin[]>(() =>
    loadCustomStylePlugins(),
  );
  const [systemDark, setSystemDark] = useState(() =>
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia("(prefers-color-scheme: dark)").matches
      : false,
  );

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia === "function" === false) return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const listener = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    mq.addEventListener("change", listener);
    return () => mq.removeEventListener("change", listener);
  }, []);

  const stylePlugins = useMemo(
    () => [...BUILTIN_STYLE_PLUGINS, ...customPlugins],
    [customPlugins],
  );

  const activePlugin = useMemo(
    () => stylePlugins.find((p) => p.id === config.skinId) ?? BUILTIN_STYLE_PLUGINS[0],
    [stylePlugins, config.skinId],
  );

  const isPluginLocked = activePlugin.id !== DEFAULT_SKIN_ID;

  const resolvedTheme: "light" | "dark" = activePlugin.lockedMode
    ? activePlugin.lockedMode
    : config.mode === "system"
      ? systemDark
        ? "dark"
        : "light"
      : config.mode;

  useEffect(() => {
    const root = document.documentElement;
    root.setAttribute("data-skin", activePlugin.id);
    root.setAttribute("data-theme", resolvedTheme);
    root.setAttribute("data-preset", config.preset);
    root.setAttribute("data-density", config.density);
    root.setAttribute("data-radius", config.radius);
    root.setAttribute("data-shadow", config.shadow);

    // 非默认风格插件接管主题色，清除自定义强调色行内覆盖
    if (!isPluginLocked && config.preset === "custom" && /^#[0-9a-fA-F]{6}$/.test(config.customAccent)) {
      root.style.setProperty("--nf-accent", config.customAccent);
      root.style.setProperty("--nf-accent-hover", config.customAccent);
      root.style.setProperty("--nf-module-icon", config.customAccent);
      root.style.setProperty("--nf-accent-soft", `${config.customAccent}1f`);
      root.style.setProperty("--nf-accent-border", `${config.customAccent}55`);
    } else {
      ["--nf-accent", "--nf-accent-hover", "--nf-module-icon", "--nf-accent-soft", "--nf-accent-border"].forEach((k) =>
        root.style.removeProperty(k),
      );
    }

    // 动态挂载外部导入插件的自定义 Token 与 CSS
    let styleEl = document.getElementById(CUSTOM_SKIN_STYLE_ID) as HTMLStyleElement | null;
    if (!activePlugin.builtin && (activePlugin.tokens || activePlugin.customCss)) {
      if (!styleEl) {
        styleEl = document.createElement("style");
        styleEl.id = CUSTOM_SKIN_STYLE_ID;
        document.head.appendChild(styleEl);
      }
      const tokenLines = activePlugin.tokens
        ? Object.entries(activePlugin.tokens)
            .filter(([k]) => k.startsWith("--"))
            .map(([k, v]) => `  ${k}: ${v};`)
            .join("\n")
        : "";
      styleEl.textContent = `html[data-skin="${activePlugin.id}"] {\n${tokenLines}\n}\n${activePlugin.customCss ?? ""}`;
    } else if (styleEl) {
      styleEl.remove();
    }

    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
    } catch {
      // ignore storage quota errors
    }
  }, [config, resolvedTheme, activePlugin, isPluginLocked]);

  const value = useMemo<ThemeContextValue>(
    () => ({
      config,
      resolvedTheme,
      stylePlugins,
      activePlugin,
      isPluginLocked,
      setSkin: (skinId) => setConfig((prev) => ({ ...prev, skinId })),
      addStylePlugin: (plugin) => {
        setCustomPlugins((prev) => {
          const next = [...prev.filter((p) => p.id !== plugin.id), plugin];
          saveCustomStylePlugins(next);
          return next;
        });
        setConfig((prev) => ({ ...prev, skinId: plugin.id }));
      },
      installStylePlugin: (rawJson) => {
        const plugin = parseExternalStylePlugin(rawJson);
        if (!plugin) return { ok: false };
        setCustomPlugins((prev) => {
          const next = [...prev.filter((p) => p.id !== plugin.id), plugin];
          saveCustomStylePlugins(next);
          return next;
        });
        setConfig((prev) => ({ ...prev, skinId: plugin.id }));
        return { ok: true, plugin };
      },
      removeStylePlugin: (pluginId) => {
        setCustomPlugins((prev) => {
          const next = prev.filter((p) => p.id !== pluginId);
          saveCustomStylePlugins(next);
          return next;
        });
        setConfig((prev) =>
          prev.skinId === pluginId ? { ...prev, skinId: DEFAULT_SKIN_ID } : prev,
        );
      },
      update: (patch) => setConfig((prev) => ({ ...prev, ...patch })),
      reset: () => setConfig(DEFAULT_THEME),
      importJson: (raw) => {
        try {
          const parsed = JSON.parse(raw) as Partial<NestiThemeConfig>;
          if (parsed.schema && parsed.schema !== "nesti.fluent.theme/v1") return false;
          setConfig({ ...DEFAULT_THEME, ...parsed, schema: "nesti.fluent.theme/v1" });
          return true;
        } catch {
          return false;
        }
      },
    }),
    [config, resolvedTheme, stylePlugins, activePlugin, isPluginLocked],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useNestiTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    return {
      config: DEFAULT_THEME,
      resolvedTheme: "light",
      stylePlugins: BUILTIN_STYLE_PLUGINS,
      activePlugin: BUILTIN_STYLE_PLUGINS[0],
      isPluginLocked: false,
      setSkin: () => {},
      addStylePlugin: () => {},
      installStylePlugin: () => ({ ok: false }),
      removeStylePlugin: () => {},
      update: () => {},
      reset: () => {},
      importJson: () => false,
    };
  }
  return ctx;
}
