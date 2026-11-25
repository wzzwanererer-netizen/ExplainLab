# 02-A · `source_identity.py` 复核（P1-01 / P1-02 基础 / P1-03）

- 文件：`backend/app/services/source_identity.py`（untracked）
- 当前 SHA-256：`9c017593179e5a2cc1621301e35cad553893af274bfb8e4ed506321ae51f895a`
- 本轮整改前 SHA-256：`1fd4e2e2d49246e82a71f38e88cbed4ca0fa192a7906b7225f912a8051ec43c1`（第二轮审计快照，非手工重建）
- 本轮性质：修改（P1-01 分类先于身份文件；新增 `identity_guard` / `has_committed_materialize`；归档不覆盖发布）
- P1/P2 映射：P1-01、P1-02（锁与冲突查询）、P2-06（归档竞态）
- 下文行号均指当前工作树。

## 1. 恢复门（所有身份操作的统一入口）

`materialize()` 第 858–861 行：

```python
def materialize(self, item_id):
    with self._journal_lock:
        # 恢复优先；恢复完成前不得分类或写身份。
        self._recover_locked()
```

`identity_guard()` 第 594–604 行、`recover_if_needed()` 第 681–683 行、`has_committed_materialize()` 第 606–610 行同样先持锁再 `_recover_locked()`。`_recover_locked()` 第 685–695 行按“无 current → 返回；PREPARED → 按 kind 恢复；COMMITTED → 只补归档”分派；`_recover_materialize`（739–792）与 `_recover_rotate`（794–816）都在写前重读 DB、校验审计摘要。

结论：**恢复门在所有身份读/写入口之前**，且 `materialize` 不会绕过它去 `ensure()`。

## 2. `classify()` 状态分支（629–678）

| 状态 | 判定（按代码顺序） | 返回 |
| --- | --- | --- |
| 3 | `import_origin_count > 0` 且存在任意 COMMITTED MATERIALIZE 记录（`_origin_materialize_conflict`，618–627） | 无身份、不可认领 |
| 3 | 有 ImportOrigin，但 `origin_state != "complete"` | 无身份 |
| 1 | 有 ImportOrigin 且 `origin_state == "complete"` | 取快照中的合法身份对 |
| 4 | 无 ImportOrigin、DB 无 `source_instance_id`，但存在 COMMITTED MATERIALIZE 记录 | 无身份 |
| 2a | 无 ImportOrigin、无 DB 实例、无记录 | `document=item.id`，待物化 |
| 2b | 无 ImportOrigin、有 DB 实例，且**恰好一条**匹配记录、总记录数也为 1 | 唯一合法 2b |
| 4 | 其余（多记录、记录与 DB 不匹配等） | 无身份 |

- 冲突判定优先于 complete：即使 ImportOrigin 自身完整，只要与 MATERIALIZE 并存即为 3（649–654），不选任何记录。
- 2b 只由 Journal 证明，不从 DB 字段推断；`len(matching) == 1 and len(records) == 1`（670）防止“多条记录中恰好一条匹配”被误认。
- 孤儿 ImportOrigin 在快照构造前 fail-closed（`_check_orphans`，177–185）。

## 3. `materialize()` 的写入顺序与零写入（858–938）

1. 858–861：持 Journal 锁并执行恢复。
2. 862–866：开 session，`classify()` **只读**分类。
3. 867–878：2b 直接返回既有 `source_instance_id`（`assert` 非空），**不调用 `ensure()`**、不写 Journal/DB。
4. 879–883：非 2a（1/3/4）抛 `SOURCE_DOCUMENT_UNMATERIALIZED`，此时尚未打开/创建任何身份文件。
5. 885：仅确认 2a 后 `target = self._store.ensure()`。
6. 886–906：构造单条物化项，写 **PREPARED** Journal current。
7. 907–926：条件 UPDATE（仅当 DB 实例仍为空）并 commit；`rowcount != 1` 立即 rollback 并报 `SOURCE_IDENTITY_INCONSISTENT`。
8. 928–930：重读 DB 校验记录值与审计摘要，`_commit_and_archive` 写 COMMITTED → 归档 → 删除 current。
9. 934–938：任何异常 rollback，session 关闭。

**零写入证据**（真实 SQLite + 真实文件系统）：

| 测试 | 断言 |
| --- | --- |
| `test_conflict_with_existing_id_keeps_id_and_journal_bytes`（832） | 冲突态：ID 文件、current、archive 逐字节不变；审计摘要不变 |
| `test_conflict_with_empty_identity_dir_creates_no_id_files`（846） | 冲突态且 ID 缺失：不创建 ID、Journal 不变 |
| `test_empty_data_dir_origin_plus_db_instance_creates_no_id`（864） | 数据目录身份证据全缺、状态 1：不创建 ID |
| `test_prepared_materialize_plus_origin_conflict_keeps_journal`（890） | PREPARED 恢复后仍冲突：Journal 字节不变、DB 实例仍为 NULL |
| `test_normal_2a_materializes_after_classification`（911） | 正常 2a 才创建 ID 并完成 2b |
| `test_normal_state_1_materialize_creates_no_id`（925） | 状态 1 拒绝且零 ID |
| `test_normal_2b_materialize_does_not_recreate_or_rewrite_id`（941） | 2b 幂等，ID/Journal/审计摘要全不变 |

## 4. `identity_guard()` 与冲突查询

- `identity_guard`（594–604）在 `threading.RLock` 内先恢复，再 `yield`；调用方的分类、写入、commit 均在同一临界区。
- `has_committed_materialize`（606–610）在同一把锁内恢复并查询 `_committed_index()`；`_committed_index`（612–616）来自 `journal.committed_materialize_records()`（532–543），后者合并 current 与 archive 并按 `operation_id` 去重、对同 ID 异内容报 `JOURNAL_CORRUPT`。
- 在 guard 内再次调用 `has_committed_materialize` 会重复获取同一 RLock，可重入，不会自锁。

## 5. 数据契约执行情况

- `item_identity_digest`（128–136）只覆盖 item_id / 实例 / 文档 / 版本；`materialization_digest`（139–143）排序后规范 JSON，并对重复 item_id 报错。
- `validate()`（约 335–415）校验顶层字段白名单、item 字段、MATERIALIZE/ROTATE 互斥字段、UUID 版本、摘要与 `journal_checksum`；归档读取要求 `phase == COMMITTED` 且文件名等于 `operation_id`（447–461）。
- `_commit_and_archive`（723–737）在写 COMMITTED 前后各重算一次审计摘要；归档后立即删除 current。因此 Materialize 记录最终都在 archive，`committed_materialize_records()` 仍会把残留 current 计入，兼容崩溃窗口。

## 6. 未覆盖/未验证

- 本文件锁为**线程级**，跨进程互斥依赖 `app.main` 启动时持有的 `ProcessLock`（单实例部署）。多进程/多 worker 同时写同一 data_dir 不在已验证范围（见风险登记 P2）。
- 真实断电/介质损坏未做；Windows 目录 fsync 为 no-op（113–125），不宣称掉电持久。
- 无 PostgreSQL 路径：身份 Journal 为文件系统，未在 PG 实例上验证并发（与 DB 方言无关）。