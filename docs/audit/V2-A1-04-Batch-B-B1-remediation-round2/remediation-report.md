# B1 缺陷、修复与验收映射

冻结条款使用设计目录内各文件的标题编号。对应测试报告区分真实环境与注入证据。原始审计为对话交付，缺陷编号沿用本轮任务。

| 编号与冻结条款 | 整改前 | 整改后及失败边界 | 回归证据 |
|---|---|---|---|
| P1-01 · GC §3–4，GC-01/02/04/08/09/10 | token 相等即可从部分状态写入，过期租约可以完成任务，人工入口缺失 | repositories_v2.py:470 起，按数据库时钟和原子 WHERE 校验 running/owner/token/expiry。worker、到期调度、运维显式入口分设。到期重排、耗尽处理、隔离等待、永久失败转人工分别限定来源；人工重试重置 attempts 并保留隔离记录。失败返回 None，无隐式提交。 | test_attachment_gc.py 的 owner/token/过期/等待写锁、提前重试、人工、隔离期和并发写回 |
| P1-02 · Storage §3.1、§4.5–4.6；GC §3、§5；ATT-12、LCK-05/08、GC-04/05 | 任意非空对象可发布、恢复；隔离、删除可绕过 guard | attachment_storage.py 的 _fence、_mutate、publish_no_clobber、move_to_quarantine、restore_from_quarantine、delete_path。要求真实 guard 覆盖 key，文件变更及 Windows 重试每次重新验租约；隔离 link 后、unlink 前复核。 | 30 组无效 guard × 操作的组合、真实 SQLite 正常 guard、占用后失锁注入 |
| P1-03 · Storage §1、§5–6；ATT-09、ATT-12 | 加载配置时解析链接，校验前 mkdir/chmod，部分 I/O 只检查最终组件 | config.py:147 起保留带组件的绝对路径。attachment_storage.py 的 _directory_chain、preflight_storage_roots、ensure_runtime、_open_regular 先查链接/重解析点，再查规范路径、目录身份和卷。main.py:79 在建库、进程锁创建前预检。文件打开比对 lstat 和 fstat，恢复/删槽只接受 key 与规范 UUID。 | 配置到 lifespan、模拟 reparse、同身份别名、其他卷注入、目录冒充 blob、越界、真实文件替换、真实 junction 用例按环境执行 |
| P1-04 · Storage §3.1/3.3；ATT-11/12、ORP-02 | 独占创建失败后会 unlink 已存在同名文件 | attachment_storage.py 的 _exclusive_temp、_unlink_owned、write_temp、copy_to_temp、publish_no_clobber。成功独占创建才建立所有权。TempBlob 随调用传递创建身份，清理前复核原文件身份。失败后不删替换文件，发布后孤儿留待 ORP。 | xb 冲突、并发创建、写及文件 fsync 失败、发布失败、发布前替换同内容临时文件 |
| P1-05 · Storage §4.2、§4.4、§4.6；LCK-02/03/05/08 | 5 秒 busy timeout 突破 0.15 秒等待；最后核对可命中旧 ORM 行 | session.py:146 起用短事务所有者、剩余预算和 BEGIN IMMEDIATE；SQLite 锁获取共享 deadline，部分获取失败非阻塞逆序清理，清理争用时保留 TTL 兜底。storage_lock.py 的 _verify_guard / _reload_lock_row 强制刷新，业务 session 失配时抛错。 | 真 SQLite 0.15 秒争用/零预算、缓存行被另一事务写入、fence 失败后业务写回滚 |
| P1-06 · Storage §4.3–4.6；LCK-10 | 心跳与 verify/release 可同时操作专用连接；连接和 SQL 没有共用预算；数据库异常与竞争混同 | storage_lock.py 的 LockGuard、_pg_apply_budget、PostgresStorageKeyLock。状态锁串行，末次 verify 停止并排空本 guard 心跳。连接等待受批 deadline 限制，晚到连接关闭；SQL 设置剩余 statement/lock timeout；使用 NullPool、按签名身份去重排序，断线不允许旧 guard 重连。区分争用 None、连接失败、SQL deadline/错误和会话断开。release 的 SQL 错误继续归类为 PostgresLockFailure，并在抛出前清理专用连接与注册状态；心跳日志只包含异常类型。 | test_storage_lock_pg_faults.py 含 release SQL 错误、关闭与再次释放断言；test_storage_lock_pg.py 保留真实 PG gate，新增 UPSERT 与 FOR UPDATE 争用 |
| P2-01 · Storage §6.1 F12；ATT-12 | Win32 18 判跨卷、55 触发 rename，原生错误还可被映射 errno 覆盖 | attachment_storage.py 的 _is_cross_volume、_is_unsupported_link、_link_or_rename。原生码优先，17 跨卷，18/55 直接失败；只对明确不支持分支降级。目标存在重验 size/hash。 | F12 旧回归、未知原生码三例、目标出现的两种 hash 分支。官方依据见下 |
| P2-02 · Storage §3.1、§6；ATT-11、ORP-01/02 | POSIX 目录打开/fsync 失败静默忽略 | attachment_storage.py 的 _fsync_dir、_fsync_parent_chain。失败向调用者报告；已发布但持久性未确认的正式 blob 原位保留。隔离 link 先持久化目标再断开正式名，失败保留可恢复状态。 | 目录打开及 fsync 两种故障注入、文件仍在且临时文件已清理 |
| P2-03 · Architecture §5；GC §4.3、GC-09 | 运行装配没有传 setting，依赖默认 8 | main.py:92 把 settings.gc_max_attempts 与隔离秒数传给 app.state.gc_task_repository_factory。 | lifespan 设置 2 和 90000，仓储 claim 拒绝已耗尽任务 |
| P2-04 · GC §3、Architecture §4.4；GC-02/08 | 短事务 busy 缺少外层有界恢复入口 | session.py:131 起识别 BUSY/LOCKED，回滚并换 session 后按剩余预算重试，耗尽抛 SQLiteWriteTimeout。main.py:96 装配仅用于可重放的 GC 纯数据库短事务；仓储不 commit，不启动 worker。 | 已 flush 后注入 busy，下一事务观察不到未提交写；真实写锁下预算耗尽 |

- F12 原生码定义依据 [Microsoft 系统错误码](https://learn.microsoft.com/en-us/windows/win32/debug/system-error-codes--0-499-)。
- PostgreSQL 同步连接的 libpq 秒级最小超时与每地址预算见 [PostgreSQL libpq 文档](https://www.postgresql.org/docs/16/libpq-connect.html)。线程仅承担专用连接建立；超时后的结果不能交给 guard。
- B1 内部发布接口由路径改为 TempBlob，隔离、恢复和删除显式传 guard。没有改变 Core port、冻结文档或现有 HTTP 接口。
- SQLite busy 重试入口仅适用于可完整重放的短数据库事务。文件变更、提交后副作用和 Batch A D23 恢复继续遵循既有协调边界。
- B1 的人工入口提供受源状态和令牌约束的原子转换。运维身份确认、动作审计及 GC 文件与引用前置校验由冻结的后续协调流程接入。
