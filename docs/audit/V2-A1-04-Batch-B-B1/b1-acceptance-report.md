# B1 验收报告（V2 A1-04 Batch B）

> 本报告只记录 B1 基础层**已真实运行**的结果。B1 不是 Batch B 验收；HTTP/审核/worker 端到端证据属于 B2–B5。未运行项一律标记“未验证/阻塞”，不以 SQLite 或模拟替代 PostgreSQL，不以 Windows 结果替代 POSIX。

## 1. 环境

| 项 | 值 | 证据 |
|---|---|---|
| OS | Windows 10.0.26300 x64（真机） | `raw/environment.txt` |
| Python | 3.11.9 | `raw/environment.txt` |
| SQLite | 3.45.1（真实文件库） | `raw/environment.txt` |
| PostgreSQL | **不可用**：`EXPLAINLAB_PG_TEST_URL` 未设置，无 `psql`/`pg_isready`，5432/5433 无监听 | `raw/pg-availability.txt` |
| POSIX | **不可用**：本机仅 Windows | — |

## 2. 测试结果（真实输出见 `raw/`）

| 命令 | 结果 | 退出码 | 原始证据 |
|---|---|---|---|
| T01/T02 存储 + Windows 套件 | 44 passed, 1 skipped | 0 | `pytest-t01-t02-storage-windows.txt` |
| Windows 真机专项（独占） | 6 passed | 0 | `pytest-t02-windows-real.txt` |
| T03 SQLite 锁 | 20 passed | 0 | `pytest-t03-lock-sqlite.txt` |
| T04 SQLite 仓储 | 16 passed | 0 | `pytest-t04-repository-sqlite.txt` |
| T03/T04 PostgreSQL（门控） | 15 skipped | 0 | `pytest-t03-t04-pg-skipped.txt` |
| 根级全量 pytest | 1204 passed, 194 skipped | 0 | `pytest-full.txt` |
| `ruff check backend knowledge-core` | 通过 | 0 | `ruff-code.txt` |
| `ruff check`（仓库全量） | 5 errors，全部位于未跟踪的冻结审阅快照 `docs/audit/V2-A1-04-Batch-B-freeze-review-package/source-evidence/.../0006_v2_markdown_kb.py`（非 B1 代码，未改动） | 1 | `ruff-check.txt` |

说明：

- 44 passed 中的 1 skipped 是 POSIX-only 的“校验后路径替换”用例（Windows 打开句柄默认拒绝替换），属预期跳过，不是失败。
- 15 skipped 全部来自 `EXPLAINLAB_PG_TEST_URL` 门控；**PG 项不得视为通过**。
- 仓库全量 ruff 的 5 个问题为审阅包内源文件副本（JSON/证据材料），B1 新增/修改的 backend 代码与测试 `ruff check` 全部通过；未通过排除配置掩盖。

## 3. 验收编号映射（仅 B1 范围）

### 3.1 存储与启动

| 编号 | B1 覆盖内容 | 结果 | 缺口 |
|---|---|---|---|
| ATT-01 | 默认根/分片路径、真实 SHA-256 向量、临时写入、发布后路径 | 已验证（Windows+SQLite） | HTTP 201/响应字段属于 B2 |
| ATT-02 | 相同内容同 key 复用（不覆盖）、COUNT=2、DISTINCT key | 已验证（存储层+仓储层） | 上传两 item 的 HTTP 流程属于 B2 |
| ATT-06 | 根路径隔离、越界/`..`/链接拒绝；文件名不进入磁盘路径 | 部分验证 | 文件名字符清洗/保留名属于 B2 |
| ATT-09 | 同句柄打开一次完成 size/hash、seek(0)、失败关闭 | 已验证（存储层） | 下载路由/头属于 B2 |
| ATT-10 | 同 key 并发发布（线程）不覆盖不损坏；双 manager 锁互斥 | 已验证（存储+SQLite 锁） | 上传/GC 屏障联调属于 B2/B5 |
| ATT-12 | F12 各分支注入；真实 Windows 占用重试、rename 不覆盖；明确不支持才降级 | 已验证（Windows 真机） | 真实跨卷仅以 monkeypatch 模拟，未在双卷真机取证 |
| ORP-02 | `.tmp` 目录创建/临时文件生命周期 | 部分 | ORP 扫描本身属于 B5，未实现 |
| R1.1-IMP-42 | 启动根：真实目录、重叠、越界、junction 拒绝、同卷 | 已验证（Windows） | sweep 行为属于 B5 |

### 3.2 StorageKeyLock

| 编号 | SQLite | PostgreSQL |
|---|---|---|
| LCK-01 新 key / token | 已验证 | **未验证/阻塞** |
| LCK-02 双 owner 互斥 | 已验证（线程 + 双 manager） | **未验证/阻塞** |
| LCK-03 过期接管/token+1 | 已验证（逻辑过期） | **未验证/阻塞**；无真实进程 kill |
| LCK-04 renew | 已验证 | **未验证/阻塞**（测试已写，未运行） |
| LCK-05 失配中止/`StorageLeaseLost` | 已验证 | **未验证/阻塞** |
| LCK-06 release 匹配/失配/保留 token | 已验证 | **未验证/阻塞** |
| LCK-07 持锁进程崩溃 | **未验证**（无子进程 kill 用例） | **未验证/阻塞** |
| LCK-08 verify→syscall TOCTOU | **未验证**（未做暂停/接管窗口注入） | **未验证/阻塞** |
| LCK-09 严格互斥降级 | 诚实记录：代码与文档均声明 SQLite 为租约逻辑锁，不宣称严格互斥 | 同左 |
| LCK-10 行 TTL 过期不授权接管 | 不适用（SQLite 无 advisory） | **未验证/阻塞**（测试已写：两连接、行过期、断连接管、同投影） |

### 3.3 仓储 / GC 基础

| 编号 | B1 覆盖内容 | 结果 | 缺口 |
|---|---|---|---|
| ATT-08 | 删除引用行、COUNT 下降、共享引用不误删 | 已验证（仓储，SQLite） | 同一事务插入 `gc_task pending` 属于 B2 服务层 |
| ATT-11 | 发布后 DB 失败 → 无行；flush/rollback 隔离 | 部分验证（仓储回滚） | 真实发布→commit 失败→ORP 收敛属于 B2/B5 |
| GC-01 | pending→running、token+1、attempts+1、租约 | 已验证（SQLite） | PG 未验证 |
| GC-02 | 双 session 并发认领仅一成功；双 manager 同 key 互斥 | 已验证（SQLite） | PG 未验证 |
| GC-09 | attempts≥8 不可认领；终态不可回写 | 已验证（仓储条件） | 真实第 8 次失败与退避由 B5 worker 验证 |
| GC-10 | token 失配更新返回 None 且不覆盖 | 已验证（SQLite） | PG 未验证 |
| GC-12 | 无计数列，COUNT 始终权威 | 已验证（SQLite） | PG 未验证 |

## 4. 未验证 / 阻塞清单

1. **真实 PostgreSQL（阻塞）**：LCK-01…10 的 PG 分支、GC/附件仓储 PG 并发与 fencing 全部未运行。原因：本机无 PG 实例、URL 未配置。不得以 SQLite 替代。
2. **POSIX 真机**：fsync/权限/符号链接/rename 语义与 POSIX-only 用例未运行。
3. **真实进程 kill**：LCK-07/GC-07 类（持锁/隔离/发布各阶段崩溃）未取证。
4. **真实跨卷**：仅以 monkeypatch `_st_dev`/`OSError` 注入验证分支，未在双卷环境实测。
5. **TOCTOU 窗口**：LCK-08 未做 verify 前/后暂停+接管。
6. **HTTP/审核/worker 端到端**：不属于 B1，未实现、未验收。
7. **仓库全量 ruff**：5 个既有问题位于未跟踪审阅快照，非 B1 代码；未修改该快照。

## 5. 判定

- B1 代码实现：**完成**。
- B1 在 SQLite + Windows 文件系统范围内的证据：**已验证**（见上表）。
- B1 整体：**有条件**。PG 阻塞 + POSIX/进程 kill/TOCTOU 未验证，不能宣称 B1 验收通过，更不能宣称 Batch B 通过。
- 下一步：停止开发，等待 Codex 独立代码审查与 ChatGPT 阶段验收；不得自行进入 B2。