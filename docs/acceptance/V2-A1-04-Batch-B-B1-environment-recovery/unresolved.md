# 未解决问题与证据边界

- **B1 正式裁决待审。** 三项定点缺口已获实机通过证据。Windows 普通 PowerShell 覆盖三个真实 junction 与 C/D 路径边界，Linux 实测应用同卷检查。Windows 真实挂载点穿过前序校验触发同卷错误仍无单独实证，本轮用 Linux 实际挂载点验证该分支，Windows 用真实不同卷验证生产配置与启动拒绝。[T01 定点报告](../V2-A1-04-Batch-B-B1-final-verification-round/T01-Windows.md)
- **PG 的证据边界。** T04 仓储 13 项及 LCK-07 客户端终止均已通过。旧的服务端终止另有证据。真实网络半开仍未独立验证，底层物理 close 抛异常有故障注入覆盖。[T04](../V2-A1-04-Batch-B-B1-final-verification-round/T04-PostgreSQL.md) · [LCK-07](../V2-A1-04-Batch-B-B1-final-verification-round/LCK-07-PostgreSQL.md)
- **历史回归问题。** 本轮 Backend/Core Ruff 通过。全仓 Ruff 的 5 项来自旧审计迁移副本。受管 D 盘首轮文件权限失败原样保留，默认测试临时目录的同组回归通过。既有 SQLite GC 排序断言存在等时间戳反例。[最终回归证据](../V2-A1-04-Batch-B-B1-final-verification-round/README.md)
- **后续阶段。** 21 项编号按冻结范围取证。GC/Journal 指定断点的进程终止及物理持久性保持原证据边界。GC/ORP 的联合流程按 B5 裁决。[53 项矩阵](acceptance-matrix.md)
