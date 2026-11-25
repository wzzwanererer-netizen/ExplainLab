"""Attachment import staging and manifest (V2 A1-04 Batch B, B3-T01).

This module owns the physical part of ZIP attachment import:

* strict manifest element schema (``AttachmentManifestItem``);
* ZIP path/ownership validation with bounded reads;
* content-addressed staging under ``<staging_root>/<staging_id>/``;
* ``.creating`` / ``.activity`` / ``.complete`` lifecycle markers;
* manifest/file validation against a staging directory;
* safe discard and a conservative sweep candidate decision.

It deliberately does **not** publish formal blobs, write ``attachment`` rows,
touch review state, or run the B5 GC/ORP worker.  Physical staging operations
are outside any database transaction; the caller owns DB commit/rollback.

Frozen contracts:
``docs/plans/V2-A1-04-Batch-B/attachment-lifecycle.md`` §3,
``active-review-integration.md`` §3, and
``storage-and-lock-contract.md`` §1.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import logging
import os
import re
import stat
import threading
import unicodedata
import uuid
import zipfile
import zlib
from collections.abc import Callable, Collection, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    ValidationError,
    field_validator,
    model_validator,
)
from sqlalchemy import select

from app.core.config import DEFAULT_ATTACHMENT_MIME_ALLOWLIST
from app.models import ReviewRequestORM
from app.services.attachment_storage import (
    ATTACHMENT_STORAGE_CROSS_VOLUME,
    ATTACHMENT_STORAGE_UNAVAILABLE,
    ATTACHMENT_WRITE_FAILED,
    AttachmentStorageError,
    StorageLayout,
    StorageRootError,
    ensure_runtime,
    is_valid_storage_key,
    sha256_bytes,
    verify_blob,
)
from app.services.attachment_validation import ATTACHMENT_EMPTY
from app.services.file_write import write_all
from knowledge_core.markdown.import_report import IMPORT_ENVELOPE_KEY, ImportEnvelope

__all__ = [
    "ATTACHMENT_COUNT_EXCEEDED",
    "ATTACHMENT_EMPTY",
    "ATTACHMENT_MANIFEST_CORRUPTED",
    "ATTACHMENT_MANIFEST_DUPLICATE",
    "ATTACHMENT_MANIFEST_INVALID",
    "ATTACHMENT_ONLY_IMPORT_UNSUPPORTED",
    "ATTACHMENT_STAGING_INVALID",
    "ATTACHMENT_STAGING_MISSING",
    "ATTACHMENT_TOTAL_TOO_LARGE",
    "AttachmentManifestItem",
    "AttachmentStagingError",
    "AttachmentStagingService",
    "ParsedImportZip",
    "StagedAttachmentSet",
    "StagingLease",
    "SweepDecision",
    "ZipAttachmentEntry",
    "ZipDocumentEntry",
    "coerce_manifest_items",
    "logical_manifest_set",
    "manifest_digest",
    "parse_import_zip",
]

logger = logging.getLogger(__name__)

ATTACHMENT_MANIFEST_INVALID = "ATTACHMENT_MANIFEST_INVALID"
ATTACHMENT_MANIFEST_CORRUPTED = "ATTACHMENT_MANIFEST_CORRUPTED"
ATTACHMENT_MANIFEST_DUPLICATE = "ATTACHMENT_MANIFEST_DUPLICATE"
ATTACHMENT_STAGING_INVALID = "ATTACHMENT_STAGING_INVALID"
ATTACHMENT_STAGING_MISSING = "ATTACHMENT_STAGING_MISSING"
ATTACHMENT_COUNT_EXCEEDED = "ATTACHMENT_COUNT_EXCEEDED"
ATTACHMENT_TOTAL_TOO_LARGE = "ATTACHMENT_TOTAL_TOO_LARGE"
ATTACHMENT_TOO_LARGE = "ATTACHMENT_TOO_LARGE"
ATTACHMENT_MIME_UNSUPPORTED = "ATTACHMENT_MIME_UNSUPPORTED"
ATTACHMENT_CONTENT_MISMATCH = "ATTACHMENT_CONTENT_MISMATCH"
ATTACHMENT_IMPORT_UNSUPPORTED = "ATTACHMENT_IMPORT_UNSUPPORTED"
ATTACHMENT_ONLY_IMPORT_UNSUPPORTED = "ATTACHMENT_ONLY_IMPORT_UNSUPPORTED"
IMPORT_ARCHIVE_INVALID = "IMPORT_ARCHIVE_INVALID"

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENT_COUNT = 100
MAX_TOTAL_BYTES = 100 * 1024 * 1024
STAGING_GRACE_SECONDS = 86400
MAX_ZIP_ENTRIES = 1000

_BLOB_RE = re.compile(r"^blobs/[0-9]{6}\.bin$")
_KEY_RE = re.compile(r"^[0-9a-f]{64}$")
_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_CREATING = ".creating"
_ACTIVITY = ".activity"
_COMPLETE = ".complete"
_BLOBS = "blobs"
_CHUNK_SIZE = 1024 * 1024

_TEXT_MIMES = frozenset({"text/plain", "text/markdown", "text/csv"})
_BINARY_SIGNATURES = (
    ("image/png", (b"\x89PNG\r\n\x1a\n",)),
    ("image/jpeg", (b"\xff\xd8\xff",)),
    ("image/gif", (b"GIF87a", b"GIF89a")),
    ("application/pdf", (b"%PDF-",)),
)
_EXTENSION_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".csv": "text/csv",
    ".svg": "image/svg+xml",
}
_ERROR_STATUS = {
    ATTACHMENT_EMPTY: 400,
    "ATTACHMENT_BLOB_MISSING": 503,
    "ATTACHMENT_BLOB_CORRUPTED": 503,
    ATTACHMENT_MANIFEST_INVALID: 422,
    ATTACHMENT_MANIFEST_CORRUPTED: 409,
    ATTACHMENT_MANIFEST_DUPLICATE: 422,
    ATTACHMENT_STAGING_INVALID: 409,
    ATTACHMENT_STAGING_MISSING: 409,
    ATTACHMENT_COUNT_EXCEEDED: 413,
    ATTACHMENT_TOTAL_TOO_LARGE: 413,
    ATTACHMENT_TOO_LARGE: 413,
    ATTACHMENT_MIME_UNSUPPORTED: 415,
    ATTACHMENT_CONTENT_MISMATCH: 415,
    ATTACHMENT_IMPORT_UNSUPPORTED: 400,
    ATTACHMENT_ONLY_IMPORT_UNSUPPORTED: 400,
    IMPORT_ARCHIVE_INVALID: 400,
    "SOURCE_HAS_PENDING_IMPORT": 409,
    ATTACHMENT_STORAGE_UNAVAILABLE: 503,
    ATTACHMENT_STORAGE_CROSS_VOLUME: 503,
    ATTACHMENT_WRITE_FAILED: 503,
}


class AttachmentStagingError(RuntimeError):
    """Staging/manifest rejection carrying only a frozen stable code."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.status_code = _ERROR_STATUS.get(code, 400)
        super().__init__(f"{code}: {message}" if message else code)


def _staging_error(code: str, message: str = "") -> AttachmentStagingError:
    return AttachmentStagingError(code, message)


def _default_directory_sync(path: Path) -> None:
    """Persist directory entries where the platform supports it.

    POSIX requires an explicit fsync of the parent directory after creating,
    renaming or unlinking entries.  Windows has no directory-fsync equivalent;
    this helper is intentionally a no-op there and the residual power-loss
    boundary is recorded in the B3-T01 acceptance docs rather than claimed as
    durable.
    """
    if os.name == "nt":
        return
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        raise _staging_error(
            ATTACHMENT_WRITE_FAILED, f"directory sync failed ({exc.errno})"
        ) from exc


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed.astimezone(UTC)


def _is_link_info(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & 0x400
    )


def validate_staging_id(value: str | uuid.UUID) -> uuid.UUID:
    text = str(value)
    if not _UUID4_RE.fullmatch(text):
        raise _staging_error(ATTACHMENT_STAGING_INVALID, "invalid staging id")
    parsed = uuid.UUID(text)
    if parsed.version != 4 or str(parsed) != text:
        raise _staging_error(ATTACHMENT_STAGING_INVALID, "invalid staging id")
    return parsed


class AttachmentManifestItem(BaseModel):
    """Frozen manifest element stored in ``__a1_import.attachments``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: StrictInt
    staging_id: StrictStr
    ordinal: StrictInt = Field(ge=1, le=MAX_ATTACHMENT_COUNT)
    blob: StrictStr
    filename: StrictStr
    mime: StrictStr
    size: StrictInt = Field(ge=1, le=MAX_FILE_BYTES)
    storage_key: StrictStr

    @field_validator("schema_version")
    @classmethod
    def _version(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported manifest schema version")
        return value

    @field_validator("staging_id")
    @classmethod
    def _staging_id(cls, value: str) -> str:
        if not _UUID4_RE.fullmatch(value):
            raise ValueError("invalid staging id")
        parsed = uuid.UUID(value)
        if parsed.version != 4 or str(parsed) != value:
            raise ValueError("invalid staging id")
        return value

    @field_validator("blob")
    @classmethod
    def _blob(cls, value: str) -> str:
        if not _BLOB_RE.fullmatch(value):
            raise ValueError("invalid blob path")
        return value

    @field_validator("filename")
    @classmethod
    def _filename(cls, value: str) -> str:
        if not 1 <= len(value) <= 500:
            raise ValueError("invalid filename length")
        if ".." in value or any(char in value for char in "/\\:"):
            raise ValueError("unsafe filename")
        for char in value:
            if char == "\x7f" or ord(char) < 32:
                raise ValueError("control character in filename")
            if unicodedata.category(char) in {"Cc", "Cs"}:
                raise ValueError("control character in filename")
        return value

    @field_validator("mime")
    @classmethod
    def _mime(cls, value: str) -> str:
        if value != value.strip().lower() or ";" in value:
            raise ValueError("mime must be a lowercase bare type")
        if value == "image/svg+xml" or value not in DEFAULT_ATTACHMENT_MIME_ALLOWLIST:
            raise ValueError("unsupported mime")
        return value

    @field_validator("storage_key")
    @classmethod
    def _storage_key(cls, value: str) -> str:
        if not _KEY_RE.fullmatch(value):
            raise ValueError("invalid storage key")
        return value

    @model_validator(mode="after")
    def _blob_matches_ordinal(self) -> AttachmentManifestItem:
        expected = f"{_BLOBS}/{self.ordinal:06d}.bin"
        if self.blob != expected:
            raise ValueError("blob must be derived from ordinal")
        return self


class _CompleteMarker(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: StrictInt
    staging_id: StrictStr
    completed_at: StrictStr
    file_count: StrictInt = Field(ge=1)
    total_bytes: StrictInt = Field(ge=1)

    @field_validator("schema_version")
    @classmethod
    def _version(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported complete marker")
        return value

    @field_validator("staging_id")
    @classmethod
    def _staging_id(cls, value: str) -> str:
        if not _UUID4_RE.fullmatch(value):
            raise ValueError("invalid staging id")
        parsed = uuid.UUID(value)
        if parsed.version != 4 or str(parsed) != value:
            raise ValueError("invalid staging id")
        return value

    @field_validator("completed_at")
    @classmethod
    def _completed_at(cls, value: str) -> str:
        _parse_iso(value)
        return value


def coerce_manifest_items(
    manifest: Sequence[AttachmentManifestItem | dict[str, Any]],
    *,
    create: bool = False,
    mime_allowlist: Collection[str] = DEFAULT_ATTACHMENT_MIME_ALLOWLIST,
) -> tuple[AttachmentManifestItem, ...]:
    """Validate manifest structure, uniqueness and aggregate limits.

    ``create=True`` maps schema failures to the frozen 422 code used while
    creating staging; otherwise approve-time validation maps them to the
    frozen 409 manifest-corrupted code.
    """
    structure_code = (
        ATTACHMENT_MANIFEST_INVALID if create else ATTACHMENT_MANIFEST_CORRUPTED
    )
    if not isinstance(manifest, Sequence) or isinstance(manifest, (str, bytes)):
        raise _staging_error(structure_code, "manifest must be a sequence")
    if not manifest:
        raise _staging_error(structure_code, "empty manifest")

    items: list[AttachmentManifestItem] = []
    for entry in manifest:
        if isinstance(entry, AttachmentManifestItem):
            items.append(entry)
            continue
        if not isinstance(entry, dict):
            raise _staging_error(structure_code, "manifest element must be an object")
        try:
            items.append(AttachmentManifestItem.model_validate(entry))
        except ValidationError as exc:
            raise _staging_error(structure_code, "invalid manifest element") from exc

    staging_ids = {item.staging_id for item in items}
    if len(staging_ids) != 1:
        raise _staging_error(structure_code, "mixed staging ids")
    ordinals = [item.ordinal for item in items]
    if len(ordinals) != len(set(ordinals)):
        raise _staging_error(structure_code, "duplicate ordinal")
    keys = [item.storage_key for item in items]
    if len(keys) != len(set(keys)):
        raise _staging_error(ATTACHMENT_MANIFEST_DUPLICATE)
    if any(item.mime not in mime_allowlist for item in items):
        raise _staging_error(ATTACHMENT_MIME_UNSUPPORTED)
    if len(items) > MAX_ATTACHMENT_COUNT:
        raise _staging_error(ATTACHMENT_COUNT_EXCEEDED)
    if sum(item.size for item in items) > MAX_TOTAL_BYTES:
        raise _staging_error(ATTACHMENT_TOTAL_TOO_LARGE)
    return tuple(sorted(items, key=lambda item: item.ordinal))


def logical_manifest_set(
    items: Sequence[AttachmentManifestItem | dict[str, Any]],
) -> tuple[tuple[str, str, str, int], ...]:
    """Order-insensitive logical attachment set used for pending comparison."""
    normalized: list[tuple[str, str, str, int]] = []
    for item in items:
        if isinstance(item, AttachmentManifestItem):
            normalized.append(
                (item.storage_key, item.filename, item.mime, int(item.size))
            )
        elif isinstance(item, dict):
            try:
                normalized.append(
                    (
                        str(item["storage_key"]),
                        str(item["filename"]),
                        str(item["mime"]),
                        int(item["size"]),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise _staging_error(
                    ATTACHMENT_MANIFEST_CORRUPTED, "invalid manifest element"
                ) from exc
        else:
            raise _staging_error(
                ATTACHMENT_MANIFEST_CORRUPTED, "invalid manifest element"
            )
    return tuple(sorted(normalized))


def manifest_digest(
    items: Sequence[AttachmentManifestItem | dict[str, Any]],
) -> str:
    body = [
        item.model_dump(mode="json")
        if isinstance(item, AttachmentManifestItem)
        else dict(item)
        for item in items
    ]
    payload = json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class ZipDocumentEntry:
    path: str
    filename: str
    data: bytes


@dataclass(frozen=True)
class ZipAttachmentEntry:
    path: str
    filename: str
    mime: str
    data: bytes
    storage_key: str


@dataclass(frozen=True)
class ParsedImportZip:
    documents: tuple[ZipDocumentEntry, ...]
    attachments: tuple[ZipAttachmentEntry, ...]
    manifest: dict[str, Any] | None

    @property
    def has_attachments(self) -> bool:
        return bool(self.attachments)

    @property
    def attachment_owner(self) -> str | None:
        if len(self.documents) == 1:
            return self.documents[0].path
        return None

    @property
    def logical_set(self) -> tuple[tuple[str, str, str, int], ...]:
        return tuple(
            sorted(
                (entry.storage_key, entry.filename, entry.mime, len(entry.data))
                for entry in self.attachments
            )
        )


@dataclass(frozen=True)
class StagedAttachmentSet:
    staging_id: uuid.UUID
    directory: Path
    manifest: tuple[AttachmentManifestItem, ...]
    completed_at: datetime
    activity_at: datetime

    @property
    def staging_id_text(self) -> str:
        return str(self.staging_id)

    @property
    def manifest_dicts(self) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in self.manifest]

    @property
    def logical_set(self) -> tuple[tuple[str, str, str, int], ...]:
        return logical_manifest_set(self.manifest)


@dataclass
class StagingLease:
    """Lifetime handle for a staging directory created under ``stage_from_zip``.

    ``stage_from_zip`` keeps the per-``staging_id`` guard for the whole
    ``with`` block.  The owning caller must:

    * set ``committed`` after the database commit that references the staging
      succeeds (the directory is then retained for pending review);
    * set ``keep_for_orp`` when a commit result is ambiguous so the directory
      is preserved for the orphan-recovery path;
    * set ``retain`` when the caller intentionally owns the directory beyond
      the block (``create_from_zip`` compatibility helper).

    If none of the flags is set when the block exits, the staging created in
    this block is removed while the guard is still held.
    """

    staging_id: uuid.UUID
    directory: Path
    staged: StagedAttachmentSet | None = None
    committed: bool = False
    keep_for_orp: bool = False
    retain: bool = False
    discarded: bool = False


@dataclass(frozen=True)
class SweepDecision:
    candidate: bool
    reason: str
    activity_at: datetime | None = None

    def __bool__(self) -> bool:
        return self.candidate


def _validate_content(data: bytes, mime: str) -> None:
    header = data[:16]
    detected: str | None = None
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        detected = "image/webp"
    else:
        for candidate, signatures in _BINARY_SIGNATURES:
            if header.startswith(signatures):
                detected = candidate
                break
    if mime in _TEXT_MIMES:
        if detected is not None or b"\x00" in data:
            raise _staging_error(ATTACHMENT_CONTENT_MISMATCH)
        try:
            data.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise _staging_error(ATTACHMENT_CONTENT_MISMATCH) from None
        return
    if detected != mime:
        raise _staging_error(ATTACHMENT_CONTENT_MISMATCH)


def _infer_mime(filename: str) -> str:
    suffix = PurePosixPath(filename).suffix.lower()
    mime = _EXTENSION_MIME.get(suffix)
    if mime is None:
        raise _staging_error(ATTACHMENT_MIME_UNSUPPORTED)
    if mime not in DEFAULT_ATTACHMENT_MIME_ALLOWLIST:
        raise _staging_error(ATTACHMENT_MIME_UNSUPPORTED)
    return mime


def _validate_zip_path(name: str) -> str:
    if not isinstance(name, str) or not name:
        raise _staging_error(IMPORT_ARCHIVE_INVALID, "empty zip path")
    if len(name) > 4096:
        raise _staging_error(IMPORT_ARCHIVE_INVALID, "zip path too long")
    if "\x00" in name or "\\" in name:
        raise _staging_error(IMPORT_ARCHIVE_INVALID, "non-canonical zip path")
    if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        raise _staging_error(IMPORT_ARCHIVE_INVALID, "absolute zip path")
    stripped = name[:-1] if name.endswith("/") else name
    if not stripped:
        raise _staging_error(IMPORT_ARCHIVE_INVALID, "empty zip path")
    parts = stripped.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise _staging_error(IMPORT_ARCHIVE_INVALID, "unsafe zip path")
    for part in parts:
        if ":" in part:
            raise _staging_error(IMPORT_ARCHIVE_INVALID, "ADS in zip path")
        for char in part:
            if char == "\x7f" or ord(char) < 32:
                raise _staging_error(IMPORT_ARCHIVE_INVALID, "control in zip path")
            if unicodedata.category(char) in {"Cc", "Cs"}:
                raise _staging_error(IMPORT_ARCHIVE_INVALID, "control in zip path")
    return stripped


def _validate_zip_original_name(info: zipfile.ZipInfo) -> None:
    """Reject NUL bytes that ``zipfile`` would hide by truncating ``filename``."""
    original = getattr(info, "orig_filename", None)
    if isinstance(original, str) and "\x00" in original:
        raise _staging_error(IMPORT_ARCHIVE_INVALID, "NUL in zip path")


def _check_zip_entry_metadata(
    info: zipfile.ZipInfo, *, max_total_bytes: int = MAX_TOTAL_BYTES
) -> None:
    mode = (info.external_attr >> 16) & 0xFFFF
    if stat.S_ISLNK(mode):
        raise _staging_error(IMPORT_ARCHIVE_INVALID, "symlink in zip")
    if info.flag_bits & 0x1:
        raise _staging_error(IMPORT_ARCHIVE_INVALID, "encrypted zip entry")
    if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        raise _staging_error(IMPORT_ARCHIVE_INVALID, "unsupported compression")
    if info.file_size < 0 or info.compress_size < 0:
        raise _staging_error(IMPORT_ARCHIVE_INVALID, "invalid zip size")
    if info.file_size > max_total_bytes or info.compress_size > max_total_bytes:
        raise _staging_error(IMPORT_ARCHIVE_INVALID, "zip entry exceeds total limit")
    if (
        info.file_size > 1024 * 1024
        and info.compress_size > 0
        and info.file_size / info.compress_size > 1000
    ):
        raise _staging_error(IMPORT_ARCHIVE_INVALID, "suspicious compression ratio")


def _read_bounded(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    *,
    limit: int,
) -> bytes:
    if info.file_size > limit:
        raise _staging_error(ATTACHMENT_TOO_LARGE)
    output = bytearray()
    try:
        with archive.open(info) as handle:
            while True:
                remaining = limit - len(output)
                if remaining <= 0:
                    extra = handle.read(1)
                    if extra:
                        raise _staging_error(ATTACHMENT_TOO_LARGE)
                    break
                chunk = handle.read(min(_CHUNK_SIZE, remaining))
                if not chunk:
                    break
                output.extend(chunk)
    except AttachmentStagingError:
        raise
    except (
        zipfile.BadZipFile,
        RuntimeError,
        OSError,
        EOFError,
        zlib.error,
        ValueError,
    ) as exc:
        raise _staging_error(IMPORT_ARCHIVE_INVALID, "zip read failed") from exc
    if len(output) != info.file_size:
        raise _staging_error(IMPORT_ARCHIVE_INVALID, "zip size mismatch")
    return bytes(output)


def parse_import_zip(
    payload: bytes | bytearray | memoryview,
    *,
    max_file_bytes: int = MAX_FILE_BYTES,
    max_attachment_count: int = MAX_ATTACHMENT_COUNT,
    max_total_bytes: int = MAX_TOTAL_BYTES,
) -> ParsedImportZip:
    """Parse a ZIP after validating every path; read only bounded selections."""
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise _staging_error(IMPORT_ARCHIVE_INVALID, "zip payload must be bytes")
    raw = bytes(payload)
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except (zipfile.BadZipFile, OSError, ValueError) as exc:
        raise _staging_error(IMPORT_ARCHIVE_INVALID, "invalid zip") from exc

    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ZIP_ENTRIES:
            raise _staging_error(IMPORT_ARCHIVE_INVALID, "too many zip entries")
        validated: list[tuple[zipfile.ZipInfo, str]] = []
        seen_exact: set[str] = set()
        seen_normalized: set[str] = set()
        for info in infos:
            _validate_zip_original_name(info)
            path = _validate_zip_path(info.filename)
            _check_zip_entry_metadata(info, max_total_bytes=max_total_bytes)
            normalized = unicodedata.normalize("NFC", path).casefold()
            if path in seen_exact or normalized in seen_normalized:
                raise _staging_error(IMPORT_ARCHIVE_INVALID, "duplicate zip path")
            seen_exact.add(path)
            seen_normalized.add(normalized)
            validated.append((info, path))
        # Every entry, selected or not, counts against the compressed archive
        # budget.  Unselected entries are never read, but they must not let a
        # caller smuggle an oversized packed stream past the parser.
        if sum(info.compress_size for info, _ in validated) > max_total_bytes:
            raise _staging_error(IMPORT_ARCHIVE_INVALID, "compressed zip too large")

        document_infos: list[tuple[zipfile.ZipInfo, str]] = []
        attachment_infos: list[tuple[zipfile.ZipInfo, str]] = []
        manifest_info: zipfile.ZipInfo | None = None
        for info, path in validated:
            if info.is_dir():
                continue
            if path == "manifest.json":
                manifest_info = info
                continue
            if path.startswith("attachments/"):
                if path.count("/") >= 1 and path.split("/", 1)[1]:
                    attachment_infos.append((info, path))
                continue
            if path.lower().endswith((".md", ".markdown")):
                document_infos.append((info, path))

        if attachment_infos:
            if len(document_infos) > 1:
                raise _staging_error(
                    ATTACHMENT_IMPORT_UNSUPPORTED, "ambiguous attachment ownership"
                )
            if len(attachment_infos) > max_attachment_count:
                raise _staging_error(ATTACHMENT_COUNT_EXCEEDED)
            for info, _ in attachment_infos:
                if info.file_size == 0:
                    # Metadata-stage rejection: no read, no staging, no DB row.
                    raise _staging_error(ATTACHMENT_EMPTY)
                if info.file_size > max_file_bytes:
                    raise _staging_error(ATTACHMENT_TOO_LARGE)
            if sum(info.file_size for info, _ in attachment_infos) > max_total_bytes:
                raise _staging_error(ATTACHMENT_TOTAL_TOO_LARGE)

        selected = list(attachment_infos) + list(document_infos)
        budgeted = list(selected)
        if manifest_info is not None:
            budgeted.append((manifest_info, "manifest.json"))
        if sum(info.file_size for info, _ in budgeted) > max_total_bytes:
            raise _staging_error(ATTACHMENT_TOTAL_TOO_LARGE)
        if sum(info.compress_size for info, _ in budgeted) > max_total_bytes:
            raise _staging_error(IMPORT_ARCHIVE_INVALID, "compressed zip too large")

        manifest: dict[str, Any] | None = None
        if manifest_info is not None:
            manifest_raw = _read_bounded(archive, manifest_info, limit=max_total_bytes)
            try:
                loaded = json.loads(manifest_raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise _staging_error(IMPORT_ARCHIVE_INVALID, "invalid manifest.json") from exc
            if not isinstance(loaded, dict):
                raise _staging_error(IMPORT_ARCHIVE_INVALID, "manifest.json not object")
            manifest = loaded

        documents: list[ZipDocumentEntry] = []
        for info, path in document_infos:
            data = _read_bounded(archive, info, limit=max_total_bytes)
            documents.append(
                ZipDocumentEntry(
                    path=path,
                    filename=PurePosixPath(path).name,
                    data=data,
                )
            )

        attachments: list[ZipAttachmentEntry] = []
        if attachment_infos:
            total = 0
            for info, path in sorted(attachment_infos, key=lambda pair: pair[1]):
                data = _read_bounded(archive, info, limit=max_file_bytes)
                total += len(data)
                if total > max_total_bytes:
                    raise _staging_error(ATTACHMENT_TOTAL_TOO_LARGE)
                filename = PurePosixPath(path).name
                if not 1 <= len(filename) <= 500 or ".." in filename:
                    raise _staging_error(ATTACHMENT_MANIFEST_INVALID, "invalid filename")
                mime = _infer_mime(filename)
                _validate_content(data, mime)
                attachments.append(
                    ZipAttachmentEntry(
                        path=path,
                        filename=filename,
                        mime=mime,
                        data=data,
                        storage_key=sha256_bytes(data),
                    )
                )
            keys = [entry.storage_key for entry in attachments]
            if len(keys) != len(set(keys)):
                raise _staging_error(ATTACHMENT_MANIFEST_DUPLICATE)

        return ParsedImportZip(
            documents=tuple(documents),
            attachments=tuple(attachments),
            manifest=manifest,
        )


class AttachmentStagingService:
    """Create/validate/discard import staging without touching formal refs."""

    def __init__(
        self,
        layout: StorageLayout,
        *,
        max_file_bytes: int = MAX_FILE_BYTES,
        max_attachment_count: int = MAX_ATTACHMENT_COUNT,
        max_total_bytes: int = MAX_TOTAL_BYTES,
        mime_allowlist: Collection[str] = DEFAULT_ATTACHMENT_MIME_ALLOWLIST,
        staging_grace_seconds: int = STAGING_GRACE_SECONDS,
        session_factory: Callable[[], Any] | None = None,
        now: Callable[[], datetime] | None = None,
        directory_sync: Callable[[Path], None] | None = None,
    ) -> None:
        self._layout = layout
        self._max_file_bytes = min(int(max_file_bytes), MAX_FILE_BYTES)
        self._max_count = min(int(max_attachment_count), MAX_ATTACHMENT_COUNT)
        self._max_total = min(int(max_total_bytes), MAX_TOTAL_BYTES)
        self._mime_allowlist = frozenset(mime_allowlist)
        self._grace = timedelta(seconds=max(0, int(staging_grace_seconds)))
        self._session_factory = session_factory
        self._now = now or (lambda: datetime.now(UTC))
        self._directory_sync = directory_sync or _default_directory_sync
        self._guard = threading.Lock()
        self._guards: dict[str, threading.Lock] = {}
        self._guard_users: dict[str, int] = {}

    @property
    def layout(self) -> StorageLayout:
        return self._layout

    @property
    def staging_root(self) -> Path:
        return Path(self._layout.staging_root)

    @contextmanager
    def staging_guard(
        self, staging_id: str | uuid.UUID | Path, *, wait_seconds: float = 10.0,
    ) -> Iterator[None]:
        sid = str(self._coerce_staging_id(staging_id))
        with self._guard:
            lock = self._guards.setdefault(sid, threading.Lock())
            self._guard_users[sid] = self._guard_users.get(sid, 0) + 1
        acquired = False
        try:
            acquired = lock.acquire(timeout=wait_seconds)
            if not acquired:
                raise _staging_error(ATTACHMENT_STAGING_INVALID, "staging guard timeout")
            yield
        finally:
            if acquired:
                lock.release()
            with self._guard:
                self._guard_users[sid] -= 1
                if self._guard_users[sid] == 0:
                    del self._guard_users[sid]
                    del self._guards[sid]

    # ------------------------------------------------------------------ zip
    def inspect_zip(self, payload: bytes | bytearray | memoryview) -> ParsedImportZip:
        return parse_import_zip(
            payload,
            max_file_bytes=self._max_file_bytes,
            max_attachment_count=self._max_count,
            max_total_bytes=self._max_total,
        )

    def create_from_zip(
        self,
        source: bytes | bytearray | memoryview | ParsedImportZip,
        *,
        staging_id: uuid.UUID | str | None = None,
        document_path: str | None = None,
    ) -> StagedAttachmentSet:
        """Create a completed staging set and hand its lifetime to the caller.

        This is a convenience wrapper.  The import path that commits a pending
        review must use :meth:`stage_from_zip` so that the guard spans staging
        creation, review creation and the database commit.
        """
        with self.stage_from_zip(
            source, staging_id=staging_id, document_path=document_path
        ) as lease:
            lease.retain = True
            if lease.staged is None:  # pragma: no cover - defensive
                raise _staging_error(ATTACHMENT_WRITE_FAILED, "staging not created")
            return lease.staged

    @contextmanager
    def stage_from_zip(
        self,
        source: bytes | bytearray | memoryview | ParsedImportZip,
        *,
        staging_id: uuid.UUID | str | None = None,
        document_path: str | None = None,
    ) -> Iterator[StagingLease]:
        """Create staging and hold its guard for the caller's whole block.

        The caller must commit the database write that references this staging
        inside the block.  On a successful commit set ``lease.committed``; on
        an ambiguous commit set ``lease.keep_for_orp``.  If neither is set the
        directory is removed while the guard is still held, so a failed
        pre-commit path never leaves a staging behind for a review that was
        never created.
        """
        parsed = self._prepare_parsed(source, document_path)
        self._ensure_runtime()
        sid = validate_staging_id(staging_id) if staging_id is not None else uuid.uuid4()
        staging_dir = self._staging_dir(sid)
        with self.staging_guard(sid):
            if staging_dir.exists() or staging_dir.is_symlink():
                raise _staging_error(ATTACHMENT_WRITE_FAILED, "staging id already exists")
            lease = StagingLease(staging_id=sid, directory=staging_dir)
            try:
                lease.staged = self._create_locked(staging_dir, sid, parsed)
            except AttachmentStagingError:
                lease.discarded = self._cleanup_incomplete(staging_dir)
                raise
            except (OSError, StorageRootError) as exc:
                lease.discarded = self._cleanup_incomplete(staging_dir)
                raise _staging_error(ATTACHMENT_WRITE_FAILED) from exc
            except Exception:
                lease.discarded = self._cleanup_incomplete(staging_dir)
                raise
            try:
                yield lease
            finally:
                if not (lease.committed or lease.keep_for_orp or lease.retain):
                    lease.discarded = self._cleanup_incomplete(staging_dir)

    def _prepare_parsed(
        self,
        source: bytes | bytearray | memoryview | ParsedImportZip,
        document_path: str | None,
    ) -> ParsedImportZip:
        parsed = source if isinstance(source, ParsedImportZip) else self.inspect_zip(source)
        if not parsed.attachments:
            raise _staging_error(ATTACHMENT_IMPORT_UNSUPPORTED, "no attachments")
        if len(parsed.documents) != 1:
            raise _staging_error(
                ATTACHMENT_IMPORT_UNSUPPORTED, "attachment owner is not unique"
            )
        if document_path is not None and parsed.documents[0].path != document_path:
            raise _staging_error(
                ATTACHMENT_IMPORT_UNSUPPORTED, "attachment owner mismatch"
            )
        keys = [entry.storage_key for entry in parsed.attachments]
        if len(keys) != len(set(keys)):
            raise _staging_error(ATTACHMENT_MANIFEST_DUPLICATE)
        if len(parsed.attachments) > self._max_count:
            raise _staging_error(ATTACHMENT_COUNT_EXCEEDED)
        total = sum(len(entry.data) for entry in parsed.attachments)
        if total > self._max_total:
            raise _staging_error(ATTACHMENT_TOTAL_TOO_LARGE)
        if any(len(entry.data) > self._max_file_bytes for entry in parsed.attachments):
            raise _staging_error(ATTACHMENT_TOO_LARGE)
        return parsed

    def _sync_directory(self, path: Path) -> None:
        try:
            self._directory_sync(Path(path))
        except AttachmentStagingError:
            raise
        except OSError as exc:
            raise _staging_error(
                ATTACHMENT_WRITE_FAILED, f"directory sync failed ({exc.errno})"
            ) from exc

    def _create_locked(
        self, staging_dir: Path, sid: uuid.UUID, parsed: ParsedImportZip
    ) -> StagedAttachmentSet:
        staging_root = self.staging_root
        root_created = not staging_root.exists()
        staging_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._assert_real_directory(staging_root, root=staging_root)
        if root_created:
            self._sync_directory(staging_root.parent)
        staging_dir.mkdir(mode=0o700, exist_ok=False)
        self._assert_real_directory(staging_dir, root=staging_root)
        self._sync_directory(staging_root)

        self._write_marker(staging_dir / _CREATING, exclusive=True)
        self._sync_directory(staging_dir)
        blobs = staging_dir / _BLOBS
        blobs.mkdir(mode=0o700)
        self._assert_real_directory(blobs, root=staging_root)
        self._sync_directory(staging_dir)

        entries = sorted(parsed.attachments, key=lambda entry: entry.path)
        items: list[AttachmentManifestItem] = []
        for ordinal, entry in enumerate(entries, start=1):
            item = AttachmentManifestItem(
                schema_version=1,
                staging_id=str(sid),
                ordinal=ordinal,
                blob=f"{_BLOBS}/{ordinal:06d}.bin",
                filename=entry.filename,
                mime=entry.mime,
                size=len(entry.data),
                storage_key=entry.storage_key,
            )
            if item.mime not in self._mime_allowlist:
                raise _staging_error(ATTACHMENT_MIME_UNSUPPORTED)
            blob_path = staging_dir / item.blob
            self._write_blob(blob_path, entry.data, staging_root=staging_root)
            self._sync_directory(blobs)
            items.append(item)
            self._write_marker(staging_dir / _ACTIVITY, exclusive=False)
            self._sync_directory(staging_dir)

        manifest = tuple(items)
        total = sum(item.size for item in manifest)
        completed_at = _utc(self._now())
        marker = _CompleteMarker(
            schema_version=1,
            staging_id=str(sid),
            completed_at=_iso(completed_at),
            file_count=len(manifest),
            total_bytes=total,
        )
        self._write_complete(staging_dir / _COMPLETE, marker)
        self._validate_staging(
            sid,
            manifest,
            require_complete=True,
            create=True,
            check_activity=False,
        )
        activity_at = self.staging_activity_at(sid)
        if activity_at is None:
            raise _staging_error(ATTACHMENT_STAGING_INVALID)
        return StagedAttachmentSet(
            staging_id=sid,
            directory=staging_dir,
            manifest=manifest,
            completed_at=completed_at,
            activity_at=activity_at,
        )

    # -------------------------------------------------------------- manifest
    def validate_manifest(
        self,
        staging_id: str | uuid.UUID | Path,
        manifest: Sequence[AttachmentManifestItem | dict[str, Any]],
        *,
        require_complete: bool = True,
        create: bool = False,
    ) -> tuple[AttachmentManifestItem, ...]:
        sid = self._coerce_staging_id(staging_id)
        with self.staging_guard(sid):
            return self.validate_manifest_locked(
                sid,
                manifest,
                require_complete=require_complete,
                create=create,
            )

    def validate_manifest_locked(
        self,
        staging_id: str | uuid.UUID | Path,
        manifest: Sequence[AttachmentManifestItem | dict[str, Any]],
        *,
        require_complete: bool = True,
        create: bool = False,
    ) -> tuple[AttachmentManifestItem, ...]:
        """Validate while the caller already holds this staging guard."""
        sid = self._coerce_staging_id(staging_id)
        items = coerce_manifest_items(
            manifest,
            create=create,
            mime_allowlist=self._mime_allowlist,
        )
        return self._validate_staging(
            sid,
            items,
            require_complete=require_complete,
            create=create,
        )

    def verify_published(self, storage_key: str, size: int) -> None:
        """Verify a formal blob for the already-applied attachment check."""
        if not is_valid_storage_key(storage_key):
            raise _staging_error(ATTACHMENT_STAGING_INVALID)
        try:
            verify_blob(self._layout, storage_key, expected_size=size)
        except AttachmentStorageError as exc:
            raise _staging_error(exc.code) from exc

    # ------------------------------------------------------------- activity
    def staging_activity_at(self, staging_id: str | uuid.UUID | Path) -> datetime | None:
        sid = self._coerce_staging_id(staging_id)
        staging_dir = self._staging_dir(sid)
        if not staging_dir.exists():
            raise _staging_error(ATTACHMENT_STAGING_MISSING)
        self._assert_real_directory(staging_dir, root=self.staging_root)
        return self._activity_at(staging_dir)

    # --------------------------------------------------------------- discard
    def discard_committed(
        self, staging_id: str | uuid.UUID | Path, *, review_id: uuid.UUID | str | None = None
    ) -> bool:
        _ = review_id
        return self._discard(staging_id)

    def discard_rejected(
        self, staging_id: str | uuid.UUID | Path, *, review_id: uuid.UUID | str | None = None
    ) -> bool:
        _ = review_id
        return self._discard(staging_id)

    def sweep_candidate(
        self,
        staging_id: str | uuid.UUID | Path,
        *,
        now: datetime | None = None,
        pending_staging_ids: Collection[str] | None = None,
    ) -> SweepDecision:
        sid = self._coerce_staging_id(staging_id)
        staging_dir = self._staging_dir(sid)
        if not staging_dir.exists():
            return SweepDecision(False, "missing", None)
        try:
            self._assert_real_directory(staging_dir, root=self.staging_root)
        except AttachmentStagingError:
            return SweepDecision(False, "unsafe_path", None)
        with self.staging_guard(sid):
            refs = (
                set(pending_staging_ids)
                if pending_staging_ids is not None
                else self.pending_staging_ids()
            )
            if refs is None:
                return SweepDecision(False, "pending_manifest_malformed", None)
            if str(sid) in refs:
                return SweepDecision(False, "active_pending", None)
            activity = self._activity_at(staging_dir)
            if activity is None:
                # Only a genuinely empty directory may use its own mtime; a
                # non-empty staging always relies on markers/ordinary files.
                try:
                    if any(staging_dir.iterdir()):
                        return SweepDecision(False, "untrusted_activity", None)
                    info = staging_dir.lstat()
                except OSError:
                    return SweepDecision(False, "unreadable", None)
                activity = datetime.fromtimestamp(info.st_mtime, UTC)
                reason = "empty_directory"
            else:
                reason = "activity"
            current = _utc(now or self._now())
            if activity > current:
                return SweepDecision(False, "future_activity", activity)
            if current - activity < self._grace:
                return SweepDecision(False, "grace", activity)
            return SweepDecision(True, reason, activity)

    def pending_staging_ids(self) -> set[str] | None:
        """Return pending staging ids; ``None`` means fail-closed.

        A service without a ``session_factory`` cannot prove that a directory
        is unreferenced.  Returning ``None`` (rather than an empty set) keeps
        both discard and sweep conservative instead of deleting live staging.
        """
        if self._session_factory is None:
            return None
        session = None
        try:
            session = self._session_factory()
            rows = session.scalars(
                select(ReviewRequestORM).where(ReviewRequestORM.status == "pending")
            )
            refs: set[str] = set()
            for row in rows:
                try:
                    payload = json.loads(row.payload or "{}")
                except (TypeError, json.JSONDecodeError):
                    return None
                if not isinstance(payload, dict):
                    return None
                if IMPORT_ENVELOPE_KEY not in payload:
                    continue
                try:
                    envelope = ImportEnvelope.from_review_payload(payload)
                except Exception:
                    return None
                if envelope is None:
                    # An explicit reserved key with a null value is malformed.
                    # Only reviews without the reserved key are ordinary reviews.
                    return None
                if not envelope.attachments:
                    continue
                try:
                    items = coerce_manifest_items(envelope.attachments)
                except AttachmentStagingError:
                    return None
                staging_ids = {item.staging_id for item in items}
                if len(staging_ids) != 1:
                    return None
                refs.update(staging_ids)
            return refs
        except Exception:
            return None
        finally:
            if session is not None:
                session.close()

    # --------------------------------------------------------------- helpers
    def _ensure_runtime(self) -> None:
        try:
            ensure_runtime(self._layout)
        except (AttachmentStorageError, StorageRootError) as exc:
            code = getattr(exc, "code", ATTACHMENT_STORAGE_UNAVAILABLE)
            raise _staging_error(code) from exc
        storage = Path(self._layout.storage_root)
        staging = Path(self._layout.staging_root)
        roots = (storage, staging, Path(self._layout.quarantine_dir))
        try:
            devices = {path.stat().st_dev for path in roots}
        except OSError as exc:
            raise _staging_error(ATTACHMENT_STORAGE_UNAVAILABLE) from exc
        if len(devices) > 1:
            raise _staging_error(ATTACHMENT_STORAGE_CROSS_VOLUME)
        try:
            storage.relative_to(staging)
            overlap = True
        except ValueError:
            overlap = False
        try:
            staging.relative_to(storage)
            overlap = True
        except ValueError:
            pass
        if overlap or storage == staging:
            raise _staging_error(
                ATTACHMENT_STAGING_INVALID, "formal storage and staging overlap"
            )

    def _coerce_staging_id(
        self, value: str | uuid.UUID | Path
    ) -> uuid.UUID:
        if isinstance(value, Path):
            try:
                relative = value.relative_to(self.staging_root)
            except ValueError:
                raise _staging_error(
                    ATTACHMENT_STAGING_INVALID, "staging path outside root"
                ) from None
            if len(relative.parts) != 1:
                raise _staging_error(
                    ATTACHMENT_STAGING_INVALID, "invalid staging path depth"
                )
            return validate_staging_id(relative.name)
        return validate_staging_id(value)

    def _staging_dir(self, sid: uuid.UUID) -> Path:
        return self.staging_root / str(sid)

    def _assert_real_directory(self, path: Path, *, root: Path) -> None:
        try:
            root_info = root.lstat()
        except FileNotFoundError:
            raise _staging_error(ATTACHMENT_STAGING_MISSING) from None
        if _is_link_info(root_info) or not stat.S_ISDIR(root_info.st_mode):
            raise _staging_error(ATTACHMENT_STORAGE_UNAVAILABLE, "unsafe staging root")
        path = Path(path)
        try:
            relative = path.relative_to(root)
        except ValueError:
            raise _staging_error(ATTACHMENT_STAGING_INVALID, "outside staging root") from None
        if ".." in relative.parts:
            raise _staging_error(ATTACHMENT_STAGING_INVALID, "traversal")
        current = root
        try:
            for part in relative.parts:
                current = current / part
                info = current.lstat()
                if _is_link_info(info):
                    raise _staging_error(
                        ATTACHMENT_STAGING_INVALID, "link/reparse in staging path"
                    )
                if not stat.S_ISDIR(info.st_mode):
                    raise _staging_error(
                        ATTACHMENT_STAGING_INVALID, "non-directory in staging path"
                    )
            if current.stat().st_dev != Path(self._layout.storage_root).stat().st_dev:
                raise _staging_error(ATTACHMENT_STORAGE_CROSS_VOLUME)
        except FileNotFoundError:
            raise _staging_error(ATTACHMENT_STAGING_MISSING) from None
        except OSError as exc:
            raise _staging_error(ATTACHMENT_STAGING_INVALID) from exc

    def _write_marker(self, path: Path, *, exclusive: bool) -> None:
        if not exclusive and path.exists():
            try:
                if _is_link_info(path.lstat()):
                    raise _staging_error(
                        ATTACHMENT_STAGING_INVALID, "link/reparse marker"
                    )
            except OSError as exc:
                raise _staging_error(ATTACHMENT_WRITE_FAILED) from exc
        flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_BINARY", 0)
        flags |= os.O_EXCL if exclusive else os.O_TRUNC
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, flags, 0o600)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError as exc:
            raise _staging_error(ATTACHMENT_WRITE_FAILED) from exc

    def _write_blob(self, path: Path, data: bytes, *, staging_root: Path) -> None:
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            fd = os.open(path, flags, 0o600)
            try:
                write_all(fd, memoryview(data))
                os.fsync(fd)
            finally:
                os.close(fd)
            info = path.lstat()
            if _is_link_info(info) or not stat.S_ISREG(info.st_mode):
                raise _staging_error(ATTACHMENT_WRITE_FAILED)
            if info.st_size != len(data):
                raise _staging_error(ATTACHMENT_WRITE_FAILED)
            if info.st_dev != staging_root.stat().st_dev:
                raise _staging_error(ATTACHMENT_STORAGE_CROSS_VOLUME)
        except AttachmentStagingError:
            raise
        except OSError as exc:
            raise _staging_error(ATTACHMENT_WRITE_FAILED) from exc

    def _write_complete(self, path: Path, marker: _CompleteMarker) -> None:
        payload = json.dumps(
            marker.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        temp = path.parent / f".complete.{uuid.uuid4().hex}.tmp"
        try:
            fd = os.open(
                temp,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_BINARY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            try:
                write_all(fd, memoryview(payload))
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(temp, path)
            self._sync_directory(path.parent)
        except OSError as exc:
            with contextlib.suppress(OSError):
                temp.unlink()
            raise _staging_error(ATTACHMENT_WRITE_FAILED) from exc

    def _validate_staging(
        self,
        sid: uuid.UUID,
        items: Sequence[AttachmentManifestItem],
        *,
        require_complete: bool,
        create: bool,
        check_activity: bool = True,
    ) -> tuple[AttachmentManifestItem, ...]:
        if len(items) > self._max_count:
            raise _staging_error(ATTACHMENT_COUNT_EXCEEDED)
        if any(item.size > self._max_file_bytes for item in items):
            raise _staging_error(ATTACHMENT_TOO_LARGE)
        if sum(item.size for item in items) > self._max_total:
            raise _staging_error(ATTACHMENT_TOTAL_TOO_LARGE)
        staging_dir = self._staging_dir(sid)
        if not staging_dir.exists():
            raise _staging_error(ATTACHMENT_STAGING_MISSING)
        self._assert_real_directory(staging_dir, root=self.staging_root)

        complete_path = staging_dir / _COMPLETE
        if require_complete and not complete_path.exists():
            raise _staging_error(ATTACHMENT_STAGING_INVALID, "missing .complete")
        marker: _CompleteMarker | None = None
        if complete_path.exists():
            try:
                info = complete_path.lstat()
                if _is_link_info(info) or not stat.S_ISREG(info.st_mode):
                    raise ValueError("not a regular marker")
                raw = complete_path.read_bytes()
                marker = _CompleteMarker.model_validate_json(raw)
            except (OSError, ValueError, ValidationError) as exc:
                raise _staging_error(
                    ATTACHMENT_STAGING_INVALID, "invalid .complete"
                ) from exc
            if marker.staging_id != str(sid):
                raise _staging_error(ATTACHMENT_STAGING_INVALID, "staging id mismatch")
            if marker.file_count != len(items):
                raise _staging_error(ATTACHMENT_STAGING_INVALID, "file count mismatch")
            if marker.total_bytes != sum(item.size for item in items):
                raise _staging_error(ATTACHMENT_STAGING_INVALID, "total mismatch")

        expected: set[str] = set()
        for item in items:
            if item.staging_id != str(sid):
                raise _staging_error(ATTACHMENT_STAGING_INVALID, "manifest id mismatch")
            expected.add(item.blob)
            blob_path = staging_dir / item.blob
            try:
                if blob_path.parent != staging_dir / _BLOBS:
                    raise ValueError("blob outside blobs/")
                info = blob_path.lstat()
                if _is_link_info(info) or not stat.S_ISREG(info.st_mode):
                    raise ValueError("not a regular blob")
                if info.st_size != item.size:
                    raise ValueError("size mismatch")
                if info.st_dev != Path(self._layout.storage_root).stat().st_dev:
                    raise ValueError("cross volume")
                data = blob_path.read_bytes()
            except FileNotFoundError:
                raise _staging_error(
                    ATTACHMENT_STAGING_INVALID, "missing blob"
                ) from None
            except (OSError, ValueError) as exc:
                raise _staging_error(ATTACHMENT_STAGING_INVALID) from exc
            if sha256_bytes(data) != item.storage_key:
                raise _staging_error(ATTACHMENT_STAGING_INVALID, "hash mismatch")
            if item.mime not in self._mime_allowlist:
                raise _staging_error(ATTACHMENT_MIME_UNSUPPORTED)
            _validate_content(data, item.mime)

        actual = self._regular_relative_files(staging_dir)
        allowed = expected | {_CREATING, _ACTIVITY, _COMPLETE}
        if actual - allowed:
            raise _staging_error(ATTACHMENT_STAGING_INVALID, "unexpected staging file")
        missing = expected - actual
        if missing:
            raise _staging_error(ATTACHMENT_STAGING_INVALID, "missing staging blob")
        directories = self._relative_directories(staging_dir)
        if directories - {_BLOBS}:
            raise _staging_error(
                ATTACHMENT_STAGING_INVALID, "unexpected staging directory"
            )
        if check_activity and _ACTIVITY not in actual:
            raise _staging_error(ATTACHMENT_STAGING_INVALID, "missing .activity")
        return tuple(items)

    def _regular_relative_files(self, staging_dir: Path) -> set[str]:
        found: set[str] = set()
        stack = [staging_dir]
        while stack:
            current = stack.pop()
            try:
                entries = list(os.scandir(current))
            except OSError as exc:
                raise _staging_error(ATTACHMENT_STAGING_INVALID) from exc
            for entry in entries:
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError as exc:
                    raise _staging_error(ATTACHMENT_STAGING_INVALID) from exc
                if _is_link_info(info):
                    raise _staging_error(
                        ATTACHMENT_STAGING_INVALID, "link/reparse in staging"
                    )
                if stat.S_ISDIR(info.st_mode):
                    stack.append(Path(entry.path))
                elif stat.S_ISREG(info.st_mode):
                    found.add(Path(entry.path).relative_to(staging_dir).as_posix())
                else:
                    raise _staging_error(
                        ATTACHMENT_STAGING_INVALID, "unknown staging entry"
                    )
        return found

    def _relative_directories(self, staging_dir: Path) -> set[str]:
        found: set[str] = set()
        stack = [staging_dir]
        while stack:
            current = stack.pop()
            try:
                entries = list(os.scandir(current))
            except OSError as exc:
                raise _staging_error(ATTACHMENT_STAGING_INVALID) from exc
            for entry in entries:
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError as exc:
                    raise _staging_error(ATTACHMENT_STAGING_INVALID) from exc
                if _is_link_info(info):
                    raise _staging_error(
                        ATTACHMENT_STAGING_INVALID, "link/reparse in staging"
                    )
                if stat.S_ISDIR(info.st_mode):
                    path = Path(entry.path)
                    found.add(path.relative_to(staging_dir).as_posix())
                    stack.append(path)
        return found

    def _activity_at(self, staging_dir: Path) -> datetime | None:
        found: list[datetime] = []
        stack = [staging_dir]
        while stack:
            current = stack.pop()
            try:
                entries = list(os.scandir(current))
            except OSError as exc:
                raise _staging_error(ATTACHMENT_STAGING_INVALID) from exc
            for entry in entries:
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError as exc:
                    raise _staging_error(ATTACHMENT_STAGING_INVALID) from exc
                if _is_link_info(info):
                    raise _staging_error(
                        ATTACHMENT_STAGING_INVALID, "link/reparse in staging"
                    )
                if stat.S_ISDIR(info.st_mode):
                    stack.append(Path(entry.path))
                elif stat.S_ISREG(info.st_mode):
                    found.append(datetime.fromtimestamp(info.st_mtime, UTC))
        if not found:
            return None
        return max(found)

    def _cleanup_incomplete(self, staging_dir: Path) -> bool:
        if not staging_dir.exists():
            return True
        complete = staging_dir / _COMPLETE
        with contextlib.suppress(OSError):
            if complete.exists() and not complete.is_symlink():
                complete.unlink()
        with contextlib.suppress(Exception):
            return self._remove_tree(staging_dir)
        return False

    def _discard(self, staging_id: str | uuid.UUID | Path) -> bool:
        sid = self._coerce_staging_id(staging_id)
        with self.staging_guard(sid):
            return self.discard_locked(sid)

    def discard_locked(self, staging_id: str | uuid.UUID | Path) -> bool:
        """Discard under the existing staging guard if no pending owns the directory."""
        sid = self._coerce_staging_id(staging_id)
        staging_dir = self._staging_dir(sid)
        if not staging_dir.exists():
            return False
        try:
            self._assert_real_directory(staging_dir, root=self.staging_root)
        except AttachmentStagingError:
            return False
        refs = self.pending_staging_ids()
        if refs is None or str(sid) in refs:
            return False
        return self._remove_tree(staging_dir)

    def _remove_tree(self, staging_dir: Path) -> bool:
        try:
            self._assert_real_directory(staging_dir, root=self.staging_root)
        except AttachmentStagingError:
            return False

        def remove(current: Path) -> bool:
            try:
                entries = list(os.scandir(current))
            except OSError:
                return False
            for entry in entries:
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError:
                    return False
                if _is_link_info(info):
                    return False
                if stat.S_ISDIR(info.st_mode):
                    if not remove(Path(entry.path)):
                        return False
                elif stat.S_ISREG(info.st_mode):
                    try:
                        os.unlink(entry.path)
                    except OSError:
                        return False
                else:
                    return False
            try:
                os.rmdir(current)
            except OSError:
                return False
            return True

        return remove(staging_dir)
