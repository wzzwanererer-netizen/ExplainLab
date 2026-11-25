# 验收覆盖缺口

静态计数为 **53 个唯一编号**。ATT 13、LCK 10、GC 12、ORP 7、IMP 1、R1-IMP 7、R1.1-IMP 3。已有编号覆盖正常上传/共享/下载/删除、基本租约与接管、两次提交、失败回滚、Windows 占用、孤儿检查和 staging 生命周期。表内为需要补强的断言，使用现有编号或继承映射即可。严重程度及是否阻塞沿用 [架构发现](architecture-findings.md) 中的对应项，覆盖缺口本身不重复计为阻塞。

| 位置与关联发现 | 现有证据计划的缺口及影响 | 最小补强 |
|---|---|---|
| ATT-10/13、R1.1-IMP-38，F01（P1） | ATT-10 明测两个 item，无法证明同 item 去重。ATT-13 先归档再发请求，不能覆盖预检后归档。R1.1-IMP-38 需卡到 Core 改状态之前，否则无法定位检查失序。 | 同 item+key 并发断言只一条、201/200、同 ID。用屏障让归档在上传预检后、Draft 或 approve 写前先提交，断言稳定错误、归档状态不被改写、零附件提交。反序则归档保留既有引用。 |
| IMP-19、R1-IMP-05/14/37，F02/F09（P1/P2） | 缺少多文档归属、同名路径、附件重复/更换后的重试、无 Markdown、metadata-only 和双方入口的兼容结果，现有测试可能让静默丢附件通过。 | 覆盖多篇混合 Draft/Active 或按冻结后的规则拒绝歧义，并验真实 owner；相同请求重试、本体相同附件变更、PENDING 已有的同/异附件集合、已应用同 hash、metadata-only、零文档；核对 JSON 单篇 400/批量逐篇既有结果及 ZIP 限制、保留键冲突。 |
| ORP-05、R1.1-IMP-41/42，F03（P1） | 当前主要造已存在的 pending 或孤儿，不能证明第二次查询至移动、隔离至 purge 的窗口。 | 让 staging 生产者卡在写入/提交边界，让 sweep 卡在复核前后并交错推进；断言 pending 永远可读或导入安全终止。覆盖标记前空目录、隔离中重新见到 pending、普通无 envelope review、一个损坏导入 manifest、purge 前恢复/再次复核。 |
| R1-IMP-10/11、横切 §8.1，F04（P1） | 坏 envelope 能 reject 的单线程案例，不能证明 fallback 与 approve 走不同身份键时只有一个结果。 | 用真实双事务与 barrier 触发 fallback key 与 identity key 不同，断言只一个终态，失败路径无附件、无错误 staging 删除；坏 envelope 单独 reject 仍可成功。 |
| GC-01/02/04–10、ORP-04/05/06，F05/F11（P1/P2） | 对同 task 并发 claim 的断言无法覆盖两个 task 的不同 quarantine 路径。GC-07 没区分 move 后记录前崩溃。LCK-08 的“下一步 verify”只能验证失配被观察后的行为，不能证明刚通过最后一次 verify 的 syscall 已被撤销。 | 真实 FS 测移动成功但 DB 没记录、旧 mtime、同 key 再发布和再删、两个 task、残留属于终态/无任务、已有引用而当前任务没有本地副本；断言等待时间从可证明起点算，恢复不覆盖，purge 前重查。明确 LCK-08 两个时点：verify 前失配必须中止，verify 后暂停验证剩余风险与隔离恢复。按 GC-08/09 核对第 8 次终态及实际调度。 |
| LCK-02/03/06/10，F06（P1） | 双连接同 key、TTL、断连有覆盖。不同完整 key 的 advisory 冲突、一次 100 keys、抢锁中途失败、持锁连接失效时同 guard 不重新连接均未证明。 | PG 实例上构造同投影的合成 key 测批内/跨批按物理锁身份获取，同批 100 keys 观测会话数与总预算。断开持锁会话后确认旧 guard 不能继续物理/业务提交，多次运行退出后无 advisory 泄漏。 |
| LCK-04/05/07/08、R1-IMP-08、横切 §8.1，F07（P1） | “identity_guard 不写”会把合法 PREPARED 恢复误判为失败。只测正常 SQLite 用例无法验证心跳与写事务竞争或失配后回滚。 | 在真实 SQLite 文件 DB 上构造 PREPARED MATERIALIZE：恢复 commit/close 在首个附件锁前。制造 busy 与真实失配，分别验证有界重试和覆盖所有 key 的最终 fencing。记录物理发布、S1 写事务和①的先后，覆盖 claim 先提交以及锁释放异常。 |
| B1-T01/T02、ORP-02、R1.1-IMP-42，F08（P1） | 现有跨卷通过 monkeypatch 和路径穿越案例，无法证明根重合、非 UUID 目录、junction/symlink 不会让清扫触及业务数据。 | 对比启动前后的文件树，拒绝 staging=正式根、与 quarantine 交叠、已知越界别名。真实 FS 用例验证目录链接/junction、非规则 staging、跨卷错误保留源。 |
| R1-IMP-08/09、ATT-09/12、横切 §8，F09/F10/F12（P2） | 两次 commit 成功不等于索引②失败后客户端行为正确。下载路径替换用例缺平台共享模式与取消清理分支，错误码也可能回显 input。 | 分别注入索引同步与② commit 失败，核对①仍提交、HTTP 与冻结口径一致、staging 可收敛。Windows 真实占用与 POSIX rename 分开测，同句柄输出无路径重开，失败/取消句柄回收；各错误核对稳定码与脱敏。 |

## 继承映射与执行口径

| 继承编号 | 当前映射判断 | 收口方式 |
|---|---|---|
| R1-IMP-07 | B3 路线提及，同来源不同 hash 的附件关联结果缺少验收条目中的精确断言。 | 挂 IMP-19 / R1-IMP-05，验证原 pending、manifest、staging 均保持，无第二张 pending、无 item 变更。 |
| R1-LOCK-07 | ORP-06 测 ORP↔GC，横切并发主要是 upload↔delete，不能替代 upload 发布至 commit 期间与 GC/ORP 的竞争。 | 挂 ATT-10 / ORP-06，在发布后、commit 前以屏障启动 GC/ORP，锁内复查引用，无误隔离。 |
| R1-LOCK-08 | LCK-10 的同 key、存活/断连不等于 advisory 投影碰撞。 | 挂 LCK-10，按 F06 增加冲突与无冲突用例并保留完整 key 核对。 |
| D22 / D23 / D24 | D22/D23 需要既有冻结回归，D24 仍归 Batch D。 | B4-T02 用现有 ID/Hash/审核套件加上述故障时序；在 B6 报告标清实际验证的批次与平台。 |

R1.3 implementation-plan 的分批出口（第 753 行）列出 R1-LOCK-07/08 与 R1-IMP-07。验收矩阵对应第 198、219–220 行。维持现有 53 个编号并可追踪地补映射即可，不需新增验收阶段。只有真实运行的环境和用例才能记通过，monkeypatch 可注入故障，不替代平台真占用、PG 双连接或进程 kill 证据。
