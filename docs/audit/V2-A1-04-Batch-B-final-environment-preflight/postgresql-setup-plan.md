# PostgreSQL 搭建与真实验收方案

**执行前提：搭建获批，且可在选定 Linux 环境内实测 loopback。当前没有已可用的真实 DSN。**

## 实例与账号

优先在获批复用的 WSL2/VM 上使用专用、可销毁的 PostgreSQL 集群。若已有专供测试且无其他数据的实例，经同等隔离核验后可复用。用可用且受支持的服务端版本，优先复用已有版本，记录实际 major、minor 和安装来源。

- 新集群在唯一的 ext4 临时父目录创建数据与 Unix socket 目录，由普通系统账号管理。选空闲端口，可先尝试 55432，仅监听 127.0.0.1。管理员在私有 Unix socket 连接，TCP 仅接受本次测试 DB/角色，使用 SCRAM。
- 每次建立独立数据库 `explainlab_b1_<runid>` 和登录角色 `explainlab_b1_test`。角色受限为 NOSUPERUSER、NOCREATEDB、NOCREATEROLE、NOREPLICATION、NOBYPASSRLS。在这一个数据库内拥有应用迁移需要的 schema 与对象权限。先检查迁移实际所需权限，并将任何额外权限保留在测试实例和该数据库的范围。
- 管理员使用 PostgreSQL 原生客户端提示设置角色密码，真实连接参数由该次运行生成。DSN 结构为 `postgresql+psycopg://explainlab_b1_test:<URL编码密码>@127.0.0.1:<端口>/explainlab_b1_<runid>`。仅在测试进程环境设置 `EXPLAINLAB_PG_TEST_URL`。使用 SQLAlchemy URL 对象组装特殊字符密码，日志只保留脱敏端点与 `current_database/current_user`。现有 Alembic URL 百分号处理保持冻结。
- 两套 fixture 会在线执行升级，并在用例前后直接清理 `storage_lock`、`gc_task`、`attachment`、`knowledge_item`。运行前必须用计划中的测试账号实际连通，并核对数据库名、角色、实例端口和数据目录。串行使用同一临时数据库。若未来并行，每个进程须有独立数据库。

初始化和认证参数依据 [PostgreSQL initdb 文档](https://www.postgresql.org/docs/16/app-initdb.html)。

获批后，按所选服务端的实际 PATH 执行 `initdb` 和 `pg_ctl start`。示例中的运行目录是新建的私有 ext4 目录，端口须先实测空闲。

```bash
initdb -D "$run_root/pgdata" --auth-local=peer --auth-host=scram-sha-256
pg_ctl -D "$run_root/pgdata" -l "$run_root/postgres.log" \
  -o "-c listen_addresses=127.0.0.1 -p $test_port -k $run_root/socket" -w start
psql -X -h "$run_root/socket" -p "$test_port" -d postgres
```

先创建私有 socket 目录，并核对实例的 `pg_hba.conf` 与本次角色和数据库范围。创建测试角色和数据库由初始化账号在上述会话执行，随后用 `\password explainlab_b1_test` 设置随机密码。运行套件前用测试角色从 TCP 实际登录，执行 `SELECT current_database(), current_user, pg_backend_pid(), inet_server_port();`。使用目标核验结果与本次运行清单交叉校验。真实 DSN 生成步骤只在批准阶段执行。

## 真实双连接与运行

1. 以测试账号同时保持两个连接，分别取得 `pg_backend_pid()`，B 再取一次确认是独立 backend。记录 server_version、当前角色/库和实际端口。通过一次受控 lock/释放 smoke 核对实际实例。
2. 从与 Round 3 哈希一致的源码副本运行已有 13 项锁和 4 项仓储真 PG 测试。用 `uv run --locked --no-sync pytest -o addopts=--import-mode=importlib -ra backend/tests/test_storage_lock_pg.py backend/tests/test_attachment_pg.py`，记录基线与退出码。预期无 PG 环境跳过。具体测试覆盖由实际输出逐项确认。
3. 关联 LCK-10 的真实 oracle 记录 A 持有会话 advisory、B 竞争失败、人工调整行 TTL 后仍不得接管、A 真实断线后 B 可接管且 token 加一，旧 guard 不能继续写。按相同投影和跨批顺序记录物理会话 PID。比对 `pg_locks` 与 token 行。会话级锁直至显式释放或会话结束，事务 rollback 不能充当实际断线。见 [PostgreSQL advisory locks](https://www.postgresql.org/docs/16/explicit-locking.html#ADVISORY-LOCKS)。
4. 补已有真机套件缺少的证据时，使用运行目录中的临时验收探针。执行 100 key/单专用会话、部分获取失败清退、持锁子进程真实终止、受控长语句令 heartbeat 正在进行时进入 verify/release、commit/rollback/close 时序、迟到建连及真实业务异常和释放错误并发。仅对本轮启动的子进程、独占测试会话与测试表操作。记录服务器 PID、`pg_locks` 残留、客户端 elapsed、原业务异常或已提交结果和稳定释放日志。
5. 将真实进程退出和正常主动关闭分别记录。模拟连接和本地故障注入可用于对照。真实半开传输若只能在获批环境中用受控的测试连接停顿实现，记录注入位置、仍然实际使用的 PostgreSQL 会话、断开时点及服务端回收时点，避免将普通 SQL 等待等同于半开故障。

## 清理

先保存脱敏日志和迁移 revision，再验证无残留测试进程和会话。已批准的清理只针对已核对名称、端口、数据目录和进程归属的这次测试资源。停掉独占集群及释放临时 DB/账号后清理专用目录。无法验证资源归属时停止清理并保留清单。
