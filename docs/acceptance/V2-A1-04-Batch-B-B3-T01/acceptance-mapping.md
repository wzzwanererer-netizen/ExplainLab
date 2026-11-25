# B3-T01 验收编号映射

本表只映射 B3-T01 实际覆盖的子集。未覆盖部分保留给 B3-T02/B4/B5，不把部分覆盖写成完整通过。

| 编号 | 冻结要求 | B3-T01 实现/证据 | 状态 |
|---|---|---|---|
| IMP-19 | ZIP-only、manifest、staging、pending 零引用、复用/冲突、Active 附件-only、JSON 入口、归档目标、多义 ZIP、数量/大小 | `test_attachment_staging.py` 34 项；真实 SQLite + tmp FS | **部分覆盖 / B3-T01 通过** |
| R1-IMP-05 | Active pending：item 不变、envelope 完整 attachments + digest、attachment 行 0、ImportOrigin 不写 | `test_active_content_change_creates_pending_manifest_zero_formal_refs`；查 review payload、digest、staging、attachment count、item | **部分覆盖 / B3-T01 通过** |
| R1.1-IMP-41 | staging 被 PENDING 引用不清理；按 envelope manifest 校验 | `test_discard_respects_pending_and_sweep_activity`、`test_reuse_pending_with_invalid_staging_fails_closed` | **判定层通过**；物理 ORP 归 B5 |
| R1.1-IMP-42 | 活动取标记/普通文件最大 mtime，不用根 mtime；越界/链接保留源 | `test_activity_uses_marker_and_file_mtime_not_root`、symlink/junction、overlap/ID 测试 | **判定层通过**；完整 ORP 归 B5 |
| ATT-01/06 | 内容寻址、路径不取用户文件名 | staging 固定 `blobs/NNNNNN.bin`；manifest 仅展示名；真实 SHA-256 | **staging 前置通过**；HTTP 上传属 B2 |
| ORP-02 | staging 不进入正式 `.tmp`，不触碰正式根 | staging 根独立；discard 只操作 staging 根 | **前置约束通过**；报告扫描归 B5 |
| IMP-19 多义 ZIP | 多篇 + 附件整包拒绝 | `test_ambiguous_ownership_is_rejected_whole` | **通过** |
| IMP-19 JSON 入口 | 单篇 400；批量逐篇 unsupported | `test_single_and_batch_json_attachment_compatibility`、顶层附件用例 | **通过** |
| IMP-19 Active 附件-only | 400 `ATTACHMENT_ONLY_IMPORT_UNSUPPORTED`，零 staging/pending | `test_active_attachment_only_rejected_with_zero_staging`、零文档用例 | **通过** |
| IMP-19 归档目标 | 附件 ZIP → 400 | `test_archived_target_with_attachment_zip_rejected` | **通过** |
| IMP-19 pending 复用 | 同来源 + 同 Hash + 同集合复用；异集合 409；无第二 pending/staging | `test_same_source_same_attachment_set_reuses_pending`、`test_different_attachment_set_conflicts_without_new_staging`、空集合用例 | **通过** |
| IMP-19 已应用 | 同 Hash 且附件满足 → SKIPPED；缺引用 Active 400 | `test_already_applied_same_hash_with_satisfied_attachment_is_skipped` | **通过** |
| IMP-19 上限 | 10 MiB / 100 个 / 100 MiB / ZIP bomb | count、bomb、manifest bounds 测试 | **通过（构造边界）**；未做 100 MiB 实测大文件 |
| R1-IMP-08/09/10/11/14/37 | approve/reject、事务①、staging 清理、envelope 篡改 | **未实现** | B4 |
| R1.1-IMP-38 | approve hook 故障与归档 | **未实现** | B4 |
| ATT-08/11/12 | 上传/发布/commit 故障 | B2 已验收；B3 未改 | 不重复声明 |
| LCK/GC/ORP 全量 | 锁/GC/ORP worker | B3 未实现 | B5 |

## 未声明通过

- 完整 IMP-19 仍依赖 B3-T02（Draft 发布）、B4（approve）、B5（ORP 清扫）；本表不把 B3-T01 子集等同于 IMP-19 全部通过。
- 真实 PostgreSQL 未运行：全量 213 skip 中 210 为 PG 门控。
- 前端未改、未跑。
- 100 MiB 总大小上限只做了声明/读取路径与较小边界测试，未构造 100 MiB 真实附件包。