# 数据流与事务边界

## 1. 入口分流

```text
POST /api/knowledge/import
POST /api/knowledge/import/batch
        │
        ├─ JSON 单篇 attachments 非空 → 400 ATTACHMENT_IMPORT_UNSUPPORTED
        ├─ ZIP + 顶层/逐篇 JSON attachments → 400 ATTACHMENT_IMPORT_UNSUPPORTED
        ├─ ZIP 无附件 → 与 Batch A 相同，可多篇
        └─ ZIP 有附件
             ├─ 多篇/归属歧义 → 整包 400 ATTACHMENT_IMPORT_UNSUPPORTED
             ├─ 零篇 + Active target → 400 ATTACHMENT_ONLY_IMPORT_UNSUPPORTED
             ├─ 零篇 + 其它 → 400 ATTACHMENT_IMPORT_UNSUPPORTED
             └─ 恰好一篇 → 绑定该篇，进入 MarkdownService
```

批量 JSON 的逐篇 `attachments`（以及批量顶层 `attachments`）由现有报告标记为 `unsupported`，其它篇继续；不创建 staging。

## 2. ZIP 解析（无 DB、无 staging）

```text
base64 解码
  → 全路径/元数据校验
  → 重复/大小写冲突、链接、加密、压缩炸弹、数量/大小限制
  → 归属判定
  → 有界读取文档/manifest/附件
  → ParsedImportZip
```

此阶段没有 staging 目录、没有 DB 写。

## 3. Active pending 创建

```text
D23 identity recover
  → Markdown preflight / D22
  → S0 只读会话
  → ImportCoordinator 来源锁 + identity_guard
  → S1 新会话
       ├─ 目标/来源唯一性
       ├─ 归档检查
       ├─ Active 检查
       ├─ title/content 变化
       ├─ pending 集合/复用检查
       └─ 已应用附件满足检查
  → create_from_zip（DB 写事务之外）
       .creating → blobs → .activity → .complete → 自校验
  → ImportEnvelope(attachments=真实 manifest).with_digest()
  → ReviewService.submit（只 flush）
  → session.commit()（唯一业务提交）
  → 返回 pending / 202
```

- staging 物理写入失败：清除本次目录，返回 staging 稳定错误；不进入 DB 写。
- Review 提交前失败：rollback，尽力清理本次 staging。
- commit 抛异常：保留 staging（提交结果不明确），B5 ORP 收敛。
- commit 成功：`attachment` 表零新增；staging 目录保留供 B4 approve。

## 4. 已应用同 Hash

```text
decision_same
  → 目标唯一/Active
  → 对每个请求 storage_key 查 attachment(item_id)
  → 每个 key 都存在引用
  → verify_blob(storage_key, size) 全部通过
  → SKIPPED + attachments_already_satisfied
```

缺引用：Active 返回 400 `ATTACHMENT_ONLY_IMPORT_UNSUPPORTED`；文件缺失/损坏返回稳定存储错误，不静默成功。

## 5. Pending 复用

```text
同来源 + 同 payload hash + 逻辑集合相等
  → validate_manifest(staging_id, pending attachments)
  → .complete/文件/size/hash/MIME 全通过
  → REUSED_PENDING（不新建 staging）
```

不同集合：

- 一侧为空或文件名/MIME/size/key 不同 → 409 `SOURCE_HAS_PENDING_IMPORT`；
- 不创建第二份 pending 或 staging。

集合相等但 staging 缺失/损坏 → staging 稳定错误（409），不新建。

## 6. 锁序

B3-T01 沿用冻结顺序，不新增业务锁：

```text
（review/import 决议锁：B4 范围）
→ ImportCoordinator 来源锁
→ identity_guard
→ staging_id 进程内 guard（目录创建 → manifest → ReviewRequest → DB commit 全程持有）
→ StorageKeyLock（B4 promote/B2 上传范围）
→ 业务 DB 写事务
```

staging guard 的获取晚于来源锁与 `identity_guard`，释放先于它们，保持冻结逆序；`stage_from_zip` 内部不会再次获取同一 guard（复用 `validate_manifest_locked`）。B3-T01 不取 StorageKeyLock，不发布正式 blob，不写附件引用。

## 7. 事务归属

- Repository 只 flush；MarkdownService 不额外 commit/rollback 既有事务。
- staging 服务不接触业务 session；`pending_staging_ids` 使用独立只读 session，查询后关闭。
- `_import_one` 外层唯一 commit/rollback；已知提交前失败在仍持 staging guard 时清理；commit 结果不明确时保留 staging（`keep_for_orp`）并释放 guard。
- 不声称物理 staging 与 DB 事务原子。

## 8. 诚实边界

- pending 期间允许：staging 完整、正式引用为 0。
- 不允许：pending 期间写正式 `attachment` 行。
- 物理文件与 DB 不是原子事务。
- B3-T01 不执行 approve/reject、不清理已提交 review 的 staging；这些属于 B4。
- B3-T01 不执行 GC/ORP 物理清扫；这属于 B5。