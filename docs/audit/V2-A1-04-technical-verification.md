# ExplainLab V2 · A1-04 第一轮只读技术核验报告

> 性质：**设计冻结前独立技术核验**（ChatGPT 架构设计 / Qoder 真实仓库取证）。本轮**只读**：未改任何业务代码/测试/迁移/依赖/lockfile/pyproject/package.json/MILESTONES，未 reset/checkout/stash/rebase，未 commit/push，未启动 A1-04 开发，未修改原四份设计文档。仅新建本报告。
> 证据分级：【已验证事实】=源码/DB结构/真实运行证据；【合理推断】=据源码推导未实测；【设计建议】=建议方案；【待验证】=须实验/测试确定；【阻断问题】=当前约束下无法安全实现。
> 最终事实来源 = **真实仓库**，不因设计文档写了某能力就默认已实现。

---

## 1. Git 基线及边界核验

### 1.1 基线（本轮开始时真实记录）【已验证事实】

| 项 | 值 |
|---|---|
| HEAD（full） | `784b1248065424e07273b272d6016cc121bc606c` |
| HEAD（short） | `784b124` |
| 分支 | `fix/m0-admission-and-m5-regressions` |
| tracked diff | **空**（`git diff --stat` 无输出） |
| staged diff | **空**（`git diff --cached --stat` 无输出） |
| 未跟踪文件 | `docs/audit/V2-A1-03-final-stage-audit/`（30 文件，上轮审计交付，未提交）+ 四份 A1-04 设计文档 |

未提交文件指纹（`git hash-object`，节选关键项）：

```
de684eceb88e7d0c585c5d8410dd2af1265f6607  docs/plans/V2-A1-04-implementation-plan.md
5176a2ae644991e7ef03019ef8f7bac47cd2a841  docs/plans/V2-A1-04-acceptance-matrix.md
f143bb69e15e840ccf73584bb6aa97c292218c8e  docs/plans/V2-A1-04-risk-register.md
d1ba42d6ab4128863e767f2e230fb9e9c43b7750  docs/plans/V2-A1-04-open-decisions.md
a1c1528b7e28904a39d7d0386679b6bb726b6392  docs/audit/V2-A1-03-final-stage-audit/A1-03-final-stage-audit.md
```

### 1.2 边界遵守自检【已验证事实】

- 本轮仅执行：Read/Glob/Grep（只读）、`git rev-parse/branch/status/diff/hash-object/ls-files`（只读）、`uv run python -c`（只读探针）、`psql -tAc SELECT`（只读查询）、`pg_dump --version`/`pg_ctl status`（只读）、`uv run pytest tests/test_v2_models.py`（运行**现有**测试，tmp 隔离夹具，未改测试/生产数据）。
- **未** CREATE/DROP/ALTER 任何数据库（PG staging 创建属写操作，本轮刻意不做，留待开发期真实验证）。
- 工作树 tracked 部分零改动；新增文件仅本报告。

### 1.3 真实运行环境【已验证事实】

| 项 | 实测值 | 命令 |
|---|---|---|
| Python | 3.11.9 | `uv run python -c "import sys..."` |
| SQLite | **3.45.1**（≥3.35，支持 DROP COLUMN + Online Backup API） | `sqlite3.sqlite_version` |
| `sqlite3.Connection.backup` | **present**（Online Backup API 可用） | `hasattr` 探针 |
| `msvcrt.locking` | **present**（Windows stdlib 文件锁可用） | `hasattr` 探针 |
| PostgreSQL | **16.8**（Visual C++ build 1942, 64-bit，Windows 原生） | `psql SELECT version()` |
| PG 服务 | running，PID 50260，data `D:/ExplainLab-pg/data` | `pg_ctl status` |
| PG 工具 | pg_dump/pg_dumpall/pg_restore/pg_basebackup/pg_ctl/psql 均在 `D:/ExplainLab-pg/pgsql/bin/` | `ls` |
| pg_dump 版本 | 16.8（与服务端同版本） | `pg_dump --version` |
| 现有数据库 | `explainlab_test`、`postgres`（无 staging） | `psql SELECT datname FROM pg_database` |
| `EXPLAINLAB_PG_TEST_URL` | 本 shell **unset**（PG 测试默认 skip；开发期须显式设置） | `echo` |
| 现有测试运行 | `test_v2_models.py -k "ImportOrigin or GcTaskAndLock or Attachment"` → **12 passed, 21 deselected**（3.70s） | `uv run pytest` |

---

## 2. 当前项目真实架构概况

【已验证事实】依赖方向 `frontend → backend → knowledge-core`（AGENTS.md §3）。

- **数据层**：迁移单 head `0006_v2_markdown_kb`（`down_revision=0005_m5_experiments`）。A1 全部 8 表 + knowledge_item 4 新列**已建**（0006:52-198）。ORM 全部存在（models.py:274-451）。
- **Core**：纯 stdlib+Pydantic+httpx；实体（entities.py）+ 端口（ports.py）全部 A1 契约已声明；Markdown codec/三 Hash/canonicalization v1（A1-02）+ 链接服务（A1-03）已实现。
- **backend 已实现**：V1 KnowledgeRepository（knowledge.py）、治理三仓库 + build_review_service（governance.py）、LinkRepository + apply_link_key_plan + build_link_sync + build_link_restorer（links.py）、K1 路由挂接（routes/governance.py）、3 个只读链接 GET（routes/links.py）、engine/session 全局单例（db/session.py）、locking.py（PG 表锁 / SQLite no-op）。
- **backend 缺失（A1-04 须建）**：Attachment/Tag/TagChangeLog/GcTask/ImportOrigin 仓库实现、db/storage_lock.py、services/{attachments,markdown,backup}.py、app/ops/（**目录不存在**，Glob 证实）、import/export/attachments/tags 路由、链接写端点、存储/GC/备份配置、相关 DTO。
- **运行入口**：`uv run uvicorn app.main:app --reload --port 8000`（scripts/dev.ps1:8）。`--reload` = reloader 父进程 + worker 子进程（**两进程**）。lifespan（main.py:34-45）仅 init_db + ensure_default_space，**无任何进程锁/维护模式**。
- **进程锁/备份机制**：grep `msvcrt|fcntl|LockFile|pg_dump|VACUUM INTO|advisory|single.?instance|pidfile|portalocker|CreateMutex` 于 backend → **仅 models.py/0006 的 "advisory" 注释命中**，无任何实现。P0-3/P0-4 完全 greenfield。

---

## 3. 四项 P0 技术门禁逐项结果

### P0-1：ReviewRequest 能否承载导入上下文 —— **结论：部分可行，存在须修订设计的重大缺口（CONDITIONAL，含 1 项阻断性子问题）**

#### 证据链（提交→批准全链）

| 环节 | 文件:行 | 事实 |
|---|---|---|
| ORM 字段 | models.py:187-202 | `ReviewRequestORM`：id/item_id(FK CASCADE)/action(String30)/**payload(Text, default "{}")**/reason/status/created_at/resolved_at/resolution_note。**无 unique 约束**（0003:47-60 仅 PK+FK） |
| payload 序列化 | services/governance.py:180 | `save_review`：`payload=json.dumps(review.payload, ensure_ascii=False)` —— **自由 JSON，可存任意键** |
| payload 反序列化 | services/governance.py:65 | `_to_review`：`payload=json.loads(row.payload)` —— **完整还原 dict** |
| update_review | services/governance.py:201-209 | 只改 status/resolved_at/resolution_note，**不动 payload**（批准时 payload 保留） |
| API 入参 | api/schemas.py:238-242 | `ReviewSubmit.payload: dict`（无键限制）；`ReviewOut.payload: dict`（230） |
| submit | review/__init__.py:65-83 | 重要变更→`ReviewRequest(payload=payload)`→save_review 返回 pending；**无去重**（每次新建） |
| approve | review/__init__.py:85-96 | 先 update_review 再 `_apply_action`（同事务，注释 92-93：删除 CASCADE 审核单自身） |
| **_apply_update** | review/__init__.py:129-143 | **只应用 title/content/status/space_id 四字段**（134-141）；**不应用 tags/extra_metadata/source_*/附件/链接** |
| 批准路由 | routes/governance.py:352-375 | `_pending_review`→`_demote_backlinks_before_delete`(363)→`service.approve`(365)→`_sync_links_after_content_change`(369)→commit(370)→`_sync_applied_action`(371)→commit(374) |
| K1 链接同步 | routes/governance.py:337-349 | `_sync_links_after_content_change`→`sync_links_or_conflict(session, item)` |
| sync 实现 | routes/links.py:43 | `build_link_sync(session).sync(item, item.content)` —— **BindingFirstLinkSync 解析正文 wikilink** |
| restorer 未接线 | services/links.py:537-541 | `build_link_restorer`（LinkImportRestorer，target_id 优先）**已定义但无任何路由调用**（grep 证实仅 links.py 自身引用） |
| 事务边界 | db/session.py:76-85 | get_session 每请求一会话，finally close（不自动 commit）；路由显式 commit；异常前未 commit→close 回滚 |

#### 六问回答

1. **能否将来源身份/源Hash/tags/extra_metadata/附件引用/链接恢复信息完整关联到审核单？**
   【已验证事实】**能"存储"但不能"结构化承载+应用"**。payload 是自由 Text JSON（governance.py:180），import 可把任意上下文塞进 payload。但：(a) 无 payload 契约/schema 约束这些键；(b) `review_payload_hash`（A1-02，markdown/__init__.py:384）**只覆盖 title/content/status/space_id**，tags/extra_metadata/附件/源身份**不在审核 hash 保护范围**；(c) Core `_apply_update` 只应用 4 字段。**故"关联"仅在 payload 字节层面成立，语义承载不成立。**

2. **批准时能否可靠恢复这些上下文？**
   【已验证事实】**不能（经现有链路）**。approve→`_apply_update` 只改 title/content/status/space_id（review/__init__.py:134-141）；批准路由的 backend 钩子只做**通用正文链接同步**（sync_links_or_conflict，非 LinkImportRestorer）+ 索引。**无任何钩子应用 tags/extra_metadata/附件引用/ImportOrigin**。即使 payload 存了这些键，批准时**静默丢弃**。链接恢复也**不走 target_id 优先绑定**（restorer 未接线），只正文重解析。→ active 导入的保真/绑定优先在批准路径**丢失**。

3. **拒绝是否错误更新已应用的 ImportOrigin？**
   【已验证事实】reject（review/__init__.py:98-105）只改审核单 status，**不触 item/ImportOrigin**。但 **ImportOrigin 无 status 字段**（entities.py:285-301，models.py:410-435 无状态列）→ 无法表示"待应用"。若 import 在 submit 时写 ImportOrigin，reject 后 ImportOrigin **遗留为"已导入"假记录**（内容未应用）；若推迟到 approve 写，则 pending 期间无幂等记录→重导产生多张 pending。**两难，设计未解决**（见 §7 冲突 F-03）。

4. **是否重复提交 pending？**
   【已验证事实】**是**。submit 无去重（review/__init__.py:77-81 每次新建）；review_request **无 unique 约束**（0003:47-60）。design §2.7:501「hash 相同→复用 pending」属 **A1-05**（review_payload_hash+proposal_version，未实现）。A1-04 重导同一 active 文件→多张 pending。

5. **批准异常能否保证知识/链接/来源身份一致性？**
   【合理推断】**第一事务内一致**（approve+demote+sync 在 commit(370) 前，异常→get_session close 回滚，审核单仍 pending）。**但**：(a) 两次 commit（370/374）拆分→索引同步在第二事务，若失败则 item/链接已提交而索引滞后（V1 既有行为，可 reindex 恢复）；(b) **真正的一致性缺陷是 tags/extra_metadata/附件/ImportOrigin 根本不被应用**（问 2），不是事务回滚问题。

6. **能否不增迁移、不改 A1-01 冻结端口实现？**
   【设计建议】**可行，但须新增 backend"导入批准钩子"+ payload 契约 + ImportOrigin 时机重设计**，而非依赖 Core：
   - payload 自由 JSON 已能存上下文（**无需迁移**）。
   - 批准路由在 `service.approve` 后、commit 前，新增 backend 钩子应用 tags（TagRepository）/extra_metadata（直接 ORM，列已存在）/附件（AttachmentRepository）/ImportOrigin（ImportOriginRepository）/绑定优先链接（**build_link_restorer 已存在**，用 payload 中的 frontmatter hints）。这些端口/装配 A1-01/A1-03 已备，**不改 Core ReviewService、不改冻结端口、无需迁移**。
   - ImportOrigin 待应用态：**active 导入推迟到 approve 写 ImportOrigin**；pending 期幂等改查 review_request.payload 中源 hash（应用层）。**无需新增 status 列**（避开迁移）。
   - 【阻断问题·子项】**若要求 DB 级 pending 去重或 ImportOrigin 状态列**→须迁移（红线 #2 禁止）或改 Core（红线 #5/#6 禁止）。故"DB 强制的审核幂等/状态"在当前约束下**不可实现**，只能应用层方案。

> **P0-1 门禁判定**：原设计 plan §5.1 假设"active→submit→approve 应用全部上下文"**与真实代码不符**（Core 只应用 4 字段、restorer 未接线、ImportOrigin 无状态）。**须修订设计**为"backend 导入批准钩子 + ImportOrigin-at-approve + 应用层 pending 去重"。修订后**可在无迁移/不改冻结端口下实现**；但"DB 强制审核幂等/状态"不可实现。**非 PASS。**

---

### P0-2：ImportOrigin 幂等保障 —— **结论：DB 无唯一约束，幂等纯应用层，并发安全须单实例+应用串行（CONDITIONAL，含阻断性子项）**

#### 证据链

| 项 | 文件:行 | 事实 |
|---|---|---|
| ORM 约束 | models.py:417-421 | `ImportOriginORM.__table_args__` = **仅两个非唯一 Index**（ix_import_origin_item_id、ix_import_origin_source_payload_hash）。**无 UniqueConstraint** |
| 迁移约束 | 0006:170-187 | import_origin：`PrimaryKeyConstraint("id")` + FK(item_id CASCADE) + 两个 `op.create_index`（**非 unique**）。**无任何 UniqueConstraint** |
| 字段可空性 | models.py:429-430 | `source_instance_id` **nullable**；`source_document_id` String(36) NOT NULL |
| 端口契约 | ports.py:410-434 | `save_origin`「**追加**一条」；`find_by_source_payload_hash`→**list[ImportOrigin]**；`find_by_source_document`→**list**。契约本身**不保证唯一**，允许多条 |
| 实体 | entities.py:285-301 | ImportOrigin **无 status 字段**；source_document_id UUID 必填 |
| 现有测试 | test_v2_models.py:629-684 | `test_defaults_and_indexes` 断言两个**非唯一**索引；`test_source_hash_lookup_for_idempotency` 用 **SELECT 查历史**（幂等基础=查询，非约束）；**无重复插入拒绝测试**（因无约束可拒） |
| 列可写 | test_v2_models.py:686-696 | `test_item_source_identity_columns` 直接 ORM 写 item.source_*/extra_metadata 成功→**列存在可写，无需迁移** |
| 真实运行 | 本轮 pytest | TestImportOriginConstraints **4 passed**（含上述） |

#### 七问回答

1. **当前 DB 是否存在真正唯一约束？**
   【已验证事实】**否**。import_origin 仅 PK(id) + 两个非唯一索引（models.py:418-421 / 0006:182-187）。**无 (source_instance_id, source_document_id) 唯一、无 source_payload_hash 唯一、无 (item_id, hash, version) 唯一**。

2. **相同来源/身份/Hash 重复导入会发生什么？**
   【合理推断】DB **不拒绝**重复 ImportOrigin 行（无约束）。幂等完全靠应用层 `find_by_source_payload_hash`→非空则 skipped（ports.py:418 返回 list）。**check-then-insert 非原子**：两请求同时查均空→均插入→**两条 origin + 可能两个 item**。

3. **同进程两异步请求同时导入相同文件？**
   【合理推断】FastAPI async 路由 + SQLAlchemy 同步 Session（每请求一会话，session.py:76）。两协程交错执行 find→insert，**无 DB 约束兜底**→竞态重复。`knowledge_item` PK(id) 仅防**同 id 重复 create**（一方 IntegrityError），但**不防同文件分配不同新 id**、不防同 id 并发 update、不防重复 origin 行。

4. **DB 事务失败后来源记录是否可能提前写入？**
   【合理推断】若 import 把"写物理附件/写 ImportOrigin"放在**同一 DB 事务**内，事务回滚则 origin 一并回滚（不会提前持久化）。但若**先独立 commit origin 再后续步骤失败**→origin 遗留。设计须保证 origin 与 item 写入**同事务**（每文档独立事务，plan §6）。**当前无 import 服务实现，属设计约束**。

5. **Active 审核未批准时 ImportOrigin 如何表示待应用？**
   【已验证事实】**无法表示**（无 status 列，entities.py:285-301）。见 P0-1 问 3 两难。【设计建议】active 推迟到 approve 写 origin；pending 幂等查 review payload。**DB 级待应用态须迁移（禁止）**。

6. **SQLite 与 PG 是否相同最终行为？**
   【已验证事实】**相同**：两方言 import_origin 均无唯一约束（0006 标准 DDL，双方言一致）。故"无 DB 幂等兜底"是**双方言共性**，非方言差异。差异仅在并发串行化手段（PG 可 advisory/行锁，SQLite 无行锁）。

7. **如何避免仅靠 Python 内存锁实现幂等？**
   【设计建议】分层：
   - **DB 唯一约束**（最可靠）→ **须迁移，红线 #2 禁止本轮**。
   - **事务保证**：origin+item 同事务，回滚一致（可行，无需迁移）。
   - **应用层串行化**：PG 对 source_hash 取 advisory lock 后 check-insert；SQLite 无行锁→须**库级短事务串行**或**单写者**。
   - **单实例部署约束**：OS 进程锁（P0-3）保证仅一 backend 写→进程内 per-item/per-hash asyncio.Lock 串行 check-insert 即足够。
   【阻断问题·子项】**多实例并发导入的 DB 强制幂等**在无迁移下**不可实现**；只能"单实例 + 应用串行 + 事务"。design §2.6.2:460「按 item 串行（**行锁/唯一约束**」**与真实不符**（import_origin 无唯一约束、SQLite 无行锁）。

> **P0-2 门禁判定**：design 宣称的"唯一约束"幂等**不存在**（重大事实错误，须直接指出）。无迁移下幂等只能"单实例进程锁 + 应用层 per-hash 串行 + 同事务"。**多实例 DB 强制幂等被红线 #2 阻断**。**非 PASS**；须 ChatGPT 决定：接受单实例约束 vs 批准迁移加唯一约束。

---

### P0-3：Windows 单实例进程锁 —— **结论：当前无任何进程锁，stdlib 可实施（CONDITIONAL，可行无新依赖）**

#### 证据链

| 项 | 文件:行 | 事实 |
|---|---|---|
| 运行入口 | scripts/dev.ps1:8 | `uvicorn app.main:app --reload --port 8000`（**reloader+worker 两进程**） |
| lifespan | main.py:34-45 | init_db + ensure_default_space，**无进程锁/维护模式** |
| 数据目录 | config.py:17-19 | BACKEND_DIR/data/explainlab.db（绝对路径锚定）；附件根拟 backend/data/attachments |
| 锁机制存在性 | grep backend | **无 msvcrt/fcntl/LockFile/pidfile/portalocker/CreateMutex 实现** |
| stdlib 能力 | 本轮探针 | **msvcrt.locking present**（Windows）；fcntl 为 POSIX stdlib |
| 依赖 | backend/pyproject.toml:6-15 | 无 portalocker/filelock（**零新依赖约束**） |

#### 八问回答

1. **两 Backend 能否同时操作同一数据目录？** 【已验证事实】**能**。无锁；两进程各自 init_db 同一 SQLite 文件→busy_timeout=5000 仅缓解写争用，**不阻止双写**；附件物理目录更可双写竞争。
2. **Backend 与维护 CLI 能否同时写？** 【已验证事实】**能**。CLI（拟 app/ops/，未建）与 backend 无共享锁→v2_downgrade/GC/重建可与在线写并发→危险。
3. **是否存在可靠 OS 级进程锁？** 【已验证事实】**否**（无任何实现）。
4. **异常退出后锁是否自动释放？** 【设计建议】用 **msvcrt.locking 锁文件句柄**（Windows）/ **fcntl.flock**（POSIX）：进程死亡→OS 关闭句柄→**锁自动释放**（无需清理 stale lock）。**优于 lockfile+PID**（PID 复用误判风险）。
5. **Windows 文件句柄是否正确关闭？** 【待验证】现无锁文件；实现须保证句柄在进程生命周期持有、退出关闭。msvcrt 锁随句柄关闭释放。
6. **PID 复用是否误判？** 【设计建议】**避免 PID 方案**。msvcrt/fcntl 锁由 OS 持有句柄，**不依赖 PID**→无复用误判。若用 lockfile+PID 须配合进程存活校验（仍有竞态），不推荐。
7. **是否需单独 lock 文件？** 【设计建议】**是**。`backend/data/.explainlab.lock`（gitignore），msvcrt.locking(fd, LK_NBLCK, 1) 非阻塞独占；获锁失败→已有实例→退出/报错。
8. **如何无新依赖实现？** 【设计建议】stdlib `msvcrt`（win）/`fcntl`（posix）分支 + `os.open(O_CREAT|O_RDWR)`。跨平台封装 `app/db/process_lock.py`（或 app/core/）。**零新依赖**。

【设计建议·真实可实施方案】
- 启动时（lifespan 或 CLI 入口）获取 `data/.explainlab.lock` 的 OS 级独占锁（msvcrt.locking / fcntl.flock，非阻塞）。失败→明确报"已有实例运行"并退出（**非** threading/asyncio.Lock）。
- **--reload 处理**：锁应由**实际 worker** 持有；reloader 父进程不持锁（或仅在 worker 启动钩子获取）。须验证 uvicorn --reload 下锁归属（【待验证】）。生产建议 `--workers 1` 且无 --reload，或多 worker 共享锁设计（A1-04 单实例假设）。
- **维护模式**：CLI（v2_downgrade/GC/重建）获取**同一把锁**→与 backend 互斥；或 backend 持锁期间 CLI 拒绝执行。备份恢复（P0-4）quiesce 依赖此锁。
- **诚实限制**：OS 进程锁保证**单实例**，但**不保证多实例**；多实例须 DB 级协调（PG advisory / 单写者部署）。**不得把进程内 threading.Lock/asyncio.Lock 描述成 OS 级单实例锁**。

> **P0-3 门禁判定**：可行、零新依赖、stdlib 已验证可用。但**当前完全缺失**，须新增设计+代码；--reload 锁归属与维护模式互斥须【待验证】。**非 PASS（无现成实现），属可解决 CONDITIONAL。**

---

### P0-4：PostgreSQL 离线备份恢复 —— **结论：工具齐备、引擎可重建，但编排/quiesce/Manifest 全缺（CONDITIONAL，可行须新代码）**

#### 证据链

| 项 | 文件:行/实测 | 事实 |
|---|---|---|
| Engine 单例 | db/session.py:47-57 | 全局 `_engine`/`_session_factory`；init_db 创建 |
| 池释放 | db/session.py:60-66 | `dispose_db()`：engine.dispose() + 重置全局→**支持池重建** |
| 池重初始化 | db/session.py:51-57 | init_db(settings) 可用新 URL 重建（**非自动切换**，须显式 dispose+init） |
| PG 引擎 | db/session.py:44 | `create_engine(url, pool_pre_ping=True)`（默认 QueuePool） |
| 每请求会话 | db/session.py:76-85 | get_session yield/close；**无 quiesce/维护模式** |
| PG 工具 | 本轮实测 | pg_dump/pg_restore/pg_basebackup **16.8**，服务端 16.8 running |
| 现有库 | 本轮实测 | explainlab_test、postgres（**可 CREATE staging**） |
| 备份实现 | grep backend | **无 pg_dump/VACUUM INTO/backup 代码**（greenfield） |
| 迁移结构 | 0006 | 单 head，双方言 up/down；downgrade 删 V2 表/列（**丢 V2 数据**） |
| design 协议 | V2-batch-A-design.md:634/663/672/839 | pg_dump --format=custom；Staging createdb；**连接池重建非 URL 自动切换**；**「不得假设单实例」多实例编排** |

#### 九问回答

1. **pg_dump 是否适合当前部署？** 【已验证事实+合理推断】**适合**。pg_dump 16.8 与服务端同版本；逻辑备份 `--format=custom` + pg_restore；单事务 MVCC 一致快照（design:634）。Windows 原生 PG 已运行。
2. **备份与附件能否同一一致性时间点？** 【合理推断】**pg_dump 仅 DB 快照，不含附件文件**。须：quiesce 写入（维护模式+进程锁）→同一时刻 pg_dump + 附件目录一致拷贝（或附件版本指针快照）。**无 quiesce 则 DB 与附件可能错配**。当前无 quiesce 机制→**须新实现**。
3. **恢复前如何确保所有连接真正关闭？** 【合理推断】`dispose_db()` 释放池，但**在途请求会话仍引用旧 engine**（get_session）。须**维护模式停止接受新请求 + 等待在途完成 + dispose**。**当前无维护模式**→须新实现。PG 侧可 `SELECT pg_terminate_backend` 强制断连（【待验证】权限）。
4. **如何避免 Staging 与正式同名冲突？** 【设计建议】`createdb explainlab_staging_<ts>`（design:663，时间戳唯一名）或 pg_restore --create 到独立名；**不触碰生产库**。现有库仅 explainlab_test/postgres，staging 名不冲突。
5. **切换失败如何恢复旧库？** 【设计建议】保留旧 generation（旧 DB + 旧附件指针）；切换失败→池切回旧库（dispose+init 旧 URL）+ Manifest phase 回滚（design:691/840）。**旧资源保留至确认**（design:555）。
6. **恢复期间其他进程能否重连？** 【合理推断】**能**（无维护模式/进程锁）→须 P0-3 进程锁 + 维护模式隔离写入。design:672「不得假设单实例」→多实例须编排器协调所有实例池重建（**A1-04 多实例编排器【待审批】延后**）。
7. **数据库重命名时残留连接如何处理？** 【合理推断·PG  documented】`ALTER DATABASE ... RENAME TO` **要求目标库无活动连接**（否则报 "database is being accessed by other users"）；`DROP DATABASE` 同样（PG13+ 可 `WITH (FORCE)`）。故**重命名切换方案须先断尽连接**；**更稳妥=池重建指向 staging（不重命名）**，避开 rename 连接限制。【待验证】真实 PG 行为。
8. **Manifest/restore-journal 如何保证崩溃后可恢复？** 【设计建议】Manifest 两阶段（prepared→switching_db→switching_attachments→committed）+ operation_id/generation_id/resource_version；fsync 顺序资源→phase→marker；崩溃后**三方对账（manifest vs DB 实际 vs 附件实际），不盲信标记**（design:691/697）。**Manifest 落文件**（backend/data/ops/，**无新迁移**，避红线 #2）。当前无实现。
9. **Windows 下如何执行整个恢复流程？** 【合理推断】Windows 原生 PG 16.8 已运行；pg_dump/pg_restore 为 Windows exe；附件指针切换用**指针文件 + os.replace**（symlink 需特权→降级）；占用文件退避重试（design §10.1）。**须真实 Windows 故障注入验证**【待验证】。

【区分】
- **PG 原生能力**：pg_dump/pg_restore/pg_basebackup、CREATE/DROP DATABASE、advisory lock、pg_terminate_backend、MVCC 快照。
- **项目现有能力**：engine dispose/init（池重建基础）、psycopg 驱动、Alembic 双方言迁移。
- **须新实现**：维护模式/quiesce、进程锁（P0-3）、备份服务（pg_dump 编排+附件一致拷贝）、Staging 恢复+校验+切换、Manifest 两阶段+对账、Windows 指针/退避、故障注入。

> **P0-4 门禁判定**：工具与引擎基础**齐备**（已验证），但**编排/quiesce/Manifest/维护模式全缺**，须新代码+设计。单实例可行；**多实例编排器 design 明言不得假设单实例，A1-04 延后**→A1-04 须明确单实例假设或交付编排框架。**非 PASS，属可解决 CONDITIONAL。**

---

## 4. 六项系统集成问题核验

### 5.1 MarkdownItemRepository 与 V1 兼容性 —— **存在字段覆盖数据丢失风险（须决策）**

【已验证事实】
- knowledge_item 列**齐备**：extra_metadata（models.py:112，Text NOT NULL default/server_default "{}"）、source_payload_hash/source_content_hash/source_instance_id（114-116，String64 nullable）。`test_item_source_identity_columns`（test_v2_models.py:686-696）**直接 ORM 写入成功**→专用 Repository 可建在这些列上，**无需迁移**。
- **V1 仓库不映射这些字段**：`_to_entity`（knowledge.py:28-48）不读 extra_metadata/tags/source_*；`save`（57-80）不写（extra_metadata 取 server_default "{}"，source_* NULL）；`update`（102-112）**只写 title/content/status/space_id/updated_at**。
- tags 在 item_tag 独立表（models.py:285），V1 仓库**完全不触**；KnowledgeItem.tags 从 DB 加载恒空。

【合理推断·关键风险】**若选"扩展 V1 仓库映射 extra_metadata"（open-decisions D-02 选项 B）**：V1 PATCH 经 KnowledgeUpdate（schemas.py:103-109，**无 extra_metadata**）→`_apply_update` 构造的 item.extra_metadata 为默认 `{}`（_to_entity 不读 DB 值）→扩展后的 `update()` 写 extra_metadata=`{}`→**V1 编辑会清空导入的 extra_metadata（数据丢失）**。
【已验证事实·当前安全】**现状 V1 update 不写 extra_metadata 列**（只写 4 字段）→V1 编辑**不会覆盖** extra_metadata/source_*（列保留）。V1 与 V2 写**不相交列**（V1:title/content/status/space_id；V2:extra_metadata/source_*/tags），无直接列覆盖。
【设计建议】**优先 D-02 选项 A/C（独立持久化路径，不改 V1 仓库）**：A1-04 导入/导出经专用 Repository 直接 ORM 写 extra_metadata/source_*/tags，V1 仓库不动→零 V1 回归、零覆盖风险。若坚持单一路径（B），**必须同时让 _to_entity 读 extra_metadata 且 _apply_update 保留未提供字段**，否则 V1 编辑丢数据——但这触碰 M1/M2 代码须全量回归。
【合理推断·幂等 subtlety】V1 编辑 content 后**不更新 source_content_hash/source_payload_hash**（V1 不知这些列）→重导同一源文件仍 skipped（source hash 记录"最近导入源"非"当前内容"）。符合 design §2.6.3 语义，但须 ImportReport 如实提示。

### 5.2 附件存储 —— **Schema 足以支撑，锁顺序须设计**

【已验证事实】
- AttachmentORM（models.py:336-351）：id PK/item_id FK CASCADE/filename/mime/size/storage_key(String64)/content_hash(String64)/created_at；**仅非唯一索引 ix_attachment_storage_key**（340），**无 (item_id, storage_key) 唯一**→同条目可重复引用行（COUNT 会含重复）。
- GcTaskORM（379-407）：lease_owner/lease_expires_at/lease_token/attempts/next_retry_at/quarantine_path/quarantined_at 齐备；**无 storage_key 唯一**（387-390 两非唯一索引）→**同 key 可多 gc_task 行**（enqueue 须应用层去重）。
- StorageLockORM（438-451）：**storage_key PK**→租约锁行互斥（`test_storage_lock_pk_unique` PASSED，IntegrityError 证实）。
- 引用数派生：`test_storage_key_shared_and_reference_count_derived` **PASSED**→COUNT(attachment WHERE storage_key) 共享语义在现有 Schema 成立。
- 端口齐备：AttachmentRepository.count_references/list_storage_keys/find_by_hash（ports.py:288-298）、StorageKeyLock acquire/renew/verify/release（448-464）。

【合理推断】内容寻址（storage_key=sha256）/引用派生/quarantine（quarantine_path 列）/孤儿扫描（list_storage_keys 对照物理）**均可直接建于现有 Schema，无需迁移**。
【设计建议·锁顺序】上传与 GC 同 key 竞争：**统一先获 StorageKeyLock(storage_key) 再做 DB 引用变更/物理操作**；上传持锁内"物理 temp→rename→插引用行"；GC 持锁内"复核 COUNT→quarantine"。**锁顺序一致（storage_key 锁→DB 短事务）避免死锁**；物理 IO 在 DB 写事务**外**（design §2.5.1）。gc_task 同 key 多行须 enqueue 去重（应用层查 list_tasks(storage_key) 非终态则不重复 enqueue）。

### 5.3 GC 状态机 —— **七态齐备，流转合法性须实现层强制**

【已验证事实】GcStatus（entities.py:238-247）七态：pending/running/done/cancelled/failed_retryable/failed_permanent/needs_manual。GcTask（250-268）lease_token ge=0/attempts ge=0/quarantine 字段。`test_gc_cancelled_terminal_state_persisted`/`test_gc_quarantine_fields` PASSED。
【已验证事实】**Pydantic 只校验类型，不校验状态流转**；DB status String(24) **无 CHECK 约束**（0006:154）→非法流转 DB 不拒。
【设计建议】合法流转须**实现层强制**（GcTaskRepository.update_task fencing + 状态机校验）：
- pending→running（claim 原子条件更新）；running→done/cancelled/failed_retryable/failed_permanent/needs_manual；
- failed_retryable→pending（next_retry_at 到期）；failed_permanent→needs_manual；needs_manual→pending/cancelled（人工）；
- **终态 done/cancelled 不可被普通 update 覆盖**（ports.py:360-361 契约）；
- 崩溃残留 running→**租约过期被他人条件认领**（新 token），**重启不直接置 pending**（ports.py:361）。
【待验证】claim 双 Worker 仅一、过期接管、旧 token fencing 中止须真实并发测试（backend 实现未建）。

### 5.4 K1 治理挂接 —— **导入须复用，不得另实现链接同步**

【已验证事实】K1 钩子在 **backend 路由层**（routes/governance.py），**非 Core ReviewService**：
- **Draft 直改**：submit_review（245）非重要→`_demote_backlinks_before_delete`(275，DELETE 前)→submit 应用→`_sync_links_after_content_change`(284，UPDATE/RESTORE 后 commit 前)→commit→`_sync_applied_action`(289 索引)。
- **Active 审核**：submit 返回 pending（201/202，不应用）；approve（352）→demote(363)→service.approve(365)→sync(369)→commit(370)→索引(371)→commit(374)。
- **DELETE 降级**：`_demote_backlinks_before_delete`(324-334)→demote_backlinks_on_delete（治理列-only，免版本守卫，delete flush 前）。
- **UPDATE/RESTORE 同步**：`_sync_links_after_content_change`(337-349)→sync_links_or_conflict（409 整事务零写入）。
- **MERGE 归档**：_apply_merge（review/__init__.py:145-168）source→ARCHIVED + DUPLICATE_OF 关系 + source_refs 复制；**MERGE 不降级入链**（governance.py:331 注释：归档非删除）。
【设计建议】A1-04 导入服务**必须复用同一套钩子函数**（demote/sync/apply_link_key_plan），**不得自行实现另一套链接同步**（用户任务 5.4 明令）。【阻断问题·关联 P0-1】但**批准路径的 sync 是通用正文重解析，非 LinkImportRestorer**→导入的 target_id 优先绑定恢复在 active 批准路径**须额外接线 build_link_restorer**（用 payload frontmatter hints），否则绑定优先丢失。这是 K1 复用**不足以**覆盖导入语义之处，须设计补充。

### 5.5 Offline Backup 双方言统一编排 —— **可统一协议，保留方言分支**

【已验证事实】SQLite Online Backup API 可用（Connection.backup present，3.45.1）；PG pg_dump/pg_restore 16.8 可用。design §10:838-840 已列双方言快照/切换/崩溃恢复差异。
【设计建议】统一离线维护协议（维护模式→quiesce→快照→校验→恢复→切换→对账→完成标记），**方言分支封装 app/db/backup.py + services/backup.py**：
- 快照：SQLite `Connection.backup`/`VACUUM INTO`（**禁裸拷 db+wal+shm**）；PG `pg_dump --format=custom`。
- 恢复切换：SQLite 临时文件 os.replace（关闭句柄后）+ 附件指针；PG Staging + **池重建（dispose+init，非 URL 自动切换）**。
- 崩溃恢复：SQLite 租约过期+Manifest 回滚；PG advisory 会话释放+池切回旧库+对账。
【合理推断】单实例下两者可在同一协议编排；**多实例 PG 须编排器（design:672，A1-04 延后）**。

### 5.6 严格迁移策略 —— **表/列无需迁移；但 DB 级幂等/状态/去重须迁移（红线冲突）**

【已验证事实】
- A1-04 所需**表与列全部已由 0006 建好**（attachment/tag/item_tag/tag_change_log/gc_task/import_origin/storage_lock/knowledge_link + knowledge_item 4 列）。`test_item_source_identity_columns` 证实列可写。**导入导出/附件/GC/备份的核心功能无需新迁移**。
- Manifest/migration_ops_log/附件版本指针**可落文件**（backend/data/ops/，仿 persist_rebuild_report links.py:519）→**无需新迁移**。
【阻断问题·红线 #2 冲突】以下**若要求 DB 强制**则**须新迁移/改 0006**（本轮禁止）：
- import_origin **唯一约束**（并发幂等 DB 兜底）——现无（P0-2）。
- ImportOrigin **待应用 status 列**（active pending 表示）——现无（P0-1）。
- review_request **pending 去重唯一约束**——现无（P0-1 问 4）。
- gc_task **storage_key 唯一**（防多任务）/ attachment **(item_id,storage_key) 唯一**（防重复引用）——现无（5.2/5.3）。
【设计建议】**本轮不新增迁移**（守红线 #2）。上述 DB 强制项**降级为应用层方案**（单实例进程锁+per-hash/per-item 串行+同事务+enqueue 去重+ImportOrigin-at-approve）。**若 ChatGPT 认为必须 DB 强制**→须**升级为独立迁移审批项**，不在本轮擅自加。**不得为完成任务擅改迁移**。

---

## 5. 现有 Schema 与设计要求对照表

| 设计能力 | 设计依据 | 现有 Schema/代码 | 差距 | 须迁移? |
|---|---|---|---|---|
| 附件内容寻址共享 | §2.5 | attachment.storage_key/content_hash + 非唯一索引（models.py:336-351）；COUNT 派生测试 PASSED | 无（可建） | 否 |
| 引用数 DB 派生 | §2.5 | count_references 端口（ports.py:292）+ 测试 PASSED | 无 | 否 |
| storage_key 互斥 | §2.5.1 | storage_lock PK（models.py:447）+ IntegrityError 测试 PASSED | 无（SQLite 租约/PG advisory 须实现） | 否 |
| GC 七态+租约+quarantine | §2.5.2 | GcStatus 七态 + gc_task 全字段（models.py:379-407） | 流转合法性须实现层强制；**无 storage_key 唯一** | 否（唯一约束须迁移） |
| 导入来源身份 | §2.6.3 | import_origin 全字段 + item.source_*（models.py:410-435/114-116） | **无唯一约束**；**无 status 列** | 否（唯一/状态须迁移） |
| 导入幂等"唯一约束" | §2.6.2:460 | **不存在**（仅非唯一索引） | **设计宣称与事实不符** | **是（若须 DB 强制）** |
| extra_metadata 保真 | §2.6 | 列存在可写（测试 PASSED）；**V1 仓库不映射** | 须专用持久化路径（D-02） | 否 |
| active 导入审核承载上下文 | §2.6/§2.7 | payload 自由 JSON 可存；**_apply_update 只 4 字段**；restorer 未接线 | 须 backend 批准钩子+payload 契约 | 否 |
| 审核 pending 去重/复用 | §2.7:501 | **A1-05 未实现**；submit 无去重；review_request 无唯一 | A1-04 应用层去重或留 A1-05 | 否（DB 唯一须迁移） |
| 链接键唯一 | §2.2 | knowledge_link UNIQUE(source,key)（models.py:310） | 无（A1-03 已建） | 否 |
| 审计口径 C | §2.2 | tag_change_log append-only + snapshot（models.py:354-376） | 无 | 否 |
| 备份 Manifest | §6 | **无实现**；可落文件 | 须新代码 | 否（文件） |
| 单实例进程锁 | （design 未具体设计） | **无实现**；msvcrt 可用 | 须新代码 | 否 |
| PG Staging 恢复 | §6.5 | pg_dump 16.8 可用；engine dispose/init 可用 | 须维护模式+编排新代码 | 否 |

---

## 6. SQLite / PostgreSQL / Windows 差异表

| 维度 | SQLite（实测 3.45.1） | PostgreSQL（实测 16.8） | Windows（实测 win32） |
|---|---|---|---|
| 行级写锁 | **无**（BEGIN IMMEDIATE 库级） | 有（FOR UPDATE/行锁） | — |
| storage_key 锁 | 租约逻辑锁（storage_lock PK+fencing+短事务） | 会话级 advisory（hashtext(key)） | — |
| 导入幂等 DB 兜底 | **无唯一约束**（同 PG） | **无唯一约束**（同 SQLite） | — |
| 并发串行化 | 单写者/库级短事务/进程锁 | advisory/行锁 | 进程锁 msvcrt |
| 一致性快照 | Online Backup API（present）/VACUUM INTO | pg_dump --format=custom（MVCC） | 两者 exe/stdlib 可用 |
| 恢复切换 | os.replace 临时文件+指针 | Staging+池重建（dispose+init） | os.replace（非 os.rename）；占用退避 |
| DB 重命名 | N/A（文件替换） | **ALTER DATABASE RENAME 须无活动连接**【合理推断】 | — |
| 进程锁 | msvcrt.locking（present）/fcntl | 同左（OS 级，跨方言） | **msvcrt 句柄锁，死亡自动释放，无 PID 复用** |
| 文件占用 | — | — | **sharing violation 阻 rename/delete→退避重试不强删** |
| symlink | — | — | **需特权→指针文件降级** |
| 跨卷 rename | — | — | **非原子（copy+delete）→Manifest+对账兜底** |
| DROP COLUMN | ≥3.35（3.45.1 OK，保 FTS5 触发器） | op.drop_column | — |
| --reload 进程 | reloader+worker 两进程 | 同 | 锁归属须验证【待验证】 |

---

## 7. 发现的设计冲突与缺陷（直接指出，不迁就原方案）

| 编号 | 冲突/缺陷 | 证据 | 性质 |
|---|---|---|---|
| **F-01** | **design §2.6.2:460 宣称导入并发"按 item 串行（行锁/唯一约束）"，但 import_origin 无任何唯一约束、SQLite 无行级写锁** | models.py:418-421 / 0006:182-187（仅非唯一索引）；ports.py:418 返回 list；design:41/311 自认 SQLite 无行锁 | **重大事实错误**（设计过承诺） |
| **F-02** | **plan §5.1 假设 active 导入 submit→approve 应用全部上下文（tags/extra_metadata/附件/源身份/绑定优先链接），但 Core _apply_update 只应用 4 字段、批准路由只做通用正文 sync、LinkImportRestorer 未接线** | review/__init__.py:134-141；routes/governance.py:369→links.py:43；links.py:537 restorer 无路由调用 | **重大设计缺口**（批准路径丢上下文） |
| **F-03** | **ImportOrigin 无 status 列，无法表示 active 待应用态；submit 时写→reject 遗留假记录，approve 时写→pending 期无幂等记录** | entities.py:285-301 / models.py:410-435（无状态列）；reject review/__init__.py:98-105 不触 origin | **设计未解决的两难** |
| **F-04** | **design §2.7:501「hash 相同→复用 pending」属 A1-05（未实现）；A1-04 submit 无去重 + review_request 无唯一约束→重导多张 pending** | review/__init__.py:77-81；0003:47-60；markdown/__init__.py:392 标注 A1-05 | **范围边界须澄清**（D-01） |
| **F-05** | **design §6.5:672「不得假设单实例」多实例编排，与 A1-04 单实例部署 + P0-3 进程锁缺口 tension；单实例 quiesce/维护模式无具体设计** | design:672；main.py:34-45 无锁/维护模式；grep 无进程锁 | **设计缺口**（单实例假设须明确） |
| **F-06** | **C-01：V1 KnowledgeRepository 不映射 extra_metadata/tags/source_*；若扩展 V1 update 映射 extra_metadata，V1 PATCH（entity 默认 {}）会清空导入 extra_metadata（数据丢失）** | knowledge.py:28-48/102-112；schemas.py:103-109 无 extra_metadata | **数据丢失风险**（D-02 须选独立路径） |
| **F-07** | **design §6.1 称 SQLite WAL，但 session.py 未启用 WAL（rollback-journal）；备份若依赖 WAL 须先确认** | session.py:36-41 仅 foreign_keys+busy_timeout；design §6.1 | **文档与代码不符**（备份用 Online Backup 不依赖 WAL 可解） |
| **F-08** | **gc_task 无 storage_key 唯一、attachment 无 (item_id,storage_key) 唯一→同 key 多任务/重复引用行可能；设计未明确 enqueue 去重** | models.py:387-390/340（非唯一索引） | **实现风险**（应用层去重） |
| **F-09** | **review_payload_hash 只覆盖 title/content/status/space_id；导入的 tags/extra_metadata/附件/源身份不在审核 hash 保护内（A1-05 防覆盖也不保护）** | markdown/__init__.py:384（A1-02 冻结） | **保护范围缺口**（须文档明示） |

---

## 8. 每个问题的解决建议

| 编号 | 建议 | 须迁移? | 须改冻结代码? | 决策 |
|---|---|---|---|---|
| F-01/P0-2 | 幂等降级：**单实例进程锁（P0-3）+ 应用层 per-source_hash 串行（PG advisory / SQLite 库级短事务或进程内锁）+ origin/item 同事务**。**停止宣称 DB 唯一约束**。多实例 DB 强制幂等→须迁移（独立审批） | 否（单实例）/ 是（多实例 DB 强制） | 否 | **D-02/D-09 + 新 D-15** |
| F-02/P0-1 | 新增 **backend 导入批准钩子**：approve 后 commit 前应用 tags/extra_metadata/附件/ImportOrigin + **build_link_restorer（payload frontmatter hints，target_id 优先）**。payload 定义导入上下文契约。**不改 Core ReviewService** | 否 | 否（backend 新代码） | **D-03 扩展** |
| F-03/P0-1 | **active 导入 ImportOrigin 推迟到 approve 写**；pending 期幂等查 review_request.payload 源 hash（应用层去重）。draft 导入即时写 origin。**不新增 status 列** | 否 | 否 | **新 D-16** |
| F-04 | A1-04 **不实现**防覆盖/撤回（A1-05）；ImportReport.warnings 如实记录多 pending 限制；应用层 pending 去重可选 | 否 | 否 | D-01 |
| F-05/P0-3/P0-4 | 明确 **A1-04 单实例部署假设**；新增 OS 进程锁（msvcrt/fcntl）+ 维护模式 quiesce；多实例编排器延后【待审批】 | 否 | 否 | **D-10 扩展 + 新 D-17** |
| F-06/5.1 | **D-02 选 A/C（独立 MarkdownItemRepository，直接 ORM 写 extra_metadata/source_*/tags，V1 仓库不动）**；若选 B 须 _to_entity 读+保留未提供字段+全量回归 | 否 | 否（A/C）/ M1 改动（B） | **D-02** |
| F-07 | 备份用 **Online Backup API/VACUUM INTO（不依赖 WAL）**；WAL 启用与否独立评估，**本轮不启用** | 否 | 否 | D-09 |
| F-08 | gc_task enqueue 应用层去重（查 list_tasks(storage_key) 非终态）；attachment 引用去重应用层；**DB 唯一须迁移（本轮不做）** | 否（应用层） | 否 | 5.2/5.3 |
| F-09 | 文档明示审核 hash 保护范围仅 4 字段；导入扩展上下文**不受 review_payload_hash 保护**（A1-05 也不保护）；ImportReport 告警 | 否 | 否 | D-01 |

---

## 9. 是否需要调整 A1-04 原设计

**是，必须调整。** 原四份设计材料存在与真实代码不符的过承诺/缺口，**不得原样冻结**：

1. **implementation-plan §5.1（active 导入数据流）**：须改为"submit 存 payload 上下文契约 → approve 经 **backend 导入批准钩子**应用 tags/extra_metadata/附件/ImportOrigin/绑定优先链接"，**删除"Core approve 应用全部上下文"的隐含假设**（F-02）。
2. **implementation-plan §6 / risk-register R-IMP-02 / acceptance-matrix IMP-03/04/18**：须**删除"DB 唯一约束保证幂等"表述**，改为"单实例进程锁+应用层 per-hash 串行+同事务"，并**明示多实例 DB 强制幂等被红线 #2 阻断**（F-01）。
3. **open-decisions D-02**：须**强烈推荐选项 A/C（独立路径）**，明示选项 B 的 V1 编辑清空 extra_metadata 数据丢失风险（F-06）。
4. **新增决策**：D-15（幂等并发策略：单实例 vs 迁移加唯一约束）、D-16（ImportOrigin-at-approve 时机 + pending 应用层去重）、D-17（单实例部署假设 + 进程锁 + 维护模式 quiesce）。
5. **implementation-plan §13 / open-decisions D-09**：确认 Manifest/指针/migration_ops_log **文件持久化无迁移**；WAL 不启用（F-07）。
6. **acceptance-matrix**：新增 P0-3 进程锁验收（双 backend 互斥/CLI 互斥/异常退出释放/--reload 归属）、P0-1 批准钩子验收（active 导入 tags/extra_metadata/附件/绑定优先批准恢复/reject 不遗留 origin）、P0-2 并发幂等验收（单实例双请求仅一）。
7. **范围澄清**：F-04（防覆盖/撤回 A1-05）、F-05（多实例编排延后）须在边界章节明示。

> 上述调整**不改变 A1-04 总体架构方向**（在既有 Schema 上补服务/仓库/API/适配/存储/GC/备份/运维层），但**修正过承诺、补缺口、明确单实例约束**。**本轮未修改原设计文档**（红线），仅在本报告提出调整建议，待 ChatGPT 审计后决定是否修订正式设计。

---

## 10. 是否具备进入正式设计冻结的条件

**当前不具备原样冻结条件。** 四项 P0 门禁均**非 PASS**：

- P0-1：批准链路丢上下文（F-02）+ ImportOrigin 无待应用态（F-03）→须修订设计为 backend 批准钩子 + at-approve 时机。
- P0-2：DB 无唯一约束（F-01）→须修订为单实例+应用串行，并明示多实例 DB 强制被红线阻断。
- P0-3：进程锁完全缺失→须新增设计（stdlib 可行）。
- P0-4：备份编排/quiesce/Manifest 全缺→须新增设计（工具齐备）。

**但所有问题均属"明确可解决"**：无迁移/不改冻结端口前提下，经"backend 批准钩子 + 独立 MarkdownItemRepository + 单实例进程锁 + 应用层串行/去重 + ImportOrigin-at-approve + 文件 Manifest + 维护模式"可安全实现。**唯一硬约束冲突**：多实例并发导入的 **DB 强制幂等**须迁移（红线 #2 禁止）→须 ChatGPT 在"接受单实例约束"与"批准独立迁移审批"间拍板。

---

## 11. 问题汇总表

| ID | 问题 | 严重程度 | 证据 | 影响范围 | 建议处理 |
|---|---|---|---|---|---|
| F-01 | import_origin 无唯一约束，design 宣称"唯一约束"幂等不符 | **P0** | models.py:418-421；0006:182-187；ports.py:418；design:460 | 导入并发幂等/重复建单 | 单实例进程锁+应用 per-hash 串行+同事务；多实例 DB 强制须迁移审批 |
| F-02 | active 批准只应用 4 字段，tags/extra_metadata/附件/源身份/绑定优先链接丢失 | **P0** | review/__init__.py:134-141；governance.py:369；links.py:43/537 | active 导入保真/数据丢失 | backend 导入批准钩子+payload 契约+接线 build_link_restorer |
| F-03 | ImportOrigin 无 status，active 待应用态无法表示（reject 假记录/pending 无幂等） | **P0** | entities.py:285-301；review/__init__.py:98-105 | 导入幂等/审核一致性 | ImportOrigin-at-approve+pending 查 review payload 去重 |
| F-06 | 扩展 V1 update 映射 extra_metadata 会致 V1 PATCH 清空导入数据 | **P0** | knowledge.py:102-112；schemas.py:103-109 | V1/V2 同条目数据丢失 | D-02 选独立路径 A/C，V1 仓库不动 |
| F-05 | 单实例进程锁/维护模式 quiesce 缺失；design 多实例假设 tension | **P0** | main.py:34-45；grep 无锁；design:672 | 双写/备份恢复并发安全 | OS 进程锁（msvcrt/fcntl）+维护模式；明确单实例假设 |
| P0-4 | PG 备份编排/quiesce/Manifest/池切换全缺 | **P1** | grep 无 backup；session.py:60-66；pg_dump 16.8 可用 | 备份恢复可实施性 | 新备份服务+维护模式+文件 Manifest+Staging 池重建 |
| F-04 | A1-04 submit 无去重+review_request 无唯一→多 pending（防覆盖属 A1-05） | **P1** | review/__init__.py:77-81；0003:47-60；design:501 | 审核单堆积 | 边界澄清 A1-05；应用层去重可选；ImportReport 告警 |
| F-08 | gc_task 无 storage_key 唯一/attachment 无 (item, key) 唯一→多任务/重复引用 | **P1** | models.py:387-390/340 | GC 重复执行/引用计数膨胀 | 应用层 enqueue 去重；DB 唯一须迁移（本轮不做） |
| F-07 | design 称 WAL 但代码未启用 | **P2** | session.py:36-41；design §6.1 | 备份协议依赖 | Online Backup 不依赖 WAL；WAL 独立评估不启用 |
| F-09 | review_payload_hash 仅 4 字段，导入扩展上下文不受保护 | **P2** | markdown/__init__.py:384 | 审核防覆盖范围 | 文档明示+ImportReport 告警 |
| P0-3a | --reload reloader+worker 两进程锁归属未验证 | **P2** | dev.ps1:8 | 进程锁正确性 | 锁由 worker 持有；真实验证【待验证】 |
| 5.3a | GC 状态流转 DB 无 CHECK，Pydantic 不校验流转 | **P2** | entities.py:238-247；0006:154 | 非法流转 | 实现层状态机+fencing 强制 |

> 严重程度：**P0** 数据丢失/错误覆盖/恢复失败/并发安全缺陷；**P1** 核心功能无法实现或破坏架构边界；**P2** 局部功能缺失/实现风险；**P3** 优化建议。

---

## 12. 最终结论

### **B. CONDITIONAL PASS**

**理由**：四项 P0 门禁均有**充分真实证据**，发现的问题**明确可解决**，但**原设计存在重大过承诺与缺口（F-01/F-02/F-03/F-06），不得原样冻结**，须按 §9 修订设计后方可进入冻结。

- **非 A（PASS）**：P0-1 批准链路丢上下文、P0-2 DB 无唯一约束、P0-3 进程锁缺失、P0-4 备份编排缺失——均非"已有充分证据可原样冻结"。
- **非 C（BLOCKED）**：所有问题在"无迁移/不改冻结端口"下**有可行解**（backend 批准钩子 + 独立 Repository + 单实例进程锁 + 应用串行/去重 + ImportOrigin-at-approve + 文件 Manifest + 维护模式）。**唯一硬约束冲突**（多实例 DB 强制幂等须迁移）可通过**接受单实例部署约束**化解，非绝对不可解。
- **条件**：ChatGPT 须 (1) 批准 §9 设计修订；(2) 拍板 D-02（独立路径 A/C）、D-15（单实例 vs 迁移）、D-16（ImportOrigin-at-approve）、D-17（单实例+进程锁+维护模式）；(3) 确认 F-04/F-05 范围边界（A1-05 防覆盖、多实例编排延后）。

**直接指出的重大设计错误（不迁就）**：
1. design §2.6.2:460「导入并发按 item 串行（**唯一约束**）」——**import_origin 无任何唯一约束**，此宣称**错误**（F-01）。
2. plan §5.1 隐含「Core approve 应用全部导入上下文」——**Core _apply_update 只应用 4 字段**，此假设**错误**（F-02）。
3. ImportOrigin 被设计为可承载导入幂等/状态——**无 status 列、无唯一约束**，active 待应用态**无法表示**（F-03）。

**本轮成功标准达成**：在开发开始前发现真实架构问题（9 项冲突/缺陷，5 项 P0），均以源码/DB结构/真实运行取证，未为通过而迁就原方案。

---

## 13. 停止点

本轮只读核验完成，仅交付本报告。**未写业务代码、未改测试/迁移/依赖/lockfile/pyproject/package.json/MILESTONES、未 reset/checkout/stash/rebase、未 commit/push、未启动 A1-04 开发、未修改原四份设计文档**。

**现停止，等待 ChatGPT 对本报告进行阶段级独立审计，再决定是否修改正式架构设计。** 不擅自进入开发，不擅自修订原设计。