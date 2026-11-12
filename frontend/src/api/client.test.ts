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