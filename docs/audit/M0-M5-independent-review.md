# ExplainLab V1.0 — M0/M5 独立复审报告

> 性质：V1.0 准入复审（**非 V2 开发**）。本报告由独立复验流程产出，所有结论均基于真实命令运行证据。
> 审计纪律：全程未修改业务代码/迁移/锁定文件/V2 文档，未提交 Git，未安装或升级生产依赖，未解除 M0/M5 门禁，未启动 V2。临时验证均在独立副本（`.tmp/`，gitignore）中进行，原始审计对象保持不变。
> 结论口径：仅 PASS / PARTIAL / FAIL；关键测试未执行则保留 PARTIAL/BLOCKED，不因多数通过自动判 PASS。

---

## 1. 审计对象与版本指纹

| 项 | 值 | 核验方式 |
|---|---|---|
| Git HEAD | `6d91718344ca1bccd3f3971f4fed7fd9576b670d`（`6d91718`） | `git rev-parse HEAD` |
| 分支 | `fix/m0-admission-and-m5-regressions` | `git rev-parse --abbrev-ref HEAD` |
| M0 初始提交 | `2d2b63443a3ba1290aafe03be5f5e3281ffa280f`（`2d2b634`，**存在且未修改**） | `git cat-file -t 2d2b634` → commit；`git show 2d2b634 --stat` |
| 修复 HEAD 提交 | `6d91718`（存在） | `git cat-file -t 6d91718` → commit |
| 提交链 | `2d2b634`(M0)→`a2a8e01`(M1)→`4dcf61b`(M2)→`872db27`(M3)→`d6b29e7`(M4)→`59068e2`(M5/main)→`4557d2e`(修复批次)→`3c9b28b`(哈希补记)→`6d91718`(回填修复/HEAD) | `git log --oneline` |
| 交付包 | `release/ExplainLab-V1.0-remediated-review.zip`（6,350,778 字节，237 条目） | 文件存在 |
| 交付包 SHA-256 | `38ca8575a5699d91b19f4f37ab8579a149e5e778ad9c4129edc3c91f03b4676a` | `hashlib.sha256` 两次复核一致 |
| 旧包 SHA-256（已取代） | `7a143945932018a8fc279f016cc6409410155cf6a3a691f6e04710c130f699cd` | 历史记录 |
| 工具链 | uv 0.13.6；Python 3.11.9；Node v22.23.2；npm 10.9.8 | `uv --version` / `uv run python --version` / `node --version` / `npm --version` |
| PostgreSQL 实例 | 便携 PostgreSQL 16.8（`D:\ExplainLab-pg\pgsql`，数据目录 `D:\ExplainLab-pg\data`，端口 55432，trust 鉴权） | `postgres --version` → 16.8；`psql SELECT version()` |

**ZIP ↔ Git 一致性（强制核验，不一致即停止）**：
- 将 ZIP 解压至独立副本 `.tmp/audit-zip/ExplainLab/`；将 `git archive 6d91718` 导出至 `.tmp/audit-git/`（195 个已跟踪文件）。
- `diff -rq .tmp/audit-zip/ExplainLab .tmp/audit-git -x AUDIT-HANDOFF.md -x explainlab-history.bundle -x git-log.txt` → **退出码 0，无差异**（排除的 3 项为 release 额外移交材料，非源码）。
- 结论：**ZIP 与指定 Git 提交 `6d91718` 完全一致**，审计对象冻结成立。

**审计期间对象未漂移**（复审结束时复核）：
- `git rev-parse HEAD` 仍为 `6d91718…`；`git diff --name-only` 与 `git diff --cached --name-only` 均为 **0**（无任何已跟踪文件改动）。
- `git status --porcelain` 仅含未跟踪项：`docs/plans/V2-batch-A-design.md`、`V2-dependency-selection.md`、`V2-plan.md`、`release/`（`.tmp/` 已 gitignore，不显示）。

---

## 2. M0 逐项复验结果（14 项）

> 命令均在原始审计对象 `D:\ExplainLab` 运行（只读测试，不改代码）；直接迁移/触发器验证在独立临时库 `.tmp/audit-m0.db` 进行。

| # | 项目 | 真实命令 | 退出码 | 关键输出 | 结果 |
|---|---|---|---|---|---|
| 1 | 前端生产构建 | `cd frontend && npm run build` | 0 | vite 8.3.8；index 256.45 kB / gzip 78.26 kB；KnowledgeMap 188.53 kB（懒加载）；graphLayout 1464.73 kB（懒加载，>500 kB 警告）；53 模块 | PASS |
| 2 | 前端全部测试 | `npm run test` | 0 | Vitest 5.1.0；**72 passed（10 文件）** | PASS |
| 3 | Python 全量测试 | `uv run pytest -o addopts="--import-mode=importlib"` | 0 | 收集 279；**262 passed, 17 skipped**（PG 门控跳过），1 warning（Starlette httpx 弃用，无害），37.86s | PASS |
| 4 | Ruff | `uv run ruff check` | 0 | **All checks passed!**（仅 check，未 format） | PASS |
| 5 | SQLite 数据库初始化 | `DATABASE_URL=sqlite:///…/.tmp/audit-m0.db uv run alembic upgrade head` | 0 | SQLiteImpl；0001→0005；`alembic_version=0005_m5_experiments` | PASS |
| 6 | SQLite 全部迁移 | 同上 + `alembic heads` / `history` | 0 | 单一 head `0005_m5_experiments`；链 0001→0002→0003→0004→0005 完整 | PASS |
| 7 | FTS5 索引创建 | 临时库 `sqlite_master` 查询 | 0 | `knowledge_fts` FTS5 虚表（trigram）+ 影子表；触发器 `knowledge_item_ai/au/ad` 存在 | PASS |
| 8 | 历史数据回填 | `test_fts_backfill.py`（4 用例）+ 直接回填 | 0 | 先建知识→执行 0004→不 reindex 直接检索历史命中 | PASS |
| 9 | 重复回填幂等 | `test_fts_backfill.py::…idempotent` + 直接二次回填 | 0 | 重复回填不产生重复索引文档（NOT EXISTS rowid 收敛） | PASS |
| 10 | downgrade→upgrade 历史仍可检索 | `alembic downgrade base`→`upgrade head` + `test_fts_backfill` | 0 | 双向退出码 0；重升级后历史知识仍可检索 | PASS |
| 11 | INSERT/UPDATE/DELETE 触发器同步 | 临时库直接 DML + MATCH | 0 | INSERT 后 3 字 MATCH `知识图` 命中（索引行=1）；UPDATE 后新词 `本体论` 命中、旧词消失；DELETE 后清空 | PASS |
| 12 | Knowledge Core 独立调用 | 干净子进程仅置 `knowledge-core/src` 于 path | 0 | `extract_json` 纯函数正确；失败契约分类正确；`WEB_FRAMEWORK_MODULES_LOADED=[]`；`CORE_INDEPENDENT_OK` | PASS |
| 13 | API 健康检查 | 临时库起 uvicorn + `curl /api/health`（ok 与 degraded 两态） | 0 | ok：HTTP 200 `status=ok, database.connected=true, dialect=sqlite`；degraded：HTTP 200 `status=degraded, error=database_unavailable`，响应无密码/主机/异常文本 | PASS |
| 14 | 新环境依赖安装与启动 | 独立干净副本 `.tmp/audit-git`：`uv sync --locked` + `npm ci` + 测试 + 构建 + 迁移 + 起服务 | 0 | 见 §7；干净副本 262/17、72、构建一致、迁移 0001→0005、`curl /api/health` HTTP 200 ok | PASS |

**第 11 项 trigram 说明（非缺陷）**：FTS5 trigram 分词要求 ≥3 字符 token。直接验证中 2 字查询 `图谱` 经 MATCH 返回空属预期行为，由已记录的「短查询 LIKE 回退」处理（AGENTS.md ZIP-01）；3 字查询 `知识图`/`本体论` 正常命中，证明触发器同步真实有效。`test_retrieval_db.py::test_fts_trigram_chinese_and_trigger_sync` 通过。

**第 13 项 degraded 复现说明**：首次用不可达 PG URL（缺省长连接超时）起服务时启动等待较久；改用与测试一致的 `connect_timeout=1` 后，lifespan 正确捕获异常、记录脱敏告警、完成启动并返回 degraded。健康端点本身始终返回稳定错误码，不外泄底层异常。

---

## 3. M5 逐项复验结果（回归审计）

| 回归项 | 核验 | 证据 | 结果 |
|---|---|---|---|
| ZIP-01：PG 迁移误生成 SQLite 专用 FTS5 SQL | 源码 + 真实 PG 迁移 | `0004_m3_retrieval.py` 按 `op.get_bind().dialect.name` 分派：PG 执行 `PG_FTS_DDL+PG_FTS_BACKFILL`，SQLite 执行 `FTS_DDL+FTS_BACKFILL`，其余 ValueError。真实 PG 迁移（PostgresqlImpl）创建 `knowledge_fts(item_id varchar, tsv tsvector)` + GIN 索引，**无 FTS5 虚表/影子表**。`PostgresFullTextIndex` 实际 SQL 用 `to_tsvector/plainto_tsquery/ts_rank/@@/ILIKE`，FTS5/MATCH/bm25/rowid 仅出现在注释 | FIXED |
| ZIP-02：根级 pytest 同名模块收集失败 | 配置 + 收集运行 | `pyproject.toml`：`testpaths=["backend/tests","knowledge-core/tests"]`（未排除任何目录）、`addopts="-q --import-mode=importlib"`、`pythonpath=["knowledge-core/tests"]`。同名模块 `test_graph.py` 确存在于两目录。`pytest --collect-only` → **279 tests collected，无 import file mismatch**，退出码 0 | FIXED |
| SQLite 不受影响 | 默认套件 | 262 passed / 17 skipped；FTS5 trigram + 触发器 + 回填测试通过 | PASS |
| PG 不受影响 | 真实 PG 套件 | 279 passed（含 17 PG）；见 §5 | PASS |
| 全量测试正常收集 | collect-only | 279 collected，退出码 0 | PASS |
| 两库测试可分别运行 | 分目录运行 | `backend/tests` 单独：126 passed, 17 skipped；`knowledge-core/tests` 单独：136 passed（126+136=262，+17 PG=279） | PASS |
| 无新增迁移回归 | heads/history + 双向迁移 | 单一 head 0005，无分支；SQLite 与 PG 均 upgrade/downgrade/upgrade 退出码 0；PG 门控未设 URL 时 17 跳过（默认套件不受影响） | PASS |

---

## 4. SQLite 测试证据

- 全量：`uv run pytest -o addopts="--import-mode=importlib"` → **262 passed, 17 skipped, 1 warning in 37.86s**，退出码 0。
- 定向 verbose（`test_fts_backfill` + `test_migrations` + `test_health` + `test_retrieval_db`）→ **13 passed**，退出码 0。
  - 回填 4 用例：历史命中 / 幂等 / downgrade-upgrade 仍可检索 / 回填后触发器仍有效。
  - 健康 6 用例：ok / degraded / 供应商配置态 / timeout 稳定码 / unavailable 稳定码 / 不泄露敏感细节。
  - 检索：trigram 中文 + 触发器同步、向量表。
- 直接迁移（临时库 `.tmp/audit-m0.db`）：`upgrade head`（0001→0005）/ `downgrade base` / `upgrade head` 均退出码 0；`alembic_version=0005_m5_experiments`。
- 直接触发器：INSERT→3 字 MATCH 命中（索引行=1）；UPDATE→新词命中旧词消失；DELETE→清空；`TRIGGER_SYNC_OK`。
- 干净副本复现：262 passed / 17 skipped（与原始一致），ruff All checks passed。

---

## 5. PostgreSQL 测试证据（真实 PG 16.8，非 SQLite 替代）

> 实例：便携 PostgreSQL 16.8，端口 55432，trust。`EXPLAINLAB_PG_TEST_URL=postgresql+psycopg://postgres@127.0.0.1:55432/explainlab_test`。
> 启动：`pg_ctl start -D D:/ExplainLab-pg/data -o "-p 55432" -w`（退出码 0，PID 27288）；`psql SELECT version()` → PostgreSQL 16.8。

| # | 项目 | 真实命令/测试 | 退出码 | 关键输出 | 结果 |
|---|---|---|---|---|---|
| 1 | 全新 PG 迁移 | 新建 `explainlab_audit` 库 + `alembic upgrade head` | 0 | PostgresqlImpl，事务 DDL，0001→0005；`test_pg_migration_creates_native_fts` PASSED | PASS |
| 2 | tsvector 索引 | `psql information_schema/pg_indexes` | 0 | `knowledge_fts(item_id character varying, tsv tsvector)`；`knowledge_fts_tsv_idx USING gin(tsv)`；FK `confdeltype=c`（CASCADE）；触发器 ai/au | PASS |
| 3 | 历史数据回填 | 直接 `PG_FTS_BACKFILL` + `test_pg_migration_backfills_historical_items` | 0 | 历史知识入索引；tsvector MATCH `ontology` 命中历史项 | PASS |
| 4 | 中文知识检索 | 直接 ILIKE + `test_pg_cjk_substring_fallback` / `test_pg_cjk_history_backfill_searchable` | 0 | `content ILIKE '%知识图谱%'` JOIN 索引命中；`simple` 分词不对无空格中文成词→ILIKE 回退（真实匹配，已记录局限） | PASS |
| 5 | 重复回填幂等 | 直接二次 `PG_FTS_BACKFILL` + `test_pg_backfill_idempotent` | 0 | 两次回填后行数均=1（`ON CONFLICT(item_id)` 收敛），IDEMPOTENT=True | PASS |
| 6 | downgrade→upgrade | 直接 `downgrade 0003`→`upgrade head` + `test_pg_downgrade_upgrade_keeps_history_searchable` / `test_pg_migration_downgrade_and_upgrade` | 0 | 拆索引保留知识数据→重建+回填；items=fts=1，tsv `historical` 命中=1，CJK 命中=1 | PASS |
| 7 | INSERT/UPDATE/DELETE 触发器 | 直接 DML + `test_pg_insert_trigger…` / `…update_trigger…` / `…delete_cascades_fts` / `…triggers_still_work_after_backfill` | 0 | INSERT 索引行=1；UPDATE 旧词 `ontology` 消失（tsv 刷新）；DELETE 级联索引行=0 | PASS |
| 8 | PG 全量测试 | `EXPLAINLAB_PG_TEST_URL=… uv run pytest -o addopts="--import-mode=importlib"` | 0 | **279 passed, 1 warning in 38.05s**（262+17 PG，0 跳过）；PG 模块 verbose **17 passed** | PASS |
| 9 | SQLite/PG 查询行为差异 | `build_full_text_index` 分派 + 两库行为对比 | 0 | SQLite→`SQLiteFullTextIndex`，PG→`PostgresFullTextIndex`，向量双方言均 `JsonVectorStore`；`test_pg_dialect_dispatch` PASSED。差异：SQLite trigram ≥3 字 + 短查询 LIKE 回退；PG simple tsvector 英文命中 + 无空格中文 ILIKE 回退；PG 返回 `-ts_rank` 与 SQLite bm25「越小越相关」契约一致 | PASS |
| 10 | 数据库连接失败错误处理 | 不可达 PG URL 起服务 + `curl /api/health` + `test_health_timeout/unavailable` | 0 | degraded：`error=database_unavailable`（稳定码），响应/健康日志无密码/主机/DSN/异常文本；timeout→`database_timeout` | PASS |

**PG 17 项测试清单（全部 PASSED）**：migration_creates_native_fts / migration_downgrade_and_upgrade / insert_trigger_and_tsvector_search / update_trigger_refreshes_tsv / delete_cascades_fts / upsert_and_remove_backfill / cjk_substring_fallback / vector_store_cosine / indexer_reindex_all_backfill / sync_index_and_remove / hybrid_search_end_to_end / dialect_dispatch / migration_backfills_historical_items / backfill_idempotent / downgrade_upgrade_keeps_history_searchable / cjk_history_backfill_searchable / triggers_still_work_after_backfill。

**UPDATE 触发器中文说明（非缺陷）**：直接验证中 UPDATE 后以 `to_tsquery('simple','分布式')` 查无空格中文新词返回 0，属 PG `simple` 分词局限（已成记录），tsv 刷新由「旧词 ontology 消失」证实；中文新词经 ILIKE 回退真实命中。`test_pg_update_trigger_refreshes_tsv` 通过。

---

## 6. 前端 + 后端测试结果

| 套件 | 命令 | 退出码 | 结果 |
|---|---|---|---|
| 后端 + 核心（默认 SQLite） | `uv run pytest -o addopts="--import-mode=importlib"` | 0 | 262 passed, 17 skipped |
| 后端 + 核心（含真实 PG） | 同上 + `EXPLAINLAB_PG_TEST_URL` | 0 | 279 passed |
| 后端单独 | `uv run pytest backend/tests …` | 0 | 126 passed, 17 skipped |
| 核心单独 | `uv run pytest knowledge-core/tests …` | 0 | 136 passed |
| Ruff | `uv run ruff check` | 0 | All checks passed! |
| 前端测试 | `npm run test` | 0 | 72 passed（10 文件） |
| 前端类型检查 | `npm run typecheck`（tsc -b） | 0 | 通过 |
| 前端构建 | `npm run build` | 0 | index 256.45 kB / gzip 78.26 kB；懒加载分包；graphLayout >500 kB 警告（仅地图打开时加载） |

---

## 7. 新环境安装结果（独立干净副本，从零安装）

> 副本 `.tmp/audit-git/`（`git archive 6d91718` 导出）：核验**无预存 `.venv`、无 `node_modules`、无 `.git`**，含 `uv.lock`/`frontend/package-lock.json`/`pyproject.toml`。原始审计对象环境未被复用或改动。

| 步骤 | 命令 | 退出码 | 关键输出 |
|---|---|---|---|
| Python 锁定安装 | `uv sync --locked` | 0 | 全新 `.venv`，按 lock 安装（psycopg 3.3.9、sqlalchemy 2.1.8、pydantic 2.14.3、fastapi/starlette、pytest 9.2.0、ruff 0.17.4 等） |
| Python 全量测试 | `uv run pytest -o addopts="--import-mode=importlib"` | 0 | **262 passed, 17 skipped**（与原始一致） |
| Ruff | `uv run ruff check` | 0 | All checks passed! |
| 前端锁定安装 | `cd frontend && npm ci` | 0 | 全新 node_modules（报告 6 high 漏洞，均为 dev 依赖，见 §9） |
| 前端类型检查 | `npm run typecheck` | 0 | 通过 |
| 前端测试 | `npm run test` | 0 | 72 passed（10 文件） |
| 前端构建 | `npm run build` | 0 | index 256.45 kB / gzip 78.25 kB（与原始一致） |
| 迁移 | `DATABASE_URL=sqlite:///…/.tmp/audit-clean.db uv run alembic upgrade head` | 0 | 0001→0005 |
| 启动 + 健康 | 干净副本起 uvicorn + `curl /api/health` | 0 | HTTP 200 `status=ok, database.connected=true, dialect=sqlite`；`model_adapter=not_configured`（副本无 `.env`，如实未配置） |

结论：**新环境可从零独立安装、迁移、启动并通过全部测试**，结果与原始环境一致，可复现。

---

## 8. Core 独立性结果

| 项 | 证据 | 结果 |
|---|---|---|
| 独立性守护测试 | `knowledge-core/tests/test_interfaces.py`（6 用例）含 `test_core_has_no_web_framework_dependency`：干净子进程导入全部核心模块，断言不含 fastapi/starlette/flask/django → PASSED | PASS |
| 脱离前后端独立调用 | 干净子进程仅置 `knowledge-core/src` 于 `sys.path`（不含 backend/frontend）：`parsing.extract_json` 正确解析围栏 JSON；导入后 `sys.modules` 无 fastapi/starlette/flask/django/sqlalchemy；`CORE_INDEPENDENT_OK` | PASS |
| Nesti 模拟调用 | 适配器 docstring 明示「通用能力，可复用于 Nesti；base_url/api_key/model 由调用方注入，不读环境变量、不替换代理」；独立纯核心调用成功，证明核心可被外部宿主（Nesti）经端口注入复用 | PASS |
| 依赖方向 | 核心仅标准库 + Pydantic + httpx；无 Web/ORM/前端 import；backend 经 ports Protocol + ModelAdapter 驱动核心 | PASS |

---

## 9. 安全审查结果

| 项 | 证据 | 结果 |
|---|---|---|
| Model Adapter 失败契约 | 直接验证 `is_retryable`：可重试 ModelTimeoutError/ProviderUnavailableError/RateLimitError=True；不可重试 AuthenticationError/MalformedResponseError/CapabilityNotSupportedError/基类=False；`test_model_adapter_contract`（14 用例）通过 | PASS |
| 能力声明诚实 | `capabilities()` 仅 `{GENERATE, EMBED}`；源码无 `ModelCapability.STREAM` 虚假声明 | PASS |
| 直连无代理 | `OpenAICompatibleAdapter`：`base_url.rstrip("/")` 原样直连，`trust_env=False`（不读 HTTP(S)_PROXY/ALL_PROXY），docstring 明示不替换代理地址 | PASS |
| 健康端点脱敏 | live ok/degraded 响应均无密码/用户名/主机/端口/DSN/异常类型/Traceback；`test_health_error_does_not_leak_sensitive_details` 断言 7 类敏感串均不出现 → PASSED；健康日志仅记异常类型（`异常类型=OperationalError`） | PASS |
| SecretStr 掩码 | 以**假密钥 DUMMY**（非真实密钥）验证：`model_dump_json`/`repr` 输出 `**********`，无明文；`get_secret_value()` 取值正确；`SECRET_MASKING_OK` | PASS |
| 密钥不入库/不进包 | `backend/.env` **未被 Git 跟踪**（`git ls-files backend/.env` 为空），已 gitignore，Git 历史无 `.env` 提交；ZIP 内无 `.env`/`*.db`/`node_modules`/`.venv`/`data/`（仅 `.env.example` 模板）；`SENSITIVE_ENTRIES_IN_ZIP=NONE` | PASS |
| 前端不持有密钥 | `frontend/src` 扫描无 api_key/secret/sk-… 等密钥字段；前端只经 HTTP 与后端通信 | PASS |
| 依赖版本锁定 | `uv.lock`、`frontend/package-lock.json`、各 `pyproject.toml` 均被 Git 跟踪，工作树无漂移；`uv sync --locked` + `npm ci` 成功 | PASS |
| 错误日志脱敏 | 健康端点日志仅异常类型；**观察项（LOW）**：启动 lifespan `main.py:42` 用 `exc_info=True` 打印完整 traceback——本次不可达 PG 运行中未出现密码/主机/DSN（扫描 NO_LOG_LEAK），但其他失败模式（如密码认证失败）理论上可能回显连接细节。建议加固为仅记异常类型 | PASS（附 LOW 建议） |
| 新环境可复现 | 见 §7，干净副本从零安装/测试/启动一致 | PASS |

**供应链观察项（LOW）**：`npm ci`/`npm audit` 报告 **6 high severity vulnerabilities**，全部位于 **dev 依赖**（vitest/vite/@vitejs/plugin-react → picomatch/tinyglobby）；`npm audit --omit=dev` → **found 0 vulnerabilities**（生产依赖无漏洞）。属开发工具链公告，无生产运行时暴露。建议择机升级 dev 工具链；**审计期间未执行任何修复/升级**（遵守纪律）。

---

## 10. BLOCKED / PARTIAL / FAIL 项汇总

| 类别 | 项 | 说明 |
|---|---|---|
| BLOCKED | 无 | 真实 PostgreSQL 16.8 实例可用并已运行全部 10 项 PG 复验，未以 SQLite 替代 |
| FAIL | 无 | 14 项 M0、10 项 PG、M5 回归、独立性、安全均通过 |
| PARTIAL | 无 | 所有关键测试均已真实执行 |
| 观察项（LOW，非阻断） | 启动日志 `exc_info=True` | 条件性泄露风险，本次未观测到敏感串；建议加固（§9） |
| 观察项（LOW，非阻断） | npm dev 依赖 6 high 公告 | 生产依赖 0 漏洞；建议择机升级 dev 工具链（§9） |
| 已记录局限（非缺陷） | PG `simple` 中文分词 | 无空格中文不成词→ILIKE 子串回退（真实匹配）；真正中文分词需 zhparser/pg_jieba（新依赖，留待批准） |
| 已记录局限（非缺陷） | elkjs graphLayout 1464.73 kB >500 kB | 懒加载，仅打开知识地图时加载，初始包不受影响 |
| 已记录局限（非缺陷） | JsonVectorStore | JSON 文本 + Python 余弦，双方言通用，不依赖 pgvector；大规模性能有限（设计选择） |
| 已记录局限（非缺陷） | PG 便携 16.8 非生产部署 | 生产部署/鉴权/打包属 V1.0 之后，不在本轮 |

---

## 11. 缺陷严重度与修复建议

> 本轮未发现阻断性缺陷（无 FAIL）。以下为非阻断加固建议，**审计期间未实施任何修复**，仅供后续批准执行。

| 编号 | 严重度 | 位置 | 现象 | 修复建议 |
|---|---|---|---|---|
| OBS-1 | LOW | `backend/app/main.py:42`（lifespan 默认空间初始化告警） | `logger.warning(..., exc_info=True)` 打印完整 traceback；本次不可达 PG 未泄露敏感串，但密码认证失败等模式理论上可能回显 DSN/主机 | 与健康端点一致，改为仅记异常类型名（`type(exc).__name__`），去除 `exc_info=True` 或过滤敏感字段 |
| OBS-2 | LOW | `frontend` dev 依赖（vitest/vite/plugin-react 传递 picomatch/tinyglobby） | npm audit 6 high（dev-only）；生产依赖 0 漏洞 | 择机升级 dev 工具链并同步 `package-lock.json`；升级前评估 breaking change，不在审计/修复批次擅自升级 |
| LIM-1 | 局限（非缺陷） | PG 全文检索 | `simple` 分词不对无空格中文成词 | 如需原生中文分词，引入 zhparser/pg_jieba（**新依赖，须先批准**）；当前 ILIKE 回退为如实记录的真实匹配 |
| LIM-2 | 局限（非缺陷） | 前端知识地图懒加载块 | graphLayout 1464.73 kB >500 kB 警告 | 已懒加载，初始包不受影响；如需可进一步拆分 elkjs，非阻断 |

---

## 12. 最终准入结论

**结论：PASS**

判定依据（全部基于真实运行证据，非多数通过自动判定）：
1. **M0 准入满足**：14 项逐项复验全部 PASS（前端构建/测试、Python 全量、Ruff、SQLite 初始化/全迁移/FTS5/回填/幂等/双向迁移/触发器、Core 独立调用、API 健康、新环境安装启动）。
2. **M5 回归缺陷已修复**：ZIP-01（PG 迁移方言分派，真实 PG 创建原生 tsvector，无 FTS5 SQL）与 ZIP-02（importlib 根级收集 279 无冲突）均 FIXED；SQLite/PG 互不影响；两库测试可分别运行；无新增迁移回归（单一 head 0005，双向迁移可逆）。
3. **历史回填真实可靠**：SQLite（NOT EXISTS rowid 收敛）与 PG（ON CONFLICT item_id 收敛）双方言幂等回填，先建知识→迁移→不 reindex 直接检索历史命中；downgrade→upgrade 后历史仍可检索；回填后 INSERT/UPDATE/DELETE 触发器仍有效。
4. **SQLite 与 PostgreSQL 均正确运行**：默认 SQLite 262 passed/17 skipped；真实 PG 16.8 279 passed（17 PG 全通过），10 项 PG 复验全 PASS，未以 SQLite 替代。
5. **新环境可独立安装/启动**：独立干净副本从零 `uv sync --locked` + `npm ci` + 测试 + 构建 + 迁移 + 起服务 + 健康检查全部通过，结果与原始一致。
6. **独立性与安全达标**：核心脱离前后端独立可用（守护测试 + 直接调用），Nesti 复用成立；失败契约清晰、能力诚实、直连无代理；健康脱敏、SecretStr 掩码、密钥不入库/不进包/不进前端、依赖锁定均验证通过。

**保留意见（非阻断）**：OBS-1（启动日志 `exc_info=True` 加固）、OBS-2（npm dev 依赖公告）为 LOW 建议；LIM-1/LIM-2 及 PG 便携非生产为已如实记录的局限。上述均不构成 FAIL/BLOCKED/PARTIAL。

**门禁与边界声明**：
- 本复审结论为 **PASS（建议准入）**，但 **M0/M5 门禁是否解除由独立审计裁定**；本复审**不解除门禁**。
- 全程遵守审计纪律：未修改业务代码/迁移/锁定文件/V2 文档，未提交 Git，未安装或升级生产依赖，未启动 V2，未进入 M1 之后新里程碑。
- 架构红线核验通过：核心无 Web/前端依赖、业务无方言 SQL（差异封装于 `app/db/fts.py` + `app/services/retrieval.py`）、未删有效测试、M0 初始提交 `2d2b634` 完整保留、未擅自加大依赖、未用假数据/虚报 PG/离线 SQL 冒充真实验证。
- **完成后停止，等待独立审计复核，不进入 V2 开发。**

---

### 附：可复现命令速查

```bash
# 默认 SQLite 全量（PG 门控跳过）
uv run pytest -o addopts="--import-mode=importlib"     # 262 passed, 17 skipped
uv run ruff check                                       # All checks passed
cd frontend && npm run test && npm run typecheck && npm run build && cd ..   # 72 passed

# 真实 PostgreSQL（便携 16.8，端口 55432）
# 启动：pg_ctl start -D D:/ExplainLab-pg/data -o "-p 55432" -w
export EXPLAINLAB_PG_TEST_URL="postgresql+psycopg://postgres@127.0.0.1:55432/explainlab_test"
uv run pytest -o addopts="--import-mode=importlib"     # 279 passed

# 切勿用 -o addopts=""（会关闭 importlib 重新引发 ZIP-02 收集冲突）
```