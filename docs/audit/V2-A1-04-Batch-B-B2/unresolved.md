# B2 未解决问题与边界

本清单只记录 B2 交付时的真实边界；不把未执行项写成通过，不提前实现后续里程碑。

## 1. 未验证（环境受限）

| 项 | 状态 | 说明 |
|---|---|---|
| B2 PostgreSQL HTTP 端到端 | **未执行** | 本机未配置 `EXPLAINLAB_PG_TEST_URL`。PG 分支（`SELECT ... FOR UPDATE` 归档保护、advisory `StorageKeyLock`、路由提交后释放）只有代码审阅；SQLite 结果不能替代 |
| Real PG 并发上传/删除 | **未执行** | 与上同；B1 已有 PG 仓储/锁的独立证据，但不能代替 B2 路由与服务编排 |
| 前端 | 未执行 | B2 无前端改动；本包不声称 UI 可通过 |
| 全仓 Ruff | 未重新取证 | 本轮只运行 `ruff check backend knowledge-core`；旧审计包迁移副本的 5 项历史错误未处理，也不在 B2 范围 |

## 2. 按阶段未实现（不是缺陷）

| 项 | 归属 | B2 现状 |
|---|---|---|
| 上传/归档 commit 失败后的 24h ORP 收敛 | B5 | 只验证“无 DB 行、孤儿 blob、无临时残留”；不删除孤儿、不提供 worker |
| 共享引用并发删除的 ORP 兜底 | B5 | 两侧均看到非零引用时可能不入队；允许由 ORP 兜底，B2 未实现 |
| GC 管理 HTTP 端点 | 未列入 B2 | 不实现 |
| B3 staging/import manifest、B4 审核集成 | B3/B4 | 不实现 |
| Range/HEAD/缓存预热 | 未列入 B2 | 不实现 |

## 3. 已知限制（冻结文档已记录）

- **SQLite 锁是逻辑租约**：读阶段不阻塞写者；靠条件更新、`verify_all` 与写阶段锁兜底。不得宣称 SQLite 读阶段已锁保护或已消除 `SQLITE_BUSY`。
- **PG 租约行 TTL 不授权接管**：接管权威是 advisory 锁，行 TTL 只用于展示/诊断。
- **下载同句柄不消除外部原地改写**：句柄保证路径替换后仍读已校验内容；外部进程原地改写同一 inode 仍是残余 TOCTOU 风险。
- **发布成功 ≠ 物理/DB 原子**：业务响应只表示引用已提交；孤儿由 B5 处理。

## 4. 历史遗留问题（必须继续保留）

- SQLite GC 列表测试 `test_gc_save_get_defaults_and_list_filters` 假设插入顺序；`created_at` 相等时仓储按 `id` 第二排序，真实探针证实可逆转。该问题与 B1 正式 PASS 不冲突，但后续复现时须先核对时间戳/排序键，不能当作 B2 回归。[历史诊断](../../acceptance/V2-A1-04-Batch-B-B1-final-verification-round/evidence/gc-order-diagnostic.log)
- 全仓 Ruff 既有 5 项历史错误来自旧审计包 `0006_v2_markdown_kb.py` 迁移副本，本轮未修复。

## 5. 审核建议

1. 在具备真实 PostgreSQL 的环境设置 `EXPLAINLAB_PG_TEST_URL`，补跑 B2 PG HTTP 用例（需先新增门控测试，或由审核方提供同口径脚本）。
2. 独立核对上传顺序与“锁在 commit 后释放”，尤其 commit 失败/归档竞态时的锁释放与孤儿边界。
3. 独立核对下载是否只使用一次打开校验的句柄。
4. 确认 ATT-11/B5 与共享引用并发删除的 ORP 兜底未被误记为已实现。