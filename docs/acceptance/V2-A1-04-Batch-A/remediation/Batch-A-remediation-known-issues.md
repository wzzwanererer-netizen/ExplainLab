# V2 · A1-04 · Batch A 整改已知问题

- 日期：2026-11-22
- 范围：仅 P1 身份并存冲突、P2 文件短写整改
- 说明：以下为**未验证或未覆盖**项，不得计为通过。

## 1. 真实 PostgreSQL 未验证

- 环境无 `EXPLAINLAB_PG_TEST_URL`、`psql`、`pg_isready`、`docker`。
- 未在真实 PG 上执行：迁移、导入/导出、身份 Journal、并存冲突分类、并发锁。
- PG 门控模块全部 skip；178 项 skip 以此为主。
- 未虚构 PG 连接或结果。

## 2. P1 覆盖边界

已覆盖：

- COMMITTED MATERIALIZE（单条/多条）与任意 ImportOrigin 并存；
- ImportOrigin 完整、同身份多版本、残缺、重复、多合法身份对、非法；
- MATERIALIZE 与 ImportOrigin 实例 ID 相同/不同；
- 正常导入状态 1、正常本地物化状态 2b 控制组；
- 导出不认领、materialize/ensure 拒绝、DB/Journal 零写。

未覆盖：

- PREPARED `current` 与 ImportOrigin 并存的直接 `classify` 调用：服务入口先过
  `recover_if_needed`，恢复会因目标已有 ImportOrigin 抛 `SOURCE_IDENTITY_INCONSISTENT`；
  未额外构造“绕过恢复门直接 classify”的非正常调用测试。
- 同一 item 同时存在多条 MATERIALIZE 且其中一条损坏/摘要不符的完整组合
  （损坏 Journal 读取会先 fail-closed，但未与并存场景组合注入）。
- 跨进程并发下人工制造 ImportOrigin + MATERIALIZE 并存的竞争测试。

## 3. P1 错误分类说明

- 分类结果使用冻结状态 **3（导入身份残缺/冲突）**，不新增外部错误码；
- 修复尝试使用既有稳定码 `SOURCE_DOCUMENT_UNMATERIALIZED`；
- 单篇导出仍返回 200 + `identity_incomplete` 警告，不写来源身份；
- 未新增 `SOURCE_IDENTITY_CONFLICT` 之类的新稳定码，避免改变冻结错误契约。

若审计要求为并存冲突单独引入稳定码，需要另行批准并同步验收矩阵。

## 4. P2 覆盖边界

已覆盖：

- `write_all` 部分写、连续 1 字节写、返回 0、异常传播；
- Journal current 写失败/半写；
- Journal archive 写失败；
- 实例 ID 创建失败/半写/无硬链接 fallback 半写；
- 实例 ID 替换失败/半写。

未覆盖：

- 真实磁盘 `ENOSPC`、配额耗尽、网络盘断电；
- `fsync` 失败注入（当前实现会传播异常且不 rename，但未单独测试）；
- `os.close` 失败注入；
- Windows/POSIX 双平台真实文件系统差异；本次仅在 Windows 实机验证；
- 断电后目录项持久性。Windows 目录 fsync 仍为 best-effort，不宣称断电安全。

## 5. 未改变的 Batch A 既有边界

- `rotate-instance-id` CLI 仍未实现；ROTATE 仅服务层验证。
- Journal 归档临时文件/rename/目录同步的逐点崩溃矩阵仍未穷尽。
- 附件导入/导出/审核仍按 Batch A 范围拒绝。
- 真实 Uvicorn `--reload`/多 worker、Windows ACL/只读目录未实测。
- Backup/Restore 属 Batch C，未实现。

## 6. Git 与范围

- 未提交、未暂存、未推送；
- 未清理或覆盖既有未提交文档；
- 未修改 `MILESTONES.md`；
- 未新增迁移/表/列/索引/依赖；
- 未修改 A1-02 Hash/Canonicalization、A1-03 链接契约、V1 API/端口；
- 未实现 Batch B，未进入下一里程碑。

## 7. 结论

- P1：已修复、已验证；存在上述边界未覆盖。
- P2：已修复、已验证；故障注入覆盖短写/0/异常，未覆盖真实介质错误与断电。
- 整体仍为“SQLite 范围内通过，真实 PG 未验证”，等待第二轮独立审计。