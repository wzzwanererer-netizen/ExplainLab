# V2 · A1-04 · Batch A 暂存格式检查独立报告

- 报告日期：2026-11-22
- 基线 HEAD：`784b1248065424e07273b272d6016cc121bc606c`
- 分支：`fix/m0-admission-and-m5-regressions`
- 检查对象：已暂存的 105 个 Batch A 文件
- 检查命令：`git diff --cached --check`
- 退出码：`2`
- 结论：18 处格式提示，全部为空白字符类提示；**业务代码与测试 0 处**，不影响暂存数量和冻结边界。

## 1. 执行摘要

| 项目 | 结果 |
|---|---|
| 暂存文件总数 | 105（8 M + 97 A） |
| `git diff --cached --check` | 退出码 2，18 处提示 |
| 其中 trailing whitespace | 17 处 |
| 其中 new blank line at EOF | 1 处 |
| 业务代码 / 测试提示 | 0 处 |
| 证据日志 / diff 快照提示 | 17 处 |
| 正式设计文档提示 | 1 处（`risk-register.md` 文件末尾空行） |
| 是否修改文件 | 否 |
| 是否改变暂存集 | 否，仍为 105 项 |

代码与测试单独检查通过：

```text
git diff --cached --check -- backend knowledge-core
退出码：0
```

因此，以下 18 项均不涉及 Python 业务逻辑、测试断言、迁移、依赖或配置内容。

## 2. 18 处提示逐项清单

| # | 文件 | 行 | 类型 | 归类 | 说明 |
|---:|---|---:|---|---|---|
| 1 | `docs/acceptance/V2-A1-04-Batch-A/evidence/frontend-regression.txt` | 46 | trailing whitespace | 初始验收证据 | 原始 Vite 报告行末尾带空格/ANSI 控制序列 |
| 2 | `.../final-remediation/diffs/backend__app__api__routes__governance.py.diff` | 7 | trailing whitespace | diff 快照 | unified diff 中新增空行以 `+ ` 表示，末尾保留一个空格 |
| 3 | `.../final-remediation/diffs/backend__app__services__import_review_hook.py.diff` | 16 | trailing whitespace | diff 快照 | 同上 |
| 4 | `.../final-remediation/diffs/backend__app__services__source_identity.py.diff` | 18 | trailing whitespace | diff 快照 | 同上 |
| 5 | `.../final-remediation/diffs/backend__app__services__source_identity.py.diff` | 37 | trailing whitespace | diff 快照 | 同上 |
| 6 | `.../final-remediation/diffs/backend__app__services__source_identity.py.diff` | 82 | trailing whitespace | diff 快照 | 同上 |
| 7 | `.../final-remediation/diffs/backend__app__services__source_identity.py.diff` | 105 | trailing whitespace | diff 快照 | 同上 |
| 8 | `.../final-remediation/evidence/frontend-build.txt` | 22 | trailing whitespace | 验收证据 | 原始 Vite 报告行末尾带空格/ANSI 控制序列 |
| 9 | `.../final-remediation/evidence/postgresql-probe.txt` | 16 | trailing whitespace | 验收证据 | 原始 WSL 输出行末尾空白 |
| 10 | `.../final-remediation/evidence/postgresql-probe.txt` | 18 | trailing whitespace | 验收证据 | 原始 WSL 输出（含环境提示与非 UTF-8 字节）行末尾空白 |
| 11 | `.../final-remediation/remediation-final.diff` | 18 | trailing whitespace | diff 快照 | unified diff 中新增空行以 `+ ` 表示 |
| 12 | `.../final-remediation/remediation-final.diff` | 37 | trailing whitespace | diff 快照 | 同上 |
| 13 | `.../final-remediation/remediation-final.diff` | 82 | trailing whitespace | diff 快照 | 同上 |
| 14 | `.../final-remediation/remediation-final.diff` | 105 | trailing whitespace | diff 快照 | 同上 |
| 15 | `.../final-remediation/remediation-final.diff` | 215 | trailing whitespace | diff 快照 | 同上 |
| 16 | `.../final-remediation/remediation-final.diff` | 245 | trailing whitespace | diff 快照 | 同上 |
| 17 | `docs/acceptance/V2-A1-04-Batch-A/remediation/evidence/05-frontend.txt` | 46 | trailing whitespace | 整改证据 | 原始 Vite 报告行末尾带空格/ANSI 控制序列 |
| 18 | `docs/plans/V2-A1-04-risk-register.md` | 285 | new blank line at EOF | 正式设计文档 | 文件末尾多出一个空行 |

## 3. 分类统计

### 3.1 按类型

| 类型 | 数量 | 说明 |
|---|---:|---|
| `trailing whitespace` | 17 | 证据日志、diff 快照中的行尾空格 |
| `new blank line at EOF` | 1 | `risk-register.md` 文件末尾空行 |
| **合计** | **18** | 无代码/测试类提示 |

### 3.2 按文件类别

| 类别 | 数量 | 文件 |
|---|---:|---|
| 初始验收证据 | 1 | `evidence/frontend-regression.txt` |
| final-remediation 证据 | 3 | `frontend-build.txt`、`postgresql-probe.txt`（2 处） |
| 整改证据 | 1 | `remediation/evidence/05-frontend.txt` |
| final-remediation diff 快照 | 12 | `diffs/*.diff`（6 处）+ `remediation-final.diff`（6 处） |
| 正式设计文档 | 1 | `docs/plans/V2-A1-04-risk-register.md` |
| **合计** | **18** | |

## 4. 成因分析

### 4.1 证据日志

前端证据来自真实 Vite 输出，其中 reporter 行包含 ANSI 控制序列和行尾空格；PostgreSQL 探针证据来自真实 WSL 命令输出，包含 Windows/WSL 环境提示和非 UTF-8 字节。这些文件是**原始输出快照**，保留原样比格式化更重要。

### 4.2 diff 快照

`diffs/*.diff` 与 `remediation-final.diff` 是 unified diff 文本。diff 中“新增空行”的标准表示是 `+ `（加号后一个空格），因此该行天然带尾随空格。这是 diff 格式本身的结果，不是业务代码中的尾随空格。

### 4.3 正式设计文档

`V2-A1-04-risk-register.md` 第 285 行为文件末尾新增空行。该文件属于已冻结的 R1.3 设计文档，当前 SHA-256 为：

```text
418c01d8345dba2ad029c449b98bc16f8402bb1735ee9f536809dd201268de37
```

如修改该空行，将改变设计文档哈希，并破坏 R1.3 merge report 的冻结记录；因此本轮未处理。

## 5. 影响评估

| 维度 | 影响 |
|---|---|
| 代码/测试正确性 | 无影响；`backend` 与 `knowledge-core` 的 cached check 退出码为 0 |
| 暂存数量 | 无影响，仍为 105 |
| 冻结边界 | 无影响；未修改 A1-02/A1-03/V1/Schema 文件 |
| 证据完整性 | 17 处属于原始证据/diff 快照，清理会改变证据字节 |
| 提交动作 | Git 默认不会仅因 `git diff --cached --check` 失败而拒绝 commit；但若验收要求该命令必须为 0，则当前状态不满足 |
| 审计可复核性 | 保留原始证据有利于复核；代价是 `--check` 返回 2 |

## 6. 处置建议

### 方案 A：接受格式豁免（建议）

将这 18 处定性为**证据保真导致的空白字符提示**，不作为代码质量失败项。理由：

1. 业务代码与测试的 `--check` 已通过；
2. 17 处位于原始日志或 diff 快照，清理会改变证据内容；
3. 唯一正式文档提示涉及已冻结的 `risk-register.md`，清理会破坏 R1.3 哈希冻结；
4. 暂存集仍严格为 105 项，未引入无关文件。

### 方案 B：清理后再冻结

需要修改 `risk-register.md`、规范化证据/diff 文件，并重新生成 `final-remediation/SHA-256SUMS`、重新核对 R1.3 设计哈希、重新暂存。该方案会超出当前“只暂存、不修改文件”的边界，本轮不执行。

### 方案 C：从提交中移除证据/diff

可使 `--check` 更容易通过，但会破坏 105 项验收完整性，并导致 final-remediation 包无法自校验，不建议。

## 7. 当前状态确认

```text
HEAD                         784b1248065424e07273b272d6016cc121bc606c
分支                         fix/m0-admission-and-m5-regressions
暂存文件                     105（8 M + 97 A）
未暂存 tracked               0
未跟踪                       101（原 100 个排除项 + 本报告 1 个）
stash                        0
commit                       未执行
push                         未执行
工作树文件修改               未执行
```

本报告自身位于 `docs/audit/`，属于审计材料，**未加入暂存集，不改变 105 项提交边界**。

## 8. 结论

18 处提示全部为空白字符类格式提示，其中 17 处位于证据日志或 diff 快照，1 处位于已冻结的风险登记文档末尾。没有业务代码、测试、迁移、依赖或配置质量问题。当前暂存集仍为 105 项，冻结边界未变。

建议审计方选择**方案 A：格式豁免**，或明确要求执行方案 B 并授权修改文件、重算哈希和重新暂存。在此之前不执行 commit、push 或任何文件修改。