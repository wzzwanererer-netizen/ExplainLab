# B1–B6 可实施性检查

**路线依赖整体成立，B1 的锁与路径契约需先闭合。** 下表区分可沿用的实现骨架和当前必须由候选文档给出答案的接口。各任务仍按原顺序与范围执行。

| 阶段 | 当前代码与可沿用的骨架 | 进入开发前需明确的事项 |
|---|---|---|
| B1 基础 | `0006_v2_markdown_kb.py:114–127,150–167,190–201` 与 `models.py:336–351,379–407,438–451` 具备所需列、FK、索引。Core ports 既有签名可以沿用。 `file_write.write_all` 可用于完整临时写。按方言实现锁与短事务。 | F06/F07/F08 直接影响锁管理器 API、会话、根校验。按 F05 固定 GC 认领、更新、恢复用字段与状态前置。锁等待 10s 是整批预算，DB busy/连接建立/语句等待须消耗剩余预算。不要把全局 SQLite busy_timeout 或 SQLAlchemy 逻辑事务标志当作实际保证。 |
| B2 附件 API | 路由与 DTO 可新增于 backend。现有 Attachment FK 和 item 路径足以支持归属、稳定元数据列表、按 key 派生引用。发布先于提交、下载同句柄和删除仅写 DB 的分工可沿用。 | F01 给出与 archive 竞争的写前置。F09 澄清错误与响应。F12 明确句柄关闭、Windows retry。删除与入队由同一事务协调，入口删除操作应按实际删行结果决定后续。 |
| B3 ZIP 与 staging | `import_export.py:70–152` 是入口，`MarkdownService._preflight`、`_import_one` 能保留逐篇事务和 D22/D23。既有 envelope 摘要已覆盖 `attachments`，无需改 Core。 | F02/F03 先明确 ZIP 归属、同 hash 重试、活动/生命周期协调。staging 建立应在确定有合法去向后，区分新 pending、复用 existing pending、Draft 成功和各种无业务结果的清理。Draft 应同步核对 F01/F07。既有批量行为依 F09 处理。 |
| B4 Active 审核 | `governance.py:385–485` 的 S0→身份门→S1→Core→Hook→①→索引②可保留 DB 顺序。Core 审核不 commit，原 Hook 不碰 staging；可在 backend 消化变化。 | F01/F04/F07 是本阶段的前置设计。按 F03 严格区分可信 staging 绑定与损坏 payload；交代 F10 的 HTTP 语义和清理责任。D23 恢复完全结束后取附件锁，锁持到业务提交，处理异常时先回滚。 |
| B5 GC/ORP | GC 状态、租约、时间、相对隔离路径均有可复用字段。claim 独立短事务 → 锁 → 持锁复核 → 文件动作 → 状态落库的方向合理。现有 ProcessLock 可守住单实例部署。 | F03/F05/F06/F08/F11。worker 启停放在 lifespan，停止并收尾后才能释放 DB/OS 锁。入队尽力去重，在重复任务与异步恢复时按物理代次判定。GC/ORP 共享引用复核与 no-clobber 规则。 |
| B6 验收 | 现有 53 编号提供完整的执行骨架。测试应沿用真库、真文件系统、短时钟推进及故障注入办法。 | 按 [验收覆盖缺口](acceptance-gaps.md) 把关键屏障时序、R1.3 继承项和平台命令挂回已有编号。Windows/POSIX/真实 PG 缺证据时按对应环境标为未验证。 |

## 冻结边界对照

| 边界 | 静态结论 |
|---|---|
| D22 exporter 与 Hash 解耦 | `markdown.py:391–503` 在 backend 对名称、reserved key 和传输字段做预处理，之后计算文档 hash。 `import_report.py:243–275` 的 envelope 完整性覆盖附件列表，属于另一投影。Batch B 应在 backend 单独作附件集合等价判断，保留原有四类 Hash、exporter 剥离和保留键冲突零导入写入。 |
| D23 身份 Journal | `source_identity.py:595–610,681–695,739–785` 显示 RLock 与恢复先后。合法 COMMITTED MATERIALIZE 仍是本地物化依据。采纳 F07 不需要改 Journal v1、归档、摘要、身份投影或恢复门。approve 在物理发布前保留 target/来源/材料化冲突验证，避免向已物化条目追加 origin。 |
| D24 本机 HTTP | R1.3 §22.3 将精确绑定及 Host/Origin/JSON 防护与网络验收归 Batch D。现有 `main.py:113–119` 是 CORS 配置，单靠它不能证明 D24。Batch B 维持 JSON transport、同一本机部署和稳定错误边界，不扩展外网暴露。D24 的实现验收保持原批次，未据此新增冻结阻塞项。 |
| Single / Strict | SQLite 与 PostgreSQL 可以使用同一既有 schema 和 Core 端口。PG 多会话/双 worker 实验与单 Backend 部署相容。候选里 PG 多实例表述须按 F06 订正。 |
| 文件系统与提交 | 可证明的是当前源码的 DB 顺序。正式文件发布、崩溃持久性、no-clobber、占用和 purge 仍要在相应平台取证。方案允许发布成功而 DB 未提交的孤儿，隔离/恢复应保全已有引用。 |
