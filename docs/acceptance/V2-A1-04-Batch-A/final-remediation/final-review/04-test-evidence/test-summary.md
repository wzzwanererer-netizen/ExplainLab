# 04-A · 测试与检查证据汇总

- 原则：**复用本轮整改期间已产生的真实结果**，未为凑新数字重跑完整套件。
- 证据原始输出：`../evidence/`（`final-remediation/evidence/`，已由既有 `SHA-256SUMS` 覆盖）。
- 代码状态：自 11:31 证据生成后未再修改；当前 Hash 与 `01-git-state/` 一致。

## 1. 结果总表

| 检查 | 范围 | 结果 | 时间 | 证据 |
| --- | --- | --- | --- | --- |
| 完整后端 + 核心 | 根级 pytest（保留 importlib） | **1124 passed, 178 skipped**，collected 1302，退出 0 | 11:25:20–11:27:59 | `evidence/pytest-full.txt` |
| Batch A 聚焦 | 7 个 Batch A 测试文件 | **166 passed**，退出 0 | 11:24:38–11:25:18 | `evidence/pytest-batch-a-focus.txt` |
| P1 专项 | 身份 45 + 导入冲突 7 | **52 passed**，退出 0 | 11:24:02–11:24:22 | `evidence/pytest-p1-item-tests.txt` |
| P2 专项 | file_write 13 + fault_injection 23 | **36 passed**，退出 0 | 11:22:54–11:22:59 | `evidence/pytest-p2-fault-tests.txt` |
| 冻结套件 | A1-02/A1-03/V1/治理/健康 | **417 passed**，退出 0 | 11:28:10–11:29:25 | `evidence/pytest-frozen-a1-a2-a3-v1.txt` |
| Ruff | `uv run ruff check` | **All checks passed** | 11:24:30–11:24:31 | `evidence/ruff-check.txt` |
| 前端单测 | `npm run test`（Vitest） | **72 passed / 10 files** | 11:29:30–11:29:32 | `evidence/frontend-test.txt` |
| 前端类型 | `npm run typecheck`（tsc -b） | 退出 0 | 11:29:35–11:29:36 | `evidence/frontend-typecheck.txt` |
| 前端构建 | `npm run build` | 退出 0（有 >500 kB chunk 警告） | 11:29:42 | `evidence/frontend-build.txt` |

完整套件的 178 skipped 全部为 PostgreSQL 门控（`EXPLAINLAB_PG_TEST_URL` 未设置），不是失败。

## 2. 失败/异常

- 0 failed、0 error、0 xfail。
- 唯一 warning：FastAPI/Starlette 关于 `httpx` 的弃用提示，与本批无关。
- 前端构建有 chunk 体积警告，不阻断构建。

## 3. 测试与整改项映射

| 整改项 | 测试 | 数量 |
| --- | --- | --- |
| P1-01 | `TestMaterializeClassificationBeforeIdentityWrite` | 7 |
| P1-02 | `TestImportCannotCreateMaterializeConflict` | 7 |
| P1-03 | `TestRotateMaterializeOriginConflict` | 2 |
| P2-01 | `TestWriteAllInterrupted` | 3 |
| P2-02 | `TestFsyncFailure` | 5 |
| P2-03 | `TestCloseFailure` | 5 |
| P2-04 | `TestReplaceFailure` | 3 |
| P2-05 | `TestLinkFileExists` | 2 |
| P2-06 | `TestArchiveNoOverwrite` | 5 |
| 合计 | | 39 新增 + 13 既有 P2 |

P2 专项 36 = `test_batch_a_file_write.py` 13 + `test_batch_a_fault_injection.py` 23。另有 `TestReplaceFailure.test_archive_uses_no_overwrite_link_not_replace` 从 P2-04 侧锁定“归档不再使用 replace”，不重复计入 P2-06。

## 4. 运行环境

- OS：Windows 10.0.26300（x64）
- Python：3.11.9；pytest 9.2.0；pytest-asyncio 1.4.1
- Node：22.x（按 `engines.node >= 22.23.2`）
- DB：SQLite（真实文件库，测试临时目录）；无 PostgreSQL 实例
- 网络/模型：本批测试不调用真实模型；无外部 API 依赖

## 5. 未重跑的项目

- 完整 1124/178、Batch A 166、P1 52、P2 36、417 均为 11:22–11:29 的真实输出；此后仅新增 `final-review/` 文档，未改代码。
- 未重跑 PostgreSQL 门控 178 项（环境无 PG）。
- 未重跑 WSL POSIX 探针（结果见 `04-B`）。

## 6. 判定

在**当前支持的单进程 SQLite/Windows 环境**下，上述检查全部通过；这不等于 PostgreSQL、POSIX 完整事务、断电持久性已通过。相关缺口见 `verification-gaps.md`。