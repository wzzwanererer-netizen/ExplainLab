# A1-03 阶段级最终审计 · 测试证据索引

> 本索引登记本次阶段审计**真实执行**的每一条命令、退出码、通过/失败/跳过计数与原始输出落盘位置。
> 所有输出均为真实运行结果，非离线推断。环境不可用项一律标 BLOCKED，本次无 BLOCKED 项。
> 证据目录：`docs/audit/V2-A1-03-final-stage-audit/evidence/`（26 个原始输出文件）。
> 采集日期：2026-11-20 / 2026-11-21（跨午夜批次）。

## 0. 环境与基线（先验证环境，再跑测试）

| 项 | 实测值 | 证据文件 | 退出码 |
|---|---|---|---|
| Python | 3.11.9 | `toolchain-baseline.txt` | 0 |
| Node | v22.23.2（符合 `engines.node >= 22.23.2`） | `toolchain-baseline.txt` | 0 |
| uv | 0.13.6 | `toolchain-baseline.txt` | 0 |
| pytest | 9.2.0 | `toolchain-baseline.txt` | 0 |
| PostgreSQL | **16.8**（真实连接，VC++ build 1942, 64-bit），server running PID 50260，port 5432，db `explainlab_test` | `pg-baseline.txt` | 0 |
| PG `knowledge_link` 真实 schema | UNIQUE(source_item_id, normalized_link_key)；ix_target_item_id（反链索引）；source FK ON DELETE CASCADE；target FK ON DELETE SET NULL | `pg-baseline.txt` | 0 |
| Git 分支 / HEAD | `fix/m0-admission-and-m5-regressions` / `784b1248065424e07273b272d6016cc121bc606c` | `git-baseline.txt` | 0 |
| Git 工作树 | 已跟踪文件**干净**（`status --porcelain -uno` 空）；唯一未跟踪 = 本审计交付目录 `docs/audit/V2-A1-03-final-stage-audit/`（按 §XIII 暂不提交） | `git-baseline.txt` | 0 |
| Git 历史 | 18 提交**线性无合并**，父子链完整，M0 初始提交 `2d2b634` 为根（无父）未被改写；**无 upstream = 未 push** | `git-baseline.txt` | 0 |
| Alembic head | 单一 head `0006_v2_markdown_kb`；迁移文件 0001–0006 齐全 | `alembic-baseline.txt` | 0 |
| Alembic current（开发 SQLite 库） | `0005_m5_experiments`（落后 head 一步）——**观察项非缺陷**：测试套件各自建库并迁移至 head，开发库未手动 upgrade | `alembic-baseline.txt` | 0 |
| 依赖锁（Python） | `uv lock --check` → Resolved 41 packages，锁文件与 manifest 一致 | `uv-lock-check.txt` | 0 |
| 依赖锁（前端） | `npm ci --dry-run` → package-lock 与 package.json 一致（未实际重装） | `npm-ci-dryrun.txt` | 0 |

**PG 真实性声明**：本次 PG 全部经 `EXPLAINLAB_PG_TEST_URL=postgresql+psycopg://postgres@127.0.0.1:5432/explainlab_test` 连接**真实 16.8 实例**执行在线迁移与检索/链接验证；`pg-baseline.txt` 含真实 `select version()` 与 `\d knowledge_link` 输出。**非离线 SQL，非假数据。**

## 1. 全量测试矩阵（根级一次性收集 backend + knowledge-core）

命令口径：`uv run pytest -o addopts="--import-mode=importlib"`（保留 importlib，仅去 `-q`；**从未**用 `-o addopts=""`）。

| 套件 | 命令要点 | 通过 | 失败 | 跳过 | 耗时 | 退出码 | 证据文件 |
|---|---|---|---|---|---|---|---|
| SQLite 全量 | 根级，未设 PG env（PG 门控模块整模块跳过） | **930** | 0 | **178** | 147.07s | 0 | `sqlite-full.txt` |
| PostgreSQL 全量 | 根级 + `EXPLAINLAB_PG_TEST_URL`（真实 16.8） | **1108** | 0 | **0** | 162.73s | 0 | `pg-full.txt` |

**计数自洽校验**：930（SQLite 兼容）+ 178（PG 门控）= 1108。设 PG env 后 178 个门控测试全部真实执行、0 跳过，证明 PG 全量是 SQLite 全量的**真实超集**，PG 集成测试确已在线运行。

## 2. 专项套件（按整改批次 / 守护拆分，双方言分别取证）

| 专项 | 测试文件 | 方言 | 通过 | 退出码 | 证据文件 |
|---|---|---|---|---|---|
| A1-01 Core 独立性守护 | `knowledge-core/tests/test_interfaces.py` | — | **14** | 0 | `core-independence-guard.txt` |
| A1-02 冻结契约 | `test_markdown_canonical.py` + `test_markdown_codec.py` + `test_markdown_frontmatter.py` | — | **291** | 0 | `a1-02-frozen.txt` |
| K1 治理链接维护 | `test_governance_links.py` + `test_governance.py` | SQLite | **25** | 0 | `k1-governance-sqlite.txt` |
| K1 治理链接维护 | `test_governance_links_pg.py` | PG | **11** | 0 | `k1-governance-pg.txt` |
| K2 并发窗口控制 | `test_links_concurrency.py` | SQLite | **7** | 0 | `k2-concurrency-sqlite.txt` |
| K2 并发窗口控制 | `test_links_concurrency_pg.py` | PG | **7** | 0 | `k2-concurrency-pg.txt` |
| P2 六字段乐观前置 | `test_links_p2_coverage.py` | SQLite | **8** | 0 | `p2-sqlite.txt` |
| P2 六字段乐观前置 | `test_links_p2_coverage_pg.py` | PG | **9** | 0 | `p2-pg.txt` |
| no-op 步8c 逐行复核 | `test_links_noop_coverage.py` | SQLite | **12** | 0 | `noop-sqlite.txt` |
| no-op 步8c 逐行复核 | `test_links_noop_coverage_pg.py` | PG | **13** | 0 | `noop-pg.txt` |
| Phantom 非碰撞新增 | `test_links_phantom_noncollision.py` | SQLite | **4** | 0 | `phantom-sqlite.txt` |
| Phantom 非碰撞新增 | `test_links_phantom_noncollision_pg.py` | PG | **6** | 0 | `phantom-pg.txt` |
| T22–T40 + HTTP 边界 | `test_links.py` + `test_links_http.py` | SQLite | **110** | 0 | `links-t22-t40-http-sqlite.txt` |
| T22–T40（PG 镜像） | `test_links_pg.py` | PG | **91** | 0 | `links-t22-t40-pg.txt` |

> 专项套件均为全量套件子集，此处单独运行以登记每专项独立计数与退出码。所有专项 0 失败。
> Phantom PG 6 测试中含**真实双连接** `_assert_external_insert_blocked_then_allowed`（空/混合 updates 各一），经 `lock_timeout` 证明 PG 表锁阻断外部非碰撞 INSERT、释放后插入成功。

### 2.1 A1-01 Core 独立性守护（14 测试）构成

- 12 × `test_service_is_abstract`：ExtractionService / RelationService / VersionService / ProvenanceService / RetrievalService / MarkdownCodec / LinkResolver / LinkSyncService / LinkRestoreService / BacklinkService / LinkReresolveService / LinkRebuildService 均为 ABC，直接实例化抛 `TypeError`。
- `test_core_has_no_web_framework_dependency`：**干净子进程**导入全部核心模块（含 `markdown.links` / `markdown.link_service`），断言 `sys.modules` 不含 `fastapi/starlette/flask/django`。
- `test_markdown_package_adds_no_new_third_party_dependency`：markdown包仅 stdlib + Pydantic 栈白名单，**无 PyYAML 等未审批依赖**。

## 3. 质量门禁

| 检查 | 命令 | 结果 | 退出码 | 证据文件 |
|---|---|---|---|---|
| Python Lint | `uv run ruff check`（**仅 check，未 format**） | All checks passed! | 0 | `ruff.txt` |
| 前端单测 | `npm run test`（Vitest） | **72 passed**（10 test files） | 0 | `frontend-vitest.txt` |
| 前端类型 | `npm run typecheck`（`tsc -b`） | 无错误 | 0 | `frontend-typecheck.txt` |
| 前端构建 | `npm run build`（Vite） | ✓ built in 646ms | 0 | `frontend-build.txt` |

## 4. 守护与边界专项核对（源码级，非仅测试名）

| 守护 | 源码位置 | 核对结论 |
|---|---|---|
| Core 无 Web 框架依赖 | `test_interfaces.py:42-92` | 干净子进程导入含 A1-03 模块，通过 |
| markdown 零新增依赖 | `test_interfaces.py:95-123` | 白名单仅 stdlib+Pydantic，通过 |
| 端口纯 Protocol | `knowledge_core/ports.py:7-247` | 仅 import stdlib + domain.entities；`LinkRepository` Protocol 8 方法，无 ORM/Web |
| 三 Hash 确定性 | `markdown/__init__.py:346-452`、`canonical.py:148-158` | content/payload/review 三 Hash + 组件 Hash；`hashes_comparable` 版本门控 |
| 链接键规范化独立于 Hash | `markdown/links.py:7-9` | 明示 Hash 输入仍用原始 Unicode，A1-02 契约不变 |
| 方言 SQL 仅在适配层 | `backend/app/db/locking.py`、`services/links.py`、`db/fts.py` | Core 无方言 SQL；PG 路径无 FTS5/MATCH/bm25/rowid |
| K1 Core 无链接 hook | `knowledge_core/review/`（grep `link\|backlink\|demote\|sync_links\|normaliz` **零命中**） | 链接维护仅在 backend 路由层 → 非 HTTP 调用方绕过为已记录残余风险 |

## 5. 未执行 / 不适用项（诚实登记）

| 项 | 状态 | 说明 |
|---|---|---|
| 干净副本从零安装（无预存 `.venv`/`node_modules`） | **本次未重做** | 本审计复用现有环境验证代码测试/构建通过；依赖锁一致性经 `uv lock --check` + `npm ci --dry-run` 核对。AGENTS.md §7「干净副本验证」属安装宣称前置，本审计不宣称全新安装，仅宣称锁一致 + 现有环境测试/构建通过。 |
| SQLite WAL 多进程边界 | **未启用 WAL，不适用** | 引擎默认 rollback-journal（`session.py` 未设 WAL）；WAL 多进程边界为已记录延后项（见 known-issues C 类）。 |
| SQLite BEGIN IMMEDIATE | **未启用** | `locking.py` 诚实记录：需全局事务控制管线改动，本轮不做；不宣称读阶段已锁保护。 |
| 浏览器截图（链接 UI） | **不适用** | 前端**零链接消费者**（grep 无命中），无链接 UI 可截图；此事实本身即 §VIII 审计结论（未交付用户功能）。 |

## 6. 证据完整性声明

- 26 个原始输出文件均含真实命令 stdout/stderr 与 `EXIT_CODE=` 行。
- 全量与专项**全部 0 失败**；SQLite 178 跳过均为 PG 门控（设 env 后全执行）。
- 无 BLOCKED 项：Python/Node/uv/pytest/真实 PG 16.8 均可用。
- 本索引所有计数直接取自落盘原始输出，未引用聊天摘要或历史报告数字。