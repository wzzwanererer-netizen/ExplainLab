"""V2 A1 领域实体契约测试（Core 独立调用，不依赖 backend/数据库/Web 框架）。

覆盖：Markdown 文档模型增量字段、双向链接身份键与版本化、附件、标签审计快照、
GC 租约任务状态机、导入来源身份、storage_key 租约凭证，以及新增仓库端口契约。
"""

from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from knowledge_core.domain import (
    CANONICALIZATION_VERSION,
    LINK_NORMALIZATION_VERSION,
    Attachment,
    GcStatus,
    GcTask,
    ImportOrigin,
    KnowledgeItem,
    KnowledgeLink,
    KnowledgeStatus,
    LinkResolution,
    StorageLease,
    TagChangeRecord,
)
from knowledge_core.domain.entities import utcnow
from knowledge_core.ports import (
    AttachmentRepository,
    GcTaskRepository,
    ImportOriginRepository,
    LinkRepository,
    StorageKeyLock,
    TagChangeLogRepository,
    TagRepository,
)


class TestMarkdownDocumentModel:
    def test_item_defaults_additive(self):
        """tags/extra_metadata 为增量字段，缺省不改变 V1 构造与默认状态。"""
        item = KnowledgeItem(title="知识图谱的定义", content="纯文本正文")
        assert item.tags == []
        assert item.extra_metadata == {}
        assert item.status is KnowledgeStatus.DRAFT
        assert item.space_id is None
        assert item.source_refs == []

    def test_mutable_defaults_not_shared(self):
        a = KnowledgeItem(title="a", content="c")
        b = KnowledgeItem(title="b", content="c")
        a.tags.append("概念")
        a.extra_metadata["custom"] = 1
        assert b.tags == []
        assert b.extra_metadata == {}

    def test_plain_text_content_preserved_verbatim(self):
        """纯文本是合法 Markdown：旧正文原样保留，零转换、不丢字符。"""
        legacy = "第一行\n第二行  带空格\n\t制表符与 *星号* 和 [方括号]"
        item = KnowledgeItem(title="旧知识", content=legacy)
        assert item.content == legacy

    def test_markdown_content_preserved_verbatim(self):
        md = "# 标题\n\n- [[其它知识|别名]]\n\n```python\nprint('x')\n```\n"
        item = KnowledgeItem(title="Markdown", content=md)
        assert item.content == md

    def test_tags_and_extra_metadata_roundtrip(self):
        item = KnowledgeItem(
            title="t",
            content="c",
            tags=["概念", "图谱"],
            extra_metadata={"obsidian_key": "value", "nested": {"a": [1, 2]}},
        )
        assert item.tags == ["概念", "图谱"]
        assert item.extra_metadata["nested"] == {"a": [1, 2]}
        # 序列化/反序列化不丢未知字段（导出保留兜底）
        restored = KnowledgeItem.model_validate_json(item.model_dump_json())
        assert restored.extra_metadata == item.extra_metadata
        assert restored.tags == item.tags

    def test_title_constraints_unchanged(self):
        with pytest.raises(ValidationError):
            KnowledgeItem(title="", content="c")
        with pytest.raises(ValidationError):
            KnowledgeItem(title="x" * 501, content="c")


class TestRuleVersions:
    def test_versions_are_positive_integers_and_independent(self):
        assert isinstance(CANONICALIZATION_VERSION, int)
        assert isinstance(LINK_NORMALIZATION_VERSION, int)
        assert CANONICALIZATION_VERSION >= 1
        assert LINK_NORMALIZATION_VERSION >= 1

    def test_link_defaults_to_current_normalization_version(self):
        link = KnowledgeLink(source_id=uuid4(), target_title="T", normalized_link_key="t")
        assert link.link_normalization_version == LINK_NORMALIZATION_VERSION

    def test_origin_defaults_to_current_canonicalization_version(self):
        origin = ImportOrigin(
            item_id=uuid4(),
            source_payload_hash="a" * 64,
            source_content_hash="b" * 64,
            source_document_id=uuid4(),
        )
        assert origin.source_canonicalization_version == CANONICALIZATION_VERSION

    def test_version_must_be_positive(self):
        with pytest.raises(ValidationError):
            KnowledgeLink(
                source_id=uuid4(),
                target_title="T",
                normalized_link_key="t",
                link_normalization_version=0,
            )
        with pytest.raises(ValidationError):
            ImportOrigin(
                item_id=uuid4(),
                source_payload_hash="a" * 64,
                source_content_hash="b" * 64,
                source_document_id=uuid4(),
                source_canonicalization_version=0,
            )


class TestLinkResolutionEnum:
    def test_five_states(self):
        assert {s.value for s in LinkResolution} == {
            "resolved",
            "missing",
            "ambiguous",
            "cross_space",
            "conflict",
        }


class TestKnowledgeLink:
    def test_defaults_unbound(self):
        source = uuid4()
        link = KnowledgeLink(source_id=source, target_title="目标标题", normalized_link_key="目标标题")
        assert link.source_id == source
        assert link.target_id is None
        assert link.alias is None
        assert link.resolution is LinkResolution.MISSING
        assert link.cross_space is False
        assert link.created_at <= link.updated_at

    def test_original_literals_never_overwritten(self):
        """规范化键与原始字面并存：全角/大小写原文保留展示，键独立。"""
        link = KnowledgeLink(
            source_id=uuid4(),
            target_title="Ｋｎｏｗｌｅｄｇｅ　Ｇｒａｐｈ",
            alias="原始 Alias",
            normalized_link_key="knowledge graph",
        )
        assert link.target_title == "Ｋｎｏｗｌｅｄｇｅ　Ｇｒａｐｈ"
        assert link.alias == "原始 Alias"
        assert link.normalized_link_key == "knowledge graph"

    def test_empty_key_rejected(self):
        with pytest.raises(ValidationError):
            KnowledgeLink(source_id=uuid4(), target_title="T", normalized_link_key="")

    def test_key_length_boundary(self):
        link = KnowledgeLink(
            source_id=uuid4(), target_title="T", normalized_link_key="k" * 1024
        )
        assert len(link.normalized_link_key) == 1024
        with pytest.raises(ValidationError):
            KnowledgeLink(
                source_id=uuid4(), target_title="T", normalized_link_key="k" * 1025
            )

    def test_empty_target_title_rejected(self):
        with pytest.raises(ValidationError):
            KnowledgeLink(source_id=uuid4(), target_title="", normalized_link_key="t")

    def test_resolved_requires_stable_id(self):
        with pytest.raises(ValidationError):
            KnowledgeLink(
                source_id=uuid4(),
                target_title="T",
                normalized_link_key="t",
                resolution=LinkResolution.RESOLVED,
            )

    def test_bound_id_cannot_be_missing(self):
        with pytest.raises(ValidationError):
            KnowledgeLink(
                source_id=uuid4(),
                target_id=uuid4(),
                target_title="T",
                normalized_link_key="t",
                resolution=LinkResolution.MISSING,
            )

    def test_resolved_with_stable_id(self):
        target = uuid4()
        link = KnowledgeLink(
            source_id=uuid4(),
            target_id=target,
            target_title="T",
            normalized_link_key="t",
            resolution=LinkResolution.RESOLVED,
        )
        assert link.target_id == target
        assert link.resolution is LinkResolution.RESOLVED

    @pytest.mark.parametrize(
        "resolution",
        [LinkResolution.AMBIGUOUS, LinkResolution.CROSS_SPACE, LinkResolution.CONFLICT],
    )
    def test_non_resolved_states_allow_unbound(self, resolution):
        """碰撞/跨空间/冲突不随机绑定：可无 target_id，保留原文待裁决。"""
        link = KnowledgeLink(
            source_id=uuid4(),
            target_title="T",
            normalized_link_key="t",
            resolution=resolution,
        )
        assert link.target_id is None
        assert link.resolution is resolution

    def test_cross_space_flag_with_binding(self):
        link = KnowledgeLink(
            source_id=uuid4(),
            target_id=uuid4(),
            target_title="T",
            normalized_link_key="t",
            resolution=LinkResolution.CROSS_SPACE,
            cross_space=True,
        )
        assert link.cross_space is True


class TestAttachment:
    def test_fields(self):
        item = uuid4()
        att = Attachment(
            item_id=item,
            filename="图.png",
            mime="image/png",
            size=2048,
            storage_key="k" * 64,
            content_hash="h" * 64,
        )
        assert att.item_id == item
        assert att.size == 2048
        assert att.storage_key == "k" * 64

    def test_negative_size_rejected(self):
        with pytest.raises(ValidationError):
            Attachment(
                item_id=uuid4(),
                filename="f",
                mime="text/plain",
                size=-1,
                storage_key="k",
                content_hash="h",
            )

    def test_empty_filename_or_key_rejected(self):
        with pytest.raises(ValidationError):
            Attachment(
                item_id=uuid4(),
                filename="",
                mime="text/plain",
                size=0,
                storage_key="k",
                content_hash="h",
            )
        with pytest.raises(ValidationError):
            Attachment(
                item_id=uuid4(),
                filename="f",
                mime="text/plain",
                size=0,
                storage_key="",
                content_hash="h",
            )

    def test_same_storage_key_shareable(self):
        """内容寻址：不同条目可共享同一 storage_key（引用数由 COUNT 派生）。"""
        key = "shared-key"
        a = Attachment(
            item_id=uuid4(), filename="a.png", mime="image/png", size=1,
            storage_key=key, content_hash="c" * 64,
        )
        b = Attachment(
            item_id=uuid4(), filename="b.png", mime="image/png", size=1,
            storage_key=key, content_hash="c" * 64,
        )
        assert a.storage_key == b.storage_key
        assert a.id != b.id


class TestTagChangeRecord:
    def test_snapshot_required(self):
        item = uuid4()
        rec = TagChangeRecord(
            item_id=item,
            item_id_snapshot=item,
            item_title_snapshot="原标题",
            old_tags=["a"],
            new_tags=["a", "b"],
            actor="user",
            change_source="api",
            correlation_id="op-1",
        )
        assert rec.item_id == item
        assert rec.old_tags == ["a"]
        assert rec.new_tags == ["a", "b"]

    def test_item_id_nullable_snapshot_retained(self):
        """条目删除后 item_id 可为 None，身份/标题快照仍保留（审计不丢）。"""
        item = uuid4()
        rec = TagChangeRecord(
            item_id=None, item_id_snapshot=item, item_title_snapshot="已删除条目"
        )
        assert rec.item_id is None
        assert rec.item_id_snapshot == item
        assert rec.item_title_snapshot == "已删除条目"
        assert rec.actor is None and rec.change_source is None and rec.correlation_id is None

    def test_snapshot_cannot_be_empty(self):
        with pytest.raises(ValidationError):
            TagChangeRecord(item_id_snapshot=uuid4(), item_title_snapshot="")

    def test_defaults_empty_lists_not_shared(self):
        a = TagChangeRecord(item_id_snapshot=uuid4(), item_title_snapshot="t")
        b = TagChangeRecord(item_id_snapshot=uuid4(), item_title_snapshot="t")
        a.new_tags.append("x")
        assert b.new_tags == []


class TestGcTask:
    def test_defaults(self):
        task = GcTask(storage_key="key-1")
        assert task.status is GcStatus.PENDING
        assert task.lease_owner is None
        assert task.lease_expires_at is None
        assert task.lease_token == 0
        assert task.attempts == 0
        assert task.next_retry_at is None
        assert task.quarantine_path is None
        assert task.quarantined_at is None

    def test_seven_states_including_cancelled(self):
        assert {s.value for s in GcStatus} == {
            "pending",
            "running",
            "done",
            "cancelled",
            "failed_retryable",
            "failed_permanent",
            "needs_manual",
        }

    def test_lease_and_quarantine_fields(self):
        now = utcnow()
        task = GcTask(
            storage_key="key-1",
            status=GcStatus.RUNNING,
            lease_owner="worker-1",
            lease_expires_at=now + timedelta(seconds=30),
            lease_token=7,
            attempts=2,
            quarantine_path="attachments/_quarantine/key-1.op-9",
            quarantined_at=now,
        )
        assert task.lease_token == 7
        assert task.quarantine_path.endswith("key-1.op-9")
        assert task.lease_expires_at > now

    def test_negative_token_or_attempts_rejected(self):
        with pytest.raises(ValidationError):
            GcTask(storage_key="k", lease_token=-1)
        with pytest.raises(ValidationError):
            GcTask(storage_key="k", attempts=-1)

    def test_empty_storage_key_rejected(self):
        with pytest.raises(ValidationError):
            GcTask(storage_key="")


class TestImportOrigin:
    def test_source_hashes_preserved_verbatim(self):
        """源 hash 原样持久化，不被目标再生覆盖（跨实例幂等判定依据）。"""
        origin = ImportOrigin(
            item_id=uuid4(),
            source_payload_hash="p" * 64,
            source_content_hash="c" * 64,
            source_instance_id="instance-A",
            source_document_id=uuid4(),
            source_canonicalization_version=1,
            import_batch_id="batch-1",
        )
        assert origin.source_payload_hash == "p" * 64
        assert origin.source_content_hash == "c" * 64
        assert origin.source_instance_id == "instance-A"
        assert origin.import_batch_id == "batch-1"

    def test_instance_and_batch_nullable(self):
        origin = ImportOrigin(
            item_id=uuid4(),
            source_payload_hash="p" * 64,
            source_content_hash="c" * 64,
            source_document_id=uuid4(),
        )
        assert origin.source_instance_id is None
        assert origin.import_batch_id is None

    def test_empty_hash_rejected(self):
        with pytest.raises(ValidationError):
            ImportOrigin(
                item_id=uuid4(),
                source_payload_hash="",
                source_content_hash="c" * 64,
                source_document_id=uuid4(),
            )

    def test_different_source_versions_distinguishable(self):
        """canonicalization_version 不同的源 hash 不可直接比较，须可区分。"""
        doc = uuid4()
        v1 = ImportOrigin(
            item_id=uuid4(), source_payload_hash="a" * 64, source_content_hash="b" * 64,
            source_document_id=doc, source_canonicalization_version=1,
        )
        v2 = ImportOrigin(
            item_id=uuid4(), source_payload_hash="a" * 64, source_content_hash="b" * 64,
            source_document_id=doc, source_canonicalization_version=2,
        )
        assert v1.source_payload_hash == v2.source_payload_hash
        assert v1.source_canonicalization_version != v2.source_canonicalization_version


class TestStorageLease:
    def test_fields(self):
        expires = utcnow() + timedelta(seconds=60)
        lease = StorageLease(
            storage_key="key-1", owner="worker-1", lease_token=3, lease_expires_at=expires
        )
        assert lease.storage_key == "key-1"
        assert lease.owner == "worker-1"
        assert lease.lease_token == 3
        assert lease.lease_expires_at == expires

    def test_token_monotonic_non_negative(self):
        with pytest.raises(ValidationError):
            StorageLease(
                storage_key="k", owner="w", lease_token=-1, lease_expires_at=utcnow()
            )

    def test_empty_owner_or_key_rejected(self):
        with pytest.raises(ValidationError):
            StorageLease(storage_key="", owner="w", lease_token=0, lease_expires_at=utcnow())
        with pytest.raises(ValidationError):
            StorageLease(storage_key="k", owner="", lease_token=0, lease_expires_at=utcnow())


class TestV2Ports:
    """新增端口为 Protocol 契约：Core 只声明，实现由 backend 注入。"""

    @pytest.mark.parametrize(
        ("port", "methods"),
        [
            (LinkRepository, {"save_link", "list_links", "list_backlinks", "find_by_key", "update_link"}),
            (AttachmentRepository, {"save_attachment", "count_references", "list_storage_keys"}),
            (TagRepository, {"ensure_tag", "set_item_tags", "list_item_tags", "list_items_by_tag"}),
            (TagChangeLogRepository, {"append", "list_for_item", "list_all"}),
            (GcTaskRepository, {"save_task", "claim", "update_task", "list_tasks"}),
            (ImportOriginRepository, {"save_origin", "find_by_source_payload_hash", "find_by_source_document"}),
            (StorageKeyLock, {"acquire", "renew", "verify", "release"}),
        ],
    )
    def test_port_declares_methods(self, port, methods):
        assert methods <= set(dir(port))

    def test_tag_change_log_port_is_append_only(self):
        """审计端口刻意不提供 update/delete，防止普通更新覆盖审计。"""
        assert not {"update", "delete", "update_record", "delete_record"} & set(
            dir(TagChangeLogRepository)
        )

    def test_gc_claim_and_update_require_fencing(self):
        import inspect

        claim_params = inspect.signature(GcTaskRepository.claim).parameters
        assert {"owner", "lease_ttl_seconds"} <= set(claim_params)
        update_params = inspect.signature(GcTaskRepository.update_task).parameters
        assert "expected_lease_token" in update_params

    def test_ports_are_protocols_not_concrete_classes(self):
        from typing import Protocol

        for port in (
            LinkRepository,
            AttachmentRepository,
            TagRepository,
            TagChangeLogRepository,
            GcTaskRepository,
            ImportOriginRepository,
            StorageKeyLock,
        ):
            assert issubclass(port, Protocol)


def test_utcnow_is_utc_aware():
    """所有 V2 实体时间口径统一 UTC（aware），与 V1 一致。"""
    now = utcnow()
    assert now.tzinfo is not None
    assert now.utcoffset().total_seconds() == 0
    item = KnowledgeItem(title="t", content="c")
    link = KnowledgeLink(source_id=item.id, target_title="T", normalized_link_key="t")
    task = GcTask(storage_key="k")
    for entity in (item, link, task):
        assert entity.created_at.utcoffset().total_seconds() == 0