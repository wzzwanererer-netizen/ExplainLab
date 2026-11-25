# Staging 生命周期和进程锁边界

## 状态

基线能证明每数据目录的 OS 单实例锁与进程内来源、身份锁。Batch B 的 review_id 决议锁、staging_id guard、完成标记、pending 生命周期、隔离/恢复/purge 及 StorageKeyLock 组合均待实现。单实例 OS 锁保护部署，staging_id guard 序列化该进程内的文件/状态动作；没有独立共享 staging 的多实例部署证据。

## 对应基线源码

[打开带原始行号的源码索引](README.md)

- `backend/app/main.py`：40–106，worker 限制、lifespan ProcessLock、身份服务。
- `backend/app/db/process_lock.py`：50–154，持久锁句柄；Windows/Unix 分支。
- `backend/app/services/import_coordinator.py`：36–末尾，进程内来源键协调。
- `backend/app/services/source_identity.py`：574–610，进程内 Journal RLock。
- `backend/app/api/routes/governance.py`：408–526，基线批准/拒绝。
- `knowledge-core/src/knowledge_core/markdown/import_report.py`：222–280，envelope/附件列表摘要。

## 当前候选设计原文（限定章节）

完整设计文件见 `design-documents/`。行号对应打包时源文件。

### attachment-lifecycle.md · §3–4 创建、完成、校验与 promote（92–146）

~~~text
  92: ## 3. 导入 staging
  93: 
  94: ### 3.1 transport、归属与重试
  95: 
  96: - ZIP-only。只有完整规范 ZIP 路径、根下 `attachments/` 的普通文件被识别为附件。含附件 ZIP 只支持 **恰好一篇非 attachments 子树中的 Markdown**；全部附件归该篇，经既有来源身份/目标解析绑定一个 item。无附件 ZIP 仍可多篇。附件 ZIP 未能唯一确定文档、路径或目标时整包拒绝，禁止分发给所有文档。
  97: - 多篇或有歧义的附件 ZIP 返回 400 `ATTACHMENT_IMPORT_UNSUPPORTED`。零 Markdown 且有附件：若明确 target_item_id 经只读校验确认为 Active，则返回 400 `ATTACHMENT_ONLY_IMPORT_UNSUPPORTED`；其余返回 400 `ATTACHMENT_IMPORT_UNSUPPORTED`（无附件且无文档保留 `IMPORT_EMPTY`）。目标最终由既有 D22/D23 规则解析；顶层 target 只在单篇有附件 ZIP 中作为候选，不能覆盖来源身份或将冲突指向的条目强行合并。Archived 优先拒绝，按 §6/API §5。
  98: - JSON 非空附件字段仍不承载附件：单篇拒绝 400，批量按 Batch A 逐篇 unsupported、其它篇继续。保留已有 frontmatter 附件引用与 ZIP 物理 manifest 的区分。
  99: - 进入任何早返回之前，在来源/身份 guard 下完成既有来源版本、PENDING、目标状态及 Core `has_content_change` 判断。Active 只有 title/content 变化可携带附件生成新 pending。Active 无此变化且附件尚未满足（包含只有 tags/metadata/links 变化）整项拒绝 400 `ATTACHMENT_ONLY_IMPORT_UNSUPPORTED`，零 staging/pending/业务写。既有无附件 metadata-only 更新不变。
 100: - 同来源同文档 Hash 已有 pending：只在附件逻辑集合完全相等且既有 pending 的非空 staging 在其 staging guard 下验证可用时返回 REUSED_PENDING，不建第二份 staging。集合是排序无关的 `(storage_key,filename,mime,size)`，排除 staging_id/ordinal/blob 路径；不同集合（含新集合为空或旧为空）返回既有 409 `SOURCE_HAS_PENDING_IMPORT`。同来源不同 Hash 仍按既有冲突处理。相等但已有 staging 不可用返回 staging 稳定错误，允许 reject 后重新导入。持来源/身份锁检查复用时不获取 review 锁；与决议通过同一来源锁协调，持 staging guard 重读原 pending 后才能确认复用。
 101: - 以上附件新增规则适用于 ZIP 含附件或与现有带附件 pending 比较的请求；双方附件集合为空时保持 Batch A 行为。
 102: - 已应用同文档 Hash：必须能唯一定位已应用 item。在来源/身份锁下取相关 key guard，按已关闭的预检会话→持锁读新快照→关闭→校验文件的顺序确认。请求的每个 key 已有该 item 的正式引用且正式文件能验证时，返回既有 SKIPPED，并在报告表明附件请求已满足；不能据此推断历史附件集合。缺少引用时 Active 按附件-only 拒绝，Draft 返回 400 `ATTACHMENT_IMPORT_UNSUPPORTED`（同 Hash 请求缺附件引用，独立上传可补齐）；有引用但正式文件缺失/损坏则返回该稳定文件错误，不静默成功。重复 / DUPLICATE 无唯一目标的附件请求显式拒绝。幂等判断留在 backend，原文档 Hash、来源版本和 Core 分类器保持。
 103: - 单附件 10 MiB、单次 100 个、100 MiB。完整文件名及候选条目先检查再读取，文件解压使用计数的有界读取，按实际字节强制限制。空文件、重复 canonical ZIP 路径、路径穿越、绝对/盘符、符号链接、别名、大小写导致的冲突均拒绝。仅唯一根 `manifest.json` 作既有传输校验，附件目录同名文件只按附件识别；保留 D22 exporter 预检且冲突零业务写。
 104: 
 105: ### 3.2 staging 创建及所有权
 106: 
 107: 1. 完成 §3.1 分流、路径、大小、MIME 与 Hash 校验。对单份文档的同一 key 重复报 422 `ATTACHMENT_MANIFEST_DUPLICATE`。任何被拒请求不得创建可见的 staging；必要解压材料使用请求所有的有界缓冲，关闭会话后进入后续锁序。
 108: 2. 生成小写 UUIDv4 `staging_id`，在创建目录之前取得该 ID 的进程内 staging guard。每份合法 ZIP 只有一个 owner，guard 从创建覆盖到 Draft/新 pending commit 或失败处置结束。guard 命名空间独立于 review 和正式 key，遵守 architecture §6。
 109: 3. 创建 `blobs/` 后写 `.creating`；以规范 ZIP 路径排序生成 ordinal、按服务端名字写实际字节并 fsync，每写一文件刷新 `.activity`。最后原子发布 `.complete`（版本、staging ID、完成时间、文件数、累计字节）；POSIX 按层级同步目录，Windows 记录其断电边界。
 110: 4. 新 pending 成功后仅其 envelope 引用该 staging。Draft commit 后在 guard 内尽力清理。失败且确认未提交 pending 时清理自己的目录，提交结果不明确则保留给 ORP；复用既有 pending 不触碰其已有 staging。进程崩溃由宽限及持 guard 复核接管。
 111: 
 112: ### 3.3 staging 状态
 113: 
 114: | 状态 | 判定 | 允许动作 |
 115: |---|---|---|
 116: | `creating` | 有 `.creating`、无 `.complete`；可能仍在写入或写入中崩溃 | 不可 approve；有 pending 引用则保留等待；无 pending 且超宽限由 ORP 隔离删除 |
 117: | `active_pending` | `.complete` 存在，且被至少一个 pending review 的 envelope 引用 | 只读；approve/reject 可推进 |
 118: | `committed` | 对应 review 已 approved 且事务①提交 | 可删除 staging；正式 blob 已存在 |
 119: | `rejected` | review 已 rejected 且状态已提交 | 可删除 staging |
 120: | `orphan` | 无 pending 引用且 `staging_activity_at` 超过宽限期（24h） | ORP 隔离后删除 |
 121: | `corrupt` | `.complete` 与目录/manifest 不符、缺文件、hash 不符、未知元素 | 有 pending 保留，approve fail-closed；未引用且无法安全判定的目录由 ORP 报告 |
 122: 
 123: - `staging_id` 在 review 生命周期内不可变；manifest 不可追加/删除元素。
 124: - staging 目录不写入用户文件名；只写序号文件，避免路径穿越与大小写冲突。
 125: - **活动时间定义**：`staging_activity_at = max(mtime of .creating/.activity/.complete 与该 staging 目录下所有普通文件)`；不得仅用 staging 根目录单一 mtime 判断孤儿（根目录 mtime 不会随子文件写入可靠更新）。
 126: - pending 引用**优先于时间**：只要任一 pending envelope 引用该 `staging_id`，无论多旧都不得清理。
 127: - `staging_grace_seconds=86400`（24h）；未完成（无 `.complete`）的 staging 同样受 pending 引用保护。
 128: 
 129: ### 3.4 staging 文件校验
 130: 
 131: 物理预发布前，在 staging guard 下逐项校验：
 132: 
 133: - staging 目录缺失 → 409 `ATTACHMENT_STAGING_MISSING`；目录 ID 须与 envelope 一致。`.complete` 存在且可解析，其 `staging_id`/`file_count`/`total_bytes` 与目录/manifest 一致；缺失或与目录/manifest 不符 → 409 `ATTACHMENT_STAGING_INVALID`；
 134: - `blob` 相对路径只允许 `blobs/<6位数字>.bin`，解析后必须仍在 staging 根内；
 135: - 文件存在、大小等于 `size`；
 136: - 重算 SHA-256 等于 `storage_key`；
 137: - `staging_id` 与目录一致；`ordinal` 唯一，`blob` 必须由该 ordinal 按六位编号派生，禁止多个条目指向同一文件；`filename`/`mime` 通过同一套校验；
 138: - 任一失败 → `ATTACHMENT_STAGING_INVALID`（409），不发布、不 commit。
 139: 
 140: ## 4. Promote（staging → 正式）
 141: 
 142: 1. 源 staging guard 先于存储锁。确认真实路径和完成标记，取齐所有待发布 key 的批 guard（SQLite 完整 key 字典序，PG 实际锁身份顺序和整批 10s）。任一失败不发布。
 143: 2. 在业务写事务之外按 §3.4 校验、复制到临时文件、fsync、重读 Hash 并 no-clobber 发布。每次物理变更前检查 guard；同 Hash blob 可复用。结果为不可变的服务端发布计划（staging ID、manifest 逻辑内容、key 集合及目标绑定），不会写正式引用。
 144: 3. 上传/Draft/approve 只在持足 storage guard 的短业务事务中引用已发布 key；S1 重读、归档保护与 `verify_all` 通过后 commit。任何失败先回滚再释放存储锁，保留 pending 的 staging；发布成功但未引用的 blob 由 ORP 处理。复制而不移动 staging 原件。
 145: 4. `.tmp` 崩溃残留只报告（ORP-02）。失败时不回撤正式路径，也不通过临时删除消除孤儿。
 146: 
~~~

### architecture.md · §6 全局锁顺序（118–124）

~~~text
 118: ## 6. 并发模型
 119: 
 120: - 单 Backend、单 worker、单数据根，沿用 Batch A 的 ProcessLock。PG 双连接及双 worker 用例属于并发取证。后台 ORP 按 GC 文档取扫描领导权。
 121: - 统一获取顺序：**review 决议锁（适用）→ ImportCoordinator 来源锁（适用）→ identity_guard（发生身份写时）→ staging_id guard（适用）→ StorageKeyLock → 业务 DB 写事务**。释放逆序；正常清理可继续持 staging guard，索引②在业务协调锁外执行。创建 pending 持来源、身份及 staging guard 至提交，不需要正式 key 锁。
 122: - Reject 走共同 review 锁，再按可解析身份或 target fallback 走来源锁；它不写身份，不进入身份 Journal。清理不能在持 storage 锁后再获取 staging/review 锁。
 123: - GC 先认领 task 的短事务然后取 storage 锁；ORP staging 先取 staging guard 再取需要的 storage 锁。列表/下载只读不取 storage lock；附件路由为同步 def。禁止在上述业务锁下做模型/网络调用。
 124: 
~~~

### active-review-integration.md · §5.4、§6–7 清理、崩溃、reject（116–145）

~~~text
 116: ### 5.4 清理 staging
 117: 
 118: - ① commit 成功后：对每个 `staging_id` 调用 `staging.discard_committed(staging_id)`；失败只告警，ORP 兜底。
 119: - ① 失败/回滚：**不清理 staging**；review 仍 pending，可重试。
 120: - ② 失败：① 已提交；staging 清理在②前尽力执行；业务/附件不回滚。
 121: 
 122: ## 6. 失败与崩溃矩阵
 123: 
 124: | 时点 | review | Attachment 行 | 正式 blob | staging | 处理 |
 125: |---|---|---|---|---|---|
 126: | envelope 摘要/结构失效，或摘要合法但附件元素非法 | pending | 无 | 无 | 保留 | 409 `IMPORT_ENVELOPE_INVALID` 或 `ATTACHMENT_MANIFEST_CORRUPTED`（§8） |
 127: | staging 目录缺失 | pending | 无 | 无 | 缺失 | 409 `ATTACHMENT_STAGING_MISSING` |
 128: | `.complete` 缺失/不一致 | pending | 无 | 无 | 保留 | 409 `ATTACHMENT_STAGING_INVALID` |
 129: | 目标 item 已 archived 或在预发布后归档 | pending | 无 | 早拒为无，竞态可有孤儿 | 保留 | 409 `ATTACHMENT_ITEM_ARCHIVED`；零业务提交 |
 130: | staging 文件缺失/hash 不符 | pending | 无 | 无 | 保留 | 409 `ATTACHMENT_STAGING_INVALID` |
 131: | 锁超时 | pending | 无 | 无 | 保留 | 409 `STORAGE_LOCK_TIMEOUT` |
 132: | 发布中 I/O 失败 | pending | 无 | 部分孤儿 | 保留 | 500/503；ORP |
 133: | 发布后、① commit 前崩溃 | pending（回滚） | 无 | 孤儿 | 保留 | 重启重试；ORP 不删被 pending 引用 staging |
 134: | ① commit 成功、响应前崩溃 | approved | 有 | 有 | 残留 | 客户端重试读状态；ORP 清理 staging |
 135: | ① commit 成功、② 失败 | approved | 有 | 有 | 可能残留 | 业务已提交；索引失败告警；不回滚 |
 136: | ① commit 失败 | pending | 无 | 孤儿 | 保留 | 回滚；可重试 |
 137: | 释放锁失败（路由/Hook 返回后） | approved/pending | 视 commit | 视 commit | 视情况 | 告警；租约过期/连接关闭释放 |
 138: 
 139: ## 7. Reject 集成
 140: 
 141: 1. 轻量 S0 仅确认 pending。始终先取与 approve 共用的 `review_id` 决议锁。来源键从能可信解析的 envelope 取，失败使用 target-item fallback；即使两条路由的来源键不同，仍由同一决议锁串行。
 142: 2. 在决议锁下重读当前 pending。只有通过既有 envelope 完整性、元素/目录 ID 和 pending 所有权核对的 staging 才取 staging guard。损坏或无法证明归属时跳过清理，仍可 reject。普通审核无 envelope 属正常。
 143: 3. Core reject flush → no-op Hook → commit；先提交状态，然后在持 staging guard 下重新确认无其他 pending 引用再尽力清理。清理失败只告警，ORP 兜底。拒绝不触碰正式 blob/引用，也不新增 GC 任务。
 144: 4. 两条路径的 S1 及决议 commit 都处于同一个 `review_id` 保护区，后到者看到终态并按既有 409 行为退出。① 失败则无终态及 staging 清理。单 Backend/单 worker 适用。
 145: 
~~~

### gc-and-orphan-recovery.md · §6.4 Staging 清扫（161–168）

~~~text
 161: ### 6.4 Staging 清扫
 162: 
 163: 1. 枚举合法 UUIDv4 的 staging 直接子目录与合法 quarantine/staging 直接子目录。排除根本身、链接/junction/越界与不可信路径。在 `staging_id` guard 内短查询全部 pending 引用，结束只读会话。普通 review 无 envelope 跳过；疑似导入 envelope/manifest 损坏（包括二次查询）则本轮 staging 操作 fail-closed，并报告。
 164: 2. 创建者在目录出现前已持同一 guard，覆盖活动写入、pending/Draft commit 和处置。approve/reject 正常清理也使用该 guard。扫描可在锁外挑选候选，拿不到 guard 跳过；决定移动前在锁内重新计算活动和 pending 归属。任何 pending 引用优先保留。
 165: 3. 活动取标记与普通文件 mtime 的最大值；只有确认合法 UUID 目录确实为空、无标记/文件且没有 pending，才用该目录自身 mtime 判断标记前半成品的宽限。读取失败或时间异常报告，不删除。宽限 24h。非空目录只依据标记/文件，根目录 mtime 永远不作正常活动依据。
 166: 4. 超宽限且无 pending，校验/Hash 扫描得到可用的正式 key 后按批次顺序取得相关 StorageKeyLock，随后短会话再次检查 pending、复核活动/路径/租约，关闭会话，才可将目录无覆盖移动到 `<quarantine>/staging/<staging_id>.<UTC隔离时刻>`。空目录靠 staging guard 即可。读取/Hash/锁失败保守报告。通过隔离路径记录隔离时间，弃用原 mtime 作为隔离起点。
 167: 5. 隔离目录的复核、移回和 purge 同样持 staging guard 与可确定的 storage guard。出现 pending 引用时优先恢复到原 staging 根，目标已存在则报告并保留两边；至少隔离 24h 且再次证明没有 pending、路径安全与 fence 有效才可删除。失败保留并等待重试。直接成功清理已有确认提交的单一所有者目录时无需等待，但必须先证明没有 pending 引用。
 168: 
~~~
