# 01 · Git 状态与范围分类

- 取证时间：2026-11-22 17:42（亚洲/上海）
- 原始输出：`git-state.txt`、`tracked-files.txt`、`untracked-files.txt`、`file-metadata.txt`
- 基线：HEAD `784b1248065424e07273b272d6016cc121bc606c`，分支 `fix/m0-admission-and-m5-regressions`
- 本轮（审计材料准备）为**只读**：没有修改业务代码、测试、设计文档、数据库、迁移、依赖或 lockfile；没有执行任何 Git 写命令。
- 本目录 `final-review/` 是唯一新增内容；此前 `final-remediation/` 的既有证据原样保留、未删除、未重新生成。

## 1. HEAD 与索引

| 项 | 值 |
| --- | --- |
| HEAD | `784b1248065424e07273b272d6016cc121bc606c` |
| 分支 | `fix/m0-admission-and-m5-regressions` |
| 与任务给定基线 | 一致，未变化 |
| 暂存区（`git diff --cached --stat`） | 空（无 staged 内容） |
| `git stash list` | 空 |

## 2. tracked 修改（相对 HEAD，共 8 个，全部为 M）

| 文件 | 归属 | 证据 |
| --- | --- | --- |
| `backend/app/api/routes/governance.py` | **最终整改轮**（仅 P1-02 部分） | 本轮 diff +11/−3；相对 HEAD 总 +164/−29，其余为 Batch A 早期 |
| `backend/app/api/schemas.py` | Batch A 早期 | mtime 2026-11-22 01:03 |
| `backend/app/core/config.py` | Batch A 早期 | mtime 00:36 |
| `backend/app/db/session.py` | Batch A 早期 | mtime 00:40 |
| `backend/app/dependencies.py` | Batch A 早期 | mtime 00:46 |
| `backend/app/main.py` | Batch A 早期 | mtime 00:48 |
| `backend/tests/conftest.py` | Batch A 早期 | mtime 00:46 |
| `backend/tests/test_health.py` | Batch A 早期 | mtime 00:52 |

完整 `git diff --stat` 与 `--porcelain=v2` 见 `git-state.txt`；Hash 见 `tracked-files.txt`。

## 3. untracked

`git ls-files --others --exclude-standard` 在 17:42 捕获到 **176** 条；其中 3 条是本目录当时已生成的 `git-state.txt`/`tracked-files.txt`/`untracked-files.txt`，**历史（本轮前）untracked 为 173**。分类（不含本目录）：

| 目录 | 数量 | 内容 |
| --- | --- | --- |
| `docs/acceptance/` | 110 | 历史验收/审计/证据包（含 `final-remediation/`） |
| `docs/audit/` | 32 | A1-03/A1-04 审计文档与证据 |
| `docs/plans/` | 10 | A1-04 设计/决策/风险/验收矩阵 |
| `backend/app/` | 11 | Batch A 新增路由/服务 |
| `backend/tests/` | 7 | Batch A 测试 |
| `knowledge-core/src/` | 2 | Markdown 服务/导入报告 |
| `knowledge-core/tests/` | 1 | Markdown 服务测试 |
| **合计** | **173** | |

> 当前（材料完成后）本目录有 24 个 untracked 文件，仓库合计 **197**。完整捕获清单见 `untracked-files.txt`（该文件自身也被列入，故其计数 176 含本目录 3 个文件）。

## 4. Batch A 相关文件清单（代码层）

生产代码（untracked）：

- `backend/app/api/routes/import_export.py`
- `backend/app/db/process_lock.py`
- `backend/app/services/file_write.py`
- `backend/app/services/import_coordinator.py`
- `backend/app/services/import_review_hook.py`
- `backend/app/services/journal_canonical.py`
- `backend/app/services/markdown.py`
- `backend/app/services/markdown_item_repository.py`
- `backend/app/services/repositories_v2.py`
- `backend/app/services/source_identity.py`
- `backend/app/services/source_instance_id.py`

测试（untracked）：

- `backend/tests/test_batch_a_canonical.py`
- `backend/tests/test_batch_a_fault_injection.py`
- `backend/tests/test_batch_a_file_write.py`
- `backend/tests/test_batch_a_process_and_identity.py`
- `backend/tests/test_markdown_batch_a_identity.py`
- `backend/tests/test_markdown_batch_a_import_conflict.py`
- `backend/tests/test_markdown_batch_a_import_export.py`

知识核心（untracked）：

- `knowledge-core/src/knowledge_core/markdown/import_report.py`
- `knowledge-core/src/knowledge_core/markdown/service.py`
- `knowledge-core/tests/test_markdown_service.py`

每个文件的 SHA-256 见 `untracked-files.txt` 的 “Batch A production/test/core files” 段。

## 5. “本轮”与“此前 Batch A”的划分

| 范围 | 文件 | 说明 |
| --- | --- | --- |
| Batch A 早期（本轮前） | 上表 7 个 tracked 文件 + 全部 untracked 中的 Batch A 基础实现/计划/审计材料 | mtime 均 ≤ 2026-11-22 02:00（tracked 为 00:36–01:03）；本轮未触碰 |
| 最终整改轮（本轮前一次） | `source_identity.py`、`source_instance_id.py`、`markdown.py`、`import_review_hook.py`、`governance.py` + 3 个测试文件 | mtime 11:01–11:23；本轮未再修改，Hash 与 `final-remediation/` 交付一致 |
| 本次审计材料轮 | 仅 `final-review/` 新文档 | 只读准备，无代码/测试/设计文档改动 |

Hash 对照（`file-metadata.txt`）：

- `source_identity.py` `9c017593…f895a`
- `source_instance_id.py` `f41955ce…1e22`
- `markdown.py` `db1255ba…e7ac`
- `import_review_hook.py` `cc2df045…0c16`
- `governance.py` `15372499…c722`
- `test_markdown_batch_a_identity.py` `383d749e…3264`
- `test_markdown_batch_a_import_conflict.py` `e35518cc…c0ce`
- `test_batch_a_fault_injection.py` `a0b7ccb6…113d`

## 6. 与“本轮开始时基线”的差异

- HEAD、分支、暂存区均未变化。
- 工作树业务文件 Hash 与最终整改交付一致（见上）。
- 新增：`docs/acceptance/V2-A1-04-Batch-A/final-remediation/final-review/`（本目录）。
- 未删除、未覆盖、未重生成 `final-remediation/` 既有 41 个文件（含 40 个受既有 SUMS 覆盖的交付文件）。