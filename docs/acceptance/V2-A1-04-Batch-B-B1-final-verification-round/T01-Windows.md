# B1-T01 · Windows 路径安全与真实跨挂载

**PASS。** 普通 PowerShell 真实 Windows 专项 4 通过、0 跳过、退出 0。Linux ext4/tmpfs 应用同卷检查另有 1 通过、0 跳过、退出 0。

| 子项 | 结果 |
| --- | --- |
| SQLite DB 祖先 junction | PASS。真实 junction 标记为 `0xa0000003`，生产 lifespan 拒绝，未创建 DB 或其目标祖先 |
| attachment_storage_root junction | PASS。真实 junction 标记为 `0xa0000003`，生产 lifespan 拒绝，目标清单及 SHA-256 保持 |
| staging_root junction | PASS。真实 junction 标记为 `0xa0000003`，生产 lifespan 拒绝，目标清单及 SHA-256 保持 |
| Windows C/D 不同卷 | PASS。两卷设备号为 721246758 和 2499681939。生产配置拒绝越出 data_dir；直接传入同一非法路径时，生产 lifespan 也在 DB 初始化和 mkdir 之前拒绝。外卷目录清单与保留文件 SHA-256 相同 |
| Linux ext4/tmpfs 分离挂载 | PASS。使用正常 Settings / lifespan 运行应用同卷检查，报 `attachment roots are on different volumes`。源目录及文件 SHA-256 保留，未创建目标、SQLite DB 或其他根目录 |

Windows 跨盘命中路径包含规则。Linux 测试让两根的路径都位于配置的 data_dir 内，命中实际同卷规则。两次均读取真实设备号。三个 Windows junction 用例均以真实 reparse tag 和目录身份确认夹具，验证 init_db 与 mkdir 均未调用，目标目录清单及 `keep.bin` SHA-256 `d12653440b921f17eee06a851e919bc364806b63155215777e5f1e4b854054f2` 保持不变。受管环境无法创建 junction 的历史运行保留。

[普通 PowerShell 原始日志](evidence/windows-normal-cbf67966e623/t01-windows.log) · [Windows JUnit](evidence/windows-normal-cbf67966e623/t01-windows.xml) · [受管 Windows 历史日志](evidence/windows-managed-165fd27e999e/t01-windows.log) · [备用卷方向复验](evidence/t01-windows-default-temp/t01-windows.log) · [Linux 原始日志](evidence/wsl-final.g8LQ7isi/t01-linux.log) · [Linux JUnit](evidence/wsl-final.g8LQ7isi/t01-linux.xml)
