import { describe, expect, it } from "vitest";

import type { GraphResponse } from "../api/types";
import {
  edgeVisual,
  layoutWithElk,
  RELATION_LABEL,
  toMapElements,
} from "./graphLayout";

const graph: GraphResponse = {
  nodes: [
    { id: "a", title: "定义", status: "active", space_id: null },
    { id: "b", title: "概念", status: "archived", space_id: null },
  ],
  edges: [
    {
      id: "e1",
      source_id: "b",
      target_id: "a",
      relation_type: "duplicate_of",
      confidence: 1,
      origin: "dedup",
    },
  ],
};

describe("toMapElements", () => {
  it("maps nodes with archived flag", () => {
    const { nodes } = toMapElements(graph);
    expect(nodes).toHaveLength(2);
    expect(nodes[0]).toMatchObject({ id: "a", title: "定义", archived: false });
    expect(nodes[1]).toMatchObject({ id: "b", archived: true });
  });

  it("maps edge label and visual", () => {
    const { edges } = toMapElements(graph);
    expect(edges[0]).toMatchObject({
      id: "e1",
      source: "b",
      target: "a",
      label: `${RELATION_LABEL.duplicate_of} 100%`,
      dashed: true,
      arrow: true,
    });
  });
});

describe("edgeVisual", () => {
  it("related is gray without arrow", () => {
    expect(edgeVisual("related")).toEqual({
      color: "#94a3b8",
      dashed: false,
      arrow: false,
    });
  });

  it("depends_on has arrow", () => {
    expect(edgeVisual("depends_on").arrow).toBe(true);
  });

  it("contradicts is red", () => {
    expect(edgeVisual("contradicts").color).toBe("#f87171");
  });
});

describe("layoutWithElk", () => {
  it("empty graph returns empty without layout", async () => {
    const result = await layoutWithElk({ nodes: [], edges: [] });
    expect(result.nodes).toEqual([]);
    expect(result.edges).toEqual([]);
  });

  it("assigns layered positions for connected nodes", async () => {
    const result = await layoutWithElk(graph);
    expect(result.nodes).toHaveLength(2);
    const a = result.nodes.find((n) => n.id === "a")!;
    const b = result.nodes.find((n) => n.id === "b")!;
    expect(Number.isFinite(a.position.x)).toBe(true);
    expect(Number.isFinite(a.position.y)).toBe(true);
    expect(Number.isFinite(b.position.y)).toBe(true);
    // layered DOWN：有边 b->a，两节点应处于不同层
    expect(b.position.y).not.toBe(a.position.y);
  });

  it("single node without edges", async () => {
    const result = await layoutWithElk({ nodes: [graph.nodes[0]], edges: [] });
    expect(result.nodes).toHaveLength(1);
    expect(result.edges).toEqual([]);
  });
});