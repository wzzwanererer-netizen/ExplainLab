"""V2 专用 Markdown 条目读写（A1-04 D-02=C；不改 V1 仓储行为）。

V1 ``SQLAlchemyKnowledgeRepository`` 仍服务 V1 API（``KnowledgeOut`` 不变），
本仓储独立读写 V2 字段（extra_metadata / source_*），避免把导入语义塞进 V1。
只 ``flush`` 不 ``commit``；事务由导入协调器 / 审核钩子控制。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ImportOriginORM, KnowledgeItemORM, SourceRefORM
from knowledge_core.domain.entities import SourceRef, SourceType

__all__ = ["MarkdownItemRecord", "MarkdownItemRepository"]


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _parse_metadata(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("extra_metadata must be a JSON object")
    return value


@dataclass(slots=True)
class MarkdownItemRecord:
    id: UUID
    title: str
    content: str
    status: str
    space_id: str | None
    extra_metadata: dict[str, Any] = field(default_factory=dict)
    source_payload_hash: str | None = None
    source_content_hash: str | None = None
    source_instance_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MarkdownItemRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # -- 读取 ---------------------------------------------------------------
    @staticmethod
    def _to_record(orm: KnowledgeItemORM) -> MarkdownItemRecord:
        return MarkdownItemRecord(
            id=UUID(orm.id),
            title=orm.title,
            content=orm.content,
            status=orm.status,
            space_id=orm.space_id,
            extra_metadata=_parse_metadata(orm.extra_metadata),
            source_payload_hash=orm.source_payload_hash,
            source_content_hash=orm.source_content_hash,
            source_instance_id=orm.source_instance_id,
            created_at=_utc(orm.created_at),
            updated_at=_utc(orm.updated_at),
        )

    def get(self, item_id: UUID | str) -> MarkdownItemRecord | None:
        orm = self.session.get(KnowledgeItemORM, str(item_id))
        return None if orm is None else self._to_record(orm)

    def list_items(self, *, space_id: str | None = None) -> list[MarkdownItemRecord]:
        stmt = select(KnowledgeItemORM).order_by(KnowledgeItemORM.created_at)
        if space_id is not None:
            stmt = stmt.where(KnowledgeItemORM.space_id == space_id)
        return [self._to_record(orm) for orm in self.session.scalars(stmt)]

    def all_identity_rows(self) -> list[MarkdownItemRecord]:
        return self.list_items()

    def find_by_source_content_hash(self, content_hash: str) -> list[MarkdownItemRecord]:
        rows = self.session.scalars(
            select(KnowledgeItemORM).where(
                KnowledgeItemORM.source_content_hash == content_hash
            )
        )
        return [self._to_record(orm) for orm in rows]

    def count_origins(self, item_id: UUID | str) -> int:
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(ImportOriginORM)
                .where(ImportOriginORM.item_id == str(item_id))
            )
            or 0
        )

    def list_sources(self, item_id: UUID | str) -> list[SourceRef]:
        rows = self.session.scalars(
            select(SourceRefORM)
            .where(SourceRefORM.item_id == str(item_id))
            .order_by(SourceRefORM.id)
        )
        return [
            SourceRef(
                id=UUID(row.id),
                source_type=SourceType(row.source_type),
                uri=row.uri,
                conversation_id=row.conversation_id,
                excerpt=row.excerpt,
                created_at=_utc(row.created_at),
            )
            for row in rows
        ]

    # -- 写入 ---------------------------------------------------------------
    def create(
        self,
        *,
        item_id: UUID | None = None,
        title: str,
        content: str,
        status: str,
        space_id: str | None,
        extra_metadata: dict[str, Any] | None = None,
        source_payload_hash: str | None = None,
        source_content_hash: str | None = None,
        source_instance_id: str | None = None,
    ) -> MarkdownItemRecord:
        orm = KnowledgeItemORM(
            id=str(item_id or uuid4()),
            title=title,
            content=content,
            status=status,
            space_id=space_id,
            extra_metadata=json.dumps(extra_metadata or {}, ensure_ascii=False),
            source_payload_hash=source_payload_hash,
            source_content_hash=source_content_hash,
            source_instance_id=source_instance_id,
        )
        self.session.add(orm)
        self.session.flush()
        return self._to_record(orm)

    def update_fields(
        self,
        item_id: UUID | str,
        *,
        title: str | None = None,
        content: str | None = None,
        status: str | None = None,
        space_id: str | None = None,
        extra_metadata: dict[str, Any] | None = None,
        source_payload_hash: str | None = None,
        source_content_hash: str | None = None,
        source_instance_id: str | None = None,
    ) -> MarkdownItemRecord:
        orm = self.session.get(KnowledgeItemORM, str(item_id))
        if orm is None:
            raise LookupError("knowledge item not found")
        if title is not None:
            orm.title = title
        if content is not None:
            orm.content = content
        if status is not None:
            orm.status = status
        if space_id is not None:
            orm.space_id = space_id or None
        if extra_metadata is not None:
            orm.extra_metadata = json.dumps(extra_metadata, ensure_ascii=False)
        if source_payload_hash is not None:
            orm.source_payload_hash = source_payload_hash
        if source_content_hash is not None:
            orm.source_content_hash = source_content_hash
        if source_instance_id is not None:
            orm.source_instance_id = source_instance_id
        orm.updated_at = datetime.now(UTC)
        self.session.flush()
        return self._to_record(orm)

    def update_source_identity(
        self,
        item_id: UUID | str,
        *,
        source_payload_hash: str,
        source_content_hash: str,
        source_instance_id: str | None,
    ) -> MarkdownItemRecord:
        return self.update_fields(
            item_id,
            source_payload_hash=source_payload_hash,
            source_content_hash=source_content_hash,
            source_instance_id=source_instance_id,
        )