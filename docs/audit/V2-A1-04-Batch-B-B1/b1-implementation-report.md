# B1 实施报告（V2 A1-04 Batch B）

- 基线提交：`970c0d8ec05f0b8c68286839a56b14c74ea230c6`
- 分支：`fix/m0-admission-and-m5-regressions`
- 实施日期：2026-11-23（北京时间）
- 范围：仅 B1-T01 → T04；未进入 B2，未改 `MILESTONES.md`，未提交、未推送。
- 设计基线：`docs/plans/V2-A1-04-Batch-B/` 十份冻结文档（SHA-256 已核对通过）。

## 1. 结论摘要

B1 四个任务的**代码与 SQLite/真实 Windows 文件系统验证已完成**；真实 PostgreSQL 因本机无实例且 `EXPLAINLAB_PG_TEST_URL` 未配置而**阻塞/未验证**，POSIX 真机证据与进程 kill 类用例**未验证**。因此 B1 不能宣称“验收通过”，只能交付实现 + 已有真实证据，等待独立审计。

| 任务 | 实现状态 | 真实证据 | 判定 |
|---|---|---|---|
| B1-T01 配置与存储根启动校验 | 完成 | SQLite 临时库 + 真实 Windows 目录/junction | 已验证（Windows）；POSIX 未验证 |
| B1-T02 内容寻址/原子发布/F12 | 完成 | 真实 Windows 文件系统 + 真实占用 | 已验证（Windows）；POSIX/真实跨卷未验证 |
| B1-T03 StorageKeyLock | 完成 | 真实 SQLite 文件库并发 | SQLite 已验证；PG 未验证/阻塞 |
| B1-T04 Attachment/GcTask Repository | 完成 | 真实 SQLite 文件库并发/回滚 | SQLite 已验证；PG 未验证/阻塞 |

## 2. 实际修改文件与原因

| 文件 | 类型 | 原因 |
|---|---|---|
| `backend/app/core/config.py` | 修改 | 冻结配置字段/默认值；根路径规范化、`..`/越界/重叠/quarantine 直接子目录校验 |
| `backend/app/main.py` | 修改 | lifespan 启动期 fail-fast 校验存储根并写入 `app.state`；按方言装配 `storage_key_lock` |
| `backend/app/services/attachment_storage.py` | 新增 | 存储布局、SHA-256、临时写入、no-clobber 发布、F12 分类、同句柄读取、quarantine 移动/恢复/删除、Windows 占用重试 |
| `backend/app/db/storage_lock.py` | 新增 | SQLite 租约锁与 PostgreSQL advisory 锁、批 guard、心跳、末次 fencing、方言装配 |
| `backend/app/services/repositories_v2.py` | 修改 | 追加 `SQLAlchemyAttachmentRepository`（七个端口方法）与 `SQLAlchemyGcTaskRepository`（save/get/list/claim/update） |
| `backend/tests/test_attachment_storage.py` | 新增 | T01/T02 单元与故障注入测试（真实 SQLite + 临时文件系统） |
| `backend/tests/test_attachment_windows.py` | 新增 | Windows 真机专项：占用重试、rename 不覆盖、junction 拒绝、命名空间/错误分类 |
| `backend/tests/test_storage_lock_sqlite.py` | 新增 | LCK-01…09 的 SQLite 行为与并发 |
| `backend/tests/test_storage_lock_pg.py` | 新增 | LCK-10 等真实 PG 测试（门控，未运行） |
| `backend/tests/test_attachment_gc.py` | 新增 | ATT-08/11、GC-01/02/09/10/12 的仓库层验证（真实 SQLite） |
| `backend/tests/test_attachment_pg.py` | 新增 | 附件/GC 仓储真实 PG 测试（门控，未运行） |

未修改：`knowledge-core`（Core/端口/实体）、A1-02 Hash、A1-03、Batch A 冻结实现、迁移、依赖、前端、`MILESTONES.md`。

## 3. 关键实现口径

### 3.1 配置与启动（T01）

- 新增字段：`attachment_storage_root`、`attachment_staging_root`、`attachment_quarantine_dir`、`attachment_max_bytes=10485760`、MIME 白名单、导入 100/100 MiB、staging 宽限 86400s、锁 TTL 60/心跳 15/等待 10、GC 8 次/退避 60…21600、隔离 86400s、ORP 300s。
- 派生规则：根默认 `<data_dir>/attachments`、`<data_dir>/import-staging`、`<storage>/_quarantine`；显式相对路径按 `data_dir` 解析；禁止 `..`、越出 `data_dir`、与 `data_dir` 相同、storage/staging 重叠、quarantine 非 storage 直接子目录或占用保留名。
- lifespan 在 ProcessLock 之后、任何导入/身份写之前创建并校验真实目录：逐组件拒绝符号链接/junction/重解析点、拒绝与 DB 文件重叠、`st_dev` 同卷；失败抛 `StorageRootError` 拒绝启动；成功写入 `app.state.attachment_storage`。

### 3.2 存储（T02）

- `content_hash = SHA-256(实际字节)`，`storage_key = content_hash`，小写 64 hex；分片 `<k0k1>/<k2k3>/<key>`。
- 临时文件 `.tmp/<uuid>.part`：`xb` 独占创建、完整写、flush + `fsync`。
- 发布前重算临时文件 hash；目标已存在 → 重新校验 size/hash 复用或 `ATTACHMENT_KEY_COLLISION`；绝不覆盖。
- 优先 `os.link` 原子 no-clobber；仅 Windows 且明确“不支持硬链接”时降级为同卷 `os.rename`（目标存在即失败）；POSIX 硬链接失败不降级。
- F12 分类独立：目标已存在、跨卷、Windows 32/33 有界重试（100ms→1s，总 5s）、权限拒绝、明确不支持、未知 I/O。
- 读取只 `open` 一次，同一句柄完成 size/hash 校验、`seek(0)` 后交给调用方；不走 `FileResponse` 重新按路径打开。
- quarantine：`<quarantine>/<key>.<task_id>` 无覆盖移动；恢复校验 hash 且保留隔离源；删除带 Windows 占用重试。

### 3.3 锁（T03）

- SQLite：短事务条件 `UPDATE`（pending/过期接管）+ `INSERT` 竞争；`lease_token` 单调；续租/校验要求 owner+token+未过期；释放只清 owner、不删除行；busy 视为瞬时竞争。
- PG：每个 guard 一个 `NullPool` 专用物理连接；advisory 身份取前 16 hex 转两个有符号 int32，去重排序；完整 key 经 UPSERT 写单调 token 行；行 TTL 过期不授权接管；释放在行条件更新后逆序 unlock 并物理关闭。
- 批 guard：key 去重排序、最多 100、共享 10s 预算、部分失败逆序退还、非重入、心跳 15s、幂等释放、`verify_all(session)` 末次 fencing。

### 3.4 仓储（T04）

- `AttachmentRepository` 七方法全部实现；`list_storage_keys` 用 DISTINCT；`count_references` 用 `COUNT`（现有 `ix_attachment_storage_key`）。
- `GcTaskRepository`：`claim` 仅 pending 或“running 且租约过期”，同时要求 `next_retry_at` 到期且 `attempts < max_attempts`，token/attempts +1；`update_task` 要求 token 匹配且当前状态非 done/cancelled/failed_permanent；不改 attempts/lease_token。
- 所有方法只 `flush`，不 `commit`；外层 Unit of Work 独占提交/回滚。

## 4. 契约核对

- 依赖方向未变：新增代码仅位于 `backend`；Core 未改。
- 无新迁移/表/列/索引；复用 `0006`。
- 无新依赖。
- Repository 无隐式提交（代码检索无 `.commit()`）。
- 不宣称“物理 + DB 原子”、不宣称 TOCTOU 消除、不宣称 PG/Windows 已验证而实际未跑。