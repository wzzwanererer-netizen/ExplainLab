/**
 * M5 交互式知识实验的纯逻辑模块（无 DOM / React）。
 *
 * 模式元数据（标签 / 说明 / 选择约束 / 主题色）、生成校验与得分色调，
 * 便于在 jsdom 中单测；视觉类名以完整字面量给出，确保 Tailwind v4 能扫描到。
 * 三种模式各自绑定一个强调色族：测验=琥珀、对比=天蓝、路径=翡翠。
 */
import type { ExperimentKind, ExperimentStatus } from "../api/types";

export interface ModeAccent {
  /** 强调文本色（完整 Tailwind 类名）。 */
  text: string;
  /** 选中态边框。 */
  border: string;
  /** 选中态底色。 */
  bg: string;
  /** 徽章底色 + 文本。 */
  badge: string;
  /** 进度 / 得分环描边色（hex，供 SVG 使用）。 */
  hex: string;
}

export interface ModeMeta {
  kind: ExperimentKind;
  label: string;
  tagline: string;
  description: string;
  /** 选择知识的最小 / 最大条数（max 为 null 表示不限）。 */
  min: number;
  max: number | null;
  requirement: string;
  needsModel: boolean;
  accent: ModeAccent;
}

export const MODE_META: Record<ExperimentKind, ModeMeta> = {
  quiz: {
    kind: "quiz",
    label: "知识测验",
    tagline: "出题检验理解",
    description: "围绕所选知识自动出题，作答后即时判分并给出解析与来源。",
    min: 1,
    max: null,
    requirement: "至少选择 1 条知识",
    needsModel: true,
    accent: {
      text: "text-amber-300",
      border: "border-amber-500/50",
      bg: "bg-amber-500/10",
      badge: "bg-amber-500/15 text-amber-300",
      hex: "#fbbf24",
    },
  },
  compare: {
    kind: "compare",
    label: "知识对比",
    tagline: "辨析异同关系",
    description: "并排对比两条知识，结构化呈现相同点、不同点与关系判定。",
    min: 2,
    max: 2,
    requirement: "恰好选择 2 条知识",
    needsModel: true,
    accent: {
      text: "text-sky-300",
      border: "border-sky-500/50",
      bg: "bg-sky-500/10",
      badge: "bg-sky-500/15 text-sky-300",
      hex: "#38bdf8",
    },
  },
  chain: {
    kind: "chain",
    label: "学习路径",
    tagline: "先修优先编排",
    description: "沿依赖 / 细化关系回溯先修知识，确定性地编排一条学习路径。",
    min: 1,
    max: null,
    requirement: "至少选择 1 条知识（作为终点）",
    needsModel: false,
    accent: {
      text: "text-emerald-300",
      border: "border-emerald-500/50",
      bg: "bg-emerald-500/10",
      badge: "bg-emerald-500/15 text-emerald-300",
      hex: "#34d399",
    },
  },
};

export const MODE_ORDER: ExperimentKind[] = ["quiz", "compare", "chain"];

export const EXPERIMENT_STATUS_LABEL: Record<ExperimentStatus, string> = {
  active: "进行中",
  completed: "已完成",
};

/** 该模式所需的最少知识条数。 */
export function minItems(mode: ExperimentKind): number {
  return MODE_META[mode].min;
}

/** 当前选择是否满足生成条件。 */
export function canGenerate(mode: ExperimentKind, selectedCount: number): boolean {
  const { min, max } = MODE_META[mode];
  return selectedCount >= min && (max === null || selectedCount <= max);
}

/** 选择上限提示：对比模式选满 2 条后继续点选时给出。 */
export function selectionHint(mode: ExperimentKind, selectedCount: number): string | null {
  const { max } = MODE_META[mode];
  if (max !== null && selectedCount >= max) {
    return `${MODE_META[mode].label}最多选择 ${max} 条，请先取消已选项。`;
  }
  return null;
}

export interface ScoreTone {
  label: string;
  hex: string;
  text: string;
}

/** 得分色调：>=0.8 翡翠、>=0.5 琥珀、其余红，直接以颜色 + 文字双重表达。 */
export function scoreTone(score: number): ScoreTone {
  if (score >= 0.8) return { label: "掌握良好", hex: "#34d399", text: "text-emerald-300" };
  if (score >= 0.5) return { label: "仍需巩固", hex: "#fbbf24", text: "text-amber-300" };
  return { label: "建议重学", hex: "#f87171", text: "text-red-300" };
}

/** 0..1 得分 → 百分比整数。 */
export function percent(score: number): number {
  return Math.round(Math.max(0, Math.min(1, score)) * 100);
}