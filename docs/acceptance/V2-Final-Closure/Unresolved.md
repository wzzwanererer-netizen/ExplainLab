# ExplainLab V2 · Backend Final Closure 未解决项与诚实边界

1. **最终独立审计裁决尚未签发**：本轮状态为 `V2 BACKEND REMEDIATION COMPLETED / READY FOR FINAL INDEPENDENT REVIEW`，不得自行宣布最终 `PASS`。所有四项遗留证据缺口（GC-02 PG 并发、ORP-01 完整恢复链、ORP-05 真实子进程崩溃接管、PostgreSQL 索引提交故障注入）均已补齐真实环境证据，待独立审计复审裁决。
2. **全仓 Ruff 8 项历史归档错误**：`ruff check backend knowledge-core` 为 `All checks passed!`（`exit=0`）；全仓 `ruff check` 仍返回 `exit=1`（8 项错误均位于历史冻结/取证归档目录 `docs/acceptance/V2-A1-04-Batch-B-B1-environment-recovery/` 与 `docs/audit/V2-A1-04-Batch-B-freeze-review-package/`，按纪律不得修改历史证据）。
3. **Windows 根级回归跳过项口径**：Windows 默认 SQLite 套件中的跳过项严格属于 `EXPLAINLAB_PG_TEST_URL`（真实 PostgreSQL 门控）与 Windows 平台/权限条件，绝不冒充通过；对应 PostgreSQL 项均在 WSL2 Ubuntu ext4 + PostgreSQL 18.6 实机以 `0 skipped / exit=0` 独立取证。
4. **沿用既有平台与架构边界**：
   - POSIX 实测范围为 WSL2 Ubuntu `ext4`，Windows 目录断电耐久性沿用冻结设计边界。
   - 24h 时间语义通过生产代码实际检查的 DB 时间戳与磁盘 `mtime` 控制验证，不 sleep 24h，不伪造生产判断逻辑。
   - PostgreSQL `simple` 分词对无空格中文的 `ILIKE` 回退沿用 M5/ZIP-01 已记录局限。
5. **未开展后续阶段**：本轮未修改前端代码、未修改 Knowledge Core、未修改 Alembic 迁移、未修改依赖清单，未提前进入 Nesti 设计系统、前后端接通或浏览器端产品验收。
