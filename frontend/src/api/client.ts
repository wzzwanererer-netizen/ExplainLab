import type {
  Conversation,
  ConversationDetail,
  ExtractResponse,
  HealthResponse,
  KnowledgeCreateInput,
  KnowledgeItem,
  KnowledgeUpdateInput,
  Message,
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
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
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
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
  createKnowledge: (input: KnowledgeCreateInput) =>
    request<KnowledgeItem>("/api/knowledge", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  updateKnowledge: (id: string, patch: KnowledgeUpdateInput) =>
    request<KnowledgeItem>(`/api/knowledge/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  deleteKnowledge: (id: string) =>
    request<void>(`/api/knowledge/${id}`, { method: "DELETE" }),
};