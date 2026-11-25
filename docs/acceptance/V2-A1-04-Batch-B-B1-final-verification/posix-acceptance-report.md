# POSIX 验收状态

**BLOCKED，未运行 POSIX 测试。** 当前未进入 Linux guest，也未确认挂载类型。未在原始 Windows 工作树上运行 Linux 验收。

| 需求 | 本轮证据 |
| --- | --- |
| 原生 ext4、普通用户、同卷目录 | 未验证 |
| hard link、no-clobber、真实 rename | 未验证 |
| 文件 fsync、目录 fsync、权限与 symlink 拒绝 | 未验证 |
| 同句柄读取与打开后路径替换 | 未验证 |
| ProcessLock、Journal 恢复 | 未验证 |
| 跨进程竞争及受控普通进程终止 | 本轮未运行。历史 Windows/SQLite 持锁进程终止记录保留原证据种类 |
| 故障注入 | 复用 Round 3 已有注入记录，计为故障注入证据 |
| 断电级验证 | 未执行 |

真实系统调用、注入失败、普通进程崩溃及断电分别取证。当前可复用的 Windows/SQLite 记录及下一步所需 Linux 证据见 [验收矩阵](acceptance-matrix.md)。
