# Storage and StorageKeyLock Contract

本文件冻结物理存储与 key 级互斥契约。所有实现必须遵守；任何偏离必须回到 `README.md` 的差异表并由 ChatGPT 裁决。

## 1. 根目录与同卷约束

```text
<data_dir>/
├─ attachments/                    # 正式内容寻址根（attachment_storage_root）
│  ├─ <k0k1>/<k2k3>/<64hex>        # 正式 blob
│  ├─ .tmp/<uuid>.part             # 同卷临时文件
│  └─ _quarantine/
│     ├─ <64hex>.<gc_task_id>      # 正式 blob 隔离
│     └─ staging/<staging_id>.<ts> # 整个 staging 目录隔离
├─ import-staging/                 # staging 根
│  └─ <staging_id>/
│     ├─ .creating                 # 创建标记
│     ├─ .activity                 # 最近活动标记（服务端刷新）
│     ├─ .complete                 # 完成标记（JSON 元数据）
│     ├─ blobs/000001.bin
│     └─ blobs/000002.bin
└─ ops/
   └─ attachment-consistency-<utc>.json
```

- 解析根的真实绝对路径，比较规范路径、目录身份和祖先关系。Windows 比较遵循卷与文件系统大小写规则。正式根和 staging 根必须是 `data_dir` 内互不相等、互不包含的专用目录；均不得等于或覆盖数据根、DB 文件/专用目录、身份 Journal、身份归档、source-instance-id 或 `ops` 路径。共享的 `data_dir` 只是父目录。
- 正式根内只允许明确分区：固定保留子目录 `.tmp`、默认 `_quarantine`（如配置则必须是正式根内独立专用直接子目录，名称不得落入分片命名空间），以及 quarantine 下的固定 `staging/`。正式枚举按实际保留子树排除，不能只匹配默认字符串。staging 根仅枚举合法小写 UUIDv4 直接子目录，正式根仅按标准 shards 枚举 64hex 普通文件。
- 启动逐组件拒绝符号链接、junction/重解析点、非目录根及路径别名。正式根、staging、`.tmp`、quarantine 及实际操作源/目标父目录均须同卷。创建路径后复核，运行期每次枚举/打开/移动/删除前检查实际类型、根内与同卷，使用平台能提供的拒绝跟随机制。可疑子树只报告，删除前不递归跟随链接；绝不移动整个根。运行中 `EXDEV` 保留源并返回既有跨卷错误。
- 目录由服务端生成，权限尽力 `0700`；磁盘名不使用用户文件名。目录创建或根校验失败拒绝启动。Windows 长路径告警保留。外部进程拥有写权限并并发替换目录仍需由本地部署权限保护，验收覆盖已存在或操作前发现的重解析路径。
- Staging 标记和活动时间按 attachment-lifecycle §3、GC/ORP §6.4。文件 mtime 是活动证据，空目录只走显式半成品分支。

## 2. 内容寻址与 hash

### 2.1 唯一算法

- `content_hash = SHA-256(实际字节)`，小写十六进制 64 字符。
- `storage_key = content_hash`；`Attachment.storage_key` 与 `Attachment.content_hash` 必须逐字相等。
- 服务端从**实际写入的字节**计算；不信任客户端 `Content-MD5`、文件名、扩展名或声明 hash。
- 上传时边写边算或写完后重读计算；以重读/最终文件计算结果为权威。二者不一致按 `ATTACHMENT_HASH_MISMATCH` 处理。

### 2.2 分片

`<k0k1>/<k2k3>/<key>`：前 2 个 hex、次 2 个 hex、完整 64 hex。例如
`ab/cd/abcd...`。分片只影响目录分布，不改变 key。

### 2.3 引用与去重

- 同一 `storage_key` 可被多条 `attachment` 行引用；引用数由 `COUNT(attachment WHERE storage_key=?)` 派生，不维护计数列。
- 上传去重以 `(item_id, storage_key)` 的现有引用为准（`list_attachments(item_id)` 后比较）；不以 `find_by_hash` 作为唯一去重/授权依据（D-B09）。
- 不新增 `content_hash` 索引；`find_by_hash` 保留端口语义，但不进入上传/下载/GC 热路径。

### 2.4 索引

只使用既有 `ix_attachment_storage_key`。`count_references`、`list_storage_keys`、按 key 查询均走该索引；禁止为此新增索引或迁移。

## 3. 正式 blob 发布（no-clobber）

### 3.1 写入步骤（上传 / promote / 导入共用）

**前置：临时文件可在锁外预先准备；`publish_no_clobber` 调用时调用方必须已成功 `acquire(StorageKeyLock)`。本函数不自行加锁、不重入。** 发布、复制、重读 Hash 和 fsync 均在业务写事务之外。调用方随后在持 guard 状态下完成业务提交。

```text
1. 校验 key：^[0-9a-f]{64}$
2. 准备临时文件 attachments/.tmp/<uuid>.part（同卷，可在锁外）：
   open('xb') → write_all → flush → os.fsync(fd) → close
3. 重新读取临时文件计算 SHA-256，必须等于 key；否则删除临时文件并报错
4. 调用方 acquire(key)；成功后才调用 publish_no_clobber；未持锁 → 编程错误
5. 若正式路径已存在：
     a. 校验 size + SHA-256
     b. 相同 → 删除临时文件，复用现有 blob，成功
     c. 不同 → 不覆盖；删除临时文件；ATTACHMENT_KEY_COLLISION
6. 正式路径不存在：
     a. 首选 os.link(temp, final)（同卷、no-clobber、原子可见）
     b. FileExistsError → 回到 5
     c. 文件系统不支持 hard link：
        - Windows：os.rename(temp, final)（目标已存在则失败，回到 5；不覆盖）
        - POSIX：不得用覆盖式 rename；返回 ATTACHMENT_STORAGE_UNAVAILABLE / ATTACHMENT_WRITE_FAILED
        发布后仍须校验；不得把该路径说成对外部进程完全免疫
7. 发布后重新校验 final 的 size + SHA-256：
     不匹配 → 持锁复核是本次发布路径，尽力隔离到 quarantine；ATTACHMENT_WRITE_CORRUPTED；若隔离也失败，保留现场并报告，不提交引用
8. POSIX 同步受影响的父目录，首次创建分片时同步新增目录项所在各级父目录；Windows 跳过目录 fsync
9. 删除残留临时文件（若 link 成功）
10. 由调用方在锁内完成 DB 写入（upload/approve）或状态更新（GC），再 release
```

### 3.2 不允许

- 不允许 `open(final, 'wb')` 直接写正式路径。
- 不允许在正式路径存在且 hash 不同的时候 `os.replace` 覆盖。
- 不允许先删正式 blob 再发布新内容。
- 不允许把 `_quarantine` 中的文件直接 rename 回正式路径而不校验 hash/锁/引用。
- 不允许把 `os.replace` 当作 no-clobber 降级；Windows 的无 hard link 降级只能使用“目标存在即失败”的 `os.rename`。

### 3.3 崩溃窗口

| 崩溃点 | 残留 | 收敛 |
|---|---|---|
| 临时文件写完、未发布 | `.tmp/*.part` | 上传自身清理；崩溃残留 Batch B **只报告不自动删**（ORP-02） |
| link/rename 成功、DB 未写 | 正式 blob 无引用 | ORP 观察零引用且 mtime 满 24h 后入 GC |
| DB 已写、响应未返回 | 正常引用 | 客户端重试命中 `(item_id, key)` 去重 |
| 发布后校验失败 | quarantine 文件 | ORP 按引用/隔离状态恢复或报告 |
| approve ① 失败 | 正式 blob 无引用 | ORP 观察零引用且 mtime 满 24h 后入 GC；**不回滚已发布文件** |

## 4. StorageKeyLock 双方言契约

### 4.1 参数与语义

- TTL：60s；心跳：15s；获取等待：10s（决策 5）。
- `StorageLease = {storage_key, owner, lease_token, lease_expires_at}`。
- `owner`：进程内唯一字符串，建议 `"<hostname[:16]>:<pid>:<uuid4hex[:12]>"`，最长 64 字符；不得含密钥/用户信息。
- `lease_token`：单调递增；每次成功获取/接管 +1；同一 key 永不回退。
- **不重入**：owner 标识一次 guard 获取，进程标识仅作前缀。同一 owner 对同一完整 key 嵌套 acquire 返回 None；批内输入先去重。
- `acquire` 只在“无锁”或“租约已过期”时成功；等待上限 10s，超时返回 `None`。
- `renew`/`verify`/`release` 仅在 owner+token 匹配且未过期时成功；否则 `False`，调用方**立即中止**不可逆操作。
- `release` 不删除 `storage_lock` 行，只清 owner 并将 `lease_expires_at` 置为当前时间；token 保留以保证单调性。PG 额外 `pg_advisory_unlock` 并物理关闭。即使行已过期，也必须释放本 guard 自己的会话锁。
- 旧 worker 持过期 token 的任何 `update_task`/文件操作必须被拒绝（fencing）。

### 4.2 SQLite：`storage_lock` 租约

表结构沿用 `StorageLockORM`：`storage_key` PK、`owner`、`lease_token`、`lease_expires_at`、`locked_at`。

获取（单条原子语句 + 插入竞争）：

```sql
-- 已存在且过期；owner 相同视为不重入，必须失败返回 None
UPDATE storage_lock
SET owner=:owner, lease_token=lease_token+1,
    lease_expires_at=:expires_at, locked_at=:now
WHERE storage_key=:key
  AND lease_expires_at <= :now
  AND owner <> :owner;

-- 不存在（INSERT 的 UNIQUE 冲突视为竞争失败，重试至等待上限）
INSERT INTO storage_lock(storage_key, owner, lease_token, lease_expires_at, locked_at)
VALUES(:key, :owner, 1, :expires_at, :now);
```

- 先 UPDATE；`rowcount==1` 即成功。`rowcount==0` 时尝试 INSERT；`IntegrityError` 说明他人刚插入，进入等待重试。
- `renew`：`UPDATE ... SET lease_expires_at=:new WHERE storage_key=:key AND owner=:owner AND lease_token=:token AND lease_expires_at > :now`；`rowcount==1` 为成功。
- `verify`：`SELECT 1 ... WHERE storage_key/owner/token/expires_at > now`。
- `release`：`UPDATE ... SET owner='', lease_expires_at=:now WHERE ... owner/token`；不 DELETE。
- **诚实限制**：SQLite 租约是逻辑锁，降低而非消除 TOCTOU；物理步骤前必须再次 `verify`。不得宣称严格并发安全。

### 4.3 PostgreSQL：每 guard 一个专用会话

- D-B02 保留：会话 advisory lock 是互斥权威，`storage_lock` 按完整 key 维护 token 与租约。有效租约还须 owner/token/expiry 匹配。行 TTL 过期不能授权其他会话接管；原会话解除锁或物理断开后，获得实际锁者才可递增 token。
- 将每个完整 key 前两段 8 hex 转有符号 int32，取二元组作为实际锁身份。整批建立 **一个独占的物理连接**，按二元组有符号字典序获取去重后的身份，同一身份只调用一次 `pg_try_advisory_lock(classid,objid)`。完整 key 不合并，取得全部物理锁后在该连接的一笔短事务按完整 key 排序 UPSERT 与递增 token；提交成功才交付 guard。一至 100 个 key 均只用一个该类连接，业务 session 另计。
- 单 key 也走同一协议。获取入口拒绝同一 owner 嵌套或重复持有同一完整 key；不能用旧 owner 行代替会话归属判断。各 key 的持有关系由 guard 记录，检查连接仍为同一物理会话、该会话仍持有对应二元组锁、完整 key 行仍匹配与未过期；校验失败即失效。禁用自动重连复活旧 guard。
- 同一会话的上锁、token 短事务、heartbeat、verify、release 串行执行，一个 guard 一个心跳调度。心跳按完整 owner/token/未过期条件批量续约，部分失败则整 guard 失效。短事务每轮结束，避免 idle-in-transaction。业务写事务不更新 PG 锁行。
- 获取总预算 10s 涵盖连接建立、重试与 SQL，所有阻塞操作用剩余预算或更短超时；拿不到全部锁或 token 写失败，回滚锁行短事务，逆序解锁已获取的唯一身份并物理关闭。释放时先尽力条件清行且保留 token，再逆序显式解锁并关闭物理连接，异常时关闭兜底。仅归还池连接不算物理关闭。中断/丢失后旧 guard 不得再操作。
- ORP 扫描领导权使用独立专用连接与 **单 bigint advisory 锁命名空间**，其生命周期为一轮扫描，业务二元组锁另取。单 Backend/单 worker 约束见 architecture §6。

### 4.4 多 key 加锁顺序

- 调用方以去重后的完整 key 集合申请 guard；SQLite 按完整 key 字典序，PG 按 §4.3 的实际冲突域顺序。一次批取齐再发布，部分成功按各自实际加锁顺序逆序释放。不可持部分锁继续或嵌套向同 manager 补取。
- 整批共用 10s deadline。S0/预发布只读会话在取锁前关闭，D23 恢复完成、相关内部事务已关闭后才获取；SQLite 已开启业务写事务时禁止独立连接获取锁行。
- `verify(lease)` 仍为既有 Core port；批 guard、带同业务 session 的 `verify_all` 和 deadline 由 backend 适配层实现。

### 4.5 owner / 接管 / 失配

| 场景 | 行为 |
|---|---|
| 同 owner 再次 acquire 同 key | 返回 `None`（不重入），调用方视为编程错误并中止 |
| 租约过期，另一 worker acquire（SQLite） | 允许；token+1；旧 worker 之后 verify/renew 失败 |
| 行租约过期，另一 worker acquire（PG） | 只有拿到 Advisory Lock 才能接管；行过期不构成授权；拿不到则等待/放弃，旧连接存活期间绝不由行 TTL 接管 |
| 旧 worker 在失配后继续写文件 | 禁止；若已进入不可逆步骤，停止并让 ORP 收敛，不得“抢回” |
| release 时 token 已变 | 返回 `False`；不释放、不删除任何文件 |
| 心跳失败 | 标记本地 lease 失效；下一次 verify 前中止；不得继续删除/移动 |
| 进程崩溃 | SQLite 靠过期；PG 连接关闭释放 advisory lock；GC 租约靠过期接管 |

### 4.6 心跳

- 每批 guard 至多一个心跳调度，每 15s 续齐持有的租约；操作结束停止。获取 SQLite 至第一把锁后即计时，整批获取不得耗尽其 TTL。
- `renew` 返回 `False`（owner/token/expiry 失配）→ 设置 abort 标志；主流程在下一个不可逆步骤前检查并抛 `STORAGE_LEASE_LOST`。
- SQLite `renew` 遇到 `database is locked/busy` 属于**瞬时竞争**，不是令牌失配：心跳应记录并稍后重试，不得立即 abort；仅当本地已观察到租约过期或 owner/token 不匹配时才 abort。实现必须区分“False（失配）”与“可重试异常”。
- 心跳线程不得执行文件操作、DB 长事务或日志刷屏；失败只记录一次。
- **非事务性批处理**（ORP、staging 清扫）若预计超过 60s，必须分片处理，每片重新获取/释放锁；不得依赖心跳无限延长。
- **上传、Draft、approve 的锁必须持有到对应 DB commit**。耗时文件操作全部在业务写事务前完成；SQLite 主写事务内心跳遇 busy 可退避，commit 前由同 session 验证 token/expiry。失配、到期或无法验证时先回滚，再释放；独立写会话不能在主事务内阻塞等待。
- `verify_all` 由将执行 commit 的同一业务 session 核对所有锁行。SQLite 在本写事务内读取 owner/token/expiry，避免另开连接。PG 在末次提交区间暂停并排空本 guard 的 heartbeat，业务 session 按完整 key 排序锁住各 token 行（`SELECT … FOR UPDATE`），核对 owner/token/expiry，再由独立专用会话只检查会话身份及 advisory 持锁状态。DB token 行锁持至 commit/rollback。若 PG 专用会话在最后检查后断线，接管者仍必须等 token 写成功并提交才能获得可用 guard，期间不能动文件。最终核验/等待有界，异常回滚业务事务后再关闭 guard。

## 5. 读取与下载

- 读取路径由 `storage_key` 计算；先校验 64 hex，再拼接；禁止任何用户输入进入路径。
- **必须只打开正式 blob 一次**：用同一个已打开文件句柄完成 size 校验与流式 SHA-256 计算；校验通过后 `seek(0)`，继续从**同一句柄**流式输出。禁止校验后按路径重新打开、禁止使用会重新 open 路径的 `FileResponse`。打开后即使路径被 rename/替换，句柄仍指向已校验内容；外部进程原地改写仍属残余风险，不得宣称完全消除。
- 打开文件后校验 `size` 与 DB 一致；并以流式分块重算 SHA-256（不整体读入内存），与 `storage_key` 不符返回 `ATTACHMENT_BLOB_CORRUPTED`（503），不返回部分内容。校验通过后再流式输出；不得边发边发现 hash 错误。
- 下载使用流式响应；不要一次读入内存（10 MiB 上限虽小，仍按流式实现）。
- 文件不存在：`ATTACHMENT_BLOB_MISSING`（503），不自动重建、不自动删除 DB 行。
- 流拥有已打开的句柄，正常结束、异常、客户端取消或校验未通过均释放。Windows 的真实占用可能阻止替换，以该结果与同句柄断言分别取证。
- 读取不加 StorageKeyLock；GC 隔离可能造成瞬时 `FileNotFoundError`，按 503 返回并由客户端重试。GC 必须先确认引用为 0 才会隔离，正常引用不应被隔离。

## 6. Windows 文件系统契约

- **文件占用**：`PermissionError`/`OSError` 的 `winerror` 32（sharing violation）、33（lock violation）视为可重试；使用 100ms 起、上限 1s、总预算 5s 的重试；仍失败 → `failed_retryable` 或 `ATTACHMENT_WRITE_BUSY`，不强制删除、不关闭他人句柄。
- **原子替换**：Windows 同卷 `os.rename` 在目标不存在时原子发布，目标存在则失败（no-clobber）；本契约禁止使用会覆盖目标的 `os.replace` 发布不同内容。无 hard link 时仅允许该 no-clobber rename 降级。
- **hard link**：NTFS 支持；FAT/exFAT/网络盘可能不支持。`OSError` 视为“不支持”；Windows 走 no-clobber `os.rename` 降级，POSIX 直接失败（不覆盖）。不得把降级说成完全原子发布。
- **路径**：统一 `pathlib.Path` + 绝对路径；禁止 `\\?\` 手工拼接；用户文件名**不得**进入任何路径（只做清洗后的展示名）；拒绝包含 `..`、盘符、UNC、ADS（`:`）的**路径输入**。文件名只用于 `Content-Disposition`，并清洗 CR/LF/引号/分隔符。
- **大小写**：key 一律小写；在大小写不敏感文件系统上按小写路径访问。
- **跨卷**：启动即拒绝；运行中发现 `EXDEV` → `ATTACHMENT_STORAGE_CROSS_VOLUME`（503），不得先删源。
- **杀毒/索引器**：可能瞬时占用新文件；发布后校验失败先重试读取，再判定损坏。
- **长路径**：启动检查根路径长度；超过 240 字符告警；不静默截断。
- **fsync**：Windows 无目录 fsync；文件 flush+fsync 仍执行。不要声称 Windows 具备 POSIX 目录持久化语义。

## 7. 锁与事务的边界

- `StorageKeyLock` 是**物理互斥**，不是数据库事务锁；不得用它替代 `ImportCoordinator` 或 DB 唯一约束。
- 上传/approve 持锁跨 DB commit 是允许的短窗口；禁止持锁做模型调用、网络 I/O、用户等待。
- GC 持锁期间只做：复核引用、移动/删除、更新 `gc_task`；不做其他业务写。
- 锁释放失败不回滚已提交业务；记录 `STORAGE_LOCK_RELEASE_FAILED`，租约自然过期。
- 隔离文件采用 GC §5 的无覆盖语义；staging 目录的无覆盖 rename 在同一 staging_id guard 下检查目标，隔离名含 ID 与时间，冲突保留源。
- 任何“先释放锁再删除”的顺序禁止；删除/隔离必须在锁内完成。
- PG 的 `storage_lock` 行 TTL 只是展示/心跳元数据；不得在未取得 Advisory Lock 时依据行状态删除、隔离或接管。
