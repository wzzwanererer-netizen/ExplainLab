# V2 A1-03 最终审计补充：步 8c Phantom 非碰撞新增覆盖

- 任务范围：只核实一个边界——**非碰撞 phantom INSERT** 是否被重建写后复核发现，不扩大 A1-03 范围。
- 审计基线：HEAD `9634ad1`（no-op 专项审计修复后）。分支 `fix/m0-admission-and-m5-regressions`。
- 执行日期：2026-11-20。
- 结论标签：【已验证事实】【源码位置】【验证场景与测试编号】【真实测试证据】【全量回归】【修复前后对照】【已知局限】【边界声明】。

## 0. 结论（先读）

**当前实现已经保证「当前数据库链接 ID 集合 == plan.row_snapshots ID 集合」，无需修改生产代码。**

但保证来源**不是步 8c**：步 8c 只做**单向**遍历（快照 → 当前），不检查「当前 ⊆ 快照」。真正提供全表 ID 集合双向一致 guarantee 的是**步 8 的治理列基线比对**——`_governance_baseline` 是**全表** `id` 键 dict（无 WHERE），步 8 比较写前/写后**整 dict 相等**。任何新增行（含非碰撞 phantom）都会使该 dict 多一个 `id` 键 → 不等 → 抛 `LinkRebuildPostWriteError("写后治理列与步 3b 基线不一致")` → 整体回滚零写入。

一条**满足版本同构（version==target）且 key-title 一致（key==norm(title,alias)）的非碰撞 phantom**，确实**绕过**步 8 版本同构复核、键对唯一复核与步 8c 逐行复核（它不在快照中），但**无法绕过**治理基线的全表 ID/治理列比对。SQLite（空/混合 updates，同事务注入）与真实 PostgreSQL（同事务注入兜底 + 真实双连接表锁阻外部 INSERT）均已真实测试证实。

依任务处理原则「如果当前实现已经保证 ID 集合完全一致：提供源码位置和真实测试证据，**不修改代码**」——本轮**仅新增验证测试**（SQLite 4 + PG 6），**生产代码零改动**，既有门禁零删除、断言零弱化。

## 1. 审查问题逐项回答

| 审计问题 | 回答 | 证据 |
|---|---|---|
| 当前 DB 链接 ID 集合是否必须与 plan.row_snapshots ID 集合完全一致？ | **是**（被动强制）。治理基线全表 `id→治理列` dict 写前/写后必须整等，蕴含 ID 集合相同（且治理列相同）。增/删任一 id → dict 不等 → 拒绝。 | `services/links.py:297-306,378,457-458`；P3 测试 |
| 步 8c 是否执行全表 ID 集合**双向**比较？ | **否**。步 8c 仅 `for snap in plan.row_snapshots` 单向遍历（存在性 + source_id/title/alias 不可变 + key-title）。phantom 不在快照 → 步 8c 不检查它。 | `services/links.py:486-502`；P3 测试 |
| SQLite 空 updates、非碰撞 phantom 是否被发现？ | **是**，由步 8 治理基线发现（非步 8c）。 | P1 `test_sqlite_empty_updates_noncollision_phantom_rejected_by_governance` |
| 额外记录是否可能绕过版本同构与 key-title 一致性检查？ | **能绕过这两项**（phantom 用目标版本 + 正确 key-title），但**仍被治理基线拒绝**。 | P1/P3 显式断言 phantom version==target、key==norm、非碰撞、不在快照 |
| PG 表锁是否阻断外部 INSERT（空/混合）？ | **是**。SHARE ROW EXCLUSIVE 与 INSERT 的 ROW EXCLUSIVE 冲突，lock_timeout 确定性触发；步 1b 无条件取锁（空 updates 亦持锁）。 | P4/P5 真实双连接 |

## 2. 源码位置（精确行号，HEAD 9634ad1）

### 2.1 治理基线 = 全表 id 键 dict（ID 集合一致性的真实守护）

`backend/app/services/links.py:297-306`：

```python
def _governance_baseline(session: Session) -> dict[str, tuple]:
    """链接行治理列基线（步 3b）：target_id/resolution/cross_space/created_at。"""
    stmt = select(
        KnowledgeLinkORM.id,
        KnowledgeLinkORM.target_item_id,
        KnowledgeLinkORM.resolution,
        KnowledgeLinkORM.cross_space,
        KnowledgeLinkORM.created_at,
    )
    return {r.id: (r.target_item_id, r.resolution, r.cross_space, r.created_at) for r in session.execute(stmt)}
```

- **无 WHERE** → 覆盖**当前全表**每一行，dict 键 = 全部链接 id。
- 步 3b 写前捕获：`services/links.py:378` `governance_before = _governance_baseline(session)`。
- 步 8 写后比对：`services/links.py:457-458`：

```python
if _governance_baseline(session) != governance_before:
    raise LinkRebuildPostWriteError("写后治理列与步 3b 基线不一致")
```

- **整 dict 相等**（Python `dict.__eq__` 比较键集合 + 每键值）→ 新增 id（phantom）使键集合变大 → 不等 → 拒绝。删除 id 同理（且步 8c 存在性复核兜底）。这是**比 ID 集合相等更强**的 guarantee（ID 集合 + 治理列均须一致）。

### 2.2 步 8c = 单向遍历快照（不检查额外行）

`backend/app/services/links.py:462-502`（no-op 专项审计新增）：

```python
final_rows = {r.id: r for r in session.execute(select(...6 列...))}
for snap in plan.row_snapshots:          # ← 只遍历快照，单向
    r = final_rows.get(str(snap.link_id))
    if r is None:
        raise LinkRebuildPostWriteError("写后快照行缺失（窗口②删除行）")
    if (UUID(r.source_item_id) != snap.source_id
            or r.target_title != snap.target_title
            or r.alias != snap.alias):
        raise LinkRebuildPostWriteError("写后 source_id/标题/别名与计划快照不一致（窗口②漂移，含 no-op 行）")
    expected_key = link_key_for_version(r.link_normalization_version, r.target_title, r.alias)
    if r.normalized_link_key != expected_key:
        raise LinkRebuildPostWriteError("写后键与当前 title/alias 不一致（过期键）")
```

- `final_rows` 虽含全表，但循环只取 `snap.link_id` → **phantom 的 id 不在 `plan.row_snapshots`，永不被步 8c 检查**。
- 步 8c **没有** `set(final_rows) == {snap ids}` 之类的双向比较。故「步 8c 单独」**不**保证 ID 集合一致；该 guarantee 来自 §2.1 治理基线。

### 2.3 步 8 其余复核对非碰撞 phantom 均「放行」

`services/links.py:443-456`：

- 版本同构 `versions_after == {target}`：phantom 用目标版本 → 全表仍 `{target}` → **放行**。
- 键对唯一 `len(set(pairs_after)) == len(pairs_after)`：phantom 非碰撞 → `(source_id,key)` 唯一 → **放行**。

→ 非碰撞 phantom 唯一被拦下的位置是 §2.1 治理基线（line 457）。

### 2.4 步 1b 写锁（PG 外部窗口②关闭）

`services/links.py:343` `acquire_rebuild_write_lock(session)`（**无条件**，空 updates 亦取锁）。PG = `LOCK TABLE knowledge_link IN SHARE ROW EXCLUSIVE MODE` + `SELECT id FOR UPDATE`，持锁至提交；SHARE ROW EXCLUSIVE 与 INSERT 所需 ROW EXCLUSIVE 冲突 → 外部 INSERT 被阻。SQLite acquire 为 no-op，读阶段不锁 → 窗口②由步 8 治理基线乐观复核兜底。

### 2.5 plan() no-op 语义（ phantom 场景前提）

`knowledge-core/src/knowledge_core/markdown/link_service.py` `LinkKeyRebuild.plan()`：`row_snapshots` 覆盖全表行；`updates` 排除「键已等于目标重算键且 version==target」的 no-op 行。**no-op 要求 version==target**，故空 updates（全 no-op）与混合 update+no-op 只在 **source==target**（同版本键漂移修复）出现。本轮据此构造真实空/混合计划。

## 3. 验证场景与测试编号

新增两个**自包含**测试文件（importlib 口径，无跨文件导入）：

- SQLite：`backend/tests/test_links_phantom_noncollision.py`（4 测试）
- 真实 PG：`backend/tests/test_links_phantom_noncollision_pg.py`（6 测试，`EXPLAINLAB_PG_TEST_URL` 门控）

phantom 统一构造为**非碰撞**（title="Phantom Noncollision"/"Phantom External"，键不同于任何现有行）、**目标版本 2**、**key==norm(title,alias)**、新 uuid id、可通过数据库约束。故障注入 = monkeypatch `links_module.check_plan_freshness`，门禁 C 真实判定后于**同一事务**插入 phantom（确定性复现窗口②）。

| # | 审计要求场景 | 方言 | 测试编号 | 结果 |
|---|---|---|---|---|
| 1 | 空 updates 非碰撞 phantom INSERT | SQLite | `test_sqlite_empty_updates_noncollision_phantom_rejected_by_governance` (P1) | 检测✓ 拒绝✓（治理基线）回滚✓ 零部分更新✓ ID还原✓ |
| 2 | 混合 updates 非碰撞 phantom INSERT | SQLite | `test_sqlite_mixed_updates_noncollision_phantom_no_partial_update` (P2) | 检测✓ 拒绝✓ r1写入回滚✓ 零部分更新✓ ID还原✓ |
| 3 | 空 updates 表锁阻外部 INSERT | 真实 PG | `test_pg_lock_blocks_external_noncollision_phantom_insert_empty_updates` (P4) | lock_timeout✓ 释放后可插✓ |
| 4 | 混合 updates 表锁阻外部 INSERT | 真实 PG | `test_pg_lock_blocks_external_noncollision_phantom_insert_mixed_updates` (P5) | lock_timeout✓ 释放后可插✓ |
| 5 | 步 8c 是否全表 ID 双向比较 | SQLite+PG | `test_sqlite_phantom_id_set_guarantee_is_governance_not_step8c` (P3) / `test_pg_phantom_id_set_guarantee_is_governance_not_step8c` | 步8c单向✗双向；治理基线全表dict✓ |
| 6 | 额外记录绕过版本同构+key-title | SQLite+PG | P1（含断言）/ `test_pg_empty_updates_noncollision_phantom_rejected_by_governance` | 绕过这两项✓ 但治理基线仍拒✓ |
| 控制 | 空 updates 无 phantom 不误拒 | SQLite+PG | `test_sqlite_empty_updates_control_no_phantom` / `test_pg_empty_updates_control_no_phantom` | rebuilt updated=0✓ ID/版本/key-title保持✓ |
| 补充 | 混合 updates 同事务 phantom 兜底 | 真实 PG | `test_pg_mixed_updates_noncollision_phantom_no_partial_update` | 治理基线拒✓ r1回滚✓ 零部分更新✓ |

每项均断言：检测漂移 / 拒绝过期计划（`LinkRebuildPostWriteError`，消息含「治理列」证明触发守护）/ 整体回滚（`_snapshot == before` 逐列）/ 零部分更新（混合 r1 键回滚为 STALE-KEY）/ ID 集合双向还原（`_link_ids == ids_before`，phantom id 不在）/ 版本同构（`{2}`）/ key-title 一致（成功态）。P1/P3 额外显式断言 phantom **非碰撞**（pairs 数=4 无重复）、**version==target**、**key==link_key_for_version(2,title,alias)**、**id 不在快照**——证明其绕过版本同构/键对唯一/步 8c 仍被治理基线拒绝。

## 4. 真实测试证据（原始输出落盘）

证据目录：`docs/acceptance/V2-A1-03-final-phantom-audit/evidence/`

| 文件 | 内容 | 关键结果 |
|---|---|---|
| `after-sqlite-phantom.txt` | SQLite 专项 4 测试 -v | **4 passed** |
| `after-pg-phantom.txt` | 真实 PG 专项 6 测试 -v | **6 passed** |
| `sqlite-full.txt` | SQLite 全量（无 PG env） | **930 passed, 178 skipped** |
| `pg-full.txt` | 全量 + 真实 PG16.8（port 5432） | **1108 passed, 0 skipped** |
| `core-independence-guard.txt` | `test_interfaces.py` | **14 passed** |
| `a1-02-frozen.txt` | canonical+codec+frontmatter | **291 passed** |
| `ruff.txt` | `uv run ruff check` | **All checks passed!** |
| `frontend-test.txt` | Vitest | **72 passed (10 files)** |
| `frontend-typecheck.txt` | `tsc -b` | 无错误 |
| `frontend-build.txt` | `vite build` | ✓ built（graphLayout chunk 警告为既有） |

PG 连接：`EXPLAINLAB_PG_TEST_URL="postgresql+psycopg://postgres@127.0.0.1:5432/explainlab_test"`，`pg_ctl status` = server running (PID 50260)，经真实在线 Alembic `upgrade head` 建表。绝不以离线 SQL/假数据/SQLite 结果冒充 PG。

## 5. 全量回归结果（生产代码零改动）

| 套件 | 上轮基线（9634ad1） | 本轮 | 增量来源 |
|---|---|---|---|
| SQLite 全量（无 PG） | 926 passed / 172 skipped | **930 passed / 178 skipped** | +4 SQLite phantom 测试；+6 PG phantom 测试被跳过 |
| 全量 + 真实 PG | 1098 passed / 0 skipped | **1108 passed / 0 skipped** | +4 SQLite phantom +6 PG phantom（PG env 下全部运行） |
| Core 独立性守护 | 14 | **14** | 不变 |
| A1-02 冻结 | 291 | **291** | 不变 |
| ruff check | clean | **clean** | 新测试文件亦 lint 通过 |
| 前端 test/typecheck/build | 72 / clean / ok | **72 / clean / ok** | 不变 |

无回归。受保护路径 git 确认未触碰：`backend/app/`、`knowledge-core/`、`backend/alembic/`、`models.py`、`uv.lock`、`pyproject.toml`、`frontend/package*.json`、`MILESTONES.md`（`git status --short` 对这些路径输出为空）。

## 6. 修复前后对照

**不适用——本轮无生产代码修复。** 既有步 8 治理基线（全表 id dict 相等）已完整覆盖非碰撞 phantom 新增，ID 集合一致性已保证。依任务原则「已保证则不修改代码」，仅新增验证测试固化该 guarantee。

- 生产代码 diff：**空**（`git status` 仅 2 个新增测试文件 untracked）。
- 既有门禁：零删除、零弱化（步 8 版本同构/键对唯一/治理基线/条目基线 + 步 8c 全部保留）。
- 新增测试为** additive 验证**，不改动任何既有测试断言。

机制取证（P3）：在 apply 之外独立复算治理基线 dict，证明 `set(gov_before) == snap_ids`、插入 phantom 后 `set(gov_after) == snap_ids | {phantom_id}`、`gov_after != gov_before` → 步 8 line457 比较必失败。回滚后 `gov_baseline() == gov_before`、`_link_ids == snap_ids`。这直接证明「ID 集合双向一致由治理基线保证，而非步 8c 单向遍历」。

## 7. 已知局限

1. **ID 集合保证是隐式的**：它来自治理基线「全表 id→治理列 dict 整等」的副作用（该基线本意是治理列复核），**并非**一条显式的 `set(current_ids) == set(snapshot_ids)` 断言。当前实现下它**稳健**（任何新 id 必改变 dict 键集合，即使治理列值相同），但属隐式 guarantee。P3 测试固化「治理基线覆盖全表 ID」这一前提，防止未来把基线改成只比对快照行而悄然回归。
2. **步 8c 本身单向**：若治理基线被削弱为快照行子集比对，步 8c 不能独立兜住 phantom 新增。本轮**未**给步 8c 增加双向 ID 比较（因治理基线已保证，依「不修改代码」原则）；此依赖关系已记录，供阶段级复审知悉。
3. **PG 外部窗口②由表锁关闭**：真实双连接证明外部非碰撞 INSERT 被 lock_timeout 阻断（空/混合计划同口径，步 1b 无条件取锁）。同事务故障注入**按设计绕过表锁**（锁阻他连接、不阻本事务），用于检验步 8 治理基线逻辑本身——这是 dialect-neutral 兜底，非 PG 外部可达路径。
4. **SQLite 读阶段无写锁**：空 updates 的 apply 为只读事务（零 UPDATE，不取 RESERVED），窗口②外部可达，由步 8 治理基线乐观复核兜底（P1/P2 实证）。
5. **非碰撞 phantom 是最难案例**：它满足版本同构 + key-title + 非碰撞，绕过步 8 前两项复核与步 8c，唯治理基线拦下。本轮已对此 hardest case 真实取证；碰撞 phantom（既有 `test_noop_phantom_insert_collision_rejected`）另由键对唯一/约束兜底，不在本轮重复。
6. **范围限定**：本轮只核实 phantom 非碰撞新增边界，未触及 A1-03 其他已知条件项（K1 治理批准路径、gate-C 残留并发窗口、D8 无 HTTP 写入口、v2 规则 fixture-only 等仍按上轮记录待阶段级复审）。

## 8. 边界声明

- 生产代码**零改动**；Core 端口/纯函数、数据模型、Alembic 迁移、依赖、锁定文件、`MILESTONES.md` **均未触碰**。
- 既有门禁零删除、断言零弱化；新增测试为 additive 验证。
- 已按批次提交（见提交记录），**未 push**。
- **不进入 A1-04**；完成后停止，等待 ChatGPT 阶段级独立复审与用户批准。