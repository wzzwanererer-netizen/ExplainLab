# 未解决、未验证与明确不做项

## 1. 按阶段未实现（不是 B3-T01 缺陷）

| 项 | 归属 | 现状 |
|---|---|---|
| Draft/新文档携带附件正式发布 | B3-T02 | B3-T01 明确 400 `ATTACHMENT_IMPORT_UNSUPPORTED`，零 staging；B3-T02 必须实现锁、发布、文档+附件引用同事务 |
| Active approve 写附件引用 | B4 | 未实现；B3 只生成 pending manifest |
| Reject/approve 后 staging 清理 | B4 | `discard_*` 已提供，但未接入治理路由 |
| ORP staging 扫描/隔离/purge | B5 | 只实现 `sweep_candidate` 判定 |
| GC worker 七态 | B5 | 未实现 |
| 一致性报告 | B5 | 未实现 |
| 附件导出 | 明确不支持 | 保持 400 |
| 前端 | 无改动 | 未跑前端测试 |

## 2. 环境未验证

| 项 | 状态 | 说明 |
|---|---|---|
| 真实 PostgreSQL | **未验证** | `EXPLAINLAB_PG_TEST_URL` 未设置；全量 213 项 skip 中 210 项为 PG 门控 |
| B3 staging 在 PG 后端 | **未验证** | B3 当前无 DB 方言分支；仍须 B6 真实 PG 证明既有事务/锁路径 |
| 第二 Windows 卷/真实跨卷 | **未验证** | 无可用第二卷 |
| Linux/POSIX staging 语义 | **未验证** | 仅 Windows 真机；symlink 测试在 Windows 用 junction/symlink 实际通过 |
| POSIX 目录 fsync 真实执行 | **未验证** | 已实现并做注入式失败测试，但本机 Windows 无法执行 POSIX 分支 |
| Windows 断电目录项持久性 | **未验证（平台限制）** | Windows 无目录 fsync，显式 no-op；不声称断电持久 |
| 100 MiB+1 归档 | **已验证（解析边界）** | 真实 104 857 601 字节 ZIP 被 `IMPORT_ARCHIVE_INVALID` 拒绝；未做 100 MiB 级成功导入 |
| 进程 kill/崩溃窗口 | **未验证** | B3-T01 未做 staging 写入中 kill 取证 |

## 3. 已知限制

1. **Draft 附件未启用**：B3-T01 拒绝而不是静默丢弃。验收时不得把 Draft 附件导入写成成功。
2. **ZIP MIME 由扩展名推断**：ZIP 无独立 MIME 声明；实际内容仍 magic/UTF-8 校验。不得声称扩展名权威。
3. **文本子类型不可区分**：TXT/MD/CSV 共享检测。
4. **ZIP 压缩比阈值**：>1 MiB 且 >1000:1 拒绝；极高压缩比的合法文本可能被保守拒绝。这是安全取舍。
5. **staging guard 为进程内锁**：单 Backend/单 worker 前提；不是跨进程分布式锁。
6. **无 session factory 时 `pending_staging_ids()` 返回 `None`**：`discard_*` 与 `sweep_candidate` 均 fail-closed，不删除/不判定可清理。实际路由注入真实 session；B4/B5 必须注入，否则清理能力失效（但不会误删）。
7. **物理 staging 与 DB 非原子**：commit 结果不明确时保留 staging 并释放 guard，等待 ORP；不得声称原子。
8. **`sweep_candidate` 只判定**：不删除、不隔离；B5 才执行。
9. **filename 只做展示**：manifest 校验拒绝路径分隔符/控制字符/`..`，但不承担磁盘路径安全；磁盘路径只由 ordinal 生成。
10. **无鉴权/本机单用户**：Batch D 范围。
11. **Windows 目录同步为空操作**：`directory_sync` 在 Windows 直接返回；文件 fsync + `os.replace` 仍执行，但目录项断电窗口未消除，也未伪装已消除。
12. **损坏 ZIP 映射为白名单异常集合**：覆盖 CRC、非法 Deflate、截断、长度不符等；不是对任意畸形流的穷举证明。

## 4. 审核关注点

1. 核对 `_import_one` 是否在所有早返回前完成归档、Active、已应用、pending 集合检查。
2. 核对 pending 复用是否在 `staging_guard` 内重新读取 pending 并验证 `.complete`、文件与 hash。
3. 核对 staging guard 是否覆盖目录创建到 DB commit，且已知失败在 guard 内清理、不留下 `.complete`。
4. 核对 commit 结果不明确时是否保留 staging、释放 guard 并交由 ORP，而不是删掉可能的已提交引用。
5. 核对 ZIP 解析是否在 staging 创建前完成全部路径/大小/数量/零字节/压缩预算校验。
6. 核对 `_read_bounded` 是否把损坏流映射为 400，而不是 500。
7. 核对 `pending_staging_ids()` 的 `None` 是否在所有调用点都 fail-closed。
8. 核对 `test_attachment_staging.py` 是否真实使用 tmp FS/SQLite，未 mock。
9. 核对 B1/B2 生产文件哈希未变（`test_attachment_api.py` 的漂移早于本轮，mtime 可证）。
10. 确认 Draft 附件、approve、ORP 的缺口没有被误记为 B3-T01 完成。

## 5. 停止点

B3-T01 实现与整改完成，等待独立审核。不得自行进入 B3-T02/B4/B5，不得重复声称 Batch B 通过。