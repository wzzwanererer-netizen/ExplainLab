# 04-B · 验证缺口清单

- 目的：明确哪些结论已由真实环境验证，哪些只是注入式/理论/未验证，避免把“测试通过”扩大解释。
- 与 `test-summary.md` 配套；所有“未验证”项不构成本轮已通过声明。

## 1. PostgreSQL：UNVERIFIED

| 项 | 状态 | 证据 |
| --- | --- | --- |
| 真实 PG 实例 | **无** | `EXPLAINLAB_PG_TEST_URL` unset；`psql`/`pg_ctl`/`postgres` 不在 PATH |
| 容器 | **无** | `docker: not found`、`podman: not found` |
| Windows 服务 | **无** | 服务查询为空 |
| WSL | **不可用** | `wsl psql: not found`、`pip3: not found`、SQLAlchemy absent |
| PG 门控测试 | **178 skipped** | 完整套件统计 |
| 迁移 up/down、tsvector/GIN/触发器/级联、CJK 回退、向量/混合检索 | **未执行** | 需真实 PG |

证据文件：`evidence/postgresql-probe.txt`。
结论：**不得表述为 PostgreSQL 已验证**。Batch A 的 Journal/ID 逻辑本身是文件系统 + SQLAlchemy，但本轮所有实测均在 SQLite。

## 2. POSIX：部分验证

WSL Ubuntu 探针（`evidence/posix-probe-run.txt`）：

| 检查 | 结果 |
| --- | --- |
| ID 创建 0600 | PASS |
| `ensure` 幂等 | PASS |
| 并发 `ensure` | PASS |
| 回退 O_EXCL | PASS |
| 目录 fsync 被调用 | PASS |
| ID replace 原子 | PASS |
| `write_all` EINTR 重试 | PASS |
| 跨进程 ProcessLock 争用 | PASS（第二进程返回 `BACKEND_ALREADY_RUNNING`） |
| 释放后子进程可获取 | PASS |
| 完整 Journal/导入事务 | **UNVERIFIED**（Python 3.14 无 pip/SQLAlchemy） |

结论：POSIX 的原子发布原语与进程锁**部分真实验证**；完整后端事务、Journal 恢复、SQLite/PG 行为**未在 POSIX 验证**。

## 3. Windows 文件系统

| 项 | 状态 |
| --- | --- |
| NTFS 真实临时文件、`os.open`/`os.write`/`os.fsync`/`os.close`/`os.replace`/`os.link` | **真实执行**（默认套件） |
| 硬链接支持 | **真实执行**（P2-05/06 使用真实 `os.link`，仅竞态用 monkeypatch 在 link 瞬间写目标） |
| 0o600 权限语义 | **不等效 POSIX ACL**；Windows 未验证实际 ACL |
| 目录 fsync | **代码 no-op**（显式 `os.name == "nt"` 返回），不宣称掉电持久 |
| 文件被占用时 rename/delete | **未验证**；设计有重试策略，但本批未注入 sharing violation |
| 跨卷发布 | **未验证**；设计假设同卷 |
| 真实断电/介质损坏 | **未验证** |

## 4. Uvicorn reload / 多 worker

| 项 | 状态 |
| --- | --- |
| 单进程 Uvicorn（开发 `--reload`） | 未在本次审计材料中启动验证 |
| `--workers > 1` | **不支持/未验证**：`ProcessLock` 在启动时独占 data_dir（`main.py:72–91`），第二个 worker 预计失败；未实测 |
| reload 期间新旧进程交接 | **未验证**；旧进程释放后新进程取锁的理论路径存在，未做真实重启测试 |
| 多实例共享 data_dir | **不支持**（设计以 ProcessLock 排除），未压测 |

## 5. 并发与锁

| 项 | 状态 |
| --- | --- |
| 线程级 `identity_guard`（RLock） | 由导入/审核冲突测试覆盖单进程内路径 |
| 真实高并发导入 + 导出物化竞争 | **未做压力测试**；并发窗口由设计锁闭合，但无大规模实测 |
| 跨进程 Journal 锁 | **未验证**；依赖单实例 ProcessLock |
| 死锁/锁顺序 | 代码审查确认 coordinator→Journal 单向；未做形式化验证 |

## 6. Journal 崩溃注入

| 项 | 状态 |
| --- | --- |
| PREPARED MATERIALIZE → 恢复 | 真实 SQLite + 手工构造 PREPARED，覆盖“DB 空”“DB 其他值”等 |
| PREPARED ROTATE → 恢复 | 覆盖 ID 未换/已换两分支 |
| COMMITTED 未归档 → 恢复补归档 | 覆盖 |
| 进程在任意指令处被 kill -9 / 断电 | **未验证**；现有注入仅为 Python 异常/函数替换 |
| Journal 文件被外部截断/篡改 | 覆盖损坏与 checksum 不匹配（fail-closed） |
| 归档写入中途崩溃 | 注入 fsync/close/replace 失败；未做真实断电 |

## 7. 测试方法本身的边界

- 故障注入通过 `monkeypatch` 替换模块内 `os.write`/`os.fsync`/`os.close`/`os.replace`/`os.link`；它能证明控制流与清理，不证明真实内核在 EIO/ENOSPC 下的行为。
- 短写/零写是人工构造；真实磁盘短写概率极低。
- 测试断言基于临时目录；不覆盖生产 `backend/data` 的权限、备份、磁盘配额。
- 未做模糊测试/属性测试。
- SQLite 为文件库，未启用 WAL 压测；未验证与外部进程同时写库。

## 8. 其他未覆盖

- 真实模型调用：本批不涉及生成/嵌入，未联调。
- 前端浏览器 E2E：仅有 Vitest/typecheck/build，未做浏览器端导入导出流程截图。
- 认证/多用户/租户隔离：超出 Batch A。
- 附件导入/审核：按设计返回 `ATTACHMENT_*_UNSUPPORTED`，未实现，非缺陷。
- 备份/恢复、降级 CLI：本批不交付。
- 性能/吞吐：`identity_guard` 全局串行化会降低导入吞吐，未量化。

## 9. 结论

已验证的范围是：Windows + SQLite + 单进程 + 真实文件系统原语 + 注入式故障。  
未验证的范围是：PostgreSQL、POSIX 完整事务、真实断电/硬件错误、多进程/多 worker、高并发压力、浏览器 E2E。审计结论应以此边界为准。