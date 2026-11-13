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
});