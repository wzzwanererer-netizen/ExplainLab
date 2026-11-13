import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "./client";
import type { HealthResponse } from "./types";

const healthPayload: HealthResponse = {
  status: "ok",
  app: "ExplainLab",
  version: "0.1.0",
  environment: "development",
  database: { connected: true, dialect: "sqlite", error: null },
  model_adapter: "not_configured",
  timestamp: "2026-11-12T12:00:00Z",
};

function mockFetchOnce(response: { ok: boolean; status: number; json?: () => Promise<unknown> }) {
  const fetchMock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api client", () => {
  it("getHealth 请求 /api/health 并解析响应", async () => {
    const fetchMock = mockFetchOnce({
      ok: true,
      status: 200,
      json: async () => healthPayload,
    });

    const data = await api.getHealth();

    expect(fetchMock).toHaveBeenCalledWith("/api/health", expect.anything());
    expect(data.database.dialect).toBe("sqlite");
    expect(data.model_adapter).toBe("not_configured");
  });

  it("非 2xx 响应抛出 ApiError 并携带状态码", async () => {
    mockFetchOnce({ ok: false, status: 503 });

    await expect(api.getHealth()).rejects.toMatchObject({
      name: "ApiError",
      status: 503,
    });
    await expect(api.getHealth()).rejects.toBeInstanceOf(ApiError);
  });

  it("网络错误原样向上抛出", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api.getHealth()).rejects.toThrow("Failed to fetch");
  });
});

describe("api client M1", () => {
  it("chat 以 POST 发送消息内容", async () => {
    const message = {
      id: "m1",
      role: "assistant",
      content: "回复",
      created_at: "2026-11-13T00:00:00Z",
    };
    const fetchMock = mockFetchOnce({ ok: true, status: 200, json: async () => message });

    const result = await api.chat("c1", "你好");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/conversations/c1/chat",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ content: "你好" }) }),
    );
    expect(result.content).toBe("回复");
  });

  it("deleteConversation 处理 204 无响应体", async () => {
    const jsonSpy = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 204, json: jsonSpy }),
    );

    await expect(api.deleteConversation("c1")).resolves.toBeUndefined();
    expect(jsonSpy).not.toHaveBeenCalled();
  });

  it("透传后端错误详情（503 模型未配置）", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        json: async () => ({ detail: "模型未配置：请设置 .env" }),
      }),
    );

    await expect(api.chat("c1", "你好")).rejects.toMatchObject({
      name: "ApiError",
      status: 503,
      message: "模型未配置：请设置 .env",
    });
  });

  it("listKnowledge 携带空间查询参数", async () => {
    const fetchMock = mockFetchOnce({ ok: true, status: 200, json: async () => [] });
    await api.listKnowledge("s1");
    expect(fetchMock).toHaveBeenCalledWith("/api/knowledge?space_id=s1", expect.anything());
  });

  it("createKnowledge 以 POST 提交条目", async () => {
    const item = {
      id: "k1",
      space_id: "s1",
      title: "标题",
      content: "内容",
      status: "draft",
      source_refs: [],
      created_at: "2026-11-13T00:00:00Z",
      updated_at: "2026-11-13T00:00:00Z",
    };
    const fetchMock = mockFetchOnce({ ok: true, status: 200, json: async () => item });

    const result = await api.createKnowledge({ title: "标题", content: "内容", space_id: "s1" });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/knowledge",
      expect.objectContaining({ method: "POST" }),
    );
    expect(result.title).toBe("标题");
  });
});