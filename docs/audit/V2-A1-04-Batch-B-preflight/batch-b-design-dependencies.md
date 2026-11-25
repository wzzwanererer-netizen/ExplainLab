# Batch B Design Dependencies

## 1. 权威文本与优先级

| 文本 | 作用 | 标签 |
|---|---|---|
| `docs/plans/V2-A1-04-implementation-plan.md` §5.3、§5.4、§7、§16、§19.3–§19.5、§20.6、§21.2、§21.5 | Batch B 数据流、状态机、任务分解、事务边界、禁改清单 | 已实现（设计文件存在） |
| `docs/plans/V2-A1-04-acceptance-matrix.md` §B | ATT/LCK/GC/ORP/BAK 验收规格 | 已实现（设计文件存在） |
| `docs/plans/V2-A1-04-open-decisions.md` D-04、D-08、§J.3、§L.2 | 参数、MIME/大小、沿用决策、稳定码 | 已实现（设计文件存在） |
| 真实代码 `970c0d8` | 唯一实现事实来源 | 已实现 |

冲突处理：R1.3 §21 与 §22 > R1.2 §21 > R1.1 §20 > R1 §19 > 早期章节。§21.2 明确 Batch B 独立出口，**不得用 Batch A 通过代替**。

## 2. Batch B 范围（设计原文归纳）

§21.2：

> 附件上传/下载、staging、**approve 附件整合**、StorageKeyLock、GC、quarantine、孤儿扫描。完成**附件 + Active approve 的完整事务闭环**：附件引用、item、tags、origin、links 同一事务提交/回滚；approve 前不得留下正式引用悬空。

独立出口：

- ATT/LCK/GC/ORP 全部；
- IMP-19；
- R1-IMP 附件/staging 部分；
- R1.1-IMP-38 附件整合、41/42。

明确**不属于 Batch B**：BAK（Batch C）、网络边界/运维 API/全量交付（Batch D）、A1-05 proposal/withdraw。

标签：部分实现（设计已定义，代码未实现）。

## 3. 设计与真实代码逐项对照

### 3.1 附件上传（§5.3）

| 设计步骤 | 真实代码 | 差距 | 标签 |
|---|---|---|---|
| `POST /knowledge/{id}/attachments` | 无路由 | 需新建 `api/routes/attachments.py` | 未实现 |
| 大小 ≤ 上限 | 无配置、无校验 | 需 config + 流式计数 | 未实现 |
| MIME 白名单 + magic bytes 双校验 | 无 | 需 stdlib 签名表 + 文本 UTF-8 校验 | 未实现 |
| SVG 拒绝（D-08） | 无 | 需显式拒绝 | 未实现 |
| 文件名清洗（仅显示名） | 无 | 需清洗/保留名/控制字符处理 | 未实现 |
| 读字节 → sha256 → storage_key | 无 | 需流式 hash（避免整文件入内存） | 未实现 |
| `StorageKeyLock.acquire` | 端口存在，无实现 | 需 T4-03 | 未实现 |
| 持锁写 temp → 原子 rename 到分片目录 | `write_all` 可复用；无附件写 | 需新服务 | 未实现 |
| 同内容已存在 → 跳过物理写 | 无 | 需先查正式路径/DB | 未实现 |
| 先物理后插 DB | 无 | 需严格顺序 | 未实现 |
| 短事务插 attachment 引用 | 无仓库 | 需 `SQLAlchemyAttachmentRepository` | 未实现 |
| DB 失败 → 孤儿 → 扫描回收 | 无扫描 | 需 T4-09 | 未实现 |
| 物理失败 → 不插 DB | 无 | 需异常映射 | 未实现 |
| fencing release | 端口存在，无实现 | 需 owner+token 校验 | 未实现 |
| 路径穿越防护 | 无 | 需 storage_key 严格格式 + resolve 校验 | 未实现 |

### 3.2 下载与删除（§5.4 / ATT-07/08）

| 设计 | 真实代码 | 差距 | 标签 |
|---|---|---|---|
| `GET /attachments/{id}` 按 id 查 storage_key | 无 | 需路由 + 仓库 | 未实现 |
| 短打开返回字节，不接受用户路径 | 无 | 需安全路径拼接 | 未实现 |
| `DELETE /attachments/{id}` 只删引用行 | 无 | 需路由 + 仓库 | 未实现 |
| COUNT==0 → enqueue `gc_task(pending)` | 无 | 需同事务写入 | 未实现 |
| 删除不删物理 | 无 | 需纪律 + 测试 | 未实现 |

### 3.3 Active approve 附件整合（§19.3/§19.4 / §21.2）

| 设计 | 真实代码 | 差距 | 标签 |
|---|---|---|---|
| envelope 必须携带 attachment staging manifest | `ImportEnvelope.attachments` 字段存在，但 backend 固定 `[]` | 需定义 manifest 元素 schema 并填充 | 部分实现 |
| pending 期间不创建正式 Attachment 引用 | 当前完全不处理附件 | 需 staging 服务 | 未实现 |
| approve 时提升/复用正式 blob | 无 | 需提升逻辑 | 未实现 |
| 附件引用与 item/tags/origin/links 同一事务 | 钩子已有同事务位置；无附件引用 | 需插入到 `apply_approved` 内、事务① commit 前 | 未实现 |
| 任一 hook 异常 rollback 全部 | 已有路由级 rollback | 可复用；需保证 staging 不被误删 | 已实现（框架）/需扩展 |
| reject 后清理 staging | `apply_rejected` 空操作 | 需 commit 后清理 | 未实现 |
| approve 前不得留下正式引用悬空 | 无附件引用 | 需“先文件后 DB 引用” | 未实现 |
| 同 hash pending 复用 / 不同 hash 拒绝 | Batch A 已有 pending 复用/拒绝语义 | 需确认附件 manifest 是否参与 hash 判定 | 需要 ChatGPT 决策 |

### 3.4 StorageKeyLock（§7.4 / §19.5 / D-04）

| 设计 | 真实代码 | 差距 | 标签 |
|---|---|---|---|
| SQLite 逻辑租约表条件 UPDATE | `storage_lock` 表存在 | 需 `db/storage_lock.py` | 未实现 |
| PG 64-bit advisory lock | 无 | 需真实 PG 实现 | 未实现 |
| lease_token 单调 | 表字段存在 | 需条件 UPDATE `token=token+1` | 未实现 |
| owner+token fencing | 端口契约存在 | 需实现 | 未实现 |
| TTL 60s / heartbeat 15s / wait 10s | 无配置 | 需 config | 未实现 |
| 同进程 keyed lock | `ImportCoordinator` 可借鉴 | 需独立 storage keyed lock | 部分实现 |
| 每不可逆步骤前 verify | 无 | 需 GC/扫描实现 | 未实现 |
| 诚实 TOCTOU 声明 | ports docstring 已声明 | 验收需记录 | 已实现（文字） |

### 3.5 GC 与 quarantine（§7.2/§7.3 / §5.4）

| 设计 | 真实代码 | 差距 | 标签 |
|---|---|---|---|
| 7 态状态机 | `GcStatus` 已定义 | 无 worker | 部分实现 |
| 原子认领（PG SKIP LOCKED / SQLite 条件 UPDATE） | 端口契约存在 | 需仓库实现 | 未实现 |
| 持锁重算 COUNT | 无 | 需 worker | 未实现 |
| COUNT>0 → cancelled | 无 | 需 worker | 未实现 |
| COUNT==0 → 持锁 quarantine | 无 | 需 FS 层 | 未实现 |
| 释放锁后只 purge 隔离区 | 无 | 需 worker | 未实现 |
| 等待期后再次持锁复核 | 无 | 需 worker | 未实现 |
| 引用回升恢复 | 无 | 需 worker | 未实现 |
| 崩溃恢复 | 无 | 需扫描 + DB 状态 | 未实现 |
| 退避/死信 | 无 | 需调度 | 未实现 |
| 24h 等待、8 次重试、300s 扫描 | 无配置 | 需 config | 未实现 |

### 3.6 孤儿扫描（§7.5 / ORP）

| 设计 | 真实代码 | 差距 | 标签 |
|---|---|---|---|
| 周期扫物理 + 隔离区 | 无 | 需 worker/调度 | 未实现 |
| 对照 `list_storage_keys` | 端口存在 | 需实现 | 未实现 |
| 排除临时文件/并发上传 | 无 | 需命名约定 + keyed lock | 未实现 |
| 超宽限期才处理 | 无 | 需 mtime 判定 | 未实现 |
| 持锁复核==0 + fencing | 无 | 需实现 | 未实现 |
| DB 有引用但原始缺失 → 从隔离区恢复 | 无 | 需实现 | 未实现 |
| DB↔物理一致性报告 | 无 | 需报告 | 未实现 |

### 3.7 staging sweep（§19.4 / §20.6）

| 设计 | 真实代码 | 差距 | 标签 |
|---|---|---|---|
| `import-staging/<review_id>/<operation_id>/` | 无目录 | 需约定 | 未实现 |
| 只清理无 PENDING 引用且超宽限期的目录 | 无 | 需扫描器 | 未实现 |
| 按 review_id + envelope manifest 文件清单检查 | 无 | 需解析 pending payload | 未实现 |
| 复核后 quarantine → purge | 无 | 需复用 GC 原语 | 未实现 |
| 正式 attachments 根绝不 sweep | 无 | 需路径隔离 | 未实现 |

## 4. 任务依赖（按 §16.1 映射到 Batch B）

| 设计任务 | Batch B 归属 | 当前状态 | 依赖 | 标签 |
|---|---|---|---|---|
| T4-01 配置 + 存储根/装配骨架 | 是 | 仅 `data_dir`/`import_lock_wait_seconds`；附件配置缺失 | — | 部分实现 |
| T4-02 V2 仓库（Attachment/GcTask/Tag/TagChangeLog/ImportOrigin） | 是（Attachment/GcTask 部分） | Tag/TagChangeLog/ImportOrigin 已实现；Attachment/GcTask 未实现 | T4-01 | 部分实现 |
| T4-03 `db/storage_lock.py` 双方言 | 是 | 不存在 | T4-01 | 未实现 |
| T4-07 `services/attachments.py` | 是 | 不存在 | T4-02/T4-03 | 未实现 |
| T4-08 GC worker | 是 | 不存在 | T4-03/T4-07 | 未实现 |
| T4-09 独立孤儿扫描 | 是 | 不存在 | T4-08 | 未实现 |
| T4-10 API 附件路由/DTO + approve 整合 | 是（附件部分） | 无附件路由；approve 钩子拒绝附件 | T4-06/T4-07 | 未实现 |
| T4-06 导入/审核钩子 | 仅“附件整合”部分 | Batch A 非附件已实现 | T4-04/T4-05 | 部分实现 |
| T4-16 全量回归 | Batch B 独立出口 | 未执行 | 全部 | 未实现 |

**实施顺序建议（与 §16.3 一致）：**

```text
T4-01 配置/目录骨架
→ T4-02 Attachment/GcTask 仓库 + T4-03 StorageKeyLock（可并行）
→ T4-07 附件上传/下载/删除/校验
→ staging manifest + approve 整合（T4-10 + T4-06 附件部分）
→ T4-08 GC（认领/状态机/quarantine/purge）
→ T4-09 孤儿扫描 + 一致性报告
→ Batch B 真实 FS/PG/并发/故障注入验收
```

GC 与 approve 整合的先后可讨论：没有 approve 整合就没有正式引用；没有 GC 则失败 blob 无法回收。最小闭环可先 approve 整合 + 手动清理，但 **Batch B 出口要求 GC/ORP 全部**，不能跳过。标签：需要 ChatGPT 决策（内部顺序，不影响范围）。

## 5. 验收矩阵 §B 的真实测试要求

### 5.1 ATT（12 项）

全部要求真实文件系统；ATT-09/11/12 要求故障注入；ATT-10 要求并发。当前零实现、零测试。标签：需要真实测试验证。

### 5.2 LCK（9 项）

- LCK-01/02/03/04/06 需要真实 SQLite/PG；LCK-02/03/05/06/07/08 需要并发/崩溃；LCK-08 明确要求“每不可逆步骤前 verify”。
- LCK-09 是 TOCTOU 降级验收，必须如实记录“降低非消除”。

标签：需要真实测试验证。

### 5.3 GC（12 项）

- GC-01/02 双 Worker 原子认领；
- GC-03/04/05 持锁 quarantine、释放后只 purge 隔离区；
- GC-06 引用回升；
- GC-07 quarantine 后崩溃；
- GC-08/09 退避/死信；
- GC-10 旧 Worker fencing；
- GC-11 人工恢复；
- GC-12 无计数器列。

标签：需要真实测试验证。

### 5.4 ORP（7 项）

全部真实 FS；ORP-01/04/05/06 需故障/并发。标签：需要真实测试验证。

### 5.5 BAK

§B 标题包含 BAK，但 §21.2 明确 BAK 属 Batch C。**Batch B 不得以 BAK 通过作为出口，也不得在本批实现 BAK。** 标签：需要 ChatGPT 决策（若 ChatGPT 要调整归属，须显式改设计，不由 Qoder 自定）。

## 6. 已冻结、不得改动的边界（§21.5）

- 不新增 migration/table/column/index；不改 `0006`。
- 不改 Core `ReviewService` / 端口签名。
- 不改 A1-02 codec/canonical/三 Hash。
- 不改 A1-03 `LinkKeyRebuild` / `apply_link_key_plan` / `db/locking.py`。
- 不改 V1 `KnowledgeRepository` / `KnowledgeOut` / GET。
- 不引入认证/网络/新依赖。
- 不改 `MILESTONES.md`；不提交/推送。
- 单 Backend/单 worker/单本地数据根（D-17）。
- attachments 与 quarantine 同卷（D-10）；跨卷只能 copy+verify，不宣称原子。
- 三个附件稳定码固定：`ATTACHMENT_IMPORT_UNSUPPORTED`、`ATTACHMENT_EXPORT_UNSUPPORTED`、`ATTACHMENT_REVIEW_UNSUPPORTED`。
- 身份锁 10s + `IMPORT_LOCK_TIMEOUT` 固定。

标签：已实现（设计已定义，代码须遵守）。

## 7. 设计内部张力与需要裁决的问题

| # | 张力 | 影响 | 标签 |
|---|---|---|---|
| 1 | §5.3 独立上传用“短事务插引用”；§21.2 Active approve 要求附件引用与 item/tags/origin/links 同一事务 | 不是矛盾，但必须明确“独立上传”与“approve 整合”是两条路径，不能把 approve 拆成短事务 | 需要 ChatGPT 决策 |
| 2 | §19.4 “Active 导入附件只写 staging，pending 不创建正式引用” vs §5.3 “上传即插引用” | 需要区分“直接上传到 item”与“导入 staging”两种入口 | 需要 ChatGPT 决策 |
| 3 | `find_by_hash` 需要 content_hash 索引；§21.5 禁止新索引 | 可能全表扫描或本批不实现秒传 | 需要 ChatGPT 决策 |
| 4 | staging manifest 放在 envelope（提交时固化）还是 approve 时追加 | 决定 DTO 是否改动、TOCTOU 处理 | 需要 ChatGPT 决策 |
| 5 | promote 用 `os.replace`（移走 staging）还是 link/copy（保留 staging 可重试） | 决定 commit 失败后的重试语义 | 需要 ChatGPT 决策 |
| 6 | 删除 item 时是否同事务 enqueue GC，还是仅靠孤儿扫描 | 决定删除路径是否改 Core/钩子 | 需要 ChatGPT 决策 |
| 7 | reject 清理 staging 在 commit 前还是后；失败如何处理 | 决定 pending 可恢复性 | 需要 ChatGPT 决策 |
| 8 | 合并（MERGE）是否迁移附件 | 当前不迁移；产品语义未定 | 需要 ChatGPT 决策 |
| 9 | 附件导出（IMP-16 / `include_attachments`）是否属 Batch B | §21.2 未逐字列出导出；Batch A 明确拒绝 | 需要 ChatGPT 决策 |
| 10 | `approve_review` docstring 写“单次 commit”，代码两次 commit | 文档与实现不一致；附件引用必须进第一次 | 需要 ChatGPT 决策（文档修正） |
| 11 | 附件下载是否需要鉴权/条目状态过滤（archived/跨空间） | 当前无认证；设计只到 loopback | 需要 ChatGPT 决策 |
| 12 | MIME 白名单对 `text/markdown`、`text/csv` 的编码/magic 判定细节 | ATT-04 验收口径 | 需要 ChatGPT 决策 |

## 8. 真实测试与环境依赖

| 环境 | 要求 | 当前 | 标签 |
|---|---|---|---|
| Windows 真实 FS | 路径穿越/保留名/占用/`os.replace`/硬链接 | 当前 win32；未执行附件测试 | 需要真实测试验证 |
| PostgreSQL 真实实例 | advisory lock、SKIP LOCKED、迁移、双方言一致性 | 需 `EXPLAINLAB_PG_TEST_URL`；Batch B 未运行 | 需要真实测试验证 |
| 双 Worker/双线程 | LCK/GC 竞争 | 当前单 worker 设计；测试需真实并发 | 需要真实测试验证 |
| 崩溃注入 | quarantine 后 kill、commit 前 kill、旧 token | 无故障注入框架 | 需要真实测试验证 |
| 磁盘满/只读/权限 | 错误映射与不插 DB | 无 | 需要真实测试验证 |
| 大文件/10 MiB 边界 | 内存与流式处理 | 无 | 需要真实测试验证 |

**不得用 mock FS 或离线 SQL 代替。** 标签：需要真实测试验证。

## 9. 结论

**Batch B 的设计依赖是清晰的：配置 → 仓库/锁 → 附件服务 → approve 整合 → GC → 孤儿扫描 → 真实验收。真实代码只提供了 schema、实体、端口和三处可复用原语；所有关键实现均缺失。设计内部有 12 个需要 ChatGPT 裁决的点，其中 staging manifest 承载方式、promote 语义、删除/拒绝清理顺序、`find_by_hash` 索引冲突最影响架构。**

标签：部分实现 / 需要 ChatGPT 决策 / 需要真实测试验证。