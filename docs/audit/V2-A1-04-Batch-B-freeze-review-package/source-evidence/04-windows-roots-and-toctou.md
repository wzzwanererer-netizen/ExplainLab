# Windows 根目录、目录身份及 TOCTOU 边界

## 状态

基线只能证明普通 data_dir、OS 锁及身份文件的防护先例。声明中的 Attachment Storage/Staging 根规范化、实际目录身份、组件级拒绝 junction/符号链接、同卷、运行期复核与同句柄下载是 Batch B 要求。外部可写进程并发替换目录或原地改写文件仍在记录的边界内；未运行 NTFS/POSIX、真实跨卷或 TOCTOU 竞态用例。

## 对应基线源码

[打开带原始行号的源码索引](README.md)

- `backend/app/core/config.py`：40–52，既有 data_dir。
- `backend/app/main.py`：65–106，创建 data_dir 与 ProcessLock。
- `backend/app/db/process_lock.py`：75–104、125–154，Windows OS 锁。
- `backend/app/services/source_identity.py`：113–126、463–549，身份 Journal 同卷归档和同步。
- `backend/app/services/source_instance_id.py`：53–68，既有目录同步差异。
- `backend/app/services/file_write.py`：20 起，完整写入循环。

## 当前候选设计原文（限定章节）

完整设计文件见 `design-documents/`。行号对应打包时源文件。

### storage-and-lock-contract.md · §1 真实路径、目录身份、同卷、junction 与根隔离（5–31）

~~~text
   5: ## 1. 根目录与同卷约束
   6: 
   7: ```text
   8: <data_dir>/
   9: ├─ attachments/                    # 正式内容寻址根（attachment_storage_root）
  10: │  ├─ <k0k1>/<k2k3>/<64hex>        # 正式 blob
  11: │  ├─ .tmp/<uuid>.part             # 同卷临时文件
  12: │  └─ _quarantine/
  13: │     ├─ <64hex>.<gc_task_id>      # 正式 blob 隔离
  14: │     └─ staging/<staging_id>.<ts> # 整个 staging 目录隔离
  15: ├─ import-staging/                 # staging 根
  16: │  └─ <staging_id>/
  17: │     ├─ .creating                 # 创建标记
  18: │     ├─ .activity                 # 最近活动标记（服务端刷新）
  19: │     ├─ .complete                 # 完成标记（JSON 元数据）
  20: │     ├─ blobs/000001.bin
  21: │     └─ blobs/000002.bin
  22: └─ ops/
  23:    └─ attachment-consistency-<utc>.json
  24: ```
  25: 
  26: - 解析根的真实绝对路径，比较规范路径、目录身份和祖先关系。Windows 比较遵循卷与文件系统大小写规则。正式根和 staging 根必须是 `data_dir` 内互不相等、互不包含的专用目录；均不得等于或覆盖数据根、DB 文件/专用目录、身份 Journal、身份归档、source-instance-id 或 `ops` 路径。共享的 `data_dir` 只是父目录。
  27: - 正式根内只允许明确分区：固定保留子目录 `.tmp`、默认 `_quarantine`（如配置则必须是正式根内独立专用直接子目录，名称不得落入分片命名空间），以及 quarantine 下的固定 `staging/`。正式枚举按实际保留子树排除，不能只匹配默认字符串。staging 根仅枚举合法小写 UUIDv4 直接子目录，正式根仅按标准 shards 枚举 64hex 普通文件。
  28: - 启动逐组件拒绝符号链接、junction/重解析点、非目录根及路径别名。正式根、staging、`.tmp`、quarantine 及实际操作源/目标父目录均须同卷。创建路径后复核，运行期每次枚举/打开/移动/删除前检查实际类型、根内与同卷，使用平台能提供的拒绝跟随机制。可疑子树只报告，删除前不递归跟随链接；绝不移动整个根。运行中 `EXDEV` 保留源并返回既有跨卷错误。
  29: - 目录由服务端生成，权限尽力 `0700`；磁盘名不使用用户文件名。目录创建或根校验失败拒绝启动。Windows 长路径告警保留。外部进程拥有写权限并并发替换目录仍需由本地部署权限保护，验收覆盖已存在或操作前发现的重解析路径。
  30: - Staging 标记和活动时间按 attachment-lifecycle §3、GC/ORP §6.4。文件 mtime 是活动证据，空目录只走显式半成品分支。
  31: 
~~~

### storage-and-lock-contract.md · §3 no-clobber 与崩溃窗口（56–103）

~~~text
  56: ## 3. 正式 blob 发布（no-clobber）
  57: 
  58: ### 3.1 写入步骤（上传 / promote / 导入共用）
  59: 
  60: **前置：临时文件可在锁外预先准备；`publish_no_clobber` 调用时调用方必须已成功 `acquire(StorageKeyLock)`。本函数不自行加锁、不重入。** 发布、复制、重读 Hash 和 fsync 均在业务写事务之外。调用方随后在持 guard 状态下完成业务提交。
  61: 
  62: ```text
  63: 1. 校验 key：^[0-9a-f]{64}$
  64: 2. 准备临时文件 attachments/.tmp/<uuid>.part（同卷，可在锁外）：
  65:    open('xb') → write_all → flush → os.fsync(fd) → close
  66: 3. 重新读取临时文件计算 SHA-256，必须等于 key；否则删除临时文件并报错
  67: 4. 调用方 acquire(key)；成功后才调用 publish_no_clobber；未持锁 → 编程错误
  68: 5. 若正式路径已存在：
  69:      a. 校验 size + SHA-256
  70:      b. 相同 → 删除临时文件，复用现有 blob，成功
  71:      c. 不同 → 不覆盖；删除临时文件；ATTACHMENT_KEY_COLLISION
  72: 6. 正式路径不存在：
  73:      a. 首选 os.link(temp, final)（同卷、no-clobber、原子可见）
  74:      b. FileExistsError → 回到 5
  75:      c. 文件系统不支持 hard link：
  76:         - Windows：os.rename(temp, final)（目标已存在则失败，回到 5；不覆盖）
  77:         - POSIX：不得用覆盖式 rename；返回 ATTACHMENT_STORAGE_UNAVAILABLE / ATTACHMENT_WRITE_FAILED
  78:         发布后仍须校验；不得把该路径说成对外部进程完全免疫
  79: 7. 发布后重新校验 final 的 size + SHA-256：
  80:      不匹配 → 持锁复核是本次发布路径，尽力隔离到 quarantine；ATTACHMENT_WRITE_CORRUPTED；若隔离也失败，保留现场并报告，不提交引用
  81: 8. POSIX 同步受影响的父目录，首次创建分片时同步新增目录项所在各级父目录；Windows 跳过目录 fsync
  82: 9. 删除残留临时文件（若 link 成功）
  83: 10. 由调用方在锁内完成 DB 写入（upload/approve）或状态更新（GC），再 release
  84: ```
  85: 
  86: ### 3.2 不允许
  87: 
  88: - 不允许 `open(final, 'wb')` 直接写正式路径。
  89: - 不允许在正式路径存在且 hash 不同的时候 `os.replace` 覆盖。
  90: - 不允许先删正式 blob 再发布新内容。
  91: - 不允许把 `_quarantine` 中的文件直接 rename 回正式路径而不校验 hash/锁/引用。
  92: - 不允许把 `os.replace` 当作 no-clobber 降级；Windows 的无 hard link 降级只能使用“目标存在即失败”的 `os.rename`。
  93: 
  94: ### 3.3 崩溃窗口
  95: 
  96: | 崩溃点 | 残留 | 收敛 |
  97: |---|---|---|
  98: | 临时文件写完、未发布 | `.tmp/*.part` | 上传自身清理；崩溃残留 Batch B **只报告不自动删**（ORP-02） |
  99: | link/rename 成功、DB 未写 | 正式 blob 无引用 | ORP 观察零引用且 mtime 满 24h 后入 GC |
 100: | DB 已写、响应未返回 | 正常引用 | 客户端重试命中 `(item_id, key)` 去重 |
 101: | 发布后校验失败 | quarantine 文件 | ORP 按引用/隔离状态恢复或报告 |
 102: | approve ① 失败 | 正式 blob 无引用 | ORP 观察零引用且 mtime 满 24h 后入 GC；**不回滚已发布文件** |
 103: 
~~~

### storage-and-lock-contract.md · §5–6 同句柄与 Windows 语义（181–202）

~~~text
 181: ## 5. 读取与下载
 182: 
 183: - 读取路径由 `storage_key` 计算；先校验 64 hex，再拼接；禁止任何用户输入进入路径。
 184: - **必须只打开正式 blob 一次**：用同一个已打开文件句柄完成 size 校验与流式 SHA-256 计算；校验通过后 `seek(0)`，继续从**同一句柄**流式输出。禁止校验后按路径重新打开、禁止使用会重新 open 路径的 `FileResponse`。打开后即使路径被 rename/替换，句柄仍指向已校验内容；外部进程原地改写仍属残余风险，不得宣称完全消除。
 185: - 打开文件后校验 `size` 与 DB 一致；并以流式分块重算 SHA-256（不整体读入内存），与 `storage_key` 不符返回 `ATTACHMENT_BLOB_CORRUPTED`（503），不返回部分内容。校验通过后再流式输出；不得边发边发现 hash 错误。
 186: - 下载使用流式响应；不要一次读入内存（10 MiB 上限虽小，仍按流式实现）。
 187: - 文件不存在：`ATTACHMENT_BLOB_MISSING`（503），不自动重建、不自动删除 DB 行。
 188: - 流拥有已打开的句柄，正常结束、异常、客户端取消或校验未通过均释放。Windows 的真实占用可能阻止替换，以该结果与同句柄断言分别取证。
 189: - 读取不加 StorageKeyLock；GC 隔离可能造成瞬时 `FileNotFoundError`，按 503 返回并由客户端重试。GC 必须先确认引用为 0 才会隔离，正常引用不应被隔离。
 190: 
 191: ## 6. Windows 文件系统契约
 192: 
 193: - **文件占用**：`PermissionError`/`OSError` 的 `winerror` 32（sharing violation）、33（lock violation）视为可重试；使用 100ms 起、上限 1s、总预算 5s 的重试；仍失败 → `failed_retryable` 或 `ATTACHMENT_WRITE_BUSY`，不强制删除、不关闭他人句柄。
 194: - **原子替换**：Windows 同卷 `os.rename` 在目标不存在时原子发布，目标存在则失败（no-clobber）；本契约禁止使用会覆盖目标的 `os.replace` 发布不同内容。无 hard link 时仅允许该 no-clobber rename 降级。
 195: - **hard link**：NTFS 支持；FAT/exFAT/网络盘可能不支持。`OSError` 视为“不支持”；Windows 走 no-clobber `os.rename` 降级，POSIX 直接失败（不覆盖）。不得把降级说成完全原子发布。
 196: - **路径**：统一 `pathlib.Path` + 绝对路径；禁止 `\\?\` 手工拼接；用户文件名**不得**进入任何路径（只做清洗后的展示名）；拒绝包含 `..`、盘符、UNC、ADS（`:`）的**路径输入**。文件名只用于 `Content-Disposition`，并清洗 CR/LF/引号/分隔符。
 197: - **大小写**：key 一律小写；在大小写不敏感文件系统上按小写路径访问。
 198: - **跨卷**：启动即拒绝；运行中发现 `EXDEV` → `ATTACHMENT_STORAGE_CROSS_VOLUME`（503），不得先删源。
 199: - **杀毒/索引器**：可能瞬时占用新文件；发布后校验失败先重试读取，再判定损坏。
 200: - **长路径**：启动检查根路径长度；超过 240 字符告警；不静默截断。
 201: - **fsync**：Windows 无目录 fsync；文件 flush+fsync 仍执行。不要声称 Windows 具备 POSIX 目录持久化语义。
 202: 
~~~

### architecture.md · §5 启动校验（108–117）

~~~text
 108: 
 109: staging 元数据文件名（服务端固定，不是配置项）：`.creating`、`.activity`、`.complete`。它们只存在于 `import-staging/<staging_id>/`，不进入正式 key 枚举。
 110: 
 111: 启动校验（fail-fast）：
 112: 
 113: - 根目录不存在则创建；创建失败 → 应用启动失败（不降级到内存/临时目录）。
 114: - 启动与运行期均按 storage-and-lock-contract §1 校验真实目录、同卷、非重叠、专用分区及链接/重解析点。
 115: - 根目录不得位于仓库跟踪目录；默认在 gitignore 的 `backend/data/` 下。
 116: - 路径必须是绝对路径或相对 `data_dir` 解析后的绝对路径；禁止 `..` 逃逸。
 117: 
~~~
