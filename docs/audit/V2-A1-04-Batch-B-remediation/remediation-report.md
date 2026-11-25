# Batch B 八项 P1 整改报告

本轮针对 [独立审计发现](../V2-A1-04-Batch-B-final-review/architecture-findings.md) F01–F08 落实设计改动。Batch A 基线为 `970c0d8ec05f0b8c68286839a56b14c74ea230c6`。表中结论是设计时序及预期行为，运行证据待 B1–B6 实现后取得。

| 审计项 | 章节 | 修正前 | 修正后 | 状态转换与失败处理 | 既有验收 |
|---|---|---|---|---|---|
| F06 · PostgreSQL advisory 锁 | storage §4.3–4.6，architecture §6，路线 B1-T03 | 每完整 key 一个连接，碰撞导致批内互等 | 每 guard 一个物理会话。按实际 int32 二元组去重、排序，完整 key 各自签发 token。最终提交区间用业务事务锁 token 行，专用会话仍检查 advisory。 | 连接建立 → 获取唯一锁 → token 短事务 → guard 有效 → unlock/关闭。部分失败撤销；断连旧 guard 不复活；新 owner 要完成 token 提交才能动文件。 | LCK-02/03/06/10，继承 R1-LOCK-08 |
| F07 · SQLite 文件与业务事务 | architecture §4.2/4.4，review §2/5，storage §4.6 | Core flush 后的 Hook 持业务写事务复制、校验、发布 | D23 恢复先结束并关闭内部事务。文件预发布在业务写前，S1 保持 Core→DB Hook→①；索引②独立。 | 恢复→取锁→预发布→S1→fencing→①。预发布失败无业务写，①失败 rollback 后释放且保留原件，已发布未引用交 ORP。 | LCK-04/05/07/08，R1-IMP-08/09，横切 §8.1 |
| F08 · 目录隔离 | storage §1/6–7，architecture §5，GC §6.2–6.4，路线 B1-T01 | 同卷不足以排除根重叠、路径别名和链接 | 规定真实路径、目录身份及祖先关系；保护 DB/Journal/ops；专用子树，清扫仅认规范 UUID/分片和普通文件。 | 部署启动验证→操作前复核；根重叠拒绝启动，运行期链接/越界/跨卷保留源并报告。 | ATT-01/06/12，ORP-02，R1.1-IMP-42 |
| F01 · 归档竞争 | architecture §4.4，lifecycle §2.3/6，review §2/5–6，API §2.1/5.3 | 早读或 Core 改成 Draft 后检查可漏掉归档 | PG 锁住 item 行，SQLite 先执行条件防护更新并检查匹配。approve 在 Core 写之前；上传/Draft 使用同一写前置。 | 归档先提交：拒绝并保留 archived、零新引用。新增先提交：后续归档保留引用。预发布留下的孤儿由 ORP 回收。 | ATT-13，IMP-19，R1.1-IMP-38 |
| F02 · ZIP 归属和幂等 | lifecycle §3.1–3.2，API §5，review §3–4，路线 B3 | 整包附件未绑定文档，按文档 hash 的早返回会吞掉附件 | 含附件 ZIP 限唯一非附件目录 Markdown。沿用来源身份规则；逻辑集合与 staging 路径分开比较。Batch A 单篇 JSON 400/批量逐篇结果保持。 | 合法请求→已满足 SKIPPED / 相等 REUSED_PENDING / 新 pending 或 Draft。归属歧义、集合冲突、缺文件和 Active 附件-only 各有稳定失败，原 pending 保全。 | IMP-19，R1-IMP-05/14/37，继承 R1-IMP-07 |
| F03 · staging 写入与清扫 | lifecycle §3.2–3.4/7，GC §6.4，architecture §6 | 二次查 pending 到移动之间，创建者仍可提交 | 进程内 staging_id guard 覆盖创建、提交与正常处置，清扫/恢复/purge 共用。持锁重算活动、读取 pending。 | 创建→完成→pending 或正常清理；孤儿→隔离→等待→清除；看到 pending 恢复或保留，损坏归属 fail-closed。 | R1.1-IMP-41/42，R1-IMP-10/11，ORP-05 |
| F04 · 审核决议竞争 | architecture §6，review §2/7–8，路线 B4 | 损坏 envelope 回退 target 锁，approve 可能持不同 identity 锁 | 单实例内以同 review_id 串行 S1 与提交，保留来源协调；reject 可在损坏 envelope 下提交，可信归属才清理。 | PENDING→APPROVED 或 REJECTED，仅一个终态；后到者既有 409，失败回滚维持 pending，不提前清理。 | R1-IMP-08/10/11/14/37，横切 §8.1 |
| F05 · GC 重复任务与物理代次 | GC §3–6，storage §7，路线 B5 | 重复 task 槽互不认识，移动/删除与 DB 写间崩溃缺处理 | 每任务确定性隔离槽、持锁新查引用/租约、按隔离和正式代次决策。无/终态任务残留经合规交接。 | 隔离后缺记录重新等待 24h；旧槽 purge 后崩溃可完成并交接新正式代次。引用回升校验并恢复；坏 Hash、无安全证据保留现场。 | GC-02–10，ORP-04/05/06，继承 R1-LOCK-07 |

## 与 Batch A 源码的衔接

- `governance.py:385–485` 与 Core review `__init__.py:85–96,129–143` 证明现有 S0 会话关闭、Core 先修改状态及业务/索引两次提交。附件路径保留 DB 顺序，提前保护归档，将物理发布移到①的业务写之前。
- `source_identity.py:595–610,681–695,739–785` 证明 guard 进入可恢复并写库。锁置于恢复完成和内部会话关闭后，Journal 保持原样。
- `import_export.py:70–152,207–246`、`markdown.py:251–288,630–735,880–888,984–1007` 证明入口、逐篇行为和文档 Hash 早返回。归属与附件集合校验在 backend，未修改 Core classifier/Hash。
- `models.py:336–351,379–407,438–451`、`0006_v2_markdown_kb.py` 和 Core ports 提供引用、任务、锁及 fencing 字段。新时序沿用现有 schema 和端口。
- `main.py:65–106` 的 OS ProcessLock 约束不放宽，PG 双连接与双 worker 测试只作并发取证。

## 本次明确的设计选择

含附件 ZIP 限单篇 Markdown。多篇附件分配需额外传输契约，本批对歧义返回既有错误；无附件 ZIP 延续批量能力。带附件的审核在①成功后返回已批准结果，清理或②失败只告警；原无附件路径沿用 Batch A。GC 缺可信隔离时间时重算 24h；第 8 次失败是终态，7680s 为公式值。
