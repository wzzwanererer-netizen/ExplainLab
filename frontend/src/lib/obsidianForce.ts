/**
 * Obsidian 风格力导向知识图谱物理引擎（纯 TypeScript，无 DOM / 第三方依赖）。
 *
 * 采用库仑斥力 + 胡克弹簧引力 + 柔和向心力 + 速度阻尼，
 * 针对个人知识库规模（1~1000 节点）在 60fps 下每帧计算耗时 < 1ms。
 */
import type { RelationType } from "../api/types";
import type { MapEdge, MapElements, MapNode } from "./graphLayout";

export interface ForceNode extends MapNode {
  degree: number;
  baseRadius: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
  fx: number | null;
  fy: number | null;
}

export interface ForceEdge extends MapEdge {
  relationType: RelationType;
}

export interface ForceConfig {
  /** 节点间斥力强度（越大越分散） */
  repulsion: number;
  /** 理想连线长度（px） */
  linkDistance: number;
  /** 连线弹簧劲度系数 */
  linkStrength: number;
  /** 柔和中心引力（防止孤立节点飘远） */
  centerGravity: number;
  /** 速度阻尼系数 (0~1) */
  damping: number;
  /** 节点缩放倍率 */
  nodeScale: number;
}

export const DEFAULT_FORCE_CONFIG: ForceConfig = {
  repulsion: 7200,
  linkDistance: 185,
  linkStrength: 0.055,
  centerGravity: 0.016,
  damping: 0.84,
  nodeScale: 1,
};

export interface ForceSimulation {
  nodes: ForceNode[];
  edges: ForceEdge[];
  nodeById: Map<string, ForceNode>;
  alpha: number;
}

export interface Neighborhood {
  nodeIds: Set<string>;
  edgeIds: Set<string>;
}

/** 从关系标签反推或由调用方传入 relationType 时的辅助映射。 */
export function computeDegrees(
  nodes: Pick<MapNode, "id">[],
  edges: Pick<MapEdge, "source" | "target">[],
): Map<string, number> {
  const degrees = new Map<string, number>();
  for (const n of nodes) degrees.set(n.id, 0);
  for (const e of edges) {
    degrees.set(e.source, (degrees.get(e.source) ?? 0) + 1);
    degrees.set(e.target, (degrees.get(e.target) ?? 0) + 1);
  }
  return degrees;
}

/** 按连接度计算基础半径：核心知识节点更醒目，类似 Obsidian。 */
export function radiusForDegree(degree: number): number {
  return 6.5 + Math.min(degree, 10) * 1.45;
}

/** 计算指定节点的 1 跳或 2 跳邻居集合（用于悬停聚焦 & 局部图谱）。 */
export function getNeighborhood(
  edges: Pick<ForceEdge, "id" | "source" | "target">[],
  rootId: string,
  hops: 1 | 2 = 1,
): Neighborhood {
  const nodeIds = new Set<string>([rootId]);
  const edgeIds = new Set<string>();
  let frontier = new Set<string>([rootId]);

  for (let step = 0; step < hops; step += 1) {
    const nextFrontier = new Set<string>();
    for (const e of edges) {
      const hasSrc = frontier.has(e.source);
      const hasTgt = frontier.has(e.target);
      if (hasSrc || hasTgt) {
        edgeIds.add(e.id);
        if (!nodeIds.has(e.source)) {
          nodeIds.add(e.source);
          nextFrontier.add(e.source);
        }
        if (!nodeIds.has(e.target)) {
          nodeIds.add(e.target);
          nextFrontier.add(e.target);
        }
      }
    }
    frontier = nextFrontier;
    if (frontier.size === 0) break;
  }

  return { nodeIds, edgeIds };
}

/**
 * 初始化力导向仿真：
 * - 用黄金角螺旋做确定性初始排布（避免节点初始重叠和闪烁）
 * - 预热若干帧，使首屏打开即呈现自然星团
 */
export function createForceSimulation(
  elements: MapElements,
  edgeTypes: Map<string, RelationType>,
  config: ForceConfig = DEFAULT_FORCE_CONFIG,
  warmupTicks = 75,
): ForceSimulation {
  const degrees = computeDegrees(elements.nodes, elements.edges);
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));
  const spacing = 88;

  // 连接度高的节点放在靠中心的位置，布局更美观
  const sorted = [...elements.nodes].sort(
    (a, b) => (degrees.get(b.id) ?? 0) - (degrees.get(a.id) ?? 0),
  );
  const rankById = new Map<string, number>();
  sorted.forEach((n, idx) => rankById.set(n.id, idx));

  const nodes: ForceNode[] = elements.nodes.map((n) => {
    const idx = rankById.get(n.id) ?? 0;
    const deg = degrees.get(n.id) ?? 0;
    const r = idx === 0 ? 0 : spacing * Math.sqrt(idx + 0.5);
    const angle = idx * goldenAngle;
    return {
      ...n,
      degree: deg,
      baseRadius: radiusForDegree(deg),
      x: Math.cos(angle) * r,
      y: Math.sin(angle) * r,
      vx: 0,
      vy: 0,
      fx: null,
      fy: null,
    };
  });

  const nodeById = new Map<string, ForceNode>(nodes.map((n) => [n.id, n]));
  const edges: ForceEdge[] = elements.edges
    .filter((e) => nodeById.has(e.source) && nodeById.has(e.target))
    .map((e) => ({
      ...e,
      relationType: edgeTypes.get(e.id) ?? "related",
    }));

  const sim: ForceSimulation = {
    nodes,
    edges,
    nodeById,
    alpha: 1,
  };

  for (let i = 0; i < warmupTicks; i += 1) {
    stepForceSimulation(sim, config);
  }
  // 留一点残余活力让刚打开画面时有轻微呼吸收敛感
  sim.alpha = Math.max(sim.alpha, 0.18);
  return sim;
}

/** 推进一步物理仿真。返回是否仍处于活跃运动状态。 */
export function stepForceSimulation(
  sim: ForceSimulation,
  config: ForceConfig = DEFAULT_FORCE_CONFIG,
): boolean {
  const { nodes, edges, nodeById } = sim;
  const n = nodes.length;
  if (n === 0) return false;

  const alpha = sim.alpha;
  const maxStep = 28;

  // 1. 库仑斥力（成对排斥）
  for (let i = 0; i < n; i += 1) {
    const a = nodes[i];
    for (let j = i + 1; j < n; j += 1) {
      const b = nodes[j];
      let dx = b.x - a.x;
      let dy = b.y - a.y;
      let distSq = dx * dx + dy * dy;
      if (distSq < 1) {
        // 防止重合奇点
        dx = ((i + 1) % 3 - 1) * 0.6 || 0.5;
        dy = ((j + 1) % 3 - 1) * 0.6 || -0.5;
        distSq = dx * dx + dy * dy;
      }
      const dist = Math.sqrt(distSq);
      // 软化半径防止过近时爆炸
      const minDist = (a.baseRadius + b.baseRadius) * config.nodeScale + 42;
      const effectiveDistSq = Math.max(distSq, minDist * minDist * 0.55);
      const force = (config.repulsion * alpha) / effectiveDistSq;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      a.vx -= fx;
      a.vy -= fy;
      b.vx += fx;
      b.vy += fy;

      // 矩形标签防重叠碰撞分离（横向宽、纵向紧凑，避免中文长标题互相遮挡）
      const halfW = 78 * config.nodeScale;
      const halfH = 30 * config.nodeScale;
      const overlapX = halfW * 2 - Math.abs(dx);
      const overlapY = halfH * 2 - Math.abs(dy);
      if (overlapX > 0 && overlapY > 0) {
        const push = 0.22 * Math.max(alpha, 0.15);
        if (overlapX < overlapY) {
          const sx = dx >= 0 ? 1 : -1;
          a.vx -= sx * overlapX * push;
          b.vx += sx * overlapX * push;
        } else {
          const sy = dy >= 0 ? 1 : -1;
          a.vy -= sy * overlapY * push;
          b.vy += sy * overlapY * push;
        }
      }
    }
  }

  // 2. 胡克弹簧引力（沿关系边拉近）
  for (const e of edges) {
    const a = nodeById.get(e.source);
    const b = nodeById.get(e.target);
    if (!a || !b) continue;
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
    const displacement = dist - config.linkDistance;
    const force = displacement * config.linkStrength * alpha;
    const fx = (dx / dist) * force;
    const fy = (dy / dist) * force;
    a.vx += fx;
    a.vy += fy;
    b.vx -= fx;
    b.vy -= fy;
  }

  // 3. 柔和中心引力 + 速度积分 + 阻尼
  let totalEnergy = 0;
  for (const node of nodes) {
    if (node.fx !== null && node.fy !== null) {
      node.x = node.fx;
      node.y = node.fy;
      node.vx = 0;
      node.vy = 0;
      continue;
    }
    node.vx += -node.x * config.centerGravity * alpha;
    node.vy += -node.y * config.centerGravity * alpha;

    node.vx *= config.damping;
    node.vy *= config.damping;

    const speed = Math.sqrt(node.vx * node.vx + node.vy * node.vy);
    if (speed > maxStep) {
      node.vx = (node.vx / speed) * maxStep;
      node.vy = (node.vy / speed) * maxStep;
    }

    node.x += node.vx;
    node.y += node.vy;
    totalEnergy += node.vx * node.vx + node.vy * node.vy;
  }

  sim.alpha = Math.max(0.002, sim.alpha * 0.985);
  return sim.alpha > 0.004 || totalEnergy > 0.02;
}
