# ExplainLab V2 · A1-04 架构 R1.1（已合并主文档索引）

> 状态：**架构修订稿（R1.1），待用户阶段级批准 + ChatGPT 阶段级独立审计**。
> 本文件是**索引与合并说明**，不是代码实现或测试通过报告。所有新增验收均为【待验证】。
> 产品约束（用户已确定）：**Offline backup / Single deployment / Strict migration**。

## 1. 四份主文档（R1.1 已合并，非增补文件替代）

| 文档 | R1.1 合并位置 | 说明 |
|---|---|---|
| [`V2-A1-04-implementation-plan.md`](./V2-A1-04-implementation-plan.md) | 头部 R1.1 说明；§3.3、§5.1、§12、§19.1–§19.4、§19.6 就地加注；新增 §19.10、§20 | §20 为 R1.1 权威修订（D16-1 / D-13 / D-15 / D-17 / FID-2 / BAK-1 / staging / 边界 / 编号映射 / 冻结门禁） |
| [`V2-A1-04-acceptance-matrix.md`](./V2-A1-04-acceptance-matrix.md) | 新增 §F（F.1–F.8） | R1.1-IMP-25…42、R1.1-SQL-10、R1.1-LNK-14、R1.1-LOCK-09…13、R1.1-BAK-15…19、R1.1-OPS-06，全部【待验证】 |
| [`V2-A1-04-risk-register.md`](./V2-A1-04-risk-register.md) | 新增 §12（12.1 / 12.2） | 12 项 R1.1-R-* 风险（P1），验收编号加 `R1.1-` 前缀 |
| [`V2-A1-04-open-decisions.md`](./V2-A1-04-open-decisions.md) | D-13 加“R1.1 取代”注；新增 §J（J.1–J.5） | R1 审计条件处置、5 项用户确认、D-01…D-17 沿用、术语澄清、冻结门禁 |

R1 与 Request I 的未冲突设计、编号、历史审计记录**全部保留**；冲突处已在原位置加注并指向 R1.1 权威章节。

## 2. 修订来源（只读证据）

- 原始增补包：`./A1-04/R1.1-amendment/ExplainLab-V2-A1-04-Architecture-R1.1-amendment.zip`
- 包内 README + 四份增补 + `SHA256SUMS.json` 已逐文件核验一致。
- 本目录四份主文档即为合并后的 R1.1 版本；增补包仅作来源留档，**不是**交付物替代。

## 3. 重点裁决速查

| 编号 | R1.1 决策 | 主文档位置 |
|---|---|---|
| D16-1 | V2-only read contract；不扩展 V1 `KnowledgeOut`/GET；V2 字段仅经 MarkdownItemRepository + TagRepository | plan §20.1 |
| D-13 / G-4 | source-instance-id：锁后首启生成、原子不覆盖、损坏 fail-closed、备份保留、clone 显式 rotate | plan §20.2 |
| D15-2 | approve 参与同一身份键锁 + fresh session 重读 + 同事务应用 | plan §20.3、§19.3 |
| D15-3 | S0 只读会话关闭→身份锁→S1→写事务 | plan §20.3、§19.2 |
| D17-1 | worker 持锁；10s 有界退避（100ms→500ms 封顶）；超时 `BACKEND_ALREADY_RUNNING` | plan §20.4 |
| D17-2 | `resolve_process_lock_path()` 由 `BACKEND_DIR.resolve()` 派生，不依赖 cwd | plan §20.4 |
| D17-3 | msvcrt/fcntl 统一排他 acquire/release；锁文件永不删除 | plan §20.4 |
| FID-2 | ImportOrigin 查历史版本 + MarkdownItemRepository 查当前来源指针 | plan §20.3 |
| BAK-1 | PG rename 前 maintenance DB 清场 + ALLOW_CONNECTIONS false + terminate + 清零 + fail-closed | plan §20.5 |

## 4. 状态与边界

- 本轮仅修改架构设计文档与 README；**未写业务代码/测试、未装依赖、未改迁移/Core/Backend/Frontend/lockfile、未改 MILESTONES.md、未提交/推送**。
- 所有 R1.1 新增验收**未执行**，统一【待验证】；Windows msvcrt/reload、真实 PG 16.8 restore+清场、SQLite 换文件崩溃、附件合并冲突、approve hook 回滚、instance-id 生命周期均须开发阶段真实取证。
- 冻结前提见 `V2-A1-04-open-decisions.md` §J.5；未满足前**不得启动 Batch A**。
