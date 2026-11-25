# 未完成验证清单（不得计为通过）

本文件只列**本轮未验证或覆盖不完整**的项。已通过项见 `../05-tests/README.md`。

## 1. 真实 PostgreSQL

- 环境：`EXPLAINLAB_PG_TEST_URL` 未设置；`pg_isready`、`psql`、`docker` 均不可用
  （见 `postgresql-environment.txt`，URL 值有意不打印）。
- PG 门控模块共收集 **178** 项，全部 skip；与全量套件的 178 skipped 一致。
- 未在真实 PG 上验证：Alembic 升级/降级、导入/导出、身份 Journal、P1 并存冲突分类、
  source-instance-id、ROTATE、并发锁。
- 本轮所有结论仅限 SQLite；**不宣称 PostgreSQL 通过**。

## 2. Journal 崩溃矩阵

已由既有/新增测试覆盖的边：

- PREPARED current 写失败/半写：不发布正式 current，不进入 DB/ID 写；
- PREPARED MATERIALIZE 在 DB 为空时恢复：条件更新后提交归档；
- DB 已写、COMMITTED 未写时崩溃：恢复补写 COMMITTED 并归档；
- COMMITTED current 未归档：恢复只补归档，不重写 DB；
- current/archive 同操作重复：按 `operation_id` 去重；
- current 损坏、archive 损坏、checksum 不匹配：fail-closed，导入前阻断；
- archive 写失败：保留有效 COMMITTED current，重启后恢复。

未覆盖/未穷尽的崩溃点：

- `write_current(COMMITTED)` 成功到第二次审计校验之间崩溃；
- `archive_committed` 成功到 `remove_current` 之间崩溃（有去重测试，但未逐点注入）；
- `os.replace` 执行中/返回后、目录 fsync 前崩溃；
- 临时文件已写但进程在 rename 前被杀，残留临时文件的清理/忽略策略；
- 归档目录已有同名不同内容文件的竞争窗口；
- 两个进程同时恢复同一 current（当前只有进程内 `RLock` + 单实例锁设计，未做跨进程故障注入）；
- 断电、内核崩溃、文件系统重排导致目录项未持久化。

## 3. fsync / close / 发布故障

- 未注入 `os.fsync` 失败；实现会把异常向上抛且不执行 rename，但没有对应测试。
- 未注入 `os.close` 失败；`finally` 中 close 抛错的行为未单独验证。
- 未验证 close 失败后临时文件/正式文件的实际状态。
- 未注入 `os.replace` 失败（Journal current/archive、实例 ID replace）。
- 未注入 `os.link` 的 `FileExistsError`（“已有 ID 时读取而不覆盖”只有静态推断）；
  只注入了非 FileExists 的 `OSError` 以进入 fallback。
- 未注入 `write_all` 的 `InterruptedError` 重试；循环逻辑存在，但无测试。
- fallback 的 `except BaseException` 在 `os.close(target)` 失败时会删除已完整写入的正式 ID；
  结果 fail-closed，但可能丢弃一个本来有效的 ID，未测试。
- archive 的“二次存在检查 → `os.replace`”之间仍有竞争窗口；依赖单实例 `ProcessLock`，
  未做跨进程注入。
- 未验证进程强杀/断电后 `.tmp` 残留的清理；当前没有主动清理陈旧 tmp 的代码，
  只清理本次调用自己创建的 tmp。
- Windows 目录 fsync 为显式 best-effort（直接返回）；不宣称掉电持久性。

## 4. POSIX

- 本轮只在 Windows 10 实机、NTFS 上运行。
- 未执行 POSIX `fcntl.flock` 分支、POSIX 目录 fsync、`0o600` 权限在 Linux/macOS 的实际效果。
- 未验证 POSIX 下 `os.link` 不支持时的 fallback 路径。
- 未验证大小写敏感文件系统、NFS/SMB/网络盘、容器卷。

## 5. Uvicorn reload / 多 worker / ACL

- 未真实启动 `uvicorn --reload`；reload 会重启进程，单实例锁与 source-instance-id 的交互未实测。
- 多 worker 仅由启动入口的参数/环境变量检查拒绝（`MULTI_WORKER_UNSUPPORTED`），
  未在真实多 worker 进程组下验证。
- 未注入 Windows ACL 拒绝、只读数据目录、文件被其他进程占用等场景。
- 未验证服务异常退出后锁文件/临时文件/current 的实际残留状态。

## 6. 真实介质错误与持久性

- 未注入真实 `ENOSPC`、磁盘配额耗尽、只读文件系统、I/O error。
- 未做断电/强杀后的恢复演练。
- 因此只能声明“短写/返回 0/异常路径已测试”，不能声明“任何介质故障下都不产生截断正式文件”。

## 7. P1 覆盖残留

- 未直接构造“PREPARED current + ImportOrigin 并存且绕过恢复门直接 `classify`”的非正常调用；
  正常入口先 `recover_if_needed`，恢复会因目标已有 ImportOrigin 抛
  `SOURCE_IDENTITY_INCONSISTENT`。
- 未组合“同一 item 多条 MATERIALIZE，其中一条损坏/摘要不符 + ImportOrigin”；
  损坏 Journal 读取本身会先 fail-closed，但未做组合注入。
- 未做跨进程并发制造 ImportOrigin + MATERIALIZE 并存的竞争测试。
- 冲突复用冻结状态 3，未新增 `SOURCE_IDENTITY_CONFLICT` 稳定码；若审计要求独立错误码，
  需另行批准并同步验收矩阵。

### 7.1 本轮新记录的结构性边界（不自行修复）

- `classify()` 本身不调用 `recover_if_needed()`；当前 4 个生产调用点都有门，
  但函数不强制，未来新增直接调用方可能绕过恢复门（见
  `../04-journal/P1-conflict-and-recovery-audit.md` §1、§6）。
- `_export_record()` 是私有方法，生产代码只被两个有恢复门的公开导出入口调用；
  它内部没有自己的恢复门。若未来被其他路径复用，需自行保证门。
- `rotate()` 对状态 3 记录 `continue`（`source_identity.py:899-901`），不中止整个 ROTATE；
  这是计划 `docs/plans/V2-A1-04-implementation-plan.md:1247` 的既有语义，
  因此 rotate **不是**“遇到冲突即整体 fail-closed”。冲突条目 DB 身份不被改写，
  但全局 ROTATE Journal 与 `source-instance-id` 仍会写入。
- 现有 rotate 状态 3 测试只覆盖“ImportOrigin 残缺”，**没有**覆盖
  “ImportOrigin + COMMITTED MATERIALIZE 并存”在 rotate 下的行为。
- `materialize()` 在分类前调用 `_store.ensure()`（`source_identity.py:807`）；
  在空数据目录 + 冲突条目场景下，冲突调用仍可能创建全局 `source-instance-id` 文件。
  现有冲突测试运行时实例 ID 已存在，未单独验证该场景。
- 批量导出只在逐条循环前过一次恢复门（`markdown.py:1073`）；循环期间若状态变化，
  不会再次经过恢复门。导出为只读，未发现身份写入路径。
- 启动时只捕获 `SQLAlchemyError`（`main.py:86`）；损坏 Journal 的
  `SourceIdentityError` 会使启动失败（fail-closed）。未做真实 Uvicorn 启动集成测试。
- 导入可以向已有 MATERIALIZE 的条目追加 ImportOrigin，从而制造并存冲突；
  导入不调用 `classify`，也不自动修复。该行为是否符合预期流程需审计确认。

## 8. 其他既有边界

- `rotate-instance-id` CLI 未实现；ROTATE 仅服务层测试。
- 附件导入/导出/审核仍按 Batch A 范围拒绝。
- Batch B 附件、Batch C Backup/Restore 未实现，不在本轮范围。
- 未连接真实模型服务；A1-04 测试使用本地替身/真实 SQLite，不涉及外部模型。

## 9. 运行产物说明

运行 pytest / 前端构建会产生 `.pytest_cache/`、`__pycache__/`、`frontend/dist/` 等产物；
这些不是源码修改，也未纳入提交。工作树源码仍为本轮整改后的原文件。