# Manifest 字段映射

实现：`backend/app/services/attachment_staging.py::AttachmentManifestItem`。Pydantic `extra="forbid"`、`frozen=True`，字段使用严格 int/str。

| 字段 | 冻结约束 | 实现 |
|---|---|---|
| `schema_version` | 整数，必须 1 | `StrictInt` + validator `== 1`；bool/字符串拒绝 |
| `staging_id` | 小写 UUIDv4，同一 manifest 全部相同，与目录名一致 | 正则 `4.../8|9|a|b...` + `uuid.UUID.version == 4` + `str(uuid)==value`；`coerce_manifest_items` 要求集合只有一个 ID；`validate_manifest` 要求目录一致 |
| `ordinal` | 整数 1–100，同一 manifest 唯一，不要求连续 | `StrictInt` + `ge=1/le=100`；`coerce_manifest_items` 检测重复 ordinal |
| `blob` | 严格 `blobs/[0-9]{6}.bin`，由 ordinal 派生 | 正则 + `model_validator` 要求 `blobs/{ordinal:06d}.bin`；文件系统校验解析后必须仍在 staging 根内 |
| `filename` | 1–500；禁止 NUL/CR/LF/控制字符/`/`/`\`/`:`/`..`；仅展示，不进入路径 | 长度、控制字符、Unicode Cc/Cs、路径分隔符、冒号、`..` 全部拒绝；磁盘只写 `blobs/000001.bin` |
| `mime` | 白名单；SVG 拒绝；必须通过内容检测 | 小写裸类型；八类白名单；`image/svg+xml` 拒绝；二进制 magic、文本严格 UTF-8 + 无 NUL |
| `size` | 整数 1–10 MiB；等于实际文件大小 | `StrictInt` + `ge=1/le=10485760`；创建时取实际字节；校验时与 `stat().st_size` 比较 |
| `storage_key` | 小写 64 hex；等于实际 SHA-256/content_hash | 正则；创建时 `sha256_bytes(data)`；校验时重算实际文件 SHA-256 |

## 尺寸/数量

| 约束 | 值 | 实现 |
|---|---:|---|
| 单附件 | 10 MiB | manifest `size`、ZIP 声明大小、实际读取、`validate_manifest` 四层 |
| 单次数量 | 100 | ZIP 声明/实际、manifest、`validate_manifest` |
| 单次总字节 | 100 MiB | ZIP 声明/实际、manifest、`validate_manifest` |
| ZIP 条目总数 | 1000 | 防元数据 DoS；不改变附件 100 限制 |
| 压缩比 | 1000:1（>1 MiB 文件） | 进入读取前拒绝可疑压缩炸弹 |
| 压缩总字节 | 100 MiB | 进入读取前拒绝 |

## 去重与明细

- 同一单文档导入重复 `storage_key` → 422 `ATTACHMENT_MANIFEST_DUPLICATE`，不静默去重。
- 重复 ordinal → 创建时 422 `ATTACHMENT_MANIFEST_INVALID`；approve 校验时 409 `ATTACHMENT_MANIFEST_CORRUPTED`。
- manifest 不写入 `attachment` 表；不新增 DB 表/列。
- manifest 完整性由 Core `ImportEnvelope.context_digest` 覆盖；`_envelope` 使用真实 attachments，不再硬编码空数组。
- `.complete` 保存：`schema_version`、`staging_id`、`completed_at`、`file_count`、`total_bytes`。`.complete` 与目录/manifest 不一致时 fail-closed。

## MIME 来源说明

ZIP 本身不携带 MIME 声明。实现按冻结白名单扩展名映射（`.png/.jpg/.jpeg/.gif/.webp/.pdf/.txt/.md/.markdown/.csv`），再按实际字节执行 magic/UTF-8 校验。扩展名只用于选择期望 MIME，不作为内容真实性依据；未知扩展名和 `.svg` 拒绝。

不声称仅凭文本字节可区分 `text/plain`/`text/markdown`/`text/csv`：三者共享严格 UTF-8 + 无 NUL 检测，以推断出的白名单文本 MIME 写入 manifest。

## 示例

```json
{
  "schema_version": 1,
  "staging_id": "3f2c1a9e-7b6d-4c2a-9f10-8e7d6c5b4a31",
  "ordinal": 1,
  "blob": "blobs/000001.bin",
  "filename": "design.png",
  "mime": "image/png",
  "size": 184320,
  "storage_key": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
}
```