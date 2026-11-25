# ExplainLab V2 · A1-04 风险登记册

> 状态：**R1.3 修订风险登记，非已发生事件**（R1 / R1.1 / R1.2 历史保留）。
> **R1 架构修订说明（2026-11-21）**：本文件已纳入 A1-04 第一轮独立技术核验后的架构裁决。本文原始章节中与文末「R1 权威修订」冲突的内容，以 R1 为准；R1 未覆盖的原设计继续有效。本文仍是**设计文件，不是实现或测试通过证明**。R1 修订未经用户阶段级批准前，不得据此启动业务代码开发。
> **R1.1 增补（2026-11-21）**：已追加 §12（12 项 `R1.1-R-*` 风险，P1，全部【待验证】）；与 `implementation-plan` §20、`acceptance-matrix` §F、`open-decisions` §J 对齐。原 §1–§11 编号与内容全部保留。
> **R1.2 增补（2026-11-21）**：已追加 §13（身份混淆 / 批次依赖 / 线程与锁生命周期 / 网络暴露，全部【待验证】）；与 `implementation-plan` §21、`acceptance-matrix` §G、`open-decisions` §K 对齐。原 §1–§12 编号与内容全部保留，不重编号、不删减。
> **R1.3 增补（2026-11-21）**：已追加 §14（3 项 `R1.3-R-*` 风险：exporter/Hash 耦合、本地身份初始化、本机 HTTP 校验，全部【待验证】）；与 `implementation-plan` §22、`acceptance-matrix` §H、`open-decisions` §L 对齐。原 §1–§13 编号、严重度与验收引用全部保留，不重编号、不删减、不降级。已按 ChatGPT 最终独立审计补入重复键折叠前拒绝、状态 4 身份不补不覆盖、rotate Journal 崩溃恢复控制；**第二轮有限修正**补入 D23 的“仅凭 DB 字段/`extra_metadata` 信息不足”结论、MATERIALIZE Journal 显式标记、`PREPARED`+旧 ID 的 DB 重查、Journal 归档/多轮/同 operation_id 重入；**第三轮定点修正**补入 MATERIALIZE 恢复优先、current→archive 同卷原子转换/去重/归档崩溃、Journal v1 schema 与摘要规则；**第四轮最终审计修正**补入 `identity_audit_digest` 全库来源身份投影/DB 重算控制与 Canonical JSON v1 字符串/代理项/重复键/测试向量控制；**第五轮最终定点修正**补入每项全部 `ImportOrigin` 原始记录（含残缺/重复/非法）逐条审计、原始字段不归一化、读取顺序无关与孤儿 fail-closed；**第六轮最终冻结前定点修正**补入 ImportOrigin 多记录状态判定表、互斥/组合优先级、多合法身份或 DB 实例不一致的 `conflict` fail-closed、禁止任选/合并/猜测，以及同身份多版本不构成冲突；**风险编号仍为 3 项，不新增**。
> 防护措施均为【提议】，须开发后真实测试取证（验收矩阵交叉引用），**不得宣称已验证**。
> 配套：`V2-A1-04-implementation-plan.md`、`V2-A1-04-acceptance-matrix.md`（验收编号）、`V2-A1-04-open-decisions.md`（决策/冲突编号）。
> 严重程度：**致命**（不可逆数据丢失/安全漏洞）> **高**（数据不一致/治理绕过/并发损坏）> **中**（可用性/幂等偏差/可恢复孤儿）> **低**（可观测/告警缺失）。
> 基线：HEAD `784b124`，A1-03 审计 CONDITIONAL PASS（D 类阻塞 0，无数据丢失路径）。本登记聚焦 A1-04 **新增**导入导出/附件/GC/备份/链接 ops 引入的风险。

---

## 1. 数据丢失（致命）

| 编号 | 风险 | 严重程度 | 发生条件 | 影响 | 防护措施 | 验收 | 决策 |
|---|---|---|---|---|---|---|---|
| R-DL-01 | GC 释放锁后误删原始文件 | **致命** | 违反 R5-1：释放 storage_key 锁后直接删原始路径，期间引用回升 | 仍被引用附件物理丢失，DB 引用悬空 | **持锁+引用复核临界区内**原子 quarantine 原始→隔离区；释放后**仅 purge 隔离区**；purge 前再次持锁复核==0+fencing；引用回升→恢复/ cancelled | GC-04/05/06 | — |
| R-DL-02 | 孤儿扫描误删仍被引用文件 | **致命** | 扫描未对照 DB 引用集合 / 未排除临时文件 / 未持锁复核 | 在用附件被回收 | 对照 `list_storage_keys`；排除 temp 命名；安全等待期（mtime）；持锁复核==0+fencing+quarantine 后才 purge | ORP-01/02/03/06 | — |
| R-DL-03 | 旧 Worker 租约被接管后继续删 | **致命** | 旧 Worker 持过期 token 恢复执行不可逆物理步骤 | 双删/误删 | 每不可逆步骤前 verify(owner+token)（storage_lock + gc_task 双 fencing），失配立即中止 | LCK-05/GC-10 | — |
| R-DL-04 | 备份恢复盲信 Manifest 标记 | **致命** | 切换中途崩溃，marker 已写但资源未齐，对账盲信 marker | 半切换/数据丢失 | 三方对账（manifest vs DB 实际 vs 附件实际）；无标记→回滚旧 generation；有标记不一致→回滚或**仅幂等可补全+校验过**才前滚 | BAK-05/06 | — |
| R-DL-05 | v2_downgrade 无备份即删 V2 数据 | **致命** | 绕过运维门禁直接 alembic downgrade | V2 数据（链接/附件元数据/审计/ImportOrigin）不可逆丢失 | CLI 门禁：备份→校验→确认→记录 migration_ops_log→才 downgrade；**Alembic 只管 Schema 不承担备份** | OPS-02/03/04 | — |
| R-DL-06 | 导入静默覆盖既有条目 | **致命** | 无 id 文档 content_hash 查重缺失 / 幂等误判 | 用户数据被覆盖 | 无 id→content_hash 查重 duplicates 提示不静默覆盖；幂等权威=入站源 payload_hash vs 持久化 source_payload_hash | IMP-03/04/10/20 | D-02 |
| R-DL-07 | Windows 强删占用文件 | **高** | sharing violation 时强制 delete | 文件损坏/句柄泄漏 | 关闭句柄+指数退避重试→仍失败 failed_retryable 交孤儿扫描/人工，**不强删** | BAK-09 | D-10 |
| R-DL-08 | 跨卷 rename 非原子致中间态丢失 | **高** | 隔离区与存储根跨卷，copy+delete 中途崩溃 | 原始已删隔离未全 | 同卷假设；跨卷降级 Manifest+对账+孤儿扫描兜底，**明确标注非原子** | BAK-10 | D-10 |

---

## 2. 重复导入 / 幂等（高/中）

| 编号 | 风险 | 严重程度 | 发生条件 | 影响 | 防护措施 | 验收 | 决策 |
|---|---|---|---|---|---|---|---|
| R-IMP-02 | 幂等比对目标再生 hash 而非源 hash | **高** | 用目标 status/version 再生 payload_hash 做幂等权威 | 重导同一文件误判 updated/重复建 | 持久化 **source_payload_hash**（ImportOrigin + item 冗余列），比对入站源 hash；目标再生不参与幂等权威 | IMP-03/04 | D-02 |
| R-IMP-03 | 同一来源身份出现多个 pending 审核单 | **高** | 并发/重复提交未执行 R1 pending 查重 | 审核单堆积/批准顺序歧义 | 同 identity+same hash 复用；不同 hash 且旧 pending 未解决则 SOURCE_HAS_PENDING_IMPORT；不实现 A1-05 防覆盖/撤回 | R1-IMP-06/07 | D-01/D-16 |
| R-IMP-04 | canonicalization 版本不一致静默比 hash | **高** | 跨版本源直接比 payload_hash | 误判相同/不同 | require_comparable_versions 抛错→降级 content_hash+字段级比对，不静默 | IMP-13 | — |
| R-IMP-05 | 重复键源文件再导 hash 变化误判 | **中** | A1-02 L2：`_duplicates` 诊断元键不再生，导出→再导 payload_hash 异 | 误判内容变更触发审核 | content_hash 相等→判元数据变化非 skipped；ImportReport 如实提示属元数据非内容 | IMP-05/12 | — |
| R-IMP-06 | 并发同来源身份导入重复 create | **高** | 两请求同身份无 keyed lock 或不做锁内重读 | 重复条目/覆盖竞态 | OS 单实例锁 + keyed lock + S0/S1 快照重读；无身份时按 target item/content hash 锁 | IMP-18/R1-IMP-01/02/15/16 | D-15/D-17 |
| R-IMP-07 | 跨实例导入保留 active 绕过本地治理 | **高** | 跨实例源 active 直建 active | 未经本地审核内容上线 | 跨实例**默认 Draft** + status_changes 告警 | IMP-09 | — |

---

## 3. 附件孤儿 / GC 误删（高/中）

| 编号 | 风险 | 严重程度 | 发生条件 | 影响 | 防护措施 | 验收 | 决策 |
|---|---|---|---|---|---|---|---|
| R-ATT-01 | DB 事务失败遗留物理孤儿 | **中** | 先写物理后插 DB，DB 失败该事务内 gc_task 随事务回滚 | 物理文件无引用无 gc_task | **独立孤儿扫描（口径 B）兜底**，不依赖失败事务 gc_task；先物理后 DB 顺序明确 | ATT-11/ORP-01 | — |
| R-ATT-02 | 物理失败但 DB 已插引用 | **高** | 顺序颠倒或物理 rename 失败未回滚 DB | DB 引用悬空（下载 404） | **先物理（temp+rename）成功才插 DB**；物理失败不插 DB；一致性检查报告 DB 有物理无 | ATT-12/ORP-04/07 | — |
| R-ATT-03 | 引用计数器漂移 | **高** | 引入独立引用计数列而非 DB 派生 | 计数!=实际→GC 误判 | **引用数=COUNT(attachment WHERE storage_key)**，无独立计数器列 | GC-12 | — |
| R-ATT-04 | quarantine 后崩溃残留不清 | **中** | quarantine 成功但 purge 前崩溃 | 隔离区堆积 | 独立扫描识别隔离区残留+安全 purge（复核==0）；DB 有引用原始缺失→从隔离区恢复 | GC-07/ORP-05 | — |
| R-ATT-05 | GC 无限重试/瞬时失败误判 permanent | **中** | 退避/分级缺失 | 任务堆积或过早人工 | failed_retryable+next_retry_at 退避；attempts≥max/不可重试→failed_permanent→needs_manual | GC-08/09 | D-04 |
| R-ATT-06 | 安全等待期不足致并发上传被回收 | **高** | purge 等待期 < 上传窗口 | 刚上传未插 DB 文件被 purge | 等待期（mtime 阈值）+ 排除 temp + 持锁复核==0 | ORP-03/GC-05 | D-04 |

---

## 4. 并发竞争（高）

| 编号 | 风险 | 严重程度 | 发生条件 | 影响 | 防护措施 | 验收 | 决策 |
|---|---|---|---|---|---|---|---|
| R-CON-01 | StorageKeyLock TOCTOU（锁与物理间隙） | **高** | SQLite 租约非严格行锁，acquire 与物理操作间窗口 | 双写/双删同 key | 每不可逆步骤前 verify(owner+token)；物理移出 DB 写事务；**诚实记录降低非消除**；严格互斥降级单写者/库级串行 | LCK-08/SQL-07 | **D-04** |
| R-CON-02 | 双 Worker 认领同 gc_task | **高** | 认领非原子 | 双执行/双删 | PG FOR UPDATE SKIP LOCKED；SQLite 短事务条件 UPDATE rowcount==1（pending OR 过期 running），token+1/attempts+1 | GC-01/02 | — |
| R-CON-03 | 租约过期双活 | **高** | 旧 owner 未察觉过期继续操作 | 与新 owner 竞争 | 单调 lease_token fencing；renew/release rowcount==0 即中止；过期可接管但 token 递增 | LCK-03/05/06 | — |
| R-CON-04 | 持锁进程崩溃锁滞留 | **中** | 崩溃未释放 | key 永久锁死 | SQLite 租约到期自动可接管；PG advisory 会话结束自动释放 | LCK-07 | — |
| R-CON-05 | 链接重建 SQLite 读阶段窗口② | **高** | 读后写前无锁（诚实 no-op），旧快照覆写 | 链接键被旧值覆盖 | **P2 六字段乐观前置 rowcount==1 + 步 8c no-op 复核**（A1-03 整改已实现，A1-04 复用不重开） | LNK-10/SQL-01 | D-09 |
| R-CON-06 | 链接重建 PG 窗口② | **高** | 读阶段无表锁 | 并发重建竞争 | **LOCK TABLE SHARE ROW EXCLUSIVE + FOR UPDATE**（A1-03 已实现，复用） | LNK-09 | — |
| R-CON-07 | SQLITE_BUSY 永久饥饿 | **中** | 高并发写 busy_timeout 不足/长事务 | 写请求永久失败 | busy_timeout=5000；GC/锁短事务立即 commit；**不擅启 BEGIN IMMEDIATE/WAL**（需全局管线改动，独立审批） | SQL-02/03/04/08 | **D-09** |
| R-CON-08 | 附件并发上传同内容竞争 | **中** | 双请求同 storage_key 无锁 | 物理损坏/重复 | StorageKeyLock 串行物理写，仅一份物理 | ATT-10 | — |
| R-CON-09 | 孤儿扫描与 GC 并发同 key | **高** | 两路径同 key 无协调 | 双删/误删 | 共享 StorageKeyLock 串行 | ORP-06 | — |

---

## 5. 文件系统与数据库不一致（高）

| 编号 | 风险 | 严重程度 | 发生条件 | 影响 | 防护措施 | 验收 | 决策 |
|---|---|---|---|---|---|---|---|
| R-FS-01 | DB 有引用物理缺失 | **高** | 物理误删/备份恢复不齐/跨卷中间态 | 下载 404/数据不可用 | 一致性检查（ORP-07）报告；从隔离区恢复（ORP-04）；备份同时间点+对账 | ORP-04/07/BAK-03 | — |
| R-FS-02 | 物理有 DB 无引用（孤儿） | **中** | DB 失败/删除引用后未 GC | 存储膨胀 | 独立孤儿扫描回收（安全等待期+复核） | ORP-01 | — |
| R-FS-03 | storage_key 与物理内容 hash 不符 | **高** | 篡改/写入损坏/备份不一致 | 内容寻址失效/共享错文件 | 上传重算 hash 比对；一致性检查 hash 校验；内容不可变 | ATT-09/ORP-07 | — |
| R-FS-04 | 备份 DB 与附件版本错配 | **高** | 非同时间点备份 | 恢复后引用悬空 | resource_version={db_snapshot_version,attachment_version,canon_version} 一致校验 | BAK-03 | — |
| R-FS-05 | SQLite 裸拷 db+wal+shm 快照不一致 | **高** | 用文件拷贝而非 Online Backup | 快照损坏/恢复失败 | **禁裸拷**；Online Backup API/VACUUM INTO | BAK-01 | D-09 |
| R-FS-06 | Manifest fsync 顺序错 | **高** | marker 先于资源 fsync | 崩溃后 marker 在资源不在 | fsync 顺序：资源→phase→marker | BAK-04 | — |

---

## 6. 权限与路径安全（致命/高）

| 编号 | 风险 | 严重程度 | 发生条件 | 影响 | 防护措施 | 验收 | 决策 |
|---|---|---|---|---|---|---|---|
| R-SEC-01 | 附件路径穿越 | **致命** | 用户控制 storage_key/下载路径，含 `..`/绝对路径/逃逸 symlink | 读写存储根外任意文件 | storage_key 由 hash 派生；规范化校验落存储根内；下载按 attachment.id 查 key **不接受用户路径**；拒逃逸 symlink | ATT-06/07 | — |
| R-SEC-02 | 文件名注入 | **高** | filename 含路径分隔/控制字符直接落盘 | 穿越/日志注入 | 文件名清洗仅显示名，去分隔/控制字符；落盘名用 hash | ATT-06 | — |
| R-SEC-03 | MIME 伪装上传恶意文件 | **高** | 仅信声明 MIME 不验 magic bytes | 存储恶意可执行/脚本 | 白名单 + **magic bytes 双校验**（stdlib 字节签名，不引 python-magic） | ATT-04 | D-08 |
| R-SEC-04 | SVG 内联脚本执行 | **高** | SVG 含 script/foreignObject 内联渲染 | XSS | SVG 禁内联或消毒【待审批】；前端 A2 渲染须 DOMPurify（未审批不引） | ATT-05 | **D-08** |
| R-SEC-05 | 超限文件耗尽存储 | **中** | 无大小上限 | 磁盘耗尽 DoS | 默认 10MB 可配，超限 413/400 不落盘 | ATT-03 | D-08 |
| R-SEC-06 | 错误响应泄漏敏感信息 | **高** | 回传 str(exc)/主机/端口/密码/堆栈 | 信息泄漏 | 对外**仅稳定码**（link_version_mismatch 等）；服务端日志只记异常类型脱敏 | 全部 API | — |
| R-SEC-07 | 密钥泄漏 | **致命** | 导入导出/附件配置含密钥/日志打印密钥 | 密钥外泄 | 新增配置非密钥（普通 str/int）；SecretStr 机制不变；不触模型密钥；日志脱敏 | GRD/配置 | — |

---

## 7. 旧版兼容 / 迁移（高/中）

| 编号 | 风险 | 严重程度 | 发生条件 | 影响 | 防护措施 | 验收 | 决策 |
|---|---|---|---|---|---|---|---|
| R-COMP-01 | A1-04 新增迁移破坏 0006 单 head | **高** | 为 Manifest/指针/migration_ops_log 建新表 | 违反红线 #2/迁移链断裂 | **无新迁移**：Manifest/指针/migration_ops_log 优先文件落 backend/data/ops/；若确需新表→升级独立审批本轮不建 | GRD-08 | **D-09** |
| R-COMP-02 | SQLite DROP COLUMN 版本不足 | **中** | SQLite <3.35 downgrade | RuntimeError | 0006 已检测 ≥3.35；**不用 batch_alter_table**（保 FTS5 触发器+rowid） | OPS-05 | — |
| R-COMP-03 | downgrade 丢 V2 数据误称无损 | **高** | 宣称删表列无损 | 用户误判可回滚 | 明确 Schema Rollback **丢 V2 数据非无损**；V1 核心不变；经 v2_downgrade 门禁+备份 | OPS-04 | — |
| R-COMP-04 | 旧 V1 条目无 ImportOrigin 重导覆盖 | **高** | 旧条目无来源记录，重导静默覆盖 | V1 数据丢失 | 补建 ImportOrigin + content_hash 查重提示不静默覆盖 | IMP-20 | D-02 |
| R-COMP-05 | extra_metadata/source_* 经 V1 Repository 丢失或被清空（C-01） | **高** | V1 PATCH entity 默认 `{}` 且 update 若扩展写 metadata | 导入 metadata 丢失 | 使用独立 MarkdownItemRepository；V1 KnowledgeRepository 不读写 V2 扩展字段 | IMP-02/03/R1-IMP-12 | D-02 |
| R-COMP-06 | A1-02/03 冻结套件回归 | **高** | A1-04 改动波及 codec/canonical/链接 | 冻结行为破坏 | 禁改 A1-02/03 业务；GRD-02/03 全量回归 | GRD-02/03 | — |
| R-COMP-07 | Core 独立性破坏 | **高** | 新 service.py 引 Web/ORM/IO | 核心不可复用（Nesti） | 新模块仅 stdlib+Pydantic+ports；守护扩展覆盖 | GRD-01/04 | — |

---

## 8. API 治理绕过（高）

| 编号 | 风险 | 严重程度 | 发生条件 | 影响 | 防护措施 | 验收 | 决策 |
|---|---|---|---|---|---|---|---|
| R-GOV-01 | 导入绕过 active 审核直改 | **高** | 导入服务直写 active 内容不经 ReviewService | 未审核内容上线 | active 内容变更**必须** submit(UPDATE_ITEM)→pending（202），不应用 | IMP-06 | D-01 |
| R-GOV-02 | 导入绕过 K1 链接挂接（C-03） | **高** | 导入直调 Core ReviewService（无链接钩子），不复刻 backend demote/sync | 链接损坏/反链未降级/409 未零写入 | 导入 Draft/Active approve 使用 LinkImportRestorer；导入分支不再二次普通 sync；普通治理请求保持 K1 sync；版本异写 409 整事务零写入 | IMP-14/15/SQL-06 | **D-03/C-03** |
| R-GOV-03 | 显式绑定 API 改 knowledge_item 内容绕审核 | **高** | resolve 端点误改条目内容 | 绕治理 | 显式绑定**仅链接治理列**（save_link），不改 knowledge_item 内容；active 内容变更仍走审核 | LNK-13 | — |
| R-GOV-04 | rebuild-keys 绕过门禁 A/B/C | **高** | 新写端点不经 apply_link_key_plan | 异质版本/旧快照/碰撞随机重绑 | **复用 apply_link_key_plan 十步**（门禁 A DISTINCT=={source_version} / B plan 内 / C check_plan_freshness + P2 + 步 8c），不重写 | LNK-06/07/08/09/10 | — |
| R-GOV-05 | rebuild-keys 混淆搜索索引重建 | **中** | 重建触 FTS/向量/条目 | 索引损坏/越界 | rebuild-keys **只写 knowledge_link 3 列**，步 8 守条目基线，不触 FTS/向量 | LNK-12 | — |
| R-GOV-06 | 非 HTTP 路径（CLI/导入）绕过治理 | **高** | K1 选项 B：CLI/内部调用不经路由挂接 | 链接维护缺失 | CLI/导入复用同一挂接函数（demote/sync/apply_link_key_plan），**非 HTTP 也不绕过** | SQL-06/OPS-01 | D-03 |
| R-GOV-07 | needs_manual/运维 API 无鉴权 | **中** | V1 无认证，运维端点暴露 | 未授权触发破坏性操作 | 运维 CLI 本地执行+确认门禁；needs_manual API 鉴权【待审批 auth 批次】；A1-04 不宣称已鉴权 | GC-11/OPS-03 | **D-05** |

---

## 9. 风险处置优先级

| 优先级 | 风险 | 理由 |
|---|---|---|
| **P0（开发前须决/须守）** | R-DL-01/02/03/04/05/06、R-SEC-01/07、R-COMP-05(C-01)、R-GOV-01/02 | 致命数据丢失/安全/治理绕过；C-01 未决则导入核心功能不可用 |
| **P1（开发中须故障注入取证）** | R-CON-01/02/03/05、R-FS-01/03/04、R-ATT-02/06、R-DL-07/08 | 并发/一致性/平台兼容，须真实并发+崩溃+Windows 取证 |
| **P2（开发中须回归守护）** | R-COMP-01/06/07、R-GOV-04/05、R-IMP-04 | 冻结套件/独立性/门禁复用 |
| **P3（如实记录限制，延后批次解决）** | R-IMP-03(A1-05)、R-GOV-07(auth)、R-CON-07(评估) | 不擅自补他批次逻辑，如实告警 |

---

## 10. 不可逆数据安全问题特别标注（用户要求明确标出）

1. **R-DL-01（GC 释放锁后删原始）**：A1-04 最高危路径。R5-1 持锁 quarantine 是**强制约束**，任何「释放锁后删原始」实现一律拒绝。须 GC-04/05/06 故障注入独立验收。
2. **R-DL-04（备份盲信 marker）**：恢复对账**不得盲信标记**，须三方比对。BAK-05/06 中途 kill 独立验收。
3. **R-DL-05（无备份 downgrade）**：v2_downgrade 门禁不可绕过；Alembic 纯 Schema。OPS-02/03 独立验收。
4. **R-SEC-01（路径穿越）**：storage_key 必须 hash 派生 + 规范化校验，下载不接受用户路径。ATT-06/07 真实文件系统取证。
5. **R-COMP-05（C-01 持久化缺口）**：现有 KnowledgeRepository 不落 extra_metadata/source_*，**导入幂等与保真依赖此缺口先决**（D-02）。未决前不得宣称导入功能可用。

> 以上五项为本轮**明确标出的不可逆/重大安全问题**，须 ChatGPT 审查与用户批准对应防护设计后方可进入开发。本轮**未改任何代码**，仅识别与设计防护。

---

## 11. R1 新增/重分类风险（权威补充）

| 编号 | 风险 | 严重程度 | 发生条件 | 影响 | 防护措施 | 验收 |
|---|---|---|---|---|---|---|
| R1-IMP-01 | 用 payload hash 而非来源身份作为锁键 | **高** | 同一 source document 内容变化后落入不同锁 | 并发重复导入/覆盖 | 锁键固定为 (source_instance_id, source_document_id)；payload hash 只判版本 | R1-IMP-01/02/03 |
| R1-IMP-02 | 锁等待期间状态已变化仍应用旧导入 | **高** | 两请求先后等待同身份锁，后到请求拿到锁后不重读 | 旧版本覆盖新版本 | 锁前快照 S0 + 锁内重读 S1；状态变化且 incoming 未已应用时拒绝 SOURCE_CHANGED_DURING_WAIT | R1-IMP-02 |
| R1-IMP-03 | 同一来源身份映射多个目标 item | **高** | 历史 ImportOrigin 已出现歧义 | 错误条目被覆盖/链接错绑 | 检查 source identity 对应 item_id 集合；多目标直接 SOURCE_IDENTITY_AMBIGUOUS | R1-IMP-04 |
| R1-IMP-04 | Active pending 上下文只存 Core 四字段 | **致命** | tags/metadata/附件/来源/链接 hints 未放入 review envelope | approve 静默丢数据 | ReviewRequest.payload `__a1_import` envelope；approve hook 完整应用+digest 校验 | R1-IMP-05…14 |
| R1-IMP-05 | Pending 期间提前写 ImportOrigin | **高** | submit 时写来源记录，之后 reject | 形成“已导入”假记录 | Active 仅 approve 成功事务写 ImportOrigin；pending 幂等查 ReviewRequest envelope | R1-IMP-05/06/10 |
| R1-IMP-06 | Approve hook 与审核状态分事务 | **致命** | hook 部分提交或先 commit review | review/item/tags/origin/links 不一致 | hook 必须位于 approve 首次 commit 前；异常 rollback 全部 DB 写入 | R1-IMP-08/09 |
| R1-IMP-07 | Active pending 附件在 reject 后泄漏/丢失 | **高** | pending 附件未隔离 staging 或清理失败无回收 | 正式引用污染/磁盘泄漏 | staging 独立目录；approve 后提升，reject 后清理；失败由 staging orphan sweep | R1-IMP-10/11 |
| R1-LOCK-01 | 多 Backend/CLI 同时写同一数据根 | **致命** | 无 OS 级单实例锁或入口绕过 | DB/附件损坏、备份不一致 | msvcrt/fcntl OS 锁；Backend 生命周期持有；维护 CLI 同锁；锁失败 fail closed | R1-LOCK-01…06 |
| R1-LOCK-02 | --reload/多 worker 锁归属错误 | **高** | supervisor/worker 生命周期不匹配 | 锁泄漏或双 worker writer | worker lifespan 持锁；workers=1；真实 reload 测试 | R1-LOCK-05/06 |
| R1-LOCK-03 | 外部程序绕过 OS 锁直接写 DB/附件 | **高** | 手工 SQL、另一安装目录、网络共享盘 | 单实例保证失效 | 明确不支持外部写者/多安装目录/SMB/NFS；部署检查与文档告警；多实例需独立审批 | R1-LOCK-01/02 |
| R1-BAK-01 | 在线备份与应用写入竞态 | **高** | Backend 未停止即备份 DB+附件 | DB/附件时间点错配 | 仅 Offline CLI；同一 OS 锁；Backend 活跃时拒绝 | R1-BAK-01/02 |
| R1-BAK-02 | 恢复时附件合并覆盖现有内容 | **致命** | 同路径 blob 内容不一致仍覆盖 | 数据不可逆损坏 | 先 hash 校验；冲突中止；不可变 blob 只合并不覆盖、不删除现存额外 blob | R1-BAK-03/04 |
| R1-BAK-03 | DB 切换成功但附件未就绪 | **致命** | 先切 DB 后复制附件 | 恢复后引用悬空 | 先完整合并并验证附件/quarantine/staging，再切 DB；DB 最后激活 | R1-BAK-04…10 |
| R1-BAK-04 | PG restore rename 中途崩溃 | **致命** | target→previous 后 staging→target 未完成 | 服务无法启动/数据指向不明 | offline restore journal + pg_database OID/名称对账；旧库不 DROP；可恢复命令 | R1-BAK-07…09 |
| R1-BAK-05 | 备份保留策略误删唯一可恢复包 | **致命** | 在新备份未完整校验前 prune | 无法恢复 | 新包 COMPLETE+hash 验证后才 prune；至少保留最近 5 个有效包 | R1-BAK-11 |

### 11.1 R1 旧风险修订

- 原 R-IMP-03“允许多张 pending 并仅 warning”由 R1 改为：同来源身份同 hash 复用 pending；不同 hash 且旧 pending 未解决时拒绝新导入。A1-05 防覆盖/撤回仍延期。
- 原 R-IMP-06“PG 行锁/SQLite 唯一约束”作废，改为 R1 单实例 OS 进程锁 + 来源身份 keyed lock + S0/S1 重读检测；数据库无唯一约束的事实必须保留。
- 原 R-COMP-05 的解决状态改为：采用独立 MarkdownItemRepository；V1 KnowledgeRepository 保持不变。
- 原 R-GOV-02 的“复刻普通 sync”改为：导入 ReviewRequest approve 分支调用 LinkImportRestorer；普通治理路径保持既有 K1 sync；不得对导入分支再执行第二次普通 sync。
- 原备份在线 quiesce/多实例协调方案作废；采用 Offline CLI + 同一 OS 进程锁。PG 服务可运行，但外部 DB 写者必须停止。

---

## 12. R1.1 新增风险（权威补充）

> 原风险编号与未受影响风险**保持不变**。以下为 R1.1 增补新增风险与控制要求；均为**设计要求，全部【待验证】**。
> 严重度沿用 R1.1 增补的 **P1** 口径（≈本册「高」，须开发阶段真实并发/崩溃/平台取证）；验收编号已统一加 `R1.1-` 前缀，与 acceptance-matrix §F 对齐。

| 编号 | 严重度 | 风险 | 控制措施 | 验收 |
|---|---|---|---|---|
| R1.1-R-READ-01 | P1 | V1 GET 暴露空 V2 字段，或 V1/V2 读路径分叉 | V2-only read contract；不扩展 V1 DTO/GET；V2 唯一读写路径为 `MarkdownItemRepository` + `TagRepository` | R1.1-IMP-25…27 |
| R1.1-R-ID-01 | P1 | source-instance-id 丢失/意外轮换 | 锁后首次生成；非法文件 fail-closed；backup manifest/checksum；同实例 restore 保留；clone 显式 rotate | R1.1-IMP-28…31 / R1.1-BAK-15 / R1.1-OPS-06 |
| R1.1-R-LOCK-01 | P1 | submit 与 approve 不共用身份锁 | approve 导入分支预检 envelope→同身份锁→fresh session 重读→单事务应用 | R1.1-IMP-35…38 |
| R1.1-R-LOCK-02 | P1 | keyed-lock registry 泄漏，或入口各自建 Coordinator | lifespan 单例、`app.state` 注入、引用计数清理 | R1.1-IMP-32…34 / 40 |
| R1.1-R-ASYNC-01 | P1 | 同步锁等待阻塞 event loop / Session 跨线程 | async keyed lock；同步 DB/FS 在线程池；Session 在线程池内部创建关闭；取消时不提前释放锁 | R1.1-SQL-10 / R1.1-IMP-39 |
| R1.1-R-RELOAD-01 | P1 | reload worker 交接锁冲突 | supervisor 不持锁；worker 有界 10s 重试；超时 fail-closed；workers>1 拒绝 | R1.1-LOCK-10…12 |
| R1.1-R-PATH-01 | P1 | Backend 与 CLI 使用不同锁文件 | `BACKEND_DIR.resolve()` 派生唯一绝对路径 helper | R1.1-LOCK-09 |
| R1.1-R-PG-RESTORE-01 | P1 | PG target 仍有连接时 rename 失败/半切换 | maintenance DB；禁新连接；terminate；`pg_stat_activity` 清零；失败恢复 `allow_connections` 并中止；不 DROP 旧库 | R1.1-BAK-17…19 |
| R1.1-R-STAGING-01 | P1 | staging sweep 误删 pending 附件 | review_id + envelope manifest 引用检查；复核后 quarantine；正式 blob 根排除 | R1.1-IMP-41/42 |
| R1.1-R-BLOB-01 | P1 | Restore 删除当前环境额外 blob | restore 只合并不覆盖/删除；额外 blob 先保留，过 grace 后由独立 GC 清理 | R1.1-BAK-16 |
| R1.1-R-S0S1-01 | P1 | S0 快照过期，或事务早于锁 | S0 会话关闭→身份锁→S1→写事务；确定性屏障测试 | R1.1-IMP-35 |
| R1.1-R-K1-01 | P1 | 导入 approve 分支绕过/重复触发 K1 | 仅 `__a1_import` 分支用 `LinkImportRestorer`；普通治理继续原 K1；409 整事务回滚 | R1.1-LNK-14 / R1.1-IMP-38 |

### 12.1 R1.1 与既有风险的对应

- **决策映射**：R1.1-R-READ-01↔D16-1；R1.1-R-ID-01↔D-13/G-4；R1.1-R-LOCK-01/02、R1.1-R-S0S1-01、R1.1-R-ASYNC-01↔D15-2/D15-3/FID-2；R1.1-R-RELOAD-01、R1.1-R-PATH-01↔D17-1/D17-2/D17-3；R1.1-R-PG-RESTORE-01↔BAK-1；R1.1-R-STAGING-01、R1.1-R-BLOB-01↔plan §20.6；R1.1-R-K1-01↔D-03/K1。
- R1.1-R-READ-01 **取代**任何「V1 GET 暴露 V2 字段」设想（与 D16-1 一致）；与 R-COMP-05 互补：前者防读路径分叉，后者防持久化缺口。
- R1.1-R-LOCK-01 / R1.1-R-S0S1-01 **强化** R-IMP-06；R1.1-R-LOCK-02 强化 §19.10 Coordinator 单例要求。
- R1.1-R-PG-RESTORE-01 **细化** R1-BAK-04；R1.1-R-STAGING-01 细化 R1-IMP-07 / R1-BAK-02/03；R1.1-R-BLOB-01 细化 R1-BAK-02。
- R1.1-R-ASYNC-01 / R1.1-R-RELOAD-01 / R1.1-R-PATH-01 为 R1 未覆盖的新维度（事件循环、reload、cwd 路径）。

### 12.2 R1.1 处置纪律

- 不新增 migration/table/column/index；不修改冻结 Core 端口、A1-02 Hash、A1-03 链接规则。
- 不修改 V1 `KnowledgeRepository` / `KnowledgeOut` / GET。
- Offline / Single / Strict 不变；不支持多 Backend、多 worker、多主机并发写。
- 任何测试失败优先 fail-closed，不得放宽唯一性、回滚校验或提前删除旧资源。

---

## 13. R1.2 新增风险（权威补充）

> 原 §1–§12 编号与未受影响风险**保持不变**。以下为 R1.2（D18–D21）增补新增风险与控制要求；均为**设计要求，全部【待验证】**。
> 严重度：**P0（致命）** = 可导致未授权破坏/不可逆数据丢失；**P1（高）** = 数据不一致/治理绕过/并发损坏/范围虚报；**P2（中）** = 可观测/信息泄漏。验收编号见 acceptance-matrix §G，决策见 open-decisions §K。

| 编号 | 严重度 | 风险 | 控制措施 | 验收 |
|---|---|---|---|---|
| R1.2-R-ID-01 | P1 | source / exporter 身份混淆：把当前导出实例当成文档来源，或再导出覆盖原来源身份 | 三字段语义分离；`DocumentIdentity=(source_instance_id, source_document_id)`；exporter 仅 frontmatter/manifest、**不落 DB**；导入/修改/再导出保留 source；exporter 差异不作为身份差异 | R1.2-ID-01/02/04/08 |
| R1.2-R-ID-02 | P1 | clone rotate 批量改写继承文档 source identity | rotate 仅更换本实例 exporter 身份；**禁止批量改写**继承文档 source；数据采纳（adoption）须显式确认+独立审批，A1-04 不自动执行 | R1.2-ID-03 |
| R1.2-R-ID-03 | P1 | legacy/未知来源被伪造 UUID 或静默覆盖既有条目 | 不编造身份、不推断为本实例；content_hash 查重 + duplicates 提示 + 默认 Draft；显式 target 才绑定；报告标 legacy/unknown | R1.2-ID-05/06 |
| R1.2-R-ID-04 | P1 | 为 exporter 新增 DB 列/迁移，违反 Strict migration | exporter 只存在于 frontmatter/manifest；**无新表/列/索引**；Alembic 单 head 仍 0006 | R1.2-ID-01/07；GRD-08 |
| R1.2-R-BAT-01 | P1 | Batch A 静默丢弃/忽略附件，用户误以为导入完整 | 含附件请求**显式拒绝/标记 unsupported**（固定稳定码 `ATTACHMENT_IMPORT_UNSUPPORTED`，open-decisions §L.2）；零附件写入；ImportReport 逐项标明；批量中单篇 unsupported 不拖累其余篇 | R1.2-BAT-01/03 |
| R1.2-R-BAT-02 | P1 | 批次范围虚报：A 宣称附件完成而 B 未交付；文档/报告把 B/C/D 记入 A | 四批独立出口门禁；验收/文档/提交说明统一映射；未通过本批不得进入下一批；不得以他批代替 | R1.2-BAT-03/05/06 |
| R1.2-R-BAT-03 | P1 | 附件 + Active approve 跨批半闭环：approve 成功但附件引用悬空/孤儿 | Batch B 完成附件引用 + item/tags/origin/links **同一事务**闭环；B 交付前 A 拒绝含附件 envelope（固定稳定码 `ATTACHMENT_REVIEW_UNSUPPORTED`，open-decisions §L.2），不得丢弃后批准 | R1.2-BAT-04；R1.1-IMP-38 |
| R1.2-R-ASYNC-01 | P1 | 同步锁等待阻塞 event loop，服务假死/超时 | 写入口用同步 `def` 路由（线程池）；禁止在 `async def` 内等待同步锁；ASGI 并发探针 | R1.2-ASYNC-01/08 |
| R1.2-R-ASYNC-02 | P1 | request-scoped Session 跨线程，产生未定义行为/数据损坏 | Session 在实际执行线程内创建/使用/关闭；禁止跨线程传递；S0/S1 独立短会话 | R1.2-ASYNC-02 |
| R1.2-R-ASYNC-03 | P1 | async keyed lock + `threading.Lock` 双协调架构：两锁不互斥/死锁/双写 | 单一同步 `ImportCoordinator`；lifespan 单例注入所有入口；**禁止双架构**；代码审计+运行时断言 | R1.2-ASYNC-06/07 |
| R1.2-R-ASYNC-04 | P1 | 事务早于锁，或客户端断开提前释放锁，导致旧快照覆盖/半写 | S0 关闭→获锁→S1→写事务；Commit/Rollback + Session 清理后才释放；断连/取消不提前释放；有界等待 fail-closed | R1.2-ASYNC-03/04/05 |
| R1.2-R-NET-01 | **P0（致命）** | 默认/误配监听 `0.0.0.0`/LAN，无认证暴露破坏性 API | 默认且仅允许 `127.0.0.1`；无认证时非 loopback **启动 fail-closed**（固定稳定码 `NON_LOOPBACK_WITHOUT_AUTH`），不得仅告警；解析后判断，allowlist 拒绝其余 | R1.2-NET-01/02/03/07 |
| R1.2-R-NET-02 | P1 | CORS/代理转发头被当作认证或访问控制 | 明确不是认证；禁止“带某 header 即放行”；请求矩阵验证 | R1.2-NET-04 |
| R1.2-R-NET-03 | P1 | 反向代理/隧道/端口转发绕过 loopback 假设对外暴露 | 文档明确额外暴露面与责任；未认证不得对外；远程访问等待 auth 批次+独立部署评审；不得宣称 loopback 即安全 | R1.2-NET-05 |
| R1.2-R-NET-04 | P1 | host 校验可被前缀/包含/DNS 解析绕过 | 解析 IPv4/IPv6/hostname 后判断；allowlist【提议】`127.0.0.1`/`::1`/`localhost`；解析失败 fail-closed；环境变量/配置文件/启动参数统一校验 | R1.2-NET-03/07 |
| R1.2-R-NET-05 | P2 | 启动失败/网络错误泄漏 host/port/堆栈/`str(exc)` | 对外只回稳定码与风险说明；日志脱敏（AGENTS.md §9） | R1.2-NET-06 |

### 13.1 R1.2 与既有风险的对应

- **决策映射**：`R1.2-R-ID-01…04` ↔ D18（§21.1）；`R1.2-R-BAT-01…03` ↔ D19（§21.2）；`R1.2-R-ASYNC-01…04` ↔ D20（§21.3，并**取代** R1.1 §19.10 的 async 机制，保留事件循环/线程属性）；`R1.2-R-NET-01…05` ↔ D21（§21.4，R1/R1.1 未覆盖的新维度）。
- R1.2-R-ID-01 **强化** R1.1-R-ID-01：R1.1 解决“实例 ID 丢失/轮换”，R1.2 进一步区分 source 与 exporter，防再导出覆盖来源。
- R1.2-R-BAT-01/03 **细化** R-ATT-01/02、R1-IMP-07、R1.1-R-STAGING-01：从“不能丢附件”提升为“批次 A 显式拒绝、批次 B 单事务闭环”。
- R1.2-R-ASYNC-01/02/04 **强化** R1.1-R-ASYNC-01 / R1.1-R-LOCK-01/02 / R1.1-R-S0S1-01：以同步模型替代 async 机制，属性要求不变。
- R1.2-R-NET-01…05 为**新增维度**；与 R-SEC-06/R1.1 无关，不改变“无认证、不宣称已鉴权”的既有边界。
- **未受影响**：R1/R1.1 其余风险编号、严重度与验收继续有效；R1.2 不重开 A1-02 Hash、A1-03 链接规则、Core ReviewService、V1 API。

### 13.2 R1.2 处置纪律

- 不新增 migration/table/column/index；不修改冻结 Core 端口、A1-02 Hash/Codec、A1-03 链接键重建、V1 `KnowledgeRepository`/`KnowledgeOut`/GET。
- Offline / Single / Strict 不变；不支持多 Backend、多 worker、多主机、代理后无认证公网暴露。
- 任何测试失败优先 fail-closed：拒绝非 loopback、拒绝附件、拒绝身份不清、拒绝双架构；不得静默降级、丢弃附件或放宽锁。
- 本登记为**设计防护**，非已实现/已验证；所有 R1.2 风险在开发阶段须以 acceptance-matrix §G 真实取证后才可降级。

---

## 14. R1.3 新增风险（权威补充）

> 原 §1–§13 编号、严重度与未受影响风险**保持不变**。以下为 R1.3（D22–D24）增补；均为**设计要求，全部【待验证】**，不表示已发生或已缓解。
> 严重度沿用：**P0（致命）**=可导致未授权破坏/不可逆数据丢失；**P1（高）**=数据不一致/治理绕过/并发损坏/范围虚报；**P2（中）**=可观测/信息泄漏。验收见 acceptance-matrix §H，决策见 open-decisions §L。

| 编号 | 严重度 | 风险 | 控制措施 | 验收 |
|---|---|---|---|---|
| R1.3-R-HASH-01 | P1 | exporter 泄漏进文档 Hash/canonical 输入：同内容因导出实例不同被判为新版本，触发重复导入、误审核或 `source_payload_hash` 漂移；或为“统一过滤”而擅改 A1-02 冻结 Hash/canonicalization v1；或 YAML 解析器折叠重复保留键导致用户 metadata 静默丢失 | exporter 仅传输元数据；**先剥离保留键再算 Hash、算完再注入**；frontmatter 用 `__explainlab_exporter_instance_id`、manifest 用 `exporter_instance_id`；Hash 函数/canonicalization v1 **零改动**；在 **YAML 折叠重复键之前**预扫描/loader 拒绝重复保留键；保留键冲突、manifest/frontmatter 不一致、嵌套用户 metadata 冲突均显式拒绝，且**校验先于任何 DB 写入（冲突零写入）**；用仅 exporter 不同的探针证明四类 Hash 不变 | `R1.3-HASH-01…04` |
| R1.3-R-ID-01 | P1 | 本地原生文档身份初始化错误：仅凭 `source_instance_id` 非空/`extra_metadata`/Hash 为空等推断“已合法物化”，把历史身份孤立误认作本地原生；或用伪 `ImportOrigin`/随机文档 UUID/`MAX(imported_at)`/静默覆盖解决；或物化未先落 Journal、Journal 缺失/损坏仍认领；或 `PREPARED`+旧 ID 未重查 DB 物化、未知 ID 被覆盖、已换新 ID 再轮换、`COMMITTED` 重复、第二次独立 rotate 被旧记录阻塞；或恢复未完成即分类/写身份、`COMMITTED` 恢复重写 DB、current/archive 被计两条、归档覆盖/删除历史、归档失败仍开新操作、Journal v1 字段/摘要/版本不一致、`identity_audit_digest` 只覆盖物化项或只凭 Journal 自证 DB、只对完整 ImportOrigin 计算摘要而把残缺/重复/非法记录的原始字段排除在审计外、对原始字段做 trim/大小写/UUID/hash 归一化、让读取顺序改变摘要、忽略孤儿 ImportOrigin、把多个不同合法身份对或 DB 实例不一致误判为 complete、从完整+残缺/重复+不同身份/多身份冲突中任选一条或合并字段、Canonical JSON 依赖平台默认导致非 ASCII/转义/重复键/代理项不可复现，导致来源身份被覆盖/重复建/审核错乱 | **DB 字段/`extra_metadata` 信息不足**：不得推断；合法物化必须由**恰好一条匹配的 COMMITTED MATERIALIZE Journal 记录**证明（item_id + 实例 ID + `source_document_id=item.id`），缺失/多条/冲突 → 状态 4 fail-closed。状态 2a（无 origin、实例空、无记录）首次导出按 PREPARED→条件 DB 写→重读→COMMITTED+归档；2b 重复导出/重启/克隆稳定不重写；状态 3/4 不认领、不补 `source_document_id`、不覆盖、不 adoption，报告如实标记。**禁止伪 ImportOrigin/`extra_metadata` 标记/改 Hash/随机文档 ID**。当前来源仍按 FID-2、多匹配 fail-closed。clone 前逐条物化 2a，再按九步 write-ahead Journal 轮换；`PREPARED`+旧 ID 必须重查 `materialization_items` 与摘要；`PREPARED`+新 ID 只补提交；未知/损坏 fail-closed；`COMMITTED` 归档后不重复且允许新 operation_id 的第二次独立 rotate；**启动先过 Journal 恢复门**，有效 PREPARED 先恢复，PREPARED+DB 空/等于目标才恢复、其他值/摘要不符 fail-closed，恢复前不分类/不写身份/不开新操作；COMMITTED 未归档只补归档、不写 DB；current→archive 同卷原子落位、current 幂等移除、同 op_id 同内容去重、异内容 fail、归档失败禁新操作、append-only；Journal v1 固定 `materialization_items` 字段/版本/排序/UTF-8 canonical/SHA-256/显式 null；`identity_audit_digest` **覆盖全部 knowledge_item 且每项逐条覆盖全部 `ImportOrigin` 原始记录**（未物化/已物化本地、有效/残缺/重复/非法/冲突；稳定记录 ID、原始 instance/document/payload、记录数量与完整性状态；不过滤、不去重、不归一化、读取顺序无关；孤儿 fail-closed），并按 **ImportOrigin 多记录状态判定表**汇总（`conflict` > `invalid` > `incomplete` > `duplicate` > `complete` > `none`；≥2 个不同合法身份对或唯一合法身份与 DB 实例不一致→`conflict`，完整+残缺→`incomplete` 不得提升，重复+不同身份→`conflict`，同一身份多版本→`complete`；冲突零认领/禁止任选），每次写后与恢复分支必须重读 DB 重算，rotate 前后各重算一次，不含 exporter；Canonical JSON v1 显式规定非 ASCII 原样 UTF-8、引号/反斜杠/控制字符转义、合法 surrogate 对组合/孤立代理项拒绝、对象键 code point 排序、重复键解析折叠前拒绝、非负整数限制，并用 8 组固定向量核对序列化与 SHA-256；Journal 归档缺失/损坏 fail-closed；受 OS 锁保护、失败不轮换；**无新迁移/列**；adoption 不在 A1-04 | `R1.3-ID-01…05` |
| R1.3-R-NET-01 | P1 | 本机 HTTP 被跨源/重绑定/代理头绕过：恶意网页经 DNS Rebinding 伪造 Host，或跨源表单/请求命中修改接口；宽泛 CORS 或 `X-Forwarded-*` 被误当访问控制，导致无认证的破坏性写入 | 绑定仅精确 `127.0.0.1`/`::1`（**拒绝 localhost 绑定**），非 loopback 启动 fail-closed；**精确 Host + 合法端口**校验（拒绝伪造/尾点/多 Host/错端口）；修改请求同源 Origin 校验；修改接口仅 `application/json`；**禁止宽泛 CORS**；代理头不授予访问权；DNS Rebinding 由 Host 白名单拒绝；只回稳定码不泄漏 host/port/堆栈；不新增认证依赖；Batch D 验收 | `R1.3-NET-01…06` |

### 14.1 R1.3 评级说明与既有风险关系

- **决策映射**：`R1.3-R-HASH-01` ↔ **D22**（§22.1）；`R1.3-R-ID-01` ↔ **D23**（§22.2）；`R1.3-R-NET-01` ↔ **D24**（§22.3）。验收映射见 §14 表末列与 acceptance-matrix §H。
- **R1.3-R-HASH-01（P1）**：不会直接造成不可逆丢失，但会制造身份/版本漂移与重复审核，且可能诱导修改冻结 Hash 契约；重复 YAML 键若被解析器折叠还会静默丢失用户数据，按“数据不一致/治理绕过”定 P1，**不降为 P2**。
- **R1.3-R-ID-01（P1）**：错误初始化会污染来源身份并影响幂等与审核归属；**仅凭 DB 字段/`extra_metadata` 无法区分合法物化与历史孤立（信息不足）**，因此 Journal 显式标记、状态 4“不补不覆盖”、`PREPARED`+旧 ID 的 DB 重查、启动恢复优先、Journal v1 schema/摘要校验、`identity_audit_digest` 全库投影（含每项全部 ImportOrigin 原始记录、残缺/重复/非法状态、原始字段不归一化、读取顺序无关、孤儿 fail-closed）、**多记录状态表（多合法身份/DB 不一致即 conflict、冲突零认领、不选一条）**与每次写后/恢复时 DB 重算、Canonical JSON v1 字符串/代理项/重复键固定规则与归档去重/多轮规则是必要防线。因有锁、fail-closed 与“不批量改写”约束，未定为 P0。**不因审计便利降级**。
- **R1.3-R-NET-01（P1）**：D24 的 Host/Origin/JSON 校验是在 R1.2 已 P0 的“非 loopback 暴露”之外，对本机浏览器攻击面的补充控制；R1.2-R-NET-01（P0）继续有效且**不因本章新增校验而降级**。本项按“治理/未授权写入”定 P1。
- **与 R1.2 关系**：R1.3-R-HASH-01 细化 R1.2-R-ID-01/04（身份与 Hash 分离、禁止 exporter 列）；R1.3-R-ID-01 细化 R1.2-R-ID-01/02/03（在既有字段上的初始化规则）；R1.3-R-NET-01 细化并收紧 R1.2-R-NET-02/03/04（从“允许 localhost 绑定 + 解析判断”收紧为“精确 IP 绑定 + Host/Origin/JSON”）。
- **未受影响**：R1/R1.1/R1.2 其余风险编号、严重度与验收继续有效；R1.3 不重开 A1-02 Hash/canonicalization、A1-03 链接规则、Core `ReviewService`、V1 API。

### 14.2 R1.3 处置纪律

- 不新增 migration/table/column/index；不修改 Core Hash/canonicalization v1/codec、A1-03 链接规则、Core `ReviewService`/端口、V1 `KnowledgeRepository`/`KnowledgeOut`/GET。
- Offline / Single / Strict 不变；不支持多 Backend、多 worker、多主机、代理后无认证公网暴露。
- 失败优先 fail-closed：Hash 输入不清拒绝、重复保留键/嵌套冲突零写入拒绝、身份不清/无 Journal 证据拒绝、非本机 Host/跨源请求拒绝、非 loopback 拒绝；不得静默删除用户 metadata、不得批量改写来源身份、不得在 Journal 未落盘时替换 ID、不得在恢复完成前分类/写身份、不得把 current 与 archive 计为两条有效记录、不得归档覆盖/删除历史或在归档失败后开新操作、不得把原子替换等同于断电持久、不得放宽 CORS；不得让 `identity_audit_digest` 只覆盖物化项或只凭 Journal 自证 DB，不得只审计完整 ImportOrigin 而跳过残缺/重复/非法记录，不得对其原始字段做静默归一化或让读取顺序影响摘要，不得忽略孤儿 ImportOrigin，不得把多个不同合法身份对或 DB 实例不一致误判为 complete，不得从完整+残缺/重复+不同身份/多身份冲突中任选、合并或猜测来源，不得依赖平台默认 JSON 序列化/解析行为（含重复键折叠、非 ASCII 转义、孤立 surrogate）。
- 本登记为**设计防护**，非已实现/已验证；所有 R1.3 风险须以 acceptance-matrix §H 真实取证后才可降级；**D24 归 Batch D，不得因此阻塞 Batch A 非附件开发**。

