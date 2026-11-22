# PostgreSQL 真实验证状态

## 1. 结论：未验证（环境不具备）

| 项目 | 状态 | 证据 |
| --- | --- | --- |
| Windows 本地 PostgreSQL 服务 | 无 | `evidence/postgresql-probe.txt`：`Get-Service *postgres*` 无输出 |
| docker | 未安装 | `docker: not found` |
| podman | 未安装 | `podman: not found` |
| psql / pg_ctl / postgres | 未安装 | 均 `not found` |
| WSL Ubuntu PostgreSQL | 未安装 | WSL 内 `psql: not found` |
| WSL Python 依赖 | 不可用 | `pip3: not found`、`sqlalchemy: absent` |
| `EXPLAINLAB_PG_TEST_URL` | 未设置 | 全量套件 178 项 PG 门控测试整模块跳过 |

**未执行任何真实 PG 连接、迁移、检索或并发验证；未伪造成功；未用 SQLite 替代。** 因此本轮不能宣称 PostgreSQL 路径通过。

## 2. 可直接执行的验证清单

以下命令在具备 PostgreSQL 的独立环境执行；每条都应保存命令、起止时间、原始输出与退出码到新的证据目录（不要覆盖本包）。

### 2.1 准备隔离实例（任选其一）

```bash
# A. 容器（推荐）
docker run --rm -d --name explainlab-pg \
  -e POSTGRES_PASSWORD=explainlab_test \
  -e POSTGRES_USER=explainlab \
  -e POSTGRES_DB=explainlab_test \
  -p 55432:5432 postgres:16
# 等待 ready
docker exec explainlab-pg pg_isready -U explainlab -d explainlab_test

# B. 原生实例（示例）
initdb -D /tmp/explainlab-pg -U explainlab --auth=trust
pg_ctl -D /tmp/explainlab-pg -o "-p 55432" -l /tmp/explainlab-pg.log start
createdb -p 55432 -U explainlab explainlab_test
```

```bash
export EXPLAINLAB_PG_TEST_URL='postgresql+psycopg://explainlab:explainlab_test@127.0.0.1:55432/explainlab_test'
```

> 只允许隔离测试库；严禁指向生产库。URL 由操作者自行提供，不使用任何代理地址。

### 2.2 迁移 up / down（必须双向）

```bash
cd backend
DATABASE_URL="$EXPLAINLAB_PG_TEST_URL" uv run alembic upgrade head
DATABASE_URL="$EXPLAINLAB_PG_TEST_URL" uv run alembic downgrade base
DATABASE_URL="$EXPLAINLAB_PG_TEST_URL" uv run alembic upgrade head
```

通过标准：三条命令退出码 0；无 `%` 插值错误；`alembic current` 停在 head；`downgrade base` 后表清空。

### 2.3 结构与检索（真实在线验证）

```bash
cd /path/to/ExplainLab
uv run pytest backend/tests/test_retrieval_pg.py -o addopts="--import-mode=importlib"
```

该模块应真实覆盖（以文件内断言为准）：

- schema：表、索引、GIN 索引、增改触发器、删除外键级联；
- 全文检索：`tsvector/tsquery` 命中；无空格中文查询回退 `ILIKE` 子串匹配（真实命中，非造假）；
- 向量：JSON 文本 + Python 余弦（`JsonVectorStore`，不依赖 pgvector）；
- 混合检索与排序；
- 迁移 up/down 后的可重复性。

同时执行一次全量：

```bash
EXPLAINLAB_PG_TEST_URL="$EXPLAINLAB_PG_TEST_URL" uv run pytest -o addopts="--import-mode=importlib"
```

记录实际 passed/skipped 数量；确认不再有 178 项 PG 跳过。

### 2.4 Batch A 专项在线场景（API/服务级）

在 PG 实例上（`DATABASE_URL` 指向测试库）逐项执行并留证：

1. **单实例锁与启动**：两个进程同时启动后端，第二个应以稳定码拒绝（不得双写）。
2. **导入 → 导出 → 再导入（P1-02）**：导入文档 → 导出成 Markdown（COMMITTED MATERIALIZE）→ 再次导入同一目标 → 必须 409 `SOURCE_IDENTITY_CONFLICT`，DB 的 `knowledge_item`/`import_origin`/`knowledge_link` 计数、Journal current/archive、实例 ID 文件均不变。
3. **多来源审计**：同一 item 多条 ImportOrigin（同/异身份、重复、不完整）→ `audit_digest` 覆盖原始记录；派生字段变化必须改变摘要。
4. **PREPARED/COMMITTED 恢复**：在 MATERIALIZE/ROTATE 写入 current 后、DB commit 前/后分别终止进程，重启后恢复门按表执行；不得出现“已 import_origin 且在 DB 中物化”的冲突成功态。
5. **ROTATE**：混合“冲突条目 + 合法 2a”执行 ROTATE；冲突条目不被物化/覆盖/认领，2a 正常物化，落盘 ROTATE 摘要与 DB 一致，导出器替换。
6. **审核回滚**：审核待决期间导出目标物化 → approve 返回 409，审核单 PENDING，正文/状态/标签/链接零变化。
7. **索引同步**：审核批准/拒绝、导入、物化后 FTS 索引与条目内容一致（检索新内容可命中，旧内容不残留）。
8. **并发**：两个请求并发“创建实例 ID”、并发导入同一来源、并发 MATERIALIZE；断言仅一个权威结果，无重复 origin、无覆盖归档。

### 2.5 判定与记录

- 每项记录：命令、开始/结束时间、原始输出、退出码、passed/failed/skipped。
- 只有全部关键项真实通过才可把 PG 标为“已验证”；任何一项失败或无法执行，保持“未验证/失败”，并写明阻塞原因。
- 完成后**不要覆盖** `docs/acceptance/V2-A1-04-Batch-A/final-remediation/`；新建独立证据目录并在审计材料中引用。

## 3. 为什么本轮不用 SQLite 代替

SQLite 与 PostgreSQL 在全文检索、类型映射、并发/锁语义、迁移方言上不同；AGENTS.md §5 明确禁止以离线 SQL 或 SQLite 结果冒充 PG 验证。本轮遵守该约束。