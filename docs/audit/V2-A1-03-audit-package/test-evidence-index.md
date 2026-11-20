# A1-03 测试证据索引

> 本索引列出本轮**真实重跑**的全部命令、原始输出文件与结果。所有输出落盘于 `evidence/`，审计方可按命令复算。
> 环境：Python 3.11.9 / uv 0.13.6 / SQLite 3.45.1 / 真实 PostgreSQL 16.8（`127.0.0.1:5432`，`explainlab_test`）/ Node 22.23.2。
> Windows 控制台 GBK，Python 命令统一加 `PYTHONIOENCODING=utf-8`（数据本身始终 UTF-8）。
> 命令纪律：根级 pytest **保留 `--import-mode=importlib`**（切勿 `-o addopts=""`，会引发 backend/tests 与 knowledge-core/tests 同名模块收集冲突）；ruff **仅 check，禁 format**。

## 1. 全量回归

| # | 命令 | 结果 | 原始输出 |
|---|---|---|---|
| 1.1 | `PYTHONIOENCODING=utf-8 uv run pytest -o addopts="--import-mode=importlib"` | **887 passed, 132 skipped, 0 failed**（124.49s） | `evidence/pytest-sqlite-full.txt` |
| 1.2 | `EXPLAINLAB_PG_TEST_URL="postgresql+psycopg://postgres@127.0.0.1:5432/explainlab_test" PYTHONIOENCODING=utf-8 uv run pytest -o addopts="--import-mode=importlib"` | **1019 passed, 0 skipped, 0 failed**（124.03s） | `evidence/pytest-pg-full.txt` |
| 1.3 | `uv run pytest backend/tests/test_links_pg.py backend/tests/test_retrieval_pg.py backend/tests/test_v2_models_pg.py -o addopts="--import-mode=importlib" -rs`（**不设** PG URL） | **132 skipped**，原因全部「未配置 EXPLAINLAB_PG_TEST_URL」 | `evidence/pytest-sqlite-pg-gated-skips.txt` |

**口径核验**：

- 1.1 与 1.2 均收集 **1019** 个用例（SQLite：887 通过 + 132 跳过；PG：1019 通过 + 0 跳过），故两文件进度字符数相近、字节数同为 5103，但**汇总行不同**（已 grep 核实）。
- 132 跳过 = `test_links_pg.py` 91 + `test_retrieval_pg.py` 18 + `test_v2_models_pg.py` 23。`-rs` 逐条核实**无意外跳过**（1.3）。
- 净增 334 = 41（Core 纯文本）+ 86（Core 服务）+ 91（SQLite 链接）+ 91（PG 链接）+ 19（HTTP）+ 6（独立性守护扩展）。A1-02 基线 685（PG）→ 1019；SQLite 644 + 243 = 887。**零回归**。
- PG 真实连接：`SELECT version()` = `PostgreSQL 16.8, compiled by Visual C++ build 1942, 64-bit`（`evidence/pg-version.txt`）。**未用 SQLite 冒充 PG**。

## 2. 链接模块逐文件计数

命令（`evidence/pytest-links-modules.txt`）：各文件单独 `uv run pytest <file> -o addopts="--import-mode=importlib"`，PG 文件加 `EXPLAINLAB_PG_TEST_URL`。

| 文件 | 层 | 结果 |
|---|---|---|
| `knowledge-core/tests/test_markdown_links.py` | ① 纯文本 | **41 passed**（0.12s） |
| `knowledge-core/tests/test_markdown_link_service.py` | ② 领域服务 | **86 passed**（0.22s） |
| `backend/tests/test_links.py` | ③ SQLite | **91 passed**（32.79s） |
| `backend/tests/test_links_http.py` | ④ HTTP/TestClient | **19 passed**（6.91s） |
| `backend/tests/test_links_pg.py` | ③ 真实 PG（门控） | **91 passed, 0 skipped**（1.85s） |

合计 328 链接用例 + 6 独立性守护扩展 = 334 净增。

## 3. 冻结 / 守护 / Lint / 环境

命令与结果（`evidence/pytest-a1-02-interfaces-ruff-env.txt`）：

| # | 命令 | 结果 |
|---|---|---|
| 3.1 | `uv run pytest knowledge-core/tests/test_markdown_canonical.py knowledge-core/tests/test_markdown_frontmatter.py knowledge-core/tests/test_markdown_codec.py knowledge-core/tests/test_interfaces.py::test_core_has_no_web_framework_dependency knowledge-core/tests/test_interfaces.py::test_markdown_package_adds_no_new_third_party_dependency -o addopts="--import-mode=importlib"` | **293 passed**（A1-02 冻结子集：291 三冻结文件 74+122+95 + 2 markdown 守护） |
| 3.2 | `uv run pytest knowledge-core/tests/test_interfaces.py -o addopts="--import-mode=importlib"` | **14 passed**（12 ABC 不可实例化 + 2 子进程守护） |
| 3.3 | `uv run pytest "knowledge-core/tests/test_markdown_link_service.py::test_d3_link_repository_signatures_frozen" -o addopts="--import-mode=importlib"` | **1 passed**（10 端口签名冻结） |
| 3.4 | `uv run ruff check` | **All checks passed!**（仅 check，未 format） |
| 3.5 | 环境：`uv run python --version` / `uv --version` / `node --version` / `uv run python -c "import sqlite3;print(sqlite3.sqlite_version)"` | Python 3.11.9 / uv 0.13.6 / node v22.23.2 / SQLite 3.45.1 |
| 3.6 | `git status --porcelain uv.lock frontend/package-lock.json` | **空**（锁定文件零漂移） |

## 4. V1 路由守护

命令：`uv run pytest backend/tests/test_links_http.py -k "router or route or three_gets or endpoint" -o addopts="--import-mode=importlib" -v`（`evidence/v1-route-guard-tests.txt`）

| 测试 | 结果 |
|---|---|
| `test_links_router_is_exactly_three_gets` | **PASSED**（links router 恰 3 GET，无写端点） |
| `test_knowledge_router_endpoint_set_unchanged` | **PASSED**（knowledge router 恰 V1 6 端点集合） |

> 2 passed, 17 deselected。另含 app 中无 `rebuild-keys`/`links/resolve`/`links/reresolve` 写路径的守护断言（在 `test_links_http.py` 内）。

## 5. 前端

命令（`evidence/frontend-test-typecheck-build.txt` + `evidence/frontend-build-full.txt`）：`cd frontend && npm run test && npm run typecheck && npm run build`

| 项 | 结果 |
|---|---|
| `npm run test`（Vitest） | **Test Files 10 passed (10) / Tests 72 passed (72)**（2.85s） |
| `npm run typecheck`（`tsc -b`） | **通过，无错误输出** |
| `npm run build` | **✓ built**；`dist/assets/index-sSXZypjv.js` **256.45 kB（gzip 78.26 kB）**；`index-_zdAirmQ.css` 23.91 kB（gzip 5.41 kB）；`index.html` 0.48 kB |

> index 256.45 kB 与基线**完全一致**（前端零改动，无增量）。graphLayout chunk 1464.73 kB 为既有 elkjs 图布局产物（非本批引入）。

## 6. 完整性 / 未变化证据

| # | 命令 | 结果 | 原始输出 |
|---|---|---|---|
| 6.1 | `sha256sum -c docs/audit/V2-A1-03-baseline/manifest.sha256`（**从仓库根**） | **18 OK + 3 FAILED**（ports.py / test_interfaces.py / markdown/__init__.py，恰为 §4.2 允许） | `evidence/fingerprint-manifest-check.txt` |
| 6.2 | `git diff 5d6dcf1..7e0582c -- knowledge-core/src/knowledge_core/ports.py` | **仅 docstring**（delete_links_of_item D3 澄清），签名不变 | `evidence/ports-py-diff.txt` |
| 6.3 | `git diff --name-only 5d6dcf1..7e0582c -- backend/alembic/` | **空**（无迁移改动） | `evidence/migration-changes.txt` |
| 6.4 | `ls backend/alembic/versions/*.py` | 0001–0006（0006 来自 A1-01，无 0007） | `evidence/alembic-versions-list.txt` |
| 6.5 | `git diff --name-only 5d6dcf1..7e0582c -- uv.lock frontend/package-lock.json frontend/package.json pyproject.toml backend/pyproject.toml knowledge-core/pyproject.toml` | **空**（依赖声明零改动） | `evidence/dependency-file-changes.txt` |

> **6.1 cwd 注意**：manifest 路径相对仓库根，必须从根运行。`cd` 进 baseline 目录再运行会全部报 `FAILED open or read`（路径不匹配的假阳性，编制中曾出现并已纠正；落盘证据为从根运行的正确结果 18 OK + 3 FAILED）。

## 7. Git / diff / T 映射证据

| 文件 | 内容 | 生成命令 |
|---|---|---|
| `evidence/git-commit-chain.txt` | 8 提交父子链 | `git log --format="%h parent=%p %ad %s" --date=short -8` |
| `evidence/git-feat-commit-715d9e7-stat.txt` | feat 提交统计（16 文件 +8517/−6） | `git show --stat --format="%H%n%s" 715d9e7` |
| `evidence/git-docs-commit-7e0582c-stat.txt` | docs 提交统计（2 文件 +286/−21） | `git show --stat --format="%H%n%s" 7e0582c` |
| `evidence/a1-03-full.diff` | 完整 A1-03 delta（9118 行） | `git diff 5d6dcf1..7e0582c` |
| `evidence/a1-03-name-status.txt` | 18 文件 A/M 清单 | `git diff --name-status 5d6dcf1..7e0582c` |
| `evidence/a1-03-diff-stat.txt` | 逐文件行数统计 | `git diff --stat 5d6dcf1..7e0582c` |
| `evidence/t22-t40-function-map.txt` | T22–T40 三文件函数名 grep | `grep -nE "^def test_t(2[2-9]\|3[0-9]\|40)\|^def test_freshness\|^def test_single_source" <三文件>` |

## 8. 证据文件总览（evidence/）

```
git-commit-chain.txt                  git-feat-commit-715d9e7-stat.txt      git-docs-commit-7e0582c-stat.txt
a1-03-full.diff                       a1-03-name-status.txt                 a1-03-diff-stat.txt
ports-py-diff.txt                     migration-changes.txt（空）           alembic-versions-list.txt
dependency-file-changes.txt（空）     fingerprint-manifest-check.txt
pytest-sqlite-full.txt                pytest-pg-full.txt                    pytest-sqlite-pg-gated-skips.txt
pytest-links-modules.txt              pytest-a1-02-interfaces-ruff-env.txt
v1-route-guard-tests.txt              t22-t40-function-map.txt
frontend-test-typecheck-build.txt     frontend-build-full.txt               pg-version.txt
```

> 所有文件均为真实命令输出重定向生成，无手工编辑结果。审计方可按 §1–§7 命令复算比对。