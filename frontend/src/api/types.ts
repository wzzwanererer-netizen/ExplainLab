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