# 02 · Design Tokens（CSS Custom Properties + Tailwind CSS v4）

完整可运行令牌定义见 [prototype/tokens.css](prototype/tokens.css)。架构严格分为三层，**严禁在业务组件内硬编码品牌色值**：

## 1. 三层令牌体系

1. **Brand Primitive Tokens（`--nf-brand-*`）**：不可变品牌原色（`#2463EB`、`#79CAFF`、`#8785EF`、`#E5EDFA`、`#F5F8FC`、`#243247`）。
2. **Semantic Tokens（`--nf-bg-*` / `--nf-text-*` / `--nf-border-*` / `--nf-status-*` / `--nf-accent-*`）**：随 `[data-theme="light|dark"]` 与 `[data-preset="glacier|iris|emerald|amber|graphite|sakura|custom"]` 动态切换。
3. **Component Tokens（`--nf-titlebar-h` / `--nf-rail-w` / `--nf-subnav-w` / `--nf-inspector-w` / `--nf-graph-edge-*`）**：供 Shell、表格、检查器与 React Flow SVG 边消费。

## 2. Tailwind CSS v4 `@theme` 映射契约

```css
@import "tailwindcss";
@theme {
  --color-window: var(--nf-bg-window);
  --color-canvas: var(--nf-bg-canvas);
  --color-surface: var(--nf-bg-surface);
  --color-accent: var(--nf-accent);
  --color-ink: var(--nf-text-primary);
  --color-ink-secondary: var(--nf-text-secondary);
  --color-ink-muted: var(--nf-text-muted);
  --color-border-subtle: var(--nf-border-subtle);
  --radius-sm: var(--nf-radius-sm);
  --radius-md: var(--nf-radius-md);
  --radius-lg: var(--nf-radius-lg);
}
```

## 3. 排版、间距、圆角与阴影标尺

- **字体族**：无衬线 `"Segoe UI Variable", "Segoe UI", "PingFang SC", "Microsoft YaHei UI", system-ui, sans-serif`；等宽 `"Cascadia Code", "JetBrains Mono", Consolas, monospace`（用于 UUID、SHA-256、RRF 分数、diff 与快捷键）。
- **字号阶梯**：`11px`（元数据/徽章）/ `12px`（次级与表格辅助）/ `13px`（桌面正文基准）/ `14px`（工具栏标题）/ `15px`（文档详情标题）。
- **密度三档（`data-density`）**：`compact`（行高 `30px`、控件 `26px`）/ `comfortable`（默认，`36px` / `30px`）/ `spacious`（`44px` / `34px`）。
- **圆角三档（`data-radius`）**：`sharp`（`2–6px`）/ `balanced`（默认，`4–10px`）/ `soft`（`6–14px`）。严禁使用超大 `24px+` 胶囊卡片。
- **阴影三档（`data-shadow`）**：`none`（纯 1px 描边扁平）/ `subtle`（默认，克制桌面抬升）/ `elevated`（更强层次，用于弹窗与浮层）。
