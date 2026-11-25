# Batch B Architecture

## 1. 总体结构

```text
frontend
  │  HTTP /api （仅 Batch B 路由）
  ▼
backend
  ├─ app/api/routes/attachments.py        # 上传/下载/删除/元数据列表
  ├─ app/api/routes/import_export.py      # 既有导入/导出（ZIP-only 附件 transport）
  ├─ app/api/routes/governance.py         # 既有 approve/reject（扩展预取锁、Hook、reject 清理点）
  ├─ app/services/attachments.py          # 附件业务编排（校验/去重/引用/列表/GC 入队）
  ├─ app/services/attachment_storage.py   # 内容寻址物理存储（无业务规则）
  ├─ app/services/attachment_staging.py   # staging 创建/写入/完成标记/校验/promote/清扫
  ├─ app/services/import_review_hook.py   # approve 内附件执行（既有文件）
  ├─ app/services/attachment_maintenance.py # GC worker + ORP + 一致性报告
  ├─ app/db/storage_lock.py               # StorageKeyLock 双方言实现
  ├─ app/services/repositories_v2.py      # Attachment/GcTask SQLAlchemy 仓库
  └─ app/core/config.py                   # 冻结参数
  │  Python import / 端口实现
  ▼
knowledge-core
  ├─ domain/entities.py                   # Attachment/GcTask/StorageLease（既有）
  ├─ ports.py                             # AttachmentRepository/GcTaskRepository/StorageKeyLock（既有）
  └─ markdown/import_report.py            # ImportEnvelope/attachments（既有，仅使用）
```

依赖方向保持 `frontend → backend → knowledge-core`。Batch B **不修改** Core 的实体字段、端口签名、`ReviewService`、A1-02 Hash、A1-03 `LinkKeyRebuild`。

## 2. 组件职责

| 组件 | 职责 | 明确不做 |
|---|---|---|
| `attachment_storage` | 计算 SHA-256、分片路径、临时写、fsync、原子发布、no-clobber、读取、隔离移动、Windows 重试 | 不查 DB、不判断引用、不 commit |
| `attachments` 服务 | 入参校验（JSON base64 上传）、MIME/magic、大小、归档策略、去重、写 `Attachment`、元数据列表、删除入队、错误映射 | 不拼 SQL、不直接操作 session commit、不引入 multipart 依赖 |
| `attachment_staging` | 创建 staging、`.creating`/`.activity`/`.complete` 标记、写文件、校验 manifest、复制/发布、清理 | 不创建正式引用；不以 staging 根目录单一 mtime 判活 |
| `import_review_hook` | 在 Core approve 后、第一次 commit 前执行既有 DB 补齐与附件引用写入 | 不修改 Core、不追加 manifest、不 commit |
| `storage_lock` | 单 key 互斥、多 key 排序、SQLite TTL/heartbeat、PG advisory 权威 + token fencing、接管 | 不承载业务状态；PG 不以行 TTL 授权接管 |
| `attachment_maintenance` | GC 认领/隔离/清除、staging 清扫、ORP、一致性报告 | 不修改用户内容、不静默删 DB 行 |
| `repositories_v2` | 纯持久化，flush 不 commit；条件更新带 token | 不判断文件是否存在 |

## 3. 数据库与迁移边界

- 使用 `0006_v2_markdown_kb.py` 已建的 `attachment`、`gc_task`、`storage_lock` 表。
- 使用既有索引 `ix_attachment_storage_key`；**不新增** `content_hash` 索引、不新增 `(item_id, storage_key)` 唯一约束。
- 不新增表/列/索引/迁移。若实现中发现缺列，停止并报告，不得就地改 schema。
- 所有时间 UTC；UUID 存 `String(36)`；JSON 负载仍以 Text 存储。
- SQLite 必须 `PRAGMA foreign_keys=ON`；附件行删除依赖既有 `item_id` FK CASCADE。
- PostgreSQL 路径不得出现 `FTS5/MATCH/bm25/rowid`；Batch B 不涉及全文检索，但共享 session/迁移代码不得引入方言污染。

## 4. 事务与一致性模型

### 4.1 两类写路径

| 路径 | DB 事务 | 物理文件 | 一致性保证 |
|---|---|---|---|
| 独立上传 | 单事务：插入 `attachment` 行 | 先写临时文件并发布正式 blob；DB 失败则 blob 成为孤儿 | 物理先于 DB；失败由 ORP 收敛，**不宣称原子**；Archived item 由事务内保护拒绝新增 |
| 独立删除 | 单事务：删 `attachment` 行 + 插入 `gc_task(pending)` | 事务内不动文件 | 引用先消失，GC 后清物理；Archived item 允许删除引用 |
| Draft 导入（ZIP-only） | 文档+附件引用同一 DB 事务 | staging 已存在；正式 blob 在 commit 前发布 | 同 4.1 第 1 行；失败 blob 由 ORP 收敛 |
| Active approve | ① 业务事务（item/tags/origin/links/附件引用）② 索引事务 | 在 ① 之前完成 promote/publish | 文件先于 ①；① 失败文件成孤儿；**两次 commit 不合并** |
| Active 附件-only 导入 | 不创建 staging/pending | 无 | **明确拒绝** `ATTACHMENT_ONLY_IMPORT_UNSUPPORTED`；不得静默成功 |

### 4.2 事务①与事务②

1. S0 只读预检并关闭会话。所有审核决议持共同 `review_id` 决议锁。导入审核再持既有来源协调锁；approve 保留基线的 `identity_guard`。恢复门先完成，任何内部恢复 DB 事务均已提交/关闭。
2. 带附件时持对应 staging guard，再获取全部 StorageKeyLock。只读复核审核快照、目标、归档及 D22/D23 前置，关闭该会话，然后校验、复制、重读 Hash、no-clobber 发布。DB 业务写事务始于发布之后。
3. S1 新业务会话重读 PENDING、复核 S0 payload 与发布计划，保护目标 item 原状态，再执行 Core approve → Hook 的 DB 补齐（含附件引用）→ `verify_all` → 业务 commit ①。Hook 无物理文件操作，发布失败不进入①。① 失败保留 staging，已发布孤儿由 ORP 收敛。
4. ① 成功后释放 storage guard；在 staging guard 下尽力清理已完成的目录；随后释放所有业务协调锁。② 独立执行提交后索引同步；失败只回滚②、记录告警，按已批准状态返回。随①触发的 FTS 更新不属于②。
5. 无附件路径保持既有业务/索引事务语义。审核时序与错误详见 active-review-integration §2、§5–7。

### 4.3 物理与 DB 的诚实边界

- 不存在跨文件系统+数据库的原子事务。
- 允许的中间态：`blob 存在、DB 无引用`（孤儿）；`DB 有引用、blob 缺失`（不一致，只报告/下载失败，不自动删 DB）。
- 不允许的中间态：`DB 引用指向被覆盖的 blob`；`pending 期间出现正式引用`；`reject 后仍可 approve`。
- 所有崩溃恢复依靠：启动时 staging/quarantine 扫描 + 周期 ORP；不依赖“进程一定优雅退出”。

### 4.4 SQLite 写事务与存储锁的先后（强制）

- 上传、Draft 导入、附件 approve：关闭 S0/预发布只读事务，完成 D23 恢复（适用时）并退出其内部会话，先取存储锁、完成物理发布，再开启短业务写事务。顺序保留 `Core approve → DB Hook → ①`。
- 业务事务内从既有 item 获取归档保护后再改变其状态或新增引用。PG 锁住目标 item 行再读状态。SQLite 在适配层对同一 item 先执行条件防护更新（现有非 archived 状态，`status=status`、`updated_at=updated_at`，保留字段值），检查匹配行数并在同 session 重读。该受控写前置早于 Core 的条目状态变更，冲突/busy 时回滚，可在请求预算内从新事务重试。无需改全局事务模式。
- SQLite commit 之前 `verify_all` 使用同一业务 session。覆盖上传、Draft 和 approve。写事务内禁止独立连接获取/等待 StorageKeyLock、复制、Hash 或发布。rollback 或 commit 完成后释放锁。
- GC claim 短事务先提交/关闭，之后取 StorageKeyLock。ORP/staging 扫描预读会话同样先关闭才取锁。SQLite 需要写锁时区分竞争和真租约失配。PG 最后提交区间按 storage §4.6 锁住完整 key 的 token 行，接管者完成 token 提交前不得触碰文件。

## 5. 配置冻结

新增配置全部有默认值，环境变量前缀沿用现有 `EXPLAINLAB_`（以 `Settings` 实际字段名为准）：

| 配置 | 默认 | 说明 |
|---|---|---|
| `attachment_storage_root` | `<data_dir>/attachments` | 正式内容寻址根；必须与 quarantine 同卷 |
| `attachment_staging_root` | `<data_dir>/import-staging` | 导入 staging 根；与正式根同卷 |
| `attachment_quarantine_dir` | `<storage_root>/_quarantine` | 不得作为正式 key 枚举 |
| `attachment_max_bytes` | `10485760`（10 MiB） | 单文件上限 |
| `attachment_mime_allowlist` | PNG/JPEG/GIF/WebP/PDF/TXT/MD/CSV | D-08；SVG 永不允许 |
| `storage_lock_ttl_seconds` | `60` | 租约 TTL |
| `storage_lock_heartbeat_seconds` | `15` | 心跳 |
| `storage_lock_wait_seconds` | `10` | 获取等待上限 |
| `gc_max_attempts` | `8` | 含首次 |
| `gc_retry_base_seconds` | `60` | 指数退避基数 |
| `gc_retry_max_seconds` | `21600` | 6h 上限 |
| `gc_quarantine_seconds` | `86400` | 24h 安全期 |
| `orphan_scan_interval_seconds` | `300` | 5 分钟 |
| `attachment_import_max_count` | `100` | 单次导入附件数（O-B05 已裁决） |
| `attachment_import_max_total_bytes` | `104857600`（100 MiB） | 单次导入总字节（O-B05） |
| `staging_grace_seconds` | `86400`（24h） | staging 清扫宽限（O-B05）；pending 引用优先于时间 |

staging 元数据文件名（服务端固定，不是配置项）：`.creating`、`.activity`、`.complete`。它们只存在于 `import-staging/<staging_id>/`，不进入正式 key 枚举。

启动校验（fail-fast）：

- 根目录不存在则创建；创建失败 → 应用启动失败（不降级到内存/临时目录）。
- 启动与运行期均按 storage-and-lock-contract §1 校验真实目录、同卷、非重叠、专用分区及链接/重解析点。
- 根目录不得位于仓库跟踪目录；默认在 gitignore 的 `backend/data/` 下。
- 路径必须是绝对路径或相对 `data_dir` 解析后的绝对路径；禁止 `..` 逃逸。

## 6. 并发模型

- 单 Backend、单 worker、单数据根，沿用 Batch A 的 ProcessLock。PG 双连接及双 worker 用例属于并发取证。后台 ORP 按 GC 文档取扫描领导权。
- 统一获取顺序：**review 决议锁（适用）→ ImportCoordinator 来源锁（适用）→ identity_guard（发生身份写时）→ staging_id guard（适用）→ StorageKeyLock → 业务 DB 写事务**。释放逆序；正常清理可继续持 staging guard，索引②在业务协调锁外执行。创建 pending 持来源、身份及 staging guard 至提交，不需要正式 key 锁。
- Reject 走共同 review 锁，再按可解析身份或 target fallback 走来源锁；它不写身份，不进入身份 Journal。清理不能在持 storage 锁后再获取 staging/review 锁。
- GC 先认领 task 的短事务然后取 storage 锁；ORP staging 先取 staging guard 再取需要的 storage 锁。列表/下载只读不取 storage lock；附件路由为同步 def。禁止在上述业务锁下做模型/网络调用。

## 7. 安全与日志

- 密钥不进入附件路径、manifest、日志、响应。
- 日志只记录：`storage_key`（hash）、`item_id`、`attachment_id`、`gc_task_id`、错误类型、状态；**不记录**文件内容、原始路径、用户文件名（文件名可能含隐私）。
- 对外错误响应只返回稳定错误码，不回传异常文本/路径/堆栈。
- 下载 `Content-Disposition` 的文件名做 CR/LF/引号/路径分隔符清洗，并按 RFC 5987 编码。
- 不接受客户端提供的绝对路径、`storage_key`、`content_hash` 作为写入依据；一律服务端计算。

## 8. 明确禁止

1. 把物理文件移动/复制说成与 DB commit 原子。
2. 为通过验收而伪造 PG 连接、伪造 Windows 证据、用 mock 替代真实文件系统。
3. 在 pending 阶段写正式 `attachment` 行。
4. approve 时向 envelope 追加/修改 `attachments`。
5. 修改 Core `ReviewService` 或端口签名。
6. 新增迁移/表/列/索引/依赖。
7. 删除/弱化既有测试或稳定错误码。
8. 在 GC/ORP 未持锁时删除文件。
9. 对正式 blob 做 `os.replace` 覆盖已有不同内容。
10. 将附件导出、BAK、Merge 附件迁移偷偷纳入 Batch B。
11. 仅凭 PG `storage_lock` 行 TTL 过期就接管仍存活的 Advisory Lock。
12. 用 staging 根目录单一 mtime 判定 staging 孤儿。
13. 下载校验后按路径重新打开文件再流式输出。
14. Active 附件-only 导入静默成功或忽略附件。
15. 对 Archived item 新增附件。
