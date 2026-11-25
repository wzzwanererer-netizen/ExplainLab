# PostgreSQL 索引提交故障注入专项报告

**状态**：实机验证通过（待独立审计最终裁决）  
**测试环境**：WSL2 Ubuntu 原生 `ext4` + 真实 PostgreSQL 18.6（`server_version_num=180006`）  
**数据库**：独立隔离库 `explainlab_closure_idx_dpfif21x`  
**测试代码**：[test_v2_closure_pg_index_faults.py](file:///D:/ExplainLab/backend/tests/test_v2_closure_pg_index_faults.py)  
**原始日志与 JUnit**：[closure-pg-index-faults.log](evidence/closure-posix-pg.SqauvYgo/closure-pg-index-faults.log) · [closure-pg-index-faults.xml](evidence/closure-posix-pg.SqauvYgo/closure-pg-index-faults.xml)

## 1. P1-01 实现核验与双事务边界

本轮**未重写或修改 P1-01 生产代码**（[governance.py](file:///D:/ExplainLab/backend/app/api/routes/governance.py) 与 [retrieval.py](file:///D:/ExplainLab/backend/app/services/retrieval.py) 保持原样）。经实测确认两条事务边界严格分离：

- **TX1（业务事务）**：在持有 review/source/identity/staging/storage 锁内完成 Core 审核决议、Hook 写入（附件引用、标签、来源、wikilink）与业务 `session.commit()`；若 TX1 失败，整事务回滚且 **staging 目录保留不删**。
- **TX2（独立索引 Session）**：在 TX1 提交并释放所有锁后，通过 `_sync_after_commit` 开启**独立 `create_session()`** 同步 PG `knowledge_fts`（tsvector）与向量；若 TX2 失败，仅记录脱敏警告码 `REVIEW_INDEX_SYNC_FAILED: <ExcType>`，不回滚 TX1，不返回虚假 HTTP 500。

## 2. PostgreSQL 18.6 专项故障注入结果（10/10 PASS，exit=0）

| 测试用例 | 注入阶段与类型 | 实测观测结果 |
| --- | --- | --- |
| `test_pg_index_commit_failure_by_business_path[attachment]` | TX2 独立索引 Session `before_commit` 抛 `RuntimeError` | HTTP 200 `approved`；业务与索引为 2 个独立 Session；附件引用 `refs=1` 与正式文件字节完好；staging 已正常清理；重复审批 409；记录 `REVIEW_INDEX_SYNC_FAILED: RuntimeError` 且无私密报错泄漏；`advisory_locks=0`；后续 `sync_index` 后 `PostgresFullTextIndex` 可检出 |
| `test_pg_index_commit_failure_by_business_path[tags]` | 同上，核验标签路径 | HTTP 200 `approved`；`tags=['pgtag_tags_d6af4c']` 完整落库；无回滚；PG FTS 可恢复；`advisory_locks=0` |
| `test_pg_index_commit_failure_by_business_path[origin]` | 同上，核验 `ImportOrigin` 路径 | HTTP 200 `approved`；`import_origin` 完整落库无悬空；PG FTS 可恢复；`advisory_locks=0` |
| `test_pg_index_commit_failure_by_business_path[links]` | 同上，核验 `KnowledgeLink` 路径 | HTTP 200 `approved`；`links=1` 完整落库无悬空；PG FTS 可恢复；`advisory_locks=0` |
| `test_pg_index_commit_failure_by_business_path[archive_guard]` | 归档目标路径预检拦截 | HTTP 409 `ATTACHMENT_ITEM_ARCHIVED`；`index_called=False`；**staging 完整保留**；零附件/标签/来源/链接写入；`advisory_locks=0` |
| `test_pg_business_commit_failure_preserves_staging_and_rolls_back` | **TX1 业务事务** `before_commit` 抛 `RuntimeError` | 业务数据完全回滚（review 保持 `pending`，item 保持 `active`，附件/标签/来源/链接全为空）；**staging 目录与 `.complete` 完整保留**（未提前删除）；`advisory_locks=0` |
| `test_pg_p1_01_routes_index_commit_failure_preserves_committed_business[ordinary_approve]` | 普通审核批准后索引失败 | HTTP 200 `approved`；独立读会话可见已提交内容 `updated`；重复审批 409；警告脱敏；`advisory_locks=0` |
| `test_pg_p1_01_routes_index_commit_failure_preserves_committed_business[draft_apply]` | 草稿直办后索引失败 | HTTP 200 `applied=True`；独立读会话可见 `updated`；警告脱敏；`advisory_locks=0` |
| `test_pg_p1_01_routes_index_commit_failure_preserves_committed_business[restore]` | 版本恢复后索引失败 | HTTP 200 恢复为 `previous`；独立读会话可见 `previous`；警告脱敏；`advisory_locks=0` |
| `test_pg_index_embedding_failure_preserves_fts_and_redacts_log` | 索引阶段 Embedder 抛 `ModelAdapterError` | HTTP 200 `approved`；仅记录 `INDEX_EMBEDDING_SYNC_FAILED: ModelAdapterError`（私密片段未泄漏）；PG `PostgresFullTextIndex` 仍可检出新内容；`advisory_locks=0` |
