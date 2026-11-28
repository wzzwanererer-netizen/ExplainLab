import type {
  AgentAddInput,
  AgentStatus,
  AnalyzeResponse,
  AnswerFeedback,
  ChatCitation,
  CompletedTaskSuggestion,
  Conversation,
  ConversationDetail,
  DocPreviewResponse,
  DuplicateCandidate,
  ExperimentAnswerInput,
  ExperimentCompleteResult,
  ExperimentCreateInput,
  ExperimentListOptions,
  ExperimentSession,
  ExtractResponse,
  FolderPreset,
  FolderScanReport,
  GraphOptions,
  GraphResponse,
  HealthResponse,
  KnowledgeCreateInput,
  KnowledgeItem,
  KnowledgeRelation,
  KnowledgeUpdateInput,
  KnowledgeVersion,
  LibraryMediaItem,
  LinkItem,
  MarkdownImportInput,
  MarkdownImportReport,
  MediaItem,
  Message,
  ModelSettings,
  ModelSettingsUpdateInput,
  ModelTestResult,
  MutationResult,
  RelationCreateInput,
  ReindexResponse,
  ReviewRequest,
  ReviewStatus,
  ReviewSubmitInput,
  ReviewSubmitResult,
  SandboxResponse,
  SearchOptions,
  SearchResponse,
  SessionFilePreview,
  SourceAttachInput,
  SourceRef,
  Space,
  AttachmentItem,
  AttachmentUploadInput,
  VacuumReport,
  WatchedFolder,
} from "./types";

import { handleDemoRequest, IS_STATIC_DEMO } from "./demoRuntime";

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
  const response = IS_STATIC_DEMO
    ? await handleDemoRequest(path, init)
    : await fetch(path, {
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

  // 模型与 API Key 热更新设置
  getModelSettings: () => request<ModelSettings>("/api/settings/models"),
  updateModelSettings: (input: ModelSettingsUpdateInput) =>
    request<ModelSettings>("/api/settings/models", {
      method: "PUT",
      body: JSON.stringify(input),
    }),
  testModelConnection: (input: {
    base_url: string;
    model_name: string;
    api_key?: string | null;
  }) =>
    request<ModelTestResult>("/api/settings/models/test", {
      method: "POST",
      body: JSON.stringify(input),
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
  chatStream: async (
    id: string,
    content: string,
    handlers: {
      onCitations?: (citations: ChatCitation[]) => void;
      onDelta?: (chunk: string) => void;
      onDone?: (message: Message) => void;
    },
  ): Promise<Message> => {
    if (IS_STATIC_DEMO) {
      const msg = await api.chat(id, content);
      handlers.onDone?.(msg);
      return msg;
    }
    const response = await fetch(`/api/conversations/${id}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    });

    // 若遇到 404（如旧版接口或单测仅 stub 了 /chat），优雅回退到非流式 /chat
    if (response.status === 404) {
      const msg = await api.chat(id, content);
      handlers.onDone?.(msg);
      return msg;
    }

    if (!response.ok) {
      let detail = "";
      try {
        const body = (await response.json()) as { detail?: unknown };
        if (typeof body.detail === "string") detail = body.detail;
      } catch {
        // ignore
      }
      throw new ApiError(
        response.status,
        detail || `请求失败（HTTP ${response.status}）：/api/conversations/${id}/chat/stream`,
      );
    }

    if (!response.body) {
      const msg = await api.chat(id, content);
      handlers.onDone?.(msg);
      return msg;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let finalMessage: Message | null = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";
      for (const rawEvent of parts) {
        for (const line of rawEvent.split("\n")) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data:")) continue;
          const jsonText = trimmed.slice(5).trim();
          if (!jsonText) continue;
          const evt = JSON.parse(jsonText) as
            | { type: "citations"; citations: ChatCitation[] }
            | { type: "delta"; content: string }
            | { type: "done"; message: Message }
            | { type: "error"; detail: string };
          if (evt.type === "citations") {
            handlers.onCitations?.(evt.citations);
          } else if (evt.type === "delta") {
            handlers.onDelta?.(evt.content);
          } else if (evt.type === "done") {
            finalMessage = evt.message;
            handlers.onDone?.(evt.message);
          } else if (evt.type === "error") {
            throw new ApiError(502, evt.detail);
          }
        }
      }
    }

    if (!finalMessage) {
      throw new ApiError(502, "流式响应意外中断，未收到完成信号。");
    }
    return finalMessage;
  },
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

  // M4 知识地图：节点 + 边只读视图
  getGraph: (options: GraphOptions = {}) => {
    const params = new URLSearchParams();
    if (options.spaceId) params.set("space_id", options.spaceId);
    if (options.includeArchived) params.set("include_archived", "true");
    const qs = params.toString();
    return request<GraphResponse>(`/api/graph${qs ? `?${qs}` : ""}`);
  },

  // M5 交互式知识实验：测验 / 对比 / 学习路径
  createExperiment: (input: ExperimentCreateInput) =>
    request<ExperimentSession>("/api/experiments/sessions", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  listExperiments: (options: ExperimentListOptions = {}) => {
    const params = new URLSearchParams();
    if (options.kind) params.set("kind", options.kind);
    if (options.spaceId) params.set("space_id", options.spaceId);
    const qs = params.toString();
    return request<ExperimentSession[]>(
      `/api/experiments/sessions${qs ? `?${qs}` : ""}`,
    );
  },
  getExperiment: (id: string) =>
    request<ExperimentSession>(`/api/experiments/sessions/${id}`),
  answerExperiment: (id: string, index: number, value: number) =>
    request<AnswerFeedback>(`/api/experiments/sessions/${id}/answer`, {
      method: "POST",
      body: JSON.stringify({ index, value }),
    }),
  completeExperiment: (id: string, answers: ExperimentAnswerInput[]) =>
    request<ExperimentCompleteResult>(`/api/experiments/sessions/${id}/complete`, {
      method: "POST",
      body: JSON.stringify({ answers }),
    }),
  deleteExperiment: (id: string) =>
    request<void>(`/api/experiments/sessions/${id}`, { method: "DELETE" }),

  // V2 附件（JSON Base64 上传 / 列表 / 流式下载 URL / 删除）
  listAttachments: (itemId: string) =>
    request<AttachmentItem[]>(`/api/knowledge/${itemId}/attachments`),
  uploadAttachment: (itemId: string, input: AttachmentUploadInput) =>
    request<AttachmentItem>(`/api/knowledge/${itemId}/attachments`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  downloadAttachmentUrl: (itemId: string, attachmentId: string) =>
    `/api/knowledge/${itemId}/attachments/${attachmentId}`,
  deleteAttachment: (itemId: string, attachmentId: string) =>
    request<void>(`/api/knowledge/${itemId}/attachments/${attachmentId}`, {
      method: "DELETE",
    }),

  // V2 双链只读查询
  listLinks: (itemId: string) => request<LinkItem[]>(`/api/knowledge/${itemId}/links`),
  listBacklinks: (itemId: string) => request<LinkItem[]>(`/api/knowledge/${itemId}/backlinks`),

  // V3 AI 助手副库管理中心 & 本地会话吸尘器
  discoverAgents: () => request<AgentStatus[]>("/api/agents/discover"),
  addAgent: (input: AgentAddInput) =>
    request<AgentStatus>("/api/agents/add", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  listAgentSessions: (agentId: string) =>
    request<SessionFilePreview[]>(`/api/agents/${encodeURIComponent(agentId)}/sessions`),
  vacuumAgents: (
    agentName?: string | null,
    maxSessions = 3,
    sessionFiles?: string[] | null,
  ) =>
    request<VacuumReport>("/api/agents/vacuum", {
      method: "POST",
      body: JSON.stringify({
        agent_name: agentName ?? null,
        max_sessions: maxSessions,
        session_files: sessionFiles && sessionFiles.length > 0 ? sessionFiles : null,
      }),
    }),
  getCompletedSuggestions: (includeLatest = false) =>
    request<CompletedTaskSuggestion[]>(
      `/api/agents/completed-suggestions?include_latest=${includeLatest ? "true" : "false"}`,
    ),
  dismissTaskSuggestion: (filePath: string, signature: string) =>
    request<{ ok: boolean }>("/api/agents/dismiss-suggestion", {
      method: "POST",
      body: JSON.stringify({ file_path: filePath, signature }),
    }),

  // V3 交互式动态原理沙盒
  getSandbox: (itemId: string) =>
    request<SandboxResponse>(`/api/knowledge/${itemId}/sandbox`),
  generateSandbox: (itemId: string, instruction?: string) =>
    request<SandboxResponse>(`/api/knowledge/${itemId}/sandbox/generate`, {
      method: "POST",
      body: JSON.stringify({ instruction: instruction?.trim() || null }),
    }),
  deleteSandbox: (itemId: string) =>
    request<void>(`/api/knowledge/${itemId}/sandbox`, { method: "DELETE" }),

  // V3 多模态媒体附件（图片 / 音频 / 视频 Range 流式播放 / Word / Excel / PPT / PDF 阅读器）
  listMediaLibrary: (kind?: string | null) =>
    request<LibraryMediaItem[]>(
      `/api/media/library${kind && kind !== "all" ? `?kind=${encodeURIComponent(kind)}` : ""}`,
    ),
  listItemMedia: (itemId: string) =>
    request<MediaItem[]>(`/api/knowledge/${itemId}/media`),
  previewItemMedia: (itemId: string, mediaId: string) =>
    request<DocPreviewResponse>(`/api/knowledge/${itemId}/media/${mediaId}/preview`),
  revealItemMedia: async (itemId: string, mediaId: string): Promise<void> => {
    const bridge = (
      window as unknown as {
        explainlabDesktop?: { showItemInFolder?: (p: string) => void };
      }
    ).explainlabDesktop;
    const hasDesktopBridge = Boolean(bridge?.showItemInFolder);
    const res = await request<{ path?: string }>(
      `/api/knowledge/${itemId}/media/${mediaId}/reveal?open_os=${hasDesktopBridge ? "false" : "true"}`,
      { method: "POST" },
    );
    if (res?.path && bridge?.showItemInFolder) {
      bridge.showItemInFolder(res.path);
    }
  },
  uploadItemMedia: async (itemId: string, file: File): Promise<MediaItem> => {
    const res = await fetch(
      `/api/knowledge/${itemId}/media?filename=${encodeURIComponent(file.name)}`,
      {
        method: "POST",
        headers: { "Content-Type": file.type || "application/octet-stream" },
        body: file,
      },
    );
    if (!res.ok) {
      let detail = `上传失败 (${res.status})`;
      try {
        const j = (await res.json()) as { detail?: string };
        if (j.detail) detail = j.detail;
      } catch {
        // ignore
      }
      throw new ApiError(res.status, detail);
    }
    return (await res.json()) as MediaItem;
  },
  deleteItemMedia: (itemId: string, mediaId: string) =>
    request<void>(`/api/knowledge/${itemId}/media/${mediaId}`, { method: "DELETE" }),

  // V3 乱文件夹哨兵（只读监听与收编）
  listFolderPresets: () => request<FolderPreset[]>("/api/folders/presets"),
  listWatchedFolders: () => request<WatchedFolder[]>("/api/folders"),
  addWatchedFolder: (input: {
    path: string;
    name?: string | null;
    space_id?: string | null;
    use_ai_summary?: boolean;
  }) =>
    request<WatchedFolder>("/api/folders", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  patchWatchedFolder: (
    folderId: string,
    patch: { enabled?: boolean; use_ai_summary?: boolean },
  ) =>
    request<WatchedFolder>(`/api/folders/${folderId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  deleteWatchedFolder: (folderId: string) =>
    request<void>(`/api/folders/${folderId}`, { method: "DELETE" }),
  scanWatchedFolder: (folderId: string, maxFiles = 12) =>
    request<FolderScanReport>(`/api/folders/${folderId}/scan`, {
      method: "POST",
      body: JSON.stringify({ max_files: maxFiles }),
    }),
  revealLocalPath: (path: string) =>
    request<void>("/api/folders/reveal", {
      method: "POST",
      body: JSON.stringify({ path }),
    }),

  // V2 Markdown / ZIP 导入导出
  importMarkdown: (input: MarkdownImportInput) =>
    request<MarkdownImportReport>("/api/knowledge/import", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  exportMarkdownZip: async (spaceId?: string | null): Promise<Blob> => {
    const response = await send("/api/knowledge/export", {
      method: "POST",
      body: JSON.stringify({ ids: [], space_id: spaceId ?? null, include_attachments: false }),
    });
    return await response.blob();
  },
  exportSingleMarkdownUrl: (itemId: string) => `/api/knowledge/${itemId}/markdown`,

  // V3 一键生成办公成品（总结 PDF / 汇报 PPT / 可编辑 Word / 高清知识卡片长图，支持自选保存目录）
  generateDeliverable: async (
    format: "pdf" | "pptx" | "docx" | "card",
    target: { space_id?: string | null; item_id?: string | null; title?: string | null },
  ): Promise<{ saved: boolean; canceled?: boolean; path?: string; filename: string }> => {
    const bridge = (
      window as unknown as {
        explainlabDesktop?: {
          saveBinaryFile?: (p: {
            defaultFilename: string;
            filterName: string;
            extensions: string[];
            base64: string;
          }) => Promise<{ saved: boolean; canceled?: boolean; path?: string }>;
          exportHtmlToPdf?: (p: {
            defaultFilename: string;
            html: string;
          }) => Promise<{ saved: boolean; canceled?: boolean; path?: string }>;
          exportHtmlToPng?: (p: {
            defaultFilename: string;
            html: string;
          }) => Promise<{ saved: boolean; canceled?: boolean; path?: string }>;
        };
      }
    ).explainlabDesktop;

    if (format === "pdf" || format === "card") {
      const res = await request<{ filename: string; html: string; item_count: number }>(
        "/api/export/html",
        {
          method: "POST",
          body: JSON.stringify({ ...target, mode: format === "card" ? "card" : "pdf" }),
        },
      );
      if (format === "pdf" && bridge?.exportHtmlToPdf) {
        const out = await bridge.exportHtmlToPdf({
          defaultFilename: res.filename,
          html: res.html,
        });
        return { ...out, filename: res.filename };
      }
      if (format === "card" && bridge?.exportHtmlToPng) {
        const out = await bridge.exportHtmlToPng({
          defaultFilename: res.filename,
          html: res.html,
        });
        return { ...out, filename: res.filename };
      }
      const win = window.open("", "_blank");
      if (win) {
        win.document.write(res.html);
        win.document.close();
        if (format === "pdf") {
          window.setTimeout(() => win.print(), 300);
        }
      }
      return { saved: true, filename: res.filename };
    }

    const endpoint = format === "docx" ? "/api/export/docx" : "/api/export/pptx";
    const resp = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(target),
    });
    if (!resp.ok) {
      let detail = `生成失败 (${resp.status})`;
      try {
        const j = (await resp.json()) as { detail?: string };
        if (j.detail) detail = j.detail;
      } catch {
        // ignore
      }
      throw new ApiError(resp.status, detail);
    }
    const cd = resp.headers.get("content-disposition") || "";
    const m = cd.match(/filename\*=UTF-8''([^;]+)/i);
    const filename = m ? decodeURIComponent(m[1]) : `Nesti-知识总结.${format}`;
    const buf = await resp.arrayBuffer();

    if (bridge?.saveBinaryFile) {
      const bytes = new Uint8Array(buf);
      let binary = "";
      for (let i = 0; i < bytes.length; i += 0x8000) {
        binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
      }
      const out = await bridge.saveBinaryFile({
        defaultFilename: filename,
        filterName: format === "docx" ? "Word 文档" : "PowerPoint 演示文稿",
        extensions: [format],
        base64: btoa(binary),
      });
      return { ...out, filename };
    }

    const blob = new Blob([buf]);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    return { saved: true, filename };
  },

  // V3 网址一键剪藏（贴链接直接抓正文转为 Markdown 卡片入库）
  clipUrl: (url: string, spaceId?: string | null) =>
    request<KnowledgeItem>("/api/export/clip-url", {
      method: "POST",
      body: JSON.stringify({ url, space_id: spaceId ?? null }),
    }),

  // V3 AI 一句话生成 UI 风格插件草稿
  generateStylePlugin: (prompt: string) =>
    request<{
      name: string;
      englishName: string;
      description: string;
      mode: "light" | "dark";
      canvasBg: string;
      cardBg: string;
      accent: string;
      secondary: string;
      fontMood: "sans" | "serif" | "mono";
      texture: "none" | "grid" | "dots" | "aurora";
      cornerStyle: "sharp" | "balanced" | "soft";
    }>("/api/export/generate-style", {
      method: "POST",
      body: JSON.stringify({ prompt }),
    }),
};