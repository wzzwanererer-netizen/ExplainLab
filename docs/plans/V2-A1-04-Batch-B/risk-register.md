# Batch B Risk Register

> **Architecture Freeze Approved · 2026-11-23（北京时间）**。本文件属于正式冻结的设计基线。设计冻结不代表实现验收通过；真实 PostgreSQL、Windows/POSIX 与故障注入取证仍待执行。架构变更须经正式审批。

> 本文件记录 Batch B 设计冻结阶段的风险与裁决落点。严重度：**高/中/低**；状态：**开放/缓解中/已裁决（设计）/已接受**。所有“缓解/已裁决”均为设计约束，不代表已实现或已验证。

## 1. 继承风险（来自 R1.3 / 既有风险登记）

| 组 | 风险 | Batch B 影响 | 处置 |
|---|---|---|---|
| R-ATT | 附件物理与 DB 非原子 | 上传/approve 可能产生孤儿或缺失 | 明确“物理先于 DB”；ORP 收敛；下载 503；不宣称原子 |
| R-FS | Windows 占用/rename/跨卷 | 发布、quarantine、purge、staging 清理可能失败 | 同卷启动校验；短重试；可重试状态；不强制删除 |
| R-SEC | 路径穿越/MIME 伪装/SVG | 上传文件名/内容可能攻击浏览器或逃逸根 | 文件名不进路径；magic+白名单；SVG 拒绝；nosniff |
| R-COMP | 多进程/多 worker 竞争 | 双 GC、双上传、ORP 与 GC 可能竞争 | StorageKeyLock + fencing；排序加锁；条件更新 |
| R-CON | 配置/默认参数漂移 | TTL/等待/上限不一致 | 配置冻结；启动校验；测试断言默认值 |
| R-DL | 大文件/资源耗尽 | 10 MiB×多附件可耗尽内存/磁盘；JSON base64 再放大 33% | 单文件 10 MiB；编码长度上限；导入总数/总字节上限（O-B05）；不宣称流式上传 |

## 2. Batch B 新风险

| ID | 风险 | 严重度 | 可能性 | 影响 | 缓解/设计约束 | 状态 |
|---|---|---|---|---|---|---|
| B-R01 | **staging 命名与 review_id 解耦**（D-B01）：R1.3 用 `<review_id>/<operation_id>`，但提交前 review_id 未知 | 高 | 高 | 清扫/approve 找不到 staging；误删/漏删 | 使用 `staging_id`；manifest 记录；pending 引用集合；**D-B01 已裁决批准** | 已裁决（设计） |
| B-R02 | **PG fencing token 来源**（D-B02）：advisory lock 无 token；`storage_lock` 行原本是 SQLite 租约 | 高 | 高 | 旧 worker 可能继续写；或 token 回退 | 每批一个专用物理会话，按实际二元组去重与排序；完整 key 独立 token；release 不删行；行 TTL 过期不授权接管；**D-B02 已裁决** | 已裁决（设计） |
| B-R03 | **导入附件 transport 原未定义**（O-B01） | 高 | 高 | IMP-19/R1-IMP 附件导入无法实现或验收；前端无入口 | **O-B01 已裁决 ZIP-only**；JSON 附件单篇 400、批量逐篇 unsupported；不引入 multipart | 已裁决（设计） |
| B-R04 | manifest 在 approve 时被追加/篡改 | 高 | 中 | 未审核附件被应用；摘要失配 | manifest 只在 pending 写入；envelope digest；approve 只读；409 | 缓解中 |
| B-R05 | 正式 blob 被静默覆盖 | 高 | 中 | 数据损坏/引用错乱 | no-clobber；同 hash 复用；异 hash 冲突；发布后校验 | 缓解中 |
| B-R06 | promote 复制/发布失败留下半成品 | 中 | 高 | 孤儿、staging 残留、approve 失败 | staging 保留；临时文件；ORP；重试 | 缓解中 |
| B-R07 | approve ① 成功后清理 staging 前崩溃 | 中 | 中 | staging 残留 | ORP 宽限清扫；正式引用已提交 | 缓解中 |
| B-R08 | approve ① 失败但 blob 已发布 | 中 | 中 | 孤儿 | ORP 24h 入 GC；不删 staging；可重试 | 缓解中 |
| B-R09 | GC 在引用回升时误删 | 高 | 中 | 附件丢失 | 24h 安全期；purge 前复核；引用>0 恢复/cancelled；锁 | 缓解中 |
| B-R10 | GC 在 quarantine 后崩溃 | 中 | 中 | 残留/状态不明 | 每任务隔离槽、缺记录重新计时、后继接手新代次；ORP 持锁有条件恢复 | 缓解中 |
| B-R11 | ORP 误删 pending staging | 高 | 中 | 审核无法完成；用户数据丢失 | 生产者与清扫/清理共用 staging_id guard；持锁复核所有 pending；疑似损坏 fail-closed | 缓解中 |
| B-R12 | 条目删除后 24h+ 才回收 | 中 | 高 | 磁盘短期膨胀 | 决策 22 接受；ORP 兜底；报告 | 已接受 |
| B-R13 | MERGE_DUPLICATE 不迁移附件 | 中 | 高 | 目标 item 无附件；源删除后回收 | 决策 21 接受；文档明确；不偷偷迁移 | 已接受 |
| B-R14 | 原未定义：附件-only 导入 Active（O-B08） | 中 | 中 | 附件不生效或静默忽略 | **O-B08 已裁决**：不独立触发 review；Active 附件-only 显式 400 `ATTACHMENT_ONLY_IMPORT_UNSUPPORTED`，零 staging/pending；独立上传走附件 API | 已裁决（设计） |
| B-R15 | 原无正式裁决：单次导入附件总数/总字节 | 中 | 中 | DoS/磁盘耗尽 | **O-B05 已裁决**：100 个/100 MiB/单文件 10 MiB；staging 宽限 24h；服务端强制 | 已裁决（设计） |
| B-R16 | 无 `content_hash` 索引（决策 2） | 低 | 高 | `find_by_hash` 慢 | 不进入热路径；去重用 `(item_id, key)`；保留端口 | 已接受 |
| B-R17 | 同 item+key 重复行 | 低 | 中 | 计数/展示重复 | 锁内二次去重；approve 检查既有行；manifest 重复拒绝；无唯一约束兜底 | 缓解中 |
| B-R18 | `.tmp` 残留不自动清理（ORP-02） | 低 | 中 | 磁盘缓慢增长 | Batch B 只报告；上传自清理；后续批次处理 | 已接受 |
| B-R19 | 附件导出继续不支持（决策 20） | 中 | 高 | 用户期望落空；IMP-16 附件部分不可用 | 明确 400；不纳入 Batch B 退出；文档/前端提示 | 已接受 |
| B-R20 | 无鉴权/本机单用户 | 高 | 中 | 若暴露公网可读写附件 | Batch B 不暴露公网；Batch D 处理；验收声明 | 已接受（范围） |
| B-R21 | GC quarantine 等待使用 `running` + 过期租约 | 中 | 中 | 状态看起来“卡住”；claim 条件复杂 | 与 acceptance-matrix GC-04 对齐；`next_retry_at` 阻止提前接管；报告解释 | 缓解中 |
| B-R22 | 两次 commit 口径（①业务/②索引） | 中 | 高 | 客户端误判失败；文档/验收歧义 | **D-B08 已裁决**：①为业务提交边界（含附件）；②索引独立且失败不回滚① | 已裁决（设计） |
| B-R23 | Windows 文件占用导致 GC 延迟 | 中 | 高 | quarantine/purge 重试；磁盘暂不释放 | 短重试；failed_retryable；不强制删 | 缓解中 |
| B-R24 | 启动时跨卷/权限失败导致应用不可用 | 中 | 低 | 不能启动 | fail-fast；明确错误；不降级到临时目录 | 已接受 |
| B-R25 | 日志/报告泄露文件名/路径 | 中 | 中 | 隐私泄露 | 只记 storage_key/id/状态；报告脱敏；不记内容 | 缓解中 |
| B-R26 | IMP-19 附件报告字段与 Core 模型不一致 | 低 | 中 | 验收口径不清；可能诱使改 Core | **D-B12 已裁决**：不改 Core `ImportReport`；用既有 warnings/errors 或 backend 摘要 | 已裁决（设计） |
| B-R27 | SVG 策略与矩阵 D-08 待审批表述不一致 | 低 | 高 | 验收预期冲突 | 按决策 23 固定拒绝；README/Acceptance 显式覆盖 | 已接受 |
| B-R28 | 大批量附件 approve 长时间持有多把锁 | 中 | 中 | 锁竞争/心跳压力/超时 | 单次总数/总字节上限；15s 心跳；超限 413；分片复制；不无限扩大 | 缓解中 |
| B-R29 | 并发删除同一 storage_key 的最后两条引用，双方 COUNT 均非 0，可能都不入队 `gc_task` | 中 | 中 | 物理 blob 回收延迟到 ORP（最长约 24h 扫描 + 24h 隔离） | 删除事务不做物理删除；ORP 以 `count_references==0` 兜底；验收记录该场景，不宣称即时入队 | 已接受（范围） |
| B-R30 | 上传采用 JSON base64，而非 multipart/流式 | 低 | 高 | 10 MiB 解码放大至约 13.3 MiB；大请求内存占用；无法边收边写 | 编码长度上限；解码后 10 MiB 上限；本机单用户；不宣称流式上传；**O-B09 已裁决** | 已裁决（设计） |
| B-R31 | manifest/envelope 损坏导致 pending 无法 reject | 高 | 中 | 用户被卡在 pending，staging 长期占用 | 共同 review_id 决议锁；reject 轻量预检不以摘要失败阻断；归属不可信则跳过 staging 清理，由 ORP 兜底；approve 仍严格 fail-closed；若存在其他损坏 pending，ORP 整轮跳过可能延迟，需人工介入 | 缓解中 |
| B-R32 | **SQLite 写事务与 StorageKeyLock 互等**：Core approve/Draft flush 后再用独立连接写 `storage_lock` | 高 | 高 | approve/导入可能死锁或长期等待；测试假死 | 附件锁在 S1/Core approve 之前预取（D-B15/O-B10 已裁决）；D23 内部恢复事务结束后取锁；GC claim 先提交；上传/Draft/approve 均先发布再进入业务写；禁止在未提交写事务中取锁 | 已裁决（设计），实现需专项验证 |
| B-R33 | **SQLite 读事务阻止锁行 commit**：上传预检/ORP 收集 pending_ids 的 session 未关闭就取锁 | 中 | 中 | 锁获取超时；并发行为偶发失败 | 取锁前关闭/rollback 只读 session；锁内去重用同一写 session；SQLite 测试覆盖 | 缓解中 |
| B-R34 | SQLite 心跳 renew 与主写事务竞争（busy） | 中 | 中 | 心跳误判失配导致 approve 中止；或锁续租延迟 | 区分 False（失配）与 busy 异常；busy 重试；commit 前用同一 session `verify_all`；TTL 60s 余量 | 缓解中 |
| B-R35 | `gc_task` 无活跃唯一约束，`ensure_gc_task` 并发下可能重复入队 | 中 | 中 | 同 key 多条任务；观感/调度开销 | 去重仅尽力；GC 幂等（锁+复核+确定性 quarantine）；验收不宣称全局唯一；不新增索引 | 已接受（范围） |
| B-R36 | 无 hard link 文件系统上的发布降级 | 中 | 中 | Windows FAT/exFAT 无 link；POSIX 异常 FS 无 link | 按 F12（storage §6.1）分类；仅明确不支持才走 Windows 同卷 no-clobber rename；POSIX 保留失败路径；发布后校验 | 已接受（诚实边界） |
| B-R37 | 非标准分片位置的 64hex 文件被误当正式 blob | 低 | 低 | 可能被 ORP 入队/GC 删除 | ORP 校验路径必须等于 shard 计算路径；不符只报告 `misplaced_blob`，不删不入队 | 缓解中 |
| B-R38 | “退避 60s→6h”与 8 次指数公式不一致 | 低 | 高 | 验收误以为 8 次内会到 6h；文档口径冲突 | **O-B11 已裁决**：第 8 次公式为 7680s，但终态无下次调度，21600s 仅为上限；不伪造 6h 到达 | 已裁决（设计） |
| B-R39 | `attachment` 无 `item_id` 索引，上传/approve 的 `(item_id,key)` 去重按 item 查询可能扫表 | 低 | 中 | 大表时上传/approve 变慢 | 决策 2 禁止新增索引；去重仅列该 item 行；本地单用户可接受；未来另立迁移 | 已接受（范围） |
| B-R40 | staging 完成性/活动时间误判 | 高 | 中 | ORP 把正在写入或 pending 引用的目录删除；或根目录 mtime 滞后导致长期残留 | `.creating`/`.activity`/`.complete` + 普通文件最大 mtime；pending 引用优先；`.complete` 缺失 approve fail-closed；ORP 报告 `staging_incomplete` | 缓解中（需真实 FS 验证） |
| B-R41 | 下载校验后按路径重开导致 TOCTOU | 高 | 中 | 校验与输出内容不一致；隔离/替换窗口 | 只打开一次，同句柄 size/hash + `seek(0)` 流式输出；禁止 `FileResponse`/路径重开；外部原地改写仍属残余风险 | 缓解中（需真实并发验证） |
| B-R42 | archived item 状态在执行中途变化 | 中 | 中 | 上传/approve 向归档 item 写入附件 | 早拒之后在业务事务内保护状态（approve 在 Core 改写前）；上传和 approve 409，导入 archived 400；读和删除允许 | 缓解中 |
| B-R43 | 文本 MIME 子类型无法可靠区分 | 低 | 高 | 误以为可区分 TXT/MD/CSV；错误拒绝合法文本 | 文本只做严格 UTF-8 + 无 NUL；以声明白名单 MIME 入库；文档/验收明确不宣称区分 | 已接受（诚实边界） |
| B-R44 | 列表端点泄露跨 item 元数据或引入读放大 | 中 | 低 | 信息泄露；大列表性能 | 路由按 item 作用域过滤；只读元数据；无分页不承诺大数据优化；跨 item 404/空列表按契约 | 缓解中 |

## 3. 设计裁决落地（全部关闭）

| ID | 裁决 | 影响 | 状态 | 关联 |
|---|---|---|---|---|
| D-B01/O-B02 | 批准 `staging_id` 作为独立 staging 目录身份 | 全部导入附件/清扫 | 已裁决 | B-R01、R1.1-IMP-41 |
| D-B02/O-B03 | PG 复用 `storage_lock` 行存单调 fencing token；Advisory Lock 为互斥权威，行 TTL 过期不授权接管 | LCK/GC 并发正确性 | 已裁决 | B-R02、LCK-10 |
| D-B03/O-B01 | 导入 transport 固定 ZIP-only；JSON 附件单篇 400、批量逐篇 unsupported；不引入 multipart | IMP-19、R1-IMP 附件导入 | 已裁决 | B-R03 |
| D-B04 | 附件导出继续不支持，覆盖 IMP-16 附件部分 | 验收范围 | 已裁决（用户） | B-R19 |
| D-B05 | `find_by_hash` 不进热路径 | 性能/去重 | 已纳入 | B-R16 |
| D-B06 | `failed_permanent` 自动终态 | GC 运维 | 已纳入 | GC-09 |
| D-B07 | `ATTACHMENT_REVIEW_UNSUPPORTED` 保留语义 | 兼容 | 已纳入 | API §7 |
| D-B08 | 事务①为业务提交边界（含附件）；事务②为独立索引提交，失败不回滚① | 验收/客户端 | 已裁决 | B-R22 |
| D-B09 | 上传去重按 `(item_id,key)` | 去重语义 | 已纳入 | B-R17 |
| D-B10/O-B04 | **新增** `GET /attachments` 元数据列表；不返回内容/路径 | 客户端体验 | 已裁决 | B-R44、ATT-13 |
| D-B11 | 不采用 LCK-09 单写者/库级串行降级 | 并发语义 | 已裁决 | LCK-09 |
| D-B12 | IMP-19 report 附件结果不改 Core `ImportReport` | 验收呈现 | 已裁决 | B-R26 |
| D-B13 | SVG 固定拒绝，覆盖 D-08 待审批策略 | 验收预期 | 已裁决（用户） | B-R27 |
| D-B14/O-B09 | 独立上传固定 JSON base64，不引入 `python-multipart` | ATT-01…13、请求体大小 | 已裁决 | B-R30 |
| D-B15/O-B10 | 附件锁在 S1/Core approve 之前预取，D23 恢复事务先关闭，物理发布在业务写前 | Active approve 事务/锁顺序 | 已裁决 | B-R32 |
| D-B16/O-B11 | 第 8 次公式值 7680s，终态无下次调度；21600s 仅上限 | GC 退避验收 | 已裁决 | B-R38 |
| O-B05 | staging 宽限 24h；单次 100 个/100 MiB；单文件 10 MiB；pending 引用优先 | ORP/DoS | 已裁决 | B-R15、B-R40 |
| O-B06 | archived 禁止新增附件；允许列表/下载/删除引用 | 产品语义 | 已裁决 | B-R42、ATT-13 |
| O-B07 | 不新增 GC 管理 HTTP 端点；保留内部人工恢复/重试与审计日志 | 运维 | 已裁决 | GC-11 |
| O-B08 | 附件-only 不独立触发 Active review；Active 附件-only 显式 400 拒绝 | 导入语义 | 已裁决 | B-R14、IMP-19 |

## 4. 风险接受与退出

F13 的事务所有者见 architecture §4.2。业务①与索引②分开，外层协调器独占 commit/rollback。

- **不可接受**：静默覆盖正式 blob；pending 阶段写正式引用；GC 未持锁删除；把物理+DB 宣称原子；伪造 PG/Windows 验收。
- **有条件接受**：SQLite 租约非严格互斥；24h/5min 回收延迟；merge 不迁移附件；附件导出不支持；无鉴权仅本机；`.tmp` 残留只报告。
- **必须实现验收**：D-B01/D-B02/O-B01/O-B05/O-B06/O-B08/O-B09/O-B10/D-B08/D-B12/D-B13；裁决已关闭，但对应实现与真实证据尚未产生，未验证前不得标“通过”。
- **风险关闭条件**：对应验收项有真实证据 + 代码审查 + 运维文档；仅设计文档不足以关闭。

## 5. 监控与审计

- 每轮 ORP 报告计数：`orphan_blobs`、`missing_blobs`、`hash_mismatched`、`quarantine_residual`、`staging_orphans`、`staging_incomplete`、`temp_residual`。
- 告警阈值（设计建议，不在 Batch B 实现外部告警）：`missing_blobs>0`、`hash_mismatched>0`、`failed_permanent>0`、`needs_manual>0`。
- 日志只记 `storage_key`/id/状态/错误类型；不记文件内容/文件名/绝对路径。
- 审计证据保存于验收目录，不提交 `backend/data/`。

## 6. 最终签发检查（非未决问题）

以下裁决已全部关闭，本节仅用于独立审计核对落点，不再要求选择方案：

1. D-B01/O-B02 `staging_id` 已批准 → `attachment-lifecycle.md` §3、`active-review-integration.md` §3。
2. D-B02/O-B03 PG advisory 权威 + token 行已批准 → `storage-and-lock-contract.md` §4.3/§4.5、LCK-10。
3. O-B01 ZIP-only 已批准 → `api-contracts.md` §5.1、`attachment-lifecycle.md` §3.1。
4. O-B08 Active 附件-only 显式拒绝已批准 → `active-review-integration.md` §3.3/§9、IMP-19。
5. O-B05 24h/100/100 MiB/10 MiB 已批准 → `architecture.md` §5、`attachment-lifecycle.md` §3.2、ORP-§6.4。
6. O-B04 列表端点已批准 → `api-contracts.md` §2.4、ATT-13。
7. O-B06 archived 策略已批准 → 上传 409、下载/列表/删除允许、ATT-13。
8. O-B07 无 HTTP 管理端点已批准 → `gc-and-orphan-recovery.md` §2/§10。
9. D-B11 不采用单写者降级已批准 → LCK-09。
10. D-B12 不改 Core `ImportReport` 已批准 → IMP-19 注记、`api-contracts.md` §5.1。
11. D-B08 ①业务/②索引已批准 → `active-review-integration.md` §2、R1-IMP-08。
12. D-B13 SVG 固定拒绝已批准 → `api-contracts.md` §4、ATT-05。
13. O-B09 JSON base64 已批准 → `api-contracts.md` §2.1、ATT-01。
14. O-B10 恢复事务已关闭 + 预发布已批准 → `active-review-integration.md` §2/§5.2、§8.1。
15. O-B11 公式、上限与终态口径 → `gc-and-orphan-recovery.md` §4.3、GC-08/09。

**复审状态**：八项 P1 已完成整改并通过静态复审。6 条继承风险和 44 条 Batch B 风险作为冻结实施基线，运行期证据仍待取证。
