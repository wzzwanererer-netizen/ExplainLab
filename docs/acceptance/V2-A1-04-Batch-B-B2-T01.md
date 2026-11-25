# ExplainLab V2 · Batch B · B2-T01 附件输入校验

**任务出口已验证。** 冻结路线图 B2-T01 的纯函数校验通过。ATT-03～ATT-06 的 HTTP、数据库、文件和下载头验收在 B2-T02 执行。

| 冻结条款 | 本轮证据 |
| --- | --- |
| ATT-03 Base64 与大小 | 标准 Base64 严格解码，空文件与无效 Base64 分别返回稳定码。10 MiB 恰好可接收，10 MiB + 1 由解码字节数拒绝，11 MiB 在解码前拦截 |
| ATT-04 声明与实际内容 | 五种二进制 MIME 按签名验证，扩展名不参与判断。三种文本 MIME 共用严格 UTF-8 检查并拒绝 NUL 与已知二进制签名，成功时保留规范化后的声明 MIME |
| ATT-05 SVG | SVG 声明即使加入配置白名单也拒绝。合法 UTF-8 SVG 字符串以文本 MIME 通过并维持该声明 |
| ATT-06 文件名 | 按 Windows 或 POSIX 拼写提取显示名，处理控制字符、ADS 分隔符、重复点、Windows 设备保留名与长度，保留合法 Unicode |

实现见 [attachment_validation.py](../../backend/app/services/attachment_validation.py)，专项见 [test_attachment_validation.py](../../backend/tests/test_attachment_validation.py)。配置可收紧文件上限或 MIME 集合，实际限制仍受冻结的 10 MiB 和八种 MIME 约束。

## 运行证据

| 命令 | 实际结果 |
| --- | --- |
| `.\.venv\Scripts\python.exe -m pytest -o "addopts=--import-mode=importlib" -ra backend/tests/test_attachment_validation.py knowledge-core/tests/test_interfaces.py -p no:cacheprovider` | 80 passed，含 B2-T01 66 项及 Core 接口与独立性 14 项。已有 Starlette TestClient/httpx 弃用警告 1 条，退出 0 |
| `.\.venv\Scripts\python.exe -m pytest -o "addopts=--import-mode=importlib" --collect-only -q -p no:cacheprovider` | 根级收集 1,580 项，退出 0 |
| `.\.venv\Scripts\ruff.exe check backend knowledge-core` | All checks passed，退出 0 |
| `.\.venv\Scripts\ruff.exe check` | 退出 1。旧审计迁移副本有 5 项，B1 取证脚本 `heartbeat-posix-probe.py` 和 `release-filesystem-probe.py` 有 3 项。后两份脚本与批准包字节一致。生产目录和 B2-T01 测试通过 |

核验了 B1 批准包外层 SHA-256 及内部清单。另对 179 个 B1 基线及冻结设计路径比对通过，其中四个 B1 最终补测文件按最终轮 SHA-256 核对。此轮校验无数据库、文件写入及前端接线，未执行 PostgreSQL/Windows 存储集成、HTTP 端到端与前端构建。
