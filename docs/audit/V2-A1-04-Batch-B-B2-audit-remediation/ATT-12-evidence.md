# B2-AUDIT-01 · ATT-12 发布失败映射

真实应用 lifespan、HTTP 路由、SQLite 文件库、存储根和生产 `publish_no_clobber` 均参与测试。`test_publish_io_failure_returns_503_and_cleans_temp` 只在目标 blob 的底层 syscall 处注入故障，其他文件系统操作照常运行。故障点验证临时文件已实际写出，并且内容与上传一致。

| Windows 用例 | 故障顺序 | 实测结果 |
| --- | --- | --- |
| `[link]` | `os.link` 返回 `EIO` | HTTP 503，`{"detail": "ATTACHMENT_WRITE_FAILED"}`，零附件记录、零临时残留、正式根无文件 |
| `[rename]` | `os.link` 返回 Windows 50，生产代码进入同卷降级，`os.rename` 返回 `EIO` | 相同稳定响应和零残留，断言实际经过两个 syscall 调用点 |

Windows 两项通过，0 跳过。WSL ext4 补跑的 link 故障用例通过，Windows rename 分支按平台跳过。既有 B1 发布错误分类、锁、清理和仓储实现及测试的 SHA-256 与审核基线一致。

[Windows 原始 pytest](evidence/att12-windows.log) · [Windows JUnit](evidence/att12-windows.xml) · [ext4 日志](evidence/pg-http.V7CaM83E/att12-posix.log) · [ext4 JUnit](evidence/pg-http.V7CaM83E/att12-posix.xml) · [基线核验](evidence/baseline-verification.log)
