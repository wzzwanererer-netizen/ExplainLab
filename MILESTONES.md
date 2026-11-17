# ExplainLab 里程碑

> 状态标记：✅ 已完成 / 🚧 进行中 / ⬜ 未开始。里程碑内容可能随验收反馈调整。

## M0 · 项目初始化与工程规范建立 ✅

**目标**：建立可运行、可测试、可扩展的工程骨架，不开发业务功能。

验收标准（2026-11-12 全部通过）：

- [x] 工作区检查完成，无已有文件被破坏
- [x] 前端工程初始化（React + TS + Vite + Tailwind，React Flow / ELK.js 依赖就绪）
- [x] 后端工程初始化（FastAPI + SQLAlchemy + Alembic + Pydantic）
- [x] Knowledge Core 独立模块骨架（不依赖前端与 Web 框架）
- [x] Model Adapter 统一接口（无具体供应商实现）
- [x] SQLite 配置完成（FTS5 能力实测通过）
- [x] PostgreSQL 连接支持（驱动 + 配置切换，未安装 PG 服务器）
- [x] Alembic 配置完成并实际执行迁移
- [x] 前后端通信打通（Vite proxy + CORS，真实请求验证）
- [x] 健康检查 API（真实数据库探测）
- [x] Git 配置与初始提交
- [x] 项目文档（README / 架构 / 开发指南）
- [x] 基础测试（后端 / Knowledge Core / 前端）全部通过
- [x] 本地启动脚本（setup / dev / test，PowerShell + Bash）

验收证据见 [docs/acceptance/M0-report.md](docs/acceptance/M0-report.md)（含真实运行输出与首页截图）。

## M1 · 对话与知识提取基础 ✅

**目标**：打通真实模型对话与知识提取持久化，建立知识空间数据模型与基本 CRUD。

验收标准（2026-11-13 全部通过）：

- [x] 会话模型与对话 API（接入首个供应商 DeepSeek，通过 Model Adapter，真实回复落库）
- [x] Knowledge Core：知识提取服务实现（LLMExtractionService + KnowledgeService）
- [x] 知识条目持久化（KnowledgeRepository 端口 + SQLAlchemy 实现，来源追溯随条目落库）
- [x] 个人总知识库 / 项目知识空间数据模型与基本 CRUD
- [x] 数据迁移 0002_m1_core（5 张表，无漂移）
- [x] 前端对话视图与知识库视图（真实 API，无假数据）
- [x] 全量测试（Python 80 通过 + 前端 15 通过 + ruff 通过 + 构建通过）
- [x] 真实模型端到端联调（对话 + 提取 2 条知识并落库，来源可追溯）
- [x] API Key 仅存 backend/.env，不进入前端；模型请求直连真实 base_url，无代理替换

验收证据见 [docs/acceptance/M1-report.md](docs/acceptance/M1-report.md)（含真实运行输出、真实模型对话与三视图截图）。

## M2 · 知识关系、去重与审核 ✅

**目标**：在 M1 提取与持久化之上补齐知识治理层——去重、关系推断、版本管理、来源追溯落地、重要变更审核流，治理逻辑全部落在独立 Knowledge Core。

验收标准（2026-11-14 全部通过）：

- [x] 迁移 0003_m2_governance 实跑、无漂移；三张治理表就绪（knowledge_relation / knowledge_version / review_request）
- [x] 去重（词面 char-bigram 召回 + LLM 同一知识判定）与关系推断可用且落库，origin（manual/llm/dedup）可追溯
- [x] 版本 create/list/restore 可用；restore 先建回滚前快照，保留线性历史
- [x] 重要变更按审核矩阵进审核；批准应用、驳回无副作用；merge 闭环（归档 + DUPLICATE_OF + 来源并入，不硬删）
- [x] 来源追溯 attach/trace 落地
- [x] 前端最小界面（详情关系/版本/来源、查重合并、审核队列、202 提示）真实可用
- [x] 全量测试（Python 117 通过 + 前端 27 通过）+ ruff + 构建 + 无漂移通过；Core 独立性守护扩展到 M2 模块
- [x] 真实 DeepSeek 联调（仅 generate，无 embed）：查重 0.98、关系落库、合并闭环、生效编辑门禁
- [x] 联调发现并修复 2 个真实缺陷（合并来源主键冲突；SQLite 外键级联 + 删除批准自毁），均补回归测试

验收证据见 [docs/acceptance/M2-report.md](docs/acceptance/M2-report.md)（含真实运行输出、真实模型治理闭环证据与界面截图）。

## M3 · 跨会话混合检索 ✅

**目标**：在 M2 治理之上提供检索层——SQLite FTS5 全文 + 真实语义向量 + RRF 融合排序，跨会话/跨知识空间检索 API 与前端检索入口，检索编排落在独立 Knowledge Core。

验收标准（2026-11-14 全部通过）：

- [x] 迁移 0004_m3_retrieval 实跑、无漂移；FTS 虚表（trigram）+ 向量表就绪，触发器同步生效
- [x] 中文全文检索（trigram + 短查询 LIKE 回退）与向量检索可用，混合 RRF（k=60）排序正确
- [x] 跨会话/跨空间检索 API 与前端「检索」页签真实可用；space 过滤与 archived 排除正确
- [x] 索引随治理变更同步；backfill（reindex）可用；embed 能力如实上报/降级（not_configured/supported/unsupported）
- [x] 全量测试（Python 149 通过 + 前端 36 通过）+ ruff + 构建 + 无漂移通过；Core 独立性守护扩展到 M3
- [x] 真实 embed 联调（SiliconFlow BAAI/bge-m3，1024 维）：3 条知识建向量，hybrid 双通道命中 + 融合排序，干净 UTF-8 证据
- [x] 向量来源独立 EMBED_* 配置（方案 A），密钥仅 backend/.env，不进入前端；直连真实 base_url 无代理

验收证据见 [docs/acceptance/M3-report.md](docs/acceptance/M3-report.md)（含真实运行输出、真实 embed 双通道证据与检索/系统状态截图）。

## M4 · 动态知识地图 ✅

**目标**：在 M2 关系 / M3 检索之上提供可视化层——Knowledge Core 装配「节点 + 边」图结构，后端只读图 API，前端 React Flow + ELK 自动布局渲染，地图与知识条目 / 关系实时联动。

验收标准（2026-11-15 全部通过）：

- [x] Knowledge Core 图服务（graph/，纯数据装配、无坐标、仅依赖端口）+ RelationRepository.list_all_relations 端口；独立性守护扩展到 M4
- [x] GET /api/graph（space_id 过滤 + include_archived 开关 + 个人空间聚合未归属 + 未知空间 404）；无新增迁移、alembic 无漂移
- [x] 图装配口径：archived 默认不入图、悬空边丢弃、自环跳过、(source,target,type) 去重
- [x] 前端「地图」页签（React Flow + ELK 分层自动布局）：节点 / 边 / 图例 / 计数 / 空间筛选 / 显示归档 / 刷新
- [x] 边视觉语义（related 灰无箭头 / depends_on 蓝 / refines 绿 / duplicate_of 红虚线箭头 / contradicts 红箭头）；归档节点灰显虚线
- [x] 点击节点→治理详情（关系 / 版本 / 来源）；切页签 / 刷新 / 治理变更重取，实时联动实测（改标题→地图同步）
- [x] 全量测试（Python 162 通过 + 前端 52 通过）+ ruff + 构建 + 无漂移通过
- [x] 真实浏览器联调 + 三张验收截图；联调发现并修复 3 个真实缺陷（自定义节点缺 Handle / 窄视口画布塌缩 / 默认白色控件与暗色冲突），均复验

验收证据见 [docs/acceptance/M4-report.md](docs/acceptance/M4-report.md)（含真实图 API 输出、边视觉语义实测与默认 / 含归档 / 详情三张截图）。

## M5 · 交互式知识实验 ✅

**目标**：在 M1 提取 / M2 治理 / M3 检索 / M4 地图之上提供主动学习层——Knowledge Core 编排测验 / 对比 / 学习路径三类实验，经端口持久化，后端实验 API，前端三模式交互 Runner，实验逻辑全部落在独立 Knowledge Core。

验收标准（2026-11-15 全部通过）：

- [x] Knowledge Core experiments（实体 + 端口 + quiz/compare/chain/service）；ExperimentRepository 端口；独立性守护扩展到 M5（TYPE_CHECKING 规避循环导入）
- [x] 迁移 0005_m5_experiments 实跑、无漂移；experiment_session / experiment_attempt 两表（Text JSON、外键级联）
- [x] 测验：模型出题（单选/判断），正确答案与解析服务端持有、作答前不下发；逐题即时判分 + 解析 + 来源；完成汇总得分 + 揭示 + 回顾
- [x] 对比：模型结构化相同点 / 不同点 / 关系判定（可能为空，如实呈现）；已有关系作为提示
- [x] 学习路径：沿依赖 / 细化先修关系确定性 DFS 编排（防环、排序确定、目标在末位），无需模型
- [x] 实验 API（创建/列表/详情/作答/完成/删除）；模型未配置 503 / 调用失败 502 / 参数非法 400 / 资源缺失 404
- [x] 前端「实验」页签：三模式卡片（琥珀/天蓝/翡翠）+ 知识选择 + 数量控制 + 三 Runner + 历史 + 治理详情抽屉（复用 M2）
- [x] 全量测试（Python 218 通过 + 前端 72 通过）+ ruff + 构建 + 无漂移通过
- [x] 真实 DeepSeek 联调：测验 3 题隐藏答案→完成得分 1.0 揭示；对比 2 相同 3 不同 + depends_on 判定；学习路径确定性 2 步；干净 UTF-8 证据
- [x] 真实浏览器联调 + 六张截图（首页/测验作答/得分环/对比/路径/治理抽屉），控制台零错误；完整交互闭环跑通

验收证据见 [docs/acceptance/M5-report.md](docs/acceptance/M5-report.md)（含真实模型实验证据、判分/揭示口径与六张交互截图）。

## M0 准入修复与 M5 回归修复 ✅（2026-11-15，等待独立审计）

**依据**：《ExplainLab M0 独立技术审计报告》（2026-11-15）。**范围**：仅修复/测试/文档同步，**未进入 M1 之后新里程碑**。分支 `fix/m0-admission-and-m5-regressions`，基线 `59068e2`，修复提交 `4557d2e`，M0 初始提交 `2d2b634` 完整保留。

M0 准入项（全部完成并真实验证）：

- [x] M0-01 Alembic 百分号编码 URL（`%`→`%%` 转义，引擎用原始 URL）；`test_alembic_url.py` 6 通过
- [x] M0-02 健康接口脱敏（稳定码 `database_timeout`/`database_unavailable`，日志仅记异常类型）+ `SecretStr`；`test_health.py` 6 通过
- [x] M0-03 Node 22.23.2 基线（engines + README + development.md 一致）
- [x] M0-04 Model Adapter 公共失败契约（可重试/不可重试 + `is_retryable`，STREAM 不虚假声明）；契约 14 + 适配器 15 通过
- [x] M0-05 锁定安装（`uv sync --locked` + `npm ci`）+ 干净副本从零安装验证
- [x] M0-06 新建 `AGENTS.md`；核心 README/`__init__` 抽象接口 vs 具体实现分层同步
- [x] M0-07 配置路径锚定 backend + 空串→None；`test_config.py` 15 通过

M5 回归项（全部完成并真实验证）：

- [x] ZIP-01 PG/SQLite 检索方言适配（PG 原生 tsvector/GIN/触发器/级联，无 FTS5·MATCH·bm25·rowid；CJK ILIKE 回退已记录局限）；**真实 PG 16.8** `test_retrieval_pg.py` 12 通过
- [x] ZIP-02 根级 pytest 收集冲突（importlib + pythonpath，未排除测试目录）；根级 258+12，含 PG 270 通过
- [x] ZIP-03 文档与真实架构同步（architecture/development/README/knowledge-core/AGENTS）
- [x] ZIP-04 前端按需加载（React.lazy + Suspense）；初始 JS 1,937.83→256.45 kB（−86.8%），真实浏览器懒加载实测

**全量证据**：默认根级 258 passed/12 skipped；含真实 PG 270 passed；核心 136 passed；ruff All checks passed；前端 72 passed + 构建初始 256.45 kB/gzip 78.26 kB；干净副本从零锁定安装+测试+构建一致通过。

**结论：本修复批次全部通过**（附已记录局限：PG 中文分词回退、elkjs 懒加载块体积）。验收证据见 [docs/acceptance/M0-M5-REMEDIATION-REPORT.md](docs/acceptance/M0-M5-REMEDIATION-REPORT.md)。**不自行宣布进入 M1，停止等待独立审计。**

### 独立复审专项修复：迁移 0004 历史数据回填 ✅（2026-11-17，等待复审）

**复审发现**：0004 建全文索引表+触发器，但未回填迁移前已存在的 `knowledge_item`，历史知识检索不到（SQLite FTS5 与 PG tsvector 均缺）。

- [x] `fts.py` 新增幂等回填 `FTS_BACKFILL`（rowid 对齐 + NOT EXISTS）/ `PG_FTS_BACKFILL`（tsv 同触发器 + 主键 ON CONFLICT）；`create_fts` 与迁移 0004 upgrade 建索引+触发器后回填
- [x] 重复执行不产生重复索引；downgrade→upgrade 再次回填仍可检索；不破坏 INSERT/UPDATE/DELETE 触发器；不改 Knowledge Core 上层检索接口
- [x] 新增回归：`test_fts_backfill.py`（SQLite 4 用例）+ `test_retrieval_pg.py` 追加 5 用例（真实 PG）——先建记录→再迁移→**不 reindex**→直接检索历史
- [x] 真实运行：SQLite 回填 4 通过；真实 PG 16.8 检索 17 通过；全量含 PG **279 通过**、默认 **262 通过/17 跳过**；ruff 通过

仅改 backend `fts.py`/迁移 0004/两个测试文件，未动前端与 Core，未开发 M1。证据见报告附录 A。**等待独立复审。**

---

## V1.0 完成

七大核心能力全部落地：① 对话自动提取知识 ② 个人总知识库 + 项目空间 ③ 自动去重 / 关系推断 ④ 重要变更审核 ⑤ 跨会话混合检索 ⑥ 动态知识地图 ⑦ 交互式知识实验。Knowledge Core 独立可复用于 Nesti。

## 长期架构约束（所有里程碑必须遵守）

1. Knowledge Core 独立于 ExplainLab 前端，未来复用于 Nesti。
2. 知识提取、关系管理、版本管理、来源追溯、检索不依赖前端页面。
3. 模型供应商只能通过 Model Adapter 接口接入，可替换。
4. API Key 不进入前端。
5. 不以假数据冒充真实功能。