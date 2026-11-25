"""Markdown Vault 导入/导出编排（V2 A1-04 Batch A；非附件）。

分层：解析/哈希/冲突判定为纯逻辑（Core），本模块负责事务、锁、持久化装配。
- 单篇/批量导入：每文档独立事务；S0 只读短会话→身份键同步锁→S1 判定→写→commit。
- D22：exporter 传输键在 YAML 折叠前查重、导入剥离、导出注入；用户 metadata 冲突
  在任何 DB 写之前整体拒绝（批量零写入）。
- D23：本地原生文档首次导出先过 Journal 恢复门并 MATERIALIZE；不推断 2b。
- 附件：显式 ``ATTACHMENT_*_UNSUPPORTED``，零附件写入。
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from app.db.storage_lock import (
    STORAGE_LOCK_UNAVAILABLE,
    LockGuard,
    PostgresStorageKeyLock,
    SQLiteStorageKeyLock,
    StorageLockError,
    StorageLockTransient,
    new_owner,
)
from app.models import KnowledgeSpace, ReviewRequestORM
from app.services.attachment_promotion import publish_staged
from app.services.attachment_staging import (
    ATTACHMENT_MANIFEST_CORRUPTED,
    ATTACHMENT_STAGING_INVALID,
    AttachmentManifestItem,
    AttachmentStagingError,
    AttachmentStagingService,
    ParsedImportZip,
    StagedAttachmentSet,
    StagingLease,
    coerce_manifest_items,
    logical_manifest_set,
)
from app.services.attachment_storage import AttachmentStorageError
from app.services.attachments import release_storage_guard
from app.services.governance import SQLAlchemyReviewRepository, build_review_service
from app.services.import_coordinator import (
    IMPORT_LOCK_TIMEOUT,
    ImportCoordinator,
    ImportLockTimeout,
)
from app.services.journal_canonical import sha256_canonical
from app.services.links import SQLAlchemyLinkRepository, build_link_restorer
from app.services.markdown_item_repository import (
    MarkdownItemRecord,
    MarkdownItemRepository,
)
from app.services.repositories_v2 import (
    SQLAlchemyAttachmentRepository,
    SQLAlchemyImportOriginRepository,
    SQLAlchemyTagChangeLogRepository,
    SQLAlchemyTagRepository,
)
from app.services.source_identity import (
    SOURCE_IDENTITY_ORPHAN,
    SourceIdentityError,
    SourceIdentityService,
)
from app.services.source_instance_id import SourceInstanceIdStore
from knowledge_core.domain.entities import (
    CANONICALIZATION_VERSION,
    ImportOrigin,
    KnowledgeItem,
    KnowledgeStatus,
    ReviewAction,
    TagChangeRecord,
)
from knowledge_core.markdown import (
    FrontmatterResolution,
    FrontmatterState,
    MarkdownDocument,
    MarkdownWarningCode,
    compute_document_hashes,
    resolve_frontmatter_conflict,
)
from knowledge_core.markdown.canonical import CanonicalizationError
from knowledge_core.markdown.codec import StdlibMarkdownCodec
from knowledge_core.markdown.import_report import (
    ChangeSet,
    ImportEnvelope,
    ImportItemResult,
    ImportItemStatus,
    ImportReport,
    classify_changes,
)
from knowledge_core.markdown.service import (
    EXPORTER_RESERVED_KEY,
    SOURCE_IDENTITY_KEYS,
    ExporterMetadataError,
    assert_exporter_metadata_clean,
    extract_frontmatter_raw,
    inject_exporter_instance_id,
    scan_frontmatter_duplicate_keys,
    split_exporter_metadata,
    split_source_identity,
)

__all__ = [
    "ATTACHMENT_EXPORT_UNSUPPORTED",
    "ATTACHMENT_IMPORT_UNSUPPORTED",
    "ATTACHMENT_ONLY_IMPORT_UNSUPPORTED",
    "ATTACHMENT_REVIEW_UNSUPPORTED",
    "IMPORT_ENVELOPE_INVALID",
    "IMPORT_FAILED",
    "MarkdownImportDocument",
    "MarkdownService",
    "MarkdownServiceError",
    "SOURCE_CHANGED_DURING_WAIT",
    "SOURCE_HAS_PENDING_IMPORT",
    "SOURCE_IDENTITY_AMBIGUOUS",
    "SOURCE_IDENTITY_CONFLICT",
]

ATTACHMENT_IMPORT_UNSUPPORTED = "ATTACHMENT_IMPORT_UNSUPPORTED"
ATTACHMENT_ONLY_IMPORT_UNSUPPORTED = "ATTACHMENT_ONLY_IMPORT_UNSUPPORTED"
ATTACHMENT_EXPORT_UNSUPPORTED = "ATTACHMENT_EXPORT_UNSUPPORTED"
ATTACHMENT_REVIEW_UNSUPPORTED = "ATTACHMENT_REVIEW_UNSUPPORTED"
SOURCE_CHANGED_DURING_WAIT = "SOURCE_CHANGED_DURING_WAIT"
SOURCE_HAS_PENDING_IMPORT = "SOURCE_HAS_PENDING_IMPORT"
SOURCE_IDENTITY_AMBIGUOUS = "SOURCE_IDENTITY_AMBIGUOUS"
SOURCE_IDENTITY_CONFLICT = "SOURCE_IDENTITY_CONFLICT"
IMPORT_ENVELOPE_INVALID = "IMPORT_ENVELOPE_INVALID"
IMPORT_FAILED = "IMPORT_FAILED"

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_UNSAFE_FILENAME = re.compile(r'[\x00-\x1f<>:"/\\|?*]+')


class MarkdownServiceError(RuntimeError):
    def __init__(self, code: str, message: str = "", *, status_code: int = 400) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(f"{code}: {message}" if message else code)


@dataclass
class MarkdownImportDocument:
    content: str
    filename: str | None = None
    target_item_id: UUID | None = None
    frontmatter_resolution: str | None = None
    attachments_requested: bool = False
    # Server-side ZIP attachment source (never a client path/filename).  The
    # route parses/validates the archive; this object is passed through preflight
    # and only materialised into staging after every Active/pending check passes.
    attachment_source: ParsedImportZip | None = None


@dataclass
class ImportOutcome:
    report: ImportReport
    index_ids: list[UUID] = field(default_factory=list)


@dataclass
class ExportOutcome:
    filename: str
    text: str
    item_id: UUID
    source_instance_id: str | None
    source_document_id: str | None
    content_hash: str
    payload_hash: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class PreparedDocument:
    filename: str
    target_item_id: UUID | None
    document: MarkdownDocument
    hash_document: MarkdownDocument
    content_hash: str
    payload_hash: str
    source_instance_id: str | None
    source_document_id: str | None
    exporter_instance_id: str | None
    legacy: bool
    conflict: bool = False
    warnings: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)
    attachment_source: ParsedImportZip | None = None
    attachment_manifest: tuple[AttachmentManifestItem, ...] = ()
    staging_id: UUID | None = None
    staging_directory: Path | None = None


@dataclass(frozen=True)
class _PendingInfo:
    review_id: UUID
    item_id: UUID
    payload_hash: str
    attachments: tuple[AttachmentManifestItem, ...]

    @property
    def logical_set(self) -> tuple[tuple[str, str, str, int], ...]:
        return logical_manifest_set(self.attachments)

    @property
    def staging_id(self) -> str | None:
        if not self.attachments:
            return None
        return self.attachments[0].staging_id


@dataclass
class _State:
    signature: tuple[Any, ...]
    item_ids: tuple[str, ...]
    anonymous_ids: tuple[str, ...]
    applied_hashes: frozenset[str]
    pending_same: _PendingInfo | None
    pending_other: _PendingInfo | None


def _is_uuid_text(value: str | None) -> bool:
    return bool(value and _UUID_RE.fullmatch(value))


def _parse_uuid(value: Any) -> UUID | None:
    if not isinstance(value, str) or not _is_uuid_text(value):
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _drop_empty_metadata(document: MarkdownDocument) -> MarkdownDocument:
    if document.extra_metadata:
        return document
    document.__pydantic_fields_set__.discard("extra_metadata")
    return document


def _clean_filename(filename: str | None, fallback: str) -> str:
    name = (filename or "").strip().replace("\\", "/").split("/")[-1]
    # 只替换文件系统不安全字符；保留中文等 Unicode 文件名（title 推导依赖它）。
    name = _UNSAFE_FILENAME.sub("_", name).strip().rstrip(".")
    name = name[:180]
    if not name:
        name = fallback
    if not name.lower().endswith((".md", ".markdown")):
        name += ".md"
    return name


class MarkdownService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        coordinator: ImportCoordinator,
        identity: SourceIdentityService,
        instance_store: SourceInstanceIdStore,
        *,
        codec: StdlibMarkdownCodec | None = None,
        storage_lock: SQLiteStorageKeyLock | PostgresStorageKeyLock | None = None,
    ) -> None:
        self._factory = session_factory
        self._coordinator = coordinator
        self._identity = identity
        self._instance_store = instance_store
        self._codec = codec or StdlibMarkdownCodec()
        self._storage_lock = storage_lock

    @property
    def exporter_instance_id(self) -> str:
        """导出传输实例 ID 必须反映当前身份（ROTATE 后不得使用旧缓存）。"""
        return self._instance_store.read()

    @property
    def session_factory(self) -> sessionmaker[Session]:
        return self._factory

    def attachment_only_error_code(self, target_item_id: UUID | None) -> str:
        """Classify a zero-document attachment ZIP without creating staging."""
        if target_item_id is None:
            return ATTACHMENT_IMPORT_UNSUPPORTED
        session = self._factory()
        try:
            record = MarkdownItemRepository(session).get(target_item_id)
        finally:
            session.close()
        if record is not None and record.status == KnowledgeStatus.ACTIVE:
            return ATTACHMENT_ONLY_IMPORT_UNSUPPORTED
        return ATTACHMENT_IMPORT_UNSUPPORTED

    # ------------------------------------------------------------------ 导入
    def import_documents(
        self,
        documents: list[MarkdownImportDocument],
        *,
        space_id: str | None = None,
        manifest: dict[str, Any] | None = None,
        batch_id: str | None = None,
        reject_attachments: bool = False,
        attachment_staging: AttachmentStagingService | None = None,
    ) -> ImportOutcome:
        if not documents:
            raise MarkdownServiceError("IMPORT_EMPTY", "no documents")
        # D23 恢复门：恢复完成前禁止分类/身份写入/新操作（含导入）。
        self._identity.recover_if_needed()
        if (
            any(doc.attachment_source is not None for doc in documents)
            and attachment_staging is None
        ):
            raise MarkdownServiceError(
                ATTACHMENT_IMPORT_UNSUPPORTED,
                "attachment staging service unavailable",
            )
        prepared = self._preflight(documents, manifest)
        if reject_attachments:
            for item in prepared:
                if ATTACHMENT_IMPORT_UNSUPPORTED in item.unsupported:
                    # 单篇入口：附件请求显式拒绝，零写入（含 item/tags/origin）。
                    raise MarkdownServiceError(
                        ATTACHMENT_IMPORT_UNSUPPORTED,
                        "Batch A 不支持附件导入",
                    )
        report = ImportReport()
        index_ids: list[UUID] = []
        for item in prepared:
            if item.conflict:
                # D-06：frontmatter 冲突篇跳过，记录 conflicts；不写任何业务字段。
                report.add(
                    ImportItemResult(
                        filename=item.filename,
                        status=ImportItemStatus.SKIPPED,
                        source_content_hash=item.content_hash,
                        source_payload_hash=item.payload_hash,
                        conflicts=["frontmatter_conflict_requires_resolution"],
                        warnings=item.warnings,
                    )
                )
                continue
            if item.unsupported:
                # 批量含附件：该篇 unsupported（零附件写入），其余篇继续。
                report.add(
                    ImportItemResult(
                        filename=item.filename,
                        status=ImportItemStatus.UNSUPPORTED,
                        source_content_hash=item.content_hash,
                        source_payload_hash=item.payload_hash,
                        errors=list(item.unsupported),
                        unsupported=list(item.unsupported),
                        warnings=item.warnings,
                    )
                )
                continue
            needs_index = False
            try:
                result, needs_index = self._import_one(
                    item,
                    default_space_id=space_id,
                    batch_id=batch_id,
                    attachment_staging=attachment_staging,
                )
            except AttachmentStagingError:
                raise
            except MarkdownServiceError as exc:
                if item.attachment_source is not None:
                    # Attachment ZIPs are a single-owner request; conflicts and
                    # stable rejections must reach the HTTP boundary, not become
                    # a per-item 200 report entry.
                    raise
                result = ImportItemResult(
                    filename=item.filename,
                    status=ImportItemStatus.ERROR,
                    errors=[exc.code],
                    source_content_hash=item.content_hash,
                    source_payload_hash=item.payload_hash,
                )
            except SourceIdentityError as exc:
                if item.attachment_source is not None:
                    raise
                result = ImportItemResult(
                    filename=item.filename,
                    status=ImportItemStatus.ERROR,
                    errors=[exc.code],
                )
            except ImportLockTimeout:
                if item.attachment_source is not None:
                    raise
                result = ImportItemResult(
                    filename=item.filename,
                    status=ImportItemStatus.ERROR,
                    errors=[IMPORT_LOCK_TIMEOUT],
                    source_content_hash=item.content_hash,
                    source_payload_hash=item.payload_hash,
                )
            except Exception:  # noqa: BLE001 - 单篇隔离，不外泄异常文本
                if item.attachment_source is not None:
                    raise
                result = ImportItemResult(
                    filename=item.filename,
                    status=ImportItemStatus.ERROR,
                    errors=[IMPORT_FAILED],
                )
            report.add(result)
            if item.legacy and result.status not in (
                ImportItemStatus.ERROR,
                ImportItemStatus.UNSUPPORTED,
            ):
                report.legacy += 1
            if result.status != ImportItemStatus.ERROR and needs_index and result.item_id:
                index_ids.append(result.item_id)
        return ImportOutcome(report, index_ids)

    # -- D22 预检（任何 DB 写之前） ----------------------------------------
    def _preflight(
        self,
        documents: list[MarkdownImportDocument],
        manifest: dict[str, Any] | None,
    ) -> list[PreparedDocument]:
        manifest_map = self._manifest_map(manifest)
        try:
            prepared = [self._prepare(doc) for doc in documents]
        except ExporterMetadataError as exc:
            raise MarkdownServiceError(exc.code, "D22 保留键冲突") from exc
        for item in prepared:
            entry = manifest_map.get(item.filename)
            if entry is not None:
                manifest_exporter = entry.get("exporter_instance_id")
                if manifest_exporter != item.exporter_instance_id:
                    raise MarkdownServiceError(
                        "EXPORTER_METADATA_RESERVED_CONFLICT",
                        f"manifest 与 frontmatter exporter 不一致: {item.filename}",
                    )
        # 用户 DB metadata 占用保留键（类型①）/嵌套（类型④）：读阶段拒绝，零写入。
        session = self._factory()
        try:
            repo = MarkdownItemRepository(session)
            for item in prepared:
                targets: set[str] = set()
                if item.source_instance_id and item.source_document_id:
                    origins = SQLAlchemyImportOriginRepository(
                        session
                    ).find_by_source_document(
                        UUID(item.source_document_id),
                        source_instance_id=item.source_instance_id,
                    )
                    targets.update(str(origin.item_id) for origin in origins)
                if item.target_item_id is not None:
                    targets.add(str(item.target_item_id))
                elif item.document.id is not None and not targets:
                    targets.add(str(item.document.id))
                if len(targets) > 1:
                    raise MarkdownServiceError(
                        SOURCE_IDENTITY_AMBIGUOUS,
                        "同一来源身份对应多个条目",
                        status_code=409,
                    )
                for target in targets:
                    record = repo.get(target)
                    if record is not None:
                        try:
                            assert_exporter_metadata_clean(record.extra_metadata)
                        except ExporterMetadataError as exc:
                            raise MarkdownServiceError(
                                exc.code, "用户 metadata 占用保留键"
                            ) from exc
        finally:
            session.close()
        return prepared

    @staticmethod
    def _manifest_map(manifest: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
        if not manifest:
            return {}
        entries = manifest.get("documents", manifest)
        result: dict[str, dict[str, Any]] = {}
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict) and isinstance(entry.get("filename"), str):
                    result[entry["filename"]] = entry
        elif isinstance(entries, dict):
            for name, entry in entries.items():
                if isinstance(entry, dict):
                    result[str(name)] = entry
        return result

    def _prepare(self, incoming: MarkdownImportDocument) -> PreparedDocument:
        filename = _clean_filename(incoming.filename, "document.md")
        text = incoming.content
        raw = extract_frontmatter_raw(text)
        if raw is not None:
            duplicates = set(scan_frontmatter_duplicate_keys(raw))
            reserved = {EXPORTER_RESERVED_KEY, *SOURCE_IDENTITY_KEYS}
            if duplicates & reserved:
                raise MarkdownServiceError(
                    "EXPORTER_METADATA_RESERVED_CONFLICT",
                    f"frontmatter 重复保留键（折叠前）: {filename}",
                )
        resolution: FrontmatterResolution | None = None
        if incoming.frontmatter_resolution is not None:
            try:
                resolution = FrontmatterResolution(incoming.frontmatter_resolution)
            except ValueError as exc:
                raise MarkdownServiceError(
                    "FRONTMATTER_RESOLUTION_INVALID",
                    f"{filename}: 非法 frontmatter resolution",
                ) from exc
        parsed = self._codec.parse(text)
        conflict = parsed.state == FrontmatterState.CONFLICT
        warnings: list[str] = []
        document = parsed.document
        if conflict and resolution == FrontmatterResolution.NORMALIZE:
            resolved = resolve_frontmatter_conflict(document, resolution)
            document = resolved.document
            warnings.extend(warning.code.value for warning in resolved.warnings)
            conflict = document.frontmatter_state == FrontmatterState.CONFLICT
        if conflict:
            # D-06：批量默认跳过并记录 conflicts；单篇须显式 normalize 才导入。
            warnings.append(MarkdownWarningCode.CONFLICT_REQUIRES_RESOLUTION.value)
        clean, exporter = split_exporter_metadata(document.extra_metadata)
        identity_invalid = False
        try:
            clean, identity = split_source_identity(clean)
        except CanonicalizationError:
            # 非法来源身份仍属传输位置：必须剥离，绝不作为用户 metadata 落库/导出。
            clean = {
                key: value
                for key, value in clean.items()
                if key not in SOURCE_IDENTITY_KEYS
            }
            identity = {}
            identity_invalid = True
        clean = {
            key: value
            for key, value in clean.items()
            if key
            not in ("_frontmatter_raw", "_raw", "_duplicates", "_conflict")
        }
        document = document.model_copy(update={"extra_metadata": clean})
        _drop_empty_metadata(document)

        instance = identity.get("source_instance_id")
        source_doc = identity.get("source_document_id")
        has_identity_fields = instance is not None or source_doc is not None
        legacy = False
        instance_uuid = _parse_uuid(instance)
        source_doc_uuid = _parse_uuid(source_doc)
        if identity_invalid:
            legacy = True
            warnings.append("legacy_source_identity")
        elif has_identity_fields and (
            instance_uuid is None or instance_uuid.version != 4 or source_doc_uuid is None
        ):
            # 来源身份不合法/不完整：按 legacy 文档处理，不伪造、不认领任何身份。
            legacy = True
            instance = None
            source_doc = None
            warnings.append("legacy_source_identity")

        hash_document = document
        _drop_empty_metadata(hash_document)
        hashes = compute_document_hashes(hash_document)
        unsupported: list[str] = []
        attachment_source = incoming.attachment_source
        # Frontmatter attachment references remain Batch A-unsupported.  A
        # validated server-side ZIP attachment source is the only path that
        # removes ATTACHMENT_IMPORT_UNSUPPORTED.
        if document.attachments or (
            incoming.attachments_requested and attachment_source is None
        ) or attachment_source is not None and not attachment_source.attachments:
            unsupported.append(ATTACHMENT_IMPORT_UNSUPPORTED)
            warnings.append(ATTACHMENT_IMPORT_UNSUPPORTED)
        for warning in parsed.warnings:
            warnings.append(warning.code.value)
        return PreparedDocument(
            filename=filename,
            target_item_id=incoming.target_item_id,
            document=document,
            hash_document=hash_document,
            content_hash=hashes.document_content_hash,
            payload_hash=hashes.document_payload_hash,
            source_instance_id=instance,
            source_document_id=source_doc,
            exporter_instance_id=exporter,
            legacy=legacy,
            conflict=conflict,
            warnings=warnings,
            unsupported=unsupported,
            attachment_source=attachment_source,
        )

    # -- 单篇导入 -----------------------------------------------------------
    def _lock_key(self, item: PreparedDocument, target: UUID | None) -> str:
        if item.source_instance_id and item.source_document_id:
            return "identity:" + sha256_canonical(
                {
                    "source_instance_id": item.source_instance_id,
                    "source_document_id": item.source_document_id,
                }
            )
        if target is not None:
            return f"target-item:{target}"
        return f"anonymous-content:{item.content_hash}"

    def _read_state(
        self, session: Session, item: PreparedDocument, target: UUID | None
    ) -> _State:
        origins_repo = SQLAlchemyImportOriginRepository(session)
        origins = []
        if item.source_instance_id and item.source_document_id:
            origins = origins_repo.find_by_source_document(
                UUID(item.source_document_id),
                source_instance_id=item.source_instance_id,
            )
        item_ids = tuple(sorted({str(origin.item_id) for origin in origins}))
        repo = MarkdownItemRepository(session)
        item_records: dict[str, MarkdownItemRecord] = {}
        for item_id in item_ids:
            record = repo.get(item_id)
            if record is None:
                raise MarkdownServiceError(
                    SOURCE_IDENTITY_ORPHAN, "origin references missing item", status_code=409
                )
            item_records[item_id] = record
        if target is not None and str(target) not in item_records:
            record = repo.get(target)
            if record is not None:
                item_records[str(target)] = record
        anonymous_records: dict[str, MarkdownItemRecord] = {}
        if not item_ids and target is None:
            # 无身份/无目标：以 content_hash 找同内容候选，仅用于“同 payload 已应用”
            # 幂等判定；不同 payload 仍走 duplicates，绝不静默覆盖。
            for record in repo.find_by_source_content_hash(item.content_hash):
                anonymous_records[str(record.id)] = record
        pending_same: _PendingInfo | None = None
        pending_other: str | None = None
        pending_signature: list[tuple[str, str, tuple[Any, ...]]] = []
        for review in SQLAlchemyReviewRepository(session).list_reviews(_pending()):
            envelope = self._envelope_or_error(review.payload)
            if envelope is None:
                continue
            if not self._envelope_matches(envelope, item, review.item_id, target):
                continue
            attachments = self._envelope_manifest(envelope)
            pending_signature.append(
                (
                    str(review.id),
                    envelope.source_payload_hash,
                    tuple(item.model_dump(mode="json") for item in attachments),
                )
            )
            if envelope.source_payload_hash == item.payload_hash:
                if pending_same is None:
                    pending_same = _PendingInfo(
                        review_id=review.id,
                        item_id=review.item_id,
                        payload_hash=envelope.source_payload_hash,
                        attachments=attachments,
                    )
            else:
                if pending_other is None:
                    pending_other = _PendingInfo(
                        review_id=review.id,
                        item_id=review.item_id,
                        payload_hash=envelope.source_payload_hash,
                        attachments=attachments,
                    )
        signature = (
            tuple(
                sorted(
                    (
                        item_id,
                        record.source_payload_hash,
                        record.source_content_hash,
                        record.source_instance_id,
                        record.title,
                        record.content,
                    )
                    for item_id, record in {**item_records, **anonymous_records}.items()
                )
            ),
            tuple(sorted(pending_signature)),
        )
        applied_hashes: set[str] = set()
        for record in item_records.values():
            if record.source_payload_hash:
                applied_hashes.add(record.source_payload_hash)
        for record in anonymous_records.values():
            if record.source_payload_hash:
                applied_hashes.add(record.source_payload_hash)
        for origin in origins:
            if origin.source_payload_hash:
                applied_hashes.add(origin.source_payload_hash)
        applied = frozenset(applied_hashes)
        return _State(
            signature,
            item_ids,
            tuple(sorted(anonymous_records)),
            applied,
            pending_same,
            pending_other,
        )

    @staticmethod
    def _envelope_or_error(payload: dict[str, Any]) -> ImportEnvelope | None:
        try:
            return ImportEnvelope.from_review_payload(payload)
        except Exception as exc:
            raise MarkdownServiceError(
                IMPORT_ENVELOPE_INVALID,
                "导入审核 envelope 非法",
                status_code=409,
            ) from exc

    @staticmethod
    def _envelope_manifest(envelope: ImportEnvelope) -> tuple[AttachmentManifestItem, ...]:
        if not envelope.attachments:
            return ()
        try:
            return coerce_manifest_items(envelope.attachments)
        except AttachmentStagingError as exc:
            code = (
                ATTACHMENT_MANIFEST_CORRUPTED
                if exc.code == "ATTACHMENT_MANIFEST_DUPLICATE"
                else exc.code
            )
            raise MarkdownServiceError(
                code,
                "审核 envelope 附件 manifest 非法",
                status_code=409 if code == ATTACHMENT_MANIFEST_CORRUPTED else exc.status_code,
            ) from exc

    @staticmethod
    def _envelope_matches(
        envelope: ImportEnvelope,
        item: PreparedDocument,
        review_item_id: UUID,
        target: UUID | None,
    ) -> bool:
        if item.source_instance_id and item.source_document_id:
            return (
                envelope.source_instance_id == item.source_instance_id
                and envelope.source_document_id == item.source_document_id
            )
        expected_target = target or item.document.id
        return (
            envelope.source_instance_id is None
            and envelope.source_document_id is None
            and expected_target is not None
            and str(review_item_id) == str(expected_target)
        )

    def _import_one(
        self,
        item: PreparedDocument,
        *,
        default_space_id: str | None,
        batch_id: str | None,
        attachment_staging: AttachmentStagingService | None,
    ) -> tuple[ImportItemResult, bool]:
        target = item.target_item_id
        target = item.document.id if target is None and item.document.id else target
        # target 仅作为候选；来源身份存在时先按身份查条目。
        lock_key = self._lock_key(item, target)
        s0_session = self._factory()
        try:
            s0 = self._read_state(s0_session, item, target)
        finally:
            s0_session.close()
        # P1-02：身份分类校验、导入 DB 写入与 commit 必须与 MATERIALIZE/ROTATE
        # 串行（同一 Journal 锁），避免并发导出物化后导入追加 ImportOrigin。
        with self._coordinator.keyed(lock_key), self._identity.identity_guard():
            session = self._factory()
            try:
                s1 = self._read_state(session, item, target)
                if len(s1.item_ids) > 1:
                    raise MarkdownServiceError(
                        SOURCE_IDENTITY_AMBIGUOUS,
                        "同一来源身份对应多个条目",
                        status_code=409,
                    )
                attachment_context = None
                if item.attachment_source is not None:
                    attachment_context = self._attachment_context(
                        session, item, target, s1, attachment_staging
                    )
                decision_same = item.payload_hash in s1.applied_hashes
                if s0.signature != s1.signature:
                    if decision_same:
                        return (
                            self._skipped_result(
                                session,
                                item,
                                s1,
                                attachment_context,
                                attachment_staging,
                            ),
                            False,
                        )
                    if s1.pending_same:
                        return (
                            self._reuse_pending(
                                item, s1.pending_same, attachment_staging
                            ),
                            False,
                        )
                    raise MarkdownServiceError(
                        SOURCE_CHANGED_DURING_WAIT,
                        "来源在等待锁期间已变化，请重新发起",
                        status_code=409,
                    )
                if decision_same:
                    return (
                        self._skipped_result(
                            session,
                            item,
                            s1,
                            attachment_context,
                            attachment_staging,
                        ),
                        False,
                    )
                if s1.pending_same:
                    return (
                        self._reuse_pending(item, s1.pending_same, attachment_staging),
                        False,
                    )
                if s1.pending_other:
                    if item.attachment_source is not None or s1.pending_other.attachments:
                        raise AttachmentStagingError("SOURCE_HAS_PENDING_IMPORT")
                    raise MarkdownServiceError(
                        SOURCE_HAS_PENDING_IMPORT,
                        "同身份已有不同版本的待审导入",
                        status_code=409,
                    )
                if item.attachment_source is not None and (
                    attachment_context is not None
                    and attachment_context[0].status == KnowledgeStatus.ACTIVE
                    and not attachment_context[1].has_content_change
                ):
                    raise MarkdownServiceError(
                        ATTACHMENT_ONLY_IMPORT_UNSUPPORTED,
                        "Active 无标题/正文变化时不允许仅附件导入",
                        status_code=400,
                    )
                if item.attachment_source is not None:
                    if attachment_staging is None:
                        raise MarkdownServiceError(
                            ATTACHMENT_IMPORT_UNSUPPORTED,
                            "attachment staging unavailable",
                        )
                    stage_context = attachment_staging.stage_from_zip(
                        item.attachment_source
                    )
                else:
                    stage_context = contextlib.nullcontext(None)
                # P1-01: the staging guard must span staging creation, the
                # ReviewRequest flush and the business commit.  The lease
                # removes its directory on a known-uncommitted failure and
                # keeps it for ORP when the commit outcome is ambiguous.
                with stage_context as lease:
                    if lease is not None and (
                        attachment_context is None
                        or attachment_context[0].status == KnowledgeStatus.DRAFT
                    ):
                        expected = attachment_context[0] if attachment_context else None
                        session.close()
                        assert attachment_staging is not None
                        return self._import_draft_attachments(
                            item, target, s1, expected, attachment_staging, lease,
                            default_space_id=default_space_id, batch_id=batch_id,
                        )
                    staged = lease.staged if lease is not None else None
                    try:
                        result, needs_index = self._apply_import(
                            session,
                            item,
                            target=target,
                            existing_ids=s1.item_ids,
                            default_space_id=default_space_id,
                            batch_id=batch_id,
                            attachment_staging=attachment_staging,
                            staged=staged,
                        )
                        if lease is not None:
                            # Preserve before commit. Rollback can also fail after
                            # a disconnect and must not remove a committed review's files.
                            lease.keep_for_orp = True
                        session.commit()
                        if lease is not None:
                            lease.committed = True
                        return result, needs_index
                    except Exception:
                        session.rollback()
                        raise
            finally:
                session.close()

    def _import_draft_attachments(
        self,
        item: PreparedDocument,
        target: UUID | None,
        state: _State,
        expected: MarkdownItemRecord | None,
        staging: AttachmentStagingService,
        lease: StagingLease,
        *,
        default_space_id: str | None,
        batch_id: str | None,
    ) -> tuple[ImportItemResult, bool]:
        assert lease.staged is not None
        manifest = lease.staged.manifest
        expected_id = expected.id if expected else None
        with self.attachment_keys([entry.storage_key for entry in manifest]) as guard:
            try:
                published = publish_staged(staging, lease.staging_id, manifest, expected_id, guard)
            except AttachmentStorageError as exc:
                raise MarkdownServiceError(exc.code, status_code=503) from None
            with self._factory() as session:
                try:
                    if expected_id is not None:
                        MarkdownItemRepository(session).lock_for_import(expected_id)
                    fresh = self._read_state(session, item, target)
                    current = self._resolve_attachment_record(session, item, target, fresh)
                    if fresh.signature != state.signature or current != expected:
                        raise MarkdownServiceError(SOURCE_CHANGED_DURING_WAIT, status_code=409)
                    result, needs_index = self._apply_import(
                        session,
                        item,
                        target=target,
                        existing_ids=fresh.item_ids,
                        default_space_id=default_space_id,
                        batch_id=batch_id,
                    )
                    if result.item_id is None or result.status not in (
                        ImportItemStatus.CREATED, ImportItemStatus.UPDATED,
                    ):
                        raise MarkdownServiceError(ATTACHMENT_IMPORT_UNSUPPORTED)
                    published.save_references(session, result.item_id)
                    result.warnings.append("attachments_applied")
                    guard.verify_all(session)
                    lease.keep_for_orp = True
                    session.commit()
                    # The successful Draft has no pending staging reference.
                    # The staging lease removes its own directory on exit.
                    lease.keep_for_orp = False
                except BaseException:
                    session.rollback()
                    raise
            return result, needs_index

    def _resolve_attachment_record(
        self,
        session: Session,
        item: PreparedDocument,
        target: UUID | None,
        state: _State,
    ) -> MarkdownItemRecord | None:
        repo = MarkdownItemRepository(session)
        if state.item_ids:
            return repo.get(state.item_ids[0])
        if target is not None:
            record = repo.get(target)
            if record is not None:
                return record
        if len(state.anonymous_ids) == 1:
            return repo.get(state.anonymous_ids[0])
        return None

    def _attachment_context(
        self,
        session: Session,
        item: PreparedDocument,
        target: UUID | None,
        state: _State,
        staging: AttachmentStagingService | None,
    ) -> tuple[MarkdownItemRecord, ChangeSet] | None:
        if staging is None:
            raise MarkdownServiceError(
                ATTACHMENT_IMPORT_UNSUPPORTED, "attachment staging unavailable"
            )
        record = self._resolve_attachment_record(session, item, target, state)
        if (
            not state.item_ids
            and (target is None or record is None)
            and item.payload_hash not in state.applied_hashes
            and self._content_duplicates(MarkdownItemRepository(session), item.content_hash)
        ):
            raise MarkdownServiceError(ATTACHMENT_IMPORT_UNSUPPORTED)
        if record is None:
            return None
        if record.status == KnowledgeStatus.ARCHIVED:
            raise MarkdownServiceError(
                ATTACHMENT_IMPORT_UNSUPPORTED, "归档条目不允许附件导入"
            )
        changes, _ = self._record_changes(session, record, item)
        return record, changes

    def _record_changes(
        self,
        session: Session,
        record: MarkdownItemRecord,
        item: PreparedDocument,
    ) -> tuple[ChangeSet, list[str]]:
        old_tags = SQLAlchemyTagRepository(session).list_item_tags(record.id)
        current_links = [
            {
                "target_title": link.target_title,
                "alias": link.alias,
                "target_id": str(link.target_id) if link.target_id else None,
                "resolution": link.resolution.value,
            }
            for link in SQLAlchemyLinkRepository(session).list_links(record.id)
        ]
        changes = classify_changes(
            current_title=record.title,
            current_content=record.content,
            current_status=record.status,
            current_space_id=record.space_id,
            current_tags=old_tags,
            current_extra_metadata=record.extra_metadata,
            current_links=current_links,
            current_attachments=[],
            incoming=item.document,
        )
        return changes, old_tags

    def _attachments_satisfied(
        self,
        session: Session,
        item_id: UUID,
        item: PreparedDocument,
        staging: AttachmentStagingService,
    ) -> bool:
        assert item.attachment_source is not None
        entries = item.attachment_source.attachments
        # The SQLite read snapshot must end before the lock manager writes its
        # lease. The checked references must come from a fresh snapshot.
        session.close()
        with self.attachment_keys([entry.storage_key for entry in entries]) as guard:
            with self._factory() as snapshot:
                refs = {
                    attachment.storage_key
                    for attachment in SQLAlchemyAttachmentRepository(snapshot).list_attachments(item_id)
                }
            if not all(entry.storage_key in refs for entry in entries):
                return False
            for entry in entries:
                guard.verify_all()
                staging.verify_published(entry.storage_key, len(entry.data))
            guard.verify_all()
            return True

    @contextlib.contextmanager
    def attachment_keys(self, keys: list[str]):
        if self._storage_lock is None:
            raise MarkdownServiceError(STORAGE_LOCK_UNAVAILABLE, status_code=503)
        guard: LockGuard | None = None
        try:
            guard = self._storage_lock.acquire_many(keys, new_owner())
            if guard is None:
                raise MarkdownServiceError("STORAGE_LOCK_TIMEOUT", status_code=409)
            yield guard
        except StorageLockError as exc:
            raise MarkdownServiceError(exc.code, status_code=503) from None
        except StorageLockTransient:
            raise MarkdownServiceError(STORAGE_LOCK_UNAVAILABLE, status_code=503) from None
        finally:
            release_storage_guard(guard)

    def _skipped_result(
        self,
        session: Session,
        item: PreparedDocument,
        state: _State,
        attachment_context: tuple[MarkdownItemRecord, ChangeSet] | None,
        staging: AttachmentStagingService | None,
    ) -> ImportItemResult:
        matched = state.item_ids or state.anonymous_ids
        if matched:
            item_id = UUID(matched[0])
        elif attachment_context is not None:
            item_id = attachment_context[0].id
        else:
            item_id = None
        warnings = list(item.warnings)
        if item.attachment_source is not None:
            if (
                attachment_context is None
                or staging is None
                or not self._attachments_satisfied(
                    session, attachment_context[0].id, item, staging
                )
            ):
                raise MarkdownServiceError(
                    ATTACHMENT_ONLY_IMPORT_UNSUPPORTED
                    if attachment_context is not None
                    and attachment_context[0].status == KnowledgeStatus.ACTIVE
                    else ATTACHMENT_IMPORT_UNSUPPORTED,
                    "已应用版本缺少请求的附件引用",
                    status_code=400,
                )
            warnings.append("attachments_already_satisfied")
        return ImportItemResult(
            filename=item.filename,
            item_id=item_id,
            status=ImportItemStatus.SKIPPED,
            source_payload_hash=item.payload_hash,
            source_content_hash=item.content_hash,
            warnings=warnings,
            unsupported=item.unsupported,
        )

    def _reuse_pending(
        self,
        item: PreparedDocument,
        pending: _PendingInfo,
        staging: AttachmentStagingService | None,
    ) -> ImportItemResult:
        incoming = (
            item.attachment_source.logical_set
            if item.attachment_source is not None
            else ()
        )
        if incoming != pending.logical_set:
            # This is an attachment-set conflict even when the retry itself has
            # no JSON attachment field; it must reach HTTP as 409, not a 200
            # per-item error report.
            raise AttachmentStagingError(SOURCE_HAS_PENDING_IMPORT)
        if pending.attachments:
            if staging is None:
                raise MarkdownServiceError(
                    ATTACHMENT_STAGING_INVALID,
                    "pending 附件 staging 服务不可用",
                    status_code=409,
                )
            staging_id = pending.staging_id
            if staging_id is None:
                raise MarkdownServiceError(
                    ATTACHMENT_MANIFEST_CORRUPTED, "pending staging id missing", status_code=409
                )
            # Hold the staging guard while re-reading the pending row, then
            # validate the physical staging beneath the same guard.  This
            # closes the S1→guard window in which the review could be resolved
            # or the envelope edited.
            with staging.staging_guard(staging_id):
                self._verify_pending_unchanged(pending)
                staging.validate_manifest_locked(
                    staging_id, pending.attachments, require_complete=True
                )
        else:
            self._verify_pending_unchanged(pending)
        warnings = list(item.warnings)
        if item.attachment_source is not None:
            warnings.append("attachments_pending_reused")
        return ImportItemResult(
            filename=item.filename,
            status=ImportItemStatus.REUSED_PENDING,
            review_id=pending.review_id,
            item_id=pending.item_id,
            source_payload_hash=item.payload_hash,
            source_content_hash=item.content_hash,
            warnings=warnings,
            unsupported=item.unsupported,
        )

    def _verify_pending_unchanged(self, pending: _PendingInfo) -> None:
        """Re-read a pending review and fail closed if it drifted."""
        session = self._factory()
        try:
            row = session.get(ReviewRequestORM, str(pending.review_id))
            if row is None or row.status != "pending":
                raise MarkdownServiceError(
                    SOURCE_CHANGED_DURING_WAIT,
                    "原待审导入已变化，请重新发起",
                    status_code=409,
                )
            if str(row.item_id) != str(pending.item_id):
                raise MarkdownServiceError(
                    SOURCE_HAS_PENDING_IMPORT,
                    "待审导入目标已变化",
                    status_code=409,
                )
            try:
                payload = json.loads(row.payload or "{}")
            except (TypeError, json.JSONDecodeError) as exc:
                raise MarkdownServiceError(
                    IMPORT_ENVELOPE_INVALID,
                    "导入审核 envelope 非法",
                    status_code=409,
                ) from exc
            if not isinstance(payload, dict):
                raise MarkdownServiceError(
                    IMPORT_ENVELOPE_INVALID,
                    "导入审核 envelope 非法",
                    status_code=409,
                )
            envelope = self._envelope_or_error(payload)
            if envelope is None:
                raise MarkdownServiceError(
                    SOURCE_HAS_PENDING_IMPORT,
                    "待审导入缺少 envelope",
                    status_code=409,
                )
            if envelope.source_payload_hash != pending.payload_hash:
                raise MarkdownServiceError(
                    SOURCE_HAS_PENDING_IMPORT,
                    "待审导入内容已变化",
                    status_code=409,
                )
            fresh = self._envelope_manifest(envelope)
            if fresh != pending.attachments:
                raise MarkdownServiceError(
                    SOURCE_HAS_PENDING_IMPORT,
                    "待审导入附件集合已变化",
                    status_code=409,
                )
        finally:
            session.close()

    # -- 落库 ---------------------------------------------------------------
    def _resolve_space(self, session: Session, desired: str | None) -> str | None:
        if desired is None:
            return None
        return desired if session.get(KnowledgeSpace, desired) is not None else None

    def _apply_import(
        self,
        session: Session,
        item: PreparedDocument,
        *,
        target: UUID | None,
        existing_ids: tuple[str, ...],
        default_space_id: str | None,
        batch_id: str | None,
        attachment_staging: AttachmentStagingService | None = None,
        staged: StagedAttachmentSet | None = None,
    ) -> tuple[ImportItemResult, bool]:
        items = MarkdownItemRepository(session)
        tags = SQLAlchemyTagRepository(session)
        origins = SQLAlchemyImportOriginRepository(session)
        logs = SQLAlchemyTagChangeLogRepository(session)
        doc = item.document
        desired_space = self._resolve_space(
            session, doc.space_id if doc.space_id is not None else default_space_id
        )
        warnings = list(item.warnings)
        if doc.space_id is not None and desired_space is None:
            warnings.append("space_not_found_personal_fallback")

        existing: MarkdownItemRecord | None = None
        if existing_ids:
            existing = items.get(existing_ids[0])
        elif target is not None:
            existing = items.get(target)
        if existing is not None and self._identity.has_committed_materialize(
            existing.id
        ):
            # §22.2：ImportOrigin 与 COMMITTED MATERIALIZE 并存即冲突态。
            # 已物化本地文档不得经导入追加来源身份或重写实例字段（2b 冻结）。
            raise MarkdownServiceError(
                SOURCE_IDENTITY_CONFLICT,
                "目标条目为已物化本地文档，导入不得追加来源身份",
                status_code=409,
            )
        # 既有条目来源身份不同 → 冲突，零写入（不覆盖来源身份）。
        if existing is not None and item.source_instance_id and item.source_document_id:
            existing_origins = origins.list_for_item(existing.id)
            if existing_origins:
                pairs = {
                    (origin.source_instance_id, str(origin.source_document_id))
                    for origin in existing_origins
                }
                if pairs != {(item.source_instance_id, item.source_document_id)}:
                    raise MarkdownServiceError(
                        SOURCE_IDENTITY_CONFLICT,
                        "目标条目来源身份与入站不一致",
                        status_code=409,
                    )

        # 无身份/无来源记录的新文档：content_hash 查重，只报告不覆盖。
        if existing is None and not existing_ids:
            duplicates = self._content_duplicates(items, item.content_hash)
            if duplicates:
                return (
                    ImportItemResult(
                        filename=item.filename,
                        status=ImportItemStatus.DUPLICATE,
                        source_payload_hash=item.payload_hash,
                        source_content_hash=item.content_hash,
                        duplicates=duplicates,
                        warnings=warnings,
                        unsupported=item.unsupported,
                    ),
                    False,
                )

        title = (doc.title or "").strip()
        if not title:
            title = item.filename.rsplit(".", 1)[0] or "未命名文档"
            warnings.append("title_from_filename")
        status_changes: list[str] = []
        if existing is None:
            new_status = KnowledgeStatus.DRAFT
            if doc.status is not None and doc.status != KnowledgeStatus.DRAFT:
                status_changes.append(f"{doc.status.value}->draft")
            record = items.create(
                title=title,
                content=doc.content,
                status=new_status.value,
                space_id=desired_space,
                extra_metadata=doc.extra_metadata,
                source_payload_hash=item.payload_hash if not item.legacy else None,
                source_content_hash=item.content_hash,
                source_instance_id=item.source_instance_id if not item.legacy else None,
            )
            old_tags: list[str] = []
            new_tags = tags.set_item_tags(record.id, doc.tags)
            self._log_tags(logs, record, old_tags, new_tags, batch_id)
            unresolved_links = self._restore_links(session, record, doc, warnings)
            if item.source_instance_id and item.source_document_id and not item.legacy:
                origins.save_origin(self._origin(record, item, batch_id))
            return (
                ImportItemResult(
                    filename=item.filename,
                    item_id=record.id,
                    status=ImportItemStatus.CREATED,
                    source_content_hash=item.content_hash,
                    source_payload_hash=item.payload_hash,
                    canonicalization_version=CANONICALIZATION_VERSION,
                    warnings=warnings,
                    unsupported=item.unsupported,
                    unresolved_links=unresolved_links,
                    status_changes=status_changes,
                ),
                True,
            )

        # 既有条目：变化分类
        changes, old_tags = self._record_changes(session, existing, item)
        is_active = existing.status == KnowledgeStatus.ACTIVE
        if is_active and changes.has_content_change:
            if item.attachment_source is not None:
                if staged is None or attachment_staging is None:
                    # The caller must create staging inside the staging guard;
                    # creating it here would release the guard before commit.
                    raise MarkdownServiceError(
                        ATTACHMENT_IMPORT_UNSUPPORTED,
                        "attachment staging lease unavailable",
                    )
                item.attachment_manifest = staged.manifest
                item.staging_id = staged.staging_id
                item.staging_directory = staged.directory
                warnings.append("attachments_staged")
            envelope = self._envelope(
                item,
                target=existing.id,
                desired_space=desired_space,
                new_status=KnowledgeStatus.DRAFT,
            )
            payload = envelope.review_payload(self._core_changes(item, desired_space))
            review = asyncio.run(
                build_review_service(session).submit(
                    existing.id,
                    ReviewAction.UPDATE_ITEM,
                    payload,
                    "Markdown 导入（Active 内容变更）",
                )
            )
            if review is None:
                raise MarkdownServiceError(IMPORT_FAILED, "active 未生成审核单", status_code=409)
            return (
                ImportItemResult(
                    filename=item.filename,
                    item_id=existing.id,
                    status=ImportItemStatus.PENDING_REVIEW,
                    review_id=review.id,
                    source_content_hash=item.content_hash,
                    source_payload_hash=item.payload_hash,
                    canonicalization_version=CANONICALIZATION_VERSION,
                    warnings=warnings,
                    unsupported=item.unsupported,
                    status_changes=["active->draft(pending review)"],
                ),
                False,
            )

        if is_active:
            new_status = KnowledgeStatus.ACTIVE
        else:
            new_status = KnowledgeStatus.DRAFT
            if doc.status is not None and doc.status != KnowledgeStatus.DRAFT:
                status_changes.append(f"{doc.status.value}->draft")
        record = items.update_fields(
            existing.id,
            title=title,
            content=doc.content,
            status=new_status.value,
            space_id=desired_space,
            extra_metadata=doc.extra_metadata,
            source_payload_hash=item.payload_hash if not item.legacy else None,
            source_content_hash=item.content_hash,
            source_instance_id=item.source_instance_id if not item.legacy else None,
        )
        new_tags = tags.set_item_tags(record.id, doc.tags)
        if old_tags != new_tags:
            self._log_tags(logs, record, old_tags, new_tags, batch_id)
        unresolved_links = self._restore_links(session, record, doc, warnings)
        if item.source_instance_id and item.source_document_id and not item.legacy:
            existing_versions = {
                origin.source_payload_hash for origin in origins.list_for_item(record.id)
            }
            if item.payload_hash not in existing_versions:
                origins.save_origin(self._origin(record, item, batch_id))
        return (
            ImportItemResult(
                filename=item.filename,
                item_id=record.id,
                status=ImportItemStatus.UPDATED,
                source_content_hash=item.content_hash,
                source_payload_hash=item.payload_hash,
                canonicalization_version=CANONICALIZATION_VERSION,
                warnings=warnings,
                unsupported=item.unsupported,
                unresolved_links=unresolved_links,
                status_changes=status_changes,
            ),
            True,
        )

    @staticmethod
    def _content_duplicates(
        items: MarkdownItemRepository, content_hash: str
    ) -> list[UUID]:
        from knowledge_core.markdown import document_content_hash

        found: list[UUID] = []
        for record in items.list_items():
            if (
                document_content_hash({"title": record.title, "content": record.content})
                == content_hash
            ):
                found.append(record.id)
        return found

    def _core_changes(
        self, item: PreparedDocument, desired_space: str | None
    ) -> dict[str, Any]:
        doc = item.document
        return {
            "title": (doc.title or "").strip() or item.filename.rsplit(".", 1)[0],
            "content": doc.content,
            "status": KnowledgeStatus.DRAFT.value,
            "space_id": desired_space,
        }

    def _envelope(
        self,
        item: PreparedDocument,
        *,
        target: UUID | None,
        desired_space: str | None,
        new_status: KnowledgeStatus,
    ) -> ImportEnvelope:
        doc = item.document
        return ImportEnvelope(
            target_item_id=str(target) if target else None,
            filename=item.filename,
            source_instance_id=item.source_instance_id,
            source_document_id=item.source_document_id,
            source_payload_hash=item.payload_hash,
            source_content_hash=item.content_hash,
            canonicalization_version=CANONICALIZATION_VERSION,
            space_id=desired_space,
            status=new_status.value,
            tags=list(doc.tags),
            extra_metadata=dict(doc.extra_metadata),
            links=list(doc.links),
            attachments=[
                manifest.model_dump(mode="json")
                for manifest in item.attachment_manifest
            ],
        ).with_digest()

    @staticmethod
    def _origin(
        record: MarkdownItemRecord, item: PreparedDocument, batch_id: str | None
    ) -> ImportOrigin:
        return ImportOrigin(
            item_id=record.id,
            source_payload_hash=item.payload_hash,
            source_content_hash=item.content_hash,
            source_instance_id=item.source_instance_id,
            source_document_id=UUID(item.source_document_id or str(record.id)),
            source_canonicalization_version=CANONICALIZATION_VERSION,
            imported_at=datetime.now(UTC),
            import_batch_id=batch_id,
        )

    @staticmethod
    def _log_tags(
        logs: SQLAlchemyTagChangeLogRepository,
        record: MarkdownItemRecord,
        old_tags: list[str],
        new_tags: list[str],
        batch_id: str | None,
    ) -> None:
        logs.append(
            TagChangeRecord(
                item_id=record.id,
                item_id_snapshot=record.id,
                item_title_snapshot=record.title,
                old_tags=old_tags,
                new_tags=new_tags,
                actor="import",
                change_source="markdown_import",
                correlation_id=batch_id,
            )
        )

    @staticmethod
    def _restore_links(
        session: Session,
        record: MarkdownItemRecord,
        doc: MarkdownDocument,
        warnings: list[str],
    ) -> list[str]:
        knowledge_item = KnowledgeItem(
            id=record.id,
            title=record.title,
            content=record.content,
            status=KnowledgeStatus(record.status),
            space_id=record.space_id,
            tags=[],
            extra_metadata=record.extra_metadata,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
        report = build_link_restorer(session).restore(knowledge_item, doc.links, doc.content)
        unresolved: list[str] = []
        for target in report.unresolved_links:
            title = target if isinstance(target, str) else getattr(target, "title", target)
            label = f"unresolved_link:{title}"
            warnings.append(label)
            unresolved.append(label)
        return unresolved

    # ------------------------------------------------------------------ 导出
    def export_documents(
        self,
        ids: list[UUID],
        *,
        space_id: str | None = None,
        include_attachments: bool = False,
    ) -> tuple[bytes, list[dict[str, Any]]]:
        if include_attachments:
            raise MarkdownServiceError(
                ATTACHMENT_EXPORT_UNSUPPORTED,
                "Batch A 不支持附件导出",
            )
        self._identity.recover_if_needed()
        session = self._factory()
        try:
            repo = MarkdownItemRepository(session)
            if ids:
                records = [repo.get(item_id) for item_id in ids]
                records = [record for record in records if record is not None]
            else:
                records = repo.list_items(space_id=space_id)
        finally:
            session.close()
        if not records:
            raise MarkdownServiceError("EXPORT_EMPTY", "无可导出条目")
        exports: list[ExportOutcome] = []
        errors: list[dict[str, str]] = []
        for record in records:
            try:
                exports.append(self._export_record(record))
            except (MarkdownServiceError, ExporterMetadataError) as exc:
                code = getattr(exc, "code", "EXPORT_FAILED")
                errors.append({"item_id": str(record.id), "error": code})
        if not exports:
            raise MarkdownServiceError("EXPORT_FAILED", "全部条目导出失败", status_code=409)

        manifest = {
            "schema_version": 1,
            "exporter_instance_id": self.exporter_instance_id,
            "attachment_export": "unsupported",
            "documents": [
                {
                    "filename": export.filename,
                    "item_id": str(export.item_id),
                    "source_instance_id": export.source_instance_id,
                    "source_document_id": export.source_document_id,
                    "exporter_instance_id": self.exporter_instance_id,
                    "document_content_hash": export.content_hash,
                    "document_payload_hash": export.payload_hash,
                    "warnings": export.warnings,
                }
                for export in exports
            ],
            "errors": errors,
        }
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for export in exports:
                archive.writestr(export.filename, export.text)
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            )
        return buffer.getvalue(), manifest["documents"]

    def export_single(self, item_id: UUID) -> ExportOutcome:
        self._identity.recover_if_needed()
        session = self._factory()
        try:
            record = MarkdownItemRepository(session).get(item_id)
        finally:
            session.close()
        if record is None:
            raise MarkdownServiceError("ITEM_NOT_FOUND", "条目不存在", status_code=404)
        return self._export_record(record)

    def _export_record(self, record: MarkdownItemRecord) -> ExportOutcome:
        assert_exporter_metadata_clean(record.extra_metadata)
        for key in SOURCE_IDENTITY_KEYS:
            if key in record.extra_metadata:
                raise ExporterMetadataError(f"用户 metadata 占用来源身份保留键 {key}")
        warnings: list[str] = []
        source_instance: str | None = None
        source_document: str | None = None
        # D23：先过恢复门；2a 需要 MATERIALIZE；2b 由 COMMITTED Journal 证明；3/4 不认领。
        session = self._factory()
        try:
            classified = self._identity.classify(session, record.id)
        finally:
            session.close()
        if classified.state == "2a":
            source_instance = self._identity.ensure_local_export_identity(record.id)
            source_document = str(record.id)
        elif classified.state == "2b":
            source_instance = classified.source_instance_id
            source_document = str(record.id)
        elif classified.state == "1":
            source_instance = classified.source_instance_id
            source_document = classified.source_document_id
        else:
            warnings.append("identity_incomplete")
        if source_document is None:
            source_document = str(record.id) if classified.state in ("2a", "2b", "1") else None

        session = self._factory()
        try:
            tags = SQLAlchemyTagRepository(session).list_item_tags(record.id)
            sources = [
                source.model_dump(mode="json")
                for source in MarkdownItemRepository(session).list_sources(record.id)
            ]
            links = [
                {
                    "target_title": link.target_title,
                    "alias": link.alias,
                    "target_id": str(link.target_id) if link.target_id else None,
                    "resolution": link.resolution.value,
                }
                for link in SQLAlchemyLinkRepository(session).list_links(record.id)
            ]
        finally:
            session.close()

        user_metadata = dict(record.extra_metadata)
        hash_document = MarkdownDocument(
            id=record.id,
            title=record.title,
            content=record.content,
            tags=tags,
            space_id=record.space_id,
            status=KnowledgeStatus(record.status),
            created_at=record.created_at,
            updated_at=record.updated_at,
            sources=sources,
            links=links,
            attachments=[],
            extra_metadata=user_metadata,
        )
        _drop_empty_metadata(hash_document)
        hashes = compute_document_hashes(hash_document)

        document_metadata = dict(user_metadata)
        if source_instance is not None and source_document is not None:
            document_metadata["source_instance_id"] = source_instance
            document_metadata["source_document_id"] = source_document
        document = hash_document.model_copy(
            update={
                "extra_metadata": document_metadata,
                "attachments": [],
            }
        )
        rendered = self._codec.dump(document)
        for warning in rendered.warnings:
            warnings.append(warning.code.value)
        text = inject_exporter_instance_id(rendered.text, self.exporter_instance_id)
        filename = _clean_filename(f"{record.title}-{record.id}", f"{record.id}.md")
        return ExportOutcome(
            filename=filename,
            text=text,
            item_id=record.id,
            source_instance_id=source_instance,
            source_document_id=source_document,
            content_hash=hashes.document_content_hash,
            payload_hash=hashes.document_payload_hash,
            warnings=warnings,
        )


def _pending():  # 延迟导入避免循环依赖
    from knowledge_core.domain.entities import ReviewStatus

    return ReviewStatus.PENDING
