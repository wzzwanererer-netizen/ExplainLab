# `SHA-256SUMS` 自校验记录

- 校验时间：2026-11-22T04:10:38+08:00（Asia/Shanghai）
- 校验目录：`docs/acceptance/V2-A1-04-Batch-A/audit-round2/`
- 清单条目数：**41**
- 校验命令：`sha256sum -c SHA-256SUMS`
- 校验退出码：**0**
- 结果：**41/41 OK**
- 清单自身 SHA-256：

```
3852878dedda92fbfc2d432bd6a654cc884a13c4694175c088e0ad7d143b9ee1 *SHA-256SUMS
```

说明：

- `SHA-256SUMS` 覆盖本目录除自身与 `SHA-256SUMS.self-check.md` 外的全部文件：
  5 个源码副本、3 个重建前文件、6 个 diff、3 个代码摘录、Git 状态/diff/untracked/mtime、
  6 个测试原始输出、2 份 P1/P2 专项审计、未验证清单与各 README。
- 本文件因包含清单自身哈希，不能纳入清单（否则循环依赖）；这是唯一排除项。
- 清单文件本身的哈希见上方，由外部命令重新计算得出。
- 本次生成顺序：先完成所有文件 → 刷新 Git 状态 → 重新生成 diff 并验证可应用 →
  重新 `cmp` 源码副本 → 生成 `SHA-256SUMS` → 立即 `sha256sum -c`。

## 逐文件校验结果

```
./01-git/file-mtimes.txt: OK
./01-git/git-diff-cached.patch: OK
./01-git/git-diff.patch: OK
./01-git/git-state.txt: OK
./01-git/scope-classification.md: OK
./01-git/untracked-files.txt: OK
./02-code/README.md: OK
./02-code/cmp-check.txt: OK
./02-code/file-metadata.txt: OK
./02-code/file_write.py: OK
./02-code/source_identity.py: OK
./02-code/source_instance_id.py: OK
./02-code/test_batch_a_file_write.py: OK
./02-code/test_markdown_batch_a_identity.py: OK
./03-diff/README.md: OK
./03-diff/before/source_identity.py: OK
./03-diff/before/source_instance_id.py: OK
./03-diff/before/test_markdown_batch_a_identity.py: OK
./03-diff/file_write.py.diff: OK
./03-diff/reconstruction-log.txt: OK
./03-diff/remediation.diff: OK
./03-diff/source_identity.py.diff: OK
./03-diff/source_instance_id.py.diff: OK
./03-diff/test_batch_a_file_write.py.diff: OK
./03-diff/test_markdown_batch_a_identity.py.diff: OK
./04-journal/P1-conflict-and-recovery-audit.md: OK
./04-journal/P2-write-and-publish-audit.md: OK
./04-journal/README.md: OK
./04-journal/classify-code-extract.txt: OK
./04-journal/journal-code-extract.txt: OK
./04-journal/recovery-entrypoints.txt: OK
./05-tests/23-new-tests.txt: OK
./05-tests/README.md: OK
./05-tests/batch-a-focus.txt: OK
./05-tests/frontend.txt: OK
./05-tests/frozen-and-v1.txt: OK
./05-tests/pytest-full-sqlite.txt: OK
./05-tests/ruff.txt: OK
./06-unverified/known-gaps.md: OK
./06-unverified/postgresql-environment.txt: OK
./README.md: OK
```

## 追加验证（不属于清单校验）

- 5 个源码副本与工作树 `cmp` 全部 `cmp_exit=0`（`02-code/cmp-check.txt`，2026-11-22T04:06:27）。
- `03-diff/` 的 `remediation.diff` 已在临时目录应用到 3 个重建前文件，
  生成 5 个文件与当前工作树逐字节一致（LF 归一化比较 `diff_exit=0`）；
  `patch -p1` 退出码 0。
- 五个源码 SHA-256（工作树与副本一致）：
  - `source_identity.py` `1fd4e2e2d49246e82a71f38e88cbed4ca0fa192a7906b7225f912a8051ec43c1`
  - `source_instance_id.py` `96ae5fe80c46115b95356aaed347865afaff15e5943676b4b65a69f5ddd8de3f`
  - `file_write.py` `64dc50821af7ff5f6536494c68570d1499e3c7e0b4123b347577b7388c56bd04`
  - `test_markdown_batch_a_identity.py` `055b05a5de5ec743d713ef17a267c6e221b8225a6df52920f1b2be20ebaaf942`
  - `test_batch_a_file_write.py` `a9cf54c9663db910f9571fb072dbd0dfc2b3e15ffecec56acd42f4b95598e36d`