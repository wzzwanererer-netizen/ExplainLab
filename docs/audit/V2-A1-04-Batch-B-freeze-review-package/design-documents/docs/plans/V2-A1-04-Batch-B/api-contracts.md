# API Contracts

本文件冻结 Batch B 的 HTTP 入参、出参、状态码、错误码与 MIME/大小规则。所有路由统一挂在 `/api` 下；错误响应体只含稳定错误码（FastAPI 的 `detail`），不回传路径/堆栈/异常文本。

## 1. 路由总表

| 方法 | 路径 | 用途 | 成功状态 |
|---|---|---|---|
| `POST` | `/api/knowledge/{item_id}/attachments` | 上传一个附件（JSON base64） | 201 新建引用；200 复用同 item+key 引用 |
| `GET` | `/api/knowledge/{item_id}/attachments` | 列出附件元数据（O-B04） | 200 |
| `GET` | `/api/knowledge/{item_id}/attachments/{attachment_id}` | 下载附件字节 | 200 |
| `DELETE` | `/api/knowledge/{item_id}/attachments/{attachment_id}` | 删除引用并入队 GC | 204 |
| `POST` | `/api/knowledge/import` | 既有单篇导入（附件 ZIP-only） | 既有 |
| `POST` | `/api/knowledge/import/batch` | 既有批量导入（附件 ZIP-only） | 既有 |
| `POST` | `/api/knowledge/export` | 既有导出（附件继续拒绝） | 200 ZIP |
| `GET` | `/api/knowledge/{item_id}/markdown` | 既有单篇 Markdown 导出 | 200 |

- **新增**附件元数据列表端点（O-B04），只返回元数据；不返回 blob 内容/物理路径。
- **不新增** GC/ORP 管理端点（O-B07）；人工恢复/重试仅内部函数 + 审计日志。
- 所有写路由为同步 `def`（D20），由 FastAPI 线程池执行；不得在 async 路由里做阻塞文件/DB 操作。列表/下载同样为同步 `def`，但只读，不取 `StorageKeyLock`。
- 不新增鉴权；Batch B 仍是本机单用户 API，不得暴露到公网（Batch D 范围）。

## 2. 上传

### 2.1 请求

```http
POST /api/knowledge/{item_id}/attachments
Content-Type: application/json
```

```json
{
  "filename": "design.png",
  "mime": "image/png",
  "content_base64": "iVBORw0KGgo..."
}
```

- 请求体为 Pydantic 模型，`extra="forbid"`；仅接受 `filename` / `mime` / `content_base64` 三个字段。
- **不使用 multipart**：现有依赖中没有 `python-multipart`，Batch B 不新增依赖；上传走 JSON base64，与既有 `archive_base64` 风格一致。
- `item_id` 必须存在 → 否则 404 `ITEM_NOT_FOUND`。
- `archived` item 禁止新增附件 → 409 `ATTACHMENT_ITEM_ARCHIVED`（O-B06）；预检已 archived 时在解码/写临时文件前拒绝。发布后仍须在业务事务中保护 item 状态；归档先提交时零附件提交，已发布的无引用 blob 由 ORP 处理。`archived` 仍允许列表/下载/删除引用；`deleted`/不存在按 404。
- `filename` 必填；长度 1–500。上传时清洗为**安全显示名**：取 basename、去掉 NUL/CR/LF/控制字符、把 `/`/`\`/`:` 替换为 `_`、折叠 `..`；不进入磁盘路径。清洗后为空或超长 → 400 `ATTACHMENT_FILENAME_INVALID`。Windows 保留名同样替换为安全显示名，不作为路径使用。
- `mime` 必填，必须是白名单 MIME；SVG 直接拒绝。实际内容由 magic/UTF-8 校验（§4）。
- `content_base64` 必填；标准 Base64（带 padding），严格解码；非法编码 → 400 `ATTACHMENT_BASE64_INVALID`。
- 解码后 0 字节 → 400 `ATTACHMENT_EMPTY`。
- 解码后大于 10 MiB，或编码字符串长度超过 `4 * ceil(10 MiB / 3) = 13,981,016`（解码前拒绝）→ 413 `ATTACHMENT_TOO_LARGE`。
- `Content-Length` 不可信；以实际 JSON 解析与解码结果为准。

### 2.2 成功响应

`201 Created`（新引用）或 `200 OK`（同 item+key 已存在）：

```json
{
  "id": "2b0f0e2a-6b7c-4d5e-8f90-123456789abc",
  "item_id": "9a7b...",
  "filename": "design.png",
  "mime": "image/png",
  "size": 184320,
  "storage_key": "9f86...64hex",
  "content_hash": "9f86...64hex",
  "created_at": "2026-11-22T12:00:00Z"
}
```

- 不返回物理路径、不返回 `storage_key` 之外的内部信息；`storage_key==content_hash` 必须成立。
- `Location: /api/knowledge/{item_id}/attachments/{id}`（201 时）。
- 响应成功只表示引用已提交；不表示物理/DB 原子。

### 2.3 失败

| 状态 | 错误码 | 条件 |
|---|---|---|
| 404 | `ITEM_NOT_FOUND` | item 不存在（沿用既有码） |
| 409 | `ATTACHMENT_ITEM_ARCHIVED` | item 已归档，禁止新增附件（O-B06） |
| 400 | `ATTACHMENT_EMPTY` | 解码后 0 字节 |
| 400 | `ATTACHMENT_BASE64_INVALID` | Base64 编码非法 |
| 400 | `ATTACHMENT_FILENAME_INVALID` | 清洗后文件名为空/超长 |
| 409 | `STORAGE_LOCK_TIMEOUT` | 10s 内未获 key 锁 |
| 409 | `ATTACHMENT_KEY_COLLISION` | 正式 key 已存在但内容/hash 不同 |
| 413 | `ATTACHMENT_TOO_LARGE` | >10 MiB |
| 415 | `ATTACHMENT_MIME_UNSUPPORTED` | 声明/实际类型不在白名单 |
| 415 | `ATTACHMENT_CONTENT_MISMATCH` | 声明类型与实际字节不符 |
| 422 | `ATTACHMENT_HASH_MISMATCH` | 服务端计算/重读 hash 不一致 |
| 503 | `ATTACHMENT_WRITE_FAILED` | 发布 I/O 失败 |
| 503 | `ATTACHMENT_WRITE_CORRUPTED` | 发布后校验失败，已隔离 |
| 503 | `ATTACHMENT_WRITE_BUSY` | Windows 占用重试耗尽（附 `Retry-After: 1`） |
| 503 | `ATTACHMENT_STORAGE_UNAVAILABLE` | 根不可用 |
| 503 | `ATTACHMENT_STORAGE_CROSS_VOLUME` | 运行期发现跨卷 |
| 503 | `STORAGE_LEASE_LOST` | 心跳/校验失败，操作中止 |

## 2.4 列表（元数据，O-B04）

```http
GET /api/knowledge/{item_id}/attachments
```

- 成功 `200`，JSON 数组，元素为 §2.2 的 `AttachmentOut`；不返回内容、物理路径或其它 item 的附件。
- 排序稳定：`created_at ASC, id ASC`。
- 不存在 item → 404 `ITEM_NOT_FOUND`；`archived` item 允许列表（O-B06）。
- 只读 DB 元数据：不做 hash/size 校验，不取 `StorageKeyLock`，不触发 GC/ORP。
- 不新增分页/搜索参数；本冻结不承诺大数据量优化。

## 3. 下载

```http
GET /api/knowledge/{item_id}/attachments/{attachment_id}
```

- item 或 attachment 不存在、或 attachment 不属于 item → 404 `ATTACHMENT_NOT_FOUND`（不泄露跨 item 存在性）。
- `archived` item 允许下载（O-B06）。
- 成功 `200`，正文为原始字节；流式输出，不整体读入内存。
- **同一句柄**：下载先打开正式 blob 一次，用该句柄完成 size/hash 校验，`seek(0)` 后从同一句柄流式输出；禁止按路径重新 open，也禁止使用会重新打开路径的 `FileResponse`。打开后即使路径被 rename/替换，句柄仍指向已校验内容；外部进程原地改写仍是残余风险，不得宣称完全消除 TOCTOU。
- 响应头：

| 头 | 值 |
|---|---|
| `Content-Type` | DB 中经校验的 MIME（不信任客户端再次声明） |
| `Content-Length` | DB `size`；与实际文件不一致则 503 |
| `Content-Disposition` | `attachment; filename="<ASCII fallback>"; filename*=UTF-8''<percent-encoded>` |
| `ETag` | `"<storage_key>"` |
| `Cache-Control` | `private, max-age=0, must-revalidate` |
| `X-Content-Type-Options` | `nosniff` |

- 文件名清洗：去掉 CR/LF/引号/路径分隔符；ASCII fallback 用 `_` 替代非法字符；UTF-8 部分按 RFC 5987 编码。
- 文件缺失 → 503 `ATTACHMENT_BLOB_MISSING`；文件大小/hash 不符 → 503 `ATTACHMENT_BLOB_CORRUPTED`；两者都不自动删除 DB 行、不返回部分内容。
- 读取阶段非缺失、非损坏的一般存储 I/O 错误以 503 `ATTACHMENT_STORAGE_UNAVAILABLE` 返回。校验前异常和流关闭路径均关闭句柄。响应开始后的传输中断结束流并清理句柄。
- 不实现 Range/HEAD/缓存预热；如未来需要，另立裁决。
- 下载不加 `StorageKeyLock`；与 GC 隔离的瞬时竞争按 503 + 客户端重试处理。

## 4. MIME、magic 与大小

### 4.1 白名单（D-08）

| MIME | 扩展名提示 | 检测 |
|---|---|---|
| `image/png` | `.png` | `89 50 4E 47 0D 0A 1A 0A` |
| `image/jpeg` | `.jpg/.jpeg` | `FF D8 FF` |
| `image/gif` | `.gif` | `GIF87a` / `GIF89a` |
| `image/webp` | `.webp` | `RIFF....WEBP` |
| `application/pdf` | `.pdf` | `%PDF-` |
| `text/plain` | `.txt` | 严格 UTF-8，无 NUL |
| `text/markdown` | `.md/.markdown` | 严格 UTF-8，无 NUL |
| `text/csv` | `.csv` | 严格 UTF-8，无 NUL |

- **SVG 永不允许**：`image/svg+xml` 一律 415；伪装为文本的 SVG 不会以 `image/svg+xml` 提供，下载头固定 `attachment` + `nosniff`（D-B13 已裁决）。
- 单文件上限 10 MiB（10,485,760 字节），含文本；空文件 → 400 `ATTACHMENT_EMPTY`。
- 扩展名不是权威；声明 MIME 必须通过对应类型的检测（见 §4.2）。扩展名与声明不一致不单独报错，但不能绕过内容校验。
- **二进制与文本分开**：
  - 二进制类型（PNG/JPEG/GIF/WebP/PDF）按 magic 判定实际类型，必须与声明一致。
  - 文本类型（`text/plain`/`text/markdown`/`text/csv`）只做严格 UTF-8 解码 + 无 NUL 校验；**不声称仅凭文本字节可以可靠区分 TXT/Markdown/CSV**。三者共享文本检测，以声明的白名单文本 MIME 写入 DB。
  - 若声明为文本但字节是已知二进制 magic（或含 NUL/非法 UTF-8）→ 415 `ATTACHMENT_CONTENT_MISMATCH`。
- 不做 BOM 强制；BOM 可作为文本内容保留。

### 4.2 声明与实际

1. 读取 JSON 的 `mime`，去掉参数、转小写。
2. 声明不在白名单 → 415 `ATTACHMENT_MIME_UNSUPPORTED`（SVG 同）。
3. 严格解码 `content_base64`；读取解码后前 16 字节做 magic 检测。
4. 声明为二进制：magic 必须匹配该类型，否则 415 `ATTACHMENT_CONTENT_MISMATCH`。
5. 声明为文本：严格 UTF-8 解码且无 NUL；若同时命中已知二进制 magic → 415 `ATTACHMENT_CONTENT_MISMATCH`。不进一步区分 TXT/Markdown/CSV。
6. 通过后以**声明 MIME**（已通过对应检测）写入 DB；不使用客户端文件名推断。
7. `size` 以解码后实际字节为准；与客户端声明不一致不报错（客户端可撒谎），以实际为准。

## 5. 导入/导出附件

### 5.1 Transport、归属和响应

- `archive_base64` 是附件唯一传输方式；根 `attachments/` 中的普通文件归唯一一篇非附件目录 Markdown。已有无附件 ZIP 仍可多篇。解析按完整规范路径识别，`manifest.json` 保持既有导出校验格式，Markdown frontmatter 附件引用与物理文件不混用。
- 含附件 ZIP 两个入口统一适用 §5.3 的整包拒绝。明确 target_item_id 只能作单篇 ZIP 候选，来源身份优先按 Batch A 解析。多文档、无有效归属、已应用 Draft 缺请求附件、archived 目标均以 `ATTACHMENT_IMPORT_UNSUPPORTED` 明确拒绝。零 Markdown 且明确目标为 Active 单列附件-only，规则见 attachment-lifecycle §3.1。
- `MarkdownImportIn.attachments` 或 `documents[].attachments` 非空仍不传物理附件。单篇入口 400 `ATTACHMENT_IMPORT_UNSUPPORTED`；批量按 Batch A 逐篇 `unsupported`、其它篇继续。既有顶层/逐篇 payload 冲突照 Batch A 处理，ZIP 请求不得借 JSON 附件字段追加附件。
- Active 仅在 title/content 变更时携带附件创建 pending。无此变化且附件未满足时 400 `ATTACHMENT_ONLY_IMPORT_UNSUPPORTED`；不建 staging/pending。相同 pending 的逻辑附件集合完全相等且 staging 可用才复用；不同文档 Hash 或集合返回 409 `SOURCE_HAS_PENDING_IMPORT`。
- 使用既有 `ImportReport`。成功时后端在对应 item 的既有 warnings 写 `attachments_staged`、`attachments_applied`、`attachments_already_satisfied` 或 `attachments_pending_reused` 之一。warnings 是状态摘要，无新增 Core 字段；失败按 §5.3；不回显用户文件名或物理路径作为错误细节。
- 单附件 10 MiB、最多 100 个、合计 100 MiB，按实际解压字节强制。解析异常与业务异常在路由同一稳定错误映射下处理。

### 5.2 导出（继续不支持附件）

- `MarkdownExportIn.include_attachments=true` → 400 `ATTACHMENT_EXPORT_UNSUPPORTED`（决策 20，永久 Batch B 行为）。
- 单篇 Markdown 导出不包含附件；不新增附件下载 URL。

### 5.3 稳定错误码（导入相关）

| 状态 | 错误码 | 条件 |
|---|---|---|
| 400 | `ATTACHMENT_IMPORT_UNSUPPORTED` | 单篇 JSON 附件；ZIP 无唯一归属、archived 目标、已应用 Draft 缺请求附件；批量 JSON 附件在逐篇报告中使用同一码 |
| 400 | `ATTACHMENT_ONLY_IMPORT_UNSUPPORTED` | Active 无 title/content 变化且附件未满足，或零文档且明确目标为 Active |
| 409 | `ATTACHMENT_ITEM_ARCHIVED` | 目标 item 已归档（已有 pending 时 approve） |
| 409 | `SOURCE_CHANGED_DURING_WAIT` | 发布后复核发现来源/目标或导入分支漂移（沿用既有码） |
| 409 | `SOURCE_HAS_PENDING_IMPORT` | 同来源已有不同文档 Hash 或不同逻辑附件集合 pending（既有） |
| 409 | `IMPORT_ENVELOPE_INVALID` | envelope 版本/摘要/结构失败，或 S0/S1 漂移（既有码） |
| 409 | `ATTACHMENT_MANIFEST_CORRUPTED` | envelope 验证成功但附件元素结构非法 |
| 409 | `ATTACHMENT_STAGING_INVALID` | staging `.complete`/文件/hash/size/路径非法 |
| 409 | `ATTACHMENT_STAGING_MISSING` | staging 目录不存在 |
| 409 | `STORAGE_LOCK_TIMEOUT` | 预发布或带附件重试获取存储锁超时 |
| 503 | `STORAGE_LEASE_LOST` | commit 前 fencing 校验失败 |
| 503 | `ATTACHMENT_BLOB_MISSING` / `ATTACHMENT_BLOB_CORRUPTED` | 已应用重试已有引用但正式文件缺失或校验失败 |
| 400 | `IMPORT_ARCHIVE_INVALID` | ZIP 结构、非法或重复规范路径等解析问题 |
| 413 | `ATTACHMENT_TOO_LARGE` | 单文件 >10 MiB |
| 413 | `ATTACHMENT_COUNT_EXCEEDED` | 单次导入附件数 >100 |
| 413 | `ATTACHMENT_TOTAL_TOO_LARGE` | 单次导入总字节 >100 MiB |
| 422 | `ATTACHMENT_MANIFEST_INVALID` | 创建 staging 时元素 schema 非法 |
| 422 | `ATTACHMENT_MANIFEST_DUPLICATE` | 单次导入重复 storage_key |

## 6. 配置与错误映射

- 附件 DTO 的 422 响应仅给稳定字段错误（字段位置与类型），过滤原始 input 和可能包含字节或路径的上下文。
- DELETE 写失败且任务表不可用 → 503 `ATTACHMENT_MAINTENANCE_UNAVAILABLE`；其它未知写失败 → 500 `ATTACHMENT_FAILED`，整笔回滚。
- 路由层只捕获业务异常并映射为 `HTTPException(status_code, detail=stable_code)`；不得返回 `str(exc)`。
- 新异常基类建议：`AttachmentServiceError(code, status_code)`；映射表集中，禁止散落字符串。
- `_http_error()` 扩展为同时识别 `AttachmentServiceError`；既有 `MarkdownServiceError/SourceIdentityError/ExporterMetadataError` 映射不变。
- 未知异常 → 500 `ATTACHMENT_FAILED` / 既有 `IMPORT_FAILED`；日志只记异常类型。
- `Retry-After` 仅用于 503 的忙碌/存储不可用；不得用于 409 锁超时（客户端可自行重试）。

## 7. 稳定错误码登记

### 7.1 保留的既有码（不得改名/改语义）

```text
ATTACHMENT_IMPORT_UNSUPPORTED
ATTACHMENT_EXPORT_UNSUPPORTED
ATTACHMENT_REVIEW_UNSUPPORTED
IMPORT_EMPTY
IMPORT_ARCHIVE_INVALID
IMPORT_ENVELOPE_INVALID
IMPORT_FAILED
IMPORT_LOCK_TIMEOUT
SOURCE_CHANGED_DURING_WAIT
SOURCE_HAS_PENDING_IMPORT
SOURCE_IDENTITY_AMBIGUOUS
SOURCE_IDENTITY_ORPHAN
EXPORT_EMPTY
EXPORT_FAILED
EXPORT_MANIFEST_COLLISION
ITEM_NOT_FOUND
DATABASE_UNAVAILABLE
DATABASE_TIMEOUT
```

### 7.2 Batch B 新增码（本次冻结登记）

```text
ATTACHMENT_EMPTY
ATTACHMENT_BASE64_INVALID
ATTACHMENT_TOO_LARGE
ATTACHMENT_MIME_UNSUPPORTED
ATTACHMENT_CONTENT_MISMATCH
ATTACHMENT_HASH_MISMATCH
ATTACHMENT_FILENAME_INVALID
ATTACHMENT_NOT_FOUND
ATTACHMENT_KEY_COLLISION
ATTACHMENT_ITEM_ARCHIVED
ATTACHMENT_ONLY_IMPORT_UNSUPPORTED
ATTACHMENT_BLOB_MISSING
ATTACHMENT_BLOB_CORRUPTED
ATTACHMENT_WRITE_FAILED
ATTACHMENT_WRITE_CORRUPTED
ATTACHMENT_WRITE_BUSY
ATTACHMENT_STORAGE_UNAVAILABLE
ATTACHMENT_STORAGE_CROSS_VOLUME
ATTACHMENT_FAILED
ATTACHMENT_MANIFEST_INVALID
ATTACHMENT_MANIFEST_CORRUPTED
ATTACHMENT_MANIFEST_DUPLICATE
ATTACHMENT_STAGING_INVALID
ATTACHMENT_STAGING_MISSING
ATTACHMENT_COUNT_EXCEEDED
ATTACHMENT_TOTAL_TOO_LARGE
ATTACHMENT_MAINTENANCE_UNAVAILABLE
STORAGE_LOCK_TIMEOUT
STORAGE_LEASE_LOST
STORAGE_LOCK_RELEASE_FAILED
```

- 新码只用于 Batch B 语义；不得与既有码互换。
- 码表是冻结契约；实现时集中定义常量，测试逐项断言 HTTP 状态 + 码。

## 8. 导出（明确不支持附件）

```http
POST /api/knowledge/export
{ "ids": ["..."], "space_id": null, "include_attachments": true }
```

→ 400 `ATTACHMENT_EXPORT_UNSUPPORTED`；即使请求中存在附件也不打包、不回填链接。

- 单篇 `GET /api/knowledge/{id}/markdown` 永不内嵌附件。
- 不新增附件导出端点、不新增 BAK、不生成附件清单。
- 现有 `EXPORT_EMPTY`/`EXPORT_FAILED`/`EXPORT_MANIFEST_COLLISION` 行为不变。

## 9. 兼容与版本

- 既有导入/导出/审核响应字段不删除、不改名；Batch B 新增附件路由、列表端点与错误码。
- 上传/下载/删除/列表不改变 `KnowledgeOut` 的附件字段（当前无）；不把附件数组嵌入 item 响应。
- 前端不强制改动；Batch B 以 API 验收为主；前端不得在 O-B01/O-B06/O-B08 语义之外自行推断附件行为。
- 导入附件固定 ZIP-only，JSON 单篇 400 与批量逐篇 unsupported 保持 Batch A 口径。

## 10. 请求/响应示例

### 10.1 上传成功

```http
POST /api/knowledge/9a7b.../attachments
Content-Type: application/json

{"filename":"design.png","mime":"image/png","content_base64":"iVBORw0KGgo..."}
```

```http
HTTP/1.1 201 Created
Location: /api/knowledge/9a7b.../attachments/2b0f...
Content-Type: application/json

{"id":"2b0f...","item_id":"9a7b...","filename":"design.png",
 "mime":"image/png","size":184320,
 "storage_key":"9f86...","content_hash":"9f86...",
 "created_at":"2026-11-22T12:00:00Z"}
```

### 10.2 超限

```http
HTTP/1.1 413 Payload Too Large
Content-Type: application/json

{"detail":"ATTACHMENT_TOO_LARGE"}
```

### 10.3 锁超时

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{"detail":"STORAGE_LOCK_TIMEOUT"}
```

### 10.4 下载头

```http
HTTP/1.1 200 OK
Content-Type: image/png
Content-Length: 184320
Content-Disposition: attachment; filename="design.png"; filename*=UTF-8''design.png
ETag: "9f86..."
Cache-Control: private, max-age=0, must-revalidate
X-Content-Type-Options: nosniff
```
