# V2 Batch A1-01 数据模型与迁移 — 实施与验证记录

> 日期：2026-11-18 ｜ 基线 HEAD：`6d91718`（M0 初始提交 `2d2b634` 保留）
> 依据：`docs/plans/V2-batch-A-design.md` §2.1（A1-T1/T2/T6/T7）、§2.2.1、§2.2.2
> 状态：**A1-01 已实现并真实验证通过**；A1-02～A1-06 未开始。改动尚未提交 Git（等待提交指示）。

## 1. 本子任务范围

只做「数据模型与迁移」：Core 实体增量 + 仓库端口契约 + ORM + 迁移 0006（双方言 additive）+ 真实测试。
**不含** Markdown 编解码、链接解析/规范化实现、导入导出服务、API、前端（分别属 A1-02～A1-06）。

对应设计任务：A1-T1（实体）、A1-T2（端口，MarkdownCodec/Hash 留待 A1-02）、A1-T6（独立性守护扩展）、A1-T7（ORM + 迁移 0006）。

## 2. 改动文件清单（8 改 4 增，无任何无关模块）

| 文件 | 类型 | 内容 |
|---|---|---|
| `knowledge-core/src/knowledge_core/domain/entities.py` | 改（增量） | `KnowledgeItem.tags/extra_metadata`；新增 `LinkResolution`/`KnowledgeLink`/`Attachment`/`TagChangeRecord`/`GcStatus`/`GcTask`/`ImportOrigin`/`StorageLease`；常量 `CANONICALIZATION_VERSION=1`、`LINK_NORMALIZATION_VERSION=1` |
| `knowledge-core/src/knowledge_core/domain/__init__.py` | 改（增量） | 导出上述新实体/枚举/常量 |
| `knowledge-core/src/knowledge_core/ports.py` | 改（增量） | 新增 7 个 Protocol 端口：`LinkRepository`/`AttachmentRepository`/`TagRepository`/`TagChangeLogRepository`/`GcTaskRepository`/`ImportOriginRepository`/`StorageKeyLock` |
| `knowledge-core/tests/test_interfaces.py` | 改（加强） | 独立性守护子进程新增导入 `knowledge_core.domain.entities` 与 `knowledge_core.ports`（此前 ports 未被守护覆盖） |
| `backend/app/models.py` | 改（增量） | `KnowledgeItemORM` 增 `extra_metadata`(Text NOT NULL default/server_default `{}`) + `source_payload_hash`/`source_content_hash`/`source_instance_id`(String(64) nullable)；新增 8 个 ORM 表 |
| `backend/alembic/versions/0006_v2_markdown_kb.py` | 增 | 双方言 additive 迁移（up/down） |
| `backend/tests/test_migrations.py` | 改（加强） | head 断言 `0005`→`0006`、表集合加 8 张新表（旧表断言全部保留）；新增「增量列」与「downgrade→upgrade 且 FTS 触发器/rowid 不坏」两用例 |
| `backend/tests/test_v2_entities.py`（core） | 增 | 54 个 Core 实体/端口契约用例 |
| `backend/tests/test_v2_models.py` | 增 | 33 个真实 SQLite 用例 |
| `backend/tests/test_v2_models_pg.py` | 增 | 24 个真实 PostgreSQL 用例（`EXPLAINLAB_PG_TEST_URL` 门控） |
| `backend/tests/test_fts_backfill.py` | 改（夹具适配） | 历史数据插入改用旧列集合裸 SQL（见 §6） |
| `backend/tests/test_retrieval_pg.py` | 改（夹具适配） | 同上（见 §6） |

**未改动**：任何 V1 服务/API/schema/前端代码；`uv.lock`、`pyproject.toml`、`package.json`、`package-lock.json`（`git diff --name-only` 对这些路径返回 0 条）。**新增依赖：0**。

## 3. 设计安全机制落地情况（A1-01 应落地部分）

| 机制 | 落地形态 | 状态 |
|---|---|---|
| 稳定 ID | 沿用 UUID `String(36)`；`knowledge_link.target_item_id` 绑定稳定 ID，`tag_change_log.item_id_snapshot`、`import_origin.source_document_id` 固化身份 | ✅ 已建表并测试 |
| `normalized_link_key` | `String(1024) NOT NULL` + `UNIQUE(source_item_id, normalized_link_key)`，修复原 `(source,target_title,alias)` 因 alias nullable 导致 NULL≠NULL 的唯一失效 | ✅ 双方言真实约束测试 |
| `link_normalization_version` | `Integer NOT NULL`，ORM/实体默认 1；原始 `target_title`/`alias` 独立保留，规范化不覆盖原文 | ✅ 已建表并测试 |
| `canonicalization_version` | 常量 `CANONICALIZATION_VERSION=1`；`import_origin.source_canonicalization_version Integer NOT NULL` | ✅ 已建表并测试（三 Hash 计算属 A1-02） |
| `ImportOrigin` / `source_payload_hash` / `source_content_hash` / `source_instance_id` | 权威历史表 `import_origin`（含 `import_batch_id`、索引 item_id/source_payload_hash）+ `knowledge_item` 三个冗余列（快速判重） | ✅ 已建表并测试 |
| 标签数据基础 + 留痕 | `tag`(name UNIQUE) / `item_tag`(复合 PK，双侧 CASCADE) / `tag_change_log`（append-only，`item_id` SET NULL + 双快照 + actor/change_source/correlation_id） | ✅ 已建表并测试 |
| GC quarantine | `gc_task.quarantine_path String(512)` / `quarantined_at`；状态机含 `cancelled`（7 态） | ✅ 字段/枚举已落地（Worker 流程属 A1-04） |
| lease / fencing | `gc_task.lease_owner/lease_expires_at/lease_token/attempts/next_retry_at`；`storage_lock(storage_key PK, owner, lease_token, lease_expires_at, locked_at)`；端口 `claim`/`update_task(expected_lease_token)`/`StorageKeyLock.acquire/renew/verify/release` | ✅ 表+端口+真实条件更新/fencing SQL 测试（方言实现属 A1-04） |
| 反向链接数据基础 | `knowledge_link` + `ix_knowledge_link_target_item_id`；端口 `list_backlinks(target_id)` 按稳定 ID | ✅ 改名后反链不断已真实测试 |
| 版本/审核兼容 | 未改 `knowledge_version`/`review_request` 任何结构；`extra_metadata` 为未知 frontmatter 保留位 | ✅ V1 表形状升级前后逐列比对一致 |
| Manifest / operation_id / generation_id / resource_version | 属备份恢复与导入批次（A1-04/A1-T13 设计项），A1-01 不建表 | ⏳ 后续子任务 |
| 三 Hash（content/payload/review） | 计算与包络序列化属 A1-02；A1-01 只落地版本号与持久化列 | ⏳ 后续子任务 |

## 4. 迁移方案（0006，additive，双方言）

**upgrade**：`knowledge_item` 加 4 列（`extra_metadata` 以 `server_default '{}'` 回填，旧行无损）→ 建 8 张表
（`tag`/`item_tag`/`knowledge_link`/`attachment`/`tag_change_log`/`gc_task`/`import_origin`/`storage_lock`）+ 7 个索引。
全部为标准 DDL，无方言特定业务 SQL。

**downgrade**：先删依赖表再删字典表（`item_tag` 先于 `tag`）→ 删 `knowledge_item` 4 列。

**关键工程决策（已在迁移 docstring 记录）**：删列时
- PostgreSQL 走 `op.drop_column`；
- SQLite 走**原生** `ALTER TABLE ... DROP COLUMN`（需 SQLite ≥ 3.35，实测运行环境 3.45.1），低于 3.35 显式报错拒绝降级；
- **刻意不用 `batch_alter_table`**：batch 会重建 `knowledge_item`，丢失 M3 的 FTS5 同步触发器并可能重排 rowid（FTS5 按 rowid 对齐），造成检索损坏。已用真实 SQLite 验证原生 DROP COLUMN 保留触发器与 rowid，并在 `test_migrations.py` 中断言「降级前后触发器集合相同、rowid 不变、降级期间新增条目仍入索引」。

**ORM 关系策略**：新表刻意不在 `KnowledgeItemORM` 上挂 relationship，V1 的加载/删除路径完全不变，清理一律由数据库外键 `CASCADE`/`SET NULL` 承担（SQLite 已 `PRAGMA foreign_keys=ON`）。

## 5. 真实运行证据

环境：Python 3.11.9 / uv 0.13.6 / SQLite 3.45.1；PostgreSQL 16.8 便携实例（`D:\ExplainLab-pg`，端口 55432，库 `explainlab_test`，PID 27288，`pg_ctl status` 确认 running）。
PG 连接串：`postgresql+psycopg://postgres@127.0.0.1:55432/explainlab_test`（经 `EXPLAINLAB_PG_TEST_URL` 注入，真实在线迁移，非离线 SQL）。

| 验证项 | 命令 | 结果 |
|---|---|---|
| Core 实体 + 独立性守护 | `uv run pytest knowledge-core/tests/test_v2_entities.py knowledge-core/tests/test_interfaces.py knowledge-core/tests/test_entities.py -o addopts="--import-mode=importlib"` | **68 passed**（含新增 54） |
| SQLite 迁移 up/down/up | `uv run pytest backend/tests/test_migrations.py -o addopts="--import-mode=importlib"` | **3 passed** |
| SQLite V2 模型/约束 | `uv run pytest backend/tests/test_v2_models.py -o addopts="--import-mode=importlib"` | **33 passed** |
| 真实 PG V2 模型/迁移/降级 | `EXPLAINLAB_PG_TEST_URL=... uv run pytest backend/tests/test_v2_models_pg.py -o addopts="--import-mode=importlib"` | **24 passed** |
| 全量（含真实 PG） | `EXPLAINLAB_PG_TEST_URL=... uv run pytest -o addopts="--import-mode=importlib"` | **392 passed, 0 skipped**（基线 279 + 新增 113，无 V1 用例丢失） |
| 全量（默认 SQLite，PG 门控） | `uv run pytest -o addopts="--import-mode=importlib"` | **351 passed, 41 skipped**（17 V1 PG + 24 V2 PG 正确跳过） |
| Lint | `uv run ruff check` | **All checks passed!**（仅 check，未使用 format） |
| 前端回归 | `npm run test` / `npm run typecheck` / `npm run build` | **72 passed（10 文件）** / tsc 无错 / 构建成功（chunk 体积警告为 V1 既有已记录项） |

### 5.1 真实开发库数据无损验证（在副本上执行，原库未改动）

把真实开发库 `backend/data/explainlab.db`（V1 验收遗留 **8 条知识**，版本 `0005`）复制到系统临时目录后执行真实迁移：

```
BEFORE   version=0005_m5_experiments  items=8  fts=8
UPGRADE  version=0006_v2_markdown_kb  items=8  extra_metadata='{}' 的行=8  source_* 全 NULL 的行=8  fts=8
DOWNGRADE→0005  items=8  新增列仍存在=False（已删除）  触发器=[knowledge_item_ad, knowledge_item_ai, knowledge_item_au]
RE-UPGRADE→0006 items=8  FTS 检索命中=1
```

迁移后对真实历史标题做 FTS5 检索（`知识图谱的定` / `知识图谱的典` / `知识图谱的概`）各命中 1 条。
验证结束后删除临时副本，**原开发库未被修改**。

### 5.2 双方言 schema 一致性

- SQLite：`create_all`（API 测试路径）与 Alembic 迁移路径逐表比对**列名/类型/可空/默认、索引、唯一约束、外键 ondelete、主键列序**完全一致（`test_v2_models.py::test_alembic_and_create_all_schemas_match`）。
- PostgreSQL：真实迁移结果与 ORM 元数据逐列比对（类型以 PG dialect 编译归一），索引/唯一/外键集合一致（`test_v2_models_pg.py::test_migration_matches_orm_metadata`）；并校验 `information_schema` 中 `boolean`/`timestamp with time zone`/`varchar(1024)`/`varchar(64)`/`text` 等真实类型。
- V1 十张表在 0005→0006 前后列/索引/外键**逐项不变**；`knowledge_item` 只增列，旧列定义不变。

## 6. 对 V1 测试夹具的必要适配（透明记录，未弱化任何断言）

`test_fts_backfill.py` 与 `test_retrieval_pg.py` 的历史数据夹具会把库**停在 0003** 再插入「迁移前历史知识」，原先用当前 ORM 仓库写入。0006 给 `knowledge_item` 增列后，当前 ORM 的 INSERT 必然带上新列，无法写入 0003 的旧 schema（真实报错：`table knowledge_item has no column named extra_metadata`）。

处理方式：新增 `_insert_legacy` / `_make_legacy_item`，**按 0003 时期的列集合用裸 SQL 写入**（同样附一条 MANUAL 来源），仅用于历史夹具；升级后的新增条目仍走原 ORM 路径。
理由：历史数据本就由旧版本写入，这样模拟更贴近真实；**所有断言、用例数量、检索词与验证意图完全不变**（回填命中、幂等、downgrade→upgrade、触发器不坏）。两文件各 4/5 个用例全部真实通过。

这是 schema 演进的必然适配，不是掩盖回归：全量 392 passed 中 V1 的 279 个用例一个未少。

## 7. 已知限制与待办（诚实声明）

1. 新增 7 个端口目前**只有契约声明，尚无 backend 实现**（实现属 A1-03/A1-04/A1-08）；`StorageKeyLock` 的 SQLite 租约/PG advisory 方言实现尚未落地，A1-01 只验证了表结构与条件更新/fencing 的真实 SQL 行为。
2. SQLite 降级依赖 ≥ 3.35（原生 DROP COLUMN）；更低版本会显式报错而非静默重建表。运行环境实测 3.45.1。
3. `normalized_link_key` 长度上限 1024 字符；因标题上限 500 字符，PG btree 索引行尺寸在实践范围内（未做超长键压测）。
4. 三 Hash 计算、frontmatter 三态、NFKC 规范化与碰撞处理、导入导出幂等、GC Worker 流程、Manifest/备份恢复、API 与前端**均未实现**，不得视为已完成。
5. `release/` 下的 ZIP/bundle/log 属交接构建产物，**未纳入 Git**（保持 untracked，不提交）。

## 8. Git 范围自检

`git status --short` 显示改动仅落在：Core `domain/`+`ports.py`+两个测试、backend `models.py`+迁移 0006+四个测试文件；新增文档为本记录。
`git diff --name-only -- uv.lock pyproject.toml backend/pyproject.toml knowledge-core/pyproject.toml frontend/package.json frontend/package-lock.json` → **0 条**（零依赖变更、零锁文件漂移）。
未提交任何 `.db`/日志/临时文件/构建产物；未修改 M0 初始提交；未重写历史；未 push。