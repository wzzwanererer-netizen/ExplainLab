# ExplainLab V2 · B5 GC 与 ORP

B5 实现质量门已完成。最终验收仍由独立审计裁决。

| 验证项 | 复验结果 |
| --- | --- |
| 任务认领与 fencing | 认领在独立短事务结束后取 key 锁。SQLite 双 worker 只有一个认领成功；任务 token 漂移阻止物理变更。PG 仓储与 advisory lock 定向回归 27 通过。 |
| 共享引用与代次 | 最后引用消失才入队，隔离期内不再增 attempts。到期只清自己槽，重发的正式代次由后继任务接手。真实 PostgreSQL 装配通过并发移除共享引用及孤儿扫描。 |
| 崩溃与恢复 | GC 子进程真实退出，隔离成功但任务未记时，接管者验证并重新计时。staging 创建进程真实退出后遗留的不完整目录由 ORP 隔离。 |
| Windows 占用 | 独占共享句柄让删除进入约 5 秒的实际退避，再将任务标为可重试，文件仍可读。 |
| 预算与人工状态 | 实际争锁 8 次，验证有效退避、终态和只经显式操作恢复到 pending。损坏隔离保留给人工。 |
| ORP | 正式孤儿满 24 小时后入队；.tmp 只报告；缺失的正式副本从可信隔离恢复；待审 staging 保留与移回；畸形 pending envelope 使 staging 扫描 fail closed。 |
| 生命周期 | 后台 startup 扫描与 300 秒周期，关闭时先停止维护线程与 PG 专用连接，再处理数据库和进程锁。 |

Windows 最终 B5 定向与历史回归 54 通过、7 跳过。Ubuntu ext4 B5 13 通过、1 跳过（Windows 专属）；真实 PostgreSQL 18.6 B5 路径 1 通过。原始运行保留了首轮 Pydantic GcTask 复制错误与修复后的重跑。时间边界通过修改真实文件 mtime 和独立测试库的隔离时间复验，测试未等待实际经过 24 小时。

[Windows 日志](evidence/b5-windows-final.log) · [Windows JUnit](evidence/b5-windows-final.xml) · [Ubuntu ext4 日志](evidence/b5-posix-pg.0WCzRsAo/b5-posix-sqlite.log) · [PostgreSQL 日志](evidence/b5-posix-pg.0WCzRsAo/b5-postgresql.log) · [PostgreSQL 27 项回归](evidence/b5-posix-pg.0WCzRsAo/b5-postgresql-lock-regression.log)
