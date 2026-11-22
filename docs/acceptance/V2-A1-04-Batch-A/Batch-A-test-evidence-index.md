# V2 · A1-04 · Batch A 测试证据索引

- 日期：2026-11-22
- 根目录：`docs/acceptance/V2-A1-04-Batch-A/evidence/`
- 所有命令在 `D:\ExplainLab` 执行；前端命令在 `frontend/`。

## 1. 原始命令输出

| 文件 | 命令 | 关键结论 |
|---|---|---|
| `pytest-full-sqlite.txt` | `uv run pytest -o addopts="--import-mode=importlib"` | **1062 passed, 178 skipped**；SQLite 全量 + Core + 既有 V1/V2 回归 |
| `pytest-batch-a.txt` | `uv run pytest backend/tests/test_batch_a_canonical.py backend/tests/test_markdown_batch_a_import_export.py backend/tests/test_markdown_batch_a_identity.py backend/tests/test_batch_a_process_and_identity.py knowledge-core/tests/test_markdown_service.py -o addopts="--import-mode=importlib"` | **132 passed** |
| `ruff-check.txt` | `uv run ruff check` | All checks passed |
| `frontend-regression.txt` | `npm run test && npm run typecheck && npm run build` | 72 tests passed；typecheck/build 通过 |
| `postgresql-unverified.txt` | 环境检查 + PG 测试模块收集 | PG 不可用；模块 skip |
| `git-worktree.txt` | `git status --short`、`git diff --stat`、`git log -1` | 未提交工作树，HEAD `784b124` |
| `frozen-contracts.txt` | 依赖/迁移/冻结文件状态 + 方言关键词扫描 | 锁文件/迁移/端口契约无改动 |

## 2. 测试文件与覆盖

### 2.1 `backend/tests/test_batch_a_canonical.py`（16 项）

- `test_fixed_canonical_vectors`：8 组固定向量精确字节 + SHA-256。
- `test_vector_7_key_order_semantically_equal`、`test_vector_8_duplicate_keys_rejected_before_folding`。
- `test_canonical_loads_requires_byte_exact_form`、`test_canonical_loads_rejects_noncanonical_escapes_and_numbers`。
- `test_isolated_surrogates_rejected`、`test_supplementary_plane_round_trip_is_utf8_bytes`、`test_booleans_only_lowercase`、`test_digest_always_prefixed`。

### 2.2 `backend/tests/test_markdown_batch_a_import_export.py`（32 项）

- 导入创建/更新/跳过/匿名重复/批量隔离/空导入。
- legacy 半身份、非字符串身份、无身份、target 冲突。
- 同身份多条目歧义 `SOURCE_IDENTITY_AMBIGUOUS`。
- D22 四类冲突零写入；导出拒绝用户 metadata 保留键。
- exporter 与四个 Hash 解耦；导入剥离保留键、DB 无 exporter 列/值。
- 单篇/ZIP 导出与再导入幂等。
- 附件：单篇拒绝、批量逐项 unsupported、导出拒绝。
- Active Review：pending 复用/不同版本拒绝、approve hook 应用、reject 零写、hook 故障回滚。

### 2.3 `backend/tests/test_markdown_batch_a_identity.py`（26 项）

身份状态：

- 2a 首次导出物化一次；2b 重启稳定、Hash 稳定；状态 4 不认领；状态 1 使用 ImportOrigin；状态 3 零认领。

ImportOrigin 审计：

- 单条 complete；两条 duplicate；完整+残缺 incomplete；两合法身份对 conflict；DB 实例不一致 conflict；同身份多版本 complete；原始字段变化摘要变化；非法字段原样保留；孤儿 fail-closed。

Journal：

- PREPARED + DB 空/其他值；损坏 current 阻断导入；COMMITTED 未归档只归档且不改 `updated_at`；DB 后 COMMITTED 前崩溃恢复；current+archive 去重；archive 损坏；校验和不符零 DB 写。

ROTATE：

- 2a/2b/导入/状态 3/状态 4；来源身份不改写；第二次 rotate；PREPARED 旧 ID 恢复完成替换；PREPARED 新 ID 只补提交。

### 2.4 `backend/tests/test_batch_a_process_and_identity.py`（30 项）

进程锁：

- 路径/默认 10s/同对象/同进程第二对象/上下文管理；
- 真实子进程竞争拒绝、释放后可获取、子进程崩溃后 OS 释放。

`source-instance-id`：

- 8 类非法内容 fail-closed 且不覆盖；缺失稳定码；
- canonical UUIDv4、单行、稳定；
- `replace` 校验/原子；
- 4 个真实子进程并发创建只产生一个 ID，无 tmp 残留。

Coordinator：

- 同键串行顺序、异键并行、超时稳定码/有界、异常后引用计数归零。

同步模型：

- 写路由同步 `def`（含 approve/reject）；
- S0 close 先于 lock-enter、Session 单线程；
- 单篇锁超时 409、批量逐项隔离；
- 异常路径 rollback → close → lock-exit；
- 无 async lock 双架构；
- 同身份并发 1 item/1 origin；异身份并发 2/2；
- 锁等待期间 event loop ticker ≥5。

### 2.5 `knowledge-core/tests/test_markdown_service.py`（28 项）

- 顶层重复键扫描（普通/保留键/引号转义/单引号/嵌套跳过/注释/非法代理项）。
- exporter 剥离/注入/嵌套冲突/DB metadata 冲突/注入不改来源 Hash。
- frontmatter 原始提取（BOM/CRLF/无块）。
- 来源身份拆分（顶层提取、显式 null、非字符串拒绝）。

## 3. 关键证据定位

| 主题 | 位置 |
|---|---|
| 零写入（D22 四类） | `pytest-batch-a.txt` 中 `TestD22Conflicts` |
| 零写入（歧义/锁超时） | `TestLegacyIdentity::test_multiple_origins...`、`TestSyncThreadModel::test_*lock_timeout*` |
| 故障注入（Journal/Rotate） | `TestJournalRecovery`、`TestRotate` |
| 真实子进程锁 | `TestProcessLock::test_cross_process_refusal_then_release`、`test_os_releases_lock_on_process_crash` |
| 真实并发 ID 创建 | `TestSourceInstanceId::test_concurrent_cross_process_creation_yields_single_id` |
| 线程/event loop | `TestSyncThreadModel`、`TestAsyncAndCancellation` |
| 前端回归 | `frontend-regression.txt` |
| 冻结面 | `frozen-contracts.txt`、`git-worktree.txt` |

## 4. 复现

```bash
# 全量（保留 importlib，完整汇总）
uv run pytest -o addopts="--import-mode=importlib"

# Batch A 聚焦
uv run pytest \
  backend/tests/test_batch_a_canonical.py \
  backend/tests/test_markdown_batch_a_import_export.py \
  backend/tests/test_markdown_batch_a_identity.py \
  backend/tests/test_batch_a_process_and_identity.py \
  knowledge-core/tests/test_markdown_service.py \
  -o addopts="--import-mode=importlib"

uv run ruff check
cd frontend && npm run test && npm run typecheck && npm run build

# PostgreSQL（需先提供真实实例）
export EXPLAINLAB_PG_TEST_URL='postgresql+psycopg://...'
uv run pytest backend/tests/test_retrieval_pg.py backend/tests/test_links_pg.py \
  backend/tests/test_v2_models_pg.py -q
```

## 5. 未纳入证据的项

- 真实 PostgreSQL：无实例，未执行。
- `rotate-instance-id` CLI：未实现。
- Journal 归档临时文件/rename/目录同步逐点崩溃：未注入。
- 真实 Uvicorn `--reload`/多 worker：未启动。
- Windows ACL/只读目录：未注入。