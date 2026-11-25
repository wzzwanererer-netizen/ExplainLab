# B1-final 与 B2 变更边界

**状态：B2 IMPLEMENTED / PENDING INDEPENDENT REVIEW。**
本文件说明：在 B1 没有提交、工作树同时承载 B1-final 与 B2 的前提下，哪些内容属于
B1 已验收实现，哪些属于 B2 本轮新增/修改，以及现有 diff 各自的准确含义。

## 1. 关键事实：B1 没有独立提交

- HEAD 仍是 Batch A 基线 `970c0d8ec05f0b8c68286839a56b14c74ea230c6`。
- B1-T01…T04 与 LCK-07 已由独立审核正式 PASS，但实现**从未提交**。
- 因此 Git 仓库中不存在“B1 正式验收提交”，无法执行
  `git diff <B1-commit>..工作树` 得到纯 B2 差异。
- 本包用两种互补材料解决：
  1. **机械全量差异**：`working-tree-tracked-vs-HEAD-970c0d8.patch`，相对 Batch A
     HEAD，包含 B1-final 的已跟踪修改 + B2 修改；**不是 B2-only**。
  2. **B2-only 差异**：以“当前工作树减去 B2 新增块”重建 B1-final `main.py` 基线，
     再生成 `main-b2-only.patch`；其余 B2 文件均为新文件或独立 hunk。
     重建基线 SHA-256 与 B1 验收清单完全一致（见 §3），因此 B2-only 差异可复核。

## 2. B1-final 已验收实现（不属于 B2）

### 2.1 生产代码

| 文件 | B1 内容 | 当前 SHA-256 |
|---|---|---|
| `backend/app/core/config.py` | 附件存储/锁/GC 配置项 | `88824611209582be1c4fdee6493ccba2b5aa777e3d6f69ed70fda2beb7a647e8` |
| `backend/app/db/session.py` | SQLite 外键/连接准备 | `3e4d3f06cf2aeec9d71c62c7e1d82a0f609429285e29fc4fdc1fecde688d8db3` |
| `backend/app/db/storage_lock.py` | SQLite 租约 / PG advisory 锁、`LockGuard.verify_all` | `ca68a7b679b9ca7ba36e5e6dea271cbfc7ee6ab991306e040ba6d7b7e3c2b17a` |
| `backend/app/services/attachment_storage.py` | 布局、`write_temp`、`publish_no_clobber`、`open_verified_blob`、`iter_file` | `3fdf01d96a709b1c2747c87b88d2933dbea0eb80d9842989d4a712eb914ce2b2` |
| `backend/app/services/repositories_v2.py` | 附件/GC 任务仓储（只 flush） | `862669e9ebe3ec27d245679e9f7b405a10961799dfac368f32035f225b812174` |
| `backend/app/main.py` | B1 存储/锁/GC 装配块 | 见 §3 重建基线 `2c5ceccd...`；当前文件因 B2 改动为 `b77ed419...` |

上述哈希与 B1 修复第 3 轮验收清单
`docs/acceptance/V2-A1-04-Batch-B-B1-remediation-round3/SHA256SUMS` 一致。
B2 未修改这些文件；B2 只 import 并调用其已验收接口。

### 2.2 B1 测试

| 文件 | 当前 SHA-256 | 说明 |
|---|---|---|
| `backend/tests/test_attachment_storage.py` | `d8ebef6a5402e04dd5b166d8c38336ff3f849650bbbc81509fb5806a1224bf81` | 与 B1 final-verification-round 清单一致 |
| `backend/tests/test_attachment_windows.py` | `8ed8863e3e5806f527cffabd87dd16d6c48720d0b6e8b676c4225de072877d30` | 同上 |
| `backend/tests/test_attachment_gc.py` | `c501c7a580f757ce94fd596e661e17e07e422621fe312ae7d77dbbca30e16498` | 与 B1 round3 清单一致 |
| `backend/tests/test_attachment_pg.py` | `3707567bed3b9b764fee70334ebd7f5b903efd52ab89ef6434ceac541580c14b` | 与 B1 final-verification-round 清单一致 |
| `backend/tests/test_storage_lock_sqlite.py` | `594c1594ab7c672dad722ec8fa333c1bf716b8899a3dd12de3bfb4177032bd3d` | 与 B1 round3 清单一致 |
| `backend/tests/test_storage_lock_pg.py` | `f11afce311fe1404cad066604228c1ec80d350826acd1316cabb5f4b47132059` | 与 B1 final-verification-round 清单一致 |
| `backend/tests/test_storage_lock_pg_faults.py` | `b93906257cf1364b70e5cd982b75a25350daf8ab642517c1ae51c3feeabc9f0b` | 与 B1 round3 清单一致 |

B2 未修改这些测试，也未删除或弱化任何断言。

## 3. `main.py` 重建基线的可验证性

B2 在 `main.py` 只有四处改动（完全由 `main-b2-only.patch` 展示）：

1. 导入 `attachments_router`；
2. 导入 `AttachmentService`；
3. 在 lifespan 中构造 `AttachmentService`；
4. `include_router(attachments_router, prefix="/api")`。

从当前 `main.py` 删除且仅删除这四处，得到
`code-review/baselines/main-b1-final-reconstructed.py`：

```
SHA-256  2c5ceccd2f20185298d7e6edb3518e9bf5b439c5fe7067f39e5990e2b2ffec06
```

该哈希与 B1 修复第 3 轮验收清单中 `backend/app/main.py` 的哈希
**完全相同**。因此：

- 重建基线不是随意猜测，而是与 B1 正式验收记录逐字节吻合；
- `main-b2-only.patch` 就是从该 B1-final 基线到当前 B2 的准确差异；
- 当前 `main.py` 的 B2 部分可独立审核，B1 装配部分未被 B2 改写。

当前 `main.py` SHA-256：`b77ed4198094df1d6609123161219370ecb67aff33e2e185e0f7a7374adc803b`。

**差异可复现性验证**：将重建基线与 HEAD 的 `schemas.py`、`dependencies.py` 放入临时树，
应用 `b2-production.diff` 后逐文件 `cmp`，六个生产文件与当前工作树**逐字节一致**。
原始输出见 [`evidence/b2-diff-apply-verification.log`](../evidence/b2-diff-apply-verification.log)：
`EXIT=0 ALL_PRODUCTION_FILES_MATCH_CURRENT`。

## 4. B2 新增/修改文件与 SHA-256

### 4.1 B2 新增生产代码

| 文件 | SHA-256 | 对应任务 |
|---|---|---|
| `backend/app/services/attachment_validation.py` | `57408668ff806cb5a1b61e418388962192ef8173441b500a9a25eef6c6304c21` | B2-T01 |
| `backend/app/services/attachments.py` | `2e37b0495b67afa93a561155cee67340e34da7c117529ff64eb8cbe7d9fe806b` | B2-T02a |
| `backend/app/api/routes/attachments.py` | `489edacdaf01c546e9cc21f26befb92d4aba697a1a5a55c68809b0c6696bc2c6` | B2-T02b |

### 4.2 B2 修改生产代码

| 文件 | SHA-256 | B2 修改范围 |
|---|---|---|
| `backend/app/api/schemas.py` | `d254590f36ae8ac02d50fe5cd86d1feb6e68d72f96bbb134ba8e37fae8219f1d` | `AttachmentUploadIn`、`AttachmentOut` |
| `backend/app/dependencies.py` | `78f8d396a37a7c8eb3d85887e1b7204b68b02b6aa9e796ea626c34dec973d34c` | `get_attachment_service` |
| `backend/app/main.py` | `b77ed4198094df1d6609123161219370ecb67aff33e2e185e0f7a7374adc803b` | 四处 B2 装配，见 §3 |

### 4.3 B2 新增测试

| 文件 | SHA-256 | 数量 |
|---|---|---|
| `backend/tests/test_attachment_api.py` | `93aa6df815c6d41b428156bc9b789bc9c27a3f871fae45fb5b3a1169e4ba2cea` | 22 项 |
| `backend/tests/test_attachment_validation.py` | `1494f0eb6dfad9eb361ca94815c2d28c94b75a8861a50448ee22e5783d132e7e` | B2-T01 专项 |

### 4.4 文档（非生产代码）

- `MILESTONES.md`：B1 PASS 与 B2 状态记录。
- `docs/acceptance/V2-A1-04-Batch-B-B2-task-list.md`、`...-B2-T01.md`。
- `docs/audit/V2-A1-04-Batch-B-B2/`：本审核包。

## 5. 差异文件索引与准确含义

| 文件 | 含义 | 是否 B2-only |
|---|---|---|
| `code-review/diffs/working-tree-tracked-vs-HEAD-970c0d8.patch` | 所有**已跟踪**文件相对 Batch A HEAD 的机械差异；含 B1-final 的 `config.py`、`session.py`、`repositories_v2.py`、`main.py` B1 块及 B2 | 否 |
| `code-review/diffs/main-b2-only.patch` | 重建 B1-final `main.py` → 当前 `main.py`；仅四处 B2 装配 | 是 |
| `code-review/diffs/b2-schemas-dependencies.patch` | `schemas.py`、`dependencies.py` 的 B2 hunk | 是 |
| `code-review/diffs/b2-new-production-files.patch` | 三个 B2 新生产文件（validation/service/routes）全文新增 diff | 是 |
| `code-review/diffs/b2-new-tests.patch` | 两个 B2 新测试文件全文新增 diff | 是 |
| `code-review/diffs/b2-production.diff` | 以上生产代码差异的合并视图 | 是 |
| `code-review/production-current/` | 六个生产文件 + 两个测试文件的完整当前源码 | 是（当前快照） |
| `evidence/b2-changes.patch` | 早先生成的 B2 变更集合，保留作历史证据 | 是 |
| `evidence/b2-files-sha256.txt` | 早先生成的 B2 哈希清单（已由 `code-review/B2-files.sha256` 更新） | — |

注意：`working-tree-tracked-vs-HEAD-970c0d8.patch` 不包含未跟踪文件（B1 的
`storage_lock.py`、`attachment_storage.py`、B1 测试，以及 B2 新文件）。未跟踪文件清单见
`evidence/git-status.txt`；其完整当前内容见 `code-review/production-current/` 与各
new-file patch。不得把该机械全量 patch 误读为 B2-only。

## 6. 不得混淆的结论

- B1 已验收 ≠ 已提交；B2 基于未提交的 B1-final 工作树。
- B2 没有修改 B1 的存储/锁/仓储实现；若审核发现底层问题，应归入 B1 依赖或
  B5 ORP，而不是记作 B2 新增缺陷。
- B2 的 PostgreSQL HTTP 路径未执行；本边界材料不改变该未验证状态。
- 本包不进行任何提交/推送；停止点为 B2 IMPLEMENTED / PENDING INDEPENDENT REVIEW。