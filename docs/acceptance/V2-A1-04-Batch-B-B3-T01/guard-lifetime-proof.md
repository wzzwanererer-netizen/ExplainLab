# P1-01 Staging Guard 生命周期证明

本文件只陈述可核对的代码路径与已真实运行的测试，不把设计意图当成运行结果。

## 1. 守卫对象与获取点

- 守卫：`AttachmentStagingService._guards[staging_id]`，每 staging_id 一把 `threading.Lock`（非重入），`staging_guard()` 超时 10 秒。
- 获取点：`stage_from_zip()`（`backend/app/services/attachment_staging.py`）在计算 `staging_id` 后立即 `with self.staging_guard(sid):`，此后才：
  1. 检查 staging 目录是否已存在；
  2. 创建根/staging/blobs 目录与 `.creating`；
  3. 写 blob、`.activity`、`.complete`；
  4. 校验 manifest 与文件哈希；
  5. 把 lease 交给调用方，并在同一个 `with` 内等待调用方 commit。

解析 ZIP（`parse_import_zip`）发生在取得 guard 之前，但该步骤纯内存、不创建 staging 目录、不写数据库，因此“guard 在 staging 目录创建之前获取”成立。

## 2. 调用方事务边界

`backend/app/services/markdown.py::_import_one`：

```python
with stage_context as lease:          # stage_from_zip 的 guard 从这里开始
    staged = lease.staged if lease is not None else None
    commit_attempted = False
    try:
        result, needs_index = self._apply_import(..., staged=staged)
        commit_attempted = True
        session.commit()              # 审核单 flush 与业务写入同事务
        if lease is not None:
            lease.committed = True
        return result, needs_index
    except Exception:
        session.rollback()
        if lease is not None and commit_attempted:
            lease.keep_for_orp = True
        raise
```

`stage_from_zip` 的 `finally`：

```python
if not (lease.committed or lease.keep_for_orp or lease.retain):
    lease.discarded = self._cleanup_incomplete(staging_dir)
```

三种结果：

| 场景 | 标志 | staging 结果 |
|---|---|---|
| commit 成功 | `committed=True` | 保留给 pending 审核 |
| 已调用 commit 但结果不明确（抛异常） | `keep_for_orp=True` | 保留给 ORP，不删 |
| commit 前已知失败 | 无标志 | 在仍持 guard 时删除本次 staging |

## 3. `create_from_zip` 兼容路径

`create_from_zip` 委托 `stage_from_zip`，设置 `lease.retain = True`，不再在内部重复取得同一把非重入锁。调用方获得 staging 后自行负责后续生命周期。

## 4. 锁顺序

外层顺序未改变：

1. review 决议锁（适用时）；
2. `ImportCoordinator.keyed(lock_key)` 来源锁；
3. `identity_guard()`；
4. `staging_guard(staging_id)`；
5. `StorageKeyLock`（B4/B5 路径）；
6. 业务 DB 写事务。

`stage_from_zip` 只在 2、3 已持有后获取 4，释放按逆序，未引入倒序或 guard 内再次获取来源锁。

## 5. pending 复用

`_reuse_pending` 在 `staging_guard` 内：

1. `_verify_pending_unchanged(pending)`：用独立会话重新读取 `ReviewRequestORM`，要求仍为 `pending`、item 一致、payload hash 与附件 manifest 未漂移；否则 409 `SOURCE_CHANGED_DURING_WAIT` / `SOURCE_HAS_PENDING_IMPORT`；
2. `validate_manifest_locked(...)`：在同一 guard 内验证 staging 的 `.complete`、文件、大小与哈希，避免调用 `validate_manifest` 造成自锁。

## 6. 真实测试证据

文件：`backend/tests/test_attachment_staging.py`

| 测试 | 证明内容 | 结果 |
|---|---|---|
| `TestStagingGuardLifetime::test_guard_covers_creation_and_releases_after_commit` | 注入 `directory_sync` 记录每次同步；每次同步时 guard 均被持有；`.complete` 已存在、blob 已落盘；请求完成后 guard 释放 | passed |
| `TestStagingGuardLifetime::test_guard_held_during_business_commit` | 在导入服务实际使用的 Session 子类上观察 `commit()` 入口，通过 `save_review` 取得 staging_id，断言 commit 时对应 guard 已持有且不能被其他线程获取；提交后释放 | passed |
| `TestStagingGuardLifetime::test_known_precommit_failure_cleans_staging` | 构造 ReviewRequest 前抛错；异常真实传出；staging 目录 0、审核单 0、正式附件 0、所有 guard 已释放 | passed |
| `TestStagingGuardLifetime::test_ambiguous_commit_keeps_staging_for_orp` | 真实提交后模拟不确定结果；保留 1 个 staging 与 1 条 pending 审核；guard 释放；正式附件 0 | passed |
| `TestPendingReuseGuard::test_reuse_validates_manifest_under_guard` | `validate_manifest_locked` 被调用时 guard 处于持有状态 | passed |
| `TestPendingReuseGuard::test_reuse_rereads_pending_under_guard` | 进入 guard 前把审核改为 approved；请求返回 409 `SOURCE_CHANGED_DURING_WAIT`，不复用陈旧 pending | passed |

原始日志：`evidence/remediation/b3-t01-special.log`（54 passed）。

## 7. 限制

- guard 是**进程内**锁，不是跨进程/分布式锁；单后端单 worker 前提未变。
- commit 成功后、pending 写入可见前若进程崩溃，物理 staging 可能先于 DB 提交存在；这类窗口由 B5 ORP 处理，本文件不声明原子性。
- “commit 结果不明确”用真实提交后再抛错模拟，不是网络分区实测；该测试证明标志与保留路径，不证明数据库层两阶段提交。