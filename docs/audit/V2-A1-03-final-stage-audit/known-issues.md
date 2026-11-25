# A1-03 阶段级最终审计 · 已知问题与未交付功能盘点

> 归类口径（§X）：
> **A 已解决** / **B 有条件完成** / **C 延后后续批次** / **D 仍然阻断 A1-03** / **E 需用户产品决策**。
> 原则：不把合理延期误判为缺陷，也不把未交付功能包装成完成。每项附源码/文档位置与证据类别。
> 证据类别：【已验证事实】【设计判断】【潜在风险】【尚待验证】【未交付功能】。

## 总览

| 类 | 数量 | 含义 |
|---|---|---|
| A 已解决 | 6 | 本轮整改批已修复并真实测试验证 |
| B 有条件完成 | 2 | 正确性达标，但附已诚实记录的运行条件/限制 |
| C 延后后续批次 | 11 | 明确延期，非 A1-03 阻断项 |
| D 仍然阻断 A1-03 | **0** | **未发现阻断缺陷，未发现知识数据丢失路径** |
| E 需用户产品决策 | 4 | 范围/语义须用户拍板，非技术缺陷 |

**关键结论：D 类为空。** 所有失败路径均整体回滚零写入；未发现造成知识数据丢失的已知路径。

---

## A 类 · 已解决（真实测试验证）

### A-1 K1 治理批准路径链接维护时序
- **问题**：治理批准（approve）/草稿直改（submit/restore）应用变更后，出链未同步、DELETE 入链未降级。
- **整改**：`governance.py` 三入口挂接——DELETE 在 delete-flush **前**降级入链（`_demote_backlinks_before_delete`）；UPDATE/RESTORE 在内容应用后、commit **前**同步出链（`_sync_links_after_content_change`）；MERGE 不降级（归档保留合法绑定）。
- **证据**：【已验证事实】`k1-governance-sqlite.txt`（25）+ `k1-governance-pg.txt`（11）；源码 `governance.py:198-201,272-284,324-349,361-369`。
- **结论**：A 已解决。

### A-2 K1 409 稳定码 + 整事务零写入
- **问题**：全局版本异写时若静默降级或回传异常文本，违反 fail-loud 与脱敏。
- **整改**：`links.py:sync_links_or_conflict` 捕获 `LinkNormalizationVersionMismatch` → 409 + 稳定码 `link_version_mismatch`（不回异常文本/版本明细）；调用方尚未 commit → 整请求零写入（含审核决议回滚）。
- **证据**：【已验证事实】`links.py:36-45`；K1 套件含 409 零写入断言。
- **结论**：A 已解决。

### A-3 门禁 C 重读→提交窗口②（PG）
- **问题**：PG READ COMMITTED 下 SELECT 不锁行，重读→提交间并发写可漂移。
- **整改**：`locking.py` PG `LOCK TABLE knowledge_link IN SHARE ROW EXCLUSIVE MODE` + `SELECT … FOR UPDATE`，持锁至提交，串行化重建写者（含 phantom 新键）。
- **证据**：【已验证事实】`k2-concurrency-pg.txt`（7）+ `phantom-pg.txt`（6，含真实双连接外部 INSERT 阻断）。
- **结论**：A 已解决（PG 窗口②完全关闭）。

### A-4 P2 乐观前置字段覆盖（3→6 字段）
- **问题**：步7 P2 前置原仅 3 字段，与门禁 C 6 字段口径不一致，标题/别名漂移可漏检。
- **整改**：P2 WHERE 扩至门禁 C 同口径 6 字段（source_id/键/版本/标题/别名 + rowcount 校验），rowcount≠1 → `LinkRebuildPostWriteError` 整体回滚。
- **证据**：【已验证事实】`p2-sqlite.txt`（8）+ `p2-pg.txt`（9）；提交 `b6c7e15`。
- **结论**：A 已解决。

### A-5 no-op 行窗口②保护（步8c）
- **问题**：空/混合 updates 中 no-op 行不经步7 P2，重读→提交间漂移无检测。
- **整改**：步8c 对 `plan.row_snapshots` **全部原始记录**逐行复核（含 no-op 行），快照≠当前 → 拒绝整体回滚。
- **证据**：【已验证事实】`noop-sqlite.txt`（12）+ `noop-pg.txt`（13）；提交 `9634ad1`。
- **结论**：A 已解决。

### A-6 Phantom 非碰撞新增 ID 集合守护
- **问题**：并发插入一条新链接（新 ID、非碰撞键、目标版本、通过 DB 约束），步8c 单向复核能否发现？
- **核实**：步8 `_governance_baseline` 为**全表 id-keyed dict（无 WHERE）**，步8 前后整 dict 相等比较 → 任何新增/删除 id 必致不等 → 拒绝。ID 集合相等由**步8 治理基线**保证（非步8c，步8c 为单向）。
- **证据**：【已验证事实】`phantom-sqlite.txt`（4）+ `phantom-pg.txt`（6）；`services/links.py:297-306,457-458`；提交 `784b124`；专项报告 `docs/acceptance/V2-A1-03-final-phantom-audit/`。
- **结论**：A 已解决（无需改生产代码，ID 集合相等已保证）。

---

## B 类 · 有条件完成（正确性达标 + 已诚实记录的限制）

### B-1 SQLite 窗口②安全依赖乐观兜底而非读锁
- **现状**：SQLite 默认 rollback-journal，**实测读阶段（步2/3 SELECT）不持阻塞写者的锁**。窗口②「重读→写」不由锁保护，而由步7 P2（update 行）+ 步8c（no-op 行）+ 步8 治理基线（phantom/ID 集合）三层乐观兜底保证**正确性**（漂移→零写入回滚）。进入写阶段后 UPDATE 持 RESERVED，并发写者提交被阻。
- **条件/限制**：【潜在风险】这是**正确性保证而非互斥保证**——并发漂移下重建以零写入回滚告终**须重试**；不宣称读阶段已锁保护。
- **证据**：【已验证事实】`locking.py:11-21,48-52` 诚实 docstring；`k2-concurrency-sqlite.txt`（7，含读阶段语义固化 + P2 故障注入）。
- **结论**：B 有条件完成（正确性达标，互斥/活性见 C-1/C-2）。

### B-2 SQLite 写升级争用活性（BUSY）
- **现状**：写阶段 RESERVED→EXCLUSIVE 升级争用属活性问题，引擎 `busy_timeout=5000`（`session.py:40`）降低即失败概率，**未消除 BUSY**。
- **条件/限制**：【潜在风险】高争用下重建仍可能 SQLITE_BUSY 失败 → 零写入回滚须重试；`locking.py` 明示「不宣称已消除 BUSY」。
- **证据**：【已验证事实】`session.py:33-41`；`locking.py:18-21`。
- **结论**：B 有条件完成（活性降级为可重试失败，非数据损坏）。

---

## C 类 · 延后后续批次（明确延期，非 A1-03 阻断）

### C-1 SQLite BEGIN IMMEDIATE 未启用
- **内容**：读阶段即取写锁可关闭 SQLite 窗口②互斥，但需全局事务控制管线改动。
- **状态**：【设计判断】本轮不做，`locking.py:19-21` 诚实记录。延后。
- **来源**：K1K2 整改报告 §8；`locking.py` docstring。

### C-2 SQLite WAL 多进程边界
- **内容**：WAL 模式下多进程读写边界与重建互斥的适用性。
- **状态**：【尚待验证】当前**未启用 WAL**（默认 rollback-journal），WAL 多进程边界不适用本轮；启用 WAL 属后续部署决策。延后。
- **来源**：no-op 专项审计 §六；`session.py`（未设 WAL）。

### C-3 K1 选项 B（Core ReviewService 链接 hook）未实施
- **内容**：把链接维护下沉到 Core `ReviewService._apply_action`，使非 HTTP 调用方也自动维护。
- **状态**：【潜在风险】需改冻结端口签名，本轮选项 A（路由层挂接）已覆盖全部现有 HTTP 入口；Core hook 延后。
- **证据**：【已验证事实】`knowledge_core/review/` grep 链接维护**零命中** → 维护仅在路由层。
- **来源**：K1K2 报告 §8；K1 计划 §4。

### C-4 Governance 非 HTTP 调用方绕过（残余架构风险）
- **内容**：未来若有非 HTTP 调用方直接调用 Core ReviewService，将绕过路由层链接维护。
- **状态**：【潜在风险】**当前无此类调用方**（全部经 HTTP 路由），属架构残余风险而非现行缺陷；与 C-3 同源，选项 B 实施后消除。
- **证据**：【已验证事实】现有三入口均经 `governance.py` 路由；Core 无 hook。
- **来源**：K1 计划 §4 L64。

### C-5 D8 人工显式绑定无 HTTP 写入口
- **内容**：`bind_explicit`（archived/跨空间候选显式绑定）仅 Core 层定义与测试，**无 HTTP 写端点**。
- **状态**：【未交付功能】A1-03 范围明确只交付候选发现 + 读取（3 GET）；绑定写入口延后 A1-04/A2。
- **证据**：【已验证事实】`links.py:1,6-7,48-95`（仅 3 GET，零写）；`link_service.py:541-567`（bind_explicit Core-only）。
- **来源**：known-issues.md K3 L36-44；D8 设计决策。

### C-6 链接键规范化 v2 规则未发布
- **内容**：`LINK_KEY_RULES={1:v1}`，v2 仅测试夹具（monkeypatch.setitem），未正式发布。
- **状态**：【未交付功能】v2 发布属后续批次；`link_key_for_version` 对未注册版本抛 ValueError（fail-loud）。
- **证据**：【已验证事实】`links.py:19,111-121`。
- **来源**：known-issues.md K4 L46-54。

### C-7 `![[embed]]` 嵌入解析延后 A1-04
- **内容**：WikilinkParser 排除 `![[embed]]` 并产 warning（D6 保留），嵌入语义解析延后。
- **状态**：【未交付功能】A1-04 范围。
- **证据**：【已验证事实】`links.py:318-329`。
- **来源**：D6 设计决策。

### C-8 MERGE 反链重定向语义
- **内容**：合并归档源条目后，指向源的反链是否重定向到目标。
- **状态**：【未交付功能】当前 MERGE 归档而非删除，入链是对存在条目的合法绑定，**不降级**；重定向属产品语义决策（见 E-2）。
- **证据**：【已验证事实】`governance.py:324-334`（MERGE 不降级）。
- **来源**：known-issues 提取。

### C-9 标题重命名后字面 staleness / 跨空间移动不重算 cross_space
- **内容**：稳定 ID 绑定下重命名不破坏链接（设计目标），但 wikilink 字面文本与目标标题可能 staleness；条目跨空间移动时 cross_space 标志不自动重算。
- **状态**：【潜在风险】稳定 ID 优先保证链接不丢；字面同步/cross_space 重算属后续增强。
- **证据**：【设计判断】binding-first + stable target_id（`link_service.py:835-842`）。
- **来源**：known-issues 提取。

### C-10 R7 解析边界（4 空格缩进代码块 / HTML 注释不排除）
- **内容**：WikilinkParser 诚实限制——4 空格缩进代码块与 HTML 注释内的 wikilink **不被排除**。
- **状态**：【潜在风险】已诚实记录的解析边界，非静默缺陷；后续增强。
- **证据**：【已验证事实】`links.py:257`（R7 限制注释）。
- **来源**：R7 设计限制。

### C-11 R5 运维静默期 / no-cache k-writes=k-scans
- **内容**：全局版本同构守卫无缓存（每次 DISTINCT 扫描），k 次写=k 次扫描；重建建议运维静默期执行。
- **状态**：【设计判断】no-cache 保证守卫实时正确（不读旧值）；性能/静默期属运维优化延后。
- **证据**：【已验证事实】`link_service.py:114-130`（pure no-cache）；`services/links.py:97-101`（单列 DISTINCT no-cache）。
- **来源**：R5 运维建议；known-issues 提取。

---

## D 类 · 仍然阻断 A1-03

**无。** 本次审计未发现阻断缺陷：
- 所有重建失败路径整体回滚零写入（门禁 A/B/C + P2 + 步8 + 步8c + 治理基线）。
- 未发现知识数据丢失路径：D12 入链降级保留为 missing（DB 层 target FK ON DELETE SET NULL + 应用层 demote 双重）；MERGE 归档非删除；导入冲突 preserve-all；codec 解析失败兜底 + 告警绝不静默丢数据。
- 双方言全量 + 专项全绿（SQLite 930/178、PG 1108/0，0 失败）。
- Core 独立性 / A1-02 冻结契约未被 A1-03 破坏。

---

## E 类 · 需用户产品决策

### E-1 人工绑定用户操作入口范围（D8）
- **决策点**：是否在 A1-04/A2 交付绑定写 HTTP 端点 + 前端绑定 UI（archived/跨空间候选显式选择）。
- **现状**：【未交付功能】Core 能力已备（bind_explicit + find_candidates），HTTP/前端入口未交付。
- **建议**：A1-04 优先交付，使「候选发现→显式绑定」闭环对用户可用。

### E-2 MERGE 反链重定向语义
- **决策点**：合并后指向源的反链应重定向到目标、保留指向归档源、还是降级 missing？
- **现状**：当前保留指向归档源（合法绑定，不降级）。
- **建议**：须用户定义合并语义后再实施（与 C-8 同源）。

### E-3 v2 规范化规则发布时机
- **决策点**：何时正式发布 v2 键规则及迁移策略（现有 v1 键如何升级）。
- **现状**：【未交付功能】v2 仅测试夹具。
- **建议**：与重建/迁移批次统筹，避免键域分裂。

### E-4 重建 / 重解析用户触发 UX
- **决策点**：重建（apply_link_key_plan）与重解析（reresolve）是否暴露用户触发入口、碰撞报告如何呈现。
- **现状**：【未交付功能】Core/backend 能力已备并真实测试，但**无 HTTP 触发端点、无前端 UI**；前端「重建索引」按钮属**搜索索引**（/search/reindex）非链接重建。
- **建议**：后续批次交付触发 + 结构化碰撞报告查看入口。

---

## 附：A1-02 冻结测试计数更正
- 历史报告曾记 293，本次实测冻结三文件（canonical+codec+frontmatter）= **291 passed**（`a1-02-frozen.txt`）。以本次真实计数 291 为准。【已验证事实】