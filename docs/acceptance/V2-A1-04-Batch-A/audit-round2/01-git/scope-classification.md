# 文件范围区分（本轮整改 / 既有遗留）

基线：HEAD `784b1248065424e07273b272d6016cc121bc606c`，分支
`fix/m0-admission-and-m5-regressions`。无暂存文件，无新提交，无推送。

## A. 本轮 P1/P2 实际修改或新增的文件（5 个）

| 文件 | Git 状态 | 本轮动作 | 说明 |
| --- | --- | --- | --- |
| `backend/app/services/source_identity.py` | untracked（Batch A 文件） | 修改 | P1 helper + classify 早退；P2 current/archive 写入 |
| `backend/app/services/source_instance_id.py` | untracked（Batch A 文件） | 修改 | P2 创建/fallback/替换写入 + fallback 半成品清理 |
| `backend/app/services/file_write.py` | untracked（本轮新增） | 新增 | `write_all` 完整写入封装 |
| `backend/tests/test_markdown_batch_a_identity.py` | untracked（Batch A 文件） | 修改 | 新增 10 项并存冲突测试与辅助断言 |
| `backend/tests/test_batch_a_file_write.py` | untracked（本轮新增） | 新增 | 13 项短写/故障注入测试 |

这 5 个文件的 mtime 集中在 2026-11-22 02:00–02:07，见 `file-mtimes.txt`。
其中 `source_identity.py` / `source_instance_id.py` 在 Git 中从未提交，因此 `git diff`
看不到它们；其整改差异见 `../03-diff/`。

## B. 本轮交接新增的审计包（仅文档/副本/原始输出）

- `docs/acceptance/V2-A1-04-Batch-A/audit-round2/` 整个目录
  - `README.md`
  - `01-git/`：Git 状态、diff、untracked、mtime、本文件
  - `02-code/`：5 个源码逐字节副本、`README.md`、`file-metadata.txt`、`cmp-check.txt`
  - `03-diff/`：`remediation.diff`、5 个逐文件 diff、`before/` 重建版本、
    `README.md`、`reconstruction-log.txt`
  - `04-journal/`：`journal-code-extract.txt`、`classify-code-extract.txt`、
    `recovery-entrypoints.txt`、`README.md`、`P1-conflict-and-recovery-audit.md`、
    `P2-write-and-publish-audit.md`
  - `05-tests/`：本轮重新运行的原始输出与 `README.md`
  - `06-unverified/`：`known-gaps.md`、`postgresql-environment.txt`
  - `SHA-256SUMS`、`SHA-256SUMS.self-check.md`
- 不修改任何代码、测试、设计文档、`MILESTONES.md`。

## C. 既有 Batch A 代码/测试（untracked，本轮未改）

源码：

- `backend/app/api/routes/import_export.py`
- `backend/app/db/process_lock.py`
- `backend/app/services/import_coordinator.py`
- `backend/app/services/import_review_hook.py`
- `backend/app/services/journal_canonical.py`
- `backend/app/services/markdown.py`
- `backend/app/services/markdown_item_repository.py`
- `backend/app/services/repositories_v2.py`
- `knowledge-core/src/knowledge_core/markdown/import_report.py`
- `knowledge-core/src/knowledge_core/markdown/service.py`

测试：

- `backend/tests/test_batch_a_canonical.py`
- `backend/tests/test_batch_a_process_and_identity.py`
- `backend/tests/test_markdown_batch_a_import_export.py`
- `knowledge-core/tests/test_markdown_service.py`

这些文件的 mtime 早于本轮整改（01:16 及以前），本轮未编辑。它们仍作为 Batch A 交付的一部分
参与回归，但不属于本轮 P1/P2 diff。

## D. 已跟踪但未提交的修改（8 个，属更早 Batch A 工作）

`git diff` 显示以下工作树修改，均非本轮 P1/P2 产生，本轮未编辑：

- `backend/app/api/routes/governance.py`
- `backend/app/api/schemas.py`
- `backend/app/core/config.py`
- `backend/app/db/session.py`
- `backend/app/dependencies.py`
- `backend/app/main.py`
- `backend/tests/conftest.py`
- `backend/tests/test_health.py`

完整内容见 `git-diff.patch`（555 行）。这些修改与 Batch A 的启动装配、导入导出、会话/配置有关，
已在既有 Batch A 验收范围内，本轮不重复宣称其正确性。

## E. 历史文档（untracked，本轮未改）

- `docs/acceptance/V2-A1-04-Batch-A/Batch-A-*.md` 与 `evidence/`：Batch A 初次交付材料。
- `docs/acceptance/V2-A1-04-Batch-A/remediation/`：上一阶段整改报告与证据（历史记录）。
- `docs/audit/V2-A1-03-final-stage-audit/`、`docs/audit/V2-A1-04-R1-independent-review.md`、
  `docs/audit/V2-A1-04-technical-verification.md`：既有审计/技术核验材料。
- `docs/plans/A1-04/` 与 `docs/plans/V2-A1-04-*.md`：冻结计划、开放决策、风险登记、合并报告。
- `docs/plans/A1-04/R1.1-amendment/ExplainLab-V2-A1-04-Architecture-R1.1-amendment.zip`。

本轮只新增 `audit-round2/`，未修改上述文档。

## F. 历史测试结果与本轮新结果

- `remediation/evidence/` 中的测试输出是**上一阶段**运行的，本轮未覆盖、未冒充。
- 本包 `05-tests/` 全部为 2026-11-22 03:56–04:00 重新运行，文件头含命令与时间，文件尾含退出码。
- 本包只使用本轮新输出做结论；历史文件仅作追溯。

## G. Git 边界确认

- `git diff --cached` 为空（`git-diff-cached.patch` 0 字节）。
- 无 `git add`、无 commit、无 push。
- 未修改 M0 初始提交，未重写历史。
- 未新增迁移/表/列/索引/依赖。
- 未修改 `MILESTONES.md`、设计文档、A1-02/A1-03/V1 契约。

## H. `git diff HEAD` 无法观察的文件（为何需要 `03-diff/`）

`git diff` / `git diff HEAD` 只显示**已跟踪**文件的修改。以下与本轮整改直接相关的文件
在 Git 中仍为 untracked，因此不会出现在 `git-diff.patch` 中：

- `backend/app/services/source_identity.py`
- `backend/app/services/source_instance_id.py`
- `backend/app/services/file_write.py`（本轮新增）
- `backend/tests/test_markdown_batch_a_identity.py`
- `backend/tests/test_batch_a_file_write.py`（本轮新增）

因此 **`git diff HEAD` 不能作为完整整改差异**。`03-diff/` 中的“整改前版本”不是 Git 历史快照，
而是根据本轮编辑记录逐条反向应用得到，并在 `03-diff/README.md` 与
`reconstruction-log.txt` 中记录每一步反向操作、出现次数校验、应用前后 SHA-256、
正向重放验证与编译检查。

除上述 5 个源码/测试文件外，`audit-round2/` 内的审计材料本身也全部是 untracked；
它们只用于交接，不计入整改代码差异。