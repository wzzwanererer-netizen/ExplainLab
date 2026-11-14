import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ExperimentsView } from "./ExperimentsView";

function ok(data: unknown) {
  return { ok: true, status: 200, json: async () => data };
}

const space = {
  id: "s1",
  name: "个人总知识库",
  kind: "personal",
  description: null,
  created_at: "2026-11-15T00:00:00Z",
  updated_at: "2026-11-15T00:00:00Z",
};

const itemK1 = {
  id: "k1",
  space_id: "s1",
  title: "定义",
  content: "知识图谱是一种网络结构数据模型。",
  status: "active",
  source_refs: [],
  created_at: "2026-11-15T00:00:00Z",
  updated_at: "2026-11-15T00:00:00Z",
};
const itemK2 = {
  id: "k2",
  space_id: "s1",
  title: "概念",
  content: "概念是思维的基本单位。",
  status: "active",
  source_refs: [],
  created_at: "2026-11-15T00:00:00Z",
  updated_at: "2026-11-15T00:00:00Z",
};
const items = [itemK1, itemK2];

const quizQuestionPublic = {
  index: 0,
  prompt: "什么是知识图谱?",
  kind: "single_choice",
  options: ["网络结构", "线性表"],
  source_item_id: "k1",
};
const quizSession = {
  id: "exp-quiz",
  kind: "quiz",
  title: "知识测验 · 定义",
  space_id: "s1",
  item_ids: ["k1"],
  payload: { questions: [quizQuestionPublic] },
  status: "active",
  created_at: "2026-11-15T00:00:00Z",
  updated_at: "2026-11-15T00:00:00Z",
};
const quizCompleted = {
  ...quizSession,
  status: "completed",
  payload: {
    questions: [{ ...quizQuestionPublic, correct_index: 0, explanation: "图由节点与边构成。" }],
  },
};
const completeResult = {
  session: quizCompleted,
  attempt: {
    id: "att-1",
    session_id: "exp-quiz",
    answers: [{ index: 0, value: 0, correct: true }],
    correct_count: 1,
    total: 1,
    score: 1,
    created_at: "2026-11-15T00:00:00Z",
  },
};
const compareSession = {
  id: "exp-cmp",
  kind: "compare",
  title: "知识对比 · 定义 ↔ 概念",
  space_id: "s1",
  item_ids: ["k1", "k2"],
  payload: {
    compare: {
      item_a_id: "k1",
      item_b_id: "k2",
      similarities: ["都是抽象结构"],
      differences: ["图强调关系，概念强调内涵"],
      relationship: "二者相关但侧重不同。",
      relation_type: "related",
    },
  },
  status: "active",
  created_at: "2026-11-15T00:00:00Z",
  updated_at: "2026-11-15T00:00:00Z",
};
const chainSession = {
  id: "exp-chain",
  kind: "chain",
  title: "学习路径 · 定义",
  space_id: "s1",
  item_ids: ["k2", "k1"],
  payload: {
    steps: [
      { item_id: "k2", title: "概念", relation_from_prev: null, position: 0 },
      { item_id: "k1", title: "定义", relation_from_prev: "depends_on", position: 1 },
    ],
  },
  status: "active",
  created_at: "2026-11-15T00:00:00Z",
  updated_at: "2026-11-15T00:00:00Z",
};

function stubFetch(opts: { createFail?: boolean } = {}) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (url === "/api/spaces") return ok([space]);
    if (url === "/api/knowledge" || url.startsWith("/api/knowledge?")) return ok(items);
    if (url === "/api/experiments/sessions" && method === "POST") {
      if (opts.createFail) {
        return { ok: false, status: 503, json: async () => ({ detail: "测验需要配置模型" }) };
      }
      const body = JSON.parse(String(init?.body)) as { kind: string };
      if (body.kind === "quiz") return ok(quizSession);
      if (body.kind === "compare") return ok(compareSession);
      return ok(chainSession);
    }
    if (url === "/api/experiments/sessions" && method === "GET") return ok([]);
    if (url.endsWith("/answer")) {
      return ok({ correct: true, correct_value: 0, explanation: "图由节点与边构成。" });
    }
    if (url.endsWith("/complete")) return ok(completeResult);
    if (url.startsWith("/api/experiments/sessions/") && method === "DELETE") {
      return { ok: true, status: 204, json: async () => undefined };
    }
    if (url === "/api/knowledge/k1") return ok(itemK1);
    if (url === "/api/knowledge/k2") return ok(itemK2);
    if (url.endsWith("/relations")) return ok([]);
    if (url.endsWith("/versions")) return ok([]);
    return { ok: false, status: 404, json: async () => ({}) };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ExperimentsView", () => {
  it("渲染三模式卡片与知识选择，初始不可生成", async () => {
    stubFetch();
    render(<ExperimentsView />);
    expect(screen.getByText("出题检验理解")).toBeInTheDocument();
    expect(screen.getByText("辨析异同关系")).toBeInTheDocument();
    expect(screen.getByText("先修优先编排")).toBeInTheDocument();
    expect(await screen.findByLabelText("定义")).toBeInTheDocument();
    expect(screen.getByLabelText("概念")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "生成知识测验" })).toBeDisabled();
  });

  it("测验完整闭环：选择→生成→作答→完成得分", async () => {
    stubFetch();
    render(<ExperimentsView />);
    fireEvent.click(await screen.findByLabelText("定义"));
    fireEvent.click(screen.getByRole("button", { name: "生成知识测验" }));
    expect(await screen.findByText("什么是知识图谱?")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /网络结构/ }));
    expect(await screen.findByText("回答正确")).toBeInTheDocument();
    expect(screen.getByText("图由节点与边构成。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "完成测验" }));
    expect(await screen.findByText("测验完成")).toBeInTheDocument();
    expect(screen.getByText("100%")).toBeInTheDocument();
    expect(screen.getByText(/答对 1 \/ 1 题/)).toBeInTheDocument();
  });

  it("对比：选两条→生成→呈现相同点与不同点", async () => {
    stubFetch();
    render(<ExperimentsView />);
    fireEvent.click(screen.getByText("辨析异同关系"));
    fireEvent.click(await screen.findByLabelText("定义"));
    fireEvent.click(screen.getByLabelText("概念"));
    fireEvent.click(screen.getByRole("button", { name: "生成知识对比" }));
    expect(await screen.findByText("都是抽象结构")).toBeInTheDocument();
    expect(screen.getByText("图强调关系，概念强调内涵")).toBeInTheDocument();
    expect(screen.getByText("相同点（1）")).toBeInTheDocument();
  });

  it("学习路径：选一条→生成→确定性步进器", async () => {
    stubFetch();
    render(<ExperimentsView />);
    fireEvent.click(screen.getByText("先修优先编排"));
    fireEvent.click(await screen.findByLabelText("定义"));
    fireEvent.click(screen.getByRole("button", { name: "生成学习路径" }));
    expect(await screen.findByText(/共 2 步/)).toBeInTheDocument();
    expect(screen.getByText("目标")).toBeInTheDocument();
    expect(screen.getByText("依赖上一步")).toBeInTheDocument();
  });

  it("模型未配置时如实报错", async () => {
    stubFetch({ createFail: true });
    render(<ExperimentsView />);
    fireEvent.click(await screen.findByLabelText("定义"));
    fireEvent.click(screen.getByRole("button", { name: "生成知识测验" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("测验需要配置模型");
  });

  it("历史实验可删除", async () => {
    stubFetch();
    render(<ExperimentsView />);
    fireEvent.click(await screen.findByLabelText("定义"));
    fireEvent.click(screen.getByRole("button", { name: "生成知识测验" }));
    await screen.findByText("什么是知识图谱?");
    fireEvent.click(screen.getByLabelText(/删除实验/));
    await waitFor(() => {
      expect(screen.getByText("历史实验（0）")).toBeInTheDocument();
    });
  });
});