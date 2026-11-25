# 测试统计核验报告

**核验对象：B1 定点回归 `passed` 数量在 README、自测报告、MILESTONES 之间的冲突。**

## 1. 发现的冲突

| 文件 | 原记录 |
|---|---|
| `README.md` | 184 passed，3 skipped |
| `self-verification-report.md` | 182 passed，3 skipped |
| `MILESTONES.md` | 184 passed，3 skipped |

没有依据“较大数字更可能正确”来选择；以下以原始 pytest 输出和实际命令为准。

## 2. 原始证据

### 2.1 原始日志

[`evidence/b1-targeted-regression.log`](evidence/b1-targeted-regression.log) 是 B2 交付时保存的原始输出，末行：

```text
184 passed, 3 skipped, 1 warning in 52.70s
EXIT=0
```

该目录下只有这一份 `b1-targeted-regression.log`，没有第二份较旧的 182 原始日志。

### 2.2 实际命令与文件范围

[`evidence/commands.txt`](evidence/commands.txt) 记录的合并回归命令为：

```bash
uv run pytest \
  backend/tests/test_attachment_storage.py \
  backend/tests/test_attachment_windows.py \
  backend/tests/test_storage_lock_sqlite.py \
  backend/tests/test_attachment_gc.py \
  backend/tests/test_attachment_api.py \
  -o addopts="--import-mode=importlib" -q
```

范围是 4 个 B1 附件/锁/GC 文件 + 1 个 B2 API 文件，共 5 个文件；没有排除目录，没有使用 `-k`、`--ignore` 或 `-x`。

### 2.3 独立复跑

为排除单次日志异常，使用同一命令重新运行并保存：

- [`evidence/b1-targeted-regression-verification.log`](evidence/b1-targeted-regression-verification.log)：`184 passed, 3 skipped`，`EXIT=0`。
- [`evidence/b1-only-regression-scope.log`](evidence/b1-only-regression-scope.log)：去掉 B2 API 文件，只跑 4 个 B1 文件并加 `-rs`，结果 `162 passed, 3 skipped`，`EXIT=0`。

数量分解可核验：

```text
B1-only 162 passed
+ B2 API 22 passed（evidence/b2-api.log）
= 184 passed
```

3 个跳过项固定为：

1. `test_attachment_storage.py:54`：Linux 真实挂载用例；
2. `test_attachment_storage.py:762`：Windows 打开文件拒绝 rename 的句柄替换取证；
3. `test_attachment_windows.py:174`：无可写第二 Windows 卷。

## 3. 结论

- **以原始日志和复跑为准：B1 定点回归为 `184 passed, 3 skipped`。**
- `self-verification-report.md` 中的 `182` 是过期文本，与当前 22 项 B2 API 测试不一致，已更正。
- 该过期文本没有对应的原始日志保留在本交付包中；不把任何推测的早期运行当作证据。
- README、自测报告、MILESTONES 现统一为 `184 passed, 3 skipped`。
- 全仓 `1394 passed, 208 skipped` 与 B2 API `22 passed` 未受此冲突影响；对应原始日志分别为 `evidence/full-suite.log`、`evidence/b2-api.log`。

## 4. 复核命令

```bash
uv run pytest backend/tests/test_attachment_storage.py \
  backend/tests/test_attachment_windows.py \
  backend/tests/test_storage_lock_sqlite.py \
  backend/tests/test_attachment_gc.py \
  backend/tests/test_attachment_api.py \
  -o addopts="--import-mode=importlib" -q

uv run pytest backend/tests/test_attachment_storage.py \
  backend/tests/test_attachment_windows.py \
  backend/tests/test_storage_lock_sqlite.py \
  backend/tests/test_attachment_gc.py \
  -o addopts="--import-mode=importlib" -q -rs
```