# Active Review Integration

本文件冻结附件 staging manifest 与 Active Review approve/reject 的集成方式。**不修改** Core `ReviewService`；唯一插入点是既有 `ImportReviewHook` 与 `governance` 路由的提交边界。

## 1. 既有事实（基线 `970c0d8`）

- `ReviewResolve` 只有 `note`，没有 approve-time manifest 字段。
- `ImportEnvelope` 存于 `ReviewRequest.payload.__a1_import`，`attachments: list[dict]` 目前为空。
- `ImportEnvelope.compute_context_digest()` 已把 `attachments` 纳入摘要；`from_review_payload()` 校验版本与摘要，结构非法 fail-closed。
- `approve_review()` 顺序：S0 只读预检 → `ImportCoordinator` 身份键锁 + `identity_guard` → S1 新会话 → 重读并比较 payload 摘要 → Core `ReviewService.approve()`（仅 flush）→ `ImportReviewHook.apply_approved()` → `session.commit()`（业务）→ 索引同步 → `session.commit()`（索引）。
- Batch B 保留 Core → DB Hook → ①，增加 review 决议锁、staging guard 和写事务前物理发布，见 §2。
- `ImportReviewHook.apply_approved()` 当前第一步是：`if envelope.attachments: raise ATTACHMENT_REVIEW_UNSUPPORTED`。Batch B 必须替换该拒绝，但保留错误码用于“能力未启用/不受支持”。
- `reject_review()` 当前提交 reject 状态；`apply_rejected()` 是 no-op。

## 2. 决议锁与事务骨架

1. S0 严格只读预检，关闭会话。验证 envelope 版本/摘要，验证附件元素结构并收集 key。结构或摘要失败返回 §8 对应码，不获取 storage lock。
2. 按 architecture §6 先取得所有 approve/reject 共用的进程内 `review_id` 决议锁，再取既有来源锁、`identity_guard`。D23 恢复可以合法写 DB，但恢复门及内部事务必须在附件取锁之前完成、关闭。随后取得可信 staging ID 的 staging guard，再取齐 StorageKeyLock。
3. 持 guard 用独立短只读会话复核 S0、目标、归档及来源前置；关闭会话。随后校验 staging、复制、重读 Hash、发布 no-clobber，生成发布计划。Core、Hook 和业务写尚未执行。
4. S1 新会话复核 PENDING、payload 摘要及发布计划；在 Core 前执行 archive 防护（architecture §4.4），然后 Core approve → DB Hook → 同业务 session 末次 fencing → commit ①。每一失败路径先结束业务事务，再释放存储锁；pending 原件仍可重试。
5. ① 后释放存储锁、在 staging guard 内尽力清理，再释放所有业务 guard。② 提交后索引同步使用独立事务/会话，失败仅告警与回滚②，返回已经保存的批准状态。已有随①触发的索引行为保持；无附件旧路径保持 Batch A 契约。

## 3. Manifest 元素 schema

### 3.1 位置

- 唯一位置：`ReviewRequest.payload.__a1_import.attachments`。
- 创建 pending 时写入；approve 只读、校验、执行。
- **approve 请求不得携带 manifest**；`ReviewResolve` 不新增字段。approve 时发现 envelope 缺失/摘要不符 → 409 `IMPORT_ENVELOPE_INVALID`。
- 不得在 approve 时追加、删除、重排元素；不得“补写”缺失元素。

### 3.2 元素定义（`AttachmentManifestItem`，backend 所有）

```json
{
  "schema_version": 1,
  "staging_id": "3f2c1a9e-7b6d-4c2a-9f10-8e7d6c5b4a31",
  "ordinal": 1,
  "blob": "blobs/000001.bin",
  "filename": "design.png",
  "mime": "image/png",
  "size": 184320,
  "storage_key": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
}
```

| 字段 | 约束 |
|---|---|
| `schema_version` | 整数，必须 `1`；创建 staging 时不支持 → `ATTACHMENT_MANIFEST_INVALID`（422）；approve 时发现不支持/被改 → `ATTACHMENT_MANIFEST_CORRUPTED`（409） |
| `staging_id` | 小写 UUIDv4 字符串；同一次导入所有元素相同；必须与目录名一致 |
| `ordinal` | 整数 1–100；同一 manifest 内唯一；用于确定性排序，不要求连续 |
| `blob` | 严格 `^blobs/[0-9]{6}\.bin$`；与 ordinal 的六位编码一致，解析后位于该 staging 根内的普通文件，禁止链接与重解析点 |
| `filename` | 1–500 字符；禁止 NUL/CR/LF/控制字符/`/`/`\`/`:`/`..`；仅展示与下载头，不进入路径 |
| `mime` | 白名单内；不得为 `image/svg+xml`；必须通过 API §4.2 对应检测（二进制 magic；文本严格 UTF-8，不区分子类型） |
| `size` | 整数 1–10 MiB；必须等于实际文件大小 |
| `storage_key` | 小写 64 hex；必须等于实际字节 SHA-256；等于 `content_hash` |

- 元素使用 `extra="forbid"`；未知字段拒绝。
- 同一次单文档导入中重复 `storage_key` → 422 `ATTACHMENT_MANIFEST_DUPLICATE`（不做静默去重）。
- 单次导入最多 100 个、总字节最多 100 MiB（O-B05 已裁决）；超限 413。
- MIME 校验区分二进制 magic 与文本 UTF-8：二进制类型按 magic 判定；文本类型（`text/plain`/`text/markdown`/`text/csv`）只做严格 UTF-8 + 无 NUL 校验，不声称仅凭文本字节可区分三者；以声明的白名单文本 MIME 为准。
- manifest 的完整性由 `ImportEnvelope.context_digest` 覆盖（已包含 `attachments`）；不新增独立摘要字段。
- 不新增 DB 表/列存 manifest；不把 manifest 写入 `attachment` 表。

### 3.3 与 `MarkdownDocument.attachments` 的区别

- `MarkdownDocument.attachments` 是 Markdown 层附件引用；Batch B 的 ZIP staging manifest 是**待提升的物理附件**。
- 二者不得混用；approve 只执行 envelope 的 `attachments`。Markdown frontmatter 中的附件引用在 Batch B 不产生正式 `attachment` 行（除非未来单独裁决）。
- 现有 `classify_changes(current_attachments=[])` 的硬编码是 Batch A 限制。Batch B 的 staging manifest 是“待提升物理附件”，**不得**直接当作 `MarkdownDocument.attachments` 参与变化分类。
- **O-B08**：没有 title/content 变化的 Active 导入不独立触发 review。附件逻辑集合、同来源 pending 和已应用重试的决策见 attachment-lifecycle §3.1。独立上传仍可给非 archived item 新增附件。
- 该限制记录于 `risk-register.md`；不得通过修改 Core 的 change classifier 实现附件-only 触发。

## 4. Pending 阶段约束

- pending 创建时：staging 已完整写入并校验，`.complete` 存在；manifest 已写入 envelope；**`attachment` 表零新增行**。
- pending 的任何读取/展示不得把 staging 当作正式附件；不得返回正式下载 URL。
- 同一来源已有 pending 先按 attachment-lifecycle §3.1 判定复用或冲突，二者均不新建 staging 或第二个 pending。
- pending 长期搁置：staging 保留；pending 引用优先于任何时间判断；ORP 不得删除被 pending 引用的目录。
- pending 期间 item 被删除/归档：approve 在 Core 写之前失败 → rollback，review 保持 pending；staging 保留。item 变 `archived` 时附件新增必须失败（`ATTACHMENT_ITEM_ARCHIVED`），不得因 pending 已存在而绕过 O-B06。

## 5. Approve 执行细节

### 5.1 预发布与 Hook 的职责

- 持 review、来源、身份、staging、storage guard，在发布前只读检查 target、exporter metadata、来源和已物化标记。D23 恢复门已在取锁前运行；后续读取 COMMITTED 证据只能使用已恢复 guard 下的只读路径。若恢复仍需写，停止并释放本次存储 guard，再从恢复门重新进入，禁止在业务写中启动恢复。
- staging 字节、完成标记、MIME、Hash、大小均在发布前验证，与 manifest 逐项对照。复制/发布产出服务端不可变计划，含目标、payload 摘要、staging_id 与准确 key 集合。存储层不会写引用。
- Hook 在 Core 后使用同一 S1 session 做既有 origin/tags/links 和附件 DB 引用补齐，只接受已验证计划。计划与 S1 摘要/manifest 或 guard key 不符即回滚。不在 Hook 里补取锁、打开 staging、复制、校验文件 Hash、发布或提交。目标是否 archived 以 Core 前受保护状态为准，Core 之后看到的 Draft 不能作为放行依据。

### 5.2 路由职责与失败

- `approve_review` 保持同步。在共同 review 锁内先按 §2 走预发布，再开新的 S1。锁超时返回 409 `STORAGE_LOCK_TIMEOUT`，commit 前任一 key 失效返回 503 `STORAGE_LEASE_LOST`。S1 发现 payload 或发布计划漂移，回滚并返回 409 `IMPORT_ENVELOPE_INVALID`，已发布孤儿留给 ORP。
- ① 提交/回滚后才释放 StorageKeyLock；释放幂等，失败只告警，PG 物理关闭兜底。① 完成后固化 ReviewOut；清理 staging 失败和②失败不改变批准结果。② 在所有业务协调 guard 退出后运行。

### 5.3 正式引用写入

每个 manifest 元素写一行：

```text
Attachment(
  id=uuid4(),
  item_id=review.item_id,
  filename=manifest.filename,
  mime=manifest.mime,
  size=manifest.size,
  storage_key=manifest.storage_key,
  content_hash=manifest.storage_key,
  created_at=utcnow(),
)
```

- 同一 approve 中重复 `(item_id, storage_key)` 已在 manifest 校验阶段拒绝。
- approve 前必须检查“item 是否已有同 `storage_key` 引用”：若已有，复用既有行，不新增重复行，manifest 元素仍视为成功。该检查在 Hook 内用 `list_attachments(review.item_id)`。
- 跨 item 共享：各自新增一行；blob 共享。
- `AttachmentRepository.save_attachment()` 只 flush；不 commit。

### 5.4 清理 staging

- ① commit 成功后：对每个 `staging_id` 调用 `staging.discard_committed(staging_id)`；失败只告警，ORP 兜底。
- ① 失败/回滚：**不清理 staging**；review 仍 pending，可重试。
- ② 失败：① 已提交；staging 清理在②前尽力执行；业务/附件不回滚。

## 6. 失败与崩溃矩阵

| 时点 | review | Attachment 行 | 正式 blob | staging | 处理 |
|---|---|---|---|---|---|
| envelope 摘要/结构失效，或摘要合法但附件元素非法 | pending | 无 | 无 | 保留 | 409 `IMPORT_ENVELOPE_INVALID` 或 `ATTACHMENT_MANIFEST_CORRUPTED`（§8） |
| staging 目录缺失 | pending | 无 | 无 | 缺失 | 409 `ATTACHMENT_STAGING_MISSING` |
| `.complete` 缺失/不一致 | pending | 无 | 无 | 保留 | 409 `ATTACHMENT_STAGING_INVALID` |
| 目标 item 已 archived 或在预发布后归档 | pending | 无 | 早拒为无，竞态可有孤儿 | 保留 | 409 `ATTACHMENT_ITEM_ARCHIVED`；零业务提交 |
| staging 文件缺失/hash 不符 | pending | 无 | 无 | 保留 | 409 `ATTACHMENT_STAGING_INVALID` |
| 锁超时 | pending | 无 | 无 | 保留 | 409 `STORAGE_LOCK_TIMEOUT` |
| 发布中 I/O 失败 | pending | 无 | 部分孤儿 | 保留 | 500/503；ORP |
| 发布后、① commit 前崩溃 | pending（回滚） | 无 | 孤儿 | 保留 | 重启重试；ORP 不删被 pending 引用 staging |
| ① commit 成功、响应前崩溃 | approved | 有 | 有 | 残留 | 客户端重试读状态；ORP 清理 staging |
| ① commit 成功、② 失败 | approved | 有 | 有 | 可能残留 | 业务已提交；索引失败告警；不回滚 |
| ① commit 失败 | pending | 无 | 孤儿 | 保留 | 回滚；可重试 |
| 释放锁失败（路由/Hook 返回后） | approved/pending | 视 commit | 视 commit | 视情况 | 告警；租约过期/连接关闭释放 |

## 7. Reject 集成

1. 轻量 S0 仅确认 pending。始终先取与 approve 共用的 `review_id` 决议锁。来源键从能可信解析的 envelope 取，失败使用 target-item fallback；即使两条路由的来源键不同，仍由同一决议锁串行。
2. 在决议锁下重读当前 pending。只有通过既有 envelope 完整性、元素/目录 ID 和 pending 所有权核对的 staging 才取 staging guard。损坏或无法证明归属时跳过清理，仍可 reject。普通审核无 envelope 属正常。
3. Core reject flush → no-op Hook → commit；先提交状态，然后在持 staging guard 下重新确认无其他 pending 引用再尽力清理。清理失败只告警，ORP 兜底。拒绝不触碰正式 blob/引用，也不新增 GC 任务。
4. 两条路径的 S1 及决议 commit 都处于同一个 `review_id` 保护区，后到者看到终态并按既有 409 行为退出。① 失败则无终态及 staging 清理。单 Backend/单 worker 适用。

## 8. 与 S0/S1 摘要校验的关系

- S0 只读预检读取 payload 并计算 `_payload_digest`；该摘要包含 `__a1_import.attachments`，因此 manifest 在获锁前被改动会被 409 `IMPORT_ENVELOPE_INVALID` 拒绝。
- `envelope_from_review()` 校验版本/摘要，失败为 `IMPORT_ENVELOPE_INVALID`。只有摘要合法但附件元素不符 schema 时才返回 `ATTACHMENT_MANIFEST_CORRUPTED`。缺 staging 目录与目录存在但无效分别返回 `ATTACHMENT_STAGING_MISSING` / `ATTACHMENT_STAGING_INVALID`。
- 不新增 approve-time manifest 参数；不新增“manifest 补丁”接口。
- 摘要不是签名：本机数据库写权限仍可伪造；不得宣称密码学不可篡改。

## 9. 与 Draft/普通导入的关系

- 新建 Draft（无 Active review）：附件引用与文档同一 DB 事务提交；staging 在提交前已存在；正式 blob 必须在开启该 DB 写事务前完成锁定/发布（SQLite 写锁约束），提交后清理。此路径不经过 approve。
- Active 内容变更：生成 pending，附件只在 approve 时提升。
- 导入 transport 固定 ZIP-only（O-B01）：JSON 单篇 HTTP 400、批量逐篇 unsupported；不新增 multipart。
- Active 附件-only 导入：显式 400 `ATTACHMENT_ONLY_IMPORT_UNSUPPORTED`，不创建 staging/pending/attachment 行。
- 若附件能力被配置关闭：approve 遇到非空 manifest → 400 `ATTACHMENT_REVIEW_UNSUPPORTED`（保留码），不执行任何物理/DB 变更。

## 10. 明确禁止

1. 在 `ReviewResolve` 增加 manifest 字段。
2. 在 approve 时向 envelope 写 `attachments`。
3. 在 pending 阶段插入 `attachment` 行。
4. 在 Hook 内 commit 或提前释放 StorageKeyLock。
5. 修改 Core `ReviewService.approve/reject`。
6. 用 staging 路径作为正式下载路径。
7. 在 reject commit 前删除 staging。
8. 把索引事务②的失败当作业务回滚理由。
9. 宣称“附件与 item/tags/origin/links 在物理文件层面原子”。
10. 在 SQLite 写事务仍开启时用独立连接获取 StorageKeyLock，或在业务写事务内复制、重读 Hash 与发布。
11. 在 PG 上仅凭 `storage_lock` 行 TTL 过期就接管/删除；必须有存活的 Advisory Lock。
12. 让 Active 附件-only 导入静默成功/忽略附件，或修改 Core 变化分类器实现附件-only 触发。
13. 向 `archived` item 新增附件（包括 pending 期间被归档后 approve）。
14. 在下载路径按 storage_key 重新 open 文件做校验/输出。
