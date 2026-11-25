# Filesystem and Lock Audit

## 1. 实际数据目录布局（盘点时）

```text
backend/data/
├─ .explainlab.process.lock      # 进程锁文件，永不删除
└─ explainlab.db                 # SQLite 主库
```

以下目录/文件**不存在**：

- `backend/data/source-instance-id`
- `backend/data/source-identity-journal.json`
- `backend/data/source-identity-journal.archive/`
- `backend/data/attachments/`
- `backend/data/import-staging/`（或任何 staging）
- `backend/data/_quarantine/`
- `backend/data/ops/`

`.gitignore` 包含 `data/`、`*.db`、`*.db-journal`；数据目录不入库。标签：已实现（忽略规则）。

说明：`source-instance-id` 与 Journal 在启动时生成；当前工作副本尚未启动过后端，因此文件不在磁盘上。这不代表功能缺失——代码路径存在。标签：已实现（代码）/需要真实运行验证（生成）。

## 2. 可复用的文件写入原语

### 2.1 `write_all`

`backend/app/services/file_write.py:20-31`：

- 循环 `os.write` 直到全部字节写完；
- `InterruptedError` 重试；
- 返回 0 → `OSError(EIO)`；
- 不负责 `fsync`、`close`、`rename`、权限、目录创建。

**可复用性：高。附件写临时文件可直接使用，但调用方必须自己 fsync + close + 发布。** 标签：已实现。

### 2.2 原子写入模式（现有两处范例）

**A. SourceInstanceIdStore（`source_instance_id.py`）**

- 临时文件：`.<name>.<uuid>.tmp`，`O_CREAT|O_EXCL`，mode 0600。
- `write_all` → `os.fsync(fd)` → `close`。
- 发布：优先 `os.link(tmp, target)` 实现 non-overwrite；目标已存在则读取既有值。
- 不支持硬链接时退回 `O_EXCL` 直接创建；写入/fsync 失败删除半成品。
- `replace` 用 `os.replace(tmp, target)` 原子替换。
- `_sync_dir` 在 POSIX 尽力 fsync 目录；Windows 直接返回（诚实声明不保证掉电持久性）。

**B. JournalStore（`source_identity.py:430-444`）**

- 临时文件同目录，0600；
- `write_all` → `fsync` → `close` → `os.replace`；
- 归档用 `os.link` / `O_EXCL` non-overwrite，并在目标已存在时比较内容，冲突则 `JOURNAL_CORRUPT`。

**这两处证明仓库已有“临时文件 + 完整写 + fsync + 原子发布 + non-overwrite”模式，可直接借鉴到附件落盘。** 标签：已实现。

### 2.3 缺口

| 能力 | 现状 | 标签 |
|---|---|---|
| 流式 sha256 计算 | 无通用工具 | 未实现 |
| 写入时同步计算 hash 并比对声明值 | 无 | 未实现 |
| 大文件分块读取/写入 | 无 | 未实现 |
| 文件大小上限（写前/写中） | 无 | 未实现 |
| 目录创建与权限统一 | 各模块自行 `mkdir` | 部分实现 |
| 跨卷检测（staging vs 正式区） | 无 | 未实现 |
| Windows 文件句柄/共享冲突处理 | 无 | 未实现 |
| 临时文件清理（启动时/超期） | 无 | 未实现 |
| 磁盘满/只读/权限错误的稳定码映射 | 无 | 未实现 |

## 3. 路径与 Windows 语义

### 3.1 现有代码的路径处理

- `Settings.data_dir` 是 `Path`，来自 `BACKEND_DIR / "data"`；测试可注入。
- `SourceInstanceIdStore` 直接 `Path(data_dir)`，不 `resolve()`。
- `ProcessLock` 用 `self.path.resolve()` 作为同进程注册表键。
- 没有统一的“数据目录必须为绝对路径/必须存在/必须可写”启动校验。

标签：部分实现。

### 3.2 附件路径必须遵守的边界

设计 §5.3 / §7.1：

```text
<storage_root>/<storage_key[:2]>/<storage_key>
```

必须由服务端根据 64 位十六进制 `storage_key` 拼接，**不得使用用户提供的 filename 作为路径**。需要防范：

| 风险 | Windows 具体表现 | 当前防护 | 标签 |
|---|---|---|---|
| `..` / 绝对路径 | `C:\...`、`\\server\share`、`/etc/...` | 无 | 未实现 |
| 盘符/UNC | `C:`、`\\?\`、`\\.\` | 无 | 未实现 |
| ADS（备用数据流） | `file.txt:evil` | 无 | 未实现 |
| 保留设备名 | `CON`、`PRN`、`AUX`、`NUL`、`COM1`…`LPT9` | 无 | 未实现 |
| 尾随点/空格 | `foo.`、`foo ` 被规范化 | 无 | 未实现 |
| 大小写不敏感 | `A` 与 `a` 同文件 | 无 | 未实现 |
| 符号链接/重解析点 | 目录可被替换为 junction | 无 | 未实现 |
| 长路径 | >260 字符需 `\\?\` 或长路径策略 | 无 | 未实现 |

**建议方向（需 ChatGPT 决策）：storage_key 严格 `^[0-9a-f]{64}$`；filename 仅作展示元数据，不参与路径；所有路径用 `Path.resolve()` 后校验 `is_relative_to(storage_root)`。** 标签：需要 ChatGPT 决策。

### 3.3 Windows 文件句柄

- Windows 上，打开的文件默认不允许 delete/rename；扫描/GC 若与下载并发，可能遇到 `PermissionError`（共享冲突）。
- 下载应使用 `FileResponse`/流式读取并及时关闭；GC 删除失败应视为可重试，而非永久失败。
- `os.replace` 在目标被占用时失败；`os.unlink` 在句柄未关时失败。
- 当前无任何附件下载/删除代码，因此无现成处理。

标签：未实现 / 需要真实测试验证（Windows）。

### 3.4 同卷约束

- `os.replace` / `os.link` 跨卷会 `EXDEV`。
- 设计把 staging 与正式区都放在 `data_dir` 下，默认同卷。
- 若未来允许配置不同根，必须启动时校验 `st_dev` 相同，或退化为 copy + fsync + 删除源。
- 当前无配置、无校验。

标签：未实现 / 需要 ChatGPT 决策。

## 4. 身份与 Journal 基础设施

### 4.1 `source-instance-id`

- 位置：`<data_dir>/source-instance-id`。
- 内容：规范小写 UUIDv4 + 单换行；禁止 BOM、前后空白、多行。
- `ensure()` 只在进程锁获取后调用；已存在则严格读取，不覆盖。
- 损坏 → `SOURCE_INSTANCE_ID_INVALID` / `SOURCE_INSTANCE_ID_UNAVAILABLE`，fail-closed。
- `replace()` 仅供 ROTATE/恢复。

**与附件的关系：不直接相关；但它是“身份 Journal”的一部分，Batch B 不得绕过。** 标签：已实现。

### 4.2 身份 Journal

- 当前文件：`source-identity-journal.json`；归档目录：`source-identity-journal.archive/`。
- schema v1：`operation_id`、`kind`（MATERIALIZE/ROTATE）、`phase`（PREPARED/COMMITTED）、materialization digest、identity audit digest、journal checksum。
- `identity_guard`（RLock）内做恢复：PREPARED 处理、COMMITTED 归档。
- `_origin_materialize_conflict` fail-closed。
- 恢复门在导入/审核前调用 `recover_if_needed()`。

**没有附件存储 Journal。** 附件 staging 是否需要独立 Journal、还是复用“文件系统 + DB 引用”即可，是设计决策。标签：需要 ChatGPT 决策。

### 4.3 可借鉴的纪律

- 写前校验、写后 digest、归档冲突检测、fail-closed、绝不猜测修复。
- 物理文件操作与 DB 事务分离，但通过“先写文件、后提交引用”保证不出现悬空引用。

标签：已实现（可借鉴）。

## 5. 隔离区、GC、孤儿扫描

| 能力 | 现状 | 标签 |
|---|---|---|
| 隔离区目录 | 无 | 未实现 |
| 隔离（quarantine）操作 | 无 | 未实现 |
| 隔离后宽限期清理 | 无 | 未实现 |
| GC worker/调度 | 无 | 未实现 |
| GC 任务认领/租约/fencing | 仅端口与 schema | 未实现 |
| 孤儿 blob 扫描 | 无 | 未实现 |
| staging 清扫 | 无 | 未实现 |
| 启动时崩溃恢复（临时文件/半成品） | 无 | 未实现 |
| 扫描与在线请求的互斥 | 无 | 未实现 |

**结论：物理存储生命周期完全空白。** 标签：未实现。

## 6. 锁体系盘点

| 锁 | 文件 | 作用 | 跨进程 | 可复用于附件？ | 标签 |
|---|---|---|---|---|---|
| 进程单实例锁 | `app/db/process_lock.py` | 阻止两个后端进程共用 data_dir | 是（OS 文件锁） | 可作为“单实例”前提，但不是细粒度锁 | 已实现 |
| ImportCoordinator | `app/services/import_coordinator.py` | 同身份/同条目导入串行 | 否（进程内） | 可复用同进程并发保护 | 已实现 |
| identity_guard | `app/services/source_identity.py` | 身份 Journal 恢复与物化串行 | 否（进程内 RLock） | approve 内可复用 | 已实现 |
| 链接重建写锁 | `app/db/locking.py` | A1-03 重建串行 | PG 是 / SQLite 部分 | **不可直接复用**（锁的是 knowledge_link） | 已实现（非本任务） |
| StorageKeyLock | 不存在 | 同 storage_key 上传/GC/删除互斥 | SQLite 表 / PG advisory | 需新建 | 未实现 |

### 6.1 进程锁事实

- 文件 `.explainlab.process.lock` 永不删除，避免 inode 替换竞态。
- Windows `msvcrt.locking`，POSIX `fcntl.flock`；非阻塞 + 有界退避（10s）。
- 同进程重复获取由注册表拒绝。
- 不做 PID 存活探测；OS 锁随进程退出释放。
- `main.py` 拒绝 `workers > 1`，因此“进程内锁”在当前部署下等价于“全局锁”。

标签：已实现。

### 6.2 StorageKeyLock 设计缺口

- 端口已有，但无 backend 实现。
- SQLite 需要 `storage_lock` 表的条件 UPDATE 实现租约；PG 需要 `pg_try_advisory_lock` / `pg_advisory_unlock`（64 位 key 由 storage_key 哈希）。
- 租约 TTL 60s、心跳 15s 来自 D-04，但配置未落地。
- 锁获取失败是返回 `None` 还是阻塞等待，端口未规定；上传 API 需要稳定码与重试策略。
- 多附件批准需按 storage_key 排序加锁，避免死锁；当前无代码。
- 锁与 DB 事务的边界：物理操作在事务外，锁必须覆盖“检查引用 → 物理操作 → 更新引用/任务”的完整窗口。

标签：未实现 / 需要 ChatGPT 决策。

## 7. 配置文件缺口

`app/core/config.py` 当前与附件相关的缺失：

| 配置 | 设计要求 | 现状 | 标签 |
|---|---|---|---|
| `attachment_storage_root` | `data_dir/attachments` | 无 | 未实现 |
| `attachment_staging_root` | `data_dir/import-staging` | 无 | 未实现 |
| `attachment_quarantine_root` | 同卷隔离区 | 无 | 未实现 |
| 最大附件大小 | 10 MiB（D-08） | 无 | 未实现 |
| MIME 白名单 | PNG/JPEG/GIF/WebP/PDF/TXT/MD/CSV（D-08） | 无 | 未实现 |
| SVG 策略 | 拒绝（D-08） | 无 | 未实现 |
| 租约 TTL / 心跳 | 60s / 15s（D-04） | 无 | 未实现 |
| GC 最大尝试 / 退避 | 8 次；60s→6h（D-04） | 无 | 未实现 |
| 隔离/孤儿宽限 | 24h（D-04） | 无 | 未实现 |
| 扫描周期 | 300s（D-04） | 无 | 未实现 |
| staging 清扫宽限 | §20.6 未给数值 | 无 | 需要 ChatGPT 决策 |

## 8. 需要真实测试验证

- Windows 上临时文件 → `os.replace` 原子性、目标被占用时的失败行为。标签：需要真实测试验证。
- 硬链接在目标文件系统是否可用；`EXDEV` 分支。标签：需要真实测试验证。
- 路径穿越/保留名/ADS/UNC 在 Windows 的真实拒绝。标签：需要真实测试验证。
- 10 MiB 边界、磁盘满、只读目录。标签：需要真实测试验证。
- 两个 worker/两个进程同时上传同一 storage_key。标签：需要真实测试验证。
- GC 与下载并发（Windows 句柄冲突）。标签：需要真实测试验证。
- 崩溃点注入：写临时文件后、rename 后、commit 前、commit 后。标签：需要真实测试验证。
- staging 清扫不误删 pending 审核单仍在引用的文件。标签：需要真实测试验证。

## 9. 结论

**文件写入原语和原子发布模式已经具备，且质量纪律（fsync、non-overwrite、fail-closed）可复用；但附件存储层、路径安全、staging、隔离区、GC、孤儿扫描、StorageKeyLock 全部不存在。Batch B 的文件系统工作不是“补几个函数”，而是一整层需要真实故障注入验收的实现。** 标签：部分实现（原语）/未实现（附件层）。