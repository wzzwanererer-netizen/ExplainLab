import type {
  AnalyzeResponse,
  Conversation,
  ConversationDetail,
  DuplicateCandidate,
  ExtractResponse,
  HealthResponse,
  KnowledgeCreateInput,
  KnowledgeItem,
  KnowledgeRelation,
  KnowledgeUpdateInput,
  KnowledgeVersion,
  Message,
  MutationResult,
  RelationCreateInput,
  ReindexResponse,
  ReviewRequest,
  ReviewStatus,
  ReviewSubmitInput,
  ReviewSubmitResult,
  SearchOptions,
  SearchResponse,
  SourceAttachInput,
  SourceRef,
  Space,
} from "./types";

/** 统一 API 客户端：所有后端请求都经过这里，前端不持有任何密钥。 */

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    // 如实透传后端错误详情（如 503 模型未配置的具体指引）
    let detail = "";
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") {
        detail = body.detail;
      }
    } catch {
      // 响应体非 JSON 时保留通用错误信息
    }
    throw new ApiError(
      response.status,
      detail || `请求失败（HTTP ${response.status}）：${path}`,
    );
  }
  return response;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await send(path, init);
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

async function requestWithStatus<T>(
  path: string,
  init?: RequestInit,
): Promise<{ status: number; data: T }> {
  const response = await send(path, init);
  if (response.status === 204) {
    return { status: 204, data: undefined as T };
  }
  return { status: response.status, data: (await response.json()) as T };
}

/** 变更类响应：202 = 重要变更进入审核；其余 = 已直接应用。 */
function mutationResult<T>(status: number, data: T | ReviewRequest): MutationResult<T> {
  if (status === 202) {
    return { kind: "review", review: data as ReviewRequest };
  }
  return { kind: "applied", data: data as T };
}

function spaceQuery(spaceId?: string): string {
  return spaceId ? `?space_id=${encodeURIComponent(spaceId)}` : "";
}

export const api = {
  getHealth: () => request<HealthResponse>("/api/health"),

  // 知识空间
  listSpaces: () => request<Space[]>("/api/spaces"),
  createSpace: (name: string, description?: string) =>
    request<Space>("/api/spaces", {
      method: "POST",
      body: JSON.stringify({ name, description: description ?? null }),
    }),

  // 会话与对话
  listConversations: (spaceId?: string) =>
    request<Conversation[]>(`/api/conversations${spaceQuery(spaceId)}`),
  createConversation: (title: string, spaceId?: string | null) =>
    request<ConversationDetail>("/api/conversations", {
      method: "POST",
      body: JSON.stringify({ title, space_id: spaceId ?? null }),
    }),
  getConversation: (id: string) =>
    request<ConversationDetail>(`/api/conversations/${id}`),
  deleteConversation: (id: string) =>
    request<void>(`/api/conversations/${id}`, { method: "DELETE" }),
  chat: (id: string, content: string) =>
    request<Message>(`/api/conversations/${id}/chat`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),
  extractKnowledge: (id: string, spaceId?: string | null) =>
    request<ExtractResponse>(`/api/conversations/${id}/extract`, {
      method: "POST",
      body: JSON.stringify({ space_id: spaceId ?? null }),
    }),

  // 知识条目
  listKnowledge: (spaceId?: string) =>
    request<KnowledgeItem[]>(`/api/knowledge${spaceQuery(spaceId)}`),
  getKnowledge: (id: string) => request<KnowledgeItem>(`/api/knowledge/${id}`),
  createKnowledge: (input: KnowledgeCreateInput) =>
    request<KnowledgeItem>("/api/knowledge", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  updateKnowledge: async (
    id: string,
    patch: KnowledgeUpdateInput,
  ): Promise<MutationResult<KnowledgeItem>> => {
    const { status, data } = await requestWithStatus<KnowledgeItem | ReviewRequest>(
      `/api/knowledge/${id}`,
      { method: "PATCH", body: JSON.stringify(patch) },
    );
    return mutationResult<KnowledgeItem>(status, data);
  },
  deleteKnowledge: async (id: string): Promise<MutationResult<void>> => {
    const { status, data } = await requestWithStatus<ReviewRequest | undefined>(
      `/api/knowledge/${id}`,
      { method: "DELETE" },
    );
    return mutationResult<void>(status, data);
  },

  // M2 治理：查重 / 分析 / 关系 / 版本 / 来源
  findDuplicates: (id: string) =>
    request<DuplicateCandidate[]>(`/api/knowledge/${id}/duplicates`),
  analyzeKnowledge: (id: string) =>
    request<AnalyzeResponse>(`/api/knowledge/${id}/analyze`, { method: "POST" }),
  listRelations: (id: string) =>
    request<KnowledgeRelation[]>(`/api/knowledge/${id}/relations`),
  createRelation: (id: string, input: RelationCreateInput) =>
    request<KnowledgeRelation>(`/api/knowledge/${id}/relations`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  deleteRelation: (relationId: string) =>
    request<void>(`/api/relations/${relationId}`, { method: "DELETE" }),
  listVersions: (id: string) =>
    request<KnowledgeVersion[]>(`/api/knowledge/${id}/versions`),
  restoreVersion: async (
    id: string,
    version: number,
  ): Promise<MutationResult<KnowledgeItem>> => {
    const { status, data } = await requestWithStatus<KnowledgeItem | ReviewRequest>(
      `/api/knowledge/${id}/versions/${version}/restore`,
      { method: "POST" },
    );
    return mutationResult<KnowledgeItem>(status, data);
  },
  attachSource: (id: string, input: SourceAttachInput) =>
    request<SourceRef>(`/api/knowledge/${id}/sources`, {
      method: "POST",
      body: JSON.stringify(input),
    }),

  // M2 治理：审核
  listReviews: (status?: ReviewStatus) =>
    request<ReviewRequest[]>(
      `/api/reviews${status ? `?status=${status}` : ""}`,
    ),
  submitReview: (input: ReviewSubmitInput) =>
    request<ReviewSubmitResult>("/api/reviews", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  approveReview: (id: string, note?: string) =>
    request<ReviewRequest>(`/api/reviews/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ note: note ?? null }),
    }),
  rejectReview: (id: string, note?: string) =>
    request<ReviewRequest>(`/api/reviews/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ note: note ?? null }),
    }),

  // M3 检索：跨会话 / 跨空间混合检索 + 索引重建
  search: (query: string, options: SearchOptions = {}) => {
    const params = new URLSearchParams({ query });
    if (options.spaceId) params.set("space_id", options.spaceId);
    if (options.limit !== undefined) params.set("limit", String(options.limit));
    if (options.mode) params.set("mode", options.mode);
    return request<SearchResponse>(`/api/search?${params.toString()}`);
  },
  reindex: () =>
    request<ReindexResponse>("/api/search/reindex", { method: "POST" }),
};