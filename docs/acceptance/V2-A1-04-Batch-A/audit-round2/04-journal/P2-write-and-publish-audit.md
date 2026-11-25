# P2 技术审计证据：`write_all` 与文件发布

- 对象：当前工作树 `784b1248`（分支 `fix/m0-admission-and-m5-regressions`），未提交。
- 范围：只记录事实与证据，不修改代码。
- 行号：当前工作树 1-based 逻辑行号。
- 证据分级：**【测试】**= 本轮真实执行且通过；**【静态】**= 代码阅读可确定但无对应测试；
  **【未验证】**= 本轮无法证明。

---

## 1. `write_all` 实现（`backend/app/services/file_write.py:20-31`）

```python
20: def write_all(fd: int, payload: bytes | bytearray | memoryview) -> None:
21:     view = memoryview(payload)
22:     total = len(view)
23:     offset = 0
24:     while offset < total:
25:         try:
26:             written = os.write(fd, view[offset:])
27:         except InterruptedError:
28:             continue
29:         if written <= 0:
30:             raise OSError(errno.EIO, "write_all: os.write returned 0")
31:         offset += written
```

语义：

| 输入/事件 | 行为 | 级别 |
| --- | --- | --- |
| 单次写少于剩余字节 | 循环继续，直到 `offset == total` | **【测试】** `test_partial_then_complete` |
| 每次只写 1 字节 | 循环推进，无死循环 | **【测试】** `test_many_one_byte_writes` |
| `os.write` 返回 0 | 抛 `OSError(EIO, "write_all: os.write returned 0")` | **【测试】** `test_zero_write_fails` |
| `os.write` 返回负数 | 同样命中 `written <= 0` 分支（负数同样抛 EIO） | **【静态】** 未单独注入负数 |
| `InterruptedError` | `continue` 重试，不推进 offset | **【静态】** 无专项测试 |
| 其他异常（如 `OSError`） | 原样传播；不补齐剩余字节 | **【测试】** `test_exception_propagates_without_remaining_write` |
| 空 payload | `while` 不进入，不调用 `os.write` | **【测试】** `test_empty_payload_is_noop` |
| 非 buffer 类型 | `memoryview` 抛 `TypeError` | **【静态】** 生产调用方都传 bytes |
| `os.write` 返回大于剩余长度 | 不存在；`os.write` 不会写入超过给定 buffer | **【静态】** |

`write_all` 不做 fsync、不关闭 fd、不发布文件；这些由 5 个调用点负责。
`grep -rn "os\.write" backend/app` 只命中 `file_write.py` 自身，未发现其他直接写路径。**【静态】**

---

## 2. 五个 `write_all` 调用点

| # | 场景 | 位置 | 发布方式 | 失败时正式文件 |
| --- | --- | --- | --- | --- |
| 1 | Journal current | `source_identity.py:434`（`_atomic_write` 428-442） | `os.replace(tmp, current)` 438 | 旧 current 保留或不存在；tmp 在 `finally` 删除 |
| 2 | Journal archive | `source_identity.py:475`（`archive_committed` 461-487） | 二次存在检查后 `os.replace(tmp, target)` 483 | 已有归档保留；tmp 删除 |
| 3 | 实例 ID 创建（tmp） | `source_instance_id.py:121`（`ensure` 118-149） | `os.link(tmp, path)` 126 | 正式 ID 不存在；tmp 删除 |
| 4 | 实例 ID 创建（无硬链接 fallback） | `source_instance_id.py:137`（`ensure` 129-146） | 直接写 `O_EXCL` 创建的正式文件 | 失败删除半成品正式文件 141-146 |
| 5 | 实例 ID 替换 | `source_instance_id.py:162`（`replace` 154-169） | `os.replace(tmp, path)` 166 | 旧 ID 保留；tmp 删除 |

### 2.1 Journal current（`source_identity.py:428-442`）

```python
428:    def _atomic_write(self, target: Path, payload: bytes) -> None:
429:        target.parent.mkdir(parents=True, exist_ok=True)
430:        tmp = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
431:        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
432:        try:
433:            try:
434:                write_all(fd, payload)
435:                os.fsync(fd)
436:            finally:
437:                os.close(fd)
438:            os.replace(tmp, target)
439:        finally:
440:            with suppress(OSError):
441:                os.unlink(tmp)
442:        _sync_dir(target.parent)
```

- `write_all` 抛异常 → 内层 `finally` close → 外层 `finally` 删除 tmp → `os.replace` 不执行。
  **【测试】** `test_current_write_failure_publishes_nothing`、`test_current_half_write_is_not_renamed_into_place`
- `fsync` 抛异常 → 同上，不 replace。**【静态】**
- `close` 抛异常 → 内层 `finally` 的异常向外传播，跳过 438 的 replace；tmp 删除。**【静态】**
- `os.replace` 抛异常 → 旧 current 不变；tmp 删除。**【静态】**
- 进程在 `write_all`/`fsync` 中被强杀 → 正式 current 不变；tmp 可能残留。后续 `read_current()`
  只读固定文件名，不扫描 `.tmp`，残留不会参与恢复。**【静态】**
- `_sync_dir` 在 Windows 直接返回；POSIX 为 try/except 静默。**【静态】**

注意：`write_current` 会无条件替换已存在的 current。PREPARED → COMMITTED 的第二次写入
依赖这一点；发布时旧 current 会消失，而不是保留双份。

### 2.2 Journal archive（`source_identity.py:461-487`）

```python
461:    def archive_committed(self, record: dict[str, Any]) -> None:
...
467:        if target.exists():
468:            if target.read_bytes() != payload:
469:                raise SourceIdentityError(JOURNAL_CORRUPT, "archive content conflict")
470:            return
471:        tmp = self.archive_dir / f".{target.name}.{uuid.uuid4().hex}.tmp"
472:        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
473:        try:
474:            try:
475:                write_all(fd, payload)
476:                os.fsync(fd)
477:            finally:
478:                os.close(fd)
479:            if target.exists():
480:                if target.read_bytes() != payload:
481:                    raise SourceIdentityError(JOURNAL_CORRUPT, "archive content conflict")
482:            else:
483:                os.replace(tmp, target)
484:        finally:
485:            with suppress(OSError):
486:                os.unlink(tmp)
487:        _sync_dir(self.archive_dir)
```

- 第一次存在检查（467）在写 tmp 前；第二次检查（479）在 replace 前，缩小竞争窗口。
- 若目标已存在且内容不同 → `JOURNAL_CORRUPT`，绝不覆盖。**【静态】**（`test_archive_corruption_fails_closed`
  覆盖的是读取损坏归档，不是写入同名冲突）
- `write_all` 失败 → 不 replace、tmp 删除；已存在的 COMMITTED current 保留。
  **【测试】** `test_archive_write_failure_keeps_committed_current_then_recovers`
- 若两次检查之间目标被同内容创建 → `target.exists()` 为真且内容相同，不 replace，tmp 删除；
  最终归档仍只有一份。**【静态】**
- 若第二次检查与 `os.replace` 之间目标被不同内容创建 → 当前实现会直接 replace 覆盖。
  生产路径由单实例 `ProcessLock` 序列化，未做跨进程竞争注入。**【未验证】**
- `fsync`/`close`/`replace` 失败、进程强杀：同 current 的静态分析；无逐点测试。**【静态】**

### 2.3 实例 ID 创建（`source_instance_id.py:110-151`）

```python
110:    def ensure(self) -> str:
111:        """读取已有 ID；不存在时生成并原子创建。必须已持有进程锁。"""
112:        if self.path.exists():
113:            return self.read()
...
117:        tmp = self.data_dir / f".{FILENAME}.{uuid.uuid4().hex}.tmp"
118:        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _BINARY, 0o600)
119:        try:
120:            try:
121:                write_all(fd, payload)
122:                os.fsync(fd)
123:            finally:
124:                os.close(fd)
125:            try:
126:                os.link(tmp, self.path)  # 目标存在 → FileExistsError，绝不覆盖
127:            except FileExistsError:
128:                return self.read()
129:            except OSError:
130:                # 不支持硬链接的文件系统：退回 O_EXCL 独占创建。
131:                try:
132:                    target = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _BINARY, 0o600)
...
141:                except BaseException:
...
144:                    with suppress(OSError):
145:                        os.unlink(self.path)
146:                    raise
147:        finally:
148:            with suppress(OSError):
149:                os.unlink(tmp)
150:        _sync_dir(self.data_dir)
151:        return new_id
```

- tmp 写失败/半写 → 正式 ID 不创建；tmp 删除。**【测试】**
  `test_create_write_failure_publishes_no_id`、`test_create_half_write_is_not_linked_into_place`
- `os.link` 因目标已存在失败 → 读取已有 ID 返回，绝不覆盖。**【静态】**
- `os.link` 因其他 OSError 失败 → 进入 fallback（2.4）。**【测试】**（fallback 测试通过 monkeypatch
  强制 `OSError`）
- `fsync`/`close` 失败 → 不执行 link；tmp 删除；正式 ID 不创建。**【静态】**
- 进程在 link 前被强杀 → tmp 残留，正式 ID 不存在；下次 `ensure` 重新生成。**【静态】**
- tmp 文件权限 `0o600`；目录 fsync 在 Windows 直接返回。**【静态】**

### 2.4 无硬链接 fallback（`source_instance_id.py:129-146`）

- 用 `O_EXCL` 直接创建正式文件，再 `write_all` + `fsync` + `close`。
- 失败时 `except BaseException` 删除 `self.path` 后原样抛出，防止截断内容以正式 ID 留下。
  **【测试】** `test_create_fallback_half_write_removes_partial_formal_file`
- 删除的是本函数刚以 `O_EXCL` 创建的路径；若 `O_EXCL` 返回 `FileExistsError`，会直接 `return self.read()`，
  不会走到删除分支。**【静态】**
- **边界**：若 `write_all` 成功、`fsync` 成功，而 `os.close(target)` 在 `finally` 中抛异常，
  异常会进入 `except BaseException`，删除已完整写入的正式 ID。结果仍是 fail-closed（启动失败，
  下次重新生成），但会丢失一个本来有效的 ID。本轮未注入 close 失败。**【静态/未验证】**
- **竞争边界**：若另一个进程在 `O_EXCL` 创建后、失败删除前替换了该路径，删除可能误删它人的文件。
  生产路径由单实例 `ProcessLock` 排除；未做跨进程注入。**【未验证】**
- tmp 清理在外层 `finally`，fallback 成功/失败都会删除 `.{FILENAME}.*.tmp`。**【测试】**（断言无 `.tmp` 残留）

### 2.5 实例 ID 替换（`source_instance_id.py:154-169`）

```python
154:    def replace(self, new_id: str) -> None:
...
158:        tmp = self.data_dir / f".{FILENAME}.{uuid.uuid4().hex}.tmp"
159:        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _BINARY, 0o600)
160:        try:
161:            try:
162:                write_all(fd, (new_id + "\n").encode("ascii"))
163:                os.fsync(fd)
164:            finally:
165:                os.close(fd)
166:            os.replace(tmp, self.path)
167:        finally:
168:            with suppress(OSError):
169:                os.unlink(tmp)
```

- `write_all` 失败/半写 → 不 replace；旧 ID 保留；tmp 删除。**【测试】**
  `test_replace_write_failure_preserves_old_id`、`test_replace_half_write_preserves_old_id`
- `fsync`/`close`/`os.replace` 失败 → 旧 ID 保留（replace 未执行或原子失败）；tmp 删除。**【静态】**
- 进程在 replace 前被强杀 → 旧 ID 保留，tmp 残留。**【静态】**
- `replace` 不检查目标是否已存在（ROTATE 语义要求替换）；不做备份。**【静态】**

---

## 3. 失败模式矩阵

| 失败模式 | current | archive | ID 创建 tmp | ID fallback | ID replace | 级别 |
| --- | --- | --- | --- | --- | --- | --- |
| 部分短写（write_all 循环内） | 继续写满 | 继续写满 | 继续写满 | 继续写满 | 继续写满 | **【测试】** 单元层 |
| 连续 1 字节写 | 写满 | 写满 | 写满 | 写满 | 写满 | **【测试】** 单元层 |
| `os.write` 返回 0 | EIO，不发布 | EIO，不发布 | EIO，不发布 | EIO，删除正式文件 | EIO，不发布 | **【测试】** 单元层；调用点零写未逐个注入 |
| `InterruptedError` | 重试 | 重试 | 重试 | 重试 | 重试 | **【静态】** 无注入测试 |
| 其他写入异常 | 不发布，tmp 删除 | 不发布，tmp 删除 | 不发布，tmp 删除 | 删除正式文件，tmp 删除 | 不发布，tmp 删除 | **【测试】** current/archive/ID 创建/fallback/replace |
| `fsync` 失败 | 不 replace | 不 replace | 不 link | 删除正式文件 | 不 replace | **【静态】** 未注入 |
| `close` 失败 | 不 replace，tmp 删除 | 不 replace，tmp 删除 | 不 link，tmp 删除 | 删除已写正式文件 | 不 replace，tmp 删除 | **【静态/未验证】** 未注入 |
| `os.replace` 失败 | 旧 current 保留 | 已有归档保留 | 不适用 | 不适用 | 旧 ID 保留 | **【静态】** 未注入 |
| `os.link` 失败（非 FileExists） | 不适用 | 不适用 | 进入 fallback | 不适用 | 不适用 | **【测试】** fallback 路径 |
| `os.link` FileExistsError | 不适用 | 不适用 | 读取已有 ID，不覆盖 | 不适用 | 不适用 | **【静态】** |
| 目标已存在且内容不同（archive） | 不适用 | `JOURNAL_CORRUPT`，不覆盖 | 不适用 | 不适用 | 不适用 | **【静态】** |
| 进程强杀在发布前 | 正式不变，tmp 残留 | 正式不变，tmp 残留 | 正式不存在，tmp 残留 | 正式可能半写（被杀时无法执行清理） | 旧 ID 保留，tmp 残留 | **【静态/未验证】** |
| 真实 ENOSPC / 配额 / 断电 | 未验证 | 未验证 | 未验证 | 未验证 | 未验证 | **【未验证】** |

说明：

- “单元层”指直接对 `write_all` 注入 `os.write` 行为；“调用点”指对
  `source_identity.write_all` / `source_instance_id.write_all` 打补丁验证发布语义。
- zero/短写在调用点大多会表现为 `write_all` 抛异常，再由调用点清理；现有调用点测试注入的是
  “直接抛异常”和“先写半再抛”，与 zero 的清理路径相同，但未逐点用真实 zero 注入。**【静态推断】**

---

## 4. 临时文件与截断发布边界

- 所有发布路径都先写同目录 `.name.<uuid>.tmp`，只有 `write_all` + `fsync` + `close`
  全部成功后才 `os.replace`/`os.link`。
- `write_all` 的短写循环保证“单次 `os.write` 短写”不会直接进入发布；但仍不能防御：
  - 进程在 `write_all` 循环中被强杀（tmp 半写残留，正式文件不变）；
  - 真实介质错误导致 `os.fsync`/`os.close`/`os.replace` 失败（异常路径，未注入）；
  - 断电后目录项未持久化（Windows 目录 fsync 为空操作）。
- `.tmp` 文件不会被 `read_current()`/`read_archive()` 读取：
  - current 只读固定 `source-identity-journal.json`；
  - archive 只 glob `*.json`，tmp 以 `.tmp` 结尾；
  - 实例 ID 只读固定 `source-instance-id`。
- 因此残留 tmp 不会污染恢复；但没有主动清理陈旧 tmp 的代码（只清理本次调用自己创建的 tmp）。

---

## 5. 与 P2 整改前的差异

- 整改前这些调用点直接调用一次 `os.write` 或未检查返回值；短写可能把截断内容
  fsync/rename/link 成正式文件。
- 整改后统一经 `write_all`，返回 0 抛 EIO，异常不进入发布。
- 整改未改变：打开模式（`O_WRONLY|O_CREAT|O_EXCL`）、`0o600`、fsync 位置、
  `os.replace`/`os.link` 发布顺序、目录 fsync 尽力而为策略、Journal 状态机与 Canonical JSON。
- 完整前后对照见 `../03-diff/file_write.py.diff`、`../03-diff/source_instance_id.py.diff`、
  `../03-diff/source_identity.py.diff`。

---

## 6. 本轮记录的不一致/边界（不自行修复）

1. `write_all` 的 `InterruptedError` 重试没有专项测试。
2. 五个调用点均未注入 `fsync` / `close` / `os.replace` 失败；只有写入失败与半写。
3. fallback 的 `except BaseException` 在 close 失败时会删除已完整写入的正式 ID；
   fail-closed 但可能丢弃有效 ID，未测试。
4. archive 的“二次检查 → replace”之间仍有竞争窗口；依赖单实例锁，未做跨进程注入。
5. 进程强杀/断电后 tmp 残留不会被主动清理；当前只保证正式文件不截断（在测试覆盖的故障模型内）。
6. 未验证真实 `ENOSPC`、配额、网络盘、只读目录、Windows ACL。
7. 以上均不改变“SQLite + Windows NTFS 范围内短写路径已测试”的结论，但不得外推为
   “任何介质/断电故障下都不产生截断正式文件”。

---

## 7. 证据分级汇总

| 结论 | 级别 |
| --- | --- |
| `write_all` 短写/1 字节/0/异常/空 payload | **【测试】** |
| 5 个调用点写入失败/半写的发布语义 | **【测试】**（archive 恢复、fallback 清理、replace 保留旧 ID） |
| `InterruptedError` 重试 | **【静态】** |
| `fsync`/`close`/`replace`/`link` 失败 | **【静态】**，未注入 |
| 进程强杀、断电、ENOSPC | **【未验证】** |
| POSIX 实机 | **【未验证】** |
| PostgreSQL 上的文件系统行为 | **【未验证】**（与 DB 无关，但未在 PG 部署环境运行） |