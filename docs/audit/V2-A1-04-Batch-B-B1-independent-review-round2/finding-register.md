# 独立审计发现

编号 IR2-* 为本次发现。行号对应审计时工作树。所有独立探针只使用临时库、临时目录或驱动替身。

## IR2-01 · P1 · SQLite 可交付已过期的批量 guard

- **代码**。[`backend/app/db/storage_lock.py:303`](../../../backend/app/db/storage_lock.py#L303) 只跟踪获取 deadline。第 319–326 行将所有 lease 直接交付给 guard。第 450–463 行按每个 key 分别计时，较晚取得的 key 不延长较早 key 的租约。
- **条款**。冻结 storage §4.4、§4.6，`storage-and-lock-contract.md:155–157,174`。整批取齐才可使用，第一把租约贯穿批量获取且不得在过程中耗尽。
- **验证**。用两个 manager 和临时 SQLite 文件。先占用排序第二的 key 约 0.38 秒，另一 manager 用 1 秒批量预算、0.15 秒 TTL 获取两个 key。0.390 秒后返回非空 guard，立即 `verify_all` 抛 `StorageLeaseLost`。
- **影响**。短 TTL 或较长批量等待时，acquire 返回表面成功，随后操作失败，早期锁已经可被接管。现有单次物理变更仍会再 fencing。应补“首把租约于批量交付前过期时不能返回可用 guard”的断言。

## IR2-02 · P1 · SQLite fencing 与连接池等待超出预算

- **代码**。[`backend/app/db/storage_lock.py:525`](../../../backend/app/db/storage_lock.py#L525) 至第 536 行直接查询 SQLite。[`backend/app/db/session.py:44`](../../../backend/app/db/session.py#L44) 设置 5 秒 busy timeout。第 156–166 行在拿到连接之后才把剩余预算写入 PRAGMA，checkout 等待发生在之前。第 179 行恢复默认值。
- **条款**。冻结 storage §4.4、§4.6，`storage-and-lock-contract.md:157,179–180`。整批获取共用预算，末次核验等待有界。
- **验证**。真实 SQLite 第二连接占有独占事务时，无外部业务 session 的 `verify_all` 在配置 0.15 秒的 manager 上用时 7.391 秒，然后抛 `OperationalError`。另用单连接池将 checkout 限到 0.35 秒，调用 `run_sqlite_write` 预算 0.04 秒，实际 0.359 秒抛 SQLAlchemy `TimeoutError`。生产引擎读取到默认 checkout timeout 30 秒。
- **影响**。获取入口对 DB 写锁的短等待控制已改善，连接池争用和物理操作前 fencing 仍可能超时挂起。ORM 刷新和失败中止的测试不覆盖此等待路径。分别验证独占锁下独立校验、提交前同 session 校验和池耗尽场景。

## IR2-03 · P1 · PostgreSQL deadline 没有覆盖客户端阻塞及心跳排空

- **代码**。[`backend/app/db/storage_lock.py:619`](../../../backend/app/db/storage_lock.py#L619) 至第 635 行在同步 `execute` 内设置服务器端参数，返回后才检查已耗时间。第 763–764、828–831、834–852 行仍同步提交、回滚或关闭。第 199–203 行无时限 `join()`，第 235–257 行在最终 verify 和 release 前等心跳，verify/release 的 SQL 预算在后续才建立。
- **条款**。冻结 storage §4.3、§4.6，`storage-and-lock-contract.md:152,180`。连接、重试及全部阻塞 SQL 要使用剩余预算，末次核验和清理有界。PostgreSQL 服务器参数覆盖服务器收到语句后的执行或锁等待。见 [PostgreSQL 参数文档](https://www.postgresql.org/docs/16/runtime-config-client.html)。
- **验证**。对专用连接替身的预算设置调用注入 0.20 秒延迟，给批量获取 0.04 秒预算。约 0.203 秒后才返回 deadline 错误，替身关闭。该探针确认 Python 控制流，真实半开连接的等待与释放仍待取证。现有 UPSERT 和 FOR UPDATE 的真实 PG 测试均被环境门控跳过。
- **影响**。网络异常、连接初始化 SQL 或未完成的心跳可拖延文件停止、业务回滚和释放，会话 advisory lock 可能在这段时间继续持有。需要独立验证整批超时、迟到连接回收、断连和排空时限。

## IR2-04 · P1 · PostgreSQL guard 退出可能覆盖业务失败

- **代码**。[`backend/app/db/storage_lock.py:251`](../../../backend/app/db/storage_lock.py#L251) 至第 263 行的 `__exit__` 无条件调用 release。第 964–969 行对释放 SQL 错误抛 `PostgresLockFailure`。第 970–977 行负责清理。退出路径缺冻结的 `STORAGE_LOCK_RELEASE_FAILED` 独立记录。
- **条款**。冻结 storage §7，`storage-and-lock-contract.md:222`。释放失败单独记录，已提交业务结果应保留。
- **验证**。复用专用连接替身，令 release SQL 返回 SQLSTATE 42P01，并让 `with guard` 内发生业务异常。外层实际收到 `PostgresLockFailure(phase=release)`，业务异常仅留在异常链，连接替身仍被关闭。
- **影响**。失败时原始业务错误码可能被掩盖。若业务已提交，调用层也可能将一次成功操作报告为失败，诱发重试。B1 暴露了该通用 guard 接口，附件业务尚未接线。显式 release 的分类测试通过，需另测上下文退出保留原业务结果和稳定日志。

## IR2-05 · P2 · Windows 路径预检查错误可错误触发 rename

- **代码**。[`backend/app/services/attachment_storage.py:589`](../../../backend/app/services/attachment_storage.py#L589) 至第 604 行将路径检查、fencing、实际 syscall 放在同一调用里。第 607–621 行 catch 这整段的 `OSError`，按 hard link 错误分类。
- **条款**。冻结 storage §3.1、§6.1，`storage-and-lock-contract.md:78–79,207–215`。仅 hard link 明确不受支持时允许 Windows 同卷 rename。
- **验证**。在临时文件和真实 SQLite guard 上运行生产发布入口，对 link 前的文件元数据检查单次注入 Win32 50。结果 `link=0`、`rename=1` 且发布成功。Win32 17/18/55 与未知码的现有分类改进得到确认。
- **影响**。非 link 错误可改变发布路径和临时源的去留。现有 F12 主要在 `os.link` 注入，缺少分阶段故障断言。需验证前置失败始终原样退出，明确的 link 不支持才降级。

## IR2-06 · P2 · 缺失的预留文件路径可被创建为存储祖先目录

- **代码**。[`backend/app/services/attachment_storage.py:303`](../../../backend/app/services/attachment_storage.py#L303) 至第 313 行，对预留目录双向比较，对预留文件只比较相等或存储根包含文件。第 348–364 行的词法和规范路径两轮检查都复用此逻辑。第 389–392 行会创建尚缺失的祖先。
- **条款**。冻结 storage §1、B1-T01，`storage-and-lock-contract.md:28–31`，`implementation-roadmap.md:35–43`。存储根专用，非法/冲突配置在启动校验时拒绝。
- **验证**。以临时 `data_dir` 的尚不存在文件作为 SQLite DB，配置存储根位于该文件路径下。preflight 接受，实际初始化后 SQLite DB 路径成为目录，存储根创建成功。
- **影响**。首次启动或重建环境的错误配置可留下副作用，后续 DB 无法使用该文件路径。既有 DB 文件已存在时，目录类型检查会阻止此场景。补预留文件为候选根祖先、且祖先尚不存在的启动验证。

具体探针结果见 [environment-evidence-review.md](environment-evidence-review.md)。
