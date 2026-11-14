import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SearchView } from "./SearchView";

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

const hit = {
  item_id: "k1",
  score: 0.0161,
  snippet: "知识图谱是一种网络结构数据模型",
  title: "知识图谱的定义",
  space_id: null,
  status: "active",
  channels: { fts: -0.0000013 },
};

const searchResponse = {
  query: "知识图谱",
  mode: "fts",
  count: 1,
  embed_capability: "not_configured",
  results: [hit],
};

const fullItem = {
  id: "k1",
  space_id: null,
  title: "知识图谱的定义",
  content: "知识图谱是一种网络结构数据模型",
  status: "active",
  source_refs: [
    {
      id: "sr1",
      source_type: "conversation",
      uri: null,
      conversation_id: "c1abcdef-0000-0000-0000-000000000000",
      excerpt: "对话摘录",
      created_at: "2026-11-14T00:00:00Z",
    },
  ],
  created_at: "2026-11-14T00:00:00Z",
  updated_at: "2026-11-14T00:00:00Z",
};

function stubFetch(searchPayload: unknown = searchResponse) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (url === "/api/spaces") return ok([space]);
      if (url === "/api/search/reindex" && method === "POST") {
        return ok({ indexed: 3, embed_capability: "not_configured" });
      }
      if (url.startsWith("/api/search?")) return ok(searchPayload);
      if (url === "/api/knowledge/k1") return ok(fullItem);
      if (url === "/api/knowledge/k1/relations") return ok([]);
      if (url === "/api/knowledge/k1/versions") return ok([]);
      return { ok: false, status: 404 };
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SearchView", () => {
  it("渲染检索表单与初始提示", async () => {
    stubFetch();
    render(<SearchView />);
    expect(screen.getByLabelText("检索关键词")).toBeInTheDocument();
    expect(screen.getByText("全部空间")).toBeInTheDocument();
    expect(await screen.findByText(/输入关键词开始跨会话检索/)).toBeInTheDocument();
  });

  it("检索展示结果与向量能力如实提示", async () => {
    stubFetch();
    render(<SearchView />);
    fireEvent.change(screen.getByLabelText("检索关键词"), {
      target: { value: "知识图谱" },
    });
    fireEvent.click(screen.getByText("检索"));

    expect(await screen.findByText("知识图谱的定义")).toBeInTheDocument();
    expect(screen.getByText("知识图谱是一种网络结构数据模型")).toBeInTheDocument();
    expect(screen.getByText(/融合分 0.0161/)).toBeInTheDocument();
    expect(screen.getByText(/全文 -0.0000/)).toBeInTheDocument();
    expect(screen.getByText(/向量通道未配置/)).toBeInTheDocument();
    expect(screen.getByText(/实际模式：仅全文/)).toBeInTheDocument();
  });

  it("无结果时展示空态", async () => {
    stubFetch({ ...searchResponse, count: 0, results: [] });
    render(<SearchView />);
    fireEvent.change(screen.getByLabelText("检索关键词"), {
      target: { value: "不存在" },
    });
    fireEvent.click(screen.getByText("检索"));
    expect(await screen.findByText(/未检索到匹配知识/)).toBeInTheDocument();
  });

  it("重建索引提示已重建条数", async () => {
    stubFetch();
    render(<SearchView />);
    fireEvent.click(screen.getByText("重建索引"));
    expect(await screen.findByText(/已重建 3 条知识索引/)).toBeInTheDocument();
  });

  it("查看详情展开知识治理详情", async () => {
    stubFetch();
    render(<SearchView />);
    fireEvent.change(screen.getByLabelText("检索关键词"), {
      target: { value: "知识图谱" },
    });
    fireEvent.click(screen.getByText("检索"));
    await screen.findByText("知识图谱的定义");
    fireEvent.click(screen.getByText("查看详情"));
    expect(await screen.findByText(/来源（1）/)).toBeInTheDocument();
  });
});