# B2 审核整改 · Git 变更摘要

- 审核基线是原始 `ExplainLab-B2-Audit-Package.zip`，SHA-256 `aa4eecb47e38d930ff304bfbb5f58aa70903a900ade4ccda8ec282f14a3d76e7`。基线 ZIP 内部清单和源码哈希已逐项核验。
- 相对该基线，本轮代码差异只涉及 `backend/tests/test_attachment_api.py`，增加 ATT-12 与真实 PG HTTP 验收。原 B2 生产实现、B1 实现与 B1 测试保留原有内容。
- `git diff --stat` 中的生产改动来自进入本轮前既有的 B1/B2 工作树。由于 API 测试本身尚未跟踪，整改专属差异单独从审核包里的原始文件生成。
- HEAD 为 `970c0d8ec05f0b8c68286839a56b14c74ea230c6`。无暂存、提交、推送或里程碑晋级。冻结设计、Knowledge Core、Alembic 目录和依赖清单均未修改。

[整改专属差异](evidence/remediation-test-only.diff) · [Git 原始快照](evidence/git-status.log) · [审核基线核验](evidence/baseline-verification.log)
