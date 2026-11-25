# SQLite D23 到审核两次提交的时序

## 状态

基线能证明 S0 关闭会话、身份恢复门、Core→现有 DB Hook→业务 commit→索引同步→索引 commit。Batch B 在 D23 恢复事务退出后获取 staging/storage guard，关闭预发布读会话后先做文件发布，再进入 S1 写、Core 前 archive 保护与同会话末次 fencing；待实现。真实 PREPARED 恢复、SQLite 争用和两次提交失败注入未在本轮运行。

## 对应基线源码

[打开带原始行号的源码索引](README.md)

- `backend/app/services/source_identity.py`：595–610、681–785，恢复后 yield，必要时内部写事务和 commit。
- `backend/app/api/routes/governance.py`：385–405、426–485，S0 关闭、S1/Core、业务提交再同步索引并提交。
- `backend/app/services/import_review_hook.py`：81 起，现有附件拒绝及导入 Hook。
- `knowledge-core/src/knowledge_core/review/__init__.py`：85–113、129–143，Core 决议与状态应用。
- `backend/app/db/session.py`：19–56，SQLite 外键、busy timeout 与会话工厂。
- `backend/app/services/retrieval.py`：272–299，提交后索引同步入口。

## 当前候选设计原文（限定章节）

完整设计文件见 `design-documents/`。行号对应打包时源文件。

### architecture.md · §4.2–4.4 审核边界与 SQLite 写门（64–85）

~~~text
  64: ### 4.2 事务①与事务②
  65: 
  66: 1. S0 只读预检并关闭会话。所有审核决议持共同 `review_id` 决议锁。导入审核再持既有来源协调锁；approve 保留基线的 `identity_guard`。恢复门先完成，任何内部恢复 DB 事务均已提交/关闭。
  67: 2. 带附件时持对应 staging guard，再获取全部 StorageKeyLock。只读复核审核快照、目标、归档及 D22/D23 前置，关闭该会话，然后校验、复制、重读 Hash、no-clobber 发布。DB 业务写事务始于发布之后。
  68: 3. S1 新业务会话重读 PENDING、复核 S0 payload 与发布计划，保护目标 item 原状态，再执行 Core approve → Hook 的 DB 补齐（含附件引用）→ `verify_all` → 业务 commit ①。Hook 无物理文件操作，发布失败不进入①。① 失败保留 staging，已发布孤儿由 ORP 收敛。
  69: 4. ① 成功后释放 storage guard；在 staging guard 下尽力清理已完成的目录；随后释放所有业务协调锁。② 独立执行提交后索引同步；失败只回滚②、记录告警，按已批准状态返回。随①触发的 FTS 更新不属于②。
  70: 5. 无附件路径保持既有业务/索引事务语义。审核时序与错误详见 active-review-integration §2、§5–7。
  71: 
  72: ### 4.3 物理与 DB 的诚实边界
  73: 
  74: - 不存在跨文件系统+数据库的原子事务。
  75: - 允许的中间态：`blob 存在、DB 无引用`（孤儿）；`DB 有引用、blob 缺失`（不一致，只报告/下载失败，不自动删 DB）。
  76: - 不允许的中间态：`DB 引用指向被覆盖的 blob`；`pending 期间出现正式引用`；`reject 后仍可 approve`。
  77: - 所有崩溃恢复依靠：启动时 staging/quarantine 扫描 + 周期 ORP；不依赖“进程一定优雅退出”。
  78: 
  79: ### 4.4 SQLite 写事务与存储锁的先后（强制）
  80: 
  81: - 上传、Draft 导入、附件 approve：关闭 S0/预发布只读事务，完成 D23 恢复（适用时）并退出其内部会话，先取存储锁、完成物理发布，再开启短业务写事务。顺序保留 `Core approve → DB Hook → ①`。
  82: - 业务事务内从既有 item 获取归档保护后再改变其状态或新增引用。PG 锁住目标 item 行再读状态。SQLite 在适配层对同一 item 先执行条件防护更新（现有非 archived 状态，`status=status`、`updated_at=updated_at`，保留字段值），检查匹配行数并在同 session 重读。该受控写前置早于 Core 的条目状态变更，冲突/busy 时回滚，可在请求预算内从新事务重试。无需改全局事务模式。
  83: - SQLite commit 之前 `verify_all` 使用同一业务 session。覆盖上传、Draft 和 approve。写事务内禁止独立连接获取/等待 StorageKeyLock、复制、Hash 或发布。rollback 或 commit 完成后释放锁。
  84: - GC claim 短事务先提交/关闭，之后取 StorageKeyLock。ORP/staging 扫描预读会话同样先关闭才取锁。SQLite 需要写锁时区分竞争和真租约失配。PG 最后提交区间按 storage §4.6 锁住完整 key 的 token 行，接管者完成 token 提交前不得触碰文件。
  85: 
~~~

### active-review-integration.md · §1–2 基线与 Batch B 时序（5–22）

~~~text
   5: ## 1. 既有事实（基线 `970c0d8`）
   6: 
   7: - `ReviewResolve` 只有 `note`，没有 approve-time manifest 字段。
   8: - `ImportEnvelope` 存于 `ReviewRequest.payload.__a1_import`，`attachments: list[dict]` 目前为空。
   9: - `ImportEnvelope.compute_context_digest()` 已把 `attachments` 纳入摘要；`from_review_payload()` 校验版本与摘要，结构非法 fail-closed。
  10: - `approve_review()` 顺序：S0 只读预检 → `ImportCoordinator` 身份键锁 + `identity_guard` → S1 新会话 → 重读并比较 payload 摘要 → Core `ReviewService.approve()`（仅 flush）→ `ImportReviewHook.apply_approved()` → `session.commit()`（业务）→ 索引同步 → `session.commit()`（索引）。
  11: - Batch B 保留 Core → DB Hook → ①，增加 review 决议锁、staging guard 和写事务前物理发布，见 §2。
  12: - `ImportReviewHook.apply_approved()` 当前第一步是：`if envelope.attachments: raise ATTACHMENT_REVIEW_UNSUPPORTED`。Batch B 必须替换该拒绝，但保留错误码用于“能力未启用/不受支持”。
  13: - `reject_review()` 当前提交 reject 状态；`apply_rejected()` 是 no-op。
  14: 
  15: ## 2. 决议锁与事务骨架
  16: 
  17: 1. S0 严格只读预检，关闭会话。验证 envelope 版本/摘要，验证附件元素结构并收集 key。结构或摘要失败返回 §8 对应码，不获取 storage lock。
  18: 2. 按 architecture §6 先取得所有 approve/reject 共用的进程内 `review_id` 决议锁，再取既有来源锁、`identity_guard`。D23 恢复可以合法写 DB，但恢复门及内部事务必须在附件取锁之前完成、关闭。随后取得可信 staging ID 的 staging guard，再取齐 StorageKeyLock。
  19: 3. 持 guard 用独立短只读会话复核 S0、目标、归档及来源前置；关闭会话。随后校验 staging、复制、重读 Hash、发布 no-clobber，生成发布计划。Core、Hook 和业务写尚未执行。
  20: 4. S1 新会话复核 PENDING、payload 摘要及发布计划；在 Core 前执行 archive 防护（architecture §4.4），然后 Core approve → DB Hook → 同业务 session 末次 fencing → commit ①。每一失败路径先结束业务事务，再释放存储锁；pending 原件仍可重试。
  21: 5. ① 后释放存储锁、在 staging guard 内尽力清理，再释放所有业务 guard。② 提交后索引同步使用独立事务/会话，失败仅告警与回滚②，返回已经保存的批准状态。已有随①触发的索引行为保持；无附件旧路径保持 Batch A 契约。
  22: 
~~~

### active-review-integration.md · §5.1–5.2 预发布与 DB Hook（81–93）

~~~text
  81: ## 5. Approve 执行细节
  82: 
  83: ### 5.1 预发布与 Hook 的职责
  84: 
  85: - 持 review、来源、身份、staging、storage guard，在发布前只读检查 target、exporter metadata、来源和已物化标记。D23 恢复门已在取锁前运行；后续读取 COMMITTED 证据只能使用已恢复 guard 下的只读路径。若恢复仍需写，停止并释放本次存储 guard，再从恢复门重新进入，禁止在业务写中启动恢复。
  86: - staging 字节、完成标记、MIME、Hash、大小均在发布前验证，与 manifest 逐项对照。复制/发布产出服务端不可变计划，含目标、payload 摘要、staging_id 与准确 key 集合。存储层不会写引用。
  87: - Hook 在 Core 后使用同一 S1 session 做既有 origin/tags/links 和附件 DB 引用补齐，只接受已验证计划。计划与 S1 摘要/manifest 或 guard key 不符即回滚。不在 Hook 里补取锁、打开 staging、复制、校验文件 Hash、发布或提交。目标是否 archived 以 Core 前受保护状态为准，Core 之后看到的 Draft 不能作为放行依据。
  88: 
  89: ### 5.2 路由职责与失败
  90: 
  91: - `approve_review` 保持同步。在共同 review 锁内先按 §2 走预发布，再开新的 S1。锁超时返回 409 `STORAGE_LOCK_TIMEOUT`，commit 前任一 key 失效返回 503 `STORAGE_LEASE_LOST`。S1 发现 payload 或发布计划漂移，回滚并返回 409 `IMPORT_ENVELOPE_INVALID`，已发布孤儿留给 ORP。
  92: - ① 提交/回滚后才释放 StorageKeyLock；释放幂等，失败只告警，PG 物理关闭兜底。① 完成后固化 ReviewOut；清理 staging 失败和②失败不改变批准结果。② 在所有业务协调 guard 退出后运行。
  93: 
~~~
