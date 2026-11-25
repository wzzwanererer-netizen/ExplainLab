# ExplainLab V2 · Backend API Mapping

**状态**：`RECONNAISSANCE COMPLETED / WAITING FOR DESIGN FREEZE`  
**数据来源**：逐行核对 `backend/app/api/routes/*.py`、`backend/app/api/schemas.py`、`frontend/src/api/client.ts` 与全部前端组件。后端共注册 **42 个 HTTP 端点**（全部挂载于 `/api` 前缀）。

## 完整映射表（Frontend Page → API Client → Backend Endpoint → Schema）

| 域 | Backend Endpoint | Request / Query Schema | Response Schema (Status) | Frontend Client (`client.ts`) | 使用页面 | 接通状态 |
| --- | --- | --- | --- | --- | --- | --- |
| **系统健康** | `GET /api/health` | — | `HealthResponse` (200) | `api.getHealth()` | `HealthPanel` | **已接通** |
| **知识空间** | `GET /api/spaces` | — | `list[SpaceOut]` (200) | `api.listSpaces()` | Chat / Knowledge / Search / Map / Experiments | **已接通** |
| **知识空间** | `POST /api/spaces` | `SpaceCreate` | `SpaceOut` (201) | `api.createSpace()` | `KnowledgeView` | **部分接通**（UI 未暴露 `description`） |
| **知识空间** | `GET /api/spaces/{space_id}` | path `space_id` | `SpaceOut` (200) | — | — | **未接通** |
| **对话** | `GET /api/conversations` | query `space_id?` | `list[ConversationOut]` (200) | `api.listConversations(spaceId?)` | `ChatView` | **部分接通**（UI 未传 `spaceId` 筛选） |
| **对话** | `POST /api/conversations` | `ConversationCreate` | `ConversationDetail` (201) | `api.createConversation()` | `ChatView` | **已接通** |
| **对话** | `GET /api/conversations/{id}` | path `conversation_id` | `ConversationDetail` (200) | `api.getConversation()` | `ChatView` | **已接通** |
| **对话** | `DELETE /api/conversations/{id}` | path `conversation_id` | `204 No Content` | `api.deleteConversation()` | `ChatView` | **已接通** |
| **对话** | `POST /api/conversations/{id}/chat` | `ChatRequest` | `MessageOut` (200) | `api.chat()` | `ChatView` | **已接通** |
| **对话/提取** | `POST /api/conversations/{id}/extract` | `ExtractRequest` | `ExtractResponse` (200) | `api.extractKnowledge()` | `ChatView` | **部分接通**（UI 未允许指定目标 `space_id`） |
| **知识管理** | `GET /api/knowledge` | query `space_id?` | `list[KnowledgeOut]` (200) | `api.listKnowledge()` | Knowledge / Experiments | **已接通** |
| **知识管理** | `POST /api/knowledge` | `KnowledgeCreate` | `KnowledgeOut` (201) | `api.createKnowledge()` | `KnowledgeView` | **已接通** |
| **知识管理** | `GET /api/knowledge/{item_id}` | path `item_id` | `KnowledgeOut` (200) | `api.getKnowledge()` | Search / Map / Experiments / Compare | **已接通** |
| **知识管理** | `PATCH /api/knowledge/{item_id}` | `KnowledgeUpdate` | `KnowledgeOut` (200) \| `ReviewOut` (202) | `api.updateKnowledge()` | `KnowledgeView` | **部分接通**（UI 未暴露修改 `space_id`） |
| **知识管理** | `DELETE /api/knowledge/{item_id}` | path `item_id` | `204` \| `ReviewOut` (202) | `api.deleteKnowledge()` | `KnowledgeView` | **已接通** |
| **治理** | `GET /api/knowledge/{id}/duplicates` | path `item_id` | `list[DuplicateOut]` (200) | `api.findDuplicates()` | — | **缺少前端交互**（Client 已封装但无页面调用） |
| **治理** | `POST /api/knowledge/{id}/analyze` | path `item_id` | `AnalyzeResponse` (200) | `api.analyzeKnowledge()` | `KnowledgeDetail` | **已接通** |
| **治理** | `GET /api/knowledge/{id}/relations` | path `item_id` | `list[RelationOut]` (200) | `api.listRelations()` | `KnowledgeDetail` | **已接通** |
| **治理** | `POST /api/knowledge/{id}/relations` | `RelationCreate` | `RelationOut` (201) | `api.createRelation()` | — | **缺少前端交互**（Client 已封装但无页面调用） |
| **治理** | `DELETE /api/relations/{relation_id}` | path `relation_id` | `204 No Content` | `api.deleteRelation()` | `KnowledgeDetail` | **已接通** |
| **治理** | `GET /api/knowledge/{id}/versions` | path `item_id` | `list[VersionOut]` (200) | `api.listVersions()` | `KnowledgeDetail` | **已接通** |
| **治理** | `POST /api/knowledge/{id}/versions/{v}/restore` | path `item_id`, `version` | `KnowledgeOut` (200) \| `ReviewOut` (202) | `api.restoreVersion()` | `KnowledgeDetail` | **已接通** |
| **治理** | `POST /api/knowledge/{id}/sources` | `SourceAttach` | `SourceRefOut` (201) | `api.attachSource()` | — | **缺少前端交互**（Client 已封装但无页面调用） |
| **审核队列** | `GET /api/reviews` | query `status?` | `list[ReviewOut]` (200) | `api.listReviews()` | `ReviewQueue` | **已接通** |
| **审核队列** | `POST /api/reviews` | `ReviewSubmit` | `ReviewSubmitResult` (200/201) | `api.submitReview()` | `KnowledgeDetail`（仅 merge） | **已接通** |
| **审核队列** | `POST /api/reviews/{id}/approve` | `ReviewResolve?` | `ReviewOut` (200) | `api.approveReview()` | `ReviewQueue` | **部分接通**（未展示导入附件/envelope；未传 `note`） |
| **审核队列** | `POST /api/reviews/{id}/reject` | `ReviewResolve?` | `ReviewOut` (200) | `api.rejectReview()` | `ReviewQueue` | **部分接通**（未传 `note`） |
| **检索** | `GET /api/search` | query `query`, `space_id?`, `limit?`, `mode?` | `SearchResponse` (200) | `api.search()` | `SearchView` | **已接通** |
| **检索** | `POST /api/search/reindex` | — | `ReindexResponse` (200) | `api.reindex()` | `SearchView` | **已接通** |
| **知识地图** | `GET /api/graph` | query `space_id?`, `include_archived?` | `GraphOut` (200) | `api.getGraph()` | `KnowledgeMap` | **已接通** |
| **实验** | `POST /api/experiments/sessions` | `ExperimentCreate` | `ExperimentOut` (201) | `api.createExperiment()` | `ExperimentsView` | **已接通** |
| **实验** | `GET /api/experiments/sessions` | query `kind?`, `space_id?` | `list[ExperimentOut]` (200) | `api.listExperiments()` | `ExperimentsView` | **部分接通**（UI 未传筛选参数） |
| **实验** | `GET /api/experiments/sessions/{id}` | path `session_id` | `ExperimentOut` (200) | `api.getExperiment()` | — | **缺少前端交互**（Client 已封装但无页面调用） |
| **实验** | `POST /api/experiments/sessions/{id}/answer` | `ExperimentAnswer` | `AnswerFeedbackOut` (200) | `api.answerExperiment()` | `QuizRunner` | **已接通** |
| **实验** | `POST /api/experiments/sessions/{id}/complete` | `ExperimentComplete` | `ExperimentCompleteResult` (200) | `api.completeExperiment()` | `QuizRunner` | **已接通** |
| **实验** | `DELETE /api/experiments/sessions/{id}` | path `session_id` | `204 No Content` | `api.deleteExperiment()` | `ExperimentsView` | **已接通** |
| **V2 附件** | `POST /api/knowledge/{item_id}/attachments` | `AttachmentUploadIn`（JSON Base64，禁止 multipart） | `AttachmentOut` (201/200 + `Location`) | — | — | **未接通** |
| **V2 附件** | `GET /api/knowledge/{item_id}/attachments` | path `item_id` | `list[AttachmentOut]` (200) | — | — | **未接通** |
| **V2 附件** | `GET /api/knowledge/{item_id}/attachments/{att_id}` | path `item_id`, `attachment_id` | `StreamingResponse` (200, `nosniff`, `ETag`, `Content-Disposition`) | — | — | **未接通** |
| **V2 附件** | `DELETE /api/knowledge/{item_id}/attachments/{att_id}` | path `item_id`, `attachment_id` | `204 No Content` | — | — | **未接通** |
| **V2 导入导出** | `POST /api/knowledge/import` | `MarkdownImportIn`（单篇 MD 或单文档含附件 ZIP `archive_base64`） | `ImportReport` dict + `index_sync` (200/201/202) | — | — | **未接通** |
| **V2 导入导出** | `POST /api/knowledge/import/batch` | `MarkdownImportIn`（`documents` 或多文档 ZIP） | `ImportReport` dict + `index_sync` (200) | — | — | **未接通** |
| **V2 导入导出** | `POST /api/knowledge/export` | `MarkdownExportIn`（`include_attachments=false`） | `application/zip` 二进制流 (200) | — | — | **未接通** |
| **V2 导入导出** | `GET /api/knowledge/{item_id}/markdown` | path `item_id` | `text/markdown; charset=utf-8` + `X-ExplainLab-*` 头 (200) | — | — | **未接通** |
| **V2 双链** | `GET /api/knowledge/links/resolve-candidates` | query `title`, `space_id?` | `list[ResolveCandidateOut]` (200) | — | — | **未接通** |
| **V2 双链** | `GET /api/knowledge/{item_id}/links` | path `item_id` | `list[LinkOut]` (200) | — | — | **未接通** |
| **V2 双链** | `GET /api/knowledge/{item_id}/backlinks` | path `item_id` | `list[BacklinkOut]` (200) | — | — | **未接通** |

> 统计：总计 47 条路由条目（注：`extract` 挂在 `knowledge.py`），其中 **已接通 25**、**部分接通 6**、**缺少前端交互（Client 有封装）4**、**完全未接通（V2 全量新能力 + `get_space`）12**。
