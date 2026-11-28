/**
 * Nesti UI 风格插件注册表（Style Plugin Registry）
 *
 * - 内置 6 套精选风格：
 *   1. Nesti Fluent（官方默认）
 *   2. 未来赛博（Cybernetic Terminal）
 *   3. 复古图书馆（Classical Library）
 *   4. 极简墨水屏（E-Ink Zen）
 *   5. 森系护眼（Nordic Matcha）
 *   6. 爵士黑金（Noir Gold）
 * - 支持可视化风格制作器（Style Builder）、AI 一句话生成风格、外部 .json 文件导入与卸载。
 */

export type StyleFontMood = "sans" | "serif" | "mono";
export type StyleCanvasTexture = "none" | "grid" | "dots" | "aurora";
export type StyleCornerStyle = "sharp" | "balanced" | "soft";

export interface StylePluginPreview {
  windowBg: string;
  sidebarBg: string;
  canvasBg: string;
  cardBg: string;
  accent: string;
  secondary: string;
  text: string;
  border: string;
}

export interface UIStylePlugin {
  schema?: "nesti.style.plugin/v1";
  id: string;
  name: string;
  englishName: string;
  description: string;
  author: string;
  version: string;
  builtin?: boolean;
  /** 非默认风格插件可锁定深浅色模式与主题色，防止手动调色破坏整体视觉氛围。 */
  lockedMode: "light" | "dark" | null;
  tags: string[];
  preview: StylePluginPreview;
  /** 外部/自定义插件覆写的 CSS 变量表 */
  tokens?: Record<string, string>;
  /** 外部/自定义插件附加样式 */
  customCss?: string;
}

export interface StyleBuilderDraft {
  name: string;
  englishName?: string;
  description?: string;
  author?: string;
  mode: "light" | "dark";
  canvasBg: string;
  cardBg: string;
  accent: string;
  secondary: string;
  fontMood: StyleFontMood;
  texture: StyleCanvasTexture;
  cornerStyle: StyleCornerStyle;
}

export const DEFAULT_SKIN_ID = "nesti-fluent";

export const BUILTIN_STYLE_PLUGINS: UIStylePlugin[] = [
  {
    schema: "nesti.style.plugin/v1",
    id: "nesti-fluent",
    name: "Nesti Fluent 官方默认",
    englishName: "Nesti Fluent 2.0",
    description:
      "冰雾瓷白与钴蓝呼吸感，支持自由切换浅/深色模式、六套官方配色与自定义强调色。",
    author: "Nesti Official",
    version: "2.0.0",
    builtin: true,
    lockedMode: null,
    tags: ["官方默认", "可自由配色", "现代极简"],
    preview: {
      windowBg: "#edf3fc",
      sidebarBg: "#eef4fd",
      canvasBg: "#fafbfd",
      cardBg: "#ffffff",
      accent: "#3b74e8",
      secondary: "#7bb8ff",
      text: "#1e2433",
      border: "rgba(30,36,51,0.12)",
    },
  },
  {
    schema: "nesti.style.plugin/v1",
    id: "cyber-neon",
    name: "未来赛博",
    englishName: "Cybernetic Terminal",
    description:
      "深空黑曜底色叠加 HUD 坐标网格、霓虹青与品红双色辉光、锐利切角与终端等宽质感。",
    author: "Nesti Style Lab",
    version: "1.0.0",
    builtin: true,
    lockedMode: "dark",
    tags: ["赛博朋克", "霓虹 HUD", "深色专属"],
    preview: {
      windowBg: "#050814",
      sidebarBg: "#080e20",
      canvasBg: "#070c1a",
      cardBg: "#0d162c",
      accent: "#00e5ff",
      secondary: "#ff2e93",
      text: "#e6f7ff",
      border: "rgba(0,229,255,0.28)",
    },
  },
  {
    schema: "nesti.style.plugin/v1",
    id: "vintage-library",
    name: "复古图书馆",
    englishName: "Classical Library",
    description:
      "温润羊皮书页底色、胡桃木侧栏、勃艮第酒红与烫金古铜点缀，搭配经典衬线书卷排版。",
    author: "Nesti Style Lab",
    version: "1.0.0",
    builtin: true,
    lockedMode: "light",
    tags: ["书卷典藏", "羊皮护眼", "复古衬线"],
    preview: {
      windowBg: "#e6dac4",
      sidebarBg: "#e9dec9",
      canvasBg: "#f5efe2",
      cardBg: "#fbf7ef",
      accent: "#8c3228",
      secondary: "#b38236",
      text: "#2b2118",
      border: "rgba(92,68,42,0.22)",
    },
  },
  {
    schema: "nesti.style.plugin/v1",
    id: "eink-zen",
    name: "极简墨水屏",
    englishName: "E-Ink Zen",
    description:
      "Kindle / reMarkable 电子纸质感，微暖宣纸白与纯炭黑高对比，零阴影零干扰专注长文阅读。",
    author: "Nesti Style Lab",
    version: "1.0.0",
    builtin: true,
    lockedMode: "light",
    tags: ["电子纸", "零干扰阅读", "极简黑白"],
    preview: {
      windowBg: "#f2f1ec",
      sidebarBg: "#f4f3ee",
      canvasBg: "#faf9f5",
      cardBg: "#ffffff",
      accent: "#181817",
      secondary: "#6b6a65",
      text: "#141413",
      border: "rgba(20,20,19,0.24)",
    },
  },
  {
    schema: "nesti.style.plugin/v1",
    id: "nordic-matcha",
    name: "森系护眼",
    englishName: "Nordic Matcha",
    description:
      "低饱和鼠尾草绿与温润松林色调，柔和圆角极低视觉疲劳，专为长时间深度工作与护眼打造。",
    author: "Nesti Style Lab",
    version: "1.0.0",
    builtin: true,
    lockedMode: "light",
    tags: ["护眼首选", "清新森系", "低饱和"],
    preview: {
      windowBg: "#e3ece4",
      sidebarBg: "#e7efe8",
      canvasBg: "#f2f6f2",
      cardBg: "#fafcfa",
      accent: "#2c6b54",
      secondary: "#6ea388",
      text: "#1c2b24",
      border: "rgba(44,107,84,0.18)",
    },
  },
  {
    schema: "nesti.style.plugin/v1",
    id: "noir-gold",
    name: "爵士黑金",
    englishName: "Noir Gold Atelier",
    description:
      "暖炭黑底搭配哑光香槟金与优雅衬线标题，克制沉稳、夜间不刺眼的高级工作室氛围。",
    author: "Nesti Style Lab",
    version: "1.0.0",
    builtin: true,
    lockedMode: "dark",
    tags: ["夜间创作", "黑金高级", "温暖深色"],
    preview: {
      windowBg: "#0f0e0c",
      sidebarBg: "#141210",
      canvasBg: "#131210",
      cardBg: "#1c1a17",
      accent: "#d4a853",
      secondary: "#a47a32",
      text: "#f3ece0",
      border: "rgba(212,168,83,0.24)",
    },
  },
];

const CUSTOM_PLUGINS_STORAGE_KEY = "explainlab.nesti.stylePlugins.v1";

function normalizeHex(hex: string, fallback: string): string {
  const s = (hex || "").trim();
  return /^#[0-9a-fA-F]{6}$/.test(s) ? s.toLowerCase() : fallback;
}

function hexToRgb(hex: string): [number, number, number] {
  const h = normalizeHex(hex, "#3b74e8").slice(1);
  return [
    parseInt(h.slice(0, 2), 16),
    parseInt(h.slice(2, 4), 16),
    parseInt(h.slice(4, 6), 16),
  ];
}

function mixHex(a: string, b: string, weightB: number): string {
  const [r1, g1, b1] = hexToRgb(a);
  const [r2, g2, b2] = hexToRgb(b);
  const w = Math.max(0, Math.min(1, weightB));
  const r = Math.round(r1 * (1 - w) + r2 * w);
  const g = Math.round(g1 * (1 - w) + g2 * w);
  const bl = Math.round(b1 * (1 - w) + b2 * w);
  return `#${[r, g, bl].map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

function isColorLight(hex: string): boolean {
  const [r, g, b] = hexToRgb(hex);
  const luma = 0.299 * r + 0.587 * g + 0.114 * b;
  return luma > 155;
}

/** 将可视化风格制作器或 AI 生成的简化草稿，自动编译为完整的 UIStylePlugin 插件对象 */
export function buildStylePluginFromDraft(draft: StyleBuilderDraft): UIStylePlugin {
  const isDark = draft.mode === "dark";
  const canvasBg = normalizeHex(draft.canvasBg, isDark ? "#0d111a" : "#f7f8fb");
  const cardBg = normalizeHex(draft.cardBg, isDark ? "#151b29" : "#ffffff");
  const accent = normalizeHex(draft.accent, isDark ? "#5b91ff" : "#3b74e8");
  const secondary = normalizeHex(draft.secondary, mixHex(accent, isDark ? "#ffffff" : "#94a3b8", 0.35));

  const windowBg = mixHex(canvasBg, isDark ? "#000000" : accent, isDark ? 0.24 : 0.08);
  const sidebarBg = mixHex(canvasBg, isDark ? "#000000" : accent, isDark ? 0.14 : 0.06);
  const subtleBg = mixHex(cardBg, canvasBg, 0.55);
  const hoverBg = mixHex(cardBg, accent, isDark ? 0.16 : 0.09);
  const activeBg = mixHex(cardBg, accent, isDark ? 0.24 : 0.15);

  const textPrimary = isDark ? "#eef3fb" : "#1c222e";
  const textSecondary = isDark ? "#a5b4cb" : "#525f75";
  const textMuted = isDark ? "#6e7e98" : "#8391a6";
  const textOnAccent = isColorLight(accent) ? "#111622" : "#ffffff";

  const [ar, ag, ab] = hexToRgb(accent);
  const borderSubtle = isDark ? `rgba(${ar},${ag},${ab},0.16)` : `rgba(30,36,51,0.10)`;
  const borderDefault = isDark ? `rgba(${ar},${ag},${ab},0.28)` : `rgba(30,36,51,0.17)`;
  const borderStrong = isDark ? `rgba(${ar},${ag},${ab},0.46)` : `rgba(${ar},${ag},${ab},0.34)`;

  const fontStack =
    draft.fontMood === "serif"
      ? '"Georgia", "Songti SC", "STSong", "Noto Serif SC", "Microsoft YaHei UI", serif'
      : draft.fontMood === "mono"
        ? '"Cascadia Code", "JetBrains Mono", "Segoe UI", "Microsoft YaHei UI", monospace'
        : '"Segoe UI Variable Text", "Segoe UI", "PingFang SC", "Microsoft YaHei UI", sans-serif';

  const radius =
    draft.cornerStyle === "sharp"
      ? { xs: "2px", sm: "3px", md: "5px", lg: "7px" }
      : draft.cornerStyle === "soft"
        ? { xs: "6px", sm: "10px", md: "14px", lg: "18px" }
        : { xs: "4px", sm: "7px", md: "10px", lg: "14px" };

  const slug = `custom-${Date.now().toString(36)}`;
  const [sr, sg, sb] = hexToRgb(secondary);

  let textureCss = "";
  if (draft.texture === "grid") {
    textureCss = `html[data-skin="${slug}"] .nf-workspace-pane { background-image: linear-gradient(rgba(${ar},${ag},${ab},0.055) 1px, transparent 1px), linear-gradient(90deg, rgba(${ar},${ag},${ab},0.055) 1px, transparent 1px); background-size: 28px 28px; }`;
  } else if (draft.texture === "dots") {
    textureCss = `html[data-skin="${slug}"] .nf-workspace-pane { background-image: radial-gradient(rgba(${ar},${ag},${ab},0.11) 1px, transparent 0); background-size: 20px 20px; }`;
  } else if (draft.texture === "aurora") {
    textureCss = `html[data-skin="${slug}"] .nf-workspace-pane { background-image: radial-gradient(ellipse 65% 50% at 15% 0%, rgba(${ar},${ag},${ab},0.10) 0%, transparent 60%), radial-gradient(ellipse 55% 45% at 95% 100%, rgba(${sr},${sg},${sb},0.09) 0%, transparent 60%); }`;
  }

  const tokens: Record<string, string> = {
    "--nf-brand-primary": accent,
    "--nf-brand-glacier": secondary,
    "--nf-bg-window": windowBg,
    "--nf-mica-window": `linear-gradient(145deg, ${windowBg} 0%, ${sidebarBg} 55%, ${windowBg} 100%)`,
    "--nf-bg-canvas": canvasBg,
    "--nf-bg-surface": cardBg,
    "--nf-bg-surface-subtle": subtleBg,
    "--nf-bg-surface-hover": hoverBg,
    "--nf-bg-surface-active": activeBg,
    "--nf-bg-glass": isDark ? "rgba(15, 20, 32, 0.86)" : "rgba(255, 255, 255, 0.86)",
    "--nf-text-primary": textPrimary,
    "--nf-text-secondary": textSecondary,
    "--nf-text-muted": textMuted,
    "--nf-text-on-accent": textOnAccent,
    "--nf-border-subtle": borderSubtle,
    "--nf-border-default": borderDefault,
    "--nf-border-strong": borderStrong,
    "--nf-accent": `${accent} !important`,
    "--nf-accent-hover": `${mixHex(accent, isDark ? "#ffffff" : "#000000", 0.14)} !important`,
    "--nf-accent-secondary": secondary,
    "--nf-accent-soft": `rgba(${ar},${ag},${ab},${isDark ? 0.18 : 0.11}) !important`,
    "--nf-accent-subtle": `rgba(${ar},${ag},${ab},${isDark ? 0.10 : 0.06})`,
    "--nf-accent-border": `rgba(${ar},${ag},${ab},${isDark ? 0.42 : 0.30}) !important`,
    "--nf-module-icon": `${accent} !important`,
    "--nf-radius-xs": radius.xs,
    "--nf-radius-sm": radius.sm,
    "--nf-radius-md": radius.md,
    "--nf-radius-lg": radius.lg,
    "--nf-font-sans": fontStack,
    "--nf-font-display": fontStack,
    "--nf-graph-grid": isDark ? `rgba(${ar},${ag},${ab},0.16)` : `rgba(30,36,51,0.10)`,
    "--nf-graph-edge-depends": accent,
    "--nf-graph-edge-refines": secondary,
    "--nesti-accent": accent,
    "--nesti-surface-0": canvasBg,
    "--nesti-surface-1": cardBg,
    "--nesti-surface-2": subtleBg,
    "--nesti-surface-hover": hoverBg,
    "--nesti-border-subtle": borderSubtle,
    "--nesti-border-strong": borderDefault,
    "--nesti-text-primary": textPrimary,
    "--nesti-text-secondary": textSecondary,
    "--nesti-text-tertiary": textMuted,
  };

  return {
    schema: "nesti.style.plugin/v1",
    id: slug,
    name: (draft.name || "我的自定义风格").trim().slice(0, 36),
    englishName: (draft.englishName || "Custom Style").trim().slice(0, 48),
    description:
      (draft.description || "通过 Nesti 风格工坊定制生成的个人专属 UI 风格插件。").trim().slice(0, 140),
    author: (draft.author || "My Studio").trim().slice(0, 28),
    version: "1.0.0",
    builtin: false,
    lockedMode: draft.mode,
    tags: [
      draft.mode === "dark" ? "深色定制" : "浅色定制",
      draft.fontMood === "serif" ? "衬线体" : draft.fontMood === "mono" ? "等宽体" : "无衬线",
      draft.author === "Nesti AI" ? "AI 生成" : "自创风格",
    ],
    preview: {
      windowBg,
      sidebarBg,
      canvasBg,
      cardBg,
      accent,
      secondary,
      text: textPrimary,
      border: borderDefault,
    },
    tokens,
    customCss: textureCss,
  };
}

export function loadCustomStylePlugins(): UIStylePlugin[] {
  try {
    const raw = window.localStorage.getItem(CUSTOM_PLUGINS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (p): p is UIStylePlugin =>
        Boolean(p) &&
        typeof p.id === "string" &&
        typeof p.name === "string" &&
        Boolean(p.preview),
    );
  } catch {
    return [];
  }
}

export function saveCustomStylePlugins(plugins: UIStylePlugin[]): void {
  try {
    window.localStorage.setItem(CUSTOM_PLUGINS_STORAGE_KEY, JSON.stringify(plugins));
  } catch {
    // ignore quota errors
  }
}

export function parseExternalStylePlugin(raw: string): UIStylePlugin | null {
  try {
    const parsed = JSON.parse(raw) as Partial<UIStylePlugin>;
    if (parsed.schema && parsed.schema !== "nesti.style.plugin/v1") return null;
    if (!parsed.id || !/^[a-z0-9][a-z0-9-_]{1,40}$/i.test(parsed.id)) return null;
    if (BUILTIN_STYLE_PLUGINS.some((b) => b.id === parsed.id)) return null;
    if (!parsed.name || typeof parsed.name !== "string") return null;

    const accent = parsed.preview?.accent || parsed.tokens?.["--nf-accent"] || "#3b74e8";
    const canvasBg = parsed.preview?.canvasBg || parsed.tokens?.["--nf-bg-canvas"] || "#111827";
    const cardBg = parsed.preview?.cardBg || parsed.tokens?.["--nf-bg-surface"] || "#1f2937";
    const text = parsed.preview?.text || parsed.tokens?.["--nf-text-primary"] || "#f8fafc";

    return {
      schema: "nesti.style.plugin/v1",
      id: parsed.id,
      name: parsed.name.slice(0, 40),
      englishName: (parsed.englishName || parsed.id).slice(0, 48),
      description: (parsed.description || "外部导入的自定义 UI 风格插件").slice(0, 140),
      author: (parsed.author || "Community").slice(0, 32),
      version: (parsed.version || "1.0.0").slice(0, 16),
      builtin: false,
      lockedMode: parsed.lockedMode === "light" || parsed.lockedMode === "dark" ? parsed.lockedMode : "dark",
      tags: Array.isArray(parsed.tags) ? parsed.tags.slice(0, 3).map(String) : ["自定义插件"],
      preview: {
        windowBg: parsed.preview?.windowBg || canvasBg,
        sidebarBg: parsed.preview?.sidebarBg || canvasBg,
        canvasBg,
        cardBg,
        accent,
        secondary: parsed.preview?.secondary || accent,
        text,
        border: parsed.preview?.border || "rgba(148,163,184,0.25)",
      },
      tokens: parsed.tokens && typeof parsed.tokens === "object" ? parsed.tokens : undefined,
      customCss: typeof parsed.customCss === "string" ? parsed.customCss : undefined,
    };
  } catch {
    return null;
  }
}
