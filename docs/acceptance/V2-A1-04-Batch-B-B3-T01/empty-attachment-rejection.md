# P2-01 · 零字节附件稳定拒绝

## 1. 冻结行为

- 稳定码：`ATTACHMENT_EMPTY`
- HTTP：400（`_ERROR_STATUS` L153）
- 拒绝阶段：ZIP 元数据阶段，**读取内容与创建 staging 之前**
- 数据库写入：0（不创建 Attachment、不创建 ReviewRequest、不改文档）
- 磁盘写入：0（不创建 staging 目录）

## 2. 实现位置

`backend/app/services/attachment_staging.py` `parse_import_zip`（L726–740）：

```python
if attachment_infos:
    if len(document_infos) > 1:
        raise _staging_error(ATTACHMENT_IMPORT_UNSUPPORTED, ...)
    if len(attachment_infos) > max_attachment_count:
        raise _staging_error(ATTACHMENT_COUNT_EXCEEDED)
    for info, _ in attachment_infos:
        if info.file_size == 0:
            # Metadata-stage rejection: no read, no staging, no DB row.
            raise _staging_error(ATTACHMENT_EMPTY)
        if info.file_size > max_file_bytes:
            raise _staging_error(ATTACHMENT_TOO_LARGE)
```

判定依据是中央目录的 `ZipInfo.file_size`，不依赖解压后的空 bytes，因此：

- 不会先解压/写盘再拒绝；
- 空文件与“解压失败得到空流”可区分（后者走 `IMPORT_ARCHIVE_INVALID`）；
- 不会把空附件静默忽略后继续导入文档。

`ATTACHMENT_EMPTY` 由 `attachment_validation.py` 定义并在 `attachment_staging.py` 的 `__all__` 中导出，路由层按 `status_code` 映射为 400。

## 3. 验证

`backend/tests/test_attachment_staging.py::TestEmptyAttachmentRejection::test_zero_byte_attachment_rejected_before_staging`，参数化 `.txt` / `.md` / `.csv`：

- 响应 400，`code == ATTACHMENT_EMPTY`；
- staging 根目录零子目录；
- Attachment 计数不变；
- ReviewRequest 计数不变。

原始日志：`evidence/remediation/b3-t01-special.log`（54 passed）。

## 4. 边界

- 该规则只针对 `attachments/` 下的附件；空文档不由此码处理；
- “零字节”指 ZIP 声明的 `file_size == 0`，与真实解压长度不一致的情况另由 `_read_bounded` 的 size mismatch 拒绝（`IMPORT_ARCHIVE_INVALID`）。