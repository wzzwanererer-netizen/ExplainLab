import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { KnowledgeView } from "./KnowledgeView";

function ok(data: unknown) {
  return { ok: true, status: 200, json: async () => data };
}

const space = {
  id: "s1",
  name: "个人总知识库",
  kind: "personal",
  description: null,
  created_at: "2026-11-13T00:00:00Z",
  updated_at: "2026-11-13T00:00:00Z",
};

const item = {
  id: "k1",
  space_id: "s1",
  title: "知识点",
  content: "内容详情",
  status: "draft",
  source_refs: [
    {
      id: "sr1",
      source_type: "conversation",
      uri: null,
      conversation_id: "c1abcdef-0000-0000-0000-000000000000",
      excerpt: "对话摘录",
      created_at: "2026-11-13T00:00:00Z",
    },
  ],
  created_at: "2026-11-13T00:00:00Z",
  updated_at: "2026-11-13T00:00:00Z",
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("KnowledgeView", () => {
  it("加载空间与知识条目并展示来源追溯", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === "/api/spaces") return ok([space]);
        if (url === "/api/knowledge?space_id=s1") return ok([item]);
        return { ok: false, status: 404 };
      }),
    );

    render(<KnowledgeView />);

    expect(await screen.findByText("知识点")).toBeInTheDocument();
    expect(screen.getByText("内容详情")).toBeInTheDocument();
    expect(screen.getByText(/来源：对话/)).toBeInTheDocument();
  });

  it("创建知识条目后刷新列表", async () => {
    let created = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const method = init?.method ?? "GET";
        if (url === "/api/spaces") return ok([space]);
        if (url === "/api/knowledge?space_id=s1" && method === "GET") {
          return ok(created ? [item] : []);
        }
        if (url === "/api/knowledge" && method === "POST") {
          created = true;
          return ok(item);
        }
        return { ok: false, status: 404 };
      }),
    );

    render(<KnowledgeView />);
    await screen.findByText(/该空间暂无知识条目/);
    fireEvent.change(screen.getByLabelText("知识标题"), { target: { value: "知识点" } });
    fireEvent.change(screen.getByLabelText("知识内容"), { target: { value: "内容详情" } });
    fireEvent.click(screen.getByText("创建"));

    expect(await screen.findByText("知识点")).toBeInTheDocument();
  });

  it("编辑生效条目收到 202 时提示已提交审核", async () => {
    const activeItem = { ...item, status: "active" };
    const review = {
      id: "r1",
      item_id: "k1",
      action: "update_item",
      payload: { title: "改" },
      reason: null,
      status: "pending",
      created_at: "2026-11-14T00:00:00Z",
      resolved_at: null,
      resolution_note: null,
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const method = init?.method ?? "GET";
        if (url === "/api/spaces") return ok([space]);
        if (url === "/api/knowledge?space_id=s1") return ok([activeItem]);
        if (url === "/api/knowledge/k1" && method === "PATCH") {
          return { ok: true, status: 202, json: async () => review };
        }
        return { ok: false, status: 404 };
      }),
    );

    render(<KnowledgeView />);
    await screen.findByText("知识点");
    fireEvent.click(screen.getByText("编辑"));
    fireEvent.change(screen.getByLabelText("知识标题"), { target: { value: "改" } });
    fireEvent.click(screen.getByText("保存修改"));

    expect(await screen.findByText(/已提交审核/)).toBeInTheDocument();
  });

  it("治理详情展示关系 / 版本 / 来源并支持查重分析", async () => {
    const relation = {
      id: "rel1",
      source_id: "k1",
      target_id: "k2abcdef-0000-0000-0000-000000000000",
      relation_type: "related",
      confidence: 0.8,
      origin: "llm",
      created_at: "2026-11-14T00:00:00Z",
    };
    const version = {
      id: "v1",
      item_id: "k1",
      version: 1,
      title: "知识点",
      content: "旧内容",
      change_summary: "编辑前快照",
      created_at: "2026-11-14T00:00:00Z",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const method = init?.method ?? "GET";
        if (url === "/api/spaces") return ok([space]);
        if (url === "/api/knowledge?space_id=s1") return ok([item]);
        if (url === "/api/knowledge/k1/relations") return ok([relation]);
        if (url === "/api/knowledge/k1/versions") return ok([version]);
        if (url === "/api/knowledge/k1/analyze" && method === "POST") {
          return ok({
            duplicates: [{ item_id: "k2", score: 0.9, title: "近似条目" }],
            relations: [relation],
          });
        }
        return { ok: false, status: 404 };
      }),
    );

    render(<KnowledgeView />);
    await screen.findByText("知识点");
    fireEvent.click(screen.getByText("治理详情"));

    expect(await screen.findByText(/相关 · k2abcdef/)).toBeInTheDocument();
    expect(screen.getByText(/v1 · 编辑前快照/)).toBeInTheDocument();
    expect(screen.getByText(/来源（1）/)).toBeInTheDocument();

    fireEvent.click(screen.getByText("查重分析"));
    expect(await screen.findByText(/疑似重复：近似条目/)).toBeInTheDocument();
    expect(screen.getByText("合并")).toBeInTheDocument();
  });
});