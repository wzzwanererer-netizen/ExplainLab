# B2 Git 变更摘要

**HEAD：`970c0d8`（Batch A 基线）；分支：`fix/m0-admission-and-m5-regressions`。未提交、未推送、未执行破坏性 Git 操作。**

工作树同时包含 B1-final 的未提交修复与 B2 本轮变更。二者需分开审核，不能把 B1-final 未提交差异算作 B2 新增功能。

## B2 新增

| 文件 | 类型 |
|---|---|
| `backend/app/services/attachments.py` | B2-T02 附件服务 |
| `backend/app/api/routes/attachments.py` | B2-T02 四路由 |
| `backend/tests/test_attachment_api.py` | B2-T02 真实 SQLite + tmp 文件系统测试 |
| `backend/app/services/attachment_validation.py` | B2-T01（本轮之前已完成，仍未提交） |
| `backend/tests/test_attachment_validation.py` | B2-T01 专项（同上） |
| `docs/acceptance/V2-A1-04-Batch-B-B2-task-list.md` | 任务清单与 ATT 映射 |
| `docs/acceptance/V2-A1-04-Batch-B-B2-T01.md` | T01 验收记录（既有） |
| `docs/audit/V2-A1-04-Batch-B-B2/` | 本轮独立审核包 |

## B2 修改

| 文件 | B2 修改 |
|---|---|
| `backend/app/api/schemas.py` | `AttachmentUploadIn`、`AttachmentOut` |
| `backend/app/dependencies.py` | `get_attachment_service` |
| `backend/app/main.py` | 构造 `AttachmentService`、注册 router（同文件另含 B1-final 的存储/锁/GC 装配，不属于 B2 新增） |
| `MILESTONES.md` | B1 正式 PASS 记录 + B2 “已实现 · 待独立审核”；不改历史记录 |

## 既有未提交（B1-final，不计入 B2）

- 已跟踪修改：`backend/app/core/config.py`、`backend/app/db/session.py`、`backend/app/services/repositories_v2.py`；`main.py` 中对应装配。
- 未跟踪 B1 文件：`storage_lock.py`、`attachment_storage.py`、B1 测试与 B1 审计/验收目录等。
- B2 只调用这些已验收接口，未改其实现。

## 未执行

- 未 `git add`/`commit`/`push`。
- 未修改冻结 Batch B 文档、Knowledge Core、Alembic、依赖清单、前端。
- 未进入 B3/B4/B5。

原始状态见 [`evidence/git-status.txt`](evidence/git-status.txt)、[`evidence/git-diff-stat.txt`](evidence/git-diff-stat.txt)、[`evidence/b2-changes.patch`](evidence/b2-changes.patch)。

完整边界、B2-only 差异文件索引与哈希见
[`code-review/b1-vs-b2-boundary.md`](code-review/b1-vs-b2-boundary.md)。
其中重建的 B1-final `main.py` 基线 SHA-256 为
`2c5ceccd2f20185298d7e6edb3518e9bf5b439c5fe7067f39e5990e2b2ffec06`，与 B1 第 3 轮
验收清单完全一致；`main-b2-only.patch` 仅含四处 B2 装配。机械全量 patch
`working-tree-tracked-vs-HEAD-970c0d8.patch` 含 B1-final + B2，不是 B2-only。