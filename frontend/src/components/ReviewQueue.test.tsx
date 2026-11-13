import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReviewQueue } from "./ReviewQueue";

function ok(data: unknown) {
  return { ok: true, status: 200, json: async () => data };
}

const pendingReview = {
  id: "r1",
  item_id: "k1abcdef-0000-0000-0000-000000000000",
  action: "update_item",
  payload: { title: "新标题" },
  reason: "重要变更",
  status: "pending",
  created_at: "2026-11-14T00:00:00Z",
  resolved_at: null,
  resolution_note: null,
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ReviewQueue", () => {
  it("展示待审核队列与变更摘要", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === "/api/reviews?status=pending") return ok([pendingReview]);
        return { ok: false, status: 404 };
      }),
    );

    render(<ReviewQueue />);

    expect(await screen.findByText("编辑知识")).toBeInTheDocument();
    expect(screen.getByText(/标题→「新标题」/)).toBeInTheDocument();
    expect(screen.getByText("理由：重要变更")).toBeInTheDocument();
    expect(screen.getByText("批准")).toBeInTheDocument();
    expect(screen.getByText("驳回")).toBeInTheDocument();
  });

  it("批准后刷新队列并提示已应用", async () => {
    let resolved = false;
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (url === "/api/reviews?status=pending") {
        return ok(resolved ? [] : [pendingReview]);
      }
      if (url === "/api/reviews/r1/approve" && method === "POST") {
        resolved = true;
        return ok({ ...pendingReview, status: "approved" });
      }
      return { ok: false, status: 404 };
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewQueue />);
    await screen.findByText("编辑知识");
    fireEvent.click(screen.getByText("批准"));

    expect(await screen.findByText("已批准并应用变更。")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/reviews/r1/approve",
      expect.objectContaining({ method: "POST" }),
    );
    expect(await screen.findByText(/当前筛选下没有审核单/)).toBeInTheDocument();
  });

  it("驳回后提示数据未改动", async () => {
    let resolved = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const method = init?.method ?? "GET";
        if (url === "/api/reviews?status=pending") {
          return ok(resolved ? [] : [pendingReview]);
        }
        if (url === "/api/reviews/r1/reject" && method === "POST") {
          resolved = true;
          return ok({ ...pendingReview, status: "rejected" });
        }
        return { ok: false, status: 404 };
      }),
    );

    render(<ReviewQueue />);
    await screen.findByText("编辑知识");
    fireEvent.click(screen.getByText("驳回"));

    expect(await screen.findByText("已驳回，数据未改动。")).toBeInTheDocument();
  });

  it("空队列如实提示", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ok([])),
    );

    render(<ReviewQueue />);

    expect(await screen.findByText(/当前筛选下没有审核单/)).toBeInTheDocument();
  });
});