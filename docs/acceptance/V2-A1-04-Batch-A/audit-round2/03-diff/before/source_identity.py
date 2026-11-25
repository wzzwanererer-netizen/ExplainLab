"""D23 本地文档身份：身份审计、MATERIALIZE/ROTATE Journal 与恢复（Batch A）。

权威规则见冻结设计 §22.2。要点：
- 状态 1/2a/2b/3/4 穷尽互斥；2b 只能由「恰好一条 COMMITTED MATERIALIZE Journal」
  证明，绝不从 DB 字段推断。
- ``identity_audit_digest`` 覆盖全部 ``knowledge_item`` 及每项**全部原始**
  ``ImportOrigin``（不过滤/归一化/去重），每次 DB 写后与恢复分支都从 DB 重算。
- Journal current → archive 同卷原子落位；恢复优先 PREPARED，COMMITTED 只补归档。
- Windows 目录同步为 best-effort，不宣称断电持久。
"""

from __future__ import annotations

import os
import re
import threading
import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.models import ImportOriginORM, KnowledgeItemORM
from app.services.journal_canonical import (
    CanonicalJsonError,
    canonical_dumps,
    canonical_loads,
    sha256_canonical,
)
from app.services.source_instance_id import SourceInstanceIdStore

__all__ = [
    "JOURNAL_CORRUPT",
    "SOURCE_IDENTITY_INCONSISTENT",
    "SOURCE_IDENTITY_ORPHAN",
    "ClassifiedIdentity",
    "JournalStore",
    "MaterializeReport",
    "RotateReport",
    "SourceIdentityError",
    "SourceIdentityService",
    "build_identity_snapshots",
    "item_identity_digest",
]

JOURNAL_CORRUPT = "SOURCE_IDENTITY_JOURNAL_CORRUPT"
SOURCE_IDENTITY_INCONSISTENT = "SOURCE_IDENTITY_INCONSISTENT"
SOURCE_IDENTITY_ORPHAN = "SOURCE_IDENTITY_ORPHAN"
SOURCE_DOCUMENT_UNMATERIALIZED = "SOURCE_DOCUMENT_UNMATERIALIZED"

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_PAYLOAD_RE = re.compile(r"^[0-9a-f]{64}$")
_TOP_FIELDS = {
    "schema_version",
    "operation_id",
    "kind",
    "phase",
    "created_at",
    "updated_at",
    "item_id",
    "source_instance_id",
    "source_document_id",
    "materialization_items",
    "materialization_digest",
    "identity_audit_digest",
    "journal_checksum",
    "old_instance_id",
    "target_instance_id",
}
_ITEM_FIELDS = {
    "item_id",
    "source_instance_id",
    "source_document_id",
    "identity_record_version",
    "item_identity_digest",
}


class SourceIdentityError(RuntimeError):
    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(f"{code}: {message}" if message else code)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _is_uuid_text(value: object, *, version: int | None = None) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        return False
    if str(parsed) != value:
        return False
    return version is None or parsed.version == version


def _has_control(value: str) -> bool:
    return any(ord(char) < 0x20 or ord(char) == 0x7F for char in value)


def _sync_dir(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def item_identity_digest(item: dict[str, Any]) -> str:
    return sha256_canonical(
        {
            "item_id": item["item_id"],
            "source_instance_id": item["source_instance_id"],
            "source_document_id": item["source_document_id"],
            "identity_record_version": item["identity_record_version"],
        }
    )


def materialization_digest(items: list[dict[str, Any]]) -> str:
    ordered = sorted(items, key=lambda item: item["item_id"])
    if len({item["item_id"] for item in ordered}) != len(ordered):
        raise SourceIdentityError(JOURNAL_CORRUPT, "duplicate item_id")
    return sha256_canonical(ordered)


# ---------------------------------------------------------------------------
# 身份审计快照
# ---------------------------------------------------------------------------
@dataclass
class _OriginView:
    row: ImportOriginORM
    origin_id: str
    instance: str | None
    document: str | None
    payload: str | None
    flags: list[str]
    duplicate_group_size: int = 1


def _origin_flags(instance: Any, document: Any, payload: Any) -> list[str]:
    flags: set[str] = set()
    if instance is None or instance == "":
        flags.add("incomplete")
    elif not isinstance(instance, str) or len(instance) > 64 or _has_control(instance):
        flags.add("invalid")
    if document is None or document == "":
        flags.add("incomplete")
    elif not isinstance(document, str) or not _is_uuid_text(document):
        flags.add("invalid")
    if payload is None or payload == "":
        flags.add("incomplete")
    elif not isinstance(payload, str) or not _PAYLOAD_RE.fullmatch(payload):
        flags.add("invalid")
    return sorted(flags)


def _check_orphans(session: Session) -> None:
    item_ids = set(session.scalars(select(KnowledgeItemORM.id)))
    for origin_id, owner in session.execute(
        select(ImportOriginORM.id, ImportOriginORM.item_id)
    ):
        if owner not in item_ids:
            raise SourceIdentityError(
                SOURCE_IDENTITY_ORPHAN, f"origin {origin_id} references missing item"
            )


def _build_origins(rows: list[ImportOriginORM]) -> list[_OriginView]:
    groups: dict[tuple[Any, Any, Any], int] = {}
    for row in rows:
        key = (row.source_instance_id, row.source_document_id, row.source_payload_hash)
        groups[key] = groups.get(key, 0) + 1
    views = []
    for row in rows:
        view = _OriginView(
            row=row,
            origin_id=str(row.id),
            instance=row.source_instance_id,
            document=row.source_document_id,
            payload=row.source_payload_hash,
            flags=_origin_flags(
                row.source_instance_id, row.source_document_id, row.source_payload_hash
            ),
        )
        key = (row.source_instance_id, row.source_document_id, row.source_payload_hash)
        view.duplicate_group_size = groups[key]
        views.append(view)
    views.sort(key=lambda view: view.origin_id)
    return views


def _origin_state(
    views: list[_OriginView], db_instance: Any
) -> tuple[str, tuple[str, str] | None, str | None]:
    """返回 (import_origin_state, 唯一有效身份对, 单记录身份摘要)。"""
    n = len(views)
    if n == 0:
        return "none", None, None
    legal = [view for view in views if not view.flags]
    pairs = {(view.instance, view.document) for view in legal}
    has_duplicate = any(view.duplicate_group_size > 1 for view in views)
    has_conflict = len(pairs) >= 2
    if len(pairs) == 1:
        instance, _document = next(iter(pairs))
        if db_instance is None or db_instance != instance:
            has_conflict = True
    if has_conflict:
        return "conflict", None, None
    if any("invalid" in view.flags for view in views):
        return "invalid", None, None
    if any("incomplete" in view.flags for view in views):
        return "incomplete", None, None
    if has_duplicate:
        return "duplicate", None, None
    if len(pairs) == 1:
        pair = next(iter(pairs))
        if len(legal) != len(views):
            return "invalid", None, None
        digest = None
        if len(legal) == 1 and legal[0].payload:
            digest = sha256_canonical(
                {
                    "source_instance_id": legal[0].instance,
                    "source_document_id": legal[0].document,
                    "source_payload_hash": legal[0].payload,
                }
            )
        return "complete", pair, digest
    # n>0 未命中任何行：实现/数据异常，保守归 invalid，绝不回落 none/complete。
    return "invalid", None, None


def build_identity_snapshots(
    session: Session,
    *,
    materialized: dict[str, tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """构造全库身份快照（在内存中应用 ``materialized`` 预测完成态）。"""
    _check_orphans(session)
    overrides = materialized or {}
    items = list(
        session.scalars(select(KnowledgeItemORM).order_by(KnowledgeItemORM.id))
    )
    origin_rows = list(session.scalars(select(ImportOriginORM)))
    by_item: dict[str, list[ImportOriginORM]] = {}
    for row in origin_rows:
        by_item.setdefault(str(row.item_id), []).append(row)

    snapshots: list[dict[str, Any]] = []
    for item in items:
        item_id = str(item.id)
        db_instance: Any = item.source_instance_id
        if item_id in overrides:
            db_instance = overrides[item_id][0]
        views = _build_origins(by_item.get(item_id, []))
        origin_state, pair, single_digest = _origin_state(views, db_instance)
        if origin_state == "none":
            item_state = "none"
            valid_instance = db_instance
            valid_document = item_id
        elif origin_state == "complete" and pair is not None:
            item_state = "complete"
            valid_instance, valid_document = pair
        else:
            item_state = "incomplete"
            valid_instance = None
            valid_document = None
        snapshot = {
            "item_id": item_id,
            "origin_state": item_state,
            "db_source_instance_id": db_instance,
            "source_instance_id": valid_instance,
            "source_document_id": valid_document,
            "import_origin_count": len(views),
            "import_origin_state": origin_state,
            "incomplete_origin_count": sum(
                1 for view in views if "incomplete" in view.flags
            ),
            "invalid_origin_count": sum(1 for view in views if "invalid" in view.flags),
            "duplicate_origin_count": sum(
                1 for view in views if view.duplicate_group_size > 1
            ),
            "import_origins": [
                {
                    "import_origin_id": view.origin_id,
                    "source_instance_id": view.instance,
                    "source_document_id": view.document,
                    "source_payload_hash": view.payload,
                    "status_flags": list(view.flags),
                    "duplicate_group_size": view.duplicate_group_size,
                }
                for view in views
            ],
            "import_origin_identity_digest": single_digest,
        }
        snapshots.append(snapshot)
    return snapshots


def identity_audit_digest(
    session: Session, *, materialized: dict[str, tuple[str, str]] | None = None
) -> str:
    return sha256_canonical(build_identity_snapshots(session, materialized=materialized))


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------
class JournalStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.current = self.data_dir / "source-identity-journal.json"
        self.archive_dir = self.data_dir / "source-identity-journal.archive"

    # -- 校验 ---------------------------------------------------------------
    @staticmethod
    def validate(record: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(record, dict) or set(record) != _TOP_FIELDS:
            raise SourceIdentityError(JOURNAL_CORRUPT, "top-level fields mismatch")
        if record["schema_version"] != 1:
            raise SourceIdentityError(JOURNAL_CORRUPT, "schema_version")
        if not _is_uuid_text(record["operation_id"], version=4):
            raise SourceIdentityError(JOURNAL_CORRUPT, "operation_id")
        if record["kind"] not in ("MATERIALIZE", "ROTATE"):
            raise SourceIdentityError(JOURNAL_CORRUPT, "kind")
        if record["phase"] not in ("PREPARED", "COMMITTED"):
            raise SourceIdentityError(JOURNAL_CORRUPT, "phase")
        for key in ("materialization_digest", "identity_audit_digest", "journal_checksum"):
            if not isinstance(record[key], str) or not _DIGEST_RE.fullmatch(record[key]):
                raise SourceIdentityError(JOURNAL_CORRUPT, key)
        items = record["materialization_items"]
        if not isinstance(items, list):
            raise SourceIdentityError(JOURNAL_CORRUPT, "materialization_items")
        for item in items:
            if not isinstance(item, dict) or set(item) != _ITEM_FIELDS:
                raise SourceIdentityError(JOURNAL_CORRUPT, "item fields")
            if item["identity_record_version"] != 1:
                raise SourceIdentityError(JOURNAL_CORRUPT, "identity_record_version")
            if not _is_uuid_text(item["item_id"]):
                raise SourceIdentityError(JOURNAL_CORRUPT, "item_id")
            if not _is_uuid_text(item["source_document_id"]):
                raise SourceIdentityError(JOURNAL_CORRUPT, "source_document_id")
            if not isinstance(item["source_instance_id"], str) or not item["source_instance_id"]:
                raise SourceIdentityError(JOURNAL_CORRUPT, "item source_instance_id")
            if not isinstance(item["item_identity_digest"], str) or not _DIGEST_RE.fullmatch(
                item["item_identity_digest"]
            ):
                raise SourceIdentityError(JOURNAL_CORRUPT, "item_identity_digest")
            if item["item_identity_digest"] != item_identity_digest(item):
                raise SourceIdentityError(JOURNAL_CORRUPT, "item digest mismatch")
        try:
            expected_materialization = materialization_digest(items)
        except CanonicalJsonError as exc:
            raise SourceIdentityError(JOURNAL_CORRUPT, "materialization canonical") from exc
        if record["materialization_digest"] != expected_materialization:
            raise SourceIdentityError(JOURNAL_CORRUPT, "materialization digest mismatch")

        kind = record["kind"]
        if kind == "MATERIALIZE":
            if len(items) != 1:
                raise SourceIdentityError(JOURNAL_CORRUPT, "MATERIALIZE item count")
            if not _is_uuid_text(record["item_id"]):
                raise SourceIdentityError(JOURNAL_CORRUPT, "MATERIALIZE item_id")
            if record["item_id"] != items[0]["item_id"]:
                raise SourceIdentityError(JOURNAL_CORRUPT, "MATERIALIZE item mismatch")
            if items[0]["source_document_id"] != items[0]["item_id"]:
                raise SourceIdentityError(JOURNAL_CORRUPT, "local document id")
            if record["source_instance_id"] != items[0]["source_instance_id"]:
                raise SourceIdentityError(JOURNAL_CORRUPT, "MATERIALIZE instance mismatch")
            if record["source_document_id"] != record["item_id"]:
                raise SourceIdentityError(JOURNAL_CORRUPT, "top document mismatch")
            if record["old_instance_id"] is not None or record["target_instance_id"] is not None:
                raise SourceIdentityError(JOURNAL_CORRUPT, "MATERIALIZE rotate fields")
        else:
            if record["item_id"] is not None or record["source_instance_id"] is not None:
                raise SourceIdentityError(JOURNAL_CORRUPT, "ROTATE top fields")
            if record["source_document_id"] is not None:
                raise SourceIdentityError(JOURNAL_CORRUPT, "ROTATE document")
            if not _is_uuid_text(record["old_instance_id"], version=4):
                raise SourceIdentityError(JOURNAL_CORRUPT, "old_instance_id")
            if not _is_uuid_text(record["target_instance_id"], version=4):
                raise SourceIdentityError(JOURNAL_CORRUPT, "target_instance_id")
            if record["old_instance_id"] == record["target_instance_id"]:
                raise SourceIdentityError(JOURNAL_CORRUPT, "rotate same id")
            for item in items:
                if item["source_instance_id"] != record["old_instance_id"]:
                    raise SourceIdentityError(JOURNAL_CORRUPT, "rotate item instance")
        body = {k: v for k, v in record.items() if k != "journal_checksum"}
        try:
            checksum = sha256_canonical(body)
        except CanonicalJsonError as exc:
            raise SourceIdentityError(JOURNAL_CORRUPT, "checksum canonical") from exc
        if checksum != record["journal_checksum"]:
            raise SourceIdentityError(JOURNAL_CORRUPT, "journal checksum mismatch")
        return record

    def read_current(self) -> dict[str, Any] | None:
        if not self.current.exists():
            return None
        try:
            return self.validate(canonical_loads(self.current.read_bytes()))
        except (OSError, CanonicalJsonError) as exc:
            raise SourceIdentityError(JOURNAL_CORRUPT, "current unreadable") from exc

    # -- 写入 ---------------------------------------------------------------
    def write_current(self, record: dict[str, Any]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._atomic_write(self.current, canonical_dumps(record).encode("utf-8"))

    def _atomic_write(self, target: Path, payload: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            try:
                os.write(fd, payload)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(tmp, target)
        finally:
            with suppress(OSError):
                os.unlink(tmp)
        _sync_dir(target.parent)

    # -- 归档 ---------------------------------------------------------------
    def read_archive(self) -> list[dict[str, Any]]:
        if not self.archive_dir.exists():
            return []
        records = []
        for path in sorted(self.archive_dir.glob("*.json")):
            try:
                record = self.validate(canonical_loads(path.read_bytes()))
            except (OSError, CanonicalJsonError) as exc:
                raise SourceIdentityError(JOURNAL_CORRUPT, f"archive {path.name}") from exc
            if record["phase"] != "COMMITTED":
                raise SourceIdentityError(JOURNAL_CORRUPT, "archived non-committed")
            if path.name != f"{record['operation_id']}.json":
                raise SourceIdentityError(JOURNAL_CORRUPT, "archive name mismatch")
            records.append(record)
        return records

    def archive_committed(self, record: dict[str, Any]) -> None:
        if record["phase"] != "COMMITTED":
            raise SourceIdentityError(JOURNAL_CORRUPT, "archive requires COMMITTED")
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        target = self.archive_dir / f"{record['operation_id']}.json"
        payload = canonical_dumps(record).encode("utf-8")
        if target.exists():
            if target.read_bytes() != payload:
                raise SourceIdentityError(JOURNAL_CORRUPT, "archive content conflict")
            return
        tmp = self.archive_dir / f".{target.name}.{uuid.uuid4().hex}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            try:
                os.write(fd, payload)
                os.fsync(fd)
            finally:
                os.close(fd)
            if target.exists():
                if target.read_bytes() != payload:
                    raise SourceIdentityError(JOURNAL_CORRUPT, "archive content conflict")
            else:
                os.replace(tmp, target)
        finally:
            with suppress(OSError):
                os.unlink(tmp)
        _sync_dir(self.archive_dir)

    def remove_current(self) -> None:
        try:
            os.unlink(self.current)
        except FileNotFoundError:
            return
        _sync_dir(self.data_dir)

    def committed_materialize_records(self) -> list[dict[str, Any]]:
        records: dict[str, dict[str, Any]] = {}
        current = self.read_current()
        candidates = self.read_archive() + ([current] if current else [])
        for record in candidates:
            if record["phase"] != "COMMITTED" or record["kind"] != "MATERIALIZE":
                continue
            operation_id = record["operation_id"]
            if operation_id in records and records[operation_id] != record:
                raise SourceIdentityError(JOURNAL_CORRUPT, "operation id conflict")
            records[operation_id] = record
        return list(records.values())


# ---------------------------------------------------------------------------
# 分类与生命周期
# ---------------------------------------------------------------------------
@dataclass
class ClassifiedIdentity:
    item_id: str
    state: str  # "1" | "2a" | "2b" | "3" | "4"
    source_instance_id: str | None
    source_document_id: str | None
    snapshot: dict[str, Any]


@dataclass
class MaterializeReport:
    item_id: str
    operation_id: str
    materialized: bool
    source_instance_id: str


@dataclass
class RotateReport:
    old_instance_id: str
    target_instance_id: str
    operation_id: str
    materialized_items: list[str]


class SourceIdentityService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        data_dir: Path,
        instance_store: SourceInstanceIdStore | None = None,
    ) -> None:
        self._factory = session_factory
        self._data_dir = Path(data_dir)
        self._store = instance_store or SourceInstanceIdStore(self._data_dir)
        self.journal = JournalStore(self._data_dir)
        self._journal_lock = threading.RLock()

    # -- 快照/分类 ----------------------------------------------------------
    def snapshots(self, session: Session) -> list[dict[str, Any]]:
        return build_identity_snapshots(session)

    def audit_digest(self, session: Session) -> str:
        return sha256_canonical(self.snapshots(session))

    def _committed_index(self) -> dict[str, list[dict[str, Any]]]:
        index: dict[str, list[dict[str, Any]]] = {}
        for record in self.journal.committed_materialize_records():
            index.setdefault(record["item_id"], []).append(record)
        return index

    def classify(self, session: Session, item_id: UUID | str) -> ClassifiedIdentity:
        item = session.get(KnowledgeItemORM, str(item_id))
        if item is None:
            raise SourceIdentityError(SOURCE_IDENTITY_INCONSISTENT, "item not found")
        snapshot = next(
            (
                row
                for row in build_identity_snapshots(session)
                if row["item_id"] == str(item.id)
            ),
            None,
        )
        if snapshot is None:  # pragma: no cover - build 覆盖全部 item
            raise SourceIdentityError(SOURCE_IDENTITY_INCONSISTENT, "snapshot missing")
        records = self._committed_index().get(str(item.id), [])
        matching = [
            record
            for record in records
            if record["source_instance_id"] == item.source_instance_id
            and record["source_document_id"] == str(item.id)
        ]
        origin_state = snapshot["import_origin_state"]
        if snapshot["import_origin_count"] > 0:
            if origin_state == "complete":
                return ClassifiedIdentity(
                    str(item.id),
                    "1",
                    snapshot["source_instance_id"],
                    snapshot["source_document_id"],
                    snapshot,
                )
            return ClassifiedIdentity(str(item.id), "3", None, None, snapshot)
        has_instance = bool(item.source_instance_id)
        if not has_instance:
            if records:
                return ClassifiedIdentity(str(item.id), "4", None, None, snapshot)
            return ClassifiedIdentity(str(item.id), "2a", None, str(item.id), snapshot)
        if len(matching) == 1 and len(records) == 1:
            return ClassifiedIdentity(
                str(item.id),
                "2b",
                item.source_instance_id,
                str(item.id),
                snapshot,
            )
        return ClassifiedIdentity(str(item.id), "4", None, None, snapshot)

    # -- Journal 恢复门 -----------------------------------------------------
    def recover_if_needed(self) -> None:
        with self._journal_lock:
            self._recover_locked()

    def _recover_locked(self) -> None:
        record = self.journal.read_current()
        if record is None:
            return
        if record["phase"] == "PREPARED":
            if record["kind"] == "MATERIALIZE":
                self._recover_materialize(record)
            else:
                self._recover_rotate(record)
        else:
            self._recover_committed(record)

    def _verify_record_db(self, record: dict[str, Any], session: Session) -> None:
        # 物化清单逐条满足 Journal 记录值（RECOVERY 表：等于才接受）。
        for entry in record["materialization_items"]:
            item = session.get(KnowledgeItemORM, entry["item_id"])
            if item is None:
                raise SourceIdentityError(JOURNAL_CORRUPT, "materialized item missing")
            origins = session.scalar(
                select(ImportOriginORM.id).where(
                    ImportOriginORM.item_id == entry["item_id"]
                )
            )
            if origins is not None:
                raise SourceIdentityError(
                    SOURCE_IDENTITY_INCONSISTENT, "materialized item has origin"
                )
            if item.source_instance_id != entry["source_instance_id"]:
                raise SourceIdentityError(
                    SOURCE_IDENTITY_INCONSISTENT, "materialized instance mismatch"
                )

    def _verify_audit(self, record: dict[str, Any], session: Session) -> None:
        if self.audit_digest(session) != record["identity_audit_digest"]:
            raise SourceIdentityError(
                SOURCE_IDENTITY_INCONSISTENT, "identity audit digest mismatch"
            )

    def _commit_and_archive(
        self, record: dict[str, Any], session: Session
    ) -> dict[str, Any]:
        self._verify_audit(record, session)
        committed = dict(record)
        committed["phase"] = "COMMITTED"
        committed["updated_at"] = _now()
        body = {k: v for k, v in committed.items() if k != "journal_checksum"}
        committed["journal_checksum"] = sha256_canonical(body)
        self.journal.write_current(committed)
        # 归档前从 DB 重算（写入 COMMITTED 不改变 DB，但规则要求逐次取证）。
        self._verify_audit(committed, session)
        self.journal.archive_committed(committed)
        self.journal.remove_current()
        return committed

    def _recover_materialize(self, record: dict[str, Any]) -> None:
        entry = record["materialization_items"][0]
        session = self._factory()
        try:
            item = session.get(KnowledgeItemORM, entry["item_id"])
            if item is None:
                raise SourceIdentityError(JOURNAL_CORRUPT, "materialize target missing")
            has_origin = session.scalar(
                select(ImportOriginORM.id).where(
                    ImportOriginORM.item_id == entry["item_id"]
                )
            )
            if has_origin is not None:
                raise SourceIdentityError(
                    SOURCE_IDENTITY_INCONSISTENT, "target has import origin"
                )
            if item.source_instance_id in (None, ""):
                stmt = (
                    update(KnowledgeItemORM)
                    .where(
                        KnowledgeItemORM.id == entry["item_id"],
                        or_(
                            KnowledgeItemORM.source_instance_id.is_(None),
                            KnowledgeItemORM.source_instance_id == "",
                        ),
                    )
                    .values(
                        source_instance_id=entry["source_instance_id"],
                        # 物化是身份元数据写，不是内容修改：保持 updated_at 不变，
                        # 否则重复导出 payload_hash 会漂移（D23 稳定导出）。
                        updated_at=KnowledgeItemORM.updated_at,
                    )
                )
                if session.execute(stmt).rowcount != 1:
                    session.rollback()
                    raise SourceIdentityError(
                        SOURCE_IDENTITY_INCONSISTENT, "conditional update failed"
                    )
                session.commit()
                session.expire_all()
                item = session.get(KnowledgeItemORM, entry["item_id"])
                assert item is not None
            if item.source_instance_id != entry["source_instance_id"]:
                raise SourceIdentityError(
                    SOURCE_IDENTITY_INCONSISTENT, "materialize value conflict"
                )
            self._verify_record_db(record, session)
            self._verify_audit(record, session)
            self._commit_and_archive(record, session)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _recover_rotate(self, record: dict[str, Any]) -> None:
        current_id = self._store.read()
        target = record["target_instance_id"]
        old = record["old_instance_id"]
        session = self._factory()
        try:
            self._verify_record_db(record, session)
            if current_id == old:
                self._verify_audit(record, session)
                self._store.replace(target)
                if self._store.read() != target:
                    raise SourceIdentityError(
                        SOURCE_IDENTITY_INCONSISTENT, "rotate id readback"
                    )
                self._verify_audit(record, session)
            elif current_id != target:
                raise SourceIdentityError(
                    SOURCE_IDENTITY_INCONSISTENT, "rotate instance mismatch"
                )
            self._verify_audit(record, session)
            self._commit_and_archive(record, session)
        finally:
            session.close()

    def _recover_committed(self, record: dict[str, Any]) -> None:
        session = self._factory()
        try:
            current_id = self._store.read()
            if record["kind"] == "ROTATE":
                if current_id != record["target_instance_id"]:
                    raise SourceIdentityError(
                        SOURCE_IDENTITY_INCONSISTENT, "committed rotate id mismatch"
                    )
            else:
                self._verify_record_db(record, session)
            self._verify_audit(record, session)
            self.journal.archive_committed(record)
            self.journal.remove_current()
        finally:
            session.close()

    # -- MATERIALIZE ---------------------------------------------------------
    def ensure_local_export_identity(self, item_id: UUID | str) -> str:
        """导出前确保本地文档有稳定身份：2b 直接复用；2a 走 Journal 物化。"""
        with self._journal_lock:
            self._recover_locked()
            session = self._factory()
            try:
                classified = self.classify(session, item_id)
            finally:
                session.close()
            if classified.state == "2b":
                assert classified.source_instance_id is not None
                return classified.source_instance_id
            if classified.state == "2a":
                return self.materialize(item_id).source_instance_id
            if classified.state == "1":
                assert classified.source_instance_id is not None
                return classified.source_instance_id
            raise SourceIdentityError(
                SOURCE_DOCUMENT_UNMATERIALIZED,
                f"identity state {classified.state} cannot be materialized",
            )

    def materialize(self, item_id: UUID | str) -> MaterializeReport:
        with self._journal_lock:
            self._recover_locked()
            target = self._store.ensure()
            session = self._factory()
            try:
                classified = self.classify(session, item_id)
                if classified.state == "2b":
                    existing = next(
                        (
                            record["operation_id"]
                            for record in self._committed_index().get(str(item_id), [])
                        ),
                        "",
                    )
                    return MaterializeReport(str(item_id), existing, False, target)
                if classified.state != "2a":
                    raise SourceIdentityError(
                        SOURCE_DOCUMENT_UNMATERIALIZED,
                        f"identity state {classified.state}",
                    )
                entry = {
                    "item_id": str(item_id),
                    "source_instance_id": target,
                    "source_document_id": str(item_id),
                    "identity_record_version": 1,
                }
                entry["item_identity_digest"] = item_identity_digest(entry)
                entries = [entry]
                expected = identity_audit_digest(
                    session, materialized={str(item_id): (target, str(item_id))}
                )
                record = self._new_record(
                    kind="MATERIALIZE",
                    phase="PREPARED",
                    item_id=str(item_id),
                    source_instance_id=target,
                    source_document_id=str(item_id),
                    items=entries,
                    audit_digest=expected,
                )
                self.journal.write_current(record)
                stmt = (
                    update(KnowledgeItemORM)
                    .where(
                        KnowledgeItemORM.id == str(item_id),
                        or_(
                            KnowledgeItemORM.source_instance_id.is_(None),
                            KnowledgeItemORM.source_instance_id == "",
                        ),
                    )
                    .values(
                        source_instance_id=target,
                        updated_at=KnowledgeItemORM.updated_at,
                    )
                )
                if session.execute(stmt).rowcount != 1:
                    session.rollback()
                    raise SourceIdentityError(
                        SOURCE_IDENTITY_INCONSISTENT, "conditional materialize failed"
                    )
                session.commit()
                session.expire_all()
                self._verify_record_db(record, session)
                self._verify_audit(record, session)
                committed = self._commit_and_archive(record, session)
                return MaterializeReport(
                    str(item_id), committed["operation_id"], True, target
                )
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

    # -- ROTATE --------------------------------------------------------------
    def rotate(self, target_instance_id: str | None = None) -> RotateReport:
        with self._journal_lock:
            self._recover_locked()
            old = self._store.ensure()
            target = target_instance_id or str(uuid.uuid4())
            if not _is_uuid_text(target, version=4):
                raise SourceIdentityError(SOURCE_IDENTITY_INCONSISTENT, "target not UUIDv4")
            if target == old:
                raise SourceIdentityError(SOURCE_IDENTITY_INCONSISTENT, "target equals old")

            session = self._factory()
            try:
                all_ids = list(session.scalars(select(KnowledgeItemORM.id)))
                pre_materialized: list[str] = []
                for raw_id in all_ids:
                    classified = self.classify(session, raw_id)
                    if classified.state == "2a":
                        self.materialize(raw_id)
                        pre_materialized.append(str(raw_id))
                    elif classified.state == "3":
                        # 状态 3 不物化、不改写；rotate 本身允许继续（来源原样保留）。
                        continue
                    elif classified.state == "4":
                        raise SourceIdentityError(
                            SOURCE_IDENTITY_INCONSISTENT,
                            f"document {raw_id} is identity state 4",
                        )
            finally:
                session.close()

            session = self._factory()
            try:
                entries = []
                for item_id in pre_materialized:
                    entry = {
                        "item_id": item_id,
                        "source_instance_id": old,
                        "source_document_id": item_id,
                        "identity_record_version": 1,
                    }
                    entry["item_identity_digest"] = item_identity_digest(entry)
                    entries.append(entry)
                expected = identity_audit_digest(session)
                record = self._new_record(
                    kind="ROTATE",
                    phase="PREPARED",
                    item_id=None,
                    source_instance_id=None,
                    source_document_id=None,
                    items=entries,
                    audit_digest=expected,
                    old_instance_id=old,
                    target_instance_id=target,
                )
                self.journal.write_current(record)
                self._verify_audit(record, session)
                self._store.replace(target)
                if self._store.read() != target:
                    raise SourceIdentityError(
                        SOURCE_IDENTITY_INCONSISTENT, "rotate readback mismatch"
                    )
                self._verify_record_db(record, session)
                self._verify_audit(record, session)
                committed = self._commit_and_archive(record, session)
                return RotateReport(
                    old,
                    target,
                    committed["operation_id"],
                    pre_materialized,
                )
            finally:
                session.close()

    # -- 记录构造 ------------------------------------------------------------
    @staticmethod
    def _new_record(
        *,
        kind: str,
        phase: str,
        item_id: str | None,
        source_instance_id: str | None,
        source_document_id: str | None,
        items: list[dict[str, Any]],
        audit_digest: str,
        old_instance_id: str | None = None,
        target_instance_id: str | None = None,
    ) -> dict[str, Any]:
        now = _now()
        record: dict[str, Any] = {
            "schema_version": 1,
            "operation_id": str(uuid.uuid4()),
            "kind": kind,
            "phase": phase,
            "created_at": now,
            "updated_at": now,
            "item_id": item_id,
            "source_instance_id": source_instance_id,
            "source_document_id": source_document_id,
            "materialization_items": items,
            "materialization_digest": materialization_digest(items),
            "identity_audit_digest": audit_digest,
            "journal_checksum": "",
            "old_instance_id": old_instance_id,
            "target_instance_id": target_instance_id,
        }
        body = {k: v for k, v in record.items() if k != "journal_checksum"}
        record["journal_checksum"] = sha256_canonical(body)
        return JournalStore.validate(record)