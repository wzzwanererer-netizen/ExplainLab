"""领域实体契约测试。"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from knowledge_core.domain import (
    KnowledgeItem,
    KnowledgeRelation,
    KnowledgeStatus,
    KnowledgeVersion,
    RelationType,
    SourceRef,
    SourceType,
)


class TestKnowledgeItem:
    def test_defaults(self):
        item = KnowledgeItem(title="标题", content="内容")
        assert item.status is KnowledgeStatus.DRAFT
        assert item.space_id is None
        assert item.source_refs == []
        assert item.created_at <= item.updated_at

    def test_title_required(self):
        with pytest.raises(ValidationError):
            KnowledgeItem(title="", content="内容")

    def test_with_source(self):
        source = SourceRef(
            source_type=SourceType.CONVERSATION,
            conversation_id="conv-1",
            excerpt="原文摘录",
        )
        item = KnowledgeItem(title="t", content="c", source_refs=[source])
        assert item.source_refs[0].conversation_id == "conv-1"


class TestKnowledgeRelation:
    def test_self_relation_rejected(self):
        uid = uuid4()
        with pytest.raises(ValidationError, match="自身"):
            KnowledgeRelation(
                source_id=uid,
                target_id=uid,
                relation_type=RelationType.RELATED,
            )

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            KnowledgeRelation(
                source_id=uuid4(),
                target_id=uuid4(),
                relation_type=RelationType.RELATED,
                confidence=1.5,
            )

    def test_valid_relation(self):
        rel = KnowledgeRelation(
            source_id=uuid4(),
            target_id=uuid4(),
            relation_type=RelationType.DEPENDS_ON,
            confidence=0.8,
        )
        assert rel.confidence == 0.8


class TestKnowledgeVersion:
    def test_version_starts_at_one(self):
        with pytest.raises(ValidationError):
            KnowledgeVersion(item_id=uuid4(), version=0, title="t", content="c")

    def test_valid_version(self):
        v = KnowledgeVersion(item_id=uuid4(), version=1, title="t", content="c")
        assert v.change_summary is None