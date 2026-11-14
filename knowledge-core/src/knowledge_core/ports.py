"""仓库端口（Protocol）。

Knowledge Core 通过端口依赖持久化能力，具体实现由应用层（如 backend 的 SQLAlchemy）注入。
这保证核心不绑定任何数据库，可复用于 Nesti。M1 方法为同步（适配 SQLAlchemy 同步会话）。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from knowledge_core.domain.entities import (
    KnowledgeItem,
    KnowledgeRelation,
    KnowledgeVersion,
    RelationType,
    ReviewRequest,
    ReviewStatus,
    SourceRef,
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


class FullTextIndex(Protocol):
    """全文索引端口（M3）。实现如 SQLite FTS5 / PostgreSQL pg_trgm。"""

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
    """向量存储与检索端口（M3）。实现如 SQLite JSON 余弦 / pgvector。"""

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