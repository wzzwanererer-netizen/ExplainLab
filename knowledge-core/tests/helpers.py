"""测试基建：假适配器与内存仓库。

这些是测试专用替身，不是产品功能；产品代码不使用假数据。
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from uuid import UUID

from knowledge_core.domain import entities
from knowledge_core.domain.entities import (
    KnowledgeItem,
    KnowledgeLink,
    KnowledgeRelation,
    KnowledgeVersion,
    RelationType,
    ReviewRequest,
    ReviewStatus,
    SourceRef,
)
from knowledge_core.experiments.entities import (
    ExperimentAttempt,
    ExperimentKind,
    ExperimentSession,
)
from knowledge_core.markdown.link_service import check_global_version_homogeneity
from knowledge_core.model_adapter import (
    ModelAdapter,
    ModelCapability,
    ModelRequest,
    ModelResponse,
)


class FakeAdapter(ModelAdapter):
    """返回预设 content 的假适配器，用于提取/编排测试。"""

    def __init__(self, content: str = '{"items": []}') -> None:
        self._content = content
        self.last_request: ModelRequest | None = None

    @property
    def provider(self) -> str:
        return "fake"

    @property
    def default_model(self) -> str:
        return "fake-model"

    def capabilities(self) -> set[ModelCapability]:
        return {ModelCapability.GENERATE, ModelCapability.EMBED}

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.last_request = request
        return ModelResponse(content=self._content, model="fake-model", provider="fake")

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]


class InMemoryKnowledgeRepository:
    """内存知识仓库，实现 KnowledgeRepository 端口。"""

    def __init__(self) -> None:
        self.items: dict[UUID, KnowledgeItem] = {}

    def save(self, item: KnowledgeItem) -> KnowledgeItem:
        self.items[item.id] = item
        return item

    def get(self, item_id: UUID) -> KnowledgeItem | None:
        return self.items.get(item_id)

    def list(
        self, *, space_id: str | None = None, include_unassigned: bool = False
    ) -> list[KnowledgeItem]:
        return [
            item
            for item in self.items.values()
            if space_id is None
            or item.space_id == space_id
            or (include_unassigned and item.space_id is None)
        ]

    def update(self, item: KnowledgeItem) -> KnowledgeItem:
        self.items[item.id] = item
        return item

    def add_source_ref(self, item_id: UUID, source: SourceRef) -> SourceRef:
        self.items[item_id].source_refs.append(source)
        return source

    def delete(self, item_id: UUID) -> bool:
        return self.items.pop(item_id, None) is not None


class InMemoryVersionRepository:
    """内存版本仓库，实现 VersionRepository 端口。"""

    def __init__(self) -> None:
        self.versions: dict[UUID, KnowledgeVersion] = {}

    def save_version(self, version: KnowledgeVersion) -> KnowledgeVersion:
        self.versions[version.id] = version
        return version

    def list_versions(self, item_id: UUID) -> list[KnowledgeVersion]:
        return sorted(
            (v for v in self.versions.values() if v.item_id == item_id),
            key=lambda v: v.version,
        )

    def get_version(self, item_id: UUID, version: int) -> KnowledgeVersion | None:
        return next(
            (
                v
                for v in self.versions.values()
                if v.item_id == item_id and v.version == version
            ),
            None,
        )


class InMemoryRelationRepository:
    """内存关系仓库，实现 RelationRepository 端口。"""

    def __init__(self) -> None:
        self.relations: dict[UUID, KnowledgeRelation] = {}

    def save_relation(self, relation: KnowledgeRelation) -> KnowledgeRelation:
        self.relations[relation.id] = relation
        return relation

    def list_relations(self, item_id: UUID) -> list[KnowledgeRelation]:
        return [
            r
            for r in self.relations.values()
            if r.source_id == item_id or r.target_id == item_id
        ]

    def list_all_relations(self) -> list[KnowledgeRelation]:
        return list(self.relations.values())

    def find_relation(
        self, source_id: UUID, target_id: UUID, relation_type: RelationType
    ) -> KnowledgeRelation | None:
        return next(
            (
                r
                for r in self.relations.values()
                if r.source_id == source_id
                and r.target_id == target_id
                and r.relation_type == relation_type
            ),
            None,
        )

    def delete_relation(self, relation_id: UUID) -> bool:
        return self.relations.pop(relation_id, None) is not None


class InMemoryReviewRepository:
    """内存审核仓库，实现 ReviewRepository 端口。"""

    def __init__(self) -> None:
        self.reviews: dict[UUID, ReviewRequest] = {}

    def save_review(self, review: ReviewRequest) -> ReviewRequest:
        self.reviews[review.id] = review
        return review

    def get_review(self, review_id: UUID) -> ReviewRequest | None:
        return self.reviews.get(review_id)

    def list_reviews(self, status: ReviewStatus | None = None) -> list[ReviewRequest]:
        return [
            r
            for r in self.reviews.values()
            if status is None or r.status == status
        ]

    def update_review(self, review: ReviewRequest) -> ReviewRequest:
        self.reviews[review.id] = review
        return review


class InMemoryExperimentRepository:
    """内存实验仓库，实现 ExperimentRepository 端口。"""

    def __init__(self) -> None:
        self.sessions: dict[UUID, ExperimentSession] = {}
        self.attempts: dict[UUID, ExperimentAttempt] = {}

    def save_session(self, session: ExperimentSession) -> ExperimentSession:
        self.sessions[session.id] = session
        return session

    def get_session(self, session_id: UUID) -> ExperimentSession | None:
        return self.sessions.get(session_id)

    def list_sessions(
        self,
        *,
        kind: ExperimentKind | None = None,
        space_id: str | None = None,
    ) -> list[ExperimentSession]:
        return sorted(
            (
                s
                for s in self.sessions.values()
                if (kind is None or s.kind == kind)
                and (space_id is None or s.space_id == space_id)
            ),
            key=lambda s: s.created_at,
            reverse=True,
        )

    def update_session(self, session: ExperimentSession) -> ExperimentSession:
        self.sessions[session.id] = session
        return session

    def delete_session(self, session_id: UUID) -> bool:
        removed = self.sessions.pop(session_id, None) is not None
        self.attempts = {
            aid: a for aid, a in self.attempts.items() if a.session_id != session_id
        }
        return removed

    def save_attempt(self, attempt: ExperimentAttempt) -> ExperimentAttempt:
        self.attempts[attempt.id] = attempt
        return attempt

    def list_attempts(self, session_id: UUID) -> list[ExperimentAttempt]:
        return sorted(
            (a for a in self.attempts.values() if a.session_id == session_id),
            key=lambda a: a.created_at,
        )


class InMemoryFullTextIndex:
    """内存全文索引替身：子串匹配，出现次数越多 rank 越靠前（越小）。"""

    def __init__(self) -> None:
        self.docs: dict[UUID, str] = {}

    def upsert(self, item_id: UUID, title: str, content: str) -> None:
        self.docs[item_id] = f"{title}\n{content}"

    def remove(self, item_id: UUID) -> None:
        self.docs.pop(item_id, None)

    def search(self, query: str, limit: int) -> list[tuple[UUID, float]]:
        if not query:
            return []
        hits = [
            (item_id, -float(text.count(query)))
            for item_id, text in self.docs.items()
            if query in text
        ]
        hits.sort(key=lambda kv: kv[1])
        return hits[:limit]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class InMemoryVectorStore:
    """内存向量存储替身：余弦相似度检索。"""

    def __init__(self) -> None:
        self.vecs: dict[UUID, list[float]] = {}

    def upsert(self, item_id: UUID, vector: list[float], model: str) -> None:
        self.vecs[item_id] = list(vector)

    def remove(self, item_id: UUID) -> None:
        self.vecs.pop(item_id, None)

    def query(self, vector: list[float], limit: int) -> list[tuple[UUID, float]]:
        hits = [(i, _cosine(vector, v)) for i, v in self.vecs.items()]
        hits.sort(key=lambda kv: kv[1], reverse=True)
        return hits[:limit]


class FakeEmbedder:
    """返回预设向量的假向量化器，用于检索编排测试。"""

    def __init__(self, vector: list[float] | None = None) -> None:
        self._vector = vector or [1.0, 0.0]

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [list(self._vector) for _ in texts]


class InMemoryLinkRepository:
    """LinkRepository 测试替身（V2 A1-03b）。

    守卫语义与生产 backend 仓库对齐：**无缓存**，每次受守卫写入重新扫描全表
    版本集合并调用 Core 单一事实来源纯函数 ``check_global_version_homogeneity``
    （§8.4.3（3））；治理列豁免写入与删除不预检。``precheck_calls`` 是单调计数
    仪表（T34 断言用），**不是版本集合缓存**。
    """

    def __init__(self) -> None:
        self._links: dict[UUID, KnowledgeLink] = {}
        self.precheck_calls = 0

    def _precheck_global_version(self) -> None:
        self.precheck_calls += 1
        check_global_version_homogeneity(
            (link.link_normalization_version for link in self._links.values()),
            entities.LINK_NORMALIZATION_VERSION,
        )

    def save_link(self, link: KnowledgeLink) -> KnowledgeLink:
        self._precheck_global_version()
        if any(
            other.source_id == link.source_id
            and other.normalized_link_key == link.normalized_link_key
            for other in self._links.values()
        ):
            raise ValueError("unique(source_id, normalized_link_key) 违反")
        self._links[link.id] = link
        return link

    def get_link(self, link_id: UUID) -> KnowledgeLink | None:
        return self._links.get(link_id)

    def list_links(self, source_id: UUID) -> list[KnowledgeLink]:
        return sorted(
            (link for link in self._links.values() if link.source_id == source_id),
            key=lambda link: (link.created_at, str(link.id)),
        )

    def list_backlinks(self, target_id: UUID) -> list[KnowledgeLink]:
        return sorted(
            (link for link in self._links.values() if link.target_id == target_id),
            key=lambda link: (link.created_at, str(link.id)),
        )

    def find_by_key(
        self, source_id: UUID, normalized_link_key: str
    ) -> KnowledgeLink | None:
        return next(
            (
                link
                for link in self._links.values()
                if link.source_id == source_id
                and link.normalized_link_key == normalized_link_key
            ),
            None,
        )

    def list_by_key(self, normalized_link_key: str) -> list[KnowledgeLink]:
        return sorted(
            (
                link
                for link in self._links.values()
                if link.normalized_link_key == normalized_link_key
            ),
            key=lambda link: (link.created_at, str(link.id)),
        )

    def list_all_links(self) -> list[KnowledgeLink]:
        return sorted(
            self._links.values(),
            key=lambda link: (str(link.source_id), link.normalized_link_key, str(link.id)),
        )

    def update_link(self, link: KnowledgeLink) -> KnowledgeLink:
        old = self._links.get(link.id)
        if old is None:
            raise ValueError(f"链接不存在: {link.id}")
        if (
            old.normalized_link_key != link.normalized_link_key
            or old.link_normalization_version != link.link_normalization_version
        ):
            self._precheck_global_version()
        self._links[link.id] = link
        return link

    def delete_link(self, link_id: UUID) -> bool:
        return self._links.pop(link_id, None) is not None

    def delete_links_of_item(self, source_id: UUID) -> int:
        ids = [
            link_id
            for link_id, link in self._links.items()
            if link.source_id == source_id
        ]
        for link_id in ids:
            del self._links[link_id]
        return len(ids)