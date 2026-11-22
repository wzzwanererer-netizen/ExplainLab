# ExplainLab V2 · A1-04 阶段级实施设计方案

> 状态：**R1.3 架构修订稿，非实现**（R1 / R1.1 / R1.2 历史保留）。本稿仅修订设计；未写业务代码、未新增迁移、未装依赖、未改测试、未提交。
> **R1 架构修订说明（2026-11-21）**：本文件已纳入 A1-04 第一轮独立技术核验后的架构裁决。本文原始章节中与文末「R1 权威修订」冲突的内容，以 R1 为准；R1 未覆盖的原设计继续有效。本文仍是**设计文件，不是实现或测试通过证明**。R1 修订未经用户阶段级批准前，不得据此启动业务代码开发。
> **R1.1 架构修订说明（2026-11-21）**：本文件已在 R1 基线上合并 R1.1 增补（`docs/plans/A1-04/R1.1-amendment/`，SHA256SUMS 已核验）。本文原始章节与 R1 章节中与文末「§20 R1.1 权威修订」冲突的内容，以 **R1.1（§20）** 为准；未冲突的设计、编号与历史审计记录全部保留。产品约束：**Offline backup / Single deployment / Strict migration**。本文仍是**设计文件，非实现或测试通过证明**；所有 R1.1 新增验收均标【待验证】。R1.1 未经用户阶段级批准与 ChatGPT 阶段级独立审计前，不得据此启动业务代码开发。
> **R1.2 架构修订说明（2026-11-21）**：本文件已合并 ChatGPT **R1.2** 架构决策 D18–D21（文档身份模型、批次依赖、同步事务执行模型、HTTP 网络边界）。本文与 §20 中与文末「§21 R1.2 权威修订」冲突的内容，以 **§21** 为准；§19.9 批次划分、§19.10 异步/线程边界、§20.2 实例身份语义已就地加注指向 §21。原 R1/R1.1 编号、历史审计记录与未冲突设计全部保留，不重编号、不删减。所有 R1.2 新增验收均标【待验证】。**本轮仅文档维护，未写业务代码、未新增迁移/表/列/索引、未加依赖、未改 Core/A1-02/A1-03/V1 API/MILESTONES，未提交/推送。** R1.2 未经用户阶段级批准与 ChatGPT 独立审计前，不得据此启动 Batch A。
> **R1.3 架构修订说明（2026-11-21）**：本文件已合并 ChatGPT **R1.3** 裁决 D22（exporter 与 Hash 解耦）、D23（本地文档身份初始化）、D24（HTTP 本机安全边界）。与 §21 冲突处以文末「**§22 R1.3 权威修订**」为准；§21.1、§21.4、§21.5 已就地修正并指向 §22。R1/R1.1/R1.2 编号、历史裁决与审计记录全部保留，不重编号、不删改。D22–D24 **不改变 A1-02 Core Hash / canonicalization v1、A1-03 链接规则、Core ReviewService、V1 API 的冻结契约**。所有 R1.3 新增验收均标【待验证】。**本轮仅文档维护，未写业务代码/测试、未新增迁移/表/列/索引、未加依赖、未改 A1-01/A1-02/A1-03、未提交/推送。** 已按 ChatGPT 最终独立审计完成有限修正（重复保留键先于 YAML 折叠检测、身份状态 2a/2b/3/4、rotate write-ahead Journal、固定附件码/锁超时）；**第二轮有限修正**明确记录：仅凭既有 DB 字段与 `extra_metadata` **信息不足**，不得推断“已合法物化”；合法物化改由 **COMMITTED MATERIALIZE Journal** 显式证明，缺失即 fail-closed，未新增 DB schema；**第三轮定点修正**补齐 MATERIALIZE 恢复优先级、Journal 归档状态转换与 Journal 数据契约 v1（`materialization_items` 结构、三个摘要的排序/编码/空值/版本兼容规则）；**第四轮最终审计修正**明确 `identity_audit_digest` 覆盖全部知识文档的来源身份投影（非仅 `materialization_items`）、恢复必须重读 DB 验证，并补齐 Canonical JSON v1 的 UTF-8/非 ASCII/转义/代理项/重复键/数字规则及 8 组固定测试向量；**第五轮最终定点修正**补齐每项 **全部 `ImportOrigin` 原始身份记录的逐条审计**（含残缺、重复、字段非法记录），保留稳定记录 ID 与原始字段、记录数量/状态，明确读取顺序无关、原始字段不归一化、孤儿记录 fail-closed；**第六轮最终冻结前定点修正**补齐 **多记录状态判定表与互斥/组合优先级**：`conflict` > `invalid` > `incomplete` > `duplicate` > `complete` > `none`；同一 item 存在多个不同合法身份对、或唯一合法身份与 `knowledge_item.source_instance_id` 不一致时必须 `conflict`，完整+残缺混合不得提升、重复+不同身份必须冲突，冲突 fail-closed、禁止认领/覆盖/合并/猜测；同一身份的不同 `source_payload_hash` 版本不算冲突。仍无 schema/代码/验收编号/风险编号变更，不新增阶段修订编号；仅扩展 `R1.3-ID-02/03/05` 验收内容。**待用户阶段级批准后方可启动 Batch A**。

> 标注约定沿用 `V2-batch-A-design.md`：【事实】= 已读真实代码核实；【提议】= 本方案建议，待审批；【待审批】= 须 ChatGPT + 用户拍板；【待验证】= 进入开发后须真实 SQLite/PG/Windows 测试，当前不得宣称已通过。
> 权威设计依据：`docs/plans/V2-batch-A-design.md`（第五轮冻结，876 行）、`docs/plans/V2-dependency-selection.md`、`docs/plans/V2-plan.md`。
> 基线：Git HEAD `784b124`，分支 `fix/m0-admission-and-m5-regressions`，工作树干净（仅未跟踪 `docs/audit/V2-A1-03-final-stage-audit/`）。A1-03 阶段级审计结论 **CONDITIONAL PASS**（D 类阻塞 0，无数据丢失路径）。
> 历史验收基线（SQLite 930/178skip、PG16.8 1108/0skip、Core 守护 14、A1-02 冻结 291、前端 72、ruff/typecheck/build 通过）为**历史记录**，本轮未重跑，不作为本轮证据。

---

## 0. 阅读指引与四份材料关系

| 文件 | 用途 |
|---|---|
| `V2-A1-04-implementation-plan.md`（本文件） | 现状核实 + 模块/数据流/事务/状态机/API/方言/安全/迁移/测试/验收 + 任务依赖与实施顺序 + 文件范围 |
| `V2-A1-04-acceptance-matrix.md` | 每项功能拆成可执行验收项（编号/输入/预期/SQLite 法/PG 法/失败条件/并发/真实文件系统/故障注入） |
| `V2-A1-04-risk-register.md` | 风险登记（严重程度/发生条件/影响/防护） |
| `V2-A1-04-open-decisions.md` | 须确认的架构决策 + 设计与真实代码冲突清单（含文件/位置/影响/建议） |

**红线遵守自检**：本文件所有「新增模块」「数据流」「状态机」均为【提议】设计，**不是已实现事实**。凡引用现有代码均标【事实】并给出文件路径。发现的原设计与真实代码冲突集中在 open-decisions §C，**未改任何代码迎合设计**。

---

## 1. 阶段目标与边界

### 1.1 A1-04 目标（对齐 A1-02 验收报告 §7 明文边界）

【事实】`docs/acceptance/V2-A1-02-markdown-codec-and-frontmatter.md:182` 明确 A1-04 范围：

> 导入导出服务、持久化源 hash 幂等、ImportOrigin、跨实例 Draft、每文档事务/部分失败、ImportReport、附件生命周期 + StorageKeyLock 方言实现 + GC 租约/隔离/孤儿扫描、Manifest。

据此 A1-04 交付四个方向（对应用户任务 A/B/C/D）：

- **A. Markdown 导入导出系统**：单/批量导入、单/批量导出、Frontmatter 保真、extra_metadata 未知字段保留、稳定 ID 恢复、导入 target_id 优先绑定恢复、ImportReport、ImportOrigin 源 hash 幂等、跨实例默认 Draft、active 内容变更经审核、每文档独立事务、批量部分失败继续。附件清单的**完整导入/导出**按 R1.2 D19 归 Batch B（§21.2）；Batch A 遇含附件请求必须显式拒绝/标记 unsupported，不得静默丢弃。
- **B. 附件生命周期与存储系统**：SHA-256 内容寻址、storage_key=内容 hash、物理共享、引用数 DB 派生（无计数器）、上传校验/文件名清洗/MIME/大小限制/路径穿越防护/内容完整性、StorageKeyLock 双方言、GC 租约认领 + 持锁 quarantine + 退避重试、独立孤儿扫描、DB↔物理一致性检查。
- **C. 链接用户操作与运维 API**：人工显式绑定写入口、候选查询（已有）、重解析、链接键重建 HTTP/CLI、碰撞报告、重建结果查看、archived/跨空间绑定确认、运维 CLI（键重建 + 迁移降级包装器）。
- **D. SQLite 并发与现有风险**：读阶段窗口②/SQLITE_BUSY 活性/busy_timeout/BEGIN IMMEDIATE 必要性/WAL 适配性/K1 选项 B 非 HTTP 绕过，给出正确性/互斥性/活性三维判断与**最小改动**建议（不擅改全局事务管线）。

### 1.2 明确不在 A1-04（边界，防止范围蔓延）

【事实】依据 A1-02 报告 §7 与 A1-03 报告 §6：

| 项 | 归属 | 依据 |
|---|---|---|
| 审核提案防覆盖（`_review_payload_hash` + `_proposal_version` + 异 payload 409 + 撤回 WITHDRAWN + 批准==应用 hash 校验） | **A1-05** | A1-02 报告:183；`markdown/__init__.py:392` review_payload_hash docstring「A1-05 集成」；`review/__init__.py` 无 withdraw/WITHDRAWN |
| 前端编辑器（CodeMirror 6 / react-markdown）、链接绑定 UI、frontmatter 冲突 UI、附件 UI | **A2** | V2-plan §1.5；dependency-selection A-1/A-2 待审批 |
| 全量回归 + 验收报告 + MILESTONES 更新 | **A1-06** | A1-02 报告:184；A1-03 报告:254「MILESTONES 留到 A1-06」 |
| 认证/真实 actor 身份 | **auth 批次** | design §9.10；V1 无认证 |
| 非 loopback 监听 / 公网暴露能力 | **A1-04 不提供**：默认且**仅允许精确 IP** `127.0.0.1`/`::1`（`localhost` 不得作为绑定配置）；无认证时拒绝非 loopback 配置并 fail-closed；代理/隧道/端口转发远程访问不支持（R1.2 D21、R1.3 D24，§21.4/§22.3）；认证与受控远程访问属 auth/部署批次 | V1 无认证；R1.2 D21；R1.3 D24 |
| 备份恢复的**多实例编排器**生产实现 | 依赖部署形态，A1-04 只交付单实例协议 + 框架，多实例编排【待审批】延后 | design §6.5/§9.7 |

> **关键边界（R1）**：A1-04 active 内容变更仍复用 `ReviewService.submit(UPDATE_ITEM)`，但新增 backend `__a1_import` envelope 与 approve/reject hook；同来源同 hash pending 复用，不同 hash 且旧 pending 未解决时拒绝新导入。proposal 防覆盖、withdraw、WITHDRAWN 仍归 A1-05。

### 1.3 工程红线（本轮强制，逐条遵守）

1. 本轮只调查和设计，不写业务代码。2. 不新增数据库迁移。3. 不安装/升级依赖。4. 不修改现有测试。5. 不修改 A1-01/A1-02/A1-03 业务代码。6. 不修改 M0 初始提交（`2d2b634`）。7. 不修改 Git 历史。8. 不 commit/不 push。9. 不自动进入 A1-05/A2。10. 不修改 MILESTONES.md。11. 不把设计描述成已实现。12. 不为完成文档编造测试结果。

---

## 2. 当前架构现状（真实代码核实，非历史文档推测）

### 2.1 已存在（A1-01/02/03 已交付，A1-04 直接复用，**不得重写**）

#### 2.1.1 数据层 —— 全部 A1 表与列已就绪【事实】

- **迁移 `0006_v2_markdown_kb`**（`backend/alembic/versions/0006_v2_markdown_kb.py`，233 行）：`down_revision=0005_m5_experiments`，单 head。upgrade 建 8 张新表 + knowledge_item 4 新列，**全部 additive**；downgrade 删表 + 删列（SQLite 原生 `ALTER TABLE DROP COLUMN` 需 ≥3.35，**刻意不用 batch_alter_table** 以保 FTS5 触发器与 rowid 对齐；PG `op.drop_column`）。
- **ORM**（`backend/app/models.py`，451 行）：`TagORM`(274)、`ItemTagORM`(285)、`KnowledgeLinkORM`(299)、`AttachmentORM`(336)、`TagChangeLogORM`(354)、`GcTaskORM`(379)、`ImportOriginORM`(410)、`StorageLockORM`(438) 全部存在；`KnowledgeItemORM`(98) 含 `extra_metadata`(112, Text NOT NULL default/server_default `{}`)、`source_payload_hash/source_content_hash/source_instance_id`(114-116, String(64) nullable)。
  - `gc_task` 已含 `lease_owner/lease_expires_at/lease_token/attempts/next_retry_at/quarantine_path/quarantined_at`，status String(24)。
  - `storage_lock` 已含 `storage_key PK/owner/lease_token/lease_expires_at/locked_at`。
  - `import_origin` 已含 `source_payload_hash/source_content_hash/source_instance_id/source_document_id/source_canonicalization_version/imported_at/import_batch_id`。
  - `knowledge_link` UNIQUE(source_item_id, normalized_link_key)（`uq_link_source_key`），target FK SET NULL，source FK CASCADE。
  - models.py:268 注释：**刻意不在 KnowledgeItemORM 新增 relationship**，新表清理一律由 DB 外键 CASCADE/SET NULL 承担（SQLite 已开 PRAGMA foreign_keys=ON）。

> **结论（核心事实）**：A1-04 所需的 attachment/tag/item_tag/tag_change_log/gc_task/import_origin/storage_lock 表与 knowledge_item 新列**已全部由 0006 建好**。**A1-04 不需要为这些表新增任何迁移**（与红线 #2 一致）。唯一可能的 schema 新增是备份恢复 Manifest 持久化——见 §13 迁移策略（建议用文件/既有表，避免新迁移；若确需新表则触发红线 #2，须升级为独立审批项）。

#### 2.1.2 Core 实体与端口 —— 全部契约已就绪【事实】

- **实体**（`knowledge-core/src/knowledge_core/domain/entities.py`，301 行）：`KnowledgeItem`(76, 含 tags/extra_metadata)、`KnowledgeLink`(178, 含 `_resolution_matches_binding` 校验器)、`Attachment`(206)、`TagChangeRecord`(219)、`GcStatus`(238, 7 态含 cancelled)、`GcTask`(250)、`StorageLease`(271)、`ImportOrigin`(285)；常量 `CANONICALIZATION_VERSION=1`(26)、`LINK_NORMALization_VERSION=1`(27)。`ReviewStatus`(126) 仅 PENDING/APPROVED/REJECTED（**无 WITHDRAWN**）；`ReviewAction`(134) 四动作。
- **端口**（`knowledge-core/src/knowledge_core/ports.py`，464 行）：`LinkRepository`(216, 10 方法)、`AttachmentRepository`(269, 含 `count_references`/`list_storage_keys`)、`TagRepository`(305)、`TagChangeLogRepository`(336, append-only)、`GcTaskRepository`(356, 含 `claim`/`update_task(expected_lease_token)`)、`ImportOriginRepository`(403, 含 `find_by_source_payload_hash`/`find_by_source_document`)、`StorageKeyLock`(437, acquire/renew/verify/release)。**全部纯 Protocol，仅依赖 stdlib + domain.entities**。

#### 2.1.3 Core Markdown 编解码 + 三 Hash + 规范化原语（A1-02）【事实】

- `markdown/__init__.py`（669 行）：`MarkdownCodec` ABC(317)、`MarkdownDocument`(184, extra=forbid, present_exchange_fields/payload_fields/content_fields/governance_fields)、三 Hash 函数 `document_content_hash`(352)/`document_payload_hash`(371)/`review_payload_hash`(384)、`compute_document_hashes`(423)、`DocumentHashes`(405)、`resolve_frontmatter_conflict`(459)、`FrontmatterState` 三态(135)、`MarkdownWarningCode`(157)、6 个链接服务 ABC(565-669)。
- `markdown/codec.py`：`StdlibMarkdownCodec`（零新增依赖，5 不变量）。
- `markdown/canonical.py`（240 行）：**canonicalization v1 序列化规则已在代码冻结**——紧凑 separators `(",",":")`(40)、datetime UTC 固定微秒 6 位 Z(50)、Decimal `format(d,'f')` 去尾零不经 float(62)、裸 float 禁用(85)、null≠缺失(19)、语义序列表排序含次级键(175-240)、原始 Unicode 不做 NFKC(22)、版本包络 + `hashes_comparable`/`require_comparable_versions`(158-169)。
  > **重要**：design §7.19/§9.20 把序列化细则标【待审批】，但 **A1-02 已实现并冻结为 v1**（A1-02 报告:75 确认）。A1-04 **不得重开这些已冻结规则**，直接复用；open-decisions 据此区分「已冻结」与「真正未决」。

#### 2.1.4 Core 链接服务 + backend 链接仓库/重建执行（A1-03）【事实】

- `markdown/link_service.py`（~960 行）：`RepositoryLinkResolver`(485, 含 `bind_explicit`(541) 允许 archived/跨空间、返回未保存链接+告警)、`BindingFirstLinkSync`(570)、`LinkImportRestorer`(630, `restore(item, frontmatter_links, body)`(643) 已实现先聚合再判定+空间重算+正文权威 D4+绑定优先+孤儿/无效提示告警)、`BacklinkQuery`(835)、`LinkReresolve`(845)、`LinkKeyRebuild`(895, `plan(target_version)` 只算计划零写入)；纯函数 `check_global_version_homogeneity`(114)/`check_plan_freshness`(290)/`binding_semantics`(411)；报告模型 `LinkRebuildPlan`(191)/`LinkRebuildReport`(233)/`LinkSyncReport`(250)/`LinkRestoreReport`(272)。
- `backend/app/services/links.py`（541 行）：`SQLAlchemyLinkRepository`(104, 10 方法，全局版本同构守卫无缓存预检)、`apply_link_key_plan(plan, session)`(309, **重建唯一执行入口**，独占单事务十步，门禁 A/B/C + P2 六字段乐观前置 + 步 8/8c 写后复核)、`demote_backlinks_on_delete`(216)、`persist_rebuild_report`(519, backend IO 落 `backend/data/ops/`)、`build_link_sync`(530)、**`build_link_restorer`(537, 注释明言「A1-04 导入路径预留」)**。
- `backend/app/db/locking.py`（54 行）：`acquire_rebuild_write_lock`——PG `LOCK TABLE knowledge_link IN SHARE ROW EXCLUSIVE` + `FOR UPDATE`；SQLite no-op（诚实：读阶段不锁，窗口②由 P2 兜底，BEGIN IMMEDIATE 未启用）。
- `backend/app/api/routes/links.py`（95 行）：**仅 3 个只读 GET**（resolve-candidates/list_item_links/list_item_backlinks）+ `sync_links_or_conflict`(36, 409 稳定码 `link_version_mismatch`)。**无任何写端点（D8）**。

#### 2.1.5 治理/CRUD 调用链与 K1 链接挂接（M2 + A1-03 整改）【事实】

- `backend/app/services/knowledge.py`（159 行）：`SQLAlchemyKnowledgeRepository`(51)。**⚠ `_to_entity`(28)/`save`(57)/`update`(102) 只映射 id/title/content/status/space_id/source_refs/时间，不映射 tags/extra_metadata/source_* hash**（见 §2.2 冲突 C-01）。
- `backend/app/services/governance.py`（238 行）：Relation/Version/Review 三仓库 + `build_review_service`(218)/`build_version_service`(212)/`build_provenance_service`(227)/`build_analysis_service`(231)。
- `knowledge-core/src/knowledge_core/review/__init__.py`（168 行）：`ReviewPolicy.is_important`(37, active 改删回滚 + 任何合并)、`ReviewService.submit`(65)/`approve`(85)/`reject`(98)/`_apply_action`(115)。**Core ReviewService 无任何链接钩子**（链接维护在 backend 路由层）。
- `backend/app/api/routes/knowledge.py`（190 行）：create→save→`sync_links_or_conflict`→commit→sync_index；PATCH→`ReviewService.submit`（active=202 不同步，draft=应用+同步）；DELETE→非 active 先 `demote_backlinks_on_delete`→submit→commit→sync_index remove。
- `backend/app/api/routes/governance.py`（391 行）：**K1 三入口×四动作链接挂接已实现**——`restore_version`(183)/`submit_review`(245)/`approve_review`(352) 均经 `_demote_backlinks_before_delete`(324, DELETE 应用前降级) + `_sync_links_after_content_change`(337, UPDATE/RESTORE 应用后 commit 前同步) + `_sync_applied_action`(303, 索引)。409 整事务零写入。
  > **对 A1-04 导入的硬约束**：链接维护钩子在 **backend 路由层**而非 Core ReviewService。**R1.1 方案**：导入 Draft/Active approve 一律使用 `LinkImportRestorer`（见 §19.3 / §20.3），普通治理保持既有 K1，**导入分支不再执行第二次普通 sync**；版本异写 409 整事务零写入。见 §5 数据流与 risk-register R-GOV-02 / R1.1-R-K1-01。

#### 2.1.6 配置/会话/装配/测试基建【事实】

- `backend/app/core/config.py`（97 行）：`Settings`，BACKEND_DIR 锚定，DEFAULT_DATABASE_URL=SQLite，model_*/embed_*（SecretStr）。**无任何附件存储根/大小上限/MIME 白名单/租约参数/GC 阈值/备份位置配置**（A1-04 须新增，见 §12）。
- `backend/app/db/session.py`（102 行）：SQLite `PRAGMA foreign_keys=ON` + `busy_timeout=5000`，**无 WAL**，`check_same_thread=False`；PG `pool_pre_ping=True`；`session_scope`(88) 自动 commit/rollback；`get_session`(76) 每请求一会话，autoflush=False/expire_on_commit=False。
- `backend/app/dependencies.py`（46 行）：仅 `get_model_adapter`/`get_embedder`/`get_model_adapter_optional`。**无存储/附件依赖**。
- `backend/app/main.py`（74 行）：路由注册顺序 health→spaces→conversations→**links（先于 knowledge，R11 静态字面优先）**→knowledge→governance→search→graph→experiments。A1-04 新路由须遵守静态字面先于 `{item_id}` 动态段。
- `backend/app/api/schemas.py`（361 行）：KnowledgeOut/Create/Update **不含 tags/extra_metadata**；LinkOut/BacklinkOut/ResolveCandidateOut 已有；**无 Attachment/Tag/Import/Gc/Export DTO**。
- 测试基建：`backend/tests/conftest.py`（91 行）tmp_path SQLite + `Base.metadata.create_all`（不走 Alembic）+ StubAdapter；`knowledge-core/tests/helpers.py`（401 行）InMemory 仓库（含 `InMemoryLinkRepository`(303) 守卫语义对齐生产）+ FakeAdapter/FakeEmbedder。**双方言模式**：PG 测试经 `EXPLAINLAB_PG_TEST_URL` 门控（`test_v2_models_pg.py:47` pytestmark skipif），真实在线 Alembic 迁移 + 真实 SQL。A1-01 已有 `test_v2_models.py`/`test_v2_models_pg.py` 直测 ORM 约束/条件更新/fencing（TestGcTaskAndLock 等）。

### 2.2 缺失（A1-04 须新建）与冲突

#### 2.2.1 缺失模块清单【事实：经 find/grep 核实不存在】

| 层 | 缺失 | 设计落点 |
|---|---|---|
| Core | `markdown/service.py`（导入导出编排纯逻辑 + ImportReport + 变化分类 + 实体↔交换映射） | A1-T5 |
| Core | 附件/GC/孤儿扫描的**纯计划/判定逻辑**（若需 Core 承载；物理 IO 一律 backend） | §2.5 |
| backend 仓库 | `AttachmentRepository`/`TagRepository`/`TagChangeLogRepository`/`GcTaskRepository`/`ImportOriginRepository` 的 SQLAlchemy 实现 | A1-T7 续 |
| backend 适配 | `app/db/storage_lock.py`（SQLite 租约锁 + PG advisory 方言分派） | §2.5.1/§10 |
| backend 服务 | `app/services/attachments.py`（上传/校验/下载/删除/GC worker/孤儿扫描）、`app/services/markdown.py`（Vault 文件 IO + 导入导出装配）、`app/services/backup.py`（备份恢复 Manifest） | A1-T9/T10/T13 |
| backend 运维 | `app/ops/`（`rebuild_link_keys`、`v2_downgrade` 迁移包装器） | A1-T14/§2.9 |
| backend API | `routes/import_export.py`、`routes/attachments.py`、`routes/tags.py`，`routes/links.py` 增写端点（resolve/reresolve/rebuild-keys） | A1-T11/§2.6 |
| backend DTO | Import/Export/Attachment/Tag/Gc/LinkOp 请求响应模型 | §2.6 |
| backend 配置 | 存储根/大小上限/MIME 白名单/租约 TTL/心跳/GC 重试上限/安全等待期/备份位置 | §2.5/§6 |
| backend 装配 | `dependencies.py` 存储/GC 依赖；`main.py` 新路由注册 | — |

#### 2.2.2 设计与真实代码冲突（**只报告不改代码**，详见 open-decisions §C）

- **C-01（关键）**：`SQLAlchemyKnowledgeRepository`（knowledge.py:28-112）不持久化/读取 `extra_metadata`、`source_payload_hash/source_content_hash/source_instance_id`、`tags`。grep 证实这些字段在 `backend/app` 内**仅出现于 models.py**，无任何服务读写。→ A1-04 导入无法经现有 KnowledgeRepository 落 extra_metadata/源身份冗余列；tags 读恒空。**须决定扩展仓库 vs 独立持久化路径**（open-decisions D-02）。
- **C-02**：design §2.6 API 表列 `POST /reviews/{id}/withdraw` 与提案防覆盖，但代码 `ReviewStatus` 无 WITHDRAWN、ReviewService 无 withdraw、review_payload_hash 标注 A1-05。→ A1-04 **不交付** withdraw/防覆盖（A1-05），API 表该项须从 A1-04 范围剔除（open-decisions D-01）。
- **C-03**：design §2.7「active 内容变更经 submit→202」依赖现有 ReviewService（已实现），但**链接钩子在 backend 路由层不在 Core**。**R1.1 方案：导入使用 `LinkImportRestorer`，普通治理保持 K1，不得二次普通 sync**（open-decisions D-03/§J + risk R-GOV-02 / R1.1-R-K1-01）。
- **C-04**：design §6.1 称「SQLite（WAL）」，但 session.py **未启用 WAL**（rollback-journal）。备份协议若依赖 WAL 须先确认是否启用 WAL（D 方向 + open-decisions D-09）；**不得为备份擅改全局日志模式**。
- **C-05**：A1-01 报告:112 提及端口实现属「A1-03/A1-04/**A1-08**」，存在 A1-06 之后子批次引用。A1-04 边界以 A1-02 报告 §7 为准；A1-08 归属须 ChatGPT 澄清（open-decisions D-12）。

---

## 3. 需新增与修改的模块（精确清单 + 依赖方向）

> 全部为【提议】。修改既有文件须遵守红线 #5（不改 A1-01/02/03 业务代码）；knowledge.py/governance.py/schemas.py/main.py/dependencies.py/config.py 属 M0–M5/A1-01 装配层，**additive 扩展**须最小化并全量回归，凡触碰 A1-03 链接业务逻辑一律禁止。

### 3.1 新增（Core，纯逻辑，零 IO/零方言）

| 模块 | 职责 | 复用 |
|---|---|---|
| `knowledge_core/markdown/service.py` | 导入编排纯逻辑：交换文档→实体映射、变化分类（content/payload/组件 hash）、ImportReport 装配、幂等判定**决策**（比对源 hash，由 backend 提供持久化 source hash）、跨实例 Draft 规则、无 id 查重决策。**不触 DB/文件**，经端口收数据 | codec/canonical/三 Hash/LinkRestoreService/ports |
| `knowledge_core/markdown/import_report.py`（或并入 service.py） | `ImportReport`/`ImportItemResult` Pydantic 模型（created/updated/skipped/duplicates/errors/pending_review/review_ids/unresolved_links/status_changes/conflicts/warnings） | MarkdownWarningCode/LinkRestoreReport |
| （可选）`knowledge_core/attachments/planning.py` | GC/孤儿扫描的**纯判定**（引用==0？超等待期？临时文件排除？状态流转合法性），物理 IO 全在 backend | GcStatus/StorageLease |

> Core 独立性守护（`test_interfaces.py::test_core_has_no_web_framework_dependency` + `test_markdown_package_adds_no_new_third_party_dependency`）须扩展覆盖新模块，**不得删除/弱化**（红线 + AGENTS.md §4）。新模块仅 stdlib+Pydantic+ports。

### 3.2 新增（backend 适配/服务/仓库/API/运维）

| 模块 | 职责 | 方言边界 |
|---|---|---|
| `app/db/process_lock.py` | Backend lifespan 与 Offline maintenance CLI 共用 OS 独占锁；Windows msvcrt / POSIX fcntl；锁文件句柄持有全生命周期 | OS 适配，仅此模块 |
| `app/db/storage_lock.py` | `StorageKeyLock`：进程内 keyed lock + SQLite storage_lock 租约/fencing；PG 64-bit SHA-256 派生 advisory lock（会话级） | **方言 SQL 仅在此** |
| `app/services/attachments.py` | 上传（temp+原子 rename+sha256+MIME magic+大小+文件名清洗+穿越防护）、下载（按 id 查 key 短打开）、删除引用、GC worker（认领→持锁复核→quarantine→释放→purge 隔离区）、独立孤儿扫描、DB↔物理一致性检查 | 物理 IO + 经 StorageKeyLock/GcTaskRepository/AttachmentRepository |
| `app/services/markdown.py` | Vault：单/批量导出（实体→交换文档→codec.dump→文件）、单/批量导入（文件→codec.parse→Core service 决策→backend 落库 + 链接恢复 + 审核）、每文档独立事务、ImportReport 汇总 | 文件 IO + 事务装配 |
| `app/services/backup.py` | 一致性快照（SQLite Online Backup/VACUUM INTO；PG pg_dump）、DB+附件同时间点备份、Restore Offline Manifest/journal + 崩溃对账（附件先合并、DB 最后切换） | 方言快照 + 平台文件操作 |
| `app/services/repositories_v2.py`（或分文件） | `SQLAlchemyAttachmentRepository`/`TagRepository`/`TagChangeLogRepository`/`GcTaskRepository`/`ImportOriginRepository` 实现（签名严格对齐 ports.py，flush 不 commit，事务边界调用方持有，仿 links.py） | SQLAlchemy 表达式双方言通用；认领条件更新/SKIP LOCKED 分派在 db 适配 |
| `app/ops/rebuild_link_keys.py` | CLI：冻结写→Core `LinkKeyRebuild.plan`→`apply_link_key_plan`→`persist_rebuild_report`→碰撞报告 | 复用 A1-03 执行入口，**不重写** |
| `app/ops/v2_downgrade.py` | CLI：备份→校验→确认→记录 migration_ops_log→门禁→alembic downgrade→后置检查 | 复用 backup.py |
| `app/api/routes/import_export.py` | GET /knowledge/{id}/markdown、POST /knowledge/export、/import、/import/batch | — |
| `app/api/routes/attachments.py` | POST /knowledge/{id}/attachments、GET/DELETE /attachments/{id} | — |
| `app/api/routes/tags.py` | GET /tags、/knowledge?tag=、/knowledge/{id}/tag-changes | — |
| `app/api/routes/links.py`（**additive 扩展**） | POST /knowledge/{id}/links/resolve（显式绑定）、/reresolve；全局 rebuild-keys 仅 CLI | 复用 Core bind_explicit/LinkReresolve |
| `app/api/schemas.py`（additive） | Import/Export/Attachment/Tag/Gc/LinkOp DTO | — |
| `app/core/config.py`（additive） | 存储/GC/租约/备份配置字段（SecretStr 无关，普通配置） | — |
| `app/dependencies.py` / `app/main.py`（additive） | 存储依赖注入 + 新路由注册（静态字面先于动态） | — |

### 3.3 可能修改的既有文件（最小 additive，须审批 + 全量回归）

- `app/services/knowledge.py`：**R1 禁止扩展其写入 extra_metadata/source_*/tags**。新增独立 MarkdownItemRepository，V1 仓库保持不变。
- `app/api/schemas.py`：**R1.1 采用 V2-only read contract（见 §20.1）：不扩展 V1 `KnowledgeOut`、不增 tags/extra_metadata 读字段、不改 V1 GET 结构**；V2 字段仅经 `MarkdownItemRepository` + `TagRepository` 的 V2 读/导出路径返回。

> **禁止修改**：`markdown/codec.py`/`canonical.py`/`link_service.py`/`links.py`（A1-02/03 业务）、`review/__init__.py`（M2 + A1-05 范围）、迁移 0006、`db/locking.py` 的 A1-03 锁逻辑、任何现有测试。

---

## 4. 模块依赖图

```
frontend(A2，本轮不动)
   │ HTTP /api
   ▼
backend API 层
   routes/import_export ─ routes/attachments ─ routes/tags ─ routes/links(扩展写端点)
   │            │                  │                 │
   ▼            ▼                  ▼                 ▼
backend 服务/装配层
   services/markdown(Vault) ─ services/attachments ─ services/backup ─ ops/{rebuild_link_keys,v2_downgrade}
   │            │                  │                 │
   │            ├─ db/storage_lock(StorageKeyLock 方言分派) ─┐
   │            ├─ services/repositories_v2(Attachment/Tag/Gc/ImportOrigin) ─┤
   │            └─ 复用 services/knowledge + governance(build_review_service) + links(build_link_restorer/apply_link_key_plan)
   ▼                                                         │
knowledge-core（纯，stdlib+Pydantic+ports）                   │
   markdown/service(导入导出编排+ImportReport+变化分类) ◀──────┘（经端口注入数据）
   markdown/{codec,canonical,link_service,links} + domain/entities + ports + review(复用)
```

【提议】依赖只能自上而下（AGENTS.md §3）。Core 不 import backend/SQLAlchemy/FastAPI；方言 SQL/文件 IO/HTTP/事务/锁全在 backend 适配层。导入编排的**决策**在 Core（纯），**落库/文件/事务**在 backend。

---

## 5. 核心数据流

### 5.1 单文档导入（A）【R1 权威提议】

**核心原则**：来源身份负责串行化，源 payload hash 负责判断内容版本；两者不可混为一个锁键。数据库没有 ImportOrigin 唯一约束，因此本阶段只承诺单实例内应用层幂等，不宣称数据库级或多实例幂等。

来源身份键：`(source_instance_id, source_document_id)`。`source_instance_id` 缺失时以显式 `null` 参与键计算，不用 payload hash 代替身份。锁键由该 tuple 的稳定规范化序列化再 SHA-256 派生。`source_payload_hash` 只用于版本比较，不作为互斥锁身份。无来源身份但显式指定目标 item_id 时锁 `target-item:<id>`；无身份/无目标 id 的新文档锁 `anonymous-content:<content_hash>`，防止同一内容并发重复建条目。

```text
POST /knowledge/import 或 /knowledge/import/batch
 0. 解析输入、校验 codec/canonicalization 版本、计算 source_payload_hash 和 content_hash；
    提取 source identity。无 source_document_id 的文档走无身份查重分支，不伪造来源身份。
 1. 在等待锁前读取来源身份状态快照 S0：所有匹配 ImportOrigin（按 imported_at 排序）、关联 item_id、当前 item.source_payload_hash，
    以及同身份 pending ReviewRequest 的 import envelope 摘要。
 2. 获取进程内 keyed 同步锁(lock_key)：有来源身份用 identity_key；已有目标用 target-item id；无身份新文档用 content_hash。所有导入入口必须经过同一个 ImportCoordinator；
    **R1.2 D20**：导入/批量导入/approve 写入口采用同步执行模型（FastAPI 同步 `def` 路由，运行于线程池），`ImportCoordinator` 统一管理同一把同步身份锁；Session 在线程池内部创建/使用/关闭，禁止异步 keyed lock 与 `threading.Lock` 双协调（§21.3）。
 3. 锁内重新读取状态 S1：
    - 若 S1 与 S0 不同，说明本请求等待期间来源已被其他请求处理；若入站 hash 已被应用或已有同 hash pending，则返回 skipped/reused pending；
      否则返回 SOURCE_CHANGED_DURING_WAIT，不写入，要求调用方重新发起/确认，避免并发旧版本覆盖新版本。
    - 若同一 source identity 对应多个不同 item_id，返回 SOURCE_IDENTITY_AMBIGUOUS，禁止自动选一个。
    - 同一 identity + 同一 source_payload_hash 已应用 → skipped。
    - 同一 identity 存在不同 hash 的 pending import → SOURCE_HAS_PENDING_IMPORT，不再创建第二张 pending。
 4. 若不存在来源身份记录：无 id/无身份文档先按 content_hash 查重；命中只报 duplicates，不静默覆盖。
    对有来源身份的文档，按策略创建目标条目。
 5. 变化分类：
    - 新条目 → draft；跨实例导入不保留 active，记录 status_changes。
    - 既有 draft 内容变化 → 直接更新。
    - 既有 active 的 title/content 变化 → 创建 UPDATE_ITEM ReviewRequest，HTTP 返回 202 语义，不改 active 内容。
    - 仅 tags/extra_metadata/附件/来源元数据变化 → 按本地导入策略更新；tags 变化写 TagChangeLog。
 6. Draft/非审核导入：在**同一个 DB 事务**内经 MarkdownItemRepository 写 item 的 V2 字段、TagRepository/TagChangeLogRepository 写 tags/审计、AttachmentRepository 写引用、LinkImportRestorer 恢复链接、
    ImportOriginRepository 追加来源版本记录并更新 item.source_* 冗余列。任何步骤失败整篇 rollback。
 7. Active 审核导入：ReviewRequest.payload 顶层保留 Core 识别的 title/content/status/space_id 字段，并增加命名空间 `__a1_import` envelope，至少包含：
    `schema_version`、source identity、source_payload_hash、canonicalization_version、完整可重建的导入上下文（tags/extra_metadata/附件 staging manifest/显式链接 hints）、context_digest。
    该 envelope 不改变 Core ReviewService；Core `_apply_update` 只应用原有四字段。
 8. Active 审核批准：backend approve 路由在 `service.approve()` 后、首次 commit 前检测 `__a1_import`：校验 envelope/schema/digest；
    应用 tags/extra_metadata/附件引用/来源冗余列/ImportOrigin；调用 LinkImportRestorer（target_id 优先、正文权威规则由既有 Core 实现）；
    **此分支不再额外调用普通正文 sync**，避免双重解析覆盖绑定。非导入 ReviewRequest 保持现有 K1 路径完全不变。所有动作与 approve 在同一事务，失败则审核仍 pending、item/links/tags/origin 全部回滚。
 9. Active pending 附件只进入 `import-staging/<review_id>/<operation_id>/`，不提前创建 Attachment 引用。approve 时将内容寻址文件提升/复用到正式附件根并写引用；reject 成功提交后清理 staging；清理失败由 staging orphan sweep 回收。
    若 approve DB 事务失败但物理 blob 已提升，blob 作为无引用孤儿保留，重试可校验 hash 后复用，绝不反向删除未知引用文件。
10. Reject：不写 ImportOrigin、不改 item/tags/attachments/links；提交 reject 后清理该 review 的 staging。
11. 每文档事务独立；单篇失败 rollback 并记录 errors，批量继续下一篇。索引同步在 DB commit 后执行，失败只记 warning/reindex-needed，不回滚已提交业务数据。
12. ImportReport 明确区分 created/updated/skipped/duplicates/errors/pending_review/reused_pending/rejected_conflicts/status_changes/unresolved_links/warnings。
```

**R1.1 时序与锁强化（见 §20.3）**：S0 必须是**只读短会话**，读取后立即关闭，绝不持有其事务等待身份键锁；获身份键锁后用**全新只读会话**读取 S1；S1 判定完成后才开启**文档写事务**，提交后释放锁。导入提交路由为 `def`（同步）或在线程池执行键同步 DB 操作，不得在 asyncio 事件循环内阻塞等待 `threading.Lock`。Approve 导入分支必须参加**同一身份键锁**（见 §19.3 / §20.3）。

**R1.2 执行模型与身份语义（见 §21）**：D20 将上述“同步或线程池”收敛为**单一同步执行模型**——写入口为同步 `def` 路由，`ImportCoordinator` 只使用同步身份锁，Session 在**实际执行线程内**创建/使用/关闭，锁覆盖从 S1 判定到 Commit/Rollback + Session 清理的完整业务事务，客户端断开不得提前释放；不引入 async keyed lock + `threading.Lock` 双架构。D18 明确 `source_instance_id` 是文档**来源实例**身份、`source_document_id` 是来源文档身份，当前导出实例身份为 `exporter_instance_id`（仅 frontmatter/manifest，不落 DB 列）；导入/修改/再导出**不得覆盖原始来源身份**，同来源不同版本进入既有冲突/审核机制。

**ImportOrigin 写入时机**：Draft/直接应用导入在成功业务事务内写入；Active 导入仅在 approve 的同一事务内写入。Pending 阶段不伪造 ImportOrigin。Pending 幂等通过扫描 ReviewRequest.payload 的 `__a1_import` envelope 实现，受单实例 keyed lock 保护。相同 identity+相同 hash 复用现有 pending；相同 identity+不同 hash 且旧 pending 未解决时拒绝新导入。

**持久化路径**：采用独立 `MarkdownItemRepository`，负责完整读写 `extra_metadata/source_*`，并协调 TagRepository；不扩展 V1 `SQLAlchemyKnowledgeRepository`，避免 V1 PATCH 默认 `{}` 覆盖导入 metadata。V1 Repository 保持原样。

**治理挂接**：导入的链接恢复必须调用既有 `build_link_restorer`；普通非导入治理请求仍走既有 K1 `sync_links_or_conflict`。不得修改 Core ReviewService，不得绕过 active 审核。

### 5.2 单/批量导出（A）【提议】

```
GET /knowledge/{id}/markdown 或 POST /knowledge/export {ids, space_id?}
 1. backend 读实体（KnowledgeRepository + TagRepository.list_item_tags + AttachmentRepository.list_attachments
    + LinkRepository.list_links + ImportOriginRepository.list_for_item）
 2. 实体 → MarkdownDocument 交换映射（sources/links/attachments 为 dict 形状，保留全部子键；
    tags/extra_metadata 回填；space encode_space；status/version/timestamps 原样）
 3. codec.dump(document, resolution=?) → RenderedMarkdown(text, state, warnings)
    - 冲突态：resolution=None → 原始块逐字 + 实体修改未写 + ENTITY_EDITS_NOT_EXPORTED 告警（不称完全无损）
 4. 单条返回 text；批量打包（zip/目录，manifest 清单含 content_hash）【待审批 D-07 打包形态】
    - **R1.2 D19**：Batch A 导出不得宣称“完整附件导出”；含附件内容请求须显式标记 unsupported，或仅导出附件**引用元数据**并明确声明不完整（不得静默丢弃）。
 5. 导出含 source_instance_id + source_document_id（来源身份，原样保留）；另写 exporter_instance_id=当前实例（仅 frontmatter/manifest，不落 DB）；**治理状态实例本地，不宣称完全无损**
```

**R1.3 Hash 投影与身份初始化（§22）**：导出时先在**剥离 exporter** 的输入上计算 `document_content_hash`/`document_payload_hash`，再于传输层注入 `__explainlab_exporter_instance_id`（ZIP manifest 用 `exporter_instance_id`）；不得修改 A1-02 Canonical/Hash（D22）。本地原生文档（无 ImportOrigin、`source_instance_id` 为空、无匹配物化记录）首次导出时，**先过 Journal 恢复门**（有效 PREPARED MATERIALIZE 必须先恢复，恢复完成前不分类/不写身份），再写 **MATERIALIZE PREPARED Journal**，物化 `source_instance_id`=当前实例、`source_document_id`=`item.id`，重读校验后 COMMITTED+归档（D23）；Journal 数据契约见 §22.2，**不得**仅凭 `source_instance_id` 非空推断已物化。

### 5.3 附件上传与共享（B）【提议】

```
POST /knowledge/{id}/attachments (UploadFile)
 1. 校验：大小 ≤ 上限（超限 413/400+warning）；MIME 白名单 + magic bytes 双校验（stdlib 字节签名，SVG 禁内联/消毒【待审批 D-08】）；
    文件名清洗（仅显示名，去路径分隔/控制字符）
 2. 读字节 → sha256 → storage_key=content_hash；内容完整性（重算 hash 比对）
 3. 获取 StorageKeyLock.acquire(storage_key, owner, ttl)（SQLite 租约 / PG advisory）
 4. 持锁：物理写入 temp → 原子 rename/os.replace 到 storage_root/<hash 前缀分片>/<storage_key>
    （同内容已存在 → 跳过物理写，共享；**先写物理后插 DB**）
 5. 短事务插 attachment 引用行（item_id, filename, mime, size, storage_key, content_hash）；
    引用数 = COUNT(attachment WHERE storage_key)（DB 派生，无计数器）
 6. DB 失败 → 物理成孤儿 → 独立孤儿扫描回收（口径 B，不依赖失败事务内 gc_task）；物理失败 → 不插 DB
 7. 释放锁（fencing：owner+token 匹配才释放）
 8. 路径穿越防护：storage_key 由 hash 派生，规范化校验落存储根内，拒 ..//绝对路径/逃逸 symlink；下载按 id 查 key
```

### 5.4 GC 与孤儿扫描（B）【提议，详见 §7 状态机】

```
删除附件引用 DELETE /attachments/{id} → 删引用行（不删物理）→ 若 COUNT(storage_key)==0 →  enqueue gc_task(pending)
GC worker：原子认领 → 获 storage_key 锁 + 心跳 → 持锁重算引用 → >0 cancelled / ==0 持锁 quarantine → 记录 → 释放 →
           安全等待期后再次持锁复核 ==0 + fencing → purge 隔离区 → done
独立孤儿扫描（周期，正确性兜底）：扫物理 + 隔离区 → 对照 DB 引用集合 → 无引用 + 超等待期 + 排除临时/并发 →
           持锁复核 ==0 → quarantine → 等待期后 purge；DB 有引用而原始缺失 → 从隔离区恢复
```

### 5.5 链接用户操作与运维（C）【提议】

```
POST /knowledge/{id}/links/resolve {target_id, title, alias?}
  → Core RepositoryLinkResolver.bind_explicit(source, target, title, alias)（允许 archived/跨空间，返回链接+告警）
  → 跨空间/archived 须用户确认参数【待审批 D-05】→ LinkRepository.save_link（全局版本守卫）→ commit
POST /knowledge/{id}/links/reresolve → Core LinkReresolve.reresolve(item)（只重试 missing/ambiguous）→ commit
CLI `app.ops.rebuild_link_keys --target-version N`（全局运维写操作，不暴露 HTTP 写入口）：获取 OS 进程锁 → Core LinkKeyRebuild.plan → apply_link_key_plan（A1-03 十步独占事务）→ persist_rebuild_report。HTTP 仅提供报告只读查询。
CLI `app.ops.backup` / `restore` / `recover` / `v2_downgrade`（Offline 维护入口，统一获取同一 OS 进程锁）
```

> **严格区分**（design §2.9 + 用户任务 C）：链接键重建（link_normalization_version）≠ 搜索索引重建（reindex/FTS/向量）。rebuild-keys 只写 knowledge_link 3 列，**不触 FTS/向量/knowledge_item**（apply_link_key_plan 步 8 已守条目基线）。不得经新 API 绕过治理门禁（显式绑定是链接治理列操作，不改 knowledge_item 内容，不进 ReviewService；但 active 内容变更仍走审核）。

---

## 6. 导入导出事务设计（A）【提议】

| 维度 | 设计 | 依据 |
|---|---|---|
| 事务粒度 | **每文档独立事务**；单文档失败 rollback 该事务 + 记 errors，继续其他 | design §2.6.2:459 |
| 批量语义 | **非全有全无**；ImportReport 汇总各文档结果 | §2.7:493 |
| 并发同来源身份 | 单实例 OS 进程锁 + 进程内 keyed threading.Lock(identity tuple) + 锁内重读/快照冲突检测 + 同一 DB 事务；不宣称 DB 唯一约束或多实例幂等 | R1 D-15/D-17 |
| 链接恢复事务 | 与条目写入**同一事务**，失败整体回滚；版本异写 409 零写入 | LinkSyncService ABC + K1 |
| 审核事务 | active 内容变更 submit 生成 pending（同事务），**不应用**；批准在独立 approve 请求应用 | review/__init__.py:65 + governance K1 |
| 附件事务 | 先物理（temp+rename，DB 事务外）→ 短事务插引用行；DB 失败物理成孤儿由独立扫描兜底 | §2.5.1:317 |
| 索引同步 | commit 后 sync_index（仿 knowledge.py，失败不回滚已提交内容，如实告警） | knowledge.py:84 |
| 幂等权威 | 入站**源文件** payload_hash vs 持久化 source_payload_hash（非目标再生 hash） | §2.6.3 + A1-02 报告 L2 |

**已知幂等边界（A1-02 报告 L2/L3，A1-04 须 ImportReport 如实提示）**：
- 含重复键源文件「导出→再导入」payload_hash 不等（`_duplicates` 诊断元键不再生），content_hash 相等 → 判元数据变化非 skipped；但「重导同一入站文件」仍 skipped（幂等权威是入站源 hash）。
- 已知键命名空间冲突前缀化（`x_explainlab_title`）致 payload_hash 变化 → 提示属元数据变化非内容审核。

---

## 7. 附件存储与 GC 状态机（B）【提议，对齐 design §2.5】

### 7.1 存储布局

- 存储根 `backend/data/attachments/`（gitignore），hash 前缀分片（如 `<key[:2]>/<key>`）。
- 隔离区 `backend/data/attachments/_quarantine/<storage_key>.<operation_id>`（**同卷**保证原子 rename）。
- 上传临时文件 temp 命名模式（孤儿扫描排除）。
- 内容寻址：storage_key=sha256(content)，物理唯一不可变，多引用共享；attachment.id 行唯一。
- **引用数 = COUNT(attachment WHERE storage_key=?)**（DB 派生权威，**无独立计数器列**）。

### 7.2 GC 状态机（7 态，GcStatus 已定义）

| 状态 | 含义 | 终态 | 流转 |
|---|---|---|---|
| pending | 待认领 | 否 | →running（原子认领） |
| running | 持租约执行中 | 否 | →done/cancelled/failed_retryable/failed_permanent/needs_manual；租约过期可被他人重新认领（新 token） |
| **cancelled** | 持锁复核引用>0，放弃回收 | **是** | 不删任何文件；引用归零后新 gc_task 重新发起 |
| done | quarantine+purge 完成 | 是 | — |
| failed_retryable | 瞬时失败 attempts<max | 否 | next_retry_at 退避→到期回 pending |
| failed_permanent | attempts≥max/不可重试 | 是（待人工） | →needs_manual |
| needs_manual | 歧义/损坏/人工 | 否（挂起） | 人工→pending 或→cancelled |

### 7.3 GC 流程（R5-1 持锁 quarantine，**禁止释放锁后删原始文件**）

1. 原子认领 gc_task（PG `FOR UPDATE SKIP LOCKED`+UPDATE；SQLite 短事务条件 UPDATE rowcount==1，lease_token+1/attempts+1）。
2. 获 storage_key 租约锁 + 心跳续租。
3. **持锁期间**短事务重算引用数（COUNT）。
4. 引用>0 → 短事务置 **cancelled** → 释放锁 → **不删文件**。
5. 引用==0 → **仍持锁**原子 quarantine：原始文件 rename→隔离区（同卷；Windows os.replace/退避见 §9）。quarantine 成功=原始路径不再持有文件。
6. 短事务记录 quarantine_path/quarantined_at（status 仍 running）→ 释放锁。
7. **purge（释放锁后，仅隔离区）**：安全等待期（mtime 阈值）后**再次持锁复核引用==0 + fencing** → 删**隔离区文件** → 置 done。
8. **关键约束**：原始文件移除必须在持锁+引用复核临界区内；释放锁后只清隔离区，**绝不直接删原始路径**。purge 前引用回升 → 隔离区文件恢复回原始路径或置 cancelled。
9. 崩溃恢复：quarantine 后崩溃 → 隔离区残留由独立孤儿扫描识别安全 purge；DB 有引用而原始缺失 → 从隔离区找回。
10. 失败分级：瞬时→failed_retryable+退避；不可重试/attempts≥max→failed_permanent→needs_manual；歧义→needs_manual。

### 7.4 StorageKeyLock 双方言（§2.5.1/§10）

- **SQLite**：租约式逻辑锁。storage_lock 表短事务条件写入（INSERT 新锁 / UPDATE WHERE lease_expires_at<now 过期接管），PK 保证仅一 owner，单调 lease_token，**立即 commit 释放库级写锁**；物理操作在 DB 写事务**之外**；释放/续租带 owner+token fencing（rowcount==1 成功，==0 中止）。**诚实限制**：非严格行级锁，**降低而非消除 TOCTOU**；严格互斥需求降级单写者/库级串行【待审批 D-04】。
- **PG**：`pg_advisory_lock(bigint_key)` 会话级，bigint_key 由 SHA-256(storage_key) 前 8 字节派生；锁绑定持有它的物理连接，finally unlock/close，崩溃自动释放。碰撞最多导致无关 key 额外串行，仍须按精确 storage_key 执行引用 COUNT。
- **旧 Worker 恢复保护**：每个不可逆物理步骤前重验 owner+token（storage_lock 与 gc_task 双重 fencing），失配中止。

### 7.5 独立孤儿扫描（口径 B，正确性兜底）

【事实】DB 事务失败后该事务内 gc_task 随事务回滚 → 不可靠 → 须独立扫描。周期扫物理+隔离区 → 对照 attachment.storage_key 集合（`list_storage_keys`）→ 无引用+超等待期+排除临时/并发 → 持锁复核==0+fencing+quarantine+等待期后 purge；DB 有引用原始缺失 → 从隔离区恢复。gc_task 为优化/可观测，孤儿扫描为正确性兜底，**两者均绝不删仍被引用文件**。

---

## 8. 链接 API 与运维入口设计（C）【提议】

### 8.1 HTTP 端点（additive，静态字面先于动态）

| 端点 | 语义 | 复用 | 治理 |
|---|---|---|---|
| GET /knowledge/links/resolve-candidates | 候选发现（已有） | RepositoryLinkResolver.find_candidates | 只读 |
| GET /knowledge/{id}/links、/backlinks | 出链/反链（已有） | LinkRepository | 只读 |
| **POST /knowledge/{id}/links/resolve** | 人工显式绑定（archived/跨空间须确认） | bind_explicit + save_link | 链接治理列，不改内容，不进 ReviewService |
| **POST /knowledge/{id}/links/reresolve** | 重解析 missing/ambiguous | LinkReresolve.reresolve | 守同一套规则 |
| GET /knowledge/links/rebuild-report/{id}（或返回体） | 重建结果/碰撞报告查看 | LinkRebuildReport | 只读；全局重建本身只允许 CLI

### 8.2 运维 CLI

- `python -m app.ops.rebuild_link_keys --target-version N`：获取 OS 进程锁→冻结链接写→plan→apply→报告落盘→碰撞 ambiguous/conflict 不随机重绑→唯一约束校验→旧版本键留痕。全局 rebuild 不提供 HTTP 写端点。
- `python -m app.ops.backup create` / `restore --backup-id ...` / `recover`：获取 OS 进程锁；仅 Backend 停止时运行。
- `python -m app.ops.v2_downgrade`：获取 OS 进程锁→备份 DB+附件→校验→用户确认（告知删 V2 数据）→写文件操作日志→**门禁：备份未完成/校验未过/未确认→拒绝**→alembic downgrade→后置检查。**Alembic 0006 downgrade 只管 Schema，不承担交互/备份**（包装器承担）。

### 8.3 D8/D10 与 A1-03 延后事项重评

| 项 | A1-03 状态 | A1-04 处置 |
|---|---|---|
| D8 显式绑定 HTTP 写入口 | Core 已验证，无 HTTP | **A1-04 交付** resolve/reresolve HTTP；全局 rebuild-keys 仅 CLI |
| D10 重建报告落盘 | persist_rebuild_report 已实现（backend/data/ops/） | **A1-04 交付**查看入口 + CLI |
| 门禁 C 残余并发窗口 | A1-03 报告标延后，**但 K1+K2 整改已关闭**（PG 表锁；SQLite P2 六字段） | A1-04 **不重开**，复用 apply_link_key_plan；D 方向只评估活性 |
| 审核批准路径写侧 demote/sync | A1-03 报告标延后，**K1 整改已挂接** governance.py | A1-04 导入 Draft/Active approve 使用 LinkImportRestorer；普通治理请求 K1 路径不变 |
| 前端绑定 UI | 无 | **A2**，A1-04 不做 |
| v2 规范化规则 | fixture-only，未发布 | A1-04 **不发布 v2**；rebuild-keys 支持目标版本参数但 v2 规则未定义→拒绝【待审批 D-11】 |

---

## 9. SQLite 与 PostgreSQL 差异（B/C/D）【提议，对齐 design §10】

| 维度 | SQLite | PostgreSQL | 封装位置 |
|---|---|---|---|
| 行级写锁 | **不支持**；BEGIN IMMEDIATE 库级 | 支持行级 | db/storage_lock.py |
| storage_key 协调 | 同进程 keyed lock + storage_lock 租约/fencing；单实例 OS lock 防第二 Backend/CLI | 会话级 advisory lock（64-bit SHA-256 派生 key） | db/storage_lock.py + process_lock.py |
| GC 认领 | 短事务条件 UPDATE rowcount==1 | FOR UPDATE SKIP LOCKED + UPDATE | db 适配 + GcTaskRepository |
| 唯一约束 | NULL 互不相等→非空 normalized_link_key（已建） | 同（不依赖 NULLS NOT DISTINCT） | 0006 已处理 |
| 一致性快照 | SQLite Online Backup API（**禁裸拷 db+wal+shm**） | Offline pg_dump --format=custom | services/backup.py |
| 恢复切换 | 附件先合并校验，staging DB 验证后关闭句柄、os.replace 切换并保留 previous | Staging DB + **按 §20.5 BAK-1 清场**（维护库 / 禁新连接 / terminate / `pg_stat_activity` 清零）后 rename target→previous、staging→target；Backend 离线，无连接池重建/多实例编排 | services/backup.py |
| 租约续租 | 心跳短事务条件 UPDATE（owner+token fencing） | advisory 会话级无需续租 | db/storage_lock.py |
| 全文检索 | FTS5 trigram（V1，**不动**） | tsvector/GIN（V1，**不动**） | 既有 retrieval，A1-04 不触 |

### 9.1 平台兼容（Windows vs POSIX，§2.5.4/§6.8/§10.1）

- Windows 占用文件无法 rename/delete（sharing violation）→ 关闭句柄 + 指数退避重试（上限 N）→ 仍失败 failed_retryable 交孤儿扫描/人工，**不强删**。
- 原子覆盖用 `os.replace`（非 os.rename）；目标占用仍失败。
- symlink 需特权 → 附件版本切换用**指针文件**（DB/配置记录当前版本目录），切换=更新指针+fsync。
- 跨卷 rename 非原子（copy+delete）→ Manifest+对账+孤儿扫描兜底，**明确标注非原子降级**。
- 同卷假设：隔离区与存储根同卷才原子 rename；跨卷部署降级【待验证 §9.16】。
- **不得宣称跨平台原子切换已验证**；目标部署平台【待审批 D-10】。

---

## 10. 错误处理与恢复策略【提议】

| 场景 | 策略 | 稳定码/告警 |
|---|---|---|
| 导入单文档失败 | rollback 该文档事务，记 errors，继续批量 | ImportReport.errors |
| frontmatter 冲突未解决 | 保留原始+未知，不静默再生；按批量策略跳过/保留 | CONFLICT_REQUIRES_RESOLUTION |
| 版本异写（链接） | 409 整事务零写入 | link_version_mismatch |
| canonicalization 版本不一致 | 拒绝直接比 hash，降级 content_hash+字段级 | CanonicalizationError→ImportReport 告警 |
| 附件超限/MIME 不符/穿越 | 413/400 拒绝，不落盘 | 稳定码 + warnings |
| DB 事务失败后物理孤儿 | 独立孤儿扫描回收（不依赖失败事务 gc_task） | — |
| GC 瞬时失败 | failed_retryable + next_retry_at 退避 | — |
| GC 不可重试/attempts≥max | failed_permanent→needs_manual | — |
| 租约续租失败/被接管 | 立即中止不可逆物理操作 | abort 原因记录 |
| Windows 占用 rename 失败 | 退避重试→failed_retryable，不强删 | — |
| 备份中途失败 | 清单不全/hash 不符判废，正式 intact | — |
| 恢复切换中途崩溃 | Manifest phase + 真实资源三方对账→回滚旧 generation（无标记）/完成（有标记且对账一致） | needs_manual（无法确定） |
| Manifest 与资源不一致 | **不盲信标记**→回滚或可验证前滚（仅幂等可补全+校验通过） | 不一致告警 |
| 模型未配置（导入不依赖模型） | 导入导出**无需模型**；查重无 id 用 content_hash 非 LLM | — |

> 对外错误只回**稳定码**，不回 str(exc)/主机/端口/堆栈（AGENTS.md §9）。服务端日志只记异常类型等脱敏信息。

---

## 11. 安全边界【提议】

- **密钥**：导入导出/附件不触模型密钥；配置新增字段非密钥（普通 str/int）。SecretStr 机制不变。
- **路径穿越**：storage_key 由 hash 派生；规范化校验落存储根内；拒 `..`/绝对路径/逃逸 symlink；下载按 attachment.id 查 key，**不接受用户路径**。文件名清洗仅显示名。
- **MIME**：白名单 + magic bytes 双校验（stdlib 字节签名，**不引 python-magic**）；SVG 禁内联或消毒【待审批 D-08】。
- **大小上限**：默认 10MB 可配，超限 413/400。
- **治理门禁**：active 内容变更经 ReviewService，导入不绕过；显式绑定是链接治理列操作（不改内容）。
- **审计**：tag_change_log append-only，删除后 item_id_snapshot/title_snapshot 保留身份（口径 C，schema 已实现）。
- **GC 误删防护**：持锁复核引用+quarantine+安全等待期+引用回升恢复，**绝不删仍被引用文件**。
- **备份门禁**：v2_downgrade 备份未完成/校验未过/未确认→拒绝破坏性 downgrade。
- **依赖**：A1 零新增必需依赖（stdlib hashlib/uuid/pathlib/json/os/shutil + 既有 SQLAlchemy/psycopg/Alembic/FastAPI UploadFile）。**不引 PyYAML/python-magic/DOMPurify/KaTeX**。

---

## 12. 配置新增（additive，backend/app/core/config.py）【提议，待审批 D-04/D-08/D-10】

| 字段（建议名） | 默认 | 用途 |
|---|---|---|
| attachment_storage_root | backend/data/attachments | 存储根（锚定 BACKEND_DIR） |
| attachment_max_size_bytes | 10*1024*1024 | 大小上限 |
| attachment_mime_whitelist | image/png,image/jpeg,image/gif,image/webp,application/pdf,text/plain,text/markdown,text/csv | MIME 白名单 + magic bytes/文本 UTF-8 校验 |
| attachment_svg_policy | reject | SVG 不接收；不做主动内容消毒 |
| storage_lease_ttl_seconds | 60 | 租约 TTL |
| storage_lease_heartbeat_seconds | 15 | 心跳间隔 |
| gc_max_attempts | 8 | 重试上限 |
| gc_quarantine_wait_seconds | 86400 | purge 安全等待期 24h |
| gc_orphan_scan_interval_seconds | 300 | 孤儿扫描周期 5min |
| backup_location / backup_retention_count | BACKEND_DIR/backups / 5 | Offline 备份位置/保留有效备份数 |
| source_instance_id（配置名沿用 R1.1；语义=本实例/导出者） | `BACKEND_DIR/data/source-instance-id`（锁后首次生成规范小写 UUID；原子不覆盖写入；损坏 fail-closed） | 逻辑实例稳定身份；重启/crash 保持；备份保留；导出时以 `exporter_instance_id` 写入 frontmatter/manifest（不落 DB 列）；clone 显式 rotate（R1.1 D-13 + R1.2 D18，见 §20.2/§21.1） |
| api_host | 127.0.0.1 | HTTP 监听地址（R1.2 D21；R1.3 D24 收紧）。仅允许精确 IP `127.0.0.1`/`::1`，**`localhost` 不得作为绑定配置**；**未启用认证时非 loopback 配置启动 fail-closed**（`NON_LOOPBACK_WITHOUT_AUTH`）；CORS/代理转发头不得视为认证（§21.4、§22.3） |

> 空字符串→None 归一沿用现有 validator 模式。配置不含密钥。具体数值须用户拍板（design §9.5）。

---

## 13. 迁移策略（**无新迁移**）【事实+提议】

- 【事实】0006 已建全部 A1 表与列（§2.1.1）。**A1-04 不为 attachment/tag/gc/import_origin/storage_lock 新增迁移**（红线 #2）。
- 【提议】备份恢复 **Manifest 持久化优先用文件**（fsync，被切换资源之外，design §6.3）+ 可选 migration_ops_log。**若需新表**（如 migration_ops_log 落 DB）→ **触发红线 #2，须升级为独立审批项，本轮不建**。建议 migration_ops_log 用文件/JSON 落 `backend/data/ops/`（仿 persist_rebuild_report），避免新迁移。
- 【提议】附件版本化目录（`attachments/<version>/`）+ 指针文件（DB/配置记录当前版本）——指针若落 DB 需新表/列→同样触发红线 #2；**建议指针落配置文件/JSON**，避免新迁移【待审批 D-09】。
- 回滚两类：Schema Rollback（0006 downgrade 删 V2 表/列，**丢 V2 数据非无损**，经 v2_downgrade 门禁）；Data Rollback（依赖备份）。**V1 核心数据 downgrade 后不变；不宣称删表列无损**。
- 旧 V1 数据无损：0006 additive 已验证（A1-01）；A1-04 导入对旧条目补建 ImportOrigin（无来源记录→content_hash 查重+提示，不静默覆盖）。

---

## 14. 测试方案【提议，全部待验证，不得宣称已通过】

### 14.1 双方言模式（沿用既有）

- SQLite：tmp_path + create_all（conftest）；真实文件附件用 tmp_path 存储根。
- PG：`EXPLAINLAB_PG_TEST_URL` 门控（pytestmark skipif），真实在线 Alembic 迁移 + 真实 SQL + 真实 advisory lock。
- Core：InMemory 仓库（helpers）+ 纯函数单测；独立性守护扩展覆盖 markdown/service.py + attachments planning。
- **真实文件系统**：附件上传/GC/quarantine/孤儿扫描/备份恢复须用真实临时目录（非 mock IO）。
- **故障注入**：DB 事务失败后孤儿、GC 双 Worker、租约过期接管、续租失败中止、quarantine 后崩溃、恢复切换中途 kill、Manifest 不一致、Windows 占用（真实 Windows 环境）。

### 14.2 测试落点（新增文件，不改现有测试）

| 测试文件（建议） | 覆盖 |
|---|---|
| knowledge-core/tests/test_markdown_service.py | 导入编排纯逻辑/变化分类/ImportReport/幂等决策/跨实例 Draft |
| backend/tests/test_import_export.py / _pg.py | 单/批量导入导出、每文档事务、部分失败、active 202、源 hash 幂等、extra_metadata 保真 |
| backend/tests/test_attachments.py / _pg.py | 上传校验/共享/引用数/穿越防护/MIME/大小/下载/删除 |
| backend/tests/test_storage_lock.py / _pg.py | SQLite 租约 fencing/续租/接管；PG advisory 互斥/崩溃释放 |
| backend/tests/test_gc.py / _pg.py | 认领双 Worker/状态机/持锁 quarantine/释放后仅 purge 隔离区/引用回升恢复/退避 |
| backend/tests/test_orphan_scan.py / _pg.py | DB 失败孤儿/隔离区残留/安全等待期/排除临时/DB 有引用原始缺失恢复 |
| backend/tests/test_backup_restore.py / _pg.py | 快照一致性/Manifest 两阶段/中途 kill 回滚/对账不盲信标记/Windows 指针 |
| backend/tests/test_link_ops_http.py | resolve/reresolve/rebuild-keys 写端点/碰撞报告/治理不绕过 |
| backend/tests/test_ops_cli.py | rebuild_link_keys/v2_downgrade 门禁 |
| backend/tests/test_import_idempotency_pg.py | 跨实例重导幂等（真实 PG） |

### 14.3 回归门禁

- 根级 `uv run pytest -o addopts="--import-mode=importlib"`（**切勿 -o addopts=""**）一次性收集 backend+core。
- `uv run ruff check`（**禁 format**）。
- 前端 `npm run test && npm run typecheck && npm run build`（A1-04 若不动前端可只验证未破坏；A1-06 全量）。
- Core 独立性守护 + A1-02 冻结 291 + A1-03 链接套件**不得回归**。
- 干净副本从零锁定安装验证（宣称安装/构建通过前）。

---

## 15. 验收标准（A1-04，对齐 design §2.11 子集）【提议，待验证】

> 逐项可执行验收见 `V2-A1-04-acceptance-matrix.md`。此处列阶段级门禁：

- [ ] 导入导出：正常态语义无损往返、未知字段不丢、冲突态不称完全无损；ImportReport 全字段；每文档事务+部分失败；跨实例默认 Draft+status_changes。
- [ ] 幂等：源 payload_hash vs 持久化 source_payload_hash（非目标再生）；重导同一文件 skipped；canon 版本不一致降级；无来源历史条目补建+content_hash 查重不静默覆盖。
- [ ] active 内容变更经 ReviewService→202 不绕过；链接恢复 target_id 优先 + 绑定优先 + LinkImportRestorer（普通治理 K1 不变）。
- [ ] 附件：storage_key=sha256 共享、引用数 DB 派生、穿越防护、MIME/大小校验、Windows 兼容。
- [ ] StorageKeyLock：SQLite 租约 fencing+续租+续租失败中止+单/多进程限制+TOCTOU 边界与降级；PG advisory 互斥+崩溃释放。
- [ ] GC：持锁引用复核+原子 quarantine（禁释放锁后删原始）+释放后仅 purge 隔离区+引用回升恢复；状态机含 cancelled；原子认领双 Worker 仅一+崩溃恢复+旧 Worker fencing。
- [ ] 独立孤儿扫描：含隔离区+安全等待期+排除临时/并发+DB 有引用原始缺失恢复。
- [ ] 链接 ops：resolve/reresolve/rebuild-keys 写端点+碰撞报告+重建结果查看；不混淆索引重建；不绕过治理。
- [ ] Offline 备份恢复：SQLite Online Backup API + PG custom dump/staging restore；附件/quarantine/import-staging 先合并并校验，DB 最后切换；journal/真实资源对账；旧 DB 保留；Windows 文件句柄/rename 故障注入。
- [ ] 迁移运维包装器门禁（Alembic 纯 Schema；备份→校验→确认→记录→才 downgrade）；**无新迁移**。
- [ ] Core 独立性守护扩展；A1 零新增必需依赖；真实测试（非假数据/非离线 SQL）；ruff+根级 pytest 通过。
- [ ] tag_change_log append-only+审计快照（schema 已实现，A1-04 服务层留痕验证）。

---

## 16. 任务依赖关系与实施顺序

### 16.1 A1-04 任务分解（建议编号 T4-01…T4-16）

| 任务 | 内容 | 依赖 | 方向 |
|---|---|---|---|
| T4-01 | 配置新增 + 存储根/依赖装配骨架 | — | B |
| T4-02 | backend V2 仓库实现（Attachment/Tag/TagChangeLog/ImportOrigin/GcTask） | T4-01 | A/B |
| T4-03 | db/storage_lock.py 双方言（SQLite 租约 + PG advisory） | T4-01 | B |
| T4-04 | Core markdown/service.py 导入导出编排 + ImportReport + 变化分类 | T4-02（端口） | A |
| T4-05 | C-01 持久化路径决策落地（extra_metadata/source_*/tags 映射） | D-02 审批 | A |
| T4-06 | services/markdown.py Vault 导入导出 + 每文档事务 + LinkImportRestorer | T4-04/T4-05 | A |
| T4-07 | services/attachments.py 上传/下载/删除/校验 | T4-02/T4-03 | B |
| T4-08 | GC worker（认领/状态机/持锁 quarantine/purge） | T4-03/T4-07 | B |
| T4-09 | 独立孤儿扫描 + DB↔物理一致性检查 | T4-08 | B |
| T4-10 | API：import_export/attachments/tags 路由 + DTO | T4-06/T4-07 | A/B |
| T4-11 | links.py 写端点（resolve/reresolve/rebuild-keys）+ 链接 ops DTO | A1-03 复用 | C |
| T4-12 | ops CLI（rebuild_link_keys/v2_downgrade） | T4-11/backup | C |
| T4-13 | services/backup.py 快照 + Manifest 两阶段 + 对账 | T4-01 | B |
| T4-14 | 备份恢复故障注入 + Windows 兼容验证 | T4-13 | B |
| T4-15 | D 方向：SQLite 并发三维评估 + 最小改动建议（如需） | T4-03/T4-08 | D |
| T4-16 | 全量回归（SQLite+PG+Core+ruff+前端）+ 守护扩展 + 验收报告 | 全部 | — |

### 16.2 依赖图

```
T4-01 ─┬─ T4-02 ─┬─ T4-04 ─┐
       │         │         ├─ T4-06 ─┐
       │         └─ T4-05 ─┘         │
       ├─ T4-03 ─┬─ T4-07 ─┬─ T4-08 ─┼─ T4-09 ─┐
       │         │         │         │         │
       │         └─────────┴─ T4-15  │         │
       └─ T4-13 ── T4-14             │         │
T4-11（复用 A1-03）── T4-12          │         │
                          T4-10 ◀────┘         │
                          T4-16 ◀──────────────┴──（全部）
```

### 16.3 建议连续实施顺序

1. **T4-01 配置骨架** → 2. **T4-02 V2 仓库** + **T4-03 storage_lock**（可并行）→ 3. **T4-05 持久化路径**（须 D-02 先批）→ 4. **T4-04 Core 编排** → 5. **T4-06 Vault 导入导出** → 6. **T4-07 附件上传** → 7. **T4-08 GC** → 8. **T4-09 孤儿扫描** → 9. **T4-10 API（A/B）** + **T4-11 链接 ops**（可并行）→ 10. **T4-13 备份** → 11. **T4-12 ops CLI** → 12. **T4-14 故障注入/Windows** + **T4-15 D 评估** → 13. **T4-16 全量回归+验收**。

### 16.4 可合并实施的工作

- T4-02 + T4-03（仓库 + 锁适配，同属 db 适配层，可一批）。
- T4-07 + T4-08 + T4-09（附件上传/GC/孤儿扫描强耦合，建议连续一批，共享 StorageKeyLock）。
- T4-10 + T4-11（API 层 additive，可一批，但链接 ops 须独立验收）。
- T4-13 + T4-14（备份 + 故障注入，须真实环境连续验证）。

### 16.5 须独立验收的高风险模块（不可合并掩盖）

| 模块 | 风险 | 独立验收理由 |
|---|---|---|
| **GC + quarantine + 孤儿扫描**（T4-08/09） | 数据丢失（误删仍被引用文件） | 须故障注入 + 双 Worker + 引用回升 + 崩溃恢复真实取证，独立验收 |
| **StorageKeyLock 双方言**（T4-03） | 并发竞争/TOCTOU | SQLite 租约 fencing/续租失败中止 + PG advisory 须分别真实并发测试 |
| **备份恢复 + Manifest 对账**（T4-13/14） | 数据丢失/不一致 | 中途 kill + 标记不一致 + Windows 占用须真实故障注入，独立验收 |
| **导入审核门禁 + K1 挂接**（T4-06） | 治理绕过/链接损坏 | active 202 不绕过 + 链接恢复绑定优先须独立验证 |
| **链接键重建写端点**（T4-11） | 并发/唯一约束 | 复用 apply_link_key_plan，须验证不绕过门禁 A/B/C |

### 16.6 预计涉及文件范围

**新增**（约 20+ 文件）：
- Core：`markdown/service.py`、`markdown/import_report.py`、（可选）`attachments/planning.py` + 对应测试。
- backend：`db/storage_lock.py`、`services/{attachments,markdown,backup,import_coordinator,import_review_hook,markdown_item_repository,repositories_v2}.py`、`ops/{rebuild_link_keys,v2_downgrade}.py`、`api/routes/{import_export,attachments,tags}.py` + 对应测试（双方言）。

**additive 修改**（最小化，须审批+回归）：
- `api/routes/links.py`（增写端点）、`api/schemas.py`（增 DTO）、`core/config.py`（增配置）、`dependencies.py`/`main.py`（装配）、（若 D-02 选扩展）`services/knowledge.py`。

**禁止修改**：A1-02/03 业务（codec/canonical/link_service/links.py）、review/__init__.py、迁移 0006、db/locking.py A1-03 逻辑、任何现有测试、MILESTONES.md、M0 初始提交。

---

## 17. 风险与未解决问题

- 完整风险登记见 `V2-A1-04-risk-register.md`（数据丢失/重复导入/附件孤儿/GC 误删/并发竞争/FS↔DB 不一致/权限路径安全/旧版兼容/API 治理绕过）。
- 全部未决决策见 `V2-A1-04-open-decisions.md`（含设计↔代码冲突 C-01…C-05 + 决策 D-01…D-12）。
- **本轮不替用户拍板**任何【待审批】项；**不宣称**任何【待验证】项已通过。

---

## 18. 停止点

本设计方案完成后**停止**，等待 ChatGPT 阶段级独立审查与用户批准。**不开始 A1-04 代码开发**，不进入 A1-05/A2，不修改 MILESTONES.md，不 commit/push。所有【提议】须审批后方可进入实施；所有【待验证】须开发后真实测试取证。

---

## 19. R1 权威修订：部署、幂等、审核批准与离线备份协议

> 本章优先级高于前文任何冲突描述。决策状态：**ChatGPT 架构裁决已提出，等待用户阶段级批准**。以下均为设计，不是实现事实。

### 19.1 部署拓扑：单活动 Backend 进程

- A1-04 只支持一个 ExplainLab Backend 活动进程、一个 worker、一个本地数据根。多实例/多主机/多 worker 写入不在本阶段支持范围。
- 新增 `app/db/process_lock.py`：Backend lifespan 启动时获取 OS 独占锁；Windows 用 `msvcrt.locking`，POSIX 用 `fcntl.flock`。锁文件默认 `backend/data/.explainlab.process.lock`，创建后**不删除**，只释放 OS 锁；文件句柄持有至进程退出。禁止 PID 文件作为互斥依据。**R1.1 强化（§20.4）**：唯一路径由 `resolve_process_lock_path()` = `BACKEND_DIR.resolve()/data/.explainlab.process.lock` 派生，Backend 与所有 Offline CLI 共用、**不依赖 cwd**；msvcrt/fcntl 对外统一排他 acquire/release 语义。
- Uvicorn `--reload` 由实际 worker 在 lifespan 获取锁，reloader supervisor 不持锁；必须测试 worker 重启时旧锁释放/新 worker 获取。生产运行强制 `workers=1`。第二个 Backend 启动失败并给出稳定错误 `BACKEND_ALREADY_RUNNING`。**R1.1 强化（§20.4）**：worker 交接允许**有界重试**（总上限 10s，初始 100ms，退避封顶 500ms），超时 fail-closed；不无限等待、不删锁文件、不以 PID 判陈旧、不提供无锁 fallback。
- 所有破坏性/维护 CLI（backup/restore/v2_downgrade/rebuild-link-keys/GC maintenance）必须获取同一把锁。Backend 运行时 CLI 失败；CLI 持锁时 Backend 启动失败。所有维护命令禁止绕过锁直接调用底层操作。
- 数据根必须位于本地文件系统；不承诺 SMB/NFS/云同步目录上的 OS 锁语义。此锁只约束同一部署根的 ExplainLab 进程，不提供跨主机数据库协调。外部程序直接写数据库/附件目录属于不支持操作。

### 19.2 来源幂等：稳定身份锁 + 源版本 hash

- 锁身份：优先 `(source_instance_id, source_document_id)`；source_instance_id 可空但必须按 null 明确编码。无来源身份但有目标 item_id 时锁目标 item；无身份的新文档锁 `content_hash`。锁键由稳定序列化后 SHA-256 派生。**禁止使用 source_payload_hash 作为有身份文档的锁身份**，否则同一文档内容变化时会得到不同锁。
- 内容版本：`source_payload_hash`。ImportOrigin 保留已成功应用的来源版本历史；`knowledge_item.source_payload_hash` 只表示当前 item 最近一次成功应用的来源版本。
- 单实例进程内 keyed lock 使用引用计数生命周期，避免锁字典无限增长。SQLite/PG 的 ImportOrigin 查询与写入仍在同一文档事务中；应用层锁是本部署模式的并发保证，不伪称 DB 唯一约束。无来源身份的内容查重也必须持 `anonymous-content` 锁后再查重。
- 锁前快照 S0、锁内重读 S1。S1 与 S0 不同：若 incoming hash 已应用/已 pending 则返回 skipped/reused pending；否则拒绝 `SOURCE_CHANGED_DURING_WAIT`，防止并发旧版本覆盖。多个 target item 对应同一来源身份时拒绝 `SOURCE_IDENTITY_AMBIGUOUS`。**R1.1（D15-3，§20.3）**：S0 为只读短会话、读后关闭；获锁后用新会话读 S1；S1 判定完成后才开写事务。
- **R1.1 来源 hash 权威读取（FID-2，§20.3）**：历史命中经 `ImportOriginRepository.find_by_source_payload_hash(source_instance_id, source_document_id, source_payload_hash)`；当前指针经 `MarkdownItemRepository.get_source_identity_snapshot(item_id)` 读 ORM 冗余列；不以 `MAX(imported_at)` 作唯一当前版本判据，不以 Core 实体携带 source_*。
- 不支持多实例并发导入；若未来要支持，必须单独审批迁移，为来源身份/版本引入 DB 唯一约束及冲突处理，不得仅删除进程锁或加 PG advisory lock 就宣称支持。

### 19.3 ReviewRequest 导入 envelope 与批准事务

- `ReviewRequest.payload` 是现有自由 JSON，不新增列、不改 Core ReviewService。导入 envelope 使用保留命名空间 `__a1_import`，带 `schema_version`，不得污染 Core 四字段更新逻辑。
- envelope 必须能重建完整的来源交换上下文，并携带 source identity/hash、canonicalization version、tags、extra_metadata、attachment staging manifest、frontmatter link hints、context_digest。Digest 仅用于完整性/一致性校验，不宣称防御有 DB 写权限的恶意篡改。
- `review_payload_hash` 仍只保护既有四字段，不能宣称覆盖 tags/extra_metadata/附件/来源身份。A1-04 另行校验 envelope 的 digest 和源 payload hash。
- Approve 路由增加 backend import hook：Core approve 后、首次 commit 前应用全部扩展上下文并恢复导入链接。导入 ReviewRequest 使用 LinkImportRestorer，普通 ReviewRequest 继续现有 K1 sync。所有 DB 写入同一事务；任何 hook 异常必须 rollback approve、item、tags、附件引用、ImportOrigin、links。索引仍在 commit 后单独同步。
- **R1.1（D15-2，§20.3）Approve 锁参与**：仅当 payload 含 `__a1_import` 时走导入分支；先独立只读短会话读 envelope identity 并**关闭**→获与 submit **相同**身份键锁→用**全新写 Session** 重读 ReviewRequest（确认仍 PENDING、envelope schema/digest 未变）并重读来源身份状态→在**同一事务**内执行 Core approve（仍只应用四字段）+ backend hook→提交后才释放锁；任一环节失败整事务 rollback、ReviewRequest 保持 PENDING。普通 ReviewRequest 保持现有 K1 路径。
- Reject 路由提交 reject 后清理 staging；清理失败只产生可回收 staging orphan，不产生 ImportOrigin。
- 同一来源身份的 pending：同 hash 复用既有 ReviewRequest；不同 hash 且旧 pending 未解决时拒绝新导入，不创建第二张 pending。A1-05 仍负责 proposal 防覆盖、withdraw、WITHDRAWN 等功能。

### 19.4 附件 staging 与文件系统一致性

- Draft 导入：物理内容寻址文件先写 temp、hash 校验、原子 rename；随后同文档 DB 事务写 Attachment 引用。DB 失败形成可回收孤儿。
- Active 导入：附件只写 `import-staging/<review_id>/<operation_id>/`，ReviewRequest pending 时不创建正式 Attachment 引用；approve 时提升/复用正式 blob 并写引用；reject 后清 staging。
- Blob 不可变，storage_key=SHA-256；GC 只删除隔离区内容，不在释放锁后删除原始路径。**R1.1（§20.6）Staging 清理器**：按 `review_id` + envelope manifest 引用检查，仍被 PENDING ReviewRequest 引用的目录**绝不清理**；无 pending 引用且超宽限期的先复核后 quarantine/purge；**正式 attachments 根绝不被 sweep**。

### 19.5 StorageKeyLock 与并发模型

- 进程锁解决跨进程单实例；同进程同 key 的上传/GC/孤儿扫描使用同一个 keyed threading lock；DB `storage_lock` lease/token 用于崩溃恢复与 fencing。
- SQLite：短事务条件写入/接管 storage_lock，commit 后执行物理 IO；每个不可逆步骤前校验 owner+token。租约不是 OS 互斥锁，正确性仍依赖单实例进程锁 + 同进程 keyed lock；不宣称在外部写者/多实例下严格互斥。
- PostgreSQL：使用会话级 advisory lock；锁必须绑定持有它的物理连接，finally 解锁/关闭连接，进程崩溃由服务端释放。64-bit key 从 SHA-256 前 8 字节派生；碰撞只会额外串行，不可用于跳过精确 storage_key 引用复核。
- 默认参数建议：lease TTL 60s、heartbeat 15s、获取锁等待 10s、GC max_attempts 8、退避 60s 起步上限 6h、quarantine/orphan grace 24h、orphan scan 300s。均可配置；实现前以配置测试确认 TTL 大于最坏物理临界区并有续租失败中止。

### 19.6 Offline Backup/Restore（无在线 quiesce）

**明确选择 Offline**：备份/恢复/降级只能由维护 CLI 在 Backend 已停止时执行。Backend 进程锁释放后，CLI 获取同一 OS 锁；若锁获取失败，命令立即退出。无需在线请求排空/维护模式/多实例协调器。PostgreSQL 服务可继续运行，但只允许维护 CLI 连接；外部写者必须停用。

备份包结构建议：

```text
backup-<timestamp>-<operation_id>/
  manifest.json
  database.sqlite3                 # SQLite
  database.dump                    # PostgreSQL custom format
  attachments/                     # active blobs + quarantine
  import-staging/                  # pending review 附件 staging
  checksums.sha256
  COMPLETE
```

- SQLite：用 `sqlite3.Connection.backup()` 生成快照，禁止裸拷 db/wal/shm。PG：`pg_dump --format=custom`；记录 server/client major version，版本不兼容则拒绝。
- 因 Backend 停止，DB 与附件目录对应用写入者形成同一离线维护窗口。备份复制 active blobs、quarantine、pending import-staging；排除未完成 temp 文件并在 Manifest 记数。Manifest 包含 operation_id、dialect、schema head(0006)、应用/codec/canonicalization 版本、DB hash/size、附件与 staging 文件逐项 hash、生成时间、source_instance_id。
- Manifest/journal 落 `backend/data/ops/backup/` 或备份包内文件；使用 temp→fsync→os.replace→目录 fsync。不得新增 DB 表/列。
- Restore 先校验整个包和所有 hash，再准备 staging DB。**先把备份中的附件/quarantine/staging 文件按相对路径合并到当前存储（同路径内容不一致即中止），再切换 DB**。内容寻址 blob 不可变；恢复不删除当前额外 blob，额外 blob 之后作为孤儿按宽限期清理。这样保证 DB 切换后其引用文件已存在。
- SQLite：staging DB 校验通过后关闭全部句柄，旧 DB 文件保留为 previous generation，`os.replace` 原子替换 live DB；切换后只读检查 schema/head 与业务不变量。
- PostgreSQL：restore 到独立 staging database，校验成功后**按 R1.1 BAK-1 清场（见 §20.5）**：CLI 连维护库（如 `postgres`）而非目标库→预检权限→对 target `ALTER DATABASE ... WITH ALLOW_CONNECTIONS false`→`pg_terminate_backend` 非维护会话→轮询 `pg_stat_activity` 目标库连接清零→再 rename target→previous、staging→target；清场失败恢复 target `ALLOW_CONNECTIONS true`、保持名称/OID/数据不变并中止；旧库保留，不立即 DROP。`pg_terminate_backend` 能否清理特定 PG 版本/权限的后台连接须真实 PG 16.8 验收，不预先宣称必然成功。
- 恢复 journal 记录准备、附件合并、DB 切换、验证、完成阶段；崩溃恢复必须同时检查 journal 与真实 DB（SQLite hash / PG database OID）及附件清单，不得只信 phase/marker。附件先合并、DB 最后切换，故未切换 DB 时多余 blob 只形成安全孤儿。
- 默认备份位置 `BACKEND_DIR/backups`，保留最近 5 份**已完成且校验通过**的备份；只有新备份 COMPLETE+hash 校验通过后才清理超额旧备份。生产建议另复制到独立物理盘。
- v2_downgrade 只允许离线 CLI：获取进程锁→创建并验证备份→用户显式确认将删除 V2 数据→写文件操作日志→执行 Alembic downgrade→验证 V1 核心数据。任何一步失败不继续。

### 19.7 R1 模块与文件边界

新增：`app/db/process_lock.py`、`app/db/storage_lock.py`、`app/services/import_coordinator.py`、`app/services/import_review_hook.py`、`app/services/markdown_item_repository.py`、`app/services/backup.py`、`app/ops/backup.py`、`app/ops/restore.py`、`app/ops/v2_downgrade.py`、`app/ops/recover_backup.py` 及对应测试。附件/GC 仓库与服务按原计划新增。

Additive 修改：`main.py` lifespan 获取进程锁；`routes/governance.py` 仅增加识别 `__a1_import` 的批准/拒绝分支，普通 K1 行为不变；`routes/import_export.py` 调用 ImportCoordinator；`config.py` 增配置。

**R1.1 追加边界**：`app/db/process_lock.py` 内提供 `resolve_process_lock_path()`（D17-2）与 msvcrt/fcntl 统一抽象（D17-3）；新增数据文件 `BACKEND_DIR/data/source-instance-id`（D-13，非迁移、非表）；instance-id 读取/生成/rotate 归 `app/services/`（rotate 仅 `app/ops/` CLI 调用），`ImportCoordinator` 负责 keyed lock 与线程池边界（§19.10）。

禁止：改 0006/新增迁移；改 Core ReviewService；改 A1-02 codec/canonical/hash；改 A1-03 LinkKeyRebuild/apply_link_key_plan/locking.py；扩展 V1 KnowledgeRepository 使其写 extra_metadata；在线备份 API；多实例支持；A1-05 防覆盖/撤回。

### 19.8 R1 阶段级冻结门禁

- 四份文档编号、状态、默认值、流程和测试交叉引用一致。
- ImportOrigin 不存在 DB 唯一约束这一事实在所有章节表述一致；任何“唯一约束保证幂等”表述必须删除。
- 单实例边界、OS 进程锁、source identity keyed lock、pending envelope、approve hook、staging、offline backup/restore 全部有验收用例。
- 原 A1-02/03 套件与所有既有测试不得删减/弱化；不新增迁移、不新增依赖。
- 当前仍未验证：Windows msvcrt 锁的生命周期/--reload worker 重启、真实 PG staging restore/rename、SQLite 文件替换崩溃恢复、附件合并冲突、approve hook 故障回滚。必须开发阶段真实取证。


### 19.9 推荐实施批次（避免碎片化开发）

A1-04 不按“一个文件/一个小函数”拆任务。按能形成完整业务闭环的工作流组织为四个开发批次；每批内部允许连续完成多个模块，但批次结束必须独立验收。

| 批次 | 一次连续交付范围 | 批次出口/独立验收 |
|---|---|---|
| **Batch A：导入/导出/来源/身份锁/审核/链接恢复闭环（不含附件）** | 进程锁基础、MarkdownItemRepository、Tag/ImportOrigin 仓库、来源身份 keyed lock、S0/S1 重读、ImportReport、非附件 Draft 导入导出、Active Review envelope（非附件上下文）、approve/reject backend hook（非附件部分）、LinkImportRestorer、批量部分失败、索引后置同步；**遇含附件请求显式拒绝/标记 unsupported，绝不静默丢弃**；**exporter 传输元数据与 Hash 解耦、本地原生文档身份初始化（MATERIALIZE Journal 显式标记；R1.3）** | Batch A 自身验收子集（IMP-01…18、IMP-20；R1-IMP 非附件项；R1.1-IMP-25…37/39/40；**R1.3-HASH-01…04、R1.3-ID-01…05**）；SQLite/真实 PG；证明 V1 PATCH 不清 metadata；A1-02/03 不回归；**不得宣称附件导入完成** |
| **Batch B：附件/锁/GC/附件审核闭环** | 附件上传/下载/删除、active review staging、approve 附件整合（与 item/tags/origin/links 同一事务闭环）、StorageKeyLock 双方言、GC 状态机、quarantine/purge、staging orphan 与独立 orphan scan、一致性报告 | ATT/LCK/GC/ORP 全部 + R1-LOCK-07/08；**IMP-19、附件相关 R1-IMP-05/07/08/09/10/11、R1.1-IMP-38 附件整合、R1.1-IMP-41/42**；真实 FS、双 Worker、kill/续租失败、Windows |
| **Batch C：Offline Backup/Restore/降级闭环** | 维护 CLI、备份包/Manifest/checksum、SQLite 快照、PG custom dump、附件/staging 合并、staging restore、DB 最后切换、journal/recovery、v2_downgrade 门禁、保留策略 | BAK 全部 + R1-BAK 全部 + R1.1-BAK-15…19；真实 SQLite/PG、Windows 文件占用、rename 中断、恢复崩溃对账 |
| **Batch D：用户入口/运维入口/网络边界/整体验收** | Tags API、附件/import-export API 收尾、显式链接 resolve/reresolve、rebuild-keys CLI、权限/错误码/文档、**loopback 网络边界、Host/Origin/JSON 校验与启动校验（R1.3 D24）**、根级回归、干净安装验证、阶段验收报告 | LNK/OPS/SQL/GRD 全部 + **R1.2-NET-01…08 + R1.3-NET-01…06**；不得削弱 A1-02/03 守护；所有未通过项明确列出 |

**R1.1 验收归属（经 R1.2 D19 修订）**：Batch A 追加 `R1.1-IMP-25…37/39/40`、`R1.1-SQL-10`、`R1.1-LNK-14`、`R1.1-LOCK-09…13`（读契约/instance-id/身份锁/同步执行模型/Coordinator/进程锁），以及 `R1.2-ID-01…08`、`R1.2-ASYNC-01…08`；Batch B 追加 `R1.1-IMP-38` 的**附件整合部分**、`R1.1-IMP-41/42`（staging sweep），以及 R1-IMP-05/07/08/09/10/11 的附件/staging 部分；Batch C 追加 `R1.1-BAK-15…19`、`R1.1-OPS-06`（备份含 ID/恢复额外 blob/PG 清场/clone rotate）；Batch D 追加 `R1.2-NET-01…08` 并做 acceptance-matrix §F/§G 全量回归汇总。`R1.2-BAT-01…06` 为**跨批门禁**，每批出口均须核对。R1.1/R1.2 项未通过，对应批次不得出口。
**R1.3 验收归属**：Batch A 追加 `R1.3-HASH-01…04`、`R1.3-ID-01…05`（exporter/Hash 解耦、本地身份初始化）；Batch D 追加 `R1.3-NET-01…06`（精确绑定、Host/Origin/JSON、重绑定防护）；**D24 网络项不阻塞 Batch A 非附件开发**。详见 §22.5 与 acceptance-matrix §H。

**批次原则**：Batch A/B/C 可各自连续开发，不要求每完成一个小文件就停下来审计；但 Batch A 的 Active approve hook、Batch B 的 GC/quarantine、Batch C 的 restore switch 是不可拆散的高风险验收单元。任何批次未通过其出口验收，不进入下一批。

---

### 19.10 Coordinator、异步与线程边界（R1.1；机制由 R1.2 D20 取代，属性保留）

> **R1.2 取代说明（D20，§21.3）**：下述「async keyed lock 负责等待、同步 DB/FS 在线程池执行」的**机制**已由 R1.2 同步事务执行模型取代——写入口改为 FastAPI 同步 `def` 路由（运行于线程池），`ImportCoordinator` 只使用**同步身份锁**，Session 在**实际执行线程内**创建/使用/关闭；**禁止 async keyed lock + `threading.Lock` 双协调架构**。本条的**属性要求仍然有效**：不得阻塞 event loop、Session 不得跨线程、取消时不得提前释放锁。验收以 `R1.2-ASYNC-01…08` 为准，`R1.1-SQL-10` 保留为属性级回归项。

- Backend lifespan 创建**唯一** `ImportCoordinator`，存于 `app.state`，并注入单篇导入、批量导入、治理 approve **三条**路径；禁止各 router 自行 new，保证同一身份锁、同一 registry。
- keyed-lock registry **引用计数**：排队前计数、退出释放、最后 holder/waiter 离开后删除条目；同身份串行、不同身份并行。
- ~~不得在 asyncio event loop 直接等待阻塞式 `threading.Lock`。推荐 async keyed lock 负责等待，同步 SQLAlchemy Session 与文件 IO 在线程池执行~~（**R1.2 D20 取代**：改为同步 `def` 路由 + 同步身份锁 + 线程内 Session；不得双架构）。属性要求不变：Session 必须在线程内创建/使用/关闭，禁止跨线程传递 request-scoped Session；event loop 不得被锁等待/同步 DB/FS 阻塞。
- 请求取消时，事务 rollback/commit 与资源清理完成前不得释放身份锁。

---

## 20. R1.1 权威修订（合并 R1.1 增补，冲突以本章为准）

> **来源**：`docs/plans/A1-04/R1.1-amendment/ExplainLab-V2-A1-04-Architecture-R1.1-amendment.zip`（README + 四份 R1.1 增补，SHA256SUMS 已逐文件核验）。
> **状态**：ChatGPT R1.1 架构修订增量，**待用户阶段级批准 + ChatGPT 阶段级独立审计**。产品约束：**Offline backup / Single deployment / Strict migration**。本章为**设计**，非实现/测试通过证明；新增验收全部【待验证】。
> **合并原则**：R1 未冲突设计、编号、历史审计记录全部保留；本章只覆盖 R1.1 明确修订条目；与本章冲突的旧表述以本章为准（已在 §3.3/§5.1/§12/§19.1–§19.4/§19.6 就地加注指向）。

### 20.1 D16-1：V1/V2 读取契约（取代 §3.3 旧 additive 读字段表述）

【设计正确】采用 **V2-only read contract**：

- **不**向 V1 `KnowledgeOut` 增加 tags/extra_metadata 读字段；**不**修改 V1 `SQLAlchemyKnowledgeRepository._to_entity()`；**不**改变现有 V1 GET/list/search 响应结构。§3.3 原「KnowledgeOut 增 tags/extra_metadata 读字段」一句**作废**，以本条为准。
- `MarkdownItemRepository` 是 A1-04 Markdown 文档唯一应用层读写入口，负责 title/content/status/space_id/extra_metadata/source_* 映射；`TagRepository` 负责 tags/item_tag；V2 聚合读在同一一致读取边界取 tags。
- V2 Markdown export、Markdown GET、V2 文档详情/导入报告中需要 V2 字段的路径，统一经 `MarkdownItemRepository` + `TagRepository`；V1 GET/list/search DTO 不返回 V2 扩展字段，不得描述为 V1 GET 可见。
- V1 PATCH 不触碰 V2 列（已核实事实）；V2 导入后 V2 export 必须读回 tags/extra_metadata/source metadata。
- 未来若让 V1 GET 暴露 V2 字段，另立兼容变更、独立审批并跑 V1 全量回归，不属 A1-04。

### 20.2 D-13 / G-4：source-instance-id 生命周期

路径固定 `BACKEND_DIR.resolve()/data/source-instance-id`；内容为规范 UUID 字符串（小写、连字符、单行），代表逻辑实例身份（非进程 ID/机器 ID；R1.2 D18 中作为导出时的 `exporter_instance_id`，见 §21.1）。

- **缺失**：仅在 Backend 已获 OS 单实例锁后生成；同目录临时文件写入、flush+fsync 后以**不覆盖**方式原子创建；若目标已被竞争者创建则重读校验、不覆盖。
- **存在但格式无效 / 权限不足 / 无法持久化**：启动 fail-closed，稳定错误 `SOURCE_INSTANCE_ID_INVALID` / `SOURCE_INSTANCE_ID_UNAVAILABLE`；**禁止静默重新生成**。
- 普通重启 / 崩溃恢复保持原 ID。
- Offline backup 将 ID 纳入 Manifest 与 checksum；同一逻辑实例 restore 必须保留。
- 恢复到独立克隆环境后、对外服务前必须显式 rotate；rotate 仅由 Offline CLI 执行（Backend 已停止且持同一 OS 锁），要求显式确认，记录旧/新 ID、时间、operation_id。
- 文件意外丢失不得自动生成新 ID；从可信备份恢复或人工受控 reinitialize。
- 所有单篇与 ZIP 导出携带 source_instance_id + source_document_id；source_instance_id **不是认证凭据**。
- 缺失 ID 的旧包视为 legacy/unknown source；不得推断为本实例或静默覆盖。
- **R1.2 D18 术语校正（§21.1）**：本文件 `data/source-instance-id` 保存的是**本部署实例（导出者）身份**，导出时写入 frontmatter/manifest 的字段名为 `exporter_instance_id`；文档自身的 `source_instance_id` 表示**原来源实例**，二者不可互换。导入/修改/再导出**不得覆盖**原来源身份；clone rotate 只更换本实例导出身份，**不得批量改写继承文档的来源身份**；同来源不同版本进入既有冲突/审核机制。

### 20.3 D-15：身份键锁、S0/S1 与 Approve 锁参与（含 D15-2、D15-3、FID-2）

- **锁键**：优先 `(source_instance_id, source_document_id)`；无身份有目标则 `target-item:<item_id>`；无身份无目标则 `anonymous-content:<document_content_hash>`；source_payload_hash 是**版本**不是锁键。
- **Submit 时序（D15-3）**：① 只读短会话 S0（当前 item 来源指针、ImportOrigin 历史命中、pending envelope 摘要）；② **关闭 S0 会话**，绝不持其事务等待锁；③ 获身份键锁；④ 全新只读会话 S1；⑤ S1 判定（已应用→skipped / 同身份同 hash pending→复用 / 同身份不同 hash pending→`SOURCE_HAS_PENDING_IMPORT` / 其他变化→`SOURCE_CHANGED_DURING_WAIT` 零写入）；⑥ 判定完成才开文档写事务，提交后释放锁；⑦ 批量每文档独立事务。
- **Approve 时序（D15-2）**：仅 `__a1_import` 走导入分支；先独立只读短会话读 envelope identity 并关闭→获**同一**身份键锁→全新写 Session 重读 ReviewRequest（确认 PENDING、schema/digest 未变）并重读来源状态→同一事务 Core approve（四字段）+ backend hook→提交后释放锁；任一环节失败整事务 rollback、ReviewRequest 保持 PENDING。普通 ReviewRequest 保持现有 K1 路径。
- `review_payload_hash` 仍只覆盖 Core 四字段；不得宣称其保护 envelope；envelope digest 仅一致性校验，**非授权/签名边界**。
- **FID-2 来源 hash 权威读取**：历史命中经 `ImportOriginRepository.find_by_source_payload_hash(...)`；当前指针经 `MarkdownItemRepository.get_source_identity_snapshot(item_id)` 读 ORM 冗余列；不以 `MAX(imported_at)` 作唯一当前版本判据，不以 Core 实体携带 source_*；多 item_id 对应同身份→`SOURCE_IDENTITY_AMBIGUOUS`，不假设 DB 唯一约束。

### 20.4 D-17：OS 单实例锁、reload 与跨平台抽象（含 D17-1、D17-2、D17-3）

- 唯一锁路径 `resolve_process_lock_path()` = `BACKEND_DIR.resolve()/data/.explainlab.process.lock`；Backend 与所有 Offline CLI 共用，**不依赖 cwd**（D17-2）。
- Windows `msvcrt.locking` 与 POSIX `fcntl.flock(LOCK_EX|LOCK_NB)` 对外统一排他 acquire/release 语义；句柄持有至释放；锁文件**永不删除**（D17-3）。
- Uvicorn reload supervisor **不持锁**，实际 worker 在 lifespan 获取。
- worker 交接允许**有界重试**：总上限 10 秒，初始 100ms，退避封顶 500ms；超时返回 `BACKEND_ALREADY_RUNNING`，不绕过锁（D17-1）。不无限等待、不删锁文件、不以 PID 判陈旧、不提供无锁 fallback。
- 任一时刻最多一个 worker 持锁；生产强制 `workers=1`；`workers>1` 启动前拒绝。
- Backend shutdown 先停止新请求并等待在途事务结束再释放锁；crash 依赖 OS 自动释放。

### 20.5 BAK-1：PostgreSQL rename 前连接清场（补充 §19.6）

1. Offline CLI 连接**维护库**（如 `postgres`），不连待 rename 目标库。
2. 预检 owner/CREATEDB/terminate backend 权限；不足则在改目标库前中止。
3. staging DB 恢复并完成 schema/checksum/业务不变量验证。
4. 对 target `ALTER DATABASE <target> WITH ALLOW_CONNECTIONS false` 阻止新连接。
5. 对 `pg_stat_activity` 中目标库其他会话执行 `pg_terminate_backend(pid)`，不终止当前维护库会话。
6. 轮询 `pg_stat_activity`，按 datname 确认目标库连接/后台类型清零；权限不足或后台/autovacuum 残留无法清零则中止。
7. 清场失败恢复 target `ALLOW_CONNECTIONS true`，保持名称/OID/数据不变；staging 保留诊断，不 DROP 旧库。
8. 清场成功后按 journal 执行 target→previous、staging→target 两步 rename，逐步记录 journal 与 OID。
9. 新 target 开放连接前验证 OID==staging OID、schema head、数据校验；previous 保留且默认禁连。
10. 崩溃后 recover CLI 连维护库，以真实 database name + OID + journal 对账；不能唯一判定则 fail-closed + needs_manual，不删任一数据库。

> `pg_terminate_backend` 能否清理特定 PG 版本/权限的全部后台连接，须**真实 PG 16.8** 验收；本设计不预先宣称必然成功。

### 20.6 附件 staging sweep 安全（补充 §19.4）

- sweep 只清理**无 PENDING ReviewRequest 引用**且**超过宽限期**的 `import-staging/<review_id>/<operation_id>/`；引用检查按 review_id + envelope manifest 文件清单。
- 仍有 pending 引用的目录绝不清理；复核后先 quarantine 再 purge；**正式 attachments 根绝不被 sweep**。
- restore 只合并不覆盖/删除当前 blob；当前环境额外 blob 保留为安全孤儿，过 grace 后由独立 GC 清理。

### 20.7 不变边界与产品约束

- **Offline backup / Single deployment / Strict migration** 三约束不变：备份/恢复/降级仅 Offline CLI（同 OS 锁、Backend 停止）；单 Backend/单 worker/单本地数据根；**不新增 migration/table/column/index**，不改冻结 Core 端口/A1-02 Hash/A1-03 链接规则，不改 V1 `KnowledgeRepository`/`KnowledgeOut`/GET，不引入依赖，不改 `MILESTONES.md`。
- BAK-1 的 `ALTER DATABASE ALLOW_CONNECTIONS` 属**运维运行时设置**（失败即恢复），非 schema 迁移，符合 Strict。
- 不支持多 Backend、多 worker、多主机、SMB/NFS/云同步目录并发写；外部直写 DB/附件目录为不支持操作。
- **R1.2 D21 / R1.3 D24 网络边界**：HTTP 默认监听 `127.0.0.1`，绑定**仅允许精确 IP** `127.0.0.1`/`::1`（`localhost` 不得作为绑定配置）；未启用认证时**拒绝非 loopback 监听配置并 fail-closed**；CORS/任意代理转发头**不是认证**；修改请求须过 **Host + 同源 Origin + JSON Content-Type** 校验，DNS Rebinding 伪造 Host 拒绝；反向代理/隧道/端口转发是额外暴露面，loopback 监听本身不解决其安全问题（§21.4、§22.3）。
- **R1.2 D19 批次隔离**：Batch A 不含附件完整导入/导出，含附件请求显式拒绝/标记 unsupported；附件 + Active approve 全事务闭环归 Batch B；四批各自独立出口，不得互相宣称完成（§21.2）。
- A1-05 proposal 防覆盖 / withdraw / WITHDRAWN 仍延期。

### 20.8 R1.1 新增验收编号映射（全部【待验证】，详见 acceptance-matrix §F）

| 主题 | 新增验收编号 |
|---|---|
| V1/V2 读取契约（D16-1） | R1.1-IMP-25…27 |
| source-instance-id 生命周期（D-13/G-4） | R1.1-IMP-28…31、R1.1-BAK-15、R1.1-OPS-06 |
| 身份键锁/S0-S1/approve（D15-2/3、FID-2） | R1.1-IMP-32…39、R1.1-SQL-10 |
| Coordinator 单例与普通 K1 回归 | R1.1-IMP-40、R1.1-LNK-14 |
| staging sweep / restore 额外 blob | R1.1-IMP-41/42、R1.1-BAK-16 |
| OS 锁/reload/跨平台（D17-1/2/3） | R1.1-LOCK-09…13 |
| PG 清场（BAK-1） | R1.1-BAK-17…19 |

> 编号沿用 R1.1 增补原文；R1 的 IMP-21…24 与 BAK-13/14 未被占用（保留空号，不重编号）。

### 20.9 R1.1 阶段级冻结门禁（在 §19.8 基础上追加）

- 四份主文档已合并 R1.1；D16-1 全文一致为 V2-only（无任何「KnowledgeOut 增 V2 读字段」残留）。
- §3.3 冲突句已就地修正；D-13 旧 A/B 选项已在 open-decisions §J 标注被 R1.1 生命周期取代。
- 所有 R1.1 新增验收入 acceptance-matrix §F 并标【待验证】；风险入 risk-register §12；决策入 open-decisions §J。
- 编号、术语、交叉引用一致（本文件 §20.8 ↔ acceptance-matrix §F ↔ risk-register §12 ↔ open-decisions §J）。
- **Offline/Single/Strict 三约束无冲突**（§20.7）。
- **R1.2 合并门禁（§21.7）**：D18–D21 已合并；§19.9 批次、§19.10 执行模型、§20.2 身份术语已就地校正；R1.2 新增验收入 acceptance-matrix §G、风险入 risk-register §13、决策入 open-decisions §K，全部【待验证】。
- **R1.3 合并门禁（§22.6）**：D22–D24 已合并；§21.1/§21.4/§21.5 与 §12 已就地校正；R1.3 新增验收入 acceptance-matrix §H、风险入 risk-register §14、决策入 open-decisions §L，全部【待验证】；R1.2 §K.2 九项已关闭。
- 仍未验证（须开发阶段真实取证，不得预先宣称）：Windows msvcrt 生命周期/`--reload` 交接窗口、真实 PG staging restore/rename+清场、SQLite 文件替换崩溃、附件合并冲突、approve hook 故障回滚、instance-id 生命周期。

---

## 21. R1.2 权威修订（合并 D18–D21，冲突以本章为准）

> **来源**：ChatGPT R1.2 架构决策 D18（文档身份模型）、D19（批次依赖调整）、D20（同步事务执行模型）、D21（HTTP 网络边界）。本任务仅将决策**合并进四份主文档**，不是重新设计，也不是代码开发。
> **状态**：**R1.2 架构修订稿，待用户阶段级批准 + ChatGPT 独立审计**。本章为**设计**，非实现或测试通过证明；所有 R1.2 新增验收均【待验证】。产品约束仍为 **Offline backup / Single deployment / Strict migration**。
> **合并原则**：R1/R1.1 未冲突设计、编号与历史审计记录全部保留；与本章冲突的旧表述以本章为准，并已在 §19.9（批次）、§19.10（执行模型）、§20.2（实例身份术语）、§12（配置）就地加注。**不得据此启动 Batch A**。
> **本轮禁改**：不写业务代码/测试；不新增迁移/表/列/索引；不加依赖；不改 Core ReviewService、A1-02 Hash/Codec、A1-03 链接键重建、V1 API、`MILESTONES.md`；不提交/推送。

### 21.1 D18：文档身份模型（source / document / exporter 三元分离）

| 字段 | 语义 | 来源 | 持久化位置 | 是否可被导入/再导出覆盖 |
|---|---|---|---|---|
| `source_instance_id` | 文档**原始来源实例**身份 | 首次导出方实例 ID（来自其 `data/source-instance-id`） | Markdown frontmatter + ZIP manifest；导入后作为文档来源身份保存在既有 `ImportOrigin`/`item.source_instance_id` 语义中 | **否**（导入/修改/再导出必须原样保留） |
| `source_document_id` | **稳定来源文档**身份 | 来源系统文档 ID（缺失则按 legacy 规则处理，不伪造） | 同上 | **否** |
| `exporter_instance_id` | **本次导出**执行实例身份 | 当前部署实例 `data/source-instance-id` | **仅** frontmatter + ZIP manifest；**不新增 DB 字段/列** | 每次导出按当前实例重写（只影响导出元数据；**不参与任何文档 Hash**，见 §22.1） |

- **文档身份**定义为 `DocumentIdentity = (source_instance_id, source_document_id)`；来源幂等锁键、`SOURCE_CHANGED_DURING_WAIT`、`SOURCE_IDENTITY_AMBIGUOUS`、pending 复用/拒绝等规则继续以该 tuple 为准（§19.2/§20.3）。
- **导入/修改/再导出**：`MarkdownItemRepository` 与导入服务只读写文档来源身份；导出时把当前实例写入 `exporter_instance_id`，**绝不**把 `exporter_instance_id` 回写为文档的 `source_instance_id`，也**绝不**把 `exporter_instance_id` 落库为列。
- **克隆实例**：`rotate-instance-id` 只更换本实例对外导出身份（新实例后续导出的 `exporter_instance_id` 变化）；**不得批量改写已继承文档的 `source_instance_id/source_document_id`**。若业务上需要把继承文档改为“本实例原生文档”，属独立的数据采纳（adoption）操作，须显式确认与独立审批，**A1-04 不自动执行**。
- **同来源不同版本**：同一 `DocumentIdentity` 下 `source_payload_hash` 不同，仍进入既有变化分类/审核/`SOURCE_CHANGED_DURING_WAIT`/pending 规则；**不因 exporter 不同而分裂为两个身份**，也不因 exporter 相同而跳过版本判断。
- **legacy/未知来源兼容规则（D23 细化见 §22.2；不伪造/不认领为强制）**：
  - `source_instance_id` 或 `source_document_id` 缺失/非法 → 视为 **legacy/unknown source**；**不得编造 UUID**、不得推断为本实例、不得静默覆盖既有条目。
  - **无 `ImportOrigin` 但 `source_instance_id` 非空** → 同属 **legacy/unknown / incomplete**，不认领为本地原生，不自动补写 `source_document_id`、不覆盖既有实例 ID、不自动 Adoption；报告如实标记（§22.2 状态 4）。
  - 走无身份分支：`content_hash` 查重 → `duplicates` 提示；跨实例/未知来源默认 **Draft** 并记录 `status_changes`；显式 `target_id` 时才允许绑定，且仍须内容 hash 复核。
  - 旧包仅有 `source_instance_id` 而无 `exporter_instance_id`：`exporter_instance_id` 记为 unknown（不推断）；来源身份按旧字段解析。
  - 兼容规则产生的跳过/降级/待确认必须在 `ImportReport` 中如实标记，不得静默。
- **无迁移**：本决策不新增 `exporter_instance_id` 列、不新增表/索引；仅扩展 frontmatter/manifest 字段与导出/导入映射（§21.5）。
- **R1.3 D22 就地修正**：`exporter_instance_id` 是**纯传输元数据**，不属于文档内容，**不参与** `document_content_hash`、`document_payload_hash`、`source_payload_hash`、`review_payload_hash`；frontmatter 专用键为 `__explainlab_exporter_instance_id`（见 §22.1）。上表“持久化位置”仅指引出的 frontmatter/manifest 与既有文档来源字段，**不表示 exporter 可写入数据库**。

### 21.2 D19：批次依赖调整（A/B/C/D 独立闭环）

> 本节**取代 §19.9 原批次表**中与附件相关的范围与验收归属；§19.9 已就地加注。四批必须各自独立验收，**不得以其他批次通过代替本批出口**。

| 批次 | 范围 | 明确边界 | 独立出口 |
|---|---|---|---|
| **Batch A** | 导入/导出、来源持久化、身份锁、审核核心、链接恢复（**非附件**） | **不得宣称完整附件导入/导出**。请求含附件清单/附件内容时：**显式拒绝或标记 unsupported**（固定稳定码 `ATTACHMENT_IMPORT_UNSUPPORTED` / 导出 `ATTACHMENT_EXPORT_UNSUPPORTED`，open-decisions §L.2），**零附件写入、不静默丢弃**；`ImportReport` 逐项标 unsupported | IMP-01…18、IMP-20；R1-IMP 非附件项；R1.1-IMP-25…37/39/40；R1.2-ID、R1.2-ASYNC；**R1.3-HASH、R1.3-ID（§22）**；A1-02/03 不回归 |
| **Batch B** | 附件上传/下载、staging、**approve 附件整合**、StorageKeyLock、GC、quarantine、孤儿扫描 | 完成**附件 + Active approve 的完整事务闭环**：附件引用、item、tags、origin、links 同一事务提交/回滚；approve 前不得留下正式引用悬空 | ATT/LCK/GC/ORP 全部；IMP-19；R1-IMP 附件/staging 部分；R1.1-IMP-38 附件整合、41/42 |
| **Batch C** | Offline Backup/Restore、Manifest、checksum、DB 切换、崩溃恢复 | 仍为 Offline CLI + 同一 OS 锁；附件先合并、DB 最后切换；不新增迁移 | BAK + R1-BAK + R1.1-BAK-15…19 |
| **Batch D** | 用户 API、运维 CLI、**网络边界**、全量回归与交付 | 网络边界按 D21 + **D24**；无认证不得对外；不得削弱守护 | LNK/OPS/SQL/GRD + R1.2-NET；**R1.3-NET（§22）** |

- **Batch A 的附件拒绝语义（R1.3 最终裁决，open-decisions §L.2）**：HTTP 返回固定稳定错误码 `ATTACHMENT_IMPORT_UNSUPPORTED` / `ATTACHMENT_EXPORT_UNSUPPORTED`（不泄漏内部细节），响应/`ImportReport` 明确标 `unsupported` 与原因；**不得部分导入后静默忽略附件**。批量导入中单篇含附件：该篇 `errors/unsupported`，其余篇按既有“每文档独立事务、部分失败继续”处理。
- **Batch B 前不得批准含附件 envelope**：Batch A 的 Active approve hook 仅处理非附件上下文；若发现 `__a1_import` envelope 含附件 staging manifest，在 B 未交付前应拒绝/挂起并给出固定稳定码 `ATTACHMENT_REVIEW_UNSUPPORTED`（open-decisions §L.2），**不得丢弃附件后批准**。
- **历史状态说明**：R1.2 §K.2 中的附件码名称仅为当时历史快照；上述三个附件稳定码已由 **open-decisions §L.2** 固定，本节与验收一律按固定值执行，不再保留未决语义。
- **批次依赖声明必须诚实**：文档、验收报告、提交说明不得把 B/C/D 的范围记入 A；`R1.2-BAT-01…06` 为跨批门禁（acceptance-matrix §G.2）。

### 21.3 D20：同步事务执行模型（取代 R1.1 §19.10 异步机制）

> **裁决**：导入、批量导入及相关 approve 写入口采用**同步执行模型**。R1.1 §19.10 推荐“async keyed lock + 线程池同步 DB/FS”的**机制作废**；其“不阻塞 event loop、Session 不跨线程、取消不提前释放锁”的**属性要求保留**（§19.10 已加注）。
> **R1.3 最终状态**：第 6 项的 **10 秒等待上限**与 **`IMPORT_LOCK_TIMEOUT`** 已由 **open-decisions §L.2** 固定；R1.2 §K.2 中的相关旧称仅为历史记录，不再作为未决项。

1. **路由形态**：导入/批量导入/approve 写入口使用 FastAPI **同步 `def`** 路由（由框架在线程池执行）；**禁止**在 `async def` 路由内直接等待阻塞式同步锁。只读/无关端点不受影响。
2. **单一协调器**：Backend lifespan 创建**唯一** `ImportCoordinator`，存于 `app.state`，注入 submit（单篇/批量）与 approve 导入分支；所有入口使用**同一把同步身份锁**与同一 registry。禁止各 router 自建 Coordinator。
3. **Session 生命周期**：SQLAlchemy Session 在**实际执行线程内**创建、使用、关闭；**禁止**把 request-scoped Session 传入其他线程。需要跨阶段读取时，S0/S1 各用独立短会话，读后立即关闭。
4. **锁覆盖范围**：S0 只读短会话关闭 → 获同步身份锁 → S1 全新会话重读 → 判定 → 开启写事务 → Commit/Rollback → 关闭 Session → **最后释放锁**。锁覆盖**完整业务事务**，不得在事务开始前释放，也不得在 Session 清理前释放。
5. **客户端断开**：请求取消/断连**不得**导致提前释放锁；必须先完成事务回滚/提交与资源清理。取消路径同样须有界，不得无限持锁。
6. **有界等待**：锁等待上限**固定为 10 秒**（open-decisions §L.2）；超时 **fail-closed**，返回固定稳定码 `IMPORT_LOCK_TIMEOUT`，不得无锁 fallback、不得无限等待。该项为最终实现约束，不再保留建议或待定语义。
7. **禁止双协调架构**：不得同时存在 async keyed lock 与 `threading.Lock` 两套协调机制；不得以“async 锁负责等待、threading.Lock 负责互斥”混合实现。`ImportCoordinator` 只有一种同步锁实现。
8. **并发度**：同 `DocumentIdentity` 串行；不同身份可并行。同步模型不得退化为全局单线程串行（除必要的单实例 OS 锁与短临界区）。
9. **与 R1.1 验收的关系**：`R1.1-IMP-32…37/39` 的身份锁/时序/取消属性继续有效；`R1.1-SQL-10`（event loop 不阻塞、Session 不跨线程）保留为属性回归项；新增 `R1.2-ASYNC-01…08` 验证同步模型本身。

### 21.4 D21：HTTP 网络边界（默认 loopback，无认证不外露）

1. **默认监听**：HTTP 默认绑定 `127.0.0.1`；配置项 `api_host` 默认值即 loopback（§12）。
2. **无认证拒绝非 loopback**：当前无认证体系，**任何非 loopback 监听配置必须启动 fail-closed**（固定稳定码 `NON_LOOPBACK_WITHOUT_AUTH`，§22.3），不得“仅告警后继续监听”。
3. **校验方式**：对配置值做**解析后判断**（IPv4/IPv6），不得用字符串前缀/包含判断；**R1.3 D24 收紧绑定允许集合为精确 IP `127.0.0.1` 或 `::1`**，`localhost` 等主机名**不得作为绑定配置**，其余一律拒绝；解析失败同样 fail-closed（§22.3）。
4. **CORS/代理头不是认证**：CORS 配置、`X-Forwarded-For`/`X-Real-IP`/任意自定义转发头**不得**被当作身份或访问控制依据；不得存在“带某 header 即放行”的逻辑。
5. **代理/隧道/端口转发**：反向代理、隧道、端口转发是**额外暴露面**；loopback 监听本身**不解决**其认证/授权/TLS 问题。文档须明确：未认证状态不得经代理/隧道对外暴露；远程访问须等待 auth 批次与独立部署评审。
6. **错误与日志**：启动失败/网络错误只返回稳定码与风险说明，**不得**回传主机、端口、密钥、堆栈或 `str(exc)`（AGENTS.md §9）。
7. **不新增依赖、不实现认证**：A1-04 不引入认证库/中间件；不得宣称已鉴权或“loopback 即安全”。网络验收归 Batch D（`R1.2-NET-01…08`）。
8. **R1.3 D24 补充（就地修正）**：绑定只接受精确本机 IP（`127.0.0.1`/`::1`），**不接受 `localhost` 绑定**；请求侧增加**精确 Host + 合法端口校验**、**浏览器修改请求同源 Origin 校验**、**修改接口仅 `application/json`**、**禁止宽泛 CORS**、**代理头不得授予访问权**、**拒绝 DNS Rebinding 伪造 Host**；非 loopback 启动仍 fail-closed（§22.3）。这些属 Batch D，**不阻塞 Batch A 非附件开发**。

### 21.5 R1.2 文件/配置边界与禁改清单

- **配置（additive）**：`backend/app/core/config.py` 增加 `api_host`（默认 `127.0.0.1`，启动校验）；不新增密钥字段、不改变 `SecretStr` 机制。
- **启动/装配（additive）**：`main.py`/启动入口按 `api_host` 校验并绑定；导入/批量/approve 写路由改为同步 `def`；`ImportCoordinator` 单例注入。不得改变既有只读端点语义。
- **导出/导入映射**：frontmatter 增加 `__explainlab_exporter_instance_id`、manifest 增加 `exporter_instance_id`；文档来源身份字段保持既有语义；**不新增 DB 列**。
- **R1.3 Hash 边界（D22）**：exporter 元数据的提取、剥离与注入**只在 backend 传输适配层**完成；调用 A1-02 codec/Hash/canonicalization v1 **之前**从 `extra_metadata` 移除专用保留键，**先算文档 Hash、再注入 exporter**；不得修改 Core Hash 函数或 canonicalization v1（§22.1）。
- **R1.3 身份初始化（D23）**：DB 身份写入只用既有字段（`knowledge_item.source_instance_id`、`knowledge_item.id`、`ImportOrigin.source_instance_id/source_document_id/source_payload_hash`），**不新增迁移/表/列/索引**；仅凭 DB 字段/`extra_metadata` 无法区分合法物化与历史孤立（信息不足），因此复用既有 data 目录 write-ahead Journal，以 **COMMITTED MATERIALIZE 记录**作为唯一显式标记；无匹配记录的非空实例不得认领；rotate 用同一 Journal 机制，不落 DB。
- **R1.3 HTTP 校验（D24）**：在本机请求处理链增加 Host/Origin/Content-Type 校验与 loopback 绑定校验；**不引入认证依赖**、不实现账号/JWT/远程访问（§22.3）。
- **禁止**：新增 migration/table/column/index；改 0006；改 Core `ReviewService`/端口；改 A1-02 codec/canonical/三 Hash；改 A1-03 `LinkKeyRebuild`/`apply_link_key_plan`/`locking.py`；改 V1 `KnowledgeRepository`/`KnowledgeOut`/GET；引入认证/网络新依赖；改 `MILESTONES.md`；提交/推送；启动 Batch A/A1-05/A2。

### 21.6 R1.2 新增验收编号映射（全部【待验证】，详见 acceptance-matrix §G）

| 主题 | 决策 | 新增验收编号 |
|---|---|---|
| 文档身份三元分离、来源身份不被覆盖、legacy 兼容 | D18 | `R1.2-ID-01…08` |
| 批次 A/B/C/D 边界、附件拒绝/不静默丢弃、独立出口 | D19 | `R1.2-BAT-01…06` |
| 同步 `def` 路由、线程内 Session、锁覆盖事务、断连不释放、无双架构 | D20 | `R1.2-ASYNC-01…08`（与 `R1.1-SQL-10` 并存） |
| loopback 默认、无认证拒绝非 loopback、代理头非认证、暴露面说明 | D21 | `R1.2-NET-01…08` |

> 编号只在 R1.2 段新增；R1/R1.1 编号不变、不重排；IMP-21…24、BAK-13/14 空号继续保留。

### 21.7 R1.2 阶段级冻结门禁与停止点

> **R1.3 注记**：R1.3 合并后，最终冻结门禁以 **§22.6** 为准；本节保留为 R1.2 历史门禁，未删除。

冻结前必须同时满足：

- 四份主文档（implementation-plan / acceptance-matrix / risk-register / open-decisions）已合并 D18–D21，**不是仅保留增补文件**；§19.9/§19.10/§20.2/§12 的就地修正与 §21 一致。
- 编号、术语（source / document / exporter）、事务顺序、批次边界、交叉引用一致（§21.6 ↔ acceptance-matrix §G ↔ risk-register §13 ↔ open-decisions §K）。
- 所有 R1.2 新增验收进入 acceptance-matrix §G 并标【待验证】；风险入 risk-register §13；决策入 open-decisions §K；不把设计写成已实现。
- 无新增 P0/P1 设计缺陷；用户明确批准 R1.2 决策（open-decisions §K.2）并完成 ChatGPT 独立审计。
- 仍未验证：同步模型真实并发/取消、loopback 校验真实启动、附件拒绝真实 API、批次门禁真实执行、legacy 身份兼容。**不得预先宣称通过。**

满足后才允许进入 Batch A；**本轮合并完成后停止，不启动 Batch A，不进入 A1-05/A2，不提交/推送**。

---

## 22. R1.3 权威修订（合并 D22–D24，冲突以本章为准）

> **来源**：ChatGPT R1.3 架构裁决 D22（exporter 与 Hash 解耦）、D23（本地文档身份初始化）、D24（HTTP 本机安全边界）。
> **状态**：**R1.3 架构修订稿，待用户阶段级批准 + ChatGPT 最终独立审计**。本章为**设计**，非实现或测试通过证明；所有 R1.3 新增验收均【待验证】。
> **合并原则**：R1/R1.1/R1.2 未冲突设计、编号与历史记录全部保留；与本章冲突的旧表述以本章为准，§21.1/§21.4/§21.5 已就地修正并指向本章。**本轮仅文档合并，不写业务代码/测试、不新增迁移/表/列/索引、不加依赖、不改 A1-01/A1-02/A1-03、不改 Core Hash、不改 V1 API、不改 `MILESTONES.md`、不提交/推送。**
> **冻结契约不变**：D22–D24 **不改变** A1-02 Core Hash 函数与 canonicalization v1、A1-03 链接键重建规则、Core `ReviewService`、V1 `KnowledgeRepository`/`KnowledgeOut`/GET。

### 22.1 D22：exporter 与 Hash 解耦（传输元数据，不参与文档身份计算）

**定义**：`exporter_instance_id` 只属于**传输元数据**（谁执行了本次导出），不属于文档内容、来源身份或审核对象。

| Hash / 数据 | 是否包含 exporter | 说明 |
|---|---|---|
| `document_content_hash` | **否** | 仅文档正文语义内容；与导出实例无关 |
| `document_payload_hash` | **否** | 文档载荷（正文 + 非保留 metadata + 结构）在**剥离 exporter 后**计算 |
| `source_payload_hash` | **否** | 入站源载荷 Hash；导入时先剥离保留键再计算 |
| `review_payload_hash` | **否** | 审核载荷 Hash；exporter 变化不得产生新审核对象 |
| ZIP Manifest 自身 checksum | **可以包含** | Manifest 内含 `exporter_instance_id`，其 checksum 随 exporter 变化是允许的；**文档 payload_hash 不得因此变化** |
| 知识条目数据库 | **禁止** | 不新增列、不写任何 exporter 字段 |

**导出顺序（强制）**：

1. 仓库读取文档内容、文档来源身份（`source_instance_id` / `source_document_id`）、tags、links、非保留 metadata；**不读取、不伪造 exporter 持久值**。
2. 传输适配层复制 `extra_metadata`，检查是否含专用保留键 `__explainlab_exporter_instance_id`；若用户数据已占用该键，**明确拒绝导出并报告冲突**，不得静默删除用户 metadata（稳定码 `EXPORTER_METADATA_RESERVED_CONFLICT`）。
3. **先**调用 A1-02 codec/Hash（canonicalization v1 原样）计算 `document_content_hash` / `document_payload_hash`；计算输入中**不含** exporter。
4. 序列化 frontmatter 后，在传输层注入 `__explainlab_exporter_instance_id: <当前实例 ID>`；该注入**不回流**到已计算的 Hash，也不写回数据库。
5. 生成 ZIP manifest 时写 `exporter_instance_id`；manifest checksum 在注入后计算，允许随 exporter 变化。

**导入顺序（强制）**：

1. **先于 YAML 映射折叠**检测 frontmatter 中的保留键重复（原始 frontmatter 预扫描或拒绝重复键的 loader hook）；通过后再解析 frontmatter / manifest，**提取并移除**传输位置的 `__explainlab_exporter_instance_id` / `exporter_instance_id`，得到纯文档 metadata。**同一 frontmatter 内保留键重复出现即拒绝**，不做“取其一”，**不得依赖**解析器“后者覆盖前者”的结果。
2. 用剥离后的 metadata 计算 `source_payload_hash`、内容比对与 `review_payload_hash`；exporter 不进入任何 Hash 输入。
3. exporter 仅作为本次导入的传输信息进入 `ImportReport`（如需要展示），**不落库、不作为身份键**。
4. 若 manifest 与 frontmatter 的 exporter 值不一致、保留键出现在**用户自定义 metadata 容器内**、或存在重复保留键（含解析器折叠前检测到的重复），按 D22 **明确拒绝并报告冲突**（`EXPORTER_METADATA_RESERVED_CONFLICT`）；**不得静默删除或覆盖用户 metadata**。
5. **校验顺序与零写入**：原始 frontmatter 重复键检测 / 传输位置提取 → 剥离保留键 → 计算 Hash → manifest 与 frontmatter 一致性校验 → **之后才允许任何数据库写入**。上述任一冲突均必须在事务写入前终止；**冲突时数据库写入为零**，不得先写入再回滚冒充“无部分写入”。

**保留字段与命名**：

| 位置 | 字段名 | 规则 |
|---|---|---|
| Markdown frontmatter | `__explainlab_exporter_instance_id` | 保留键；导入前剥离、导出后注入；用户占用即冲突拒绝 |
| ZIP Manifest | `exporter_instance_id` | 传输字段；不参与文档 payload Hash |
| 数据库 | 无 | **不新增列/表/索引** |

**冻结边界**：A1-02 的 Hash 函数、canonicalization v1、codec 行为**一律不改**；解耦全部在 backend 传输适配层完成。不得以“把 exporter 加入 canonical 输入再统一过滤”等方式变相修改 Core 契约。

### 22.2 D23：本地文档身份初始化（既有 DB 字段 + data 目录 Journal）

**不新增迁移、表、列或索引**。DB 身份写入仅使用以下既有字段；另复用既有 **data 目录原子文件/Journal** 作为“已合法物化”的显式证据（非 DB schema）：

| 字段/文件 | 用途 |
|---|---|
| `knowledge_item.source_instance_id` | 本地原生文档首次导出时物化为当前实例 ID |
| `knowledge_item.id` | 本地原生文档的稳定 `source_document_id` |
| `ImportOrigin.source_instance_id` | 导入文档的来源实例身份（权威来源之一） |
| `ImportOrigin.source_document_id` | 导入文档的稳定来源文档身份（权威来源之一） |
| `ImportOrigin.source_payload_hash` | 来源载荷 Hash（幂等与当前来源判定） |
| `data/source-identity-journal.json` + `data/source-identity-journal.archive/<operation_id>.json` | 物化/rotate 的 write-ahead Journal 与完成归档；**本地物化的唯一显式标记** |

**【事实】（2026-11-21 只读核对）** `backend/app/models.py`：`KnowledgeItemORM.source_instance_id` 为 nullable（:116）；`ImportOriginORM.source_instance_id` 为 nullable（:429）、`source_document_id` 为 non-null（:430）。`knowledge_item` **没有** `source_document_id` 列，因此本地原生文档的 `source_document_id` 由 `item.id` **派生**。`knowledge_item`/`import_origin` 均**没有**“本地原生来源类型/状态”列；`import_origin` 仅 PK + 两个非唯一索引，无身份/来源唯一约束（`models.py:410-435`；`0006_v2_markdown_kb.py:169-188`）。该核对只证明字段现状，不证明 D23 行为已实现。

**【关键事实】现有 DB 字段与 `extra_metadata` 无法可靠区分“已合法物化”与“历史身份孤立”**：

- **无来源类型标记**：`knowledge_item` 无 provenance/kind/status 列；`ImportOrigin` 也没有“本地物化”类型字段，且 `import_batch_id` 仅是自由文本 correlation，**没有保留值/哨兵语义**（`ports.py:403-434`、`entities.py:285-301`）。
- **`extra_metadata` 不能当免费标记**：`MarkdownDocument.present_exchange_fields()` 把非空 `extra_metadata` 纳入交换载荷（`knowledge-core/src/knowledge_core/markdown/__init__.py:231-232`），`document_payload_hash` 覆盖完整载荷（:371-381），`extra_metadata_hash` 专门覆盖该字段（:448-450）。写入标记会改变文档身份 Hash，违反 A1-02 冻结边界。
- **不能靠 `source_instance_id` 非空推断**：历史孤立行与合法物化行在 DB 形状上完全相同；`source_payload_hash`/`source_content_hash` 为 NULL 也不是独占证据。不得把“无 ImportOrigin + 非空实例 ID”一律认领为本地原生。
- **不能插入伪 `ImportOrigin` 行作标记**：`save_origin` 是追加语义、`find_by_source_payload_hash`/`find_by_source_document` 返回 list、无唯一约束；伪行会改变身份状态判定，污染导入幂等/S0/S1 与 FID-2 当前来源解析，并可能制造 `SOURCE_IDENTITY_AMBIGUOUS`。**明确禁止**。
- **不用 `MAX(imported_at)`/排序/随机 ID/静默覆盖**：这些都不能证明物化来源，且违反 FID-2 与 D18。

> **信息不足结论（强制记录）**：仅凭现有 DB 字段与 `extra_metadata`，**无法安全区分**“D23 合法物化的本地文档”与“历史遗留的身份孤立文档”。本设计**不据此做任何推断**，也不编造分类规则；合法物化必须由 **COMMITTED MATERIALIZE Journal 记录**证明；证明缺失、损坏或多条冲突即 **fail-closed**（归状态 4）。若用户不接受新增 Journal 记录作为显式标记，则本项只能保持阻断，不得自动物化。

**Journal 显式标记（复用既有 data 目录，不落 DB）**：

- 当前 Journal：`data/source-identity-journal.json`；归档：`data/source-identity-journal.archive/<operation_id>.json`；与 `data/source-instance-id` 同卷。完成记录**append-only 保留**，应用不自动删除；备份/恢复必须把归档与 DB 一并处理，缺失即 fail-closed。
- **Journal 数据契约 v1（闭合 schema；仅 Journal 使用，不改变 A1-02 Core Hash/canonicalization）**：

  **顶层记录字段（所有字段必须出现；不适用时写 JSON `null`，不得省略）**：

  | 字段 | 类型 | 约束 |
  |---|---|---|
  | `schema_version` | integer | 固定 `1`；缺失/未知版本 fail-closed |
  | `operation_id` | string | UUIDv4；仅操作关联，**绝不作为文档身份** |
  | `kind` | string | `MATERIALIZE` 或 `ROTATE` |
  | `phase` | string | `PREPARED` 或 `COMMITTED` |
  | `created_at` / `updated_at` | string | UTC RFC3339、`Z` 结尾；参与 checksum，不参与身份 |
  | `item_id` | string/null | `MATERIALIZE` 为目标 item；`ROTATE` 为 `null` |
  | `source_instance_id` | string/null | `MATERIALIZE` 为目标实例；`ROTATE` 为 `null` |
  | `source_document_id` | string/null | `MATERIALIZE` 必须等于 `item_id`；`ROTATE` 为 `null` |
  | `materialization_items` | array | `MATERIALIZE` 恰好 1 项；`ROTATE` 为 0..N 项（rotate 前已物化的 2a，使用 rotate 前旧实例） |
  | `materialization_digest` | string | `sha256:` + 64 位小写十六进制 |
  | `identity_audit_digest` | string | `sha256:` + 64 位小写十六进制 |
  | `journal_checksum` | string | `sha256:` + 64 位小写十六进制 |
  | `old_instance_id` | string/null | `ROTATE` 旧实例；`MATERIALIZE` 为 `null` |
  | `target_instance_id` | string/null | `ROTATE` 目标实例；`MATERIALIZE` 为 `null` |

  **`materialization_items[]` 元素字段（v1 闭合）**：

  | 字段 | 类型 | 约束 |
  |---|---|---|
  | `item_id` | string | `knowledge_item.id`；同一 Journal 内唯一 |
  | `source_instance_id` | string | 非空；该 item 实际写入的实例 ID；`MATERIALIZE` 必须等于顶层 `source_instance_id`，`ROTATE` 的预物化项必须等于 `old_instance_id` |
  | `source_document_id` | string | 非空；本地原生文档必须等于 `item_id` |
  | `identity_record_version` | integer | 固定 `1`；未知版本 fail-closed |
  | `item_identity_digest` | string | `sha256:` + 64 位小写十六进制；计算对象见下 |

  `item_identity_digest = SHA-256(canonical JSON of {item_id, source_instance_id, source_document_id, identity_record_version})`，对象键排序、无 exporter。

  **`identity_audit_digest` 的覆盖面（与 `materialization_items` 严格区分）**：

  `materialization_items` **仅**列出本次需要物化的本地原生文档（MATERIALIZE 恰好 1 项；ROTATE 为 rotate 前已物化的 2a 项）。`identity_audit_digest` **覆盖全部 `knowledge_item` 及其全部已附着 `ImportOrigin` 记录**：未物化本地（2a）、已物化本地（2b）、正常导入（1）、导入身份残缺（3）、原生字段孤立/冲突（4）均各有一条知识项快照；**每条 `ImportOrigin` 原始记录都必须进入该项的 `import_origins[]`，不得因完整/残缺/重复/字段非法而过滤、去重、合并或退出审计**。它**不**用 Journal 记录反推 2b/4，也不以摘要匹配替代“恰好一条 COMMITTED MATERIALIZE 记录”校验；2b 合法性仍由该记录单独证明，摘要只证明 DB 身份投影（含全部原始 origin 记录）与 Journal 预期一致。

  **孤儿 `ImportOrigin` 的处理（强制）**：每次计算摘要前，必须独立检查全部 `import_origin.item_id` 是否存在于 `knowledge_item`。只要存在孤儿记录（包括 FK 历史遗留/关闭外键检查时形成的行），立即 **fail-closed**（稳定错误码【提议】`SOURCE_IDENTITY_ORPHAN`），零身份写入、零分类、零 Journal 提交；不得静默跳过、不得只审计可连接行、不得伪造归属。孤儿变更不能借“未进入快照”掩盖，因为该状态直接拒绝操作，不产生可接受摘要。即使 schema/外键本应阻止孤儿，也必须保留该防御性检查。

  **`identity_audit_digest` 的单项快照字段（v1 闭合）**：

  | 字段 | 类型 | 约束 |
  |---|---|---|
  | `item_id` | string | `knowledge_item.id`；全部知识文档按此字段升序 |
  | `origin_state` | string | 有效身份状态：`none`=无 `ImportOrigin`；`complete`=全部记录合法、仅一个来源身份对 `(source_instance_id, source_document_id)`、无逐字节重复组、`knowledge_item.source_instance_id` 与该身份对一致（可含同一身份的不同 `source_payload_hash` 版本记录）；`incomplete`=其余所有可附着记录情形（残缺/重复/非法/冲突），不产生有效身份。不得由 exporter 或时间推断 |
  | `db_source_instance_id` | string/null | `knowledge_item.source_instance_id` 原值；`null` 与空字符串按 DB 原值分别保留，不做归一化；用于完整性审计 |
  | `source_instance_id` | string/null | 有效来源实例：`none` 时取 `db_source_instance_id`；`complete` 时取该唯一来源身份对的 `source_instance_id`（多版本记录共享同一值）；`incomplete` 时为 `null`（不回落本地值） |
  | `source_document_id` | string/null | 有效来源文档：`none` 时为 `item.id`（本地原生文档稳定身份，未物化也成立）；`complete` 时取该唯一来源身份对的 `source_document_id`（多版本记录共享同一值）；`incomplete` 时为 `null` |
  | `import_origin_count` | integer | 该 item 的全部已附着 `ImportOrigin` 行数，**包含残缺/重复/非法记录**；无记录为 `0` |
  | `import_origin_state` | string | 审计汇总：`none` / `complete` / `duplicate` / `incomplete` / `invalid` / `conflict`。按 `conflict` > `invalid` > `incomplete` > `duplicate` > `complete` > `none` 的固定优先级判定（完整判定见下表）；计数/逐条状态仍分别保留，不因汇总值丢失 |
  | `incomplete_origin_count` | integer | `status_flags` 含 `incomplete` 的记录数 |
  | `invalid_origin_count` | integer | `status_flags` 含 `invalid` 的记录数 |
  | `duplicate_origin_count` | integer | `duplicate_group_size > 1` 的记录数 |
  | `import_origins` | array | 该 item 的全部 `ImportOrigin` 原始记录；无记录为 `[]`；按 `import_origin_id` 的 Unicode code point 升序 |
  | `import_origin_identity_digest` | string/null | **仅** `origin_state=complete` **且恰好一条合法 `ImportOrigin`** 时计算 `sha256(canonical JSON of {source_instance_id, source_document_id, source_payload_hash})`；其余为 `null`（包括同一身份的多版本历史记录）。该字段只是完整单一来源记录的便利摘要，**不是**审计覆盖本身；残缺/重复/非法/多版本的覆盖由 `import_origins` 承担 |

  **`import_origins[]` 元素字段（v1 闭合）**：

  | 字段 | 类型 | 约束 |
  |---|---|---|
  | `import_origin_id` | string | `ImportOrigin.id` 原始稳定主键；逐条保留并作为排序键，不重新生成、不改写 |
  | `source_instance_id` | string/null | DB 原值，逐字节保留；`null` 与空字符串不同；不做 trim、大小写、UUID/ULID 或其他归一化 |
  | `source_document_id` | string/null | DB 原值（正常列非空；历史/损坏数据若为 `null` 也必须原样记录），逐字节保留；`null`、空字符串、非法格式均为审计值，不得静默替换为 `item.id` 或空串 |
  | `source_payload_hash` | string/null | DB 原值（正常列非空；历史/损坏数据若为 `null` 也必须原样记录），逐字节保留；`null`、空字符串、非法格式均为审计值，不得静默重算或归一化 |
  | `status_flags` | array | 按字典序升序的闭合标记数组，元素仅 `incomplete`、`invalid`；字段完全合法时为 `[]`；两种异常可同时出现；重复状态由 `duplicate_group_size` 单独表达，不写入本数组 |
  | `duplicate_group_size` | integer | **同一 `knowledge_item` 内**与该记录三个原始身份字段**逐字节完全相同**的记录数（含自身），`>=1`；`>1` 表示该 item 内的重复组。`null`、`""`、大小写差异均视为不同值；跨 item 相同身份不由本字段合并 |

  `status_flags` 判定（只用于审计标记，不改变原始值）：`incomplete` = `source_instance_id` 为 `null` 或空串，或 `source_document_id` 为 `null` 或空串，或 `source_payload_hash` 为 `null` 或空串；`invalid` = 所有非空字段中任一不满足既有字段契约（如 `source_document_id` 不是规范 UUID 文本、`source_payload_hash` 不是 64 位小写十六进制、`source_instance_id` 超长或含非法控制字符）。

  **`ImportOrigin` 多记录状态判定表（v1 闭合；每个 item 恰有一个汇总状态）**：

  > 记 `n = import_origin_count`；`identity(r) = (source_instance_id, source_document_id)` 为来源身份对（按原始字节比较）；`version(r) = source_payload_hash` 为来源版本。`source_payload_hash` 不同只表示同一来源文档的不同版本，**不是**不同来源身份（D18/FID-2）。`legal_origins` = `status_flags=[]` 的记录；`identity_count` = `legal_origins` 中不同身份对的个数；`db_match` = `identity_count=1` 且 `db_source_instance_id` 非空、逐字节等于该身份对的实例 ID；`has_conflict` = `identity_count>=2` 或（`identity_count=1` 且非 `db_match`）；`has_duplicate` = 任一记录 `duplicate_group_size>1`。

  | 顺序 | `import_origin_state` | 判定条件（按顺序首个命中；除 `none` 外均要求 `n>0`） | 有效来源身份 | 处置 |
  |---:|---|---|---|---|
  | 1 | `conflict` | `has_conflict`：存在 ≥2 个不同合法身份对；或唯一合法身份对的实例与 `knowledge_item.source_instance_id` 不一致（含 DB 为 `null`） | `source_instance_id=null`、`source_document_id=null` | **fail-closed**；不认领/不覆盖/不合并/不猜测；不得以 DB 指针、记录顺序、`MAX(imported_at)`、ID 或 Hash 选择任一条 |
  | 2 | `invalid` | 无 `conflict`，且任一记录 `status_flags` 含 `invalid` | 同上 | 状态 3/4 fail-closed；逐条原值保留审计 |
  | 3 | `incomplete` | 无 `conflict`/`invalid`，且任一记录 `status_flags` 含 `incomplete` | 同上 | 状态 3 fail-closed；**即使同时存在完整记录，也不得提升为 `complete` 或选用该完整记录** |
  | 4 | `duplicate` | 无上述，全部记录合法、`identity_count=1` 且 `has_duplicate` | 同上 | 状态 3/4 fail-closed；重复记录**不得去重/合并/任选**；重复组大小保留 |
  | 5 | `complete` | 无上述，全部记录合法、`identity_count=1`、无重复组，且 `db_match` | 该唯一身份对的 `source_instance_id`/`source_document_id`；版本指针仍按 FID-2/当前 DB 指针，不由本表挑选某条 origin | 状态 1；可含同一身份的多个不同 `source_payload_hash` 版本记录（不构成 `conflict`）；不得改写来源 |
  | 6 | `none` | `n=0` | 不由 origin 产生：本地路径按 2a/2b/4 与 Journal 判定 | 无 `ImportOrigin` 时不套用本表的 conflict；`source_instance_id` 非空但无 2b 证据仍归状态 4 fail-closed |

  **互斥、组合与优先级（强制）**：

  - 汇总状态**互斥**：每个 item 只能取上表一个值。完整记录与残缺/非法记录混合时，按“`conflict` > `invalid` > `incomplete` > `duplicate` > `complete` > `none`”取**最保守**值；逐条 `status_flags` 与计数仍保留，不得因汇总值丢失。
  - **任一记录可同时带 `incomplete` 与 `invalid`**；汇总按上述优先级取 `invalid`（除非先命中 `conflict`）。`duplicate_group_size>1` 可与异常标记共存；汇总同样按优先级处理，重复计数不丢。
  - **多个不同但均合法的身份对 → 必须 `conflict`**：即使其中一条与 DB 指针相同、即使其他记录残缺或非法，也不得把该条提升为有效来源；**不得**选择/排序/合并后作为唯一来源。
  - **完整 + 残缺混合** → `incomplete`（无更高优先级时）：完整记录不得被单独选中；有效身份为 `null`；不得物化/认领/覆盖。
  - **重复 + 不同身份混合** → `conflict`（无更高优先级时）：重复组不得被当作“更可信”或“更新”；不得合并字段、不得按组大小或时间选一条。
  - **`knowledge_item` 与 `ImportOrigin` 不一致**：仅比较 `knowledge_item.source_instance_id` 与唯一合法身份对的实例 ID（`source_document_id` 无对应的 `knowledge_item` 列，不做伪造比较）。DB 为 `null` 或逐字节不同 → `conflict`；若无合法 origin（全部残缺/非法），不构造有效身份，保持 `invalid`/`incomplete` 并 fail-closed。`source_payload_hash`/`source_content_hash` 是版本/内容指针，**不参与身份对冲突判定**，也不得据此挑选 origin。
  - **无 `ImportOrigin` + `source_instance_id` 非空**不属于本表的 `conflict`（`import_origin_state=none`），仍按 D23 状态 4 处理：无恰好一条 COMMITTED MATERIALIZE 记录即 fail-closed，不补、不覆盖、不认领。
  - **残余组合**：若 `n>0` 但未能命中任何行（实现/数据异常），一律按 `invalid` fail-closed，**不得回落为 `none` 或 `complete`**。

  **`conflict` 的统一处置（强制）**：冲突项的 `origin_state` 为 `incomplete`（不产生有效来源身份）；任何需要该 item 来源身份的分类、物化、认领、导出身份写入、rotate 身份改写、adoption 或 FID-2 归并均 **fail-closed 且零身份写入**（`knowledge_item`/`ImportOrigin`/Journal 均不产生认领结果）；只允许在报告/快照中如实记录 `conflict` 与全部原始记录。不得以“跳过该文档后继续正常处理”的方式静默降级，也不得把冲突项计为状态 1/2b。批量/rotate 中其他无关 item 的既有规则不变，但冲突项本身必须保持原样并由 `identity_audit_digest` 覆盖。

  身份审计快照**不得包含** `exporter_instance_id`、`__explainlab_exporter_instance_id`、title、content、`extra_metadata`、时间戳或 `import_batch_id` 等其他非身份字段。`origin_state=incomplete` 表示**不存在可用的唯一来源身份**（含残缺、无效、重复、冲突及多身份对），不把任何单条 origin 当作有效身份；其分类仍为状态 3/4 并 fail-closed。

  **`identity_audit_digest` 的时点语义与 DB 验证（强制）**：

  - 它是**操作完成后的预期身份状态**摘要。`PREPARED` 时在身份锁内读取全部 `knowledge_item` 与**全部 `ImportOrigin`（不得按完整性/重复/状态过滤，不得用会丢弃坏行的内连接）**，先做孤儿检查，再构造逐条快照；在内存中将 `materialization_items` 应用到当前快照（不写 DB）后计算。`ROTATE` 的预期值等于当前快照（2a 已在 rotate 前物化）。
  - **每次 DB 写入后、以及每个恢复分支，都必须重新读取全部 `knowledge_item`/`ImportOrigin` 并重算摘要**；不得仅凭 Journal 自身记录、内存对象或旧快照证明 DB 正确。重算值必须等于 Journal 的预期完成态值，否则 fail-closed。
  - `ROTATE` 必须在 exporter ID 替换**前**计算一次，替换**后**再次从 DB 重算；两次均须等于 PREPARED 预期值，且两次都必须完成孤儿检查与全量 `ImportOrigin` 读取。`exporter_instance_id` 不参与摘要，因此合法 rotate 不应改变 `identity_audit_digest`。
  - `COMMITTED` 未归档恢复虽然不重写 DB，仍须重读 DB 并重算摘要；不一致即 fail-closed，不得直接归档或移除 current。
  - **判别性**：任一 `ImportOrigin` 的 `import_origin_id`、原始 `source_instance_id`/`source_document_id`/`source_payload_hash`、记录数量、`status_flags` 或 `duplicate_group_size` 变化，以及任一 item 的记录集合增减，都必须改变 `identity_audit_digest`；数据库返回顺序、连接顺序、查询顺序不得改变摘要。除 `materialization_items` 列出的 item 外，任何知识文档的来源身份变化均导致摘要不符并 fail-closed。
  - **不做静默归一化**：原始 origin 字段按 DB 存储值进入 canonical JSON；`null`、空串、大小写、UUID 文本形式差异均保留。不得因“看起来等价”而合并记录或改写字段；重复只在同一 item 内按逐字节相同三元组计算组大小。

  **三个摘要的计算对象、排序与编码**：

  | 摘要 | 计算对象 | 排序 | 编码/算法 |
  |---|---|---|---|
  | `materialization_digest` | `materialization_items` 完整数组 | 按 `item_id` 升序；重复 ID 非法 | canonical UTF-8 JSON，SHA-256，`sha256:` 前缀 |
  | `identity_audit_digest` | **全部 `knowledge_item`（每项含全部 `ImportOrigin` 原始记录 `import_origins[]`）** 的单项身份快照数组（**操作完成后的预期状态**；不是仅 `materialization_items`） | 知识项按 `item_id` 升序；每项 `import_origins` 按 `import_origin_id` 升序 | canonical UTF-8 JSON，SHA-256，`sha256:` 前缀 |
  | `journal_checksum` | 顶层记录除 `journal_checksum` 外的全部字段（含两个摘要与数组） | 对象键排序；数组保持其既定排序 | canonical UTF-8 JSON，SHA-256，`sha256:` 前缀 |

  **Canonical JSON v1（Journal 专用；字节级固定，不使用平台默认序列化）**：

  以下规则同时适用于三个摘要、`item_identity_digest` 与测试向量。实现必须显式控制编码与转义，不得直接采用语言默认 JSON 序列化的 `ensure_ascii`、浮点格式、键排序、控制字符转义或重复键覆盖行为。

  - **编码**：UTF-8，无 BOM、无结尾换行、无多余空白；分隔符 `,`/`:` 无空格。
  - **非 ASCII**：U+0080 及以上按 UTF-8 原样输出（中文、emoji、补充平面字符均不转 `\uXXXX`）；`/` 不转义；U+007F 原样输出。
  - **字符串转义**：`"`→`\"`，`\`→`\\`；U+0008/U+0009/U+000A/U+000C/U+000D 用 `\b`/`\t`/`\n`/`\f`/`\r`；其余 U+0000–U+001F 用 `\u00xx`（小写十六进制）；不输出 `\/`。
  - **Unicode 标量**：输入必须是 Unicode 标量序列；合法 high/low surrogate 对在解析后组合为一个补充平面标量；孤立/未配对 surrogate 拒绝；序列化不得输出 surrogate 码点或 `\uD800`–`\uDFFF` 转义。不做 trim、NFC/NFKC、大小写或其他归一。
  - **对象键**：按 Unicode code point 升序；不使用 locale 或平台排序。重复键必须在解析折叠前拒绝，包括解码后相同的 `"a"` 与 `"\u0061"`；不得 last-wins。实现须使用保留重复项的解析钩子或原始 token 扫描。
  - **数字**：只允许非负整数 token `0|[1-9][0-9]*`；禁止负数、前导零、`-0`、`+`、浮点、指数、`NaN`、`Infinity`。
  - **字面量**：`null` 小写；若未来字段使用布尔，只允许小写 `true`/`false`。
  - **结构**：所有字段必须出现；不适用写 `null`；**有效身份字段**（顶层 `source_instance_id`/`source_document_id` 的有效投影）空字符串非法；但 `import_origins[]` 的原始历史字段必须原样保留，空字符串是审计值，**不得归一化为 `null` 或丢弃**。知识项数组按 `item_id` 升序，每项 `import_origins` 按 `import_origin_id` 升序。v1 为闭合 schema，未知/缺失字段、重复 `item_id`/`import_origin_id`、类型不符、摘要不匹配均 fail-closed。

  **Canonical JSON v1 固定测试向量（必须纳入真实测试；表中 SHA-256 为 canonical UTF-8 字节的 64 位小写十六进制，不含 BOM/结尾换行/多余空格，写入 Journal 时加 `sha256:` 前缀）**：

  | # | 场景 | 输入（语义值） | Canonical JSON（UTF-8） | 字节 | SHA-256 |
  |---|---|---|---|---:|---|
  | 1 | 中文字符 | `{"标题":"知识核心","阶段":"验证"}` | `{"标题":"知识核心","阶段":"验证"}` | 43 | `5d4ba0a3747ba7e5a4d83e409f61a4639c3a38b69b385bfcaa8530f821dda203` |
  | 2 | ASCII | `{"a":"A","b":"B"}` | `{"a":"A","b":"B"}` | 17 | `89890778befbd3e99a11947e3b7387b190604bcb6dc61e5e82e49454cff53d59` |
  | 3 | 双引号与反斜杠 | 字符串 `say "hi" \ done` | `{"text":"say \"hi\" \\ done"}` | 29 | `f953d54be55fea91be6583c958e228c0aaf924a4d744efcac9ff8b339a55205f` |
  | 4 | 控制字符 | 字符串 `A<U+0001>B<TAB>C<LF>D` | `{"text":"A\u0001B\tC\nD"}` | 25 | `f6b74248ce2612e65485be611ef0f6752ceeab70fd04844b2d919780034f2300` |
  | 5 | Unicode 补充平面 | 字面 `😀`（U+1F600）或 JSON 转义对 `\uD83D\uDE00` | `{"emoji":"😀"}` | 16 | `4525cb52c6a0122eacc150bacd11eb4a1d4615485ca8a5639c28d70f1c240193` |
  | 6 | null | `{"b":"x","a":null}` | `{"a":null,"b":"x"}` | 18 | `7f50a16d8ed0dc4a8890fb342067aae8fe8597dcd4a1fb44ddec0d86afdcc4e3` |
  | 7 | 对象键顺序不同但语义相同 | `{"b":2,"a":1}` 与 `{"a":1,"b":2}` | 两者均 `{"a":1,"b":2}` | 13 | `43258cff783fe7036d8a43033f830adfc60ec037382473548ac742b888292777` |
  | 8 | 重复键拒绝 | `{"a":1,"a":2}`；`{"a":1,"\u0061":2}` | 解析折叠前拒绝；无序列化 | — | —（无 Hash） |

  > 测试向量只用于 canonicalization 单元测试，**不得替代**真实 SQLite/PG/文件系统验证；重复键拒绝必须在解析层取证，不能只断言最终字典值。向量 8 的两种输入都必须拒绝，不得 last-wins。

  **版本与空值兼容规则**：

  - 只接受 `schema_version = 1` 且 `identity_record_version = 1`；缺失、未知、混用版本均 fail-closed，不自动升级、不猜测迁移。
  - 归档记录必须由支持其声明版本的 reader 读取；当前 v1 实现遇到非 `1` 版本 fail-closed；未来版本必须显式定义新的 canonicalization/摘要规则，不得让旧读者静默忽略新字段。
  - 摘要中的 `null` 是确定值（参与哈希），不得被省略或替换为空串；数据库缺失值与 JSON `null` 的映射必须显式且稳定。
  - 归档 reader 必须按同一 Canonical JSON v1 规则重新解析与校验；BOM、尾随换行、重复键、孤立 surrogate、非法数字、非规范转义或键序错误均视为损坏/冲突，fail-closed，不得依赖平台解析器的宽松行为。
  - **`materialization_digest`、`identity_audit_digest`、`journal_checksum` 与 `item_identity_digest` 均不得包含 exporter 字段**；exporter 仅用于传输层，不属于来源身份。

- `materialization_items` 是 Journal 明确定义的字段，不得引用不存在的清单；任一摘要或 checksum 不符即视为 Journal 损坏/冲突，fail-closed。
- 判定：无 `ImportOrigin`、`source_instance_id` 非空，且存在**恰好一条**（current/archive 去重后）`COMMITTED MATERIALIZE` 记录满足 `item_id` 相同、记录 `source_instance_id` 等于当前值、记录 `source_document_id == item.id`、v1 字段/摘要/版本校验通过，且无冲突记录 → **状态 2b**；无匹配、多条匹配、记录损坏或 DB 值不一致 → **状态 4**，不认领、不补写、不覆盖。不得用时间排序挑选。

**身份状态分类（四类；状态 2 分 2a/2b，穷尽且互斥）**：

| 状态 | 判定条件 | 归类 | 允许动作 |
|---|---|---|---|
| **1. 正常导入** | 存在 `ImportOrigin`，且 `import_origin_state=complete`（全部记录合法、仅一个身份对、无重复/冲突、`knowledge_item.source_instance_id` 一致；可含同一身份的不同版本） | 已导入来源 | 沿用该唯一来源身份；不改写 |
| **2a. 本地原生（未物化）** | **无 `ImportOrigin`**、`knowledge_item.source_instance_id` **为空**，且无匹配的 COMMITTED 物化记录 | 本地原生 | 首次导出可经 **MATERIALIZE Journal** 物化当前实例 ID；`source_document_id=item.id`；无 Journal 证据则**不得写 DB** |
| **2b. 本地原生（已物化）** | **无 `ImportOrigin`**、`source_instance_id` **非空**，且存在**恰好一条**匹配的 COMMITTED MATERIALIZE 记录 | 本地原生（已物化） | 身份稳定；重复导出/重启/克隆后保持；**不得重写** |
| **3. 导入身份残缺/冲突** | 存在 `ImportOrigin`，但 `import_origin_state` 为 `incomplete` / `invalid` / `duplicate` / `conflict`（含完整+残缺混合、重复+不同身份、多个合法身份对、DB 实例不一致） | legacy/unknown / conflict | 不认领、不补身份、不覆盖、不合并、不选任一条；等待显式处理 |
| **4. 原生字段孤立** | **无 `ImportOrigin`**、`source_instance_id` **非空**，但**无/多条/冲突**匹配记录，或记录与 DB 不一致 | legacy/unknown / incomplete | **不得**认领为本地原生；**不得**自动创建/补写 `source_document_id`；**不得**覆盖既有 `source_instance_id`；等待显式处理 |

> 任何“有 `ImportOrigin` 但又有本地物化记录”、或“实例为空但有物化记录”的组合均为**冲突态**，一律 fail-closed，不纳入正常状态。`ImportOrigin` 多记录的分类、组合与优先级以本 §22.2 的状态判定表为准；`conflict` 不得被任何“单条完整记录”覆盖。

**生命周期图**：

```text
[1 正常导入] --导出/修改/再导出--> ImportOrigin 身份原样保留；仅 exporter 变化
[2a 本地原生未物化] --首次导出--> MATERIALIZE PREPARED --> DB source_instance_id=当前实例
                                   --> 重读校验 --> COMMITTED+归档 --> [2b]
[2b 本地原生已物化] --重复导出/重启/克隆--> 由 COMMITTED 记录证明，身份稳定；不重写
[3 导入身份残缺] --导出/rotate--> legacy/unknown；如实报告；不补身份
[4 原生字段孤立] --导出/rotate--> legacy/unknown；不补/不覆盖；报告；不 adoption
[Journal 丢失/损坏/冲突] --任何 2b--> fail-closed，归状态 4；不自动重认领
```

**规则（逐条强制）**：

1. **正常导入文档**：仅当 `import_origin_state=complete` 时使用该唯一来源身份对；不重新生成、不改写。若为 `conflict`/`invalid`/`incomplete`/`duplicate`，按状态 3/4 fail-closed，**不得**从多条记录中任选一条。
2. **本地原生文档**：`source_document_id` 使用稳定 `item.id`；**不得**为它编造随机文档 ID；`operation_id` 的随机 UUID 仅是操作关联，不是文档身份。
3. **首次导出物化（2a → 2b）**：仅在状态 2a；**先过 Journal 恢复门**；在既有身份锁内 S1 重读；**先写并持久化 `MATERIALIZE` PREPARED Journal，再在单事务内条件更新 `source_instance_id`（仅当仍为空且无 `ImportOrigin`），重读校验通过后写 COMMITTED 并归档**；任何 Journal/DB 校验失败均不得导出，也不得静默物化。物化不写 `extra_metadata`、不写 `ImportOrigin`、不改 Hash。
4. **已物化判定**：状态 2b 必须由匹配的 COMMITTED MATERIALIZE 记录证明；**不得**以 `source_instance_id` 非空、Hash 为 NULL、时间排序或“看起来像本地”推断。
5. **有 `ImportOrigin` 但身份非 `complete`**：继续视为 **legacy/unknown / conflict**（状态 3）；**不得**认领为本地原生文档，**不得**用 `item.id` 反向补齐其来源身份，**不得**从残缺/重复/冲突记录中挑一条、合并字段或按时间/ID/Hash 猜测。
6. **无 `ImportOrigin` 但 `source_instance_id` 非空（状态 4）**：无匹配 Journal 记录时**不得**认领；**不得自动创建或补写 `source_document_id`**；**不得覆盖**既有 `source_instance_id`；归 **legacy/unknown / incomplete**。可按 legacy 规则导出/报告（不伪造 `source_document_id`），或 fail-closed；**不得自动 Adoption**。
7. **禁止伪标记**：不得为区分状态而插入伪 `ImportOrigin`、不得在 `extra_metadata` 写标记、不得改 A1-02 Hash/canonicalization、不得新增 DB 迁移/表/列/索引。
8. **当前来源解析**：导入文档仍按既有 **FID-2** 规则解析；**禁止**用 `MAX(imported_at)` 或排序猜测；多条匹配必须 **fail-closed**（既有 `SOURCE_IDENTITY_AMBIGUOUS` 语义）。若同一 item 的 `import_origin_state=conflict`，连 FID-2 的候选归属也不得建立，零身份写入。本地物化 Journal 不参与 FID-2 的 ImportOrigin 历史判定。
9. **克隆 rotate 顺序**：执行 `rotate-instance-id` 前，先对全部状态 2a 逐条完成 MATERIALIZE（含 COMMITTED+归档），**再**轮换 exporter ID；任一条物化失败即中止 rotate。状态 3/4 不物化、不改写；rotate 仅更换 exporter，导入/继承文档来源原样保留。
10. **锁与 Journal 持久化**：物化与轮换受既有 **OS 单实例锁**保护（Backend 停止 + CLI 同锁，与 R1.1 D17 一致）；Journal/ID 文件按下方九步顺序持久化。任一步失败或崩溃不得完成轮换；Journal 写失败不得执行 ID 替换；**COMMITTED 后按归档转换规则落 archive，current 在归档校验/同步后幂等移除；归档失败禁止新操作**；恢复规则见状态机。
11. **不批量改写导入文档**：clone/rotate 不得批量改写已导入文档的 `source_instance_id` / `source_document_id`；继承文档来源原样保留。
12. **Adoption 不属于 A1-04**：把导入/继承文档“转为本实例原生文档”须显式确认与独立审批，**A1-04 不自动执行、不提供隐式路径**。

**MATERIALIZE 时序（首次导出，设计，待真实取证）**：

1. 取得既有 OS/身份锁；只读 S1 重读，确认仍为状态 2a（无 `ImportOrigin`、`source_instance_id` 为空、无匹配记录）；构造 `materialization_items`，读取**全部 `knowledge_item`/`ImportOrigin`**，在内存中应用物化项后计算全库 `identity_audit_digest` 预期完成态。
2. 生成 `operation_id`；写 `MATERIALIZE` PREPARED Journal（含 v1 schema、`materialization_digest`、预期 `identity_audit_digest`；临时文件 → fsync → 原子替换 → 父目录同步）。失败即中止，**零 DB 写**。
3. 单事务条件更新 `knowledge_item.source_instance_id` 为当前实例 ID（仅当仍为空且无 `ImportOrigin`）；校验影响行数恰为 1；提交。
4. 重读 DB：`source_instance_id` 等于记录值、仍无 `ImportOrigin`、`item.id` 未变；并读取**全部知识文档及全部 ImportOrigin 原始记录**重算 `identity_audit_digest`，必须等于 PREPARED 预期；否则 fail-closed。
5. 写 COMMITTED Journal（临时文件 → fsync → 原子替换 → 父目录同步），然后按**归档转换规则**落 archive 并校验；归档成功后才允许导出；归档失败保留 current、禁止新操作，**不重复写 DB**。
6. 导出失败不回滚已正确物化的身份（值稳定且非伪造）；但若第 2–5 步任一步失败，不得留下“无 Journal 证据的非空身份”。

**Journal 持久化顺序（强制；MATERIALIZE 跳过第 5–7 步）**：

1. **写 PREPARED Journal 临时文件**：同目录、同卷；内容含上述字段与 `journal_checksum`。
2. **fsync 临时 Journal**：文件句柄 `fsync` 成功后才继续。
3. **原子替换 Journal**：`os.replace`/等价覆盖当前 Journal；不得原地截断写。
4. **同步父目录**：POSIX 打开目录并 `fsync`；Windows 见下方能力表。
5. **写/fsync exporter-ID 临时文件**：仅 ROTATE；同目录、同卷。
6. **原子替换 exporter ID**：仅 ROTATE；覆盖 `data/source-instance-id`。
7. **再次同步父目录**：仅 ROTATE。
8. **重读并校验**：ROTATE 重读 ID 必须等于 `target_instance_id`；同时按 `materialization_items` **重新查询 DB**（见恢复规则），并读取**全部 `knowledge_item`/`ImportOrigin`** 重算 `identity_audit_digest`，与 Journal 的**预期完成态值**比较；任一不符即 fail-closed，不得提交。替换前与替换后均须各重算一次，两次都必须一致。
9. **原子更新并持久化 COMMITTED Journal**：临时文件 fsync → 原子替换 → 父目录同步 → 归档；失败保持 PREPARED，下次按状态机恢复。

> **原子替换 ≠ 断电持久化**。`os.replace` 只保证同卷目录项替换的原子可见性；是否在断电后仍存在取决于文件系统与目录/文件同步。未完成 fsync 或目录同步的步骤一律不得宣称已持久化。

**Windows / POSIX 持久化能力与失败处理（如实区分）**：

| 能力 | POSIX | Windows | 失败处理 |
|---|---|---|---|
| 文件 fsync | `os.fsync(file)` | `os.fsync(file)`（FlushFileBuffers 语义） | 临时文件 fsync 失败 → 不替换、不写 DB/ID；Journal fsync 失败 → 保持 PREPARED 并 fail-closed |
| 原子替换 | 同卷 `os.replace` 原子可见 | 同卷 `os.replace` 原子可见；目标被占用可能失败 | 失败 → 不继续后续步骤；不得原地截断写；不得重试掩盖 |
| 父目录同步 | 打开目录 `O_RDONLY` 后 `fsync` | Python 无可靠目录 fsync；仅能 best-effort，**不保证**目录项断电持久 | POSIX 失败 → fail-closed；Windows 记录 `dir_sync=unsupported/best_effort`，不得宣称断电持久；验收须标“有条件/待验证” |
| 断电后保证 | 取决于 FS；仍须真实取证 | 取决于 NTFS/磁盘缓存；**不保证** | 无真实断电测试证据时不得宣称通过；崩溃/进程终止一致性不等于断电持久性 |

**恢复优先级（Backend/CLI 启动与每次进入身份操作前，强制）**：

1. 取得既有 OS 单实例锁后，**先检查当前 Journal**；当前 Journal 是唯一活动操作记录。
2. **有效 `PREPARED MATERIALIZE` 必须先恢复**：按 `materialization_items` 逐项重查 DB，并校验 `identity_record_version`/`item_identity_digest`；DB 为空则幂等补写，等于 Journal 目标值则接受，存在其他值、Journal 损坏或摘要不一致则 fail-closed。随后必须从 DB **重新读取全部 `knowledge_item`/`ImportOrigin` 并重算 `identity_audit_digest`**，与预期完成态一致才可继续；不得只校验物化项或只信 Journal。
3. **有效 `PREPARED ROTATE` 同样先恢复**：按第 8 步重读 ID、重查 DB 物化清单，并从 DB 重算全库 `identity_audit_digest`；旧 ID/新 ID/其他 ID 按恢复表处理。
4. **`COMMITTED` 已写入但归档未完成时，只恢复归档，不重复写 DB**；归档前必须重读 DB 并重算全库 `identity_audit_digest`，与记录一致才允许归档；归档完成并校验后才就绪。
5. **恢复完成前禁止相关身份写入、MATERIALIZE/ROTATE/导出身份判定和新操作**；身份状态分类（1/2a/2b/3/4）只能在 Journal 恢复门通过后进行。
6. 当前 Journal 损坏、checksum/摘要不符、记录冲突或恢复失败：fail-closed，保持 Journal，不得分类、不得写身份、不得开新操作。

**Journal 生命周期与状态机（current vs archive）**：

- **当前 Journal**：`data/source-identity-journal.json`，同一时刻至多一个未归档操作。所有 `MATERIALIZE`/`ROTATE` 必须经**同一把进程内 Journal 互斥锁 + 既有 OS 单实例锁**串行，禁止并发写同一 Journal。**当前记录是唯一活动操作记录**；不得把归档记录当作 current 继续执行。
- **归档转换（COMMITTED 成功后）**：
  1. 校验当前记录：`phase=COMMITTED`、`journal_checksum`、`materialization_digest`、`identity_audit_digest` 与目标 ID 全部一致；其中 `identity_audit_digest` 必须由**重读全部 `knowledge_item`/`ImportOrigin` 后重算**得到，不得仅凭 Journal 自证；不一致 fail-closed。
  2. 写归档临时文件（与归档目标同目录、同卷），内容为当前 COMMITTED 记录；`fsync` 临时文件。
  3. 使用**同卷原子 rename**（`os.replace`/等价）将临时文件落到 `data/source-identity-journal.archive/<operation_id>.json`；随后同步归档目录。**不跨卷复制、不原地截断、不覆盖已有归档**。
  4. 若归档目标已存在：同 `operation_id` 且内容完全一致 → 视为同一逻辑记录已归档，不再覆盖；内容不一致 → fail-closed。
  5. 归档记录校验通过且目录同步完成后，才**幂等移除 current**；不得在归档落位前删除 current。current 的移除不是历史删除，历史保留在 archive。
  6. 归档写入/rename/同步失败，或 archive 与 current 冲突：**current 保留，禁止启动新操作**，等待重试或人工处理。
- **去重规则**：同一 `operation_id` 的 current 与 archive **同内容按一条有效记录计算**，不得计为两条匹配记录；异内容一律 fail-closed。身份状态 2b 的“恰好一条 COMMITTED MATERIALIZE”按去重后的唯一记录判定。
- **append-only**：`archive/<operation_id>.json` 仅 COMMITTED 成功后写入；完成后 append-only 保留，应用不自动删除；备份/恢复必须把归档与 DB 一并处理，缺失即 fail-closed。已归档操作的 `operation_id` 重入规则保持不变（同内容 no-op、异内容 fail、不得用旧 ID 发起新轮换）。

**归档崩溃点与恢复**：

| 崩溃点 | 磁盘状态 | 恢复行为 |
|---|---|---|
| COMMITTED 已写、归档临时文件写前 | current 为 COMMITTED；archive 不存在 | 重新校验并归档；**不写 DB** |
| 归档临时文件写/fsync 失败 | current 保留；临时文件可丢弃 | 保持 current，禁止新操作，重试归档 |
| 临时文件已写、rename 前 | current 保留；archive 不存在 | 丢弃/重建临时文件后重试；不写 DB |
| rename 后、归档目录同步前 | current + archive 均可能存在且同内容 | 校验并去重；同步目录后幂等移除 current；不写 DB |
| 归档目录同步后、移除 current 前 | current + archive 同内容 | 去重为一条；幂等移除 current；不写 DB |
| 移除 current 后 | archive 仅存 | 校验 archive 后就绪；不重复执行 |
| archive 已存在但内容冲突 | current + 冲突 archive | fail-closed，保留 current，禁止新操作 |
| 归档丢失且 current 已移除 | 无有效记录 | fail-closed；受影响文档按状态 4，禁止推断/自动重建 |

- **启动/进入导出/rotate 前**：取得既有 OS 锁后先执行 **Journal 恢复门**：无 current → 就绪；PREPARED → 按恢复表处理，未解决前不得开始新操作；COMMITTED → 校验后归档，归档成功后才就绪；current 损坏/校验和不符 → fail-closed。**历史 Journal** 只从归档读取；不得把归档当 current 继续执行。
- **`operation_id` 唯一性**：每次操作生成一个新 UUIDv4；归档文件名使用该 ID。相同 ID 的 current/归档若内容（kind/old/target/清单/校验和）不一致 → fail-closed；相同内容且已 COMMITTED → 幂等 no-op（不重复执行）；相同 ID 仍 PREPARED → 只做恢复。
- **重复执行保护**：请求的 `operation_id` 已归档且当前 exporter 已等于其 target → 返回已完成，不再次替换；当前 exporter 不等于 target → fail-closed，不重跑。**不得**用旧 operation_id 发起新轮换。
- **完成后的下一次独立 rotate**：COMMITTED 归档并校验成功后，允许以**新 operation_id** 发起下一次独立 rotate（old=当前 ID，target=新实例 ID）；上一次记录只作历史，不阻塞新操作。未归档/恢复未完成前不得开始第二次。
- **归档保留**：A1-04 不做自动清理；归档属于数据根，备份/恢复必须保留；缺失/损坏时受影响文档 fail-closed 为状态 4，不自动重建/认领。

**恢复状态表（取得 OS 锁后、执行任何导出/rotate 前）**：

| 当前 Journal | 实际 exporter ID / DB | 校验结果 | 允许动作 | 禁止 |
|---|---|---|---|---|
| 无 | 任意 | 状态预检通过 | 可开始新 MATERIALIZE/ROTATE；无证据的非空实例一律状态 4 | 从非空实例反推“已物化” |
| `MATERIALIZE PREPARED` | 无 ID 变更；DB 为空或已等于记录值 | 逐条重查 `materialization_items`：item 存在、无 `ImportOrigin`、值**为空或等于记录值**；v1 字段/版本/`item_identity_digest` 校验通过；**从 DB 重读全部知识文档及全部 ImportOrigin 原始记录并重算** `identity_audit_digest`，等于**预期完成态** | **逐条**处理：为空则幂等补物化，等于则接受，其他值冲突 fail-closed；全部满足后只补 COMMITTED+归档 | 覆盖其他实例值 / 用时间排序选记录 / 混合状态静默跳过 / 只算物化项或只信 Journal |
| `ROTATE PREPARED` | **等于旧 ID** | 重查 `materialization_items` 全部等于记录值、v1 字段/摘要/版本正确；**从 DB 重读全部知识文档及全部 ImportOrigin 原始记录重算** `identity_audit_digest`，结果未变；Journal 校验和正确 | 允许执行第 5–9 步（替换、重读、提交） | 跳过 DB 重查 / 只信 Journal 清单 / 引用不存在的字段 |
| `ROTATE PREPARED` | **等于目标新 ID** | 同上且 ID 完整 | **只补 COMMITTED+归档**，不再次替换 | 再次轮换 / 跳过 DB 重查 |
| `ROTATE PREPARED` | 既非旧也非新 | 任意 | **fail-closed**，保持 Journal | 猜测/覆盖未知 ID |
| `ROTATE PREPARED` | 任意 | DB 物化清单/摘要不符 | **fail-closed**，保持 Journal | 带缺陷提交 |
| `COMMITTED` | 等于 target | ID/Journal 校验通过；**重读全部知识文档及全部 ImportOrigin 原始记录重算** `identity_audit_digest` 与记录一致；archive 不存在或同内容 | 先归档并同步，再幂等移除 current；**不重复写 DB**；归档后可开新操作 | 重复执行同一操作 / 未归档即删除 current / 只凭 Journal 自证 DB |
| `COMMITTED` | 等于 target；current + archive 同内容 | 去重后一条记录；**重读 DB 重算摘要一致** | 视为同一逻辑记录；校验后归档/移除 current，不写 DB | 计为两条匹配记录 / 跳过 DB 重算 |
| `COMMITTED` | 等于 target；archive 内容冲突 | 任意 | **fail-closed**，保留 current，禁止新操作 | 覆盖 archive / 按时间挑一条 |
| `COMMITTED` | 不等于 target | 任意 | **fail-closed** | 自动重做/覆盖 |
| 损坏/校验和不符 | 任意 | 任意 | **fail-closed**，人工处理 | 删除后盲目重试 |

> **PREPARED + 旧 ID 的 DB 重校验**：不引用任何不存在的“物化清单字段”；只读取本 Journal 明确定义的 `materialization_items`，逐条重新查询 `knowledge_item` 与 `ImportOrigin`；并**读取全部知识文档及全部 ImportOrigin 原始记录**重算 `identity_audit_digest`，与 Journal 的**预期完成态值**比较。若记录声称物化但 DB 缺失/冲突或全库摘要不符，fail-closed，不继续替换。摘要匹配不能替代 COMMITTED 记录校验，Journal 记录也不能替代 DB 重读。

- **崩溃点覆盖**：Journal 写入前 → 无 Journal、无 DB/ID 写入；Journal PREPARED 后、DB 写前 → 恢复补物化；DB 提交后、COMMITTED 前 → 恢复校验后补提交；ID 替换后、COMMITTED 前 → PREPARED+新 ID，只补提交；COMMITTED 后、归档临时文件前/后、rename 后、目录同步后、移除 current 后 → 只恢复归档/去重，不重复写 DB；归档后 → 不重复。**每个恢复分支都必须从 DB 重读全部知识文档及全部 ImportOrigin 原始记录并重算 `identity_audit_digest`，不得只信 Journal 自身记录。** Journal 写失败不得替换 ID；COMMITTED 后同一操作不得重复执行；**恢复完成前不得做身份分类或新身份写入**。
- 并发：物化与 rotate 必须走与导入相同的 OS/身份锁/事务边界；**不得**在只读 S0 会话中写；单 Backend/单 worker 边界不变。

**与 D18 的关系**：D18 定义 source/document/exporter 语义；D23 只解决“本地原生文档尚无来源身份时如何初始化”，不改变 `DocumentIdentity` 定义、不改变 exporter 不落库、不改变导入幂等。DB 身份写入仍只用既有字段；Journal 是显式证据，不是新的来源身份字段。

### 22.3 D24：HTTP 本机安全边界（默认 loopback + 请求校验）

1. **默认绑定**：HTTP 默认监听 `127.0.0.1`。
2. **绑定允许集合**：仅允许**精确 IP** `127.0.0.1` 或 `::1`；**不接受 `localhost` 作为绑定配置**；`0.0.0.0`、`::`、LAN IP、主机名、含端口/协议/路径的值、解析失败值一律拒绝。**非 loopback 配置启动 fail-closed**（稳定码 `NON_LOOPBACK_WITHOUT_AUTH`）。
3. **Host 校验**：每个请求的 `Host` 必须是**精确本机 Host + 合法端口**。允许的本机 Host 形式为 `127.0.0.1`、`localhost`、`[::1]`（【提议】精确集合，端口须为合法十进制且与监听端口一致或为缺省端口）；拒绝后缀/前缀匹配、带尾点、含 userinfo、多 Host、非法端口、绝对形式 URI 绕过。
4. **Origin 校验**：对浏览器发起的修改请求（POST/PUT/PATCH/DELETE），若携带 `Origin`，必须与请求的 scheme + Host + port **精确同源**；跨源、`null`、畸形 Origin 一律拒绝（稳定码【提议】`CROSS_ORIGIN_REQUEST_REJECTED`）。不带 `Origin` 的非浏览器请求仍需通过 Host 校验与 JSON 约束，**不得**因此获得任何认证语义。
5. **修改接口 Content-Type**：修改接口只接受 `application/json`；`text/plain`、表单、JSONP、无 Content-Type 等一律拒绝（415）。请求体按既有大小限制处理。
6. **不开放宽泛 CORS**：不得配置 `Access-Control-Allow-Origin: *`、不得允许跨源携带凭据；不新增“方便调试”的宽泛 CORS 中间件。同源访问不需要 CORS 放行。
7. **代理头不授予访问权**：`X-Forwarded-For` / `X-Forwarded-Host` / `X-Forwarded-Proto` / `X-Real-IP` / 任意自定义转发头**不得**用于身份、Host/Origin 放宽或访问控制；Host/Origin 判定只用实际请求行与 `Host` 头。
8. **DNS Rebinding 防护**：攻击者域名解析到 `127.0.0.1` 时，请求的 `Host` 为攻击者域名，**必须**被规则 3 拒绝；不得因客户端源地址是 loopback 而放行伪造 Host。
9. **错误与日志**：拒绝响应只返回稳定错误码与简短原因，**不泄漏** host/port/密钥/堆栈/`str(exc)`；日志脱敏（AGENTS.md §9）。
10. **远程访问边界**：反向代理、隧道、端口转发仍属**额外暴露面**，**A1-04 不支持**任何无认证远程访问；loopback 监听不等于“已认证/可公网”。
11. **不新增认证依赖**：不实现账号、JWT、OAuth、会话或远程访问系统；不引入认证/网络新依赖。

**批次归属**：D24 的启动绑定校验、Host/Origin/Content-Type 校验与网络验收归 **Batch D**；**不得**因此阻塞 Batch A 的非附件导入/导出开发（D22/D23 归 Batch A）。

### 22.4 R1.3 文件/配置边界与禁改清单

| 层 | R1.3 允许的改动（开发阶段，additive） |
|---|---|
| backend 传输适配层（导入/导出） | 提取/剥离/注入 exporter 元数据；先算 Hash 后注入；保留键冲突拒绝；manifest 字段 |
| backend 身份初始化 | 本地原生状态 2a/2b/3/4 判定、**`ImportOrigin` 多记录状态判定表（`conflict` > `invalid` > `incomplete` > `duplicate` > `complete` > `none`；多合法身份对/DB 实例不一致即 conflict，冲突零认领）**、MATERIALIZE/ROTATE write-ahead Journal（既有 data 目录当前文件 + 完成归档）、Journal v1 schema/摘要/版本规则、`identity_audit_digest` 覆盖全部知识文档及**每项全部 `ImportOrigin` 原始记录（含残缺/重复/字段非法，按稳定记录 ID 排序，不归一化）**、孤儿 `ImportOrigin` fail-closed、每次写后/恢复时从 DB 重算、Canonical JSON v1 字符串规则与 8 组固定向量、启动恢复优先（PREPARED 先恢复、COMMITTED 只补归档）、current→archive 同卷原子落位与去重、物化前写 PREPARED、COMMITTED 后才导出、clone rotate 前逐条物化、既有字段读写、既有锁/事务复用；**不得**推断无证据的非空实例 |
| backend 配置/启动/HTTP 校验 | `api_host` 精确 IP 校验；Host/Origin/Content-Type 校验；拒绝宽泛 CORS；代理头不参与判定 |
| 文档与验收 | §22、acceptance §H、risk §14、open-decisions §L |

- **禁止**：新增 migration/table/column/index（Alembic 单 head 仍为既有版本）；改 Core Hash/canonicalization v1/codec；改 A1-03 链接规则；改 Core `ReviewService` 或端口；改 V1 `KnowledgeRepository`/`KnowledgeOut`/GET；加认证/网络依赖；改 `MILESTONES.md`；提交/推送；启动 Batch A。
- **不改变冻结契约**：D22–D24 均为 backend 适配/初始化/校验层设计，**不修订** A1-02/A1-03 的公开契约与测试断言。

### 22.5 R1.3 新增验收编号映射（全部【待验证】，详见 acceptance-matrix §H）

| 主题 | 决策 | 新增验收 | 批次 |
|---|---|---|---|
| exporter 不参与四类 Hash、先算后注入、保留键冲突 | D22 | `R1.3-HASH-01…04` | **Batch A** |
| 本地原生文档身份初始化（状态 2a/2b/3/4）、**ImportOrigin 多记录状态判定/冲突优先级/同身份多版本不算冲突**、MATERIALIZE Journal 显式标记、启动恢复优先与归档转换、Journal 数据契约 v1、`identity_audit_digest` 全库身份投影与 DB 重算、**全部 `ImportOrigin` 原始记录（含残缺/重复/非法）逐条审计、原始字段不归一化、读取顺序无关、孤儿 fail-closed**、Canonical JSON v1 字符串规则/测试向量、DB 字段信息不足不推断、legacy 不认领、FID-2 解析、ROTATE Journal/归档/多轮与崩溃恢复 | D23 | `R1.3-ID-01…05`（仅扩展 ID-02/03/05） | **Batch A** |
| 精确绑定、Host/Origin/JSON、无宽泛 CORS、代理头/重绑定防护 | D24 | `R1.3-NET-01…06` | **Batch D** |

> R1.3 仅新增上述 15 项；R1/R1.1/R1.2 编号全部保留、不重排；IMP-21…24、BAK-13/14 空号继续保留。

### 22.6 R1.3 阶段级冻结门禁与停止点

冻结前必须同时满足：

- 四份主文档已合并 D22–D24，**不是仅保留增补文件**；§21.1/§21.4/§21.5 的就地修正与 §22 一致。
- 术语与字段一致（`source_instance_id` / `source_document_id` / `source_payload_hash` 版本 / `exporter_instance_id` / `__explainlab_exporter_instance_id` / `DocumentIdentity`）；Hash 解耦、身份状态 2a/2b/3/4、ImportOrigin 多记录状态表与 `conflict` 优先级/身份不一致 fail-closed、DB 字段信息不足不推断、MATERIALIZE/ROTATE Journal 时序、启动恢复优先、current→archive 归档转换/去重、Journal v1 schema/摘要/版本、`identity_audit_digest` 覆盖全部知识文档及每项全部 `ImportOrigin` 原始记录且恢复必须重读 DB、原始字段不归一化/读取顺序无关/孤儿 fail-closed、Canonical JSON v1 字符串/代理项/重复键规则、Host/Origin 校验无相互矛盾。
- 编号唯一、交叉引用一致（§22.5 ↔ acceptance §H ↔ risk §14 ↔ open-decisions §L）；所有 R1.3 验收【待验证】。
- Batch A（D22/D23）与 Batch D（D24）边界清晰；**D24 不阻塞 Batch A**；四批独立出口不变。
- R1.2 §K.2 九项待决已在 open-decisions §L.2 关闭，历史 §K.2 原文保留；三个附件稳定码与 10 秒/`IMPORT_LOCK_TIMEOUT` 以 §L.2 为最终依据。
- Offline / Single / Strict 无冲突：无新迁移、单 Backend/单 worker、无认证不外露。
- 无新增 P0/P1 设计缺陷；用户明确批准 R1.3 决战后完成 ChatGPT 最终独立审计。
- 仍未验证：真实导出/导入 Hash 稳定性、重复/嵌套保留键冲突真实拒绝且零写入、身份状态 2a/2b/3/4 与 **ImportOrigin 多记录状态表（多合法身份对、完整+残缺、重复+不同身份、DB 实例不一致、同身份多版本）真实识别及冲突零认领**、启动恢复优先（PREPARED 先恢复、COMMITTED 只补归档、恢复前禁分类/写入）、Journal v1 schema/摘要/版本兼容、`identity_audit_digest` 全库覆盖（含每项全部 `ImportOrigin` 原始记录、残缺/重复/非法状态、孤儿 fail-closed、原始字段不归一化、读取顺序无关）与每次写后/恢复时 DB 重算、Canonical JSON v1 非 ASCII/引号/反斜杠/控制字符/补充平面/null/键序/重复键/孤立 surrogate 规则及 8 组固定向量、current→archive 同卷原子落位/去重/各归档崩溃点、MATERIALIZE Journal 物化与归档、ROTATE Journal 各崩溃点/多轮/同 operation_id 重入、Windows/POSIX 持久化差异、真实进程 Host/Origin/重绑定拒绝。**不得预先宣称通过；Windows 目录同步不保证断电持久，须如实标“有条件/待验证”。**

满足后才允许进入 Batch A；**本轮合并完成后停止，不启动 Batch A，不进入 A1-05/A2，不提交/推送**。
