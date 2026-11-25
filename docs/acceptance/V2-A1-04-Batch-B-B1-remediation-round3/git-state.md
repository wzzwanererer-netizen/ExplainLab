# Git 状态与交付边界

- 分支 `fix/m0-admission-and-m5-regressions`
- HEAD `970c0d8ec05f0b8c68286839a56b14c74ea230c6`
- 暂存区为空，`git diff --check` 退出码 0。
- Round 2 包中有 13 个 B1 源码和测试文件，本轮相对它修改 7 个。当前 tracked diff 还含原 B1 已有改动。
- 冻结 SHA-256 清单 14/14 一致，覆盖十份设计及四份冻结记录。Core、前端、实际迁移、依赖文件和 MILESTONES 与 HEAD 一致。
- 按 AST 比较原有 132 个顶层 B1 测试函数及装饰器，全部匹配，另增加 12 个顶层测试函数。初始工作树缺少 Round 2 的 Windows busy 到期断言，已从提交包恢复其原断言和配套的到期检查。

## Round 3 代码差异

- `backend/app/core/config.py`
- `backend/app/db/session.py`
- `backend/app/db/storage_lock.py`
- `backend/app/services/attachment_storage.py`
- `backend/tests/test_attachment_storage.py`
- `backend/tests/test_storage_lock_pg_faults.py`
- `backend/tests/test_storage_lock_sqlite.py`

逐行差异见 [round2-to-round3.diff.txt](evidence/round2-to-round3.diff.txt)。

## 工作树快照

以下快照取于打包前。

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
?? docs/acceptance/V2-A1-04-Batch-A/audit-round2/
?? docs/acceptance/V2-A1-04-Batch-A/final-remediation/final-review/
?? docs/acceptance/V2-A1-04-Batch-B-B1-remediation-round3/
?? docs/audit/ExplainLab-B1-Independent-Review-Round2.zip
?? docs/audit/ExplainLab-B1-Remediation-Round2.zip
?? docs/audit/V2-A1-03-final-stage-audit/
?? docs/audit/V2-A1-04-Batch-A-format-check-report.md
?? docs/audit/V2-A1-04-Batch-B-B1-independent-review-round2/
?? docs/audit/V2-A1-04-Batch-B-B1-remediation-round2/
?? docs/audit/V2-A1-04-Batch-B-B1/
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
