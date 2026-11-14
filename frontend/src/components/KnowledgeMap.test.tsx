import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { KnowledgeMap } from "./KnowledgeMap";

// 画布用确定性替身：单测聚焦组件装配/取数/联动逻辑；真实 React Flow 画布以浏览器验收为准。
vi.mock("@xyflow/react", () => ({
  ReactFlow: ({
    nodes,
    edges,
    onNodeClick,
  }: {
    nodes: { id: string; data: { title: string } }[];
    edges: { id: string; label: string }[];
    onNodeClick?: (evt: unknown, node: { id: string }) => void;
  }) => (
    <div data-testid="flow-canvas">
      {nodes.map((n) => (
        <button key={n.id} type="button" onClick={(e) => onNodeClick?.(e, n)}>
          {n.data.title}
        </button>
      ))}
      {edges.map((e) => (
        <span key={e.id}>{e.label}</span>
      ))}
    </div>
  ),
  Background: () => null,
  Controls: () => null,
  Handle: () => null,
  Position: { Top: "top", Bottom: "bottom", Left: "left", Right: "right" },
  MarkerType: { ArrowClosed: "arrowclosed" },
}));

function ok(data: unknown) {
  return { ok: true, status: 200, json: async () => data };
}

const space = {
  id: "s1",
  name: "个人总知识库",
  kind: "personal",
  description: null,
  created_at: "2026-11-14T00:00:00Z",
  updated_at: "2026-11-14T00:00:00Z",
};

const graph = {
  nodes: [
    { id: "k1", title: "定义", status: "active", space_id: null },
    { id: "k2", title: "概念", status: "archived", space_id: null },
  ],
  edges: [
    {
      id: "e1",
      source_id: "k2",
      target_id: "k1",
      relation_type: "duplicate_of",
      confidence: 1,
      origin: "dedup",
    },
  ],
};

const fullItem = {
  id: "k1",
  space_id: null,
  title: "定义",
  content: "知识图谱是一种网络结构数据模型",
  status: "active",
  source_refs: [],
  created_at: "2026-11-14T00:00:00Z",
  updated_at: "2026-11-14T00:00:00Z",
};

function stubFetch(graphPayload: unknown = graph, graphOk = true) {
  const fetchMock = vi.fn(async (url: string) => {
    if (url === "/api/spaces") return ok([space]);
    if (url.startsWith("/api/graph")) {
      return graphOk ? ok(graphPayload) : { ok: false, status: 500 };
    }
    if (url === "/api/knowledge/k1") return ok(fullItem);
    if (url === "/api/knowledge/k1/relations") return ok([]);
    if (url === "/api/knowledge/k1/versions") return ok([]);
    return { ok: false, status: 404 };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("KnowledgeMap", () => {
  it("渲染工具条、节点、边与计数", async () => {
    stubFetch();
    render(<KnowledgeMap />);
    expect(screen.getByLabelText("地图空间")).toBeInTheDocument();
    expect(screen.getByLabelText("显示归档")).toBeInTheDocument();
    expect(await screen.findByText("定义")).toBeInTheDocument();
    expect(screen.getByText("概念")).toBeInTheDocument();
    expect(screen.getByText("重复 100%")).toBeInTheDocument();
    expect(screen.getByText(/节点 2 · 边 1/)).toBeInTheDocument();
  });

  it("空图展示空态", async () => {
    stubFetch({ nodes: [], edges: [] });
    render(<KnowledgeMap />);
    expect(
      await screen.findByText(/当前空间暂无可展示的知识节点/),
    ).toBeInTheDocument();
  });

  it("显示归档开关触发 include_archived 重取", async () => {
    const fetchMock = stubFetch();
    render(<KnowledgeMap />);
    await screen.findByText("定义");
    fireEvent.click(screen.getByLabelText("显示归档"));
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(([url]) =>
          String(url).includes("include_archived=true"),
        ),
      ).toBe(true);
    });
  });

  it("点击节点打开治理详情", async () => {
    stubFetch();
    render(<KnowledgeMap />);
    fireEvent.click(await screen.findByText("定义"));
    expect(await screen.findByText("知识详情")).toBeInTheDocument();
    expect(await screen.findByText(/来源（0）/)).toBeInTheDocument();
  });

  it("后端失败如实报错", async () => {
    stubFetch(graph, false);
    render(<KnowledgeMap />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});