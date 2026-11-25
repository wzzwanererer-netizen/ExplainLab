# Batch B Acceptance Plan

> **Architecture Freeze Approved · 2026-11-23（北京时间）**。本文件属于正式冻结的设计基线。设计冻结不代表实现验收通过；真实 PostgreSQL、Windows/POSIX 与故障注入取证仍待执行。架构变更须经正式审批。

> **状态声明：53 个验收编号已冻结，所有条目当前均为【待验证】。** 本文件是执行计划，不是通过证明；未真实运行的项不得写成“已通过”。验收必须在真实 SQLite、真实文件系统、真实 PostgreSQL（门控）与真实 Windows 环境取证。

## 1. 环境与取证

| 环境 | 要求 |
|---|---|
| OS | Windows 10/11 x64（主验收环境）；另跑 Linux/POSIX 以覆盖 fsync/权限差异 |
| Python | 3.11（审计基线 3.11.9），`uv sync --locked` |
| SQLite | 默认 `backend/data/explainlab.db` 或测试临时 DB；真实 FTS5 不影响本批 |
| PostgreSQL | 真实实例，`EXPLAINLAB_PG_TEST_URL=postgresql+psycopg://...`；未设置时 PG 项必须标“未验证”，不得跳过冒充通过 |
| 文件系统 | `tmp_path` 真实目录；正式根/ staging / quarantine 同卷；Windows 真机 |
| 工具 | `pytest`、`TestClient`、`threading.Barrier`、子进程 kill、DB 查询、文件 hash 比对 |
| 证据 | 测试输出、DB 查询结果、文件树/`stat`、hash、日志（脱敏）、必要时截图；不提交 `backend/data/` |

通用命令：

```bash
uv sync --locked
uv run ruff check
uv run pytest -o addopts="--import-mode=importlib" \
  backend/tests/test_attachment_storage.py \
  backend/tests/test_attachment_validation.py \
  backend/tests/test_attachment_api.py \
  backend/tests/test_attachment_staging.py \
  backend/tests/test_attachment_review.py \
  backend/tests/test_attachment_gc.py \
  backend/tests/test_attachment_orp.py \
  backend/tests/test_storage_lock_sqlite.py

# PostgreSQL（真实实例；不得用 SQLite 结果替代）
EXPLAINLAB_PG_TEST_URL='postgresql+psycopg://...' uv run pytest \
  backend/tests/test_storage_lock_pg.py backend/tests/test_attachment_pg.py

# Windows 专项（真机）
uv run pytest backend/tests/test_attachment_windows.py
```

## 2. 通用测试装置

- `clock`：GC/ORP 服务接受可注入 `now()`；测试推进时间或直接改 `quarantined_at`/`next_retry_at`/文件 mtime，**不 sleep 24h**。
- `fault`：monkeypatch `os.link`/`os.rename`/`Path.open`/`Session.commit`/repository 方法；每个故障点独立取证，需要验证恢复时可组合屏障与故障。
- `concurrency`：两个真实 session/连接 + `Barrier`；SQLite 使用文件 DB（非 `:memory:`），PG 使用两个连接。
- `fs`：每个用例独立 `tmp_path`；结束后断言正式根/staging/quarantine 的文件集合。
- `db`：直接 SQL 查询 `attachment`/`gc_task`/`storage_lock`；不依赖响应体推断。
- `subprocess`：LCK-07/GC-07 用子进程持锁/写文件后 `kill`，父进程验证接管/恢复。

## 3. ATT：上传/列表/下载/删除

| ID | 测试条件/输入 | 测试方法 | 预期结果 | 故障注入点 | SQLite/PG 差异 | Windows 真实环境 |
|---|---|---|---|---|---|---|
| ATT-01 | 合法 PNG/PDF/TXT（≤10 MiB，白名单） | JSON base64 上传；查 `attachment` 行；查分片路径；重算 hash | 201；`storage_key==content_hash==sha256`；文件在 `ab/cd/<key>`；size/mime/filename 正确；无临时残留 | 无 | 同逻辑；PG 仅换 DB/连接池 | 需要：真实路径/权限/大小写 |
| ATT-02 | 相同内容上传到两个 item | 两次 JSON 上传；查物理文件数、两行、`count_references` | 物理仅 1 份；2 行；COUNT==2；两次均成功（第二 item 201） | 无 | 同左 | 需要：同卷 hard link/复用 |
| ATT-03 | >10 MiB 文件；非法 Base64 | JSON 上传 10 MiB+1 解码内容；另传非法 Base64；查 DB/FS | 413 `ATTACHMENT_TOO_LARGE` / 400 `ATTACHMENT_BASE64_INVALID`；无行；无正式/临时残留 | 限制边界 10 MiB/10 MiB+1；坏 Base64 | 同左 | 需要：大文件解码/内存边界 |
| ATT-04 | 声明 `image/png`，实际 JPEG/文本；或声明 `text/plain`，实际 PNG；文本子类型交叉（TXT/MD/CSV） | 构造伪装字节并 Base64 编码；上传 | 二进制 magic 不符 → 415 `ATTACHMENT_CONTENT_MISMATCH`；文本含 NUL/非法 UTF-8/二进制 magic → 415；**文本子类型不因内容被区分**：合法 UTF-8 声明为三种文本 MIME 均接受并以声明 MIME 入库；不得声称仅凭字节区分 TXT/MD/CSV | 替换 magic 前 16 字节；文本 NUL/非法序列 | 同左 | 需要：解码/校验内存 |
| ATT-05 | 声明 `image/svg+xml`；另以文本 MIME 提供合法 UTF-8 SVG 字符串 | 上传 SVG（Base64）；下载尝试 | SVG MIME 415、无行/文件；合法 UTF-8 文本可按文本保存，只以文本 MIME、attachment 与 nosniff 下载 | 声明/内容两种伪装 | 同左 | 需要：浏览器/下载头验证 |
| ATT-06 | 文件名 `../../evil.png`、`C:\x.png`、含 CR/LF/控制字符 | JSON 上传；查落点与响应头 | 文件名清洗为安全显示名；落点仍在存储根；`storage_key` 由内容派生；响应头无 CR/LF | 路径穿越/保留名 | 同左 | 需要：Windows 路径/保留名 |
| ATT-07 | 正常下载；跨 item 猜测 id；用户传路径 | GET 两路径；比对字节；尝试用文件名/path 参数 | 200 正确字节；跨 item 404 `ATTACHMENT_NOT_FOUND`；不接受用户路径；头正确 | 路径注入 | 同左 | 需要：流式/大文件 |
| ATT-08 | 删除引用（独享/共享） | DELETE；查行/物理/`gc_task` | 204；独享：行删、物理仍在、`gc_task pending`；共享：行删、COUNT>0、**不**入队 | 无 | 同左；PG FK/CASCADE 真实 | 需要：文件仍存在 |
| ATT-09 | 上传后篡改物理字节；上传后重算；校验后路径替换 | 篡改文件；GET；上传校验；下载校验后/输出前重命名或替换路径 | 上传 hash 一致；篡改后 GET 503 `ATTACHMENT_BLOB_CORRUPTED`；校验失败不返回部分内容；下载使用**同一已打开句柄**完成 size/hash 与流式输出，校验后路径替换不改变已校验内容；取消/校验失败关闭句柄（Windows 若因共享模式拒绝替换，按实际占用结果取证） | 修改文件字节；校验后替换路径 | 同左 | 需要：文件占用/替换 |
| ATT-10 | 两请求并发上传同内容 | Barrier 双线程/双 JSON 请求；同 item 与不同 item 两组；查文件数/行数及上传与 GC/ORP 屏障 | 仅一份正式文件；不同 item 两行；同 item 201/200 且同 ID、唯一引用；发布至 commit 间 GC/ORP 不得误隔离；锁串行；无损坏 | 并发竞争 | SQLite 租约；PG advisory；均需真实并发 | 需要：双进程/句柄 |
| ATT-11 | 发布成功后 DB commit 失败 | monkeypatch commit 抛错；上传；查 FS/DB；触发 ORP | 无 `attachment` 行；正式 blob 成孤儿；ORP 24h 后入 GC；无临时残留 | commit 失败 | 同左；PG 事务回滚真实 | 需要：文件仍存在 |
| ATT-12 | 发布 rename/link 失败 | 分别注入目标已存在、跨卷、Windows 占用、拒绝访问、明确不支持和未识别 I/O；上传及降级 rename 竞争 | 按 storage §6.1 逐分支核对现有错误码和 guard；仅明确不支持才可在 Windows 同卷 no-clobber 降级；目标已存在时校验，绝不覆盖；失败无新引用 | `os.link` / `os.rename` 注入各错误 | 同左 | 需要：真实 Windows 占用、目标竞争及 POSIX 行为 |
| ATT-13 | 元数据列表 + archived 策略（O-B04/O-B06） | 向含多个附件的 item 发 `GET /attachments`；将 item 置 archived 后尝试上传/列表/下载/删除；跨 item 列表；另以屏障令归档在预检后、写保护前提交 | 列表 200、仅该 item 元数据、稳定排序、无路径/内容；archived 上传 409 `ATTACHMENT_ITEM_ARCHIVED` 且零新增行；早拒无发布，竞态已发布无引用 blob 由 ORP 收敛；archived 列表/下载/删除允许；跨 item 不泄露 | archived 状态；跨 item id | 同左；PG 真实查询 | 需要：真实状态/文件 |

> ATT-07/08 的矩阵路径为简写；Batch B 使用 item 作用域路由（`/api/knowledge/{item_id}/attachments/{attachment_id}`），以便校验归属并避免跨 item 猜测。
>
> ATT-05 按用户决策 23 固定“拒绝 SVG”，覆盖 `acceptance-matrix §B.1` 中“deny_inline/消毒【待审批 D-08】”的未决表述；不再测试消毒分支。
>
> ATT-06 按矩阵“清洗为安全显示名”执行；文件名不进入磁盘路径，因此不存在“清洗后逃逸”的路径。
>
> ATT-08 的并发最后两条引用删除：两侧 COUNT 可能均非 0，允许不产生 `gc_task`，由 ORP 兜底（B-R29）；验收断言物理文件不丢、最终可回收，不宣称即时入队。
>
> ATT-13 的列表只读 DB 元数据，不取 `StorageKeyLock`、不重算 hash；不得用“列表时校验”替代下载校验。

## 4. LCK：StorageKeyLock 双方言

| ID | 测试条件/输入 | 测试方法 | 预期结果 | 故障注入点 | SQLite/PG 差异 | Windows 真实环境 |
|---|---|---|---|---|---|---|
| LCK-01 | 新 key acquire | 调 `acquire(key, owner, 60)`；查 `storage_lock` | 返回 lease；token≥1；expires≈now+60；行 owner/token 匹配 | 无 | SQLite 行；PG advisory+token 行 | 不需要 |
| LCK-02 | 两 owner 同 key | Barrier 双线程 acquire | 仅一成功；另一 `None`；行仅一 owner | 并发 | SQLite 条件 UPDATE；PG advisory 互斥 | 不需要 |
| LCK-03 | 租约过期后接管 | 推进时间/改 expires；旧 lease 不 release；新 owner acquire | 新 acquire 成功；token 严格 +1；旧 lease verify/renew false | 过期 | SQLite 条件 UPDATE；PG 关闭旧连接释放 advisory | 需要：进程 kill 场景 |
| LCK-04 | renew 匹配 | acquire 后 renew；查 expires | 返回 True；expires 延后；rowcount==1（SQLite） | 无 | PG advisory 无需续租，行 expires 仍更新 | 不需要 |
| LCK-05 | renew 失配（旧 token/被接管） | 接管后旧 lease renew；执行受保护删除 | renew/verify False；旧 worker 立即中止；无文件被删 | 构造失配 | 同左 | 需要：物理步骤前 verify |
| LCK-06 | release 匹配/失配 | 正常 release；接管后旧 lease release | 匹配 True；失配 False；不释放他人；行保留 token | 构造失配 | PG 额外 unlock；SQLite 不删行 | 不需要 |
| LCK-07 | 持锁进程崩溃 | 子进程 acquire 后 kill；父进程等待/接管 | SQLite 过期可接管；PG 会话结束自动释放；无永久锁 | kill | SQLite 过期；PG 连接关闭 | 需要：真实进程 kill |
| LCK-08 | 锁与物理间隙 TOCTOU | 分别暂停在最终 verify 前和 verify 后；另一 owner 接管 | 已观察失配必须中止；verify 后停顿验证残余窗口与后续隔离恢复，不宣称撤销已进入的 syscall | 延迟+接管 | 同左 | 需要：真实文件操作 |
| LCK-09 | 严格互斥降级（D-04） | 检查是否提供单写者/库级串行降级；检查声明 | **不宣称严格互斥**；Batch B 不提供额外降级模式；按默认参数与诚实边界记录 | 无 | PG advisory 为互斥；SQLite 为租约 | 不需要 |
| LCK-10 | PG 行 TTL 过期但 advisory 仍存活（O-B03/D-B02） | 两个真实连接：连接 A 取 advisory + 写行；把行 expires 推到过去；连接 B 尝试 acquire/接管/隔离；再关闭 A 后重试；构造两不同完整 key 同投影及跨批竞争；100 keys、部分失败、中途断连 | 行过期不授权接管：B 在 A 存活时 acquire 失败/不得删除；A 关闭后 B 可取得 advisory 并 token+1；同投影批内不自阻塞、批间按冲突域顺序；每批只一个专用会话；无残留锁，断连旧 guard 不恢复 | 行 TTL 过期；连接存活/关闭 | 必须真实 PG，不得用 SQLite 代替 | 不需要 |

> LCK-09 说明：本冻结按用户决策采用 SQLite 租约 + PG advisory；R1.3 的“单写者/库级串行降级”不纳入 Batch B（D-B11 已裁决：不采用）。
>
> LCK-10 说明：必须两个真实 PostgreSQL 连接；若环境无 PG，该项标“未验证/阻塞”，不得以 SQLite 结果替代，也不得只测行条件 UPDATE。

## 5. GC：七态与 quarantine

| ID | 测试条件/输入 | 测试方法 | 预期结果 | 故障注入点 | SQLite/PG 差异 | Windows 真实环境 |
|---|---|---|---|---|---|---|
| GC-01 | enqueue pending + worker 认领 | 构造 `gc_task(pending)`；worker 跑一轮；查行 | pending→running；`lease_token` +1；`attempts` +1；`lease_owner/expires` 正确 | 无 | SQLite 条件 UPDATE；PG `SKIP LOCKED`/条件 UPDATE | 不需要 |
| GC-02 | 双 Worker 同 task | 两 worker 同时 claim 同一 task；另以同 key 的两个 task 竞争 | 仅一成功；另一 `None`；不同 task 不删除、覆盖对方槽；新一代正式路径另计隔离期 | 并发 | SQLite 单写者；PG 行锁 | 不需要 |
| GC-03 | 持锁复核引用>0 | 构造共享引用；运行 GC | status→`cancelled`；不删正式或唯一有效副本；自有冗余且正式验证通过才按等待期清理；释放锁 | 无 | 同左 | 需要：文件仍在 |
| GC-04 | 引用==0 | 独享引用删除后运行 GC | 持锁 rename 正式→`_quarantine/<key>.<task>`；记录 path/time；status 保持 `running`（租约过期，next_retry=+24h）；原路径不存在 | 无 | 同左；PG 真实文件同卷 | 需要：rename/占用 |
| GC-05 | 安全期后 purge | 将 quarantined_at/mtime 推到 24h 前；claim；复核 | 持锁复核仍 0 → 删 quarantine → `done`；原路径不重建；无残留 | 无 | 同左 | 需要：删除/占用 |
| GC-06 | purge 前引用回升 | quarantine 后新增同 key 引用；再跑 | 恢复 quarantine→正式（校验 hash）并 `cancelled`，或保持不删；**绝不删被引用文件** | 引用回升 | 同左 | 需要：rename 恢复 |
| GC-07 | quarantine 后崩溃 | 子进程在隔离后写记录前、purge 后写状态前分别 kill，并重发同 key；重启 ORP/GC | 有引用→恢复；无可靠隔离时间才重新计时；无引用且满 24h 只 purge 旧槽；新正式代次交后继；任务状态可解释；无残留误删 | kill | SQLite 任务过期；PG 连接释放 | 需要：真实崩溃 |
| GC-08 | 瞬时失败 attempts<8 | 注入一次 `PermissionError`/DB 错误 | `failed_retryable`；`next_retry_at≈now+60s`；到期回 pending/claim；不死循环 | 瞬时失败 | 同左 | 需要：占用错误 |
| GC-09 | 持续失败 attempts≥8/不可重试 | 连续注入失败 8 次；或跨卷/路径错误 | 第 8 次后 `failed_permanent`；不删；不自动重试；仅运维显式→`needs_manual` | 持续失败 | 同左 | 需要：占用/权限 |
| GC-10 | 旧 worker token 被接管 | 旧 worker 持 token；新 worker 接管；旧 worker 执行 update/删除 | 旧 worker verify/update 失败并中止；无文件被删；token 单调 | token 失配 | 同左 | 需要：物理步骤前 verify |
| GC-11 | needs_manual 人工恢复 | 构造歧义/quarantine 冲突；调用内部运维函数 | 仅显式操作可转 pending/cancelled；不自动删；审计日志 | 人工操作 | 同左 | 需要：文件保留 |
| GC-12 | 引用数派生 | 检查 schema；增删引用；COUNT | 无独立计数列；`COUNT(attachment WHERE storage_key)` 始终权威；无漂移 | 无 | 同左 | 不需要 |

> GC-04/05 的状态与 `acceptance-matrix §B.3` 对齐：quarantine 后任务仍为 `running`（租约过期，`next_retry_at=+24h`），不是 `pending`。
>
> GC 任务去重是尽力而为：`gc_task` 无唯一约束，并发最后引用删除/ORP 竞争可能产生同 key 重复任务。GC-01/02 验证“同一 task 不被双 worker 同时认领”和“重复任务不双删”，**不**断言并发下全局只有一条任务。
>
> GC-08/09 的退避按 `min(60*2**(n-1),21600)` 验证：8 次内为 60/120/240/480/960/1920/3840/7680s；`21600`（6h）是配置上限，8 次窗口内不会达到。公式第 8 项仅用于校核，失败终态不安排下次调度；隔离到期再认领消耗预算。

## 6. ORP：孤儿扫描与一致性

| ID | 测试条件/输入 | 测试方法 | 预期结果 | 故障注入点 | SQLite/PG 差异 | Windows 真实环境 |
|---|---|---|---|---|---|---|
| ORP-01 | DB 事务失败遗留物理孤儿（无 gc_task） | ATT-11 后把 mtime 推到 24h 前；运行 ORP | 扫描识别；入队 pending；GC 持锁复核 0→quarantine→等待→purge；不误删引用文件 | DB 失败 + 扫描 | 同左；PG 真实扫描 | 需要：真实 FS |
| ORP-02 | 上传临时文件 | 在 `.tmp` 放 `*.part`；运行 ORP | 不被计入正式 blob、不被回收/删除；报告 `temp_residual`；正式根不受影响 | 临时文件 | 同左 | 需要：文件存在 |
| ORP-03 | 安全等待期内文件 | 新孤儿 mtime<24h；运行 ORP | 不 purge；可报告；不改变文件 | 时间边界 | 同左 | 需要：mtime |
| ORP-04 | DB 有引用、原始缺失、quarantine 存在 | 删正式、保留 quarantine；运行 ORP/GC | 持锁恢复 quarantine→正式；校验 hash；告警；不删 DB 行 | 缺失+残留 | 同左 | 需要：rename 恢复 |
| ORP-05 | quarantine 残留（崩溃后） | 构造无任务/终态/活跃任务、损坏文件及交接两侧崩溃；运行 ORP | 识别；有引用恢复，无引用可信残留通过接收任务隔离并重新计时；未知命名只报告不删 | 残留 | 同左 | 需要：真实残留 |
| ORP-06 | ORP 与 GC 并发同 key | Barrier 同时运行；查文件/任务 | StorageKeyLock 串行；不双删/不误删；一者 cancelled/done，另一跳过 | 并发 | SQLite 租约；PG advisory | 需要：真实并发 |
| ORP-07 | DB↔物理一致性 | 构造：DB 有物理无、物理有 DB 无、hash 不符；运行 ORP | 报告三类齐全；不自动删 DB；不泄露路径/内容；JSON 可解析 | 三类构造 | 同左 | 需要：全量比对 |

> ORP-07 的三类对应 `missing_blobs`、`orphan_blobs`、`hash_mismatched`；报告只读，不自动“修复”。

## 7. 导入/R1 附件条目

| ID | 测试条件/输入 | 测试方法 | 预期结果 | 故障注入点 | SQLite/PG 差异 | Windows 真实环境 |
|---|---|---|---|---|---|---|
| IMP-19 | 导入含附件清单（ZIP-only） | ZIP 导入；查 staging、manifest、attachment、物理；另测多篇附件 ZIP、零文档、路径冲突、同/异集合重试、Active metadata-only、archived、JSON 两入口 | 附件内容寻址共享；引用行正确；report 使用既有 warnings 摘要；无重复物理；pending 期间零正式引用；JSON 单篇 400、批量逐篇 unsupported；多义 ZIP 整包拒绝；同来源同 Hash 同集合才复用 pending，异集合冲突；Active 附件-only 400 `ATTACHMENT_ONLY_IMPORT_UNSUPPORTED` 且零 staging/pending；archived 目标 400；单次 >100/100 MiB 413 | 缺文件/重复 key/仅附件/归档 | 同左；PG 真实事务 | 需要：真实 FS |
| R1-IMP-05 | Active 导入提交 pending | 提交含附件 manifest；查 review/item/origin/attachment | ImportOrigin 不写；item 不变；envelope 完整含 attachments+digest；attachment 行 0 | 无 | 同左 | 不需要 |
| R1-IMP-08 | Approve 导入 ReviewRequest | TestClient approve；查全字段；分别注入②同步/commit 失败 | title/content/status+tags+metadata+附件引用+source_*+ImportOrigin+links 同一业务事务①；文件发布在业务写前，②独立提交；②失败①不回滚，已批准响应和 staging 处置保持 | 无 | PG 全字段核对 | 需要：文件/索引 |
| R1-IMP-09 | Approve hook 写 tags 后故障 | 在 tags 后注入异常；查全表 | review 仍 pending；item/tags/log/attachments/origin/links 全部回滚；索引未更新；staging 保留 | 分步异常 | 同左；PG 注入 | 需要：文件保留 |
| R1-IMP-10 | Reject active 导入 | reject；坏 envelope 与不同来源键的 approve/reject 并发；查 DB/FS | 不写 origin、不改 item/links/tags/attachment 引用；提交后清 staging；正式 blob 不动；同 review 只能有一个有效终态，未知归属由 ORP 保守处理 | 无 | 同左 | 需要：清理 |
| R1-IMP-11 | Reject staging 清理失败 | 占用/拒绝删除 staging；reject | reject 状态仍正确；staging orphan 可被 ORP 标记；不误删正式 blob | 占用/权限 | 同左 | 需要：真实占用 |
| R1-IMP-14 | envelope digest/schema 不匹配 | 修改 payload/manifest 后 approve | 拒绝并 rollback；稳定错误码；不泄漏 payload；零写入 | 摘要/字段篡改 | 同左 | 不需要 |
| R1-IMP-37 | approve 预检后 envelope 改动 | S0 后改 DB payload；approve | 获锁 fresh session 检测；拒绝；review pending；零写入 | DB barrier | 同左 | 不需要 |
| R1.1-IMP-38 | approve hook 任一点故障 | 在附件/标签/origin/links 各点注入；另测 让目标归档在预发布后、Core 前完成，及已归档早拒 | Core approve+全部业务写整体 rollback；无半提交/悬空 origin；staging 保留；archived 情形返回 409 `ATTACHMENT_ITEM_ARCHIVED` 且零附件引用且状态仍 archived | 分步骤故障；归档状态 | 同左；PG 注入 | 需要：文件保留 |
| R1.1-IMP-41 | staging 仍被 PENDING 引用 | 构造 pending + staging；运行 sweep | 不清理；按 review/envelope manifest 校验；正式根不动 | 并发/引用 | 同左 | 需要：真实 FS |
| R1.1-IMP-42 | staging 无 pending 且超 grace | 构造孤儿/不完整 staging；分别设置 `.creating`/`.activity`/`.complete`/文件 mtime；并交错运行生产者、sweep 复核/移动、隔离恢复/purge；加空目录和 symlink/junction | 复核后 quarantine/purge；活动时间取标记+普通文件最大 mtime，**不**用根目录单一 mtime；pending 引用优先于 24h；**正式 attachments 根绝不被 sweep**；不误删 pending；路径重叠启动拒绝，越界/链接保留源 | 并发；标记缺失/时钟异常 | 同左 | 需要：真实 FS |

> IMP-19 的“report 含附件结果”不得通过修改 Core `ImportReport` 模型实现；使用 API §5.1 定义的既有 warnings 摘要与已有 errors/unsupported。若产品要求 Core 字段，另立裁决。
>
> R1-IMP-08 原文“成功后仅一 commit 边界”与真实代码/本冻结的两次 commit 冲突。**D-B08 已裁决**：事务①为业务提交边界（含附件引用），事务②为独立索引提交且失败不回滚①；验收按此口径判定。
>
> R1.1-IMP-41 原文按 `review_id` 校验；本冻结按 **D-B01 已裁决**使用 `staging_id`，验收同时校验 envelope 中的 `staging_id` 与目录一致，并校验 `.complete`。
>
> R1-IMP-10 追加：人为破坏 envelope 摘要/结构后，reject 仍必须成功；可信归属才立即清理，否则由 ORP 兜底，不得返回 409 把 pending 卡死。

## 8. 横切验收

### 8.1 并发

- 上传同 key × 2；上传/删除同 key；approve 多附件 × 2；GC 双 worker；ORP 与 GC；reject 与 approve。
- 断言：无死锁、无双重删除、无半提交、锁顺序稳定；超时为 10s 预算而非无限等待。
- **SQLite 专项**：approve 的 StorageKeyLock 必须在 S1/Core approve 之前取得，且 D23 PREPARED MATERIALIZE 恢复先提交/关闭；复制、Hash、发布位于业务写前，同业务 session 末次 fencing。用真实库与事件顺序区分 SQLite busy、真失配及异常 rollback 后释放。GC claim 必须先提交再取锁。

- **F13（沿用 ATT-08/11、R1-IMP-08/09/10）**：观测事务所有者对 commit/rollback 的调用。服务、Repository、Hook 无提交；业务①与索引②分别提交一次，按失败断点验证仅回滚本事务，无隐式或重复提交。

### 8.2 故障注入

- DB：commit 失败、连接断开、`gc_task` 更新 token 失配、事务回滚。
- FS：`os.link`/`os.rename` 失败、`PermissionError(winerror=32)`、跨卷、文件缺失、hash 篡改、磁盘只读。
- 进程：持锁 kill、quarantine 后 kill、staging 写入中 kill、approve ① 前后 kill。
- 断言：失败后无“DB 有行物理无”新增；孤儿可被 ORP 发现；pending 不丢 staging；不静默覆盖。

### 8.3 安全

- 路径穿越/绝对路径/UNC/ADS/保留名；文件名不进路径；下载头清洗。
- MIME 伪装/SVG/超大/空文件/非法 Base64；未知类型拒绝；二进制 magic 与文本 UTF-8 分开验证，不宣称文本子类型可区分。
- archived item 上传被拒绝；下载/列表/删除引用仍可用。
- 下载校验与流式输出使用同一句柄；不得按路径重新打开。
- 日志/报告/响应不含密钥、绝对路径、文件内容、用户文件名（报告可脱敏）。
- 无鉴权边界：仅本机；不得宣称公网安全。

### 8.4 回归

- 根级 pytest 全量；Batch A 导入/导出/审核测试不回归。
- `uv run ruff check`；前端 `npm run test && npm run typecheck && npm run build`（若前端未改，仍跑基线）。
- PostgreSQL 迁移 up/down（`0006` 已存在；Batch B 无新迁移，确认不破坏）。
- 不得删除/弱化既有测试；不得用排除目录掩盖收集冲突。

### 8.5 R1.3 继承映射

- R1-IMP-07 → IMP-19 / R1-IMP-05。不同文档 Hash 或不同附件集合均保持原 pending、manifest、staging，无第二张审核单、无 item 写入。
- R1-LOCK-07 → ATT-10 / ORP-06。屏障卡在发布后、业务 commit 前，运行 GC/ORP，验证持锁复查与引用一致性。
- R1-LOCK-08 → LCK-10。真实 PG 连接覆盖同 key、不同 key 与相同 advisory 投影；碰撞只增加串行等待。
- B1 路径核验并入 ATT-01/06、ORP-02、R1.1-IMP-42。覆盖别名、实际根交叠、重解析点、平台真实跨卷与保留源。
- D22/D23 用既有 Batch A 回归加 SQLite 恢复时序；D24 仍归 Batch D。没有新增 Batch B 验收编号。

## 9. 退出条件

Batch B 可提交独立审计的最低条件：

1. ATT-01…13（13 项）、LCK-01…10（10 项）、GC-01…12（12 项）、ORP-01…07（7 项）全部有真实证据；PG/Windows 项不得以“同左”代替真实运行；O-B11 已裁决，按 8 次实际退避序列验证，不得写“6h 已到达”。**合计 53 个验收编号**（含 IMP-19、R1 7 项、R1.1 3 项）。
2. IMP-19 与 R1-IMP-05/08/09/10/11/14/37、R1.1-IMP-38/41/42 全部有证据；O-B01/D-B01/O-B08/O-B09/O-B10/D-B08/D-B13 已裁决，不得再把相关项标“阻塞”；若最终签发改变裁决，先改设计。
3. 无新增迁移/依赖；Core/端口/A1-02/A1-03 未改；未改 Core `ImportReport`。
4. 所有失败路径可解释；孤儿/不一致有报告；无“物理+DB 原子”虚假声明。
5. 验收报告区分“已验证/有条件/未通过”；未验证项单列；PG/Windows 未跑时明确标未验证。
6. 不自动进入 Batch C/BAK；等待独立审计。

## 10. 不得声称

- 不得声称“附件上传与 DB 原子”。
- 不得声称“GC 已完全消除 TOCTOU”。
- 不得声称“PG 已验证”而无真实实例输出。
- 不得声称“Windows 已验证”而只在 Linux 跑。
- 不得声称文本字节可可靠区分 TXT/Markdown/CSV。
- 不得声称 PG 行 TTL 过期可绕过仍存活的 Advisory Lock。
- 不得声称下载已完全消除外部原地改写风险（同一句柄只消除路径重开）。
- 不得把本计划中的预期结果写成已通过。
