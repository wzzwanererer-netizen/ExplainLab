# B2 代码审查材料索引

**状态：B2 IMPLEMENTED / PENDING INDEPENDENT REVIEW。**
本目录只包含审核材料，不含任何业务代码修改。

| 材料 | 内容 |
|---|---|
| [`audit-focus.md`](audit-focus.md) | 十项审核重点的文件、函数、行号、上下文、对应测试与已知限制 |
| [`b1-vs-b2-boundary.md`](b1-vs-b2-boundary.md) | B1-final 与 B2 的严格边界；无 B1 提交时的两类差异说明；哈希与基线重建证明 |
| [`production-current/`](production-current/) | 6 个生产文件 + 2 个测试文件的完整当前源码 |
| [`diffs/b2-production.diff`](diffs/b2-production.diff) | B2 生产代码-only 差异；已应用验证与当前六文件逐字节一致 |
| [`evidence/b2-changes.patch`](../evidence/b2-changes.patch) | B2-only 合并差异（生产 + 测试） |
| [`diffs/main-b2-only.patch`](diffs/main-b2-only.patch) | `main.py` 四处 B2 装配；基线哈希与 B1 验收清单一致 |
| [`diffs/b2-new-production-files.patch`](diffs/b2-new-production-files.patch) | 三个新生产文件全文 |
| [`diffs/b2-new-tests.patch`](diffs/b2-new-tests.patch) | 两个新测试文件全文 |
| [`diffs/b2-schemas-dependencies.patch`](diffs/b2-schemas-dependencies.patch) | `schemas.py` / `dependencies.py` 的 B2 hunk |
| [`diffs/working-tree-tracked-vs-HEAD-970c0d8.patch`](diffs/working-tree-tracked-vs-HEAD-970c0d8.patch) | 机械全量已跟踪差异（**含 B1-final + B2，不是 B2-only**） |
| [`B2-files.sha256`](B2-files.sha256) | B2 八个生产/测试文件哈希 |
| [`B1-boundary-files.sha256`](B1-boundary-files.sha256) | B1-final 生产/测试文件与重建基线哈希 |

## 关键证明

1. 重建的 B1-final `main.py` SHA-256 =
   `2c5ceccd2f20185298d7e6edb3518e9bf5b439c5fe7067f39e5990e2b2ffec06`，
   与 `docs/acceptance/V2-A1-04-Batch-B-B1-remediation-round3/SHA256SUMS` 完全一致。
2. 将 `b2-production.diff` 应用于该基线 + HEAD 的 `schemas.py`/`dependencies.py`，
   六个生产文件与当前工作树逐字节一致：
   [`evidence/b2-diff-apply-verification.log`](../evidence/b2-diff-apply-verification.log)。
3. B1 的存储/锁/仓储生产文件与 B1 验收清单哈希一致，B2 未修改它们。

## 快速复核

```bash
cd docs/audit/V2-A1-04-Batch-B-B2
sha256sum -c SHA256SUMS
cd code-review
sha256sum -c B2-files.sha256
sha256sum -c B1-boundary-files.sha256
```

Windows 下应用带 CRLF 的 diff 时使用 `patch -p1 --binary`；`git apply` 可能因
行尾转换拒绝。审核目标是阅读差异，不要求实际应用。