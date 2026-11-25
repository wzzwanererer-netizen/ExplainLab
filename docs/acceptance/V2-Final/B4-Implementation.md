# ExplainLab V2 · B4 附件审核决议

B3-T02 实现质量门已完成。B4 实现质量门已完成，正式裁决由独立审计负责。

| 边界 | 实现及核对 |
| --- | --- |
| 审批物理发布 | S0 只读验证 envelope 和 manifest。按 review、来源、identity、staging、storage 锁序执行。合法 PREPARED MATERIALIZE 恢复事务先结束。关闭锁内只读探查会话，再复制、校验并发布 blob。 |
| 审批业务事务 | 新会话重新验证审核单、payload、目标及归档。Core 先应用，Hook 在同一会话补齐来源、标签、链接与附件引用，末次 fencing 后只提交一次。失败回滚后释放存储锁。 |
| 索引与清理 | 业务提交并释放存储锁后，在 staging guard 内尽力清理，再退出所有业务锁。索引使用独立事务，失败不会撤销已提交的审核。 |
| 拒绝和竞争 | 两条决议路由共用 review 锁。拒绝成功提交才清可信 staging，损坏的 envelope 仍可拒绝。Windows 真实占用时终态成功、保留文件交 ORP。 |
| 历史兼容 | 保留既有 ReviewResolve 请求形状，Core ReviewService、ImportReport、迁移与依赖保持冻结基线。无附件审批仍使用既有索引流程。 |

Windows 初次审核专项及 Batch A 导入导出回归 42 通过、1 跳过。当前 Windows 审核专项 12 通过、1 跳过，包含 Windows 独占句柄回归。Ubuntu ext4 审核专项 11 通过、1 跳过，跳过项仅适用于 Windows。真实 PostgreSQL 18.6 审核集成 1 项通过，含归档拒绝、拒绝清理、S1 漂移、Hook 回滚重试及批准，DB 结果 2 条附件引用、0 个 advisory lock。16 个 overlay 哈希全部匹配。Windows 根级回归 1,462 通过、223 跳过、0 失败；全量启动后新增的 Windows 文件句柄用例在最终专项中单独通过。源码 Ruff 与 Git diff --check 通过。

[审核专项](evidence/b4-windows-review-current.log) · [审核 JUnit](evidence/b4-windows-review-current.xml) · [真实占用](evidence/b4-windows-handle.log) · [Batch A 定向回归](evidence/b4-windows-targeted.log) · [根级回归](evidence/b4-windows-full.log) · [阶段源码 SHA-256](evidence/b4-source.sha256) · [复验脚本](evidence/run-b4-posix-pg.sh)

[Ubuntu ext4 原始日志](evidence/b4-posix-pg.S8g3eVxW/b4-posix-sqlite.log) · [ext4 JUnit](evidence/b4-posix-pg.S8g3eVxW/b4-posix-sqlite.xml) · [PostgreSQL 原始日志](evidence/b4-posix-pg.S8g3eVxW/b4-postgresql.log) · [PostgreSQL JUnit](evidence/b4-posix-pg.S8g3eVxW/b4-postgresql.xml) · [数据库证据](evidence/b4-posix-pg.S8g3eVxW/db-after-http.log)
