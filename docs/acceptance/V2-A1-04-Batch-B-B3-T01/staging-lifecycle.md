# Staging 生命周期

目录：`<data_dir>/import-staging/<staging_id>/`

```text
<staging_id>/
├─ .creating
├─ .activity
├─ .complete
└─ blobs/
   ├─ 000001.bin
   └─ 000002.bin
```

## 1. 创建顺序

1. 生成小写 UUIDv4 `staging_id`；取得进程内 staging guard，并**一直持有到调用方事务提交完成**（见 `guard-lifetime-proof.md`）。
2. 确认正式根/staging 根互不包含、同卷、真实目录、无链接/重解析点。
3. 创建 staging 目录与 `blobs/`，按 P1-02 顺序执行目录级 fsync（Windows 为显式 no-op）。
4. **先写 `.creating`**。
5. 按规范 ZIP 路径排序分配 ordinal；实际字节写入 `blobs/{ordinal:06d}.bin`，`xb` 独占创建、完整写入、`fsync`，并同步 `blobs/` 目录。
6. 每写入一个附件刷新 `.activity`（重新写标记并把 mtime 推进），同步 staging 目录。
7. 全部写完后写 `.complete`（临时文件 + fsync + `os.replace` + 同步父目录），最后用同一 manifest 再校验整个目录。
8. 返回 `StagedAttachmentSet`；guard 仍由调用方块持有。

任何一步失败：

- 删除 `.complete`（若已存在）；
- 在仍持 guard 时尽力删除本次受控目录；
- 不让“看似完成”的 staging 留在磁盘；
- 若清理也失败，至少保持无 `.complete`，由 B5 ORP 收敛。

提交结果不明确时相反：保留 staging、设置 `keep_for_orp`、释放 guard，等待 ORP 核对。

## 2. `.complete`

只包含冻结元数据，`extra="forbid"`：

```json
{
  "schema_version": 1,
  "staging_id": "3f2c1a9e-7b6d-4c2a-9f10-8e7d6c5b4a31",
  "completed_at": "2026-11-24T12:00:00Z",
  "file_count": 1,
  "total_bytes": 184320
}
```

校验要求：

- `.complete` 是普通文件，不是链接；
- JSON/schema 合法；
- `staging_id` 等于目录名；
- `file_count` 等于 manifest 数量；
- `total_bytes` 等于 manifest size 总和；
- 目录内文件集合恰好是标记 + manifest 列出的 blob；不得有额外文件/目录；
- 每个 blob 是普通文件、同卷、大小等于 manifest、SHA-256 等于 storage_key、MIME 与内容一致；
- 缺失目录 → `ATTACHMENT_STAGING_MISSING`；缺失/不一致 → `ATTACHMENT_STAGING_INVALID`。

## 3. 活动时间

`staging_activity_at`：

```text
max(mtime(.creating), mtime(.activity), mtime(.complete),
    所有普通文件 mtime)
```

显式不使用 staging 根目录单一 mtime。测试把根 mtime 改为 10 天前、文件改为 1 小时前，活动时间仍取文件/标记值。

## 4. 状态与动作

| 状态 | 判定 | B3-T01 行为 |
|---|---|---|
| `creating` | 有 `.creating`、无 `.complete` | 不可 approve；本次创建失败时清理；B5 宽限清扫 |
| `active_pending` | `.complete` 被 pending envelope 引用 | `sweep_candidate` 返回 false；approve/reject 由 B4 |
| `committed` | review approved 且事务①提交 | `discard_committed` 可清理 |
| `rejected` | review rejected 已提交 | `discard_rejected` 可清理 |
| `orphan` | 无 pending 且活动时间超 24h | `sweep_candidate` 返回 true；B5 执行隔离/清除 |
| `corrupt` | `.complete`/文件/manifest 不符 | 有 pending 保留；approve 由 B4 fail-closed |

`discard_*` 检查真实 pending 引用；有引用或 pending manifest 损坏时拒绝删除。无 session factory 时 `pending_staging_ids()` 返回 `None`，`discard_*` 与 `sweep_candidate` 一律 fail-closed（不删除、不判定可清理）；实际路由注入真实 session factory。

## 5. 安全删除

- 只删除 `<staging_root>/<staging_id>/`；
- 目录链逐级 lstat，拒绝 symlink/junction/reparse；
- 删除不递归跟随链接；
- 不触碰正式 attachments 根；
- 删除失败返回 false，保留现场。

## 6. 与 B5 的边界

B3-T01 只实现 `sweep_candidate` 判定与安全 discard；不实现：

- ORP 300s 扫描；
- quarantine/staging 物理隔离；
- 24h 隔离后 purge；
- 报告文件。

这些属于 B5。