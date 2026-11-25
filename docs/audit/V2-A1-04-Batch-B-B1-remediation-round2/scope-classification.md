# 变更范围归类

| 分类 | 路径 |
|---|---|
| 本轮生产代码 | backend/app/core/config.py、main.py、db/session.py、db/storage_lock.py、services/attachment_storage.py、services/repositories_v2.py |
| 本轮修改既有 B1 未跟踪测试 | backend/tests/ 下 test_attachment_gc.py、test_attachment_pg.py、test_attachment_storage.py、test_attachment_windows.py、test_storage_lock_sqlite.py、test_storage_lock_pg.py |
| 本轮新增测试 | backend/tests/test_storage_lock_pg_faults.py |
| 本轮交付 | docs/audit/V2-A1-04-Batch-B-B1-remediation-round2/ |
| 其他未跟踪文件 | 早期 Batch A/B 审计材料、冻结设计与交付 ZIP 等，保留原位 |
| Batch A 与冻结边界 | Core、实际迁移、schema、A1-02/A1-03、身份 Journal、依赖、前端和 MILESTONES.md 均不在变更清单 |

Git diff 只能看到四个已跟踪修改。两个 B1 实现及七个测试仍未跟踪，复审必须纳入。原 B1 哈希文件是上一轮快照，整改后其中 11 个源码/测试项预期变更。原报告和原始日志保留，冻结设计以独立 Freeze SHA-256 核验。
