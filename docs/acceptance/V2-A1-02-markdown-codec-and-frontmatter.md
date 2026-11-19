# V2 Batch A1-02 Markdown 序列化与 frontmatter — 实施与验证记录

> 日期：2026-11-18 ｜ 基线 HEAD：`6d91718`（M0 初始提交 `2d2b634` 保留）
> 依据：`docs/plans/V2-batch-A-design.md` §2.2.3（交换格式）、§2.3（口径 A 冲突三态）、§2.6.1（三 Hash + canonicalization）、§2.6.2（变化分类）、A1-T2/T3/T6
> 状态：**A1-02 已实现并真实验证通过（Core 层）**；A1-03～A1-06 未开始。改动尚未提交 Git（等待提交指示）。

## 1. 本子任务范围

只做「Markdown 序列化与 frontmatter」的 **Knowledge Core 纯 Python 实现**：
确定性 canonical 序列化 + 三 Hash + 零依赖保守 frontmatter 解析/再生 + `MarkdownCodec` ABC 与
`StdlibMarkdownCodec` 实现 + frontmatter 冲突三态 + 单元测试与编解码级导入导出往返测试 + 独立性守护扩展。

**不含**（属后续子任务，本轮未实现、未验证）：
wikilink 解析/NFKC 规范化/LinkResolver/反向链接（A1-03）、
导入导出服务与 DB 幂等/ImportOrigin/ImportReport/附件 GC（A1-04）、
版本/审核集成与索引同步（A1-05）、API 与前端（A1-06 回归范围内）。

对应设计任务：**A1-T2**（MarkdownCodec ABC + 三 Hash）、**A1-T3**（编解码/三态/语义字节边界）、**A1-T6**（独立性守护扩展）。

## 2. 改动文件清单（1 改 7 增，无任何无关模块）

| 文件 | 类型 | 行数 | 内容 |
|---|---|---|---|
| `knowledge-core/src/knowledge_core/markdown/__init__.py` | 增 | 540 | `MarkdownCodec` ABC；`MarkdownDocument`/`ParsedMarkdown`/`RenderedMarkdown`/`ConflictResolution`；`FrontmatterState` 三态、`FrontmatterResolution`、`MarkdownWarningCode`(14)、`CodecWarning`；`KNOWN_FRONTMATTER_KEYS`(11)、`RESERVED_META_KEYS`、`EXTRA_KEY_PREFIX`；`encode_space`/`decode_space`；三 Hash 函数 + `DocumentHashes`/`compute_document_hashes`；`resolve_frontmatter_conflict` |
| `knowledge-core/src/knowledge_core/markdown/canonical.py` | 增 | 239 | `canonicalize`/`canonical_json`/`sha256_canonical`；`canonical_datetime`（UTC 固定微秒 6 位）/`canonical_decimal`（不经 float）；裸 float 拒绝；null≠缺失；语义序排序器 `sort_tags/sort_links/sort_attachments/sort_sources`；`hashes_comparable`/`require_comparable_versions` |
| `knowledge-core/src/knowledge_core/markdown/frontmatter.py` | 增 | 583 | 零依赖保守 frontmatter 解析（标量/流式/块映射/块序列，深度≤3）+ 确定性 emitter（已知键固定序、未知键字典序、原始片段逐字回写、不产生重复键） |
| `knowledge-core/src/knowledge_core/markdown/codec.py` | 增 | 300 | `StdlibMarkdownCodec.parse/dump`：已知键映射实体、未知键入 `extra_metadata`、复杂值 `_raw` 兜底、冲突态 `_frontmatter_raw` 原始保留、`x_explainlab_` 命名空间冲突、稳定告警码 |
| `knowledge-core/tests/test_markdown_canonical.py` | 增 | 499 | **74** 用例：canonical JSON/时间/Decimal/float 禁用/null≠缺失/列表序/版本包络/三 Hash 分离/§2.6.2 变化分类逐行/Unicode 身份/跨构造确定性 |
| `knowledge-core/tests/test_markdown_frontmatter.py` | 增 | 454 | **122** 用例：切分/BOM/未闭合、标量与集合解析、保守边界与原始兜底、重复键、emitter 确定性、parse→emit→parse 稳定性 |
| `knowledge-core/tests/test_markdown_codec.py` | 增 | 637 | **95** 用例：§2.2.3 示例全字段映射、正文逐字保真、确定性再生、语义无损往返、未知字段保留、**冲突三态前后**、重复键、命名空间冲突、告警、Hash 幂等基础 |
| `knowledge-core/tests/test_interfaces.py` | 改（加强） | +37 | `SERVICES` 增 `MarkdownCodec`（抽象不可实例化）；Web 框架守护子进程增导入 `markdown`/`.canonical`/`.frontmatter`/`.codec`；**新增零新增依赖守护**（非 stdlib 顶层模块白名单仅 Pydantic 栈） |

**未改动**：任何 V1 服务/API/schema/前端代码；A1-01 已落地的实体/端口/ORM/迁移（本轮只消费，不修改）。
`uv.lock`、`pyproject.toml`、`backend/pyproject.toml`、`knowledge-core/pyproject.toml`、`frontend/package.json`、`frontend/package-lock.json`
经 `git diff --name-only` 核对返回 **0 条**。**新增依赖：0**（未安装 PyYAML / KaTeX / DOMPurify / python-magic / CodeMirror 6 / react-markdown）。

## 3. 设计安全机制落地情况（A1-02 应落地部分）

| 机制 | 落地形态 | 状态 |
|---|---|---|
| `document_content_hash` | `SHA256(canonical({title?, content}, v))`；**拒绝多余键**（只允许 title/content），排除治理状态与易变元数据 | ✅ 74+95 用例真实验证 |
| `document_payload_hash` | `SHA256(canonical(完整交换载荷, v))`，含 id/title/content/tags/space/status/version/timestamps/sources/links/attachments/extra_metadata；**整体序列化**而非组件拼接 | ✅ 同上 |
| `review_payload_hash` | `SHA256(canonical(变更 payload, v))`，只允许 `title/content/status/space_id`，**空变更拒绝** | ✅ 函数与边界用例已验证；**接入审核流程属 A1-05，未验证** |
| `canonicalization_version` | 包络显式 `{"canonicalization_version": 1, ...}`；非 mapping 输入包成 `{"value": ...}`；业务字段占用保留键→报错；`require_comparable_versions` 拒绝跨版本直接比较 | ✅ 版本包络/保留键/不可比较用例 |
| 组件 Hash（变化分类） | `tags_hash`/`links_hash`/`attachments_hash`/`extra_metadata_hash`/`governance_hash` 由**实际存在字段**子集计算（缺失≠空） | ✅ §2.6.2 逐行分类用例 |
| frontmatter 三态（口径 A） | `normal` / `frontmatter_conflict_requires_resolution` / `normalized`，与设计表三行一一对应 | ✅ 三态前后往返用例 + 真实文件冒烟 |
| 不静默生成重复键 | `_frontmatter_raw` 存在 ⟺ 冲突态；冲突态导出**逐字回写原始块**，拒绝再生其中已知键；状态被误置 normal 时**防御性升级**为冲突 | ✅ 不变量用例 + 防御升级用例 |
| 实体修改暂存不写交换文件 | 冲突态未解决导出：实体 title/version 修改**不出现**在文本中，并发 `ENTITY_EDITS_NOT_EXPORTED` 告警 | ✅ 用例 + 冒烟逐字节比对 |
| 用户主动解决 | `NORMALIZE`（实体再生已知 + 未知回写 + 丢弃原始块 + 告警）/ `KEEP_ORIGINAL`（原始权威 + 实体不导出 + 告警）；**不给 resolution 绝不静默规范化** | ✅ 两种 resolution 用例 |
| 未知字段保留 | 简单未知值结构化保留；复杂未知值 `_raw` **逐字**回写 + `UNKNOWN_COMPLEX_VALUE` 告警；诊断元键（`_raw/_frontmatter_raw/_duplicates/_conflict`）**永不**作为 frontmatter 键再生 | ✅ 往返 payload_hash 相等用例 |
| 已知键命名空间 | `extra_metadata` 已知同名 → `x_explainlab_<key>` + `KNOWN_KEY_COLLISION` 告警；前缀再撞 → `_2/_3` 确定性后缀；输出无重复键 | ✅ 用例（含 hash 局限，见 §6） |
| 重复键 | 取最后值 + `_duplicates` 记录全部原始值 + `DUPLICATE_KEY` 告警；再生无重复键 | ✅ 用例（含 hash 局限，见 §6） |
| 零依赖保守解析诚实边界 | 仅 stdlib；块标量 `\|`/`>`、锚点/别名/标签、深度>3、tab 缩进、`%` 指令、不可识别行 → **原始兜底 + 告警**，绝不静默丢弃；未闭合 `---` → 全文当正文（零丢失） | ✅ 122 用例含参数化边界矩阵 |
| 独立性守护（A1-T6） | 干净子进程导入 markdown 全部模块：① 不含 fastapi/starlette/flask/django；② 非 stdlib 顶层模块 ⊆ `{knowledge_core, pydantic, pydantic_core, annotated_types, typing_extensions, typing_inspection}` | ✅ 真实子进程断言通过 |
| `normalized_link_key` / `link_normalization_version` | A1-01 已建表/常量；**本轮不实现规范化算法**（A1-03） | ⏳ A1-03 |
| `ImportOrigin` / `source_payload_hash` / GC / lease / Manifest / operation_id | A1-01 已建表/端口；**本轮不实现服务流程**（A1-04） | ⏳ A1-04 |

## 4. 实现决策（设计留待实现阶段确定的细节，未重开设计讨论）

| # | 决策 | 依据与理由 |
|---|---|---|
| D1 | `attachments` 列为**第 11 个已知 frontmatter 键** | §2.3 正文列举 10 键，但 §2.6.1 覆盖字段表明确含 `attachments(清单+content_hash)` 且分类为交换元数据。两处不一致时取**更完整的 §2.6.1**，否则附件清单会落入 extra_metadata 而无法参与 attachments_hash 分类。已加用例锁定。 |
| D2 | canonical JSON 采用**紧凑 separators** `(",", ":")` | §2.6.1「固定 separators（`, ` / `: ` 或紧凑，**定其一**）」授权实现择一。紧凑形式无尾随空格歧义。**如需改为带空格形式，必须 bump `canonicalization_version` 并重算全部 hash。** |
| D3 | YAML 小数字面量解析为 **`Decimal`**，绝不产生 float | §2.6.1「Decimal 不经 float」「hash 输入禁用裸 float」。`emit_scalar` 遇 float **抛错**，从源头堵住平台 repr 差异。 |
| D4 | 时间戳输出固定 `YYYY-MM-DDTHH:MM:SS.ffffffZ`，用**显式 f-string 格式化**而非 `strftime` | §2.6.1 固定微秒 6 位。`strftime("%Y")` 在部分平台对年份补零行为不一致，显式格式化消除平台漂移；naive 视为 UTC，带偏移转 UTC。 |
| D5 | 字段存在性用 Pydantic `model_fields_set` 判定 | §2.6.1「缺失≠null，二者 hash 不同；导入/导出须保持字段存在性一致」。显式 `title: null` 会再生 `title: null`；缺失键不补 null。 |
| D6 | 集合语义序排序，**排序只在 payload_fields 层做，不改动用户数据顺序** | §2.6.1「语义序列表排序 + 次级键保证全序」。`sort_tags` 键 `(casefold, 原字面)`；`sort_links` 键 `(normalized_link_key or title, target_id, title, alias, resolution)`——A1-03 前 links 交换字典可能尚无 `normalized_link_key`，故以 title 兜底，A1-03 落地后自动改用规范键；`sort_attachments` 以 `content_hash` 首键；`sort_sources` 以 `(type, conversation_id, uri, excerpt, id)`。 |
| D7 | hash 输入用**原始 Unicode**，不做 NFKC/casefold | §2.6.1「规范化仅用于链接键，不污染 hash」。已加 `Ｆｏｏ≠Foo`、`ﬁle≠file` 身份用例。 |
| D8 | 集合字段显式 `null` 判为**类型不符→冲突态**；标量 `null` 合法 | 集合实体类型为 list，`tags: null` 无法安全映射；`space: null` 等价 `personal-null`（个人总知识库）。 |
| D9 | 交换子对象（sources/links/attachments）以 **dict 形态**承载，不直接绑实体 | Core 编解码须可独立调用、不依赖持久化；实体装配属 A1-04 服务层。 |
| D10 | `frontmatter_state`/`conflict_resolution` **不入 payload_hash** | 二者是实例本地诊断/用户选择，非交换身份；但 `_frontmatter_raw`/`_conflict`/`_duplicates` 属 extra_metadata，**参与**身份（原始数据保留本身是载荷的一部分）。已加用例锁定该区分。 |
| D11 | `MarkdownDocument` 设 `extra="forbid"` | 本轮真实发现并修复的缺陷：`space` 交换键曾被误写入不存在的 `space` 字段而被 Pydantic 静默丢弃（数据丢失）。改为 forbid 后任何键名拼写错误立即报错，不再静默吞字段。 |
| D12 | 保守解析深度上限 `_MAX_COLLECTION_DEPTH = 3` | 顶层值深度 1、集合成员深度 2、成员内部标量深度 3；`k: [[a,b],{c:d}]` 可解析，`k: [[[a]]]` 超范围→原始兜底。覆盖 Obsidian 常见 frontmatter，超出即诚实降级。 |

> 设计中标注【待审批】的取值（紧凑 separators、v1 初值、naive→UTC、Decimal 去尾零、禁用裸 float、null≠缺失、原始 Unicode）
> 均**按设计正文所述方案实现**，未自行改变语义。这些取值一旦变更，须 bump `canonicalization_version` 并重算 hash（§2.6.1）。

## 5. 真实验证证据（全部实际运行，非离线推断）

环境：Python 3.11.9 / uv 0.13.6 / SQLite 3.45.1 / 真实 PostgreSQL 16.8（`127.0.0.1:55432`，`pg_isready` 返回 `accepting connections`）。
Windows 控制台为 GBK，命令统一加 `PYTHONIOENCODING=utf-8` 避免中文乱码（数据本身始终 UTF-8）。

### 5.1 本轮新增测试

```
$ uv run pytest knowledge-core/tests/test_markdown_canonical.py \
      knowledge-core/tests/test_markdown_frontmatter.py \
      knowledge-core/tests/test_markdown_codec.py \
      knowledge-core/tests/test_interfaces.py -o addopts="--import-mode=importlib"
299 tests collected
```

逐文件用例数（`--collect-only -q` 实测）：`test_markdown_canonical` **74**、`test_markdown_frontmatter` **122**、
`test_markdown_codec` **95**、`test_interfaces` **8**（原 6 + 新增 2）。
本轮净增 **293** 个用例。

### 5.2 Lint

```
$ uv run ruff check --fix      # 仅修 F541（测试中多余 f 前缀）2 处
Found 2 errors (2 fixed, 0 remaining).
$ uv run ruff check
All checks passed!
```

另手工消除 1 处 SIM103（`_needs_quotes` 直接返回布尔表达式，语义等价）。**全程未使用 `ruff format`**。

### 5.3 全量回归 — 默认 SQLite

```
$ uv run pytest -o addopts="--import-mode=importlib"
============ 644 passed, 41 skipped, 1 warning in 65.99s (0:01:05) ============
```

41 skipped 全部为 `EXPLAINLAB_PG_TEST_URL` 门控的 PG 模块（预期）。
对照 A1-01 基线 351 passed / 41 skipped：351 + 293 = **644**，**V1 与 A1-01 用例零回归**。

### 5.4 全量回归 — 真实 PostgreSQL

```
$ EXPLAINLAB_PG_TEST_URL="postgresql+psycopg://postgres@127.0.0.1:55432/explainlab_test" \
  uv run pytest -o addopts="--import-mode=importlib"
================== 685 passed, 1 warning in 68.17s (0:01:08) ==================
```

**0 skipped**：41 个 PG 用例（含 A1-01 的 24 个 V2 模型用例、迁移 up/down、tsvector/触发器/级联、CJK 回退、向量、混合检索）
全部连真实实例执行通过。392 + 293 = **685**。

### 5.5 真实文件级导出→重新导入冒烟（临时目录，未写入仓库）

以设计 §2.2.3 示例写入真实 `.md` 文件，经 `parse → dump → 写盘 → parse → dump → 写盘`：

```
[正常态] state: normal -> normal warnings: 0
  content_hash 相等: True
  payload_hash 相等: True
  源文件 vs 导出文件 字节相同: False      ← 预期：确定性再生（时间戳补微秒、流式映射键排序）
  导出 vs 再导出 字节相同: True           ← 再生后达到字节稳定（不动点）
  正文逐字保留: True
  content_hash: beaabd9a766354ff payload_hash: 21ece04142d137c6
```

冲突三态同一文件真实验证（`version: 三点五` 类型不符 + `complex: |` 复杂未知值）：

```
[冲突态] codes: unknown_complex_value, known_type_mismatch,
                frontmatter_raw_preserved, frontmatter_conflict_requires_resolution
  未解决导出 == 源文件字节: True | 实体修改未写入: True
  规范化后 state: normalized
    ---
    id: 550e8400-e29b-41d4-a716-446655440000
    title: 实体新标题          ← 实体修改此时才写入
    version: 9
    complex: |                 ← 复杂未知值仍逐字保留
      原始片段
    custom: 保留值
    ---
    正文
  规范化后再往返 payload_hash 相等: True
[保留原文] state: frontmatter_conflict_requires_resolution | 原文权威: True
```

### 5.6 前端

本轮**未触碰前端任何文件**，故未重跑前端测试（A1-01 已验证 72 tests + typecheck + build 通过；A1-06 将全量重跑）。

## 6. 诚实局限（已实测确认，不写成 PASS）

| # | 局限 | 实测结果 | 影响与处置 |
|---|---|---|---|
| L1 | **字节级无损不保证**（正常态） | 源文件 vs 导出文件字节不同；再生一次后达到字节稳定 | 符合 §2.3「语义无损（正常态保证）；字节级不保证」。仅原始兜底片段逐字回写。 |
| L2 | **含重复键的源文件**：导出→再导入会改变 `payload_hash` | 同文件重复解析 hash **相等**（幂等成立）；导出后再导入 hash **不等**（`_duplicates` 诊断元键不再生，再生文件已无重复键）；`content_hash` **相等** | 幂等权威是**入站源文件**的 hash（§2.6.3），故「重导同一文件→skipped」不受影响。但「导出自己的文件再导入」在源含重复键时会被判为元数据变化而非 skipped。A1-04 须在 ImportReport 中如实提示。 |
| L3 | **已知键命名空间冲突**：导出→再导入会改变 `payload_hash` | `extra_metadata={"title": ...}` 导出为 `x_explainlab_title`，再导入得到键名 `x_explainlab_title` → hash 不等；`content_hash` 相等 | 前缀化是 §2.3 明文规则，键名变化不可避免。A1-04 须提示该变化属元数据变化（非内容审核）。 |
| L4 | **非通用 YAML 解析器** | 块标量 `\|`/`>`、锚点 `&`/别名 `*`/标签 `!`、深度>3、tab 缩进、`%` 指令、多文档 `---` 等 → 原始兜底 + 告警 | §2.3 明文诚实边界。未知键兜底后仍语义无损；**已知键**兜底则进冲突态待用户解决。需结构化理解须另行审批 PyYAML（**暂不批准，本轮未安装**）。 |
| L5 | 冲突态**不得称完全无损往返** | 冲突态导出 = 原始块逐字 + 正文；实体已知字段修改未写入 | 已在代码 docstring、告警码与本记录中明确；A1-04 的 ImportReport / A1-06 的 UI 须承接该提示。 |
| L6 | `sort_links` 暂以 title 兜底首键 | A1-03 前交换字典可能无 `normalized_link_key` | **已判定无需 bump 版本**：设计规则本就是「links 按 normalized_link_key 排序」，title 只是该键缺失时的兜底；A1-03 后链接行带上规范键属**载荷字段变化**（hash 本就应该变），不是序列化规则变化。若将来改动排序规则本身，才须 bump `canonicalization_version` 重算。 |

## 7. 未验证 / 后续子任务（不得视为已完成）

- ⏳ **A1-03**：wikilink 解析（代码块/行内代码/转义/畸形排除）、NFKC+casefold+空白折叠、`\x1f` 键、碰撞 ambiguous/conflict 处理、`link_normalization_version`、LinkResolver、绑定优先同步、反向链接、reresolve、键重建；改名/连续保存/导出重导测试。
  - 衔接点已判定（见 L6）：规范键落地属载荷字段变化，**不 bump** `canonicalization_version`。
- ⏳ **A1-04**：导入导出服务、持久化源 hash 幂等、ImportOrigin、跨实例 Draft、每文档事务/部分失败、ImportReport、附件生命周期 + StorageKeyLock 方言实现 + GC 租约/隔离/孤儿扫描、Manifest。
- ⏳ **A1-05**：active 编辑→202 提案、draft 直改、`review_payload_hash` + `proposal_version` + 异 payload 拒绝 + 撤回、批准→索引同步。
- ⏳ **A1-06**：SQLite + PG + Core + API + 前端全量回归、验收报告、MILESTONES 更新。
- ⏳ **DB 级导入/导出真实验收**（17 项必须实现之第 17 项）：本轮只完成**编解码级**往返验证，数据库落库/幂等/跨实例尚未实现，**未验证**。

## 8. Git 自检

```
$ git log --oneline -1
6d91718 fix: 迁移 0004 回填历史 knowledge_item 到全文索引（SQLite FTS5 + PG tsvector）

$ git diff --name-only -- uv.lock frontend/package-lock.json pyproject.toml \
      backend/pyproject.toml knowledge-core/pyproject.toml frontend/package.json
（空 → 零锁定文件/依赖漂移）
```

工作树改动仅含 A1-01（8 改 4 增）+ A1-02（1 改 7 增）文件；
`docs/audit/`、`docs/plans/V2-*.md`、`release/` 仍为未跟踪，**不提交**。
无临时测试文件、数据库、日志、构建产物入库（冒烟脚本走系统临时目录，运行后即销毁）。
**本轮未执行任何 commit / push**（AGENTS.md §8：未经用户明确要求不提交、不推送）。

## 9. 结论

A1-02「Markdown 序列化与 frontmatter」在 **Knowledge Core 层已实现并真实验证通过**：
三 Hash 与 canonicalization 包络、零依赖保守解析与确定性再生、frontmatter 冲突三态、未知字段保留、
命名空间冲突与重复键处理、独立性与零新增依赖守护，均以真实运行取证；
全量回归 **SQLite 644 passed / 41 skipped**、**真实 PostgreSQL 685 passed / 0 skipped**，V1 与 A1-01 零回归，ruff 全通过。

§6 的 6 项局限已如实记录，未写成 PASS；§7 的后续子任务未开始。
按批准的开发顺序，**下一步进入 A1-03（稳定链接与反向链接）**，先出计划再实现。