# GC and Orphan Recovery

本文件冻结附件 GC 七态状态机、quarantine、退避、独立孤儿扫描（ORP）、staging 清扫与一致性报告。所有删除动作都必须可审计、可恢复、可解释。

## 1. 原则

1. **引用消失后允许隔离，清除须等待**；必须经 `gc_task` + 24h 安全期。
2. **任何删除/隔离前必须持 `StorageKeyLock` 并校验 fencing token**。
3. DB 不可用、锁不可得、引用不确定时：**不删**，转为重试或人工。
4. 正式 blob 与 staging 分开治理；staging 删除不得影响正式 blob。
5. 只报告 DB↔物理不一致，不自动删 DB 引用；不静默“修复”用户数据。
6. 物理操作与 DB 状态更新不是原子事务；崩溃由下一次 worker/ORP 收敛。

## 2. 任务来源

| 来源 | 行为 |
|---|---|
| 删除最后一条附件引用 | 同一 DB 事务插入 `gc_task(status=pending)`；不删文件 |
| ORP 发现无引用且超 24h 的正式 blob | 插入 `gc_task(status=pending)`（若无活跃任务） |
| GC 重试到期 | `failed_retryable` 且 `next_retry_at<=now` → 可被 claim |
| 人工运维 | 仅内部函数 + 审计日志（操作者/时间/任务/前后状态）；Batch B 不新增 HTTP 管理端点（O-B07） |

`ensure_gc_task(storage_key)`：

- 已有 `pending/running/failed_retryable` 同 key 任务 → 不新增。
- 已有 `failed_permanent/needs_manual` → 不自动新增，只记录告警。
- 已有 `done/cancelled` 且再次无引用 → 可新增新任务。
- 插入后 `lease_token=0`、`attempts=0`、`next_retry_at=NULL`。

> **去重的诚实边界**：`gc_task` 只有普通索引，没有 `(storage_key, active_status)` 唯一约束（决策 3 禁止新增索引/迁移）。`ensure_gc_task` 的“查活跃再插入”在两个并发删除/ORP 与删除竞争时**可能插入重复任务**。冻结口径：去重是尽力而为，不是严格保证；GC 必须按任务幂等处理（持 StorageKeyLock、引用复核、确定性 quarantine 路径），重复任务最终分别 `done/cancelled`，不得双删；验收不得宣称“并发下必无重复任务”。

## 3. 并发与认领

- 任务认领：`GcTaskRepository.claim(task_id, owner, lease_ttl_seconds=60)`。
  - `pending` 或租约过期的 `running` → `running`，`lease_token+1`，`attempts+1`。
  - 租约过期的 `running` 若 `next_retry_at > now`（quarantine 安全期未到）→ 返回 `None`，不得提前接管。
  - 终态、未过期 running、未到期、预算已用尽等条件不满足 → `None`。除隔离等待尚未到期外，过期且已耗尽的 running 可条件转 failed_permanent，保留文件供观察/恢复。
- 任务租约心跳 15s；与 `StorageKeyLock` 心跳独立但同参数。SQLite busy/locked 视为瞬时竞争，重试而不立即中止；只有条件更新返回 token/owner 失配或租约已过期才中止。
- 拿到任务后，再获取该 key 的 `StorageKeyLock`；顺序固定：**先任务租约，后存储锁**，避免反向死锁。
- `claim` 必须是独立短事务：提交并关闭该事务后，才可获取 `StorageKeyLock`。**禁止**在未提交的 `claim` 写事务中再用独立连接写 `storage_lock`（SQLite 单写者互等）。
- 多 key 批处理遵循 storage-and-lock-contract §4.4；任务本身逐 key 认领。
- **PG 锁权威**（D-B02 已裁决）：`StorageKeyLock.acquire` 只有在取得会话 Advisory Lock 后才算成功；`storage_lock` 行仅保存单调 token 与展示租约。行 TTL 过期**不释放**、也不授权接管仍存活的 Advisory Lock；只有原连接关闭/进程死亡才释放。验收用两个真实连接覆盖（LCK-10）。
- 任务 worker 每次物理变更前以短查询/条件更新核对 task 仍为 running、owner/token 匹配且租约未过期，同时复核 storage guard 及引用/路径前置。后续任务更新继续条件检查 owner/token 和当前状态；不接受失效 worker 写回。SQLite 物理步骤前结束 DB 写事务，不能靠持未提交任务写锁保护文件。ORP 无任务的识别/恢复阶段不冒用 task token，使用同一 StorageKeyLock 并复核最新引用和候选。
- 观察到失配立即停止。verify 到 syscall 的残余窗口按隔离、重新复核与物理代次恢复处理。旧 worker 无权用下一代正式路径替代已确定的 quarantine 槽执行 purge。

## 4. 七态状态机

### 4.1 状态定义

| 状态 | 含义 | 是否终态 |
|---|---|---|
| `pending` | 待处理（初始或人工重试），不含 quarantine 等待 | 否 |
| `running` | 已被 worker 认领并持有租约 | 否 |
| `done` | 本任务负责的隔离代次已清除（或无文件）；仍有无引用正式代次时已交接给后继任务/ORP | 是 |
| `cancelled` | 持锁复核发现引用>0，放弃回收；不删文件 | 是 |
| `failed_retryable` | 瞬时失败，等待退避重试 | 否 |
| `failed_permanent` | 达到最大尝试或不可重试错误；自动终态 | 是（仅运维可转 `needs_manual`） |
| `needs_manual` | 状态不明/冲突/损坏，必须人工判断 | 否（等待运维） |

### 4.2 允许迁移

```text
pending ──claim──▶ running
running ──claim(租约过期接管)──▶ running   # token+1, attempts+1
running ──引用>0──▶ cancelled
running ──本任务负责的零引用代次已完成或无文件──▶ done
running ──成功 quarantine──▶ running      # 记录 path/time；租约置过期；next_retry_at=quarantined_at+24h
running ──瞬时失败, attempts<8──▶ failed_retryable
running ──第 8 次失败、到期且耗尽或不可重试──▶ failed_permanent
running ──状态不明/冲突──▶ needs_manual
failed_retryable ──到期──▶ pending        # 由调度器/worker 条件更新
failed_retryable ──attempts>=8/不可重试──▶ failed_permanent
pending ──操作员取消──▶ cancelled         # 可选，Batch B 不提供 HTTP
failed_permanent ──运维显式转人工──▶ needs_manual
needs_manual ──运维重试──▶ pending
needs_manual ──运维放弃──▶ cancelled
```

**禁止：**

- `done/cancelled` → 任意状态（终态不可覆盖）。
- `failed_permanent` → `pending` 自动重试；必须先显式转 `needs_manual`。
- 重启时把所有 `running` 置 `pending`；只能等租约过期后 `claim` 接管。
- 在 quarantine 等待阶段删除文件而不复核 24h 与引用；不得把该等待改写成 `pending`。

### 4.3 计数与时间

- `attempts` 只在 claim 成功时 +1，最多 8 次，包含隔离等待到期后的再次认领。正常隔离等待期间不认领，不递增。第 8 次失败转终态；隔离成功后仍保留 24h 窗口。预算耗尽时将到期任务转 failed_permanent，保留给 ORP 合规恢复或运维处理。人工显式重试时重置 attempts，保留有效隔离路径和时间。
- 第 n 次认领后的可重试失败，若仍有自动预算，按 `min(60 * 2**(n-1), 21600)` 秒退避。O-B11 保留 60/120/240/480/960/1920/3840/7680 的公式值。第 8 次终态无下次调度，21600s 为配置上限。
- 引用删除入队可直接安排隔离。ORP 只在看到零引用且正式文件 mtime 满 24h 时入队。purge 至少等隔离记录 `quarantined_at` 与文件 mtime 各满 24h。使用 UTC；未来时间或无法识别的时钟证据保守等待/报告，禁止以前移 mtime 缩短隔离期。

## 5. GC 执行流程与物理代次

- 每个 task 的唯一隔离槽为 `<quarantine>/{key}.{task_id}`。以受锁保护的实际路径存在性及 `quarantine_path/quarantined_at` 判断代次。槽中副本和同 key 后来重新发布到正式路径的文件属于不同代次。只接受合法 key、规范 task UUID 和根内普通文件。对每个 key，任务槽不会被覆盖或回到正式名以外的任意路径。
- claim 提交关闭 → 取 StorageKeyLock → 在锁内重读引用、任务 fence、正式及对应槽。锁失败按 §4 退避。每个文件动作开始前重复 fencing、引用/状态前置，结束后短事务条件写回。围绕文件操作不持 DB 写事务。
- 恢复走 no-clobber 发布，以同 key Hash 验证正式和隔离源；没有可靠 Hash 或类型证据时转人工/报告。Windows 占用失败按 §5.3。释放锁不撤销已完成状态。

### 5.1 持锁观察到引用 > 0

| 正式路径 | 当前任务槽 / 其他可信槽 | 动作 |
|---|---|---|
| 有且 Hash 正确 | 无任务自有副本 | 当前任务 cancelled，其他任务按各自槽继续 |
| 有且 Hash 正确 | 当前槽有相同 Hash 副本 | 核对隔离时间；到期后复核正式副本仍有效，才可删除自有冗余副本并 cancelled；未到期等待 |
| 缺失 | 有经验证的自有或其他隔离副本 | no-clobber 复制/链接恢复并再次核对正式文件；不移动或删除他任务的槽；有自有冗余槽时按上一行处理 |
| 缺失或损坏 | 无有效副本、或已有正式路径内容冲突 | needs_manual，原样保全并报告 |

若参考其他任务或无任务槽，只用它作恢复来源并保留原槽。GC 自有副本删除前确认正式副本；禁止因有引用就 purge 唯一有效物理副本。恢复后如自有槽没有可靠隔离记录，按 §5.2 采纳并重新计时；等待时维持 running、租约置过期，next_retry_at 取最早安全时间。等待隔离到期期间，ORP 仍可优先恢复缺失的正式路径。

### 5.2 持锁观察到零引用

| 正式路径 | 当前任务槽及 DB 记录 | 动作 |
|---|---|---|
| 有 | 无槽、无隔离记录 | 复核正式 Hash、类型与 fencing 后无覆盖移动到本任务槽；记 path/time、租约置过期、维持 running、安排 +24h |
| 任意 | 有槽、缺可靠隔离记录 | 视为移动或 ORP 接管后未记录；验证槽后采纳，使用当前时间重新起算至少 24h。绝不把旧文件 mtime 当作隔离时点 |
| 任意 | 有槽、有可信时间 | 未满等待；满期再次核对任务/存储 lease、引用为零、时间和 Hash，仅 purge 本任务槽；POSIX 同步受影响目录 |
| 有 | 槽已无、存在对应隔离记录 | 视为旧代次已被处理（含 purge 后、状态提交前崩溃）。完成本任务后，由同一短 DB 事务确保后继或交给已有活跃任务；ORP 可兜底。保留当前正式代次直至另一轮持锁隔离并重新计时 |
| 无 | 无本任务槽 | 本任务 done；别的槽不归本任务删除，交对应任务或 ORP |
| 任意 | 槽 Hash/路径/时间信息冲突 | needs_manual 或保守等待；保留现场 |

- 若同一时刻有正式与当前槽，先完成该槽的旧代次，严禁覆盖、合并或顺手删正式代次。两个任务各有槽，任一任务不得当作另一任务已无文件或替其删槽。任务终态更新与后继入队可在同一短事务；失败后重跑仍由同一观察表决定。
- purge 只操作该槽，已有正式路径的隔离是不同动作。隔离文件优先用无覆盖的同卷原子移动；平台无该原语时可用 no-clobber hard link，再在锁内复核两端是同一文件并移除源。link 后崩溃形成双路径，按表中“双代次”分支保守处理，保留正式路径直到后继识别。两种原语均不可用就按存储错误重试或报告，禁止覆盖。物理空缺/可疑时不得通过删除 DB 引用掩盖。

### 5.3 Windows 占用

- 移动/删除遇到 `winerror 32/33`：100ms→1s、总 5s 重试；仍失败 → `failed_retryable`。
- 禁止强制关闭句柄、禁止 `del /f` 绕过、禁止把“占用”当永久失败（除非重试预算耗尽且明确不可恢复）。
- quarantine 目录与正式根同卷；跨卷不移动，直接失败并报告。

## 6. ORP 独立孤儿扫描

### 6.1 调度与领导权

- 间隔 300s；启动后安排首次轻量扫描、后台继续，可停止事件控制。单 Backend、单数据根、单 worker，沿用 ProcessLock；双 worker 用例只取证。生命周期结束时停止 worker 并释放专用连接，再释放 DB/OS 锁。
- PostgreSQL 每轮通过独立物理连接持扫描领导权，使用单 bigint 锁命名空间，详见 storage-and-lock-contract §4.3。取不到则跳过该轮；结束或异常都 unlock/物理关闭。SQLite 依赖既有单实例部署。

### 6.2 正式 blob 扫描

```text
for path in walk(storage_root), skip .tmp/_quarantine/dotdirs:
    key = parse 64hex filename; 非法 → 报告，不删
    expected = storage_root/<key[0:2]>/<key[2:4]>/<key>
    if path != expected: 报告 misplaced_blob，不删、不入队
    refs = count_references(key)
    if refs > 0: continue
    if mtime > now - 24h: continue          # 给上传/approve 留窗口
    ensure_gc_task(key, pending)            # 不直接删
```

- 不依赖 `attachment` 行是否存在；以 `count_references` 为准。
- mtime 在未来（时钟异常）→ 报告 `future_mtime`，不 enqueue。
- 扫描与上传并发：上传持 StorageKeyLock；ORP 只入队，GC 后续持锁复核。不会因扫描瞬间无引用就删除。
- `ensure_gc_task` 失败（DB 不可用）→ 本轮停止，记录错误，不删任何文件。

### 6.3 Quarantine 残留扫描

- 排除 `staging/`，只接受符合 key/UUID 命名规范的根内普通文件。不能验证类型、时间、Hash 或名称的残留仅报告。发布后损坏留下的 `<key>.<uuid>` 不能按名字当成有效副本，Hash 不符时保留现场。
- 先持 StorageKeyLock，再复核新鲜引用、正式路径、候选路径和任务归属。若被引用且正式缺失，验证可用候选后沿用 §5.1 no-clobber 恢复并保留隔离源，无需等待 purge。已存在且冲突则报告。
- 活跃任务的槽由任务接管，ORP 不替它清除。failed_permanent/needs_manual 保留，允许上述安全恢复，自动处置仍交运维。无任务或 done/cancelled 的可信残留，零引用时以既有 GC 入队机制建立唯一可确认的接收任务，保持同一个、已经获取的 StorageKeyLock，将其无覆盖移至接收任务的空槽；已有其他活跃任务或无法确认接收槽则保留并重查。接收任务直接创建 pending，原终态任务在此仅作来源证据，不阻止交接；同 key 存在人工态任务时保持现场。DB 先提交 pending 再移动，GC 可 claim 但在同一 key 锁外等待。移动前崩溃原槽可再识别，移动后崩溃按 §5.2 由新槽重新计时；此路径不直接 purge。已引用且正式 Hash 有效的无任务/终态副本可同样交接，随后按 §5.1 安全处理冗余。
- 接收任务只在来源槽和目标槽可明确区分并均已安全验证时使用；未知或损坏文件始终仅报告。ORP 如因 PG 会话中断而失去 guard，应重新进入扫描，不继续沿用旧的路径或 DB 决策。任务终态保持。出错重跑先重查实际两槽，绝不覆盖或删除另一代次。

### 6.4 Staging 清扫

1. 枚举合法 UUIDv4 的 staging 直接子目录与合法 quarantine/staging 直接子目录。排除根本身、链接/junction/越界与不可信路径。在 `staging_id` guard 内短查询全部 pending 引用，结束只读会话。普通 review 无 envelope 跳过；疑似导入 envelope/manifest 损坏（包括二次查询）则本轮 staging 操作 fail-closed，并报告。
2. 创建者在目录出现前已持同一 guard，覆盖活动写入、pending/Draft commit 和处置。approve/reject 正常清理也使用该 guard。扫描可在锁外挑选候选，拿不到 guard 跳过；决定移动前在锁内重新计算活动和 pending 归属。任何 pending 引用优先保留。
3. 活动取标记与普通文件 mtime 的最大值；只有确认合法 UUID 目录确实为空、无标记/文件且没有 pending，才用该目录自身 mtime 判断标记前半成品的宽限。读取失败或时间异常报告，不删除。宽限 24h。非空目录只依据标记/文件，根目录 mtime 永远不作正常活动依据。
4. 超宽限且无 pending，校验/Hash 扫描得到可用的正式 key 后按批次顺序取得相关 StorageKeyLock，随后短会话再次检查 pending、复核活动/路径/租约，关闭会话，才可将目录无覆盖移动到 `<quarantine>/staging/<staging_id>.<UTC隔离时刻>`。空目录靠 staging guard 即可。读取/Hash/锁失败保守报告。通过隔离路径记录隔离时间，弃用原 mtime 作为隔离起点。
5. 隔离目录的复核、移回和 purge 同样持 staging guard 与可确定的 storage guard。出现 pending 引用时优先恢复到原 staging 根，目标已存在则报告并保留两边；至少隔离 24h 且再次证明没有 pending、路径安全与 fence 有效才可删除。失败保留并等待重试。直接成功清理已有确认提交的单一所有者目录时无需等待，但必须先证明没有 pending 引用。

### 6.5 `.tmp` 临时文件

- ORP 的正式 blob 枚举**必须排除** `attachments/.tmp/`；临时文件不得被当作孤儿回收（ORP-02）。
- Batch B **不自动删除** `.tmp` 文件；只在一致性报告中记录数量/最旧 mtime，供后续批次或运维处理。
- 上传流程自身在成功/失败路径清理自己的临时文件；崩溃残留不交给 ORP 删除。
- 不得把 `.tmp` 内的文件计入 `formal_blobs`/`orphan_blobs`。

## 7. 一致性报告

每轮 ORP 生成：

```json
{
  "generated_at": "2026-11-22T12:00:00Z",
  "storage_root": "<redacted-absolute-path>",
  "counts": {
    "attachment_rows": 0,
    "referenced_keys": 0,
    "formal_blobs": 0,
    "orphan_blobs": 0,
    "missing_blobs": 0,
    "hash_mismatched": 0,
    "misplaced_blobs": 0,
    "quarantine_files": 0,
    "staging_dirs": 0,
    "staging_incomplete": 0,
    "pending_staging_refs": 0
  },
  "orphan_blobs": [{"storage_key": "...", "mtime": "..."}],
  "missing_blobs": [{"attachment_id": "...", "storage_key": "..."}],
  "hash_mismatched": [{"storage_key": "...", "actual_hash": "..."}],
  "misplaced_blobs": [{"storage_key": "...", "relative_path": "..."}],
  "temp_residual": {"count": 0, "oldest_mtime": null},
  "quarantine_residual": [],
  "staging_orphans": [],
  "malformed_manifests": [],
  "notes": []
}
```

- 写入 `ops/attachment-consistency-<UTC>.json`：临时文件 + flush/fsync + `os.replace`；失败只告警。这里的 `os.replace` 仅用于报告文件自身，不属于正式 blob 发布路径，不违反 §3 no-clobber 契约。
- 保留最近 30 份，按文件名时间清理更旧文件；不删除正在写的临时文件。
- 报告不包含文件内容、用户文件名、绝对密钥路径；`storage_root` 可脱敏为 `<data_dir>/attachments`。
- **报告不触发自动删 DB 行**；`missing_blobs` 只用于下载 503 与运维。
- 报告生成失败不得阻止应用运行，但要记录错误。

## 8. 启动恢复

应用启动顺序：

1. 校验/创建存储根、同卷、权限；失败拒绝启动。
2. 初始化 repositories、StorageKeyLock、GC/ORP worker。
3. 执行一次轻量恢复扫描：
   - 过期 `running` 任务不直接改状态（等 `claim` 接管）；
   - 不删除 `.tmp`；只报告残留；
   - quarantine/staging 残留只报告/按 §6 处理；staging 活动时间按 `.creating`/`.activity`/`.complete` 与普通文件计算，不使用根目录单一 mtime；
   - 不删除任何正式 blob。
4. 启动周期 worker（300s）。

- 启动恢复不得调用模型、不得阻塞 HTTP 就绪超过必要时间；扫描失败记录后继续，但不得静默关闭 worker。
- 若数据库中 `gc_task` 表不可用：应用可启动，但附件删除/GC 功能返回 `ATTACHMENT_MAINTENANCE_UNAVAILABLE`；不得假装成功。

## 9. 失败分类

| 错误 | 分类 | 处理 |
|---|---|---|
| 锁获取超时 | 可重试 | `failed_retryable`；按退避 |
| DB 暂时不可用 | 可重试 | 不触碰文件；下轮 |
| Windows 占用 | 可重试 | 短重试后 `failed_retryable` |
| 跨卷 `EXDEV` | 永久/配置错误 | `failed_permanent`；报告 |
| 路径解析失败/符号链接 | 永久/安全 | `needs_manual`；不删 |
| hash 不符/双重文件冲突 | 人工 | `needs_manual`；保留证据 |
| 任务 token 失配 | 中止 | 不写；由接管者处理 |
| 存储锁失配 | 中止 | 不写；由 ORP 处理 |
| 超过 8 次 | 永久 | `failed_permanent` |
| 未知异常 | 保守 | `needs_manual` 或 `failed_retryable`（仅确定瞬时） |

- 不得把“未知异常”当永久失败后删除；删除只发生在确定性成功路径。
- 不得把 `needs_manual` 自动重置为 `pending`；必须显式运维动作（O-B07）。

## 10. 观测与审计

- 日志字段：`event`, `gc_task_id`, `storage_key`, `status`, `attempts`, `lease_token`, `error_type`；不记录内容/文件名/路径。
- 每个状态迁移记录 `from -> to`、原因、owner；不记录密钥。
- 一致性报告作为验收证据；不提交 `backend/data/`（gitignore）。
- 不新增 HTTP 管理端点、不新增指标依赖。

## 11. 验收边界

- GC 七态、24h、8 次、退避、锁/fencing、ORP 300s、staging 清扫、报告均需真实 SQLite + 真实文件系统验证。
- PostgreSQL 需真实实例验证 advisory lock 与任务条件更新；**两个真实连接**覆盖“行 TTL 过期但 Advisory 仍存活不可接管”与断连接管（LCK-10）；不得用 SQLite 结果替代。
- Windows 需真实占用/重命名失败场景；不得只跑 Linux。
- staging 清扫需验证 `.creating`/`.activity`/`.complete` 与“pending 引用优先于 24h”；不得以根目录 mtime 判定。
- 所有验收初始状态为“待验证”；本设计不宣称已通过。
