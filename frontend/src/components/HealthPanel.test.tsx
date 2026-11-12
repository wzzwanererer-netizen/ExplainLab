import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HealthPanel } from "./HealthPanel";
import type { HealthResponse } from "../api/types";

const healthPayload: HealthResponse = {
  status: "ok",
  app: "ExplainLab",
  version: "0.1.0",
  environment: "development",
  database: { connected: true, dialect: "sqlite", error: null },
  model_adapter: "not_configured",
  timestamp: "2026-11-12T12:00:00Z",
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HealthPanel", () => {
  it("加载后展示真实健康数据", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => healthPayload,
      }),
    );

    render(<HealthPanel />);

    expect(screen.getByRole("status")).toHaveTextContent("正在连接后端");
    expect(await screen.findByText("正常")).toBeInTheDocument();
    expect(screen.getByText(/sqlite · 已连接/)).toBeInTheDocument();
    expect(screen.getByText(/未配置/)).toBeInTheDocument();
    expect(screen.getByText(/ExplainLab v0\.1\.0/)).toBeInTheDocument();
  });

  it("后端不可达时展示错误态而非假数据", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    render(<HealthPanel />);

    expect(await screen.findByText("无法连接后端")).toBeInTheDocument();
    expect(screen.getByText("Failed to fetch")).toBeInTheDocument();
    expect(screen.queryByText("正常")).not.toBeInTheDocument();
  });
});