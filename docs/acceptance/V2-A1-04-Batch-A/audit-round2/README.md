# ExplainLab V2 · A1-04 · Batch A 第二轮独立审计包

- 生成时间：2026-11-22（Asia/Shanghai）
- 范围：仅 P1 身份并存冲突、P2 文件短写整改的审计材料交接
- 状态：**未提交、未暂存、未推送；未进入 Batch B**
- 结论口径：SQLite 范围内通过；真实 PostgreSQL **未验证**

## 0. 审计材料导航

| 要求 | 位置 |
| --- | --- |
| 完整 Git 状态、文件范围区分 | `01-git/` |
| 完整代码（5 个文件，逐字节副本） | `02-code/` |
| 完整整改 diff、P1/P2 调用点前后对照、SHA-256 | `03-diff/` |
| Journal 写入/归档/恢复、PREPARED/COMMITTED、classify 入口 | `04-journal/`（含 P1/P2 专项审计） |
| 本轮新运行的原始测试输出 | `05-tests/` |
| 未完成验证清单 | `06-unverified/` |
| 全包校验 | `SHA-256SUMS` |

## 1. Git 基线

- HEAD：`784b1248065424e07273b272d6016cc121bc606c`
- 分支：`fix/m0-admission-and-m5-regressions`
- 暂存区：空（`git diff --cached` 0 字节）
- 提交/推送：无
- `MILESTONES.md`、设计文档、A1-02/A1-03/V1 契约：未修改
- 迁移/表/列/索引/依赖：未新增

详细内容：

- `01-git/git-state.txt`：HEAD、分支、`git status --porcelain=v2 --untracked-files=all`、
  `git status --short`、diff stat、cached stat
- `01-git/git-diff.patch`：完整已跟踪文件 diff（8 个文件，属更早 Batch A 工作）
- `01-git/git-diff-cached.patch`：空
- `01-git/untracked-files.txt`：全部 untracked 文件
- `01-git/file-mtimes.txt`：关键文件 mtime
- `01-git/scope-classification.md`：本轮整改 / 既有 Batch A / 历史文档的区分

**关键事实**：`source_identity.py`、`source_instance_id.py`、`test_markdown_batch_a_identity.py`
在 Git 中仍是 untracked，`file_write.py`、`test_batch_a_file_write.py` 为本轮新增；
因此不存在 `git diff HEAD` 形式的整改基线。`03-diff/` 的“整改前”是从本轮编辑记录逐条
反向应用重构，并在 `03-diff/README.md` 中明确标注方法。

## 2. 本轮实际改动的 5 个文件

| 文件 | 逻辑行数 | `wc -l` | 字节数 | SHA-256 |
| --- | ---: | ---: | ---: | --- |
| `backend/app/services/source_identity.py` | 987 | 986 | 41868 | `1fd4e2e2d49246e82a71f38e88cbed4ca0fa192a7906b7225f912a8051ec43c1` |
| `backend/app/services/source_instance_id.py` | 170 | 169 | 6364 | `96ae5fe80c46115b95356aaed347865afaff15e5943676b4b65a69f5ddd8de3f` |
| `backend/app/services/file_write.py` | 31 | 30 | 984 | `64dc50821af7ff5f6536494c68570d1499e3c7e0b4123b347577b7388c56bd04` |
| `backend/tests/test_markdown_batch_a_identity.py` | 804 | 803 | 32736 | `055b05a5de5ec743d713ef17a267c6e221b8225a6df52920f1b2be20ebaaf942` |
| `backend/tests/test_batch_a_file_write.py` | 288 | 287 | 10360 | `a9cf54c9663db910f9571fb072dbd0dfc2b3e15ffecec56acd42f4b95598e36d` |

五个文件末尾均无换行，逻辑行数比 `wc -l` 多 1；副本与工作树 `cmp` 均为 0。

完整源码副本在 `02-code/`（`cmp` 与工作树一致）。

## 3. 本轮新运行的测试结果

所有输出文件头记录命令与开始时间，文件尾记录退出码；**未复用历史结果**。

| 范围 | 结果 | 退出码 | 证据 |
| --- | --- | ---: | --- |
| P1 10 项 + P2 13 项 | 23 passed | 0 | `05-tests/23-new-tests.txt` |
| Batch A 聚焦（6 文件） | 155 passed | 0 | `05-tests/batch-a-focus.txt` |
| A1-02/A1-03/V1 冻结回归 | 605 passed | 0 | `05-tests/frozen-and-v1.txt` |
| 根级 SQLite/Core 全量 | 1085 passed, 178 skipped | 0 | `05-tests/pytest-full-sqlite.txt` |
| Ruff | All checks passed | 0 | `05-tests/ruff.txt` |
| 前端 | 72 passed；typecheck/build 通过 | 0 | `05-tests/frontend.txt` |

时间戳：

- 23 项：2026-11-22 03:56:32 +08:00
- 聚焦：2026-11-22 03:56:43 +08:00
- 冻结：2026-11-22 03:57:18 +08:00
- 全量：2026-11-22 03:58:16 +08:00
- Ruff：2026-11-22 04:00:43 +08:00
- 前端：2026-11-22 04:00:44 +08:00

178 skipped 与 PG 门控模块收集数（178）一致，全部因未设置
`EXPLAINLAB_PG_TEST_URL` 而跳过；不是 PG 通过。

## 4. 修复摘要

### P1

- 新增 `_origin_materialize_conflict(snapshot, records)`：
  `import_origin_count > 0 && bool(records)` 即冲突。
- 在 `classify()` 的原状态 1/3 分支之前早退为状态 3；
  `source_instance_id` / `source_document_id` 均为 `None`。
- 覆盖单条/多条完整 origin、残缺、重复、多合法身份对、同/异实例 ID、多条 MATERIALIZE；
  正常导入仍状态 1，正常本地物化仍状态 2b。
- 冲突路径零 DB/Journal 写入，不选可信记录、不合并、不删除、不物化、不修复。

### P2

- 新增 `file_write.write_all`：循环写完全部字节；返回 0 抛 `OSError(EIO)`；
  异常原样传播；支持 `InterruptedError` 重试。
- 接入 Journal current、Journal archive、source-instance-id 创建、fallback、替换，共 5 个调用点。
- fallback 半写失败删除半成品正式文件，绝不留下截断 ID；旧 ID 不被覆盖。
- 保持 `0o600`、临时文件、fsync、`os.replace`/`os.link`、Journal 状态机与 Canonical JSON v1 不变。

## 5. 未验证项（详见 `06-unverified/known-gaps.md`）

- 真实 PostgreSQL：未连接，178 项 PG 门控全部 skip。
- Journal 崩溃矩阵：未穷尽（COMMITTED 写后、archive 后、replace 中、目录 fsync 前、断电等）。
- `fsync` / `close` 故障：未注入。
- POSIX：只在 Windows NTFS 实机验证。
- Uvicorn `--reload` / 多 worker / Windows ACL：未实测。
- 真实 `ENOSPC`、配额、网络盘、断电：未验证。
- P1：未直接测试绕过恢复门的 PREPARED+origin classify、损坏多 MATERIALIZE 组合、跨进程竞争。
- P1：`rotate()` 对状态 3 `continue`，不中止整个 ROTATE（符合计划 1247，但非整体 fail-closed）；
  ImportOrigin + COMMITTED MATERIALIZE 并存冲突在 rotate 下无专项测试。
- P2：未注入 `InterruptedError`、`fsync`/`close`/`os.replace`/`os.link(FileExists)` 失败；
  fallback 在 close 失败时会删除已写正式 ID（fail-closed，未测试）。
- `rotate-instance-id` CLI 未实现；Batch B/C 未做。

上述边界的逐项代码证据与分级见 `04-journal/P1-conflict-and-recovery-audit.md`、
`04-journal/P2-write-and-publish-audit.md`、`06-unverified/known-gaps.md`。
不得将上述项计为通过。

## 6. 生成说明

- 本包只新增文档/副本/原始输出，**未修改任何代码、测试、设计文档、`MILESTONES.md`**。
- 未执行 `git add`、commit、push。
- 测试运行产生的 `.pytest_cache/`、`__pycache__/`、`frontend/dist/` 为构建产物，不是源码改动。
- 全包校验见 `SHA-256SUMS`（不包含该文件自身）。