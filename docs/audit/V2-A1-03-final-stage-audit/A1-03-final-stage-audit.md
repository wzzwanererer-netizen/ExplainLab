# ExplainLab V2 · A1-03 阶段级最终独立审计报告

> **审计对象**：A1-03 完整交付（含 A1-01/A1-02 基础、A1-03 核心、K1/K2/P2/no-op/Phantom 全部整改批）。
> **审计性质**：阶段级最终独立审计（Final Stage Audit），只读审查 + 真实测试 + 构建 + Git 历史检查 + 独立源码核对。
> **最终问题**：A1-03 是否达到冻结条件，是否可以进入 A1-04。
> **审计日期**：2026-11-20 / 2026-11-21。
> **执行边界遵守**：未修改任何业务代码；未提交本报告（待批准）；未 push；未进入 A1-04；未修改 MILESTONES.md；未 reset/rebase/checkout/覆盖既有工作；未清理历史提交或交付材料。
>
> **证据类别图例**（全文严格区分）：
> 【已验证事实】= 真实运行输出或亲自核对源码所得；
> 【设计判断】= 基于源码/设计文档的合理推断；
> 【潜在风险】= 已识别但当前未触发的风险；
> 【尚待验证】= 本环境/本轮未覆盖；
> 【未交付功能】= 能力存在但无用户操作入口或不在本轮范围。

---

## 0. 执行摘要与阶段结论

**总体结论：CONDITIONAL PASS（有条件通过）——就 A1-03 原定的 Core/backend 范围，具备正式冻结条件；用户可见的链接专属功能为已记录的后续批次延期（D8），非阻断缺陷。**

三句话结论：
1. **A1-03 后端/核心目标已完成并经真实双方言验证**：稳定链接、反链、绑定优先、导入恢复、重建十步并发保护全部落地，SQLite 全量 930 passed/178 skipped、真实 PostgreSQL 16.8 全量 1108 passed/0 skipped，专项与质量门禁全绿，**0 失败、0 阻断（D 类为空）、未发现知识数据丢失路径**。
2. **A1-01/A1-02 基础契约未被破坏**：Core 独立性守护（14）、A1-02 冻结契约（291）通过；链接键规范化独立于三 Hash，Hash 输入仍用原始 Unicode。
3. **用户经 Web 尚不可直接操作/查看链接专属功能**：前端零链接消费者，人工绑定/重解析/重建触发/碰撞报告/反链展示均无 HTTP 写入口或 UI（D8 明确延后）。链接维护目前作为治理写的**透明副作用**自动发生。

**对「是否进入 A1-04」的建议**：建议**有条件批准**——A1-03 后端/核心可冻结；A1-04 宜覆盖延后的用户入口（D8 绑定 UI、embed、v2 发布、重建/重解析触发与碰撞报告查看），并持续跟踪 SQLite 活性/WAL 与 K1 选项 B 非 HTTP 绕过残余风险。**但本审计不自动进入 A1-04**；最终决定等待 ChatGPT 独立复审 + 用户批准（§XIII）。

---

## 1. 审计范围与方法

- **范围**：A1-01（Core 底座）、A1-02（Markdown 交换/三 Hash/frontmatter）、A1-03（稳定链接四层）、K1（治理三入口链接维护）、K2（双方言并发窗口控制）、P2（六字段乐观前置）、no-op（步8c）、Phantom（非碰撞新增 ID 集合守护）。
- **方法**：① 从**当前仓库实际读取** Git 历史/环境（不假定哈希与历史报告一致）；② 先验证环境与数据库再跑测试；③ 全量 + 专项 + 质量门禁真实运行落盘；④ **逐项亲自核对源码**（非仅引用测试名）；⑤ 区分 Core 能力 / API 交付 / 前端可操作 / fixture 内部四层；⑥ 正确性/活性/互斥三维分开报告，SQLite 与 PG 结论不互相套用。
- **配套交付**：`acceptance-matrix.md`（验收矩阵）、`known-issues.md`（A–E 盘点）、`test-evidence-index.md`（命令/退出码/计数索引）、`evidence/`（26 个原始输出）。

## 2. Git 历史与环境基线（§III，真实读取）

【已验证事实】（`evidence/git-baseline.txt`、`toolchain-baseline.txt`、`pg-baseline.txt`、`alembic-baseline.txt`）：

- **分支/HEAD**：`fix/m0-admission-and-m5-regressions`，HEAD `784b1248065424e07273b272d6016cc121bc606c`。
- **工作树**：已跟踪文件干净；唯一未跟踪 = 本审计交付目录（按 §XIII 暂不提交）。**无未提交业务改动、无遗漏交付物、无被覆盖/回滚/重复文件**。
- **历史**：18 提交**线性无合并**，父子链完整：
  `2d2b634`(M0 根)→`a2a8e01`(M1)→`4dcf61b`(M2)→`872db27`(M3)→`d6b29e7`(M4)→`59068e2`(M5)→`4557d2e`(M0 准入+M5 回归)→`3c9b28b`(docs)→`6d91718`(迁移0004回填)→`f847e4f`(A1-01/02)→`41ff761`(docs)→`5d6dcf1`(gitignore)→`715d9e7`(A1-03 四层)→`7e0582c`(A1-03 验收)→`ccf6194`(K1+K2)→`b6c7e15`(P2 六字段)→`9634ad1`(no-op 步8c)→`784b124`(Phantom，HEAD)。
  **M0 初始提交 `2d2b634` 为根未被改写；无 upstream = 未 push。** 每个整改批提交真实存在、父接子。
- **工具链**：Python 3.11.9、Node v22.23.2、uv 0.13.6、pytest 9.2.0。
- **数据库**：真实 **PostgreSQL 16.8**（PID 50260，port 5432，db `explainlab_test`，真实 `select version()` 取证）；开发默认 SQLite。
- **PG `knowledge_link` 真实 schema**：UNIQUE(source_item_id, normalized_link_key)、`ix_target_item_id`（反链索引）、source FK **ON DELETE CASCADE**（出链随源删除清理）、target FK **ON DELETE SET NULL**（入链随目标删除降级，D12 数据库层强制）。
- **迁移**：单一 head `0006_v2_markdown_kb`，0001–0006 齐全；开发 SQLite 库 current=`0005`（落后一步，**观察项非缺陷**：测试套件各自建库迁移至 head）。
- **依赖锁**：`uv lock --check`（41 包一致）、`npm ci --dry-run`（lock 一致）均 exit 0。

## 3. A1-01/A1-02 基础审计（§IV）

【已验证事实】
- **Core 独立性**：`ports.py` 仅 import stdlib + `domain.entities`，`LinkRepository` 为纯 Protocol（8 方法），无 ORM/Web。`test_core_has_no_web_framework_dependency` 在**干净子进程**导入全部核心模块（含 `markdown.links`/`link_service`），断言无 fastapi/starlette/flask/django——**通过**。12 服务 ABC 不可实例化——通过。markdown 零新增第三方依赖（无 PyYAML）——通过。（守护合计 14 passed）
- **A1-02 契约**：`StdlibMarkdownCodec` 五不变量（`codec.py:6-14`）——_frontmatter_raw⟺冲突态且拒绝重复已知键；冲突未解决暂存实体不写交换文件、不宣称无损往返；复杂未知值 _raw 逐字回写、诊断元键不再生；正文逐字保真；解析失败兜底+告警绝不静默丢数据。三 Hash（content/payload/review + 组件）确定性、`hashes_comparable` 版本门控（`__init__.py:346-452`、`canonical.py:148-158`）。冻结三文件 **291 passed**。
- **A1-03 未破坏基础**：`links.py:7-9` 明示链接键规范化 v1 与 A1-02 Hash 规范化**相互独立**，Hash 输入仍用原始 Unicode。【设计判断】A1-03 在独立派生索引层扩展，未触碰 Hash/codec/端口契约。

## 4. A1-03 核心功能审计（§V，逐项核对源码）

【已验证事实】源码位置见 acceptance-matrix 第三–六节。要点：
- **纯文本层 `links.py`**：normalize_v1（NFKC→strip→空白折叠→casefold，非 lower）；normalized_link_key=title键+\x1f+别名键（空别名→""非 NULL）；LINK_KEY_RULES{1:v1}，**v2 未发布**（仅夹具），未注册版本 ValueError；WikilinkParser 排除矩阵，`![[embed]]` 排除+warning（D6→A1-04）；**R7 诚实限制**：4 空格缩进代码块/HTML 注释不排除；merge_same_key first-occurrence；控制字符/长度守卫。
- **服务层 `link_service.py`**：全局版本同构守卫 pure no-cache；门禁 C `check_plan_freshness` 双向（row_deleted/added/not_covered/duplicate_id）6 字段精确 Unicode（None≠""），update 与 no-op 行均校 expected_key，noop_row_requires_update（T37）；自动解析三态（1→RESOLVED/>1→AMBIGUOUS/0→MISSING），archived 自动排除（E5/R24）；`find_candidates` 含 archived+跨空间供显式选择；**`bind_explicit` Core-only 无 HTTP 写入口（D8）**；BindingFirstLinkSync 绑定优先（局部守卫 all([])==True 已知边界）；LinkImportRestorer 三类非法/冲突 preserve-all/兜底/孤儿/绑定优先；BacklinkQuery 按稳定 target_id；LinkReresolve 仅 missing/ambiguous；LinkKeyRebuild.plan snapshots 全行、refused_mixed_version、refused_collision 整组零写入、updates 排除 no-op。
- **backend 适配 `services/links.py`**：`list_links` WHERE source、`list_backlinks` WHERE target（**索引查询，无必要全表加载**）；`list_all_links` 全表**仅重建独占事务**用；`_to_entity` D12 读侧防御映射；`demote_backlinks_on_delete` D12 写侧仅治理列（键/版本不变不触发守卫）；`_governance_baseline` **全表 id-keyed dict 无 WHERE**；`apply_link_key_plan` 十步（步1b 无条件取锁→门禁A→重读6列→治理/items基线→门禁B→门禁C→新键唯一→步7 P2 六字段+rowcount→步8 写后复核→步8c 逐行快照→步9 commit），任一步失败整体回滚零写入。**方言中立，仓库仅 flush()。**
- **反链可靠性**：稳定 ID 绑定使重命名不丢链接；PG `ix_target_item_id` + target FK SET NULL 双重保障。【已验证事实】后端正/反向查询正确。【未交付功能】**Web 未渲染反链**（前端零消费者）。

## 5. K1 治理三入口 × 四动作审计（§VI）

【已验证事实】（`governance.py`，K1 套件 SQLite 25 / PG 11 passed）：
- **三入口**：`approve_review`、`submit_review`（草稿直改）、`restore_version`（草稿直改）。
- **四动作时序**：DELETE 在 delete-flush **前**降级入链（先按 target_id 捕获再置 missing+NULL）；UPDATE/RESTORE 在内容应用后、commit **前**同步出链；MERGE **不降级**（归档保留合法绑定）；active 改删回滚/任何合并进审核（202/201）。
- **409 零写入**：`sync_links_or_conflict` → 409 稳定码 `link_version_mismatch`（不回异常文本），调用方未 commit → 整审核事务零写入。
- **其他写入口绕过核查**：全部经 governance 路由，无其他绕过写入口。
- 【潜在风险】**非 HTTP 调用方绕过**：`knowledge_core/review/` grep 链接维护**零命中** → 维护仅在路由层（选项 A）。Core `ReviewService._apply_action` 无链接 hook，未来非 HTTP 调用方将绕过。**当前无此类调用方**，属残余架构风险（选项 B 延后，需改冻结端口签名）。→ K1-08 **CONDITIONAL PASS**。

## 6. K2 并发与数据库审计（§VII，三维分开，双方言不互套）

【已验证事实】（`locking.py`、`session.py`，K2/P2/noop/phantom 双方言全绿）：

**PostgreSQL**（默认 READ COMMITTED）：
- **互斥**：`LOCK TABLE knowledge_link IN SHARE ROW EXCLUSIVE MODE` + `SELECT … FOR UPDATE`，持锁至提交，阻并发 INSERT/UPDATE/DELETE（含 phantom 新键），允许并发只读。
- **正确性**：窗口②（重读→提交，含步8→步9 间隙）**完全关闭**。
- **真实双连接证据**：`phantom-pg` 经 `lock_timeout` 证明外部非碰撞 INSERT 被表锁阻断、释放后插入成功（空/混合 updates 各一）。

**SQLite**（默认 rollback-journal，isolation_level=None）：
- **互斥**：【已验证事实】**实测读阶段（步2/3 SELECT）不持阻塞写者的锁**——窗口②「重读→写」**不由锁保护**。进入写阶段后 UPDATE 持 RESERVED，并发写者提交被阻（EXCLUSIVE 冲突）。
- **正确性**：由**步7 P2 六字段（update 行）+ 步8c 逐行快照（no-op 行）+ 步8 治理基线全表 ID 集合（phantom）**三层乐观兜底保证；漂移→rowcount=0 或基线不等→`LinkRebuildPostWriteError` 整体回滚零写入。
- **活性**：写升级争用（SQLITE_BUSY）由 `busy_timeout=5000` 降低即失败概率，**未消除 BUSY**；争用下重建以零写入回滚告终**须重试**。
- **诚实限制**：**未启用 BEGIN IMMEDIATE**（需全局事务管线改动，本轮不做）；**未启用 WAL**（多进程边界延后）。不宣称读阶段已锁保护，亦不宣称已消除 BUSY。

→ 互斥：PG **PASS** / SQLite **CONDITIONAL PASS**；正确性：双方言 **PASS**；活性：SQLite **CONDITIONAL PASS**（可重试失败，非数据损坏）。**未发现任何方言的数据丢失路径。**

## 7. API 与前端实际交付边界审计（§VIII，四层）

【已验证事实】（`links.py` 仅 3 GET；前端 grep 零命中；`KnowledgeDetail.tsx`/`KnowledgeMap` 核对）：
- **已交付 HTTP**：3 只读 GET（resolve-candidates / links / backlinks）+ 治理写（approve/submit/restore）的链接维护副作用。
- **Core 有·API 缺**：`bind_explicit`（人工绑定）、`reresolve`（重解析）、`apply_link_key_plan`（重建）、碰撞报告——**无 HTTP 写/触发端点**（D8）。
- **API 有·前端缺**：3 link GET **无任何前端消费者**（grep `backlink|wikilink|/links|resolve-candidates|link_version|rebuild|collision|reparse` 零命中）。
- **前端可操作**：链接专属功能**无一可操作**。`KnowledgeDetail` 仅渲染治理关系（api.listRelations）；`KnowledgeMap` 消费 /api/graph 关系边；**「重建索引」按钮属搜索索引（/search/reindex）非链接重建**。
- **明确回答**：人工绑定仍 Core-only？是。用户绑定 UI？无。重解析可执行？无 UI 入口。重建可触发？无 UI 入口。碰撞报告可查看？无 UI。**反链在 Web 实际展示？否。**
- 【未交付功能】**不得将上述后端能力描述为已交付的用户功能**——它们是 Core/backend 能力，用户入口属后续批次。

## 8. 完整测试矩阵（§IX，真实运行）

【已验证事实】详见 `test-evidence-index.md`。汇总（全部 exit 0、0 失败）：

| 套件 | 通过 | 跳过 |
|---|---|---|
| SQLite 全量 | 930 | 178（PG 门控） |
| **真实 PG 16.8 全量** | **1108** | **0** |
| Core 独立性守护 | 14 | 0 |
| A1-02 冻结 | 291 | 0 |
| K1 治理（SQLite/PG） | 25 / 11 | 0 |
| K2 并发（SQLite/PG） | 7 / 7 | 0 |
| P2（SQLite/PG） | 8 / 9 | 0 |
| no-op（SQLite/PG） | 12 / 13 | 0 |
| Phantom（SQLite/PG） | 4 / 6 | 0 |
| T22–T40+HTTP（SQLite）/ T22–T40（PG） | 110 / 91 | 0 |
| ruff / 前端 Vitest / typecheck / build | All passed / 72 / 0 / ✓ | — |

计数自洽：930+178=1108，证明 PG 全量为 SQLite 全量真实超集，PG 集成确已在线运行。**无 BLOCKED 项。**

## 9. 九个最终问题（§XI）

1. **A1-03 完成原定目标？** 【已验证事实】Core/backend 范围（E1–E4：解析/键/绑定/反链/导入/重建并发）**完成并真实验证**。【未交付功能】用户操作入口属 D8 明确延后，非 A1-03 原定后端范围。→ **后端目标达成**。
2. **稳定链接与反链可靠使用？** 【已验证事实】程序化层面可靠（稳定 ID、绑定优先、索引查询、双方言测试、D12 双重保障）。【未交付功能】终端用户经 Web 尚不可见/操作。→ **后端可靠，用户可见性延后**。
3. **SQLite/PG 关键数据一致性充分证据？** 【已验证事实】充分——全量+专项+真实双连接 PG+治理基线+P2+步8c+Phantom，双方言零写入回滚，PG 真实 schema 约束取证。→ **充分**。
4. **并发保护达到设计承诺？** 【已验证事实】PG 互斥+正确性完全达标；SQLite **正确性达标**（三层乐观兜底），**互斥/活性有条件**（读阶段不锁、BUSY 未消除，已诚实记录，BEGIN IMMEDIATE/WAL 延后）。→ **正确性达标，SQLite 活性有条件**。
5. **存在造成知识数据丢失的已知路径？** 【已验证事实】**未发现**——所有失败整体回滚零写入；D12 降级保留 missing；MERGE 归档非删除；导入冲突 preserve-all；codec 绝不静默丢数据。→ **无已知数据丢失路径**。
6. **用户实际能使用哪些功能？** 【已验证事实】经 Web：知识 CRUD、治理关系、搜索、地图（V1）；链接维护作为治理写**透明副作用**自动发生。【未交付功能】链接专属直接操作/查看（反链展示、绑定、重解析、重建、碰撞报告）**无入口**。→ **链接对用户透明自动维护，无直接入口**。
7. **哪些功能尚无用户操作入口？** 【未交付功能】人工绑定、重解析、重建触发、碰撞报告查看、出链/反链展示、候选发现 UI——全部链接专属 UI 未交付（D-03/04/05/07）。
8. **具备正式冻结条件？** 【设计判断】就 A1-03 原定 Core/backend 范围：**具备**（契约全验证、双方言全绿、0 阻断、0 数据丢失）。用户入口为已记录延期（DEFERRED），非冻结阻断。→ **后端/核心范围具备冻结条件**。
9. **批准进入 A1-04？** 【设计判断】**建议有条件批准**：A1-03 后端/核心可冻结；A1-04 宜覆盖延后用户入口并跟踪残余风险（SQLite 活性/WAL、K1 选项 B）。**本审计不自动进入 A1-04**，最终等待 ChatGPT 独立复审 + 用户批准。

## 10. 已知问题盘点（§X，A–E）

详见 `known-issues.md`。汇总：**A 已解决 6**（K1 时序/409、PG 窗口②、P2 六字段、no-op 步8c、Phantom ID 集合）；**B 有条件完成 2**（SQLite 乐观兜底正确性、BUSY 活性）；**C 延后 11**（BEGIN IMMEDIATE、WAL、K1 选项 B、非 HTTP 绕过、D8 绑定入口、v2 发布、embed、MERGE 重定向、字面 staleness/cross_space、R7 解析边界、R5 静默期/no-cache）；**D 阻断 0**；**E 产品决策 4**（绑定 UI 范围、MERGE 反链语义、v2 时机、重建/重解析 UX）。

## 11. 阶段结论与停止声明（§XII/§XIII）

**阶段结论：A1-03 = CONDITIONAL PASS。**
- 就原定 Core/backend 范围：**达到冻结条件**（PASS 主体，0 FAIL，0 BLOCKED，0 D 类阻断，0 已知数据丢失路径）。
- 条件项（CONDITIONAL PASS）：K1 非 HTTP 绕过残余风险、SQLite 互斥/活性、干净副本安装未重做——均已诚实记录，非数据正确性缺陷。
- 延后项（DEFERRED）：全部链接专属用户入口（D8）+ SQLite BEGIN IMMEDIATE/WAL + K1 选项 B + v2/embed——明确后续批次，**不阻断 A1-03 后端冻结**。

**停止声明**：本审计已完成四份报告 + 26 个证据文件。依 §XIII：
- **未修改任何业务代码**（审计全程只读 + 测试 + 构建 + Git 检查）。
- **未提交本审计报告**——等待后续明确批准。
- **未 push、未进入 A1-04、未修改 MILESTONES.md、未清理历史提交或交付材料**。
- 审计未发现需立即整改的阻断缺陷；若独立复审认定条件项须前置整改，将另行记录证据/根因/影响/最小整改建议并等待阶段审查决定，**不擅自大规模修改代码**。

**现停止，等待 ChatGPT 独立复审与用户批准。本任务目标是结束 A1-03，而非开启下一轮无边界整改。**