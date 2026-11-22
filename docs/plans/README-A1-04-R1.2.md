# ExplainLab V2 · A1-04 架构 R1.2（已合并主文档索引）

> 状态：**架构修订稿（R1.2，D18–D21），待用户阶段级批准 + ChatGPT 独立审计**。
> 本文件是**索引与合并说明**，不是代码实现或测试通过报告。所有 R1.2 新增验收均为【待验证】。
> 产品约束（用户已确定）：**Offline backup / Single deployment / Strict migration**。
> 本轮仅文档维护：未写业务代码/测试、未新增迁移/表/列/索引、未加依赖、未改 Core/A1-02/A1-03/V1 API/MILESTONES、未提交/推送。

## 1. 四份主文档（R1.2 已合并，非增补文件替代）

| 文档 | R1.2 合并位置 | 说明 |
|---|---|---|
| [`V2-A1-04-implementation-plan.md`](./V2-A1-04-implementation-plan.md) | 头部 R1.2 说明；§1.1/§1.2、§5.1、§5.2、§12、§19.9、§19.10、§20.2、§20.7、§20.9 就地加注；新增 §21 | §21 为 R1.2 权威修订（D18 / D19 / D20 / D21 / 边界 / 编号映射 / 冻结门禁） |
| [`V2-A1-04-acceptance-matrix.md`](./V2-A1-04-acceptance-matrix.md) | 新增 §G（G.1–G.5） | `R1.2-ID-01…08`、`R1.2-BAT-01…06`、`R1.2-ASYNC-01…08`、`R1.2-NET-01…08`，全部【待验证】 |
| [`V2-A1-04-risk-register.md`](./V2-A1-04-risk-register.md) | 新增 §13（13.1 / 13.2） | 16 项 `R1.2-R-*` 风险（含 1 项 P0 网络暴露、15 项 P1/P2），全部【待验证】 |
| [`V2-A1-04-open-decisions.md`](./V2-A1-04-open-decisions.md) | 头部 R1.2 说明；新增 §K（K.1–K.4） | D18–D21 裁决、仍需用户确认的 9 项细节、取代/扩展关系、冻结门禁 |

R1 与 R1.1 的未冲突设计、编号、历史审计记录**全部保留**；冲突处已在原位置加注并指向 R1.2 权威章节。

## 2. 修订来源

- R1.2 决策由 ChatGPT 提供（文档身份模型、批次依赖、同步事务执行模型、HTTP 网络边界）。
- 本目录四份主文档即为合并后的 R1.2 版本；**不存在只放增补文件替代主文档的情况**。

## 3. 重点裁决速查

| 编号 | R1.2 决策 | 主文档位置 |
|---|---|---|
| D18 | `source_instance_id` / `source_document_id` / `exporter_instance_id` 三元分离；exporter 仅 frontmatter/manifest、不落 DB；来源身份不可覆盖；clone 只 rotate exporter；legacy 不伪造 | plan §21.1 |
| D19 | Batch A 不含附件完整导入/导出，含附件显式拒绝/unsupported；Batch B 完成附件 + Active approve 全事务闭环；四批独立出口 | plan §21.2、§19.9 |
| D20 | 同步 `def` 路由 + 单一同步 `ImportCoordinator` + 线程内 Session；锁覆盖完整事务；断连不提前释放；禁止 async + threading 双架构 | plan §21.3、§19.10 |
| D21 | 默认 `127.0.0.1`；无认证拒绝非 loopback 并 fail-closed；CORS/代理头不是认证；代理/隧道为额外暴露面 | plan §21.4、§12 |

## 4. 状态与边界

- 所有 R1.2 新增验收**未执行**，统一【待验证】；同步模型并发/取消、loopback 校验、附件拒绝、批次门禁、legacy 身份兼容均须开发阶段真实取证。
- 冻结前提见 `V2-A1-04-open-decisions.md` §K.4；未满足前**不得启动 Batch A**，不进入 A1-05/A2。
- R1.1 索引保留在 [`README-A1-04-R1.1.md`](./README-A1-04-R1.1.md) 作为历史记录。
