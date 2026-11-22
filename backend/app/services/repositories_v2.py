"""V2 端口仓储的 SQLAlchemy 实现（标签 / 标签审计 / 导入来源）。

严格实现 ``knowledge_core.ports`` 协议；只 ``flush`` 不 ``commit``，
事务边界由调用方（导入协调器 / 审核钩子）统一控制。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ImportOriginORM, ItemTagORM, TagChangeLogORM, TagORM
from knowledge_core.domain.entities import ImportOrigin, TagChangeRecord

__all__ = [
    "SQLAlchemyImportOriginRepository",
    "SQLAlchemyTagChangeLogRepository",
    "SQLAlchemyTagRepository",
]


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(value)


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


class SQLAlchemyTagRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def ensure_tag(self, name: str) -> UUID:
        tag_name = name.strip()
        if not tag_name:
            raise ValueError("tag name must not be empty")
        if len(tag_name) > 100:
            raise ValueError("tag name too long")
        existing = self.session.scalar(select(TagORM).where(TagORM.name == tag_name))
        if existing is not None:
            return UUID(existing.id)
        tag = TagORM(id=str(uuid4()), name=tag_name)
        try:
            with self.session.begin_nested():
                self.session.add(tag)
                self.session.flush()
        except IntegrityError:
            # 并发下由 UNIQUE(name) 兜底：回读已存在行（savepoint 已回滚）。
            row = self.session.scalar(select(TagORM).where(TagORM.name == tag_name))
            if row is None:
                raise
            return UUID(row.id)
        return UUID(tag.id)

    def set_item_tags(self, item_id: UUID, tags: Sequence[str]) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for raw in tags:
            name = raw.strip()
            if not name or name in seen:
                continue
            seen.add(name)
            ordered.append(name)
        self.session.execute(delete(ItemTagORM).where(ItemTagORM.item_id == str(item_id)))
        for name in ordered:
            tag_id = self.ensure_tag(name)
            self.session.add(ItemTagORM(item_id=str(item_id), tag_id=str(tag_id)))
        self.session.flush()
        return ordered

    def list_item_tags(self, item_id: UUID) -> list[str]:
        rows = self.session.scalars(
            select(TagORM.name)
            .join(ItemTagORM, ItemTagORM.tag_id == TagORM.id)
            .where(ItemTagORM.item_id == str(item_id))
            .order_by(TagORM.name)
        )
        return list(rows)

    def list_items_by_tag(self, name: str) -> list[UUID]:
        rows = self.session.scalars(
            select(ItemTagORM.item_id)
            .join(TagORM, TagORM.id == ItemTagORM.tag_id)
            .where(TagORM.name == name.strip())
        )
        return [UUID(row) for row in rows]

    def list_tags(self) -> list[str]:
        return list(self.session.scalars(select(TagORM.name).order_by(TagORM.name)))

    def delete_tag(self, name: str) -> bool:
        tag = self.session.scalar(select(TagORM).where(TagORM.name == name.strip()))
        if tag is None:
            return False
        self.session.delete(tag)
        self.session.flush()
        return True


class SQLAlchemyTagChangeLogRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def append(self, record: TagChangeRecord) -> TagChangeRecord:
        orm = TagChangeLogORM(
            id=str(record.id),
            item_id=str(record.item_id) if record.item_id is not None else None,
            item_id_snapshot=str(record.item_id_snapshot),
            item_title_snapshot=record.item_title_snapshot,
            old_tags=json.dumps(record.old_tags, ensure_ascii=False),
            new_tags=json.dumps(record.new_tags, ensure_ascii=False),
            actor=record.actor,
            change_source=record.change_source,
            correlation_id=record.correlation_id,
            changed_at=record.changed_at,
        )
        self.session.add(orm)
        self.session.flush()
        return record

    @staticmethod
    def _to_entity(orm: TagChangeLogORM) -> TagChangeRecord:
        return TagChangeRecord(
            id=UUID(orm.id),
            item_id=UUID(orm.item_id) if orm.item_id else None,
            item_id_snapshot=UUID(orm.item_id_snapshot),
            item_title_snapshot=orm.item_title_snapshot,
            old_tags=json.loads(orm.old_tags),
            new_tags=json.loads(orm.new_tags),
            actor=orm.actor,
            change_source=orm.change_source,
            correlation_id=orm.correlation_id,
            changed_at=_utc(orm.changed_at),
        )

    def list_for_item(self, item_id_snapshot: UUID) -> list[TagChangeRecord]:
        rows = self.session.scalars(
            select(TagChangeLogORM)
            .where(TagChangeLogORM.item_id_snapshot == str(item_id_snapshot))
            .order_by(TagChangeLogORM.changed_at)
        )
        return [self._to_entity(row) for row in rows]

    def list_all(self, *, limit: int | None = None) -> list[TagChangeRecord]:
        stmt = select(TagChangeLogORM).order_by(TagChangeLogORM.changed_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        return [self._to_entity(row) for row in self.session.scalars(stmt)]


class SQLAlchemyImportOriginRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save_origin(self, origin: ImportOrigin) -> ImportOrigin:
        orm = ImportOriginORM(
            id=str(origin.id),
            item_id=str(origin.item_id),
            source_payload_hash=origin.source_payload_hash,
            source_content_hash=origin.source_content_hash,
            source_instance_id=origin.source_instance_id,
            source_document_id=str(origin.source_document_id),
            source_canonicalization_version=origin.source_canonicalization_version,
            imported_at=origin.imported_at,
            import_batch_id=origin.import_batch_id,
        )
        self.session.add(orm)
        self.session.flush()
        return origin

    @staticmethod
    def _to_entity(orm: ImportOriginORM) -> ImportOrigin:
        return ImportOrigin(
            id=UUID(orm.id),
            item_id=UUID(orm.item_id),
            source_payload_hash=orm.source_payload_hash,
            source_content_hash=orm.source_content_hash,
            source_instance_id=orm.source_instance_id,
            source_document_id=UUID(orm.source_document_id),
            source_canonicalization_version=orm.source_canonicalization_version,
            imported_at=_utc(orm.imported_at),
            import_batch_id=orm.import_batch_id,
        )

    def list_for_item(self, item_id: UUID) -> list[ImportOrigin]:
        rows = self.session.scalars(
            select(ImportOriginORM)
            .where(ImportOriginORM.item_id == str(item_id))
            .order_by(ImportOriginORM.imported_at, ImportOriginORM.id)
        )
        return [self._to_entity(row) for row in rows]

    def find_by_source_payload_hash(
        self,
        source_payload_hash: str,
        *,
        source_canonicalization_version: int | None = None,
    ) -> list[ImportOrigin]:
        stmt = select(ImportOriginORM).where(
            ImportOriginORM.source_payload_hash == source_payload_hash
        )
        if source_canonicalization_version is not None:
            stmt = stmt.where(
                ImportOriginORM.source_canonicalization_version
                == source_canonicalization_version
            )
        stmt = stmt.order_by(ImportOriginORM.imported_at, ImportOriginORM.id)
        return [self._to_entity(row) for row in self.session.scalars(stmt)]

    def find_by_source_document(
        self,
        source_document_id: UUID,
        *,
        source_instance_id: str | None = None,
    ) -> list[ImportOrigin]:
        stmt = select(ImportOriginORM).where(
            ImportOriginORM.source_document_id == str(source_document_id)
        )
        if source_instance_id is not None:
            stmt = stmt.where(ImportOriginORM.source_instance_id == source_instance_id)
        stmt = stmt.order_by(ImportOriginORM.imported_at, ImportOriginORM.id)
        return [self._to_entity(row) for row in self.session.scalars(stmt)]


def list_all_import_origins(session: Session) -> list[ImportOrigin]:
    """审计快照用：全部导入来源（稳定顺序由调用方按 item 分组排序）。"""
    rows = session.scalars(
        select(ImportOriginORM).order_by(ImportOriginORM.item_id, ImportOriginORM.id)
    )
    return [SQLAlchemyImportOriginRepository._to_entity(row) for row in rows]