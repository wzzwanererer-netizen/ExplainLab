# 原整改十项逐项审计

原编号来自提交整改映射。冻结依据的 §号分别对应 storage-and-lock-contract、gc-and-orphan-recovery、architecture 与 implementation-roadmap。

| 原整改项 | 代码、契约及证据 | 复审 |
| --- | --- | --- |
| P1-01 GC 租约与状态机 | `repositories_v2.py:418–601`。GC §3–4。认领、写回、调度和人工各走条件 UPDATE。worker WHERE 同时校验 running、owner、token、DB 时间和 expiry。调度只重新排到期可重试任务。人工仅四条允许边，未接公开管理 API。SQLite 逾期写回和续租、并发写回、到期调度、人工分支及竞争写锁用例复跑。 | SQLite 已覆盖的过期 owner 写回被拒绝。PG 需要专项验证锁等待跨过 expiry 且前置事务不改变行版本时的行为。人工调用者身份与操作审计尚未接入，按 GC-11 进入 B5。仅凭当前内部方法无 actor 参数，不能认定对外绕过。 |
| P1-02 文件 fencing | `attachment_storage.py:583–604,644–652,667–714,773–846`。storage §3、§4.5–4.6。覆盖 key 与真 guard，正式路径修改前再 verify，Windows retry 重验，隔离 link 后与 unlink 前再次校验。复核缺失、错误 key、释放、过期和 token 失配用例。 | 已观察失效会拒绝文件写。SQLite 核验等待见 IR2-02。最终校验后到 syscall 的窗口仍存在，见残余风险。 |
| P1-03 路径边界 | `config.py:147–208`，`main.py:79–87`，`attachment_storage.py:194–252,303–418,762–769`。storage §1。逐组件保留词法路径，再检查规范路径、目录身份、卷、非普通文件及 Windows 重解析属性。 | 实测发现预留 DB 文件祖先遗漏，IR2-06。交付日志提供真实 junction 证据，本环境复跑的 mklink /J 被跳过。 |
| P1-04 临时所有权 | `attachment_storage.py:441–510,676–714,813–819`。storage §3、ORP-02。O_EXCL 独占，fstat 跟踪标识，失败清理前复核；冲突、写入、文件 fsync、替换与并发创建均有生产入口用例。 | 已覆盖的正常冲突和身份替换不会误删。身份比较到 unlink 仍有外部目录写者引入的窗口，先前验证与最终清理之间的 inode 重用也未实测。按 storage §1 与 ORP-02 保留部署和跨进程清扫边界。 |
| P1-05 SQLite deadline 与 fencing | `storage_lock.py:303–326,447–488,525–536,582–594`，`session.py:139–187`。storage §4.2、§4.4、§4.6。BEGIN IMMEDIATE 前设剩余 PRAGMA，`populate_existing=True`，业务 session 失配回滚用例实际复跑。 | 未闭环。首把过期后交付及预算外等待见 IR2-01、IR2-02。 |
| P1-06 PostgreSQL 锁及心跳 | `storage_lock.py:188–263,619–635,647–652,689–852,863–995`。storage §4.3–4.6、§7。NullPool 每 guard 一物理连接、投影去重排序，互斥状态锁串行，最终核验 FOR UPDATE 与实际会话标识，迟到连接回调清理。 | 替身覆盖晚到连接、SQL 分类、连接失效、交错与关闭。未覆盖真实传输阻塞和上下文异常保真，见 IR2-03、IR2-04。真实 PG 门槛仍阻塞。 |
| P2-01 Windows F12 | `attachment_storage.py:515–580,589–626`。storage §6.1。Win32 17 / EXDEV、32/33、5/1314、80/183 各自分类；18、55 与未知码直接失败。测试含 Windows 真机占用、错误注入和目标已存在 no-clobber。 | 原码修正有效。截获了路径预检错误，仍可能触发不合规降级，IR2-05。Windows 1 的适用范围也应限定到 hard link 调用明确报告的失败。 |
| P2-02 POSIX 目录 fsync | `attachment_storage.py:421–434,656–664,696–714,792–839`。storage §3.1 第 8 步，GC §5.2。注入打开及 fsync 错误，发布报告失败并保留正式孤儿，退出清理自有临时。 | 代码与注入路径符合。真实 POSIX 仍需验证目录持久性与硬链接语义。 |
| P2-03 gc_max_attempts | `config.py:78` → `main.py:92–98` → `repositories_v2.py:453,526,557,568–573`。architecture §5、GC §4.3。启动配置覆盖调用真实 factory/写事务入口，并检验预算耗尽任务不 claim，见 `test_attachment_storage.py:978`。 | 装配链成立。定向复跑排除 lifespan，用提交的原生 B1 日志复核该条。 |
| P2-04 SQLite busy 重试 | `session.py:131–187`，`main.py:96–98`。architecture §4.4、GC §3。区分 SQLite BUSY/LOCKED，回滚 session 和 connection 后新事务有限重试。已 flush 后注入 busy 与真实写锁耗尽测试复跑。 | 短事务重试及回滚成立。外层连接池预算缺口见 IR2-02，PG 短事务入口的 B5 调用隔离待真实环境复核。 |

关于 GC 的业务前置，引用复核、任务租约与存储 guard 的双重核验和 24 小时条件归 B5 协调器。当前 `operator_transition` 保留了预期状态白名单与 token 条件，调用身份和审计记录的端到端验收仍需 GC-11。
