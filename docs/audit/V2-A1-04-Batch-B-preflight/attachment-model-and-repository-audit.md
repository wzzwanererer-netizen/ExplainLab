# Attachment Model and Repository Audit

## 1. 审计范围

- Core 实体与端口：`domain/entities.py`、`ports.py`
- backend ORM 与迁移：`app/models.py`、`alembic/versions/0006_v2_markdown_kb.py`
- backend 仓库：`app/services/repositories_v2.py`
- 正式设计：`V2-A1-04-implementation-plan.md` §5.3、§7、§16、§21.2
- 验收矩阵：`V2-A1-04-acceptance-matrix.md` §B（ATT-01…ATT-12）

## 2. 模型现状

### 2.1 `Attachment`（Core）

```python
class Attachment(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    item_id: UUID
    filename: str = Field(min_length=1, max_length=500)
    mime: str = Field(min_length=1, max_length=200)
    size: int = Field(ge=0)
    storage_key: str = Field(min_length=1, max_length=64)
    content_hash: str = Field(min_length=1, max_length=64)
    created_at: datetime = Field(default_factory=utcnow)
```

| 检查项 | 现状 | 标签 |
|---|---|---|
| 纯 Pydantic、无 ORM/Web 依赖 | 是 | 已实现 |
| 字段与 ORM 对齐 | id/item_id/filename/mime/size/storage_key/content_hash/created_at 对齐 | 已实现 |
| `storage_key == content_hash` | 无校验 | 未实现 |
| `storage_key` 为 64 位十六进制 sha256 | 只校验长度 1–64，不校验字符集/长度=64 | 未实现 |
| `content_hash` 为 sha256 | 同上 | 未实现 |
| `size` 上限 | 无（仅 >=0） | 未实现 |
| `mime` 白名单 | 无 | 未实现 |
| 文件名清洗/路径分隔符拒绝 | 无 | 未实现 |
| 同 item 同 storage_key 去重不变量 | 无 | 需要 ChatGPT 决策 |
| 附件的 `space_id` | 无此字段，经 item 间接归属 | 已实现（现状） |

**判断：实体是“存储事实”的最小载体，不承载安全策略。策略放服务层是可接受的，但当前没有任何层实现这些校验。** 标签：部分实现。

### 2.2 `AttachmentORM`

```python
__tablename__ = "attachment"
__table_args__ = (Index("ix_attachment_storage_key", "storage_key"),)
id: String(36) PK
item_id: String(36) FK knowledge_item.id ON DELETE CASCADE, nullable=False
filename: String(500), nullable=False
mime: String(200), nullable=False
size: Integer, nullable=False, default=0
storage_key: String(64), nullable=False
content_hash: String(64), nullable=False
created_at: DateTime(timezone=True), nullable=False
```

| 检查项 | 现状 | 标签 |
|---|---|---|
| 表存在且迁移可回滚 | `0006` 创建/删除 | 已实现 |
| item 删除级联 attachment 行 | FK CASCADE 已测 | 已实现 |
| `storage_key` 查询索引 | 有 | 已实现 |
| `content_hash` 索引 | 无；但 `find_by_hash` 需要按 content_hash 查询 | 未实现（性能/契约） |
| `(item_id, storage_key)` 唯一 | 无 | 需要 ChatGPT 决策 |
| `storage_key` 唯一 | 无（多 item 共享同一 blob，必须非唯一） | 已实现（正确） |
| `size >= 0` CHECK | 无 DB CHECK | 部分实现 |
| `storage_key` 长度=64 CHECK | 无 | 未实现 |

**注意：`find_by_hash` 端口按 `content_hash` 查，但表上没有 content_hash 索引。若 Batch B 实现该端口，需决定是加索引（新迁移，可能违反“不新增迁移”约束）还是接受全表扫描。** 标签：需要 ChatGPT 决策。

### 2.3 引用计数语义

- 设计采用“派生引用数”，不设计数器列。
- 权威查询：`SELECT COUNT(*) FROM attachment WHERE storage_key = ?`。
- `test_v2_models.py:448-463` 已验证两个 item 共享同一 `storage_key` 时 COUNT=2。
- 删除 attachment 行后 COUNT 自然下降；COUNT=0 才允许 GC 物理删除。
- **竞态**：COUNT 与物理删除之间若有新引用插入，会误删。设计要求 StorageKeyLock + DB 事务/隔离配合；当前无实现。标签：部分实现（模型）/未实现（并发保护）。

### 2.4 内容寻址与共享

- `storage_key` 被设计为内容 sha256；相同内容只存一份物理文件，多条 attachment 行引用。
- 当前没有任何代码计算 sha256 或写入物理文件。
- 当前 `storage_key` 与 `content_hash` 可被调用方任意赋值，二者可不同。
- 导入/导出路径都不产生 attachment 行。

标签：未实现（计算、写入、校验）。

## 3. 端口契约审计

`knowledge-core/src/knowledge_core/ports.py`：

### 3.1 `AttachmentRepository`

```python
def save_attachment(self, attachment: Attachment) -> Attachment: ...
def get_attachment(self, attachment_id: UUID) -> Attachment | None: ...
def list_attachments(self, item_id: UUID) -> list[Attachment]: ...
def find_by_hash(self, content_hash: str) -> list[Attachment]: ...
def count_references(self, storage_key: str) -> int: ...
def list_storage_keys(self) -> list[str]: ...
def delete_attachment(self, attachment_id: UUID) -> bool: ...
```

| 方法 | 设计用途 | 当前实现 | 标签 |
|---|---|---|---|
| `save_attachment` | 插入一条引用行 | 无 | 未实现 |
| `get_attachment` | 下载前取元数据/鉴权 | 无 | 未实现 |
| `list_attachments` | 条目附件列表 | 无 | 未实现 |
| `find_by_hash` | 秒传/去重候选 | 无；且缺索引 | 未实现 |
| `count_references` | GC 前判 0 | 无 | 未实现 |
| `list_storage_keys` | 孤儿扫描的“被引用集合” | 无 | 未实现 |
| `delete_attachment` | 删引用行（不删 blob） | 无 | 未实现 |

**契约缺口：**

1. `save_attachment` 是否幂等（同 id 重复保存）未定义。标签：需要 ChatGPT 决策。
2. `list_storage_keys` 返回全表去重 key 还是全部行？方法名暗示去重集合，docstring 未逐字规定。标签：需要 ChatGPT 决策。
3. `delete_attachment` 是否要求调用方先持 StorageKeyLock？端口未表达。标签：需要 ChatGPT 决策。
4. 删除最后一条引用后是否在同一事务内 enqueue `gc_task`？端口无此方法，需服务层编排。标签：需要 ChatGPT 决策。
5. `find_by_hash` 返回多条（不同 item 的同一内容），调用方如何选择未定义。标签：需要 ChatGPT 决策。

### 3.2 `GcTaskRepository`

```python
def save_task(self, task: GcTask) -> GcTask: ...
def get_task(self, task_id: UUID) -> GcTask | None: ...
def list_tasks(self, *, status: GcStatus | None = None,
               storage_key: str | None = None) -> list[GcTask]: ...
def claim(self, task_id: UUID, *, owner: str, lease_ttl_seconds: int,
          now: datetime | None = None) -> GcTask | None: ...
def update_task(self, task: GcTask, *, expected_lease_token: int) -> GcTask | None: ...
```

| 契约点 | 端口是否明确 | 标签 |
|---|---|---|
| 认领必须原子条件 UPDATE | 是（docstring） | 已实现（契约） |
| 仅 pending 或过期 running 可认领 | 是 | 已实现（契约） |
| 认领成功 token 单调 +1 | 是 | 已实现（契约） |
| attempts 认领时 +1 | 是 | 已实现（契约） |
| 状态转移更新必须带 expected_lease_token | 是 | 已实现（契约） |
| token 失配返回 None | 是 | 已实现（契约） |
| 物理操作在 DB 写事务之外 | 是 | 已实现（契约） |
| 7 态转移矩阵是否穷尽 | 否（哪些状态可转哪些未列） | 需要 ChatGPT 决策 |
| 重试退避由谁计算 | 否（端口只存 next_retry_at） | 需要 ChatGPT 决策 |
| 死信（failed_permanent/needs_manual）如何人工恢复 | 否 | 需要 ChatGPT 决策 |

### 3.3 `StorageKeyLock`

```python
def acquire(self, storage_key: str, owner: str, *,
            ttl_seconds: int) -> StorageLease | None: ...
def renew(self, lease: StorageLease, *, ttl_seconds: int) -> bool: ...
def verify(self, lease: StorageLease) -> bool: ...
def release(self, lease: StorageLease) -> bool: ...
```

| 契约点 | 端口是否明确 | 标签 |
|---|---|---|
| SQLite 用逻辑租约锁表 | 是 | 已实现（契约） |
| PG 用 advisory lock | 是 | 已实现（契约） |
| 租约含单调 token | 是 | 已实现（契约） |
| owner+token 失配即中止 | 是 | 已实现（契约） |
| 租约过期接管语义 | 是 | 已实现（契约） |
| TOCTOU 诚实声明 | 是（docstring 明示降低不消除） | 已实现（契约） |
| 重入（同 owner 再次 acquire） | 未定义 | 需要 ChatGPT 决策 |
| 同进程多线程 owner 唯一性 | 未定义 | 需要 ChatGPT 决策 |
| 锁获取失败是等待还是立即返回 None | 端口语义为 None；上层重试策略未定 | 需要 ChatGPT 决策 |
| 锁与 DB 事务的先后顺序 | 未表达 | 需要 ChatGPT 决策 |

## 4. 与正式设计的差异

| 设计条款 | 设计要求 | 当前代码 | 差异标签 |
|---|---|---|---|
| §5.3 上传序列 | 大小上限 → MIME+magic → sha256 → StorageKeyLock → temp 写 → fsync → 原子 rename → 短事务插引用 → 失败留孤儿 → fencing release | 全部缺失 | 未实现 |
| §5.3 路径穿越 | 文件名清洗；storage_key 只允许安全字符；落盘路径由服务端拼 | 无 | 未实现 |
| §5.3 共享/秒传 | 相同 sha256 复用 blob | 无 | 未实现 |
| §7.1 存储根 | `backend/data/attachments/<key[:2]>/<key>` | 无目录 | 未实现 |
| §7.2 隔离区 | 与正式区同卷，可 rename | 无 | 未实现 |
| §7.3 7 态 GC | 认领→quarantine→purge | 无 | 未实现 |
| §16.1 T4-02 | V2 仓库（tag/origin/attachment/gc） | 仅 tag/origin | 部分实现 |
| §21.2 同事务 | 附件引用与 item/tags/origin/links 同一 approve 事务 | 无附件引用写入 | 未实现 |
| §21.5 不新增表/列 | 使用既有 0006 | 满足（但 `find_by_hash` 索引问题需决策） | 已实现（有争议点） |

## 5. 必须由 ChatGPT 决策的契约问题

1. **`storage_key` 与 `content_hash` 是否强制相等？** 若相等，`Attachment` 应加 validator，且仓库应拒绝不一致。若允许不同（例如将来换哈希算法），必须定义引用/去重以谁为准。标签：需要 ChatGPT 决策。
2. **是否允许同一 item 重复引用同一 storage_key？** 影响 `(item_id, storage_key)` 唯一约束、`list_attachments` 展示、删除语义。标签：需要 ChatGPT 决策。
3. **`find_by_hash` 是否本批实现？** 若实现，content_hash 无索引可能全表扫描；新增索引需要迁移，与“不新增迁移”冲突。标签：需要 ChatGPT 决策。
4. **删除最后引用时是否同步 enqueue GC？** 若同步，删除 API 的事务边界需定义；若靠孤儿扫描，延迟由扫描周期决定。标签：需要 ChatGPT 决策。
5. **`list_storage_keys` 的返回语义**（去重集合 vs 全量）需在 docstring 固定，避免 SQLite/PG 实现不一致。标签：需要 ChatGPT 决策。
6. **GC 状态机完整转移表**（含 cancelled、failed_*、needs_manual 的入口/出口）需正式化。标签：需要 ChatGPT 决策。
7. **StorageKeyLock 的 owner 生成规则与重入语义**需固定，否则 fencing 无法验收。标签：需要 ChatGPT 决策。

## 6. 需要真实测试验证的点

- ATT-01…12 全部需要真实文件系统；当前零测试。标签：需要真实测试验证。
- 共享 blob 的引用计数在并发上传/删除下的正确性。标签：需要真实测试验证。
- 路径穿越（`../`、绝对路径、Windows 盘符、UNC、保留名）。标签：需要真实测试验证。
- MIME 与 magic bytes 不一致时的拒绝。标签：需要真实测试验证。
- 10 MiB 边界与超限拒绝。标签：需要真实测试验证。
- SQLite 与 PG 的仓储行为一致性。标签：需要真实测试验证。

## 7. 结论

**模型与端口是“可用的契约骨架”，但没有一行 repository 实现、没有物理存储、没有策略校验。Batch B 不能只“接线”，必须补齐实体不变量、仓储实现、安全校验和真实 FS 测试。** 标签：部分实现。