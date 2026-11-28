import { useCallback, useEffect, useRef, useState } from "react";

import type { RelationType } from "../api/types";
import type { MapElements } from "../lib/graphLayout";
import {
  createForceSimulation,
  getNeighborhood,
  stepForceSimulation,
  type ForceConfig,
  type ForceNode,
  type ForceSimulation,
} from "../lib/obsidianForce";

export interface ObsidianGraphCanvasProps {
  elements: MapElements;
  edgeTypes: Map<string, RelationType>;
  nodeColors?: Map<string, string>;
  selectedId: string | null;
  searchQuery: string;
  config: ForceConfig;
  showArrows: boolean;
  showEdgeLabels: boolean;
  reheatToken: number;
  onSelectNode: (id: string) => void;
  onDoubleClickNode?: (id: string) => void;
}

interface Camera {
  x: number;
  y: number;
  scale: number;
}

interface ThemeColors {
  isDark: boolean;
  bg: string;
  gridDot: string;
  accent: string;
  draft: string;
  archived: string;
  textPrimary: string;
  textMuted: string;
  labelHalo: string;
  edgeDefault: string;
  pillBg: string;
  pillBorder: string;
}

function readThemeColors(): ThemeColors {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return {
      isDark: false,
      bg: "#f5f8fc",
      gridDot: "rgba(36, 50, 71, 0.08)",
      accent: "#2463eb",
      draft: "#7c3aed",
      archived: "#94a3b8",
      textPrimary: "#1e293b",
      textMuted: "#64748b",
      labelHalo: "rgba(245, 248, 252, 0.88)",
      edgeDefault: "rgba(100, 116, 139, 0.35)",
      pillBg: "rgba(255, 255, 255, 0.92)",
      pillBorder: "rgba(148, 163, 184, 0.35)",
    };
  }
  const root = document.documentElement;
  const isDark = root.getAttribute("data-theme") === "dark";
  const cs = getComputedStyle(root);
  const accent = cs.getPropertyValue("--nesti-accent").trim() || "#2463eb";
  const textPrimary =
    cs.getPropertyValue("--nesti-text-primary").trim() ||
    (isDark ? "#e2e8f0" : "#1e293b");
  const textMuted =
    cs.getPropertyValue("--nesti-text-secondary").trim() ||
    (isDark ? "#94a3b8" : "#64748b");

  return {
    isDark,
    bg: isDark ? "#0b1120" : "#f5f8fc",
    gridDot: isDark ? "rgba(148, 163, 184, 0.12)" : "rgba(36, 50, 71, 0.08)",
    accent,
    draft: isDark ? "#a78bfa" : "#7c3aed",
    archived: isDark ? "#64748b" : "#94a3b8",
    textPrimary,
    textMuted,
    labelHalo: isDark ? "rgba(11, 17, 32, 0.86)" : "rgba(245, 248, 252, 0.9)",
    edgeDefault: isDark
      ? "rgba(148, 163, 184, 0.28)"
      : "rgba(100, 116, 139, 0.32)",
    pillBg: isDark ? "rgba(15, 23, 42, 0.9)" : "rgba(255, 255, 255, 0.92)",
    pillBorder: isDark
      ? "rgba(148, 163, 184, 0.28)"
      : "rgba(148, 163, 184, 0.36)",
  };
}

function drawRoundedRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

/**
 * Obsidian 风格交互式力导向图谱画布（HiDPI HTML5 Canvas）。
 * 支持物理拖拽、悬停邻居聚光灯、滚轮定点缩放、双击居中、主题色彩联动。
 */
export function ObsidianGraphCanvas({
  elements,
  edgeTypes,
  nodeColors,
  selectedId,
  searchQuery,
  config,
  showArrows,
  showEdgeLabels,
  reheatToken,
  onSelectNode,
  onDoubleClickNode,
}: ObsidianGraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  const simRef = useRef<ForceSimulation | null>(null);
  const cameraRef = useRef<Camera>({ x: 0, y: 0, scale: 1 });
  const hoveredIdRef = useRef<string | null>(null);
  const draggingNodeRef = useRef<ForceNode | null>(null);
  const panningRef = useRef<{
    startX: number;
    startY: number;
    camX: number;
    camY: number;
  } | null>(null);
  const pointerDownPosRef = useRef<{ x: number; y: number } | null>(null);
  const rafRef = useRef<number | null>(null);
  const sizeRef = useRef<{ width: number; height: number }>({
    width: 800,
    height: 540,
  });

  // 实时同步 props 到 ref，避免 rAF 闭包陈旧
  const configRef = useRef(config);
  configRef.current = config;
  const selectedIdRef = useRef(selectedId);
  selectedIdRef.current = selectedId;
  const searchQueryRef = useRef(searchQuery.trim().toLowerCase());
  searchQueryRef.current = searchQuery.trim().toLowerCase();
  const showArrowsRef = useRef(showArrows);
  showArrowsRef.current = showArrows;
  const showEdgeLabelsRef = useRef(showEdgeLabels);
  showEdgeLabelsRef.current = showEdgeLabels;
  const nodeColorsRef = useRef(nodeColors);
  nodeColorsRef.current = nodeColors;

  const [cursorStyle, setCursorStyle] = useState<"grab" | "grabbing" | "pointer">(
    "grab",
  );
  const [zoomPercent, setZoomPercent] = useState(100);

  const screenToWorld = useCallback((sx: number, sy: number) => {
    const { width, height } = sizeRef.current;
    const cam = cameraRef.current;
    return {
      x: (sx - width / 2) / cam.scale - cam.x,
      y: (sy - height / 2) / cam.scale - cam.y,
    };
  }, []);

  const hitTestNode = useCallback(
    (sx: number, sy: number): ForceNode | null => {
      const sim = simRef.current;
      if (!sim) return null;
      const { x: wx, y: wy } = screenToWorld(sx, sy);
      const scale = cameraRef.current.scale;
      const nodeScale = configRef.current.nodeScale;
      // 反向遍历使顶层节点优先命中
      for (let i = sim.nodes.length - 1; i >= 0; i -= 1) {
        const node = sim.nodes[i];
        const hitR = Math.max(
          node.baseRadius * nodeScale + 6,
          14 / Math.max(scale, 0.5),
        );
        const dx = wx - node.x;
        const dy = wy - node.y;
        if (dx * dx + dy * dy <= hitR * hitR) {
          return node;
        }
      }
      return null;
    },
    [screenToWorld],
  );

  const fitView = useCallback(() => {
    const sim = simRef.current;
    if (!sim || sim.nodes.length === 0) {
      cameraRef.current = { x: 0, y: 0, scale: 1 };
      setZoomPercent(100);
      return;
    }
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    for (const n of sim.nodes) {
      if (n.x < minX) minX = n.x;
      if (n.x > maxX) maxX = n.x;
      if (n.y < minY) minY = n.y;
      if (n.y > maxY) maxY = n.y;
    }
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    const spanX = Math.max(maxX - minX + 260, 320);
    const spanY = Math.max(maxY - minY + 200, 260);
    const { width, height } = sizeRef.current;
    const scale = Math.max(
      0.35,
      Math.min(1.15, Math.min(width / spanX, height / spanY) * 0.86),
    );
    cameraRef.current = { x: -cx, y: -cy, scale };
    setZoomPercent(Math.round(scale * 100));
  }, []);

  const drawFrame = useCallback(() => {
    const canvas = canvasRef.current;
    const sim = simRef.current;
    if (!canvas || !sim) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const { width, height } = sizeRef.current;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const targetW = Math.max(1, Math.floor(width * dpr));
    const targetH = Math.max(1, Math.floor(height * dpr));
    if (canvas.width !== targetW || canvas.height !== targetH) {
      canvas.width = targetW;
      canvas.height = targetH;
    }

    const theme = readThemeColors();
    const cam = cameraRef.current;
    const cfg = configRef.current;
    const hoveredId = hoveredIdRef.current;
    const activeSelectedId = selectedIdRef.current;
    const query = searchQueryRef.current;

    ctx.save();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    // 1. 背景与柔和径向氛围光
    ctx.fillStyle = theme.bg;
    ctx.fillRect(0, 0, width, height);

    const glow = ctx.createRadialGradient(
      width * 0.5,
      height * 0.45,
      20,
      width * 0.5,
      height * 0.45,
      Math.max(width, height) * 0.65,
    );
    glow.addColorStop(
      0,
      theme.isDark ? "rgba(36, 99, 235, 0.09)" : "rgba(121, 202, 255, 0.14)",
    );
    glow.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, width, height);

    // 2. 轻微点阵背景（随相机平移缩放）
    const gridSpacing = 32 * cam.scale;
    if (gridSpacing >= 12) {
      const offsetX = (((width / 2 + cam.x * cam.scale) % gridSpacing) + gridSpacing) % gridSpacing;
      const offsetY = (((height / 2 + cam.y * cam.scale) % gridSpacing) + gridSpacing) % gridSpacing;
      ctx.fillStyle = theme.gridDot;
      for (let gx = offsetX; gx < width; gx += gridSpacing) {
        for (let gy = offsetY; gy < height; gy += gridSpacing) {
          ctx.beginPath();
          ctx.arc(gx, gy, 1, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }

    // 3. 计算聚焦集合（悬停优先，其次选中，其次搜索）
    const focusRoot = hoveredId ?? activeSelectedId;
    const focusNeighborhood = focusRoot
      ? getNeighborhood(sim.edges, focusRoot, 1)
      : null;

    const matchedIds = query
      ? new Set(
          sim.nodes
            .filter((n) => n.title.toLowerCase().includes(query))
            .map((n) => n.id),
        )
      : null;

    const hasSpotlight =
      Boolean(hoveredId) || (matchedIds !== null && matchedIds.size > 0);

    // 世界坐标变换
    ctx.translate(width / 2, height / 2);
    ctx.scale(cam.scale, cam.scale);
    ctx.translate(cam.x, cam.y);

    // 4. 绘制边
    for (const e of sim.edges) {
      const src = sim.nodeById.get(e.source);
      const tgt = sim.nodeById.get(e.target);
      if (!src || !tgt) continue;

      const inFocus = focusNeighborhood?.edgeIds.has(e.id) ?? false;
      const inSearch =
        matchedIds !== null &&
        (matchedIds.has(e.source) || matchedIds.has(e.target));
      const highlighted = inFocus || inSearch;

      let alpha = 0.42;
      if (hasSpotlight) {
        alpha = highlighted ? 0.92 : 0.08;
      } else if (activeSelectedId && !inFocus) {
        alpha = 0.25;
      }

      ctx.save();
      ctx.globalAlpha = alpha;
      ctx.strokeStyle =
        highlighted || e.relationType !== "related"
          ? e.color
          : theme.edgeDefault;
      ctx.lineWidth = (highlighted ? 1.8 : 1.15) / Math.sqrt(Math.max(cam.scale, 0.4));
      if (e.dashed) {
        ctx.setLineDash([5, 4]);
      }

      const dx = tgt.x - src.x;
      const dy = tgt.y - src.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const ux = dx / dist;
      const uy = dy / dist;
      const srcR = src.baseRadius * cfg.nodeScale;
      const tgtR = tgt.baseRadius * cfg.nodeScale;

      const startX = src.x + ux * (srcR + 2);
      const startY = src.y + uy * (srcR + 2);
      const endX = tgt.x - ux * (tgtR + (showArrowsRef.current && e.arrow ? 6 : 2));
      const endY = tgt.y - uy * (tgtR + (showArrowsRef.current && e.arrow ? 6 : 2));

      ctx.beginPath();
      ctx.moveTo(startX, startY);
      ctx.lineTo(endX, endY);
      ctx.stroke();

      // 箭头
      if (showArrowsRef.current && e.arrow && dist > srcR + tgtR + 12) {
        ctx.setLineDash([]);
        const headLen = 7 / Math.sqrt(Math.max(cam.scale, 0.5));
        const angle = Math.atan2(dy, dx);
        ctx.fillStyle = e.color;
        ctx.beginPath();
        ctx.moveTo(endX + ux * 3, endY + uy * 3);
        ctx.lineTo(
          endX - headLen * Math.cos(angle - Math.PI / 6),
          endY - headLen * Math.sin(angle - Math.PI / 6),
        );
        ctx.lineTo(
          endX - headLen * Math.cos(angle + Math.PI / 6),
          endY - headLen * Math.sin(angle + Math.PI / 6),
        );
        ctx.closePath();
        ctx.fill();
      }

      // 边标签：仅在悬停高亮该边或用户打开“显示连线标签”时绘制
      if ((showEdgeLabelsRef.current && cam.scale >= 0.75) || (hoveredId && inFocus)) {
        const mx = (src.x + tgt.x) / 2;
        const my = (src.y + tgt.y) / 2;
        const fontSize = Math.max(9.5, 10.5 / Math.sqrt(Math.max(cam.scale, 0.55)));
        ctx.font = `500 ${fontSize}px "Segoe UI", system-ui, sans-serif`;
        const metrics = ctx.measureText(e.label);
        const padX = 5;
        const pillW = metrics.width + padX * 2;
        const pillH = fontSize + 6;
        ctx.globalAlpha = highlighted ? 0.95 : 0.72;
        ctx.fillStyle = theme.pillBg;
        ctx.strokeStyle = theme.pillBorder;
        ctx.lineWidth = 0.75;
        drawRoundedRect(ctx, mx - pillW / 2, my - pillH / 2, pillW, pillH, 4);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = theme.textMuted;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(e.label, mx, my + 0.5);
      }

      ctx.restore();
    }

    // 5. 绘制节点（按层级排序：暗淡背景节点先画，高亮邻居/悬停/选中节点最后画在最顶层，避免遮挡）
    const showAllLabels = sim.nodes.length <= 28 || cam.scale >= 0.72;
    const orderedNodes = [...sim.nodes].sort((a, b) => {
      const rank = (id: string) =>
        id === hoveredId
          ? 3
          : id === activeSelectedId
            ? 2
            : focusNeighborhood?.nodeIds.has(id) || matchedIds?.has(id)
              ? 1
              : 0;
      return rank(a.id) - rank(b.id);
    });

    for (const node of orderedNodes) {
      const isHovered = node.id === hoveredId;
      const isSelected = node.id === activeSelectedId;
      const isNeighbor = focusNeighborhood?.nodeIds.has(node.id) ?? false;
      const isSearchMatch = matchedIds?.has(node.id) ?? false;

      let alpha = 1;
      if (hasSpotlight) {
        alpha = isHovered || isSelected || isNeighbor || isSearchMatch ? 1 : 0.16;
      } else if (activeSelectedId && !isNeighbor) {
        alpha = 0.48;
      }

      const r =
        node.baseRadius *
        cfg.nodeScale *
        (isHovered ? 1.24 : isSelected ? 1.15 : 1);

      const customColor = nodeColorsRef.current?.get(node.id);
      const nodeColor = node.archived
        ? theme.archived
        : (customColor ?? (node.status === "draft" ? theme.draft : theme.accent));

      ctx.save();
      ctx.globalAlpha = alpha;

      // 外围光晕（悬停 / 选中 / 搜索命中 / 核心高连接度节点）
      if (isHovered || isSelected || isSearchMatch || node.degree >= 3) {
        const haloR = r + (isHovered || isSelected ? 11 : 6);
        const radial = ctx.createRadialGradient(
          node.x,
          node.y,
          r * 0.4,
          node.x,
          node.y,
          haloR,
        );
        radial.addColorStop(
          0,
          isHovered || isSelected
            ? `${nodeColor}66`
            : isSearchMatch
              ? "#f59e0b55"
              : `${nodeColor}2b`,
        );
        radial.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = radial;
        ctx.beginPath();
        ctx.arc(node.x, node.y, haloR, 0, Math.PI * 2);
        ctx.fill();
      }

      // 节点主体圆
      ctx.beginPath();
      ctx.arc(node.x, node.y, r, 0, Math.PI * 2);
      if (node.archived) {
        ctx.fillStyle = theme.isDark ? "#1e293b" : "#e2e8f0";
        ctx.fill();
        ctx.setLineDash([3, 2.5]);
        ctx.strokeStyle = theme.archived;
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.setLineDash([]);
      } else {
        ctx.fillStyle = nodeColor;
        ctx.fill();
        // 顶部柔和立体高光点（Nesti Fluent 质感）
        const inner = ctx.createRadialGradient(
          node.x - r * 0.3,
          node.y - r * 0.35,
          r * 0.1,
          node.x,
          node.y,
          r,
        );
        inner.addColorStop(0, "rgba(255, 255, 255, 0.42)");
        inner.addColorStop(1, "rgba(255, 255, 255, 0)");
        ctx.fillStyle = inner;
        ctx.fill();
      }

      // 选中/悬停/搜索外环
      if (isHovered || isSelected || isSearchMatch) {
        ctx.beginPath();
        ctx.arc(node.x, node.y, r + 2.8, 0, Math.PI * 2);
        ctx.strokeStyle = isSearchMatch && !isSelected ? "#f59e0b" : nodeColor;
        ctx.lineWidth = isHovered || isSelected ? 2 : 1.5;
        ctx.stroke();
      }

      // 节点标题标签
      const shouldShowLabel =
        showAllLabels ||
        isHovered ||
        isSelected ||
        isSearchMatch ||
        (hoveredId !== null && isNeighbor);

      if (shouldShowLabel) {
        const fontSize = Math.max(
          10.5,
          (isHovered || isSelected ? 12.5 : 11.5) /
            Math.sqrt(Math.max(cam.scale, 0.55)),
        );
        ctx.font = `${isHovered || isSelected ? 600 : 500} ${fontSize}px "Segoe UI", "PingFang SC", system-ui, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        const label =
          node.title.length > 14 && !isHovered && !isSelected
            ? `${node.title.slice(0, 13)}…`
            : node.title;
        const labelY = node.y + r + 6;

        // 文字描边光晕防止与边重叠难辨认
        ctx.lineJoin = "round";
        ctx.lineWidth = 3.5;
        ctx.strokeStyle = theme.labelHalo;
        ctx.strokeText(label, node.x, labelY);

        ctx.fillStyle =
          isHovered || isSelected ? theme.textPrimary : theme.textMuted;
        ctx.fillText(label, node.x, labelY);
      }

      ctx.restore();
    }

    ctx.restore();
  }, []);

  const ensureLoopRunning = useCallback(() => {
    if (rafRef.current !== null) return;
    const tick = () => {
      const sim = simRef.current;
      if (!sim) {
        rafRef.current = null;
        return;
      }
      const moving = stepForceSimulation(sim, configRef.current);
      drawFrame();
      if (moving || draggingNodeRef.current) {
        rafRef.current = window.requestAnimationFrame(tick);
      } else {
        rafRef.current = null;
      }
    };
    rafRef.current = window.requestAnimationFrame(tick);
  }, [drawFrame]);

  // 初始化或重建力导向仿真
  useEffect(() => {
    simRef.current = createForceSimulation(
      elements,
      edgeTypes,
      configRef.current,
      75,
    );
    fitView();
    drawFrame();
    ensureLoopRunning();
    return () => {
      if (rafRef.current !== null) {
        window.cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
    };
  }, [elements, edgeTypes, fitView, drawFrame, ensureLoopRunning]);

  // 参数或手动“重新散开”变化时重新加热仿真
  useEffect(() => {
    const sim = simRef.current;
    if (!sim) return;
    sim.alpha = Math.max(sim.alpha, 0.55);
    ensureLoopRunning();
  }, [config, reheatToken, ensureLoopRunning]);

  // 选中/搜索/开关/配色变化时重绘一帧
  useEffect(() => {
    drawFrame();
  }, [selectedId, searchQuery, showArrows, showEdgeLabels, nodeColors, drawFrame]);

  // 监听容器尺寸与主题切换
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const updateSize = () => {
      const rect = el.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        sizeRef.current = { width: rect.width, height: rect.height };
        drawFrame();
      }
    };
    updateSize();

    let ro: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver(updateSize);
      ro.observe(el);
    }

    const mo = new MutationObserver(() => drawFrame());
    mo.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme", "data-accent", "style"],
    });

    return () => {
      ro?.disconnect();
      mo.disconnect();
    };
  }, [drawFrame]);

  // 指针交互：拖拽节点 / 平移画布 / 悬停聚焦 / 点击选中 / 双击居中
  const handlePointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;
    pointerDownPosRef.current = { x: sx, y: sy };

    const hit = hitTestNode(sx, sy);
    if (hit) {
      draggingNodeRef.current = hit;
      hit.fx = hit.x;
      hit.fy = hit.y;
      if (simRef.current) {
        simRef.current.alpha = Math.max(simRef.current.alpha, 0.45);
      }
      setCursorStyle("grabbing");
      ensureLoopRunning();
    } else {
      panningRef.current = {
        startX: sx,
        startY: sy,
        camX: cameraRef.current.x,
        camY: cameraRef.current.y,
      };
      setCursorStyle("grabbing");
    }
    canvas.setPointerCapture?.(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;

    if (draggingNodeRef.current) {
      const world = screenToWorld(sx, sy);
      draggingNodeRef.current.fx = world.x;
      draggingNodeRef.current.fy = world.y;
      draggingNodeRef.current.x = world.x;
      draggingNodeRef.current.y = world.y;
      if (simRef.current) {
        simRef.current.alpha = Math.max(simRef.current.alpha, 0.3);
      }
      ensureLoopRunning();
      return;
    }

    if (panningRef.current) {
      const dx = (sx - panningRef.current.startX) / cameraRef.current.scale;
      const dy = (sy - panningRef.current.startY) / cameraRef.current.scale;
      cameraRef.current = {
        ...cameraRef.current,
        x: panningRef.current.camX + dx,
        y: panningRef.current.camY + dy,
      };
      drawFrame();
      return;
    }

    const hit = hitTestNode(sx, sy);
    const nextHover = hit ? hit.id : null;
    if (nextHover !== hoveredIdRef.current) {
      hoveredIdRef.current = nextHover;
      setCursorStyle(nextHover ? "pointer" : "grab");
      drawFrame();
    }
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;
    const down = pointerDownPosRef.current;
    const movedDist = down ? Math.hypot(sx - down.x, sy - down.y) : 999;

    const dragged = draggingNodeRef.current;
    if (dragged) {
      dragged.fx = null;
      dragged.fy = null;
      draggingNodeRef.current = null;
      if (movedDist < 6) {
        onSelectNode(dragged.id);
      }
      ensureLoopRunning();
    }

    panningRef.current = null;
    pointerDownPosRef.current = null;
    setCursorStyle(hoveredIdRef.current ? "pointer" : "grab");
    canvas.releasePointerCapture?.(e.pointerId);
  };

  const handleDoubleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const hit = hitTestNode(e.clientX - rect.left, e.clientY - rect.top);
    if (!hit) {
      fitView();
      drawFrame();
      return;
    }
    cameraRef.current = {
      x: -hit.x,
      y: -hit.y,
      scale: Math.max(cameraRef.current.scale, 1.25),
    };
    setZoomPercent(Math.round(cameraRef.current.scale * 100));
    drawFrame();
    onDoubleClickNode?.(hit.id);
  };

  const handleWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;
    const before = screenToWorld(sx, sy);

    const factor = e.deltaY < 0 ? 1.12 : 0.89;
    const nextScale = Math.max(0.22, Math.min(4.2, cameraRef.current.scale * factor));
    const { width, height } = sizeRef.current;
    const nextCamX = (sx - width / 2) / nextScale - before.x;
    const nextCamY = (sy - height / 2) / nextScale - before.y;

    cameraRef.current = { x: nextCamX, y: nextCamY, scale: nextScale };
    setZoomPercent(Math.round(nextScale * 100));
    drawFrame();
  };

  const zoomBy = (factor: number) => {
    const nextScale = Math.max(0.22, Math.min(4.2, cameraRef.current.scale * factor));
    cameraRef.current = { ...cameraRef.current, scale: nextScale };
    setZoomPercent(Math.round(nextScale * 100));
    drawFrame();
  };

  return (
    <div
      ref={containerRef}
      data-testid="obsidian-graph-canvas"
      className="relative h-full w-full select-none overflow-hidden"
    >
      <canvas
        ref={canvasRef}
        className="block h-full w-full"
        style={{ cursor: cursorStyle, touchAction: "none" }}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={() => {
          if (!draggingNodeRef.current && !panningRef.current) {
            hoveredIdRef.current = null;
            drawFrame();
          }
        }}
        onDoubleClick={handleDoubleClick}
        onWheel={handleWheel}
      />

      {/* 左下角 Obsidian 风格浮动缩放/居中控制条 */}
      <div
        className="absolute bottom-3 left-3 flex items-center gap-1 rounded-lg border px-1.5 py-1 shadow-sm backdrop-blur-md"
        style={{
          background: "var(--nesti-surface-1)",
          borderColor: "var(--nesti-border-subtle)",
          color: "var(--nesti-text-secondary)",
        }}
      >
        <button
          type="button"
          onClick={() => zoomBy(1.2)}
          title="放大"
          aria-label="放大"
          className="rounded px-2 py-0.5 text-xs font-medium hover:bg-[var(--nesti-surface-hover)]"
        >
          +
        </button>
        <span className="min-w-[40px] text-center text-[11px] tabular-nums">
          {zoomPercent}%
        </span>
        <button
          type="button"
          onClick={() => zoomBy(0.82)}
          title="缩小"
          aria-label="缩小"
          className="rounded px-2 py-0.5 text-xs font-medium hover:bg-[var(--nesti-surface-hover)]"
        >
          −
        </button>
        <span
          className="mx-0.5 h-3.5 w-px"
          style={{ background: "var(--nesti-border-subtle)" }}
        />
        <button
          type="button"
          onClick={() => {
            fitView();
            drawFrame();
          }}
          title="自适应画布"
          className="rounded px-2 py-0.5 text-[11px] hover:bg-[var(--nesti-surface-hover)]"
        >
          自适应
        </button>
      </div>

      {/* 操作提示 */}
      <div
        className="pointer-events-none absolute bottom-3 right-3 hidden rounded-md px-2.5 py-1 text-[11px] backdrop-blur-sm sm:block"
        style={{
          background: "var(--nesti-surface-1)",
          color: "var(--nesti-text-tertiary)",
          opacity: 0.85,
        }}
      >
        拖拽节点体验弹性联动 · 滚轮缩放 · 双击居中
      </div>

      {/* 无障碍语义镜像：支持键盘导航与自动化测试直接交互 */}
      <div className="sr-only" aria-label="图谱节点列表">
        {elements.nodes.map((n) => (
          <button
            key={n.id}
            type="button"
            onClick={() => onSelectNode(n.id)}
          >
            {n.title}
          </button>
        ))}
        {elements.edges.map((e) => (
          <span key={e.id}>{e.label}</span>
        ))}
      </div>
    </div>
  );
}
