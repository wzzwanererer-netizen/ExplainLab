/** 与后端 app/api/routes/health.py 的响应结构对应。 */

export interface DatabaseHealth {
  connected: boolean;
  dialect: string;
  error: string | null;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  app: string;
  version: string;
  environment: string;
  database: DatabaseHealth;
  model_adapter: string;
  embed_adapter: string;
  timestamp: string;
}

/** 以下与后端 app/api/schemas.py 的 DTO 对应（M1）。 */

export interface Space {
  id: string;
  name: string;
  kind: "personal" | "project";
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
}

export interface ChatCitation {
  item_id: string;
  title: string;
  snippet: string;
  score: number;
  status: KnowledgeStatus;
}

export interface Conversation {
  id: string;
  space_id: string | null;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
}

export type KnowledgeStatus = "draft" | "active" | "archived";

export interface SourceRef {
  id: string;
  source_type: "conversation" | "document" | "manual" | "import";
  uri: string | null;
  conversation_id: string | null;
  excerpt: string | null;
  created_at: string;
}

export interface KnowledgeItem {
  id: string;
  space_id: string | null;
  title: string;
  content: string;
  status: KnowledgeStatus;
  source_refs: SourceRef[];
  created_at: string;
  updated_at: string;
}

export interface ExtractResponse {
  count: number;
  items: KnowledgeItem[];
}

export interface KnowledgeCreateInput {
  title: string;
  content: string;
  space_id?: string | null;
}

export type KnowledgeUpdateInput = Partial<
  Pick<KnowledgeItem, "title" | "content" | "status" | "space_id">
>;

/** 以下与后端 M2 治理 DTO 对应。 */

export type RelationType =
  | "related"
  | "depends_on"
  | "duplicate_of"
  | "refines"
  | "contradicts";

export type RelationOrigin = "manual" | "llm" | "dedup";

export interface KnowledgeRelation {
  id: string;
  source_id: string;
  target_id: string;
  relation_type: RelationType;
  confidence: number;
  origin: RelationOrigin;
  created_at: string;
}

export interface RelationCreateInput {
  target_id: string;
  relation_type: RelationType;
  confidence?: number;
}

export interface KnowledgeVersion {
  id: string;
  item_id: string;
  version: number;
  title: string;
  content: string;
  change_summary: string | null;
  created_at: string;
}

export type ReviewStatus = "pending" | "approved" | "rejected";

export type ReviewAction =
  | "update_item"
  | "delete_item"
  | "merge_duplicate"
  | "restore_version";

export interface ReviewRequest {
  id: string;
  item_id: string;
  action: ReviewAction;
  payload: Record<string, unknown>;
  reason: string | null;
  status: ReviewStatus;
  created_at: string;
  resolved_at: string | null;
  resolution_note: string | null;
}

export interface ReviewSubmitInput {
  item_id: string;
  action: ReviewAction;
  payload?: Record<string, unknown>;
  reason?: string | null;
}

export interface ReviewSubmitResult {
  applied: boolean;
  review: ReviewRequest | null;
}

export interface DuplicateCandidate {
  item_id: string;
  score: number;
  title: string;
}

export interface AnalyzeResponse {
  duplicates: DuplicateCandidate[];
  relations: KnowledgeRelation[];
}

export interface SourceAttachInput {
  source_type: SourceRef["source_type"];
  uri?: string | null;
  conversation_id?: string | null;
  excerpt?: string | null;
}

/**
 * 变更类请求的结果：重要变更被审核门禁拦截时返回审核单（HTTP 202），
 * 否则直接应用。前端据此提示「已提交审核」。
 */
export type MutationResult<T> =
  | { kind: "applied"; data: T }
  | { kind: "review"; review: ReviewRequest };

/** 以下与后端 M3 检索 DTO 对应。 */

export type SearchMode = "hybrid" | "fts" | "vector";

/** 向量通道能力（后端如实上报）：未配置 / 已配置 / 支持 / 不支持。 */
export type EmbedCapability =
  | "not_configured"
  | "configured"
  | "supported"
  | "unsupported";

export interface SearchHit {
  item_id: string;
  score: number;
  snippet: string;
  title: string;
  space_id: string | null;
  status: KnowledgeStatus;
  channels: Record<string, number>;
}

export interface SearchResponse {
  query: string;
  mode: SearchMode;
  count: number;
  embed_capability: EmbedCapability;
  results: SearchHit[];
}

export interface ReindexResponse {
  indexed: number;
  embed_capability: EmbedCapability;
}

export interface SearchOptions {
  spaceId?: string | null;
  limit?: number;
  mode?: SearchMode;
}

/** 以下与后端 M4 知识地图 DTO 对应。 */

export interface GraphNode {
  id: string;
  title: string;
  status: KnowledgeStatus;
  space_id: string | null;
}

export interface GraphEdge {
  id: string;
  source_id: string;
  target_id: string;
  relation_type: RelationType;
  confidence: number;
  origin: RelationOrigin;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GraphOptions {
  spaceId?: string | null;
  includeArchived?: boolean;
}

/** 以下与后端 M5 交互式知识实验 DTO 对应。 */

export type ExperimentKind = "quiz" | "compare" | "chain";
export type ExperimentStatus = "active" | "completed";
export type QuizQuestionKind = "single_choice" | "true_false";

/** 测验题对外视图：correct_index / explanation 仅在会话完成后出现。 */
export interface QuizQuestionPublic {
  index: number;
  prompt: string;
  kind: QuizQuestionKind;
  options: string[];
  source_item_id: string;
  correct_index?: number;
  explanation?: string;
}

export interface CompareResult {
  item_a_id: string;
  item_b_id: string;
  similarities: string[];
  differences: string[];
  relationship: string;
  relation_type: RelationType | null;
}

export interface ChainStep {
  item_id: string;
  title: string;
  relation_from_prev: RelationType | null;
  position: number;
}

export interface ExperimentPayload {
  questions?: QuizQuestionPublic[];
  compare?: CompareResult;
  steps?: ChainStep[];
}

export interface ExperimentSession {
  id: string;
  kind: ExperimentKind;
  title: string;
  space_id: string | null;
  item_ids: string[];
  payload: ExperimentPayload;
  status: ExperimentStatus;
  created_at: string;
  updated_at: string;
}

export interface ExperimentCreateInput {
  kind: ExperimentKind;
  item_ids: string[];
  space_id?: string | null;
  count?: number;
  seed_id?: string | null;
}

export interface AnswerFeedback {
  correct: boolean;
  correct_value: number;
  explanation: string;
}

export interface ExperimentAnswerInput {
  index: number;
  value: number;
}

export interface ExperimentAttempt {
  id: string;
  session_id: string;
  answers: { index: number; value: number; correct?: boolean }[];
  correct_count: number;
  total: number;
  score: number;
  created_at: string;
}

export interface ExperimentCompleteResult {
  session: ExperimentSession;
  attempt: ExperimentAttempt;
}

export interface ExperimentListOptions {
  kind?: ExperimentKind;
  spaceId?: string | null;
}

/** 以下与后端 V2 附件 / 双链 / Markdown 导入导出 DTO 对应。 */

export interface AttachmentItem {
  id: string;
  item_id: string;
  filename: string;
  mime: string;
  size: number;
  storage_key: string;
  content_hash: string;
  created_at: string;
}

export interface AttachmentUploadInput {
  filename: string;
  mime: string;
  content_base64: string;
}

export interface LinkItem {
  id: string;
  source_id: string;
  target_id: string | null;
  target_title: string;
  alias: string | null;
  resolution: string;
  cross_space: boolean;
  created_at: string;
  updated_at: string;
}

export interface MarkdownImportInput {
  content?: string | null;
  filename?: string | null;
  target_item_id?: string | null;
  space_id?: string | null;
  archive_base64?: string | null;
}

export interface MarkdownImportReport {
  items: {
    status: string;
    item_id?: string | null;
    review_id?: string | null;
    warnings?: string[];
    errors?: string[];
  }[];
  index_sync?: string;
}