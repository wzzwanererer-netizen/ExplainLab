# ExplainLab V2 · Batch B · B1 PowerShell 实机复验交接

**2026-11-23（北京时间）｜当前状态 `BLOCKED`，待 GPT 独立复审。** 普通 PowerShell 已成功启动 Ubuntu WSL2。Linux 原生 ext4 专项 **169 项通过**，真实 PostgreSQL 18.6 专项 **17 项通过**，三组补充探针均退出 0。旧报告中的“无法进入 WSL、未连接真实 PG”是较早一轮的结果。当前需要裁决的是剩余证据是否满足 B1-T01～T04，以及 Round 3 的六项修复能否关闭。

## 1. 本轮执行范围

- Windows 工作区 `D:\ExplainLab`，分支 `fix/m0-admission-and-m5-regressions`，Batch A 基线与 HEAD 均为 `970c0d8ec05f0b8c68286839a56b14c74ea230c6`。Round 3 源码和测试仍在工作树中，包含 4 个已跟踪改动文件、2 个新增实现文件、7 个新增测试文件。暂存区为空。
- 受管终端的 WSL 枚举和启动返回 `Wsl/E_ACCESSDENIED`。普通 PowerShell 可枚举 Ubuntu、启动 guest 并回写日志。受管终端随后仍复现拒绝，内部权限检查点未定位。B1 测试已在普通 PowerShell 路径完成。
- Linux 输入包含基线源码、13 个 B1 实现及测试文件覆盖项和冻结设计。包内 232 条 SHA-256 已复核。Ubuntu 26.04.1 LTS / WSL2 下，项目和 pytest 临时目录位于原生 ext4，Python 3.11.9 锁定安装和导入检查通过。交接前的比对覆盖 180 个源码、测试、迁移、冻结设计及配置文件，137 个字节一致，43 个仅换行符不同，内容差异为 0。
- PostgreSQL 18.6 通过验收目录内解压的软件包运行，使用回环专用实例与独立数据库。服务端日志记录测试后正常停止。本轮变更为验收资料和取证脚本，业务源码、测试、冻结设计、迁移和台账沿用现状。无提交或推送。

## 2. 实机执行结果

| 门槛或探针 | 日志结果 | 证据能支持的结论 |
| --- | --- | --- |
| Linux / ext4 pytest | 169 通过，0 失败，0 跳过，1 警告，25.71 秒，退出 0 | 实际文件的发布、同 key 并发与 no-clobber、隔离和恢复、同句柄读取、打开后替换、symlink 与越界拒绝、ProcessLock 进程竞争和终止后释放 |
| PostgreSQL pytest | 17 通过，0 失败，0 跳过，1 警告，7.28 秒，退出 0 | 专用 advisory lock 互斥，TTL 到期仍禁止接管，关闭连接后接管且 token 递增，旧 guard 拒绝，共享引用计数、双 session GC 认领与 fencing |
| LCK-10 补测 | 退出 0 | 100 key 的 100 把 advisory 锁由同一个 backend 持有。部分获取失败会释放前序锁且不写 token。批次中实际 `pg_terminate_backend` 后可接管，token 保持原子语义 |
| Heartbeat 与 POSIX 权限补测 | 退出 0 | 真实行锁分别阻塞 heartbeat 与 verify、release 的排空交错。交错解除后专用 backend 关闭。存储、staging、隔离、临时及分片目录模式为 `0700`，临时文件与正式对象为 `0600` |
| 释放异常与 EXDEV 补测 | 退出 0 | 真实 PG 行锁触发 release 超时，保留原始业务异常 traceback 和已提交结果，旧 backend 关闭且同 key 可重取。ext4 与 `/dev/shm` 上直接调用 link、rename 均返回 `EXDEV`，源保留且目标未出现 |

两组 pytest 的警告均来自既有 Starlette TestClient/httpx 弃用提示。历史 Round 3 Windows/SQLite 记录另有 B1 专项 **175 通过、22 跳过**，根级 **1,299 通过、200 跳过**，Backend/Core Ruff 通过。历史全仓 Ruff 仍因旧审计目录的迁移副本报 5 项。前端检查本轮未重跑。各批次用例存在交集，计数分别引用。

## 3. Round 3 缺陷回查

独立二审曾提出 4 项 P1 和 2 项 P2。下表给出此次提交的证据及复审边界，最终关闭由审核方裁决。

| 编号 | 整改主题 | 审核所需的证据 |
| --- | --- | --- |
| IR2-01 · P1 | SQLite 批次首个租约可能已过期 | 真实 SQLite 回归覆盖首个租约先到期、整批拒绝交付、清理和重取 token |
| IR2-02 · P1 | SQLite fencing 和连接池 checkout 等待越过预算 | 真实 SQLite 独占写锁、池耗尽和业务 session 场景。历史 0.15 秒预算探针的对应记录约为 0.156～0.157 秒 |
| IR2-03 · P1 | PG 客户端阻塞和 heartbeat 排空 deadline | 驱动阻塞及晚到清理用替身覆盖。真实 PG 已覆盖 SQL 等待、批次连接被终止、verify/release 排空交错。真实网络半开与客户端传输故障仍无独立证据 |
| IR2-04 · P1 | PG guard 释放异常覆盖业务结果 | 真实行锁触发释放超时，两条路径分别保留原异常与已提交结果。底层物理 close 自身抛异常仍由故障注入覆盖 |
| IR2-05 · P2 | Windows 非 link 预检查错误可能触发 rename 降级 | 实际临时文件与 SQLite guard 下的 F12 分类注入覆盖生产入口。内核 EXDEV 探针提供跨文件系统事实，应用分离挂载的拒绝链仍缺证据 |
| IR2-06 · P2 | SQLite 预留文件路径可能被建成存储祖先目录 | lifespan 回归验证非法配置及正常独立目录。Windows 新增祖先 reparse 细项仍需对照真实 junction/symlink 门槛 |

## 4. 剩余证据与冻结合约的归属

按环境恢复矩阵最后一列统计 53 个编号，**19 项 B1 子项已验证、13 项部分、21 项明确留在后续阶段**。部分项为 `ATT-06/08/10/11/12`、`LCK-05/07/08`、`GC-01/09/12`、`ORP-05/06`。一个编号可同时含基础层断言与后续联调内容，须逐条按阶段裁决。

| 冻结任务 | 请重点裁决的剩余问题 |
| --- | --- |
| B1-T01 配置与启动校验 | 路线图明列真实 Windows junction/symlink 与跨卷拒绝。查现有真机证据能否覆盖 Round 3 新增的 DB 祖先 reparse 负例和当前应用启动路径。应用在实际分离挂载下的拒绝及源目录保留仍待补证 |
| B1-T02 原子发布与读取 | ext4 正常路径、权限、无覆盖和同句柄读取有真机证据。目录 fsync/Journal 错误仍属注入。请裁定冻结条款要求的同步、故障注入和崩溃证据分别达到什么粒度，以及哪些崩溃断点属于 B5 |
| B1-T03 SQLite/PG 存储锁 | 区分连接主动关闭、服务端终止 backend、客户端进程被杀和网络半开四种边界。核对 `LCK-07` 的客户端退出断言，以及物理文件 fencing 与 PG guard 联动哪些已由 B1 独立覆盖、哪些按 B4/B5 验收 |
| B1-T04 附件与 GC 仓储 | 真实 PG 已有共享计数、并发认领、token 和终态 fencing。请逐条核对 PG 外层 rollback、FK、DISTINCT、attempts 和认领状态矩阵是否被现有用例覆盖，列出仍缺的基础层断言 |
| 质量门 §10 | 旧审计副本导致全仓 Ruff 报 5 项，业务目录 Ruff 已通过。请裁定这是 B1 验收阻塞还是另行处理的归档卫生问题 |

B2 负责附件 HTTP，B3 负责 ZIP/staging，B4 负责审核集成，B5 负责 GC/ORP worker 和崩溃恢复端到端。冻结路线图要求先完成 B1。当前状态继续保留 `BLOCKED`。

## 5. 给 GPT 的审核指令

> 请以独立审计者身份审查 ExplainLab V2 Batch B 的 B1。先读本报告、冻结路线图 §3/§10、验收计划和存储锁契约，再用 Round 3 映射、矩阵最后一列和原始输出交叉核对。早期 Final Verification 报告记录的是受管终端无法进 WSL 的阶段，普通 PowerShell 的复验更新了环境证据。请逐项输出 IR2-01～06 和 B1-T01～T04 的裁决、对应冻结条款、证据引用及残余风险。给出 B1 整体裁决。若仍阻塞，请只列 B1 最小补测清单，并写明优先级、真实环境、触发条件、断言和应保存的日志。把 B2～B5 的联调事项按冻结阶段登记。若判定通过，请写明进入 B2 的具体准入依据。

## 6. 证据索引

证据链接指向本目录上一级的验收与审计记录。恢复目录的 SHA-256 清单 43/43 已于交接整理时复核。

- [恢复复验矩阵](../V2-A1-04-Batch-B-B1-environment-recovery/acceptance-matrix.md) · [恢复记录](../V2-A1-04-Batch-B-B1-environment-recovery/environment-recovery.md) · [Git 与源码一致性](../V2-A1-04-Batch-B-B1-environment-recovery/git-state.md)
- [ext4 pytest 原始输出](../V2-A1-04-Batch-B-B1-environment-recovery/evidence/acceptance.R3sYC6uE/posix-pytest.log) · [真实 PG pytest 原始输出](../V2-A1-04-Batch-B-B1-environment-recovery/evidence/acceptance.R3sYC6uE/postgresql-pytest.log)
- [批次锁探针](../V2-A1-04-Batch-B-B1-environment-recovery/evidence/pg-probe.OL0D7vGW/probe.log) · [心跳与权限探针](../V2-A1-04-Batch-B-B1-environment-recovery/evidence/heartbeat-posix.ObKWO2Ft/probe.log) · [释放与 EXDEV 探针](../V2-A1-04-Batch-B-B1-environment-recovery/evidence/release-filesystem.6qBa0AMA/probe.log)
- [Round 3 修复映射](../V2-A1-04-Batch-B-B1-remediation-round3/finding-mapping.md) · [Round 3 测试报告](../V2-A1-04-Batch-B-B1-remediation-round3/test-report.md) · [独立二审发现](../../audit/V2-A1-04-Batch-B-B1-independent-review-round2/finding-register.md) · [冻结路线图](../../plans/V2-A1-04-Batch-B/implementation-roadmap.md)
