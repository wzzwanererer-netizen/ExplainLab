# 六项整改实施报告

## IR2-01 · SQLite 批量租约

原行为只考虑总获取时间，首把租约的有效期可在第二把等待中耗尽。现在逐把成功后以最早到期时间裁剪同一个批次 deadline，到期后逆序尝试返还部分锁。全部获取后通过一次真实数据库查询读取所有 owner、token 和 expiry，以同一时刻确认有效，随后才启动心跳并交付。未续长已有 lease，原 token 递增及到期接管保持冻结语义。临时竞争阻断清理时，仍靠租约到期进入可接管状态。

## IR2-02 · SQLite 连接池与 fencing

原独立核验沿用全局 5 秒 busy timeout，连接池可按默认 30 秒等待。SQLite 写事务 checkout 按调用的绝对 deadline 等待，独立核验同时约束调用方时间和 SQLite busy timeout。最终核验使用同一业务 Session，在查询执行中强制刷新 ORM，并将 busy timeout 恢复为进入前的值。失败抛出 StorageLeaseLost，业务事务所有者负责回滚，独立读连接由校验入口归还。普通 Batch A 非预算事务继续沿用原连接池与 busy 设置。

## IR2-03 · PostgreSQL 有界等待

原 SQL 参数只限服务器处理，客户端同步阶段及无时限线程 join 可超预算。现在获取将建连、SQL、短事务和清理放在同一个绝对 deadline 下。专用会话调用的客户端等待独立计时，psycopg I/O 使用剩余预算，token 行写入仍与物理 advisory lock 的所有权关联。迟到操作保持唯一连接所有权，结束后执行物理关闭，防止另一线程复用或抢先关闭仍在调用中的替身连接。已弃用的原生专用会话在清理时先终止物理传输，再清理 SQLAlchemy 状态。

最终核验与释放先在各自统一预算内排空心跳，再获取 guard 状态锁。最终核验用业务 Session 读取 FOR UPDATE，专用会话检查真实锁投影与连接身份。连接建立、SQL 错误、会话中断和阶段预算耗尽保留分类。实际 PostgreSQL 服务端确认待实机取证。

## IR2-04 · guard 释放异常

原上下文直接调用 release，清理错误会成为调用方看到的异常。现在显式 release 继续返回结果或抛分类错误。上下文退出记录 `STORAGE_LOCK_RELEASE_FAILED`，保留原业务结果或异常 traceback。关闭失败尝试使连接失效。已经提交的结果和独立清理的失败各自可追踪。

## IR2-05 · Windows F12

原捕获区同时覆盖路径预检、fencing 和 hard link，使预检 Win32 50 可触发 rename。现在错误分类仅处理各自 syscall 抛出的 OSError。Windows 32/33 仍走有界占用重试，另一次尝试前会再次 fencing。仅 hard link 明确不支持后，才尝试 Windows 同卷 no-clobber rename。目标冲突仍走原验证或冲突分支。

## IR2-06 · SQLite 数据库预留文件

原预留文件检查缺少“候选根位于该文件下面”的判断。现在词法和规范路径两轮均比较相等及双向祖先关系，预检在已有应用 lifespan 的 mkdir、锁文件和 DB 初始化前执行。数据库配置保留未解析的路径组件。SQLite URL 解析会排除连接参数和纯内存库，路径组件及已有文件类型先通过检查，再进行规范化和创建。

代码与测试对应关系见 [finding-mapping.md](finding-mapping.md)。
