# ExplainLab V2 · A1-04 · Batch B 开发前代码基线盘点

- 盘点日期：2026-11-22
- 目标基线：`970c0d8ec05f0b8c68286839a56b14c74ea230c6`
- 当前分支：`fix/m0-admission-and-m5-regressions`
- 盘点性质：**只读代码与设计核对，未开发 Batch B、未修改业务代码/测试/设计文档、未新增迁移、未安装依赖、未执行 git add/commit/push、未更新 MILESTONES.md。**
- 输出目录：`docs/audit/V2-A1-04-Batch-B-preflight/`

## 1. 基线结论

| 检查项 | 实测结果 | 标签 |
|---|---|---|
| HEAD | `970c0d8ec05f0b8c68286839a56b14c74ea230c6` | 已实现 |
| Batch A 提交存在 | `git cat-file -t` 为 `commit`，主题 `feat(explainlab): complete A1-04 Batch A implementation` | 已实现 |
| 分支 | `fix/m0-admission-and-m5-regressions` | 已实现 |
| 暂存区 | 0 个文件 | 已实现 |
| 已跟踪未暂存改动 | 0 个文件 | 已实现 |
| 未跟踪文件 | 107 个（盘点基线 101 + 本目录 6 份报告），均为审计/盘点材料，不含未提交业务代码 | 已实现 |
| Batch A 之后是否另有代码改动 | 未发现；HEAD 即 Batch A 提交，跟踪工作树干净 | 已实现 |

## 2. 总体判断

**Batch B 的“附件模型”目前只有数据库 schema、Core 实体/端口契约和 Batch A 的附件拒绝语义；没有附件服务、没有上传/下载/删除路由、没有物理内容寻址存储、没有 StorageKeyLock 实现、没有 GC worker、没有 quarantine/孤儿扫描。** 这是本报告最重要的结论。

| 能力域 | 当前真实状态 | 标签 |
|---|---|---|
| `Attachment` 实体 / `AttachmentORM` / `attachment` 表 | 已有字段、索引、FK CASCADE | 已实现 |
| `AttachmentRepository` 端口 | 已有 7 个方法签名 | 已实现 |
| backend `SQLAlchemyAttachmentRepository` | 不存在 | 未实现 |
| `GcTask` / `GcStatus` / `GcTaskORM` / `gc_task` 表 | 已有字段、7 态枚举、索引 | 已实现 |
| `GcTaskRepository` 端口 | 已有认领/状态流转签名 | 已实现 |
| backend `SQLAlchemyGcTaskRepository` | 不存在 | 未实现 |
| `StorageLease` / `StorageKeyLock` 端口 | 已有租约与 fencing 契约 | 已实现 |
| backend StorageKeyLock（SQLite 租约 / PG advisory） | 不存在；`app/db/locking.py` 是 A1-03 链接重建锁，不是本锁 | 未实现 |
| 附件物理存储根 / 分片目录 / 临时文件 / quarantine | 不存在；`backend/data` 仅有 DB 与进程锁文件 | 未实现 |
| 附件上传/下载/删除 API | 不存在 | 未实现 |
| 附件 MIME/大小/magic bytes/路径穿越校验 | 不存在（仅有 Markdown 显示文件名清洗，不是附件安全校验） | 未实现 |
| GC 状态机执行体、worker、调度 | 不存在 | 未实现 |
| 独立孤儿扫描 / DB↔物理一致性检查 | 不存在 | 未实现 |
| Active Review 非附件事务闭环 | 已有 S0→锁→S1→Core approve→Hook→commit | 已实现 |
| Active Review 附件 staging manifest | envelope 仅有空 `attachments` 字段；Hook 遇到非空即拒绝 | 部分实现 |
| Batch A 附件拒绝语义 | 单篇导入拒绝、批量标 unsupported、导出拒绝、审核 Hook 拒绝 | 已实现 |

## 3. 对核心问题的初步回答

**“如何在不破坏 Batch A 已冻结行为的情况下，把附件 staging manifest 纳入 approve 完整事务？”**

真实代码给出的可插入点非常明确：`governance.approve_review()` 在 Core `ReviewService.approve()` 之后、第一次 `session.commit()` 之前调用 `ImportReviewHook.apply_approved()`。附件引用若要满足 Batch B 的“item、tags、origin、links、附件引用同一事务提交/回滚”，应在这个 Hook 内完成附件校验、staging 提升/复用与 `attachment` 引用写入；物理文件操作必须在数据库事务提交前完成，但不能把物理操作伪装成数据库原子事务。完整的依赖、锁顺序、失败语义与需要 ChatGPT 裁决的点见 `active-review-transaction-audit.md`。

当前**不能**直接把附件 manifest 写入 approve 请求：`ReviewResolve` 只有 `note` 字段；manifest 应已存在于 pending `ReviewRequest.payload.__a1_import.attachments`，approve 只重读并校验。是否允许在 approve 请求新增 manifest 字段、manifest 的 schema 版本、staging 目录命名与提升/复制语义，需要 ChatGPT 在 Batch B 架构设计中裁决。

## 4. 与正式设计的对照结论

| 设计主题 | 设计位置 | 与真实代码的差异 | 标签 |
|---|---|---|---|
| 附件上传先物理后 DB | implementation-plan §5.3 | 物理层与引用仓库均不存在 | 未实现 |
| GC 7 态与持锁 quarantine | §5.4、§7.2、§7.3 | 只有枚举/字段；无执行体 | 未实现 |
| StorageKeyLock 双方言 | §7.4 | 只有端口与 `storage_lock` 表；无实现 | 未实现 |
| 独立孤儿扫描 | §7.5 | 不存在 | 未实现 |
| Batch B 任务 T4-02/03/07/08/09/10 | §16.1 | T4-02 仅完成 Tag/ImportOrigin 仓库；附件、锁、GC、孤儿、附件路由均缺失 | 部分实现 |
| Batch B 全事务闭环 | §21.2 D19 | approve 当前只覆盖 item/tags/origin/links，不覆盖附件引用 | 部分实现 |
| 无新迁移 | §21.5、§13 | `0006` 已含 attachment/gc_task/storage_lock；Batch B 可沿用 | 已实现 |
| D-04 参数与 TOCTOU 降级 | open-decisions §D-04、§J.3 | 设计已给默认值；配置字段与实现均不存在 | 部分实现 |
| D-08 MIME/SVG/大小 | open-decisions §D-08、§J.3 | 设计已给白名单/拒绝 SVG/10 MiB；代码无校验 | 部分实现 |
| 验收矩阵 §B | acceptance-matrix §B | ATT/LCK/GC/ORP 基本无实现，无法执行 | 未实现 |

## 5. 报告文件

1. `current-code-inventory.md`：Git 基线、模块/文件级真实盘点、测试覆盖现状。
2. `attachment-model-and-repository-audit.md`：Attachment / GcTask / StorageLock 的模型、字段、端口、索引、缺失实现与风险。
3. `active-review-transaction-audit.md`：Active Review 的 S0/锁/S1/Core/Hook/双 commit 事务边界，以及附件 staging manifest 的可行插入点。
4. `filesystem-and-lock-audit.md`：`backend/data` 实际布局、source-instance-id、Journal、file_write、进程锁、原子替换、缺失的存储/隔离/孤儿能力。
5. `batch-b-design-dependencies.md`：设计条款与真实代码的逐项差异、Batch B 依赖图、必须由 ChatGPT 裁决的事项、不能直接开工的理由。

## 6. 标签说明

本目录所有条目使用以下标签：

- **已实现**：真实代码存在且可运行，或 schema/契约已完整落地。
- **部分实现**：只有 schema、实体、端口、字段或拒绝语义，缺少可运行执行体。
- **未实现**：仓库中不存在对应实现或测试。
- **需要 ChatGPT 决策**：设计未明确或存在两种以上合理实现，不能由 Qoder 自行拍板。
- **需要真实测试验证**：实现后必须在真实 SQLite/PostgreSQL/文件系统/Windows 环境取证，不能以静态检查代替。

## 7. 本次未执行的事项与限制

- 未运行完整测试套件；本报告是代码/设计盘点，不是测试通过证明。现有测试的描述来自源码静态阅读。
- 未启动 Backend；`backend/data` 的实际文件布局是盘点时的真实目录，不代表下次启动后的布局（启动会按代码创建 `source-instance-id` 等）。
- 未连接 PostgreSQL；所有 PG 行为仅为代码/设计阅读结论，未做真实 PG 验证。
- 未修改任何业务代码、测试、设计文档、迁移、依赖或锁文件。
- 未执行 `git add`、`git commit`、`git push`；未更新 `MILESTONES.md`；未开始 B1。

## 8. 停止点

**盘点完成，停止。等待 ChatGPT 根据本目录的真实代码盘点完成 Batch B 正式架构设计；在收到明确开发指令前，不开始 Batch B 业务代码开发。**