# P1 技术审计证据：身份并存冲突与恢复门

- 对象：当前工作树 `784b1248`（分支 `fix/m0-admission-and-m5-regressions`），未提交。
- 范围：只记录事实与证据，不修改代码。
- 行号：当前工作树 1-based 逻辑行号；完整摘录见
  `journal-code-extract.txt`、`classify-code-extract.txt`、`recovery-entrypoints.txt`。
- 证据分级：**【测试】**= 本轮真实执行且通过；**【静态】**= 代码阅读可确定但无对应测试；
  **【未验证】**= 本轮无法证明。

---

## 1. 生产代码中的 `classify` 调用点（全量）

`grep -rn "\.classify(" backend/app` 结果只有 4 处：

| # | 调用点 | 位置 | 所在公开入口 | 调用前是否过恢复门 |
| --- | --- | --- | --- | --- |
| 1 | `ensure_local_export_identity` | `source_identity.py:788` | 导出 / `materialize` 的 2a 分支 | 是，同函数 `785` 行 `_recover_locked()` |
| 2 | `materialize` | `source_identity.py:810` | 导出 2a、ROTATE 预物化 | 是，同函数 `806` 行 `_recover_locked()` |
| 3 | `rotate` | `source_identity.py:895` | ROTATE 全量遍历 | 是，同函数 `882` 行 `_recover_locked()` |
| 4 | `_export_record` | `markdown.py:1148` | `export_documents` / `export_single` 的私有实现 | 由公开入口 `markdown.py:1073` / `1127` 的 `recover_if_needed()` 覆盖 |

说明：

- 导入路径（`markdown.py:249`）只过恢复门，不调用 `classify`。
- `_export_record` 是私有方法，生产代码中只被 `export_documents:1090` 与
  `export_single:1135` 调用；两处公开入口都在进入前执行 `recover_if_needed()`。**【静态】**
- `classify()` 本身不调用 `recover_if_needed()`。若未来新增直接调用方绕过公开入口，
  恢复门不会自动生效。**【静态】**
- 测试代码中的 `_classify()`、`_assert_record_conflict_readonly()` 等不是生产入口。

---

## 2. 恢复门实现（当前工作树）

### 2.1 `recover_if_needed` / `_recover_locked`（`source_identity.py:627-641`）

```python
627:    def recover_if_needed(self) -> None:
628:        with self._journal_lock:
629:            self._recover_locked()
630:
631:    def _recover_locked(self) -> None:
632:        record = self.journal.read_current()
633:        if record is None:
634:            return
635:        if record["phase"] == "PREPARED":
636:            if record["kind"] == "MATERIALIZE":
637:                self._recover_materialize(record)
638:            else:
639:                self._recover_rotate(record)
640:        else:
641:            self._recover_committed(record)
```

- `read_current()` 会 `validate()`；损坏/校验失败抛 `JOURNAL_CORRUPT`，不自动删除。
- PREPARED MATERIALIZE → `_recover_materialize`（685-738）。
- PREPARED ROTATE → `_recover_rotate`（740-762）。
- COMMITTED（任何 kind）→ `_recover_committed`（764-779），只补归档，不改 DB。

### 2.2 公开入口的加锁范围

| 入口 | 加锁/恢复 | 后续操作是否仍在锁内 |
| --- | --- | --- |
| `ensure_local_export_identity` | `784 with self._journal_lock` → `785 _recover_locked()` | 是 |
| `materialize` | `805 with self._journal_lock` → `806 _recover_locked()` | 是 |
| `rotate` | `881 with self._journal_lock` → `882 _recover_locked()` | 是 |
| `export_documents` | `1073 recover_if_needed()`（锁只覆盖恢复本身） | 否；逐条 `_export_record` 在锁外 |
| `export_single` | `1127 recover_if_needed()` | 否 |
| 导入 | `249 recover_if_needed()` | 否；导入写入在锁外 |

`_journal_lock` 是进程内 `threading.RLock`，不是跨进程锁。跨进程互斥依赖
`ProcessLock` 的单实例 OS 锁（启动时获取）。**【静态；跨进程并发未验证】**

---

## 3. 冲突判定代码

### 3.1 索引来源（`source_identity.py:558-562`）

```python
558:    def _committed_index(self) -> dict[str, list[dict[str, Any]]]:
559:        index: dict[str, list[dict[str, Any]]] = {}
560:        for record in self.journal.committed_materialize_records():
561:            index.setdefault(record["item_id"], []).append(record)
562:        return index
```

### 3.2 归档 + current 的合并（`source_identity.py:496-507`）

```python
496:    def committed_materialize_records(self) -> list[dict[str, Any]]:
497:        records: dict[str, dict[str, Any]] = {}
498:        current = self.read_current()
499:        candidates = self.read_archive() + ([current] if current else [])
500:        for record in candidates:
501:            if record["phase"] != "COMMITTED" or record["kind"] != "MATERIALIZE":
502:                continue
503:            operation_id = record["operation_id"]
504:            if operation_id in records and records[operation_id] != record:
505:                raise SourceIdentityError(JOURNAL_CORRUPT, "operation id conflict")
506:            records[operation_id] = record
507:        return list(records.values())
```

- 证据来源：**归档目录全部 `*.json` + 可选 current**；只取 `COMMITTED` + `MATERIALIZE`。
- 同一 `operation_id` 内容相同则去重；内容不同 → `JOURNAL_CORRUPT`。
- 归档文件本身在 `read_archive()`（445-459）逐条 `validate()`，非 COMMITTED → `JOURNAL_CORRUPT`；
  文件名必须等于 `<operation_id>.json`。
- 因此 PREPARED 记录**不会**进入索引；只有 COMMITTED 的 MATERIALIZE 参与冲突判定。

### 3.3 判定函数（`source_identity.py:564-573`）

```python
564:    @staticmethod
565:    def _origin_materialize_conflict(
566:        snapshot: dict[str, Any], records: list[dict[str, Any]]
567:    ) -> bool:
568:        """§22.2：ImportOrigin 与任意 COMMITTED MATERIALIZE 记录并存即冲突。..."""
573:        return snapshot["import_origin_count"] > 0 and bool(records)
```

### 3.4 `classify()` 中的优先级（`source_identity.py:589-600`）

```python
589:        records = self._committed_index().get(str(item.id), [])
...
596:        origin_state = snapshot["import_origin_state"]
597:        if self._origin_materialize_conflict(snapshot, records):
600:            return ClassifiedIdentity(str(item.id), "3", None, None, snapshot)
601:        if snapshot["import_origin_count"] > 0:
602:            if origin_state == "complete":
603:                return ClassifiedIdentity(... "1" ...)
610:            return ClassifiedIdentity(str(item.id), "3", None, None, snapshot)
```

- 冲突检查在“origin 完整 → 状态 1”之前，命中即状态 3。
- `source_instance_id`、`source_document_id` 均为 `None`，不选可信记录。
- `records` 不按实例 ID、不按来源对过滤：任意条数、任意实例均冲突。
- 正常导入（origin 完整、无 MATERIALIZE）仍是状态 1；本地物化（无 origin、恰好一条匹配）
  仍是状态 2b。控制组测试见 `test_markdown_batch_a_identity.py:425`、`:433`。**【测试】**

---

## 4. 各入口在冲突状态下的行为

### 4.1 单篇/批量导出（`markdown.py:1073/1127 → 1137 _export_record`）

- `_export_record:1148` 分类；状态 3 落入 `else`，只追加警告 `identity_incomplete`
  （`1160-1161`），`source_instance`/`source_document` 保持 `None`；
  metadata 不写来源身份键（`1204-1205` 仅在非 None 时写）。
- 不调用 `ensure_local_export_identity`（只有 2a 才调用），不写 DB/Journal。
- 单篇导出返回 **200** + `identity_incomplete`，不是 4xx。**【测试】**（
  `test_single_materialize_plus_single_complete_origin` 等 10 项，其中 2 项为控制组）
- 批量导出对单条 `_export_record` 的异常收集为 `errors`；状态 3 不抛异常，正常导出。
- 批量导出只在循环前过一次恢复门（`1073`）；循环期间的新冲突不会被再次分类门拦截，
  但导出只读，不会自动修复或写身份。**【静态】**

### 4.2 `ensure_local_export_identity`（`source_identity.py:782-802`）

- 恢复门后分类；状态 3 不在 2b/2a/1 分支，落到 `799-802`：
  抛 `SOURCE_DOCUMENT_UNMATERIALIZED`，**不写 DB/Journal/实例 ID**。
- 状态 2a 才调用 `materialize`；状态 3 不会进入物化。**【测试】**

### 4.3 `materialize`（`source_identity.py:804-877`）

- `805` 加锁、`806` 恢复门、`807` `self._store.ensure()`，然后 `810` 分类。
- 状态 3 → `820-824` 抛 `SOURCE_DOCUMENT_UNMATERIALIZED`；不写 Journal、不更新 DB。
- **注意**：`807` 的 `_store.ensure()` 在分类之前执行。若 `source-instance-id` 尚不存在，
  冲突调用也可能创建该全局实例 ID 文件；这不是条目身份/DB/Journal 写入，但属于文件写入。
  现有冲突测试运行时实例 ID 已存在，未单独覆盖“空数据目录 + 冲突 + materialize”。**【静态/未验证】**

### 4.4 `rotate`（`source_identity.py:880-951`）

- `882` 恢复门、`883` `self._store.ensure()`，然后遍历全部条目 `895` 分类。
- 状态 2a → 逐条 `materialize`；状态 3 → `899-901` **`continue`**，不物化、不改写该条目；
  状态 4 → `902-906` 抛 `SOURCE_IDENTITY_INCONSISTENT`，整个 rotate 中止。
- 状态 3 不中止 rotate 是既有设计：`docs/plans/V2-A1-04-implementation-plan.md:1247`
  明确“状态 3/4 不物化、不改写；rotate 仅更换 exporter”。
- 因此严格说 **rotate 不是“遇到冲突即整体 fail-closed”**：它会继续生成全局 ROTATE Journal、
  替换 `source-instance-id`；冲突条目的 DB 身份保持不变。这是本轮发现的语义边界，
  不是本轮改动引入的回归。**【静态】**
- 现有 `test_rotate_materializes_2a_keeps_imported_identity_and_exporter`（`:691`）包含一个
  “origin 残缺 → 状态 3”的条目并断言不物化/不改写；它**不是** ImportOrigin + COMMITTED
  MATERIALIZE 并存冲突。后者在 rotate 下**无专项测试**。**【未验证】**
- 如果冲突条目是“本地原生 2a + origin + MATERIALIZE”，rotate 跳过它后它仍未物化；
  rotate 结束后该条目仍为状态 3。是否允许长期保留未物化冲突条目，取决于后续人工处置；
  本轮没有自动修复路径。**【静态】**

### 4.5 导入（`markdown.py:249` 起）

- 导入在分类/身份写入前过恢复门，但导入本身不调用 `classify`。
- 导入可以向已有 MATERIALIZE 的条目追加 ImportOrigin，从而**制造**并存冲突；
  这正是 P1 分类要发现的场景，不是自动修复。**【静态；测试通过导入构造冲突场景】**
- 导入对“既有条目来源身份不同”使用 `SOURCE_IDENTITY_CONFLICT` 409（`markdown.py:774-786`），
  这是导入入站 origin 与既有 origin 的比较，与 `classify` 的状态 3 不是同一判定。
- 导入不会因“既有条目已有 COMMITTED MATERIALIZE”而拒绝；冲突在后续分类/导出时体现。**【静态】**

### 4.6 启动（`main.py:84-87`）

```python
84:            try:
85:                identity.recover_if_needed()
86:            except SQLAlchemyError:
87:                logger.warning("启动时数据库不可达，身份 Journal 恢复延后")
```

- 只捕获 `SQLAlchemyError`。Journal 损坏/冲突抛出的 `SourceIdentityError` 不被捕获，
  会导致应用启动失败（fail-closed）。**【静态；未做真实 Uvicorn 启动集成测试】**
- DB 暂不可达时恢复延后，导入/导出入口会再次调用恢复门。

---

## 5. PREPARED / 损坏 Journal 对分类与新操作的影响

| 场景 | 行为 | 证据 |
| --- | --- | --- |
| PREPARED MATERIALIZE，DB 身份为空 | 恢复条件 UPDATE → 复核 → COMMITTED → 归档 | **【测试】** `test_prepared_materialize_recovers_db_empty` |
| PREPARED MATERIALIZE，DB 为其他值 | `SOURCE_IDENTITY_INCONSISTENT`，current 保留 | **【测试】** `test_prepared_materialize_other_db_value_fails_closed` |
| PREPARED MATERIALIZE，目标已有 ImportOrigin | `SOURCE_IDENTITY_INCONSISTENT`（`697-700`） | **【静态】** 未做“PREPARED + origin 绕过恢复直接 classify”测试 |
| DB 已写、COMMITTED 未写 | 恢复补写 COMMITTED 并归档 | **【测试】** `test_crash_after_db_before_committed_recovers` |
| COMMITTED current 未归档 | 只补归档，`updated_at` 不变 | **【测试】** `test_committed_unarchived_only_archives_without_db_rewrite` |
| current 损坏 | `JOURNAL_CORRUPT`，导入前阻断 | **【测试】** `test_corrupt_current_blocks_import_before_any_write` |
| archive 损坏 | `JOURNAL_CORRUPT` | **【测试】** `test_archive_corruption_fails_closed` |
| checksum 不匹配 | 恢复前 fail-closed，DB 未写 | **【测试】** `test_checksum_mismatch_fails_closed_before_db_write` |
| PREPARED ROTATE | 旧 ID → 替换 target；已是 target → 只补提交；其他 → 失败 | **【测试】** `test_prepared_rotate_*` |
| 跨进程同时恢复 | 仅进程内 RLock + 单实例锁设计；无跨进程故障注入 | **【未验证】** |

结论：在正常入口上，PREPARED/损坏 Journal 会在分类与新操作之前阻断或完成恢复；
但 `classify()` 自身不检查 Journal，“绕过恢复门直接 classify”不受保护。**【静态】**

---

## 6. 本轮记录的不一致/边界（不自行修复）

1. **`classify()` 无恢复门**：4 个生产调用点的当前调用链都有门，但函数本身不强制；
   未来新增直接调用方可能绕过。属结构性风险，不是当前缺陷。
2. **`rotate()` 对状态 3 `continue`**：与“冲突即 fail-closed”的直觉不同，但符合计划 1247。
   需审计确认该语义是否可接受。
3. **rotate 的冲突并存无专项测试**：现有 rotate 状态 3 测试是“origin 残缺”，不是 P1 并存冲突。
4. **`materialize()` 在分类前 `_store.ensure()`**：冲突时可能创建全局实例 ID 文件（空数据目录场景），
   不写 DB/Journal，但不符合“零文件写”的严格表述。
5. **批量导出恢复门只在循环前一次**：循环期间的状态变化不会被再次恢复门拦截；
   导出为只读，未发现身份写入路径。
6. **`_export_record` 私有但无内部恢复门**：当前仅被两个有门公开入口调用；
   若未来被其他路径复用，需自行保证门。
7. **导入可制造冲突**：向已有 MATERIALIZE 的条目追加 origin 不会被导入拒绝；
   P1 只在分类时报告状态 3，不自动修复。需审计确认这是预期流程。

---

## 7. 证据分级汇总

| 结论 | 级别 |
| --- | --- |
| 4 个生产 classify 调用点及其恢复门位置 | **【静态】**（grep + 代码） |
| 冲突判定条件、状态 3、ID 置空 | **【测试】**（8 项冲突 + 2 项控制组） |
| 导出/ensure/materialize 冲突零 DB/Journal 写 | **【测试】** |
| rotate 跳过状态 3、状态 4 中止 | **【静态】**；rotate 状态 3 有残缺-origin 测试，非并存冲突 |
| 损坏 Journal 阻断导入 | **【测试】** |
| 启动因损坏 Journal 失败 | **【静态】**，未做真实启动集成测试 |
| PREPARED + ImportOrigin 恢复失败 | **【静态】**，未专项测试 |
| 跨进程恢复/竞争 | **【未验证】** |
| PostgreSQL 上的全部行为 | **【未验证】**（无 PG 实例） |