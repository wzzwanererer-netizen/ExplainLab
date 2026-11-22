# 改动范围分类与冻结边界核对

## 1. 分类总表

### 1.1 代码（5 个文件，4 个 untracked + 1 个 tracked）

| 文件 | 改动性质 | 行数（约） |
| --- | --- | --- |
| `backend/app/services/source_identity.py` | P1-01 分类前移；P1-02 `identity_guard`/`has_committed_materialize`；P2-06 归档不覆盖发布 | +69 / −8 |
| `backend/app/services/source_instance_id.py` | P2-03 回退 close 失败不删有效 ID | +9 / −4 |
| `backend/app/services/markdown.py` | P1-02 导入持身份锁 + 已物化拒绝 | +13 / −1 |
| `backend/app/services/import_review_hook.py` | P1-02 钩子注入 identity + 批准前校验 | +12 / −1 |
| `backend/app/api/routes/governance.py` | P1-02 批准持身份锁；钩子传 identity | +11 / −3 |

未使用的依赖、未新增依赖；未改 `file_write.py`。完整 diff 见 `diffs/` 与 `remediation-final.diff`。

### 1.2 测试（3 个文件）

| 文件 | 性质 | 数量 |
| --- | --- | --- |
| `backend/tests/test_markdown_batch_a_identity.py` | 追加 2 个类 | +9 |
| `backend/tests/test_markdown_batch_a_import_conflict.py` | 新文件 | 7 |
| `backend/tests/test_batch_a_fault_injection.py` | 新文件 | 23 |

- 未删除任何既有有效测试；未弱化断言。
- 本轮中途在 `test_batch_a_file_write.py` 追加的 8 项重复测试已移除，该文件恢复为第二轮审计快照（逐字节一致，`a9cf54…e36d`）。

### 1.3 文档 / 证据（本包）

`README.md`、`final-remediation-report.md`、`final-test-report.md`、`final-known-issues.md`、`postgresql-verification.md`、`posix-verification.md`、`git-state.md`、`scope-classification.md`、`before-sha256.tsv`、`before/`、`diffs/`、`remediation-final.diff`、`evidence/`、`SHA-256SUMS`。

未修改 `MILESTONES.md`、`AGENTS.md`、`docs/architecture.md`、`docs/development.md`。

### 1.4 证据脚本

- `evidence/reconstruct_before.py`：重建整改前快照（只读源文件 + 写入本包 `before/`）。
- `evidence/posix_probe.py`：WSL 标准库探针（临时目录，不写仓库数据）。

## 2. 冻结边界核对（逐项）

| 冻结项 | 是否改动 | 证据 |
| --- | --- | --- |
| A1-02 Core Hash 契约 | 否 | `knowledge-core/` 在 10:00 后无修改（`evidence/scope-mtime.txt`）；冻结集 417 passed |
| A1-03 V1 契约 | 否 | 同上；链接/治理/重建测试全通过 |
| D22 / D23 / D24 | 否 | 未改相关文档与 Journal/ROTATE 语义；P1-03 仅加测试 |
| Canonical JSON v1 | 否 | `journal_canonical.py` 未修改；`test_batch_a_canonical.py` 通过 |
| DB schema / Alembic / 字段契约 | 否 | `backend/alembic/` 在 10:00 后无修改；无模型改动 |
| 身份状态定义（1/2a/2b/3/4） | 否 | `classify` 逻辑未改；仅调整 `materialize` 调用顺序 |
| MATERIALIZE/ROTATE Journal 状态机 | 否 | 未改 PREPARED/COMMITTED 与恢复分支；仅归档**发布方式**改为不覆盖 |
| ImportOrigin 全量审计规则 | 否 | `audit_digest`/snapshot 逻辑未改 |
| MILESTONES 阶段拆分 | 否 | `MILESTONES.md` mtime 2026-11-17，哈希 `66f04e…d1ae` |
| 现有依赖 / 锁文件 | 否 | `pyproject.toml`（11-15）、`uv.lock`（11-13）、`package.json`/`package-lock.json`（11-15）均未改 |
| 前端产品行为 | 否 | `frontend/` 10:00 后无修改；仅运行测试/类型检查/构建 |
| 附件范围 | 否 | 未扩展；附件审核仍稳定拒绝 `ATTACHMENT_REVIEW_UNSUPPORTED` |

## 3. 明确不在本轮范围

- Batch B 及任何新阶段开发；
- R1.4 或新契约修订；
- 无关重构、格式化（未运行 `ruff format`）；
- 提交/推送/历史改写；
- 用 SQLite 或离线 SQL 替代 PostgreSQL 验证；
- 用 Windows 结果替代 POSIX 验证。

## 4. 与“禁止项”的对照

| 禁止项 | 本轮执行 |
| --- | --- |
| 删除/下调既有断言 | 未发生；既有测试全部保留 |
| 修改测试掩盖缺陷 | 未发生；新增测试断言零写入与失败即拒绝 |
| 伪造 PG/POSIX | 未发生；PG 明确未验证，POSIX 部分 UNVERIFIED |
| 无关重构或前端改动 | 未发生 |
| 提交/推送/破坏性 Git 操作 | 未发生 |
| 覆盖既有审计包/删除历史证据 | 未发生；新建 `final-remediation/`，旧 `remediation/`、`audit-round2/` 原样保留 |