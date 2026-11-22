# V2 · A1-04 · Batch A 已知问题

- 日期：2026-11-22
- 说明：以下均为**未验证或明确不支持**，不得在审计中计为通过。

## 1. 真实 PostgreSQL 未验证（阻断项）

- 环境无 `EXPLAINLAB_PG_TEST_URL`、`psql`、`pg_isready`、`docker`。
- 未在真实 PG 上执行：Alembic up/down、导入/导出、身份 Journal、并发锁、审核 hook、索引同步。
- 现有 PG 测试模块全部 skip（178 项 skip 的主要来源）。
- 未虚报连接成功；未用离线 SQL 代替真实数据库。

## 2. R1.3-ID-02 / ID-05 崩溃矩阵未穷尽

已覆盖：

- PREPARED MATERIALIZE：DB 空、DB 等于目标、DB 其他值、损坏 JSON、校验和不符。
- DB 写入后、COMMITTED 前崩溃。
- COMMITTED 未归档恢复。
- current/archive 同 operation_id 同内容去重；archive 损坏。
- ROTATE：PREPARED + 旧 ID、PREPARED + 新 ID、ID 替换前/后崩溃、第二次独立 rotate。

未逐一注入：

- Journal 写前崩溃；
- PREPARED 写入后、DB 写入前崩溃；
- 归档临时文件写前/后、同卷 rename 前后、目录同步后崩溃；
- 移除 current 前/后崩溃；
- 归档失败后再次 rotate 的完整拒绝路径（部分由当前 Journal 存在阻止，但未逐点测试）；
- 归档 `operation_id` 同内容 no-op / 异内容冲突的端到端重复调用；
- Windows 与 POSIX 双实机的目录同步差异。

因此 ID-02/ID-05 只能记 **PARTIAL**。

## 3. 缺少 `rotate-instance-id` CLI

- 服务层 `SourceIdentityService.rotate` 已实现并由真实 DB/FS 测试覆盖。
- 但验收矩阵 R1.2-ID-03 / R1.1-OPS-06 要求的 CLI（停后端、持同一 OS 锁、显式确认、原子更换、operation journal）未提供。
- 未宣称 CLI 可用。

## 4. 真实 Uvicorn reload / 多 worker 未实测

- 代码有 `_configured_workers() > 1` 拒绝守卫；未启动真实 `uvicorn --workers 2` 或 `--reload` 验证交接。
- 进程锁单实例语义已用真实子进程验证；reload supervisor 行为未实测。

## 5. Windows 文件权限/不可写目录未注入

- 未在 Windows 上模拟空数据根目录不可写、ACL 拒绝、只读文件等场景。
- `source-instance-id` 损坏、非法、缺失、并发创建已覆盖；权限拒绝未覆盖。

## 6. 持久性声明边界

- Windows 目录 `fsync` 为 best-effort；本实现**不宣称断电持久**。
- 文件原子替换（`os.replace`/硬链接）已实现，但未做断电/掉盘实验。

## 7. 附件与 Batch B 能力

- 附件导入、附件导出、附件审核明确拒绝（固定稳定码），零附件写入。
- 未实现附件 staging、GC、Backup/Restore、Batch D 网络能力；报告中未宣称完成。

## 8. 审核 hook 边界

- Batch A 只支持非附件 envelope。
- approve 的 Core 四字段与 hook 字段在同一事务；hook 故障回滚已测。
- 附件 envelope 在写任何导入字段前返回 `ATTACHMENT_REVIEW_UNSUPPORTED`。
- 未覆盖 Batch B 的附件引用/物理文件/悬空清理。

## 9. 并发验证环境

- 同/异身份并发、event loop 探针、锁超时均在单进程真实 SQLite + 真实线程/子进程下验证。
- 未在多机、多进程共享 PostgreSQL、网络延迟、数据库死锁场景下验证。
- SQLite 写并发受 `busy_timeout=5000` 保护；未做高争用压力测试。

## 10. 文档与范围

- 未修改 `MILESTONES.md`；未自行宣布 Batch A 完成或进入下一里程碑。
- 本轮工作树包含此前轮次未提交的设计/审计文档，未清理、未提交，避免覆盖他人改动。
- 验收结论为“有条件通过”，最终以独立审计为准。