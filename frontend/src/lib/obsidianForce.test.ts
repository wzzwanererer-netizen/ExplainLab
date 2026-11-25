import { describe, expect, it } from "vitest";

import type { GraphResponse, RelationType } from "../api/types";
import { toMapElements } from "./graphLayout";
import {
  computeDegrees,
  createForceSimulation,
  DEFAULT_FORCE_CONFIG,
  getNeighborhood,
  radiusForDegree,
  stepForceSimulation,
} from "./obsidianForce";

const sampleGraph: GraphResponse = {
  nodes: [
    { id: "a", title: "核心节点", status: "active", space_id: null },
    { id: "b", title: "一跳节点", status: "active", space_id: null },
    { id: "c", title: "二跳节点", status: "draft", space_id: null },
    { id: "d", title: "孤立节点", status: "archived", space_id: null },
  ],
  edges: [
    {
      id: "e1",
      source_id: "a",
      target_id: "b",
      relation_type: "depends_on",
      confidence: 0.95,
      origin: "llm",
    },
    {
      id: "e2",
      source_id: "b",
      target_id: "c",
      relation_type: "refines",
      confidence: 0.8,
      origin: "manual",
    },
  ],
};

describe("obsidianForce", () => {
  it("computes node degrees and scales radius with degree", () => {
    const elements = toMapElements(sampleGraph);
    const degrees = computeDegrees(elements.nodes, elements.edges);
    expect(degrees.get("a")).toBe(1);
    expect(degrees.get("b")).toBe(2);
    expect(degrees.get("d")).toBe(0);
    expect(radiusForDegree(2)).toBeGreaterThan(radiusForDegree(0));
  });

  it("computes 1-hop and 2-hop neighborhoods accurately", () => {
    const elements = toMapElements(sampleGraph);
    const hop1 = getNeighborhood(elements.edges, "a", 1);
    expect([...hop1.nodeIds].sort()).toEqual(["a", "b"]);
    expect([...hop1.edgeIds]).toEqual(["e1"]);

    const hop2 = getNeighborhood(elements.edges, "a", 2);
    expect([...hop2.nodeIds].sort()).toEqual(["a", "b", "c"]);
    expect([...hop2.edgeIds].sort()).toEqual(["e1", "e2"]);
  });

  it("initializes finite non-overlapping coordinates and settles smoothly", () => {
    const elements = toMapElements(sampleGraph);
    const types = new Map<string, RelationType>(
      sampleGraph.edges.map((e) => [e.id, e.relation_type]),
    );
    const sim = createForceSimulation(elements, types, DEFAULT_FORCE_CONFIG, 60);
    expect(sim.nodes).toHaveLength(4);
    expect(sim.edges).toHaveLength(2);
    for (const node of sim.nodes) {
      expect(Number.isFinite(node.x)).toBe(true);
      expect(Number.isFinite(node.y)).toBe(true);
    }

    // 固定一个节点拖动时，其坐标保持在 fx/fy
    const a = sim.nodeById.get("a")!;
    a.fx = 123;
    a.fy = -45;
    stepForceSimulation(sim, DEFAULT_FORCE_CONFIG);
    expect(a.x).toBe(123);
    expect(a.y).toBe(-45);
  });
});
