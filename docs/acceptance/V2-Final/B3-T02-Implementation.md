# ExplainLab V2 · B3-T02 Draft 附件导入

B3-T02 实现质量门已完成。冻结设计沿用 Batch B 已批准版本。

| 项目 | 实现及验证 |
| --- | --- |
| Draft 新建与更新 | ZIP 绑定单文档。持 staging guard 创建目录，关闭旧读会话，按 B1 契约取存储多键锁、校验 manifest 和发布文件。打开新的业务会话，锁定既有条目，复核来源、目标及状态。 |
| 数据库提交边界 | 文档、标签、来源、链接与正式附件引用同事务。业务会话执行末次 fencing 后提交，失败先回滚再释放存储锁。 |
| 去重 | 同 Hash 在正式存储复用，同 item 保持一个引用，跨 item 各自保留引用。重放按已应用 Hash 守卫校验，缺 blob 返回稳定 503，Draft 缺引用返回稳定 400。 |
| staging | Draft 成功后清理；明确提交前失败清理；提交结果不明确保留给 ORP。Active pending 继续保留 staging。已发布的孤儿 blob 交由后续冻结的 ORP 流程。 |
| Windows / SQLite Draft 专项 | PASS，最终 Draft 专项 7 通过、1 跳过。跳过项为真实 PostgreSQL HTTP。相关 Windows 回归 383 通过、12 跳过，跳过项为 PostgreSQL 或平台能力。 |
| Ubuntu ext4 / PostgreSQL | Ubuntu ext4 SQLite 专项 63 通过，PostgreSQL 18.6 并发 HTTP 1 通过。两个条目共用同一物理 blob，持久化 2 条附件引用，剩余 advisory lock 为 0。 |
| 后续阶段 | IMP-19 的本阶段实机矩阵已有 Windows、Ubuntu ext4 和 PostgreSQL 证据。正式裁决由独立审计负责。 |

首跑发现 SQLite 的条目保护语句触发 ORM 的 updated_at 自动更新，造成状态快照误判。修复后保护语句保持 updated_at 不变。创建响应断言按既有 HTTP 契约核对 201。

[首跑原始记录](evidence/b3-t02-windows.log) · [Draft 专项](evidence/b3-t02-windows-draft-final.log) · [Draft JUnit](evidence/b3-t02-windows-draft-final.xml) · [相关历史回归](evidence/b3-t02-windows-final.log) · [回归 JUnit](evidence/b3-t02-windows-final.xml) · [阶段源码 SHA-256](evidence/b3-t02-source.sha256) · [Ubuntu ext4 和 PostgreSQL 运行脚本](evidence/run-b3-t02-posix-pg.sh)

[Ubuntu ext4 日志及退出码](evidence/b3-t02-posix-pg.Dy0WTNFu/b3-posix-sqlite.log) · [ext4 JUnit](evidence/b3-t02-posix-pg.Dy0WTNFu/b3-posix-sqlite.xml) · [PostgreSQL 日志](evidence/b3-t02-posix-pg.Dy0WTNFu/b3-postgresql.log) · [PostgreSQL JUnit](evidence/b3-t02-posix-pg.Dy0WTNFu/b3-postgresql.xml) · [DB 验证](evidence/b3-t02-posix-pg.Dy0WTNFu/db-after-http.log) · [overlay SHA-256](evidence/b3-t02-posix-pg.Dy0WTNFu/source-overlays.sha256)
