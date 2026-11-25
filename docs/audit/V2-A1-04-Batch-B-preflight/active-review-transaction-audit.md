# Active Review Transaction Audit

## 1. 范围与入口

- 提交侧：`MarkdownService._apply_import()` → Core `ReviewService.submit()` → `ReviewRequest`（pending）。
- 批准侧：`POST /reviews/{review_id}/approve` → `approve_review()`。
- 拒绝侧：`POST /reviews/{review_id}/reject` → `reject_review()`。
- 钩子：`ImportReviewHook.apply_approved()` / `apply_rejected()`。
- Core 应用：`knowledge_core.review.ReviewService.approve()`。
- 会话：`app.db.session.create_session()`。

本报告只描述真实代码路径，不修改任何行为。

## 2. 提交侧（生成 pending）

`backend/app/services/markdown.py` 的 Active 导入路径：

1. 读取既有条目，构造 `ChangeSet`。
2. 判定需要审核后，构造 `ImportEnvelope`，再经 `review_payload(core_changes)` 合并为 Review payload。
3. 调用 Core `ReviewService.submit(item_id, UPDATE_ITEM, payload, reason)`。
4. `ReviewPolicy.is_important(UPDATE_ITEM, ACTIVE)` 为真 → 只保存 `ReviewRequest`，**不应用** item 变更。
5. 同会话写 `ImportOrigin`、tags、links 等？——当前导入分支在 pending 生成时只写审核单；实际 item/tags/origin/links 的补齐在 approve 钩子完成。
6. `session.commit()` 保存 pending。

**关键事实：`MarkdownService._envelope(...)` 当前硬编码 `attachments=[]`。因此 Batch A 永远不会生成带附件 manifest 的 pending。** 标签：已实现（Batch A 语义）。

### 2.1 `__a1_import` 包络

`ImportEnvelope`（`import_report.py:222-279`）：

- `extra="forbid"`，未知键拒绝。
- `schema_version` 必须等于 `IMPORT_ENVELOPE_SCHEMA_VERSION`（当前 1）。
- `attachments: list[dict[str, Any]]` 字段**已存在**，当前无元素 schema、无大小/数量限制。
- `context_digest = sha256_canonical(body excluding context_digest)`；读取时重算并比对。
- 摘要覆盖整个 envelope，包括 `attachments` 与 `links`；因此 manifest 内容在 S0→S1 之间被任何改动都会被 409 拒绝。
- 摘要**不是签名**，不防同信任域内的伪造；docstring 明示。

**结论：从数据形状看，附件 staging manifest 的天然位置就是 `payload.__a1_import.attachments`，无需新增顶层字段。** 标签：部分实现（字段存在，语义为空）。

## 3. 批准侧真实时序

```text
POST /reviews/{id}/approve
│
├─ S0: create_session()
│    ├─ _pending_review(id)                 # 404 / 409
│    ├─ 非导入 → 返回 (payload, None, None)
│    └─ 导入   → envelope_from_review()     # 结构+版本+摘要校验
│                 → 必须 UPDATE_ITEM
│                 → 返回 (payload, digest, lock_key)
│    close()
│
├─ coordinator.keyed(lock_key)              # 同身份/同条目有界等待（10s）
├─ identity.identity_guard()                # 与 MATERIALIZE/ROTATE 串行
│
└─ S1: create_session()
     ├─ _pending_review(id)                 # 重新读取
     ├─ envelope_from_review()              # 重新解析
     ├─ s0_digest == digest(pending.payload)  # 获锁前被改 → 409
     ├─ service = build_review_service(session)
     ├─ _demote_backlinks_before_delete()   # DELETE 预降级，写 DB
     ├─ asyncio.run(service.approve(...))
     │    ├─ _pending() 再校验 PENDING
     │    ├─ review.status = APPROVED; resolved_at; note
     │    ├─ reviews.update_review(review)  # flush
     │    └─ _apply_action:
     │         UPDATE_ITEM:
     │           ├─ 读 item
     │           ├─ versions.create_version(item, "编辑前快照")
     │           ├─ 覆盖 title/content/status/space_id
     │           ├─ item.updated_at = utcnow()
     │           └─ items.update(item)      # flush
     ├─ 导入分支: ImportReviewHook.apply_approved(review, envelope)
     │    ├─ envelope.attachments 非空 → 立即 400（当前）
     │    ├─ target 一致性 / exporter 保留键
     │    ├─ item 存在
     │    ├─ identity.has_committed_materialize → fail-closed 409
     │    ├─ ImportOrigin（去重后）
     │    ├─ extra_metadata / source hashes
     │    ├─ tags + TagChangeRecord
     │    └─ build_link_restorer().restore(links)
     ├─ session.commit()                     # ① 业务提交（第 470 行）
     ├─ asyncio.run(_sync_applied_action(...))  # 同 session 同步索引
     │    ├─ sync_index → FTS upsert / 向量重算
     │    └─ ModelAdapterError 被吞并告警；其他异常上抛
     ├─ session.commit()                     # ② 索引提交（第 476 行）
     └─ return ReviewOut
```

### 3.1 事务边界

| 边界 | 内容 | 事实 | 标签 |
|---|---|---|---|
| S0 | 只读 pending + envelope | 独立会话，`finally close` 无 commit | 已实现 |
| S1 事务① | 审核状态、版本快照、item、origin、tags、tag log、links | 单次 `commit()` 全部落库 | 已实现 |
| 事务② | 索引/FTS/向量 | 第二次 `commit()` | 已实现 |
| 异常（业务/hook） | `rollback()` | pending 保持 PENDING，item/版本/origin/tags/links 全部回滚 | 已实现 |
| 事务①后异常 | `rollback()` | 业务已提交，无法回滚；异常继续上抛 | 已实现（现状） |
| 拒绝 | 审核状态 → rejected | 单次 commit；`apply_rejected` 空操作 | 已实现 |

**注意：`approve_review` 的 docstring 写“单次 commit”，但真实代码是两次 commit（第 470、476 行）。附件引用必须进入事务①，不能落在事务②。** 标签：需要 ChatGPT 决策（文档与代码不一致的表述是否修正，属 Batch B 文档同步，不在本轮改动）。

### 3.2 锁关系

| 锁 | 获取位置 | 作用域 | 备注 | 标签 |
|---|---|---|---|---|
| `ImportCoordinator.keyed` | 路由层，S1 之前 | 同身份键或同 target item | 进程内 `threading.Lock`，10s 有界等待，跨进程无效 | 已实现 |
| `identity_guard` | 路由层，S1 全程 | 进程内 + 身份 Journal 恢复门 | 与 MATERIALIZE/ROTATE 串行 | 已实现 |
| StorageKeyLock | 不存在 | — | 需 Batch B 新增 | 未实现 |

**锁键规则（`_review_lock_key`）：**

- 有完整 `source_instance_id + source_document_id` → `identity:<sha256(canonical pair)>`。
- 否则 → `target-item:<item_id>`。
- 这意味着“同一文档的导入提交”和“该文档的审核批准”互斥；不同文档可并发。

**拒绝路径只拿 `coordinator.keyed`，不拿 `identity_guard`。** 对纯 Batch A 无影响；若 Batch B 的 reject 需要清理 staging 或与身份物化互斥，是否补 `identity_guard` 必须决策。标签：需要 ChatGPT 决策。

## 4. `ReviewRequest.payload` 与 manifest 的承载

当前 `ReviewRequest`：

```python
id, item_id, action, payload: dict, reason, status,
created_at, resolved_at, resolution_note
```

- `payload` 直接 JSON 文本存 `review_request.payload`。
- `ReviewOut` 原样返回 `payload`；前端/客户端可见完整 `__a1_import`（含 attachments 若未来非空）。
- `ReviewSubmit` 接受任意 `payload: dict`；没有服务端 schema 白名单。
- `ReviewResolve` 只有 `note`，批准时不能追加新 manifest。

**因此，如果 Batch B 采用“提交时已 stage、manifest 随 pending 固化”的模型，当前表结构和 DTO 已足够，不需要新列/新表。** 标签：已实现（承载能力）。

**如果要求批准时才上传附件或补 manifest，则必须改 `ReviewResolve`，并处理 submit→approve 之间的 TOCTOU。** 标签：需要 ChatGPT 决策。

### 4.1 三种 manifest 方案对比（供决策，不实施）

| 方案 | 形状 | 优点 | 风险 | 标签 |
|---|---|---|---|---|
| A. 提交时写 `__a1_import.attachments` | 复用现有 envelope 字段 | 无 schema 变更；digest 自动覆盖；S0/S1 双校验现成 | 提交时必须已有 staging 文件；`attachments` 元素 schema 需定义 | 需要 ChatGPT 决策 |
| B. approve 时 `ReviewResolve` 带 manifest | 新 DTO 字段 | 可先审后传 | 需改冻结的 ReviewResolve；approve 前文件可被替换；需二次 digest | 需要 ChatGPT 决策 |
| C. 独立 staging 表/会话 | 新表或复用表 | 显式生命周期 | §21.5 禁止新表；若复用 `gc_task` 语义污染 | 需要 ChatGPT 决策 |

## 5. 附件整合到 approve 的关键问题

### 5.1 写入顺序

物理文件与 DB 不在同一事务。可选的正确顺序只有一种方向：

```text
校验 manifest + staging 文件（S1 内、写 DB 前）
→ 逐附件获取 StorageKeyLock（按 storage_key 排序）
→ 将 staging blob 原子“提升”为正式 blob（同卷 rename 或 no-overwrite link）
→ 插入 attachment 引用行（同一 S1 事务）
→ 事务① commit
→ 释放 StorageKeyLock
```

- **绝不能先插 DB 引用再提升文件**：commit 后会出现“DB 有引用、磁盘无文件”的不可恢复态。
- 先提升文件后 commit，最坏是“磁盘有 blob、DB 无引用”的孤儿，可由独立扫描回收，是安全方向。
- 多附件时若第 N 个失败，前 N-1 个 blob 已成为孤儿；DB 尚未 commit，引用行回滚。重试必须幂等（同 storage_key 已存在则复用）。标签：需要 ChatGPT 决策（all-or-nothing vs 逐件）。

### 5.2 与 Core approve 的先后

Core `approve()` 已经：
1. 改审核单状态；
2. 创建编辑前版本快照；
3. 改 item 四字段。

这些都只是 flush，尚未 commit。钩子在 Core 之后执行，因此：

- 附件引用插入时，item 新内容已在 session 中；
- 若附件失败，整个 S1 `rollback()` 会把审核单恢复为 PENDING、版本快照和 item 修改一并回滚；
- **staging 文件不能因 rollback 被删除**，否则重试批准时文件已丢。清理只能在“确定不再需要”后做。标签：需要 ChatGPT 决策（失败后 staging 保留策略）。

### 5.3 commit 失败

- 事务① commit 失败 → DB 全回滚（pending 保留）；已提升的 blob 成为孤儿；staging 若已被 rename 移走，则重试时缺失。
- 因此“提升”应优先用 **copy + fsync + no-overwrite link/rename** 或“先 link 到正式区、保留 staging 原件”，使重试可重复。纯 `os.replace` 会移走 staging 原件，降低可重试性。标签：需要 ChatGPT 决策（rename vs link/copy）。
- 若 staging 与正式区跨卷，`rename/link` 会 `EXDEV`；设计要求同卷。配置必须约束或启动时校验。标签：需要 ChatGPT 决策。

### 5.4 索引第二次 commit

- 附件元数据不参与 FTS/向量；索引同步只针对 item 内容。
- 事务②失败不影响已提交的附件引用；但若 `sync_index` 抛非 `ModelAdapterError` 异常，路由会 `rollback()`（对已提交事务是 no-op）并返回 500，客户端可能误以为批准失败而重试；重试会命中文档已 APPROVED → 409。标签：已实现（现状风险）。

### 5.5 拒绝路径

当前：

```text
S0 → coordinator.keyed → S1 → service.reject → apply_rejected(no-op) → commit
```

Batch B 需要在拒绝后清理 staging。顺序必须是：

1. 先 commit `REJECTED`；
2. 再删除 staging 文件；
3. 删除失败仅告警，交由 staging 清扫（仅清理无 pending 且超过宽限期的文件）。

若先删文件再 commit，commit 失败会使 pending 审核单失去附件，无法再批准。标签：需要 ChatGPT 决策。

### 5.6 删除条目与附件 GC

- Core `DELETE_ITEM` 直接 `items.delete(item_id)`；DB FK 级联删除 attachment 行。
- 当前没有钩子在删除前读取 attachment storage_key 并 enqueue GC。
- 若 Batch B 要求“删除后引用归零的 blob 进入 GC”，需在 `_demote_backlinks_before_delete` 同类位置增加附件预读取 + GC 任务写入，且与删除同一事务。标签：需要 ChatGPT 决策。
- 若完全依赖独立孤儿扫描，则删除无需特殊处理，但有最长一个扫描周期的延迟。标签：需要 ChatGPT 决策。

### 5.7 合并（MERGE_DUPLICATE）

- 当前 `_apply_merge` 只迁移 `source_refs`，不迁移 attachment。
- 源条目归档而非删除，附件仍挂在源条目上，可访问。
- 设计未要求合并迁移附件；若产品要求“合并后附件归目标”，必须新增逻辑。标签：需要 ChatGPT 决策。

## 6. 不破坏 Batch A 冻结行为的边界

| 冻结行为 | 附件整合时如何保持 | 标签 |
|---|---|---|
| 空 `attachments` 的导入/审核行为完全不变 | 钩子仅在 `attachments` 非空时走新分支；空列表保持现有路径 | 已实现（当前行为，必须保持） |
| `ATTACHMENT_REVIEW_UNSUPPORTED` 稳定码 | 若 Batch B 支持附件，该码不再对合法 manifest 返回；需明确是否保留给“非法/未启用”场景 | 需要 ChatGPT 决策 |
| 审核单状态机与两阶段提交 | 附件引用只在事务①，不新增 commit | 已实现（当前行为，必须保持） |
| S0 只读、S1 重读 | manifest 校验在 S0 可做结构校验，权威校验在 S1 | 已实现（当前行为，必须保持） |
| `identity_guard` 覆盖 S1 | 文件提升与 DB 写入都在 guard 内 | 已实现（当前行为，必须保持） |
| digest 防篡改 | manifest 已在 digest 覆盖范围内 | 已实现（结构上） |
| `context_digest` 非签名 | 不得把 digest 当授权凭证 | 已实现（当前行为，必须保持） |
| V1/非导入审核不受影响 | 附件逻辑只在 `is_import` 分支 | 已实现（当前行为，必须保持） |

## 7. 结论

**Batch B 的最小侵入点是 `ImportReviewHook.apply_approved()`：在现有 Core approve 之后、事务① commit 之前，校验 manifest、取得 storage-key 锁、提升 blob、插入引用行。S0/S1、身份锁、digest 校验、两阶段 commit 均可原样复用。** 标签：需要 ChatGPT 决策（最终方案）。

**未决的核心问题不是“能不能放进去”，而是“staging 生命周期与失败重试语义”：manifest 何时固化、promote 用 rename 还是 link/copy、失败后 staging 保留多久、拒绝/删除如何清理。** 标签：需要 ChatGPT 决策。