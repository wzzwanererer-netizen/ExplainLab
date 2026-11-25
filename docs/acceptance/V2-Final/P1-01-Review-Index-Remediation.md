# ExplainLab V2 · P1-01 审批响应整改

`approve_review` 在业务提交并退出业务 Session、审核锁与来源锁后调用统一的索引同步入口。有无附件的审批均返回已提交的批准结果。Draft 直接应用和版本恢复复用该入口。恢复路径在业务事务内生成响应对象，索引阶段使用独立 Session。索引异常仅写入异常类型和稳定警告码 `REVIEW_INDEX_SYNC_FAILED`，由索引 Session 结束其事务。共享向量索引同步在模型故障时也只记录稳定警告码与异常类型。Core ReviewService 的事务契约照旧。

Windows 定向复验覆盖普通审核、无附件 Active import、有附件审批、Draft 直接应用和版本恢复。故障从真实索引调用与真实 Session 提交边界注入。测试核对业务状态在独立读会话已可见、业务与索引 Session 不同、成功响应、脱敏警告、终态重试及审核数量。

[P1 7 项复验日志](evidence/remediation-windows-p1-current.log) · [JUnit XML](evidence/remediation-windows-p1-current.xml) · [审计基线差异](evidence/remediation-from-audit.patch)
