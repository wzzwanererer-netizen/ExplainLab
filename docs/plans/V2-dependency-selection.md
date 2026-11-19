# ExplainLab V2 · 新增依赖选型对比表（逐项审批用）

> 文档性质：**选型对比 + 审批材料**，非安装动作。
> 编写日期：2026-11-17 ｜ 修订：2026-11-17（第一轮审查：优先 CodeMirror 6 + react-markdown，暂不批准 KaTeX/PyYAML/非必要依赖，react-markdown 安全加固，DOMPurify 重评，版本 LICENSE 核对）｜ 修订：2026-11-17（第二轮复审：A-5 强化 stdlib 非通用 YAML 解析器、语义无损而非字节级无损的诚实边界）｜ 修订：2026-11-17（**第四轮复审：A-6 同步 SQLite 租约锁/PG advisory、GC 租约认领/重启恢复、Restore Manifest 两阶段、SQLite/PG 分别备份恢复协议（PG Staging+连接池重建）、A1 零新增必需依赖结论**）｜ 修订：2026-11-17（**第五轮整改：A-6 同步 GC 持锁 quarantine、跨实例来源身份、租约续租/TOCTOU、GC 状态机含 cancelled、canonicalization_version、Manifest operation_id/generation_id/resource_version+崩溃对账、Windows 兼容；A1 零新增结论不变**）
> 上游：[V2-plan.md](V2-plan.md) ｜ 设计：[V2-batch-A-design.md](V2-batch-A-design.md)
> 状态：**第五轮冻结版（待逐项审批）**。本版本为第五轮冻结基线，与主设计文档一致；**不安装任何依赖**、不改 lockfile。

## 阅读说明

- 本表对每个候选给出：**用途 / 替代方案 / 许可证 / 性能影响 / 维护风险 / 建议**。
- **许可证为常见声明，最终批准前必须核对「具体拟用版本」的官方 LICENSE 文件**（npm 包 LICENSE / GitHub 仓库），不凭印象批准。
- 「建议」含**本轮审批状态**：优先评估待批准 / 暂不批准 / 条件性 / 延后。
- 依赖方向硬约束：编辑器/渲染/YAML 库/图谱渲染/AI 平台 SDK **不得进入 Knowledge Core**（Core 仅 stdlib + Pydantic + httpx）。

---

## A 批次（开放 Markdown 知识库）依赖

### A-1 Markdown 编辑器（前端）— 优先 CodeMirror 6

| 候选 | 用途 | 替代方案 | 许可证 | 性能影响 | 维护风险 | 建议 / 审批状态 |
|---|---|---|---|---|---|---|
| **CodeMirror 6** | Markdown 源码编辑、语法高亮、wikilink/标签自动补全、快捷键 | Monaco / TipTap / Milkdown / 纯 textarea | MIT（核对拟用版本） | 模块化按需引入，体积中等；懒加载可控初始包 | 活跃维护、生态成熟、API 稳定 | **优先评估，待批准**（审查项六）。补全/高亮契合 `[[ ]]` 与标签需求 |
| Monaco Editor | 重型代码编辑器 | CodeMirror 6 | MIT | 体积大（数 MB），初始包/懒加载压力高 | 活跃（VS Code 同源） | 备选；对笔记编辑偏重，**不优先** |
| TipTap / Milkdown | 富文本/所见即所得 Markdown | CodeMirror 6 | MIT | 中等；ProseMirror 内核 | 活跃 | 备选；WYSIWYG 与「源码+预览」路线不完全契合，**不优先** |
| 纯 `<textarea>` | 零依赖兜底 | — | 无 | 极小 | 无 | 兜底；无补全/高亮，**不满足审查项五体验要求**，仅作降级 |

> 结论：**优先 CodeMirror 6**。批准前核对其具体版本 MIT LICENSE 与子包（@codemirror/*）许可证一致性。

### A-2 Markdown 渲染（前端）— 优先 react-markdown（含安全加固）

| 候选 | 用途 | 替代方案 | 许可证 | 性能影响 | 维护风险 | 建议 / 审批状态 |
|---|---|---|---|---|---|---|
| **react-markdown** | Markdown→React 渲染、自定义组件（wikilink/image/link） | marked / markdown-it / remark-rehype | MIT（核对拟用版本） | 轻量、React 原生、按需插件 | 活跃、unified 生态成熟 | **优先评估，待批准**（审查项六）。**须落实下方安全加固** |
| marked | Markdown→HTML 字符串 | react-markdown | MIT | 极快、极小 | 活跃 | 备选；输出 HTML 字符串需额外消毒，React 集成不如 react-markdown 直接 |
| markdown-it | Markdown→HTML，插件丰富 | react-markdown | MIT | 快、小 | 活跃 | 备选；同样需 HTML 消毒 |
| remark-rehype | unified 底层管线 | react-markdown（已封装） | MIT | 中 | 活跃 | react-markdown 已内含，无需单独引入 |

**react-markdown 安全加固（采用则必须落实，审查项六）**

1. **默认禁用原始 HTML**：**不引入 `rehype-raw`**；react-markdown 默认跳过/转义 raw HTML，第三方 md 中的 `<script>`/内联事件/危险标签不渲染。
2. **URL 协议校验**：自定义 `urlTransform`，仅允许 `http:`/`https:`/`mailto:` 及内部附件相对路径（`attachments/`）；**拦截 `javascript:`/`data:`/`vbscript:` 等危险协议**（含大小写/编码绕过）。
3. **自定义组件安全检查**：
   - wikilink 组件：渲染为内部跳转（按稳定 ID），不外发危险 URL。
   - image 组件：`src` 经协议校验；附件走后端安全 serve；禁内联 SVG 脚本。
   - link 组件：外链加 `rel="noopener noreferrer"`、`target` 受控；协议校验。
4. **不启用 dangerouslySetInnerHTML**；渲染全程走 React 元素，避免 HTML 注入面。
5. 安全测试（A2）：raw HTML 不渲染、危险 URL 被拦、自定义组件无注入（Vitest + 真实浏览器）。

> 结论：**优先 react-markdown + 上述安全加固**。批准前核对具体版本 MIT LICENSE。

### A-3 HTML 消毒（前端）— DOMPurify 重新评估

| 候选 | 用途 | 替代方案 | 许可证 | 性能影响 | 维护风险 | 建议 / 审批状态 |
|---|---|---|---|---|---|---|
| ~~DOMPurify~~ | 渲染原始 HTML 时消毒 | react-markdown 默认禁 raw HTML + URL 校验 + 安全组件 | Apache-2.0 OR MPL-2.0（双许可，核对版本） | 小 | 活跃 | **重新评估 → 暂不批准**（审查项六）。react-markdown 默认不渲染 raw HTML，配合 A-2 加固**通常无需 DOMPurify**；**仅当未来引入 rehype-raw 渲染原始 HTML 才需要**，届时再审批 |
| sanitize-html | HTML 消毒 | DOMPurify | MIT | 中 | 活跃 | 同上，暂不需要 |

> 结论：**A 批次不引入 DOMPurify**。以「默认禁 raw HTML + URL 协议校验 + 安全自定义组件」替代消毒需求；保留「若启用 raw HTML 则必须消毒」的条件性约束。

### A-4 数学公式（前端）— 暂不批准

| 候选 | 用途 | 替代方案 | 许可证 | 性能影响 | 维护风险 | 建议 / 审批状态 |
|---|---|---|---|---|---|---|
| ~~KaTeX~~ | 数学公式渲染 | 延后；纯文本/代码块暂代 | MIT | 中（字体+引擎） | 活跃 | **暂不批准**（审查项六）。非 A 必需，延后到确有公式需求再议 |
| ~~MathJax~~ | 数学公式渲染 | KaTeX | Apache-2.0 | 较大 | 活跃 | **暂不批准**，延后 |

### A-5 Frontmatter / YAML（后端 / Core）— 暂不批准 PyYAML

| 候选 | 用途 | 替代方案 | 许可证 | 性能影响 | 维护风险 | 建议 / 审批状态 |
|---|---|---|---|---|---|---|
| ~~PyYAML~~ | 第三方复杂 frontmatter 结构化解析 | **Core stdlib 确定性 emitter + 保守解析 + 原始文本兜底保真** | MIT | 小 | 活跃 | **暂不批准**（审查项六）。A1 以零依赖方案保留未知字段（结构化简单值；复杂值原始文本兜底 + 告警，不静默丢失）；若未来需结构化理解复杂第三方 YAML 再审批 |
| python-frontmatter | frontmatter 读写（依赖 PyYAML） | Core stdlib 方案 | MIT | 小 | 活跃 | **暂不批准**（连带 PyYAML） |
| ruamel.yaml | 保序 YAML 往返 | Core stdlib 方案 | MIT | 中 | 活跃 | **暂不批准**，延后 |

> 结论：**A1 零新增必需依赖**。Core 用 stdlib 实现**固定已知 schema** 的确定性导出 + 保守解析；未知字段经 `extra_metadata` 保留，复杂值原始文本兜底 + warnings，**不静默丢失**（详见设计 §2.3）。PyYAML 等暂不批准。
>
> **诚实边界（第二轮复审）**：stdlib 保守解析器**仅覆盖固定已知 schema + 简单未知标量/列表/映射**，**不是通用 YAML 解析器，不能完整解析任意 YAML**；复杂/非标准 YAML（锚点、别名、多行折叠、自定义标签等）以**原始文本兜底保真**（保真而非结构化理解）+ 告警。保真口径为**语义无损**（已知字段映射 + 未知字段键值语义保留），**不承诺字节级无损**（导出器确定性再生 frontmatter，键序/格式可能变化，仅原始兜底片段逐字回写）。**不得宣称 stdlib 方案能完整解析任意 YAML 或字节级无损。** 若未来需结构化理解复杂第三方 YAML，再审批 PyYAML。

### A-6 附件 / 备份恢复（后端）

| 能力 | 实现 | 新增依赖 | 审批状态 |
|---|---|---|---|
| 附件存储/哈希去重/路径穿越防护 | stdlib `hashlib`/`uuid`/`pathlib` + 既有 FastAPI UploadFile | 无 | 零新增 |
| MIME 嗅探（magic bytes） | stdlib 字节签名比对（白名单） | 无（如需 python-magic 另议） | 零新增；python-magic **暂不批准**，先用 stdlib 签名 |
| **三 Hash + canonicalization_version（第四/五轮）** | document_content_hash / document_payload_hash / review_payload_hash；hash 包络含 **canonicalization_version**；datetime/Decimal/null/缺失/float/列表序确定性规则 | stdlib `hashlib`+`json`+`datetime`+`decimal`（确定性序列化） | 无 | 零新增 |
| **跨实例来源身份持久化（第五轮 R5-2）** | **ImportOrigin / source_payload_hash + source_instance_id + source_content_hash**；幂等比对持久化源 hash（非目标再生 hash） | 既有 SQLAlchemy（import_origin 表/item 来源列） | 无 | 零新增 |
| **storage_key 并发锁（第四/五轮）** | **SQLite：租约式逻辑锁**（storage_lock 表 + lease_token fencing + 短事务 + **续租心跳/续租失败中止/旧 Worker 恢复保护**，物理操作移出 DB 写事务；【事实】SQLite 无行级写锁，BEGIN IMMEDIATE 为库级；**TOCTOU 仅降低非消除，严格互斥需降级**）/ **PG：既有 psycopg `pg_advisory_lock`（会话级）** | 无 | 零新增（方言差异封装 backend 适配层；单/多进程限制与降级见设计 §2.5/§10） |
| **GC 持锁 quarantine + 状态机（第五轮 R5-1/R5-4）** | **持 storage_key 锁期间引用复核 + 原子 quarantine 隔离（锁内 rename 原始→隔离区），禁止释放锁后删原始；释放锁后仅 purge 隔离区**；统一状态机含 **cancelled**；既有 SQLAlchemy `gc_task`（lease_owner/lease_expires_at/attempts/next_retry_at/lease_token/**quarantine_path/quarantined_at**）；PG `FOR UPDATE SKIP LOCKED` / SQLite 短事务条件更新 | 无 | 零新增 |
| **附件孤儿扫描兜底（第四/五轮口径 B）** | stdlib 物理目录扫描（**含隔离区**）+ 既有 DB 引用对照 + 安全等待期/排除临时文件/并发上传；quarantine 残留清理与引用回升恢复 | 无 | 零新增（独立于可能随事务回滚的 gc_task） |
| DB 备份恢复（双方言分别协议） | **SQLite**：Online Backup API / VACUUM INTO（stdlib `sqlite3`）+ integrity_check + 临时文件 os.replace；**PG**：`pg_dump`/`pg_restore`（既有 psycopg + 本机 PG 工具）+ **Staging DB + 连接池重建（非 DATABASE_URL 自动切换）+ 附件版本切换 + 多实例编排** | 无 | 零新增 |
| **Restore Manifest 两阶段 + 崩溃对账（第三/四/五轮）** | stdlib `json`/`hashlib`/`os`（fsync/rename）+ 既有 DB 驱动；**operation_id/generation_id/resource_version**；完成标记+旧资源保留+崩溃回滚+**Manifest 与真实资源不一致对账（不盲信标记）** | 无 | 零新增 |
| **Windows 平台兼容（第五轮 R5-7）** | 【事实】Windows 占用阻塞 rename/delete、os.rename 目标存在失败、symlink 需特权；**指针文件替代 symlink + os.replace + sharing violation 退避重试 + copy+delete 非原子降级（Manifest+孤儿兜底）** | stdlib `os`/`shutil`/`time`（无新增） | 无 | 零新增（平台差异封装 backend 适配层；正确性待真实 Windows 验证） |
| **迁移运维包装器 + 规范化键重建（第三/四轮）** | stdlib + 既有 Alembic/psycopg；备份→校验→确认→记录→才 downgrade；NFKC 键重建（link_normalization_version） | 无 | 零新增 |

> **第四/五轮结论**：三 Hash + **canonicalization_version**、**跨实例来源身份持久化（ImportOrigin）**、SQLite 租约锁（fencing+短事务+**续租/TOCTOU 边界**）/PG advisory、**GC 持锁 quarantine + 统一状态机含 cancelled**、独立孤儿扫描（含隔离区）、Restore Manifest 两阶段（**operation_id/generation_id/resource_version + 崩溃对账**）、**SQLite/PG 分别备份恢复协议（PG Staging DB + 连接池重建，非 DATABASE_URL 自动切换）**、**Windows 平台兼容（指针文件/os.replace/退避重试/非原子降级）**、迁移门禁、NFKC 规范化键重建等新增机制**全部用既有栈（stdlib + SQLAlchemy + psycopg + Alembic + FastAPI）实现，A1 仍零新增必需依赖**。方言/平台差异封装 backend 适配层，业务/Core 不写方言/平台特定代码。详见设计 §2.5/§2.6/§6/§10。
>
> **诚实边界（第四/五轮）**：【事实】SQLite 无行级写锁、仅进程内 Lock 不跨进程安全、修改 DATABASE_URL 不自动切换现有连接、Windows 占用阻塞 rename/delete 且 symlink 需特权；相应租约锁/连接池重建/quarantine/对账/Windows 兼容方案为【设计提议】，正确性【待实际验证】。**TOCTOU 仅降低而非消除、租约锁非严格互斥、Windows 跨平台原子切换未验证**等限制如实写明，**不得通过改写措辞宣称问题已解决或已实现完全并发安全**。

---

## B–F 批次依赖（延后，本轮不审批）

> 仅登记方向与许可证风险，**本轮不批准、不安装**；进入对应批次前再逐项审批。

| 批次 | 能力 | 候选 | 许可证 | 备注 / 风险 |
|---|---|---|---|---|
| C 图谱 | 全局力导向/智能探索 | d3-force / cytoscape / sigma / vis-network / 既有 React Flow | ISC / MIT / MIT / (Apache-2.0 OR MIT) / MIT | React Flow+elkjs 已在依赖（层级布局）；力导向需新引擎，核对版本 LICENSE；**不得进 Core** |
| E 外部采集 | MCP Server | MCP Python SDK | MIT | 6 工具；核对版本；平台 ToS + 用户授权 |
| E 导入 | PDF 解析 | pypdf / pdfplumber / ~~PyMuPDF~~ | BSD-3 / MIT / **AGPL-3.0** | **PyMuPDF AGPL-3.0 许可证风险高，避免**；优先 pypdf/pdfplumber |
| E 导入 | HTML 解析 | selectolax / bs4 / lxml | MIT / MIT / BSD-3 | 核对版本 |
| E 采集 | 浏览器扩展 | MV3 / WXT / Plasmo | MIT（框架） | 最小权限、用户触发、平台 ToS；核对框架版本 LICENSE |

---

## 审批清单（本轮）

**优先评估、待批准（核对具体版本官方 LICENSE 后）**
- [ ] **CodeMirror 6**（Markdown 编辑器 + wikilink/标签补全）— MIT，核对拟用版本及 @codemirror/* 子包。
- [ ] **react-markdown**（预览渲染）— MIT，核对拟用版本；**须落实安全加固**（禁 raw HTML / URL 协议校验 / 安全自定义组件 / 无 dangerouslySetInnerHTML）。

**暂不批准（审查项六）**
- [x] ~~KaTeX / MathJax~~（数学公式，延后）
- [x] ~~PyYAML / python-frontmatter / ruamel.yaml~~（A1 用 Core stdlib 零依赖方案 + 原始文本兜底保真）
- [x] ~~DOMPurify / sanitize-html~~（react-markdown 默认禁 raw HTML，重评后暂不引入；启用 raw HTML 时再议）
- [x] ~~python-magic~~（附件 MIME 先用 stdlib 签名嗅探）

**延后（B–F，本轮不审批）**
- [ ] 图谱力导向引擎 / MCP SDK / PDF / HTML 解析 / 浏览器扩展框架（进入对应批次前逐项审批；**PyMuPDF AGPL-3.0 避免**）。

**硬约束**
- 编辑器/渲染/YAML/图谱/AI 平台 SDK **不进 Knowledge Core**。
- 本轮**不安装依赖、不改 lockfile**；最终批准前**核对具体版本官方 LICENSE**。
- A1 **零新增必需依赖**（含第五轮 quarantine/续租/来源身份/canonicalization_version/Manifest 对账/Windows 兼容，均用既有栈）；A2 仅 CodeMirror 6 + react-markdown 两项待批准（含安全加固）。
- **第五轮设计决策待审批**（非依赖安装）：GC quarantine 机制、来源身份持久化形态、租约参数与 TOCTOU 降级、GC 状态机、canonicalization_version 序列化细则、Manifest 对账、Windows 兼容策略——详见主设计 §7 第 15–21 项；本轮不替用户拍板。

---

## 声明

本表为选型对比与审批材料，**非安装记录**。本轮（第五轮）未安装任何依赖、未改 `uv.lock`/`package-lock.json`、未提交。许可证均为常见声明，**批准前以拟用具体版本官方 LICENSE 核实**。A-6 已与设计文档第四轮（P0-3 SQLite 租约锁/P0-4 GC 租约认领/P1-5 PG Staging 恢复/三 Hash/孤儿扫描）及**第五轮七项整改（R5-1 GC 持锁 quarantine/R5-2 跨实例来源身份/R5-3 租约续租与 TOCTOU/R5-4 GC 状态机含 cancelled/R5-5 canonicalization_version/R5-6 Manifest operation_id/generation_id/resource_version+崩溃对账/R5-7 Windows 兼容）**保持一致；A1 零新增必需依赖结论不变。CodeMirror 6 / react-markdown 仍待逐项审批（不自装）；PyYAML/KaTeX/DOMPurify/python-magic 暂不批准。第五轮新增机制均为设计提议、正确性待实际验证，TOCTOU/Windows 原子切换等限制如实写明，不宣称已解决。等待用户逐项审批与独立复审（第五轮冻结版，不再新增设计）。