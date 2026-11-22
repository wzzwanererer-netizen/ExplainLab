# 已知问题与未验证项

本清单只记录**当前仍未闭环**的事项；已修复项见 `final-remediation-report.md`。任何“未验证”均未计为通过。

## A. 环境缺失导致的未验证（阻塞性，需独立环境）

1. **真实 PostgreSQL 全链路未验证**
   - 现状：Windows 无 docker/podman/psql/pg_ctl/postgres 服务；WSL Ubuntu 无 PostgreSQL、无 pip、无 SQLAlchemy；`EXPLAINLAB_PG_TEST_URL` 未设置。
   - 影响：178 项 PG 门控测试跳过；迁移 up/down、tsvector/触发器/级联、CJK ILIKE 回退、向量与混合检索、PG 并发锁行为均无本轮真实证据。
   - 处置：不伪造、不以 SQLite 替代；提供可执行清单 `postgresql-verification.md`。
   - 风险等级：高（部署目标为 PostgreSQL）。

2. **POSIX 完整链路仅部分验证**
   - 已验证：`0o600` 创建、ID 幂等/并发、无硬链接回退 `O_EXCL`、POSIX 目录 fsync、`os.replace` 原子替换、`write_all` EINTR 重试、跨进程锁竞争与释放（WSL 真实 Linux 原语）。
   - 未验证：完整 Journal 导入（`journal_store_full_import`），因 WSL 无法安装后端依赖；未运行 Linux 下的完整 pytest 套件。
   - 处置：不把 Windows 结果当作 POSIX 证据；见 `posix-verification.md`。

## B. 故障注入的覆盖边界（设计内局限）

3. **进程内异常 ≠ 真实断电/介质损坏**
   - 本轮注入的是 `InterruptedError`、fsync/close/replace/link 抛错与发布瞬间竞态；没有模拟内核崩溃、掉电、磁盘坏块、fsync 谎报成功。
   - 结论仅到“异常传播时不发布不完整文件、保留旧文件、清理临时文件”；不能据此宣称崩溃一致性已被穷尽证明。

4. **目录 fsync 在 Windows 为空操作**
   - `_sync_dir` 在 Windows 不做实际同步（平台不支持）；POSIX 探针已确认真实调用一次目录 fsync。
   - 本轮不改变该平台差异；部署到 Linux 时目录项持久性依赖该 fsync。

5. **close 失败的 fd 泄漏未以计数断言**
   - 实现上 `os.close` 位于 `finally`，不存在跳过关闭的代码路径；测试断言“文件语义正确”，未用 `/proc/self/fd` 或 `psutil` 统计 fd 数（Windows 下不可移植）。

6. **Journal replace 失败后的恢复**
   - 已断言旧 current 保留且 `.tmp` 清理；未单独构造“旧 current 为 PREPARED 且 replace 失败后再重启恢复”的组合场景。恢复逻辑本身由既有 `TestJournalRecovery` 与冻结集覆盖。

## C. 行为与性能权衡（已知、非缺陷）

7. **`identity_guard` 为全局 Journal 锁**
   - 导入/审核提交与 MATERIALIZE/ROTATE 全局互斥；并发导入吞吐受限。以一致性优先，未做细粒度锁优化（避免扩大改动面）。

8. **冲突策略为 fail-closed**
   - 导入/审核遇到已物化目标直接 409，不自动合并、不选边；用户需另行处理（符合 §22.2）。
   - 状态 1 条目导出后再导入仍允许（无 MATERIALIZE 记录），这是契约内行为，不是冲突。

9. **ROTATE 对冲突条目的处理保持原语义**
   - 冲突条目（state 3）在 ROTATE 中既不物化也不阻断整批；state 4 仍整体阻断。本轮未改变 D23 状态机。

## D. 测试卫生

10. **本轮曾产生重复测试类，已清理**
    - `test_batch_a_file_write.py` 曾追加与 `test_batch_a_fault_injection.py` 重复的 8 项；已移除重复副本，净修改为零（文件与第二轮审计快照逐字节一致）。

11. **前端构建 chunk 体积警告**
    - `graphLayout` chunk 1.46 MB（gzip 453 kB）触发 Vite 警告；既有问题，本轮不涉及前端产品行为，未处理。

## E. 流程状态

12. **未提交、未推送**
    - 工作树保持改动状态；未执行任何 Git 写操作；等待 ChatGPT 独立审计。
13. **未进入 Batch B，未改动冻结契约**
    - 见 `scope-classification.md`。