# M3 实施计划 · 跨会话混合检索（细化稿，待确认）

- 日期：2026-11-14
- 状态：**向量来源已确认 = A（配置 embed 供应商）**；整体待用户「确认 开始T1」。确认后按「计划确认 → 开发 → 实跑 → 验收报告 + MILESTONES + 提交」执行。
- 上游：M0 ✅、M1 ✅（`a2a8e01`）、M2 ✅（`4dcf61b`）。
- 定位：M3 = **检索层**。在 M2 治理之上，提供跨会话、跨知识空间的「全文 + 向量」混合检索 API 与前端检索入口。

## 0. 范围边界（做什么 / 不做什么）

做：SQLite FTS5 全文索引、向量存储与检索、混合融合排序、跨会话/跨空间检索 API、前端最小检索入口、索引随治理变更同步、PostgreSQL 阶段迁移方案（文档化，不实施）。

不做（严禁提前）：
- M4 知识地图（React Flow / ELK.js）、M5 交互实验。
- 不实际安装 PostgreSQL / pgvector；仅给出迁移方案与方言抽象，开发仍跑 SQLite。
- 不铺全量页面；前端只加一个「检索」页签。

## 1. 架构对齐

- 检索编排落在 **Knowledge Core**（`retrieval/` 实现 M0 的 `RetrievalService` 抽象），仅 Pydantic + 纯 Python，经端口依赖索引/向量存储，不依赖前端 / Web 框架（独立性闭包测试继续守护并扩展到 M3 模块）。
- 复用 M0 接口：`RetrievalService.search(query, space_id, limit) -> list[SearchResult]`，**不改签名**。
- 新增端口（Core `ports.py`，Protocol）：
  - `FullTextIndex`：`upsert(item_id, title, content)` / `remove(item_id)` / `search(query, limit) -> list[(item_id, rank)]`。
  - `VectorStore`：`upsert(item_id, vector)` / `remove(item_id)` / `query(vector, limit) -> list[(item_id, cosine)]` / `rebuild(...)`。
  - `Embedder`：`embed(texts) -> list[list[float]]`（与 ModelAdapter.embed 同形；后端注入适配器或本地实现）。
- Backend 提供 SQLite 实现（FTS5 虚表 + 向量表），与 M1/M2 仓库同风格；PostgreSQL 实现留接口不实施。

## 2. 全文检索（SQLite FTS5）

- 迁移 `0004_m3_retrieval`：虚表 `knowledge_fts(item_id UNINDEXED, title, content, tokenize='trigram')` + 向量表 `knowledge_vector(item_id PK, model, dim, vector JSON, updated_at)`。
- **中文分词决策**：M0 仅实测默认 tokenizer 的英文；默认 `unicode61` 对中文整段成词、召回差。实测（本计划前已只读验证）SQLite 3.45/3.40 的 **`trigram`** tokenizer 支持中文子串 MATCH（「知识图谱」「智能问答」均命中），无需新增分词依赖。故选 trigram。
- 短查询（<3 字符）trigram 不命中 → 回退 `LIKE '%q%'`（真实、不造假），并在结果中标注 channel=fts_like。
- 索引同步：FTS 用 SQLite 触发器（AFTER INSERT/UPDATE/DELETE on knowledge_item）保持与条目一致；删除/合并归档同步移除或保留（archived 条目默认不参与检索，可配置）。
- 排序：FTS5 `bm25()` 归一化为 rank；snippet 用 `snippet()` 或 Python 截取命中上下文。

## 3. 向量检索（已确认：A 配置 embed 供应商）

**供应商约束**：当前聊天供应商 DeepSeek 的 OpenAI 兼容端点**无 `/embeddings`**（M1/M2 已确认）。`ModelAdapter.embed` 已实现并就绪，但需要一个真正支持 embed 的来源。开发前先以只读方式探测所配置 embed 端点能力，不臆断。

**确认方案 A**：新增 `EMBED_BASE_URL / EMBED_API_KEY / EMBED_MODEL`（独立于聊天配置，密钥仅 backend/.env）。复用 `OpenAICompatibleAdapter`（embed_model 注入），真实语义向量。可选 SiliconFlow / 智谱 / OpenAI / 通义等。**用户需在 T4 前提供一个 embed 密钥**（或确认沿用某个已有密钥）。符合「供应商只经 Model Adapter、可替换」。

已否决 / 备选（仅记录，不采用）：
- **B. 本地语义模型（sentence-transformers / ONNX）**：引入重依赖 + 模型下载，改变技术栈；V1 不采用。
- **C. 本地词面向量降级（TF-IDF / hashing）**：仅作为「embed 端点临时不可用」时的明确标注应急降级，不作为默认通道；不造假、不冒充语义。

融合与存储（A/C 通用）：
- 向量存 `knowledge_vector`（JSON），开发期余弦在 Python 内对候选集计算（本地规模足够）；PostgreSQL 阶段换 pgvector（§6）。
- 索引同步：条目 create/update/restore/merge 后由服务钩子重算向量（A 调 embed，C 本地计算）；提供 backfill 命令为存量条目建索引。
- 模型/维度变更时重建向量（记录 model+dim，不一致则 rebuild）。

## 4. 混合融合排序

- `HybridRetrievalService(RetrievalService)`：并行取 FTS top-K 与向量 top-K → **RRF（Reciprocal Rank Fusion）** 融合：`score = Σ_channel 1/(k+rank)`（k=60），去重按 item_id，返回 top-limit。
- 结果 `SearchResult` 扩展（向后兼容）：保留 item_id/score/snippet，另附 `channels`（fts/vector 各自 rank/score）与 title/space_id/status 便于前端展示；不破坏 M0 签名（新增字段可选）。
- `space_id=None` 跨全部空间（含个人总知识库，聚合 space_id=None 条目，沿用 M1 语义）；限定 space_id 时过滤。
- 仅检索 `status != archived`（默认），draft/active 均可检索。

## 5. Backend API 与 Frontend

新增：
- `POST /api/search`（或 GET，query/space_id/limit/mode）：mode=hybrid|fts|vector；模型/embed 未配置时 vector 通道如实降级或 503（A 未配置→按 C 或仅 fts，明确上报）。
- `POST /api/search/reindex`：backfill/重建索引（管理入口）。
- 健康检查上报 embed 能力（configured/not_configured/unsupported）。

Frontend：新增「检索」页签——查询框 + 空间筛选 + 模式选择；结果列表（标题/snippet/分数/通道/来源链接），点击跳转知识详情。不新增 M4+ 页面。

## 6. PostgreSQL 阶段迁移方案（文档化，不实施）

- FTS5 → PG `tsvector`（中文需 zhparser / pg_jieba）或 `pg_trgm`（与 trigram 对齐，免分词依赖，推荐 pg_trgm）。
- 向量表 → `pgvector`（`vector(dim)` + HNSW 索引），余弦下推到 SQL。
- 端口不变，仅换 Backend 实现；迁移脚本与方言开关随部署阶段提供。

## 7. 测试与验证

- Core：RRF 融合单测；HybridRetrievalService（InMemory FTS/Vector/Embedder 双件）；space 过滤与 archived 排除；Embedder 协议契约；独立性闭包扩展到 M3。
- Backend：迁移 0004 表/虚表存在；trigram 中文 MATCH 与短查询 LIKE 回退；触发器同步（增改删）；向量 upsert/query/rebuild；search API 三模式；embed 未配置降级如实；reindex backfill。
- Frontend：检索页签渲染、结果展示、模式切换。
- 全量：pytest + ruff + vitest + build + alembic 无漂移。

## 8. 真实模型联调

- A（已确认）：用真实 embed 端点对现有 3 条知识建向量，跑 hybrid 检索（中文查询「知识图谱 用途」等），确认 FTS+向量双通道命中与融合排序；留存干净 UTF-8 证据。
- 应急降级 C 仅在 embed 端点临时不可用时启用并明确标注，不作为验收默认路径。
- 不调用聊天 embed 以外的无关能力；URL 只用真实 base_url，trust_env=False。

## 9. 任务拆分与依赖

| # | 任务 | 依赖 |
|---|---|---|
| T1 | 端口 + 迁移 0004（FTS 虚表/触发器 + 向量表） | — |
| T2 | Core HybridRetrievalService + RRF + Embedder 协议 | T1 |
| T3 | Backend SQLite FTS/Vector 实现 + 索引同步钩子 + backfill | T1,T2 |
| T4 | Embed 来源装配（A 适配器 / C 本地）+ 能力探测 + 配置 | T3 |
| T5 | search/reindex API + 健康上报 | T3,T4 |
| T6 | Frontend 检索页签 | T5 |
| T7 | 全量测试 + lint + 构建 + 无漂移 | T6 |
| T8 | 真实联调 + 验收报告 + MILESTONES + 提交 | T7 |

## 10. 风险与决策

1. DeepSeek 无 embed → 已确认 A：用户需在 T4 前提供 EMBED_BASE_URL/EMBED_API_KEY/EMBED_MODEL；开发前只读探测 embed 能力，未配置/不支持时如实上报，不造假。
2. 中文分词 → trigram（已实测），短查询 LIKE 回退；不引入 jieba 等新依赖。
3. 向量规模 → 开发期 Python 余弦足够；PG 阶段 pgvector 下推。
4. 索引一致性 → FTS 触发器 + 向量服务钩子 + backfill；archived 默认不检索。
5. 不提前做 M4/M5；不实际装 PG/pgvector。

## 11. 验收标准（M3 完成定义）

- [ ] 迁移 0004 实跑、无漂移；FTS 虚表 + 向量表就绪，触发器同步生效。
- [ ] 中文全文检索（trigram + 短查询回退）与向量检索可用，混合 RRF 排序正确。
- [ ] 跨会话/跨空间检索 API 与前端检索入口真实可用；space 过滤与 archived 排除正确。
- [ ] 索引随治理变更同步；backfill 可用；embed 能力如实上报/降级。
- [ ] 全量测试 + ruff + 构建 + 无漂移通过；Core 独立性守护通过。
- [ ] 真实联调证据；验收报告 + 截图；MILESTONES M3 ✅；Git 提交。

---

向量来源已确认 A。回复「确认计划 开始T1」后，我按 T1→T8 开始开发（T4 前会引导你填写 embed 密钥）。