# 最终测试报告

- 环境：Windows 10.0.26300（x64）、Python 3.11（uv）、Node v24.22.1、SQLite（开发默认）
- 仓库：`D:\ExplainLab`，HEAD `784b1248065424e07273b272d6016cc121bc606c`
- 原则：每条结论均对应 `evidence/` 内的原始输出；未执行的测试不记为通过；PG 跳过原因如实记录。

## 1. 汇总

| # | 项目 | 命令 | 开始 | 结束 | 结果 | 退出码 | 证据 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P1 专项（P1-01/02/03） | `uv run pytest backend/tests/test_markdown_batch_a_identity.py backend/tests/test_markdown_batch_a_import_conflict.py -o addopts="--import-mode=importlib"` | 11:24:02 | 11:24:22 | 52 passed（既有 36 + 本轮 identity 9 + import_conflict 7） | 0 | `evidence/pytest-p1-item-tests.txt` |
| 2 | P2 专项（P2-01…06） | `uv run pytest backend/tests/test_batch_a_file_write.py backend/tests/test_batch_a_fault_injection.py -o addopts="--import-mode=importlib"` | 11:22:54 | 11:22:59 | 36 passed（R1 13 + 本轮 23） | 0 | `evidence/pytest-p2-fault-tests.txt` |
| 3 | Batch A 聚焦 | 7 个 Batch A 测试文件（见证据首行） | 11:24:38 | 11:25:18 | 166 passed | 0 | `evidence/pytest-batch-a-focus.txt` |
| 4 | 冻结集 A1-02/A1-03/V1 | 14 个治理/链接/Markdown 测试文件 | 11:28:10 | 11:29:25 | 417 passed | 0 | `evidence/pytest-frozen-a1-a2-a3-v1.txt` |
| 5 | 全量 Python（SQLite + Core） | `uv run pytest -o addopts="--import-mode=importlib"` | 11:25:20 | 11:27:59 | **1124 passed, 178 skipped**, 1 warning | 0 | `evidence/pytest-full.txt` |
| 6 | Ruff 全仓 | `uv run ruff check` | 11:24:30 | 11:24:31 | All checks passed | 0 | `evidence/ruff-check.txt` |
| 7 | 前端单测 | `npm run test` | 11:29:29 | 11:29:32 | 10 files / 72 tests passed | 0 | `evidence/frontend-test.txt` |
| 8 | 前端类型检查 | `npm run typecheck` | 11:29:35 | 11:29:36 | 无错误输出 | 0 | `evidence/frontend-typecheck.txt` |
| 9 | 前端构建 | `npm run build` | 11:29:40 | 11:29:42 | built in 679ms（仅 chunk>500kB 警告） | 0 | `evidence/frontend-build.txt` |
| 10 | POSIX 探针（WSL） | `wsl.exe -e bash -lc "... PYTHONPATH=/mnt/d/ExplainLab/backend python3 posix_probe.py"`（全文见证据） | 11:31:21 | 11:31:26 | 9 PASS / 1 UNVERIFIED | 0 | `evidence/posix-probe-run.txt`（首次捕获见 `posix-probe-output.txt`） |
| 11 | PostgreSQL | `EXPLAINLAB_PG_TEST_URL` 未设置 | — | — | **未执行（178 项门控跳过）** | — | `evidence/postgresql-probe.txt` |

注 1：P1 专项 52 = 既有 identity 测试 36 + 本轮 identity 新增 9 + import_conflict 的 7 项（全部为本轮新增）。全量 1124 = 本轮首轮全量（含 8 项重复）1131 − 去重 8 + 本轮净新增 1（39 项新增中有 8 项曾重复，去重后净增 31，再计入 1 项补充用例，见 §4）。

注 2：`pytest-batch-a-focus` 与 `pytest-full` 的 warning 为仓库既有 Pydantic/SQLAlchemy 弃用提示，非新增失败。

## 2. 新增测试逐项执行映射

| 项 | 类 / 数量 | 所在文件 | 包含于 |
| --- | --- | --- | --- |
| P1-01 | `TestMaterializeClassificationBeforeIdentityWrite` / 7 | `test_markdown_batch_a_identity.py` | #1、#3、#5 |
| P1-02 | `TestImportCannotCreateMaterializeConflict` / 7 | `test_markdown_batch_a_import_conflict.py` | #1、#3、#5 |
| P1-03 | `TestRotateMaterializeOriginConflict` / 2 | `test_markdown_batch_a_identity.py` | #1、#3、#5 |
| P2-01 | `TestWriteAllInterrupted` / 3 | `test_batch_a_fault_injection.py` | #2、#3、#5 |
| P2-02 | `TestFsyncFailure` / 5 | `test_batch_a_fault_injection.py` | #2、#3、#5 |
| P2-03 | `TestCloseFailure` / 5 | `test_batch_a_fault_injection.py` | #2、#3、#5 |
| P2-04 | `TestReplaceFailure` / 3 | `test_batch_a_fault_injection.py` | #2、#3、#5 |
| P2-05 | `TestLinkFileExists` / 2 | `test_batch_a_fault_injection.py` | #2、#3、#5 |
| P2-06 | `TestArchiveNoOverwrite` / 5 | `test_batch_a_fault_injection.py` | #2、#3、#5 |

失败/错误：以上各次运行均为 0 failed、0 error。

## 3. 跳过与未验证

- **178 skipped（全量）**：`backend/tests/test_retrieval_pg.py` 等 PostgreSQL 门控测试，因 `EXPLAINLAB_PG_TEST_URL` 未设置整模块跳过。这是环境不具备，不是通过。
- **PostgreSQL**：未执行任何真实 PG 连接、迁移或检索验证；无 docker/podman/psql/pg_ctl/本地服务。见 `postgresql-verification.md`。
- **POSIX**：9 项真实 Linux 原语验证通过；`journal_store_full_import` 因 WSL 无 pip/SQLAlchemy 标记 UNVERIFIED。见 `posix-verification.md`。
- 未使用 SQLite 冒充 PG，未伪造 POSIX 结果，未用 Windows 结果顶替 Linux。

## 4. 测试数量变化说明

- 本轮新增测试 39 项（P1 16、P2 23）。
- 过程中 `test_batch_a_file_write.py` 一度重复追加了 8 项（与 `test_batch_a_fault_injection.py` 的 Interrupted/Fsync 类重复），已移除重复副本，覆盖不减少；该文件最终与第二轮审计快照逐字节一致。
- 因此全量从本轮首轮运行（含重复）1131 passed 变为 1124 passed：−8（去重） +1（新增“不完整 ImportOrigin + MATERIALIZE”用例） = −7。

## 5. 原始证据索引

| 证据文件 | 说明 |
| --- | --- |
| `evidence/pytest-p1-item-tests.txt` | P1 专项原始输出 |
| `evidence/pytest-p2-fault-tests.txt` | P2 专项原始输出 |
| `evidence/pytest-batch-a-focus.txt` | Batch A 聚焦原始输出 |
| `evidence/pytest-frozen-a1-a2-a3-v1.txt` | 冻结契约回归原始输出 |
| `evidence/pytest-full.txt` | 全量套件原始输出 |
| `evidence/ruff-check.txt` | Ruff 原始输出 |
| `evidence/frontend-test.txt` / `frontend-typecheck.txt` / `frontend-build.txt` | 前端三项原始输出 |
| `evidence/posix-probe-run.txt` / `posix-probe-output.txt` / `posix-probe-stderr.txt` / `posix_probe.py` | POSIX 探针（带命令头 / 首次捕获 / stderr / 脚本） |
| `evidence/postgresql-probe.txt` | PG 环境探测（工具/服务/URL 均不可用） |