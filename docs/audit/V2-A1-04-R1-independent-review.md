# V2 A1-04 架构 R1 独立技术审计报告

- 审计角色：独立技术审计（非本轮架构设计者，不重新设计、不改变已确定架构决策）
- 审计对象：ChatGPT 产出的 A1-04 Architecture R1（四份修订文档 + README-A1-04-R1.md）
- 审计方法：以当前真实 Git HEAD 为基线，只读核对 R1 与真实仓库代码 / DB 模型 / 接口契约的一致性；对 OS 锁原语做非破坏性真实探针；对工具链做只读环境核验
- 审计日期：2026-11-21
- 执行边界：本轮只读。未修改任何业务代码 / 测试 / 迁移 / lockfile / 依赖 / R1 文档；未提交、未推送、未重置、未切换分支；未启动 Batch A。仅执行只读代码检查、SQL 查询、Git 状态检查、非破坏性锁探针。
- 结论标记体系：【已验证事实】（真实代码/运行/探针证据）、【设计正确】（设计与真实契约一致且可实现）、【设计缺陷】（设计与真实契约冲突或存在数据安全/一致性漏洞）、【待验证】（设计合理但尚无真实运行证据，需开发阶段验收）、【建议改进】（非阻断，建议补充澄清或测试）

---

## 1. 审计基线与 Git 状态

【已验证事实】本轮审计开始时与结束时 Git 基线一致，未发生任何写操作：

| 项 | 值 |
|---|---|
| HEAD | `784b1248065424e07273b272d6016cc121bc606c` |
| 分支 | `fix/m0-admission-and-m5-regressions` |
| M0 初始提交（根） | `2d2b63443a3ba1290aafe03be5f5e3281ffa280f`（未改动） |
| tracked 工作树改动 | 空（`git status --porcelain -uno` 无输出） |
| staged 改动 | 空（`git diff --cached --stat` 无输出） |
| Alembic 单一 head | `0006_v2_markdown_kb`（未新增迁移） |

未跟踪文件（均非本轮新增业务代码）：
- `docs/audit/V2-A1-03-final-stage-audit/`（上一阶段产物）
- `docs/audit/V2-A1-04-technical-verification.md`（Request J 首轮只读核验报告）
- `docs/plans/V2-A1-04-implementation-plan.md` / `-acceptance-matrix.md` / `-risk-register.md` / `-open-decisions.md`（Request I 原始四份设计文档，未跟踪、未改动）
- 本报告 `docs/audit/V2-A1-04-R1-independent-review.md`（本轮唯一新增文件）

【已验证事实】R1 规划的全部新增模块当前均为 greenfield（不存在），与"设计阶段、尚未实现"定位一致：
`backend/app/db/process_lock.py`、`backend/app/db/storage_lock.py`、`backend/app/services/import_coordinator.py`、`import_review_hook.py`、`markdown_item_repository.py`、`backup.py`、`backend/app/ops/`（含 backup/restore/v2_downgrade/recover_backup）——逐一核验均 "No such file or directory"。

环境基线（只读核验）：
- Python 3.11.9；SQLite 3.45.1，`sqlite3.Connection.backup` 存在（Online Backup API 可用）
- PostgreSQL 16.8 Windows 原生（`D:/ExplainLab-pg/pgsql/bin/`，data `D:/ExplainLab-pg/data`，服务运行中 PID 50260）；`pg_dump` / `pg_restore` 16.8
- `EXPLAINLAB_PG_TEST_URL` 在当前 shell 未设置（PG 集成测试默认整模块跳过；本轮未执行 PG 在线迁移/检索，相关结论标【待验证】）
- 平台 win32；`msvcrt.locking` 原语经真实探针验证（见 §5）

---

## 2. 四份文档完整性

【已验证事实】指纹方法统一采用 `git hash-object`（blob SHA-1，即 `SHA1("blob <len>\0" + content)`）。本轮同时用原始 `sha1sum` 交叉核验，两法对同一文件稳定可复现；行数与首次读取时完全一致，确认材料未被改动。

R1 审计材料（用户提供的 Temp 路径，只读，未修改）：

| 文件 | blob SHA-1 | 行数 |
|---|---|---|
| `README-A1-04-R1.md` | `a5c86243a6c590b7c950b4ef61fe5b58fe2fbdb1` | 31 |
| `V2-A1-04-implementation-plan.md` | `5a13b6f15e073dbce06ff478ffb84faa60c27ad2` | 741 |
| `V2-A1-04-acceptance-matrix.md` | `e4e3e9fadccc38272be7c1b8af1223f1331648e8` | 239 |
| `V2-A1-04-risk-register.md` | `c75178c6072cbcb0c04f2cba817846514f227d58` | 174 |
| `V2-A1-04-open-decisions.md` | `306b5c579e1f46a572d5d9f92e90b4acb83f66d6` | 318 |

仓库原始四份（`docs/plans/`，Request I 基线，未跟踪、未改动）：

| 文件 | blob SHA-1 |
|---|---|
| `V2-A1-04-implementation-plan.md` | `de684eceb88e7d0c585c5d8410dd2af1265f6607` |
| `V2-A1-04-acceptance-matrix.md` | `5176a2ae644991e7ef03019ef8f7bac47cd2a841` |
| `V2-A1-04-risk-register.md` | `f143bb69e15e840ccf73584bb6aa97c292218c8e` |
| `V2-A1-04-open-decisions.md` | `d1ba42d6ab4128863e767f2e230fb9e9c43b7750` |

【已验证事实】R1 与原始版内容确实不同（如 implementation-plan：R1 `5a13b6f1…` ≠ 原始 `de684ece…`），R1 为含 D-15/D-16/D-17 的真实修订版，非原始文档冒充。原始四份仅含 D-01…D-14 / C-01…C-05。

【已验证事实】README-A1-04-R1.md 明确：R1 是 ChatGPT 的设计修订、等待用户批准；**不是实现/测试报告**；历史测试结果不构成本轮证据；批准后的下一步是 Qoder 将四份 R1 同步至 `docs/plans/` + 只读一致性检查 → 冻结 → Batch A（**非本轮**）。本轮审计尊重该定位，不将 R1 的【待验证】项当作已完成。

【设计正确】R1 文档体系内部交叉引用一致：open-decisions §H 权威决策表（D-01…D-17 + H.1…H.5）与 implementation-plan §19（19.1…19.9）、acceptance-matrix §E（R1-IMP/LOCK/BAK）、risk-register §11（R1-IMP/LOCK/BAK + §11.1 旧风险作废）相互对应；旧"按 item 串行（PG 行锁/SQLite 唯一约束）""多实例跨实例导入幂等""在线 quiesce/多实例编排"在 H.5 / §11.1 明确作废。未发现"唯一约束保证幂等"的残留过度承诺（F-01 已修复，见 §3）。

---

## 3. D-15 审计结论：来源身份与导入幂等

### 3.1 ImportOrigin 真实字段与索引

【已验证事实】`backend/app/models.py:410-435` `ImportOriginORM`：
- `__table_args__`（418-421）= `Index("ix_import_origin_item_id","item_id")` + `Index("ix_import_origin_source_payload_hash","source_payload_hash")`，**两者均非唯一**；无 `UniqueConstraint`；无 status 列。
- `source_payload_hash` / `source_content_hash`：`String(64)` NOT NULL；`source_instance_id`：`String(64)` **nullable**；`source_document_id`：`String(36)` NOT NULL；`source_canonicalization_version`：Integer；`imported_at`；`import_batch_id` nullable。

【已验证事实】迁移 `0006_v2_markdown_kb.py`：import_origin 段 `PrimaryKeyConstraint("id")`（182）+ 两个 `create_index` 非唯一（184-186），**无 UniqueConstraint**。对比同迁移：tag 有 `uq_tag_name`（75）、knowledge_link 有 `uq_link_source_key`（104）、item_tag 复合 PK（84）、storage_lock PK(storage_key)（197）。即 import_origin 是**刻意不设唯一约束**的表。

【设计正确】R1 D-15 / §19.2 / H.1 明确"ImportOrigin 无 DB 唯一约束，幂等由应用层单实例 + 身份键锁 + 同事务判定保证"，与真实模型/迁移完全一致。首轮核验 F-01（旧设计"SQLite 唯一约束/PG 行锁保证幂等"过度承诺）在 R1 中已全面移除，risk-register §11.1 明确作废旧 R-IMP-06。**未发现任何"唯一约束保证幂等"残留**。

### 3.2 身份设计：(source_instance_id, source_document_id)

【设计正确】R1 锁键 = 身份元组 `(source_instance_id, source_document_id)`，`source_instance_id` 为 null 时**显式编码**（非省略），payload_hash 仅作版本判据而非锁键。回退键 `target-item:<id>`（显式目标更新）/ `anonymous-content:<content_hash>`（无身份导入）。键经稳定序列化后 SHA-256。此设计与真实字段语义吻合：
- `source_document_id` NOT NULL → 身份必有文档稳定 ID；
- `source_instance_id` nullable → 必须显式编码 null，R1 已规定；
- D-13 首启生成稳定 UUID 文件 `backend/data/source-instance-id` → 解决"同实例多次导入 instance_id 漂移"，使身份键稳定。

【已验证事实】`KnowledgeItem` 核心领域实体（`knowledge_core/domain/entities.py`）**不含 source_\* 字段**；source_payload_hash/source_content_hash/source_instance_id 是 **ORM-only 冗余列**（`models.py:114-116`）。因此"当前已应用 hash"的读取必须经 backend ORM 或 `ImportOriginRepository.find_by_source_document`（`ports.py:427-434`，按源文档稳定 ID + 可限定源实例查权威历史），**不能从 Core 实体取**。R1 §19.2 将 item.source_payload_hash 描述为冗余指针、权威历史在 import_origin，与此一致。

【建议改进】FID-2：R1 应显式写明"幂等判定读取的当前 hash 来自 ImportOriginRepository（最新 imported_at）或 backend ORM 读，而非 Core KnowledgeItem 实体"，避免实现者误以为实体携带 source_*。属设计澄清，非缺陷。

### 3.3 keyed lock 生命周期

【设计正确】R1 §19.2 / §5.1 step 2：进程内单一 `ImportCoordinator` 持按身份键的 `threading.Lock`，**引用计数**管理（获锁计数+1、释放-1、归零移除字典项），避免锁字典无限增长。单条与批量导入入口共享同一 Coordinator 单例。这是**进程内**按身份串行，与 §5 的 OS 级**跨进程**单实例锁分层清晰，R1 §19.5 正确区分二者，未把 threading.Lock 当 OS 锁。

【建议改进】G-1：验收矩阵无"keyed lock 引用计数生命周期 / 锁字典泄漏 / 同身份重入"专项。建议新增 R1-IMP-17（并发同身份导入后锁字典归零、无泄漏；不同身份并行不互相阻塞）。
【建议改进】G-2：无"ImportCoordinator 单例被单条+批量入口共享"断言。建议新增 R1-IMP-18。

### 3.4 S0/S1 双阶段读：锁等待期间旧版本覆盖新版本

【设计正确】R1 H.1 / §19.2：S0 = 获锁前快照（身份 + 当前 hash + pending 状态）；获身份键锁后 S1 = 锁内重读。若 S1 与 S0 不一致（等待期间他人已应用新版本 / 已生成 pending）：
- 来件 hash ≠ S1 当前 hash 且来件非"已被应用/已 pending" → `SOURCE_CHANGED_DURING_WAIT`（拒绝旧版本覆盖新版本）；
- 同身份映射到多个 item_id → `SOURCE_IDENTITY_AMBIGUOUS`（拒绝歧义）。

该机制在概念上正确防止"锁等待期间旧 payload 覆盖新 payload"。成立前提（R1 应显式保证）：
1. **DB 读事务在获锁后、S1 之前开启**（或 S1 用全新读），使 S1 读到的是锁内最新已提交状态。SQLite 默认串行化写、PG 默认 READ COMMITTED，S1 新读可见他人已提交版本。
2. 检查与写入（ImportOrigin append + item 冗余列更新 + tags/metadata/links）在**同一 DB 事务**内（§3.5 / D-16）。

【建议改进】D15-3：R1 应显式规定"DB 写事务在身份键锁内、S1 重读之后开启"，避免实现者在锁外提前开事务导致 S1 读到陈旧快照（PG READ COMMITTED 下事务内首读建立快照）。属实现约束澄清。
【待验证】G-11：R1-IMP-02 列"双线程确定性交错"，但需强制屏障/故障注入钩子在 S0 与获锁之间注入状态变更才能确定性复现等待窗口。建议明确测试机制（barrier + inject），否则该交错可能偶发不可复现。

### 3.5 同身份多 item_id 歧义 / 同源不同 payload_hash 版本更新

【设计正确】同身份多 item_id → SOURCE_IDENTITY_AMBIGUOUS 拒绝（不猜测）。同源不同 payload_hash → ImportOrigin **append 历史**（权威），item.source_payload_hash 更新为当前指针；S1 检测到来件 hash 既非当前已应用、亦非已 pending 时按版本更新处理，若等待期间已被他人更新则 SOURCE_CHANGED_DURING_WAIT。与 ImportOrigin 无唯一约束、append-only 历史语义一致（`ports.py:403-434` save_origin/list_for_item/find_by_source_payload_hash/find_by_source_document）。

### 3.6 进程内锁与 OS 单实例锁的关系

【设计正确】分层：
- OS 级单实例锁（D-17，§5）：保证**同一时刻只有一个 Backend 进程**写库 → 排除跨进程并发写者；
- 进程内身份键 threading.Lock（D-15）：在单进程内**按身份串行**导入检查-写入 → 排除同身份并发交错；
- DB 事务原子性：检查与写入同事务 → 排除部分成功。

三者叠加，在"单实例"约束下构成完整幂等正确性链条。R1 §19.5 明确 threading.Lock 仅进程内、OS 锁才跨进程，未混淆。

### 3.7 关键判断：不新增唯一约束，单实例限制是否足以支撑幂等正确性

【设计正确】**结论：是——在 D-17 单实例 OS 锁真实生效的前提下，应用层（身份键锁 + S0/S1 + 同事务检查-插入）足以保证导入幂等正确性，无需 DB 唯一约束。**

论证：
1. 幂等竞态的唯一来源是"两个执行体同时对同一身份做 check-then-insert"。OS 单实例锁排除跨进程并发；身份键 threading.Lock 排除进程内同身份并发；故任一时刻同一身份只有一个执行体在检查-写入。
2. 检查（S1 读当前 hash / pending / item_id 映射）与写入（ImportOrigin append + 冗余列 + tags/metadata/links）同 DB 事务，要么全成功要么全回滚（§4 已验证 get_session 回滚语义），不存在"检查通过但写入部分成功"的中间态被他人观察到。
3. 无唯一约束时，正确性**完全依赖**上述应用层串行 + 事务原子性，而非 DB 兜底。R1 诚实声明此为"应用层幂等，非 DB 强制"，并将多实例/外部写者明确排除在范围外（H.5 作废旧多实例幂等测试）。这是诚实且自洽的取舍。

成立条件与残余风险（必须如实记录）：
- 【待验证】正确性依赖 D-17 OS 锁在 uvicorn 真实生命周期（含 --reload worker 重启、崩溃、CLI 同锁）中确实生效（§5）。原语已验证，集成待验证。
- 【设计正确→需实现保证】导入提交路由必须是 `def`（同步）或在线程池执行键锁等待，**不得在 asyncio 事件循环内用 threading.Lock 阻塞**（R1 §5.1 step 2 已规定 sync/threadpool）。现有 governance approve 路由是 `async def`（§4），新导入路由须避免沿用该模式做阻塞锁等待。
- 【建议改进】G-3：无"导入路由 sync/threadpool 执行、不阻塞事件循环"断言。建议新增 R1-IMP-19 或 SQL-10。
- 多实例/外部直写 DB 的幂等**不在本轮范围**，R1 未过度承诺；若未来需 DB 强制幂等，须另行批准迁移加唯一约束（本轮禁止新增迁移）。

【建议改进】D15-2：approve 钩子（写 ImportOrigin）是否参与身份键锁，R1 未显式说明。分析：pending 复用/阻塞天然串行化 submit 与 approve（pending 期间新 submit 被复用或阻塞；approve 提交后 origin 已应用 → 后续 submit 跳过），故功能上安全；但 R1 应**显式记录该串行化论证**，或令 approve 钩子同样经 Coordinator 身份键锁，以杜绝实现歧义。建议新增 G-6 / R1-IMP-23 验证 submit-approve 串行。

---

## 4. D-16 审计结论：Active 导入审核

### 4.1 ReviewRequest.payload 是否完整承载 __a1_import 信封

【已验证事实】`models.py:187-202` `ReviewRequestORM.payload` 为 `Text`（自由 JSON 文本，default "{}"），无 schema 约束。governance 仓库 `save_review` 以 `json.dumps` 写入、`_to_review` 以 `json.loads` 读出、`update_review` 保留 payload 原样。故 payload **可完整承载** R1 §19.3 / H.2 定义的 `__a1_import` 信封（schema_version、source 身份/hash、canonicalization_version、tags、extra_metadata、附件 staging manifest、link hints、context_digest）。

【设计正确】R1 明确 context_digest 仅**完整性校验**（防意外损坏/字段错配），**不是防篡改/权限边界**（诚实声明，§19.3）；review_payload_hash 仍仅覆盖 title?/content?/status?/space_id? 四字段（A1-02 冻结，A1-05 集成），信封 digest 与之分离、不混用。R1 未过度承诺 digest 的安全语义。

### 4.2 Core ReviewService 四字段 apply 行为

【已验证事实】`knowledge-core/src/knowledge_core/review/__init__.py`：
- `approve`（85-96）：_pending 校验 → 置 APPROVED + resolved_at/note → **先 `update_review`（94）再 `await _apply_action`（95）**；注释（92-93）明确同事务回滚语义；**方法内无 commit**。
- `_apply_update`（129-143）：create_version 快照（133）→ **仅当 payload 含对应键时**写 title/content/status/space_id（134-141）→ updated_at → items.update。**不触碰 tags/extra_metadata/source_\*/attachments/links**。
- `reject`（98-105）：仅置状态，无 apply。
- `_pending`（107-113）：缺失/非 PENDING 抛 ValueError。

【设计正确】R1 D-16 保持 Core ReviewService **完全不变**（§19.7 禁改 Core ReviewService），四字段以外的导入上下文由 **backend approve 钩子**在同一事务内补齐。这与 Core 真实行为精确吻合：Core 只 apply 四字段，钩子负责 tags/extra_metadata/附件引用/source 身份/ImportOrigin/LinkImportRestorer。无需改 Core、无需改冻结端口。

### 4.3 backend approve 钩子的真实调用位置

【已验证事实】`backend/app/api/routes/governance.py` `approve_review`（352-375，`async def`）真实序列：
1. `_pending_review`（359）
2. `build_review_service`（360）
3. `_demote_backlinks_before_delete`（363，仅 DELETE 动作）
4. `await service.approve(...)`（365；except ValueError → 400）
5. `_sync_links_after_content_change`（369，UPDATE/RESTORE → V1 repo.get → sync_links_or_conflict，即常规 K1 同步）
6. **`session.commit()`（370，第一次提交）**
7. `await _sync_applied_action(...)`（371-373，索引同步）
8. **`session.commit()`（374，第二次提交）**
9. 返回 ReviewOut

【设计正确】R1 钩子插入点 = **365 之后、370（首次 commit）之前**；导入分支**跳过 369 的常规 K1 同步**，改用 `build_link_restorer`（`links.py:537-541`）→ `LinkImportRestorer.restore`。该位置真实存在且可行：
- `service.approve` 无内部 commit（§4.2），故 365 返回时 review 状态变更与四字段 apply 仍在**未提交事务**中；
- 钩子在 370 之前对同一 session 追加 tags/extra_metadata/附件引用/source 冗余列/ImportOrigin/链接 restore（均 flush 不 commit）；
- 370 一次 commit 提交全部 → 满足 R1-IMP-08"同事务全字段单提交边界"。

【已验证事实】`LinkImportRestorer.restore`（`link_service.py:643-648`）解析 body wikilinks、分组 hints、校验 target_id（no_target_id/malformed_uuid/target_not_found → invalid+warning），并经 `self._links.save_link/update_link`（726/739/766/779/796/799）在**同一 session** 持久化链接，返回 report（823）。`build_link_restorer`（`links.py:537-541`）注入 `SQLAlchemyKnowledgeRepository(session)` + `SQLAlchemyLinkRepository(session)` + `RepositoryLinkResolver(items)`，docstring 注明"A1-04 导入路径预留"。故链接 restore 与审核 apply 同事务可行，无需第二次常规同步（R1-IMP-13）。

### 4.4 tags/extra_metadata/附件引用/source 身份/ImportOrigin/LinkImportRestorer 是否同一 DB 事务

【设计正确】是。全部经同一 `session` 的仓库方法 flush（不 commit），在 370 首次 commit 前完成：
- tags：TagRepository.set_item_tags + TagChangeLogRepository.append（`ports.py:305-353`）；
- extra_metadata：MarkdownItemRepository 写 ORM 列（`models.py:112`）；
- 附件引用：AttachmentRepository.save_attachment（`ports.py:276`，元数据入库；物理 blob 提升在事务外，见 §4.7）；
- source 身份冗余列 + ImportOrigin：MarkdownItemRepository / ImportOriginRepository.save_origin（`ports.py:410`）；
- 链接：LinkImportRestorer.restore（§4.3）。

【已验证事实】这些端口方法在 backend SQLAlchemy 实现中均为 session 内 flush，无独立 commit；Core 服务亦无内部 commit。故"同事务"在真实代码结构上成立。

### 4.5 commit 失败是否全回滚

【已验证事实】`backend/app/db/session.py` `get_session`（76-85）：`yield session` 后 **finally 仅 `session.close()`**（84-85），无 commit。SQLAlchemy Session.close() 对未提交事务执行回滚。故：
- 钩子在 370 之前抛异常 → 异常传播 → get_session finally close → **整个未提交事务回滚**，包括 service.approve 已 flush 的 review 状态变更（APPROVED）与四字段 apply。
- 结果：review **保持 pending**（回滚到 approve 前），item/tags/origin/links 均未写入 → 满足 R1-IMP-09"钩子在 tags 之后故障 → review pending + 全回滚"。

【设计正确】R1"失败回滚一切、review 保持 pending"与真实 get_session 回滚语义精确一致。Core approve 注释（92-93）亦声明同事务回滚意图。无需额外补偿逻辑。

### 4.6 reject staging 清理可靠性

【已验证事实】`reject_review`（378-391，async def）：_pending（384）→ service.reject（387，仅 update_review 置 REJECTED）→ **commit（390）**。service.reject 无 apply、无内部 commit。

【设计正确】R1：reject **不写 ImportOrigin、不改 item**，staging 清理在 **390 commit 之后**执行。清理失败 → staging 孤儿，由孤儿清扫兜底（§4.7 / G-5），**不得因清理失败回滚已提交的 reject**。实现要点：清理须 try/except 包裹，异常仅记日志/留待清扫，不向上抛致 get_session 误判（reject 已 commit，close 不再回滚已提交内容，但抛异常会污染响应）。R1-IMP-10/11 覆盖。

### 4.7 特殊核查：是否存在"审核已批准但附件/来源身份尚未持久化"的部分成功态

【设计正确】**结论：在钩子正确置于首次 commit（370）之前且异常正确传播的前提下，不存在"review 已 APPROVED 但 ImportOrigin/附件引用/source 身份缺失"的部分成功态。**

论证：
- review 状态 APPROVED 与 ImportOrigin/附件引用/source 冗余列/tags/links **同在 370 一次 commit**。commit 成功 → 全部持久化；commit 失败/钩子异常 → 全部回滚（review 回 pending）。二者原子绑定，无中间态。
- 唯一在 commit 之外的步骤：
  1. **物理 blob 提升**（staging → 正式 storage，§5.1 step 9）：R1 规定 blob 先提升、DB 事务后提交；若 blob 已提升但 DB 事务失败 → 正式区出现**无引用孤儿 blob**，R1 明确"保留孤儿、重试按 hash 校验复用、绝不反向删除未知引用文件"。这是**安全的孤儿**（非数据丢失、非引用不一致），由 GC/孤儿清扫处理。不存在"DB 引用了不存在的 blob"（因 DB 未提交）。
  2. **索引同步**（371-373，第二次 commit 374）：在 item/origin/links 已提交（370）之后。索引失败仅致搜索索引滞后，R1 §5.1 step 11 以 warning/reindex 兜底，**不影响 item/origin/附件引用的一致性**。

【已验证事实】真实路由结构（370 首提交、374 次提交、get_session 回滚）支持上述原子性。故 R1-IMP-08（同事务单提交）/ R1-IMP-09（故障全回滚）在真实代码上可实现，部分成功态被设计排除。

【待验证】上述为设计+代码结构论证；真实故障注入（钩子在 tags 后抛异常、commit 失败、blob 提升后 DB 失败）须在 Batch A 以真实 SQLite/PG 运行验证（R1-IMP-08/09/11/14），本轮未执行。

### 4.8 pending 重复导入复用

【设计正确】R1：同身份+同 hash 的 pending → 复用既有审核单（不新建）；同身份+不同 hash 且已有 pending → `SOURCE_HAS_PENDING_IMPORT` 阻塞。判定经扫描 ReviewRequest.payload 的 `__a1_import` 信封（应用层，身份键锁保护）。因无 DB 唯一约束，pending 去重正确性依赖身份键锁串行（§3.7），R1 诚实归为应用层幂等。

### 4.9 D-16 发现的问题

【设计缺陷】D16-1 / FID-1（P1，读路径一致性，非数据丢失）：R1 §3.3 声称"KnowledgeOut 增 tags/extra_metadata 读字段（additive，前端 A2 才消费）"，但同时要求 **V1 KnowledgeRepository 完全保持原样**。真实代码：
- `schemas.py:84-94` `KnowledgeOut` 当前**无** tags/extra_metadata/source_* 字段；
- V1 服务 `_to_entity`（`services/knowledge.py:28-48`）**不映射** tags/extra_metadata（Core 实体虽含 tags/extra_metadata，但 V1 仓库读路径未填充）；
- V1 GET 路由 `list_knowledge`（`routes/knowledge.py:51-65`，def sync）/ `get_knowledge`（89-97，def sync）经 V1 repo → KnowledgeOut.model_validate。

后果：若仅按 R1 字面给 KnowledgeOut 加 tags/extra_metadata 字段而 V1 读路径不变，则**导入已把 tags/extra_metadata 写入 DB 后，V1 GET /knowledge 与 /knowledge/{id} 仍恒返回空 tags/默认 extra_metadata**——DTO 字段误导性恒空，读路径与写路径不一致。这不是数据丢失（DB 数据完整、导出/MarkdownItemRepository 读路径可取），而是 API 读一致性缺陷。

R1 必须二选一澄清：
- (a) 允许 V1 `_to_entity` 做 **additive 只读映射**（读 tags/extra_metadata），但这与"V1 仓库保持原样"措辞冲突，须把冻结口径精确改为"V1 写路径不变、读路径可 additive 映射"；或
- (b) V2 读字段**仅经导出 / MarkdownItemRepository 读路径**暴露，撤回/限定"KnowledgeOut additive 读字段"声称，避免 V1 GET 恒空误导。

【建议改进】D16-2：approve_review 为 `async def` 却运行同步 DB 操作（现有 V1 模式，_sync_links 亦然）。导入钩子在 async 路由内做同步 DB 写入会阻塞事件循环（非本轮新增问题，但钩子工作量更大）。建议钩子高效执行或经线程池；与 G-3（导入路由 sync/threadpool）一并澄清。
【建议改进】G-7：无"常规治理 approve 的 K1 同步在导入分支引入后保持不变"的显式回归断言（GRD-03 跑套件但未显式区分导入分支 vs 常规分支）。建议新增 R1-IMP-24 / LNK-14：常规 UPDATE/RESTORE approve 仍走 _sync_links_after_content_change（369），导入分支才跳过。

---

## 5. D-17 审计结论：OS 级单实例锁

### 5.1 Windows msvcrt.locking 真实语义（非破坏性探针）

【已验证事实】本轮以真实探针（Temp 脚本，repo 外，自清理临时锁目录）验证 `msvcrt.locking`：

| 测试 | 操作 | 结果 |
|---|---|---|
| T1 | 对**空文件**首字节 `locking(fd, LK_NBLCK, 1)` | **成功**（允许锁超出 EOF 的字节，空文件可锁） |
| T2 | 同进程第二句柄对同一字节 LK_NBLCK | **EXCLUDED**（PermissionError，同进程亦互斥） |
| T4 | 父进程持锁时，子进程独立句柄 LK_NBLCK | **CHILD EXCLUDED**（跨进程互斥成立） |
| T3 | 父进程 close 句柄后，子进程 LK_NBLCK | **CHILD ACQUIRED**（句柄关闭即释放，不依赖 PID） |

常量核实：`LK_NBLCK=2`、`LK_UNLCK=0`。结论：msvcrt.locking 提供**真正的 OS 级跨进程排他锁**，**句柄关闭/进程死亡自动释放**（无 PID 残留依赖），**空文件可锁**（无需预写字节）。R1 D-17 选用 msvcrt 锁 1 字节、句柄持有至进程退出、**锁文件永不删除**（仅释放 OS 锁）的原语**经真实验证成立**。

【设计正确】"锁文件永不删除"避免 inode/句柄-文件名竞态：锁附着于打开句柄而非文件名，删除/重建文件会使新旧句柄指向不同 inode 而互斥失效。R1 §19.1 明确不删锁文件，探针 T1-T4 佐证该设计正确。**未把 threading.Lock/asyncio.Lock 当 OS 锁**（§3.6 已分层）。

### 5.2 POSIX fcntl 兼容

【合理推断】R1 规定 POSIX 用 `fcntl.flock` 排他锁，句柄关闭/进程死亡释放。语义与 msvcrt 对应（advisory exclusive，close 释放）。
【待验证】当前环境 win32，POSIX 分支无法真实运行；须在 Linux/macOS 真实验证（R1-LOCK 系列 POSIX 列）。本轮不宣称 POSIX 已验证。

### 5.3 Backend lifespan 获取/释放

【设计正确】R1：FastAPI lifespan 启动获锁、关闭释放；进程死亡 → OS 自动释放（探针 T3 佐证）。锁文件 `backend/data/.explainlab.process.lock`，句柄持有至进程退出。
【待验证】真实 lifespan 接线 + 启动失败时释放（获锁后初始化抛异常须释放句柄，避免残留）须 Batch B 真实运行验证（R1-LOCK-01/04）。本轮模块 greenfield，未实现。

### 5.4 多 worker / --reload / 异常退出

【设计正确】R1：worker 持锁、supervisor 不持锁、`workers=1`；第二 Backend → `BACKEND_ALREADY_RUNNING`（fail-closed）；`workers>1` 拒绝启动（R1-LOCK-06）。异常退出 → OS 释放（探针 T3）。
【待验证 / 建议改进】D17-1：`--reload` worker 重启存在**锁交接窗口**——uvicorn 杀旧 worker 后启新 worker，若旧 worker 句柄尚未完全关闭，新 worker 获锁可能撞 `BACKEND_ALREADY_RUNNING`。R1-LOCK-05 列出该场景但**未给出交接失败的处理设计**（重试/退避，或 supervisor 协调交接）。建议 R1 明确：新 worker 获锁失败时的有限重试/退避策略，或说明 uvicorn reload 的进程替换时序保证旧句柄先关闭。此为真实风险，须 R1-LOCK-05 真实运行验证后方可宣称锁机制完成（R1 §19.8 已诚实列为待验证）。

### 5.5 Offline CLI 与 Backend 同一锁

【设计正确】R1：所有维护 CLI（backup/restore/v2_downgrade/recover_backup）与 Backend 共用同一锁文件，Backend 持锁时 CLI fail-closed（R1-LOCK-02/03）。
【建议改进】D17-2：锁文件路径须在 Backend 与 CLI 间**绝对一致**。Backend 经 config `BACKEND_DIR` 锚定 `backend/data/`；CLI 的 cwd 可能不同，若用相对路径会指向不同锁文件而互斥失效。R1 应明确 CLI 经同一 config/BACKEND_DIR 解析**绝对路径**，不得依赖 cwd。
【待验证】CLI 同锁 fail-closed 须真实双进程验证（R1-LOCK-02/03）。

### 5.6 崩溃释放 / 锁文件删除-重建竞态

【已验证事实】崩溃释放：探针 T3（close→可获锁）；进程死亡关闭全部句柄 → OS 释放，无 PID 文件依赖（R1 明确不用 PID-file mutex）。R1-LOCK-04（kill→OS 释放、锁文件不删）设计正确。
【设计正确】锁文件删除-重建竞态：R1 永不删锁文件 → 规避（§5.1）。

### 5.7 跨平台字节范围语义差异

【建议改进】D17-3：msvcrt 锁**字节范围**（探针锁 1 字节），fcntl.flock 锁**整文件**。二者均排他，但抽象层须统一语义（建议 POSIX 亦用 fcntl.locking 字节范围或明确 flock 整文件与 msvcrt 1 字节等价排他）。探针确认 msvcrt 1 字节足够互斥。属实现细节澄清，非缺陷。

### 5.8 D-17 总判定

【设计正确】OS 锁原语（msvcrt）经真实探针验证成立；单实例/worker 持锁/CLI 同锁/不删锁文件/崩溃释放/不用 PID mutex 的设计与真实 OS 语义一致；与进程内键锁分层清晰。
【待验证】集成层（lifespan 接线、--reload 交接窗口、POSIX fcntl、CLI 同锁、workers>1 拒绝）须开发阶段真实运行验收。R1 §19.8 诚实声明"真实 Windows 进程测试通过前不得宣称锁机制完成"，本轮尊重该声明，不将原语验证等同于集成验证。

---

## 6. Offline Backup / Restore 审计

### 6.1 备份原语与工具链

【已验证事实】SQLite `Connection.backup`（Online Backup API）在 3.45.1 可用；R1 用 Online Backup 而非裸文件拷贝（避免 WAL/写中拷贝不一致）。PG `pg_dump --format=custom` + `pg_restore` 16.8 可用、服务运行中；R1 规定版本校验。工具链真实存在。
【设计正确】R1 不改 WAL 模式、不改 busy_timeout（§19.6），备份经 Online Backup API 取一致快照，符合 SQLite 推荐实践。

### 6.2 Manifest / journal / checksum 文件持久化

【设计正确】R1：Manifest/journal/checksum 落 `backend/data/ops/backup/` 文件（非 DB 表、无迁移），fsync 顺序"资源→journal→完成标记"，包结构 manifest.json / database.sqlite3|database.dump / attachments / import-staging / checksums.sha256 / COMPLETE。
【已验证事实】文件持久化模式在仓库已有先例：`links.py:519-527` `persist_rebuild_report` 将 JSON 报告写 ops_dir。R1 仿此模式合理、无需新表。

### 6.3 附件合并 + DB 最后切换的正确性

【设计正确】R1 §19.6 / H.4 恢复安全序：维护锁 → 校验 COMPLETE/Manifest/全 checksum → staging DB 恢复 + schema head 校验 → **按相对路径合并 attachments/quarantine/import-staging**（同路径不同 hash → ABORT；只新增/校验，**绝不覆盖/删除当前 blob**）→ **DB 最后切换**（SQLite 关全部句柄 + os.replace + 保留 previous；PG 恢复 staging、确认无目标连接、rename target→previous 再 staging→target，连接/权限不足在 rename 前中止、保留旧库不立即 DROP）→ journal 完成标记 → **journal vs 真实 DB（SQLite hash / PG OID）vs 附件清单三方对账**（不盲信阶段标记）→ 旧资源保留至确认。

该顺序正确防止"DB 已恢复但附件缺失/引用不一致"：附件先合并并校验，DB 切换在最后，切换后 DB 引用的 blob 必已就位；冲突在切换前 ABORT，不会留下半恢复态。

### 6.4 恢复中途崩溃

【设计正确】
- DB 切换前崩溃 → 存活 DB 仍为旧库，已合并的额外 blob 为**安全孤儿**（无引用、不损坏旧库），后续可清扫。
- DB 切换后崩溃 → journal + 三方对账（SQLite 文件 hash / PG database OID，OID 在 rename 后不变）判定真实状态，不盲信 COMPLETE 标记。
- R1-BAK-05/06/09 覆盖切换前/后崩溃 + PG rename 崩溃 OID 对账。

### 6.5 Windows 文件占用 / 连接池 / 文件替换

【设计正确】R1：os.replace 同卷、先关全部句柄、退避重试不强删、保留 previous 世代。
【待验证】Windows 真实文件占用/替换/崩溃恢复须真实运行（R1-BAK-08/09/10）。os.replace 在 Windows 要求目标无打开句柄（含连接池），R1"关全部句柄"正确，但真实连接池关闭时序须验证。

### 6.6 PG staging DB + rename 真实可行性

【合理推断】`ALTER DATABASE ... RENAME TO` 要求**目标库零活动连接**（PG 文档约束）；CLI 执行 rename 时须连到维护库（如 `postgres`）而非目标库；autovacuum launcher/后台 worker 可能连目标库 → 需 `pg_terminate_backend` 清场并核验 `pg_stat_activity` 为空后再 rename。rename 后 OID 不变，可用于对账。
【设计正确】R1 §19.6"确认无连接后 rename，任何连接无法关闭或权限不足在 rename 前中止、保留旧库"概念正确。
【待验证 / 建议改进】BAK-1：R1 应**显式写明** rename 前清场步骤（连 postgres 维护库、pg_terminate_backend 目标库连接、核验 pg_stat_activity 空、含 autovacuum 处理），而非仅"确认无连接"。真实 PG staging 恢复/rename/崩溃 OID 对账须 Batch C 连真实实例验证（R1-BAK-07/08/09）。本轮 PG 在线操作未执行（EXPLAINLAB_PG_TEST_URL 未设、只读边界），不宣称已验证。

### 6.7 关键核查：是否可能"DB 已恢复但附件缺失/引用不一致"

【设计正确】**结论：R1 的"附件先合并校验 + DB 最后切换 + 全 checksum 前置校验 + 冲突 ABORT + 三方对账"设计排除了该状态。**
- 不完整备份（包内缺附件）→ 恢复前全 checksum 校验失败 → 拒绝（R1-BAK-03），不会进入切换。
- 合并冲突（同路径不同 hash）→ 切换前 ABORT，旧库不动。
- 切换后 → DB 引用的 blob 必已合并就位；额外当前 blob 成为安全孤儿（不丢失、后续清扫）。
残余【待验证】：真实 Windows 文件替换崩溃、PG rename 连接清场须开发阶段真实证据。

### 6.8 Backup/Restore 发现的问题

【建议改进】BAK-2：恢复合并后"额外当前 blob 成为孤儿、后续清扫"——孤儿清扫有 grace（24h），R1-BAK-04 覆盖冲突 ABORT 但无"额外 blob 保留 + 最终安全清扫"专项。建议新增 R1-BAK-14（G-9）。
【建议改进】BAK-3：备份含 import-staging（pending 审核附件），R1-BAK-10 验证 staging 存活+hash 匹配；建议确保 Manifest 记录 staging 文件清单 + review_id 关联，使恢复可校验 pending 信封的 staging 引用完整性（R1 §19.6 Manifest 含 staging 逐文件 hash，方向正确，补充关联即可）。

---

## 7. 数据保真与 V1 兼容性

### 7.1 V1 KnowledgeRepository 与独立 MarkdownItemRepository 隔离

【设计正确】R1 D-02=C：独立 MarkdownItemRepository，V1 仓库完全不变。
【已验证事实】V1 服务 `update`（`services/knowledge.py:102-112`）**仅写** row.title/content/status/space_id/updated_at，**不写** extra_metadata/source_*/tags。V1 `KnowledgeUpdate`（`schemas.py:103-109`）仅 title/content/status/space_id，**无 extra_metadata 入参**。故 V1 写路径与 V2 列**不相交**。

### 7.2 V1 PATCH 是否会清空 V2 extra_metadata

【已验证事实】**不会**。V1 update 不触碰 extra_metadata/source_* 列（§7.1），PATCH 后这些列保持原值。R1-IMP-12（V1 PATCH 不清空 V2 字段）在真实代码上成立。风险仅在于"若有人扩展 V1 写路径写 extra_metadata"——R1 §19.7 明确禁止 V1 repo 写扩展，红线守住。

### 7.3 tags / source_* 读写一致性

【设计正确（写）】tags/extra_metadata/source_* 经 MarkdownItemRepository（导入路径）写入；V1 写路径不触碰 → 写一致。
【设计缺陷（读）】见 D16-1 / FID-1（§4.9）：V1 GET 读路径不映射 tags/extra_metadata → 导入后 V1 GET 恒空。读一致性缺口，须 R1 澄清（additive 只读映射 或 限定 V2 字段仅经导出/MarkdownItemRepository 读路径）。
【已验证事实】source_* 为 ORM-only（Core 实体无），MarkdownItemRepository 经 backend ORM 方法写 source_*，不经 Core 实体、不改冻结端口（`ports.py:40-74` KnowledgeRepository 接收 KnowledgeItem，含 tags/extra_metadata，无 source_*）。

### 7.4 A1-02 三 Hash 契约

【已验证事实】canonicalization_version=1 冻结；document_content_hash（title+content）、document_payload_hash（全交换）、review_payload_hash（仅 title?/content?/status?/space_id? 四字段）。R1 复用三 Hash、信封 context_digest 与之分离（§4.1），不改 A1-02 codec/canonical/hash（§19.7 禁改）。
【设计正确】R1 未触碰冻结的 A1-02 契约。

### 7.5 A1-03 链接绑定恢复 + 治理钩子

【已验证事实】`build_link_restorer`（`links.py:537-541`）+ `LinkImportRestorer.restore`（`link_service.py:643-648`，save_link/update_link 726-799）真实存在，docstring 注明 A1-04 预留。常规 K1 治理钩子在 backend 路由（governance.py），非 Core。
【设计正确】R1 D-03：导入用 LinkImportRestorer，Active approve 钩子替代常规同步（导入分支跳过 369），常规治理 K1 不变。与真实代码一致。R1 §19.7 禁改 A1-03 LinkKeyRebuild/apply_link_key_plan/locking.py，红线守住。

### 7.6 0006 / 冻结端口是否必须改动

【已验证事实】**无需改动**。全部所需表/列已存在于 0006（knowledge_item.extra_metadata/source_*、tag/item_tag/knowledge_link/attachment/tag_change_log/gc_task/import_origin/storage_lock）；`ports.py` 已含 LinkRepository/AttachmentRepository/TagRepository/TagChangeLogRepository/GcTaskRepository/ImportOriginRepository/StorageKeyLock 全部 V2 端口；KnowledgeRepository 接收含 tags/extra_metadata 的 KnowledgeItem。MarkdownItemRepository 实现既有端口 + backend 专属 source_* 写方法即可，**无需新迁移、无需改冻结端口**。R1 §19.7/§19.8 禁新增迁移/改冻结端口，与真实状态一致。

### 7.7 数据保真总判定

【设计正确】写路径隔离、V1 PATCH 不清空、三 Hash 冻结、A1-03 恢复钩子、无迁移/端口改动——均与真实代码一致。
【设计缺陷】唯一实质问题为 D16-1/FID-1 读路径一致性缺口（P1，非数据丢失），须 R1 澄清。
【建议改进】FID-2（§3.2）：澄清当前 hash 读取来源（ImportOriginRepository/ORM，非 Core 实体）。

---

## 8. SQLite / PostgreSQL / Windows 差异

【设计正确】R1 方言差异封装在 backend 适配层，业务/Core 不写方言 SQL，符合 AGENTS.md §5 红线：
- 全文检索：SQLite FTS5（trigram/bm25/LIKE 回退）vs PG tsvector/tsquery+GIN+ILIKE 回退（既有 ZIP-01，R1 不改）。
- storage_key 锁：SQLite 租约式逻辑锁（storage_lock 表，短事务条件写+fencing+心跳）vs PG 会话级 advisory lock（D-04/D-14，SHA-256 前 8 字节→bigint，碰撞仅额外串行、绝不跳过精确 COUNT）。`StorageLockORM`（`models.py:438-451`，PK storage_key）真实存在，SQLite 路径有据；PG advisory 为后端适配，无需表。
- OS 单实例锁：Windows msvcrt（§5 已验证原语）vs POSIX fcntl（待验证）。
- 备份：SQLite Online Backup API vs PG pg_dump custom（§6 工具链已验证）。
- 恢复 DB 切换：SQLite os.replace（同卷、关句柄）vs PG staging+rename（零连接、OID 对账）。

【已验证事实】向量存储双方言通用 JSON 文本 + Python 余弦（JsonVectorStore，不依赖 pgvector），R1 不改。
【待验证】PG 真实在线路径（advisory 碰撞 R1-LOCK-08、staging restore/rename R1-BAK-07/08/09、PG 列全部 R1-IMP/ATT/GC）须连真实 PG 实例验证；本轮只读边界 + EXPLAINLAB_PG_TEST_URL 未设，未执行 PG 在线操作，不宣称 PG 已验证。
【待验证】Windows 真实文件系统（os.replace 占用/崩溃 R1-BAK-08/09/10、msvcrt 生命周期 R1-LOCK-01/04/05）须真实运行；msvcrt 原语本轮已验证，集成待验证。
【设计正确】R1 未把离线 SQL 等同真实 DB 验证、未虚报 PG 成功（§19.8 诚实列待验证），符合 AGENTS.md §5/§10。

---

## 9. 验收矩阵缺口

【设计正确】R1 验收矩阵整体覆盖充分：R1-IMP-01…16、R1-LOCK-01…08、R1-BAK-01…12，多数项含 SQLite/真实 PG 双列；Windows 真实 FS（BAK-08/09/10、LOCK-01/04/05）、多进程锁竞争（LOCK-01/02/03/06）、故障注入（IMP-09/11/14、BAK-03…09、GC-06/07/10）、事务回滚（IMP-08/09）、崩溃恢复（LOCK-04、BAK-05/06/09）、数据完整性（BAK-04、ORP-07）、旧版本兼容（IMP-12、IMP-20、OPS-05）均有对应项。全部标【待验证】，诚实。

【建议改进】发现以下缺口，**明确提出应新增的测试，不自行编写**：

| 编号 | 缺口 | 建议新增验收项 |
|---|---|---|
| G-1 | keyed lock 引用计数生命周期 / 锁字典泄漏 / 同身份重入 | R1-IMP-17：并发同身份导入后锁字典归零无泄漏；不同身份并行不互阻 |
| G-2 | ImportCoordinator 单例被单条+批量入口共享 | R1-IMP-18：两入口共用同一 Coordinator，同身份跨入口串行 |
| G-3 | 导入路由 sync/threadpool 执行、不阻塞事件循环 | R1-IMP-19 / SQL-10：断言导入提交路由为 def 或线程池执行键锁等待 |
| G-4 | D-13 source-instance-id 生命周期（首启生成/重启稳定/备份恢复保留/rotate CLI/导出携带）| R1-IMP-20/21 + OPS-06：首启生成文件、重启不变、backup/restore 保留、rotate-instance-id CLI 变更、导出携带 instance_id |
| G-5 | staging 孤儿清扫安全（有 active pending 的目录不清扫；无 pending+过 grace 才清扫；正式 blob 绝不删）| R1-IMP-22：清扫只命中无 pending 且过 grace 的 staging，正式区与 active pending 不受影响 |
| G-6 | approve 钩子参与身份键锁 / submit-approve 串行 | R1-IMP-23：pending 期间 submit 复用/阻塞，approve 与 submit 不交错写同身份 |
| G-7 | 常规治理 approve K1 同步在导入分支引入后保持不变 | R1-IMP-24 / LNK-14：常规 UPDATE/RESTORE 仍走 369 同步，仅导入分支跳过 |
| G-8 | PG rename 连接清场（含 autovacuum）+ CLI 连 postgres 维护库 | R1-BAK-13：rename 前 pg_terminate_backend + pg_stat_activity 空核验，CLI 连维护库 |
| G-9 | 恢复保留额外当前 blob + 最终安全孤儿清扫 | R1-BAK-14：恢复后额外 blob 保留为安全孤儿，grace 后清扫不误删被引用 blob |
| G-10 | V1 GET 读路径对 tags/extra_metadata 的一致性（D16-1）| R1-IMP-25：导入后 V1 GET 反映 tags/extra_metadata（取决于 §4.9 澄清方案），或显式断言 V2 字段仅经导出读路径 |
| G-11 | S0/S1 确定性交错的测试机制 | R1-IMP-02 补充：强制屏障+故障注入在 S0 与获锁间注入状态变更，确定性复现 SOURCE_CHANGED_DURING_WAIT |

【建议改进】G-4（instance-id 生命周期）为最显著缺口：D-13 是 D-15 身份键稳定性的前提，但验收矩阵无任何 instance-id 生成/持久/恢复/rotate/导出携带项。强烈建议补全，否则身份幂等的前提本身未经验收。

---

## 10. 全部发现的问题及严重程度

按严重程度排序（P0 致命/阻断冻结；P1 重要/须冻结前澄清；P2 一般/建议改进；V 待验证/开发阶段真实证据）：

| 编号 | 严重度 | 类别 | 问题 | 证据 | 处置 |
|---|---|---|---|---|---|
| D16-1 / FID-1 | **P1** | 设计缺陷 | KnowledgeOut additive 读字段 vs V1 读路径不变 → 导入后 V1 GET 恒空 tags/extra_metadata，读写不一致 | schemas.py:84-94；services/knowledge.py:28-48；routes/knowledge.py:51-65/89-97；R1 §3.3 | 冻结前澄清：additive 只读映射（精确化冻结口径）或 V2 字段仅经导出/MarkdownItemRepository 读路径 |
| D17-1 | **P1/V** | 设计待澄清+待验证 | --reload worker 重启锁交接窗口可能撞 BACKEND_ALREADY_RUNNING，R1 未给交接失败处理设计 | R1 §19.1/R1-LOCK-05；探针 T3（close 释放） | R1 明确重试/退避或交接时序；R1-LOCK-05 真实运行验证 |
| G-4 | **P1** | 验收缺口 | D-13 instance-id 生命周期无任何验收项（身份幂等前提未验收） | acceptance-matrix §E 无对应项；R1 D-13/H.1 | 新增 R1-IMP-20/21 + OPS-06 |
| D15-2 | P2 | 建议改进 | approve 钩子是否参与身份键锁未显式说明 | R1 §19.2/§19.3；governance.py:352-375 | 记录 pending 串行化论证或令 approve 经 Coordinator；G-6 |
| D15-3 | P2 | 建议改进 | S0/S1 与 DB 事务快照时序未显式约束 | R1 H.1/§19.2 | 明确写事务在锁内 S1 后开启；G-11 测试机制 |
| BAK-1 | P2/V | 建议改进+待验证 | PG rename 连接清场（autovacuum/维护库）未显式写明 | R1 §19.6；PG RENAME 零连接约束 | 显式清场步骤；R1-BAK-13 真实 PG 验证 |
| D17-2 | P2 | 建议改进 | 锁文件路径 Backend/CLI 须绝对一致（cwd 差异） | R1 §19.1 | CLI 经 BACKEND_DIR 解析绝对路径 |
| FID-2 | P2 | 建议改进 | 当前 hash 读取来源（ImportOriginRepository/ORM 非 Core 实体）未显式 | entities.py 无 source_*；ports.py:427-434 | R1 澄清读取来源 |
| G-1/G-2/G-3/G-5/G-6/G-7/G-9/G-10 | P2 | 验收缺口 | 键锁生命周期/Coordinator 单例/sync 路由/staging 清扫安全/submit-approve 串行/常规 K1 回归/额外 blob 保留/V1 GET 一致性 | §9 表 | 新增对应验收项（不自行编写） |
| D16-2 | P2 | 建议改进 | approve async 路由内同步 DB 阻塞事件循环（既有模式） | governance.py:352 async def | 钩子高效/线程池；与 G-3 一并澄清 |
| D17-3 | P2 | 建议改进 | msvcrt 字节范围 vs fcntl 整文件语义统一 | 探针 T1；R1 §19.1 | 抽象层统一排他语义 |
| BAK-2/BAK-3 | P2 | 建议改进 | 恢复额外 blob 清扫专项 / staging-review_id 关联 | R1 §19.6；R1-BAK-04/10 | R1-BAK-14；Manifest 补关联 |
| V-集成 | **V** | 待验证 | msvcrt lifespan/--reload/POSIX fcntl/CLI 同锁/workers>1；PG advisory 碰撞/staging restore/rename/OID 对账；Windows os.replace 占用/崩溃；approve 钩子故障全回滚；S0/S1 确定性交错 | R1 §19.8 诚实列待验证；模块 greenfield | Batch A/B/C 真实 SQLite/PG/Windows/多进程/故障注入运行验收，通过前不得宣称完成 |

【已验证事实】**无 P0 致命设计缺陷**。首轮核验 F-01…F-09 的重大错误在 R1 中均已正确修复：
- F-01（唯一约束过度承诺）→ 全面移除，import_origin 真实无唯一约束（§3.1）；
- F-02（approve 钩子位置不可行）→ 钩子置于 365 后 370 前，真实可行（§4.3）；
- F-03（ImportOrigin 写入时机）→ approve 时写、同事务（§4.4）；
- F-05（多实例幂等过度承诺）→ 单实例显式 + OS 锁原语已验证（§3.7/§5）；
- F-06（V1 仓库耦合）→ 独立 MarkdownItemRepository、V1 写路径不变（§7.1）。

---

## 11. 建议修订事项

供 ChatGPT 独立复审与 R1 修订参考（本轮不修改 R1 文档，仅提出建议）：

1. **【P1，须冻结前解决】澄清 D16-1 读路径**：在 R1 §3.3 明确二选一——(a) 允许 V1 `_to_entity` additive **只读**映射 tags/extra_metadata，并把冻结口径精确改为"V1 **写**路径不变、**读**路径可 additive 映射"；或 (b) 撤回"KnowledgeOut additive 读字段"，V2 读字段仅经导出/MarkdownItemRepository 读路径暴露。配套新增 G-10/R1-IMP-25 验收。
2. **【P1】补全 D-13 instance-id 生命周期验收（G-4）**：新增 R1-IMP-20/21（首启生成/重启稳定/备份恢复保留/导出携带）+ OPS-06（rotate-instance-id CLI）。这是 D-15 身份幂等的前提，必须验收。
3. **【P1/V】明确 --reload 锁交接设计（D17-1）**：R1 §19.1 补充新 worker 获锁失败的有限重试/退避或 supervisor 协调交接时序；R1-LOCK-05 真实运行验证通过前不得宣称锁机制完成。
4. **【P2】显式 approve 钩子锁参与（D15-2）+ S0/S1 事务时序（D15-3）**：记录 pending 串行化论证或令 approve 经 Coordinator 身份键锁；明确 DB 写事务在锁内 S1 后开启。配套 G-6/G-11。
5. **【P2/V】显式 PG rename 连接清场（BAK-1）**：R1 §19.6 写明连 postgres 维护库、pg_terminate_backend、pg_stat_activity 空核验（含 autovacuum）；新增 R1-BAK-13 真实 PG 验证。
6. **【P2】锁文件绝对路径一致性（D17-2）+ 跨平台锁语义统一（D17-3）**：CLI 经 BACKEND_DIR 解析绝对路径；抽象层统一 msvcrt 字节范围/fcntl 排他语义。
7. **【P2】澄清当前 hash 读取来源（FID-2）**：R1 §19.2 写明经 ImportOriginRepository（最新 imported_at）或 backend ORM 读，非 Core 实体。
8. **【P2】补全验收缺口 G-1/G-2/G-3/G-5/G-7/G-9**：键锁引用计数生命周期、Coordinator 单例共享、导入路由 sync/threadpool 断言、staging 孤儿清扫安全、常规 K1 回归、恢复额外 blob 保留+清扫。**仅提出应新增的测试，不自行编写。**
9. **【V】开发阶段真实证据**：§10 V-集成 全部待验证项须在 Batch A/B/C 以真实 SQLite/真实 PG/真实 Windows FS/多进程锁竞争/故障注入/事务回滚/崩溃恢复运行验收；通过前不得宣称完成（R1 §19.8 已诚实声明，维持）。

以上修订均**不要求新增迁移、不改冻结端口、不改 A1-02/A1-03 冻结契约、不扩展 V1 写路径、不弱化数据安全**，可在 R1 既有约束内解决。

---

## 12. 最终审计结论

### 判定：**CONDITIONAL PASS（有条件通过）**

**判定依据：**

【设计正确】R1 架构与真实仓库代码/DB 模型/接口契约**整体一致且可实现**，并正确修复了首轮核验（Request J）的全部重大错误（F-01…F-09，见 §10）。核心安全设计经真实证据支撑：
- D-15 单实例 + 身份键锁 + S0/S1 + 同事务，在单实例约束下**足以保证导入幂等，无需 DB 唯一约束**（§3.7 关键判断：是）；import_origin 真实无唯一约束，R1 无过度承诺。
- D-16 approve 钩子真实位置（governance.py 365 后 370 前）可行，Core 无内部 commit + get_session 回滚语义保证**全回滚、review 保持 pending**，**排除"已批准但附件/来源身份缺失"的部分成功态**（§4.7 特殊核查：不存在）。
- D-17 msvcrt OS 锁原语经**真实探针验证**（T1-T4：空文件可锁/同进程互斥/跨进程互斥/close 释放），不删锁文件/不用 PID mutex/与进程内键锁分层正确（§5）。
- Backup/Restore 附件先合并校验 + DB 最后切换 + 三方对账，**排除"DB 已恢复但附件缺失/引用不一致"**（§6.7 关键核查：排除）；工具链（Online Backup API/pg_dump 16.8）真实可用。
- 数据保真：V1 PATCH 不清空 V2 列（写路径不相交，已验证）、三 Hash/A1-03 冻结契约不改、无需新迁移/改冻结端口（§7）。

**未给 PASS 的原因（条件）：**
1. **【P1 设计缺陷】D16-1/FID-1 读路径一致性缺口**未解决：KnowledgeOut additive 读字段与"V1 读路径不变"冲突，导入后 V1 GET 恒空 V2 字段。须冻结前澄清（§11.1）。
2. **【P1 验收缺口】G-4 D-13 instance-id 生命周期无验收项**：身份幂等前提本身未验收，须补全（§11.2）。
3. **【P1/V】D17-1 --reload 锁交接窗口**处理设计未明确，须澄清+真实验证（§11.3）。
4. **【V】关键集成项尚待真实证据**：msvcrt lifespan/--reload/POSIX/CLI 同锁、PG staging restore/rename/OID 对账/advisory 碰撞、Windows os.replace 占用/崩溃、approve 钩子故障全回滚、S0/S1 确定性交错——R1 §19.8 诚实列为待验证，模块当前 greenfield，本轮只读边界未执行这些真实运行。**原语/工具链验证不等同于集成验证**，开发阶段须以真实 SQLite/PG/Windows/多进程/故障注入验收，通过前不得宣称完成。
5. **【P2】若干设计澄清与验收缺口**（§11.4-11.8）建议补充，非阻断但应在冻结前/开发中落实。

**未给 FAIL 的原因：**
- **无 P0 致命/不可实现/不可逆数据安全设计缺陷**；全部问题可在 R1 既有约束内（无新迁移/不改冻结端口/不弱化安全）解决。
- R1 诚实声明限制（应用层幂等非 DB 强制、digest 非安全边界、单实例范围、待验证项），未虚报、未把离线 SQL 当真实验证、未把规划写成已完成。
- 核心原语（msvcrt）与工具链（Online Backup/pg_dump）经真实验证成立，架构与真实代码结构兼容。

**数据安全要求未被弱化**：本审计如实标记读路径缺陷与全部待验证项，未为通过而放宽幂等/原子性/恢复一致性/单实例约束；CONDITIONAL PASS 的条件均为**加强**澄清与验收，而非降低安全标准。

### 后续步骤（遵守执行边界）

- 本报告完成后**停止**，等待 ChatGPT 独立复审。
- **不自行开始 A1-04 开发**，不启动 Batch A。
- 不修改 R1 四份文档（Temp）与仓库原始四份；不修改业务代码/测试/迁移/lockfile/依赖；不提交/推送/重置/切换分支。
- R1 修订与批准由 ChatGPT/用户决定；批准后按 README 流程（Qoder 同步 R1 至 docs/plans/ + 只读一致性检查 → 冻结 → Batch A）另行执行，**非本轮**。

---

### 附录：本轮真实证据清单

- Git：HEAD 784b124…、branch fix/m0-admission-and-m5-regressions、M0 2d2b634…、tracked/staged 空（§1）。
- 文档指纹：R1 五份 + 原始四份 blob SHA-1（git hash-object）+ 行数，原始未变、R1≠原始（§2）。
- msvcrt 探针：T1 空文件锁成功 / T2 同进程 EXCLUDED / T4 跨进程 CHILD EXCLUDED / T3 close 后 CHILD ACQUIRED；LK_NBLCK=2/LK_UNLCK=0（§5.1）。
- 环境：Python 3.11.9、SQLite 3.45.1（Connection.backup True）、PG 16.8 原生运行中 PID 50260、pg_dump/pg_restore 16.8、EXPLAINLAB_PG_TEST_URL 未设（§1/§6/§8）。
- greenfield：process_lock/storage_lock/import_coordinator/import_review_hook/markdown_item_repository/backup/app/ops 均不存在（§1）。
- 代码引用：governance.py 303-321/324-334/337-349/352-375(365/369/370/371-373/374)/378-391(387/390)；review/__init__.py 85-96(94/95)/98-105/107-113/129-143(134-141)/145-168；links.py 519-527/530-534/537-541；link_service.py 630/643-648/726-799/823；routes/knowledge.py 51-65/89-97；services/knowledge.py 28-48/102-112；session.py 60-66/76-85(84-85)/88-102；ports.py 40-74/276/305-353/403-434/437-464；models.py 98-127(112/114-116)/187-202/410-435(418-421)/438-451；schemas.py 84-94/103-109；0006:75/84/104/125-127/143/166-167/182-186/197。