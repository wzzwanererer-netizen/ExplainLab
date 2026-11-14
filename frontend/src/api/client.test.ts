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
  embed_adapter: "not_configured",
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

describe("api client M2", () => {
  const review = {
    id: "r1",
    item_id: "k1",
    action: "update_item",
    payload: { title: "新" },
    reason: null,
    status: "pending",
    created_at: "2026-11-14T00:00:00Z",
    resolved_at: null,
    resolution_note: null,
  };

  it("updateKnowledge 收到 202 时返回审核单而非条目", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 202, json: async () => review }),
    );

    const result = await api.updateKnowledge("k1", { title: "新" });

    expect(result.kind).toBe("review");
    if (result.kind === "review") {
      expect(result.review.id).toBe("r1");
      expect(result.review.status).toBe("pending");
    }
  });

  it("updateKnowledge 收到 200 时返回已应用条目", async () => {
    const item = { id: "k1", title: "新" };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => item }),
    );

    const result = await api.updateKnowledge("k1", { title: "新" });

    expect(result.kind).toBe("applied");
  });

  it("deleteKnowledge 处理 204 直接删除与 202 审核", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 204, json: vi.fn() }),
    );
    await expect(api.deleteKnowledge("k1")).resolves.toMatchObject({ kind: "applied" });

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 202, json: async () => review }),
    );
    await expect(api.deleteKnowledge("k1")).resolves.toMatchObject({ kind: "review" });
  });

  it("submitReview 以 POST 提交审核动作", async () => {
    const fetchMock = mockFetchOnce({
      ok: true,
      status: 201,
      json: async () => ({ applied: false, review }),
    });

    const result = await api.submitReview({
      item_id: "k1",
      action: "merge_duplicate",
      payload: { target_id: "k2" },
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/reviews",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          item_id: "k1",
          action: "merge_duplicate",
          payload: { target_id: "k2" },
        }),
      }),
    );
    expect(result.applied).toBe(false);
    expect(result.review?.id).toBe("r1");
  });

  it("restoreVersion 收到 202 时返回审核单", async () => {
    const fetchMock = mockFetchOnce({ ok: true, status: 202, json: async () => review });

    const result = await api.restoreVersion("k1", 2);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/knowledge/k1/versions/2/restore",
      expect.objectContaining({ method: "POST" }),
    );
    expect(result.kind).toBe("review");
  });

  it("listReviews 携带状态筛选参数", async () => {
    const fetchMock = mockFetchOnce({ ok: true, status: 200, json: async () => [] });
    await api.listReviews("pending");
    expect(fetchMock).toHaveBeenCalledWith("/api/reviews?status=pending", expect.anything());
  });
});

describe("api client M3", () => {
  const searchResponse = {
    query: "知识图谱",
    mode: "fts",
    count: 1,
    embed_capability: "not_configured",
    results: [
      {
        item_id: "k1",
        score: 0.016,
        snippet: "知识图谱是…",
        title: "知识图谱的定义",
        space_id: null,
        status: "active",
        channels: { fts: -0.0000013 },
      },
    ],
  };

  it("search 携带 query / space_id / mode 查询参数", async () => {
    const fetchMock = mockFetchOnce({
      ok: true,
      status: 200,
      json: async () => searchResponse,
    });

    const result = await api.search("知识图谱", { spaceId: "s1", mode: "hybrid" });

    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain("/api/search?");
    expect(url).toContain("query=%E7%9F%A5%E8%AF%86%E5%9B%BE%E8%B0%B1");
    expect(url).toContain("space_id=s1");
    expect(url).toContain("mode=hybrid");
    expect(result.embed_capability).toBe("not_configured");
    expect(result.results[0].title).toBe("知识图谱的定义");
  });

  it("search 默认仅携带 query（跨全部空间）", async () => {
    const fetchMock = mockFetchOnce({
      ok: true,
      status: 200,
      json: async () => searchResponse,
    });
    await api.search("知识图谱");
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).not.toContain("space_id");
    expect(url).not.toContain("mode");
  });

  it("reindex 以 POST 重建索引", async () => {
    const fetchMock = mockFetchOnce({
      ok: true,
      status: 200,
      json: async () => ({ indexed: 3, embed_capability: "not_configured" }),
    });

    const result = await api.reindex();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/search/reindex",
      expect.objectContaining({ method: "POST" }),
    );
    expect(result.indexed).toBe(3);
  });

  it("getKnowledge 请求单条知识详情", async () => {
    const fetchMock = mockFetchOnce({
      ok: true,
      status: 200,
      json: async () => ({ id: "k1", title: "知识图谱的定义" }),
    });
    const result = await api.getKnowledge("k1");
    expect(fetchMock).toHaveBeenCalledWith("/api/knowledge/k1", expect.anything());
    expect(result.title).toBe("知识图谱的定义");
  });
});