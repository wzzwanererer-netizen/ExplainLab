# B3-T01 独立审计包

**状态：B3-T01 IMPLEMENTED / PENDING INDEPENDENT REVIEW**

## 当前整改复审包

- ZIP：`ExplainLab-B3-T01-Remediation-Audit-Package.zip`
- SHA-256：`ed2ba5bbee0acd80c5a98f9650480ae10459578ae589a7758be50d278c2b34cf`
- 大小：148,729 bytes
- 内容：
  - `REVIEW-PROMPT.md`：复审重点、命令、已知未验证项；
  - `acceptance/`：整改报告、专项证明、字段映射、原始日志（含 `evidence/remediation/`）；
  - `source/`：B3-T01 源码/测试精确快照（5 个文件）；
  - `SOURCE-SHA256SUMS`、`PACKAGE-SHA256SUMS`。

验证：

```bash
unzip ExplainLab-B3-T01-Remediation-Audit-Package.zip -d b3
cd b3
sha256sum -c PACKAGE-SHA256SUMS
sha256sum -c SOURCE-SHA256SUMS
```

已实际解压验证：57/57 文件 OK，5/5 源码 OK。包内无 `.env`、`.db`、密钥或前端依赖目录。

## 历史初始审计包

- `ExplainLab-B3-T01-Audit-Package.zip`（初版实现，不含本轮整改）
- SHA-256：`536638fcc55da3b5e377c60ccaacbf54c7a48da7a7bf2895e446ef6c61bc2b63`

保留用于对照，不应作为整改后实现的最新依据。

## 边界

未提交、未推送；未实现 B3-T02/B4/B5。真实 PostgreSQL、真实 POSIX 主机、进程 kill/断电一致性未验证。