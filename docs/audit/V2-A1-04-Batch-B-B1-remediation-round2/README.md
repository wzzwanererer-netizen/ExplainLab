# ExplainLab Batch B · B1 第二轮缺陷整改

- Batch A 基线：970c0d8ec05f0b8c68286839a56b14c74ea230c6
- 原始裁决：B1 BLOCKED。整改结果等候 Codex 独立复审及 ChatGPT 阶段验收。
- 判定依据：十份 Architecture Freeze 文档、原 B1 实施与验收报告、已知问题与原始日志，以及本轮任务所列、经此前 Codex BLOCKED 裁决核对的十项发现。独立审计全文未作为单独文件随工作树交付。
- 交付范围：六项 P1、四项 P2、定向回归、完整命令输出、工作区状态。到 B1 停止。

| 文件 | 内容 |
|---|---|
| [remediation-report.md](remediation-report.md) | 十项缺陷逐项对照及代码/验收映射 |
| [remediation-test-report.md](remediation-test-report.md) | 测试结果、跳过原因及断言调整 |
| [known-issues-and-risks.md](known-issues-and-risks.md) | 尚需真实环境或后续阶段验证的事项 |
| [git-state.md](git-state.md) | HEAD、分支、暂存、工作区快照 |
| [scope-classification.md](scope-classification.md) | 本轮变动和原有变动边界 |
| [SHA256SUMS](SHA256SUMS) | 项目根相对路径，覆盖本轮源码、测试、报告及日志 |

ZIP 保留项目根相对路径，并包含冻结设计、原 B1 报告和整改源码。独立复核时，以基线提交建立干净副本，将 ZIP 内容覆盖到副本，再按测试报告执行命令。旧尝试的截断日志保留为过程记录，以带退出码的最终日志为准。
