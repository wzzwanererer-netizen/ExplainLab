import { describe, expect, it } from "vitest";
import {
  canGenerate,
  EXPERIMENT_STATUS_LABEL,
  minItems,
  MODE_META,
  MODE_ORDER,
  percent,
  scoreTone,
  selectionHint,
} from "./experiments";

describe("experiments lib", () => {
  it("三种模式元数据完整且各绑定强调色", () => {
    expect(MODE_ORDER).toEqual(["quiz", "compare", "chain"]);
    for (const kind of MODE_ORDER) {
      const meta = MODE_META[kind];
      expect(meta.label).toBeTruthy();
      expect(meta.accent.hex).toMatch(/^#[0-9a-f]{6}$/i);
      expect(meta.accent.text).toContain("text-");
      expect(meta.accent.border).toContain("border-");
    }
    expect(MODE_META.quiz.needsModel).toBe(true);
    expect(MODE_META.compare.needsModel).toBe(true);
    expect(MODE_META.chain.needsModel).toBe(false);
  });

  it("minItems 反映各模式最少条数", () => {
    expect(minItems("quiz")).toBe(1);
    expect(minItems("compare")).toBe(2);
    expect(minItems("chain")).toBe(1);
  });

  it("canGenerate 校验上下限", () => {
    expect(canGenerate("quiz", 0)).toBe(false);
    expect(canGenerate("quiz", 1)).toBe(true);
    expect(canGenerate("quiz", 9)).toBe(true);
    expect(canGenerate("compare", 1)).toBe(false);
    expect(canGenerate("compare", 2)).toBe(true);
    expect(canGenerate("compare", 3)).toBe(false);
    expect(canGenerate("chain", 0)).toBe(false);
    expect(canGenerate("chain", 1)).toBe(true);
  });

  it("selectionHint 仅在对比选满时提示", () => {
    expect(selectionHint("compare", 1)).toBeNull();
    expect(selectionHint("compare", 2)).toMatch(/最多选择 2 条/);
    expect(selectionHint("quiz", 5)).toBeNull();
    expect(selectionHint("chain", 3)).toBeNull();
  });

  it("scoreTone 三档阈值 + 颜色文字双重表达", () => {
    expect(scoreTone(0.9).label).toBe("掌握良好");
    expect(scoreTone(0.8).hex).toBe("#34d399");
    expect(scoreTone(0.5).label).toBe("仍需巩固");
    expect(scoreTone(0.49).label).toBe("建议重学");
    expect(scoreTone(0).text).toBe("text-red-300");
  });

  it("percent 四舍五入并钳制 0..1", () => {
    expect(percent(0)).toBe(0);
    expect(percent(1)).toBe(100);
    expect(percent(0.666)).toBe(67);
    expect(percent(-1)).toBe(0);
    expect(percent(2)).toBe(100);
  });

  it("状态标签覆盖进行中 / 已完成", () => {
    expect(EXPERIMENT_STATUS_LABEL.active).toBe("进行中");
    expect(EXPERIMENT_STATUS_LABEL.completed).toBe("已完成");
  });
});