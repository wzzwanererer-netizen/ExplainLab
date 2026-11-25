# Git 状态与差异摘要

## 1. 基线

- HEAD：`970c0d8ec05f0b8c68286839a56b14c74ea230c6`
- 分支：`fix/m0-admission-and-m5-regressions`
- 工作树同时包含此前未提交的 B1/B2 已验收实现与文档；本轮没有提交这些历史改动。
- B3-T01 未 commit、未 push。

## 2. B3-T01 修改

```text
backend/app/api/routes/import_export.py | 169 +++++++---
backend/app/services/markdown.py        | 546 +++++++++++++++++++++++++++-----
2 files changed, 583 insertions(+), 132 deletions(-)
```

新增：

```text
backend/app/services/attachment_staging.py
backend/tests/test_attachment_staging.py
docs/acceptance/V2-A1-04-Batch-B-B3-T01/**
```

## 3. 禁止项核对

| 约束 | 结果 |
|---|---|
| Knowledge Core 未改 | `git status knowledge-core` 无变化 |
| Alembic/迁移未改 | `backend/alembic/**` 无变化 |
| 依赖清单未改 | `pyproject.toml`、`uv.lock`、`frontend/package*.json` 无变化 |
| B1/B2 生产文件未改 | B2 六项生产 SHA-256 与 `docs/audit/V2-A1-04-Batch-B-B2/code-review/B2-files.sha256` 逐项一致 |
| B2 测试 `test_attachment_validation.py` 未改 | SHA-256 一致 |
| `test_attachment_api.py` 本轮未改 | mtime `2026-11-24 11:29:00` 早于本轮起始 `16:38`；当前哈希与最初 B2 包不同，差异属此前 B2 整改阶段，见下方说明 |
| B4 `governance.py` 未改 | 无变化 |
| `import_review_hook.py` 未改 | 无变化 |
| 冻结设计文档未改 | `docs/plans/V2-A1-04-Batch-B/**` 未修改 |
| `MILESTONES.md` 未改 | 本轮无变化 |
| 未进入 B3-T02/B4/B5 | 无对应生产实现 |
| 未 commit/push | HEAD 未变 |

B2 哈希复核：

```text
attachment_validation.py  57408668ff806cb5a1b61e418388962192ef8173441b500a9a25eef6c6304c21 OK
attachments.py            2e37b0495b67afa93a561155cee67340e34da7c117529ff64eb8cbe7d9fe806b OK
routes/attachments.py     489edacdaf01c546e9cc21f26befb92d4aba697a1a5a55c68809b0c6696bc2c6 OK
api/schemas.py            d254590f36ae8ac02d50fe5cd86d1feb6e68d72f96bbb134ba8e37fae8219f1d OK
dependencies.py           78f8d396a37a7c8eb3d85887e1b7204b68b02b6aa9e796ea626c34dec973d34c OK
main.py                   b77ed4198094df1d6609123161219370ecb67aff33e2e185e0f7a7374adc803b OK
test_attachment_validation.py 1494f0eb6dfad9eb361ca94815c2d28c94b75a8861a50448ee22e5783d132e7e OK
test_attachment_api.py    current 9148e630fa940e4f299581c3e9fd471e0cefba080d5545d8b013e74b35a0a49a
                          B2-files.sha256 93aa6df815c6d41b428156bc9b789bc9c27a3f871fae45fb5b3a1169e4ba2cea（不同）
                          mtime 2026-11-24 11:29:00，早于本轮起始 16:38；本轮未触碰
```

## 4. 工作树免责声明

`git status` 仍会显示 B1/B2 阶段已存在但未提交的生产文件、测试和审核材料。这些不是 B3-T01 新增改动；本报告不把它们混入 B3 代码差异。B3 变更边界以 `file-change-list.md` 为准。

## 5. 原始证据

- `evidence/git-status.txt`
- `evidence/git-diff-check.txt`
- `evidence/git-diff-stat.txt`
- `evidence/source-hashes.txt`

`git diff --check` exit 0；仅有 Git 对 CRLF 的提示，不是空白错误。