# 02-B · `identity_guard` 全事务覆盖复核（P1-02）

- 目标：证明“分类校验 + 导入身份写入 + commit”与 MATERIALIZE/ROTATE 在同一把 Journal 锁内，且直接导入、批量导入、审核批准三条链路无旁路。
- 实现：`backend/app/services/source_identity.py:594–604`
- 调用点：`backend/app/services/markdown.py:648`、`backend/app/api/routes/governance.py:433`
- 性质：P1-02 修复；未新增/修改冻结契约。

## 1. 实现

```python
# source_identity.py:594
@contextmanager
def identity_guard(self) -> Iterator[None]:
    with self._journal_lock:
        self._recover_locked()
        yield
```

- 锁对象：`self._journal_lock = threading.RLock()`（585）。
- 获锁后**先恢复**，再交给调用方；恢复失败直接抛出，调用方不会进入写入。
- RLock 可重入：guard 内 `has_committed_materialize()`（606–610）再次取锁安全。
- 释放：`with` 退出即释放；异常路径同样释放（`contextmanager` 语义），不存在手工 unlock 遗漏。

## 2. 直接导入与批量导入（同一链路）

入口：

- 单篇：`POST /api/knowledge/import` → `import_markdown`（`import_export.py:207–225`）→ `service.import_documents(...)`
- 批量：`POST /api/knowledge/import/batch` → `import_markdown_batch`（`import_export.py:228–246`）→ `service.import_documents(...)`
- 两者只在 `reject_attachments` 与 HTTP 状态上不同；身份处理完全共用 `import_documents`。

`import_documents`（`markdown.py:237–...`）：

1. 249：`self._identity.recover_if_needed()` —— 批次级恢复门。
2. 261–288：逐篇预检、跳过冲突/不支持项。
3. 291–295：逐篇调用 `_import_one`；单篇异常被捕获为该篇 `ERROR`，**不破坏批次其他条目**（304–315）。

`_import_one`（`markdown.py:630–740`）：

```python
# 640–645：锁外 S0 只读（advisory，仅用于早期拒绝）
s0_session = self._factory()
s0 = self._read_state(s0_session, item, target)
s0_session.close()

# 648：coordinator 键锁 + Journal 身份锁
with self._coordinator.keyed(lock_key), self._identity.identity_guard():
    session = self._factory()
    try:
        s1 = self._read_state(session, item, target)   # 651：锁内重读
        ...
        result, needs_index = self._apply_import(...)   # 726
        session.commit()                               # 734
        return result, needs_index
    except Exception:
        session.rollback()                             # 737
        raise
    finally:
        session.close()                                # 740
```

- 锁内 S1 重读（651）后若签名与 S0 不同，按 `SOURCE_CHANGED_DURING_WAIT`（409）等处理；因此锁外 S0 不构成正确性依赖。
- `_apply_import` 的身份校验与全部 ImportOrigin/实例字段写入都在 648 的 `with` 内；`session.commit()` 也在同一缩进层级内。
- 冲突检查：`markdown.py:775–784` 在解析出既有条目后、写任何导入字段前调用 `has_committed_materialize(existing.id)`，命中即 `SOURCE_IDENTITY_CONFLICT`（409）。异常由 736–738 rollback 整条 session。

## 3. 审核批准链路

`approve_review`（`governance.py:408–485`）：

| 步骤 | 行号 | 是否在 guard 内 |
| --- | --- | --- |
| S0 预检（独立 session，取 payload 摘要与锁键） | 421–424 | 否（只读，锁内会重读比对） |
| 取 coordinator keyed 锁 + `identity.identity_guard()` | 430–433 | — |
| S1 新 session 重读 pending、重新解析 envelope、比对 S0 摘要 | 434–455 | **是** |
| 同事务入链预降级 | 457 | 是 |
| `ReviewService.approve`（Core 四字段） | 458–463 | 是 |
| `ImportReviewHook.apply_approved`（origins/tags/metadata/links） | 464–467 | 是 |
| 第一次 `session.commit()`（审核 + 导入字段） | 470 | 是 |
| 索引同步 + 第二次 commit | 471–476 | 是（与身份无关） |
| `MarkdownServiceError`/`SourceIdentityError` → rollback | 478–480 | 是 |
| 其他异常 → rollback | 481–483 | 是 |

- 钩子内冲突检查：`import_review_hook.py:109–116`，在 `update_fields` / `save_origin` / tag / link 之前 fail-closed；路由回滚后审核单保持 PENDING。
- S0 摘要比对（447–455）保证获锁前 envelope 未被改写；即便被改写也 409，而不是用旧摘要应用新内容。
- `reject_review`（488–526）只调用 `apply_rejected`（516），该函数为显式空操作（`import_review_hook.py:192–194`）；因此不取 `identity_guard` 是正确的：拒绝不写任何身份字段。

## 4. 锁顺序与旁路检查

- 导入/批准固定顺序：**coordinator 键锁 → Journal 锁**（648；433 外层 coordinator，内层 guard）。
- MATERIALIZE/ROTATE/导出身份确保只取 Journal 锁：`materialize`（859）、`rotate`（942）、`ensure_local_export_identity`（838）、`has_committed_materialize`（608）。不存在“先 Journal 再 coordinator”的路径，因此无锁环。
- `_apply_import` 全仓库只有一个调用点（`markdown.py:726`），位于 guard 内；`apply_approved` 只有一个调用点（`governance.py:467`），位于 guard 内。
- 未发现第二条直接写 `ImportOriginORM` 或 `KnowledgeItemORM.source_instance_id` 的导入旁路（导入写入集中在 `_apply_import` 与钩子）。
- 跨进程：Journal 锁是线程锁；应用启动时 `ProcessLock` 保证同一 `data_dir` 仅一个后端实例（`main.py:72–91`）。该前提下的并发已覆盖；多实例共享 data_dir 不在支持范围。

## 5. 事务边界说明（非身份风险）

批准路径有两次 commit：第一次提交审核 + 导入字段（身份一致性的关键边界），第二次提交索引同步。若第二次失败，审核与身份已落库但索引可能滞后；这不会制造 §22.2 冲突，属于既有“索引最终一致”行为，未在本轮改动。

## 6. 测试映射

`backend/tests/test_markdown_batch_a_import_conflict.py`（7 项）：

| 测试 | 覆盖 |
| --- | --- |
| `test_same_identity_import_into_materialized_is_rejected`（101） | 直接导入 2b → 409，item/origin/link/ID/Journal 零变化 |
| `test_different_identity_import_into_materialized_is_rejected`（129） | 不同身份同样拒绝、零写入 |
| `test_conflict_item_does_not_accept_duplicate_origin_via_import`（157） | 已有重复 origin 不追加/不覆盖 |
| `test_batch_isolates_conflict_and_creates_unrelated_document`（200） | 批量中冲突项失败、无关项正常提交 |
| `test_materialized_active_item_rejects_before_review_creation`（235） | active 条目在创建审核单前拒绝 |
| `test_approve_rejects_when_target_materialized_after_review`（261） | 审核待决期间被物化 → 批准 409，审核仍 PENDING |
| `test_incomplete_origin_plus_materialize_rejects_import`（308） | 残缺 origin + MATERIALIZE 仍判冲突 |

另由 `test_markdown_batch_a_identity.py::TestJournalRecovery`（572–688）覆盖恢复门、损坏 Journal、COMMITTED 补归档等；`TestMaterializeClassificationBeforeIdentityWrite` 覆盖 guard 内恢复先于分类。

## 7. 未验证

- 多进程/多 worker 同时操作同一 data_dir：未验证（设计上由 `ProcessLock` 排除）。
- 审核批准与真实外部 HTTP 并发压测：未做；现有线程级故障注入覆盖单进程内并发窗口。
- 真实 PostgreSQL 下的审核事务：未连真实 PG（见 `04-test-evidence/verification-gaps.md`）。