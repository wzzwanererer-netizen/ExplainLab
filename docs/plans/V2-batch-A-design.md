# ExplainLab V2 · 批次 A 技术设计（A1 + A2）

> 文档性质：**技术设计（Design Only）**，不是实现成果，不代表已进入 V2 开发，**不得将设计方案描述为已通过实际测试的功能**。
> 编写：2026-11-17 ｜ 修订：第一/二/三/四轮 ｜ 修订：2026-11-17（**第五轮整改**：GC 持锁 quarantine、跨实例来源身份、租约续租/TOCTOU、GC 状态机含 cancelled、canonicalization_version、Manifest operation_id/generation_id/resource_version 与崩溃对账、Windows 兼容）
> 基线：V1.0 + 回填修复 `6d91718` ｜ 上游：[V2-plan.md](V2-plan.md) ｜ 依赖：[V2-dependency-selection.md](V2-dependency-selection.md)
> 状态：**第五轮设计冻结版（Design Only）；暂不批准 A1/A2 开发；等待独立复审**。本版本为第五轮冻结基线，不再新增业务设计/技术机制。只改设计文档：不写业务代码、不安装依赖、不修改数据库迁移、不改 Core/Backend 实现、不改 lockfile、不提交、不改 V1 功能、不解除 M0/M5 独立复审门禁、不宣布 V2 正式开发启动。

## 标注约定（本轮强制）

每项新增设计按以下之一标注：
- **【事实】**：已确认的技术事实（含 SQLite/PG 引擎行为、V1 代码现状）。
- **【提议】**：本设计提出的方案（尚未实现）。
- **【待审批】**：需用户拍板的决策。
- **【待验证】**：需进入开发后以真实测试验证、当前不得宣称已验证的结论。

---

## 0. 已确认的设计方向

### 0.1 用户初次拍板

1. Markdown 路线 1：DB 权威存储，正文 Markdown，标准 Markdown + YAML Frontmatter 无损导出/重新导入。
2. `[[标题]]` 双向链接，绑定稳定 Knowledge ID，改名不断链。
3. 普通双向链接与语义关系分开建模；图谱统一展示保留不同关系类型。
4. Core 独立：编辑器/React/AI 平台依赖不进 Core。
5. V2 按 A→F，开放 Markdown 知识库优先。
6. 新大型依赖不统一批准，先选型再逐项审批。
7. 仅规划与技术设计。
8. 不提前宣布进入 V2 正式开发。

### 0.2 第一/二/三轮已确认

tags 低风险直改+留痕；active 导入进审核；FTS 索引原文不动触发器/回填；链接与语义关系独立；依赖优先 CodeMirror 6 + react-markdown，KaTeX/PyYAML/DOMPurify/python-magic 暂不批准；react-markdown 禁 raw HTML+URL 校验+安全组件；extra_metadata 保留未知字段；绑定优先同步；语义无损非字节级；stdlib 非通用 YAML 解析器；附件 DB 派生引用数；downgrade 区分 schema/data 须备份；resolve-candidates 路由 `/knowledge/links/resolve-candidates`；active 编辑暂存单一提案；跨实例默认 Draft+status_changes；normalized_link_key 非空唯一；审核提案防覆盖；GC 持久化；Restore Manifest 两阶段；迁移运维包装器门禁。

### 0.3 第四轮复审修订对照表（本轮，含落点）

| # | 问题 | 修订要点 | 落点 |
|---|---|---|---|
| P0-1 | Unicode 链接规范化 | 采用 **NFKC+casefold+空白折叠**【待审批】（修复 NFC 与全角测试矛盾）；分析 NFKC 兼容合并碰撞；原始标题/别名保留；碰撞→ambiguous/显式冲突不随机绑定；**`link_normalization_version`** 版本化；升级/规则变更/重建键流程；双方言测试 | §2.4 / §2.9 / §8 |
| P0-2 | 拆分三种 Hash | **`document_content_hash`**（内容身份）/ **`document_payload_hash`**（完整交换载荷身份）/ **`review_payload_hash`**（审核变更身份）；逐字段覆盖表；内容/治理/交换元数据分类与目标实例再生字段；幂等/跨实例 Draft/时间戳版本/仅元数据变化/active 门禁/确定性序列化/批准前后校验 | §2.6 / §2.7 / §8 |
| P0-3 | SQLite StorageKeyLock 重设计 | 【事实】SQLite 无行级写锁，BEGIN IMMEDIATE 为库级写锁；**租约式逻辑锁 + fencing token + 短事务**，物理操作移出 DB 写事务；区分单/多进程；锁创建/提交/释放/超时/崩溃恢复；租约过期防误释放；PG advisory 分别设计；物理/DB 失败恢复；无法严格跨进程则明确限制与降级 | §2.5 / §10 / §8 |
| P0-4 | GC Worker 租约认领 | gc_task 增 **lease_owner/lease_expires_at/attempts/next_retry_at**；原子认领（PG `FOR UPDATE SKIP LOCKED` / SQLite 短事务条件更新）；双 Worker 仅一成功；崩溃租约过期恢复；旧 Worker fencing 防接管后操作；状态分级（可重试/永久/人工）；多 Worker/崩溃/租约测试 | §2.5 / §10 / §8 |
| P1-5 | PG 备份恢复协议 | **维护模式→Staging DB 恢复→完整校验→业务写入隔离→应用连接切换→附件版本切换→健康检查→完成标记**；Staging 创建/恢复；多实例/连接池/Worker 维护；**连接池重建（非 DATABASE_URL 自动切换）**【事实】；附件版本与 DB 一致；中途回滚；旧资源保留/清理；PG 故障注入 | §6 / §10 / §8 |
| P1-6 | tag_change_log 审计快照 | 增 **item_id（可空 FK）/item_id_snapshot/item_title_snapshot**；普通删除 vs 审计保留；审计保留不丢历史身份；actor/change_source/correlation_id 来源；**审计记录 append-only 不可普通更新覆盖**；删除/查询/保留测试 | §2.2 / §8 |
| 口径 A | Frontmatter 冲突三态 | 正常=语义无损；冲突未解决=原始保留但**不保证实体修改写入交换文件**；显式规范化后=恢复语义无损；**不得称冲突态完全无损往返** | §2.3 |
| 口径 B | 附件孤儿回收兜底 | gc_task 可能随失败事务回滚 → **独立孤儿扫描**（扫物理→对照 DB 引用→识别无引用→安全回收）；排除上传中临时文件/并发上传；安全等待期防误删 | §2.5 |
| 口径 C | tag_change_log 默认审计策略 | 评估 CASCADE vs SET NULL 风险；**推荐审计保留（SET NULL+快照）**+理由；**不替用户最终批准**【待审批】 | §2.2 / §7 |

### 0.4 历轮补充落点索引

Markdown 开放性/保真§2.3；链接§2.4；附件/GC/锁/quarantine/Windows§2.5；三 Hash/序列化/来源身份§2.6；导入审核/治理§2.7；编辑器治理§3.6；依赖§2.12/§3.9/依赖表；兼容§4；备份/Manifest/崩溃对账/Windows§6；迁移§2.9/§5；测试§8；开放项§9；方言/平台差异§10。

### 0.5 第五轮整改对照表（本轮，含落点）

> 第五轮复审指出上传文件仍为第四轮内容、七项整改未落实。本轮在**正文**逐项落实（非仅改日期/对照表）。

| # | 整改 | 修订要点 | 落点 |
|---|---|---|---|
| R5-1 | GC 持锁 quarantine | **禁止释放锁后删原始文件**；改为**持 storage_key 锁期间完成引用复核 + 原子 quarantine 隔离**（锁内 rename 原始→隔离区），释放锁后仅清理隔离区；quarantine 与 purge 分离；崩溃由孤儿扫描兜底 | §2.5.2 / §2.5.3 / §8 |
| R5-2 | 跨实例来源身份持久化 | 新增 **ImportOrigin / item.source_payload_hash + source_instance_id + source_content_hash + imported_at**；幂等比对**持久化的源 payload_hash**（非目标再生后的 payload_hash），解决源身份与目标再生字段冲突 | §2.6.3 / §2.6.2 / §2.7 / §8 |
| R5-3 | SQLite 租约续租/TOCTOU | 增**续租（心跳短事务条件延长 lease_expires_at）+ 续租失败中止 + 旧 Worker 恢复 fencing 保护**；明确 **TOCTOU 风险边界**（复核与不可逆操作间须持续持锁+token 校验；长物理操作期间租约可能被接管→不可保证严格互斥→降级） | §2.5.1 / §10 / §8 |
| R5-4 | GC 状态机统一 | 正式定义 **cancelled**（引用>0 终态不删）及完整状态流转表（pending/running/done/cancelled/failed_retryable/failed_permanent/needs_manual） | §2.5.2 / §8 |
| R5-5 | Hash canonicalization_version | hash 输入包络增 **canonicalization_version**；明确 **datetime（UTC 定格式）/Decimal（定字符串）/null vs 缺失字段/浮点数（禁用或定表示）/列表顺序（语义序排序 vs 保序）** 规则；规则变更 bump 版本重算 | §2.6.1 / §8 |
| R5-6 | Manifest 标识与崩溃对账 | Manifest 增 **operation_id/generation_id/resource_version**；补齐 **Manifest 与真实资源不一致时的崩溃对账**（启动按实际资源版本/校验和核对，不盲信 manifest，回滚旧 generation 或可验证前滚） | §6.3 / §6.7 / §8 |
| R5-7 | Windows 兼容 | 【事实】Windows 文件占用阻塞 rename/delete、os.rename 目标存在失败、symlink 需特权；设计**指针文件替代 symlink、关闭句柄后 os.replace、sharing violation 退避重试、copy+delete 降级（非原子→manifest+孤儿兜底）** | §2.5.4 / §6.8 / §10 / §8 |

---

## 1. 总体设计原则与兼容基石

### 1.1 旧数据零转换无损迁移

- 【事实】`content` 在实体/ORM/DTO/前端均为字符串；纯文本是合法 Markdown，旧正文原样保留即 Markdown，无需转换。
- 提取产出纯文本，A1 不改提取；版本快照/FTS 触发器/向量机制不动（FTS 索引原文，不碰回填/触发器）。
- 数据模型纯增量；旧字段语义与旧行内容不变，新列带默认、新表独立。
- **upgrade 无损**（旧 V1 逐字段不变）；**downgrade 非无损**（删 V2 数据，须先备份，§2.9）。

### 1.2 兼容三原则

- 只增不改不删：现有端点/方法/字段/状态码/审核门禁/索引同步保留；新字段可选带默认；新端点避动态路由冲突。
- Core 纯净：仅 stdlib+Pydantic（+既有 httpx），经端口注入；编辑器/渲染/React/YAML 库/AI SDK 不进 Core。
- 方言中立：标准 SQLAlchemy ORM；业务/Core 不写方言 SQL；**锁/唯一约束/快照/恢复方言差异封装 backend 适配层**（§10）；迁移双方言 up/down。

### 1.3 开放性与保真分层

- 标准 Markdown+YAML Frontmatter 开放交换；未知字段经 extra_metadata 保留不静默丢失。
- **语义无损保证（正常态）；不承诺字节级无损**；冲突态保真降级见 §2.3 口径 A。
- 【事实】stdlib 保守解析器仅覆盖固定已知 schema+简单未知值，**非通用 YAML 解析器，不能完整解析任意 YAML**；复杂值原始文本兜底+告警。

### 1.4 身份与 Hash 分层（第四轮新增）

- **稳定 ID**：KnowledgeItem.id（UUID），跨实例保留。
- **三种 Hash 分离**（§2.6）：内容身份 / 完整交换载荷身份 / 审核变更身份，各自独立、确定性序列化。
- **链接规范化版本**：`link_normalization_version`（§2.4），规则变更可重建。

### 1.5 批次边界

- A1：Core+后端 Markdown 数据模型、稳定 ID、NFKC 规范化链接键/绑定优先/反链/重解析、三 Hash 幂等导入导出、审核提案防覆盖、附件生命周期+租约锁+GC 认领+孤儿扫描、迁移 0006（运维门禁+规范化重建）、API、备份恢复（SQLite/PG 分别协议+Manifest）。
- A2：编辑器（编辑/阅读/分屏+治理暂存+提案撤回）、预览、补全、自动保存/未保存提醒、附件插入、反链侧栏、标签 UI、导入导出 UI（冲突三态交互）。
- 后续批次：分类/验证/来源平台（D）、全局图（C）、导航（B）、外部采集（E）、认证/审计 actor（auth 批次）。

---

## 2. A1 详细设计（Knowledge Core + 后端）

### 2.1 详细任务分解

| 任务 | 内容 | 落点 |
|---|---|---|
| A1-T1 | 实体：KnowledgeItem.tags/extra_metadata；KnowledgeLink（normalized_link_key+**link_normalization_version**+原始字面）；Attachment；TagChangeRecord（actor/source/correlation+**item_id_snapshot/item_title_snapshot**）；GcTask（**lease_owner/lease_expires_at/attempts/next_retry_at**+状态分级）；StorageLease；RestoreManifest | domain/entities.py |
| A1-T2 | 端口：Link/Attachment/Tag/TagChangeLog/GcTask 仓库；MarkdownCodec ABC；**StorageKeyLock 抽象**；Hash 计算（三 Hash） | ports.py、markdown/__init__.py |
| A1-T3 | 编解码：确定性 emitter；未知字段保留+原始兜底+告警；**frontmatter 三态冲突**；语义/字节边界 | markdown/codec.py |
| A1-T4 | 链接：WikilinkParser（代码块/行内/转义/畸形排除）；**NFKC 规范化+碰撞处理+版本化**；LinkResolver；绑定优先同步；Backlink；Reresolve；**键重建** | markdown/links.py |
| A1-T5 | 导入导出：稳定 ID 去重；未知字段保留；target_id 优先恢复；**三 Hash 确定性计算+变化分类**；ImportReport（pending_review/review_ids/unresolved_links/status_changes/conflicts/warnings） | markdown/service.py |
| A1-T6 | 独立性守护扩展 | tests/test_interfaces.py |
| A1-T7 | ORM+迁移 0006：tag/item_tag/knowledge_link(normalized_link_key+version)/attachment/tag_change_log(快照)/gc_task(租约)/storage_lock(租约) + extra_metadata 列；additive 双方言 | models.py、alembic/versions/0006 |
| A1-T8 | 仓库：tags/extra_metadata 映射+绑定优先链接同步+tag append-only 留痕；Link/Attachment/Tag/GcTask 仓库 | services/* |
| A1-T9 | Vault 适配：frontmatter 渲染/保守解析、导出/批量/附件打包、导入、冲突三态 | services/markdown.py |
| A1-T10 | 附件：大小/MIME/清洗/内容寻址/DB 引用数/**StorageKeyLock（SQLite 租约 vs PG advisory）**/**GC 租约认领+重启恢复**/**独立孤儿扫描**/穿越防护 | services/attachments.py、db/storage_lock.py |
| A1-T11 | API：links/backlinks/links/resolve-candidates/resolve/reresolve、export/import(batch)、tags、attachments、reviews/withdraw、**links/rebuild-keys**；旧端点不变 | api/routes/*、schemas.py |
| A1-T12 | 导入审核：active→202；**三 Hash 幂等+每文档事务+部分失败**；**review_payload_hash+proposal_version+异 payload 拒绝+撤回** | services/markdown.py、routes |
| A1-T13 | 备份恢复：**SQLite 协议 + PG Staging 协议** + Manifest 两阶段+完成标记+崩溃回滚+旧资源保留 | services/backup.py（设计） |
| A1-T14 | 迁移运维包装器 + **规范化键重建命令** | scripts/、app/ops/（设计） |
| A1-T15 | 测试：§8 全场景（真实 SQLite+PG） | tests/ |
| A1-T16 | 文档同步（仅文档） | docs/ |

### 2.2 数据模型设计

#### 2.2.1 领域实体（Core，纯 Pydantic，增量）

```python
# 设计示意（非实现代码）
class KnowledgeItem(BaseModel):
    id: UUID; title: str; content: str          # content = Markdown 正文
    status: KnowledgeStatus; space_id: str | None
    source_refs: list[SourceRef]
    tags: list[str] = []
    extra_metadata: dict = {}
    created_at: datetime; updated_at: datetime

class KnowledgeLink(BaseModel):
    id: UUID; source_id: UUID
    target_id: UUID | None                      # 绑定稳定 ID
    target_title: str                           # 原始书写标题（展示，不被规范化覆盖）
    alias: str | None = None                    # 原始别名（展示）
    normalized_link_key: str                    # 非空规范化身份键
    link_normalization_version: int             # 第四轮：规范化规则版本
    resolution: LinkResolution                  # resolved/missing/ambiguous/cross_space/conflict
    cross_space: bool = False
    created_at: datetime; updated_at: datetime

class Attachment(BaseModel):
    id: UUID; item_id: UUID
    filename: str; mime: str; size: int
    storage_key: str; content_hash: str         # 内容 sha256，内容寻址可共享
    created_at: datetime

class TagChangeRecord(BaseModel):               # append-only，不可普通更新覆盖
    id: UUID
    item_id: UUID | None                        # 可空 FK（审计保留 SET NULL）
    item_id_snapshot: UUID                      # 第四轮：删除前稳定 ID 快照
    item_title_snapshot: str                    # 第四轮：删除时标题快照
    old_tags: list[str]; new_tags: list[str]
    actor: str | None; change_source: str | None; correlation_id: str | None
    changed_at: datetime

class GcTask(BaseModel):                        # 第四/五轮：租约认领 + quarantine
    id: UUID; storage_key: str
    status: GcStatus                            # pending/running/done/cancelled/failed_retryable/failed_permanent/needs_manual
    lease_owner: str | None                     # Worker 标识
    lease_expires_at: datetime | None           # 租约到期
    lease_token: int                            # fencing token（单调）
    attempts: int = 0
    next_retry_at: datetime | None = None
    quarantine_path: str | None = None          # 第五轮：持锁隔离后的隔离区路径
    quarantined_at: datetime | None = None
    created_at: datetime; updated_at: datetime

class ImportOrigin(BaseModel):                  # 第五轮 R5-2：跨实例来源身份持久化
    id: UUID; item_id: UUID
    source_payload_hash: str                    # 源 document_payload_hash（不被目标再生覆盖）
    source_content_hash: str                    # 源内容身份
    source_instance_id: str | None
    source_document_id: UUID
    source_canonicalization_version: int
    imported_at: datetime; import_batch_id: str | None
```

> 【提议】链接身份键 = `normalized_link_key`（NFKC 规范化，§2.4），非空；`target_title`/`alias` 保留原始字面展示，**规范化绝不覆盖原文**。
> 【提议】审核提案元数据：`ReviewRequest.payload` 内嵌 `_review_payload_hash` + `_proposal_version`（每 item+action 单调）；`_apply_update` 只读 title/content/status/space_id，忽略下划线元键，不改 V1 review 表结构。
> 【提议】`StorageLease`（storage_key/owner/lease_token/lease_expires_at）与 `RestoreManifest`（§6）为 backend 适配层概念。

#### 2.2.2 持久化表（迁移 0006，additive）

| 表/列 | 关键字段 | 约束/说明 |
|---|---|---|
| knowledge_item.extra_metadata | Text JSON 默认 `{}` | 新增列 |
| knowledge_item.source_payload_hash / source_content_hash / source_instance_id | String(64)/String(64)/String(64) nullable | 第五轮：最新来源身份冗余列（快速判重，权威历史在 import_origin） |
| tag | id PK；name String(100) UNIQUE | 标签字典 |
| item_tag | item_id FK CASCADE；tag_id FK CASCADE；PK(item_id,tag_id) | 多对多 |
| knowledge_link | id PK；source_item_id FK CASCADE；target_item_id FK SET NULL；target_title String(500)；alias nullable；**normalized_link_key String(1024) NOT NULL**；**link_normalization_version Integer NOT NULL**；resolution String(20)；cross_space Boolean；timestamps；**UNIQUE(source_item_id, normalized_link_key)** | 非空键双方言唯一（修复 alias NULL≠NULL）【事实】 |
| attachment | id PK；item_id FK CASCADE；filename/mime/size；storage_key String(64)；content_hash String(64)；index(storage_key) | storage_key 可共享；引用数 COUNT 派生 |
| tag_change_log | id PK；**item_id FK nullable（CASCADE 或 SET NULL 按策略）**；**item_id_snapshot String(36) NOT NULL**；**item_title_snapshot String(500)**；old/new_tags Text JSON；actor/change_source/correlation_id nullable；changed_at | **append-only**；审计快照保身份 |
| gc_task | id PK；storage_key String(64)；status String(24)（含 cancelled）；**lease_owner String(64)**；**lease_expires_at**；**lease_token Integer**；attempts Integer；next_retry_at；**quarantine_path String(512) nullable**；**quarantined_at nullable**；timestamps；index(status,next_retry_at)；index(storage_key) | 租约认领+重启恢复+持锁 quarantine |
| import_origin | id PK；item_id FK CASCADE；**source_payload_hash String(64)**；source_content_hash String(64)；source_instance_id nullable；source_document_id String(36)；source_canonicalization_version Integer；imported_at；import_batch_id nullable；index(item_id)；index(source_payload_hash) | 第五轮：跨实例来源身份持久化（导入历史） |
| storage_lock | storage_key String(64) PK；owner String(64)；**lease_token Integer**；lease_expires_at；locked_at | **SQLite 租约锁表**；PG 用 advisory lock（§10） |

- 【事实】原 `uq(source,target_title,alias)` 因 alias nullable，SQLite/PG 默认 NULL 互不相等 → 唯一失效；改非空 normalized_link_key 修复。
- 【提议】tag_change_log 默认策略见 §7 口径 C（推荐审计保留 SET NULL+快照，待审批）。
- 【提议】方言差异（storage_lock vs advisory、认领、快照、恢复）封装 `app/db/` 适配层；业务/Core 经抽象，不写方言 SQL。

#### 2.2.3 Markdown 交换格式

```markdown
---
id: <稳定 UUID>
title: 知识图谱的定义
tags: [概念, 图谱]
space: personal-null | project-<id>
status: active
version: 3
created_at: 2026-11-17T12:00:00Z
updated_at: 2026-11-17T12:30:00Z
sources: [{type: conversation, conversation_id: ..., uri: ..., excerpt: ...}]
links: [{target_id: ..., title: ..., alias: ..., resolution: resolved}]
custom_field: 任意值            # 未知字段原样保留（extra_metadata）
---
知识图谱是一种网络结构数据模型，参见 [[知识表示]] 与 [[本体论|本体]]。
![](attachments/<storage_key>)
```

### 2.3 Markdown 开放性专节（口径 A：冲突三态）

**未知字段保留**：已知键 `id/title/tags/space/status/version/created_at/updated_at/sources/links` 映射实体；未知键全存 extra_metadata 原样回写；再生 frontmatter 不丢未知字段；降级写 warnings。

**语义无损 vs 字节级无损**：语义无损（正常态保证）；字节级不保证（确定性再生，仅原始兜底片段逐字回写）。

**零依赖保守解析诚实边界**：【事实】stdlib 仅固定已知 schema+简单未知值，非通用 YAML 解析器；复杂值 `_raw`/`_frontmatter_raw` 原始兜底+告警。需结构化理解再审批 PyYAML（暂不批准）。

**Frontmatter 冲突三态（口径 A，第四轮统一）**【提议】

| 状态 | 保证 | 不保证 |
|---|---|---|
| **正常** | 语义无损往返（已知映射+未知保留+正文保真） | 字节级无损 |
| **冲突未解决**（`frontmatter_conflict_requires_resolution`） | **原始数据保留**（原始块+全部未知字段不动） | **不保证实体修改写入交换文件**；**不得称完全无损往返** |
| **用户显式规范化后** | 恢复正常语义无损（已知字段实体再生+未知回写，无重复键） | 字节级无损 |

- 触发：原始块含已知键且与实体冲突、无法安全外科修改 → 置冲突态。
- **不静默生成重复键**：导出器检测原始块含已知键 → 拒绝同时再生该键 → 置冲突态+提示。
- 冲突态：实体已知字段修改**暂存实体不写交换文件**；UI/ImportReport 提示「实体已修改，因 frontmatter 冲突尚未写入交换文件，待解决」。
- 解决（用户主动）：(a) **规范化**→实体再生已知+extra_metadata 回写未知，丢弃原始块（用户授权），清冲突；(b) **保留原始**→已知键以原始为准，实体修改不导出+warning。
- 规范化后导出：确定性再生，无重复键，后续往返语义无损。

**已知/未知冲突规则**：已知键保留命名空间；类型不符→`_conflict`+warnings+冲突态；重复键→取最后值+`_duplicates`+warnings；extra_metadata 已知同名→`x_explainlab_` 前缀+warnings。

### 2.4 双向链接解析专节（P0-1：NFKC 规范化）

**规范化规则（第四轮修订）**

- 【事实】NFC 保留兼容字符（全角 `Ｆｏｏ` 不分解为 `Foo`），故 NFC+casefold **无法**使 `Ｆｏｏ`==`Foo`，与第三轮测试预期矛盾。
- 【待审批】**采用 NFKC + casefold + 空白折叠**（替代 NFC）：
  1. `unicodedata.normalize("NFKC", s)`（兼容分解：全角→半角、合字 ﬁ→fi、圈码等）。
  2. 去首尾空白；内部连续空白折叠为单空格。
  3. `str.casefold()`。
  4. alias 同规范化；空 alias→规范空串 `""`（非 NULL）。
  5. `normalized_link_key = norm(title) + "\x1f" + norm(alias)`，始终非空。
- **NFKC 碰撞分析**【事实+提议】：兼容合并可能使语义不同的标题同键（如 `ﬁle`/`file`、`①`/`1`、`㈱`/`(株)`、全角/半角）。**规范化同键 ≠ 语义同一**。
- **原始保留**【提议】：`target_title`/`alias` 存原始值展示，规范化绝不覆盖原文。
- **碰撞处理**【提议】：
  - 解析时当前空间多个目标标题规范化同键 → **ambiguous，不随机绑定**，提示显式选择。
  - 同源多个 wikilink 书写规范化同键（如 `[[Foo]]` 与 `[[Ｆｏｏ]]`）→ 唯一约束冲突 → 合并为单链接行（保留首现原始字面展示）；若意图指向不同目标 → **conflict 态，显式处理**，不随机绑定。
- **`link_normalization_version`**【提议】：整数版本号（v1=NFKC+casefold+空白折叠）；存于链接行；规则变更→bump 版本。

**解析规则（LinkResolver）**：当前空间优先；唯一→resolved；多同名（含规范化碰撞）→ambiguous 不随机；无匹配→missing 不自动跨项目；用户主动跨空间→cross_space；稳定 ID 改名安全；删除→SET NULL missing 保留快照；reresolve 重试守规则。

**绑定优先同步（按 normalized_link_key 匹配）**【提议】：链接行身份=normalized_link_key；保存时解析正文 wikilink→计算键（排除代码块/行内/转义/畸形）→与既有行按键匹配：键不变且有 target_id→**保留绑定不重解析**；键不变未解析→维持；新键→解析；删键→删行。仅链接本身变化或用户主动才解析。

**导入 target_id 优先恢复**：frontmatter target_id 存在→校验目标存在→直接恢复绑定；缺失/无效/跨实例不存在→回退标题解析+unresolved_links。

**规范化版本升级 / 键重建（第四轮新增）**【提议+待验证】

- 旧数据升级：0006 增 normalized_link_key+version 列；回填按当前版本从原始 title/alias 计算键（additive）。
- 规则变更：bump `link_normalization_version` → **重建命令**（运维包装器，§2.9）从原始字面重算所有键；**绑定优先：target_id 保留，仅重算键**；重建产生的碰撞→ambiguous/conflict 报告，**不随机重绑定**。
- 重建期间冻结链接写入；重建后校验唯一约束；旧版本键留痕供回滚。

**书写边界**：`[[标题]]`/`[[标题|别名]]`；排除围栏代码块/行内代码/转义 `\[[`/畸形（未闭合/空/嵌套/超长，可记 warnings）；别名变化视为键变化。

**API**：GET links/backlinks；GET links/resolve-candidates；POST links/resolve；POST links/reresolve；**POST links/rebuild-keys（运维，重建规范化键）**。

### 2.5 附件生命周期专节（P0-3 锁 / P0-4 GC / 口径 B 孤儿）

**基础安全**：大小上限（默认 10MB 可配，超限 413/400+warnings）；MIME 白名单+magic bytes 双校验（SVG 禁内联或消毒）；文件名清洗（仅显示名）；路径穿越防护（storage_key 由 hash 派生，规范化校验落存储根内，拒 `..`/绝对路径/逃逸符号链接，下载按 id 查 key）。

**存储与引用数**：storage_key=内容 sha256（内容寻址，物理唯一不可变，存储根 `backend/data/attachments/` hash 前缀分片）；attachment.id 行唯一，storage_key 可共享；**引用数=COUNT(attachment WHERE storage_key=?)（DB 派生权威，无独立计数器）**。

#### 2.5.1 StorageKeyLock 重设计（P0-3）

- 【事实】**SQLite 不支持行级写锁**；`BEGIN IMMEDIATE` 取得**数据库级写锁**（整库），并非 storage_key 级行锁。
- 【事实】**仅 Python 进程内 Lock 不能宣称跨进程安全**（多进程各自独立内存锁）。
- 【提议】**租约式逻辑锁 + fencing token + 短事务**（SQLite）：
  - **锁记录**：`storage_lock(storage_key PK, owner, lease_token, lease_expires_at)`。
  - **获取**：**短事务**条件写入——`INSERT` 新锁行，或 `UPDATE ... WHERE storage_key=? AND lease_expires_at<now`（过期接管）；PK/唯一保证仅一 owner；分配单调 `lease_token`；**立即 commit 释放库级写锁**。
  - **持有**：逻辑租约期间执行物理文件操作（**在 DB 写事务之外**，避免长事务持库锁做文件 IO）。
  - **释放**：**短事务** `DELETE/UPDATE WHERE storage_key=? AND owner=? AND lease_token=?`（**fencing：token 匹配才释放**）；commit。
  - **续租（第五轮 R5-3）**【提议】：长物理操作期间 Worker 周期性**心跳续租**——短事务 `UPDATE storage_lock SET lease_expires_at=now+lease_ttl WHERE storage_key=? AND owner=? AND lease_token=?`；rowcount==1 续租成功，==0 表示已被接管/释放。续租与释放/接管同样受 fencing token 约束。
  - **续租失败处理**【提议】：续租 rowcount==0（租约过期被新 owner 接管，token 失配）→ **立即中止当前物理操作**，不得继续不可逆步骤；已完成的 quarantine 隔离由新 owner/孤儿扫描接管处理；记录 abort 原因。
  - **旧 Worker 恢复保护**【提议】：崩溃后旧 Worker 恢复运行时，**每个不可逆物理步骤前重新校验 owner==self 且 lease_token 匹配**（读锁行）；失配→放弃任务（已被新 Worker 接管），不重复操作；GC 任务侧另以 gc_task.lease_token fencing（§2.5.2）。
  - **超时/崩溃恢复**：lease_expires_at 到期 → 他人可条件接管（新 token）；崩溃残留锁靠租约过期回收。
  - **防误释放**【提议】：租约过期被新 owner 接管（新 token）后，旧 owner 的释放/物理操作因 **token 不匹配而失败/中止**（fencing），不得继续操作已被接管的资源。
  - **单进程 vs 多进程**【提议】：单进程可用进程内 per-key mutex 作优化 + DB 租约保持久/崩溃恢复；**多进程必须依赖 DB 租约**，进程内锁单独不构成跨进程安全。
  - **限制与降级**【待验证】：租约式逻辑锁非严格行级锁；正确性依赖 fencing+短事务+租约过期。**若无法实现严格跨进程锁语义，明确降级**：推荐单写者部署，或粗粒度库级写锁串行化（短事务），**不得宣称已实现完全并发安全**。
  - **TOCTOU 风险边界（第五轮 R5-3）**【事实+提议+待验证】：
    - 【事实】租约锁是**逻辑租约**而非内核强制互斥；在「引用复核」与「不可逆物理操作（quarantine/purge）」之间，若租约到期被他人接管，存在 **time-of-check-to-time-of-use 窗口**：复核时引用==0，执行时可能已有新上传引用该 key。
    - 【提议】收敛手段：① 引用复核与 quarantine rename **尽量在同一持锁短临界区内连续完成**，缩短窗口；② 不可逆步骤前**即时重验 lease_token**（fencing），失配即中止；③ **quarantine 而非直接 delete**——隔离后原始路径不再持有文件，新上传同 key 会重新写入物理文件，隔离区文件经安全等待期+再次引用复核才 purge，使 TOCTOU 误判可恢复（§2.5.2）；④ 续租心跳降低操作中途过期概率。
    - **诚实限制**【待验证】：上述手段**降低而非消除** TOCTOU；租约式逻辑锁**无法保证长物理操作期间的严格跨进程互斥**。若业务要求严格互斥，**降级为单写者部署**或**库级写锁串行化全部附件物理操作**（牺牲并发）。**不得宣称已消除 TOCTOU 或已实现完全并发安全。**
- 【提议】**PostgreSQL**：`pg_advisory_lock(hashtext(storage_key))` **会话级**咨询锁（跨物理操作持有，显式 `pg_advisory_unlock`；会话结束/崩溃自动释放）；或事务级 `pg_advisory_xact_lock` 仅用于 DB 临界区。与 SQLite 租约分别设计（§10）。
- **物理/DB 失败恢复**【提议】：先写物理（temp+原子 rename）→短事务插 DB 行；DB 失败→物理成孤儿→**独立孤儿扫描**回收（口径 B，不依赖失败事务内 gc_task）；物理失败→不插 DB 行。

#### 2.5.2 GC Worker 租约与认领（P0-4）

- 【提议】gc_task 增 `lease_owner/lease_expires_at/lease_token/attempts/next_retry_at`；**统一状态机（第五轮 R5-4）**：`pending/running/done/cancelled/failed_retryable/failed_permanent/needs_manual`（正式纳入 **cancelled**）。
- **原子认领**：
  - 【提议】**PG**：`SELECT ... FOR UPDATE SKIP LOCKED` 选候选 → 同事务 `UPDATE` 置 running+lease_owner+lease_expires_at+lease_token+attempts+1 → 仅一 Worker 成功。
  - 【提议】**SQLite**：**短事务条件更新** `UPDATE gc_task SET status='running', lease_owner=?, lease_expires_at=?, lease_token=lease_token+1, attempts=attempts+1 WHERE id=? AND (status='pending' OR (status='running' AND lease_expires_at<now))`；**rowcount==1 才算认领成功**（库级写锁串行化条件更新）；rowcount==0→他人已认领。
- **双 Worker 同任务**：条件更新/SKIP LOCKED 保证仅一成功。
- **崩溃恢复**：lease_expires_at 过期 → 任务可被他人条件认领。
- **旧 Worker 防接管后操作**【提议】：每个不可逆物理步骤前**校验 lease_owner==self 且 lease_token 匹配**（fencing，含 storage_lock 与 gc_task 双重）；不匹配→中止（任务已被新 Worker 接管）；续租失败同样中止（§2.5.1）。

**GC 状态机（第五轮 R5-4 统一定义）**【提议】

| 状态 | 含义 | 终态 | 主要流转 |
|---|---|---|---|
| pending | 待认领 | 否 | →running（原子认领） |
| running | 已认领持租约执行中 | 否 | →done / →cancelled / →failed_retryable / →failed_permanent / →needs_manual；租约过期可被他人重新认领（→running，新 token） |
| **cancelled** | **持锁复核发现引用>0，放弃回收**（第五轮正式定义） | **是** | 终态，不删任何文件；可由后续引用归零的新 gc_task 重新发起 |
| done | quarantine+purge 成功完成 | 是 | 终态 |
| failed_retryable | 瞬时失败（attempts<max） | 否 | 置 next_retry_at 退避→到期回 pending 重认领 |
| failed_permanent | attempts≥max 或不可重试错误 | 是（待人工） | →needs_manual（人工分诊） |
| needs_manual | 歧义/损坏/需人工 | 否（人工挂起） | 人工→pending（重置重试）或→cancelled（放弃） |

- 流转约束：状态变更走**短事务条件更新**（带 lease_token fencing）；终态 done/cancelled 不可被普通更新覆盖；failed_retryable→pending 由 next_retry_at 到期触发；重启不直接将 running 置 pending，而是**靠租约过期条件认领**（§2.5.2 原子认领）。

**GC 流程（第五轮 R5-1：持锁 quarantine，禁止释放锁后删原始文件）**【提议+待验证】

1. **原子认领** gc_task（置 running+lease_owner+lease_expires_at+lease_token+attempts+1）。
2. **获取 storage_key 租约锁**（§2.5.1），开始心跳续租。
3. **持锁期间**短事务**重算引用数**（COUNT attachment WHERE storage_key）。
4. **引用>0** → 短事务置 **cancelled**（终态）→ 释放锁 → **不删任何文件**。
5. **引用==0** → **仍在持锁期间**执行**原子 quarantine 隔离**：将原始文件 `rename` 到隔离区 `attachments/_quarantine/<storage_key>.<operation_id>`（同卷原子 rename；Windows 兼容见 §2.5.4）；**quarantine 成功 = 原始路径不再持有该文件**（新上传同 key 会重新写入原始路径）。
6. quarantine 成功后短事务**记录 `quarantine_path`/`quarantined_at`（status 仍 running，不新增枚举）**→ **释放锁**。
7. **purge 阶段（释放锁之后，仅针对隔离区文件）**：安全等待期（mtime 阈值）后，**再次持锁复核引用==0 + fencing 校验** → 删除**隔离区文件**（非原始文件）→ 短事务置 **done**。
8. **关键约束**：**原始文件的移除（quarantine rename）必须在持锁+引用复核临界区内完成；释放锁后只允许清理隔离区，绝不直接删除原始路径文件**。purge 前若引用回升（新上传）→ 将隔离区文件**恢复回原始路径**（rename 回）或放弃 purge 置 cancelled，保证不丢仍被引用内容。
9. **崩溃恢复**：quarantine 后崩溃 → 隔离区残留文件由**独立孤儿扫描**（§2.5.3）识别（无引用+超等待期）安全 purge；原始路径若已空且 DB 无引用→一致；若 DB 有引用而原始缺失→孤儿扫描/恢复流程从隔离区找回。
10. 失败分级：瞬时错误→failed_retryable+退避；不可重试/attempts≥max→failed_permanent→needs_manual；引用复核歧义→needs_manual。

#### 2.5.3 独立孤儿扫描兜底（口径 B，第四轮新增）

- 【事实/提议】DB 事务失败后在该事务内创建的 gc_task **会随事务回滚**，不可靠 → 需要**独立于 gc_task 的孤儿扫描**作为正确性兜底。
- 【提议】**周期孤儿扫描**：
  1. 扫描物理存储目录文件（storage_key 命名）**及隔离区 `attachments/_quarantine/`**（第五轮 R5-1：quarantine 残留）。
  2. 对照 DB 引用（attachment.storage_key 集合）。
  3. 识别无引用物理文件 → 孤儿候选；**隔离区文件**：核对对应 gc_task 状态与 quarantine_path，无引用且超等待期→purge；若 DB 仍有引用而原始路径缺失→**从隔离区恢复回原始路径**（不丢内容）。
  4. **安全等待期**：文件 mtime 早于阈值（如 >N 分钟）**且**非活跃上传临时文件 → 才入回收（防误删上传中文件）。
  5. **排除上传中临时文件**（temp 命名模式/活跃上传登记）与并发上传（持 storage_key 锁复核引用）。
  6. 进入安全回收（**持锁→重算引用==0→fencing→quarantine 隔离→等待期后 purge 隔离区**，与 §2.5.2 同机制，**不释放锁后删原始文件**）；可生成 gc_task 但**不依赖其存在**。
- gc_task 为优化/可观测，孤儿扫描为正确性兜底；两者均持锁复核引用+quarantine 隔离，绝不删仍被引用文件。

#### 2.5.4 附件物理操作平台兼容（第五轮 R5-7：Windows）

- 【事实】**Windows 文件语义与 POSIX 不同**：
  - 被打开句柄占用的文件**无法 rename/delete**（sharing violation，`ERROR_SHARING_VIOLATION`/`ERROR_LOCK_VIOLATION`）；杀软/索引器/预览可能短暂占用。
  - `os.rename` 在**目标已存在时失败**（POSIX 可原子覆盖）；原子覆盖须用 `os.replace`，但**目标被占用时仍失败**。
  - **符号链接需特权**（`SeCreateSymbolicLinkPrivilege` 或开发者模式）；普通用户进程**不能依赖 symlink** 做目录切换。
  - 目录被任一打开句柄占用时**目录 rename 失败**；跨卷 rename 非原子（实为 copy+delete）。
- 【提议】**兼容设计**：
  - **quarantine/上传 rename 同卷**：隔离区与存储根同一卷，保证 rename 原子性；避免跨卷。
  - **先关闭句柄再 rename**：物理操作前确保本进程已关闭文件句柄；下载/serve 使用短打开+及时关闭，避免长占用。
  - **原子覆盖用 `os.replace`**（非 `os.rename`）；目标存在场景统一 replace。
  - **sharing violation 退避重试**：捕获占用错误→指数退避重试（上限 N 次）；仍失败→记 failed_retryable，交孤儿扫描/人工，**不强删**。
  - **目录/版本切换不用 symlink**：改用**指针文件**（DB/配置记录当前附件版本目录，§6.8），切换=更新指针+fsync，规避 Windows symlink 特权问题。
  - **rename 被阻塞的降级**：极端占用下若必须切换，**copy+delete 降级**（**非原子**）→ 以 Manifest（§6）+孤儿扫描兜底一致性，**明确标注非原子降级，不得宣称原子**。
- 【待验证】Windows 占用/rename/权限行为需真实 Windows 环境测试；Linux/macOS 与 Windows 差异封装 backend 适配层（§10）。**不得宣称跨平台原子切换已验证。**

### 2.6 API 与三 Hash 设计（P0-2）

| 方法/路径 | 用途 |
|---|---|
| GET /knowledge/{id}/links、/backlinks | 出链/反链 |
| GET /knowledge/links/resolve-candidates | 解析候选（避 {item_id} 冲突） |
| POST /knowledge/{id}/links/resolve、/reresolve | 主动选定/重解析 |
| POST /knowledge/links/rebuild-keys | 规范化键重建（运维） |
| GET /knowledge/{id}/markdown | 单条导出（含 conflict_state） |
| POST /knowledge/export、/import、/import/batch | 导出/导入 |
| GET /tags、/knowledge?tag=、/knowledge/{id}/tag-changes | 标签 |
| POST /knowledge/{id}/attachments、GET/DELETE /attachments/{id} | 附件 |
| POST /reviews/{id}/withdraw | 撤回提案 |

**路由**：resolve-candidates 三段 `/knowledge/links/resolve-candidates` 不匹配 `{item_id}`/`{item_id}/links`；export/import POST 与 {item_id} GET/PATCH/DELETE 不冲突；静态字面先于动态声明。

#### 2.6.1 三种 Hash 定义（第四轮核心）【提议】

| Hash | 身份 | 覆盖字段 | 用途 |
|---|---|---|---|
| **document_content_hash** | 知识**内容**身份 | `title` + `content`（正文） | 内容去重/内容变更判定；**排除**治理状态与易变交换元数据 |
| **document_payload_hash** | **完整交换载荷**身份 | 全部交换字段：id/title/content/tags/space/status/version/timestamps/sources/links/attachments(清单+content_hash)/extra_metadata | 精确文档身份/完全相同导入幂等；**含易变字段，独立身份** |
| **review_payload_hash** | **实际审核变更**身份 | 提交审核的变更 payload：`title?/content?/status?/space_id?`（实际应用字段） | 提案身份/防覆盖/批准==应用校验 |

**字段分类与目标实例再生**

| 字段 | 类别 | content_hash | payload_hash | review_hash | 目标实例再生 |
|---|---|---|---|---|---|
| content 正文 | 内容 | ✓ | ✓ | ✓(若变更) | 否 |
| title | 内容 | ✓ | ✓ | ✓(若变更) | 否 |
| tags | 交换元数据(组织) | ✗ | ✓ | ✗(低风险直改) | 否 |
| space | 交换元数据(实例本地) | ✗ | ✓(源空间标识) | ✓(若变更) | 是(跨实例可重映射) |
| status | 治理状态 | ✗ | ✓(源状态) | ✗ | **是(跨实例默认 draft)** |
| version | 治理状态 | ✗ | ✓ | ✗ | 是(目标版本序列) |
| timestamps | 交换元数据(易变) | ✗ | ✓ | ✗ | 是(目标导入时间) |
| sources | 交换元数据(溯源) | ✗ | ✓ | ✗ | 否(保留) |
| links | 交换元数据(派生) | ✗ | ✓ | ✗ | 部分(target_id 跨实例可失效) |
| attachments | 交换元数据(清单+hash) | ✗ | ✓ | ✗ | 否(内容寻址) |
| extra_metadata | 交换元数据(未知) | ✗ | ✓ | ✗ | 否(保留) |
| id | 稳定身份 | ✗(独立身份键) | ✓ | ✗(item_id 另传) | 否(保留) |

> 【提议】content_hash 仅 title+content（纯内容身份，与 id 解耦，利于同内容去重）；payload_hash 是**完整载荷独立身份**（含 version/timestamps/status），**不得仅靠排除易变字段定义**；review_hash 仅实际应用变更字段（tags 不入审核）。

**确定性序列化与组件 Hash 关系（第五轮 R5-5 强化）**【提议+待验证】

- **canonicalization_version**：hash 输入包络显式携带 `canonicalization_version`（整数，初值 v1【待审批】），即 `canonical_doc = {"canonicalization_version": 1, ...字段}`；**序列化规则变更→bump 版本→重算 hash**；不同版本 hash 不可直接比较，升级须重算并留痕（与 link_normalization_version 独立）。
- **canonical JSON 基础**：`sort_keys=True`、`ensure_ascii=False`、固定 separators（`, ` / `: ` 或紧凑，定其一【待审批】）、UTF-8 编码后 SHA-256。
- **类型规范化规则（第五轮逐项明确）**【提议】：
  - **datetime**：统一转 **UTC**，固定 ISO-8601 格式 `YYYY-MM-DDTHH:MM:SS.ffffffZ`（**固定微秒 6 位**，无时区偏移歧义）；naive 时间视为 UTC【待审批】；禁止本地时区/可变精度进入 hash。
  - **Decimal**：转**定字符串表示**（`format(d, 'f')` 去尾零规范化【待审批】），**不经 float**（避免精度丢失）；保留原始精度语义。
  - **浮点数 float**：**hash 输入禁用裸 float**【提议】；如必须，转 Decimal 定表示或固定 rounding（如 17 位有效数字 repr）【待审批】；避免平台 repr 差异。
  - **null vs 缺失字段**：**区分**【提议】——canonical 仅序列化**实际存在的字段**；显式 `null` 保留为 `null`，**缺失字段不补 null**（缺失≠null，二者 hash 不同）；导入/导出须保持字段存在性一致【待验证】。
  - **列表顺序**：**语义序列表排序**——links 按 normalized_link_key、attachments 按 content_hash、tags 按 casefold 名、sources 按稳定键排序；**顺序敏感列表**（如版本序列）保留原序并标注；排序键含次级键保证全序（避免相等键不稳定）。
  - **Unicode**：hash 输入用**原始值**（不做 NFKC/casefold），保证身份稳定；规范化仅用于链接键（§2.4），不污染 hash【待审批确认】。
- `document_payload_hash = SHA256(canonical(完整交换文档, canonicalization_version))`（**独立整体身份**）。
- `document_content_hash = SHA256(canonical({title, content}, canonicalization_version))`。
- `review_payload_hash = SHA256(canonical(变更 payload, canonicalization_version))`。
- 组件 Hash（tags_hash/links_hash/extra_meta_hash/attachments_hash/governance_hash）由对应子集 canonical 计算，**仅用于变化分类**；payload_hash 非组件简单拼接，而是整体序列化哈希。
- 同文档多次计算字节一致（确定性）；**规则变更前后 hash 变化由 canonicalization_version 标识**【待验证】。

#### 2.6.2 幂等与变化分类（第四轮统一）

| 情形 | 判定 | 行为 |
|---|---|---|
| **同一文档重复导入** | 入站源 document_payload_hash == **持久化 source_payload_hash**（§2.6.3） | `skipped`（无新条目/新审核单） |
| **跨实例导入默认 Draft** | 源 payload_hash 不变；目标 status/version/timestamps 再生 | status_changes 提示；**重导同一文件→比对持久化源 payload_hash（非目标再生 payload_hash）→skipped**（§2.6.3） |
| **时间戳/版本变化** | content_hash 不变；payload_hash 变 | 交换元数据变化，**非内容变更**，不触发内容审核 |
| 仅 tags 变化 | content_hash 同；payload 异 | 低风险直改+tag_change_log |
| 仅 extra_metadata 变化 | content_hash 同；payload 异 | 低风险元数据直改+留痕 |
| 仅 title 变化 | **content_hash 异** | draft 直改 / **active 经 UPDATE_ITEM 审核** |
| 仅 links 变化（正文同） | content_hash 同；payload 异 | 绑定优先链接恢复/重解析（非内容审核） |
| 正文变化 | content_hash 异 | draft 直改 / **active 审核** |
| 附件变化 | attachments_hash 异 | 附件生命周期（非内容审核） |
| 无 id 导入 | document_content_hash 查重 | duplicates 提示，不静默覆盖 |

- **事务边界**：每文档独立事务；单文档失败记 errors 继续，不回滚其他；批量非全有全无。
- **并发导入同 id**：按 item 串行（行锁/唯一约束），避免重复 create。
- **active 审核门禁**：内容变更（content_hash 异）经 ReviewService→202（§2.7）。

#### 2.6.3 跨实例导入来源身份持久化（第五轮 R5-2）【提议+待验证】

**问题**：第四轮以「源 document_payload_hash 相等」判幂等，但目标实例会再生 status/version/timestamps（甚至 space 重映射），导致**目标自身重新计算的 payload_hash ≠ 源 payload_hash**；若用目标再生后的 hash 判重，跨实例重导同一文件会误判为「变化」→重复建单/重复导入。

**方案：持久化来源身份，幂等比对源 hash 而非目标再生 hash**

- 【提议】新增 **ImportOrigin** 持久化模型（或在 knowledge_item 增来源列），记录**导入时的源身份**，与目标再生字段解耦：

| 字段 | 含义 |
|---|---|
| item_id | 目标条目稳定 ID（FK） |
| **source_payload_hash** | **导入时源文档的 document_payload_hash**（源实例 canonicalization_version 下计算，原样持久化，**不被目标再生覆盖**） |
| **source_content_hash** | 源 document_content_hash（内容身份，跨实例稳定） |
| **source_instance_id** | 源实例标识（导出方 instance id；无则 null/unknown） |
| source_document_id | 源文档 id（通常==item_id，跨实例保留） |
| source_canonicalization_version | 源 hash 所用 canonicalization_version（版本不同时不可直接比 hash，须重算或标注） |
| imported_at | 本次导入时间（目标本地） |
| import_batch_id | 导入批次（correlation） |

- **幂等判定（修订）**：入站文件计算源 payload_hash → 与目标条目**持久化的 source_payload_hash** 比对（同 source_canonicalization_version 前提下）：
  - 相等 → **skipped**（即使目标 status/version/timestamps 已再生变化，也不误判）。
  - 不等 → 按 §2.6.2 变化分类处理；处理后**更新 source_payload_hash 为新的源 hash**（记录最新来源身份）。
- **目标再生字段不影响幂等**：status/version/timestamps/space 的目标再生**只改变目标自身 payload_hash，不改变持久化 source_payload_hash**；二者明确分离。
- **canonicalization_version 不一致**：源与目标版本不同→hash 不可直接比→以 source_content_hash（内容身份）+ 字段级比对降级判定，或标注「需重算」【待审批】。
- **无来源记录的历史条目**：首次导入补建 ImportOrigin；之前已存在但无来源记录→以 content_hash 查重 + 提示，不静默覆盖。
- **持久化位置**【待审批】：独立 import_origin 表（一对多历史）vs knowledge_item 来源列（仅最新）；推荐独立表保留导入历史，item 列冗余最新 source_payload_hash 便于快速判重。
- 【待验证】跨实例重导幂等、源 hash 与目标再生解耦、版本不一致降级，均需真实测试。

### 2.7 导入审核与治理状态（含 review_payload_hash 防覆盖）

**ImportReport**：created/updated/skipped/duplicates/errors/pending_review/review_ids/unresolved_links/status_changes/conflicts/warnings。

**审核行为**：新建直建 draft；草稿直改；active 内容变更经 submit(UPDATE_ITEM)→202，记 pending_review/review_ids，批准后应用；tags 任意状态直改+留痕；无 id 查重不静默覆盖。

**审核提案防覆盖（第三/四轮）**【提议】

- 每提案 `_review_payload_hash`（canonical 变更 payload SHA-256）+ `_proposal_version`（每 item+action 单调），存 payload 元键（不改 V1 review 表）。
- submit：算 review_payload_hash → 查同 item+action pending：
  - **hash 相同**→复用 pending（幂等）。
  - **hash 不同**→**不得覆盖**→**409 拒绝**「已有不同内容待审核提案，请先撤回或处理」。
  - 无 pending→建新提案 proposal_version=max+1。
- 提案 payload 创建后不可就地编辑；新内容须**显式 withdraw→新建**（`POST /reviews/{id}/withdraw`→WITHDRAWN【待审批：新枚举 vs REJECTED+note】→新 proposal_version+新 hash）。
- **批准==应用**【提议+待验证】：approve 应用该 review id 存储 payload 原文；应用前重算 review_payload_hash 与存储 `_review_payload_hash` 比对，**不一致中止**；保证审核人批准内容==最终应用内容。
- 并发提交同 item+action 串行（行锁）。

**编解码无损 vs 治理状态**：编解码无损=content/frontmatter/未知字段/链接（语义无损，正常态）；治理状态（status/审核历史/版本）实例本地不属编解码无损；**跨实例默认 Draft**+status_changes+warnings 明确「原 active→导入 draft」，**不宣称治理状态完全无损**；同实例重导入自身导出可恢复 status 但 active 更新仍走审核。

### 2.8 模块依赖关系

```
frontend(A2) ──HTTP /api──▶ backend ──Python import──▶ knowledge-core
```

- Core（纯）：entities←markdown/{codec,links,service}←ports；stdlib+Pydantic+ports；NFKC 规范化/绑定优先 diff/三 Hash/ImportReport/冲突三态在 Core；不依赖 backend/SQLAlchemy/FastAPI/React/YAML 库/编辑器/AI SDK。
- backend：models+迁移 0006；services/* + db/storage_lock（方言锁/认领适配）+ ops（迁移包装器/键重建）；api/routes+DTO。backend→core 严禁反向。
- I/O/方言边界：文件系统、附件存储/锁/GC、frontmatter 切分、HTTP、备份恢复、DB 事务/锁、advisory lock、连接池切换全在 backend 适配层；Core 纯文档/链接/编排，可被 Nesti 复用。
- 复用既有 Repository/sync_index/ReviewService/VersionService；不改 retrieval 方言/FTS 触发器/回填/extraction。

### 2.9 迁移兼容与回滚门禁（含规范化重建）

**升级（无损）**：0006 新建 tag/item_tag/knowledge_link(normalized_link_key+version)/attachment/tag_change_log(快照)/gc_task(租约)/storage_lock(租约) + extra_metadata 列；旧列/旧表不动；回填按当前规范化版本计算键（additive）；旧 V1 数据无损；FTS/向量不重算。

**回滚两类**：Schema Rollback（downgrade 删 V2 表/列，**丢 V2 数据非无损**）；Data Rollback（依赖备份）。

**迁移执行门禁（第三/四轮）**【提议】

- 【事实/提议】**Alembic 0006 downgrade() 只管 Schema 变更，不承担交互/备份**。
- **运维包装器/独立命令**（`python -m app.ops.v2_downgrade`）：① 备份 DB+附件（§6）② 校验备份 ③ 用户确认（告知删 V2 数据）④ 记录 migration_ops_log（备份位置/校验结果/from-to 版本/执行时间/操作者/确认）⑤ **门禁：备份未完成/校验未过/未确认→拒绝破坏性 downgrade** ⑥ 通过→alembic downgrade→后置检查。
- **规范化键重建命令**（`app.ops.rebuild_link_keys`）：规则变更 bump version→冻结链接写入→从原始字面重算键→绑定优先（target_id 保留）→碰撞报告 ambiguous/conflict 不随机重绑→校验唯一约束→旧版本键留痕。
- 附件物理回滚：downgrade 前备份物理；之后孤儿 GC/归档。
- 精确口径：V1 核心数据 downgrade 后不变；V2 数据除非备份否则丢失；不宣称删表列无损。

### 2.10 测试用例（A1）

> 第四轮必补场景集中见 §8；常规覆盖：语义无损往返（正常态）/冲突三态往返；NFKC 规范化+碰撞+版本重建；绑定优先连续；三 Hash 确定性+变化分类；提案防覆盖+批准 hash 校验；附件锁/GC 认领/孤儿扫描；备份恢复故障注入；迁移门禁；旧 API 回归；ruff+根级 pytest 保留 importlib；真实 SQLite+PG（门控）。

### 2.11 验收标准（A1）

- [ ] 旧 V1 upgrade 逐字段无损（SQLite+PG）；旧 API 兼容；resolve-candidates 无冲突。
- [ ] Markdown 正常态语义无损往返，未知字段不丢；不宣称字节级无损；**冲突态不称完全无损**。
- [ ] **NFKC 规范化**（全角/半角同键）+碰撞 ambiguous/conflict 不随机+原始保留+**link_normalization_version 升级重建**；双方言唯一约束测试。
- [ ] 链接当前空间优先/同名不随机/不自动跨项目/主动跨空间/改名不断链/删除保留未解析/reresolve；绑定优先连续；导入 target_id 优先。
- [ ] **三 Hash 分离**（content/payload/review）字段覆盖正确；payload 完整独立身份；完全相同/跨实例 Draft/时间戳版本/仅元数据/active 门禁分类正确；确定性序列化；批准前后 hash 一致。
- [ ] 提案防覆盖：同 hash 复用/异 hash 拒绝/撤回新建/批准==应用。
- [ ] 附件：**SQLite 租约锁（短事务+fencing+续租+续租失败中止+单/多进程限制+TOCTOU 边界与降级）/PG advisory**；**GC 持锁引用复核+原子 quarantine（禁止释放锁后删原始）+释放锁后仅 purge 隔离区+引用回升恢复**；**GC 状态机含 cancelled**；租约原子认领+双 Worker 仅一+崩溃恢复+旧 Worker fencing；**独立孤儿扫描（含隔离区+安全等待期+排除临时/并发）**；DB 引用数；穿越防护；**Windows 占用/rename/os.replace/指针切换兼容**。
- [ ] **跨实例来源身份持久化（ImportOrigin/source_payload_hash）**：幂等比对源 hash 而非目标再生 hash；canonicalization_version 不一致降级。
- [ ] **三 Hash canonicalization_version + 序列化规则**（datetime/Decimal/null/缺失/float/列表序）确定性；规则变更 bump 重算。
- [ ] frontmatter 三态：不静默重复键/确认前保留原始+未知/实体未写提示/规范化后恢复语义无损。
- [ ] ImportReport 全字段（status_changes/conflicts）；active 进 202 不绕过；每文档事务+部分失败；跨实例默认 Draft+提示。
- [ ] **tag_change_log append-only+审计快照**（item_id_snapshot/title_snapshot）；普通删除 vs 审计保留；actor/source/correlation 来源。
- [ ] FTS 索引原文不动触发器/回填。
- [ ] 迁移运维包装器门禁（Alembic 纯 Schema；备份→校验→确认→记录→才 downgrade）；规范化重建命令。
- [ ] **备份恢复：SQLite 协议 + PG Staging 协议（连接池重建非 URL 自动切换）+ Manifest（operation_id/generation_id/resource_version）两阶段+完成标记+崩溃回滚+旧资源保留+Manifest 与真实资源不一致对账（不盲信标记）+Windows 指针切换/非原子降级**；故障注入。
- [ ] Core 独立性守护；无编辑器/React/YAML 库/AI SDK；stdlib 非通用 YAML 声明；A1 零新增必需依赖。
- [ ] 真实测试（非假数据/非离线 SQL）；ruff+根级 pytest 通过。
- [ ] 对应 PRD §15 #2/#3/#12。

### 2.12 新增依赖清单（A1）

| 依赖 | 用途 | 状态 |
|---|---|---|
| 无（Core stdlib + 既有 SQLAlchemy/psycopg/Alembic/FastAPI） | A1 全部（含租约锁/GC/三 Hash/Manifest/PG staging） | **零新增必需依赖** |
| ~~PyYAML~~ | 复杂 frontmatter 结构化 | 暂不批准；原始兜底；stdlib 非通用解析器 |

---

## 3. A2 详细设计（前端）

### 3.1 任务分解

| 任务 | 内容 |
|---|---|
| A2-T1 | 类型：tags/extra_metadata、KnowledgeLink(normalized_link_key/version)、Attachment、ImportReport(status_changes/conflicts)、TagChange(快照/actor/source)、Review(review_payload_hash/proposal_version)、三 Hash 字段 |
| A2-T2 | client：links/backlinks/resolve-candidates/resolve/reresolve/rebuild-keys、export/import(batch)、tags/tag-changes、attachments、reviews/withdraw；旧方法不变 |
| A2-T3 | 编辑器（CodeMirror 6 待批准）：编辑模式、wikilink/标签补全、工具栏 |
| A2-T4 | 预览（react-markdown 待批准）：阅读模式、禁 raw HTML、URL 校验、安全组件 |
| A2-T5 | 模式切换：编辑/阅读/分屏 |
| A2-T6 | 反链侧栏 |
| A2-T7 | 治理保存：Draft debounce；Active 暂存+明确提交一单；异 payload 提示撤回→新建；dirty 守卫 |
| A2-T8 | 附件插入（预检+拖拽/粘贴） |
| A2-T9 | 标签 UI（编辑/补全/过滤/修改记录 actor/source） |
| A2-T10 | 导入导出 UI：ImportReport 全字段；**frontmatter 冲突三态交互（规范化/保留原始）**；跨实例 status_changes 提示 |
| A2-T11 | KnowledgeView 渐进改造（保留旧能力） |
| A2-T12 | 懒加载（ZIP-04） |
| A2-T13 | 测试：Vitest+typecheck+build+真实浏览器联调 |

### 3.2 状态 / 3.3 API 消费 / 3.4 依赖 / 3.5 兼容

- 状态：content/tags/模式/保存状态/dirty/active 暂存 buffer+待提交提案+review_payload_hash/补全候选/未解析提示/**frontmatter 冲突三态**。
- API：复用 A1（含 rebuild-keys/withdraw）；updateKnowledge 返回 MutationResult（202→审核提示）；导入展示 ImportReport 全字段+冲突解决交互+跨实例 status_changes；异内容 pending→引导撤回→新建。
- 依赖：编辑/渲染库仅前端，React.lazy+Suspense；Core/backend 不引入。
- 兼容：类型/client 增量容错（`?? []`/`?? {}`）；旧方法签名不变；旧纯文本原样渲染；typecheck+build；懒加载不退化。

### 3.6 编辑器体验与治理

- 完整体验：编辑/阅读/分屏；wikilink `[[` 补全（当前空间候选，同名/规范化碰撞歧义提示）；标签补全；附件插入；反链侧栏；未保存提醒。
- 治理保存：

| 状态 | 行为 |
|---|---|
| Draft | debounce 自动保存（PATCH 直改）；状态指示 |
| Active 编辑期间 | 仅本地暂存，不自动保存后端、不每 debounce 建单 |
| Active 明确提交 | 一份完整 submit(UPDATE_ITEM,payload)→一个 pending（202，带 review_payload_hash/proposal_version）；多次修改合并一单 |
| 已有不同内容 pending | 不覆盖→提示→显式 withdraw→新建；同 payload 复用 |
| 批准后统一更新 | approve（hash 校验批准==应用）→统一同步链接（绑定优先）+sync_index+版本；tags 直改+留痕 |

### 3.7 测试 / 3.8 验收 / 3.9 依赖

- 测试：补全/模式/预览/react-markdown 安全（raw HTML 不渲染、危险 URL 拦截、组件安全）/wikilink 跳转/反链/治理保存状态机（含异 payload 撤回新建）/未保存守卫/附件插入/TagEditor/ImportExport 全字段/**冲突三态交互**/KnowledgeView 不退化；typecheck+build+包体积；真实浏览器联调（in-app Browser bringToFront；fullPage 超时→viewport+重试；urllib UTF-8）：编辑/阅读/分屏、补全跳转改名不断链歧义跨空间反链 reresolve、active 暂存→提交→异内容撤回→新建→批准统一更新、导出导入一致+审核提示+跨实例 status_changes+冲突解决、标签/附件、自动保存/未保存、多视口无溢出（PRD#1）、控制台零错误。
- 验收：三模式+实时预览（PRD#2）；补全+跳转+改名不断链+歧义+跨空间+反链+reresolve（PRD#3）；治理保存+异 payload 撤回新建+批准统一更新；附件/标签；ImportReport 全字段+冲突三态交互；react-markdown 安全；旧能力不退化；无溢出；Vitest+typecheck+build+懒加载；真实浏览器证据；编辑/渲染库仅前端。
- 依赖：CodeMirror 6 / react-markdown 待逐项批准（核对版本 MIT）；DOMPurify 重评暂不批准；KaTeX 暂不批准。

---

## 4. 旧版 API 兼容策略

只增不改不删。现有端点路径/方法/字段/状态码/审核门禁/索引同步不变；新能力走新端点/可选字段（避动态路由冲突）。GET/POST/PATCH/DELETE /knowledge、extract、relations/versions/restore/sources/reviews/duplicates/analyze、search/reindex、graph、实验/空间/会话/健康全兼容。口径：tags 低风险直改+留痕；active 导入进审核（202 不绕过）；FTS 索引原文不动触发器/回填；链接与语义关系独立。

---

## 5. 旧数据无损迁移方案

1. 零内容转换（纯文本⊂Markdown）。2. 纯增量 schema。3. 旧机制不动。4. 未知字段保真。5. **升级无损/降级有损**（经运维包装器备份→校验→确认→记录→才执行；不宣称删表列无损）。6. 真实断言（0005→0006 逐字段+检索不变；门禁；SQLite+PG）。7. 前端容错。8. 导出兜底（旧知识批量导出标准 .md 带稳定 ID/来源）。9. 备份恢复保障（§6）。10. **规范化键回填/重建**（§2.4/§2.9，绑定优先，碰撞不随机）。

---

## 6. 备份恢复专节（P1-5：SQLite/PG 分别协议）

### 6.1 一致性快照

- **SQLite（WAL）**【事实+提议】：Online Backup API（`sqlite3.Connection.backup()`）或 `VACUUM INTO` 一致快照（**禁裸拷 db+wal+shm**）；integrity_check。
- **PostgreSQL**【事实+提议】：`pg_dump`（MVCC 单事务一致快照，--format=custom）或 pg_basebackup；真实实例。

### 6.2 同一时间点 DB+附件备份

冻结写入+GC（维护窗口）→DB 快照→复制快照引用附件物理+hash 清单→记录备份元数据（时间戳/快照标识/附件版本/清单）。附件内容寻址不可变，冻结窗口内一致。

### 6.3 Restore Manifest 与两阶段切换（通用框架）

- 【事实】DB 与附件目录是**两个独立资源**，**不能宣称跨资源原子切换**；以 Manifest+两阶段+完成标记+旧资源保留+崩溃回滚实现**崩溃一致**（非字面原子）。
- **Restore Manifest**（持久化于被切换资源之外，fsync；第五轮 R5-6 增标识字段）：
  - **operation_id**：本次恢复操作唯一 ID（UUID，幂等重驱标识）。
  - **generation_id**：资源世代单调标识（每次成功切换 +1；旧/新资源各属一个 generation）。
  - **resource_version**：`{db_snapshot_version, attachment_version, canonicalization_version}`（DB 快照与附件版本绑定，确保一致）。
  - backup_id/db_snapshot_path/attachment_manifest/target 位置/old 资源保留路径（含 old generation_id）/phase(prepared|switching_db|switching_attachments|committed|rolled_back)/completion_marker/checksums/timestamps。
- 两阶段：Phase1 准备（恢复到临时/staging+校验+manifest prepared fsync，记录 operation_id/generation_id/resource_version）；Phase2 切换（冻结写→切换 DB→切换附件版本→写完成标记 fsync，bump generation_id）。
- **旧资源保留至完成标记持久化前绝不删除**；崩溃/断电/中途重启按 manifest phase + **真实资源对账**（§6.7）回滚旧 generation（无标记）或完成（有标记且对账一致）。
- 旧资源清理：仅 phase=committed+标记 fsync+**真实资源对账一致**+保留策略满足后。

### 6.4 SQLite 恢复协议【提议】

维护模式（暂停写入/GC/Worker）→恢复 DB 到临时文件+附件到临时目录→完整校验（integrity/hash/引用/逐字段）→业务写入隔离→**关闭句柄后 `os.replace` 临时 DB 入位 + 附件版本指针切换（不用 symlink，§6.8）**→健康检查→完成标记（manifest resource_version/generation_id）→（保留窗口+对账一致后）清理旧资源。中途失败：标记前回滚旧资源（切回旧 DB/旧指针），临时丢弃；Windows 占用退避重试/非原子降级见 §6.8。

### 6.5 PostgreSQL 恢复协议（P1-5，第四轮新增）【提议+待验证】

> 【事实】**修改 DATABASE_URL 不会使现有连接自动切换**；已建立连接仍连旧库。必须重建连接池。

完整流程：

1. **维护模式**：所有应用实例进入维护（共享维护标志/编排器），暂停摄入/后台 Worker/GC，**排空连接池**，停止写入。
2. **Staging Database 恢复**：`createdb explainlab_staging_<ts>`（或 `pg_restore --create`）→ `pg_restore` 备份入 staging；**不触碰生产库**。
3. **完整校验**：staging 上 integrity/引用/逐字段/hash 比对备份；附件版本与 DB 快照一致（manifest 绑定）。
4. **业务写入隔离**：确认所有实例/池/Worker 已停写（多实例协调）。
5. **应用连接切换**：**建立指向 staging/恢复库的新连接池（新 engine）→排空/关闭旧池→切换应用数据源引用→以新连接重启 Worker**；**非 DATABASE_URL 修改自动切换**【事实】。
6. **附件版本切换**：附件目录版本化（`attachments/<version>/`），**通过指针文件/DB 记录切换当前版本（不用 symlink，规避 Windows 特权问题，§6.8）**；与 DB 版本一致（manifest resource_version 绑定）。
7. **健康检查**：新池连通/读写探针/引用一致/附件可下载。
8. **完成标记**：manifest committed+marker fsync。
- **中途失败回滚**：标记前旧 DB+旧附件版本保留 → 回滚=应用切回旧池/旧附件版本，staging 丢弃；多实例逐一回滚。
- **旧资源保留/清理**：标记前保留旧库+旧附件版本；标记后+健康检查+保留策略满足才清理 staging/旧资源。
- **多实例连接切换**：编排器协调所有实例池重建；不得假设单实例。

### 6.6 中途失败与故障注入测试

备份中途失败（清单不全/hash 不符判废，正式 intact）；恢复临时/staging 校验中途失败（正式不动）；**切换到一半程序终止**（kill 于 switching_db/switching_attachments/标记前→重启回滚旧资源；标记后→完成）；断电 fsync 顺序；**PG 恢复中途失败 + 多应用实例连接切换**；哈希去重共享；迁移前后演练。SQLite+PG（门控）。

### 6.7 Manifest 与真实资源不一致的崩溃对账（第五轮 R5-6）【提议+待验证】

**问题**：manifest 的 phase/completion_marker 可能与真实资源状态不一致——例如标记已写但附件版本切换未完成、DB 已切但 manifest 未更新、断电导致 manifest 落后/超前于实际资源。**不能盲信 manifest 单一记录**。

**启动对账流程**【提议】：

1. **读取 manifest**（operation_id/generation_id/resource_version/phase/checksums）。
2. **探测真实资源**：当前 DB 实际快照版本/校验和、当前附件指针版本/清单校验和、连接池实际指向。
3. **三方比对**（manifest 记录 vs DB 实际 vs 附件实际）：

| 情形 | 判定 | 处置 |
|---|---|---|
| manifest=committed 且 DB/附件实际==resource_version 且校验和一致 | 切换成功 | 确认完成；保留窗口后清理旧 generation |
| manifest=committed 但**实际资源不一致**（附件版本落后/DB 校验不符） | **标记超前于实际** | **不盲信标记**→回滚到 old generation（旧 DB+旧附件指针）或**可验证前滚**（仅当缺失步骤可幂等补全且校验通过）；记录不一致告警 |
| manifest=switching_* 无标记 | 切换中途崩溃 | 回滚 old generation；丢弃 staging/临时 |
| manifest=prepared | 未开始切换 | 正式资源 intact；清理临时 |
| manifest 缺失/损坏但资源已部分切换 | 记录丢失 | 以**真实资源探测+备份元数据**重建判定；无法确定→保守回滚旧资源+人工介入（needs_manual） |

4. **幂等重驱**：以 operation_id 保证同一恢复操作重驱不重复副作用；generation_id 单调防止回退到错误世代。
5. **前滚条件**【待验证】：仅当剩余步骤可幂等执行且 resource_version 校验和可达成时才前滚；否则一律回滚旧 generation。**不得在资源不一致时宣称恢复成功。**
6. **fsync 顺序**：先 fsync 资源切换→再 fsync manifest phase→最后 fsync completion_marker；保证标记不会超前于持久化资源（降低而非消除不一致，仍需对账）。

### 6.8 备份恢复平台兼容（第五轮 R5-7：Windows）【事实+提议+待验证】

- 【事实】Windows 下：被占用文件/目录无法 rename；`os.rename` 目标存在失败（须 `os.replace`）；**symlink 需特权**；跨卷 rename 非原子。
- 【提议】**附件版本切换用指针文件而非 symlink**：当前版本记录于 DB/配置指针（`attachment_root_pointer`），切换=原子更新指针+fsync；各版本目录 `attachments/<version>/` 并存；读取按指针解析。规避 Windows symlink 特权与目录占用 rename 问题。
- 【提议】**DB 文件切换（SQLite）**：切换前**关闭所有连接/句柄**（排空池）→`os.replace` 临时 DB 入位；占用导致失败→退避重试→仍失败则保持旧 DB+标记 switching 失败回滚，**不强切**。
- 【提议】**降级**：rename 被长期阻塞时 copy+delete（**非原子**）→Manifest+对账（§6.7）+孤儿扫描兜底；**明确标注非原子降级**。
- 【待验证】Windows 占用/rename/指针切换/多实例需真实 Windows 测试；平台差异封装 backend 适配层（§10）。**不得宣称跨平台原子切换已验证。**

---

## 7. 待批准 / 待确认决策点（第五轮更新）

**已确认方向**：见 §0.1/0.2/0.3/0.5。

**待用户审批**：

1. **NFKC 规范化采用**（替代 NFC）+ 碰撞 ambiguous/conflict 口径 + link_normalization_version 初值与重建策略。
2. **三 Hash 字段覆盖**（content=title+content；payload 含易变字段独立身份；review 仅应用字段）+ timestamps/version 排除 content_hash 但纳入 payload_hash 口径。
3. **SQLite 租约锁方案**（短事务+fencing+单/多进程限制+降级）；是否接受「非严格行级锁、租约式正确性」；PG advisory 会话级 vs 事务级。
4. **GC 认领与状态分级**（PG SKIP LOCKED / SQLite 条件更新；failed_retryable/permanent/needs_manual；租约时长/重试上限）。
5. **PG 恢复协议**（staging 命名/连接池重建/多实例编排/附件版本化/保留策略）。
6. **tag_change_log 默认审计策略（口径 C）**：【提议】**推荐审计保留（SET NULL+item_id_snapshot/item_title_snapshot，append-only）**，理由：治理/审计价值，删除不丢历史身份；风险：孤儿行累积需保留/清理策略、查询用快照。**CASCADE 风险**：删除即丢审计 trail。**最终批准权属用户，本轮不替用户拍板**。
7. **actor/change_source/correlation_id 来源**：actor=认证用户（auth 批次）/auth 前 local-user/system/import；change_source=manual_edit/import/api/merge；correlation_id=导入批次/审核单/请求 id。
8. **WITHDRAWN 枚举** vs REJECTED+note 替代。
9. 依赖逐项审批：CodeMirror 6 / react-markdown（核对版本 LICENSE+安全方案）；DOMPurify 是否确需。
10. 附件上限/MIME 白名单/SVG 策略；storage_key=sha256；存储根。
11. frontmatter 冲突三态 UI（规范化/保留原始，批量导入冲突逐条 vs 默认）。
12. 批量导入事务/幂等/并发口径；跨实例默认 Draft+status_changes。
13. 备份位置/保留份数；迁移包装器形态/migration_ops_log 字段。
14. **门禁**：M0/M5 回填修复独立复审通过后，是否批准启动 A1。
15. **（R5-1）GC quarantine 机制**：隔离区位置/命名、purge 安全等待期、quarantine 后引用回升的恢复策略；是否接受「持锁 quarantine + 释放锁后仅清隔离区」。
16. **（R5-2）来源身份持久化形态**：独立 import_origin 表 vs item 来源列；source_instance_id 来源（导出方如何标识实例）；canonicalization_version 不一致时的降级判定。
17. **（R5-3）租约参数与 TOCTOU 降级**：lease_ttl/续租心跳间隔/重试上限；是否接受 TOCTOU「降低而非消除」并要求严格互斥时降级单写者/库级串行。
18. **（R5-4）GC 状态机**：cancelled 终态语义、failed_permanent→needs_manual 人工流程、needs_manual 重置规则。
19. **（R5-5）canonicalization_version 与序列化细则**：初值、separators 紧凑/可读、datetime 微秒精度与 naive=UTC、Decimal 去尾零、float 禁用/定表示、null vs 缺失字段区分、列表排序键。
20. **（R5-6）Manifest 标识与对账**：operation_id/generation_id/resource_version 生成与持久化；不一致时前滚 vs 回滚判定阈值；manifest 损坏保守策略。
21. **（R5-7）Windows 兼容策略**：指针文件替代 symlink、os.replace+退避重试参数、copy+delete 非原子降级的接受度；目标部署平台（Windows/Linux）确认。

---

## 8. 测试场景清单（第四/五轮必补，集中）

> 均为**设计级测试计划**，【待验证】——进入开发后以真实 SQLite+PG（及 Windows 平台）执行，当前不得宣称已通过。

### 8.1 第四轮场景

| 场景 | 覆盖要点 | 落点 |
|---|---|---|
| NFKC/NFC 规范化碰撞 | `Ｆｏｏ`/`Foo`、`ﬁle`/`file`、`①`/`1` 同键；碰撞→ambiguous/conflict 不随机；原始字面保留 | §2.4 |
| 规范化版本升级 | bump version→重建键→target_id 保留→碰撞报告→唯一约束校验 | §2.4/§2.9 |
| 内容 Hash 与 Payload Hash 分离 | content_hash 仅 title+content；payload_hash 含 version/timestamps/status 独立身份；时间戳/版本变→content 不变 payload 变 | §2.6 |
| 跨实例 Draft 导入幂等 | 源 payload_hash 不变→重导 skipped；status_changes 提示；目标 status 再生 | §2.6/§2.7 |
| 仅 tags/title/links/extra_metadata 变化 | 分类正确（tags/extra 直改、title 内容审核、links 绑定恢复） | §2.6 |
| 多进程 SQLite 锁竞争 | 两进程同 storage_key 租约仅一获取；进程内锁单独不跨进程安全 | §2.5/§10 |
| SQLite 锁超时与进程崩溃 | 租约过期接管（新 token）；崩溃残留锁回收；旧 owner fencing 防误释放 | §2.5 |
| PG advisory lock 并发 | 同 key 会话级锁互斥；崩溃会话自动释放 | §2.5/§10 |
| 两个 GC Worker 同时认领 | 条件更新/SKIP LOCKED 仅一 rowcount==1 | §2.5 |
| Worker 租约过期与旧 Worker 恢复 | 过期可接管；旧 Worker fencing 校验失败中止 | §2.5 |
| 上传与 GC 并发交错 | 同 key 锁互斥；GC 获锁重算引用>0 取消；上传先→GC 不删 | §2.5 |
| DB 事务失败后附件孤儿扫描 | gc_task 随事务回滚→独立孤儿扫描识别无引用物理→安全等待期+排除临时/并发→回收 | §2.5 口径 B |
| PG 恢复中途失败 | kill 于 staging 校验/池切换/附件切换/标记前→回滚旧资源 | §6.5 |
| 多应用实例连接切换 | 多实例池重建协调；非 DATABASE_URL 自动切换 | §6.5 |
| 审计记录删除后身份保留 | 审计模式删条目→item_id_snapshot/title_snapshot 留存→按快照查历史；append-only 不可覆盖；普通删除 CASCADE | §2.2 |
| Frontmatter 冲突解决前后往返 | 冲突态原始保留+实体未写+不称完全无损；规范化后恢复语义无损无重复键 | §2.3 |
| 唯一约束双方言 | 同源同 normalized_link_key 重复插入拒绝（含 NULL alias）；SQLite+PG | §2.2 |
| 提案防覆盖 | 同 hash 复用/异 hash 409/撤回新建/批准 hash==应用 | §2.7 |
| 备份中途失败/切换中途终止 | 判废/回滚旧资源/标记后完成 | §6 |

### 8.2 第五轮新增场景（R5，全部【待验证】）

| 场景 | 覆盖要点 | 落点 |
|---|---|---|
| GC 持锁引用复核→cancelled | 持 storage_key 锁复核引用>0→置 cancelled 终态→不删任何文件 | §2.5.2 R5-1/R5-4 |
| GC 持锁原子 quarantine | 引用==0 时**锁内** rename 原始→隔离区；原始路径不再持有文件 | §2.5.2 R5-1 |
| 禁止释放锁后删原始 | 释放锁后仅 purge 隔离区；断言原始文件移除发生在持锁临界区内 | §2.5.2 R5-1 |
| quarantine 后引用回升恢复 | purge 前再复核引用>0→隔离区文件恢复回原始路径/置 cancelled，不丢内容 | §2.5.2 R5-1 |
| quarantine 后崩溃孤儿清理 | 隔离区残留→孤儿扫描识别无引用+超等待期→安全 purge；DB 有引用而原始缺失→从隔离区找回 | §2.5.3 R5-1 |
| 跨实例重导幂等（来源身份） | 目标 status/version/timestamps 再生后重导同一文件→比对持久化 source_payload_hash→skipped | §2.6.3 R5-2 |
| 源 hash 与目标再生解耦 | 目标自身 payload_hash 变化不影响 source_payload_hash；幂等不误判 | §2.6.3 R5-2 |
| canonicalization_version 不一致降级 | 源/目标版本不同→content_hash+字段级降级判定/标注需重算 | §2.6.3 R5-2/R5-5 |
| 无来源记录历史条目补建 | 首次导入补建 ImportOrigin；无记录条目 content_hash 查重不静默覆盖 | §2.6.3 R5-2 |
| SQLite 租约续租成功 | 心跳短事务条件延长 lease_expires_at（owner+token 匹配）rowcount==1 | §2.5.1 R5-3 |
| 续租失败中止 | 租约被接管→续租 rowcount==0→立即中止物理操作，不执行不可逆步骤 | §2.5.1 R5-3 |
| 旧 Worker 恢复 fencing | 崩溃恢复后每不可逆步骤前重验 owner+token；失配放弃任务不重复操作 | §2.5.1/§2.5.2 R5-3 |
| TOCTOU 窗口可恢复 | 复核==0 后新上传引用同 key→quarantine 隔离使新上传重写原始→隔离区等待期复核恢复，不丢内容；验证「降低而非消除」 | §2.5.1 R5-3 |
| GC cancelled 终态流转 | cancelled 不可被普通更新覆盖；引用归零后新 gc_task 重新发起 | §2.5.2 R5-4 |
| 失败分级流转 | failed_retryable→next_retry_at 到期回 pending；failed_permanent→needs_manual；人工重置 | §2.5.2 R5-4 |
| canonical datetime 确定性 | UTC 固定微秒格式；naive=UTC；本地时区/变精度不入 hash；多次计算字节一致 | §2.6.1 R5-5 |
| Decimal/float/null/缺失/列表序 | Decimal 定字符串不经 float；float 禁用/定表示；null≠缺失字段；语义序列表排序稳定 | §2.6.1 R5-5 |
| canonicalization_version bump | 规则变更 bump 版本→hash 重算→不同版本不可直接比 | §2.6.1 R5-5 |
| Manifest operation_id 幂等重驱 | 同一 operation_id 重驱不重复副作用 | §6.7 R5-6 |
| Manifest 与资源不一致对账 | committed 但附件版本落后/DB 校验不符→不盲信标记→回滚旧 generation 或可验证前滚 | §6.7 R5-6 |
| manifest 损坏保守恢复 | manifest 缺失/损坏但资源部分切换→真实探测+备份元数据重建→无法确定保守回滚+人工 | §6.7 R5-6 |
| generation_id 单调防回退 | 回滚仅到 old generation；generation 单调防止错误世代 | §6.3/§6.7 R5-6 |
| Windows 文件占用 rename | 占用导致 sharing violation→退避重试→仍失败 failed_retryable 不强删 | §2.5.4/§6.8 R5-7 |
| Windows os.replace 覆盖 | 目标存在用 os.replace 原子覆盖（非 os.rename）；关闭句柄后执行 | §2.5.4/§6.8 R5-7 |
| Windows 指针版本切换 | 无 symlink 特权下用指针文件切换附件版本；读取按指针解析 | §6.8 R5-7 |
| Windows 非原子降级兜底 | rename 长期阻塞→copy+delete 非原子降级→Manifest+对账+孤儿扫描兜底一致性 | §6.8 R5-7 |

---

## 9. 仍未解决的开放问题（待独立复审/后续批次）

1. **NFKC 碰撞语义判定**：兼容合并同键但语义不同的标题，ambiguous/conflict 的 UI 判定与用户解决路径需细化；是否提供「按原始字面精确匹配」回退选项【待审批】。
2. **SQLite 租约锁严格性**：租约式逻辑锁在极端并发/时钟漂移下的正确性边界【待验证】；是否需降级单写者部署【待审批】。
3. **PG advisory lock 哈希碰撞**：hashtext(storage_key) 碰撞概率与是否改 key→整数映射【待验证】。
4. **lease_token 单调来源**：SQLite 多进程下 token 单调递增的生成（DB 序列/条件更新）需细化【待验证】。
5. **GC 租约时长/重试上限/安全等待期阈值**：具体数值待定【待审批】。
6. **三 Hash canonical 序列化细节**：Unicode 规范化是否纳入 hash 输入（建议 hash 用原始值保证身份稳定，规范化仅用于链接键）【待审批】。
7. **PG 多实例连接切换编排器**：维护标志/池重建协调的具体实现（共享存储/编排服务）依赖部署形态【待验证】。
8. **附件版本化目录与 storage_key 关系**：版本目录切换后旧版本 storage_key 引用一致性细节【待验证】。
9. **WITHDRAWN 枚举落地**：改 V1 枚举 vs REJECTED+note【待审批】。
10. **actor 身份**：V1 无认证，真实 actor 依赖 auth 批次；A1 预留字段【待审批】。
11. **审计保留默认策略最终批准**：推荐 SET NULL+快照，但用户拍板【待审批】；审计保留是否扩展到其他历史（版本/审核）留后续治理批次。
12. **frontmatter 冲突批量导入处理**：逐条 vs 批量默认规范化/保留【待审批】。
13. **MIME 白名单/SVG 策略**【待审批】。
14. **依赖最终批准**：CodeMirror 6/react-markdown 版本 LICENSE 核对未执行（本轮不装）【待审批】。
15. **M0/M5 独立复审**：回填修复 `6d91718` 仍待独立复审；A1 启动以复审通过+用户批准为前提。
16. **（R5-1）quarantine 同卷假设**：隔离区与存储根须同卷才原子 rename；跨卷部署的降级（copy+delete 非原子）正确性【待验证】；quarantine 后引用回升恢复的并发安全【待验证】。
17. **（R5-2）source_instance_id 来源**：导出方实例标识如何生成/持久化（V1 无实例 id）；跨实例 canonicalization_version 不一致的降级判定阈值【待审批/待验证】。
18. **（R5-3）TOCTOU 残余风险**：租约式逻辑锁无法消除 TOCTOU，仅降低；严格互斥需求下的单写者/库级串行降级是否被接受【待审批】；时钟漂移对租约过期/续租的影响【待验证】。
19. **（R5-4）needs_manual 人工流程**：人工分诊/重置的 API 与权限（依赖 auth 批次）；cancelled 后重新发起的触发条件【待审批】。
20. **（R5-5）序列化细则定值**：separators、datetime 精度、Decimal 去尾零、float 表示、null/缺失口径需用户拍板后冻结为 canonicalization_version v1【待审批】；hash 输入是否完全排除 Unicode 规范化【待审批】。
21. **（R5-6）对账前滚判定**：manifest 与资源不一致时「可验证前滚」的充分条件需细化；manifest 损坏重建的备份元数据依赖【待验证】；多实例下对账协调【待验证】。
22. **（R5-7）Windows 实测**：文件占用/rename/os.replace/指针切换/非原子降级需真实 Windows 环境验证；目标部署平台未确认【待审批/待验证】；杀软/索引器占用重试上限【待审批】。

> 开放项不阻塞设计修订，但**进入 A1 开发前须逐项关闭或明确延后**；【待验证】项不得宣称已验证。

---

## 10. SQLite 与 PostgreSQL 实现差异 + 平台兼容汇总（第四/五轮）

| 维度 | SQLite | PostgreSQL |
|---|---|---|
| 行级写锁 | 【事实】**不支持**；BEGIN IMMEDIATE 库级写锁 | 支持行级锁 |
| storage_key 协调 | **租约式逻辑锁**（storage_lock 表+lease_token fencing+短事务，物理操作移出写事务）；多进程依赖 DB 租约 | **会话级 advisory lock**（pg_advisory_lock(hashtext(key))，跨物理操作持有，显式 unlock，崩溃自动释放） |
| GC 任务认领 | 短事务**条件更新** rowcount==1（库级写锁串行化） | **FOR UPDATE SKIP LOCKED** + UPDATE |
| 唯一约束 | NULL 互不相等→需非空 normalized_link_key | 同（NULLS NOT DISTINCT 仅 PG15+，不依赖）→非空键 |
| 一致性快照 | Online Backup API / VACUUM INTO | pg_dump（MVCC）/ pg_basebackup |
| 恢复切换 | 临时文件 **os.replace**（关闭句柄后）+ 附件版本**指针切换**（Windows 兼容 §6.8/§10.1） | **Staging DB + 连接池重建**（非 URL 自动切换）+ 附件版本指针切换 + 多实例编排 |
| 崩溃恢复 | 租约过期 + Manifest phase 回滚 + 真实资源对账（§6.7） | advisory 会话释放 + Manifest phase 回滚 + 池切回旧库 + 对账 |
| 租约续租（R5-3） | 心跳短事务条件 UPDATE 延长 lease_expires_at（owner+token fencing）；续租失败中止 | advisory 会话级锁无需续租（会话存活即持有）；事务级锁随事务结束释放 |
| GC quarantine（R5-1） | 持锁 rename 原始→隔离区（同卷）；释放锁后仅 purge 隔离区 | 同机制（advisory 锁持锁期间 quarantine）；物理 rename 平台差异见 §10.1 |
| GC 状态机（R5-4） | 统一含 cancelled；条件更新流转 | 同；SKIP LOCKED 认领 |
| 封装位置 | `app/db/storage_lock.py`、`app/db/backup.py` 适配层；业务/Core 经抽象不写方言 SQL | 同 |

> 【待验证】以上方言实现均需进入开发后真实 SQLite+PG 测试验证；本轮为设计提议。

### 10.1 平台兼容差异（第五轮 R5-7：Windows vs POSIX）【事实+待验证】

| 维度 | POSIX（Linux/macOS） | Windows |
|---|---|---|
| 打开句柄占用 | 通常仍可 rename/unlink（句柄指向 inode） | **占用阻塞 rename/delete**（sharing violation）→关闭句柄+退避重试 |
| 目标存在 rename | `os.rename` 原子覆盖 | `os.rename` **失败**→须 `os.replace`（目标占用仍失败） |
| symlink | 普通用户可创建 | **需特权/开发者模式**→附件版本切换改用**指针文件**（§6.8） |
| 目录 rename | 同卷原子 | 任一打开句柄占用即失败；跨卷非原子 |
| 跨卷 rename | 非原子（EXDEV，copy+delete） | 非原子→Manifest+孤儿扫描兜底 |
| 降级 | — | rename 长期阻塞→copy+delete **非原子降级**（明确标注，不宣称原子） |

> 平台差异封装 backend 适配层；Core/业务不写平台特定代码。【待验证】需真实 Windows + POSIX 测试；**不得宣称跨平台原子切换已验证**。

---

## 11. 执行边界自检（本轮）

- 仅修改 `docs/plans/V2-batch-A-design.md` 与 `docs/plans/V2-dependency-selection.md`。
- **未写业务代码、未改 Core/Backend 实现、未安装依赖、未修改数据库迁移、未改 lockfile、未提交、未改 V1 功能、未解除 M0/M5 独立复审门禁、未宣布 V2 正式开发启动**。
- Git 状态以实际 `git status`/`git diff` 为准（见汇报）：预期仅未跟踪设计文档变更，HEAD 仍 `6d91718`，无已跟踪文件改动。

---

## 12. 声明

- 本文件实体/表/端点/代码块均为**设计示意（非实现代码）**；新增设计按【事实】/【提议】/【待审批】/【待验证】标注。
- 「现状/兼容事实」基于真实代码与引擎行为；「A1/A2 设计」为待批准提议（未实现、未测试）。
- 第四轮六项问题+三口径修订见 §0.3；**第五轮七项整改见 §0.5**（正文落点 §2.5/§2.6/§6/§10）；测试见 §8（8.1 第四轮 / 8.2 第五轮）；开放项见 §9；方言/平台差异见 §10；待审批见 §7。
- **诚实声明（第五轮）**：GC 持锁 quarantine、租约续租、TOCTOU、Manifest 对账、Windows 兼容等均为【设计提议】，正确性【待实际验证】；**TOCTOU 仅降低而非消除、Windows 跨平台原子切换未验证、租约锁非严格互斥**等限制已如实写明，**不得通过改写措辞宣称问题已解决**。
- 下一步：**第五轮设计冻结，停止，等待独立复审**（不再新增设计/机制，不自行进入下一轮）；§7 拍板 + §9 开放项关闭 + 依赖逐项审批 + 回填修复独立复审结论由用户/独立复审驱动；获批后再按 A1→A2 启动，届时更新 MILESTONES 与验收报告。