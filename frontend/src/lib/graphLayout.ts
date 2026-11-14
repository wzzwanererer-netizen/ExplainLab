/**
 * M4 知识地图布局纯模块。
 *
 * 只依赖 Core 图 DTO 与 ELK.js（纯 JS，无 DOM），不引 React Flow 运行时，
 * 便于在 jsdom 中单测。React Flow 的节点/边转换在 KnowledgeMap 组件内完成。
 */
import ELK from "elkjs/lib/elk.bundled.js";

import type { GraphResponse, KnowledgeStatus, RelationType } from "../api/types";

export const RELATION_LABEL: Record<RelationType, string> = {
  related: "相关",
  depends_on: "依赖",
  duplicate_of: "重复",
  refines: "细化",
  contradicts: "矛盾",
};

export const STATUS_LABEL: Record<KnowledgeStatus, string> = {
  draft: "草稿",
  active: "生效",
  archived: "归档",
};

export const NODE_WIDTH = 220;
export const NODE_HEIGHT = 64;

export interface MapNode {
  id: string;
  title: string;
  status: KnowledgeStatus;
  archived: boolean;
  position: { x: number; y: number };
}

export interface MapEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  color: string;
  dashed: boolean;
  arrow: boolean;
}

export interface MapElements {
  nodes: MapNode[];
  edges: MapEdge[];
}

/** 关系类型 → 视觉（颜色/虚线/箭头）。duplicate_of 红虚线呈现合并闭环。 */
export function edgeVisual(type: RelationType): {
  color: string;
  dashed: boolean;
  arrow: boolean;
} {
  switch (type) {
    case "duplicate_of":
      return { color: "#f87171", dashed: true, arrow: true };
    case "contradicts":
      return { color: "#f87171", dashed: false, arrow: true };
    case "depends_on":
      return { color: "#60a5fa", dashed: false, arrow: true };
    case "refines":
      return { color: "#34d399", dashed: false, arrow: true };
    default:
      return { color: "#94a3b8", dashed: false, arrow: false };
  }
}

/** Core 图 → 地图元素（坐标暂为 0，布局由 layoutWithElk 填充）。 */
export function toMapElements(graph: GraphResponse): MapElements {
  return {
    nodes: graph.nodes.map((n) => ({
      id: n.id,
      title: n.title,
      status: n.status,
      archived: n.status === "archived",
      position: { x: 0, y: 0 },
    })),
    edges: graph.edges.map((e) => {
      const visual = edgeVisual(e.relation_type);
      return {
        id: e.id,
        source: e.source_id,
        target: e.target_id,
        label: `${RELATION_LABEL[e.relation_type]} ${Math.round(e.confidence * 100)}%`,
        ...visual,
      };
    }),
  };
}

const elk = new ELK();

/** ELK layered 自动布局（自上而下）。空图直接返回，不布局。 */
export async function layoutWithElk(graph: GraphResponse): Promise<MapElements> {
  const elements = toMapElements(graph);
  if (elements.nodes.length === 0) return elements;
  const laid = await elk.layout({
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": "DOWN",
      "elk.spacing.nodeNode": "40",
      "elk.layered.spacing.nodeNodeBetweenLayers": "60",
    },
    children: elements.nodes.map((n) => ({
      id: n.id,
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
    })),
    edges: elements.edges.map((e) => ({
      id: e.id,
      sources: [e.source],
      targets: [e.target],
    })),
  });
  const positions = new Map<string, { x: number; y: number }>(
    (laid.children ?? []).map((c) => [c.id, { x: c.x ?? 0, y: c.y ?? 0 }]),
  );
  return {
    nodes: elements.nodes.map((n) => ({
      ...n,
      position: positions.get(n.id) ?? n.position,
    })),
    edges: elements.edges,
  };
}