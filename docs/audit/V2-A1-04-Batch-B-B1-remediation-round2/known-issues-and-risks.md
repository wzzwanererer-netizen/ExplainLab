# 剩余风险与验证条件

| 项目 | 当前证据与限制 |
|---|---|
| 真实 PostgreSQL | EXPLAINLAB_PG_TEST_URL 未设置且没有可用本地实例证据。故障注入只验证 Python 控制流。真实锁投影竞争、NullPool 断连释放、ROW FOR UPDATE、UPSERT、租约与 PG 仓储仍待实测。服务器超时约束服务器端等待，半开连接、连接清理和传输延迟未获得实测界限。 |
| POSIX 真机 | 当前为 Windows。目录打开与 fsync 错误通过注入验证；真实 POSIX 的硬链接、目录 fsync 和打开句柄后替换仍待验证。WSL 枚举返回 Wsl/E_ACCESSDENIED。 |
| 真实 Windows junction/symlink | 本轮环境无法创建目录链接，相关用例跳过。模拟重解析点验证了配置到启动的拒绝逻辑。原 B1 日志中此前真机 junction 结果仅作为历史证据。 |
| 真实跨卷 | 当前证据为卷号和 EXDEV 注入，双卷未实测。 |
| 真实进程崩溃 | 未做 LCK-07、GC-07 真实 kill 或重启恢复。B1 辅助层与后续 GC/ORP 编排分属不同阶段。 |
| TOCTOU | 真实 Windows 同内容替换及注入复核可验证打开前后路径身份检查。verify 与 syscall 间仍有窗口，已打开文件被外部进程原地写入也仍可能。跨进程暂停并接管未执行。 |
| 原生 GC 调度 | 本轮交付仓储转换和外层短事务入口。任务编排、文件代次复核及隔离期验证仍按既有 B5 计划。 |
| 受限执行环境 | 当前执行环境内默认 Proactor socketpair 未完成初始化，卡点堆栈已保存。以证据目录中的 Windows 测试进程适配补跑，并与工作树留存的原生命令日志分别记录。 |
| Ruff 仓库范围 | 5 项存量 lint 均来自未跟踪的冻结复审归档里的迁移源码副本。实际 backend 和 knowledge-core lint 通过。 |
