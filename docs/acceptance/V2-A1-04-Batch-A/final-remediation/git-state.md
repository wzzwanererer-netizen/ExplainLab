# Git 状态（只读取证）

- 取证时间：2026-11-22 11:23（亚洲/上海）
- 原始输出：`evidence/git-state.txt`
- HEAD：`784b1248065424e07273b272d6016cc121bc606c`
- 分支：`fix/m0-admission-and-m5-regressions`
- 最近提交：
  - `784b124` test: A1-03 最终审计补充 — phantom 非碰撞新增 ID 集合守护验证
  - `9634ad1` fix: 专项审计修复 — 重建步8c 逐行复核补齐 no-op 行窗口②并发保护
  - `b6c7e15` fix: 专项审计修复 — 重建步7 P2 乐观前置扩至门禁C同口径6字段

## 1. 本轮 Git 操作

**无。** 未执行 `git commit`、`push`、`add`、`reset`、`clean`、`stash`、`checkout`、`merge`、`rebase`；未修改 M0 初始提交；未重写历史；`git stash list` 为空。

本轮只创建/修改工作树文件与 `docs/acceptance/.../final-remediation/` 证据包。

## 2. 本轮实际修改（工作树相对本轮开始）

| 文件 | 状态 | 归属 |
| --- | --- | --- |
| `backend/app/services/source_identity.py` | untracked，已修改 | 本轮（P1-01/P1-02/P2-06） |
| `backend/app/services/source_instance_id.py` | untracked，已修改 | 本轮（P2-03） |
| `backend/app/services/markdown.py` | untracked，已修改 | 本轮（P1-02） |
| `backend/app/services/import_review_hook.py` | untracked，已修改 | 本轮（P1-02） |
| `backend/app/api/routes/governance.py` | tracked，已修改 | 本轮仅 +11/−3 行（P1-02）；其余 +153/−26 行为 Batch A 早期工作 |
| `backend/tests/test_markdown_batch_a_identity.py` | untracked，已修改 | 本轮新增 9 项测试 |
| `backend/tests/test_markdown_batch_a_import_conflict.py` | untracked，新文件 | 本轮（7 项测试） |
| `backend/tests/test_batch_a_fault_injection.py` | untracked，新文件 | 本轮（23 项测试） |
| `docs/acceptance/V2-A1-04-Batch-A/final-remediation/` | untracked，新目录 | 本交付包 |

`backend/app/services/file_write.py`、`backend/tests/test_batch_a_file_write.py` 最终与第二轮审计快照逐字节一致（净修改为零）。

## 3. 工作树中非本轮产生的改动（Batch A 既有、保持原样）

- 已跟踪、已修改（mtime 00:36–01:03，早于本轮 10:00 起点）：
  `backend/app/api/schemas.py`、`backend/app/core/config.py`、`backend/app/db/session.py`、`backend/app/dependencies.py`、`backend/app/main.py`、`backend/tests/conftest.py`、`backend/tests/test_health.py`。
- 未跟踪的 Batch A 实现/测试/计划/审计文件：
  `backend/app/api/routes/import_export.py`、`backend/app/db/process_lock.py`、`backend/app/services/file_write.py`、`import_coordinator.py`、`journal_canonical.py`、`markdown_item_repository.py`、`repositories_v2.py`、`backend/tests/test_batch_a_canonical.py`、`test_batch_a_file_write.py`、`test_batch_a_process_and_identity.py`、`test_markdown_batch_a_import_export.py`、`knowledge-core/src/knowledge_core/markdown/{import_report.py,service.py}`、`knowledge-core/tests/test_markdown_service.py`、`docs/plans/*`、`docs/audit/*`、`docs/acceptance/V2-A1-04-Batch-A/*`。
- 本轮未修改 `knowledge-core/`、`backend/alembic/`、`frontend/`（`find -newermt "2026-11-22 10:00"` 输出见 `evidence/scope-mtime.txt`）。

## 4. 未提交原因与停止条件

按用户指令：本轮禁止任何 Git 写操作，整改完成即停止，等待 ChatGPT 独立审计。工作树保持可复核状态；审计通过前不提交、不推送、不进入 Batch B。