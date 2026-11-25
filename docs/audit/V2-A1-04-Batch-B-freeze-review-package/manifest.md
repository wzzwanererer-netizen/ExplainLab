# 文件清单与完整性

- 文件数量：**61**。未压缩总大小：**932209 字节**。
- SHA-256 清单覆盖除自身外的所有文件（60 项）。清单自身也参加 ZIP 内源文件逐项哈希比对。
- 原整改 SHA-256 清单中的 15 条当前摘要及原审计摘要已对照当前文件。
- 原件保留字节，源码节选附原文件、提交、Git blob 与行号。设计或历史版本来源见各入口。
- Git 保持 HEAD、索引和包外工作区不变，新增本材料目录与 ZIP。运行环境证据和 39 项原清单的缺失见 README。

- `acceptance-and-risks`：5 个文件。
- `design-documents`：16 个文件。
- `original-audit`：5 个文件。
- `remediation`：6 个文件。
- `source-evidence`：25 个文件。
- `根目录`：4 个文件。

| 包内路径 | 字节 |
|---|---:|
| `README.md` | 1975 |
| `SHA-256SUMS` | 7763 |
| `acceptance-and-risks/coverage-and-residuals.md` | 2717 |
| `acceptance-and-risks/docs/plans/V2-A1-04-Batch-B/acceptance-plan.md` | 26603 |
| `acceptance-and-risks/docs/plans/V2-A1-04-Batch-B/api-contracts.md` | 18293 |
| `acceptance-and-risks/docs/plans/V2-A1-04-Batch-B/risk-register.md` | 17309 |
| `acceptance-and-risks/stable-error-code-register.md` | 3492 |
| `design-documents/batch-a-r1.3/docs/plans/README-A1-04-R1.3.md` | 6327 |
| `design-documents/batch-a-r1.3/docs/plans/V2-A1-04-R1.3-merge-report.md` | 20738 |
| `design-documents/batch-a-r1.3/docs/plans/V2-A1-04-acceptance-matrix.md` | 82063 |
| `design-documents/batch-a-r1.3/docs/plans/V2-A1-04-implementation-plan.md` | 181695 |
| `design-documents/batch-a-r1.3/docs/plans/V2-A1-04-open-decisions.md` | 60340 |
| `design-documents/batch-a-r1.3/docs/plans/V2-A1-04-risk-register.md` | 46080 |
| `design-documents/docs/plans/V2-A1-04-Batch-B/README.md` | 15789 |
| `design-documents/docs/plans/V2-A1-04-Batch-B/acceptance-plan.md` | 26603 |
| `design-documents/docs/plans/V2-A1-04-Batch-B/active-review-integration.md` | 14836 |
| `design-documents/docs/plans/V2-A1-04-Batch-B/api-contracts.md` | 18293 |
| `design-documents/docs/plans/V2-A1-04-Batch-B/architecture.md` | 12446 |
| `design-documents/docs/plans/V2-A1-04-Batch-B/attachment-lifecycle.md` | 20760 |
| `design-documents/docs/plans/V2-A1-04-Batch-B/gc-and-orphan-recovery.md` | 21757 |
| `design-documents/docs/plans/V2-A1-04-Batch-B/implementation-roadmap.md` | 16928 |
| `design-documents/docs/plans/V2-A1-04-Batch-B/risk-register.md` | 17309 |
| `design-documents/docs/plans/V2-A1-04-Batch-B/storage-and-lock-contract.md` | 19269 |
| `git-state.md` | 3165 |
| `manifest.md` | 5472 |
| `original-audit/docs/audit/V2-A1-04-Batch-B-final-review/README.md` | 2943 |
| `original-audit/docs/audit/V2-A1-04-Batch-B-final-review/acceptance-gaps.md` | 6420 |
| `original-audit/docs/audit/V2-A1-04-Batch-B-final-review/architecture-findings.md` | 18948 |
| `original-audit/docs/audit/V2-A1-04-Batch-B-final-review/freeze-recommendation.md` | 1853 |
| `original-audit/docs/audit/V2-A1-04-Batch-B-final-review/implementation-readiness.md` | 4718 |
| `remediation/docs/audit/V2-A1-04-Batch-B-remediation/README.md` | 992 |
| `remediation/docs/audit/V2-A1-04-Batch-B-remediation/SHA256SUMS.txt` | 4126 |
| `remediation/docs/audit/V2-A1-04-Batch-B-remediation/cross-document-audit.md` | 2180 |
| `remediation/docs/audit/V2-A1-04-Batch-B-remediation/remaining-risks.md` | 1402 |
| `remediation/docs/audit/V2-A1-04-Batch-B-remediation/remediation-report.md` | 5799 |
| `remediation/docs/audit/V2-A1-04-Batch-B-remediation/updated-acceptance-mapping.md` | 2882 |
| `source-evidence/01-postgresql-advisory-lock.md` | 10514 |
| `source-evidence/02-sqlite-review-sequence.md` | 9174 |
| `source-evidence/03-staging-lock-boundaries.md` | 16306 |
| `source-evidence/04-windows-roots-and-toctou.md` | 11609 |
| `source-evidence/README.md` | 3803 |
| `source-evidence/batch-a/backend/alembic/versions/0006_v2_markdown_kb.py` | 12090 |
| `source-evidence/batch-a/backend/app/api/routes/governance.py.lines.txt` | 11036 |
| `source-evidence/batch-a/backend/app/api/routes/import_export.py.lines.txt` | 8810 |
| `source-evidence/batch-a/backend/app/core/config.py.lines.txt` | 2075 |
| `source-evidence/batch-a/backend/app/db/process_lock.py` | 5140 |
| `source-evidence/batch-a/backend/app/db/session.py.lines.txt` | 4004 |
| `source-evidence/batch-a/backend/app/main.py.lines.txt` | 3491 |
| `source-evidence/batch-a/backend/app/models.py.lines.txt` | 7973 |
| `source-evidence/batch-a/backend/app/services/file_write.py` | 984 |
| `source-evidence/batch-a/backend/app/services/governance.py.lines.txt` | 2164 |
| `source-evidence/batch-a/backend/app/services/import_coordinator.py` | 2388 |
| `source-evidence/batch-a/backend/app/services/import_review_hook.py` | 7959 |
| `source-evidence/batch-a/backend/app/services/journal_canonical.py` | 4735 |
| `source-evidence/batch-a/backend/app/services/markdown.py.lines.txt` | 26147 |
| `source-evidence/batch-a/backend/app/services/retrieval.py.lines.txt` | 1503 |
| `source-evidence/batch-a/backend/app/services/source_identity.py.lines.txt` | 33811 |
| `source-evidence/batch-a/backend/app/services/source_instance_id.py` | 6488 |
| `source-evidence/batch-a/knowledge-core/src/knowledge_core/markdown/import_report.py.lines.txt` | 9559 |
| `source-evidence/batch-a/knowledge-core/src/knowledge_core/ports.py.lines.txt` | 4830 |
| `source-evidence/batch-a/knowledge-core/src/knowledge_core/review/__init__.py.lines.txt` | 5331 |
