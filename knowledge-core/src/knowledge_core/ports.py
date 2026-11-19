"""仓库端口（Protocol）。

Knowledge Core 通过端口依赖持久化能力，具体实现由应用层（如 backend 的 SQLAlchemy）注入。
这保证核心不绑定任何数据库，可复用于 Nesti。M1 方法为同步（适配 SQLAlchemy 同步会话）。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from knowledge_core.domain.entities import (
    Attachment,
    GcStatus,
    GcTask,
    ImportOrigin,
    KnowledgeItem,
    KnowledgeLink,
    KnowledgeRelation,
    KnowledgeVersion,
    RelationType,
    ReviewRequest,
    ReviewStatus,
    SourceRef,
    StorageLease,
    TagChangeRecord,
)

if TYPE_CHECKING:
    # 仅用于类型注解（字符串化），避免与 experiments 包初始化形成运行时循环导入。
    from knowledge_core.experiments.entities import (
        ExperimentAttempt,
        ExperimentKind,
        ExperimentSession,
    )


class KnowledgeRepository(Protocol):
    """知识条目持久化端口。"""

    def save(self, item: KnowledgeItem) -> KnowledgeItem:
        """新增一条知识（含来源），返回持久化后的条目。"""
        ...

    def get(self, item_id: UUID) -> KnowledgeItem | None:
        """按 ID 获取；不存在返回 None。"""
        ...

    def list(
        self, *, space_id: str | None = None, include_unassigned: bool = False
    ) -> list[KnowledgeItem]:
        """列出知识。

        Args:
            space_id: 限定知识空间；None 时返回全部空间。
            include_unassigned: 仅在指定 space_id 时生效。为 True 时同时返回
                space_id 为 None 的条目（领域语义中 None 即个人总知识库），
                供个人总知识库视图聚合「未显式归属」的条目。
        """
        ...

    def update(self, item: KnowledgeItem) -> KnowledgeItem:
        """更新一条知识，返回更新后的条目。"""
        ...

    def add_source_ref(self, item_id: UUID, source: SourceRef) -> SourceRef:
        """为条目追加一个来源追溯记录，返回持久化后的来源。"""
        ...

    def delete(self, item_id: UUID) -> bool:
        """删除一条知识；返回是否删除成功。"""
        ...


class RelationRepository(Protocol):
    """知识关系持久化端口（M2）。"""

    def save_relation(self, relation: KnowledgeRelation) -> KnowledgeRelation:
        """新增一条关系，返回持久化后的关系。"""
        ...

    def list_relations(self, item_id: UUID) -> list[KnowledgeRelation]:
        """列出与条目相关的全部关系（作为 source 或 target）。"""
        ...

    def list_all_relations(self) -> list[KnowledgeRelation]:
        """列出全部关系（M4 全图装配用）。"""
        ...

    def find_relation(
        self, source_id: UUID, target_id: UUID, relation_type: RelationType
    ) -> KnowledgeRelation | None:
        """按 (source, target, type) 查找关系；不存在返回 None。"""
        ...

    def delete_relation(self, relation_id: UUID) -> bool:
        """删除一条关系；返回是否删除成功。"""
        ...


class VersionRepository(Protocol):
    """知识版本持久化端口（M2）。"""

    def save_version(self, version: KnowledgeVersion) -> KnowledgeVersion:
        """新增一个版本快照，返回持久化后的版本。"""
        ...

    def list_versions(self, item_id: UUID) -> list[KnowledgeVersion]:
        """按版本号升序列出条目的全部历史版本。"""
        ...

    def get_version(self, item_id: UUID, version: int) -> KnowledgeVersion | None:
        """按 (item, version) 获取版本；不存在返回 None。"""
        ...


class ReviewRepository(Protocol):
    """审核单持久化端口（M2）。"""

    def save_review(self, review: ReviewRequest) -> ReviewRequest:
        """新增一张审核单，返回持久化后的审核单。"""
        ...

    def get_review(self, review_id: UUID) -> ReviewRequest | None:
        """按 ID 获取审核单；不存在返回 None。"""
        ...

    def list_reviews(self, status: ReviewStatus | None = None) -> list[ReviewRequest]:
        """列出审核单；status 为 None 时返回全部。"""
        ...

    def update_review(self, review: ReviewRequest) -> ReviewRequest:
        """更新审核单（状态/决议），返回更新后的审核单。"""
        ...


class ExperimentRepository(Protocol):
    """实验会话与作答持久化端口（M5）。"""

    def save_session(self, session: ExperimentSession) -> ExperimentSession:
        """新增一次实验会话，返回持久化后的会话。"""
        ...

    def get_session(self, session_id: UUID) -> ExperimentSession | None:
        """按 ID 获取实验会话；不存在返回 None。"""
        ...

    def list_sessions(
        self,
        *,
        kind: ExperimentKind | None = None,
        space_id: str | None = None,
    ) -> list[ExperimentSession]:
        """列出实验会话，可按模式与知识空间过滤；按创建时间倒序。"""
        ...

    def update_session(self, session: ExperimentSession) -> ExperimentSession:
        """更新实验会话（状态/内容），返回更新后的会话。"""
        ...

    def delete_session(self, session_id: UUID) -> bool:
        """删除实验会话（连同作答记录）；返回是否删除成功。"""
        ...

    def save_attempt(self, attempt: ExperimentAttempt) -> ExperimentAttempt:
        """新增一次作答记录，返回持久化后的记录。"""
        ...

    def list_attempts(self, session_id: UUID) -> list[ExperimentAttempt]:
        """列出某会话的全部作答记录；按创建时间升序。"""
        ...


class FullTextIndex(Protocol):
    """全文索引端口（M3）。实现如 SQLite FTS5（trigram）/ PostgreSQL 原生 tsvector/tsquery（GIN）。"""

    def upsert(self, item_id: UUID, title: str, content: str) -> None:
        """新增或更新一条知识的全文索引。"""
        ...

    def remove(self, item_id: UUID) -> None:
        """移除一条知识的全文索引。"""
        ...

    def search(self, query: str, limit: int) -> list[tuple[UUID, float]]:
        """全文检索，返回 (item_id, rank) 列表，rank 越小越相关。"""
        ...


class VectorStore(Protocol):
    """向量存储与检索端口（M3）。实现为 JSON 文本 + Python 余弦（SQLite/PostgreSQL 通用，不依赖 pgvector）。"""

    def upsert(self, item_id: UUID, vector: list[float], model: str) -> None:
        """新增或更新一条知识的向量。"""
        ...

    def remove(self, item_id: UUID) -> None:
        """移除一条知识的向量。"""
        ...

    def query(self, vector: list[float], limit: int) -> list[tuple[UUID, float]]:
        """余弦相似度检索，返回 (item_id, cosine) 列表，cosine 越大越相关。"""
        ...


class Embedder(Protocol):
    """文本向量化端口（M3）。与 ModelAdapter.embed 同形，可注入适配器或本地实现。"""

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """文本向量化，返回与输入等长的向量列表。"""
        ...


class LinkRepository(Protocol):
    """双向链接持久化端口（V2 A1，设计 §2.4）。

    身份键 normalized_link_key 非空，(source_id, normalized_link_key) 唯一；
    target_id 绑定稳定 UUID，改名不断链；target_title/alias 保留原始字面。
    """

    def save_link(self, link: KnowledgeLink) -> KnowledgeLink:
        """新增一条链接，返回持久化后的链接。"""
        ...

    def get_link(self, link_id: UUID) -> KnowledgeLink | None:
        """按 ID 获取链接；不存在返回 None。"""
        ...

    def list_links(self, source_id: UUID) -> list[KnowledgeLink]:
        """列出某条知识的全部出链（按创建时间升序）。"""
        ...

    def list_backlinks(self, target_id: UUID) -> list[KnowledgeLink]:
        """列出指向某稳定 ID 的全部反向链接（按稳定 ID 而非标题）。"""
        ...

    def find_by_key(self, source_id: UUID, normalized_link_key: str) -> KnowledgeLink | None:
        """按 (source, 规范化键) 查找链接；不存在返回 None。"""
        ...

    def list_by_key(self, normalized_link_key: str) -> list[KnowledgeLink]:
        """按规范化键列出全部链接（碰撞检测 / 解析候选 / 键重建用）。"""
        ...

    def list_all_links(self) -> list[KnowledgeLink]:
        """列出全部链接（全量重解析 / 规范化键重建用）。"""
        ...

    def update_link(self, link: KnowledgeLink) -> KnowledgeLink:
        """更新链接（绑定优先：保留 target_id，仅重算键/状态），返回更新后的链接。"""
        ...

    def delete_link(self, link_id: UUID) -> bool:
        """删除一条链接；返回是否删除成功。"""
        ...

    def delete_links_of_item(self, source_id: UUID) -> int:
        """删除某条知识的全部出链（连续保存时先清后建），返回删除条数。"""
        ...


class AttachmentRepository(Protocol):
    """附件元数据持久化端口（V2 A1，设计 §2.5）。

    storage_key 内容寻址可共享；引用数由 COUNT 派生，不维护冗余计数列。
    物理文件操作不经本端口（见 StorageKeyLock 与 backend 存储适配层）。
    """

    def save_attachment(self, attachment: Attachment) -> Attachment:
        """新增一条附件引用，返回持久化后的附件。"""
        ...

    def get_attachment(self, attachment_id: UUID) -> Attachment | None:
        """按 ID 获取附件；不存在返回 None。"""
        ...

    def list_attachments(self, item_id: UUID) -> list[Attachment]:
        """列出某条知识的全部附件（按创建时间升序）。"""
        ...

    def find_by_hash(self, content_hash: str) -> list[Attachment]:
        """按内容 sha256 列出附件（内容寻址去重 / 共享判定）。"""
        ...

    def count_references(self, storage_key: str) -> int:
        """派生引用数：COUNT(attachment WHERE storage_key)。GC 持锁复核用。"""
        ...

    def list_storage_keys(self) -> list[str]:
        """列出全部被引用的 storage_key（独立孤儿扫描的 DB 侧集合）。"""
        ...

    def delete_attachment(self, attachment_id: UUID) -> bool:
        """删除一条附件引用（不删物理文件）；返回是否删除成功。"""
        ...


class TagRepository(Protocol):
    """标签字典与条目-标签关联持久化端口（V2 A1）。

    标签为低风险变更：直改 + 经 TagChangeLogRepository 留痕，不走审核。
    """

    def ensure_tag(self, name: str) -> UUID:
        """幂等确保标签字典存在该名称，返回标签 ID。"""
        ...

    def set_item_tags(self, item_id: UUID, tags: Sequence[str]) -> list[str]:
        """整体替换某条知识的标签关联（去重保序），返回生效标签列表。"""
        ...

    def list_item_tags(self, item_id: UUID) -> list[str]:
        """列出某条知识的标签（按名称升序）。"""
        ...

    def list_items_by_tag(self, name: str) -> list[UUID]:
        """列出带某标签的全部知识 ID。"""
        ...

    def list_tags(self) -> list[str]:
        """列出标签字典全部名称（按名称升序）。"""
        ...

    def delete_tag(self, name: str) -> bool:
        """删除标签字典项（关联经 FK CASCADE 清理）；返回是否删除成功。"""
        ...


class TagChangeLogRepository(Protocol):
    """标签变更审计端口（V2 A1，append-only）。

    刻意不提供 update/delete：审计记录不可被普通更新覆盖。条目删除后
    item_id 置 NULL，身份由 item_id_snapshot / item_title_snapshot 保留。
    """

    def append(self, record: TagChangeRecord) -> TagChangeRecord:
        """追加一条标签变更记录（含删除前快照），返回持久化后的记录。"""
        ...

    def list_for_item(self, item_id_snapshot: UUID) -> list[TagChangeRecord]:
        """按稳定 ID 快照列出某条知识的全部标签变更（按 changed_at 升序）。"""
        ...

    def list_all(self, *, limit: int | None = None) -> list[TagChangeRecord]:
        """列出审计记录（按 changed_at 倒序）；limit 为 None 时返回全部。"""
        ...


class GcTaskRepository(Protocol):
    """附件 GC 任务持久化端口（V2 A1，设计 §2.5.2）。

    认领与状态流转必须是**原子条件更新 + lease_token fencing**：
    双 Worker 同任务仅一成功；终态 done/cancelled 不可被普通更新覆盖；
    崩溃残留 running 靠租约过期被他人条件认领，重启不直接置 pending。
    """

    def save_task(self, task: GcTask) -> GcTask:
        """新增一个 GC 任务，返回持久化后的任务。"""
        ...

    def get_task(self, task_id: UUID) -> GcTask | None:
        """按 ID 获取任务；不存在返回 None。"""
        ...

    def list_tasks(
        self,
        *,
        status: GcStatus | None = None,
        storage_key: str | None = None,
    ) -> list[GcTask]:
        """列出任务，可按状态与 storage_key 过滤（按创建时间升序）。"""
        ...

    def claim(
        self,
        task_id: UUID,
        *,
        owner: str,
        lease_ttl_seconds: float,
        now: datetime | None = None,
    ) -> GcTask | None:
        """原子认领：pending 或租约已过期的 running → running（新 token、attempts+1）。

        认领成功返回带新租约的任务；他人已认领 / 终态 / 条件不满足返回 None。
        """
        ...

    def update_task(self, task: GcTask, *, expected_lease_token: int) -> GcTask | None:
        """带 fencing 的状态流转：仅当 lease_token 匹配才写入。

        token 失配（已被接管）或终态不可覆盖时返回 None，调用方必须中止物理操作。
        """
        ...


class ImportOriginRepository(Protocol):
    """导入来源身份持久化端口（V2 A1，设计 §2.6.3）。

    权威导入历史；幂等判定比对**源** payload_hash（同 canonicalization_version
    前提下），而非目标实例再生 hash。
    """

    def save_origin(self, origin: ImportOrigin) -> ImportOrigin:
        """追加一条导入来源记录，返回持久化后的记录。"""
        ...

    def list_for_item(self, item_id: UUID) -> list[ImportOrigin]:
        """列出某条知识的全部导入来源（按 imported_at 升序）。"""
        ...

    def find_by_source_payload_hash(
        self,
        source_payload_hash: str,
        *,
        source_canonicalization_version: int | None = None,
    ) -> list[ImportOrigin]:
        """按源 payload_hash 查来源；可限定源 canonicalization_version。"""
        ...

    def find_by_source_document(
        self,
        source_document_id: UUID,
        *,
        source_instance_id: str | None = None,
    ) -> list[ImportOrigin]:
        """按源文档稳定 ID（可限定源实例）查来源，跨实例重复导入判定用。"""
        ...


class StorageKeyLock(Protocol):
    """storage_key 级互斥抽象（V2 A1，设计 §2.5.1）。

    方言差异封装在 backend 适配层：SQLite 为租约式逻辑锁（短事务条件写入 +
    fencing token + 心跳续租），PostgreSQL 为会话级 advisory lock。
    业务/Core 只经本端口，不写任何方言 SQL。

    诚实限制：租约式逻辑锁**降低而非消除** TOCTOU，不宣称完全并发安全；
    每个不可逆物理步骤前须 verify/renew 校验 owner+token，失配立即中止。
    """

    def acquire(
        self, storage_key: str, owner: str, *, ttl_seconds: float
    ) -> StorageLease | None:
        """获取租约（新锁或过期接管），签发单调 lease_token；被他人持有返回 None。"""
        ...

    def renew(self, lease: StorageLease, *, ttl_seconds: float) -> bool:
        """心跳续租：仅 owner+token 匹配才延长到期时间；失配返回 False（须中止）。"""
        ...

    def verify(self, lease: StorageLease) -> bool:
        """fencing 校验：锁行仍存在且 owner+token 匹配且未过期。"""
        ...

    def release(self, lease: StorageLease) -> bool:
        """释放租约：仅 owner+token 匹配才释放（防误释放他人接管后的锁）。"""
        ...