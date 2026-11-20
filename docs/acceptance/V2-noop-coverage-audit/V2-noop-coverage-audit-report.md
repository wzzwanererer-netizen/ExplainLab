# V2 A1-03 最终专项审计报告：No-op 行并发保护完整性

- **审计对象**：K2 P2 六字段修复（提交 `b6c7e15`）后，重建计划中 **no-op 行**（键已等于目标版本重算键、版本已是目标）是否获得完整并发保护。
- **审计方法**：真实源码审查 + 真实故障注入测试（SQLite 与真实 PostgreSQL 分别运行），修复前先取证、修复后回归。**不以普通 update 行的 P2 测试冒充 no-op 测试**——所有漂移均施加于显式断言为 no-op（不在 `plan.updates`）的行。
- **结论**：发现真实缺陷（no-op 行窗口②漂移不被检测，过期/不一致行被提交，混合计划存在部分更新）。已实施**最小方言中立修复**（步 8c 逐行复核全部快照行），SQLite 与真实 PG 八场景全过，全量回归零回归。
- **边界**：本审计仅修复/测试/文档；未改 Core 端口、数据模型、迁移、依赖、`MILESTONES.md`；未进入 A1-04；**未 push**。完成后停止，等待阶段级独立复审。

---

## 一、【已验证事实】源码路径审查

### 1.1 `LinkKeyRebuild.plan()` 的 snapshots 与 updates
`knowledge-core/src/knowledge_core/markdown/link_service.py:906-1021`：
- `row_snapshots`（:910-921）覆盖 **全部行**（含 no-op），每行 6 字段 + target_id。
- `updates`（:992-1009）过滤条件 `if not (new_keys[r.id] == r.normalized_link_key and r.link_normalization_version == target_version)` → **no-op 行被排除出 updates**。
- **关键推论**：no-op 条件要求 `version == target_version`。故跨版本重建（source≠target，如 1→2）时**每行都是 update**（version≠target）；「全 no-op（空 updates）」与「混合 update+no-op」**只在 source==target**（同版本修复键漂移）时出现。本审计据此构造真实 no-op/混合/空 updates 计划（见 §三测试夹具）。
- 空 updates 时 `status="ready"`、`source_version=target_version`、`unchanged=observed_row_count=len(rows)`（:1010-1021）。

### 1.2 `apply_link_key_plan()` 步 3 / 步 7 / 步 8
`backend/app/services/links.py`：
- **步 3**（:355-374）：重读当前全表 6 列（id/source_id/key/version/title/alias）→ `current`。
- **步 3b**（:375-377）：`_governance_baseline`（id→target_id/resolution/cross_space/created_at）+ `_item_baseline`（knowledge_item 全列）。
- **步 5 门禁 C**（:387-390）：`check_plan_freshness(plan, current)`，对**全部行**（含 no-op）6 字段精确比对 + 逐行重算 expected_key；no-op 分支（link_service.py:390-403）`cur.key != expected_key or cur.version != target → noop_row_requires_update`。**仅关闭窗①（重读时刻）**。
- **步 6**（:392-405）：新键唯一性，no-op 行以**当前**键/源参与。
- **步 7 P2**（:407-438）：`for u in plan.updates` 逐行 `UPDATE ... WHERE id + source_id + old_key + old_version + target_title + alias`，`rowcount != 1 → LinkRebuildPostWriteError`。**no-op 行不在 updates → 不进入步 7 → 不受 P2 六字段前置保护**。
- **步 8**（:440-458，修复前）：① 全表版本同构 `versions_after == {target}`；② `(source_id, key)` 键对唯一；③ 治理列基线相等；④ knowledge_item 基线相等。**不重读 target_title/alias，不逐行比对快照，不验 key==norm(title,alias)**。

### 1.3 六字段 P2 WHERE 条件
步 7 WHERE 含 `id/source_item_id/normalized_link_key(old)/link_normalization_version(old)/target_title/alias`（:421-428）。`new_key` 由 title+alias 派生、唯一域为 `(source_id, key)`，故六字段覆盖全部影响 new_key 与唯一域的正确性字段——**但仅对 update 行生效**。

### 1.4 no-op 行是否进入 UPDATE
**否**。步 7 仅迭代 `plan.updates`，no-op 行被 plan() 排除（§1.1）。空 updates 时步 7 循环体**零次执行**。

### 1.5 空 updates 时是否仍获有效并发保护
- **步 1b 取锁无条件**（:341）：PG `acquire_rebuild_write_lock` 取 SHARE ROW EXCLUSIVE + FOR UPDATE（持锁至提交），**即便空 updates 仍取锁** → 阻一切外部并发写（窗②由锁关闭）。SQLite `acquire` 为 no-op；空 updates 时步 7 零写 → 整个 apply 事务**只读，从不取 RESERVED 写锁** → 窗②在 SQLite 上**不由锁保护**。
- 修复前：空 updates 的 SQLite apply 对 no-op 行漂移**无任何检测**（步 7 无 P2、步 8 不查 title/alias/key-title）→ 缺陷在 SQLite 上**真实可达**。

### 1.6 步 8 是否覆盖全部原始快照
**修复前否**。步 8 仅聚合校验（版本同构/键对唯一/治理基线/条目基线），治理基线列为 target_id/resolution/cross_space/created_at，**不含 title/alias/source_id/key**。故 no-op 行的 title/alias/source_id（无碰撞时）/key 漂移在窗②**不被步 8 发现**。

---

## 二、【发现的缺陷】no-op 行窗口②保护缺口

**根因**：no-op 行不进步 7（无 P2），而步 8 不逐行复核字面/源/键-title 一致性。门禁 C 通过后（窗②）并发修改 no-op 行的 title/alias/source_id/key（键列未同步改），apply 仍报 `rebuilt` 并提交不一致行；混合计划中 update 行被写入而 no-op 漂移被放过 → **部分更新**。

### 2.1 修复前真实取证（原始输出见 evidence/）

| 场景 | SQLite（before-fix-sqlite.txt） | 真实 PG（before-fix-pg.txt） |
|---|---|---|
| 4 no-op title 漂移 | **FAILED — DID NOT RAISE** | **FAILED — DID NOT RAISE** |
| 5 no-op alias 漂移 | **FAILED — DID NOT RAISE** | **FAILED — DID NOT RAISE** |
| 6 no-op source_id 漂移（无碰撞） | **FAILED — DID NOT RAISE** | **FAILED — DID NOT RAISE** |
| 7 混合 no-op 漂移（部分更新） | **FAILED — DID NOT RAISE** | **FAILED — DID NOT RAISE** |
| 8 空 updates 并发修改 | **FAILED — DID NOT RAISE** | **FAILED — DID NOT RAISE** |
| 补充 no-op key 漂移 | **FAILED — DID NOT RAISE** | **FAILED — DID NOT RAISE** |
| 1/2/3 控制组 | PASSED | PASSED |
| no-op 版本漂移（步8同构） | PASSED（既有守护） | PASSED（既有守护） |
| no-op phantom 碰撞（步8唯一） | PASSED（既有守护） | PASSED（既有守护） |
| 只读取锁取证 | PASSED（SQLite 0 UPDATE） | PASSED（PG 空 updates 仍取锁） |
| **合计** | **6 failed / 6 passed** | **6 failed / 7 passed** |

### 2.2 具体腐败证据（diag-before-fix.txt，修复前）
```
[场景4] plan.updates 数 = 0 (空 updates，全 no-op)
[场景4] apply 报告 status = rebuilt updated = 0
[场景4] no-op 行 r2: title='Drifted Title' key='targettwo\x1falias'
[场景4] 按当前 title 重算 expected_key='driftedtitle\x1falias'
[场景4] key-title 一致? False  <-- 过期键被提交

[场景7] apply 报告 status = rebuilt updated = 1
[场景7] update 行 r1 key='targetone\x1f' (原 STALE-KEY → 被写入新键 = 部分更新)
[场景7] no-op 行 r2 title='Drifted Noop' key='targettwo\x1falias'
[场景7] r2 key-title 一致? False  <-- 过期键被提交
```

### 2.3 可达性诚实界定
- **SQLite**：读阶段不锁保护（`test_links_concurrency.py::test_sqlite_read_phase_not_lock_protected` 实测固化），空 updates apply 只读 → 窗②外部漂移**真实可达**，缺陷成立。
- **PG**：表锁字段无关地阻一切外部写（`test_pg_lock_blocks_concurrent_noop_row_drift` 真实双连接证明，修复前即 PASSED）→ 窗②外部漂移被锁关闭。但步 8 对 no-op 行**无逐行兜底**，与 update 行（有 P2）不对称；K2 设计明确「纵深防御，不依赖锁单一手段」。同事务故障注入绕过表锁（锁阻他连接、不阻本事务）确定性暴露步 8 逻辑缺口。
- 触发漂移需「改 title/alias/source 但键列未同步改」的写入（应用 `update_link` 总是同步重算键且不改 source_id）；与上一轮 P2 字段审计同口径，属一致性/对抗性写入下的防御缺口。修复为**双方言统一的纵深防御补齐**。

---

## 三、【修复内容】最小方言中立修复

### 3.1 设计原则
- 不删既有门禁、不弱化断言；不改 Core 纯函数/端口签名/数据模型/迁移/依赖。
- 方言中立：纯 SQLAlchemy 列选择 + Core 纯函数 `link_key_for_version`，零方言分支（AGENTS.md §5）。
- 在步 8 末尾**新增步 8c**：逐行复核**全部原始快照行**（含 no-op），与 update 行 P2 同口径。

### 3.2 步 8c（`backend/app/services/links.py`，import :52 + 步 8c :462-503）
重读全表 6 列，对 `plan.row_snapshots` 每行：
1. **行存在**：快照行缺失（窗②删除）→ 拒绝（治理基线已兜底，再逐行确认）；
2. **不可变字面/源**：`source_id/target_title/alias` 与快照精确相等（重建只写键/版本/updated_at，这三者对全部行不可变）→ 任一漂移拒绝（no-op 行 source_id **无条件拒绝**，而非仅碰撞时，与 update 行 P2 对称）；
3. **key-title 一致**：`key == link_key_for_version(version, title, alias)`（含 no-op 过期键）。
版本同构已于步 8 上方确认（全表==target），故 `link_key_for_version` 取目标规则有效。任一不符抛 `LinkRebuildPostWriteError` → with 块整体回滚零写入。

### 3.3 守护更新（纯增强，非弱化）
步 8c 新增一次 6 列重读（`sixcol`）。两处镜像守护同步**增强**：
- `test_links.py` / `test_links_pg.py` T34：`sixcol == 1 → 2`（步3重读 + 步8c复核）。
- T39 成功顺序：末尾追加 `"sixcol"`（`... pairs, gov, items, sixcol`）。
- 门禁失败路径（T39 gate a/b/c）顺序**不变**（步 8c 在拒绝路径不执行）；distinct/update/gov/items/pairs 计数**不变**。

### 3.4 改动文件（fix.diff，123 行）
| 文件 | 改动 |
|---|---|
| `backend/app/services/links.py` | import `link_key_for_version` + 步 8c（44 行）+ docstring |
| `backend/tests/test_links.py` | T34 sixcol 1→2、T39 成功序追加 sixcol（增强） |
| `backend/tests/test_links_pg.py` | 同上（PG 镜像） |
| `backend/tests/test_links_noop_coverage.py` | **新增** SQLite 12 测试 |
| `backend/tests/test_links_noop_coverage_pg.py` | **新增** 真实 PG 13 测试 |

**受保护路径零改动**（`git status` 核验为空）：`knowledge-core/`、`backend/app/models.py`、`backend/app/db/`、`backend/alembic/`、`uv.lock`、`pyproject.toml`、`frontend/package*.json`、`MILESTONES.md`。

---

## 四、修复后验证：八场景 × 七问矩阵（SQLite 与真实 PG 同口径）

测试编号：SQLite `test_links_noop_coverage.py`、PG `test_links_noop_coverage_pg.py`（同名同断言）。每项均经真实故障注入（monkeypatch 门禁 C 于重读后、写前同事务注入漂移）+ 真实数据库运行。

| # | 场景 / 测试名 | 检测漂移 | 拒绝过期计划 | 整体回滚 | 部分更新 | key-title 一致 | 版本同构 | 只读事务未获写锁 |
|---|---|---|---|---|---|---|---|---|
| 1 | 全更新控制 `scenario1_all_rows_update_control` | 无漂移 | rebuilt | — | 无 | ✅{2} | ✅{2} | 有写（步7） |
| 2 | 全 no-op 控制 `scenario2_all_noop_control` | 无漂移 | rebuilt updated=0 | — | 无 | ✅{2} | ✅{2} | SQLite 只读0写/PG 取锁 |
| 3 | 混合控制 `scenario3_mixed_update_and_noop_control` | 无漂移 | rebuilt updated=1 | — | 无 | ✅{2} | ✅{2} | 有写（r1） |
| 4 | no-op title 漂移 `scenario4_noop_title_drift_rejected` | ✅步8c | ✅抛异常 | ✅snap==before | ✅零 | ✅回滚后 | ✅{2} | SQLite 只读/PG 锁 |
| 5 | no-op alias 漂移 `scenario5_noop_alias_drift_rejected` | ✅步8c | ✅ | ✅ | ✅零 | ✅ | ✅{2} | 同上 |
| 6 | no-op source_id 漂移 `scenario6_noop_source_id_drift_rejected` | ✅步8c（无条件） | ✅ | ✅ | ✅零 | ✅ | ✅{2} | 同上 |
| 7 | 混合 no-op 漂移 `scenario7_mixed_noop_drift_no_partial_update` | ✅步8c | ✅ | ✅r1写入一并回滚 | ✅零（r1键回STALE-KEY） | before态含故意漂移r1* | ✅{2} | 有写后回滚 |
| 8 | 空 updates 并发修改 `scenario8_empty_updates_concurrent_modify_rejected` | ✅步8c | ✅ | ✅ | ✅零 | ✅ | ✅{2} | SQLite 只读0写/PG 取锁 |
| 补 | no-op key 漂移 `noop_key_drift_rejected` | ✅步8c key-title | ✅ | ✅ | ✅零 | ✅ | ✅{2} | 同上 |
| 补 | no-op 版本漂移 `noop_version_drift_rejected_by_step8_homogeneity` | ✅步8同构（既有） | ✅ | ✅ | ✅零 | ✅ | ✅{2} | 同上 |
| 补 | no-op phantom 碰撞 `noop_phantom_insert_collision_rejected` | ✅步8唯一/DB UNIQUE（既有） | ✅ | ✅ | ✅零 | ✅ | ✅{2} | 同上 |
| 取证 | SQLite 空 updates 只读 `sqlite_empty_updates_apply_is_readonly_no_write_lock` | — | rebuilt | — | 0 UPDATE | ✅ | ✅{2} | **✅只读未取写锁（实测固化）** |
| 取证 | PG 空 updates 取锁 `pg_empty_updates_apply_holds_write_lock` | — | rebuilt | — | 0 UPDATE | ✅ | ✅{2} | **PG locks≥2（空 updates 仍取锁）** |
| 取证 | PG 双连接阻 no-op 漂移 `pg_lock_blocks_concurrent_noop_row_drift` | ✅表锁（lock_timeout） | 外部写被阻 | — | — | — | — | PG 持锁阻 title/alias/source |

\* 场景7 的 before 态含**故意**键漂移的 r1（`STALE-KEY`，使其成为 update 行）；回滚恢复该 before 态，故「全表 key-title 一致」不变量仅对**成功重建后**成立，不对回滚到故意不一致的 before 态成立。`snap == before` 已逐列证明零部分更新（r1 写入与 r2 漂移均回滚），并显式断言 `r1.key=='STALE-KEY'`、`r2.title=='Target Two'`。

**修复后结果**：SQLite no-op **12 passed**（after-fix-sqlite-noop.txt）；真实 PG no-op **13 passed**（after-fix-pg-noop.txt）。八场景全部：检测漂移✅、拒绝过期计划✅、整体回滚✅、零部分更新✅、版本同构✅。

---

## 五、全量回归（修复后，原始输出见 evidence/）

| 套件 | 结果 | 证据 | 基线对照 |
|---|---|---|---|
| SQLite 全量（backend+core） | **926 passed / 172 skipped** | sqlite-full.txt | 914→926（+12 no-op）；159→172（+13 PG 门控） |
| 真实 PostgreSQL 全量 | **1098 passed / 0 skipped** | pg-full.txt | 1073→1098（+12 SQLite no-op +13 PG no-op） |
| SQLite 焦点（no-op+T34/T39+K2+P2） | **118 passed** | after-fix-sqlite-focused.txt | T34/T39 守护增强后全过 |
| 真实 PG 焦点（no-op+T34/T39+K2+P2） | **120 passed** | after-fix-pg-focused.txt | 同上 |
| Core 独立性守护 | **14 passed** | core-independence-guard.txt | 与基线一致 |
| A1-02 冻结（canonical/codec/frontmatter） | **291 passed** | a1-02-frozen.txt | 与基线一致 |
| ruff check | **All checks passed** | ruff.txt | 仅 check，未 format |
| 前端 test | **72 passed（10 文件）** | frontend-test.txt | 与基线一致 |
| 前端 typecheck（tsc -b） | **clean** | frontend-typecheck.txt | 与基线一致 |
| 前端 build | **✓ built**（graphLayout chunk 警告为既有） | frontend-build.txt | 与基线一致 |

K1（治理链接维护）、K2（双方言并发锁 + P2）、T22–T40 门禁矩阵、上一轮 P2 六字段覆盖测试**全部保持通过**，零回归。

---

## 六、【尚待验证】
- 无未验证的功能项。八场景与全量回归均在真实 SQLite / 真实 PostgreSQL 实例运行通过。
- 真实**多进程**并发（非本审计的同事务确定性故障注入）下的 SQLite WAL 模式行为未在本轮专项覆盖；既有 K2 测试已固化默认 journal 模式读/写阶段锁语义，本审计沿用同口径。

## 七、【已知局限】（如实记录）
1. **SQLite 读阶段不锁保护**：空 updates 的 SQLite apply 为只读事务，从不取 RESERVED 写锁（`sqlite_empty_updates_apply_is_readonly_no_write_lock` 实测 0 UPDATE 固化）。窗②在 SQLite 上由**步 8c 乐观逐行复核**兜底（检测→拒绝→整体回滚零写入），非锁保护。此为方言真实语义，非伪称已锁。
2. **PG 表锁关闭外部窗②**：PG 即便空 updates 仍取 SHARE ROW EXCLUSIVE + FOR UPDATE（`pg_empty_updates_apply_holds_write_lock` locks≥2），外部并发写被阻（`pg_lock_blocks_concurrent_noop_row_drift` 双连接 lock_timeout 实证）。步 8c 在 PG 上为**纵深防御**（与 update 行 P2 对称），不依赖锁单一手段。
3. **同事务故障注入绕过表锁**：monkeypatch 门禁 C 于持有锁的**同一事务**注入漂移，锁阻他连接、不阻本事务，故 PG 侧注入直接检验步 8c 逻辑本身（确定性、非 flaky）；真实跨连接锁排除由独立双连接测试证明。
4. **可达性**：触发需「改 title/alias/source 但键列未同步改」的一致性/对抗性写入；应用 `update_link` 总同步重算键且不改 source_id。修复为防御补齐，与上一轮 P2 字段审计同口径。
5. **步 8c 新增一次 6 列重读**：成功路径查询数 sixcol 1→2（守护已同步增强）；拒绝路径不执行步 8c，查询序不变。纯列选择 + Core 纯函数，零方言分支、零新增依赖/迁移。
6. **场景7 回滚态含故意不一致 r1**：混合 before 态的 r1 键被故意置为 STALE-KEY（构成 update 行），回滚恢复该态，全表 key-title 一致不变量仅对成功重建后成立（已在矩阵脚注说明）。

---

## 八、测试编号 / 源码位置 / 证据索引

### 8.1 新增测试（25 个）
- SQLite `backend/tests/test_links_noop_coverage.py`（12）：scenario1/2/3/4/5/6/7/8、sqlite_empty_updates_apply_is_readonly_no_write_lock、noop_key_drift_rejected、noop_version_drift_rejected_by_step8_homogeneity、noop_phantom_insert_collision_rejected。
- 真实 PG `backend/tests/test_links_noop_coverage_pg.py`（13）：scenario1/2/3/4/5/6/7/8、pg_empty_updates_apply_holds_write_lock、noop_key_drift_rejected、noop_version_drift_rejected_by_step8_homogeneity、noop_phantom_insert_collision_rejected、pg_lock_blocks_concurrent_noop_row_drift。
- 守护增强：`test_links.py` / `test_links_pg.py` 的 T34（sixcol==2）、T39 成功序（追加 sixcol）。

### 8.2 源码位置
- plan no-op 排除：`knowledge-core/.../link_service.py:992-1009`；snapshots 全行：:910-921。
- 门禁 C no-op 分支：`link_service.py:390-403`。
- 步 7 P2（仅 updates）：`backend/app/services/links.py:407-438`。
- 步 8（修复前聚合校验）：`links.py:440-458`；**步 8c（新增逐行复核）**：`links.py:462-503`；import：:52。
- 取锁：`links.py:341` → `backend/app/db/locking.py`（PG 表锁/SQLite no-op，未改）。

### 8.3 证据文件（evidence/）
before-fix-sqlite.txt、before-fix-pg.txt、diag-before-fix.txt、after-fix-sqlite-noop.txt、after-fix-pg-noop.txt、after-fix-sqlite-focused.txt、after-fix-pg-focused.txt、sqlite-full.txt、pg-full.txt、core-independence-guard.txt、a1-02-frozen.txt、ruff.txt、frontend-test.txt、frontend-typecheck.txt、frontend-build.txt、fix.diff。

---

## 九、边界声明
- 未改 Core 端口/纯函数、数据模型、Alembic 迁移、依赖锁定文件、`MILESTONES.md`（git 核验为空）。
- 未删除既有门禁、未弱化断言（守护为纯增强）。
- 未进入 A1-04；**未 push**；提交后停止，等待 ChatGPT 阶段级独立复审与用户批准。