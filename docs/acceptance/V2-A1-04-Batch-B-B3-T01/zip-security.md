# ZIP 安全处理

实现：`parse_import_zip` 与 `AttachmentStagingService.inspect_zip`。所有路径与元数据先检查，再按限制读取；任何拒绝都发生在 staging 创建之前。

## 1. 解析顺序

1. Base64 解码由路由完成；非法 Base64 → 400 `IMPORT_ARCHIVE_INVALID`。
2. 打开 ZIP，只读取 central directory，不落盘解压。
3. 遍历全部 `ZipInfo`：
   - 检查原始文件名 `orig_filename` 含 NUL（zipfile 会把 `filename` 截断，必须查原值）；
   - 校验完整规范路径；
   - 拒绝符号链接/重解析点、加密条目、不支持的压缩法、异常声明大小、可疑压缩比；
   - 检测重复规范路径与大小写/Unicode 规范化冲突。
4. 以**全部条目**（含未选中的文档/附件之外条目）的压缩字节总和核对整体压缩预算，未选中条目从不读取，但不能借此绕过预算。
5. 根据已验证路径分类：
   - 根 `manifest.json`；
   - 根下 `attachments/` 普通文件；
   - `attachments/` 子树外的 `.md/.markdown` 文档。
6. 含附件时先判断归属：必须恰好一篇非附件 Markdown；多篇整包拒绝。
7. 再执行数量/单文件/总字节限制；附件 `file_size == 0` 在元数据阶段直接 400 `ATTACHMENT_EMPTY`。
8. 只对选中的文档、根 manifest、附件执行有界读取；根 manifest 也计入读取预算。

## 2. 路径规则

拒绝：

- NUL、反斜杠（非规范 ZIP 路径）、控制字符；
- 绝对路径（`/...`）、Windows 盘符（`C:...`）；
- UNC（`//server/...`）；
- ADS（任意路径段含 `:`）；
- 空段、`.`、`..`、双斜杠；
- 超过 4096 字符；
- 重复 exact path；
- NFC + casefold 后冲突（大小写归一化冲突）；
- ZIP symlink（`external_attr` 模式）；
- 加密条目（flag bit 0）；
- 非 STORED/DEFLATED 压缩法。

## 3. 归属规则

- 只有完整路径位于根 `attachments/` 下的普通文件被视为附件。
- 含附件 ZIP 只支持恰好一篇非 `attachments/` 子树 Markdown。
- 多篇 + 附件 → 整包 400 `ATTACHMENT_IMPORT_UNSUPPORTED`。
- 零篇 + 附件：
  - 明确 target 且 Active → 400 `ATTACHMENT_ONLY_IMPORT_UNSUPPORTED`；
  - 其余 → 400 `ATTACHMENT_IMPORT_UNSUPPORTED`；
  - 不创建 staging。
- 附件文件名只用于 manifest 展示/下载提示和 MIME 扩展名映射；磁盘写入固定 `blobs/NNNNNN.bin`。
- 根 `manifest.json` 唯一；附件子树内 `manifest.json` 不当作传输 manifest。

## 4. 资源限制与 ZIP bomb

| 项 | 行为 |
|---|---|
| 单附件声明 >10 MiB | 413 `ATTACHMENT_TOO_LARGE`，读取前拒绝 |
| 实际读取 >10 MiB | 有界读取检测并拒绝 |
| 附件数量 >100 | 413 `ATTACHMENT_COUNT_EXCEEDED` |
| 附件总声明/实际 >100 MiB | 413 `ATTACHMENT_TOTAL_TOO_LARGE` |
| 选中文件声明总和 >100 MiB | 413 |
| 压缩总字节 >100 MiB（全部条目） | 400 `IMPORT_ARCHIVE_INVALID` |
| 选中文档/附件 + 根 manifest 压缩字节总和 >100 MiB | 400 `IMPORT_ARCHIVE_INVALID` |
| 根 `manifest.json` 实际读取 >100 MiB | 413 / 400 上限拒绝 |
| ZIP 条目总数 >1000 | 400 `IMPORT_ARCHIVE_INVALID` |
| 单条目 >1 MiB 且压缩比 >1000:1 | 400 `IMPORT_ARCHIVE_INVALID` |
| 附件声明大小为 0 | 400 `ATTACHMENT_EMPTY`，元数据阶段拒绝 |
| 声明大小与实际读取不一致 | 400 `IMPORT_ARCHIVE_INVALID` |
| 损坏 CRC/Deflate/截断流 | 400 `IMPORT_ARCHIVE_INVALID`，不是 500 |

读取使用 `zipfile.open` + 1 MiB 分块 + 上限；不调用无界 `archive.read()`，不将解压内容落盘。

## 5. MIME 与内容

- 附件 MIME 由白名单扩展名推断，随后按实际字节校验：
  - 二进制：PNG/JPEG/GIF/WebP/PDF magic；
  - 文本：严格 UTF-8 + 无 NUL + 不命中已知二进制 magic；
  - `.svg` 推断为 `image/svg+xml` 后拒绝。
- 文本子类型不因字节不同被区分，不声称可区分 TXT/Markdown/CSV。

## 6. 测试证据

`test_attachment_staging.py::TestZipSafety` 与 `TestStagingValidation` 覆盖：

- `../`、绝对路径、UNC、盘符、ADS、路径内 `../`；
- 重复 exact path、大小写冲突；
- 多文档归属歧义；
- 101 附件数量上限；
- 高压缩比 ZIP bomb；
- MIME 伪装（`.png` 实为 PDF）；
- 附件数量/内容均在创建 staging 前拒绝，staging 目录为 0。

整改新增覆盖（`TestEmptyAttachmentRejection`、`TestCorruptZipMapping`、`TestZipBudgetBoundaries`）：

- 零字节 `.txt/.md/.csv` 附件 400 `ATTACHMENT_EMPTY`；
- CRC 不匹配、非法 Deflate、截断 Deflate → 400 `IMPORT_ARCHIVE_INVALID`；
- `orig_filename` 含 NUL；
- 未选中条目的压缩字节计入整体预算；
- 根 `manifest.json` 计入预算；
- 真实 104 857 601 字节 ZIP 在元数据阶段拒绝（`evidence/remediation/real-100mib-boundary.log`）。

原始结果见 `evidence/b3-staging-windows.log` 与 `evidence/remediation/b3-t01-special.log`。