"""重要变更审核（M2）。

ReviewPolicy 判定「重要变更」；ReviewService 编排 提交 / 批准 / 驳回。
重要变更提交后仅生成 pending 审核单、不应用；批准才应用，驳回不改动数据。
全部基于端口，不绑定数据库与 Web 框架，可复用于 Nesti。
"""

from __future__ import annotations

from uuid import UUID, uuid4

from knowledge_core.domain.entities import (
    KnowledgeRelation,
    KnowledgeStatus,
    RelationOrigin,
    RelationType,
    ReviewAction,
    ReviewRequest,
    ReviewStatus,
    utcnow,
)
from knowledge_core.ports import (
    KnowledgeRepository,
    RelationRepository,
    ReviewRepository,
)
from knowledge_core.versioning import VersionService


class ReviewPolicy:
    """重要变更判定矩阵。

    草稿为 scratch，改/删/回滚直接应用；生效知识的改/删/回滚与任何合并重复
    属重要变更，须审核。draft→active 发布不视为重要变更。
    """

    @staticmethod
    def is_important(action: ReviewAction, status: KnowledgeStatus) -> bool:
        if action == ReviewAction.MERGE_DUPLICATE:
            return True
        if action in (
            ReviewAction.UPDATE_ITEM,
            ReviewAction.DELETE_ITEM,
            ReviewAction.RESTORE_VERSION,
        ):
            return status == KnowledgeStatus.ACTIVE
        return False


class ReviewService:
    """审核单提交与应用编排。"""

    def __init__(
        self,
        items: KnowledgeRepository,
        reviews: ReviewRepository,
        versions: VersionService,
        relations: RelationRepository,
    ) -> None:
        self._items = items
        self._reviews = reviews
        self._versions = versions
        self._relations = relations

    async def submit(
        self,
        item_id: UUID,
        action: ReviewAction,
        payload: dict | None = None,
        reason: str | None = None,
    ) -> ReviewRequest | None:
        """提交变更。重要变更返回 pending 审核单（不应用）；否则直接应用返回 None。"""
        item = self._items.get(item_id)
        if item is None:
            raise ValueError(f"知识条目不存在: {item_id}")
        payload = payload or {}
        if ReviewPolicy.is_important(action, item.status):
            review = ReviewRequest(
                item_id=item_id, action=action, payload=payload, reason=reason
            )
            return self._reviews.save_review(review)
        await self._apply_action(item_id, action, payload)
        return None

    async def approve(
        self, review_id: UUID, note: str | None = None
    ) -> ReviewRequest:
        review = self._pending(review_id)
        review.status = ReviewStatus.APPROVED
        review.resolved_at = utcnow()
        review.resolution_note = note
        # 先记录决议再应用：删除动作会级联清理审核单本身（外键 CASCADE），
        # 若先应用再更新审核单，行已不存在会失败。同一事务内，应用失败则整体回滚。
        updated = self._reviews.update_review(review)
        await self._apply_action(review.item_id, review.action, review.payload)
        return updated

    async def reject(
        self, review_id: UUID, note: str | None = None
    ) -> ReviewRequest:
        review = self._pending(review_id)
        review.status = ReviewStatus.REJECTED
        review.resolved_at = utcnow()
        review.resolution_note = note
        return self._reviews.update_review(review)

    def _pending(self, review_id: UUID) -> ReviewRequest:
        review = self._reviews.get_review(review_id)
        if review is None:
            raise ValueError(f"审核单不存在: {review_id}")
        if review.status != ReviewStatus.PENDING:
            raise ValueError(f"审核单已处理: {review_id} ({review.status})")
        return review

    async def _apply_action(
        self, item_id: UUID, action: ReviewAction, payload: dict
    ) -> None:
        if action == ReviewAction.UPDATE_ITEM:
            await self._apply_update(item_id, payload)
        elif action == ReviewAction.DELETE_ITEM:
            self._items.delete(item_id)
        elif action == ReviewAction.MERGE_DUPLICATE:
            await self._apply_merge(item_id, payload)
        elif action == ReviewAction.RESTORE_VERSION:
            await self._versions.restore(item_id, int(payload["version"]))
        else:  # pragma: no cover - 枚举已穷尽
            raise ValueError(f"未知审核动作: {action}")

    async def _apply_update(self, item_id: UUID, payload: dict) -> None:
        item = self._items.get(item_id)
        if item is None:
            raise ValueError(f"知识条目不存在: {item_id}")
        await self._versions.create_version(item, change_summary="编辑前快照")
        if "title" in payload:
            item.title = payload["title"]
        if "content" in payload:
            item.content = payload["content"]
        if "status" in payload:
            item.status = KnowledgeStatus(payload["status"])
        if "space_id" in payload:
            item.space_id = payload["space_id"]
        item.updated_at = utcnow()
        self._items.update(item)

    async def _apply_merge(self, item_id: UUID, payload: dict) -> None:
        source = self._items.get(item_id)
        target_id = UUID(str(payload["target_id"]))
        target = self._items.get(target_id)
        if source is None or target is None:
            raise ValueError(f"合并双方不存在: {item_id} -> {target_id}")
        await self._versions.create_version(source, change_summary="合并前快照")
        if self._relations.find_relation(
            source.id, target.id, RelationType.DUPLICATE_OF
        ) is None:
            self._relations.save_relation(
                KnowledgeRelation(
                    source_id=source.id,
                    target_id=target.id,
                    relation_type=RelationType.DUPLICATE_OF,
                    origin=RelationOrigin.DEDUP,
                )
            )
        for ref in source.source_refs:
            # 并入目标的是「新行」：保留来源信息但分配新 id，避免与源行主键冲突
            self._items.add_source_ref(target.id, ref.model_copy(update={"id": uuid4()}))
        source.status = KnowledgeStatus.ARCHIVED
        source.updated_at = utcnow()
        self._items.update(source)