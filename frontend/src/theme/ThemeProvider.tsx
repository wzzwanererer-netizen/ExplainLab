import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type ThemeMode = "light" | "dark" | "system";
export type ThemePreset = "glacier" | "iris" | "emerald" | "amber" | "graphite" | "sakura" | "custom";
export type ThemeDensity = "compact" | "comfortable" | "spacious";
export type ThemeRadius = "sharp" | "balanced" | "soft";
export type ThemeShadow = "none" | "subtle" | "elevated";

export interface NestiThemeConfig {
  schema: "nesti.fluent.theme/v1";
  mode: ThemeMode;
  preset: ThemePreset;
  customAccent: string;
  density: ThemeDensity;
  radius: ThemeRadius;
  shadow: ThemeShadow;
}

export const DEFAULT_THEME: NestiThemeConfig = {
  schema: "nesti.fluent.theme/v1",
  mode: "light",
  preset: "glacier",
  customAccent: "#2463eb",
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
  { id: "glacier", name: "Glacier Blue", desc: "默认冰蓝钴蓝", primary: "#2463EB", secondary: "#79CAFF" },
  { id: "iris", name: "Iris Purple", desc: "鸢尾蓝紫", primary: "#6D5CE7", secondary: "#A79BFF" },
  { id: "emerald", name: "Emerald Green", desc: "翡翠青绿", primary: "#0F9D75", secondary: "#6EE7B7" },
  { id: "amber", name: "Amber Orange", desc: "琥珀暖橙", primary: "#D97706", secondary: "#FCD34D" },
  { id: "graphite", name: "Graphite", desc: "石墨中性", primary: "#475569", secondary: "#94A3B8" },
  { id: "sakura", name: "Sakura Pink", desc: "樱粉柔调", primary: "#DB4B7D", secondary: "#F9A8D4" },
];

const STORAGE_KEY = "explainlab.nesti.theme.v1";

function loadStoredTheme(): NestiThemeConfig {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_THEME;
    const parsed = JSON.parse(raw) as Partial<NestiThemeConfig>;
    return { ...DEFAULT_THEME, ...parsed, schema: "nesti.fluent.theme/v1" };
  } catch {
    return DEFAULT_THEME;
  }
}

interface ThemeContextValue {
  config: NestiThemeConfig;
  resolvedTheme: "light" | "dark";
  update: (patch: Partial<NestiThemeConfig>) => void;
  reset: () => void;
  importJson: (raw: string) => boolean;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<NestiThemeConfig>(() => loadStoredTheme());
  const [systemDark, setSystemDark] = useState(() =>
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia("(prefers-color-scheme: dark)").matches
      : false,
  );

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const listener = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    mq.addEventListener("change", listener);
    return () => mq.removeEventListener("change", listener);
  }, []);

  const resolvedTheme: "light" | "dark" =
    config.mode === "system" ? (systemDark ? "dark" : "light") : config.mode;

  useEffect(() => {
    const root = document.documentElement;
    root.setAttribute("data-theme", resolvedTheme);
    root.setAttribute("data-preset", config.preset);
    root.setAttribute("data-density", config.density);
    root.setAttribute("data-radius", config.radius);
    root.setAttribute("data-shadow", config.shadow);
    if (config.preset === "custom" && /^#[0-9a-fA-F]{6}$/.test(config.customAccent)) {
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
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
    } catch {
      // ignore storage quota errors
    }
  }, [config, resolvedTheme]);

  const value = useMemo<ThemeContextValue>(
    () => ({
      config,
      resolvedTheme,
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
    [config, resolvedTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useNestiTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    return {
      config: DEFAULT_THEME,
      resolvedTheme: "light",
      update: () => {},
      reset: () => {},
      importJson: () => false,
    };
  }
  return ctx;
}
