# Journal / 恢复证据（A1-04 Batch A 第二轮审计包）

本目录只做证据摘录与索引，不修改代码。完整源文件见 `../02-code/source_identity.py`；
逐行摘录见 `journal-code-extract.txt`（行号与当前工作树一致）。

## 1. 文件与目录

| 对象 | 路径 | 说明 |
| --- | --- | --- |
| source-instance-id | `<data_dir>/source-instance-id` | 单行规范小写 UUIDv4；仅在进程锁内 `ensure` |
| Journal current | `<data_dir>/source-identity-journal.json` | 同一时刻最多一条未完成/未归档记录 |
| Journal archive | `<data_dir>/source-identity-journal.archive/<operation_id>.json` | 仅允许 COMMITTED 记录 |
| 进程锁 | `<data_dir>/.explainlab.process.lock` | OS 独占锁，永不删除 |

## 2. 写入路径

### current

1. `JournalStore.write_current()` 调 `canonical_dumps(record)` 得到字节。
2. `_atomic_write()`：同目录创建 `.<name>.<uuid>.tmp`，`O_WRONLY|O_CREAT|O_EXCL`，权限 `0o600`。
3. `write_all(fd, payload)` 写完全部字节；`os.fsync(fd)`；`os.close(fd)`。
4. 仅在上述全部成功后 `os.replace(tmp, target)`；`finally` 清理临时文件。
5. `_sync_dir()`：POSIX 尽力 fsync 目录；Windows 直接返回（不宣称掉电持久性）。

### archive

1. `archive_committed(record)` 首先拒绝非 COMMITTED。
2. 目标为 `<archive_dir>/<operation_id>.json`；若已存在且内容不同 → `JOURNAL_CORRUPT`，绝不覆盖。
3. 临时文件同样 `0o600` + `write_all` + `fsync` + `os.close`。
4. 发布前再次检查目标：已存在且内容不同 → `JOURNAL_CORRUPT`；否则 `os.replace(tmp, target)`。
5. 归档成功后 `remove_current()` 删除 current，避免同一操作重复归档。

## 3. PREPARED → COMMITTED 状态转换

| 阶段 | 触发点 | 持久化动作 | 失败时 |
| --- | --- | --- | --- |
| PREPARED | `_new_record(..., phase="PREPARED")`；MATERIALIZE 在 `materialize()`，ROTATE 在 `rotate()` | `journal.write_current(record)` | current 未发布或旧 current 保留；不进入 DB 写/ID 替换 |
| 业务写 | MATERIALIZE：条件 UPDATE `source_instance_id`；ROTATE：`SourceInstanceIdStore.replace(target)` | DB commit / 原子替换 ID | 条件更新 0 行 → rollback + `SOURCE_IDENTITY_INCONSISTENT`；ID 读回不一致 → 异常 |
| 复核 | `_verify_record_db` + `_verify_audit` | 只读 | 摘要/DB 不一致 → fail-closed |
| COMMITTED | `_commit_and_archive()` | 复制记录、`phase="COMMITTED"`、刷新 `updated_at`、重算 checksum、再次 `write_current` | current 写失败 → 不归档、不删 current |
| 归档 | `archive_committed(committed)` | 原子发布归档文件 | 归档失败 → current 保留为有效 COMMITTED，供下次恢复补归档 |
| 收尾 | `remove_current()` | 删除 current | 删除失败会抛出；归档文件已是权威副本 |

`_commit_and_archive()` 在写 COMMITTED 前后各校验一次 `identity_audit_digest`；COMMITTED 记录不改变 DB，
因此第二次校验仍应相等。checksum 覆盖除 `journal_checksum` 外的全部字段。

## 4. 恢复入口与分派

| 入口 | 位置 | 行为 |
| --- | --- | --- |
| 启动 | `backend/app/main.py:85` | 进程锁获取、source-instance-id `ensure` 后调用；DB 不可达时记录警告并延后，不阻断启动 |
| 导入 | `backend/app/services/markdown.py:249` | 任何导入分类/身份写入前调用 |
| 批量导出 | `backend/app/services/markdown.py:1073` | 进入逐条导出前调用 |
| 单篇导出 | `backend/app/services/markdown.py:1127` | 读取条目前调用 |
| 服务内部 | `ensure_local_export_identity` / `materialize` / `rotate` | 均在 `_journal_lock` 内先 `_recover_locked()` |

`recover_if_needed()`（`source_identity.py:627`）在 `_journal_lock` 内读 current：

- 无 current：直接返回。
- current 为 `PREPARED`：
  - `MATERIALIZE` → `_recover_materialize`：目标不得有 ImportOrigin；DB 身份为空则条件 UPDATE；
    已等于记录值则接受；其他值 fail-closed；复核后 `_commit_and_archive`。
  - `ROTATE` → `_recover_rotate`：当前 ID 等于 old 时原子 `replace(target)` 并读回；
    等于 target 时只补提交；其他值 fail-closed。
- current 为 `COMMITTED` → `_recover_committed`：MATERIALIZE 复核 DB；
  ROTATE 校验当前 ID 等于 target；复核审计摘要后只补归档并删除 current，**不重写 DB**。

损坏/校验失败一律抛 `SourceIdentityError`，不自动删除、不重建、不猜测。

## 5. 所有 `classify` 调用入口

生产代码：

| 调用点 | 位置 | 恢复门 |
| --- | --- | --- |
| `ensure_local_export_identity` | `source_identity.py:788` | 同函数内 `_recover_locked()` 先执行 |
| `materialize` | `source_identity.py:810` | 同函数内 `_recover_locked()` 先执行 |
| `rotate` | `source_identity.py:895` | 同函数内 `_recover_locked()` 先执行 |
| `_export_record` | `markdown.py:1148` | 由 `export_documents:1073` / `export_single:1127` 的恢复门覆盖 |

测试代码（非生产入口）：

- `backend/tests/test_markdown_batch_a_identity.py:100`（`_classify` 辅助）
- `backend/tests/test_markdown_batch_a_identity.py:278`（重启后复核 2b）
- `backend/tests/test_markdown_batch_a_identity.py` 中 `_assert_record_conflict_readonly` 内的分类断言

## 6. P1 冲突判定与 Journal 的关系

- `classify()` 调 `_committed_index()`，后者只汇总 `kind="MATERIALIZE"` 且 `phase="COMMITTED"` 的
  current/archive 记录（`committed_materialize_records()`）。
- 判定条件：`snapshot["import_origin_count"] > 0 && bool(records)`；`records` 为该 item 的全部
  COMMITTED MATERIALIZE 记录，不限条数、不限实例 ID 是否相同。
- 命中即返回状态 3，`source_instance_id`/`source_document_id` 均为 `None`；不选可信记录、
  不合并、不删除、不物化、不修复。
- 正常导入（有 ImportOrigin、无 MATERIALIZE）仍为状态 1；正常本地物化（无 ImportOrigin、
  恰好一条匹配 MATERIALIZE）仍为状态 2b；其他既有分支与优先级未改。
- 未新增稳定错误码；冲突分类复用冻结状态 3。

## 7. 本轮未改变的内容

- Journal v1 字段集合、排序、Canonical JSON v1、三个摘要与 checksum 规则未变。
- 文件打开模式、临时文件、fsync、`os.replace`/`os.link` 发布顺序未变。
- source-instance-id 的格式、校验、ROTATE 语义未变。
- 未新增表/列/索引/迁移/依赖。

## 8. 专项技术审计文档

| 文件 | 内容 |
| --- | --- |
| `P1-conflict-and-recovery-audit.md` | 4 个生产 `classify` 调用点、恢复门覆盖、冲突判定、各入口冲突行为、PREPARED/损坏 Journal 影响、不一致记录、证据分级 |
| `P2-write-and-publish-audit.md` | `write_all` 语义、5 个调用点发布细节、失败模式矩阵、临时文件/截断边界、证据分级 |

两份文档均区分 **【测试】** / **【静态】** / **【未验证】**，并记录本轮发现但不修复的边界
（rotate 状态 3 `continue`、`classify` 无内置恢复门、fallback close 失败删除正式 ID 等）。