import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChatView } from "./ChatView";

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

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ChatView", () => {
  it("加载并展示会话列表", async () => {
    const conv = {
      id: "c1",
      space_id: "s1",
      title: "学习会话",
      created_at: "2026-11-13T00:00:00Z",
      updated_at: "2026-11-13T00:00:00Z",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === "/api/spaces") return ok([space]);
        if (url === "/api/conversations") return ok([conv]);
        return { ok: false, status: 404 };
      }),
    );

    render(<ChatView />);

    expect(await screen.findByText("学习会话")).toBeInTheDocument();
  });

  it("创建会话并打开线程", async () => {
    const detail = {
      id: "c1",
      space_id: "s1",
      title: "新会话",
      created_at: "2026-11-13T00:00:00Z",
      updated_at: "2026-11-13T00:00:00Z",
      messages: [],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const method = init?.method ?? "GET";
        if (url === "/api/spaces") return ok([space]);
        if (url === "/api/conversations" && method === "GET") return ok([]);
        if (url === "/api/conversations" && method === "POST") return ok(detail);
        if (url === "/api/conversations/c1") return ok(detail);
        return { ok: false, status: 404 };
      }),
    );

    render(<ChatView />);
    fireEvent.change(screen.getByLabelText("新会话标题"), { target: { value: "新会话" } });
    fireEvent.click(screen.getByText("创建会话"));

    expect(await screen.findByRole("heading", { name: "新会话" })).toBeInTheDocument();
  });

  it("模型未配置时如实展示 503 指引而非假回复", async () => {
    const conv = {
      id: "c1",
      space_id: "s1",
      title: "会话",
      created_at: "2026-11-13T00:00:00Z",
      updated_at: "2026-11-13T00:00:00Z",
    };
    const detail = {
      ...conv,
      messages: [
        { id: "m0", role: "user", content: "你好", created_at: "2026-11-13T00:00:00Z" },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const method = init?.method ?? "GET";
        if (url === "/api/spaces") return ok([space]);
        if (url === "/api/conversations" && method === "GET") return ok([conv]);
        if (url === "/api/conversations/c1" && method === "GET") return ok(detail);
        if (url === "/api/conversations/c1/chat" && method === "POST") {
          return {
            ok: false,
            status: 503,
            json: async () => ({ detail: "模型未配置：请在 backend/.env 设置" }),
          };
        }
        return { ok: false, status: 404 };
      }),
    );

    render(<ChatView />);
    fireEvent.click(await screen.findByRole("button", { name: "会话" }));
    await screen.findByText("你好");
    fireEvent.change(screen.getByLabelText("消息输入"), { target: { value: "新问题" } });
    fireEvent.click(screen.getByText("发送"));

    expect(await screen.findByRole("alert")).toHaveTextContent("模型未配置");
  });
});