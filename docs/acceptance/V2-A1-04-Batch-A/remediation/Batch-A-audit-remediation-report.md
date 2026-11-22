# V2 · A1-04 · Batch A 独立审计整改报告

- 日期：2026-11-22
- 依据：ChatGPT 独立审计报告的 P1（身份分类）与 P2（文件短写）
- 范围：仅修复这两类缺陷及对应测试；未进入 Batch B
- 基线：HEAD `784b1248065424e07273b272d6016cc121bc606c`，分支 `fix/m0-admission-and-m5-regressions`
- 工作树：未提交、未暂存、未推送；既有未提交设计与审计文档保留

## 1. 开发前基线核验

已执行并保存：

- `git rev-parse HEAD`、`git branch --show-current`
- `git status --short`
- `git diff --cached --stat`（空）
- `git diff --stat`（既有 8 个 tracked 修改）
- `git ls-files --others --exclude-standard`（Batch A 新文件与既有未提交文档）

证据：`evidence/00-baseline.txt`、`evidence/10-git-status.txt`。

基线特征：

- 无 staged 内容；
- Batch A 实现文件仍为 untracked（包括 `source_identity.py`、`source_instance_id.py`）；
- 未清理、未覆盖、未 reset 任何既有文件；
- 另存在此前轮次未提交的 `docs/plans`、`docs/audit`、`docs/acceptance` 文件，全部保留。

## 2. P1：MATERIALIZE 与 ImportOrigin 并存冲突

### 2.1 缺陷

`SourceIdentityService.classify` 原先只依据 `ImportOrigin` 自身状态：

```python
if snapshot["import_origin_count"] > 0:
    if origin_state == "complete":
        return ClassifiedIdentity(..., "1", ...)
    return ClassifiedIdentity(..., "3", ...)
```

当同一 `knowledge_item` 已存在 COMMITTED MATERIALIZE 记录、又存在完整 ImportOrigin 时，
仍返回状态 1，违反冻结 §22.2：

> 任何“有 ImportOrigin 但又有本地物化记录”的组合均为冲突态，一律 fail-closed。

### 2.2 修复

在 `source_identity.py` 增加统一跨记录检查：

```python
@staticmethod
def _origin_materialize_conflict(snapshot, records) -> bool:
    return snapshot["import_origin_count"] > 0 and bool(records)
```

分类器在判断 ImportOrigin 自身状态之前先执行该检查：

```python
if self._origin_materialize_conflict(snapshot, records):
    return ClassifiedIdentity(str(item.id), "3", None, None, snapshot)
```

位置：`source_identity.py:565`（helper）、`:597`（调用）。

### 2.3 行为

- 覆盖状态 1 与状态 3 的所有 ImportOrigin 组合：完整、残缺、重复、非法、多合法身份对、多版本。
- 同一 item 只要有任意 COMMITTED MATERIALIZE 记录与任意 ImportOrigin 并存，即归状态 3。
- 冲突时 `source_instance_id/source_document_id` 均为 `None`，不选择任一记录。
- 导出不写来源身份头/元数据；`ensure_local_export_identity` 与 `materialize` 以既有稳定码
  `SOURCE_DOCUMENT_UNMATERIALIZED` 拒绝；不物化、不认领、不修复。
- 不删除、合并或覆盖 ImportOrigin / Journal 记录。
- 无 ImportOrigin 的正常导入仍为状态 1；无 ImportOrigin 的本地物化仍为状态 2b；状态 4 逻辑未改。

### 2.4 状态

| 项 | 状态 |
|---|---|
| 代码修复 | 已修复 |
| 10 类专项测试 | 已验证（10 passed） |
| 全量回归 | 已验证（1085 passed） |

## 3. P2：文件短写

### 3.1 缺陷

以下路径原先单次 `os.write` 后直接 `fsync`，不检查返回值：

- `JournalStore._atomic_write`（current）
- `JournalStore.archive_committed`（archive）
- `SourceInstanceIdStore.ensure`（首次创建）
- `SourceInstanceIdStore.replace`（ROTATE）

短写或 0 返回时可能把截断内容发布为正式 Journal/archive/实例 ID。

### 3.2 修复

新增统一封装 `backend/app/services/file_write.py`：

```python
def write_all(fd, payload) -> None:
    view = memoryview(payload)
    total = len(view)
    offset = 0
    while offset < total:
        try:
            written = os.write(fd, view[offset:])
        except InterruptedError:
            continue
        if written <= 0:
            raise OSError(errno.EIO, "write_all: os.write returned 0")
        offset += written
```

接入四处：

- `source_identity.py:434` Journal current；
- `source_identity.py:475` Journal archive；
- `source_instance_id.py:121` 实例 ID 创建临时文件；
- `source_instance_id.py:162` 实例 ID 替换临时文件；
- 另接入 `source_instance_id.py:135` 无硬链接 fallback 正式文件。

fallback 特殊处理：

```python
except BaseException:
    with suppress(OSError):
        os.unlink(self.path)  # 移除短写半成品，保留旧 ID 不适用（O_EXCL 新文件）
    raise
```

### 3.3 失败语义

- 短写：循环继续写剩余字节；
- 返回 0：抛 `OSError(EIO)`；
- 写入异常：原样传播，不再写、不 fsync、不 rename；
- 未完整写入：临时文件由既有 `finally` 清理，正式 current/archive 不出现；
- archive 失败：合法 COMMITTED current 保留，后续恢复只补归档；
- 实例 ID 替换失败：临时文件清理，原 ID 字节不变；
- fallback 创建失败：删除半成品正式 ID 文件；
- 文件模式 `0o600`、fsync、`os.replace`/`os.link`、Journal v1 数据契约均未改。

### 3.4 状态

| 项 | 状态 |
|---|---|
| 代码修复 | 已修复 |
| 13 项故障注入 | 已验证（13 passed） |
| 全量回归 | 已验证（1085 passed） |

## 4. 修改文件清单

本次整改实际改动：

| 文件 | 改动 |
|---|---|
| `backend/app/services/source_identity.py` | P1 跨记录冲突检查；P2 两处 Journal 写入接入 `write_all` |
| `backend/app/services/source_instance_id.py` | P2 创建/替换/fallback 写入接入 `write_all`；fallback 失败清理半成品 |
| `backend/app/services/file_write.py` | 新增统一完整写入封装 |
| `backend/tests/test_markdown_batch_a_identity.py` | 新增 10 项并存冲突/控制组测试 |
| `backend/tests/test_batch_a_file_write.py` | 新增 13 项短写/故障注入测试 |

未改动：

- `MILESTONES.md`；
- Alembic 迁移、数据库表/列/索引；
- A1-02 Hash/Canonicalization/codec；
- A1-03 链接契约与 `db/locking.py`；
- V1 API/端口；
- 依赖与锁文件；
- Batch B/附件功能；
- 其他无关业务模块。

关键 diff：`evidence/09-key-diff.txt`。文件 SHA-256 与行数：`evidence/11-frozen-and-files.txt`。

## 5. 验证摘要

| 命令 | 结果 | 证据 |
|---|---|---|
| 全量 SQLite + Core | **1085 passed, 178 skipped** | `evidence/01-pytest-full-sqlite.txt` |
| Batch A 聚焦 | **155 passed** | `evidence/02-pytest-batch-a-focus.txt` |
| A1-02/A1-03/V1 冻结回归 | **605 passed** | `evidence/03-frozen-and-v1.txt` |
| P1 专项 | **10 passed** | `evidence/07-p1-conflict-tests.txt` |
| P2 专项 | **13 passed** | `evidence/08-p2-write-fault-tests.txt` |
| `uv run ruff check` | All checks passed | `evidence/04-ruff.txt` |
| 前端 test/typecheck/build | 72 passed；typecheck/build 通过 | `evidence/05-frontend.txt` |
| PostgreSQL | 未验证 | `evidence/06-postgresql-unverified.txt` |

真实 PostgreSQL 仍未验证：无 `EXPLAINLAB_PG_TEST_URL`、`psql`、`pg_isready`、`docker`。
未把 SQLite 结果写成 PG 通过。

## 6. 结论

- P1：**已修复、已验证**。
- P2：**已修复、已验证**（短写、0、异常、Journal current/archive、实例 ID 创建/替换/fallback）。
- 全量 SQLite/Core/前端回归：**已验证**。
- 真实 PostgreSQL：**未验证**。
- 未提交、未推送、未进入 Batch B。

等待 ChatGPT 第二轮独立审计。