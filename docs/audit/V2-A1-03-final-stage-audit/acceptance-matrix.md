# A1-03 阶段级最终审计 · 验收矩阵

> 结论取值**仅限**：PASS / CONDITIONAL PASS / FAIL / BLOCKED / DEFERRED。
> 每行附：验收编号 / 需求来源 / 源码位置 / 对应测试 / 测试结果 / 实际用户可见能力 / 已知限制 / 最终结论。
> 测试结果均取自 `evidence/` 真实落盘输出（见 test-evidence-index.md）。源码位置经本次审计**逐项亲自核对**，非仅引用测试名。
> 「实际用户可见能力」严格区分 Core/backend 能力与终端用户经 Web 可操作功能（§VIII）。

## 一、A1-01 基础契约（Core 独立性 / 端口边界）

| 编号 | 需求来源 | 源码位置 | 对应测试 | 测试结果 | 实际用户可见能力 | 已知限制 | 结论 |
|---|---|---|---|---|---|---|---|
| F-01 | AGENTS §3/§4 依赖方向 | `ports.py:7-247`（仅 stdlib+entities） | `test_interfaces.py::test_core_has_no_web_framework_dependency` | 14 passed（含本项）exit 0 | 无（架构契约） | 无 | **PASS** |
| F-02 | AGENTS §4 服务 ABC 不可实例化 | `markdown/__init__.py` ABCs；12 服务 | `test_service_is_abstract`×12 | 12 passed | 无 | 无 | **PASS** |
| F-03 | AGENTS §4 端口注入 | `ports.py:216-251` LinkRepository Protocol 8 方法 | 守护 + backend 实现测试 | 全量绿 | 无 | backend 另加 demote 等适配助手（非端口变更） | **PASS** |
| F-04 | A1-01 Nesti 可复用 / 零 Web 依赖 | `markdown/links.py`、`link_service.py` 纯 Python | 干净子进程导入守护 | passed | 无 | 无 | **PASS** |
| F-05 | AGENTS §6 模型失败契约 | `model_adapter/errors.py`（is_retryable 统一） | 全量含契约测试 | 全量绿 | 无 | STREAM 未实现不虚假声明 | **PASS** |
| F-06 | AGENTS §5 方言隔离 | `db/locking.py`、`services/links.py`、`db/fts.py` | PG 全量 1108 | 1108 passed 0 skipped | 无 | PG 无 FTS5/MATCH/bm25/rowid | **PASS** |

## 二、A1-02 基础契约（规范化 / 三 Hash / frontmatter）

| 编号 | 需求来源 | 源码位置 | 对应测试 | 测试结果 | 实际用户可见能力 | 已知限制 | 结论 |
|---|---|---|---|---|---|---|---|
| F-07 | A1-02 canonical 确定性 | `canonical.py:148-158` sha256_canonical | `test_markdown_canonical.py` | 291 passed（三文件合计） | 无（交换底座） | 无 | **PASS** |
| F-08 | A1-02 三 Hash | `markdown/__init__.py:346-452` content/payload/review + 组件 | canonical/codec 测试 | 291 passed | 无 | hashes_comparable 版本门控 | **PASS** |
| F-09 | A1-02 frontmatter 三态 | `codec.py:113-211` NORMAL/CONFLICT | `test_markdown_frontmatter.py` | 291 passed | 无 | 冲突态未解决不宣称无损往返 | **PASS** |
| F-10 | A1-02 未知字段保留 | `codec.py:262-301` _raw 逐字回写 + x_explainlab_ 命名空间 | codec 测试 | 291 passed | 无 | 诊断元键不再生 | **PASS** |
| F-11 | A1-02 冲突处理 / 复杂 YAML 兜底 | `codec.py:176-202,221-253` _frontmatter_raw⟺冲突 | codec/frontmatter 测试 | 291 passed | 无 | 解析失败兜底+告警绝不静默丢数据 | **PASS** |
| F-12 | A1-02 导入导出往返 | `codec.py` parse/dump | codec 测试 | 291 passed | 无 | 冲突态暂存实体不写交换文件 | **PASS** |
| F-13 | A1-03 不破坏 A1-02 Hash 契约 | `links.py:7-9`（Hash 输入仍原始 Unicode） | 冻结 291 + 守护 | 291 passed | 无 | 链接键规范化独立于 Hash | **PASS** |

## 三、A1-03 核心 · wikilink 解析与键派生

| 编号 | 需求来源 | 源码位置 | 对应测试 | 测试结果 | 实际用户可见能力 | 已知限制 | 结论 |
|---|---|---|---|---|---|---|---|
| L-01 | A1-03 wikilink 解析 | `links.py:261-293` WikilinkParser.parse | `test_links.py` T22+ | 110 passed（SQLite）/91（PG） | 无 UI；解析为后端能力 | R7：4 空格代码块/HTML 注释不排除（C-10） | **PASS** |
| L-02 | A1-03 `![[embed]]` 排除 | `links.py:318-329` 排除+warning | T22+ | passed | 无 | D6 嵌入语义延后 A1-04（C-7） | **PASS**（排除已交付，嵌入 DEFERRED） |
| L-03 | A1-03 NFKC+casefold 规范化 | `links.py:70-98` normalize_v1/key_v1 | T22+ | passed | 无 | casefold 非 lower | **PASS** |
| L-04 | A1-03 normalized_link_key + 版本 | `links.py:111-121` LINK_KEY_RULES{1:v1} | T22+ | passed | 无 | v2 未发布（C-6）；未注册版本 ValueError | **PASS** |
| L-05 | A1-03 同键合并 / 提示聚合 | `links.py:186-215` merge_same_key/group_hints | T22+ | passed | 无 | first-occurrence 合并 | **PASS** |
| L-06 | A1-03 控制字符/长度守卫 | `links.py` 键≤1024 标题/别名≤500 Cc 拒绝 | T22+ + DB 约束 | passed | 无 | PG varchar 长度实测一致 | **PASS** |

## 四、A1-03 核心 · 解析 / 绑定优先 / 反链

| 编号 | 需求来源 | 源码位置 | 对应测试 | 测试结果 | 实际用户可见能力 | 已知限制 | 结论 |
|---|---|---|---|---|---|---|---|
| L-07 | A1-03 自动解析三态 | `link_service.py:503-528` 1→RESOLVED/>1→AMBIGUOUS/0→MISSING | T22+ | passed | 无 UI | archived 自动排除（E5/R24） | **PASS** |
| L-08 | A1-03 绑定优先同步 | `link_service.py:583-627` BindingFirstLinkSync | T22+ + K1 | passed | 经治理写自动维护（透明） | 局部守卫 all([])==True 已知边界 | **PASS** |
| L-09 | A1-03 重命名稳定 ID | `link_service.py:835-842` backlinks by target_id | T22+ | passed | 无 | 字面 staleness（C-9） | **PASS** |
| L-10 | A1-03 自链接 / archived / 跨空间 | `link_service.py:411-453,491-501` | T22+ | passed | 无 | archived warning-only（D7）；cross_space 精确等值 | **PASS** |
| L-11 | A1-03 歧义/碰撞处理 | `link_service.py` resolve + plan refused_collision | T22+ + rebuild | passed | 无 | 碰撞整组零写入拒绝 | **PASS** |
| L-12 | A1-03 反链正/反向查询 | `services/links.py:133-147` list_links WHERE source / list_backlinks WHERE target | T22+ | passed | **Web 未渲染反链**（前端零消费者） | 索引查询，无必要全表加载 | **PASS**（后端）/ 用户可见 **DEFERRED** |
| L-13 | A1-03 反链索引（无全表扫描） | PG `ix_target_item_id`；`list_all_links` 仅重建用 | `pg-baseline.txt` \d + T22+ | passed | 无 | list_all_links 全表仅重建独占事务 | **PASS** |
| L-14 | A1-03 D12 读侧防御映射 | `services/links.py:68-94` _to_entity | T22+ | passed | 无 | NULL target+非法组合→missing+False | **PASS** |
| L-15 | A1-03 D12 写侧降级 | `services/links.py:216-234` demote + PG target FK SET NULL | K1 + `pg-baseline.txt` | passed | 无 | 仅治理列，键/版本不变不触发守卫 | **PASS** |

## 五、A1-03 核心 · 导入绑定恢复

| 编号 | 需求来源 | 源码位置 | 对应测试 | 测试结果 | 实际用户可见能力 | 已知限制 | 结论 |
|---|---|---|---|---|---|---|---|
| L-16 | A1-03 导入绑定恢复 | `link_service.py:643-832` LinkImportRestorer.restore | T22+ | passed | 无 UI | 绑定优先 | **PASS** |
| L-17 | A1-03 非法 UUID / 目标不存在 | restore 三类非法处理 | T22+ | passed | 无 | 三类分别处理 | **PASS** |
| L-18 | A1-03 冲突/重复提示保留 | restore conflict preserve-all | T22+ | passed | 无 | 冲突全保留不丢 | **PASS** |
| L-19 | A1-03 跨实例 / cross_space 一致 | restore + resolve cross_space | T22+ | passed | 无 | 解析与恢复 cross_space 同口径 | **PASS** |
| L-20 | A1-03 人工绑定 HTTP 边界 | `link_service.py:541-567` bind_explicit Core-only；`links.py` 零写 | T22+（Core） | passed | **无 HTTP 写入口、无用户绑定 UI** | D8（C-5/E-1） | Core **PASS** / 用户入口 **DEFERRED** |

## 六、A1-03 核心 · 重建 plan / apply 十步

| 编号 | 需求来源 | 源码位置 | 对应测试 | 测试结果 | 实际用户可见能力 | 已知限制 | 结论 |
|---|---|---|---|---|---|---|---|
| R-01 | A1-03 plan() no-op 语义 | `link_service.py:906-1021` snapshots ALL/updates EXCLUDE no-op | T22+ + noop | passed | 无触发 UI | 跨版本重建每行皆 update | **PASS** |
| R-02 | A1-03 门禁 A 全局同构 | `link_service.py:114-130` + `services/links.py:97-101` DISTINCT no-cache | rebuild | passed | 无 | refused_mixed_version | **PASS** |
| R-03 | A1-03 门禁 B 计划内部 | apply 步4 | rebuild | passed | 无 | 无 | **PASS** |
| R-04 | A1-03 门禁 C 新鲜度 | `link_service.py:290-405` 双向 6 字段 + noop_row_requires_update | rebuild + P2 | passed | 无 | row_deleted/added/not_covered/duplicate_id | **PASS** |
| R-05 | A1-03 步7 P2 六字段 | `services/links.py` apply 步7 WHERE 6 字段+rowcount | `p2-*`（8/9） | passed | 无 | rowcount≠1→PostWriteError 回滚 | **PASS** |
| R-06 | A1-03 步8 写后复核 | apply 步8 versions/pairs/governance/items 基线 | rebuild + phantom | passed | 无 | 治理基线全表 id-dict | **PASS** |
| R-07 | A1-03 步8c 逐行快照复核 | `services/links.py:462-502` 单向 snapshot→current | `noop-*`（12/13） | passed | 无 | 单向；ID 集合由步8 保证 | **PASS** |
| R-08 | A1-03 Phantom 非碰撞新增 | 步8 治理基线全表相等 | `phantom-*`（4/6） | passed | 无 | 新增/删除 id 必拒绝 | **PASS** |
| R-09 | A1-03 配对唯一性 | PG `uq_link_source_key`；步8 pairs | `pg-baseline.txt` + rebuild | passed | 无 | UNIQUE(source,key) | **PASS** |
| R-10 | A1-03 整体回滚零写入 | apply 任一步失败→rollback | rebuild + 并发 + phantom | passed | 无 | 无部分更新 | **PASS** |
| R-11 | A1-03 幂等性 | plan no-op + apply 重读 | noop + rebuild | passed | 无 | 同版本重跑 no-op | **PASS** |
| R-12 | A1-03 碰撞整组拒绝 | plan refused_collision all-groups-zero-write | rebuild | passed | 无 | 结构化报告 | **PASS** |
| R-13 | A1-03 重建用户触发 / 碰撞报告查看 | Core/backend 能力已备 | rebuild 测试 | passed | **无 HTTP 触发端点、无前端报告 UI** | E-4 | Core **PASS** / 用户入口 **DEFERRED** |

## 七、K1 治理三入口 × 四动作

| 编号 | 需求来源 | 源码位置 | 对应测试 | 测试结果 | 实际用户可见能力 | 已知限制 | 结论 |
|---|---|---|---|---|---|---|---|
| K1-01 | K1 approve_review 链接维护 | `governance.py:352-375` demote 前/sync 后 commit 前 | `k1-governance-*`（25/11） | passed | 经审核批准自动维护 | 无 | **PASS** |
| K1-02 | K1 submit_review 草稿直改 | `governance.py:245-291` | K1 | passed | 经治理提交自动维护 | 无 | **PASS** |
| K1-03 | K1 restore_version 草稿直改 | `governance.py:183-210` | K1 | passed | 经回滚自动维护 | active 进审核 202 | **PASS** |
| K1-04 | K1 DELETE 先降级后删除 | `governance.py:324-334` delete-flush 前 | K1 | passed | 无 | 仅非重要变更直改时预降级 | **PASS** |
| K1-05 | K1 MERGE 保留归档绑定 | `governance.py:324-334` MERGE 不降级 | K1 | passed | 无 | 重定向语义待决（E-2） | **PASS** |
| K1-06 | K1 409 整审核事务回滚 | `links.py:36-45` + governance commit 前 | K1 | passed | 无 | 稳定码 link_version_mismatch | **PASS** |
| K1-07 | K1 其他写入口绕过核查 | 全部经 governance 路由 | K1 + 源码核对 | passed | 无 | 无其他绕过写入口 | **PASS** |
| K1-08 | K1 非 HTTP 调用方绕过 | Core review 无 hook（grep 零命中） | 源码核对 | — | 无 | **残余架构风险**（C-3/C-4），当前无此类调用方 | **CONDITIONAL PASS** |

## 八、K2 并发与数据库（正确性 / 活性 / 互斥分开）

| 编号 | 维度·方言 | 源码位置 | 对应测试 | 测试结果 | 已知限制 | 结论 |
|---|---|---|---|---|---|---|
| K2-01 | 互斥·PG | `locking.py:41-47` SHARE ROW EXCLUSIVE + FOR UPDATE | `k2-concurrency-pg`（7）+`phantom-pg`（6 真实双连接） | passed | 持锁至提交，阻并发 INSERT/UPDATE/DELETE | **PASS** |
| K2-02 | 正确性·PG | 表锁关闭重读→提交窗口② | K2/phantom PG | passed | 含步8→步9 间隙 | **PASS** |
| K2-03 | 互斥·SQLite | `locking.py:48-52` 读阶段不锁（诚实） | `k2-concurrency-sqlite`（7） | passed | 读阶段无互斥，由乐观兜底 | **CONDITIONAL PASS** |
| K2-04 | 正确性·SQLite | P2+步8c+步8 治理基线三层 | K2/P2/noop/phantom SQLite | passed | 漂移→零写入回滚须重试 | **PASS** |
| K2-05 | 活性·SQLite | `session.py:40` busy_timeout=5000；写阶段 RESERVED | K2 SQLite | passed | BUSY 未消除，降级可重试失败（B-2） | **CONDITIONAL PASS** |
| K2-06 | 锁时序·双方言 | apply 步1b 无条件取锁（含空 updates） | K2/phantom | passed | 仅重建独占事务，不影响常规 CRUD | **PASS** |
| K2-07 | 空+混合 updates·双方言 | plan no-op + apply | noop/phantom 双方言 | passed | 空 updates 亦取锁/复核 | **PASS** |
| K2-08 | BEGIN IMMEDIATE·SQLite | 未启用（C-1） | — | — | 需全局事务管线改动，延后 | **DEFERRED** |
| K2-09 | WAL 多进程·SQLite | 未启用 WAL（C-2） | — | — | 默认 rollback-journal，延后 | **DEFERRED** |
| K2-10 | lock_timeout·PG | 测试每轮重设（事务中止回滚 SET） | phantom-pg 双连接 | passed | 真实双连接验证 | **PASS** |

## 九、API 与前端实际交付边界（§VIII 四层）

| 编号 | 层 | 源码位置 | 核对结果 | 实际用户可见能力 | 结论 |
|---|---|---|---|---|---|
| D-01 | 已交付 HTTP | `links.py:48-95` 3 GET（resolve-candidates/links/backlinks） | 3 只读 GET 真实存在 | 后端可读，**前端无消费者** | **PASS**（后端）|
| D-02 | 已交付 HTTP（写副作用） | `governance.py` approve/submit/restore | 治理写自动维护链接 | 用户经治理操作间接触发（透明） | **PASS** |
| D-03 | Core 有·API 缺 | bind_explicit/reresolve/apply_link_key_plan/碰撞报告 | **无 HTTP 写/触发端点**（D8） | 用户不可操作 | **DEFERRED** |
| D-04 | API 有·前端缺 | 3 link GET | 前端 grep `backlink\|wikilink\|/links\|resolve-candidates\|link_version\|rebuild\|collision\|reparse` **零命中** | 用户不可见 | **DEFERRED** |
| D-05 | 前端可操作 | `KnowledgeDetail.tsx`（仅治理关系 api.listRelations）；`KnowledgeMap`（/api/graph 关系边） | 无链接专属 UI | 反链**未在 Web 展示** | **DEFERRED** |
| D-06 | 易混淆项澄清 | `/search/reindex` + 「重建索引」按钮 | 属**搜索索引**非链接重建 | 用户可见的是搜索重建 | **PASS**（澄清，非链接功能）|
| D-07 | fixture/内部 only | v2 键规则、bind_explicit | 测试夹具/Core 内部 | 非用户功能 | **DEFERRED** |

## 十、质量门禁与工程规范

| 编号 | 需求来源 | 命令/位置 | 测试结果 | 结论 |
|---|---|---|---|---|
| Q-01 | AGENTS §7 ruff | `uv run ruff check` | All checks passed exit 0 | **PASS** |
| Q-02 | AGENTS §7 前端单测 | `npm run test` | 72 passed（10 files）exit 0 | **PASS** |
| Q-03 | AGENTS §7 前端类型 | `npm run typecheck` | exit 0 | **PASS** |
| Q-04 | AGENTS §7 前端构建 | `npm run build` | ✓ 646ms exit 0 | **PASS** |
| Q-05 | AGENTS §7 依赖锁 | `uv lock --check` / `npm ci --dry-run` | 均 exit 0 一致 | **PASS** |
| Q-06 | AGENTS §5 迁移 | `alembic heads` | 单一 head 0006 | **PASS** |
| Q-07 | AGENTS §7 干净副本安装 | 本次未重做（复用现有环境） | 锁一致已核对 | **CONDITIONAL PASS**（不宣称全新安装） |
| Q-08 | AGENTS §8 Git | `git-baseline.txt` | 线性 18 提交/M0 未改写/未 push/工作树干净 | **PASS** |
| Q-09 | 开发库迁移状态 | `alembic current` | 0005（落后 head 一步） | **PASS**（观察项非缺陷，测试库各自至 head） |

## 矩阵汇总

- **PASS**：F-01–F-13、L-01–L-19（后端）、R-01–R-12（后端）、K1-01–K1-07、K2-01/02/04/06/07/10、D-01/02/06、Q-01–Q-06/Q-08/Q-09。
- **CONDITIONAL PASS**：K1-08（非 HTTP 残余风险）、K2-03/05（SQLite 互斥/活性）、Q-07（干净副本未重做）。
- **DEFERRED**：L-12/L-20/R-13 用户入口、D-03/04/05/07、K2-08/09、C 类延后项。
- **FAIL**：无。
- **BLOCKED**：无（环境全部可用，真实 PG 16.8 在线）。