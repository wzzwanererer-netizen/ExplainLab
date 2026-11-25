# P1-02 · 目录级 fsync 与持久化边界

## 1. 实现

`backend/app/services/attachment_staging.py`

| 位置 | 行为 |
|---|---|
| `_default_directory_sync` (L187–207) | POSIX：`os.open(dir, O_RDONLY \| O_DIRECTORY)` + `os.fsync(fd)` + `close`；`os.name == "nt"` 直接返回（显式 no-op）；`OSError` 映射 `ATTACHMENT_WRITE_FAILED` (503) |
| `__init__(..., directory_sync=None)` (L820) | 允许注入同步函数（测试故障注入），默认 `_default_directory_sync` |
| `_sync_directory` (L954–962) | 统一入口；透传 `AttachmentStagingError`，其余 `OSError` 映射 503 |
| `_create_locked` (L964–1033) | 见下方顺序 |
| `_write_complete` (L1333–1361) | 临时文件 `os.open(O_EXCL\|O_NOFOLLOW)` → `fsync(fd)` → `os.replace` → 同步父目录；任何 `OSError` 清理临时文件并返回 503 |

## 2. 同步顺序（`_create_locked`）

1. 若 `import-staging` 根为新建：`fsync(staging_root.parent)`（L971–972）
2. `mkdir staging_id` 后：`fsync(staging_root)`（L975）
3. 写 `.creating` 后：`fsync(staging_dir)`（L977–978）
4. 建 `blobs/` 后：`fsync(staging_dir)`（L979–982）
5. 每个 blob：`fsync(file)` → `fsync(blobs/)`（L1000–1001）
6. 更新 `.activity` 后：`fsync(staging_dir)`（L1003–1004）
7. `.complete`：`fsync(temp)` → `os.replace` → `fsync(staging_dir)`（L1016、L1352–1357）

`.complete` 与全部 blob 在 `stage_from_zip` 返回前已经落盘；DB pending 提交发生在其后的调用方事务中，因此“提交时磁盘已有完整 staging”成立。

## 3. 失败语义

- 目录同步失败 → `ATTACHMENT_WRITE_FAILED` / HTTP 503，不降级、不吞异常。
- 失败发生在 `stage_from_zip` 创建段：异常在 guard 内触发 `_cleanup_incomplete`，不留下 `.complete`，不创建 pending。
- 失败发生在 `.complete` 写入：临时文件删除，目录仍无 `.complete`，由创建段清理。

## 4. Windows 边界（如实声明）

Windows 无目录 fsync 等价物，`_default_directory_sync` 为显式 no-op。因此：

- Windows 上只保证“写入完成 + 文件 fsync + 原子替换”，不保证目录项在突然断电后仍存活；
- 该残留窗口是平台限制，未用其他手段（如 `FlushFileBuffers` 对目录）伪装成已解决；
- 不在验收中声称 Windows 断电持久性。

## 5. 验证

`backend/tests/test_attachment_staging.py::TestDirectoryDurability`

| 测试 | 内容 | 结果 |
|---|---|---|
| `test_directory_sync_failure_rejects_without_pending` | 注入 `OSError` 的 `directory_sync`；断言 503 `ATTACHMENT_WRITE_FAILED`、零 staging、零 pending、零附件 | 通过 |
| `test_directory_sync_is_platform_explicit` | Windows 断言默认同步为 no-op；非 Windows 断言目录可打开并 fsync | Windows 通过（POSIX 分支未在本机执行） |

原始日志：`evidence/remediation/b3-t01-special.log`（54 passed）。

## 6. 未验证

- **真实 POSIX 主机上的 fsync 行为未执行**（本机 Windows，无 Linux 环境）；
- 断电/崩溃后的目录项存活未做进程 kill 或断电取证；
- 上述两点不得记为已验证。