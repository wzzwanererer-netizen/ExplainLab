# ExplainLab V2 · A1-04 验收矩阵

> 状态：**R1.3 修订验收规格，非已执行结果**（R1 / R1.1 / R1.2 历史保留）。
> **R1 架构修订说明（2026-11-21）**：本文件已纳入 A1-04 第一轮独立技术核验后的架构裁决。本文原始章节中与文末「R1 权威修订」冲突的内容，以 R1 为准；R1 未覆盖的原设计继续有效。本文仍是**设计文件，不是实现或测试通过证明**。R1 修订未经用户阶段级批准前，不得据此启动业务代码开发。
> **R1.1 增补（2026-11-21）**：已追加 §F（R1.1-* 专项验收，全部【待验证】）；决策依据见 `open-decisions` §J 与 `implementation-plan` §20。原 A–E 与 R1 编号全部保留，不覆盖、不删减、不弱化。
> **R1.2 增补（2026-11-21）**：已追加 §G（R1.2-ID / R1.2-BAT / R1.2-ASYNC / R1.2-NET，全部【待验证】）；决策依据见 `implementation-plan` §21、`open-decisions` §K、`risk-register` §13。原 A–F 与 R1/R1.1 编号全部保留，不重编号、不删减、不弱化。**本轮未执行任何测试。**
> **R1.3 增补（2026-11-21）**：已追加 §H（R1.3-HASH / R1.3-ID / R1.3-NET，共 15 项，全部【待验证】）；决策依据见 `implementation-plan` §22、`open-decisions` §L、`risk-register` §14。原 A–G 与 R1/R1.1/R1.2 编号及断言全部保留，不重编号、不删改。R1.3-NET 在**请求侧**扩展并收紧 R1.2-NET-03 的绑定允许集合（`localhost` 不再允许作为绑定配置），旧行作为历史保留。已按 ChatGPT 最终独立审计完成有限修正（HASH-03 三类冲突/零写入、ID-02/03 状态 2a/2b/3/4 与 Journal 证据、ID-05 九步 Journal/归档/多轮/崩溃恢复）；**第二轮 D23 有限修正未新增编号，未改变 15 项，未执行任何测试**；**第三轮定点修正**仅在既有 ID-02/03/05 内补充 Journal 恢复优先、归档转换/去重和 v1 数据契约验收；**第四轮最终审计修正**仅在既有编号内补充 `identity_audit_digest` 全库来源身份投影/DB 重算验收，以及 Canonical JSON v1 字符串/代理项/重复键规则与 8 组固定向量，**不新增编号**；**第五轮最终定点修正**仅在 ID-02/03/05 内补充**每项全部 `ImportOrigin` 原始记录（含残缺/重复/非法）逐条审计**、原始字段不归一化、读取顺序无关、孤儿 fail-closed 的判别验收，**不新增编号**；**第六轮最终冻结前定点修正**仅在 ID-02/03/05 内补充 **ImportOrigin 多记录状态判定表/互斥组合优先级/冲突零认领/DB 身份不一致**验收，仍**不新增编号**。
> 所有项当前为【待验证】，进入开发后须用真实 SQLite / 真实 PG / 真实文件系统 / 故障注入取证，**不得宣称已通过、不得用假数据或离线 SQL 冒充**。
> 配套：`V2-A1-04-implementation-plan.md`（§14 测试方案 / §15 验收标准）、`V2-A1-04-risk-register.md`（风险编号交叉引用）。
> 双方言约定：SQLite = tmp_path + `Base.metadata.create_all`（conftest 模式）；PG = `EXPLAINLAB_PG_TEST_URL` 门控（未设置整模块 skip，设置后真实在线 Alembic 迁移 + 真实 SQL）。命令 `uv run pytest -o addopts="--import-mode=importlib"`（**禁 -o addopts=""**）；`uv run ruff check`（**禁 format**）。
> 列含义：**并发**=是否需多线程/多进程/双 Worker 竞争；**真实FS**=是否需真实临时目录文件操作（非 mock）；**故障注入**=是否需模拟崩溃/事务失败/占用/kill。

---

## A. Markdown 导入导出（IMP）

> **R1.2 D19 归属注记**：本段 `IMP-19`（导入含附件清单）与任何附件/staging 断言归 **Batch B**；Batch A 遇含附件请求须显式拒绝/标记 unsupported（验收 §G.2 `R1.2-BAT-01`），**不得宣称附件导入完成**。其余 IMP 项仍按 Batch A 非附件范围执行。

| 编号 | 测试输入 | 预期结果 | SQLite 验证法 | PostgreSQL 验证法 | 失败条件 | 并发 | 真实FS | 故障注入 |
|---|---|---|---|---|---|---|---|---|
| IMP-01 | 正常态 .md（title/content/tags/status=draft）单篇导入 | 创建 draft 条目，content_hash/payload_hash 与 codec 一致，ImportReport.created=1 | TestClient POST /knowledge/import + 查 DB | 同左（真实 PG） | 条目未建/hash 不符/report 缺字段 | 否 | 是（读上传文件） | 否 |
| IMP-02 | 含未知 frontmatter 键（x_custom）导入 | extra_metadata 保留未知键，payload_hash 含之，再导出往返不丢 | 查 knowledge_item.extra_metadata | 同左 | extra_metadata 空/未知键丢失（**C-01 未解决则此项必失败**） | 否 | 是 | 否 |
| IMP-03 | 同一入站文件重复导入两次 | 第二次 skipped（源 payload_hash==持久化 source_payload_hash），不新建/不改 | 查 ImportOrigin + item 计数 | 同左 | 第二次 created/updated 而非 skipped | 否 | 是 | 否 |
| IMP-04 | 目标 status/version 已再生后重导同一源文件 | 仍 skipped（幂等权威是入站源 hash 非目标再生 hash） | 先改目标再重导 | 同左 | 误判 updated | 否 | 是 | 否 |
| IMP-05 | 源文件正文变化后重导（同 id） | content_hash 异 → 分类内容变更；draft 直改 / active→审核 | 比对 content_hash + status | 同左 | 静默覆盖 active/未分类 | 否 | 是 | 否 |
| IMP-06 | active 条目导入 title/content 变更 | ReviewService.submit(UPDATE_ITEM)→pending 审核单，**不应用**，report.pending_review+review_ids | 查 review_request pending | 同左（真实 PG） | 直改 active/绕过审核 | 否 | 是 | 否 |
| IMP-07 | 仅 tags/extra_metadata 变化导入 | 低风险直改 + TagChangeLog 留痕，非内容审核 | 查 tag_change_log append | 同左 | 触发内容审核/无留痕 | 否 | 是 | 否 |
| IMP-08 | 仅时间戳/version 变化导入 | 非内容变更（content_hash 同），不触发审核 | 比对 content_hash | 同左 | 误判内容变更 | 否 | 是 | 否 |
| IMP-09 | 跨实例导入（source_instance_id 异）原 active 文档 | 默认 Draft + status_changes 告警「active→draft」 | 查 item.status + report.status_changes | 同左 | 保留 active/无告警 | 否 | 是 | 否 |
| IMP-10 | 无 id 文档导入，content_hash 与既有条目同 | duplicates 提示，**不静默覆盖**，分配新 id 或跳过（按策略） | 查 duplicates + 既有条目未改 | 同左 | 静默覆盖既有 | 否 | 是 | 否 |
| IMP-11 | 批量导入 N 篇，其中第 k 篇畸形 | 第 k 篇 errors + rollback 该事务，其余成功，**非全有全无** | 查 report.errors + 各条目 | 同左 | 整批回滚/第 k 篇半写入 | 否 | 是 | 是（单篇失败） |
| IMP-12 | frontmatter CONFLICT 态导入（resolution=None） | 保留原始块+未知，conflicts/warnings 告警，**不称完全无损** | 查 report.conflicts + frontmatter_state | 同左 | 静默再生/称无损 | 否 | 是 | 否 |
| IMP-13 | canonicalization_version 不一致源导入 | require_comparable_versions 抛错→降级 content_hash+字段级，**不静默比 hash** | 构造异版本源 | 同左 | 直接比 hash/静默 | 否 | 是 | 否 |
| IMP-14 | 导入含 links（target_id 有效/无效/多义） | LinkImportRestorer：有效单 target 绑定优先；无效→warning+fallback；多义→CONFLICT；孤儿提示→无行+warning | 查 knowledge_link + report.unresolved_links | 同左（真实 PG） | 随机重绑/丢绑定优先 | 否 | 是 | 否 |
| IMP-15 | 导入触发链接版本异写 | 409 link_version_mismatch，**整文档事务零写入** | 构造异版本 + 查无写入 | 同左 | 部分写入/非 409 | 否 | 是 | 否 |
| IMP-16 | 导出单篇 GET /knowledge/{id}/markdown | text 与 codec.dump 一致，tags/extra_metadata/sources/links/attachments 回填 | 比对往返 hash | 同左 | 字段丢失/hash 异 | 否 | 是 | 否 |
| IMP-17 | 批量导出 POST /knowledge/export | 打包清单含各 content_hash，manifest 完整 | 解包校验 | 同左 | 清单缺项 | 否 | 是 | 否 |
| IMP-18 | 同来源身份并发导入（两请求、同 hash） | 单实例 keyed lock 串行；仅一条应用记录，第二请求 skipped/reused pending；不依赖 DB 唯一约束 | 双线程/双请求 + SQLite 锁前后快照 | 双请求真实 PG，单 Backend 实例 | 重复 origin/item 或重复 pending | **是** | 是 | 是 |
| IMP-19 | 导入含附件清单 | 附件内容寻址共享 + 引用行（见 ATT/GC），report 含附件结果 | 查 attachment + storage_key | 同左 | 附件丢失/重复物理 | 否 | 是 | 否 |
| IMP-20 | 旧 V1 条目（无 ImportOrigin）重导 | 补建 ImportOrigin + content_hash 查重提示，不静默覆盖 | 查 ImportOrigin 新建 | 同左 | 静默覆盖/无补建 | 否 | 是 | 否 |

---

## B. 附件生命周期与存储（ATT / LCK / GC / ORP / BAK）

### B.1 上传/下载/删除（ATT）

| 编号 | 测试输入 | 预期结果 | SQLite 验证法 | PostgreSQL 验证法 | 失败条件 | 并发 | 真实FS | 故障注入 |
|---|---|---|---|---|---|---|---|---|
| ATT-01 | 上传合法文件（≤上限，白名单 MIME） | sha256=storage_key，物理落分片目录，attachment 引用行，size/mime/filename 正确 | 真实 tmp 存储根 + 查 DB | 同左 | hash 不符/未落盘/行缺 | 否 | **是** | 否 |
| ATT-02 | 上传相同内容两附件（不同 item） | 物理**共享一份**（storage_key 同），两引用行，COUNT==2 | 查物理文件数==1 + COUNT | 同左 | 物理重复/计数错 | 否 | **是** | 否 |
| ATT-03 | 上传超限文件（>max_size） | 413/400 拒绝，**不落盘** | 查无物理文件 | 同左 | 落盘/未拒 | 否 | 是 | 否 |
| ATT-04 | 上传 MIME 不符（magic bytes 与声明异） | 拒绝（白名单+magic 双校验） | 构造伪装文件 | 同左 | 接受伪装 | 否 | 是 | 否 |
| ATT-05 | 上传 SVG（按策略） | deny_inline/消毒【待审批 D-08】，不内联执行 | 查策略生效 | 同左 | 内联未消毒 | 否 | 是 | 否 |
| ATT-06 | 文件名含 `../`/绝对路径/控制字符 | 清洗为安全显示名，storage_key 由 hash 派生，**穿越防护** | 查落点在存储根内 | 同左 | 逃逸存储根 | 否 | **是** | 否 |
| ATT-07 | 下载 GET /attachments/{id} | 按 id 查 storage_key 短打开返回字节，**不接受用户路径** | 比对字节 | 同左 | 路径注入/字节异 | 否 | 是 | 否 |
| ATT-08 | 删除引用 DELETE /attachments/{id} | 删引用行（**不删物理**），COUNT 减 1；COUNT==0→enqueue gc_task(pending) | 查行删 + 物理在 + gc_task | 同左 | 删物理/无 gc_task | 否 | **是** | 否 |
| ATT-09 | 内容完整性：上传后重算 hash | 与 storage_key 一致；篡改物理→检测不一致 | 重算比对 | 同左 | 篡改未检出 | 否 | 是 | 是（篡改） |
| ATT-10 | 并发上传相同内容（双请求） | StorageKeyLock 串行物理写，仅一份物理，两引用行 | 真实并发 + 锁 | advisory 并发 | 物理竞争/损坏 | **是** | **是** | 否 |
| ATT-11 | 上传中 DB 事务失败 | 物理成孤儿，**不插引用行**，独立孤儿扫描回收 | 注入 DB 失败 | 同左 | 半引用/孤儿不回收 | 否 | **是** | **是** |
| ATT-12 | 上传中物理失败（rename 失败） | **不插 DB**，failed_retryable/告警 | 注入物理失败 | 同左 | DB 有行物理无 | 否 | **是** | **是** |

### B.2 StorageKeyLock 双方言（LCK）

| 编号 | 测试输入 | 预期结果 | SQLite 验证法 | PostgreSQL 验证法 | 失败条件 | 并发 | 真实FS | 故障注入 |
|---|---|---|---|---|---|---|---|---|
| LCK-01 | acquire 新 storage_key | 返回 StorageLease(owner,token,expires)，storage_lock 行 | 真实 SQLite 短事务 | advisory lock 获取 | 无锁/无行 | 否 | 否 | 否 |
| LCK-02 | 两 owner 竞争同 key | 仅一 acquire 成功，另一 None（PK/条件更新） | 真实双线程/双进程 | advisory 互斥 | 双获锁 | **是** | 否 | 否 |
| LCK-03 | 租约过期后他人接管 | 过期可被接管，**lease_token 单调递增** | 推进时间 + 条件 UPDATE | advisory 崩溃释放后重获 | token 回退/双活 | **是** | 否 | 是（过期） |
| LCK-04 | renew 心跳（owner+token 匹配） | rowcount==1 续租成功，expires 延后 | 真实续租 | advisory 无需续租（验证语义） | 续租失败未中止 | 否 | 否 | 否 |
| LCK-05 | renew 失配（旧 token/被接管） | rowcount==0 → **立即中止不可逆物理操作** | 构造失配 | 同左 | 旧 Worker 继续删 | **是** | **是** | **是** |
| LCK-06 | release（owner+token 匹配） | rowcount==1 释放；失配==0 不释放他人锁 | 真实释放 | advisory unlock | 误释他人锁 | **是** | 否 | 否 |
| LCK-07 | 持锁进程崩溃 | SQLite 租约到期自动可接管；PG advisory **会话结束自动释放** | kill 进程 + 过期 | kill 会话 | 锁永久滞留 | **是** | 否 | **是** |
| LCK-08 | TOCTOU 边界（锁与物理间隙） | 诚实记录降低非消除；每不可逆步骤前 verify(owner+token) | verify 调用断言 | 同左 | 未 verify 即删 | **是** | **是** | **是** |
| LCK-09 | 严格互斥需求降级 | 单写者/库级串行降级路径【待审批 D-04】 | 降级模式验证 | N/A | 宣称严格互斥 | 否 | 否 | 否 |

### B.3 GC 状态机与 quarantine（GC）

| 编号 | 测试输入 | 预期结果 | SQLite 验证法 | PostgreSQL 验证法 | 失败条件 | 并发 | 真实FS | 故障注入 |
|---|---|---|---|---|---|---|---|---|
| GC-01 | enqueue pending + worker 认领 | status pending→running，lease_token+1/attempts+1 | 短事务条件 UPDATE rowcount==1 | FOR UPDATE SKIP LOCKED | 双认领 | **是** | 否 | 否 |
| GC-02 | 双 Worker 竞争同 task | **仅一认领成功**，另一 None | 真实双 Worker | SKIP LOCKED 双 Worker | 双执行 | **是** | 否 | 否 |
| GC-03 | 持锁复核引用>0 | status→**cancelled**（终态），**不删任何文件**，释放锁 | COUNT>0 构造 | 同左 | 删文件/非 cancelled | 否 | **是** | 否 |
| GC-04 | 持锁复核引用==0 | **持锁**原子 rename 原始→隔离区，记录 quarantine_path/quarantined_at（status running） | 真实 rename + 查记录 | 同左 | 释放锁后才删原始 | 否 | **是** | 否 |
| GC-05 | purge（释放锁后，仅隔离区） | 安全等待期后**再次持锁复核==0+fencing**→删**隔离区**→done | mtime 阈值 + 复核 | 同左 | 删原始路径/未复核 | 否 | **是** | 否 |
| GC-06 | purge 前引用回升 | 隔离区文件**恢复回原始**或 cancelled，**不删** | 回升引用构造 | 同左 | 误删被引用文件 | **是** | **是** | **是** |
| GC-07 | quarantine 后崩溃 | 隔离区残留由孤儿扫描识别安全 purge；DB 有引用原始缺失→从隔离区找回 | kill + 扫描 | 同左 | 残留不清/误删 | **是** | **是** | **是** |
| GC-08 | 瞬时失败 attempts<max | failed_retryable + next_retry_at 退避→到期回 pending | 注入瞬时失败 | 同左 | 无退避/直接 permanent | 否 | 否 | **是** |
| GC-09 | attempts≥max/不可重试 | failed_permanent→needs_manual | 注入持续失败 | 同左 | 无限重试/误删 | 否 | 否 | **是** |
| GC-10 | 旧 Worker 恢复（token 已被接管） | 每不可逆步骤前 verify 失配→**中止** | 构造旧 token | 同左 | 旧 Worker 删文件 | **是** | **是** | **是** |
| GC-11 | needs_manual 人工恢复 | 人工→pending 或 cancelled，歧义/损坏不自动删 | 人工接口 | 同左 | 自动删歧义文件 | 否 | **是** | 否 |
| GC-12 | 引用数 DB 派生（无计数器） | COUNT(attachment WHERE storage_key) 始终权威，无独立计数列 | 查无计数列 + COUNT | 同左 | 计数器漂移 | 否 | 否 | 否 |

### B.4 独立孤儿扫描与一致性（ORP）

| 编号 | 测试输入 | 预期结果 | SQLite 验证法 | PostgreSQL 验证法 | 失败条件 | 并发 | 真实FS | 故障注入 |
|---|---|---|---|---|---|---|---|---|
| ORP-01 | DB 事务失败遗留物理孤儿（无 gc_task） | 独立扫描识别（口径 B）→持锁复核==0→quarantine→等待期 purge | 注入失败 + 扫描 | 同左 | 孤儿永不清 | 否 | **是** | **是** |
| ORP-02 | 扫描排除上传临时文件 | temp 命名模式**不被误回收** | 构造 temp + 扫描 | 同左 | 误删 temp | **是** | **是** | 否 |
| ORP-03 | 安全等待期内文件 | **不 purge**（mtime 阈值未到） | 新文件 + 扫描 | 同左 | 提前 purge | 否 | **是** | 否 |
| ORP-04 | DB 有引用而原始物理缺失 | 从隔离区**恢复**原始（若存在），告警 | 删原始 + 扫描 | 同左 | 不恢复/误判孤儿 | 否 | **是** | **是** |
| ORP-05 | 隔离区残留（quarantine 后崩溃） | 扫描识别 + 安全 purge（复核==0） | 构造残留 | 同左 | 残留不清 | 否 | **是** | **是** |
| ORP-06 | 扫描与 GC 并发同 key | StorageKeyLock 串行，不双删/不误删 | 真实并发 | advisory | 竞争误删 | **是** | **是** | **是** |
| ORP-07 | DB↔物理一致性检查 | 报告：DB 有物理无 / 物理有 DB 无 / hash 不符 三类 | 全量比对 | 同左 | 漏报 | 否 | **是** | 否 |

### B.5 备份恢复与 Manifest（BAK）

| 编号 | 测试输入 | 预期结果 | SQLite 验证法 | PostgreSQL 验证法 | 失败条件 | 并发 | 真实FS | 故障注入 |
|---|---|---|---|---|---|---|---|---|
| BAK-01 | SQLite 一致性快照 | Online Backup API/VACUUM INTO（**禁裸拷 db+wal+shm**），快照可打开 | 真实备份 + 打开 | N/A | 裸拷/快照损坏 | 否 | **是** | 否 |
| BAK-02 | PG 一致性快照 | Offline CLI 使用 pg_dump --format=custom，staging restore 可恢复；不依赖 pg_basebackup | N/A | 真实 pg_dump + pg_restore | 快照不一致/版本不兼容 | 否 | **是** | 否 |
| BAK-03 | DB+附件同时间点备份 | resource_version={db_snapshot_version,attachment_version,canon_version} 一致 | 比对版本 | 同左 | 版本错配 | 否 | **是** | 否 |
| BAK-04 | Offline Manifest/journal 正常恢复 | prepared→staging_verified→attachments_merged→database_switched→verified→committed；附件先合并，DB 最后切换，fsync 顺序资源→journal→marker | 查 journal + DB hash | Staging DB + pg_database OID | phase 与真实资源不符/未 fsync | 否 | **是** | 否 |
| BAK-05 | 恢复切换中途崩溃（无 marker） | 三方对账（manifest vs DB 实际 vs 附件实际）→**回滚旧 generation** | kill + 对账 | 同左 | 盲信标记/半切换 | 否 | **是** | **是** |
| BAK-06 | 有 marker 但对账不一致 | **不盲信标记**→回滚或可验证前滚（仅幂等可补全+校验过） | 构造不一致 | 同左 | 盲信 marker | 否 | **是** | **是** |
| BAK-07 | PG staging database 激活 | Backend 停止；restore 到独立 staging DB，确认目标无连接后 rename target→previous、staging→target；保留 previous | N/A | 真实 PG staging/rename/OID 对账 | 未关闭连接仍切换/旧库被删 | 否 | **是** | **是** |
| BAK-08 | Windows SQLite DB 文件替换 | 所有 DB 句柄关闭；同卷 os.replace 原子替换 live DB；previous generation 保留 | Windows 真实环境 | N/A | 句柄未关闭/旧库丢失/非原子跨卷 | 否 | **是** | **是** |
| BAK-09 | Windows 占用文件 rename/delete | 关闭句柄 + 指数退避重试→仍失败 failed_retryable，**不强删** | Windows 占用注入 | N/A | 强删/未退避 | 否 | **是** | **是** |
| BAK-10 | GC quarantine 跨卷 | 配置强制存储根与 quarantine 同卷；若无法满足则拒绝启动 GC，不执行 copy+delete 冒充原子 rename | 跨卷构造 | 同左 | 跨卷仍执行删除/宣称原子 | 否 | **是** | **是** |
| BAK-11 | 备份中途失败 | 清单不全/hash 不符判废，正式 intact | 注入失败 | 同左 | 废备份被用 | 否 | **是** | **是** |
| BAK-12 | 旧 generation 资源保留 | 恢复后旧资源保留至确认，不立即删 | 查旧资源在 | 同左 | 提前删旧 | 否 | **是** | 否 |

---

## C. 链接用户操作与运维 API（LNK / OPS）

| 编号 | 测试输入 | 预期结果 | SQLite 验证法 | PostgreSQL 验证法 | 失败条件 | 并发 | 真实FS | 故障注入 |
|---|---|---|---|---|---|---|---|---|
| LNK-01 | POST /knowledge/{id}/links/resolve（有效 target） | bind_explicit→save_link，resolution=resolved，target_id 绑定 | TestClient + 查 link | 同左（真实 PG） | 未绑定/绕守卫 | 否 | 否 | 否 |
| LNK-02 | 显式绑定 archived target | 允许 + 告警（archived 确认参数）【待审批 D-05】 | 查告警 + 绑定 | 同左 | 拒绝/无告警 | 否 | 否 | 否 |
| LNK-03 | 显式绑定跨空间 target | 允许 + cross_space 告警 + 用户确认 | 查 resolution=cross_space | 同左 | 静默跨空间 | 否 | 否 | 否 |
| LNK-04 | 候选查询 GET resolve-candidates | 返回候选（已有 A1-03，回归不破坏） | 查候选 | 同左 | 候选错/回归 | 否 | 否 | 否 |
| LNK-05 | POST /knowledge/{id}/links/reresolve | 只重试 missing/ambiguous，resolved/bound 不动 | 构造 missing + 重解析 | 同左 | 重绑已 bound | 否 | 否 | 否 |
| LNK-06 | CLI rebuild_link_keys（同版本） | 获取 OS 进程锁；apply_link_key_plan 十步，updated/unchanged 正确，碰撞组报告；无 HTTP 全局写入口 | 真实 CLI + 查 3 列 | 同左（表锁） | 绕过进程锁/触 FTS/向量/条目 | 否 | 否 | 否 |
| LNK-07 | rebuild-keys 碰撞（同 key 多 target） | ambiguous/conflict **不随机重绑**，碰撞报告 | 构造碰撞 | 同左 | 随机重绑 | 否 | 否 | 否 |
| LNK-08 | rebuild-keys 门禁 A（版本异质） | DISTINCT!={source_version}→拒绝，零写入 | 构造异质 | 同左 | 异质通过 | 否 | 否 | 否 |
| LNK-09 | rebuild-keys 并发（PG 窗口②） | LOCK TABLE SHARE ROW EXCLUSIVE + FOR UPDATE 关闭读阶段窗口 | N/A | 真实并发 + 表锁 | 窗口②漏 | **是** | 否 | 否 |
| LNK-10 | rebuild-keys 并发（SQLite P2） | 六字段乐观前置 rowcount==1 + 步 8c no-op 复核 | 真实并发 + P2 | N/A | 旧快照覆写 | **是** | 否 | 否 |
| LNK-11 | 重建结果查看 GET rebuild-report | 返回 LinkRebuildReport（碰撞/拒绝/updated/unchanged） | 查报告 | 同左 | 报告缺 | 否 | 否 | 否 |
| LNK-12 | rebuild-keys **不触搜索索引** | FTS/向量/knowledge_item 基线不变（步 8 守） | 比对索引 | 同左 | 索引被改 | 否 | 否 | 否 |
| LNK-13 | 显式绑定**不绕过治理** | 链接治理列操作不改 knowledge_item 内容，active 内容变更仍走审核 | 查 item 未改 | 同左 | 绕审核改内容 | 否 | 否 | 否 |
| OPS-01 | CLI rebuild_link_keys | 冻结写→plan→apply→报告落 backend/data/ops/→碰撞留痕 | 真实 CLI 运行 | 同左 | 无报告/未冻结 | 否 | **是** | 否 |
| OPS-02 | CLI v2_downgrade 门禁（备份未成） | **拒绝** downgrade | 注入备份失败 | 同左 | 无备份即 downgrade | 否 | **是** | **是** |
| OPS-03 | CLI v2_downgrade 门禁（未确认） | **拒绝**（告知删 V2 数据） | 未确认 | 同左 | 未确认即删 | 否 | 否 | 否 |
| OPS-04 | CLI v2_downgrade 正常 | 备份→校验→确认→记录 migration_ops_log→downgrade→后置检查；V1 核心不变 | 真实 downgrade + 查 V1 | 同左 | V1 受损/无记录 | 否 | **是** | 否 |
| OPS-05 | 0006 downgrade 双方言 | SQLite 原生 DROP COLUMN（≥3.35，保 FTS5 触发器）；PG drop_column | 真实 down/up | 真实 down/up | FTS5 触发器丢/不可逆 | 否 | 否 | 否 |

---

## D. SQLite 并发与现有风险（SQL）

> D 方向以**评估 + 最小改动建议**为主，多数为分析判定项而非新功能测试；凡涉及改动须先审批（不擅改全局事务管线）。

| 编号 | 测试输入/分析对象 | 预期结果/判定 | SQLite 验证法 | PostgreSQL 验证法 | 失败条件 | 并发 | 真实FS | 故障注入 |
|---|---|---|---|---|---|---|---|---|
| SQL-01 | 读阶段窗口②（链接重建读后写前） | **正确性**：P2 六字段乐观前置 + 步 8c 复核兜底；**互斥性**：读阶段不锁（诚实 no-op）；**活性**：不阻塞读 | 真实并发读改写 | 表锁关闭（对照） | 旧快照覆写未被 P2 拦 | **是** | 否 | 否 |
| SQL-02 | SQLITE_BUSY 活性 | busy_timeout=5000 重试；高并发写不永久饥饿 | 真实并发压测 | N/A | 永久 BUSY/死锁 | **是** | 否 | 否 |
| SQL-03 | busy_timeout 必要性评估 | 5000ms 现状评估，是否需调【待审批 D-09】 | 压测对比 | N/A | 活性不足 | **是** | 否 | 否 |
| SQL-04 | BEGIN IMMEDIATE 必要性 | **不启用**（需全局事务管线改动）；评估写冲突场景由短事务+busy_timeout 覆盖 | 分析 + 压测 | N/A | 擅改全局管线 | 否 | 否 | 否 |
| SQL-05 | WAL 适配性评估 | 现状 rollback-journal（**C-04**）；WAL 利弊 + 备份依赖；**不擅自启用** | 分析（若启用须独立审批+回归） | N/A | 擅改日志模式 | 否 | 否 | 否 |
| SQL-06 | K1 选项 B 非 HTTP 绕过 | 导入路径使用 `LinkImportRestorer`（普通治理 K1 不变），**不经 HTTP 也不绕过**；409 整事务零写入 | 导入路径断言挂接 | 同左 | 导入绕链接维护/二次普通 sync | 否 | 是 | 否 |
| SQL-07 | StorageKeyLock SQLite TOCTOU 三维 | 正确性依赖单实例 OS lock + 进程内 keyed lock + DB lease fencing；外部写者/多实例不支持；短事务不长期持库锁 | 真实并发 + 边界 | advisory 对照 | 宣称多实例/外部写者下严格互斥 | **是** | **是** | **是** |
| SQL-08 | GC 短事务认领活性 | 条件 UPDATE 短事务立即 commit，不长期持库级写锁 | 真实双 Worker 压测 | SKIP LOCKED 对照 | 库锁滞留 | **是** | 否 | 否 |
| SQL-09 | 附件物理操作在 DB 写事务外 | 物理 IO 不持库级写锁（租约逻辑锁协调） | 断言事务边界 | advisory 会话级 | 物理在写事务内 | 否 | **是** | 否 |

---

## 守护与回归（GRD，不可弱化）

| 编号 | 对象 | 预期 | 验证法 | 失败条件 |
|---|---|---|---|---|
| GRD-01 | Core 独立性守护 | test_core_has_no_web_framework_dependency 干净子进程导入全部核心模块（含新 service.py）无 fastapi/starlette/flask/django | 根级 pytest | 守护被删/弱化/新模块引 Web 库 |
| GRD-02 | A1-02 冻结套件 | 291 项不回归（codec/canonical/三 Hash） | 根级 pytest | 任一回归 |
| GRD-03 | A1-03 链接套件 | 链接服务/重建/K1/K2/P2/no-op/phantom 不回归 | 根级 pytest（SQLite+PG） | 任一回归 |
| GRD-04 | 零新增必需依赖 | A1 仅 stdlib+Pydantic+httpx（Core）；backend 既有 SQLAlchemy/psycopg/Alembic/FastAPI | 依赖清单核对 + 干净副本安装 | 引入未审批依赖 |
| GRD-05 | ruff | `uv run ruff check` 通过（**禁 format**） | ruff check | format 漂移/检查失败 |
| GRD-06 | 根级收集 | `uv run pytest -o addopts="--import-mode=importlib"` 一次性收集 backend+core | 根级 pytest | 用 -o addopts="" / 排除整目录 |
| GRD-07 | 前端 | npm run test/typecheck/build 不破坏（A1-04 不动前端则验证未回归） | 前端三命令 | 回归 |
| GRD-08 | 无新迁移 | Alembic 单 head 仍 0006；A1-04 不新增 versions | alembic heads | 新增迁移（红线 #2） |
| GRD-09 | 审计快照 | tag_change_log append-only，删除后 item_id_snapshot/title_snapshot 保留 | 查审计行 | 身份丢失/可改 |

---

## E. R1 架构修订专项验收（R1-IMP / R1-LOCK / R1-BAK）

> 以下均为新增验收，全部【待验证】。任何测试不得用 mock 代替要求的真实 DB/真实文件系统/真实 Windows 进程。

### E.1 来源幂等与审核批准

| 编号 | 测试输入 | 预期结果 | SQLite 验证法 | PostgreSQL 验证法 | 失败条件 | 并发 | 真实FS | 故障注入 |
|---|---|---|---|---|---|---|---|---|
| R1-IMP-01 | 同一 source identity + 同一 payload hash 双请求 | 第二请求 skipped；仅一条有效 origin 版本/目标 item | 两线程同步屏障，检查 DB | 两连接/两请求，单 Backend | 重复 origin 或 item | 是 | 否 | 是 |
| R1-IMP-02 | 同一 source identity、不同 hash 并发到达 | 锁前后快照发现状态变化；后到请求返回 SOURCE_CHANGED_DURING_WAIT，不覆盖先到版本 | 双线程确定性交错 | 真实 PG 同样验证 | 最终状态被无提示覆盖 | 是 | 否 | 是 |
| R1-IMP-03 | 两个 source identity 不同但 payload hash 相同 | 不互相持锁；按无 id/content hash 规则返回 duplicates，不错误合并来源身份 | 并发屏障 | 真实 PG | 锁键错误使用 payload hash | 是 | 否 | 否 |
| R1-IMP-04 | 同 identity 查出多个不同 item_id | SOURCE_IDENTITY_AMBIGUOUS，零写入 | 构造多 origin | 真实 PG | 自动挑选任一 item | 否 | 否 | 否 |
| R1-IMP-05 | Active 导入提交 pending | ImportOrigin 不写；ReviewRequest.payload 含完整 __a1_import envelope/digest；item 不变 | 查 review/item/origin | 同左 | pending 假 origin 或上下文缺失 | 否 | 是 | 否 |
| R1-IMP-06 | 同 identity+同 hash 重复提交 active 导入 | 复用同一 pending ReviewRequest，不新增第二张 | 连续请求 | 真实 PG | 多张相同 pending | 是 | 是 | 否 |
| R1-IMP-07 | 同 identity+不同 hash，旧 pending 未解决 | SOURCE_HAS_PENDING_IMPORT，零新增 pending、零 item 写入 | 连续请求 | 真实 PG | 创建第二张 pending | 否 | 是 | 否 |
| R1-IMP-08 | Approve 导入 ReviewRequest | 同一事务应用 title/content/status + tags + extra_metadata + 附件引用 + source_* + ImportOrigin + LinkImportRestorer；成功后仅一 commit 边界 | TestClient + DB 全字段核对 | 真实 PG 全字段核对 | 任一上下文静默丢失/多事务半提交 | 否 | 是 | 否 |
| R1-IMP-09 | Approve hook 在写 tags 后故障 | review 仍 pending；item/tags/log/attachments/origin/links 全部回滚；索引未被错误更新 | 注入异常查全表 | 真实 PG 注入 | 部分提交 | 否 | 是 | 是 |
| R1-IMP-10 | Reject active 导入 | 不写 ImportOrigin、不改 item/links/tags/attachment refs；提交后清 staging | 查 DB + FS | 同左 | 假 origin/提前应用 | 否 | 是 | 否 |
| R1-IMP-11 | Reject staging 清理失败 | reject 状态仍正确；staging orphan 被扫描标记，不误删正式 blob | 文件占用/权限故障 | 同左 | 拒绝事务回滚或正式文件被删 | 否 | 是 | 是 |
| R1-IMP-12 | V1 PATCH 导入过 extra_metadata 后执行 | V1 PATCH 不清空 extra_metadata/source_*；V1 Repository 未被扩展写字段 | PATCH 前后 DB 对比 | 同左 | metadata 变 `{}`/source 字段被覆盖 | 否 | 否 | 否 |
| R1-IMP-13 | 导入显式 target_id + 正文 wikilink | LinkImportRestorer 按既有 target_id 优先/正文权威规则恢复；不再追加普通 sync 覆盖 | 查 knowledge_link + report | 同左 | target_id 丢失/重复双重解析 | 否 | 否 | 否 |
| R1-IMP-14 | ReviewRequest envelope digest/schema 不匹配 | approve 拒绝并 rollback；返回稳定错误码，不泄漏 payload | 修改 payload 注入 | 同左 | 不完整 envelope 被应用 | 否 | 否 | 是 |
| R1-IMP-15 | 无来源身份、无目标 item_id 的同 content_hash 双请求 | anonymous-content 锁串行；第二请求 duplicates/skipped，不重复创建 item | 双线程屏障 | 真实 PG 双请求 | 两个 item 同时创建 | 是 | 是 | 是 |
| R1-IMP-16 | 无来源身份但指定相同 target item_id 的并发导入 | target-item 锁串行；锁内重读并拒绝旧快照覆盖 | 双线程屏障 | 真实 PG 双请求 | 丢失更新/重复来源记录 | 是 | 是 | 是 |

### E.2 单实例进程锁与存储锁

| 编号 | 测试输入 | 预期结果 | SQLite 验证法 | PostgreSQL 验证法 | 失败条件 | 并发 | 真实FS | 故障注入 |
|---|---|---|---|---|---|---|---|---|
| R1-LOCK-01 | 启动两个 Backend 指向同一部署根 | 仅一个获取 OS lock；另一个以 BACKEND_ALREADY_RUNNING 失败 | Windows 双进程 | POSIX/PG 部署同样验证 | 双进程同时运行 | 是 | 是 | 否 |
| R1-LOCK-02 | Backend 运行时启动 backup/restore/downgrade CLI | CLI 获取锁失败并退出，不执行任何写操作 | 子进程 CLI | 同左 | CLI 越过锁执行 | 是 | 是 | 否 |
| R1-LOCK-03 | CLI 持锁时启动 Backend | Backend 启动失败；CLI 退出后可正常启动 | 双进程 | 同左 | 双方同时持有锁 | 是 | 是 | 否 |
| R1-LOCK-04 | Backend 被 kill/崩溃 | OS 自动释放锁；重启可获取；lock 文件不删除 | 真实 kill | 真实 kill | stale PID 阻止重启/删除锁文件 | 是 | 是 | 是 |
| R1-LOCK-05 | Uvicorn --reload worker 重启 | supervisor 不持锁；旧 worker 退出释放，新 worker 获锁；无双 worker 写窗口 | Windows 实际命令 | N/A | reload 后锁泄漏/双 worker | 是 | 是 | 是 |
| R1-LOCK-06 | Uvicorn workers>1 | 第二 worker 不得成为活动 writer；启动整体失败或明确拒绝 | 多 worker 真实启动 | 同左 | 多 worker 同时服务写请求 | 是 | 是 | 否 |
| R1-LOCK-07 | 同 storage_key 上传与 GC/孤儿扫描竞争 | 同进程 keyed lock 串行；引用复核+fencing 后无误删 | 多线程+真实FS | advisory + 真实FS | 双删/误删/损坏 | 是 | 是 | 是 |
| R1-LOCK-08 | PG advisory 64-bit key 冲突/同 key | 同 key 互斥；不同 key 可并发；哈希碰撞最多导致额外串行 | N/A | 真实双连接 | 将 advisory 锁当精确身份或跳过 COUNT | 是 | 否 | 否 |

### E.3 Offline Backup / Restore

| 编号 | 测试输入 | 预期结果 | SQLite 验证法 | PostgreSQL 验证法 | 失败条件 | 并发 | 真实FS | 故障注入 |
|---|---|---|---|---|---|---|---|---|
| R1-BAK-01 | Backend 未停止时创建备份 | CLI 因进程锁占用拒绝；DB/FS 零写入 | 启动 Backend 后 CLI | 同左 | 在线备份继续执行 | 是 | 是 | 否 |
| R1-BAK-02 | Backend 停止后创建完整备份 | CLI 获锁；DB+attachments+quarantine+import-staging 同一离线窗口；manifest/checksum/COMPLETE 完整 | Online Backup API + 真实目录 | pg_dump custom + 真实目录 | 漏文件/hash 错/缺 COMPLETE | 否 | 是 | 否 |
| R1-BAK-03 | 备份包被篡改/缺文件 | restore 在 staging 前拒绝；live DB/附件零变化 | 改 hash/删文件 | 同左 | 不完整包继续恢复 | 否 | 是 | 是 |
| R1-BAK-04 | Restore 合并附件时同路径不同内容 | 中止，不切换 DB；冲突路径保留并报告 | 构造冲突文件 | 同左 | 覆盖现有 blob | 否 | 是 | 是 |
| R1-BAK-05 | SQLite restore 在 DB switch 前崩溃 | live DB 保持旧版本；额外附件只形成安全孤儿；journal 可恢复 | kill 注入 | N/A | live DB 半写/引用缺文件 | 否 | 是 | 是 |
| R1-BAK-06 | SQLite restore 在 DB switch 后崩溃 | 依据 DB hash+journal 判定新 DB 已激活；恢复命令可完成校验/标记，不误回滚 | kill 注入+重启恢复 | N/A | 只信 marker 或误删旧 DB | 否 | 是 | 是 |
| R1-BAK-07 | PG staging restore 校验失败 | 目标库不改名、不终止生产库连接、不删除旧库 | N/A | 真实 pg_restore staging | staging 失败仍切换 | 否 | 是 | 是 |
| R1-BAK-08 | PG 目标库存在无法终止连接/权限不足 | 在 rename 前中止；旧库和配置名保持不变 | N/A | 真实连接+权限测试 | 半切换/强制 DROP | 是 | 否 | 是 |
| R1-BAK-09 | PG rename 交换中途崩溃 | journal + pg_database OID + DB 名对账，恢复旧目标或完成新目标；旧库保留 | N/A | 真实 PG 故障注入 | 盲信 phase/丢旧库 | 否 | 是 | 是 |
| R1-BAK-10 | 恢复含 pending review 附件 staging | ReviewRequest payload 指向的 staging 文件仍存在且 hash 匹配 | 查 DB+FS | 同左 | pending 审核附件丢失 | 否 | 是 | 否 |
| R1-BAK-11 | 备份保留清理 | 只清理超额、完整、校验通过的旧包；至少保留最近 5 份有效包 | 构造多包 | 同左 | 删除唯一有效备份/未完成包 | 否 | 是 | 是 |
| R1-BAK-12 | v2_downgrade 在线/无备份/未确认 | 任一条件不满足即拒绝；不运行 Alembic downgrade | CLI 门禁注入 | 同左 | 直接 downgrade | 否 | 是 | 是 |

## F. R1.1 架构修订专项验收（R1.1-IMP / R1.1-SQL / R1.1-LNK / R1.1-LOCK / R1.1-BAK / R1.1-OPS）

> **全部【待验证】**。真实 SQLite、真实 PostgreSQL 16.8、真实 Windows 文件系统/多进程；**不得以 mock 或离线 SQL 冒充**。
> **逐项状态声明**：本 §F 下 F.1–F.7 **每一个编号的验收项**当前均为 **【待验证】**（未执行、无通过结论）；执行纪律见 F.8。R1.1 增补包中裸编号（如 `IMP-25`）在本矩阵统一加 **`R1.1-`** 前缀，以与 R1 的 `R1-IMP-*` 及原 A–E 段区分；编号语义与增补原文一致。R1 的 IMP-21…24 与 BAK-13/14 未被占用（保留空号，不重编号）。

### F.1 V1/V2 读取契约（D16-1）

| 编号 | 测试输入 | 预期结果 | SQLite 验证法 | PostgreSQL 验证法 | 失败条件 | 并发 | 真实FS | 故障注入 |
|---|---|---|---|---|---|---|---|---|
| R1.1-IMP-25 | 导入 tags/extra_metadata 后调用 V1 GET | V1 schema/响应保持历史不变，**不返回 V2 字段**；V2 export 可读回完整字段 | TestClient + DB + export | 同左 | V1 GET 暴露 V2 字段或结构变化 | 否 | 否 | 否 |
| R1.1-IMP-26 | V1 PATCH 后 V2 export | V1 PATCH **不清空** extra_metadata/tags/source_*；V2 export 读到原值及新正文 | DB 前后快照 | 同左 | metadata 被清零或正文未更新 | 否 | 否 | 否 |
| R1.1-IMP-27 | 所有 V2 读取路径 | 统一经 `MarkdownItemRepository` + `TagRepository`，无第二条分叉 ORM 读路径 | 路由/依赖集成测试 | 同左 | 出现绕过仓库的 V2 读路径 | 否 | 否 | 否 |

### F.2 source-instance-id 生命周期（D-13 / G-4）

| 编号 | 测试输入 | 预期结果 | SQLite 验证法 | PostgreSQL 验证法 | 失败条件 | 并发 | 真实FS | 故障注入 |
|---|---|---|---|---|---|---|---|---|
| R1.1-IMP-28 | 空数据根首次启动 | 获 OS 锁后生成规范 UUID；原子写入、fsync；不覆盖已存在文件 | 真实 FS/双进程 | 同左 | 未持锁生成/非原子/覆盖 | 是 | 是 | 是 |
| R1.1-IMP-29 | 正常重启与 crash restart | ID 字节内容保持不变 | kill/restart | 同左 | 重启后 ID 变化 | 否 | 是 | 是 |
| R1.1-IMP-30 | ID 文件损坏/权限拒绝 | fail-closed，稳定错误码，**不自动生成替代 ID** | 真实 FS | 同左 | 静默重生成/启动继续 | 否 | 是 | 是 |
| R1.1-IMP-31 | 单篇与 ZIP 导出 | 携带 source_instance_id + source_document_id | 解包核对 | 同左 | 缺 instance_id/document_id | 否 | 否 | 否 |
| R1.1-BAK-15 | 同一逻辑实例 backup/restore | Manifest/checksum 包含 ID，restore 保持一致 | SQLite Online Backup | pg_dump + restore | 恢复后 ID 变化/未纳入校验 | 否 | 是 | 是 |
| R1.1-OPS-06 | clone 后 rotate-instance-id | Backend 停止，CLI 持同一 OS 锁，显式确认，原子更换并留 operation journal | Windows CLI | POSIX CLI | 未持锁/无确认/无 journal | 是 | 是 | 是 |

### F.3 身份键锁、S0/S1、approve（D15-2 / D15-3 / FID-2）

| 编号 | 测试输入 | 预期结果 | SQLite 验证法 | PostgreSQL 验证法 | 失败条件 | 并发 | 真实FS | 故障注入 |
|---|---|---|---|---|---|---|---|---|
| R1.1-IMP-32 | 多身份导入结束 | keyed-lock 引用计数归零、registry 无泄漏 | 多身份并发 | 同左 | 计数泄漏/条目残留 | 是 | 否 | 否 |
| R1.1-IMP-33 | 同身份/不同身份并发 | 同身份串行，不同身份并行 | 确定性屏障 | 同左 | 同身份并行/不同身份串行 | 是 | 否 | 否 |
| R1.1-IMP-34 | 单篇与批量入口竞争同身份 | 共用同一个 `app.state` ImportCoordinator | 实例身份断言 | 同左 | 两套 coordinator/两把锁 | 是 | 否 | 否 |
| R1.1-IMP-35 | S0 后、获锁前注入状态变化 | S1 检测变化，按 applied/pending/changed 规则处理 | barrier，不用随机 sleep | 同左 | 旧快照覆盖/未检测变化 | 是 | 否 | 是 |
| R1.1-IMP-36 | submit 与 approve 同身份并发 | 共用身份锁，不产生重复 pending/origin 或半应用 | 确定性 barrier | 同左 | 重复 pending/半应用 | 是 | 否 | 否 |
| R1.1-IMP-37 | approve 预检后 envelope 改动 | 获锁后 fresh session 重读，拒绝且零写入，review 仍 pending | DB barrier | 同左 | 应用已变更 envelope | 是 | 否 | 是 |
| R1.1-IMP-38 | approve hook 任一点故障 | Core approve + tags/attachments/origin/links 整体 rollback | 分步骤故障注入 | 同左 | 部分提交/悬空 origin | 否 | 是 | 是 |
| R1.1-IMP-39 | 请求取消时 worker 正在写事务 | 事务与资源清理完成后才释放身份锁 | cancellation injection | 同左 | 提前释放锁/半写 | 是 | 是 | 是 |
| R1.1-SQL-10 | 导入等待锁时 event loop 探针 | 锁等待不阻塞 event loop；Session 不跨线程 | ASGI concurrency probe | 同左 | event loop 卡死/跨线程 Session | 是 | 否 | 否 |

### F.4 Coordinator 单例与普通 K1 回归

| 编号 | 测试输入 | 预期结果 | SQLite 验证法 | PostgreSQL 验证法 | 失败条件 | 并发 | 真实FS | 故障注入 |
|---|---|---|---|---|---|---|---|---|
| R1.1-IMP-40 | 单篇/批量/治理 approve 三路径 | 使用同一 lifespan `ImportCoordinator` | dependency identity | 同左 | 任一路径使用独立实例 | 否 | 否 | 否 |
| R1.1-LNK-14 | 导入分支上线后执行普通 K1 UPDATE/RESTORE/DELETE/MERGE | 普通治理保持原 K1 时序；仅 import envelope 分支走专用 hook | SQLite/PG API 回归 | 同左 | 普通 K1 被导入 hook 影响 | 否 | 否 | 否 |

### F.5 Staging / Restore

| 编号 | 测试输入 | 预期结果 | SQLite 验证法 | PostgreSQL 验证法 | 失败条件 | 并发 | 真实FS | 故障注入 |
|---|---|---|---|---|---|---|---|---|
| R1.1-IMP-41 | staging sweep 遇仍被 PENDING ReviewRequest 引用的文件 | 不清理；按 review_id + envelope manifest 校验 | DB + 真实 FS | 同左 | pending 引用文件被清 | 否 | 是 | 否 |
| R1.1-IMP-42 | staging 无 pending 引用且超过 grace | 复核后 quarantine/purge；**正式 attachments 根绝不被 sweep** | DB + 真实 FS | 同左 | 误删正式附件 | 是 | 是 | 是 |
| R1.1-BAK-16 | restore 后当前环境额外 blob | 保留为安全孤儿；grace 后仅清理确认无引用对象 | 真实恢复 + GC | 同左 | 恢复时覆盖/删除现存 blob | 否 | 是 | 是 |

### F.6 OS 单实例锁 / reload / 跨平台抽象（D17-1 / D17-2 / D17-3）

| 编号 | 测试输入 | 预期结果 | SQLite 验证法 | PostgreSQL 验证法 | 失败条件 | 并发 | 真实FS | 故障注入 |
|---|---|---|---|---|---|---|---|---|
| R1.1-LOCK-09 | Backend/CLI 从不同 cwd 启动 | 解析同一 `BACKEND_DIR.resolve()` 绝对锁路径 | Windows/POSIX 子进程 | 同左 | 因 cwd 不同锁不同 | 是 | 是 | 否 |
| R1.1-LOCK-10 | Uvicorn --reload 交接 | supervisor 不持锁；新 worker 有界退避（100ms→500ms，总≤10s）；最多一个 holder | Windows 真实 reload | POSIX reload | 双 worker/无限等待/锁泄漏 | 是 | 是 | 是 |
| R1.1-LOCK-11 | 第二个独立 Backend 启动 | 有界等待后 `BACKEND_ALREADY_RUNNING` | 双进程 | 同左 | 第二实例成功启动 | 是 | 否 | 否 |
| R1.1-LOCK-12 | workers>1 | 启动前拒绝 | 实际 Uvicorn | 同左 | 多 worker 同时服务写 | 是 | 否 | 否 |
| R1.1-LOCK-13 | msvcrt/fcntl 抽象 | 排他、释放、崩溃释放语义一致 | Windows | POSIX | 平台语义分叉 | 否 | 是 | 是 |

### F.7 PostgreSQL restore 连接清场（BAK-1）

| 编号 | 测试输入 | 预期结果 | SQLite 验证法 | PostgreSQL 验证法 | 失败条件 | 并发 | 真实FS | 故障注入 |
|---|---|---|---|---|---|---|---|---|
| R1.1-BAK-17 | target 有普通连接 | maintenance DB 禁新连接、terminate、轮询 `pg_stat_activity` 清零后才 rename | N/A | 真实 PG 16.8 | 有连接仍 rename | 是 | 否 | 是 |
| R1.1-BAK-18 | 后台连接残留/权限不足 | 清场失败中止，恢复 `ALLOW_CONNECTIONS`，旧 target/OID 不变 | N/A | 真实 PG | 半清场/改坏旧库 | 是 | 否 | 是 |
| R1.1-BAK-19 | rename 中崩溃或 journal/OID 不符 | recover 以 DB name+OID+journal 对账；不唯一则 fail-closed | N/A | 真实 PG kill/restart | 盲信 phase/误删库 | 否 | 是 | 是 |

### F.8 R1.1 执行纪律

1. 本段所有新增项保持 **【待验证】**，不得预先写入任何"已验证"结论。
2. PG 项必须真实连接 **PostgreSQL 16.8**；Windows 项必须真实 Windows FS/多进程。
3. 并发测试使用 **barrier/event/双进程**，不用随机 sleep 充当证明。
4. 故障注入须断言 **rollback、原数据保留、无部分写入**。
5. 原 R1 全部验收编号（§E）保留，不覆盖、不删减、不弱化。
6. **产品约束一致性**：F.2/F.6/F.7 的备份/恢复/rotate/进程锁项必须按 **Offline（Backend 停止 + 维护锁）/ Single（单 worker）/ Strict（无新迁移）** 执行，不得改写为在线维护或多实例并发验收。

## G. R1.2 架构修订专项验收（R1.2-ID / R1.2-BAT / R1.2-ASYNC / R1.2-NET）

> **全部【待验证】**。对应决策见 `implementation-plan` §21（D18/D19/D20/D21）、`open-decisions` §K；风险见 `risk-register` §13。
> **逐项状态声明**：本 §G 下 G.1–G.4 **每一个编号**当前均为 **【待验证】**（未执行、无通过结论）。R1.2 编号为本轮新增，不复用、不覆盖 R1/R1.1 编号。执行纪律见 G.5。
> 本段不改写 §F：`R1.1-SQL-10` 继续作为“event loop 不阻塞、Session 不跨线程”的属性回归项；`R1.2-ASYNC-*` 验证 D20 同步执行模型本身。

### G.1 文档身份模型（D18）

| 编号 | 测试输入 | 预期结果 | SQLite 验证法 | PostgreSQL 验证法 | 失败条件 | 并发 | 真实FS | 故障注入 |
|---|---|---|---|---|---|---|---|---|
| R1.2-ID-01 | 当前实例导出单篇与 ZIP | frontmatter/manifest 同时含 `source_instance_id`、`source_document_id`、`exporter_instance_id`；exporter=当前实例；**DB 无 exporter 列** | 解析导出文本 + `PRAGMA table_info` | 解析导出 + `information_schema.columns` | exporter 被当作 source / 新增 DB 列 | 否 | 是 | 否 |
| R1.2-ID-02 | 实例 X 导入文档 → 修改 → 实例 Y 再导出 | 原始 `source_instance_id/source_document_id` 不变；`exporter_instance_id`=Y | 两实例 ID + 查 ImportOrigin/item + 解析导出 | 同左 | 来源身份被 Y 覆盖 | 否 | 是 | 否 |
| R1.2-ID-03 | 克隆实例执行 rotate-instance-id 后导出继承文档 | 仅 exporter 变为克隆实例；继承文档 source identity **原样保留**，无批量改写 | CLI rotate + 多文档导出核对 | 同左（POSIX CLI） | 批量重写继承文档 source identity | 否 | 是 | 否 |
| R1.2-ID-04 | 同一 `DocumentIdentity`、不同 `source_payload_hash`，来自不同 exporter | 进入既有变化分类/审核/`SOURCE_CHANGED_DURING_WAIT`/pending 规则；**不分裂身份**、不静默覆盖 | 构造两版本 + 查 origin/review | 同左 | 按 exporter 分裂身份/绕过审核 | 否 | 是 | 否 |
| R1.2-ID-05 | legacy 包：缺 `source_instance_id` 或 `source_document_id`，或含非法值 | 不编造 UUID、不推断为本实例；content_hash 查重 + 默认 Draft + 显式 target 才绑定；报告标 legacy/duplicates | 构造 legacy 包 + 查 item/report | 同左 | 伪造 UUID/静默覆盖 | 否 | 是 | 否 |
| R1.2-ID-06 | 身份字段只存在其一（半身份） | fail-closed 或走 legacy 规则；不得拼凑成新身份 | 构造半身份 | 同左 | 拼凑身份/默认采用 | 否 | 是 | 是 |
| R1.2-ID-07 | 同逻辑实例 backup→restore→再次导出 | Manifest/checksum 含实例 ID；restore 后 exporter 与 source identity 均保持；导出 source 不变 | SQLite Online Backup + 导出核对 | pg_dump/restore + 导出核对 | 恢复后身份变化/未纳入校验 | 否 | 是 | 是 |
| R1.2-ID-08 | 导出后重新导入同一实例（exporter==source_instance_id） | 按来源身份幂等，exporter 字段差异**不**导致重复建/误判新来源 | 导出→再导 + 查计数 | 同左 | exporter 差异被当身份差异 | 否 | 是 | 否 |

### G.2 批次依赖与附件边界（D19）

| 编号 | 测试输入 | 预期结果 | SQLite 验证法 | PostgreSQL 验证法 | 失败条件 | 并发 | 真实FS | 故障注入 |
|---|---|---|---|---|---|---|---|---|
| R1.2-BAT-01 | Batch A 导入请求含附件清单/附件内容 | **显式拒绝或标记 unsupported**（固定稳定码 `ATTACHMENT_IMPORT_UNSUPPORTED`，open-decisions §L.2）；零附件写入、不静默丢弃、报告逐项标明 | TestClient + 查无附件行/无物理文件 | 同左 | 静默忽略附件/部分写入 | 否 | 是 | 否 |
| R1.2-BAT-02 | Batch A 导出请求含附件内容 | 明确 unsupported（固定稳定码 `ATTACHMENT_EXPORT_UNSUPPORTED`，open-decisions §L.2），或仅导出附件引用元数据并声明**不完整**；不得宣称完整附件导出 | 解包/响应核对 | 同左 | 无提示丢失附件 | 否 | 是 | 否 |
| R1.2-BAT-03 | 审阅 Batch A 验收清单与报告 | 不含 ATT/GC/ORP/BAK 项，不宣称附件导入完成；范围与 §21.2 一致 | 清单核对 | 同左 | 虚报附件完成 | 否 | 否 | 否 |
| R1.2-BAT-04 | Batch B：Active approve 含附件 staging | 附件引用 + item + tags + origin + links **同一事务**提交；任一点失败全部回滚、review 保持 pending、无悬空引用 | 分步骤故障注入 | 同左 | 部分提交/悬空附件引用 | 否 | 是 | 是 |
| R1.2-BAT-05 | 批次出口门禁 | Batch A/B/C/D 各自独立验收；未通过本批出口不得进入下一批；不得以他批通过代替 | 门禁执行记录 | 同左 | 跳批/代替验收 | 否 | 否 | 是 |
| R1.2-BAT-06 | 文档/验收报告/提交说明的批次映射 | 不把 B/C/D 的范围记入 A；附件相关验收归属 B；声明与实际一致 | 文档审计 | 同左 | 范围虚报 | 否 | 否 | 否 |

### G.3 同步事务执行模型（D20）

| 编号 | 测试输入 | 预期结果 | SQLite 验证法 | PostgreSQL 验证法 | 失败条件 | 并发 | 真实FS | 故障注入 |
|---|---|---|---|---|---|---|---|---|
| R1.2-ASYNC-01 | 导入/批量导入/approve 写路由 | 同步 `def`，由框架线程池执行；不在 `async def` 内等待同步锁 | 路由签名 + 线程探针 | 同左 | async 路由阻塞/无线程池 | 否 | 否 | 否 |
| R1.2-ASYNC-02 | 导入全流程 Session 使用 | Session 在实际执行线程内创建/使用/关闭；无跨线程传递 | 线程 ID 与 Session 生命周期断言 | 同左 | 跨线程 Session | 是 | 否 | 否 |
| R1.2-ASYNC-03 | S0→锁→S1→写事务 | S0 只读短会话关闭后才获锁；S1 全新会话重读；写事务在锁内；锁覆盖完整业务事务 | 确定性 barrier + 顺序断言 | 同左 | 事务早于锁/持 S0 等锁 | 是 | 否 | 是 |
| R1.2-ASYNC-04 | 请求在写事务中取消/客户端断开 | Commit/Rollback 与 Session 清理完成后才释放锁；不提前释放、不半写 | cancellation injection | 同左 | 断连释放锁/半写 | 是 | 是 | 是 |
| R1.2-ASYNC-05 | 锁等待超时 | 固定 10 秒有界等待，超时 fail-closed（固定稳定码 `IMPORT_LOCK_TIMEOUT`，open-decisions §L.2）；不无限等待、不无锁 fallback | 长时间持锁屏障 | 同左 | 无限等待/绕过锁 | 是 | 否 | 是 |
| R1.2-ASYNC-06 | 代码与运行时协调机制 | 只有同步身份锁一套；**无 async keyed lock + threading.Lock 双架构** | 代码审计 + 运行时断言 | 同左 | 双锁不互斥/死锁 | 是 | 否 | 否 |
| R1.2-ASYNC-07 | 同身份/不同身份并发 | 同身份串行；不同身份并行；不退化为全局单线程 | 双/多请求 barrier | 同左 | 同身份并行/全全局串行 | 是 | 否 | 否 |
| R1.2-ASYNC-08 | 锁等待期间 event loop 探针 | 同步 DB/FS/锁等待不阻塞 event loop（在线程池执行） | ASGI concurrency probe | 同左 | event loop 卡死 | 是 | 否 | 否 |

### G.4 HTTP 网络边界（D21）

| 编号 | 测试输入 | 预期结果 | SQLite 验证法 | PostgreSQL 验证法 | 失败条件 | 并发 | 真实FS | 故障注入 |
|---|---|---|---|---|---|---|---|---|
| R1.2-NET-01 | 默认配置启动 | 监听 `127.0.0.1`，不是 `0.0.0.0`/`::` | 启动参数 + 连接探针 | 同左 | 默认对外监听 | 否 | 否 | 否 |
| R1.2-NET-02 | 无认证时配置非 loopback | 启动 **fail-closed**（固定稳定码 `NON_LOOPBACK_WITHOUT_AUTH`，D24），不监听 | 真实启动 | 同左 | 成功启动并监听 | 否 | 否 | 是 |
| R1.2-NET-03 | 配置 `0.0.0.0`/`::`/LAN IP/`127.0.0.1.evil.com`/解析失败 | 解析后判断，全部拒绝；允许集合【提议】`127.0.0.1`/`::1`/`localhost` | 参数化启动矩阵 | 同左 | 前缀/包含判断被绕过 | 否 | 否 | 否 |
| R1.2-NET-04 | 携带 CORS/`X-Forwarded-For`/自定义头请求 | 不被当作认证；无“带 header 即放行”逻辑 | 请求矩阵 | 同左 | 代理头绕过 | 否 | 否 | 否 |
| R1.2-NET-05 | 反向代理/隧道/端口转发说明 | 文档明确其为额外暴露面；loopback 监听不解决其认证/TLS/授权问题；未认证不得对外 | 文档核对 + 部署检查 | 同左 | 宣称 loopback 即安全 | 否 | 否 | 否 |
| R1.2-NET-06 | 启动失败/网络错误响应与日志 | 只给稳定码与风险说明；无 host/port/密钥/堆栈/`str(exc)` | 抓取响应/日志 | 同左 | 敏感信息泄漏 | 否 | 否 | 是 |
| R1.2-NET-07 | 环境变量/配置文件/启动参数的 host 设置 | 所有入口均经同一校验；任一入口不得绕过 | 参数化配置矩阵 | 同左 | 某入口绕过校验 | 否 | 是 | 否 |
| R1.2-NET-08 | 依赖与能力声明 | 不新增认证/网络依赖；不宣称已鉴权或可安全公网暴露 | 依赖清单 + 文档 | 同左 | 引入依赖/虚假声明 | 否 | 否 | 否 |

### G.5 R1.2 执行纪律

1. 本段所有新增项保持 **【待验证】**，不得预先写入任何“已验证”结论；本轮（文档合并）**未执行任何测试**。
2. 并发/取消测试使用 **barrier/event/双进程**，不用随机 sleep 充当证明；同步模型须在真实 ASGI 线程池下验证。
3. 网络项须**真实启动进程**验证监听地址与 fail-closed，不得只读代码推断。
4. 附件拒绝项须断言**零附件写入、无静默丢弃、报告明确**；Batch B 须断言**单事务全回滚**。
5. 原 R1（§E）与 R1.1（§F）全部编号保留，不覆盖、不删减、不弱化；`R1.2-*` 仅新增。
6. **产品约束一致性**：D19/D20/D21 不得改写 Offline（Backup 停止 + 同 OS 锁）/ Single（单 Backend/单 worker）/ Strict（无新迁移）三约束；网络边界不得被解释为“已认证可公网”。

## H. R1.3 架构修订专项验收（R1.3-HASH / R1.3-ID / R1.3-NET）

> **全部【待验证】**。对应决策见 `implementation-plan` §22（D22/D23/D24）、`open-decisions` §L；风险见 `risk-register` §14。
> **逐项状态声明**：本 §H 下 H.1–H.3 **每一个编号**当前均为 **【待验证】**（未执行、无通过结论）。R1.3 编号为本轮新增，不复用、不覆盖 R1/R1.1/R1.2 编号。
> **批次归属**：`R1.3-HASH-*`、`R1.3-ID-*` 归 **Batch A**（非附件）；`R1.3-NET-*` 归 **Batch D**。D24 网络验收**不得阻塞** Batch A 的非附件开发。
> **历史保留**：R1.2-NET-03 的旧绑定允许集合（含 `localhost`）作为历史保留；R1.3-NET-01 起以**精确 IP 绑定**与**请求侧 Host/Origin 校验**为准。

### H.1 exporter 与 Hash 解耦（D22）

> 本表全部【待验证】；归 **Batch A**。

| 编号 | 测试输入 | 预期结果 | SQLite 验证法 | PostgreSQL 验证法 | 失败条件 | 并发 | 真实FS | 故障注入 |
|---|---|---|---|---|---|---|---|---|
| R1.3-HASH-01 | 同一未变更文档分别由实例 X、Y 导出 | `document_content_hash`、`document_payload_hash` 完全相同；frontmatter `__explainlab_exporter_instance_id` 分别为 X/Y；manifest checksum 可变但**文档 payload_hash 不变** | 解析两版导出并比对 Hash | 同左（真实 PG） | Hash 随 exporter 变化 / exporter 进入 Hash 输入 | 否 | 是 | 否 |
| R1.3-HASH-02 | 导入含 `__explainlab_exporter_instance_id` 的包（exporter 不同/缺失） | 导入前剥离保留键；`source_payload_hash`、`review_payload_hash` 与同内容无 exporter 包一致；DB **无 exporter 值/列** | 查 Hash + `PRAGMA table_info` + 查 extra_metadata | 同左 + `information_schema.columns` | Hash 受 exporter 影响 / exporter 落库 | 否 | 是 | 否 |
| R1.3-HASH-03 | 四类保留键冲突：①用户 `extra_metadata` 已含 `__explainlab_exporter_instance_id`；②同一 frontmatter 重复保留键（解析器折叠前）；③manifest 与 frontmatter exporter 不一致；④保留键位于用户自定义 metadata 容器 | 四类均**明确拒绝并报告冲突**（`EXPORTER_METADATA_RESERVED_CONFLICT`）；**不静默删除/覆盖**用户 metadata；**零数据库写入**（校验在任何 DB 写之前完成） | 构造四类冲突 + 查 item/origin/link 均未变 + 查无 ImportReport 成功项 | 同左 | 解析器折叠重复键导致静默丢失 / 任一冲突产生写入 / 删除用户 metadata | 否 | 是 | 是 |
| R1.3-HASH-04 | 代码契约探针：仅改变 exporter 的等价 metadata 输入 | 剥离后 A1-02 `document_content_hash`/`document_payload_hash`/`source_payload_hash`/`review_payload_hash` 全部一致；Core Hash/canonicalization v1 文件无改动；DB schema 无 exporter 列 | 单元探针 + `git diff` 证明 Core 未改 | 同左 | Core Hash 被修改 / 探针结果不一致 | 否 | 否 | 否 |

### H.2 本地文档身份初始化（D23）

> 本表全部【待验证】；归 **Batch A**。
> **D23 前提（强制）**：仅凭现有 DB 字段与 `extra_metadata` **信息不足**，不得推断“已合法物化”；合法物化只能由**恰好一条匹配的 COMMITTED MATERIALIZE Journal 记录**证明；无证据的非空实例一律按状态 4 fail-closed，不认领、不补写、不覆盖。
> **恢复与归档前提（强制）**：启动/进入身份操作前先过 Journal 恢复门；有效 `PREPARED MATERIALIZE` 必须先恢复（DB 为空则补、等于目标则接受、其他值/摘要不符 fail-closed），恢复完成前不得分类、不得写身份、不得开新操作；`COMMITTED` 未归档只补归档、不重复写 DB；归档采用同卷原子落位，current/archive 同 `operation_id` 同内容按一条记录去重，异内容 fail-closed；Journal v1 的 `materialization_items` 与三个摘要必须按 `implementation-plan` §22.2 的字段、排序、编码、空值和版本规则校验；`materialization_items` **仅**列本次物化项，`identity_audit_digest` 必须是**全部 knowledge_item 的操作完成后预期来源身份投影**（含未物化/已物化本地、有效 ImportOrigin、残缺/冲突状态），且**每项必须逐条纳入其全部 `ImportOrigin` 原始记录**（含残缺、重复、字段非法；稳定 `import_origin_id`、原始 `source_instance_id`/`source_document_id`/`source_payload_hash`、记录数量/状态；不过滤、不去重、不归一化）；不得只覆盖物化项、不得只信 Journal 证明 DB；每次写后与恢复分支必须重读 DB 重算；任何孤儿 `ImportOrigin` 必须 fail-closed，不得静默跳过；不得包含 exporter。Canonical JSON v1 必须显式实现 UTF-8 非 ASCII 原样输出、引号/反斜杠/控制字符转义、合法 surrogate 对组合/孤立 surrogate 拒绝、对象键 code point 排序、重复键解析折叠前拒绝、非负整数限制，并覆盖 §22.2 的 8 组固定测试向量。
> **多记录状态前提（强制）**：按 §22.2 判定表，`ImportOrigin` 汇总状态互斥且优先级固定为 `conflict` > `invalid` > `incomplete` > `duplicate` > `complete` > `none`；**同一 item 出现 ≥2 个不同合法身份对，或唯一合法身份与 `knowledge_item.source_instance_id` 不一致（含 DB `null`）时必须 `conflict`**；完整+残缺混合不得提升，重复+不同身份必须冲突；同一身份的不同 `source_payload_hash` 版本不算冲突。冲突项零认领/覆盖/合并/猜测，不得任选一条作为有效来源。

| 编号 | 测试输入 | 预期结果 | SQLite 验证法 | PostgreSQL 验证法 | 失败条件 | 并发 | 真实FS | 故障注入 |
|---|---|---|---|---|---|---|---|---|
| R1.3-ID-01 | 正常导入文档（含 ImportOrigin） | 来源身份取自 `ImportOrigin.source_instance_id/source_document_id`；不重新生成 UUID、不用 `item.id` 替代 | 查 ImportOrigin + knowledge_item | 同左（真实 PG） | 生成新身份/覆盖来源 | 否 | 是 | 否 |
| R1.3-ID-02 | 本地原生状态 2a（无 `ImportOrigin`、`source_instance_id` 为空、无匹配 COMMITTED MATERIALIZE 记录）首次导出；随后重复导出、重启、克隆；启动/重启时当前 Journal 分别为无、`PREPARED MATERIALIZE`、`COMMITTED` 未归档、损坏/摘要不符；`PREPARED` 时 DB 逐项为空、等于 Journal 目标、存在其他值；并分别在 Journal 写前、PREPARED 后 DB 前、DB 后 COMMITTED 前、COMMITTED 后归档临时文件前/后、归档 rename 后、目录同步后、移除 current 后崩溃；Journal/归档缺失或损坏；全库另含单条有效、单条残缺、两条重复、字段非法、同一身份多版本、多个不同合法身份对、完整+残缺混合、重复+不同身份混合及 DB `source_instance_id` 与唯一合法身份不一致的 `ImportOrigin`，分别在 PREPARED 后重读前修改其原始 `source_instance_id`/`source_document_id`/`source_payload_hash`、增删记录、打乱数据库返回顺序，并构造孤儿 `ImportOrigin` | 首次导出严格按 **MATERIALIZE PREPARED 持久化 → 条件写 `source_instance_id`=当前实例 ID（`source_document_id` 仅由 `item.id` 派生，**无随机文档 UUID**）→ 重读校验 → COMMITTED → 归档 → 导出**；`materialization_items` **仅**列本次物化项；`identity_audit_digest` 必须覆盖**全部 knowledge_item** 的来源身份投影并按 v1 **预期完成态**计算，DB 写后/各恢复分支必须重读 DB 重算，不得只信 Journal；**每项全部 `ImportOrigin` 原始记录逐条进入 `import_origins[]`**（残缺/重复/非法不得过滤、不得归一化；稳定记录 ID 排序；记录数/状态可审计）；任一原始记录字段变化或记录集合增减均须导致 `identity_audit_digest` 变化；孤儿 `ImportOrigin` 必须直接 fail-closed；数据库读取顺序变化不得影响 Canonical JSON 或摘要；多记录必须按 §22.2 表判定：多个不同合法身份对或唯一合法身份与 DB 实例不一致→`conflict`，完整+残缺→`incomplete`，重复+不同身份→`conflict`，同一身份多版本→`complete`（不算冲突）；上述冲突/残缺均零认领、不得任选一条；不写 `ImportOrigin`/`extra_metadata`、不改 Hash；**启动先过 Journal 恢复门**：有效 `PREPARED MATERIALIZE` 必须先恢复（DB 为空则幂等补写、等于目标则接受、其他值或摘要不符 fail-closed），恢复完成前不得做身份分类、不得写身份、不得开新操作；`COMMITTED` 未归档只补归档、**不重复写 DB**；current/archive 同 `operation_id` 同内容按一条记录去重，异内容 fail-closed；重复导出/重启/克隆后身份稳定且不重写；Journal/归档缺失/损坏/冲突时 **fail-closed**（零 DB 写，不把非空实例认领为 2b）；任何崩溃点恢复不得产生“无 Journal 证据的非空身份” | 导出前后查 `knowledge_item`/`ImportOrigin`/Journal+archive + 解析 frontmatter + 比对 Hash；启动恢复门须在分类前执行 | 同左（真实 PG） | 未过恢复门即分类/写身份 / 未写 PREPARED 就写 DB / 无 Journal 证据仍物化 / 用随机文档 ID / 非空即认领 / 每次导出变化 / 写 `extra_metadata` 或伪 `ImportOrigin` / COMMITTED 恢复重写 DB / PREPARED 其他值被覆盖 / 恢复未完成开新操作 / current+archive 计两条 / 摘要只覆盖物化项 / 只信 Journal 未重读 DB / 过滤或去重残缺/重复/非法 ImportOrigin / 原始字段被 trim/大小写/UUID/hash 归一化 / 读取顺序影响摘要 / 孤儿 origin 被静默跳过 / 多合法身份对未判 conflict / 完整+残缺被提升为 complete / 重复+不同身份未判 conflict / DB 实例不一致未 fail-closed / 冲突时按顺序/时间/ID/Hash 任选一条 / canonical 字符串或重复键规则不符 | 否 | 是 | 是 |
| R1.3-ID-03 | ①存在 `ImportOrigin` 但身份字段缺失/非法；②无 `ImportOrigin` 且 `source_instance_id` 非空但**无匹配 COMMITTED MATERIALIZE 记录**；③同一 item 有多条/冲突物化记录；④实例为空但存在物化记录；⑤`ImportOrigin` 与物化记录并存；⑥当前 Journal 为 `PREPARED`/`COMMITTED`/损坏/摘要不符，分别在恢复前与恢复后分类；另构造单条残缺、两条重复、字段非法、同一身份多版本、多个不同合法身份对、完整+残缺混合、重复+不同身份混合及 DB 实例不一致的 `ImportOrigin`，并分别修改原始 instance/document/payload、增删记录、打乱读取顺序 | 全部归 **legacy/unknown 或冲突态**，不认领为本地原生/2b；①**不**用 `item.id` 反向补齐；②**不自动创建/补写 `source_document_id`**、**不覆盖**既有 `source_instance_id`；③–⑤ 及⑥中损坏/摘要不符/恢复失败态 fail-closed；⑥中有效 `PREPARED`/`COMMITTED` 必须先恢复，恢复通过后再分类；**身份分类只能发生在 Journal 恢复门通过之后**；Journal v1 字段/排序/编码/空值/版本或摘要不符时不得认领；`identity_audit_digest` 必须覆盖全部知识文档且由 DB 重读重算，不能只覆盖物化项或只凭 Journal 自证；每项必须逐条纳入全部 `ImportOrigin`（含残缺/重复/非法；原始字段原样、记录数/状态/稳定 ID、读取顺序无关）；多记录按 §22.2 表汇总：多个不同合法身份对或唯一合法身份与 DB 实例不一致→`conflict`，完整+残缺→`incomplete`（不得提升），重复+不同身份→`conflict`，同一身份多版本→`complete`；冲突/残缺均无有效来源身份、不得任选一条；孤儿 `ImportOrigin` 必须 fail-closed；均不自动 Adoption；导出/rotate 报告如实标身份不完整/冲突；**零身份写入** | 构造五类状态 + Journal 恢复前后快照 + 查 item/ImportOrigin/Journal/report + 断言零改写；按 v1 schema 校验字段与摘要 | 同左（真实 PG） | 任一类被物化/补齐/覆盖/静默忽略 / 多记录中按时间挑一条 / 恢复前分类 / 用损坏或未恢复记录认领 / 缺失证据仍认领 / 摘要只覆盖物化项 / 未从 DB 重算摘要 / 残缺或重复 origin 的 `import_origin_identity_digest=null` 后不再纳入其原始字段 / 过滤/合并非法 origin / 原始字段被归一化 / 读取顺序影响摘要 / 孤儿 origin 未 fail-closed / 多合法身份对未判 conflict / 完整+残缺被提升 / 重复+不同身份未判 conflict / DB 实例不一致未 fail-closed / 冲突时按顺序/时间/ID/Hash 任选或合并字段 / canonical 重复键被折叠 | 否 | 是 | 是 |
| R1.3-ID-04 | 同一当前来源存在多条匹配 ImportOrigin | 按 FID-2 解析；**多条匹配 fail-closed**（`SOURCE_IDENTITY_AMBIGUOUS`）；**不得**用 `MAX(imported_at)` 猜测；零写入；物化 Journal 不参与 ImportOrigin 历史挑选 | 构造重复 origin + 查无写入 | 同左 | 按时间猜测 / 任选一条 | 否 | 是 | 是 |
| R1.3-ID-05 | clone rotate：存在状态 2a、2b、正常导入、状态 3、状态 4 文档；分别在物化失败、Journal 写失败、Journal 写前/后、ID 原子替换前/后崩溃、`PREPARED`+旧 ID / `PREPARED`+新 ID / 两者皆非、`COMMITTED` 后重启、第二次独立 rotate、同一 `operation_id` 重入；并在归档临时文件写前/后、同卷 rename 后、目录同步后、移除 current 前后崩溃；current+archive 并存、archive 冲突/缺失、归档失败后尝试新 rotate；Journal v1 字段/排序/编码/空值/版本/摘要异常；Windows 与 POSIX 文件系统；全库另含单条有效、单条残缺、两条重复、字段非法、同一身份多版本、多个不同合法身份对、完整+残缺混合、重复+不同身份混合及 DB 实例不一致的 `ImportOrigin`，分别在 rotate PREPARED 后、ID 替换前/后修改原始 instance/document/payload、增删记录、打乱读取顺序 | 2a 在 rotate 前逐条完成 **MATERIALIZE PREPARED→DB→COMMITTED+归档**，任一条失败即中止 rotate；rotate 严格执行九步持久化顺序（PREPARED temp→fsync→原子替换→父目录同步→ID temp/fsync→原子替换→父目录同步→重读 ID+按 `materialization_items` 重查 DB/摘要→COMMITTED+归档）；`PREPARED`+旧 ID **必须重查 DB 物化清单**后继续；`PREPARED`+新 ID **只补提交、不再轮换**；两者皆非/损坏/摘要不符 fail-closed；**启动先恢复 PREPARED，恢复完成前不分类/不写身份/不开新操作**；`COMMITTED` 只补归档、**不重复写 DB**；archive 临时文件以**同卷原子 rename**落到 `archive/<operation_id>.json`，current 在 archive 校验/同步后幂等移除；current/archive 同 `operation_id` 同内容按**一条记录**去重、异内容 fail-closed；归档失败**禁止新操作**；归档成功后允许**新 operation_id 的第二次独立 rotate**；archive append-only、不自动删除；已归档 `operation_id` 重入规则不变（同内容 no-op、异内容 fail）；Journal v1 的 `materialization_items` 与三个摘要必须按字段/排序/编码/空值/版本规则校验；`identity_audit_digest` 必须覆盖**全部 knowledge_item 且每项逐条纳入全部 `ImportOrigin` 原始记录**（含残缺/重复/非法；稳定 ID/原始字段/记录数/状态；不过滤、不归一化、读取顺序无关），并在 rotate ID 替换前、替换后各从 DB 重读重算一次且均与 PREPARED 预期一致；任一 origin 原始字段/记录数变化或孤儿出现必须导致摘要不符/fail-closed；多记录按 §22.2 表判定，`conflict`/`incomplete`/`duplicate` 项在 rotate 中保持原样、不物化、不改写、不产生有效身份，不得任选一条或合并字段；同一身份多版本仍为 `complete`；Canonical JSON v1 必须按字符串转义/非 ASCII/补充平面/重复键拒绝规则执行并覆盖 8 组固定向量；2b/导入文档来源**不被批量改写**；状态 3/4 零写；失败不完成轮换；adoption 不执行；Windows 目录同步不支持时不得宣称断电持久 | 真实 CLI + Journal/ID/DB/archive 快照 + 各崩溃点故障注入 + current/archive 并存/冲突 + 多文档/多轮核对 + Windows/POSIX 实机 + v1 schema 校验 | 同左（POSIX CLI） | 先替换后写 Journal / 未重查 DB 物化清单 / 引用不存在的清单字段 / 新 ID 再轮换 / 未知 ID 被覆盖 / 失败仍轮换 / 批量改写来源 / 同一 operation_id 重复 / 第二次 rotate 被旧 Journal 阻塞 / current+archive 计两条 / 归档覆盖或删除历史 / 归档失败仍开新 rotate / COMMITTED 恢复重写 DB / archive 缺失仍认领 / 跳过 schema/摘要校验 / 恢复前分类 / Windows 虚假持久化声明 / 摘要只覆盖物化项 / rotate 前后未重算全库摘要 / 未逐条纳入全部 ImportOrigin 原始记录 / 过滤或合并残缺/重复/非法记录 / 原始字段被归一化 / 读取顺序影响摘要 / 孤儿 origin 未 fail-closed / 多合法身份对或 DB 实例不一致未判 conflict / 冲突项被物化/改写/任选一条 / 完整+残缺被提升 / 重复+不同身份未判 conflict / canonical 字符串或重复键规则不符 | 是 | 是 | 是 |

**ImportOrigin 全量审计判别用例（不新增验收编号；由 `R1.3-ID-02/03/05` 共同覆盖，全部【待验证】）**

> 前置：同一 DB 中构造下列记录集合；每项都必须证明“参与审计的原始记录变化会改变 `identity_audit_digest`”。摘要计算须使用 §22.2 的 Canonical JSON v1；不得过滤、去重或归一化原始字段。

| # | 判别用例 | 预期结果 | 归入 |
|---|---|---|---|
| 1 | 单条有效 `ImportOrigin` | 该记录进入 `import_origins[]`；`import_origin_count=1`、`status_flags=[]`、`duplicate_group_size=1`、`import_origin_state=complete`；摘要可复算 | ID-02/03/05 |
| 2 | 单条残缺（如 `source_instance_id=null`，或 `source_document_id`/`source_payload_hash` 为 `null`/空串） | 记录仍完整进入 `import_origins[]`；`status_flags` 含 `incomplete`，`origin_state=incomplete`，不产生有效来源身份；原始 `null`/空串保留 | ID-03/05 |
| 3 | 同一 item 内两条重复 `ImportOrigin`（三个原始字段逐字节相同） | 两条均进入数组，`duplicate_group_size=2`、`duplicate_origin_count=2`、`import_origin_state=duplicate`；不得任选一条或去重 | ID-03/05 |
| 4 | 修改某条 `source_instance_id` | 即使该记录残缺/重复，摘要也变化；重算与 PREPARED 不符即 fail-closed | ID-02/03/05 |
| 5 | 修改某条 `source_document_id` | 摘要变化；不得把原值替换为 `item.id` 或规范 UUID 后“视为相同” | ID-02/03/05 |
| 6 | 修改某条 `source_payload_hash` | 摘要变化；不得静默重算/规范化 hash | ID-02/03/05 |
| 7 | `ImportOrigin` 数量增加（添加残缺/重复/非法记录） | 数组、`import_origin_count` 与相应状态计数变化，摘要变化 | ID-02/03/05 |
| 8 | `ImportOrigin` 数量减少（删除任一条） | 数组/计数变化，摘要变化；不得把“剩余记录相同”当作等价 | ID-02/03/05 |
| 9 | 孤儿 `ImportOrigin`（`item_id` 无对应 `knowledge_item`） | `SOURCE_IDENTITY_ORPHAN`（提议）fail-closed；零写入、零分类、零 Journal 提交；不得静默忽略或纳入错误 item | ID-02/03/05 |
| 10 | 同一记录集合不同读取/返回顺序（含正序、逆序、随机） | 按 `item_id` 与 `import_origin_id` code point 排序后 canonical JSON 完全相同，摘要一致 | ID-02/03/05 |
| 11 | 修改某条稳定 `import_origin_id`（删除+重建同字段记录） | 记录身份变化，摘要变化；不得只按三个身份字段去重而忽略稳定记录 ID | ID-02/03/05 |
| 12 | 同一 item 两条合法但身份对不同（instance/document 不同） | `import_origin_state=conflict`、`origin_state=incomplete`、有效来源身份为 null；零认领/零写入；不得任选一条 | ID-02/03/05 |
| 13 | 一条完整 + 一条残缺（或缺字段） | 汇总为 `incomplete`，**不得**提升为 `complete`，不得选用完整记录；有效身份 null | ID-02/03/05 |
| 14 | 两条重复（同三元组）+ 一条不同合法身份 | 汇总为 `conflict`（优先于 `duplicate`）；重复组大小仍保留；有效身份 null，不得合并/任选 | ID-02/03/05 |
| 15 | 唯一合法身份与 `knowledge_item.source_instance_id` 不一致（含 DB `null`） | 汇总为 `conflict`；不得用 DB 值补 origin 或用 origin 覆盖 DB；零身份写入 | ID-02/03/05 |
| 16 | 同一身份对、不同 `source_payload_hash` 的多版本记录 | 汇总为 `complete`（版本≠身份）；有效身份为该唯一对；`import_origin_identity_digest=null`（非单条），但所有版本均进入 `import_origins[]` | ID-02/03/05 |
| 17 | 无 `ImportOrigin` 且 `source_instance_id` 非空、无匹配 COMMITTED MATERIALIZE | `import_origin_state=none`（不套用 conflict）；仍按 D23 状态 4 fail-closed，不补/不覆盖/不认领 | ID-02/03/05 |

### H.3 HTTP 本机安全边界（D24）

> 本表全部【待验证】；归 **Batch D**，不阻塞 Batch A 非附件开发。

| 编号 | 测试输入 | 预期结果 | SQLite 验证法 | PostgreSQL 验证法 | 失败条件 | 并发 | 真实FS | 故障注入 |
|---|---|---|---|---|---|---|---|---|
| R1.3-NET-01 | 默认配置启动；分别配置 `127.0.0.1`、`::1`、`localhost` | 默认精确绑定 `127.0.0.1`；`::1` 允许；`localhost` 作为**绑定值被拒绝**；不出现 `0.0.0.0`/`::` | 真实启动 + 连接/监听探针 | 同左 | 默认对外 / 接受 localhost 绑定 | 否 | 否 | 否 |
| R1.3-NET-02 | 配置 `0.0.0.0`/`::`/LAN IP/主机名/畸形值；环境变量与配置文件入口 | 全部 **启动 fail-closed**（`NON_LOOPBACK_WITHOUT_AUTH`）；所有配置入口同一校验、无绕过 | 参数化真实启动矩阵 | 同左 | 任一入口成功监听非 loopback | 否 | 是 | 是 |
| R1.3-NET-03 | Host 矩阵：`127.0.0.1:port`、`localhost:port`、`[::1]:port`；攻击者域名、尾点、userinfo、多 Host、非法/错端口 | 精确本机 Host + 合法端口通过；其余全部拒绝；**来自 loopback 客户端的伪造 Host 同样拒绝** | 真实 HTTP 请求矩阵 | 同左 | 前缀/后缀匹配绕过 / 伪造 Host 放行 | 否 | 否 | 否 |
| R1.3-NET-04 | 修改请求携带跨源/`null`/畸形 Origin；同源 Origin；非浏览器无 Origin | 跨源/`null`/畸形一律拒绝（【提议】`CROSS_ORIGIN_REQUEST_REJECTED`）；同源通过；无 Origin 仅在 JSON + Host 校验下处理，**不获得认证语义** | 请求矩阵 | 同左 | 跨源修改成功 / 把 Origin 当认证 | 否 | 否 | 否 |
| R1.3-NET-05 | 修改接口发送表单/`text/plain`/无 Content-Type；携带 CORS/代理头 | 非 `application/json` 拒绝（415）；无 `Access-Control-Allow-Origin: *`、无跨源凭据；`X-Forwarded-*` 等**不授予访问权、不放宽 Host/Origin** | 请求矩阵 + 响应头检查 | 同左 | 接受表单/宽泛 CORS/代理头放行 | 否 | 否 | 否 |
| R1.3-NET-06 | DNS Rebinding（攻击者域名解析到 127.0.0.1）；代理/隧道说明；依赖与错误响应 | 伪造 Host 请求被拒绝；文档明确代理/隧道/端口转发**不属于 A1-04**；无认证依赖、不宣称已鉴权；错误只回稳定码，无 host/port/堆栈/`str(exc)` | 真实重绑定请求 + 依赖清单 + 日志 | 同左 | 重绑定成功 / 泄漏敏感信息 / 虚假鉴权声明 | 否 | 是 | 是 |

### H.4 R1.3 执行纪律

1. 本段所有新增项保持 **【待验证】**，不得预先写入任何“已验证”结论；本轮（R1.3 第六轮最终冻结前定点修正）**未执行任何测试**，也未新增验收编号。
2. Hash 项须比对**真实导出/导入文本与 DB**，不得只读代码推断；`R1.3-HASH-03` 必须证明四类冲突（尤其重复键在 YAML 折叠前被拒绝）均**零数据库写入**；`R1.3-HASH-04` 须同时证明 Core/A1-02 文件与 schema 未改。
3. 身份初始化项须使用**真实 SQLite + 真实 PG**，覆盖状态 2a/2b/3/4 与冲突态（尤其状态 4 不补不覆盖、无 Journal 证据不认领），并验证 **Journal 恢复优先**（有效 `PREPARED MATERIALIZE` 先恢复、DB 空/等于目标才恢复、其他值/摘要不符 fail-closed、恢复完成前不分类/不写身份）、`COMMITTED` 只补归档不重复写 DB、MATERIALIZE 物化/归档、rotate 九步 Journal 顺序、`PREPARED`+旧 ID 的 DB 重查、第二次独立 rotate、同 `operation_id` 重入、OS 锁、各崩溃点恢复与失败中止；同时验证 **current→archive 同卷原子落位、current/archive 同内容去重、异内容 fail、归档失败禁新操作、append-only 不自动删除**；并验证 Journal v1 的 `materialization_items` 字段/排序/编码/空值/版本及三个摘要；`identity_audit_digest` 必须覆盖全部知识文档、**每项逐条覆盖全部 `ImportOrigin` 原始记录（残缺/重复/非法均不得过滤或归一化，稳定记录 ID 排序，记录数/状态可审计，孤儿 fail-closed）**、在每次 DB 写后/恢复时从 DB 重读重算，rotate 前后各重算一次，且不得含 exporter；H.2 的 17 个 ImportOrigin 判别用例必须逐项取证，证明原始记录变更均改变摘要、读取顺序不改变摘要，且多记录组合按状态表判定（多合法身份/DB 不一致→conflict，完整+残缺→incomplete，重复+不同身份→conflict，同身份多版本→complete），冲突零认领；Canonical JSON v1 须以 §22.2 的 8 组固定向量逐字节核对序列化与 SHA-256，重复键拒绝必须在解析层取证。不得用 `MAX(imported_at)`、随机数据或“非空即本地”推断冒充。Windows 目录同步不保证断电持久，验收须如实标“有条件/待验证”。
4. 网络项须**真实启动进程**，覆盖默认绑定、非 loopback fail-closed、Host/Origin/Content-Type、DNS Rebinding 与代理头；不得只做单元 mock。
5. 原 R1（§E）、R1.1（§F）、R1.2（§G）全部编号保留，不覆盖、不删减、不弱化；`R1.3-*` 仍为 15 项，无新增编号。
6. **产品约束一致性**：D22–D24 不得改写 Offline（Backup 停止 + 同 OS 锁）/ Single（单 Backend/单 worker）/ Strict（无新迁移）三约束；D24 不得被解释为“已认证可公网”。**D24 归 Batch D，不阻塞 Batch A 非附件开发。**

## 验收执行约定

1. **每项须真实取证**：真实测试输出 / 真实模型联调（导入导出不依赖模型）/ 真实文件系统 / 必要时浏览器截图（in-app Browser：bringToFront、fullPage 超时→viewport+重试、urllib UTF-8）。
2. **如实区分**「已验证 / 有条件 / 未通过」；规划不得写成已完成；离线 SQL ≠ 真实数据库验证；无 PG 环境先报告等待批准，**不得伪造 PG 通过**。
3. **高风险模块独立验收**（GC/quarantine/孤儿扫描、StorageKeyLock、备份恢复、导入审核门禁、链接键重建）不得合并掩盖。
4. 验收报告落 `docs/acceptance/V2-A1-04/`（开发阶段产出，本轮不写）；MILESTONES 更新属 A1-06。
5. 本矩阵所有项当前 **【待验证】**；编号供 risk-register / open-decisions / 测试文件交叉引用。
