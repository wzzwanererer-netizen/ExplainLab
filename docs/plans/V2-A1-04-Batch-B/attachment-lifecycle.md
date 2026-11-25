# Attachment Lifecycle

> **Architecture Freeze Approved · 2026-11-23（北京时间）**。本文件属于正式冻结的设计基线。设计冻结不代表实现验收通过；真实 PostgreSQL、Windows/POSIX 与故障注入取证仍待执行。架构变更须经正式审批。

本文件定义附件从“字节进入系统”到“引用消失、物理回收”的完整生命周期。物理操作与 DB 事务的边界见 `architecture.md` §4；锁细节见 `storage-and-lock-contract.md`。

## 1. 生命周期总览

```text
独立上传（JSON base64，O-B09）:
  字节 → 临时文件 → hash → 锁 → 发布正式 blob → DB 引用 → commit → 释放锁
  失败: 临时/孤儿 blob 由 ORP 收敛

独立列表/下载/删除:
  列表：只读元数据，不取 StorageKeyLock
  下载：单个已打开句柄完成 size/hash 校验并流式输出（不按路径重开）
  删除：删引用 + 入队 gc_task(pending) 同一事务 → commit
    → GC 持锁复核并 quarantine → 自隔离时间起至少 24h → 持锁 purge

导入（ZIP-only，O-B01）:
  ZIP attachments/ → staging（.creating/.activity/.complete）→ manifest 元素
    → pending review envelope
    → approve: 预取锁 → 复制/校验/发布 → 附件引用进入事务① → commit → 清理 staging
    → reject: 提交 reject 状态 → 清理 staging（不触碰正式 blob）
    → 崩溃: staging 由 ORP 按 pending 引用 + 活动时间判定
  JSON 附件字段：单篇 HTTP 400；批量逐篇 unsupported，沿用 ATTACHMENT_IMPORT_UNSUPPORTED
  Active 附件-only 导入：400 ATTACHMENT_ONLY_IMPORT_UNSUPPORTED（不建 staging/pending）

条目删除:
  FK CASCADE 删引用 → 无 gc_task → ORP 发现 mtime 满 24h 的无引用 blob → 入 GC

MERGE_DUPLICATE:
  不迁移附件；源条目附件保持原引用；若源条目随后被删除，走 ORP

Archived item（O-B06）:
  禁止新增上传；允许列表/下载/删除引用
```

## 2. 独立上传

### 2.1 前置校验

1. 路径中的 `item_id` 必须存在；不存在 → 404 `ITEM_NOT_FOUND`。
   - `archived` item 禁止**新增**附件：返回 409 `ATTACHMENT_ITEM_ARCHIVED`；不得先写临时文件/发布后才发现。
   - `archived` item 仍允许列表、下载、删除既有附件引用（O-B06）；`deleted`/不存在的 item 按 404 处理。
2. JSON 请求体只允许 `filename` / `mime` / `content_base64`；额外字段由 `extra="forbid"` 拒绝（422），缺字段同样 422。**不使用 multipart**（O-B09，不新增 `python-multipart` 依赖）。
3. 文件名必填，长度 1–500；清洗为安全显示名（basename、去除控制字符/路径分隔符、`..` 折叠），仅用于展示与下载头；不进入磁盘路径。
4. 声明 `mime` 必须在白名单；SVG 直接拒绝；实际内容必须与声明一致（`api-contracts.md` §4，二进制 magic 与文本 UTF-8 分开判定）。
5. 严格 Base64 解码；非法编码 → 400 `ATTACHMENT_BASE64_INVALID`；解码后累计字节；超过 10 MiB → 413 `ATTACHMENT_TOO_LARGE`，不写临时文件。
6. 服务端计算 SHA-256；`storage_key=content_hash`。

### 2.2 去重

- 先查该 item 现有引用：若存在 `(item_id, storage_key)`：
  - 返回 200 + 既有 `AttachmentOut`；
  - 若正式 blob 存在且 hash 一致，不重写；
    - 若正式 blob 缺失，在非 archived 的前提下按 §2.3 重新发布，仍返回既有引用；
  - 若正式 blob 存在但 hash 不一致 → `ATTACHMENT_KEY_COLLISION`，不覆盖。
- **进入业务写事务后必须再次查询** `(item_id, storage_key)`：并发上传在同一 key 锁释放后可能已由前一个请求插入；若已存在则复用该行、删除临时文件、返回 200，禁止插入重复行。
- 预检查询只用于快速路径；其只读 session 必须在 `acquire` 前关闭/rollback。锁内二次查询应使用随后执行写入的同一 session，避免在 SQLite 默认 rollback journal 下“读事务阻止锁行 commit”。
- 不存在则创建新引用。跨 item 共享同一 blob，但各自有 `attachment` 行。
- `find_by_hash` 不作为唯一去重依据（无 `content_hash` 索引，见 D-B05/D-B09）。

### 2.3 发布与提交

1. 预检 item 存在且未 archived，关闭读取会话。校验请求、写临时文件并重读 Hash。
2. 获取 StorageKeyLock，再按存储契约校验/发布正式 blob，已有同 Hash 文件复用，缺失可重发，冲突不覆盖。此阶段没有业务写事务。
3. 新业务事务先执行 architecture §4.4 的受保护 item 状态检查。PG 行锁对应同一条目，SQLite 条件防护更新检查实际匹配行。删除/归档先提交则失败；如果本次事务先提交，后续归档保留引用。已 archived 预检直接拒绝；在发布后才确认的竞争失败可留无引用 blob，由 ORP 收敛。
4. 在同一 session 查 `(item_id,key)`；匹配则复用引用（200），否则插入引用（201）。持锁覆盖 `verify_all(session)` 和外层 Unit of Work 的一次 commit。失败由该协调器 rollback，再释放锁。既有引用的修复同样经受保护检查，归档后仍不得通过上传修复。
5. 发布/校验失败没有引用事务；提交失败允许物理孤儿。释放失败告警，已提交响应保持成功。

### 2.4 上传失败矩阵

| 失败点 | DB | 物理 | 返回 | 收敛 |
|---|---|---|---|---|
| Base64 非法 | 无 | 无 | 400 | 无 |
| 解码后超限 | 无 | 无 | 413 | 无 |
| MIME/内容不符 | 无 | 无 | 415 | 无 |
| hash 计算/重读不符 | 无 | 临时删除 | 422 | 无 |
| 等锁超时 | 无 | 临时删除 | 409 | 无 |
| 正式 key 冲突 | 无 | 临时删除 | 409 | 需人工/ORP 报告 |
| 发布 I/O 失败 | 无 | 临时清除尽力 | 503 | ORP |
| DB commit 失败 | 回滚 | 可能孤儿 | 500 | ORP |

### 2.5 元数据列表（只读，O-B04）

`GET /api/knowledge/{item_id}/attachments` 只返回该 item 的附件元数据（`AttachmentOut` 数组），按 `created_at`、`id` 稳定排序。

- 不返回物理路径、blob 内容、其它 item 的附件。
- 不进行 blob 重算 hash、不取 `StorageKeyLock`、不触发 GC；元数据来自 DB。
- 不存在 item → 404 `ITEM_NOT_FOUND`；`archived` item 允许列表（O-B06）。
- 不新增分页/搜索参数（本冻结无此需求）；数据量大时由未来批次另立裁决。

## 3. 导入 staging

### 3.1 transport、归属与重试

- ZIP-only。只有完整规范 ZIP 路径、根下 `attachments/` 的普通文件被识别为附件。含附件 ZIP 只支持 **恰好一篇非 attachments 子树中的 Markdown**；全部附件归该篇，经既有来源身份/目标解析绑定一个 item。无附件 ZIP 仍可多篇。附件 ZIP 未能唯一确定文档、路径或目标时整包拒绝，禁止分发给所有文档。
- 多篇或有歧义的附件 ZIP 返回 400 `ATTACHMENT_IMPORT_UNSUPPORTED`。零 Markdown 且有附件：若明确 target_item_id 经只读校验确认为 Active，则返回 400 `ATTACHMENT_ONLY_IMPORT_UNSUPPORTED`；其余返回 400 `ATTACHMENT_IMPORT_UNSUPPORTED`（无附件且无文档保留 `IMPORT_EMPTY`）。目标最终由既有 D22/D23 规则解析；顶层 target 只在单篇有附件 ZIP 中作为候选，不能覆盖来源身份或将冲突指向的条目强行合并。Archived 优先拒绝，按 §6/API §5。
- JSON 非空附件字段仍不承载附件：单篇拒绝 400，批量按 Batch A 逐篇 unsupported、其它篇继续。保留已有 frontmatter 附件引用与 ZIP 物理 manifest 的区分。
- 进入任何早返回之前，在来源/身份 guard 下完成既有来源版本、PENDING、目标状态及 Core `has_content_change` 判断。Active 只有 title/content 变化可携带附件生成新 pending。Active 无此变化且附件尚未满足（包含只有 tags/metadata/links 变化）整项拒绝 400 `ATTACHMENT_ONLY_IMPORT_UNSUPPORTED`，零 staging/pending/业务写。既有无附件 metadata-only 更新不变。
- 同来源同文档 Hash 已有 pending：只在附件逻辑集合完全相等且既有 pending 的非空 staging 在其 staging guard 下验证可用时返回 REUSED_PENDING，不建第二份 staging。集合是排序无关的 `(storage_key,filename,mime,size)`，排除 staging_id/ordinal/blob 路径；不同集合（含新集合为空或旧为空）返回既有 409 `SOURCE_HAS_PENDING_IMPORT`。同来源不同 Hash 仍按既有冲突处理。相等但已有 staging 不可用返回 staging 稳定错误，允许 reject 后重新导入。持来源/身份锁检查复用时不获取 review 锁；与决议通过同一来源锁协调，持 staging guard 重读原 pending 后才能确认复用。
- 以上附件新增规则适用于 ZIP 含附件或与现有带附件 pending 比较的请求；双方附件集合为空时保持 Batch A 行为。
- 已应用同文档 Hash：必须能唯一定位已应用 item。在来源/身份锁下取相关 key guard，按已关闭的预检会话→持锁读新快照→关闭→校验文件的顺序确认。请求的每个 key 已有该 item 的正式引用且正式文件能验证时，返回既有 SKIPPED，并在报告表明附件请求已满足；不能据此推断历史附件集合。缺少引用时 Active 按附件-only 拒绝，Draft 返回 400 `ATTACHMENT_IMPORT_UNSUPPORTED`（同 Hash 请求缺附件引用，独立上传可补齐）；有引用但正式文件缺失/损坏则返回该稳定文件错误，不静默成功。重复 / DUPLICATE 无唯一目标的附件请求显式拒绝。幂等判断留在 backend，原文档 Hash、来源版本和 Core 分类器保持。
- 单附件 10 MiB、单次 100 个、100 MiB。完整文件名及候选条目先检查再读取，文件解压使用计数的有界读取，按实际字节强制限制。空文件、重复 canonical ZIP 路径、路径穿越、绝对/盘符、符号链接、别名、大小写导致的冲突均拒绝。仅唯一根 `manifest.json` 作既有传输校验，附件目录同名文件只按附件识别；保留 D22 exporter 预检且冲突零业务写。

### 3.2 staging 创建及所有权

1. 完成 §3.1 分流、路径、大小、MIME 与 Hash 校验。对单份文档的同一 key 重复报 422 `ATTACHMENT_MANIFEST_DUPLICATE`。任何被拒请求不得创建可见的 staging；必要解压材料使用请求所有的有界缓冲，关闭会话后进入后续锁序。
2. 生成小写 UUIDv4 `staging_id`，在创建目录之前取得该 ID 的进程内 staging guard。每份合法 ZIP 只有一个 owner，guard 从创建覆盖到 Draft/新 pending commit 或失败处置结束。guard 命名空间独立于 review 和正式 key，遵守 architecture §6。
3. 创建 `blobs/` 后写 `.creating`；以规范 ZIP 路径排序生成 ordinal、按服务端名字写实际字节并 fsync，每写一文件刷新 `.activity`。最后原子发布 `.complete`（版本、staging ID、完成时间、文件数、累计字节）；POSIX 按层级同步目录，Windows 记录其断电边界。
4. 新 pending 成功后仅其 envelope 引用该 staging。Draft commit 后在 guard 内尽力清理。失败且确认未提交 pending 时清理自己的目录，提交结果不明确则保留给 ORP；复用既有 pending 不触碰其已有 staging。进程崩溃由宽限及持 guard 复核接管。

### 3.3 staging 状态

| 状态 | 判定 | 允许动作 |
|---|---|---|
| `creating` | 有 `.creating`、无 `.complete`；可能仍在写入或写入中崩溃 | 不可 approve；有 pending 引用则保留等待；无 pending 且超宽限由 ORP 隔离删除 |
| `active_pending` | `.complete` 存在，且被至少一个 pending review 的 envelope 引用 | 只读；approve/reject 可推进 |
| `committed` | 对应 review 已 approved 且事务①提交 | 可删除 staging；正式 blob 已存在 |
| `rejected` | review 已 rejected 且状态已提交 | 可删除 staging |
| `orphan` | 无 pending 引用且 `staging_activity_at` 超过宽限期（24h） | ORP 隔离后删除 |
| `corrupt` | `.complete` 与目录/manifest 不符、缺文件、hash 不符、未知元素 | 有 pending 保留，approve fail-closed；未引用且无法安全判定的目录由 ORP 报告 |

- `staging_id` 在 review 生命周期内不可变；manifest 不可追加/删除元素。
- staging 目录不写入用户文件名；只写序号文件，避免路径穿越与大小写冲突。
- **活动时间定义**：`staging_activity_at = max(mtime of .creating/.activity/.complete 与该 staging 目录下所有普通文件)`；不得仅用 staging 根目录单一 mtime 判断孤儿（根目录 mtime 不会随子文件写入可靠更新）。
- pending 引用**优先于时间**：只要任一 pending envelope 引用该 `staging_id`，无论多旧都不得清理。
- `staging_grace_seconds=86400`（24h）；未完成（无 `.complete`）的 staging 同样受 pending 引用保护。

### 3.4 staging 文件校验

物理预发布前，在 staging guard 下逐项校验：

- staging 目录缺失 → 409 `ATTACHMENT_STAGING_MISSING`；目录 ID 须与 envelope 一致。`.complete` 存在且可解析，其 `staging_id`/`file_count`/`total_bytes` 与目录/manifest 一致；缺失或与目录/manifest 不符 → 409 `ATTACHMENT_STAGING_INVALID`；
- `blob` 相对路径只允许 `blobs/<6位数字>.bin`，解析后必须仍在 staging 根内；
- 文件存在、大小等于 `size`；
- 重算 SHA-256 等于 `storage_key`；
- `staging_id` 与目录一致；`ordinal` 唯一，`blob` 必须由该 ordinal 按六位编号派生，禁止多个条目指向同一文件；`filename`/`mime` 通过同一套校验；
- 任一失败 → `ATTACHMENT_STAGING_INVALID`（409），不发布、不 commit。

## 4. Promote（staging → 正式）

1. 源 staging guard 先于存储锁。确认真实路径和完成标记，取齐所有待发布 key 的批 guard（SQLite 完整 key 字典序，PG 实际锁身份顺序和整批 10s）。任一失败不发布。
2. 在业务写事务之外按 §3.4 校验、复制到临时文件、fsync、重读 Hash 并 no-clobber 发布。每次物理变更前检查 guard；同 Hash blob 可复用。结果为不可变的服务端发布计划（staging ID、manifest 逻辑内容、key 集合及目标绑定），不会写正式引用。
3. 上传/Draft/approve 只在持足 storage guard 的短业务事务中引用已发布 key；S1 重读、归档保护与 `verify_all` 通过后 commit。任何失败先回滚再释放存储锁，保留 pending 的 staging；发布成功但未引用的 blob 由 ORP 处理。复制而不移动 staging 原件。
4. `.tmp` 崩溃残留只报告（ORP-02）。失败时不回撤正式路径，也不通过临时删除消除孤儿。

## 5. 删除附件

### 5.1 路由语义

`DELETE /api/knowledge/{item_id}/attachments/{attachment_id}`：

- item 或 attachment 不存在、或 attachment 不属于该 item → 404 `ATTACHMENT_NOT_FOUND`（不泄露跨 item 存在性）。
- `archived` item **允许删除附件引用**（O-B06）；不因 item 状态返回 409。
- 成功 → 204，无响应体。

### 5.2 事务

```text
外层 Unit of Work 提供 session：
  attachment = get(attachment_id) 且 item_id 匹配
  delete_attachment(attachment)     # flush
  refs = count_references(storage_key)  # 同一事务内
  if refs == 0:
      ensure_gc_task(storage_key, status=pending)  # 仅当无活跃任务
  外层 Unit of Work 提交一次；失败由该协调器回滚
```

- 物理文件**不在**此事务内删除。附件服务编排操作，Repository 负责持久化和 flush；服务及 Repository 不自行 commit/rollback。
- 若 `ensure_gc_task` 失败：整个事务回滚，附件仍存在；返回 500。
- 若 commit 成功但进程在 kick worker 前崩溃：任务已在 DB，周期 worker 会拾取。
- GC 任务去重：若已有 `pending/running/failed_retryable` 同 key 任务，不再插入；`done` 后可新建；`failed_permanent/needs_manual` 不自动新建，记录告警（O-B07）。

### 5.3 并发删除

- 两个请求同时删除同一引用：一个成功，另一个 404 或删除 0 行；不得重复入队。
- 删除最后引用与上传同 key 并发：上传持 StorageKeyLock；删除事务不持锁，但只改 DB。GC 在隔离前持锁复核；若此时引用>0 → `cancelled` 或恢复，不删文件。
- 删除与 GC 并发：GC 持锁复核引用；删除在 DB 事务中。正常路径下上传/approve 必须持同一 key 锁完成“发布 + 引用提交”，因此 GC 不能在发布窗口隔离新 blob。但 SQLite 租约过期/心跳失败时仍存在理论窗口：旧 writer 可能在失去 token 后、commit 前继续。缓解：① 所有 writer 在 DB commit 前再次 `verify`，失败则回滚；② GC 隔离后不立即删除，24h 后再复核；③ 复核发现引用>0 时恢复 quarantine。窗口内下载返回 503。**不得宣称完全消除 TOCTOU**；验收 LCK-08 记录此限制。

## 6. 独立上传与导入的引用一致性

- 独立上传：引用在单事务提交；blob 已先发布。
- 导入 Draft（ZIP-only）：文档与附件引用同一 DB 事务；staging 已存在；正式发布必须在开启该 DB 写事务前按同一 `StorageKeyLock` 契约取锁并完成，commit 前 verify。提交失败 → 文档/引用都不生效，blob 孤儿由 ORP。
- Active approve：附件引用与 item/tags/origin/links 同一事务①；文件在①的写事务开始前发布；①失败 → 全部 DB 变更回滚，blob 孤儿。
- 不存在“附件单独 commit、item 后 commit”的路径。

## 7. Approve / Reject / 崩溃时的 staging

| 事件 | review 状态 | 正式引用 | staging | 后续 |
|---|---|---|---|---|
| approve 校验失败（锁/文件/hash/`.complete`） | pending（未提交） | 无 | 保留 | 修复后可重试；错误返回 |
| approve 发布部分 blob 后失败 | pending | 无 | 保留 | 正式 blob 孤儿；ORP |
| approve 事务①提交前崩溃 | pending（回滚） | 无 | 保留 | 重启后重试；ORP 不删被 pending 引用的 staging |
| approve 事务①提交成功、清理前崩溃 | approved | 有 | 残留 | ORP 在宽限后清理 staging |
| reject 状态提交前崩溃 | pending | 无 | 保留 | 仍可 approve/reject |
| reject 状态提交后、清理前崩溃 | rejected | 无 | 残留 | ORP 清理 |
| 进程在 staging 写入中崩溃 | 无 review | 无 | 无 `.complete` 半成品 | 有 pending 引用则保留；否则按 `staging_activity_at` 超 24h 后由 ORP 隔离删除 |
| pending 被人工长期搁置 | pending | 无 | 保留 | 不自动清理；pending 引用优先于时间 |

## 8. MERGE_DUPLICATE、条目删除、导出

### 8.1 MERGE_DUPLICATE

- **不迁移附件**（决策 21）：不新增 `attachment.item_id` 更新，不复制附件行，不移动 blob。
- 源条目附件仍引用源 item；目标 item 不自动获得附件。
- 若合并流程随后删除源条目：FK CASCADE 删除附件行；blob 若无其他引用，由 ORP 兜底（决策 22）。
- 不得在 merge 中直接删除 blob 或 gc_task；不得新增 merge 专用 GC。

### 8.2 条目删除

- 既有 `knowledge_item` 删除 → `attachment` FK CASCADE；**不**自动插入 `gc_task`。
- 无引用 blob 由 ORP 周期扫描发现：观察到零引用且正式文件 mtime 至少 24h 才入队，隔离期另从可证实的隔离时点算至少 24h。
- 因共享 blob 可能仍被其他 item 引用，ORP 以 `count_references` 为准，不以“条目删除事件”为准。
- 删除条目事务不得执行物理删除；不得因删除条目阻塞在 GC 上。

### 8.3 附件导出

- 继续返回 400 `ATTACHMENT_EXPORT_UNSUPPORTED`；`include_attachments=true` 一律拒绝（决策 20）。
- 单篇 Markdown 导出不嵌入/不打包附件；不新增 `attachments` frontmatter 回填。
- 不改既有 `EXPORT_EMPTY`、`EXPORT_FAILED`、`EXPORT_MANIFEST_COLLISION` 等稳定错误码。

## 9. 生命周期不变量

1. 正式引用只在“上传事务 / Draft 导入事务 / Active approve 事务①”中产生；pending 为零。
2. 每个正式 blob 的发布都先于其引用提交；失败窗口由 ORP 收敛。
3. 删除引用从不立即删物理文件；必须经 `gc_task` 与 24h 安全期。
4. staging 文件不参与正式 key 枚举；staging 删除不等于正式 blob 删除。
5. 任何覆盖/移动/删除前必须持锁并校验 token（GC/ORP/promote）。
6. 导出、merge、条目删除均不新增附件迁移能力。
7. 所有“自动修复”只允许：发布缺失的同 hash blob、恢复被误隔离但仍有引用的 blob；不允许自动删除 DB 引用或覆盖不同内容。
8. `archived` item 不得新增附件；不得因状态拒绝下载/列表/删除引用。
9. Active 附件-only 导入必须显式 400 拒绝；不得创建 staging/pending/attachment 行或静默成功。
10. staging 完成性与活动时间以 `.creating`/`.activity`/`.complete` 及目录内普通文件为准；不得用 staging 根目录单一 mtime。
11. 下载的 size/hash 校验与流式输出必须使用同一个已打开文件句柄；不得按路径重新 open。
12. 列表端点只读元数据，不触发 blob 校验或 GC。
