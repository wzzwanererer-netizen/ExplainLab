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