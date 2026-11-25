# 架构缺陷与风险

文档节号以候选为准。代码位置均以 Batch A 基线为准。下列时序为静态反例。

## F01 · P1 · 阻塞 · 归档检查在正确的事务位置缺失

- **位置**：`attachment-lifecycle.md` §2.1–2.3、§6，`active-review-integration.md` §4、§5.1，`risk-register.md` B-R42。代码 `backend/app/services/markdown.py:880–888,974–982`，`backend/app/api/routes/governance.py:433–470`，`knowledge-core/src/knowledge_core/review/__init__.py:85–96,129–143,145 起`。
- **事实与影响**：Active 导入的 Core payload 带 `status=draft`。目标先被既有治理路径归档，随后 approve 执行时 Core 先把状态改为 Draft。Hook 才查状态会漏掉原 archived 状态，导致审核提交、条目被改回 Draft、附件被新增。独立上传仅在取 key 锁前查归档，锁保护 blob 而不覆盖条目状态变更。普通二次 SELECT 也会在读与写之间留下窗口，Draft 更新有同类风险。
- **最小修正**：带附件的 approve 在 S1、Core 改写状态前，以与归档更新冲突的事务内保护重新读取条目。上传和既有 Draft 导入共用相同的保护点。PG 用锁住目标行的读取，SQLite 在适配层用本事务的条件写/等价受保护写前置并检查影响行数，沿用现有事务管线。定义归档先完成时返回对应入口的稳定错误，附件写先完成时后续归档可保留既有引用。S0 仅作早拒，锁次序与 Core 不变。

## F02 · P1 · 阻塞 · ZIP 附件未确定归属，既有幂等分流会吞掉请求

- **位置**：`api-contracts.md` §1、§5，`attachment-lifecycle.md` §3，`active-review-integration.md` §3、§9，`implementation-roadmap.md` B3-T01/T02。代码 `backend/app/api/routes/import_export.py:70–152,207–246`，`backend/app/services/markdown.py:261–324,548–562,630–735,822–941,984–1007`，`knowledge-core/src/knowledge_core/markdown/import_report.py:158–165`。
- **事实与影响**：现有两入口可从一个 ZIP 读多篇 Markdown，ZIP 路径被折成 basename，archive 分支不给文档传顶层 target。候选只定义 `attachments/` 与每附件字段，既有 export manifest 也不提供附件到文档的关联。在混合 Draft/Active ZIP 中，无法确定何处写引用及 pending 所有权，复制全包到每篇会串挂并使一篇清理另一篇 staging。全次按 key 拒重与按 `(item_id,key)` 拒重亦不一致。Batch A 的已应用 payload 和同 hash pending 早返回发生在实际变化分类前。只看文档 hash 的 Active 重试可能将不同附件集合静默 SKIPPED 或 REUSED_PENDING。tags/metadata-only 不触发 Core 内容审核，规范也缺少它们与附件同包时的落点。无 Markdown 的 ZIP 会先命中既有 `IMPORT_EMPTY`。
- **最小修正**：明确有附件 ZIP 的可接受文档数、绑定方式、跨篇去重粒度和 staging 所有权。最小可落地裁决是仅接受附件归属唯一的包，并给无归属/多义包稳定失败；若既有裁决要求多篇附件包，则必须显式、无歧义地逐文档绑定。规定全包限制先验、逐篇事务及清理；定义相同文档+相同附件集合可复用、不同集合不得静默复用或替换 pending；为已应用重试、同 hash 不同附件、Active metadata-only 加附件和零文档 ZIP 定义结果。维持 D22 文档 Hash 投影与 Core 变化分类器，附件比较放在 backend。ZIP 入口须先按完整路径识别条目再解压，限制实际累计输出，先保留 D22 reserved key 与 manifest 冲突校验再落业务数据。

## F03 · P1 · 阻塞 · staging 生产者与清扫者没有同一保护区间

- **位置**：`attachment-lifecycle.md` §3.2–3.4、§7，`active-review-integration.md` §4、§5.4、§7，`gc-and-orphan-recovery.md` §6.4。代码 `backend/app/services/markdown.py:630–740,880–913`，`backend/app/api/routes/governance.py:489–526`。
- **事实与影响**：ORP 的第二次 pending 查询在短会话中结束，随后才移动目录。Active 导入在 staging 完整后才提交 pending，候选未规定提交者与 ORP 持同一把 guard。导入停顿超过 24h 后恢复、或者 ORP 先根据旧活动快照挑选目录，均可能造成复核结束后 pending 才提交。此时目录已被隔离，approve 只能报错。第二阶段 purge/restore 还需明确同样的保护与复核，按文件 hash 加锁对空目录/创建中目录无效。解析失败后的 reject 不应从未验证 payload 取目录身份直接删除。ORP 若把无导入 envelope 的普通 review 当损坏，会持续停扫。
- **最小修正**：给 staging 写入至 pending/Draft 提交、隔离、恢复、purge 和正常清理定义共同的目录生命周期协调点，复用既有受控单实例边界，固定在全局锁序中的位置。移动/清除前在保护区内重新核对活动和 pending 归属。正常 review 无 envelope 按无 staging 跳过，疑似导入但损坏 fail-closed。reject 对不能验证所有权的目录跳过即时清理，交 ORP。空目录或标记前崩溃目录须有保守且可终结的处理。

## F04 · P1 · 阻塞 · reject 逃生通道缺同一审核单的决议串行

- **位置**：`active-review-integration.md` §2、§7–8，`implementation-roadmap.md` B4-T01，`architecture.md` §4.3。代码 `backend/app/api/routes/governance.py:306–312,370–405,426–470,489–526`，`backend/app/services/governance.py:201–209`，`knowledge-core/src/knowledge_core/review/__init__.py:85–113`。
- **事实与影响**：当前 reject 走严格预检，损坏 envelope 阻塞退出，候选提出轻量回退是必要的。候选同时假定两个决议必拿同一个身份键，但从损坏快照回退到 target 键后，另一个请求可能从修正后的快照走 identity 键。现有 review UPDATE 只按 ID，S1 的读不锁行也不做 PENDING 条件更新。失去同锁保证时，两个请求可先后提交曾基于 PENDING 的结果，最终审核状态与已生效附件/内容不一致。
- **最小修正**：approve/reject 增加共同的 reviewer 决议互斥键 `review_id` 或等价的 S1 DB 条件决议保护，规定相对于 identity/storage 锁的顺序。保留导入 identity key 的职责，并允许损坏 payload 下 reject 先提交。测试在轻量预检与 S1 之间切换 payload 或用屏障模拟双分支，只允许一条终态。

## F05 · P1 · 阻塞 · GC/ORP 对重复任务与崩溃后的物理代次缺闭合规则

- **位置**：`gc-and-orphan-recovery.md` §2–6、§9，`storage-and-lock-contract.md` §3.1、§3.3，`attachment-lifecycle.md` §5。代码 `backend/app/models.py:379–407`，`backend/alembic/versions/0006_v2_markdown_kb.py:150–167`，`knowledge-core/src/knowledge_core/ports.py:356–398`。
- **事实与影响**：任务 A 隔离正式文件后、记录 path/time 前崩溃，确定性文件名可找回文件，但没有可靠隔离起点。移动保留原文件 mtime，旧 mtime 不能充当隔离时间。若同 key 被再次上传后又删引用，任务接管时可能同时遇到正式文件和自己的隔离副本。§5.2 没定义该组合的后续状态，§6.3 也没定义有终态任务的残留，以及 task B 遇到 task A 的隔离副本时谁负责恢复。发布后损坏产生 `<key>.<uuid>`，无任务 ORP 路径可以直接恢复/删除，但未继承 §5 的 hash/no-clobber/持锁重查条件。只按过期 token 重读或在锁外先数引用会让过时判断参与不可逆操作。
- **最小修正**：补一张正式/当前任务隔离/其它任务隔离/引用数的处理表，区分当前正式文件与旧隔离副本的回收责任。路径存在但缺可靠隔离时间时，持锁采纳并从当前时间重新等 24h。ORP 与 GC 使用同一物理与 fencing 前置，锁内重读引用及任务状态，校验 hash 后恢复或 purge。明确终态残留、无任务损坏文件和双副本走恢复、报告人工或安排后续处理的条件。不得覆盖正式 blob 或仅凭 mtime 提前 purge。

## F06 · P1 · 阻塞 · PG 多 key 锁的会话、真实锁身份和部署边界不闭合

- **位置**：`storage-and-lock-contract.md` §4.3–4.6，`architecture.md` §6，`gc-and-orphan-recovery.md` §6.1，`implementation-roadmap.md` B1-T03。代码 `backend/app/main.py:65–106`，`backend/app/db/session.py:19–56`，`knowledge-core/src/knowledge_core/ports.py:437–464`。冻结依据 R1.3 §22.2、§22.6 和 R1-LOCK-08。
- **事实与影响**：现方案按每个完整 key 建专用会话，但 advisory 身份只取前 64 位。两个不同 key 投影相同、出现在同一批，后一个连接会被同批前一个连接挡住，结果是批内自竞争超时。投影碰撞若跨批，完整 key 顺序也未必等于物理冲突域顺序。允许 100 个 key 的请求会为一个 guard 打开最多 100 个会话，还需业务/维护会话，路线未定义可承受的预算；“每键一个守护线程”同时引入放大。另有几段写 PG 应用多实例，与 ProcessLock、单 Backend/单本地数据根冻结口径冲突，共库不同根甚至会按彼此的数据库引用情况处理不同目录。
- **最小修正**：将 PG advisory 连接归属于整批 guard，按实际 advisory 身份去重、固定顺序获取，完整 key 仍分别写/验 fencing 行。定义在同一专用连接串行化 heartbeat/verify/release，禁止自动重连后沿用旧 guard；所有退出都 unlock 或物理关闭，另为 ORP leader 规定固定连接与独立锁名空间。给 100 keys 验证连接预算。固化单 Backend/单根/单 worker；多连接、双 worker 验收是并发取证，不等于批准多实例部署。

## F07 · P1 · 阻塞 · SQLite 写事务内物理 promote 与 R1.3 边界冲突

- **位置**：`architecture.md` §4.2/4.4，`active-review-integration.md` §2、§5，`attachment-lifecycle.md` §4，`storage-and-lock-contract.md` §4.6；R1.3 implementation-plan §7.4。代码 `backend/app/services/source_identity.py:595–610,681–695,739–785`，`backend/app/services/governance.py:201–209`，`backend/app/api/routes/governance.py:461–476`，`backend/app/db/session.py:19–56`。
- **事实与影响**：D-B15 明确修正的是先拿锁，未单列批准将 SQLite 文件复制、fsync/hash 和发布放进写事务。R1.3 §7.4 明定物理操作在 DB 写事务外，候选仍让 Hook 在 Core 已 flush 后处理最多 100 MiB。此时独立 SQLite 心跳写与主写事务竞争，60s 到期会使慢盘/占用路径重复失败，且期间阻塞其他写入。候选称 `identity_guard` 只读也与代码不符，guard 入口可恢复 PREPARED MATERIALIZE，内部提交并退出会话后才 yield。 `has_committed_materialize` 也会调用恢复入口，不能无条件当普通只读。
- **最小修正**：把 O-B10 表述为「取附件锁时，D23 恢复已完成，相关 SQLite 写事务均已提交/关闭」，保留同一 Journal RLock，不挪走恢复门。Draft/approve 在锁下、业务写前进行可完成的物理校验、复制和发布，S1 写路径只做 DB 保护性重读、Core → Hook → ①；预发布失败由原有 ORP 收敛。若保留写事务内发布，须由裁决明确覆盖 §7.4，并给出允许的物理临界区和不会让心跳自等的事务内 fencing 方案。用同一业务 session 做最终验证，异常路径先 rollback 再释放。

## F08 · P1 · 阻塞 · 配置未隔离 staging、正式根、quarantine 和身份数据

- **位置**：`architecture.md` §5，`storage-and-lock-contract.md` §1、§5–6，`gc-and-orphan-recovery.md` §6.2–6.4，`implementation-roadmap.md` B1-T01/T02。代码 `backend/app/main.py:69–88`，`backend/app/services/source_identity.py:574–585`（共享 data_dir）。
- **事实与影响**：当前启动条件只要求同卷、根内/权限与 quarantine 位于正式根内。允许 staging 等于正式根或等于 quarantine。后续 staging sweep 枚举任意子目录，可能将正式 shard/临时目录误作待清目录。配置校验 `st_dev` 根相同也不覆盖运行期子目录变为不同挂载点，路径字符串相等不能替代拒绝符号链接、junction/重解析点和非普通文件。默认目录布局本身合理。
- **最小修正**：解析并比较实际根，禁止别名、交叠及指向 Journal/DB/操作目录，唯一允许的嵌套是规划中正式根的 `.tmp`、quarantine 和其 staging 子树。清扫严格限制为服务端生成的有效目录身份、可核验路径和预期文件类型，遇链接/junction/越界仅报告。发布、隔离、清扫在运行期发现跨卷即失败，保留源。B1 用现有文件系统机制即可，无需新依赖。

## F09 · P2 · 非阻塞 · HTTP/DTO 和既有批量兼容需要一张权威表

- **位置**：`api-contracts.md` §2.3、§3–7、§9，`attachment-lifecycle.md` §2.4，`active-review-integration.md` §3–6，`acceptance-plan.md` ATT-05/12、IMP-19。代码 `backend/app/api/routes/import_export.py:43–50,120–152,180–204,228–246`，`backend/app/services/markdown.py:251–288`，`backend/tests/test_markdown_batch_a_import_export.py:587–623`。
- **事实与影响**：批量 JSON 附件目前逐篇 unsupported 且其余篇继续。候选把统一 400 称为沿用 Batch A，与既有测试冲突。目录缺失、envelope 摘要不符、摘要有效但附件元素非法三类错误边界交叠。导入解析在映射 try 外；下载一般 I/O/权限/占用、校验前后是否成功隔离、删除 DB/维护不可用的精确码没有全部落到路由表。DTO 的 422 校验应避免将原始请求 input（含 Base64/文件名）回显。ATT-05 同时承诺按 SVG 后缀或内容拒绝，API §4 又允许 UTF-8 文本声明承载 SVG 字符串，当前预期无法统一。
- **最小修正**：单篇保留 400，批量保留逐篇 unsupported，除非另有明确裁决。列出路由×失败点的状态/稳定码/报告字段，覆盖解析异常、403/权限类 I/O 映射至规定的 503、500、几类 manifest/staging 错误及脱敏 422。对齐 SVG 的真实拒绝范围和测试，用既有 Core ImportReport 或选定的 backend 附加字段，不改变 Core 模型。

## F10 · P2 · 非阻塞 · approve 索引②失败的 HTTP 语义与基线不一致

- **位置**：`architecture.md` §4.2，`active-review-integration.md` §2、§5.4–6，`implementation-roadmap.md` B4，`acceptance-plan.md` R1-IMP-08。代码 `backend/app/api/routes/governance.py:470–485`，`backend/app/services/retrieval.py:272–299`，`backend/app/api/routes/import_export.py:155–168`。
- **事实与影响**：① 提交和②失败不撤销①已由代码证明。approve 当前一般异常会 rollback 当前事务并重新抛出，可能已经提交业务却返回失败。候选同时写“只记录告警”和“不得改代码行为”。而且 FTS 触发器可能已经随①更新，②是提交后索引同步，不能认为全部索引只发生在②。
- **最小修正**：明确②失败时 HTTP 行为。若以“只告警”为权威，参照导入索引同步路径单独捕获②失败、只回滚②、按已保存的 ReviewOut 返回并清理 staging；如果沿用已有 HTTP 失败，则文档明确可重新查询已 approve 的状态。验收分别注入同步和② commit 失败。

## F11 · P2 · 非阻塞 · GC 时间定义和第 8 次失败口径冲突

- **位置**：候选 README §3、§6，`attachment-lifecycle.md` §1、§8.2，`gc-and-orphan-recovery.md` §2、§4.3、§5.2、§6.2，`acceptance-plan.md` GC-04/08/09。代码 `backend/app/models.py:392–407`。冻结依据 R1.3 §7.3/7.5。
- **事实与影响**：生命周期示意图写删除后先等 24h 才隔离，GC 伪代码却立即 claim/隔离。ORP 以 blob mtime 满 24h 入队，部分说明则像要求从“无引用开始”计时，旧 blob 刚失去引用也可能马上被 ORP 识别。第 8 次失败进入终态，所以 7680s 是公式值；在无其它成功认领消耗次数的情况下，最后实际调度的失败退避为第 7 次的 3840s。隔离后的正常接管也消耗一次 claim，不能把所有认领当作连续失败数。
- **最小修正**：明确引用删除事件、无任务 ORP 扫描和物理隔离三个计时起点。R1.3 支持正式 blob 在必要条件满足时先隔离，再等至少 24h purge。若要另加删除后等待，写明由现有时间字段承载及恢复规则。保留 O-B11 的公式与终态，说明第 8 次无自动下次调度。补齐最大认领次数对过期 running 接管/正常隔离接管的判定。

## F12 · P2 · 非阻塞 · Windows/POSIX 的发布失败与句柄归属需确定

- **位置**：`storage-and-lock-contract.md` §3、§5–6，`api-contracts.md` §3，`implementation-roadmap.md` B1-T02/B2-T02，`acceptance-plan.md` ATT-09/12。可复用基线 `backend/app/services/file_write.py`；Batch B 尚无下载与发布实现。
- **事实与影响**：hard link 优先与 no-clobber 降级合理。把所有 `OSError` 当作 hard link 不支持，会将卷、权限和 Windows 占用错分并尝试错误降级。新 shard 首次创建时只 fsync 最末父目录，不能据此认定全部新增目录条目已持久化。下载同句柄设计正确，但校验异常/取消/断开后的关闭责任未写。Windows 可能因共享模式令真实替换失败，不能用替换必须成功作为同句柄的证明。
- **最小修正**：仅对已识别的“不支持”错误降级，分流目标已存在、跨卷、占用和权限；重试每个不可逆步骤前复核 guard。规定 POSIX 新建层级与正式路径的目录同步策略及 Windows 持久化上限。下载由响应流拥有句柄，正常/错误/取消都关闭，用真实占用和 POSIX 路径替换分别取证。

## F13 · P3 · 非阻塞 · 落点与依赖声明有文档漂移

- **位置**：`architecture.md` §2、§6，`implementation-roadmap.md` §2、B2-T02、B3-T01、§9–10，`risk-register.md` §6。代码 `backend/app/services/markdown.py:237–259,407–503,984–1007`，`backend/app/services/repositories_v2.py:36,107,158`，`backend/app/services/import_coordinator.py`。
- **事实与影响**：候选同时说 attachment service 不 commit 又按上传 service commit 列时序；把 MarkdownImportDocument 加字段但未说明如何穿过 PreparedDocument；B2 持有 DTO/验证/GC 入队逻辑，B3 与 B2 宣称可并行；配置表写默认值但部分值经裁决为固定约束；ImportCoordinator 被误写成 A1-03。单篇真实代码对普通 metadata、身份、报告已有路径。
- **最小修正**：在现有任务中指定事务持有者、B1/B2 公用校验及入队接口的交付次序、两层 backend 文档对象的字段传递与固定参数约束。统一引用与文档路径，无需新增阶段。
