# 03 · Diff 汇总

- 基线：HEAD `784b1248…c606c`（本轮无基线漂移）。
- 对比对象：**本轮整改前状态**（非 HEAD）。原因：这 8 个文件在 HEAD 中不是同一形态（5 个生产文件为 untracked，3 个测试中 2 个为新增）。
- `per-file/` 下 6 个 diff 从既有已验收的 `final-remediation/diffs/` **原样复制**，未重新生成；复制后逐个执行 `git apply --check --reverse`，6/6 OK，证明它们仍精确对应当前工作树。
- 另外 2 个新增测试文件用 `git diff --no-index /dev/null <file>` 生成“新文件”diff（全部为 `+` 行）。
- 不得把这 6 个 diff 当作 Git 历史差异：其中 `markdown.py`、`import_review_hook.py`、`governance.py` 的 before 文件是**逆向重建**（`final-remediation/evidence/reconstruct_before.py`），不是 Git 原始 blob；`source_identity.py`、`source_instance_id.py`、`test_markdown_batch_a_identity.py` 的 before 来自第二轮审计快照。

## 1. 文件与统计

| # | 文件 | 类别 | before SHA-256 | after SHA-256 | +/− | diff |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `backend/app/services/source_identity.py` | 生产 | `1fd4e2e2d49246e82a71f38e88cbed4ca0fa192a7906b7225f912a8051ec43c1`（审计快照） | `9c017593179e5a2cc1621301e35cad553893af274bfb8e4ed506321ae51f895a` | +69/−8 | `per-file/backend__app__services__source_identity.py.diff` |
| 2 | `backend/app/services/source_instance_id.py` | 生产 | `96ae5fe80c46115b95356aaed347865afaff15e5943676b4b65a69f5ddd8de3f`（审计快照） | `f41955ced1be52af02ec9ba5ce547c7895e32bab1c03aa47f29be0ecf3951e22` | +9/−4 | `per-file/backend__app__services__source_instance_id.py.diff` |
| 3 | `backend/app/services/markdown.py` | 生产 | `aac4716bb7947aeaadbf3010a39566fab017659c7eae4f0288ac25e90704c6b5`（重建） | `db1255bafbaffd3b3637818a3937274518ef832abdf2cd2a27328363f868e7ac` | +13/−1 | `per-file/backend__app__services__markdown.py.diff` |
| 4 | `backend/app/services/import_review_hook.py` | 生产 | `edf6c1a5aeb1321328ceac1f9a3b28a794cf6d64f043c22efe016417a0505469`（重建） | `cc2df0452469652cfa43f4a91990f48912f2aa2fb6651a55c919f5c11fa80c16` | +12/−1 | `per-file/backend__app__services__import_review_hook.py.diff` |
| 5 | `backend/app/api/routes/governance.py` | 生产 | `d1822d5bc34d659b2589233e159796429407061cb015a7db039a926109d7fee1`（重建） | `1537249912cc1f9d2a68105e6401aafb2e1f6e49ce4e3c62e4e5309e1c1bc722` | +11/−3 | `per-file/backend__app__api__routes__governance.py.diff` |
| 6 | `backend/tests/test_markdown_batch_a_identity.py` | 测试 | `055b05a5de5ec743d713ef17a267c6e221b8225a6df52920f1b2be20ebaaf942`（审计快照） | `383d749ede40eaf3dbd8d01c0ef9ee3a86be5e8f5909ac263e9d110960193264` | +260/−1 | `per-file/backend__tests__test_markdown_batch_a_identity.py.diff` |
| 7 | `backend/tests/test_markdown_batch_a_import_conflict.py` | 测试（新） | 不存在 | `e35518cc3702a01f47d5f076ddb109ac8e1223b67a02b47b5c396de3ba26c0ce` | +351/−0 | `per-file/backend__tests__test_markdown_batch_a_import_conflict.py.diff` |
| 8 | `backend/tests/test_batch_a_fault_injection.py` | 测试（新） | 不存在 | `a0b7ccb6a737601f3e18f8d08b0ad4f1ec3c2d8720c0b77eae795dc6264c113d` | +448/−0 | `per-file/backend__tests__test_batch_a_fault_injection.py.diff` |

完整 Hash 见 `01-git-state/tracked-files.txt` 与 `untracked-files.txt`。

## 2. 每个 diff 的整改意图

| 文件 | 改动要点 | P1/P2 | 对应测试 |
| --- | --- | --- | --- |
| `source_identity.py` | 新增 `identity_guard` / `has_committed_materialize` / `_committed_index`；`materialize` 先分类后 `ensure`；归档改为 `_publish_archive_no_overwrite`（link/O_EXCL + 复核）；`archive_committed` 使用该发布函数 | P1-01/P1-02/P2-06 | 身份测试 9 项新增 + 故障注入归档 5 项 |
| `source_instance_id.py` | 回退路径新增 `write_ok`，fsync 成功后 close 失败不删除有效正式 ID | P2-03 | `TestCloseFailure` 5 项（含回退路径） |
| `markdown.py` | `_import_one` 用 `coordinator.keyed + identity.identity_guard` 包住 S1 重读、`_apply_import`、commit；`_apply_import` 对已物化目标在写前抛 409 | P1-02 | `test_markdown_batch_a_import_conflict.py` 7 项 |
| `import_review_hook.py` | 构造器注入 `SourceIdentityService`；`apply_approved` 在任何导入字段写入前检查已物化并 fail-closed | P1-02 | 审核批准冲突用例 |
| `governance.py` | 批准路径取 identity 服务（缺失 503）、在 `identity_guard` 内执行 Core approve + 钩子 + commit；拒绝路径注入 identity 但不持 guard | P1-02 | 批准 409 / 拒绝零写入 |
| `test_markdown_batch_a_identity.py` | 新增 `TestMaterializeClassificationBeforeIdentityWrite`（7）与 `TestRotateMaterializeOriginConflict`（2） | P1-01/P1-03 | 自身 |
| `test_markdown_batch_a_import_conflict.py` | 新增 7 项导入/批准冲突测试 | P1-02 | 自身 |
| `test_batch_a_fault_injection.py` | 新增 23 项故障注入（fsync/close/replace/link/归档竞态/中断） | P2-01…06 | 自身 |

## 3. 未列入 8 个文件但相关的项

- `backend/app/services/file_write.py`：本轮未修改，SHA-256 `64dc50821af7ff5f6536494c68570d1499e3c7e0b4123b347577b7388c56bd04`；其 13 项测试仍为 P2 证据。
- `backend/tests/test_batch_a_file_write.py`：本轮净修改为零（曾短暂重复，已恢复为第二轮审计逐字节状态 `a9cf54c9663db910f9571fb072dbd0dfc2b3e15ffecec56acd42f4b95598e36d`）。
- `backend/app/services/journal_canonical.py`、`import_coordinator.py`、`process_lock.py`、`import_export.py` 等：Batch A 早期实现，本轮未改。

## 4. 复核方法

```bash
# 6 个既有 diff 仍精确对应工作树
for f in final-review/03-diff/per-file/*.diff; do
  git apply --check --reverse "$f"
done
```

结果：6 个有 before 的 diff 全部 OK；2 个新文件 diff 为 `new file` 格式，不参与 reverse 检查。

## 5. 局限

- `markdown.py` / `import_review_hook.py` / `governance.py` 的 before 为逆向重建，仅用于展示“本轮改了什么”，不能作为 Git 历史证据。
- 若审计需要严格 Git 差异，这 5 个生产文件在 HEAD 中不存在（untracked），`git diff HEAD` 只会显示 `governance.py` 的 Batch A 全量变更，无法分离本轮。
- 未对 diff 做语义等价的形式化证明；结论基于逐行复核 + 现有测试。