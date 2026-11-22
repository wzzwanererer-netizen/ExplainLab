# ExplainLab V2 · A1-04 架构 R1.3（已合并主文档索引）

> 状态：**架构修订稿（R1.3），已完成第二轮 D23 身份生命周期/Journal 修正、第三轮定点修正（MATERIALIZE 恢复优先、归档状态转换、Journal 数据契约 v1）、第四轮最终审计修正（`identity_audit_digest` 全库覆盖/DB 重算、Canonical JSON v1 字符串规则与 8 组向量）、第五轮最终定点修正（每项全部 `ImportOrigin` 原始记录逐条审计、原始字段不归一化、孤儿 fail-closed）及第六轮最终冻结前定点修正（ImportOrigin 多记录状态判定表/冲突优先级/身份不一致 fail-closed），待用户阶段级批准**。
> 本文件是**索引与合并说明**，不是代码实现或测试通过报告。所有 R1.3 新增验收均为【待验证】。D23 已明确：仅凭既有 DB 字段/`extra_metadata` **信息不足**，合法物化改由 COMMITTED MATERIALIZE Journal 显式证明；未新增 DB schema。Journal v1 的字段/摘要/版本规则以 `implementation-plan` §22.2 为准。
> 产品约束（用户已确定）：**Offline backup / Single deployment / Strict migration**。

## 1. 四份主文档（R1.3 已合并，非增补文件替代）

| 文档 | R1.3 合并位置 | 说明 |
|---|---|---|
| [`V2-A1-04-implementation-plan.md`](./V2-A1-04-implementation-plan.md) | 头部 R1.3 说明；§21.1、§21.4、§21.5 就地修正；§12、§19.9、§20.7、§20.9、§21.2 同步；新增 §22 | §22 为 R1.3 权威修订（D22 / D23 / D24 / 文件边界 / 验收映射 / 冻结门禁） |
| [`V2-A1-04-acceptance-matrix.md`](./V2-A1-04-acceptance-matrix.md) | 头部 R1.3 说明；新增 §H（H.1–H.4） | `R1.3-HASH-01…04`、`R1.3-ID-01…05`、`R1.3-NET-01…06`，共 15 项，全部【待验证】 |
| [`V2-A1-04-risk-register.md`](./V2-A1-04-risk-register.md) | 头部 R1.3 说明；新增 §14（14.1 / 14.2） | 3 项 `R1.3-R-*` 风险（P1），不降级旧风险 |
| [`V2-A1-04-open-decisions.md`](./V2-A1-04-open-decisions.md) | 头部 R1.3 说明；K.2 加“已关闭”注；新增 §L（L.1–L.4） | D22–D24 裁决；R1.2 §K.2 九项关闭记录；R1.3 冻结门禁 |

R1、R1.1、R1.2 的未冲突设计、编号、风险、验收与历史审计记录**全部保留**；冲突处已在原位置加注并指向 R1.3 权威章节。

## 2. 重点裁决速查

| 编号 | R1.3 决策 | 主文档位置 |
|---|---|---|
| D22 | exporter 只属传输元数据，不参与四类文档 Hash；A1-02 Core Hash/canonicalization v1 零改动；先算 Hash 再注入；frontmatter `__explainlab_exporter_instance_id`、manifest `exporter_instance_id`；不落 DB；重复保留键须在 YAML 折叠前拒绝，保留键/manifest 冲突显式拒绝且零 DB 写 | plan §22.1 |
| D23 | 不新增迁移/表/列/索引；**信息不足结论**：仅凭 DB 字段/`extra_metadata` 无法区分合法物化与历史孤立，禁止以非空实例/Hash/时间推断；复用既有 data 目录 Journal，**COMMITTED MATERIALIZE 记录是本地物化的唯一显式标记**；状态 2a（未物化）/2b（已物化）/3（导入残缺）/4（孤立/冲突）；2a 首次导出 PREPARED→条件 DB 写→重读→COMMITTED+归档，2b 稳定不重写；3/4 不补 `source_document_id`、不覆盖、不 adoption；FID-2、禁 `MAX(imported_at)`；**启动先过 Journal 恢复门：有效 PREPARED 先恢复、PREPARED+DB 空/等于目标才恢复、COMMITTED 未归档只补归档不写 DB、恢复前不分类/不写身份**；clone 前逐条物化 2a，再按九步 write-ahead Journal rotate；`PREPARED`+旧 ID 重查 `materialization_items`+摘要；**COMMITTED 后 current→archive 同卷原子落位、同内容去重、异内容 fail、归档失败禁新操作、append-only**；**Journal v1 固定 `materialization_items` 字段/版本/排序/UTF-8 canonical/SHA-256/显式 null；`identity_audit_digest` 覆盖全部 knowledge_item 且每项逐条纳入全部 ImportOrigin 原始记录（含残缺/重复/非法；稳定 ID/原始字段/记录数/状态，不归一化、读取顺序无关、孤儿 fail-closed）；多记录按固定表判定（`conflict` > `invalid` > `incomplete` > `duplicate` > `complete` > `none`；≥2 个不同合法身份对或 DB 实例不一致→conflict，完整+残缺不得提升，重复+不同身份→conflict，同身份多版本→complete；冲突零认领），每次写后/恢复重读 DB 重算、rotate 前后重算；Canonical JSON v1 固定非 ASCII/转义/代理项/重复键规则与 8 组向量；所有摘要不含 exporter**；Windows 目录同步不保证断电持久 | plan §22.2 |
| D24 | 默认 `127.0.0.1`；绑定仅精确 `127.0.0.1`/`::1`（不接受 `localhost` 绑定）；精确 Host + 合法端口；修改请求同源 Origin；仅 `application/json`；无宽泛 CORS；代理头不授权；DNS Rebinding 拒绝；非 loopback fail-closed；无认证依赖 | plan §22.3 |
| 批次 | D22/D23 归 Batch A；D24 网络验收归 Batch D，**不阻塞 Batch A 非附件开发** | plan §22.4/§22.5；acceptance §H |
| R1.2 待决 | §K.2 九项全部关闭 | decisions §L.2 |

## 3. 状态与边界

- 本轮仅修改架构设计文档与索引；**未写业务代码/测试、未装依赖、未改迁移/Core/Backend/Frontend/lockfile、未改 A1-01/A1-02/A1-03、未改 V1 API、未改 MILESTONES.md、未提交/推送**。
- 所有 R1.3 新增验收**未执行**，统一【待验证】；Hash 稳定性、保留键冲突、MATERIALIZE 恢复优先/物化/归档、身份状态 2a/2b/3/4、**ImportOrigin 多记录状态（多合法身份、完整+残缺、重复+不同身份、DB 实例不一致、同身份多版本）与冲突零认领**、current→archive 同卷原子转换/去重/归档崩溃点、Journal v1 字段/摘要/版本、`identity_audit_digest` 全库覆盖及每项全部 ImportOrigin 原始记录逐条审计（含残缺/重复/非法、原始字段不归一化、读取顺序无关、孤儿 fail-closed）/DB 重算、Canonical JSON v1 字符串/代理项/重复键/8 组向量、rotate 九步/多轮/同 operation_id 重入/Windows-POSIX 持久化差异、真实进程 Host/Origin/重绑定拒绝均须开发阶段真实取证。
- 冻结前提见 `V2-A1-04-open-decisions.md` §L.4；未满足前**不得启动 Batch A**。
