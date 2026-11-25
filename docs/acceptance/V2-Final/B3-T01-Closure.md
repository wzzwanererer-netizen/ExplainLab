# ExplainLab V2 · B3-T01 接手验收

当前阶段为 B3-T01 整改收尾。Qoder 的既有审计报告和原始证据保留原样。

| 检查 | 当前结果 |
| --- | --- |
| Staging guard 覆盖 pending 的创建、写入和提交 | 已有实现。另修复一个提交已生效但 commit 与 rollback 都报错的窗口。现在提交尝试前标记保留，避免释放 guard 前误删已提交 pending 的 staging |
| 已应用附件重试的引用与 blob 一致性 | 新增真实 StorageKeyLock 保护。先关闭旧读会话，在锁内新读引用并关闭会话，再校验正式 blob。锁有竞争时请求返回 409，释放后正确复用 |
| POSIX 目录级 fsync | Windows 故障注入与 Ubuntu ext4 实机均通过 |
| Pending 查询与损坏 envelope | 保留既有数据库不可用时的 fail-closed 行为。另补齐保留键存在但值为 `null` 的情况，禁止将其误判为普通审核，清扫与直接清理均保留 staging |
| 空附件、损坏 ZIP、原始文件名 NUL、ZIP 总预算 | 保留 Qoder 的实现和回归，最新 Windows 专项已重跑 |
| B1/B2 生产基线与冻结文档 | 10 份冻结文档与 B1 正式包完全一致。B1/B2 专属源码和测试按原审核清单核对。共享 `main.py` 的唯一内容差异为将既有锁管理器传给 MarkdownService |

Windows 当前 B3 专项 **55 通过、1 跳过**，跳过原因为当前环境无法创建 symlink 或 junction。加入显式 null envelope 回归之前的 B3、Batch A、B1/B2 定向运行 **409 通过、11 跳过**，其中 5 项为 PostgreSQL 门控。真实 ZIP 的 100 MiB + 1 字节边界已重跑通过。

首轮根级运行在新用例的成功重试中遇到 50ms 测试预算导致的超时。已将测试短预算限定在争锁步骤，重试使用生产预算，断言保持。后续全量在当前生产源码上运行 **1,444 通过、221 跳过、0 失败**。仅含测试预算调整的当前工作树另做了上述完整 B3 专项。源码 Ruff 通过，仓库根 Ruff 记录 8 项历史归档问题。Git diff 空白检查通过。

当前受管 Windows 进程启动 Ubuntu 返回 `Wsl/E_ACCESSDENIED`，且未设置真实 PostgreSQL 测试 URL。真实 POSIX 验收入口已准备并交给普通 PowerShell。Windows 与故障注入结果仅用于其对应范围。

[基线核验](evidence/baseline-verification.log) · [接手差异](evidence/b3-t01-handoff.diff) · [当前源码摘要](evidence/b3-t01-source.sha256) · [Windows 专项日志](evidence/b3-t01-windows-final.log) · [Windows 专项 JUnit](evidence/b3-t01-windows-final.xml) · [Windows 定向运行](evidence/b3-t01-windows-targeted.log) · [初次根级失败日志](evidence/b3-t01-windows-full.log) · [根级复跑](evidence/b3-t01-windows-full-latest.log) · [100 MiB 边界](evidence/b3-t01-100mib.log) · [环境探针](evidence/environment-preflight.log) · [真实 POSIX 回归入口](evidence/run-b3-t01-posix.sh) · [Qoder 整改报告](../V2-A1-04-Batch-B-B3-T01/B3-T01-remediation-report.md)

## 当前质量门

- B3-T01 Windows 专项及 Backend + Knowledge Core 全量回归已完成。 [最终全量日志](evidence/b3-t01-windows-full-final.log) · [最终全量 JUnit](evidence/b3-t01-windows-full-final.xml)
- B3-T01 真实 POSIX 目录 `fsync` 已取得 ext4 实机复验证据，见下节。
- 本报告证据覆盖 B3-T01，B3-T02 及后续阶段结果由各阶段报告记录。

## Ubuntu ext4 补证（2026-11-24）

原始日志确认测试根位于 /dev/sdd 的 ext4 卷。JUnit 为 56 通过、0 跳过、0 失败、0 错误，退出码 0。已在 B3-T02 修改前比对 10 个 overlay 源码 SHA-256，全部一致。目录同步真实平台路径、失败注入和链接拒绝均在该批执行。B3-T01 实现质量门已达成，进入 B3-T02，正式裁决由独立审计负责。

[原始日志](evidence/b3-t01-posix.GwzYRVnh/pytest.log) · [JUnit](evidence/b3-t01-posix.GwzYRVnh/pytest.xml) · [源码 SHA-256](evidence/b3-t01-posix.GwzYRVnh/source-overlays.sha256)
