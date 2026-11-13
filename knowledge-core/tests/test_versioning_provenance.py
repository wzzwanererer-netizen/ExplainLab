"""M2 版本管理与来源追溯测试（InMemory 仓库，不发真实请求）。"""

from __future__ import annotations

from uuid import uuid4

import pytest
from helpers import InMemoryKnowledgeRepository, InMemoryVersionRepository

from knowledge_core.domain.entities import KnowledgeItem, SourceRef, SourceType
from knowledge_core.provenance.service import RepositoryProvenanceService
from knowledge_core.versioning.service import RepositoryVersionService


def _setup():
    items = InMemoryKnowledgeRepository()
    versions = InMemoryVersionRepository()
    item = items.save(KnowledgeItem(title="标题A", content="内容A"))
    return items, versions, item


async def test_create_version_increments_and_lists_ascending():
    items, versions, item = _setup()
    service = RepositoryVersionService(versions, items)
    v1 = await service.create_version(item, change_summary="初版")
    assert v1.version == 1
    item.content = "内容B"
    items.update(item)
    v2 = await service.create_version(item)
    assert v2.version == 2
    listed = await service.list_versions(item.id)
    assert [v.version for v in listed] == [1, 2]
    assert listed[0].content == "内容A"
    assert listed[1].content == "内容B"


async def test_restore_snapshots_pre_state_and_reverts():
    items, versions, item = _setup()
    service = RepositoryVersionService(versions, items)
    await service.create_version(item)  # v1 = 内容A
    item.content = "内容B"
    items.update(item)
    await service.create_version(item)  # v2 = 内容B

    restored = await service.restore(item.id, 1)
    assert restored.content == "内容A"
    listed = await service.list_versions(item.id)
    assert [v.version for v in listed] == [1, 2, 3]
    assert listed[2].content == "内容B"  # 回滚前快照保留线性历史


async def test_restore_missing_item_or_version_raises():
    items, versions, item = _setup()
    service = RepositoryVersionService(versions, items)
    with pytest.raises(ValueError):
        await service.restore(item.id, 99)
    with pytest.raises(ValueError):
        await service.restore(item.id, 1)  # 尚无任何版本


async def test_provenance_attach_and_trace():
    items, _, item = _setup()
    service = RepositoryProvenanceService(items)
    source = SourceRef(
        source_type=SourceType.CONVERSATION, conversation_id="conv-1", excerpt="原文"
    )
    await service.attach_source(item.id, source)
    traced = await service.trace(item.id)
    assert len(traced) == 1
    assert traced[0].conversation_id == "conv-1"
    assert traced[0].excerpt == "原文"


async def test_provenance_missing_item_raises():
    items, _, _ = _setup()
    service = RepositoryProvenanceService(items)
    missing = uuid4()
    with pytest.raises(ValueError):
        await service.trace(missing)
    with pytest.raises(ValueError):
        await service.attach_source(missing, SourceRef(source_type=SourceType.MANUAL))