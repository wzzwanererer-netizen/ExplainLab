# ExplainLab V2 · Frontend-Backend Gaps

**状态**：`RECONNAISSANCE COMPLETED / WAITING FOR DESIGN FREEZE`

## 1. 高优先级功能缺口（V2 已完成后端验收，前端完全未接通）

1. **附件全生命周期（B2，4 个端点）**：
   - 前端缺少 `AttachmentOut` / `AttachmentUploadIn` 类型与 Client 封装。
   - **关键契约注意点**：后端上传接口 `POST /api/knowledge/{item_id}/attachments` 采用 **JSON Base64**（`AttachmentUploadIn` 设 `extra="forbid"`，严禁 `multipart/form-data`），单文件上限 `10 MiB`，白名单仅 8 种 MIME（严禁 SVG），同条目重复内容可能返回 `200` 而非 `201`，归档条目上传返回 `409 ATTACHMENT_ITEM_ARCHIVED`。
   - 下载接口返回二进制流与 `Content-Disposition` / `X-Content-Type-Options: nosniff`，现有 `client.ts` 仅解析 JSON，需补充 Blob 下载通道。
2. **Markdown 与含附件 ZIP 导入 / 导出（A1-04 & B3，4 个端点）**：
   - 前端无导入弹窗/面板（单篇 `.md`、批量 `.md`、含附件 `.zip` 经 Base64 上传），亦无导入结果报告（`ImportReport` 的 `created/updated/skipped/pending_review/error/warnings`）展示。
   - 前端无导出按钮（单篇 `.md` 下载与勾选/按空间导出 `.zip`；需注意后端明确禁止 `include_attachments=true` 并返回 `400 ATTACHMENT_EXPORT_UNSUPPORTED`）。
3. **Active 导入审核单展示（B4）**：
   - 当 Active 条目通过含附件 ZIP 导入生成 `pending` 审核单时，`ReviewRequest.payload` 包含 `__a1_import` envelope 与附件 manifest。
   - 现有 `ReviewQueue.tsx` 仅展示 `title/content/status` 摘要，未解析导入上下文、待发布附件清单、标签变更与 `resolution_note` 输入；需在前端新设计中补齐。
4. **双链（Wikilinks）只读视图（A1-03，3 个端点）**：
   - 后端已提供出链（`/links`）、反链（`/backlinks`）与候选解析（`/links/resolve-candidates`），前端 `KnowledgeDetail` 尚未展示出链/反链面板，编辑器也未接入 `[[` 候选补全提示。

## 2. 现有已封装但缺 UI 交互的能力（M1–M5）

- `api.createRelation()` / `api.attachSource()` / `api.findDuplicates()` / `api.getExperiment()` 已在 `client.ts` 实现并通过单测，但无页面 UI 入口。
- `ReviewQueue` 批准/驳回未提供 `note` 输入框；`ChatView` 未支持按空间过滤会话；`ExperimentsView` 历史列表未接入 `kind` / `space_id` 过滤。

## 3. 契约一致性与需后端确认事项

- **已接通端点契约一致**：核对 `types.ts` 与 `schemas.py` 的全部 M0–M5 DTO，字段名与类型完全匹配，无字段漂移。
- **需后端确认（供下阶段设计决策）**：
  1. **标签（Tags）独立 HTTP 查询/编辑**：后端 `tag` / `item_tag` 表与 `SQLAlchemyTagRepository` 已存在并用于 Markdown 导入，但 `KnowledgeOut` 当前未包含 `tags` 字段，也无独立 `/api/tags` 路由——如需在知识卡片/编辑页直接展示和编辑标签，需确认是否扩展 `KnowledgeOut` 或新增只读/写接口。
  2. **知识地图是否叠加双链（`knowledge_link`）**：当前 `GET /api/graph` 仅返回 M2 `knowledge_relation` 边，未包含 V2 `[[wikilink]]` 边；需确认前端地图是否保持仅关系边或提供图层切换。
  3. **健康检查与运维信息**：`/api/health` 当前未返回附件存储根可用性或待处理审核数量，若新桌面外壳顶部需要「待审核角标」，可直接用 `GET /api/reviews?status=pending` 计数，无需改后端。
  4. **错误码国际化映射**：V2 路由返回稳定英文错误码（如 `ATTACHMENT_TOO_LARGE`、`ATTACHMENT_ITEM_ARCHIVED`、`IMPORT_ENVELOPE_INVALID`、`link_version_mismatch`），前端需建立集中错误码 → 中文提示映射表，避免直接把原始英文码暴露给用户。
