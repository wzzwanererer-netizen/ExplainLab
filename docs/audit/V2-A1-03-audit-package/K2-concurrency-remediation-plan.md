# K2 整改方案 — 链接重建并发窗口控制（双方言可执行）

> **性质**：**设计建议（待审批后实施）**。本轮只设计方案，**不修改业务代码、不新增测试文件、不安装依赖、不改迁移**。
> **依据**：[`A1-03-final-review.md`](A1-03-final-review.md) §2/§3；真实源码 file:line；既有门禁测试 T22–T40。
> **范围红线**：并发控制封装在 **backend 数据库适配层**（`app/db/`、`app/services/links.py`），Core 纯函数与端口签名不变；不重写 Core；方言差异不得进业务服务/Core（AGENTS.md §5/§11）。
> **标签**：每条标注 **【已验证事实】/【设计建议】/【尚待验证】/【潜在风险】**。

## 1. 问题陈述（已验证事实）

### 1.1 两个窗口

- **【已验证事实】** **窗口①（计划生成 → 应用）已关闭**：`LinkKeyRebuild.plan`（link_service.py:906）只读生成 frozen 快照；`apply_link_key_plan`（services/links.py:308）步 3（:342）独占事务内重读全表，步 5 门禁 C `check_plan_freshness`（:374 → link_service.py:290）逐行比对（双向覆盖 + link_id 唯一 + 6 字段原始 Unicode 等值 + 每行新键重算含 no-op）。窗口①数据变化 → 拒绝 + 零写入 + requires_replan。T22–T30 实跑通过（evidence/t22-t40-function-map.txt）。
- **【已验证事实】** **窗口②（重读 → 提交）未关闭**：门禁 C 基于步 3 快照通过后，步 7（:394–405）批量写、步 9（:427）提交之间，并发事务可改链接行。步 7 为 **blind UPDATE `WHERE id=u.link_id`**（:397–405），**无键/版本乐观前置条件、无 rowcount 校验**。

### 1.2 无锁配置 / 无并发测试（硬证据）

- **【已验证事实】** `session.py`：SQLite `create_engine(url, connect_args={"check_same_thread":False})`（:25），**未设 journal_mode / isolation_level / busy_timeout**；PG `create_engine(url, pool_pre_ping=True)`（:40），**未设 isolation_level**。sessionmaker `autoflush=False, expire_on_commit=False`（:52）。`get_session`（:72）yield + finally close（回滚未提交事务）。
- **【已验证事实】** grep 锁/隔离关键字（journal_mode/WAL/BEGIN IMMEDIATE/isolation_level/with_for_update/FOR UPDATE/LOCK TABLE/busy_timeout）于 `backend/app/`+`backend/alembic/` → **空**；grep 并发关键字（concurrent/threading/Thread(/race/with_for_update）于链接测试 → **空**。
- **【已验证事实】** 门禁 C **不比对** target_id/resolution/cross_space/created_at/updated_at（link_service.py:299–300；LinkRowState:136「target_id 携带但不参与比对」）——治理列窗口内合法变化不拒绝；键/版本/title/alias/source/行数变化才拒绝。

## 2. 门禁保证矩阵（已验证事实 + 设计建议）

| 门禁 | 位置 | 保证 | **不**保证 |
|---|---|---|---|
| A 版本同构 | services/links.py:329（步 2） | 重读时全表版本集合 == {plan.source_version}（空表仅当 observed_row_count==0 放行） | 跨事务互斥；重读后到提交间的版本漂移 |
| B 计划自洽 | :366 → `_gate_b`:257 | 计划内部覆盖/唯一（**不查库**） | 任何数据库当前状态 |
| C 计划新鲜度 | :374 → link_service.py:290 | 计划快照 == 步 3 重读快照（关**窗口①**） | 步 3 之后（**窗口②**）的并发修改；治理列变化（故意不比对） |
| 步 6 新键唯一 | :379 | 代入 updates 后 (source_id,new_key) 无碰撞（基于步 3 快照） | 并发 INSERT 引入的新碰撞（窗口②） |
| 步 8 写后复核 | :407–425 | 同事务重读：版本 DISTINCT=={target}、键唯一、治理列/条目基线不变；不符抛 `LinkRebuildPostWriteError` → 整体回滚 | 步 8 → 步 9 间窗口；并发改 title（不改 version）可能绕过版本检查；READ COMMITTED 下可见性取决于隔离级别 |

**【已验证事实】** 门禁 A/B/C + 步 6/步 8 均**不提供跨事务互斥或隔离**。窗口②的关闭须靠**数据库锁/隔离**或**乐观并发控制**，而非现有门禁。

## 3. 双方言实际锁行为（设计建议 / 尚待验证）

> **【尚待验证】** 以下基于 SQLite/PG 文档化语义 + §1.2「无配置」事实推断，**非实跑并发测试**。真实交错行为须整改批次以双会话/线程真实测试核实。

### 3.1 SQLite（默认 rollback-journal，DEFERRED）

- **【设计建议】** 读持 SHARED 锁；写升级 RESERVED；提交需 EXCLUSIVE（**单写者**）。步 3 重读（SHARED）→ 步 7 写升级之间，另一写者可提交 → 本事务快照过期；写升级时另一写者持锁 → `SQLITE_BUSY`。
- **【设计建议】** `BEGIN IMMEDIATE` 在事务开始即持 RESERVED，**串行化写者**、关闭窗口②（重读前已独占写权）。`busy_timeout` 让争用等待而非立即 BUSY。WAL 模式允许读写并发但写者仍单写，须配合 IMMEDIATE。

### 3.2 PostgreSQL（默认 READ COMMITTED）

- **【设计建议】** SELECT 不锁行；步 3 重读 → 步 9 提交之间并发 UPDATE/INSERT 可提交。步 7 blind UPDATE 覆盖过期键；步 8 在 READ COMMITTED 下能看到并发已提交变化、提供部分兜底，但步 8 → 步 9 仍有窗口，且并发改 title（不改 version）可能绕过步 8 版本 DISTINCT 检查。
- **【设计建议】** 关闭手段：`SELECT … FOR UPDATE` 锁既有行（阻并发 UPDATE）+ 表级锁阻 INSERT（防 phantom 新键碰撞）；或 `SERIALIZABLE`（SSI）检测写偏斜并抛串行化失败（须重试）。

## 4. 并发控制方案（设计建议，须审批择一/组合）

### 方案 P1 — 悲观锁（双方言适配层分派，推荐）

**【设计建议】** 在 `apply_link_key_plan` 步 1 事务开始后、步 3 重读前，按方言加锁，封装在 backend 适配层（如 `app/db/locking.py` 或 services/links.py 内方言分派 helper），**Core 不变**：
- **PostgreSQL**：
  - 对全表链接行 `SELECT … FOR UPDATE`（锁既有行，阻并发 UPDATE/DELETE）；
  - **加表锁 `LOCK TABLE knowledge_link IN SHARE ROW EXCLUSIVE MODE`**（阻并发 INSERT/UPDATE/DELETE，防 phantom 新键碰撞与窗口②写入）。SHARE ROW EXCLUSIVE 与自身以外的写锁冲突，串行化重建写者。
  - 或简化：直接 `LOCK TABLE … IN EXCLUSIVE MODE`（更强，阻一切写）。**【潜在风险】** 锁强度越高并发吞吐越低，须权衡。
- **SQLite**：
  - 事务以 `BEGIN IMMEDIATE` 开始（预先持 RESERVED，串行化写者）；
  - 引擎设 `busy_timeout`（如 5000ms）让争用等待；
  - 可选 `journal_mode=WAL`（读写并发，写者仍单写）。**【设计建议】** WAL/IMMEDIATE/busy_timeout 经 `create_engine_from_url` 的 SQLite 分支设置（connect 事件或 `isolation_level`/`connect_args`），与既有 `PRAGMA foreign_keys=ON`（session.py:33）并列。
- **优点**：语义直观，窗口②在重读前即关闭；门禁 A/B/C/步 8 保留为纵深防御。
- **【潜在风险】** PG 表锁/行锁死锁（多重建并发或与其它写事务交叉）→ 须统一锁顺序 + 死锁重试；SQLite BUSY 超时 → 须重试/稳定错误码；全表锁期间阻塞所有链接写入（性能）。锁等待超时须映射稳定错误码（AGENTS.md §9），不回传 str(exc)。

### 方案 P2 — 乐观并发控制（方言中立，备选/组合）

**【设计建议】** 步 7 改为**带前置条件的 UPDATE + rowcount 校验**：`UPDATE … SET key/version/updated_at WHERE id=u.link_id AND normalized_link_key=u.old_key AND link_normalization_version=u.old_version`；rowcount==0 → 该行已被并发改 → 抛异常整体回滚（零写入）。
- **优点**：方言中立（SQLite/PG 同语义），无显式锁、无死锁；精确检测被改行。
- **缺点 / 缺口**：**phantom INSERT 无法靠行级乐观锁覆盖**（并发新增链接行引入新键碰撞，步 7 不触及新行）→ 仍须步 8 写后唯一性复核兜底，或配合表级版本/计数哨兵。**【潜在风险】** 步 8 → 步 9 窗口在 READ COMMITTED 下仍可能漏；纯乐观锁对「全表重建」这类集合操作覆盖不全。
- **【设计建议】** P2 宜与 P1 表锁/IMMEDIATE **组合**（乐观锁检既有行漂移 + 表锁/IMMEDIATE 阻 phantom），而非单独替代。

### 方案 P3 — SERIALIZABLE 隔离（PG 备选）

**【设计建议】** PG 重建事务设 `isolation_level="SERIALIZABLE"`（SSI），由数据库检测写偏斜/读写依赖环，冲突抛 `serialization_failure` → 应用层重试。SQLite 单写者本质已近似串行化（配合 IMMEDIATE）。
- **优点**：无需手工表锁，数据库保证可串行化。
- **【潜在风险】** SSI 假阳性重试开销；须重试循环 + 上限 + 稳定错误码；SQLite 无 SSI，双方言机制不同（K3 语义对齐须测试核实）。**【尚待验证】** SSI 在本重建读写模式下的实际冲突率与重试行为。

**【设计建议】** 推荐 **P1（PG FOR UPDATE + 表锁 / SQLite BEGIN IMMEDIATE + busy_timeout）为主，P2 乐观 rowcount 为纵深防御**；P3 作为 PG 侧可选演进。所有锁/隔离配置封装在 backend 适配层，按 `engine.dialect.name` 分派，Core 纯函数与端口签名零改动。

## 5. 与既有事务/门禁的兼容（设计建议）

- **【已验证事实】** `apply_link_key_plan` 要求传入 Session **无活动事务**（:311，`session.begin()` 在已有事务上抛 InvalidRequestError → 零写入）；拒绝报告 with 块内返回（零写入）；写后复核失败抛异常整体回滚。
- **【设计建议】** 加锁须在 `with session.begin():`（:328）**之内**、步 3 重读之前，保持「独占单事务 + 任一失败整体回滚」语义不变；不得在 Core 或路由层另开事务。
- **【设计建议】** 门禁 A/B/C/步 6/步 8 **全部保留**为纵深防御：锁关闭窗口②，门禁继续关窗口①与计划自洽/写后不变量。锁失败/超时 → 稳定错误码 + 零写入（不部分提交）。
- **【潜在风险】** SQLite `BEGIN IMMEDIATE` 与 SQLAlchemy 默认 BEGIN 时序：须确保 SQLAlchemy 不在 IMMEDIATE 前已发 DEFERRED BEGIN（经 `isolation_level` 引擎参数或 connect 事件控制），否则锁升级时机错位。须真实测试核实。

## 6. K3 双方言语义对齐（设计建议 / 尚待验证）

- **【已验证事实】** 链接业务操作（save/sync/demote/rebuild/gates）双方言镜像测试同名同断言通过（test_links.py 91 / test_links_pg.py 91，evidence/pytest-links-modules.txt）；FK DDL 方言无关 + SQLite pragma 强制；`_utc`（services/links.py:58）时间归一；规范化 Core Python 方言无关。
- **【潜在风险 / 尚待验证】** **并发语义当前不一致**：同一「并发重建」SQLite 单写者（BUSY）vs PG READ COMMITTED（静默过期写）。整改须以统一锁/隔离策略使双方言在并发下**行为对齐**（要么都串行化、要么都乐观回滚），并以真实双会话并发测试核实。
- **【设计建议】** 守护点：SQLite 外键依赖 per-connect pragma（session.py:33），新增引擎路径不得绕过 `create_engine_from_url`；建议整改批次加守护断言（FK 生效 + 锁配置存在）。

## 7. 未来测试计划（仅提案，本轮不新增测试文件）

**【设计建议】** 整改批次须补**真实并发测试**（双会话/双线程，SQLite 必测 + PG 真实实例镜像）：
1. **窗口②既有行漂移**：会话 1 生成 plan 并进入 apply（重读后、提交前暂停）；会话 2 改某链接行键/版本 → 会话 1 提交 → 断言：P1 锁阻塞会话 2 或 P2 rowcount==0 回滚；最终全表版本同构、无过期键、零部分写入。
2. **phantom INSERT 碰撞**：会话 1 apply 中；会话 2 INSERT 新链接行引入新键碰撞 → 断言表锁/IMMEDIATE 阻塞或步 8 唯一性复核回滚。
3. **治理列合法变化不误拒**：窗口内并发改 resolution/target_id（治理列）→ 断言门禁 C 不比对治理列（link_service.py:299）、重建按策略处理（锁串行化或步 8 治理基线复核）。
4. **SQLite BUSY / PG 死锁 / SSI 重试**：争用下断言稳定错误码 + 重试上限 + 零写入；不回传 str(exc)/堆栈。
5. **双方言语义对齐**：同一并发交错在 SQLite 与 PG 下断言一致终态（K3）。
6. **门禁回归**：T22–T40 不回归；窗口①拒绝/零写入语义不变。
7. **全量回归**：SQLite 887 / PG 1019 / A1-02 293 / ruff / 独立性守护。

**【尚待验证】** 上述并发测试**尚未编写/运行**；§3 锁行为为语义推断。不得把推断/提案写成已验证通过。

## 8. 实施边界与停止点

- **【设计建议】** 本方案须**另批审批**后实施（涉及 session.py 锁/隔离配置、services/links.py 方言分派加锁、可能的新适配层 helper、步 7 乐观前置条件）。**不改 Core 纯函数/端口签名、不改迁移、不改 A1-01/A1-02**。
- **本轮不实施**：不修改业务代码、不新增测试、不安装依赖、不改迁移、不提交、不推送、不进入 A1-04、不改 MILESTONES.md。
- **【潜在风险】** 锁策略不当会引入死锁/BUSY/SSI 重试风暴/吞吐下降；乐观锁单独使用漏 phantom；SQLite BEGIN 时序错位致锁失效。须按 §4/§5 约束实施并以 §7 真实并发测试核实，**不得以离线推断冒充真实并发验证**（AGENTS.md §5/§11）。

**停止点**：方案设计完成即停止，等待审批与进一步指令。

---

## 9. 实施状态与实测修正（K1+K2 整改批，2026-11-20 追加）

> 本节为整改批**实施后**追加，保留上文原始设计推断以供审计对照。验收详见
> [`docs/acceptance/V2-K1K2-remediation/V2-K1K2-remediation-report.md`](../../acceptance/V2-K1K2-remediation/V2-K1K2-remediation-report.md)。

### 9.1 已实施（已验证事实）

- **P1 方言写锁**：新增 `backend/app/db/locking.py::acquire_rebuild_write_lock`，于 `apply_link_key_plan` 步 1b（`session.begin()` 后、门禁 A 前）调用，持锁至提交。PG = `LOCK TABLE knowledge_link IN SHARE ROW EXCLUSIVE MODE` + `SELECT id … FOR UPDATE`；SQLite = 无额外语句（见 9.2 实测修正）。
- **P2 乐观前置（双方言）**：步 7 `UPDATE … WHERE id AND normalized_link_key=old_key AND link_normalization_version=old_version`，`rowcount!=1` → `LinkRebuildPostWriteError` → 整体回滚零写入。
- **SQLite busy_timeout**：`session.py` connect 事件 `PRAGMA busy_timeout=5000`（liveness）。
- **门禁 A/B/C 与步 8 写后复核全部保留**；Core 纯函数/端口签名/迁移**零改动**。

### 9.2 实测修正：SQLite 读阶段**不**持阻塞写者的锁（推翻 §3 推断）

- **【已验证事实】** 实测（`isolation_level=None`、`journal_mode=delete`）：重建事务自门禁 C 重读（SELECT）起至写之前，并发连接**可写并提交**（不被阻塞）；仅当进入写阶段（步 7 UPDATE 持 RESERVED）才阻并发提交。固化测试：`test_links_concurrency.py::test_sqlite_read_phase_not_lock_protected`（读阶段不阻）与 `::test_sqlite_write_phase_blocks_concurrent_commit`（写阶段阻）。
- **结论修正**：§3 「SQLite 自步 2/3 重读起持 SHARED 锁直至提交、写侧安全已由锁语义保证」的推断**不成立**。SQLite 窗口②「重读 → 写」**不由锁保护**，而由 **P2 乐观前置**兜底（并发漂移 → rowcount=0 → 回滚零写入，`test_p2_key_drift_after_reread_rolls_back` / `test_p2_version_drift_after_reread_rolls_back` 实证）。写阶段 RESERVED 锁 + busy_timeout 为补充。
- **【已验证事实】** PG 表锁排除经真实双连接 `lock_timeout` 实证：`test_links_concurrency_pg.py::test_pg_rebuild_lock_blocks_concurrent_update` / `::…_insert_phantom` / `::…_serializes_second_rebuild` 均通过——PG 窗口②（含 phantom 与步 8 → 步 9 间隙）由表锁关闭。
- **BEGIN IMMEDIATE 仍延期**：需全局事务控制管线改动（`isolation_level=None` + begin 事件），本轮不做；不宣称已消除 BUSY。SQLite 窗口②安全由 P2 保证，已实证。

### 9.3 测试与回归（已验证事实）

- 新增并发测试：SQLite 7（`test_links_concurrency.py`）+ PG 7（`test_links_concurrency_pg.py`）。
- 既有 PG T39 顺序守护更新：`_QueryCounter` 新增 `lock` 分类，断言取锁（LOCK TABLE + FOR UPDATE）**先于门禁 A**（更强守护，非弱化）；SQLite T39 因 acquire 无操作不变。
- 全量：SQLite 906 passed / 150 skipped；真实 PG 1056 passed / 0 skipped；ruff 全过；独立性守护 14 过；A1-02 frozen 291 过；前端 72 过 / typecheck / build 不变。