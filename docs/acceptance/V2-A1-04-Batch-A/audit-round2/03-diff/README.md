# 整改差异（P1 / P2）

## 0. 基线说明（重要）

Batch A 整体尚未提交：`source_identity.py`、`source_instance_id.py`、`test_markdown_batch_a_identity.py`
在 Git 中仍是 **untracked**，`file_write.py`、`test_batch_a_file_write.py` 为本轮新增文件。
因此不存在可用的 `git diff HEAD` 基线。

本目录的“整改前”文件不是 Git 快照，而是从本轮会话的编辑记录中**逐条反向应用**得到的：

- 反向应用了 P1 的 `12947`、`13058`、`13062` 编辑；
- 反向应用了 P2 的 `12979`、`12997`、`13001`、`13007`、`13011`、`13015`、`13036` 编辑；
- 反向应用了测试的 `12953`、`12958`、`12963`、`13165` 编辑；
- 每次反向替换前断言 `new_string` 在文中恰好出现一次，避免误替换；
- 反向应用完成后，再按时间正序把同一批 `old_string`/`new_string` 应用回去，
  断言结果与当前 LF 归一化文本逐字节一致；
- 三个重建文件均通过 Python `compile(..., "exec")` 语法检查；
- 每一步反向操作、字节/行数、替换次数、应用后 SHA-256，以及正向校验结果，
  逐项记录在 `reconstruction-log.txt`。

“整改后”为当前工作树原文件。`remediation.diff` 由这两份文本生成。
diff 为便于审阅统一按 LF 展示；工作树中 `source_identity.py` / `source_instance_id.py` 实际为 CRLF，
其余三个文件为 LF。源码原件见 `../02-code/`。

| 文件 | 整改前逻辑行数 / `wc -l` | 整改后逻辑行数 / `wc -l` | 整改后 SHA-256 |
| --- | ---: | ---: | --- |
| `backend/app/services/source_identity.py` | 971 / 970 | 987 / 986 | `1fd4e2e2d49246e82a71f38e88cbed4ca0fa192a7906b7225f912a8051ec43c1` |
| `backend/app/services/source_instance_id.py` | 161 / 160 | 170 / 169 | `96ae5fe80c46115b95356aaed347865afaff15e5943676b4b65a69f5ddd8de3f` |
| `backend/app/services/file_write.py` | 0（不存在） | 31 / 30 | `64dc50821af7ff5f6536494c68570d1499e3c7e0b4123b347577b7388c56bd04` |
| `backend/tests/test_markdown_batch_a_identity.py` | 663 / 662 | 804 / 803 | `055b05a5de5ec743d713ef17a267c6e221b8225a6df52920f1b2be20ebaaf942` |
| `backend/tests/test_batch_a_file_write.py` | 0（不存在） | 288 / 287 | `a9cf54c9663db910f9571fb072dbd0dfc2b3e15ffecec56acd42f4b95598e36d` |

五个整改后文件末尾均无换行，逻辑行数比 `wc -l` 多 1；整改前重建文件同样无末尾换行。

整改前重构文件 SHA-256：

- `before/source_identity.py` → `c6bcaf1f0532727ca61a8f741826818f73dd193a7a3e49ef3d5f53c52fafb370`
- `before/source_instance_id.py` → `5d7c32cdaec40032288d917a7df5738bc76ba374157f8719f542348c0658a586`
- `before/test_markdown_batch_a_identity.py` → `7b8cffcfaaf143411a8b767b0b4efe0f0e381f79733d32d8d2370d9d716168c0`

完整 diff：

- `remediation.diff`：五个文件合并（651 行）
- `source_identity.py.diff`
- `source_instance_id.py.diff`
- `file_write.py.diff`
- `test_markdown_batch_a_identity.py.diff`
- `test_batch_a_file_write.py.diff`

可应用性校验（2026-11-22）：

- 在临时目录放入 3 个 `before/` 文件，对 `remediation.diff` 执行 `patch -p1`，
  退出码 0；生成的 5 个文件与当前工作树逐字节一致（LF 归一化比较，`diff_exit=0`）。
- 两个新增文件没有末尾换行，其 diff 以标准
  `\ No newline at end of file` 标记结束，避免 `patch` 误判为半行。
- 合并 diff 与逐文件 diff 均可独立应用；`remediation.diff` 为五个逐文件 diff 的顺序拼接。

## 1. P1：ImportOrigin 与 MATERIALIZE 并存冲突

文件：`backend/app/services/source_identity.py`

### 1.1 新增统一判定（helper）

插入位置：`_committed_index()` 之后、`classify()` 之前（当前文件 `:564`）。

```python
@staticmethod
def _origin_materialize_conflict(
    snapshot: dict[str, Any], records: list[dict[str, Any]]
) -> bool:
    """§22.2：ImportOrigin 与任意 COMMITTED MATERIALIZE 记录并存即冲突。

    仅检查 ImportOrigin 自身是否 complete 不足以发现跨记录冲突；
    冲突时不选任何一条作为可信来源。
    """
    return snapshot["import_origin_count"] > 0 and bool(records)
```

判定只看两件事：该 item 是否存在 ImportOrigin；该 item 是否存在任意 COMMITTED MATERIALIZE 记录。
不比较实例 ID，不比较记录条数，不比较来源版本。

### 1.2 `classify()` 调用点

整改前：

```python
origin_state = snapshot["import_origin_state"]
if snapshot["import_origin_count"] > 0:
    if origin_state == "complete":
        return ClassifiedIdentity(
            str(item.id), "1",
            snapshot["source_instance_id"],
            snapshot["source_document_id"],
            snapshot,
        )
    return ClassifiedIdentity(str(item.id), "3", None, None, snapshot)
```

整改后（当前 `:596`）：

```python
origin_state = snapshot["import_origin_state"]
if self._origin_materialize_conflict(snapshot, records):
    # §22.2：任何 ImportOrigin 与本地 MATERIALIZE 记录并存均为冲突态，
    # 即使 ImportOrigin 自身为 complete。不得任选一条作为可信来源。
    return ClassifiedIdentity(str(item.id), "3", None, None, snapshot)
if snapshot["import_origin_count"] > 0:
    if origin_state == "complete":
        return ClassifiedIdentity(
            str(item.id), "1",
            snapshot["source_instance_id"],
            snapshot["source_document_id"],
            snapshot,
        )
    return ClassifiedIdentity(str(item.id), "3", None, None, snapshot)
```

冲突分支位于原状态 1/3 判定之前，因此：

- `complete` + MATERIALIZE → 状态 3（不再状态 1）；
- `incomplete` / `duplicate` / `conflict` + MATERIALIZE → 状态 3（与原先结果一致，但统一走同一判定）；
- 多条 MATERIALIZE + ImportOrigin → 状态 3；
- 无 MATERIALIZE 的正常导入 → 仍状态 1；
- 无 ImportOrigin 的本地物化 → 仍按原 2a/2b/4 分支。

状态 3 返回的 `source_instance_id` 与 `source_document_id` 均为 `None`。本轮未增加新稳定错误码，
未改变状态 2a/2b/4 分支和判定顺序。

## 2. P2：统一完整写入

### 2.1 新增 `file_write.py`

```python
def write_all(fd: int, payload: bytes | bytearray | memoryview) -> None:
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

语义：

- 部分写：继续写剩余字节；
- 多次 1 字节写：循环直到写完；
- 返回 0：抛 `OSError(EIO)`，绝不当作成功；
- `InterruptedError`：重试；
- 其他写异常：不捕获、不吞掉，调用方不会执行 fsync/rename；
- 空 payload：循环不进入，立即返回。

### 2.2 调用点逐项对照

| # | 文件 / 函数 | 整改前 | 整改后 |
| --- | --- | --- | --- |
| 1 | `source_identity.py` 导入区 | 无 | `from app.services.file_write import write_all` |
| 2 | `JournalStore._atomic_write`（current 发布） | `os.write(fd, payload)` | `write_all(fd, payload)` |
| 3 | `JournalStore.archive_committed`（archive 发布） | `os.write(fd, payload)` | `write_all(fd, payload)` |
| 4 | `source_instance_id.py` 导入区 | 无 | `from app.services.file_write import write_all` |
| 5 | `SourceInstanceIdStore.ensure` 临时文件 | `os.write(fd, payload)` | `write_all(fd, payload)` |
| 6 | `SourceInstanceIdStore.ensure` 无硬链接 fallback | `os.write(target, payload)` + `fsync` + `close`，无失败清理 | `write_all(target, payload)`；失败时删除半成品正式文件后重抛 |
| 7 | `SourceInstanceIdStore.replace` 临时文件 | `os.write(fd, (new_id + "\n").encode("ascii"))` | `write_all(fd, (new_id + "\n").encode("ascii"))` |

其余顺序未变：`0o600`、临时文件、写完才 `fsync`、`os.close`、`os.replace` / `os.link`、
目录尽力同步、Journal 校验与归档顺序。

### 2.3 fallback 清理（调用点 6）

整改前：

```python
try:
    os.write(target, payload)
    os.fsync(target)
finally:
    os.close(target)
```

整改后：

```python
try:
    try:
        write_all(target, payload)
        os.fsync(target)
    finally:
        os.close(target)
except BaseException:
    # 不支持硬链接时只能直接写目标；失败必须移除半成品，
    # 绝不让截断文件以正式 ID 身份留下。
    with suppress(OSError):
        os.unlink(self.path)
    raise
```

该分支只在 `os.link(tmp, self.path)` 抛 `OSError`（非 `FileExistsError`）时进入。
若正式文件写入半途失败，删除的是 `self.path`（刚以 `O_EXCL` 创建的目标），不会触碰旧 ID；
随后原异常继续向上传播。

## 3. 保持不变

- Journal v1 字段、排序、Canonical JSON v1、三个摘要、checksum 未变。
- `source-instance-id` 格式、严格校验、ROTATE 语义未变。
- 状态 1/2a/2b/3/4 的既有优先级未改（P1 只在原判定前增加跨记录冲突早退）。
- 未新增迁移、表、列、索引、依赖。
- 未改 A1-02 Hash/Canonicalization、A1-03 链接契约、V1 API/端口。