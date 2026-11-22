# V2 · A1-04 · Batch A 最终整改与验证包（final-remediation）

- 仓库：`D:\ExplainLab`
- 分支：`fix/m0-admission-and-m5-regressions`
- HEAD：`784b1248065424e07273b272d6016cc121bc606c`（未改动、未提交）
- 时间：2026-11-22（亚洲/上海）
- 状态：**整改与可执行验证已完成，停止并等待 ChatGPT 独立审计**；未进入 Batch B。

## 结论摘要

| 项目 | 结论 | 说明 |
| --- | --- | --- |
| P1-01 MATERIALIZE 冲突零写入 | 已修复 / 已验证 | 先只读分类，冲突在创建实例 ID 之前返回；7 项新测试断言 ID/DB/Journal/归档零变化 |
| P1-02 导入不得制造身份冲突 | 已修复 / 已验证 | 直接导入、批量导入、审核批准三条路径 fail-closed；Journal 锁串行化分类+写入+提交；7 项新测试 |
| P1-03 ROTATE 冲突专项 | 已验证（不改语义） | 冲突条目既不物化也不覆盖，其他合法 2a 继续；审计摘要一致；2 项新测试 |
| P2-01 InterruptedError | 已验证 | 重试、连续中断、中断后 OSError 传播；3 项新测试 |
| P2-02 fsync 失败 | 已验证 | Journal current/archive、ID 创建/回退/replace 五路径；5 项新测试 |
| P2-03 close 失败 | **已修复真实缺陷** / 已验证 | 硬链接不受支持时的回退路径，fsync 成功后 close 抛错会误删有效正式 ID；已修复并锁定；5 项新测试 |
| P2-04 os.replace 失败 | 已验证 | current/ID replace 保留旧值并清理临时文件；归档改用原子不覆盖发布；3 项新测试 |
| P2-05 os.link FileExistsError | 已验证 | 不覆盖既有 ID、复核内容、不误入回退删除；2 项新测试 |
| P2-06 归档竞态 | 已修复 / 已验证 | 以 `os.link`（或 `O_EXCL` 回退）原子发布并复核字节，消除“检查后 replace”竞态；5 项新测试 |
| 真实 PostgreSQL | **未验证（环境不具备）** | 无 docker/podman/psql/pg_ctl/服务；`EXPLAINLAB_PG_TEST_URL` 未设置，178 项 PG 门控测试跳过；未伪造、未用 SQLite 替代，附可执行清单 |
| POSIX | **部分验证** | WSL Ubuntu 真实 Linux 原语 9 项 PASS；完整 Journal 导入 UNVERIFIED（WSL 无 pip/SQLAlchemy），未用 Windows 顶替 |

新增测试合计 **39 项**（P1-01 7、P1-02 7、P1-03 2、P2 共 23）。全量 Python：**1124 passed, 178 skipped**；Batch A 聚焦：**166 passed**；冻结集（A1-02/A1-03/V1）：**417 passed**；Ruff 全仓通过；前端 72 passed / typecheck / build 通过。

## 包内文件

| 文件 | 内容 |
| --- | --- |
| `README.md` | 本文件：入口、结论、包结构、停止声明 |
| `final-remediation-report.md` | 逐项缺陷、实现、设计取舍、修改文件、before/after SHA-256 |
| `final-test-report.md` | 完整测试矩阵（命令/起止时间/原始输出/退出码/计数/跳过原因） |
| `final-known-issues.md` | 未验证项、残余风险、明确边界 |
| `postgresql-verification.md` | PG 真实状态 + 可直接执行的验证清单 |
| `posix-verification.md` | POSIX 已验证/未验证拆分与探针说明 |
| `git-state.md` | HEAD/分支/工作树/本轮修改归属；未执行任何 Git 写操作 |
| `scope-classification.md` | 代码/测试/文档/证据分类与冻结边界核对 |
| `before-sha256.tsv` | 6 个本轮修改文件的 before/after SHA-256 |
| `before/` | 本轮整改前快照（3 个来自第二轮审计快照，3 个逆向重建） |
| `diffs/` | 6 个逐文件统一 diff（整改前 → 当前） |
| `remediation-final.diff` | 上述 diff 合并 |
| `evidence/` | 所有命令原始输出与探针脚本 |
| `SHA-256SUMS` | 本包全部文件的 SHA-256 |

## 取证与复现

- 所有测试/构建命令均在 `evidence/*.txt` 中保留 `command`、`cwd`、`start`、`end`、`exit_code` 与原始输出。
- 整改前快照由 `evidence/reconstruct_before.py` 逆向应用本轮编辑生成；每处替换要求“当前片段恰好出现 1 次”，失败即中止。
- `before-sha256.tsv` 的哈希基于磁盘原始字节；本轮未触碰的 `file_write.py` 与第二轮审计快照逐字节一致。
- 复现整改前快照：`python docs/acceptance/V2-A1-04-Batch-A/final-remediation/evidence/reconstruct_before.py`。

## 冻结边界

未修改 A1-02 Core Hash 契约、A1-03 V1 契约、D22/D23/D24、Canonical JSON v1、数据库 schema/迁移、身份状态定义、Journal 状态机、ImportOrigin 全量审计规则、MILESTONES 阶段拆分、依赖与锁文件。详见 `scope-classification.md`。

## 停止声明

本包完成后未执行任何 `git commit/push/add/reset/clean/stash/checkout`，未删除历史证据，未覆盖既有审计包，未启动 Batch B。**等待 ChatGPT 独立审计，不自行宣布通过或进入下一阶段。**