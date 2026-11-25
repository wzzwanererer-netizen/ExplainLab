# ExplainLab V2 · A1-04 · Batch B Architecture Freeze

- 文档性质：**Architecture Freeze Candidate（八项 P1 整改版，待独立复审）**，用于 ChatGPT 最终签发；**不是开发完成证明，不是验收通过证明**。
- 基线提交：`970c0d8ec05f0b8c68286839a56b14c74ea230c6`（Batch A 完成提交）。
- 基线盘点：[`docs/audit/V2-A1-04-Batch-B-preflight/`](../../audit/V2-A1-04-Batch-B-preflight/README.md)。
- 整改日期：2026-11-22。正式冻结日期待签发。
- 当前状态：**D-B01…D-B16、O-B01…O-B11 已全部裁决并落点**；八项 P1 已落实到设计，候选等待 ChatGPT 独立复审。**未写业务代码、未改测试、未新增迁移、未改 MILESTONES、未执行 git add/commit/push、未启动 B1、未运行实现验收测试**。

## 1. 目的与边界

本冻结把 ChatGPT 已裁决的 25 项 Batch B 架构决策及最终复审裁决落成可执行、可验收、无隐含假设的设计契约，覆盖：

- 内容寻址附件的物理存储、分片、临时文件、原子发布与 no-clobber；
- 独立上传/下载/删除/**元数据列表** API；
- 导入 staging、ZIP-only 附件 transport、manifest schema、Active Review 全事务附件引用；
- `StorageKeyLock` 的 SQLite 租约与 PostgreSQL Advisory Lock 双方言实现；
- GC 七态状态机、quarantine 24h 安全期、退避重试；
- 独立孤儿扫描（ORP）、staging 清扫、DB↔物理一致性报告；
- Batch B 验收矩阵、任务路线、风险与冲突。

**严格不在本批范围：**

- 附件导出（沿用 `ATTACHMENT_EXPORT_UNSUPPORTED`，见决策 20）；
- `MERGE_DUPLICATE` 的附件迁移（决策 21；归入后续批次）；
- 备份/恢复/打包（BAK，归 Batch C）；
- 鉴权、多用户、公开网络暴露（Batch D 范围）；
- 修改 Core `ReviewService`、A1-02 Hash 契约、A1-03 `LinkKeyRebuild`（决策 13/14）；
- 修改 Core `ImportReport` 模型（D-B12）；
- 新表、新列、新索引、新迁移（决策 3）；
- 新第三方依赖（含 `filetype`、`python-magic`、`python-multipart`、`pgvector` 等）。

## 2. 权威顺序

发生冲突时按以下顺序裁决：

1. **本轮 ChatGPT 最终复审裁决（D-B01…D-B16、O-B01…O-B11 关闭结果）**；
2. 用户此前给出的 25 项 Batch B 架构决策；
3. 本目录 10 份 Batch B 冻结文档；
4. `docs/plans/V2-A1-04-implementation-plan.md`（R1.3 正式设计）；
5. `docs/plans/V2-A1-04-open-decisions.md`；
6. `docs/plans/V2-A1-04-acceptance-matrix.md`；
7. Batch B 预检报告（事实盘点）。

R1.3 与本冻结不一致之处**不得静默覆盖**，全部列入 §5、§6 与 `risk-register.md`。

## 3. 25 项决策追踪矩阵

| # | 决策 | 落点 | 状态 |
|---|---|---|---|
| 1 | `storage_key == content_hash`，统一 SHA-256 | `storage-and-lock-contract.md` §2 | 已纳入 |
| 2 | 复用 `ix_attachment_storage_key`，不建新索引 | 同上 §2.4；`architecture.md` §3 | 已纳入 |
| 3 | 不新增迁移/表/列/索引 | `architecture.md` §3；`implementation-roadmap.md` §1 | 已纳入 |
| 4 | SQLite 用 `storage_lock` 租约；PG 用 Advisory Lock + token 行 | `storage-and-lock-contract.md` §4 | 已纳入（D-B02 已批准） |
| 5 | TTL 60s / heartbeat 15s / wait 10s | 同上 §4.1；`api-contracts.md` §6 | 已纳入 |
| 6 | 多 key 按实际冲突域排序：SQLite 完整 key、PG advisory 二元组 | 同上 §4.4 | 已纳入 |
| 7 | PG 每批一个专用物理连接持有 session 级 Advisory Lock | 同上 §4.3 | 已纳入（D-B02 已批准） |
| 8 | promote 优先安全复制保留 staging 原件 + 原子发布 | `attachment-lifecycle.md` §4；`active-review-integration.md` §5 | 已纳入 |
| 9 | 正式目录不得静默覆盖 | `storage-and-lock-contract.md` §3 | 已纳入 |
| 10 | staging manifest 冻结在 `__a1_import.attachments` | `active-review-integration.md` §3 | 已纳入 |
| 11 | approve 时不得追加 manifest | 同上 §3、§4 | 已纳入 |
| 12 | 附件引用进入 Active approve 第一次 DB commit | 同上 §5 | 已纳入 |
| 13 | 不改 Core `ReviewService` | `architecture.md` §1；`implementation-roadmap.md` §1 | 已纳入 |
| 14 | 不改 A1-02 Hash / A1-03 `LinkKeyRebuild` | 同上 | 已纳入 |
| 15 | pending 期间无正式 Attachment 引用 | `attachment-lifecycle.md` §3；`active-review-integration.md` §4 | 已纳入 |
| 16 | reject 先提交状态，再清理 staging | `active-review-integration.md` §7 | 已纳入 |
| 17 | GC 安全等待 24h、最多 8 次、退避 60s→6h 上限 | `gc-and-orphan-recovery.md` §4、§5 | 已裁决：第 8 次公式值 7680s，无下次调度，21600s 仅为配置上限 |
| 18 | 孤儿扫描间隔 300s | 同上 §6 | 已纳入 |
| 19 | GC 与 ORP 必须使用 StorageKeyLock + fencing | 同上 §3、§6 | 已纳入 |
| 20 | 附件导出继续不支持 | `api-contracts.md` §8；`attachment-lifecycle.md` §8.3 | 已纳入 |
| 21 | `MERGE_DUPLICATE` 不迁移附件 | `attachment-lifecycle.md` §8.1 | 已纳入 |
| 22 | 删除 item 的孤儿由 ORP 兜底 | 同上 §8.2；`gc-and-orphan-recovery.md` §6 | 已纳入 |
| 23 | 拒绝 SVG；单附件上限 10 MiB | `api-contracts.md` §4 | 已纳入（D-B13 已裁决） |
| 24 | MIME 同时校验声明类型与实际内容 | 同上 §4.2 | 已纳入；文本子类型按 UTF-8 族校验，不宣称字节可区分 TXT/MD/CSV |
| 25 | Windows 文件占用错误支持安全重试 | `storage-and-lock-contract.md` §6；`gc-and-orphan-recovery.md` §5.3 | 已纳入 |

## 4. 文档地图

| 文件 | 内容 |
|---|---|
| `architecture.md` | 组件、依赖方向、事务边界、配置、禁止项 |
| `storage-and-lock-contract.md` | 内容寻址布局、原子写、no-clobber、StorageKeyLock、Windows |
| `attachment-lifecycle.md` | 上传/去重/删除/列表/staging/promote/merge/item 删除/导出 |
| `active-review-integration.md` | manifest schema、approve 事务、失败/崩溃、reject |
| `gc-and-orphan-recovery.md` | GC 七态、quarantine、退避、ORP、staging 清扫、一致性报告 |
| `api-contracts.md` | 路由、DTO、状态码、稳定错误码、MIME/大小、下载响应 |
| `implementation-roadmap.md` | B1–B6 任务、文件级改动面、退出条件 |
| `acceptance-plan.md` | ATT/LCK/GC/ORP 与 IMP/R1 条目逐项方法 |
| `risk-register.md` | 继承风险、Batch B 新风险、裁决影响、残余风险 |

## 5. 与 R1.3 的显式差异与最终裁决（D-B）

> 以下差异均**未被静默覆盖**。最终裁决已关闭全部 D-B 项；实现必须按“本冻结”列执行。

| ID | R1.3 / 既有设计 | 本冻结（最终） | 裁决结果 |
|---|---|---|---|
| D-B01 | staging 路径为 `<review_id>/<operation_id>` | staging 根下使用 `<staging_id>/`；manifest 记录 `staging_id` | **已批准** |
| D-B02 | PG 仅用 Advisory Lock；`storage_lock` 表被描述为 SQLite 租约 | PG 互斥权威是 Advisory Lock；同一 `storage_lock` 行承载单调 fencing token 与展示用租约元数据；**行 TTL 过期不能绕过仍存活的 Advisory Lock** | **已批准** |
| D-B03 | 导入附件传输方式未定义 | **ZIP-only**：`archive_base64` 的 `attachments/` 进入 staging；JSON 附件单篇 400，批量逐篇 unsupported；不引入 multipart | **已批准（O-B01）** |
| D-B04 | IMP-16 期望导出包含附件回填 | 附件导出继续不支持；IMP-16 附件部分不进入 Batch B 退出条件 | 已按裁决覆盖 |
| D-B05 | 设计提到按 `content_hash` 去重 | 去重以 `storage_key`（等于 hash）为准；`find_by_hash` 保留但**不进入热路径** | 已纳入 |
| D-B06 | `failed_permanent` 在部分文字中被视为可再次人工处理 | 冻结为**自动终态**；仅允许运维显式转 `needs_manual` 后再重试 | 已纳入 |
| D-B07 | `ATTACHMENT_REVIEW_UNSUPPORTED` 在 Batch A 对所有附件 manifest 返回 | 对合法 manifest 放行；该错误码保留给“附件能力关闭/不受支持” | 已纳入 |
| D-B08 | “单次 commit”出现在 approve 路由 docstring | **事务①为业务提交边界（含附件引用）；事务②为独立索引提交**；②失败不回滚① | **已裁决** |
| D-B09 | `find_by_hash` 被当作通用去重入口 | 上传去重按 `(item_id, storage_key)` 查现有引用；`find_by_hash` 不作为授权/去重唯一依据 | 已纳入 |
| D-B10 | 附件列表端点未定义 | **新增只读 `GET /api/knowledge/{item_id}/attachments`，只返回元数据**（O-B04） | **已裁决** |
| D-B11 | LCK-09 提到“单写者/库级串行降级” | Batch B **不提供**该降级；SQLite 用诚实租约，PG 用 advisory；不宣称严格互斥 | **已裁决：不采用** |
| D-B12 | IMP-19 要求 report 含附件结果；Core `ImportReport` 无附件字段 | **不修改 Core `ImportReport`**；使用既有 `warnings/errors/unsupported` 或 backend 响应摘要 | **已裁决** |
| D-B13 | `acceptance-matrix ATT-05` 的 SVG 策略待审批 | **SVG 固定拒绝**；不做内联/消毒 | **已裁决** |
| D-B14 | 独立上传 transport 未定义；初稿曾拟用 multipart | 固定为 **JSON base64**：`filename` / `mime` / `content_base64`；不引入 `python-multipart` | **已批准（O-B09）** |
| D-B15 | 原顺序 Hook 内取锁 | 附件锁在 **S1/Core approve 之前、任何 DB 写事务之外**预取；D23 恢复事务结束后取锁；物理预发布早于业务写；Hook 只补齐 DB 并验证计划 | **已批准（O-B10）** |
| D-B16 | 决策 17 写“退避 60s→6h” | 保留 `min(60*2**(n-1),21600)` 与 8 次上限；第 8 次公式值 **7680s**，终态无下次调度，21600s（6h）仅为配置上限，不承诺 8 次内达到 | **已接受（O-B11）** |

## 6. 开放问题最终裁决（O-B，全部关闭）

| ID | 问题 | 最终裁决 | 落点 |
|---|---|---|---|
| O-B01 | 导入附件 transport | **ZIP-only**；JSON 附件单篇 400，批量逐篇 unsupported；不增加 multipart | `api-contracts.md` §5；`attachment-lifecycle.md` §3 |
| O-B02 | staging 目录命名 | **批准 `<staging_id>/`**；不引入 `review_id` 预分配 | `storage-and-lock-contract.md` §1；`active-review-integration.md` §3 |
| O-B03 | PG fencing token | **批准**复用 `storage_lock` 行；Advisory Lock 是互斥权威，行 TTL 不授权接管 | `storage-and-lock-contract.md` §4.3 |
| O-B04 | 附件列表端点 | **新增只读列表端点，只返回元数据**；不放宽下载/路径信息 | `api-contracts.md` §2.4；`attachment-lifecycle.md` §2.5 |
| O-B05 | staging 清扫与导入上限 | 宽限 **24h**；单次 **≤100 个**、**≤100 MiB**；单文件 **≤10 MiB**；**pending 引用优先于时间判断** | `gc-and-orphan-recovery.md` §6.4；`architecture.md` §5 |
| O-B06 | 归档 item 附件策略 | **禁止新增附件**；**允许下载/元数据列表/删除引用** | `attachment-lifecycle.md` §2.1、§5；`api-contracts.md` §2.3 |
| O-B07 | GC 人工恢复入口 | **不新增 HTTP 管理端点**；保留内部人工恢复/重试函数与审计日志 | `gc-and-orphan-recovery.md` §9、§10 |
| O-B08 | 附件-only 导入 Active | **不独立触发 Active Review**；Active 附件-only 导入**明确拒绝**（`ATTACHMENT_ONLY_IMPORT_UNSUPPORTED`），不得静默成功或忽略附件；独立上传走附件 API | `attachment-lifecycle.md` §3.1；`active-review-integration.md` §3.3 |
| O-B09 | 独立上传 transport | **批准 JSON base64**；不引入 `python-multipart`；单文件 10 MiB | `api-contracts.md` §2 |
| O-B10 | approve 预取锁 | **批准**在 S1/Core approve 之前预取；取锁时 D23 恢复的内部事务已提交/关闭，发布在业务写前 | `active-review-integration.md` §2、§5.2 |
| O-B11 | 退避曲线 | **接受** 第 8 次公式值 7680s，无下次调度；21600s 仅为上限 | `gc-and-orphan-recovery.md` §4.3 |

## 7. 不可违反的不变量

1. 物理文件操作与数据库 commit **不是**一个原子事务；任何文档、日志、验收均不得如此表述。
2. 导入/审核路径中，正式附件引用只允许在 Active approve 的**第一次** DB commit 或 Draft 导入的文档事务中产生；pending 期间为零。独立上传按自身单事务产生引用。
3. 正式 blob 发布后永不静默覆盖；同 key 内容必须逐字节一致。
4. 任何删除/隔离动作前必须持有对应 `StorageKeyLock` 并校验 fencing token。
5. `storage_key` 只由服务端从实际字节计算，绝不信任客户端声明。
6. manifest 只在 pending 创建时写入；approve 只读、校验、执行，不追加。
7. 稳定错误码不得改名、不得复用为其他语义；新错误码集中登记。
8. 不改 Core、不改 A1-02/A1-03、不新增迁移/依赖、不改 Core `ImportReport`。
9. PostgreSQL 的行租约过期**不**等于 Advisory Lock 释放；其他 worker 不得仅凭行 TTL 接管或操作文件。
10. staging 写入、提交与清扫持同一 staging_id guard。活动按文件/标记 mtime；确认无 pending 的空半成品按其自身目录 mtime 保守处理。
11. 下载的完整 hash 校验与后续流式输出必须使用**同一个已打开文件句柄**，禁止校验后按路径重新打开。
12. Archived item：禁止新增附件；允许下载、列表、删除引用。
13. Active 附件-only 导入必须显式拒绝；独立上传支持单独新增附件；含 title/content 变更的合法 ZIP 可在批准时随业务提交附件。

## 8. 复审检查清单

- [x] 25 项决策是否全部有唯一落点且无相互矛盾（见 §3）。
- [x] D-B01/D-B02 是否批准（均已批准）。
- [x] O-B01 是否裁决（ZIP-only）。
- [x] O-B04 列表端点是否裁决（新增只读元数据端点）。
- [x] O-B05 导入上限/staging 宽限是否裁决（24h / 100 / 100 MiB / 10 MiB / pending 优先）。
- [x] O-B06 归档 item 策略是否裁决（禁新增；允许下载/列表/删除）。
- [x] O-B07 人工 GC 入口是否裁决（内部函数 + 审计，无 HTTP）。
- [x] O-B08 附件-only Active 是否裁决（拒绝 + 独立上传）。
- [x] O-B09/D-B14 是否批准 JSON base64 独立上传（已批准）。
- [x] O-B10/D-B15 是否批准附件锁在 S1/Core approve 之前预取（恢复事务结束后取锁，业务写之前完成物理发布）。
- [x] O-B11/D-B16 是否接受“第 8 次公式值 7680s，无下次调度、6h 仅为上限”（已接受）。
- [x] GC 七态是否闭合，`failed_permanent` 是否确认自动终态。
- [x] StorageKeyLock 的 owner/重入/接管/release/mismatch 语义是否确认。
- [x] 是否接受“物理操作非事务、失败由 ORP 收敛”的诚实边界。
- [x] 是否接受验收全部标记“待验证”，且未把设计当实现。
- [ ] ChatGPT 最终签发 Architecture Freeze。

## 9. 整改与复审索引

- P1 修正落点：PG 锁 → storage §4；SQLite 事务与归档 → architecture §4 和 review §2/5；路径隔离 → storage §1；ZIP 归属/重试 → lifecycle §3 和 API §5；staging → lifecycle §3、GC §6.4；审核决议 → review §2/7；GC 代次 → GC §5/6。
- D22/D23、A1-02/A1-03 与原身份 Journal 保持。D24 仍由 Batch D 验收。单 Backend、单 worker、单数据根。数据库 schema 与 Core 端口维持 Batch A。
- 验收计划保留 53 项编号，继承 R1-IMP-07 与 R1-LOCK-07/08 通过既有条目映射。所有实现验收待验证。
- [整改报告与复审索引](../../audit/V2-A1-04-Batch-B-remediation/README.md)。

## 10. 停止点

本目录完成八项 P1 整改后停止：**不进入 B1，不修改业务代码/测试/迁移/依赖/MILESTONES，不执行 git add/commit/push，不运行实现验收测试**。等待 ChatGPT 最终签发 Architecture Freeze。
