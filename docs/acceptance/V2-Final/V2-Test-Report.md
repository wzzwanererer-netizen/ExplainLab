# ExplainLab V2 · 测试与故障恢复

| 配置 | 测试 | 通过 | 跳过 | 失败 |
| --- | --- | ---: | ---: | ---: |
| Windows，SQLite 默认 | Backend + Knowledge Core 根级回归 | 1477 | 224 | 0 |
| Windows，SQLite | ZIP 到审核、Draft、共享引用和 GC 总集成 | 1 | 0 | 0 |
| Windows，SQLite | 清除后进程退出、ORP 并发、审核写入和索引 commit 故障 | 6 | 0 | 0 |
| 正常权限 Windows | SQLite DB 祖先、附件、staging junction，真实跨卷 | 4 | 0 | 0 |
| Ubuntu ext4，SQLite | staging、审核、GC/ORP、存储专项 | 191 | 2 | 0 |
| Ubuntu ext4，PostgreSQL 18.6 | API 上传和共享、Draft 并发、Active 审核、端到端 GC | 8 | 0 | 0 |
| Ubuntu ext4，PostgreSQL 18.6 | 真实 PG 回归、锁、迁移、检索和治理 | 205 | 0 | 0 |

Windows 根级回归中的跳过来自真实 PG 门控和平台条件，独立 PG 组和正常权限 Windows 组提供对应证据。ext4 的两项跳过为 Windows 可验证的文件占用测试。根级回归启动后新增的串联用例和故障补测单独执行；POSIX 与 PostgreSQL 最终批次早于新增六项 Windows 补测，生产代码哈希一致。运行命令、UTC 时间、退出码与 JUnit XML 在各证据目录。

| 验证 | 观测 |
| --- | --- |
| 并发 Draft 及独立上传 | 两个 PostgreSQL 后端 PID，对共享文件只生成一个正式 blob，各自持有附件引用。 |
| 并发审核与 key 争锁 | approve/reject 只产生一个终态；真实争锁依次退避，预算耗尽保留文件。 |
| DB 回滚与不明结果 | Draft 回滚保留可能发布的 blob 给 ORP；提交确认丢失保留 staging。审批 Hook 故障回滚业务事务；索引故障不撤销已审批。 |
| I/O 与 Windows 占用 | 底层 link/rename I/O 故障稳定返回 503，清临时与 staging。实际共享冲突耗尽短重试，回退为可重试状态。 |
| GC 和 staging 子进程退出 | 子进程在物理移动后和 staging 文件落盘后直接退出。真实磁盘状态由后续 worker 接管。 |
| PostgreSQL 客户端进程退出恢复 | 已观测普通客户端进程被终止后旧 PG backend 关闭，token 由 1 递增到 2；此证据与 pg_terminate_backend 用例分开。 |
| 一致性 | ORP 恢复可信隔离副本并保留引用，临时残留只报告。最终 PG 集成数据库为空引用、零 advisory lock。 |

[Windows 根级日志](evidence/v2-windows-full.log) · [Windows 根级 JUnit](evidence/v2-windows-full.xml) · [Windows 端到端日志](evidence/v2-windows-e2e.log) · [Windows 端到端 JUnit](evidence/v2-windows-e2e.xml) · [正常权限路径日志](evidence/v2-windows-normal-e4487e5f13b4/t01-windows.log) · [正常权限路径 JUnit](evidence/v2-windows-normal-e4487e5f13b4/t01-windows.xml)

[WSL 运行总日志](evidence/v2-final-posix-pg.QIRJGLxe/driver.log) · [ext4 JUnit](evidence/v2-final-posix-pg.QIRJGLxe/final-posix.xml) · [PG 回归 JUnit](evidence/v2-final-posix-pg.QIRJGLxe/final-pg-regression.xml) · [PG 端到端 JUnit](evidence/v2-final-posix-pg.QIRJGLxe/final-pg-e2e.xml) · [PG DB 终态](evidence/v2-final-posix-pg.QIRJGLxe/db-after-e2e.log)

[最终故障补测日志](evidence/v2-windows-fault-addendum.log) · [补测 JUnit](evidence/v2-windows-fault-addendum.xml)

## 最终审计整改复验

| 复验 | 通过 | 失败 | 错误 | 跳过 | 证据 |
| --- | ---: | ---: | ---: | ---: | --- |
| P1 与日志隔离 | 13 | 0 | 0 | 0 | [日志](evidence/remediation-windows-logging-isolation.log) · [JUnit](evidence/remediation-windows-logging-isolation.xml) |
| GC 与 ORP 专项 | 8 | 0 | 0 | 0 | [日志](evidence/remediation-windows-gc-trace.log) · [JUnit](evidence/remediation-windows-gc-trace.xml) |
| Windows 受管附件回归 | 288 | 0 | 0 | 20 | [日志](evidence/remediation-windows-special.log) · [JUnit](evidence/remediation-windows-special.xml) |
| Windows 受管 Sweep | 7 | 0 | 0 | 1 | [日志](evidence/remediation-windows-sweep-managed.log) · [JUnit](evidence/remediation-windows-sweep-managed.xml) |
| Backend + Knowledge Core 根级回归 | 1504 | 0 | 0 | 230 | [日志](evidence/remediation-windows-full-final.log) · [JUnit](evidence/remediation-windows-full-final.xml) |
| 普通权限 Windows Sweep | 8 | 0 | 0 | 0 | [日志](evidence/remediation-windows-normal-cbd2945355bf/staging-sweep.log) · [JUnit](evidence/remediation-windows-normal-cbd2945355bf/staging-sweep.xml) |
| 普通权限 Windows 真实启动路径 | 4 | 0 | 0 | 0 | [日志](evidence/remediation-windows-normal-cbd2945355bf/t01-windows.log) · [JUnit](evidence/remediation-windows-normal-cbd2945355bf/t01-windows.xml) |
| Ubuntu / PostgreSQL final-pg-api | 5 | 0 | 0 | 0 | [日志](evidence/remediation-posix-pg.3XoAQbf0/final-pg-api.log) · [JUnit](evidence/remediation-posix-pg.3XoAQbf0/final-pg-api.xml) |
| Ubuntu / PostgreSQL final-pg-draft | 1 | 0 | 0 | 0 | [日志](evidence/remediation-posix-pg.3XoAQbf0/final-pg-draft.log) · [JUnit](evidence/remediation-posix-pg.3XoAQbf0/final-pg-draft.xml) |
| Ubuntu / PostgreSQL final-pg-e2e | 1 | 0 | 0 | 0 | [日志](evidence/remediation-posix-pg.3XoAQbf0/final-pg-e2e.log) · [JUnit](evidence/remediation-posix-pg.3XoAQbf0/final-pg-e2e.xml) |
| Ubuntu / PostgreSQL final-pg-regression | 205 | 0 | 0 | 0 | [日志](evidence/remediation-posix-pg.3XoAQbf0/final-pg-regression.log) · [JUnit](evidence/remediation-posix-pg.3XoAQbf0/final-pg-regression.xml) |
| Ubuntu / PostgreSQL final-pg-review | 6 | 0 | 0 | 0 | [日志](evidence/remediation-posix-pg.3XoAQbf0/final-pg-review.log) · [JUnit](evidence/remediation-posix-pg.3XoAQbf0/final-pg-review.xml) |
| Ubuntu / PostgreSQL final-posix | 218 | 0 | 0 | 2 | [日志](evidence/remediation-posix-pg.3XoAQbf0/final-posix.log) · [JUnit](evidence/remediation-posix-pg.3XoAQbf0/final-posix.xml) |

[整改结果与未验证范围](V2-Final-Audit-Remediation-Report.md)
