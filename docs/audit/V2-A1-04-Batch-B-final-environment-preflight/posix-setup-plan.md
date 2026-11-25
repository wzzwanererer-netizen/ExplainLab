# POSIX 环境与 ext4 验证方案

**执行前提：搭建获批。优先复用一台运行中的 WSL2 发行版或已有 Linux VM。**

1. 在获批宿主机运行 `wsl -l -v`，确认所选发行版的版本为 2。进入 guest 后记录内核、发行版、架构、挂载选项和实际路径。若同一宿主机 WSL 仍不可用，使用现有可登录 Linux VM。两者均不可用时再确定单一新环境，避免重复安装。见 [Microsoft WSL 命令](https://learn.microsoft.com/en-us/windows/wsl/basic-commands)。
2. 源码、`.venv`、pytest basetemp、`data_dir`、附件正式根、staging、quarantine、SQLite 测试库及 Journal/Identity 目录固定在 Linux guest 原生 ext4。Windows 工作树来源可以通过现有方式只读传入，实际执行路径用 `findmnt -T <path> -o TARGET,SOURCE,FSTYPE,OPTIONS`、`stat -c '%d %a %i %n'` 核验。项目测试目录用普通 Linux 用户，主要根目录控制在同一设备号。避免 `/mnt/d`、DrvFs、Windows 网络共享和容器 overlay 作为 POSIX 证据。见 [Microsoft WSL 文件系统说明](https://learn.microsoft.com/en-us/windows/dev-environment/wsl-interop)。
3. 在 ext4 上做独立源码副本。用 Batch A 提交建立干净副本并按项目根路径叠加 Round 3 ZIP，记录解压前后的清单及校验。保留完整源码、测试、迁移、`uv.lock` 和冻结文件，仅在副本生成虚拟环境及数据。核查 Python 3.11.9（若只能用另一 3.11 补丁版本，记录差异），执行 `uv sync --locked --python 3.11.9`，再用 `uv run --locked --no-sync python` 实际导入 Backend、Core、SQLite 和 psycopg。Windows 锁检查无法说明 Linux 安装已完成。见 [uv 锁定安装说明](https://docs.astral.sh/uv/concepts/projects/sync/)。
4. 固定 `TMPDIR` 和 `--basetemp` 到本次专用 ext4 目录。优先用 `backend/tests/test_attachment_storage.py` 中的路径、根校验、同卷、链接拒绝、权限、独占临时文件、no-clobber、并发发布、打开句柄后路径替换、同步失败和 quarantine 辅助层测试。按 `--collect-only` 核对选择范围，运行时禁止将关键环境场景跳过计成通过。
5. 做同卷 hard link 的 inode/link count 证据、已有文件 no-clobber 的 hash、目录权限/符号链接拒绝、正式与 quarantine 的内容保真。用原生文件/目录 fd 的真实 fsync 调用和重启或子进程受控中断后的复核，证实计划内的持久性边界。若有 `strace`，保存针对文件和父目录同步的脱敏跟踪。区分正常 fsync、注入 I/O 失败和断电等级证据。验证真实跨挂载 EXDEV 时，只在独立临时 mount 中做负例。主存储仍保持 ext4 同卷，无第二 mount 时单列未验证。
6. 用现有 Batch A 用例挑选物理依赖强的 Journal 写入、PREPARED/COMMITTED 恢复、Identity 原子替换及跨进程 ProcessLock 子集。候选源文件为 `test_batch_a_file_write.py`、`test_batch_a_process_and_identity.py`、`test_markdown_batch_a_identity.py`。真实 Linux 记录独立子进程 PID、锁互斥、终止后释放、恢复前后文件 hash 与 DB revision。保持冻结的业务调用路径和断言。
7. POSIX 测试与 PostgreSQL 真机套件分别取证。Linux 系统任务终止测试不得等同于 B5 的 GC/ORP 崩溃收敛。已充分验证的 Windows 非平台依赖回归直接引用 Round 3 日志。

### 首次执行的收集命令

下列命令从已核验的 Linux/ext4 源码副本运行。先收集用例并记录准确的 node ID，后续以对应平台子集执行。每组使用独立空 `--basetemp` 目录。

```bash
uv run --locked --no-sync pytest -o addopts=--import-mode=importlib --collect-only -q \
  backend/tests/test_attachment_storage.py \
  backend/tests/test_storage_lock_sqlite.py \
  backend/tests/test_batch_a_file_write.py \
  backend/tests/test_batch_a_process_and_identity.py \
  backend/tests/test_markdown_batch_a_identity.py
```

同句柄路径替换的必测节点为 `backend/tests/test_attachment_storage.py::test_verified_handle_survives_path_replacement`。目录权限从普通用户实际创建的 inode 和拒绝访问结果取证。Journal 选 `test_archive_write_failure_keeps_committed_current_then_recovers`、`test_prepared_materialize_recovers_db_empty`、`test_crash_after_db_before_committed_recovers`、原子 Identity 替换和实际跨进程锁释放。SQLite 锁仅补 Linux 文件锁和进程退出相关行为。
