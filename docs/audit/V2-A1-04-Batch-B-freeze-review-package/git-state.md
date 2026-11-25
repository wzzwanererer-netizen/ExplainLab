# Git 与环境状态

- 分支：`fix/m0-admission-and-m5-regressions`
- HEAD：`970c0d8ec05f0b8c68286839a56b14c74ea230c6`
- 取证环境：Windows-10-10.0.26300-SP0；git version 2.55.0.windows.5；Python 3.10.11。
- 取证时间：2026-11-23T02:25:18+00:00 UTC。
- Git 查询禁用 optional locks，索引与 HEAD 不变。以下为创建本复审目录前的快照。

## git status --short

~~~text
?? docs/acceptance/V2-A1-04-Batch-A/audit-round2/
?? docs/acceptance/V2-A1-04-Batch-A/final-remediation/final-review/
?? docs/audit/V2-A1-03-final-stage-audit/
?? docs/audit/V2-A1-04-Batch-A-format-check-report.md
?? docs/audit/V2-A1-04-Batch-B-final-review.zip
?? docs/audit/V2-A1-04-Batch-B-final-review/
?? docs/audit/V2-A1-04-Batch-B-preflight/
?? docs/audit/V2-A1-04-Batch-B-remediation-review.zip
?? docs/audit/V2-A1-04-Batch-B-remediation/
?? docs/audit/V2-A1-04-R1-independent-review.md
?? docs/audit/V2-A1-04-technical-verification.md
?? docs/plans/A1-04/
?? docs/plans/V2-A1-04-Batch-B/
~~~

## git diff --stat

~~~text
(empty)
~~~

## git diff --cached --stat

~~~text
(empty)
~~~

## Batch B 十份设计文档

`git ls-files --stage -- docs/plans/V2-A1-04-Batch-B` → 空输出，十份均未跟踪。当前工作树内容已逐份原样纳入。未跟踪文件不会出现在 git diff --stat。

~~~text
?? docs/plans/V2-A1-04-Batch-B/README.md
?? docs/plans/V2-A1-04-Batch-B/acceptance-plan.md
?? docs/plans/V2-A1-04-Batch-B/active-review-integration.md
?? docs/plans/V2-A1-04-Batch-B/api-contracts.md
?? docs/plans/V2-A1-04-Batch-B/architecture.md
?? docs/plans/V2-A1-04-Batch-B/attachment-lifecycle.md
?? docs/plans/V2-A1-04-Batch-B/gc-and-orphan-recovery.md
?? docs/plans/V2-A1-04-Batch-B/implementation-roadmap.md
?? docs/plans/V2-A1-04-Batch-B/risk-register.md
?? docs/plans/V2-A1-04-Batch-B/storage-and-lock-contract.md
~~~

## 其他材料及范围

- 当前跟踪文件变更：空。 本轮纳入全部指定目录的设计文件、整改记录和原独立审计。
- 另有未跟踪的 Batch A 旧验收记录、Batch B preflight、早期 independent/technical verification 报告、上一轮两个 ZIP，以及 `docs/plans/A1-04/R1.1-amendment/` 的旧 ZIP。它们列于状态快照，作为历史辅助/重复件留在仓库；R1.1 旧 ZIP 不作当前 R1.3 基线。其他项目/阶段审计同样不属于本包。
- Batch A 四份主设计件及 R1.3 入口、合并报告从当前 HEAD 按 Git blob 提取，§22 和 §L 提供 D22–D24 原裁决。位置：

~~~text
HEAD:docs/plans/V2-A1-04-implementation-plan.md:986:## 22. R1.3 权威修订（合并 D22–D24，冲突以本章为准）
HEAD:docs/plans/V2-A1-04-implementation-plan.md:993:### 22.1 D22：exporter 与 Hash 解耦（传输元数据，不参与文档身份计算）
HEAD:docs/plans/V2-A1-04-implementation-plan.md:1032:### 22.2 D23：本地文档身份初始化（既有 DB 字段 + data 目录 Journal）
HEAD:docs/plans/V2-A1-04-implementation-plan.md:1348:### 22.3 D24：HTTP 本机安全边界（默认 loopback + 请求校验）
HEAD:docs/plans/V2-A1-04-open-decisions.md:453:## L. R1.3 决策台账（D22–D24，权威，关闭 R1.2 待决项）
~~~
