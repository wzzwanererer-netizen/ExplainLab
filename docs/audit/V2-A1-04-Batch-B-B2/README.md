# ExplainLab V2 · A1-04 Batch B · B2 附件 API · 独立审核包

**状态：B2 IMPLEMENTED / PENDING INDEPENDENT REVIEW（2026-11-24，北京时间）。**
本包记录 B2-T02 的实现、真实 SQLite 自测、B1 定点回归与环境边界。它**不是**正式验收通过，也不表示已获准进入 B3。

| 项目 | 结果 |
|---|---|
| B2-T01 纯函数校验 | 已完成（历史记录见 `docs/acceptance/V2-A1-04-Batch-B-B2-T01.md`） |
| B2-T02 HTTP 附件 API | 已实现：上传 / 列表 / 下载 / 删除 |
| B2 API 专项测试 | 22 通过，0 失败（真实 SQLite 文件库 + `tmp_path` 文件系统） |
| B1 附件/锁/GC 定点回归 | 184 通过，3 跳过 |
| 全仓 backend + core | 1394 通过，208 跳过，0 失败 |
| `ruff check backend knowledge-core` | 通过（退出 0） |
| 真实 PostgreSQL HTTP 路径 | **未执行（环境受限）**：本机无 `EXPLAINLAB_PG_TEST_URL` |
| ATT-11 的 24h ORP 收敛 | 未实现；属 B5，未提前开发 |
| Git | 未提交、未推送；工作树含 B1-final 与 B2 变更 |

## 文档

- [实施报告](implementation-report.md)：范围、文件、数据/事务/锁边界、错误映射、未做项。
- [自测报告](self-verification-report.md)：环境、命令、ATT-01…13 逐项状态、跳过分类。
- [验收映射](acceptance-mapping.md)：ATT-01…13 与 22 项测试逐项对应，明确未验证项。
- [测试统计核验报告](test-count-verification.md)：184/182 冲突的原始日志、命令范围与复跑结论。
- [未解决问题](unresolved.md)：PG HTTP 未验证、ORP/B5、历史排序问题、既有 ruff 历史问题。
- [Git 变更摘要](git-change-summary.md)：B2 新增/修改与 B1-final 未提交差异的边界。
- [B1-final 与 B2 边界](code-review/b1-vs-b2-boundary.md)：无 B1 提交时的两类差异、哈希与基线重建证明。
- [独立审核重点定位](code-review/audit-focus.md)：上传去重、锁、发布、归档、fencing、事务、下载、删除、并发的文件/函数/行号。
- [B2 任务清单与验收映射](../../acceptance/V2-A1-04-Batch-B-B2-task-list.md)。

## 代码审查材料

- 索引：[`code-review/README.md`](code-review/README.md)。
- 完整当前源码：[`code-review/production-current/`](code-review/production-current/)（3 个 B2 新生产文件、3 个 B2 修改文件、2 个 B2 测试文件）。
- B2-only 差异：[`code-review/diffs/`](code-review/diffs/)。
  - `b2-new-production-files.patch`：`attachment_validation.py`、`attachments.py`、`routes/attachments.py` 全文新增。
  - `b2-schemas-dependencies.patch`：`schemas.py`、`dependencies.py` 的 B2 hunk。
  - `main-b2-only.patch`：重建 B1-final `main.py` → 当前的四段 B2 装配。
  - `b2-production.diff`：以上生产差异合并视图。
  - `b2-new-tests.patch`：B2 测试全文新增。
- 机械全量差异：[`working-tree-tracked-vs-HEAD-970c0d8.patch`](code-review/diffs/working-tree-tracked-vs-HEAD-970c0d8.patch)；
  **含 B1-final + B2，不是 B2-only**。
- B1-final `main.py` 重建基线：[`baselines/main-b1-final-reconstructed.py`](code-review/baselines/main-b1-final-reconstructed.py)；
  SHA-256 与 B1 验收清单一致（`2c5ceccd…`），证明 B2-only diff 的基线可复核。
- 哈希清单：[`B2-files.sha256`](code-review/B2-files.sha256)、[`B1-boundary-files.sha256`](code-review/B1-boundary-files.sha256)。

## 证据

原始日志位于 [`evidence/`](evidence/)：

- `b2-api.log`：B2 API 22 项。
- `b1-targeted-regression.log`：附件存储/Windows/锁/GC/API 合并回归。
- `full-suite.log`：全仓 backend + core。
- `skip-summary.log`：PG 与平台门控跳过明细。
- `ruff-backend-core.log`：Backend/Core Ruff。
- `b2-diff-apply-verification.log`：B2-only 生产差异应用到重建基线后，六文件与工作树逐字节一致的验证。
- `git-status.txt`、`git-diff-stat.txt`、`b2-changes.patch`、`b2-files-sha256.txt`、`commands.txt`、[`SHA256SUMS`](SHA256SUMS)。

## 范围边界

- 只实现冻结路线图 B2-T01/T02；未实现 B3 staging/import、B4 审核集成、B5 GC/ORP worker 或管理 HTTP 端点。
- 未修改 `docs/plans/V2-A1-04-Batch-B/` 冻结契约；未改 Core、端口、数据库 schema、Alembic 迁移、依赖清单。
- 复用 B1 的 `attachment_storage`、`storage_lock`、`SQLAlchemyAttachmentRepository`、`SQLAlchemyGcTaskRepository`；不重写底层发布/锁/仓储能力。
- 前端未改动，本包不声称前端验收。

## 审核入口

请以冻结 `implementation-roadmap.md` §4 B2 与 `acceptance-plan.md` ATT-01…13 为依据，核对：

1. 四路由的状态码、稳定错误码、响应头与 item 作用域隔离；
2. 上传顺序：archived 早拒 → 解码校验 → 临时写 → key 锁 → no-clobber 发布 → 受保护 item → 引用 flush → 路由唯一 commit → 锁释放；
3. 下载是否只使用一次打开并校验的同一句柄，不重开路径；
4. 删除最后引用才入队 `gc_task pending`，共享引用不入队，物理文件不由 B2 删除；
5. 归档竞态、锁超时、commit 失败、损坏/缺失 blob 的零写入或残留边界；
6. PG HTTP 未执行与 ATT-11 ORP/B5 未实现的如实标注。