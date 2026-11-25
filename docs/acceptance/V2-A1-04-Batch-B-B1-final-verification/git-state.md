# Git 状态

- 核验时间（UTC） 2026-11-23T11:17:04.932392+00:00
- HEAD `970c0d8ec05f0b8c68286839a56b14c74ea230c6`
- 分支 `fix/m0-admission-and-m5-regressions`
- 暂存区为空，`git diff --check` 返回 0。
- 本地 Round 3 的 74 项不变。冻结 14 项一致。迁移、锁文件、Core、前端及 MILESTONES 与 HEAD 一致。
- 状态快照早于最终交付 ZIP。工作树的既有 B1 改动继续保留。本轮新增项为验收报告、证据和 Linux 导入包。

```text
## fix/m0-admission-and-m5-regressions
 M backend/app/core/config.py
 M backend/app/db/session.py
 M backend/app/main.py
 M backend/app/services/repositories_v2.py
?? ExplainLab-Batch-B-GPT-Review.zip
?? backend/app/db/storage_lock.py
?? backend/app/services/attachment_storage.py
?? backend/tests/test_attachment_gc.py
?? backend/tests/test_attachment_pg.py
?? backend/tests/test_attachment_storage.py
?? backend/tests/test_attachment_windows.py
?? backend/tests/test_storage_lock_pg.py
?? backend/tests/test_storage_lock_pg_faults.py
?? backend/tests/test_storage_lock_sqlite.py
?? docs/acceptance/ExplainLab-B1-Remediation-Round3.zip
?? docs/acceptance/ExplainLab-B1-Round3-Linux-Input.zip
?? docs/acceptance/V2-A1-04-Batch-A/audit-round2/
?? docs/acceptance/V2-A1-04-Batch-A/final-remediation/final-review/
?? docs/acceptance/V2-A1-04-Batch-B-B1-final-verification/
?? docs/acceptance/V2-A1-04-Batch-B-B1-remediation-round3/
?? docs/audit/ExplainLab-B1-Final-Environment-Preflight.zip
?? docs/audit/ExplainLab-B1-Independent-Review-Round2.zip
?? docs/audit/ExplainLab-B1-Remediation-Round2.zip
?? docs/audit/V2-A1-03-final-stage-audit/
?? docs/audit/V2-A1-04-Batch-A-format-check-report.md
?? docs/audit/V2-A1-04-Batch-B-B1-independent-review-round2/
?? docs/audit/V2-A1-04-Batch-B-B1-remediation-round2/
?? docs/audit/V2-A1-04-Batch-B-B1/
?? docs/audit/V2-A1-04-Batch-B-final-environment-preflight/
?? docs/audit/V2-A1-04-Batch-B-final-review.zip
?? docs/audit/V2-A1-04-Batch-B-final-review/
?? docs/audit/V2-A1-04-Batch-B-freeze-review-package.zip
?? docs/audit/V2-A1-04-Batch-B-freeze-review-package/
?? docs/audit/V2-A1-04-Batch-B-freeze/
?? docs/audit/V2-A1-04-Batch-B-preflight/
?? docs/audit/V2-A1-04-Batch-B-remediation-review.zip
?? docs/audit/V2-A1-04-Batch-B-remediation/
?? docs/audit/V2-A1-04-R1-independent-review.md
?? docs/audit/V2-A1-04-technical-verification.md
?? docs/plans/A1-04/
?? docs/plans/V2-A1-04-Batch-B/
```
