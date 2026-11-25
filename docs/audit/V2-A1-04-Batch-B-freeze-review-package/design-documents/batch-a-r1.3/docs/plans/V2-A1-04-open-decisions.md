# ExplainLab V2 · A1-04 待决策事项与设计↔代码冲突清单

> 状态：**R1.3 架构裁决/决策台账稿**（R1 / R1.1 / R1.2 历史保留）。下列 R1.3/R1.2/R1.1/R1 决策已由 ChatGPT 提出为正式推荐，等待用户阶段级批准；未批准前仍不得开发。
> **R1 架构修订说明（2026-11-21）**：本文件已纳入 A1-04 第一轮独立技术核验后的架构裁决。本文原始章节中与文末「R1 权威修订」冲突的内容，以 R1 为准；R1 未覆盖的原设计继续有效。本文仍是**设计文件，不是实现或测试通过证明**。R1 修订未经用户阶段级批准前，不得据此启动业务代码开发。
> **R1.1 增补（2026-11-21）**：已追加 §J（R1.1 决策台账）；§D 的 D-13 旧选项已加注被取代。原 §H R1 裁决与历史记录保留，冲突以 **§J** 为准。配套 `implementation-plan` §20 / `acceptance-matrix` §F / `risk-register` §12。
> **R1.2 增补（2026-11-21）**：已追加 §K（R1.2 决策台账，D18–D21）；§D D-13 与 `implementation-plan` §19.9/§19.10/§20.2 已就地加注。原 §H/§J 与历史记录保留，冲突以 **§K** 为准。配套 `implementation-plan` §21 / `acceptance-matrix` §G / `risk-register` §13。**本轮仅文档合并，未写代码、未提交。**
> **R1.3 增补（2026-11-21）**：已追加 §L（R1.3 决策台账，D22–D24），并将 R1.2 §K.2 的**九项待决全部关闭**（原文保留为历史）。冲突以 **§L** 为准；配套 `implementation-plan` §22 / `acceptance-matrix` §H / `risk-register` §14。**本轮仅文档合并与最终审计有限修正，未写代码/测试、未新增迁移/依赖、未提交。** **第三轮定点修正**仅补 D23 的 Journal 恢复优先、current→archive 转换与 v1 数据契约；**第四轮最终审计修正**仅补 D23 的 `identity_audit_digest` 全库来源身份投影/DB 重算与 Canonical JSON v1 字符串/代理项/重复键/8 组固定向量；**第五轮最终定点修正**仅补 D23 每项全部 `ImportOrigin` 原始记录（含残缺/重复/非法）逐条审计、原始字段不归一化、读取顺序无关与孤儿 fail-closed；**第六轮最终冻结前定点修正**仅补 D23 的 **ImportOrigin 多记录状态判定表/互斥组合优先级/多合法身份或 DB 实例不一致的 conflict 零认领/同身份多版本不冲突**，不改 D22/D24、不新增验收/风险编号、不新增阶段修订。
> 【提议】仅为建议，**不得擅自把尚未确认的设计写成既定事实**。须 ChatGPT 阶段级独立审查 + 用户批准后方可进入实施。
> 配套：`V2-A1-04-implementation-plan.md`（任务依赖 §16 / 文件范围 §16.6）、`V2-A1-04-acceptance-matrix.md`（验收编号）、`V2-A1-04-risk-register.md`（风险编号）。
> 基线：HEAD `784b124`，分支 `fix/m0-admission-and-m5-regressions`，工作树干净（仅未跟踪 `docs/audit/V2-A1-03-final-stage-audit/`）。
> **重要区分**：design §7/§9 把部分事项标【待审批】，但其中一些**已在 A1-01/02/03 代码冻结**（见 §A），A1-04 **不得重开**；真正未决项见 §D。

---

## A. 已冻结 / 已实现事项（**非未决，A1-04 直接复用，不得重开**）

| 项 | 状态 | 代码证据 |
|---|---|---|
| canonicalization v1 序列化规则（紧凑 separators / datetime UTC 微秒 6 / Decimal 不经 float / 裸 float 禁用 / null≠缺失 / 语义序列表次级键 / 原始 Unicode 不 NFKC / 版本包络 / hashes_comparable） | **已冻结** | `knowledge-core/src/knowledge_core/markdown/canonical.py`（240 行）；A1-02 报告:75 |
| 三 Hash 字段定义（content=title+content；payload=完整交换；review=title?/content?/status?/space_id?） | **已冻结** | `markdown/__init__.py:352/371/384` |
| 全部 A1 表 + knowledge_item 4 新列（attachment/tag/item_tag/tag_change_log/gc_task/import_origin/storage_lock/knowledge_link） | **已建** | 迁移 `0006_v2_markdown_kb.py`；`models.py` |
| 全部 A1 Core 实体 + 端口契约 | **已建** | `domain/entities.py`（301 行）；`ports.py`（464 行） |
| 审计口径 C（tag_change_log append-only + item_id_snapshot/title_snapshot 删除后保留身份） | **已实现 schema** | `models.py:354` TagChangeLogORM；`entities.py:219` |
| 链接键规范化 v1（NFKC→strip→whitespace-fold→casefold；UNIQUE(source,key)；全局版本同构守卫无缓存） | **已实现** | `markdown/links.py`；`services/links.py` |
| 链接键重建执行（apply_link_key_plan 十步 + 门禁 A/B/C + P2 六字段 + 步 8c） | **已实现** | `services/links.py:309` |
| K1 治理链接挂接（governance 三入口×四动作 demote/sync/409 零写入） | **已实现** | `routes/governance.py:303/324/337` |
| K2 PG 窗口②关闭（LOCK TABLE SHARE ROW EXCLUSIVE + FOR UPDATE） | **已实现** | `db/locking.py` |
| SQLite 窗口② P2 兜底（六字段乐观前置 + no-op 复核） | **已实现** | `services/links.py` 步 7/8c |
| LinkImportRestorer（绑定优先 + 正文权威 D4 + 空间重算 + 孤儿/无效提示告警） | **已实现 Core** | `markdown/link_service.py:630`；`build_link_restorer`（links.py:537，注释「A1-04 导入路径预留」） |
| D10 重建报告落盘 | **已实现** | `services/links.py:519` persist_rebuild_report → backend/data/ops/ |

> **结论**：design §7.19/§9.20（序列化细则）、§9 审计口径、§2.5 schema **不再是未决项**。A1-04 复用，重开即违反红线 #5（不改 A1-01/02/03 业务）。

---

## B. A1-04 范围边界确认（须 ChatGPT 确认）

### D-01：导入审核防覆盖 / 撤回归属（A1-04 vs A1-05）

- **背景**：design §2.6 API 表列 `POST /reviews/{id}/withdraw`，§2.7 提「提案防覆盖」。但代码 `ReviewStatus`（entities.py:126）仅 PENDING/APPROVED/REJECTED，**无 WITHDRAWN**；`ReviewService`（review/__init__.py）**无 withdraw、无 _proposal_version、无 _review_payload_hash 防覆盖**；`review_payload_hash` docstring（markdown/__init__.py:392）明言「A1-05 集成」。A1-02 报告:183 明确防覆盖/撤回属 A1-05。
- **冲突**：design API 表与代码现状不一致（C-02）。
- **选项**：
  - (A)【提议】A1-04 导入**复用现有 submit(UPDATE_ITEM)→pending**，**不实现**防覆盖/撤回；批量重导可能产生多张 pending，ImportReport.warnings **如实记录此限制**；防覆盖/撤回/WITHDRAWN 留 A1-05。
  - (B) A1-04 提前实现防覆盖（**违反子批次边界 + 红线 #5 改 review 业务 + 范围蔓延**，不推荐）。
- **建议**：选 A。**须 ChatGPT 确认** A1-04 不含 withdraw/防覆盖，API 表该项从 A1-04 剔除。
- **影响**：R-IMP-03（多张 pending）；验收 IMP-06；A1-05 边界。

### D-12：A1-08 子批次归属澄清

- **背景**：A1-01 报告:112 提及端口实现属「A1-03/A1-04/**A1-08**」，存在 A1-06 之后子批次引用；A1-02 报告 §7 只列 A1-04/05/06。
- **选项**：(A)【提议】A1-04 边界以 A1-02 报告 §7 为准；A1-08 若存在属后续批次，A1-04 不承担。(B) 重新定义子批次。
- **建议**：选 A，**须 ChatGPT 澄清 A1-08 是否存在及其范围**，避免 A1-04 范围歧义。
- **影响**：任务分解完整性。

---

## C. 设计↔真实代码冲突（**只报告，未改代码**；用户要求指出文件/位置/影响/建议）

### C-01（关键）：KnowledgeRepository 不持久化 tags / extra_metadata / source_* 列

- **文件/位置**：`backend/app/services/knowledge.py`
  - `_to_entity`（28–48）：只映射 id/title/content/status/space_id/source_refs/created_at/updated_at。
  - `save`（57–80）、`update`（102–112）：**不写** tags/extra_metadata/source_payload_hash/source_content_hash/source_instance_id。
- **证据**：grep `extra_metadata|source_payload_hash|source_content_hash|source_instance_id|\.tags` 于 `backend/app` → **仅出现于 models.py**（列声明）+ import_origin ORM，无任何服务读写。`KnowledgeItem.tags`（entities.py:76）从 DB 加载恒空。
- **影响**：
  - 导入**无法经现有 KnowledgeRepository 落 extra_metadata**（未知 frontmatter 保真失败，IMP-02 必失败）。
  - **源身份冗余列不落** → 幂等权威 source_payload_hash 缺失（IMP-03/04 失败，R-IMP-02/R-COMP-05）。
  - tags 读恒空 → 导出 tags 丢失（IMP-16）。
  - 这是 A1-04 导入核心功能的**前置阻塞**。
- **建议（须决策 D-02，不擅自改）**：见 D-02 两选项。**本轮未改 knowledge.py**。

### C-02：design API 表 withdraw / 防覆盖 vs 代码无 WITHDRAWN

- **文件/位置**：design §2.6 API 表 `POST /reviews/{id}/withdraw`；`entities.py:126` ReviewStatus 无 WITHDRAWN；`review/__init__.py` 无 withdraw/防覆盖；`markdown/__init__.py:392` 标注 A1-05。
- **影响**：A1-04 若照 design API 表实现 withdraw 会越界 A1-05 + 改 review 业务（红线 #5）。
- **建议**：A1-04 剔除 withdraw/防覆盖（D-01 选 A）。**未改代码**。

### C-03：Core ReviewService 无链接钩子（钩子在 backend 路由层）

- **文件/位置**：`knowledge-core/src/knowledge_core/review/__init__.py`（`_apply_action`/`_apply_update` 无 demote/sync）；链接挂接在 `backend/app/api/routes/governance.py:303/324/337`（K1）。
- **影响**：A1-04 导入服务若直调 Core `ReviewService.submit/approve`，**绕过链接维护**（反链未降级/内容变更后未同步/409 未零写入）→ R-GOV-02。
- **建议（R1.1 已定）**：导入 Draft/Active approve 使用 **`LinkImportRestorer`**（target_id 优先 + 绑定优先 + 正文权威 D4 + 空间重算）；普通治理保持既有 K1（`sync_links_or_conflict` / `demote_backlinks_on_delete`），**不得对导入分支二次普通 sync**；版本异写 409 整事务零写入。**不改 Core ReviewService**（红线 #5 + A1-05 范围）。见 §J / D-03。

### C-04：design 称「SQLite（WAL）」但代码未启用 WAL

- **文件/位置**：design §6.1 称 SQLite WAL；`backend/app/db/session.py`（connect 事件）仅 `PRAGMA foreign_keys=ON` + `busy_timeout=5000`，**无 `journal_mode=WAL`**（rollback-journal）。
- **影响**：备份协议（§6）若依赖 WAL 快照语义须先确认；**不得为备份擅改全局日志模式**（影响 V1 全部事务/并发/备份）。
- **建议**：备份用 Online Backup API/VACUUM INTO（**不依赖 WAL**，rollback-journal 亦支持）；WAL 启用与否独立评估（D-09），**本轮不启用**。须 ChatGPT 确认备份不依赖 WAL。

### C-05：A1-03 报告延后项已被整改关闭（描述须更新）

- **文件/位置**：A1-03 报告 §6 标「门禁 C 残余并发窗口延后」「审核批准路径 demote/sync 延后」；但整改提交 `ccf6194`(K1+K2)/`b6c7e15`(P2)/`9634ad1`(no-op)/`784b124`(Phantom) **已关闭**：PG 窗口②表锁（locking.py）、SQLite 窗口② P2 六字段+步 8c（links.py）、governance approve demote/sync（governance.py）。
- **影响**：A1-04 设计**不得把这些描述为仍开放**；应复用已关闭机制，D 方向只评估活性不重开正确性。
- **建议**：本方案 §2.1.5/§8.3 已按**当前代码**描述（窗口②已关闭）。**未改代码**，仅纠正文档认知。

---

## D. 真正未决决策（须 ChatGPT + 用户拍板）

### D-02：extra_metadata / source_* / tags 持久化路径（**P0，C-01 前置**）

- **背景**：C-01 缺口。knowledge.py 属 M1 代码（非 A1-03，红线 #5 不直接保护，但改动须 V1 全量回归）。
- **选项**：
  - (A)【提议·保守】A1-04 导入服务**独立持久化路径**：导入/导出经 ORM 直写 extra_metadata/source_* 列，tags 经 TagRepository（set_item_tags/list_item_tags），**不改 M1 KnowledgeRepository**。优点：零 V1 回归风险；缺点：知识条目读写出现两条路径（V1 仓库 + A1-04 导入），须保证一致。
  - (B) **扩展 SQLAlchemyKnowledgeRepository**：_to_entity/save/update additive 映射 tags/extra_metadata/source_*。优点：单一路径；缺点：触碰 M1 代码，须 V1 全量回归（930 项），tags 读路径改变可能影响 V1 行为。
  - (C) 新增 A1-04 专用仓库（如 MarkdownItemRepository）封装完整映射，V1 仓库不动。
- **建议**：优先评估 A 或 C（保守，不动 M1）；若 ChatGPT 倾向单一路径则 B + 全量回归。**须用户/ChatGPT 拍板**。**未决前 IMP-02/03/16 不可宣称可用**。
- **影响**：R-COMP-05/R-IMP-02；导入核心功能；文件范围（是否改 knowledge.py）。

### D-03：导入链接挂接复刻方式（C-03）

- **背景**：K1 钩子在 backend 路由层，导入服务须复刻。
- **选项**：(A)【提议】抽取 governance.py 的 `_sync_links_after_content_change`/`_demote_backlinks_before_delete` 为**共享 helper**（additive，不改 A1-03 逻辑），导入服务复用。(B) 导入服务内联复刻同等逻辑。(C) 把钩子下沉 Core ReviewService（**违反红线 #5 + A1-05 范围，不推荐**）。
- **建议**：A（共享 helper，DRY，非 HTTP 也守同一门禁 R-GOV-06）。**须确认**抽取不破坏 governance 现有行为（回归）。
- **影响**：R-GOV-02/06；IMP-14/15/SQL-06。
- **R1.1 取代**：原“共享 helper / 内联复刻”方案**不作为导入恢复方案**；导入走 `LinkImportRestorer`，普通 K1 路径不变（见 §J 与 implementation-plan §20.3）。A/B 仅作历史记录，不再作为待决选项。

### D-04：StorageKeyLock / GC 参数与 TOCTOU 降级 acceptance

- **背景**：design §9.5 数值待用户定；SQLite 租约非严格互斥（ports.py docstring 诚实「降低而非消除 TOCTOU」）。
- **未决子项**：
  - 租约 TTL / 心跳间隔 / GC max_attempts / quarantine 安全等待期 / 孤儿扫描周期（具体秒数）。
  - **TOCTOU 降级 acceptance**：是否接受 SQLite 租约「降低非消除」+ verify fencing？严格互斥需求是否降级单写者/库级串行？
  - lease_token 单调来源（DB 自增 vs 时间戳 vs 计数器）。
- **选项**：(A)【提议】接受租约+fencing（每不可逆步骤 verify），严格互斥场景降级单写者；数值给默认建议待用户调。(B) 要求 SQLite 严格互斥→须 BEGIN IMMEDIATE/库级串行（**全局管线改动，独立审批**）。
- **建议**：A。**须用户拍板数值 + ChatGPT 确认 TOCTOU 降级可接受**。
- **影响**：R-CON-01/R-ATT-05/06；LCK/GC/ORP 验收；config 字段。

### D-05：显式绑定 archived/跨空间确认 + 运维 API 鉴权

- **背景**：bind_explicit（link_service.py:541）允许 archived/跨空间，返回告警；V1 无认证。
- **未决子项**：
  - 显式绑定 archived/跨空间是否须**显式确认参数**（如 confirm_cross_space=true）还是仅告警？
  - needs_manual / rebuild-keys / v2_downgrade 等运维端点鉴权（auth 批次未做）。
- **选项**：(A)【提议】archived/跨空间须确认参数 + 告警；运维 CLI 本地执行+确认门禁，HTTP 运维端点鉴权留 auth 批次，A1-04 **不宣称已鉴权**。(B) 仅告警不强制确认。
- **建议**：A。**须 ChatGPT 确认**确认参数语义 + 鉴权延后。
- **影响**：R-GOV-07；LNK-02/03/GC-11/OPS-03。

### D-06：批量导入 frontmatter 冲突默认策略

- **背景**：codec CONFLICT 态须用户主动 resolution（normalize/keep_original），不静默再生（markdown/__init__.py:459）。
- **选项**：(A)【提议】批量默认 **keep_original + 告警 + 记 conflicts**（保守，不丢未知）；单篇可交互 resolution。(B) 批量默认 normalize（**可能丢未知字段，不推荐**）。(C) 冲突篇跳过（errors/skipped）。
- **建议**：A 或 C（保守）。**须用户拍板**批量冲突默认行为。
- **影响**：IMP-12；ImportReport.conflicts。

### D-07：批量导出打包形态

- **背景**：design §2.6 POST /knowledge/export 批量。
- **选项**：(A)【提议】zip 包 + manifest.json（含各 content_hash/storage_key 清单）。(B) 目录结构。(C) multipart。
- **建议**：A（zip+manifest，便于跨实例导入幂等）。**须确认**打包形态 + manifest 字段。
- **影响**：IMP-17；导出 DTO。

### D-08：附件 MIME 白名单 / SVG 策略 / 大小上限

- **背景**：design §2.5 MIME 白名单+magic bytes；SVG 待审批；默认 10MB。
- **未决子项**：白名单具体 MIME 列表；SVG deny_inline vs 消毒（消毒需 DOMPurify，**A2 未审批不引**）；大小上限默认值。
- **选项**：(A)【提议】白名单常见图片/文档（png/jpeg/gif/webp/pdf/txt/md/csv 等，**具体列表待定**）；SVG **deny_inline**（A1-04 不消毒，A2 渲染再议）；默认 10MB 可配。
- **建议**：A。**须用户拍板白名单 + SVG 策略 + 上限**。
- **影响**：R-SEC-03/04/05；ATT-03/04/05；config。

### D-09：备份位置/保留 + Manifest 持久化 + WAL/busy_timeout（**含红线 #2 触发**）

- **背景**：C-04（无 WAL）；design §6 备份/Manifest；红线 #2 不新增迁移。
- **未决子项**：
  - 备份位置 / 保留份数。
  - **Manifest / 附件版本指针 / migration_ops_log 持久化**：文件（backend/data/ops/，**无新迁移**）vs DB 新表（**触发红线 #2，须独立审批本轮不建**）。
  - WAL 是否启用（C-04）；busy_timeout 5000 是否调整。
- **选项**：(A)【提议】Manifest/指针/migration_ops_log **全用文件**（fsync，仿 persist_rebuild_report），**无新迁移**；备份用 Online Backup/VACUUM INTO（不依赖 WAL）；**WAL 不启用、busy_timeout 不调**（避免全局管线改动）。(B) DB 新表持久化→**升级独立审批，本轮不建**。
- **建议**：A（守红线 #2 + 不擅改全局）。**须 ChatGPT 确认文件持久化足够 + 用户定备份位置/保留**。
- **影响**：R-COMP-01/R-FS-05/R-CON-07；BAK/GRD-08；SQL-03/04/05。

### D-10：目标部署平台（Windows vs POSIX）+ 同卷假设

- **背景**：design §10.1 Windows 兼容（占用/os.replace/指针/跨卷非原子）。
- **未决子项**：目标部署平台（决定 Windows 兼容是否须真实取证）；隔离区与存储根**同卷假设**是否成立（跨卷降级）。
- **选项**：(A)【提议】开发/验收在 Windows（当前环境 win32）真实取证占用/指针/退避；生产平台待定；同卷假设默认成立，跨卷降级标注非原子。(B) 仅 POSIX（Windows 兼容延后）。
- **建议**：A（当前 win32，须真实 Windows 取证 BAK-08/09/10）。**须用户确认目标平台 + 同卷部署**。
- **影响**：R-DL-07/08；BAK-08/09/10；不得宣称跨平台原子已验证。

### D-11：链接键规范化 v2 是否发布

- **背景**：A1-03 v2 fixture-only，**未发布**；LINK_KEY_RULES{1:v1}。
- **选项**：(A)【提议】A1-04 **不发布 v2**；rebuild-keys 支持 target_version 参数但 v2 规则未定义→**拒绝**（CapabilityNotSupported 语义）。(B) A1-04 定义并发布 v2（**范围蔓延 + 改 A1-03 业务，不推荐**）。
- **建议**：A。**须 ChatGPT 确认** v2 延后。
- **影响**：LNK-06；rebuild-keys 参数校验。

### D-13：source_instance_id 生成（V1 无实例 id）

- **背景**：design §9.17；ImportOrigin.source_instance_id（entities.py:285）；V1 无实例标识。
- **选项**：(A)【提议】config 新增 source_instance_id（默认 None）；导出时若配置则写入 frontmatter，跨实例导入据此判跨实例→默认 Draft；未配置→None，幂等仅靠 source_payload_hash。(B) 自动生成 UUID 实例 id（须持久化位置，可能触发新表/配置）。
- **建议**：A（config 可选，不强制）。**须用户确认**实例 id 来源与是否必填。
- **R1.1 取代**：上述 A/B 选项已由 **R1.1 D-13/§J** 的生命周期取代（实现见 implementation-plan §20.2）：稳定 UUID 文件、锁后首启原子生成、损坏 fail-closed、备份保留、clone 显式 rotate。A/B 仅作历史记录，**不再作为待决选项**。
- **影响**：IMP-09；config；跨实例幂等。

### D-14：PG advisory hashtext 碰撞处置

- **背景（原方案）**：原设计使用 `hashtext(storage_key)` 32-bit advisory key；R1 改为 SHA-256 前 64-bit 派生 bigint key，避免低熵哈希。
- **选项**：(A)【提议】接受 hashtext 碰撞概率（不同 key 偶共享锁→**仅降低并发度不致误删**，因引用复核仍按精确 storage_key COUNT）；记录局限。(B) 用 64-bit 双 hashtext 或精确 key 锁表（更复杂）。
- **建议**：A（碰撞只影响互斥粒度，正确性由持锁精确 COUNT 复核保证）。**须 ChatGPT 确认**碰撞不影响正确性论证。
- **影响**：LCK-02/PG；R-CON-01。

---

## E. 全部未决决策汇总（供审查勾选）

| 编号 | 决策 | 优先级 | 须谁确认 | 阻塞项 |
|---|---|---|---|---|
| D-01 | 导入防覆盖/撤回属 A1-05，A1-04 复用 submit | P0 | ChatGPT | 范围边界 |
| D-02 | extra_metadata/source_*/tags 持久化路径（C-01） | **P0** | ChatGPT+用户 | **导入核心功能** |
| D-03 | 导入链接挂接复刻方式（C-03） | P0 | ChatGPT | 治理不绕过 |
| D-04 | StorageKeyLock/GC 参数 + TOCTOU 降级 | P1 | ChatGPT+用户 | 并发正确性 |
| D-05 | archived/跨空间确认 + 运维鉴权 | P1 | ChatGPT | 治理/安全 |
| D-06 | 批量 frontmatter 冲突默认策略 | P1 | 用户 | 导入保真 |
| D-07 | 批量导出打包形态 | P2 | ChatGPT | 导出 DTO |
| D-08 | MIME 白名单/SVG/大小上限 | P1 | 用户 | 附件安全 |
| D-09 | 备份位置/Manifest 持久化/WAL/busy_timeout | P0 | ChatGPT+用户 | **红线 #2**/备份 |
| D-10 | 目标平台 + 同卷假设 | P1 | 用户 | Windows 取证 |
| D-11 | 规范化 v2 是否发布 | P2 | ChatGPT | rebuild-keys |
| D-12 | A1-08 子批次归属 | P2 | ChatGPT | 范围 |
| D-13 | source_instance_id 生成 | P1 | 用户 | 跨实例幂等 |
| D-14 | PG hashtext 碰撞处置 | P2 | ChatGPT | PG 锁 |

> **P0 决策（D-01/02/03/09）未拍板前，A1-04 不得进入对应模块开发**。尤其 D-02（C-01）未决则导入保真/幂等不可用；D-09 未决则备份持久化可能触发红线 #2。
> **R1.1 状态**：本表为 Request I 待决快照，**已被 §H（R1）与 §J（R1.1）取代**；D-03 已定为 `LinkImportRestorer`、D-13 已定为实例 ID 生命周期。本表仅作历史记录，不作为待决依据。

---

## F. 任务依赖 / 实施顺序 / 文件范围（索引至 implementation-plan §16）

> 完整内容见 `V2-A1-04-implementation-plan.md` §16，此处汇总供审查：

- **任务分解**：T4-01…T4-16（配置骨架→V2 仓库+storage_lock→持久化路径(D-02)→Core 编排→Vault 导入导出→附件上传→GC→孤儿扫描→API(A/B)+链接 ops→备份→ops CLI→故障注入/Windows+D 评估→全量回归验收）。
- **可合并实施**：T4-02+03（db 适配层）；T4-07+08+09（附件/GC/孤儿强耦合）；T4-10+11（API additive）；T4-13+14（备份+故障注入）。
- **须独立验收高风险模块**：GC+quarantine+孤儿扫描（T4-08/09）、StorageKeyLock 双方言（T4-03）、备份恢复+Manifest 对账（T4-13/14）、导入审核门禁+K1 挂接（T4-06）、链接键重建写端点（T4-11）。
- **预计文件范围**：新增约 20+ 文件（Core markdown/service.py+import_report.py+可选 attachments/planning.py；backend db/storage_lock.py、services/{attachments,markdown,backup,repositories_v2}.py、ops/{rebuild_link_keys,v2_downgrade}.py、routes/{import_export,attachments,tags}.py + 双方言测试）；additive 修改 links.py/schemas.py/config.py/dependencies.py/main.py（+ 若 D-02 选 B 则 knowledge.py）。**禁改** A1-02/03 业务、review/__init__.py、迁移 0006、locking.py A1-03 逻辑、现有测试、MILESTONES.md、M0 初始提交。
- **无新迁移**（红线 #2）：0006 已建全部 A1 表/列；Manifest/指针/migration_ops_log 优先文件持久化（D-09）。

---

## G. 停止点与审查请求

本文件与其余三份材料构成 A1-04 **完整设计交付**。本轮：

- ✅ 完成 9 项调查（Git/审计一致性/ORM 迁移端口/CRUD 审核链接链/附件现状/存储配置/测试夹具双方言/依赖必要性/子批次边界）。
- ✅ 输出四份设计材料（implementation-plan / acceptance-matrix / risk-register / open-decisions）。
- ✅ 给出任务依赖、实施顺序、可合并工作、独立验收高风险模块、文件范围、全部未决决策。
- ✅ 报告设计↔代码冲突 C-01…C-05（**未改代码迎合设计**）。
- ✅ 明确标出不可逆数据安全问题（risk-register §10 五项）。
- ❌ **未写业务代码、未新增迁移、未装依赖、未改测试、未改 A1-01/02/03 业务、未改 M0/历史、未 commit/push、未进入 A1-05/A2、未改 MILESTONES、未把设计写成已实现、未编造测试结果**。

**现停止，等待 ChatGPT 阶段级独立审查 + 用户对 §E 决策（尤其 P0：D-01/02/03/09）拍板。不开始 A1-04 代码开发。**

---

## H. R1 架构裁决（取代本文件中与之冲突的旧待决项）

> 状态：**ChatGPT 架构设计裁决，等待用户批准**。用户已明确产品约束：备份 Offline、部署 Single、迁移 Strict。以下将其落实为可执行设计。

| 决策 | R1 裁决 | 原因/边界 | 状态 |
|---|---|---|---|
| D-01 | A1-04 不实现 proposal 防覆盖、withdraw、WITHDRAWN；归 A1-05 | 不改 Core ReviewService，不扩大子批次 | 建议批准 |
| D-02 | 选 C：独立 MarkdownItemRepository，完整映射 extra_metadata/source_*；tags 经 TagRepository；V1 KnowledgeRepository 不改 | 防止 V1 PATCH 默认 `{}` 清空导入 metadata | 建议批准 |
| D-03 | 导入路径使用 LinkImportRestorer；Active approve hook 替代普通 sync；普通治理路径保持现有 K1 helper | 保留 target_id 优先语义，避免双重解析 | 建议批准 |
| D-04 | SQLite keyed lock + storage_lock lease/fencing；PG 64-bit advisory lock；默认 TTL 60s/heartbeat 15s/lock wait 10s | 单实例为主互斥，DB lease 为崩溃恢复/纵深防御；不宣称外部多实例严格互斥 | 建议批准 |
| D-05 | archived/跨空间显式绑定要求 confirm 参数；全局破坏性操作只走本地 CLI，不新增无认证 HTTP 运维写入口 | 当前无认证体系，不扩大攻击面 | 建议批准 |
| D-06 | 批量遇 frontmatter CONFLICT 默认跳过该文档并记录 conflicts；单篇可显式 resolution | 不静默 normalize/丢未知字段 | 建议批准 |
| D-07 | 批量导出采用 ZIP + manifest.json | 可校验内容与附件清单 | 建议批准 |
| D-08 | MIME allowlist：PNG/JPEG/GIF/WebP/PDF/TXT/MD/CSV；SVG 拒绝上传；单文件默认 10 MiB；magic bytes + 文本 UTF-8 校验 | 不引入消毒依赖，不允许主动内容执行 | 建议批准 |
| D-09 | Offline CLI；Manifest/journal/checksum 文件持久化；SQLite Online Backup API；PG pg_dump custom；不启 WAL、不改 busy_timeout；备份默认 BACKEND_DIR/backups，保留最近 5 个有效包 | 不新增表/列，不在线 quiesce | 建议批准 |
| D-10 | Windows 为必须真实验收平台；POSIX 保持兼容；活动附件根与 quarantine 同卷；跨卷仅可 copy+verify，绝不宣称原子 | 当前主要开发环境为 Windows | 建议批准 |
| D-11 | 不发布 link normalization v2；继续使用 A1-03 冻结 v1 | 不重开 A1-03 | 建议批准 |
| D-12 | A1-04 以 A1-02 §7 范围为准；A1-08 不纳入本阶段 | 防止范围蔓延 | 建议批准 |
| D-13 | 首次启动生成稳定 UUID，写入 `backend/data/source-instance-id`；导出携带；备份恢复保留；显式 clone 时须运行 rotate-instance-id CLI | 避免长期 None 导致跨实例身份混淆；文件持久化不需迁移 | 建议批准 |
| D-14 | PG advisory key 使用 SHA-256 前 64-bit 派生 bigint；碰撞只增加串行，不替代精确 key 复核 | 避免 32-bit hashtext 低熵 | 建议批准 |
| D-15 | 接受单实例，不新增 ImportOrigin 唯一约束；来源身份 keyed lock + S0/S1 快照重读 + 同事务写入 | 多实例 DB 强制幂等需要迁移，Strict 策略不允许 | **P0 建议批准** |
| D-16 | Active ImportOrigin-at-approve；pending 记录在 ReviewRequest.payload 的 `__a1_import` envelope；同 hash pending 复用，不同 hash pending 阻止新导入 | 无 status 列/唯一约束时避免假 origin 和重复 pending | **P0 建议批准** |
| D-17 | 单 Backend/单 worker + OS 进程锁；Backend lifespan 持锁，Offline maintenance CLI 使用同一锁；Backend 活跃时维护命令拒绝 | Single 部署可验证、无在线维护模式 | **P0 建议批准** |

### H.1 D-15 来源身份锁与幂等的精确定义

1. 锁键为 `(source_instance_id, source_document_id)`，不是 `source_payload_hash`。来源内容变更不应产生另一把锁。
2. `source_payload_hash` 是来源版本标识；`ImportOrigin` 记录已成功应用的版本历史，item.source_payload_hash 是当前已应用版本的冗余指针。
3. 请求在锁前读取 S0，获得 keyed lock 后重读 S1。若状态发生变化且 incoming hash 未被应用/挂起，则返回 `SOURCE_CHANGED_DURING_WAIT`，不自动覆盖。
4. 同一身份关联多个 item_id 时拒绝 `SOURCE_IDENTITY_AMBIGUOUS`。
5. 单实例进程锁 + 进程内 keyed lock 是并发保证；不把非唯一索引说成唯一约束，不支持多实例写。

### H.2 D-16 Active Review 生命周期

- submit 时 ReviewRequest.payload 存 `__a1_import` envelope；Core 继续只应用四字段。
- pending 阶段不写 ImportOrigin，不写正式附件引用；附件落 import-staging。
- 同 identity + 同 hash pending：复用现有 ReviewRequest。
- 同 identity + 不同 hash pending：返回 `SOURCE_HAS_PENDING_IMPORT`，不新增 pending。
- approve：backend hook 在首次 commit 前应用 tags/extra_metadata/attachments/source identity/ImportOrigin/LinkImportRestorer；失败整事务 rollback。
- reject：不写 origin、不改 item；commit 后清理 staging，失败由 staging orphan sweep 回收。
- `review_payload_hash` 仍只覆盖 Core 四字段；不得宣传它保护导入 envelope。envelope digest 只做一致性检查，不作为权限/签名边界。

### H.3 D-17 Offline Maintenance 与进程锁

- Backend lifespan 获取 OS 锁并持有至进程退出；Windows msvcrt，POSIX fcntl。锁文件不删除，避免 inode/句柄竞争。
- Backup/restore/v2_downgrade/全局 rebuild 等维护 CLI 必须获取同一锁。Backend 未停止时 CLI fail closed；CLI 运行时 Backend 不可启动。
- Offline 备份不需要在线请求排空、维护 API 或多实例协调器。PostgreSQL 服务保持运行，但所有应用外写者必须停止。
- `--reload` 必须由 worker 获取锁；生产只允许一个 worker。真实 Windows 进程测试通过前不得宣称锁机制完成。

### H.4 Offline Restore 安全顺序

1. 获取维护锁；验证备份 COMPLETE、Manifest、全部 checksum。
2. 在 staging 恢复数据库并验证 schema head/必要不变量。
3. 将备份中的 attachments、quarantine、import-staging 按相对路径合并到现存存储；同路径 hash 不同即中止；只增加/校验，不覆盖、不删除当前 blob。
4. 数据库最后切换：SQLite 关闭句柄后原子替换 DB 文件并保留 previous；PG restore staging DB，**按 implementation-plan §20.5 BAK-1 清场（维护库 / 禁新连接 / terminate / `pg_stat_activity` 清零 / 失败恢复）后** rename target→previous、staging→target。
5. 写 journal 完成标记；通过 SQLite hash 或 PG database OID 与真实资源对账。崩溃后由 recover CLI 对账，不盲信 phase。
6. 旧 DB/旧备份保留，确认恢复成功后才允许后续保留策略清理。

### H.5 旧 D 项处置

- D-04/D-05/D-06/D-07/D-08/D-09/D-10/D-11/D-12/D-13/D-14 由上表给出 R1 推荐值，等待用户整体批准；用户无需逐条重复回答。
- D-02 原 A/B/C 选项收敛为 C。
- D-03 原共享普通 sync helper 方案不作为导入恢复方案；导入走 LinkImportRestorer，普通 K1 不变。
- 原文关于“按 item 串行（PG 行锁 / SQLite 唯一约束）”“多实例跨实例导入幂等测试”“在线 quiesce/多实例编排”的描述全部以 R1 为准。

---

## I. R1 停止点

四份文档已按同一决策集修订，但仍属于**待用户批准的设计修订稿**。未获批准前不得启动 A1-04 业务代码开发；获批后 Qoder 仅按冻结设计实施，不自行改变架构决策。

---

## J. R1.1 决策台账（合并 R1.1 增补，权威）

> 来源：`docs/plans/A1-04/R1.1-amendment/` 内 `V2-A1-04-open-decisions-R1.1-ledger.md`（SHA256SUMS 已核验）。
> 用户已确定：**Offline backup / Single deployment / Strict migration**。R1 其余未受本轮影响的裁决继续沿用。本节**不把设计建议伪装成用户已批准**；§E（原待决表）与 §H（R1 裁决）作为历史记录保留，与本节冲突处以 **§J** 为准。

### J.1 R1 审计条件处置

| 审计项 | R1.1 决策 | 状态 |
|---|---|---|
| D16-1/FID-1 V1 GET 恒空 V2 字段 | **V2-only read contract**；不扩展 V1 DTO/GET；V2 统一走 `MarkdownItemRepository` + `TagRepository` | ChatGPT 架构裁决，待用户批准 |
| G-4/D-13 instance-id 生命周期 | 首启 UUID、重启稳定、备份保留、clone rotate、损坏 fail-closed | 已补设计，待用户批准/测试 |
| D17-1 reload 锁交接 | worker 持锁 + 10s 有界退避；超时 fail-closed | 已补设计，待用户批准/测试 |
| D15-2 submit/approve 锁 | 同一身份键锁；approve 获锁后 fresh session 重读并同事务应用 | 已补设计，待用户批准/测试 |
| D15-3 S0/S1 时序 | S0 只读会话关闭→keyed lock→S1→写事务 | 已补设计，待用户批准/测试 |
| D17-2 绝对锁路径 | `BACKEND_DIR.resolve()` 派生唯一锁路径 | 已补设计，待用户批准/测试 |
| D17-3 跨平台抽象 | msvcrt/fcntl 统一排他 acquire/release | 已补设计，待用户批准/测试 |
| FID-2 source hash 来源 | ImportOrigin 查历史版本；MarkdownItemRepository 查当前来源指针 | 已补设计，待用户批准/测试 |
| BAK-1 PG 清场 | maintenance DB + ALLOW_CONNECTIONS false + terminate + `pg_stat_activity` 清零 + fail-closed | 已补设计，待真实 PG 验证 |
| G-1…G-11 | 新增 R1.1-IMP-32…42、R1.1-LOCK-09…13、R1.1-BAK-15…19、R1.1-OPS-06、R1.1-SQL-10、R1.1-LNK-14 | 已补验收，全部【待验证】 |

### J.2 需要用户阶段级确认（5 项）

1. 接受 D16-1 采用 **V2-only read contract**（不改变 V1 API）。
2. 接受 source-instance-id 在逻辑实例生命周期内必需且**不可静默重建**；克隆必须显式 rotate。
3. 接受 `--reload` 锁交接有界等待 **10 秒**，超时 fail-closed。
4. 接受导入 approve 必须参与与 submit **相同身份键锁**，并使用 fresh session 重读。
5. 接受 PG rename 前必须**清空目标库所有连接**；权限/后台进程无法清理时中止恢复。

### J.3 继续沿用的 R1 决策

- D-01：proposal 防覆盖/withdraw/WITHDRAWN 归 A1-05。
- D-02：独立 MarkdownItemRepository；V1 KnowledgeRepository 不改。
- D-03：导入使用 LinkImportRestorer；普通治理 K1 路径不变。
- D-04：SQLite lease/fencing + PG 64-bit advisory；不宣称跨主机互斥。
- D-05：archived/跨空间显式确认；全局破坏性操作本地 CLI；无认证 HTTP 运维写入口。
- D-06：批量 frontmatter CONFLICT 默认跳过并记录 conflicts。
- D-07：批量导出 ZIP + manifest.json。
- D-08：PNG/JPEG/GIF/WebP/PDF/TXT/MD/CSV 白名单；SVG 拒绝；默认 10 MiB。
- D-09：Offline CLI；Manifest/journal/checksum 文件；SQLite Online Backup API；PG pg_dump custom；不启 WAL、不改 busy_timeout；`BACKEND_DIR/backups`，保留最近 5 个有效包。
- D-10：Windows 必须真实验收，POSIX 兼容；attachments/quarantine 同卷；跨卷不宣称原子。
- D-11：不发布 link normalization v2。
- D-12：A1-08 不纳入 A1-04。
- D-13：稳定 UUID 文件，导出携带，备份恢复保留，clone 显式 rotate。
- D-14：PG advisory key 由 SHA-256 前 64-bit 派生；碰撞只额外串行，精确 storage_key COUNT 仍权威。
- D-15：单实例应用层幂等；身份键 keyed lock + S0/S1 + 同事务；不新增 ImportOrigin 唯一约束。
- D-16：ImportOrigin-at-approve；pending envelope；同 hash pending 复用，不同 hash pending 拒绝。
- D-17：单 Backend/单 worker/OS 进程锁；Offline CLI 同锁。

### J.4 合并时补充的术语与边界澄清

- **严重度口径**：R1.1 增补用 `P1` 表示高优先级风险，等同本册「高」，须开发阶段真实并发/崩溃/平台取证；不表示「已接受」。
- **D16-1 取代**原 §3.3「KnowledgeOut 增 tags/extra_metadata 读字段」；全文不得再有 V1 GET 暴露 V2 字段的表述（implementation-plan §20.1）。
- **D-13 取代**原 A/B 选项（本文件 §D D-13 已加注）；旧选项仅历史记录。
- **BAK-1 的 `ALTER DATABASE ALLOW_CONNECTIONS`** 属运维运行时设置、失败即恢复，**非 schema 迁移**，不违反 Strict migration。
- **编号规范**：R1.1 增补中的裸编号在四份主文档内统一加 `R1.1-` 前缀（如 `R1.1-IMP-25`）；R1 既有 `R1-*` 编号不变；IMP-21…24 保留空号。
- **三约束一致性**：Offline（备份/恢复/降级仅 CLI + 同 OS 锁）、Single（单 Backend/单 worker/单数据根）、Strict（无新迁移、无新表列）在 §H/§J 决策下无冲突；§20.7 汇总。

### J.5 设计冻结门禁（R1.1）

冻结前必须同时满足：

- 四份主文档（implementation-plan / acceptance-matrix / risk-register / open-decisions）已合并 R1.1，**不是仅放入增补文件**。
- 所有编号、术语、事务顺序、交叉引用一致（见各文件 §20 / §F / §12 / §J）。
- 所有新增验收进入 acceptance-matrix §F 并标 **【待验证】**；风险入 risk-register §12；决策入本节 §J。
- Qoder 只读复核无新增 P0/P1 缺陷（本报告 §5）。
- 用户明确批准 R1.1 五项（§J.2），并完成 ChatGPT 阶段级独立审计。

满足后才启动 Batch A；**本轮不启动**。

---

## K. R1.2 决策台账（D18–D21，权威）

> 来源：ChatGPT R1.2 架构决策（2026-11-21）。用户已确定 **Offline backup / Single deployment / Strict migration**；R1/R1.1 未受本轮影响的裁决继续沿用。本节**严格区分「已由 ChatGPT 裁决（待用户批准）」与「仍需用户拍板的细节」**，不把设计建议伪装成已批准或已实现。
> 原 §E（待决快照）、§H（R1）、§J（R1.1）作为历史记录保留；与本节冲突处以 **§K** 为准。

### K.1 R1.2 已裁决事项（待用户阶段级批准）

| 决策 | R1.2 裁决 | 与既有决策关系 | 状态 |
|---|---|---|---|
| **D18** 文档身份模型 | `source_instance_id`=原来源实例、`source_document_id`=稳定来源文档、`exporter_instance_id`=本次导出实例；`DocumentIdentity=(source_instance_id, source_document_id)`；导出仅在 frontmatter/manifest 写 exporter，**不新增 DB 字段**；导入/修改/再导出不覆盖来源身份；clone 只 rotate exporter、不批量改写继承文档来源；同来源不同版本进入既有冲突机制；legacy 不伪造 UUID、content_hash 查重 + 默认 Draft + 显式 target | **扩展** R1.1 D-13/§20.2：原 `data/source-instance-id` 明确为 exporter 身份；不改变 D-13 生命周期 | ChatGPT 裁决，**待用户批准** |
| **D19** 批次依赖调整 | Batch A=导入/导出/来源/身份锁/审核核心/链接恢复（**不含附件完整导入导出**），含附件请求显式拒绝/标 unsupported；Batch B=附件上传下载/staging/approve 附件整合/StorageKeyLock/GC/quarantine/孤儿扫描，完成附件+Active approve 全事务闭环；Batch C=Offline Backup/Restore/Manifest/checksum/DB 切换/崩溃恢复；Batch D=用户 API/运维 CLI/网络边界/全量回归与交付；四批各自独立出口 | **取代** `implementation-plan` §19.9 原批次范围与验收归属；不改变 R1/R1.1 验收编号 | ChatGPT 裁决，**待用户批准** |
| **D20** 同步事务执行模型 | 导入/批量导入/approve 写入口用 FastAPI 同步 `def` 路由（线程池）；`ImportCoordinator` 统一同步身份锁；Session 在实际执行线程内创建/使用/关闭；S0 读后关闭→获锁→S1 重读→写事务；锁覆盖完整事务，Commit/Rollback+清理后才释放；断连不提前释放；有界等待 fail-closed；**禁止 async keyed lock + threading.Lock 双架构** | **取代** R1.1 §19.10 的 async 机制；保留“不阻塞 event loop / Session 不跨线程 / 取消不提前释放”属性；`R1.1-SQL-10` 保留为属性回归 | ChatGPT 裁决，**待用户批准** |
| **D21** HTTP 网络边界 | 默认监听 `127.0.0.1`；无认证时拒绝非 loopback 配置（fail-closed）；CORS/任意代理转发头不是认证；反向代理/隧道/端口转发为额外暴露面，loopback 不解决其安全问题；增加配置校验、风险说明、网络测试；不新增认证依赖 | **新增维度**（R1/R1.1 未覆盖）；与 D-05“无认证、不新增 HTTP 运维写入口”一致并强化 | ChatGPT 裁决，**待用户批准** |

### K.2 R1.2 待决快照（已由 R1.3 §L.2 关闭，历史保留）

> **R1.3 状态注记（2026-11-21）**：以下 9 项**已由 R1.3 §L.2 全部裁决/关闭**；本列表保留为 R1.2 历史快照，不再作为待决项。当前待决与冻结门禁见 §L。

1. **D18 身份语义**：接受 source/document/exporter 三元分离与 `DocumentIdentity`；接受 legacy/未知来源**不伪造身份**、content_hash 查重 + 默认 Draft + 显式 target 的兼容规则（具体报告字段与提示语待定）。
2. **D18 clone/adoption**：接受 rotate 仅更换 exporter、继承文档来源身份不变；确认“把继承文档转为本地原生文档”的 adoption 操作**不在 A1-04**、须独立审批。
3. **D19 附件拒绝语义**：确认 Batch A 对含附件导入/导出采用“显式拒绝或 unsupported”且**零附件写入**；确认稳定码命名（历史提案 `ATTACHMENT_IMPORT_UNSUPPORTED` / `ATTACHMENT_EXPORT_UNSUPPORTED` / `ATTACHMENT_REVIEW_UNSUPPORTED`；**已由 §L.2 固定**）。
4. **D19 批次门禁**：确认四批独立验收、不得跳批/代替；确认附件相关 R1-IMP 与 `R1.1-IMP-38/41/42` 归 Batch B。
5. **D20 锁等待上限**：沿用 R1.1 的 **10 秒**有界等待（历史提案 `IMPORT_LOCK_TIMEOUT`；**已由 §L.2 固定**）；确认同步模型只保留**一套同步身份锁**，不引入 async keyed lock + `threading.Lock` 双架构。
6. **D20 线程/Session 边界**：确认所有写入口（单篇、批量、approve）均为同步执行；确认不存在“async 路由 + `run_in_threadpool` 内再等同步锁”的变体绕过。
7. **D21 监听白名单**：确认允许集合为 `127.0.0.1` / `::1` / `localhost`（或是否允许 `127.0.0.0/8`）；确认稳定码 `NON_LOOPBACK_WITHOUT_AUTH`。
8. **D21 远程访问**：确认 A1-04 **不提供**任何经代理/隧道/端口转发的无认证远程访问；认证与受控远程访问属 auth/部署批次。
9. **R1.2 冻结**：确认四份文档合并完成、无新增 P0/P1 设计缺陷后，才批准进入 Batch A。

### K.3 R1.2 取代 / 扩展 / 保留关系

| 既有内容 | R1.2 处置 | 说明 |
|---|---|---|
| R1.1 §19.10 async keyed lock 推荐 | **机制取代**（D20） | 属性要求保留；验收以 `R1.2-ASYNC-*` 为主，`R1.1-SQL-10` 仍保留 |
| R1.1 §19.9 批次表/验收归属 | **范围修订**（D19） | Batch A 去掉附件完整导入导出；附件 + approve 归 B；四批独立出口 |
| R1.1 D-13 / §20.2 实例 ID | **术语扩展**（D18） | 本实例 ID 明确为 `exporter_instance_id`；文档来源身份独立且不可覆盖 |
| R1.1 D-15/D-16/D-17、D-01…D-14 | **继续沿用** | D18–D21 不重开这些决策；不改变 Core/A1-02/A1-03/V1 API |
| R1/R1.1 验收编号 | **全部保留** | R1.2 只新增 `R1.2-ID/BAT/ASYNC/NET`；IMP-21…24、BAK-13/14 空号保留 |
| R1/R1.1 风险编号 | **全部保留** | R1.2 只新增 §13；不重编号、不降级旧风险 |
| Offline / Single / Strict | **不变** | D19/D20/D21 均须在此三约束内执行；D21 不把 loopback 解释为“已认证” |

### K.4 R1.2 设计冻结门禁与停止点

冻结前必须同时满足：

- 四份主文档已合并 D18–D21，**不是仅保留增补文件**；`implementation-plan` §21 与 §19.9/§19.10/§20.2/§12 的就地修正一致。
- 编号、术语、事务顺序、批次边界、交叉引用一致（implementation-plan §21.6 ↔ acceptance-matrix §G ↔ risk-register §13 ↔ 本节 §K）。
- 所有 R1.2 新增验收进入 acceptance-matrix §G 并标 **【待验证】**；所有 R1.2 风险入 risk-register §13；不把设计写成已实现/已测试。
- Qoder 只读复核无新增 P0/P1 设计缺陷；用户明确批准 §K.1/§K.2，并完成 ChatGPT 阶段级独立审计。
- **本轮不启动 Batch A、不进入 A1-05/A2、不提交/推送、不修改 MILESTONES。**

满足后才允许进入 Batch A；**本轮文档合并完成后停止**，等待用户批准与 ChatGPT 独立审计。

---

## L. R1.3 决策台账（D22–D24，权威，关闭 R1.2 待决项）

> 来源：ChatGPT R1.3 架构裁决（2026-11-21）。本节记录 **D22 exporter 与 Hash 解耦、D23 本地文档身份初始化、D24 HTTP 本机安全边界**，并关闭 R1.2 §K.2 的九项待决。
> 原 §H（R1）、§J（R1.1）、§K（R1.2）作为历史记录全部保留；与本节冲突处以 **§L** 为准。**本节仅为设计裁决，非实现/验证结果；所有 R1.3 验收【待验证】。**
> 产品约束不变：**Offline backup / Single deployment / Strict migration**。

### L.1 R1.3 已裁决事项（ChatGPT 裁决，等待用户阶段级批准）

| 决策 | R1.3 裁决 | 与既有决策关系 | 状态 |
|---|---|---|---|
| **D22** exporter 与 Hash 解耦 | `exporter_instance_id` **只属传输元数据**；**不参与** `document_content_hash` / `document_payload_hash` / `source_payload_hash` / `review_payload_hash`；A1-02 Core Hash 与 canonicalization v1 **零改动**；backend 传输适配层提取/剥离/注入；frontmatter 用 `__explainlab_exporter_instance_id`、manifest 用 `exporter_instance_id`；**先算文档 Hash、再注入**；不落 DB；用户 metadata 占用保留键**显式拒绝并报告**；**重复保留键必须在 YAML 解析器折叠之前拒绝**；manifest/frontmatter 不一致、嵌套用户 metadata 冲突同样拒绝，且**冲突时零数据库写入**；manifest checksum 可随 exporter 变化，文档 payload_hash 不得 | **扩展** D18：D18 确立 source/exporter 分离，D22 明确 Hash 投影与注入顺序；不改变 `DocumentIdentity`、导入幂等或来源身份规则 | ChatGPT 裁决，**待用户阶段级批准** |
| **D23** 本地文档身份初始化 | **不新增迁移/表/列/索引**；DB 身份写入只用 `knowledge_item.source_instance_id`、`knowledge_item.id`、`ImportOrigin.source_instance_id/source_document_id/source_payload_hash`；**信息不足结论**：仅凭现有 DB 字段与 `extra_metadata` **无法安全区分**“合法物化”与“历史孤立”，**禁止**以 `source_instance_id` 非空、Hash 为空、时间排序或伪 `ImportOrigin` 推断。复用既有 data 目录 Journal，以**恰好一条匹配的 COMMITTED MATERIALIZE 记录**（item_id + 实例 ID + `source_document_id=item.id`）作为本地物化的唯一显式标记；状态 2a（无 origin、实例空、无记录）/2b（无 origin、实例非空、恰好一条匹配记录）/3（ImportOrigin 残缺）/4（无 origin、实例非空、无/多条/冲突记录）；2a 首次导出 **PREPARED→条件 DB 写→重读→COMMITTED+归档→导出**，2b 重复导出/重启/克隆稳定不重写；3/4 不补 `source_document_id`、不覆盖、不 adoption、报告；Journal/归档缺失/损坏 fail-closed。**启动先过 Journal 恢复门**：有效 `PREPARED MATERIALIZE`/`ROTATE` 先恢复，`PREPARED`+DB 空/等于目标才恢复、其他值/摘要不符 fail-closed；恢复前不分类/不写身份/不开新操作；`COMMITTED` 未归档只补归档、不重复写 DB。**COMMITTED 后 current→archive 同卷原子落位、current 幂等移除、同 operation_id 同内容去重、异内容 fail、归档失败禁新操作、append-only**。**Journal v1** 固定 `materialization_items{item_id, source_instance_id, source_document_id, identity_record_version, item_identity_digest}`；`materialization_items` 仅列本次物化项，**`identity_audit_digest` 覆盖全部 knowledge_item 的来源身份投影**（含未物化/已物化本地、有效 ImportOrigin、残缺/冲突），快照含 `item_id`、`origin_state`、`db_source_instance_id`、有效 `source_instance_id`/`source_document_id`、`import_origin_count`/`import_origin_state`/异常计数与 `import_origin_identity_digest`；每项还必须以 `import_origins[]` **逐条纳入全部 ImportOrigin 原始记录**（稳定 `import_origin_id`、原始 instance/document/payload、`status_flags`、`duplicate_group_size`），残缺/重复/非法不得过滤、去重或归一化，读取顺序无关，孤儿 fail-closed；**多记录状态按固定表判定**：互斥汇总 `conflict` > `invalid` > `incomplete` > `duplicate` > `complete` > `none`；≥2 个不同合法身份对或唯一合法身份与 `knowledge_item.source_instance_id` 不一致（含 DB `null`）必须 `conflict`，完整+残缺混合不得提升、重复+不同身份必须冲突、同一身份不同 `source_payload_hash` 版本不算冲突；冲突项零认领/覆盖/合并/猜测、不得任选一条；三个摘要采用 canonical UTF-8、对象键 code point 排序、数组按 `item_id` 排序、SHA-256、显式 `null`、未知版本 fail-closed；每次 DB 写后/恢复分支必须重读 DB 重算，rotate 前后各重算一次，不得只凭 Journal 自证 DB；Canonical JSON v1 固定非 ASCII 原样 UTF-8、引号/反斜杠/控制字符转义、合法 surrogate 对/孤立代理项拒绝、重复键解析折叠前拒绝、非负整数与 8 组向量；所有摘要不含 exporter。当前来源仍按 FID-2、禁 `MAX(imported_at)`、多匹配 fail-closed；clone 先逐条物化 2a 再按九步 write-ahead Journal rotate；`PREPARED`+旧 ID **必须重查 DB `materialization_items`+摘要**，`PREPARED`+新 ID 只补提交，未知/损坏 fail-closed，`COMMITTED` 归档后不重复且允许新 operation_id 的第二次独立 rotate；Journal 写失败不替换；Windows 目录同步不保证断电持久；**不批量改写**导入来源；adoption 不在 A1-04 | **补充** D18/D-13：不改变三元身份语义，解决“本地原生文档尚无来源身份”的初始化与时序；不改变 D15/D16/D17。**若用户不接受 MATERIALIZE Journal 作为显式标记，本项只能保持阻断，不得自动物化。** | ChatGPT 裁决 + R1.3 第二轮/第三轮/第四轮/第五轮/第六轮最终冻结前定点修正，**待用户阶段级批准** |
| **D24** HTTP 本机安全边界 | 默认监听 `127.0.0.1`；绑定**仅允许精确 IP `127.0.0.1`/`::1`**，**不接受 `localhost` 绑定**；**精确 Host + 合法端口**校验；浏览器修改请求**同源 Origin** 校验；修改接口**仅 `application/json`**；**不开放宽泛 CORS**；代理头**不授予访问权**；**DNS Rebinding 伪造 Host 必须拒绝**；非 loopback **启动 fail-closed**；代理/隧道/端口转发远程访问**不属于 A1-04**；**不增加认证依赖**、不实现账号/JWT/远程访问 | **收紧并扩展** D21：绑定集合去掉 `localhost`，新增 Host/Origin/Content-Type/重绑定控制；不改变“无认证不外露”边界 | ChatGPT 裁决，**待用户阶段级批准** |

### L.2 R1.2 §K.2 九项待决关闭记录

| # | R1.2 §K.2 待决项 | R1.3 最终裁决 | 依据 |
|---|---|---|---|
| 1 | D18 三元身份模型与 legacy 兼容 | **接受** source/document/exporter 三元分离与 `DocumentIdentity`；legacy 不伪造、不认领 | §L.1 D22/D23；`implementation-plan` §21.1、§22.1–§22.2 |
| 2 | D18 clone rotate 与 adoption | **接受** rotate 仅更换 exporter、继承文档来源不变；clone 前先逐条 **MATERIALIZE** 状态 2a（COMMITTED+归档）再 rotate；rotate 采用 write-ahead Journal/归档/崩溃恢复规则；**启动先恢复有效 PREPARED，COMMITTED 未归档只补归档不写 DB，恢复完成前不分类/不写身份；current→archive 同卷原子落位/去重/归档失败禁新操作**；`identity_audit_digest` 覆盖全部知识文档且每项逐条纳入全部 ImportOrigin 原始记录（含残缺/重复/非法；不归一化、读取顺序无关、孤儿 fail-closed），并按多记录状态表处理（多合法身份/DB 实例不一致→conflict，冲突零认领、不得任选），每次从 DB 重算；Canonical JSON v1 固定字符串/重复键/代理项规则；**adoption 延后**，不在 A1-04 | §L.1 D23；`implementation-plan` §22.2 |
| 3 | D19 附件稳定错误码命名 | **固定（最终）**为 `ATTACHMENT_IMPORT_UNSUPPORTED`、`ATTACHMENT_EXPORT_UNSUPPORTED`、`ATTACHMENT_REVIEW_UNSUPPORTED`；不再使用“提案/待批准”语义 | `implementation-plan` §21.2 |
| 4 | D19 A/B/C/D 独立批次门禁 | **接受**四批独立验收、不跳批/不代替；附件相关项归 Batch B | `implementation-plan` §21.2；`acceptance-matrix` §G.2 |
| 5 | D20 身份锁等待与单锁架构 | **固定（最终）10 秒**有界等待，超时 `IMPORT_LOCK_TIMEOUT`；只保留**一套同步身份锁**，禁止 async keyed lock + `threading.Lock` 双架构；不再使用“建议/待确认”语义 | `implementation-plan` §21.3 |
| 6 | D20 写入口统一同步 | **单篇、批量、approve 写入口统一同步 `def`**；无绕过变体 | `implementation-plan` §21.3 |
| 7 | D21 监听白名单 | **绑定允许集合固定为 `127.0.0.1`、`::1`**；`localhost` **不得作为绑定配置**（Host 头仍可按 §22.3 精确允许） | §L.1 D24；`implementation-plan` §22.3 |
| 8 | D21 远程访问 | **A1-04 不支持**任何经代理/隧道/端口转发的无认证远程访问 | §L.1 D24 |
| 9 | R1.2 冻结与进入开发 | **R1.3 完成合并并完成一次独立复核后**进入开发；本轮停止 | §L.4 |

> 以上为**关闭记录**，不删除 §K.2 原文；§K.2 仍保留为 R1.2 历史快照。
> **最终依据声明**：三个附件稳定码（`ATTACHMENT_IMPORT_UNSUPPORTED` / `ATTACHMENT_EXPORT_UNSUPPORTED` / `ATTACHMENT_REVIEW_UNSUPPORTED`）与身份锁 **10 秒 + `IMPORT_LOCK_TIMEOUT`** 以本 §L.2 为最终依据；`implementation-plan` §21.2/§21.3、`acceptance-matrix` 与 `risk-register` 中相关历史“提案/待确认”字样仅为演进记录，不再表示未决。

### L.3 R1.3 取代 / 扩展 / 保留关系

| 既有内容 | R1.3 处置 | 说明 |
|---|---|---|
| R1.2 D18 exporter 语义 | **扩展**（D22） | exporter 明确为传输元数据、不参与四类 Hash、先算后注入；source 身份规则不变 |
| R1.2 D18 clone 规则 | **补充时序**（D23） | clone 前先逐条以 MATERIALIZE Journal 物化状态 2a（COMMITTED+归档），再按 write-ahead Journal 原子 rotate；`PREPARED`+旧 ID 重查 DB 物化清单；失败/崩溃按状态表恢复，不重复轮换，允许新 operation_id 的第二次独立 rotate；**COMMITTED 后 current→archive 同卷原子落位、同内容去重、归档失败禁新操作；Journal v1 schema/摘要/版本按 §22.2 校验；`identity_audit_digest` 覆盖全库且每项逐条纳入全部 ImportOrigin 原始记录（含残缺/重复/非法；不归一化、读取顺序无关、孤儿 fail-closed），并按多记录状态表处理（多合法身份/DB 实例不一致→conflict，冲突零认领、不得任选），并在 rotate 前后从 DB 重算；Canonical JSON v1 字符串/重复键/代理项规则固定** |
| R1.2 D21 绑定允许集合（含 `localhost`） | **收紧**（D24） | 绑定只接受精确 IP；`localhost` 不再允许作为绑定值；请求侧 Host 校验另行定义 |
| R1.2 §K.2 九项待决 | **全部关闭** | 见 §L.2；原文保留 |
| D-01…D-17、D18–D21 其余内容 | **继续沿用** | R1.3 不重开 Core/A1-02/A1-03/V1 API；仅补充 D22–D24 |
| R1/R1.1/R1.2 验收与风险编号 | **全部保留** | 只新增 `R1.3-HASH/ID/NET` 15 项与 `R1.3-R-*` 3 项；空号保留 |
| Offline / Single / Strict | **不变** | D23 无新迁移；D22 不改 Hash；D24 不引入认证/多实例；D24 归 Batch D |

### L.4 R1.3 设计冻结门禁与停止点

冻结前必须同时满足：

- 四份主文档已合并 D22–D24，**不是仅保留增补文件**；`implementation-plan` §22 与 §21.1/§21.4/§21.5 的就地修正一致。
- 编号、术语、Hash 投影、身份状态 2a/2b/3/4、DB 字段信息不足不推断、MATERIALIZE/ROTATE Journal 与归档恢复时序、**启动恢复优先（PREPARED 先恢复、COMMITTED 只补归档、恢复前不分类/不写身份）**、**current→archive 同卷原子落位/去重/归档失败禁新操作**、**Journal v1 schema/摘要/排序/编码/空值/版本**、**`identity_audit_digest` 全库来源身份投影/每项全部 ImportOrigin 原始记录逐条审计（残缺/重复/非法、原始字段不归一化、读取顺序无关、孤儿 fail-closed）/每次 DB 写后与恢复重算/rotate 前后重算**、**Canonical JSON v1 非 ASCII/转义/代理项/重复键/8 组固定向量**、Host/Origin 校验、批次边界、交叉引用一致（`implementation-plan` §22.5 ↔ `acceptance-matrix` §H ↔ `risk-register` §14 ↔ 本节 §L）。
- 所有 R1.3 新增验收进入 `acceptance-matrix` §H 并标 **【待验证】**；风险入 `risk-register` §14；不把设计写成已实现/已测试。
- R1.2 §K.2 九项已关闭；历史 §K.2 与 R1/R1.1/R1.2 编号、裁决未被删除或重排；三个附件稳定码与 10 秒/`IMPORT_LOCK_TIMEOUT` 以 §L.2 为最终依据。
- **D22 重复保留键必须在 YAML 折叠前拒绝且冲突零 DB 写；D23 必须明确记录“DB 字段/`extra_metadata` 信息不足”，不得推断非空实例为本地原生；合法物化只能由 COMMITTED MATERIALIZE Journal 证明，缺失/损坏/冲突 fail-closed；状态 4 不补不覆盖不 adoption；`PREPARED`+旧 ID 必须重查 DB 物化清单与摘要；rotate Journal 写失败不得替换 ID；恢复完成前不得分类/写身份；`COMMITTED` 未归档只补归档不写 DB；current/archive 同内容去重、异内容 fail、归档失败禁新操作；Journal v1 字段/摘要/版本不符 fail-closed；`identity_audit_digest` 必须覆盖全部知识文档及每项全部 ImportOrigin 原始记录并重读 DB 验证，不得只覆盖物化项、只审计完整 origin、过滤/归一化残缺重复非法记录或只信 Journal；ImportOrigin 多记录必须按 §22.2 表判定（多合法身份/DB 实例不一致→conflict，完整+残缺不得提升，重复+不同身份→conflict，同身份多版本→complete，冲突不得任选/合并/猜测）；孤儿 ImportOrigin 必须 fail-closed；读取顺序不得影响摘要；Canonical JSON v1 必须拒绝重复键/孤立 surrogate/平台默认序列化差异，并用 8 组固定向量核对；原子替换不得等同于断电持久**。
- **D24 网络验收归 Batch D，不阻塞 Batch A 非附件开发**；Batch A/B/C/D 独立出口不变。
- 无新增 P0/P1 设计缺陷；用户明确批准 §L.1/§L.2 并完成 ChatGPT **最终独立审计**。
- **本轮不启动 Batch A、不进入 A1-05/A2、不提交/推送、不修改 MILESTONES。**

满足后才允许正式启动 Batch A；**本轮文档合并完成后停止**，等待用户批准与 ChatGPT 最终独立审计。
