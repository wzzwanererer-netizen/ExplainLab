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

export interface SandboxResponse {
  item_id: string;
  exists: boolean;
  html: string | null;
  updated_at: string | null;
}

export interface AgentStatus {
  id: string;
  name: string;
  description: string;
  space_name: string;
  space_id: string | null;
  installed: boolean;
  connected: boolean;
  item_count: number;
  session_dir: string | null;
  session_files_count: number;
  unprocessed_count: number;
  rule_installed: boolean;
  last_vacuum_at: string | null;
  is_custom: boolean;
}

export interface AgentAddInput {
  name: string;
  description?: string | null;
  session_dir?: string | null;
  write_rule?: boolean;
}

export interface SessionFilePreview {
  file_path: string;
  label: string;
  preview: string;
  updated_at: string;
  size_kb: number;
  processed: boolean;
  created_count: number;
}

export interface VacuumCreatedItem {
  id: string;
  agent_name: string;
  space_id: string;
  title: string;
  source_file: string;
}

export interface VacuumReport {
  scanned_sessions: number;
  skipped_sessions: number;
  created_items: VacuumCreatedItem[];
  errors: string[];
}

export interface MediaItem {
  id: string;
  item_id: string;
  filename: string;
  kind: "image" | "audio" | "video" | "pdf" | "word" | "excel" | "ppt" | "file" | string;
  mime: string;
  size_bytes: number;
  url: string;
  created_at: string;
}

export interface LibraryMediaItem extends MediaItem {
  item_title: string;
  space_id: string | null;
  space_name: string | null;
}

export interface DocPreviewWordBlock {
  type: "heading" | "paragraph" | "table" | "image";
  level?: number;
  text?: string;
  rows?: string[][];
  src?: string;
}

export interface DocPreviewExcelSheet {
  name: string;
  rows: string[][];
  total_rows: number;
  truncated: boolean;
}

export interface DocPreviewPptSlide {
  index: number;
  title: string;
  bullets: string[];
  tables: string[][][];
  images: string[];
  notes: string;
}

export interface DocPreviewZipEntry {
  name: string;
  size_bytes: number;
  compressed_bytes: number;
  is_dir: boolean;
}

export interface DocPreviewResponse {
  kind: string;
  stream_url?: string;
  warning?: string;
  blocks?: DocPreviewWordBlock[];
  sheets?: DocPreviewExcelSheet[];
  slides?: DocPreviewPptSlide[];
  entries?: DocPreviewZipEntry[];
  total_entries?: number;
  total_size_bytes?: number;
  truncated?: boolean;
  html?: string;
  language?: string;
  text?: string;
}

export interface FolderPreset {
  label: string;
  path: string;
}

export interface WatchedFolder {
  id: string;
  name: string;
  path: string;
  space_id: string;
  space_name: string;
  enabled: boolean;
  use_ai_summary: boolean;
  file_count: number;
  indexed_count: number;
  last_scan_at: string | null;
  created_at: string;
}

export interface FolderScanReport {
  folder_id: string;
  scanned_files: number;
  skipped_files: number;
  created_items: {
    id: string;
    title: string;
    file_path: string;
    kind: string;
  }[];
  errors: string[];
}

export interface ModelSettings {
  model_provider: string | null;
  model_base_url: string | null;
  model_name: string | null;
  model_api_key_set: boolean;
  model_api_key_masked: string | null;
  embed_base_url: string | null;
  embed_model: string | null;
  embed_api_key_set: boolean;
  embed_api_key_masked: string | null;
  env_file: string;
}

export interface ModelSettingsUpdateInput {
  model_base_url?: string | null;
  model_name?: string | null;
  model_api_key?: string | null;
  clear_model_api_key?: boolean;
  embed_base_url?: string | null;
  embed_model?: string | null;
  embed_api_key?: string | null;
  clear_embed_api_key?: boolean;
}

export interface ModelTestResult {
  ok: boolean;
  latency_ms: number;
  error_code?: string | null;
  message: string;
}

export interface CompletedTaskSuggestion {
  suggestion_id: string;
  agent_id: string;
  agent_name: string;
  space_id: string | null;
  file_path: string;
  signature: string;
  label: string;
  preview: string;
  updated_at: string;
}
