# B3-T01 文件变更清单

基线 `970c0d8ec05f0b8c68286839a56b14c74ea230c6`。工作树同时包含此前未提交的 B1/B2 实现；下表只列本轮 B3-T01 新增/修改。

## 新增

| 文件 | 行数 | 说明 |
|---|---:|---|
| `backend/app/services/attachment_staging.py` | 1589 | Manifest schema、ZIP 解析、staging 生命周期与目录同步、校验、discard/sweep |
| `backend/tests/test_attachment_staging.py` | 1279 | 54 个真实 tmp FS + 真实 SQLite 测试（初版 34 + 整改新增 20） |

## 修改

| 文件 | 说明 |
|---|---|
| `backend/app/services/markdown.py` | 传递服务端附件源、pending 附件集合、Active 检查、真实 envelope manifest |
| `backend/app/api/routes/import_export.py` | ZIP 安全解析接入、入口分流、stable error 映射、staging service 惰性装配 |

本轮 B3 代码差异统计（含整改后）：

```text
backend/app/api/routes/import_export.py | 169 +++++++---
backend/app/services/markdown.py        | 546 +++++++++++++++++++++++++++-----
2 files changed, 583 insertions(+), 132 deletions(-)
```

（`git diff --stat` 只统计已跟踪文件；新增文件未包含。）

## 明确未修改

```text
knowledge-core/**
backend/alembic/**
backend/app/services/attachment_storage.py
backend/app/services/attachments.py
backend/app/services/attachment_validation.py
backend/app/api/routes/attachments.py
backend/app/api/schemas.py
backend/app/dependencies.py
backend/app/main.py
backend/app/db/**
backend/app/services/repositories_v2.py
backend/app/services/governance.py
backend/app/services/import_review_hook.py
backend/tests/test_attachment_api.py
backend/tests/test_attachment_storage.py
backend/tests/test_attachment_validation.py
backend/tests/test_attachment_gc.py
backend/tests/test_attachment_pg.py
backend/tests/test_attachment_windows.py
backend/tests/test_storage_lock_*.py
pyproject.toml
uv.lock
frontend/**
docs/plans/V2-A1-04-Batch-B/**
MILESTONES.md
```

B2 生产文件哈希与 B2 整改包 `SOURCE-SHA256SUMS` 一致：

| 文件 | SHA-256 |
|---|---|
| `attachment_validation.py` | `57408668ff806cb5a1b61e418388962192ef8173441b500a9a25eef6c6304c21` |
| `attachments.py` | `2e37b0495b67afa93a561155cee67340e34da7c117529ff64eb8cbe7d9fe806b` |
| `routes/attachments.py` | `489edacdaf01c546e9cc21f26befb92d4aba697a1a5a55c68809b0c6696bc2c6` |
| `api/schemas.py` | `d254590f36ae8ac02d50fe5cd86d1feb6e68d72f96bbb134ba8e37fae8219f1d` |
| `dependencies.py` | `78f8d396a37a7c8eb3d85887e1b7204b68b02b6aa9e796ea626c34dec973d34c` |
| `main.py` | `b77ed4198094df1d6609123161219370ecb67aff33e2e185e0f7a7374adc803b` |

B2 测试文件 `test_attachment_validation.py` 未修改且哈希一致。`test_attachment_api.py` **本轮未修改**（mtime `2026-11-24 11:29:00`，早于本轮起始 `16:38`），但其当前哈希 `9148e630…` 与 `docs/audit/V2-A1-04-Batch-B-B2/code-review/B2-files.sha256` 记录的 `93aa6df8…` 不同；差异产生于此前 B2 整改阶段，不计入本轮，也不声称与最初 B2 包逐字一致。

## 本轮交付文档

`docs/acceptance/V2-A1-04-Batch-B-B3-T01/` 下 17 类交付物（含整改文档与 `evidence/remediation/`），以及更新后的独立审计材料目录 `docs/audit/V2-A1-04-Batch-B-B3-T01/`。

## Git

- HEAD 仍为 `970c0d8ec05f0b8c68286839a56b14c74ea230c6`；
- 未 commit、未 push；
- `git diff --check` exit 0。