# 回归与测试断言审查

提交原始输出位于 `../V2-A1-04-Batch-B-B1-remediation-round2/test-evidence/`。校验 ZIP 内日志与工作树副本一致。

| 提交记录 | 原始日志核对 | 退出码 |
| --- | --- | ---: |
| B1 七文件最终专项 | `round2-final-b1.txt`，154 通过，18 跳过。17 个须真实 PostgreSQL，1 个是 POSIX 句柄路径替换场景。 | 0 |
| Batch A / A1-02 | `round2-final-hash-and-batch-a.txt`，251 通过。 | 0 |
| A1-03、治理/API、V1 | `round2-current-frozen.txt`，409 通过，154 跳过。日志列出各跳过原因。 | 0 |
| 根级 SQLite/Windows | `round2-current-full-sqlite.txt`，1,278 通过，196 跳过。此数字涵盖其他组，汇总时不重复计数。 | 0 |
| Ruff Backend/Core | `round2-current-ruff-code.txt`，通过。独立重跑一致。 | 0 |
| Ruff 全仓 | `round2-current-ruff-repo.txt`，5 项。独立复跑 5 项均位于冻结审查历史副本里的 `0006_v2_markdown_kb.py:33,39–41`（UP035、I001、UP007）。迁移实际文件无 Git 差异。 | 1 |

独立复跑在现有解释器执行 `pytest -o addopts=--import-mode=importlib -p no:cacheprovider -ra`，且使用 `-B` 避免生成字节码。仓库已有完整结果，本轮另做高风险的复核子集和边界探针。

| 独立范围 | 结果 | 包含的证据 |
| --- | --- | --- |
| GC SQLite、存储锁 SQLite、PG 替身故障。过滤 `-k 'not lifespan'` | 57 通过，1 deselected，退出 0 | 23 项 GC，24 项 SQLite 锁，10 项 PG 替身 |
| storage 与 Windows 的 F12、temp、fence、目录同步、文件路径与真机占用子集 | 52 通过，1 跳过，44 deselected，退出 0 | 路径、fencing、所有权及 fsync 注入，真实 Windows 占用。junction 创建受限跳过 |
| Ruff Backend/Core 与全仓 | Backend/Core 退出 0，全仓退出 1 | 结果与历史审计副本路径归因一致 |
| 独立边界探针 | 复现缺陷 | 查看 [发现登记](finding-register.md) 和 [环境证据](environment-evidence-review.md) |

第二个子集的选择表达式为 `f12 or exclusive_temp or final_mutations or directory_sync_error or publish_does_not_unlink or windows_real or read_rejects or runtime_rejects or same_directory_identity`。三组提交的长跑日志为既有提交证据，本轮没有宣称重跑全量。

### 断言与覆盖质量

- **GC 状态**。现行测试同时断言过期 owner、token/owner 不匹配、非法目标、提前重排、合法人工退回和并发更新。整改报告披露旧版曾把 failed_retryable → done 当成合法路径，改为拒绝并检查任务状态，同时增加到期重试确认。此方向符合 GC §4.2。
- **正式文件与临时文件**。测试使用真实 SQLite guard 走生产入口。碰撞检查要求原字节保持，临时文件测试检查独占失败、写入/同步失败、文件身份替换及多线程只一方成功。Windows 目录同步错误分支由 monkeypatch 注入。F12 测试主要注入 `os.link`，缺预检错误来源断言。
- **SQLite 事务**。用真实写锁测试短获取预算，用 ORM 已缓存行加另一事务修改验证刷新，且 fencing 失败后业务写回滚。busy 重试测试覆盖已执行写入后的 rollback 和换事务。未覆盖第一把租约在交付前过期、pool checkout 或独占写事务阻塞独立 verify。
- **PG 测试**。替身验证投影顺序、延迟建连关闭、heartbeat 与 verify/release 串行、SQL 错误类型和调用顺序。真实 `FOR UPDATE`、UPSERT、advisory 跨连接与 TTL 用例存在，提交时全部跳过。显式 release 错误测试不会经过 `__exit__` 的业务异常传播。
- **历史代码可追溯性**。七个 B1 测试未跟踪，Batch A HEAD 没有其首版文件。原 B1 SHA 清单和整改说明有据，未发现当前测试通过删除关键断言来掩盖上述场景。缺少首版逐字源码或测试，无法对所有历史断言执行逐行差分。
