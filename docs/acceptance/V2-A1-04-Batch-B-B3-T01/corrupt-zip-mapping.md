# P2-02 · 损坏 ZIP 解压异常映射

## 1. 目标

ZIP 中央目录可信但数据流损坏时，不得抛出未捕获异常导致 500；统一映射为冻结的 400 `IMPORT_ARCHIVE_INVALID`，且不创建 staging、不写数据库。

## 2. 实现

### 2.1 打开阶段

`parse_import_zip`（L682–685）：

```python
try:
    archive = zipfile.ZipFile(io.BytesIO(raw))
except (zipfile.BadZipFile, OSError, ValueError) as exc:
    raise _staging_error(IMPORT_ARCHIVE_INVALID, "invalid zip") from exc
```

### 2.2 有界读取阶段

`_read_bounded`（L633–668）在 `archive.open()` / `handle.read()` 期间捕获：

| 异常 | 典型来源 |
|---|---|
| `zipfile.BadZipFile` | CRC 校验失败、头部不一致 |
| `zlib.error` | Deflate 流非法 |
| `EOFError` | Deflate 流被截断 |
| `RuntimeError` | zipfile 内部对不支持/损坏流的包装 |
| `OSError` / `ValueError` | 句柄与参数层异常 |

统一转为 `IMPORT_ARCHIVE_INVALID`；`AttachmentStagingError`（如超限）先被重新抛出，不被吞掉。读取完成后再校验：

```python
if len(output) != info.file_size:
    raise _staging_error(IMPORT_ARCHIVE_INVALID, "zip size mismatch")
```

因此“解压成功但长度与声明不符”同样拒绝，不会把截断内容当附件。

### 2.3 发生时机

解析在 `stage_from_zip` 的 `_prepare_parsed` 内、创建 staging 目录之前完成；异常路径没有 staging 目录可清理，也没有 pending/附件写入。

## 3. 验证

`backend/tests/test_attachment_staging.py::TestCorruptZipMapping`

| 测试 | 构造方式 | 断言 |
|---|---|---|
| `test_crc_mismatch_maps_to_import_archive_invalid` | 真实 ZIP 本地头/中央目录，CRC 取反 | 400 `IMPORT_ARCHIVE_INVALID`，零 staging，零 ReviewRequest |
| `test_invalid_deflate_stream_maps_to_import_archive_invalid` | `ZIP_DEFLATED` + 非 Deflate 字节 `\xff\xff\xff\xff` | 400，零 staging |
| `test_truncated_deflate_maps_to_import_archive_invalid` | 合法 Deflate 流截去末尾 8 字节 | 400，零 staging |

测试使用 `_raw_single_entry_zip` 生成真实损坏归档（真实 central directory、真实压缩流），没有 mock `_read_bounded` 或整个导入函数。

原始日志：`evidence/remediation/b3-t01-special.log`（54 passed）。

## 4. 边界

- 只覆盖 zipfile/zlib 已知异常集合；“进程被 kill”“磁盘 I/O 中断”不在本映射范围；
- 未对全部可能的畸形 ZIP 变体做穷举，只覆盖 CRC、非法 Deflate、截断三类代表路径；
- 映射后仅返回稳定码，不向客户端回传异常文本。