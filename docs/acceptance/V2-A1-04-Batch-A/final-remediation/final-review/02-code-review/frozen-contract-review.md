# 02-E · 冻结契约未变更复核

- 结论：本批整改**未修改** A1-02 Core Hash / Canonical JSON v1、A1-03 链接规则、D22–D24 契约文本、Core ReviewService、DB schema/迁移、V1 API、依赖/lockfile、MILESTONES。
- 证据类型：Git 工作树对 HEAD 的归一化 diff 为空（tracked 路径）+ 文件 mtime + 冻结套件 417 passed。
- 注意：`docs/plans/` 下设计文档为 untracked，无法用 HEAD 比对；以 mtime 与内容哈希记录，且本轮未编辑。

## 1. A1-02 三种 Core Hash

定义（`docs/plans/V2-A1-04-implementation-plan.md:88`）：

- `document_content_hash`（`markdown/__init__.py:352`）
- `document_payload_hash`（`:371`）
- `review_payload_hash`（`:384`）

证据：

- `git diff --stat -- knowledge-core/src/knowledge_core/markdown/canonical.py knowledge-core/src/knowledge_core/markdown/codec.py` 输出为空、退出码 0。
- `knowledge-core/src/knowledge_core/markdown/__init__.py` 工作树原始 Hash 与 `HEAD` blob 一致：`7030fad7…688b7f`。
- `test_markdown_canonical.py`、`test_markdown_service.py` 等包含在 417 项冻结套件中并全部通过。

## 2. A1-03 链接规则

- 核心：`knowledge-core/src/knowledge_core/markdown/links.py`、`link_service.py`；后端：`backend/app/services/links.py`、`backend/app/api/routes/links.py`。
- `git diff --stat` 对以上四个路径输出为空、退出码 0（`links.py` 等均为 tracked 且未改）。
- 测试：`test_links*.py`（7 个后端文件）+ `test_markdown_links.py` / `test_markdown_link_service.py` 均在 417 项冻结套件内通过。
- K1 的删除降级/内容变更同步仅在 `governance.py` 内以既有函数调用，未改链接规则本身。

## 3. D22–D24 与设计文本

| 文档 | mtime | SHA-256 |
| --- | --- | --- |
| `docs/plans/V2-A1-04-implementation-plan.md`（含 §22 R1.3 D22–D24） | 2026-11-21 22:09:45 | `bc171f64…f6fff` |
| `docs/plans/V2-A1-04-acceptance-matrix.md` | 2026-11-22 00:11:48 | `9a1d0288…48e96` |
| `docs/plans/V2-batch-A-design.md` | 2026-11-18 12:35:03 | `2898bc12…1ed4` |
| `docs/plans/V2-A1-04-open-decisions.md` | 2026-11-21 22:08:57 | `75c85e23…b979` |

均早于本轮整改时间窗（11-22 10:00 之后），`evidence/scope-mtime.txt` 的“10:00 后修改文件”清单不含任何 `docs/plans` 或 `knowledge-core` 文件。

D22：exporter 只属传输元数据，不参与文档 Hash；实现中导出先算 Hash 再注入 exporter，Hash 文件未改。
D23：状态 1/2a/2b/3/4 与 Journal PREPARED/COMMITTED 定义未改；本轮只是让 `materialize()` 更早执行分类、给导入/审核加锁。
D24：HTTP 本机安全边界未触碰。

## 4. Canonical JSON v1

- 实现文件 `knowledge-core/src/knowledge_core/markdown/canonical.py` 对 HEAD 无 diff。
- 8 组固定向量与 canonical 测试在 `test_markdown_canonical.py`、`test_batch_a_canonical.py` 中通过。
- 本轮新增的 Journal 记录继续使用 `canonical_dumps` / `sha256_canonical`，未新增或修改编码规则。

## 5. 状态机与 Journal 数据契约

- `classify()` 返回的状态标签仍为 `"1" | "2a" | "2b" | "3" | "4"`（`source_identity.py:552`），判定表与冻结文档一致。
- Journal `schema_version` 仍为 1（`_new_record`，1030）；字段集合未增删（`_TOP_FIELDS`，61–77）；PREPARED/COMMITTED 两阶段与归档规则未改。
- 本轮对 `source_identity.py` 的改动是“调用顺序与锁 + 归档发布方式”，不是数据契约变更；逐行见 `03-diff/per-file/…source_identity.py.diff`。

## 6. DB schema / Alembic

- `git status --porcelain -- backend/alembic backend/app/models.py` 输出为空；`git diff` 为空。
- 未新增迁移、未改表/列/索引；`ImportOriginORM` 与 `KnowledgeItemORM` 的既有列足够，本轮无 schema 变更。
- 测试使用真实 SQLite 建表与迁移后的结构；未连接真实 PostgreSQL（见验证缺口）。

## 7. V1 API 与 Core ReviewService

- V1 路由除 `governance.py` 外均无改动；`governance.py` 只改导入审核分支的锁/钩子注入，未改请求/响应模型与既有 K1 行为。
- `knowledge-core/src/knowledge_core/review/` 对 HEAD 无 diff；`ReviewService` 的四字段应用语义未改。
- 417 项冻结套件包含 `test_governance.py`、`test_governance_links.py`、`test_health.py` 与所有 links 测试，全部通过。

## 8. Core 独立性

- 守护测试存在：`knowledge-core/tests/test_interfaces.py:42::test_core_has_no_web_framework_dependency`。
- 该测试在完整套件（1124 passed）中通过；核心新增的 `markdown/import_report.py`、`markdown/service.py` 只依赖标准库/Pydantic（导入报告为 Core 纯数据），未引入 FastAPI/Starlette/SQLAlchemy。
- 本轮未在 `knowledge-core` 下新增 Web/ORM 依赖。

## 9. 依赖与 lockfile

| 文件 | Git 状态 | SHA-256 |
| --- | --- | --- |
| `pyproject.toml` | clean vs HEAD | `f944c5e8…65919` |
| `uv.lock` | clean vs HEAD | `f5bdea35…00cea` |
| `frontend/package.json` | clean vs HEAD | `06d63b43…e437` |
| `frontend/package-lock.json` | clean vs HEAD | `3489b371…9cae` |

`git status --porcelain` 对这些路径为空；未安装/升级依赖。

## 10. MILESTONES.md

- `git status --porcelain -- MILESTONES.md` 为空；工作树与 HEAD 一致。
- SHA-256 `66f04e30…4dd1ae`，mtime 2026-11-17，早于本轮。
- 未新增里程碑、未改验收状态。

## 11. 冻结套件实测

命令（与既有证据一致）：

```text
uv run pytest backend/tests/test_batch_a_canonical.py \
  backend/tests/test_links.py backend/tests/test_links_http.py \
  backend/tests/test_links_concurrency.py backend/tests/test_links_noop_coverage.py \
  backend/tests/test_links_p2_coverage.py backend/tests/test_links_phantom_noncollision.py \
  backend/tests/test_governance.py backend/tests/test_governance_links.py \
  backend/tests/test_health.py \
  knowledge-core/tests/test_markdown_canonical.py \
  knowledge-core/tests/test_markdown_links.py \
  knowledge-core/tests/test_markdown_link_service.py \
  knowledge-core/tests/test_markdown_service.py \
  -o addopts="--import-mode=importlib"
```

结果：**417 passed，74.09s**，退出码 0（`evidence/pytest-frozen-a1-a2-a3-v1.txt`）。此处直接引用既有真实结果，本轮未重跑。

## 12. 未验证

- 设计文档为 untracked，不能像 tracked 文件那样用 HEAD 证明“自基线未改”；只能证明本轮未编辑（mtime + 未出现在修改清单）。
- 未连真实 PostgreSQL 验证 schema/迁移；未运行 PG 门控的 178 项。
- 未做 Core 独立性之外的架构依赖静态分析（仅运行守护测试）。