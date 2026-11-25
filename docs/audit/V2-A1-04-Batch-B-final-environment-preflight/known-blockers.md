# 当前阻塞

| 阻塞或待取证 | 影响 | 解除依据 |
| --- | --- | --- |
| WSL 所有调用返回 `Wsl/E_ACCESSDENIED`，当前无可用 Linux guest 证据 | B1-T01/T02 的原生 POSIX 验证和 Linux 安装阻塞 | 在获批环境看到实际 Linux shell、ext4 挂载与锁定依赖安装成功。 |
| PostgreSQL 回环探测为 WinError 10013，真机 DSN 未配置 | B1-T03/T04 真实 PostgreSQL 验收阻塞 | 测试账号连接独立库，实际运行在线迁移和真实双连接测试。 |
| 真实 PostgreSQL 套件已存在，但当前记录为 17 项跳过 | PG 实现正确性未取得实测 | 现有 17 项不再门控跳过，并补各项缺失探针。 |
| Round 3 的 Linux 目录同步、同句柄路径替换与真实权限没有实机证据 | 存储层平台支持未关闭 | 获批环境在原生 ext4 提供真实系统调用和文件结果。 |
| Round 3 Windows 真 junction/symlink 测试受本次权限跳过 | 新增 DB 祖先真实 reparse 拒绝缺当前版本证据 | 旧版可复用系统行为证据。当前新场景如仍需冻结要求的实机取证，Windows 只定向跑该组。 |
| GC 隔离写记录前、purge 后写状态前崩溃 | B5 GC-07 端到端验证缺口 | 既有 SQLite 持锁进程 kill 证据只用于 LCK-07。GC-07 按冻结后续阶段收敛。 |

Round 3 known issues 记载的 PostgreSQL 真实传输与 POSIX 缺口仍然成立。本轮没有新发现可复现的代码缺陷，不能据此前提关闭 Round 3 待实测风险。TOCTOU 为冻结中保留的窗口，验证对象和后续收敛见 (LCK-08)。
