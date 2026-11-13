"""M2 审核策略与审核服务测试（InMemory 仓库，不发真实请求）。"""

from __future__ import annotations

from uuid import uuid4

import pytest
from helpers import (
    InMemoryKnowledgeRepository,
    InMemoryRelationRepository,
    InMemoryReviewRepository,
    InMemoryVersionRepository,
)

from knowledge_core.domain.entities import (
    KnowledgeItem,
    KnowledgeStatus,
    RelationOrigin,
    RelationType,
    ReviewAction,
    ReviewStatus,
    SourceRef,
    SourceType,
)
from knowledge_core.review import ReviewPolicy, ReviewService
from knowledge_core.versioning.service import RepositoryVersionService


def _service():
    items = InMemoryKnowledgeRepository()
    reviews = InMemoryReviewRepository()
    versions = InMemoryVersionRepository()
    relations = InMemoryRelationRepository()
    version_service = RepositoryVersionService(versions, items)
    service = ReviewService(items, reviews, version_service, relations)
    return items, reviews, relations, service


def _item(items, status=KnowledgeStatus.DRAFT, **kw):
    return items.save(KnowledgeItem(title="标题", content="内容", status=status, **kw))


def test_policy_matrix():
    assert ReviewPolicy.is_important(ReviewAction.UPDATE_ITEM, KnowledgeStatus.ACTIVE)
    assert not ReviewPolicy.is_important(ReviewAction.UPDATE_ITEM, KnowledgeStatus.DRAFT)
    assert ReviewPolicy.is_important(ReviewAction.DELETE_ITEM, KnowledgeStatus.ACTIVE)
    assert not ReviewPolicy.is_important(ReviewAction.DELETE_ITEM, KnowledgeStatus.DRAFT)
    assert ReviewPolicy.is_important(ReviewAction.MERGE_DUPLICATE, KnowledgeStatus.DRAFT)
    assert ReviewPolicy.is_important(ReviewAction.MERGE_DUPLICATE, KnowledgeStatus.ACTIVE)
    assert ReviewPolicy.is_important(ReviewAction.RESTORE_VERSION, KnowledgeStatus.ACTIVE)
    assert not ReviewPolicy.is_important(
        ReviewAction.RESTORE_VERSION, KnowledgeStatus.DRAFT
    )


async def test_submit_draft_update_applies_immediately():
    items, reviews, _, service = _service()
    item = _item(items)
    result = await service.submit(item.id, ReviewAction.UPDATE_ITEM, {"title": "新标题"})
    assert result is None  # 非重要，直接应用
    assert items.get(item.id).title == "新标题"
    assert reviews.list_reviews() == []


async def test_submit_active_update_gates_and_approve_applies():
    items, reviews, _, service = _service()
    item = _item(items, status=KnowledgeStatus.ACTIVE)
    review = await service.submit(item.id, ReviewAction.UPDATE_ITEM, {"title": "新标题"})
    assert review is not None
    assert review.status == ReviewStatus.PENDING
    assert items.get(item.id).title == "标题"  # 未应用

    approved = await service.approve(review.id, note="同意")
    assert approved.status == ReviewStatus.APPROVED
    assert approved.resolved_at is not None
    assert items.get(item.id).title == "新标题"


async def test_reject_leaves_data_unchanged():
    items, reviews, _, service = _service()
    item = _item(items, status=KnowledgeStatus.ACTIVE)
    review = await service.submit(item.id, ReviewAction.DELETE_ITEM)
    rejected = await service.reject(review.id, note="不同意")
    assert rejected.status == ReviewStatus.REJECTED
    assert items.get(item.id) is not None  # 未删除


async def test_approve_twice_raises():
    items, reviews, _, service = _service()
    item = _item(items, status=KnowledgeStatus.ACTIVE)
    review = await service.submit(item.id, ReviewAction.UPDATE_ITEM, {"title": "X"})
    await service.approve(review.id)
    with pytest.raises(ValueError):
        await service.approve(review.id)


async def test_delete_active_gated_then_approved_removes():
    items, reviews, _, service = _service()
    item = _item(items, status=KnowledgeStatus.ACTIVE)
    review = await service.submit(item.id, ReviewAction.DELETE_ITEM)
    assert items.get(item.id) is not None
    await service.approve(review.id)
    assert items.get(item.id) is None


async def test_merge_archives_source_and_links_and_merges_sources():
    items, reviews, relations, service = _service()
    source = _item(
        items,
        status=KnowledgeStatus.ACTIVE,
        source_refs=[SourceRef(source_type=SourceType.CONVERSATION, conversation_id="c1")],
    )
    target = _item(items, status=KnowledgeStatus.ACTIVE)
    review = await service.submit(
        source.id, ReviewAction.MERGE_DUPLICATE, {"target_id": str(target.id)}
    )
    assert review is not None  # 合并总是重要
    await service.approve(review.id)

    assert items.get(source.id).status == KnowledgeStatus.ARCHIVED
    rel = relations.find_relation(source.id, target.id, RelationType.DUPLICATE_OF)
    assert rel is not None
    assert rel.origin == RelationOrigin.DEDUP
    assert any(r.conversation_id == "c1" for r in items.get(target.id).source_refs)


async def test_restore_active_gated_then_approved_reverts():
    items = InMemoryKnowledgeRepository()
    reviews = InMemoryReviewRepository()
    version_repo = InMemoryVersionRepository()
    relations = InMemoryRelationRepository()
    version_service = RepositoryVersionService(version_repo, items)
    service = ReviewService(items, reviews, version_service, relations)

    item = items.save(
        KnowledgeItem(title="标题", content="内容", status=KnowledgeStatus.ACTIVE)
    )
    await version_service.create_version(item)  # v1 = 内容
    item.content = "改动后"
    items.update(item)

    review = await service.submit(item.id, ReviewAction.RESTORE_VERSION, {"version": 1})
    assert review is not None
    await service.approve(review.id)
    assert items.get(item.id).content == "内容"


async def test_submit_missing_item_raises():
    items, _, _, service = _service()
    with pytest.raises(ValueError):
        await service.submit(uuid4(), ReviewAction.UPDATE_ITEM, {})