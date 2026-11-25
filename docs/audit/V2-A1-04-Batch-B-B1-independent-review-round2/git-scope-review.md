# 完整性与 Git 范围

| 项目 | 独立检查结果 |
| --- | --- |
| 本地审计输入 | `D:\ExplainLab\docs\audit\ExplainLab-B1-Remediation-Round2.zip`，239,966 bytes |
| ZIP SHA-256 | `5c5113d42e722c43198848937a23e47ad6051523a184f5856dfc5bb879b763fa` |
| ZIP 内容 | 86 个唯一条目，包含 85 个期望摘要及清单本身。CRC 检查通过，85 项 SHA-256 全通过，工作树对应项 85/85 一致。 |
| 分支与 HEAD | `fix/m0-admission-and-m5-regressions`，`970c0d8ec05f0b8c68286839a56b14c74ea230c6` |
| Index 与格式差异 | 暂存区无改动，`git diff --check` 退出 0 |
| Architecture Freeze | 批准清单 14/14，覆盖十份设计及四份冻结记录。目录现为未跟踪，身份依批准清单与 ZIP 双重核验。 |
| 其他源码范围 | `knowledge-core`、前端、数据库迁移、依赖清单和锁文件、MILESTONES.md 与 HEAD 一致。tracked 差异完整见下。 |

四个 tracked 文件：

- `backend/app/core/config.py`
- `backend/app/db/session.py`
- `backend/app/main.py`
- `backend/app/services/repositories_v2.py`

两个 untracked 实现与七个 untracked 测试均在当前工作树逐文件核对，也都在提交清单：

| untracked 类型 | 路径 |
| --- | --- |
| 实现 | `backend/app/db/storage_lock.py`，`backend/app/services/attachment_storage.py` |
| 测试 | `backend/tests/test_attachment_gc.py`，`test_attachment_pg.py`，`test_attachment_storage.py`，`test_attachment_windows.py`，`test_storage_lock_pg.py`，`test_storage_lock_pg_faults.py`，`test_storage_lock_sqlite.py` |

未跟踪文档和既有审计 ZIP 仍在项目目录。历史冻结复审的源码快照单独归类。本轮报告输出仅增加独立审计报告。没有 git add、commit 或 push。

同名远端复上传件的临时下载受 DNS 限制。本轮核验以项目目录的本地提交 ZIP、其完整 SHA-256 清单及当前工作树为对象。远端复上传件未作字节等同认证。
