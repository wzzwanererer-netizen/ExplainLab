# 验收、风险及独立复审索引

- [53 项完整矩阵](docs/plans/V2-A1-04-Batch-B/acceptance-plan.md)：与审计前编号集合及顺序一致，均待验证。
- [50 条完整风险登记](docs/plans/V2-A1-04-Batch-B/risk-register.md)：6 条继承风险、44 条 Batch B 风险，原编号集合及顺序一致。
- [八项 P1 原问题](../original-audit/docs/audit/V2-A1-04-Batch-B-final-review/architecture-findings.md) · [整改前后](../remediation/docs/audit/V2-A1-04-Batch-B-remediation/remediation-report.md) · [验收映射](../remediation/docs/audit/V2-A1-04-Batch-B-remediation/updated-acceptance-mapping.md) · [剩余风险](../remediation/docs/audit/V2-A1-04-Batch-B-remediation/remaining-risks.md)。
- [稳定错误码完整登记与历史对照](stable-error-code-register.md)。

## 名称核对

### 验收
- `ATT-05`：原名称「`.svg` 或 `image/svg+xml`」，当前名称「声明 `image/svg+xml`；另以文本 MIME 提供合法 UTF-8 SVG 字符串」。

### 风险
- 行首名称无差异。

## 原审计 P2/P3 的复审口径

以下严重度与非阻塞分类沿用原审计。当前修订写入设计，运行结果仍待验证。复审者可核对分类或重新裁定。

| 编号 | 现有设计证据 | 原审计为何列为非阻塞 | 剩余证据 |
|---|---|---|---|
| F09 · P2 | API §2–7、§9；lifecycle §3 | 接口及兼容语义可在现有路由/DTO落实，无需新 schema，原归类非架构阻塞。 | 逐路由核对批量兼容、状态/错误码和脱敏。 |
| F10 · P2 | architecture §4.2；review §2、§5.2；R1-IMP-08 | 业务①与索引②已拆分，剩余为①已提交时的索引失败反馈及取证。 | 真实注入同步和②提交失败，复核响应和清理。 |
| F11 · P2 | GC §4.3、§5、§6.2；GC-04/08/09 | 计时起点和终态调度可用既有字段及状态机表达，不要求重设 GC 架构。 | 实测窗口、忙重试、认领耗尽及第八次失败终态。 |
| F12 · P2 | storage §3、§5–7；ATT-09/12 | 文件原语的错误分流与句柄生命周期可在既有存储接口实现。 | 实测 NTFS 占用/句柄、POSIX 同步及真实失败。 |
| F13 · P3 | roadmap §2–7、architecture §2/6 | 任务归属、措辞和消费接口的可追踪性问题，无需新增阶段。 | B1–B5 对照路线检查接口及写事务所有权。 |

历史验收与风险行首从审计前版本读取，本包归档的是当前完整原件。证据源：[验收历史快照](https://chatgpt.com/library?file_id=libfile_264f3e581fa48191a845bbdc5c65ff73&account_id=personal) · [风险历史快照](https://chatgpt.com/library?file_id=libfile_57b9566b3e248191b6fb7fafeb838cb2&account_id=personal)。
