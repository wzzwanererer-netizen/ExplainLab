"""Attachment GC coordinates short database transactions and fenced file operations."""

from __future__ import annotations

import ctypes
import errno
import json
import logging
import os
import re
import stat
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.orphan_scan_lock import orphan_scan_leadership
from app.db.session import SQLiteWriteTimeout, run_short_write
from app.db.storage_lock import (
    LockGuard,
    StorageLockError,
    StorageLockTransient,
    new_owner,
)
from app.models import AttachmentORM
from app.services.attachment_staging import (
    AttachmentStagingError,
    AttachmentStagingService,
    validate_staging_id,
)
from app.services.attachment_storage import (
    ATTACHMENT_STORAGE_CROSS_VOLUME,
    ATTACHMENT_STORAGE_UNAVAILABLE,
    ATTACHMENT_WRITE_BUSY,
    AttachmentStorageError,
    StorageLayout,
    StorageRootError,
    _directory_chain,
    _file_info,
    _fsync_dir,
    _identity,
    _is_link,
    _link_or_rename,
    _mutate,
    _open_regular,
    delete_path,
    ensure_runtime,
    is_valid_storage_key,
    move_to_quarantine,
    restore_from_quarantine,
    retry_windows_busy,
    sha256_stream,
    verify_blob,
)
from app.services.attachments import release_storage_guard
from app.services.repositories_v2 import (
    SQLAlchemyAttachmentRepository,
    SQLAlchemyGcTaskRepository,
)
from knowledge_core.domain.entities import GcStatus, GcTask, utcnow

logger = logging.getLogger(__name__)
_ACTIVE = {GcStatus.PENDING, GcStatus.RUNNING, GcStatus.FAILED_RETRYABLE}
_BLOCKING = {GcStatus.FAILED_PERMANENT, GcStatus.NEEDS_MANUAL}
_STAGE_TIME = "%Y%m%dT%H%M%S%fZ"
_SHARD = re.compile(r"[0-9a-f]{2}")
_STAGED_BLOB = re.compile(r"blobs/[0-9]{6}\.bin")
_MARKER_TEMP = re.compile(r"\.complete\.[a-f0-9]{32}\.tmp")


class _TaskLeaseLost(RuntimeError):
    pass


class _UnsafeAttachment(RuntimeError):
    pass


class _PendingManifestUnknown(RuntimeError):
    pass


def _present(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _slot_key(path: Path) -> tuple[str, UUID] | None:
    key, _, suffix = path.name.partition(".")
    if not is_valid_storage_key(key):
        return None
    try:
        task_id = UUID(suffix)
    except ValueError:
        return None
    return (key, task_id) if str(task_id) == suffix else None


def _slot_stat(layout: StorageLayout, path: Path, key: str):
    with _open_regular(path, on_volume=layout.storage_root) as source:
        if sha256_stream(source) != key:
            raise _UnsafeAttachment("quarantine hash mismatch")
        observed = os.fstat(source.fileno())
    if _identity(observed) != _identity(_file_info(path, on_volume=layout.storage_root)):
        raise _UnsafeAttachment("quarantine identity changed")
    return observed


class _TaskStorageGuard(LockGuard):
    """Add task and reference fencing to the existing B1 filesystem primitives."""

    def __init__(self, storage_guard: LockGuard, check) -> None:
        self._storage_guard = storage_guard
        self._check_task_and_refs = check

    def lease_for(self, storage_key):
        return self._storage_guard.lease_for(storage_key)

    def verify_all(self, session: Session | None = None, *, deadline: float | None = None):
        self._check_task_and_refs()
        self._storage_guard.verify_all(session, deadline=deadline)


class _MaintenanceDatabase:
    def __init__(self, factory: sessionmaker[Session], settings: Settings) -> None:
        self.factory = factory
        self.settings = settings

    def repository(self, session: Session) -> SQLAlchemyGcTaskRepository:
        return SQLAlchemyGcTaskRepository(
            session,
            max_attempts=self.settings.gc_max_attempts,
            quarantine_seconds=self.settings.gc_quarantine_seconds,
        )

    def write(self, operation):
        return run_short_write(
            self.factory, operation, is_sqlite=self.settings.is_sqlite,
            deadline=time.monotonic() + self.settings.storage_lock_wait_seconds,
        )

    def enqueue(self, session: Session, key: str) -> GcTask | None:
        repo = self.repository(session)
        tasks = repo.list_tasks(storage_key=key)
        if any(task.status in _BLOCKING or task.status in _ACTIVE for task in tasks):
            return None
        return repo.save_task(GcTask(storage_key=key, status=GcStatus.PENDING))


class GcWorker:
    def __init__(self, factory, layout: StorageLayout, storage_lock, settings: Settings) -> None:
        self.database = _MaintenanceDatabase(factory, settings)
        self.layout = layout
        self.storage_lock = storage_lock
        self.settings = settings
        self.owner = new_owner()
        self.quarantine_period = timedelta(seconds=settings.gc_quarantine_seconds)

    def run_due(self, stop: threading.Event | None = None) -> None:
        with self.database.factory() as session:
            tasks = self.database.repository(session).list_tasks()
        for scheduled in tasks:
            if stop is not None and stop.is_set():
                return
            if scheduled.status in _ACTIVE:
                self._run_task(scheduled)

    def operate(self, task_id: UUID, *, target: GcStatus, actor: str) -> GcTask | None:
        """Audited operator transition using the repository's allowed transition set."""
        if not actor or not actor.isprintable():
            raise ValueError("an operator identifier is required")

        def transition(session):
            repo = self.database.repository(session)
            current = repo.get_task(task_id)
            if current is None:
                return None, None
            return current, repo.operator_transition(
                task_id, source=current.status, target=target,
                expected_lease_token=current.lease_token,
            )

        before, after = self.database.write(transition)
        if after is not None and before is not None:
            self._log_transition(before, after, "operator")
            logger.info("GC_OPERATOR actor=%s task=%s action=%s", actor, task_id, target.value)
        return after

    def _claim(self, scheduled: GcTask) -> GcTask | None:
        def claim(session):
            repo = self.database.repository(session)
            if scheduled.attempts >= self.settings.gc_max_attempts:
                final = repo.fail_unretryable(
                    scheduled.id, expected_lease_token=scheduled.lease_token,
                )
                return None, final
            if (
                scheduled.status == GcStatus.FAILED_RETRYABLE
                and repo.requeue_due(scheduled.id, expected_lease_token=scheduled.lease_token) is None
            ):
                return None, None
            return repo.claim(
                scheduled.id, owner=self.owner,
                lease_ttl_seconds=self.settings.storage_lock_ttl_seconds,
            ), None

        claimed, exhausted = self.database.write(claim)
        if exhausted is not None:
            self._log_transition(scheduled, exhausted, "budget_exhausted")
        if claimed is not None:
            self._log_transition(scheduled, claimed, "claim")
        return claimed

    def _run_task(self, scheduled: GcTask) -> None:
        now = utcnow()
        if scheduled.next_retry_at is not None and scheduled.next_retry_at > now:
            return
        if scheduled.status == GcStatus.RUNNING and (
            scheduled.lease_expires_at is None or scheduled.lease_expires_at > now
        ):
            return
        task = self._claim(scheduled)
        if task is None:
            return
        stop, abort = threading.Event(), threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat, args=(task, stop, abort), daemon=True,
            name="attachment-gc-heartbeat",
        )
        heartbeat.start()
        guard = None
        try:
            if not is_valid_storage_key(task.storage_key):
                self._finish(task, GcStatus.NEEDS_MANUAL, "invalid_key")
                return
            try:
                guard = self.storage_lock.acquire_many([task.storage_key], new_owner())
            except (StorageLockError, StorageLockTransient) as exc:
                self._retry(task, type(exc).__name__)
                return
            if guard is None:
                self._retry(task, "storage_lock_timeout")
                return
            referenced = self._observe(task, abort)
            fenced = _TaskStorageGuard(guard, lambda: self._require_refs(task, abort, referenced))
            try:
                self._process(task, fenced, referenced)
            except (_TaskLeaseLost, StorageLockError, StorageLockTransient):
                logger.warning("GC_FENCE_LOST task=%s", task.id)
            except AttachmentStorageError as exc:
                guard.verify_all()
                if exc.code in {ATTACHMENT_WRITE_BUSY, ATTACHMENT_STORAGE_UNAVAILABLE}:
                    self._retry(task, exc.code)
                elif exc.code == ATTACHMENT_STORAGE_CROSS_VOLUME:
                    self._finish(task, GcStatus.FAILED_PERMANENT, exc.code)
                else:
                    self._finish(task, GcStatus.NEEDS_MANUAL, exc.code)
            except (_UnsafeAttachment, OSError, StorageRootError):
                guard.verify_all()
                self._finish(task, GcStatus.NEEDS_MANUAL, "unsafe_physical_state")
        except (_TaskLeaseLost, StorageLockError, StorageLockTransient, SQLAlchemyError,
                SQLiteWriteTimeout) as exc:
            logger.warning("GC_TASK_DEFERRED task=%s error=%s", task.id, type(exc).__name__)
        finally:
            stop.set()
            heartbeat.join()
            release_storage_guard(guard)

    def _heartbeat(self, task, stop, abort) -> None:
        if self.settings.storage_lock_heartbeat_seconds <= 0:
            return
        while not stop.wait(self.settings.storage_lock_heartbeat_seconds):
            try:
                renewed = self.database.write(lambda session: self.database.repository(
                    session,
                ).renew_task(
                    task.id, owner=self.owner, lease_token=task.lease_token,
                    lease_ttl_seconds=self.settings.storage_lock_ttl_seconds,
                ))
            except (SQLAlchemyError, SQLiteWriteTimeout):
                continue
            if renewed is None:
                abort.set()
                return

    def _observe(self, task: GcTask, abort: threading.Event) -> bool:
        if abort.is_set():
            raise _TaskLeaseLost
        with self.database.factory() as session:
            current = self.database.repository(session).get_task(task.id)
            if (
                current is None
                or current.status != GcStatus.RUNNING
                or current.lease_owner != self.owner
                or current.lease_token != task.lease_token
                or current.lease_expires_at is None
                or current.lease_expires_at <= utcnow()
            ):
                raise _TaskLeaseLost
            return SQLAlchemyAttachmentRepository(session).count_references(task.storage_key) > 0

    def _require_refs(self, task: GcTask, abort: threading.Event, expected: bool) -> None:
        if self._observe(task, abort) != expected:
            raise _TaskLeaseLost

    def _process(self, task: GcTask, guard: LockGuard, referenced: bool) -> None:
        ensure_runtime(self.layout)
        key = task.storage_key
        final = self.layout.final_path(key)
        slot = self.layout.quarantine_dir / f"{key}.{task.id}"
        has_final, has_slot = _present(final), _present(slot)
        for path, exists in ((final, has_final), (slot, has_slot)):
            if exists:
                info = path.lstat()
                if _is_link(info) or not stat.S_ISREG(info.st_mode):
                    raise _UnsafeAttachment("non-regular attachment path")
        if task.quarantine_path not in (None, slot.name):
            raise _UnsafeAttachment("task slot mismatch")
        if referenced:
            if has_final:
                verify_blob(self.layout, key)
            else:
                source = slot if has_slot else self._restore_source(key)
                if source is None:
                    raise _UnsafeAttachment("referenced blob missing")
                _slot_stat(self.layout, source, key)
                restore_from_quarantine(self.layout, source, key, lock_guard=guard)
                verify_blob(self.layout, key)
        if has_slot:
            self._process_slot(task, guard, slot, final, referenced)
        elif referenced:
            guard.verify_all()
            self._finish(task, GcStatus.CANCELLED, "referenced")
        elif has_final and task.quarantine_path is None and task.quarantined_at is None:
            verify_blob(self.layout, key)
            move_to_quarantine(self.layout, key, task_id=task.id, lock_guard=guard)
            guard.verify_all()
            now = utcnow()
            self._wait_quarantine(task, slot, now, now + self.quarantine_period)
        else:
            guard.verify_all()
            self._finish(task, GcStatus.DONE, "slot_absent", successor=has_final)

    def _process_slot(self, task, guard, slot, final, referenced) -> None:
        info = _slot_stat(self.layout, slot, task.storage_key)
        now = utcnow()
        mtime = datetime.fromtimestamp(info.st_mtime, UTC)
        quarantined_at = task.quarantined_at
        if quarantined_at is None or task.quarantine_path is None:
            quarantined_at = now
        if mtime > now or quarantined_at > now:
            raise _UnsafeAttachment("future quarantine timestamp")
        safe_at = max(mtime, quarantined_at) + self.quarantine_period
        guard.verify_all()
        if safe_at > now:
            self._wait_quarantine(task, slot, quarantined_at, safe_at)
            return
        if referenced:
            verify_blob(self.layout, task.storage_key)
        delete_path(self.layout, slot, task.storage_key, lock_guard=guard)
        guard.verify_all()
        if referenced:
            self._finish(task, GcStatus.CANCELLED, "redundant_slot_purged")
        else:
            self._finish(task, GcStatus.DONE, "slot_purged", successor=_present(final))

    def _restore_source(self, key: str) -> Path | None:
        for path in sorted(self.layout.quarantine_dir.glob(f"{key}.*")):
            if _slot_key(path) is not None:
                try:
                    _slot_stat(self.layout, path, key)
                except (_UnsafeAttachment, OSError, AttachmentStorageError, StorageRootError):
                    continue
                return path
        return None

    def _wait_quarantine(
        self, task: GcTask, slot: Path, quarantined_at: datetime, safe_at: datetime,
    ) -> None:
        change = task.model_copy(update={
            "quarantine_path": slot.name, "quarantined_at": quarantined_at,
            "next_retry_at": safe_at,
        })
        self._writeback(task, change, "quarantine_wait")

    def _retry(self, task: GcTask, reason: str) -> None:
        if task.attempts >= self.settings.gc_max_attempts:
            self._finish(task, GcStatus.FAILED_PERMANENT, reason)
            return
        seconds = min(
            self.settings.gc_retry_base_seconds * 2 ** (task.attempts - 1),
            self.settings.gc_retry_max_seconds,
        )
        change = task.model_copy(update={
            "status": GcStatus.FAILED_RETRYABLE,
            "next_retry_at": utcnow() + timedelta(seconds=seconds),
        })
        self._writeback(task, change, reason)

    def _finish(
        self, task: GcTask, status: GcStatus, reason: str, *, successor: bool = False,
    ) -> None:
        self._writeback(task, task.model_copy(update={"status": status}), reason, successor=successor)

    def _writeback(
        self, task: GcTask, change: GcTask, reason: str, *, successor: bool = False,
    ) -> None:
        def update(session):
            saved = self.database.repository(session).update_task(
                change, expected_lease_token=task.lease_token,
            )
            if saved is not None and successor:
                self.database.enqueue(session, task.storage_key)
            return saved

        saved = self.database.write(update)
        if saved is None:
            raise _TaskLeaseLost
        self._log_transition(task, saved, reason)

    @staticmethod
    def _log_transition(before: GcTask, after: GcTask, reason: str) -> None:
        logger.info(
            "GC_TRANSITION task=%s key=%s owner=%s from=%s to=%s attempts=%s token=%s reason=%s",
            after.id, after.storage_key, after.lease_owner or before.lease_owner,
            before.status.value, after.status.value, after.attempts, after.lease_token, reason,
        )


@dataclass
class _ConsistencyReport:
    counts: dict = field(default_factory=lambda: dict.fromkeys((
        "attachment_rows", "referenced_keys", "formal_blobs", "orphan_blobs",
        "missing_blobs", "hash_mismatched", "misplaced_blobs", "quarantine_files",
        "staging_dirs", "staging_incomplete", "pending_staging_refs",
    ), 0))
    orphan_blobs: list = field(default_factory=list)
    missing_blobs: list = field(default_factory=list)
    hash_mismatched: list = field(default_factory=list)
    misplaced_blobs: list = field(default_factory=list)
    quarantine_residual: list = field(default_factory=list)
    staging_orphans: list = field(default_factory=list)
    malformed_manifests: list = field(default_factory=list)
    temp_residual: dict = field(default_factory=lambda: {"count": 0, "oldest_mtime": None})
    notes: list = field(default_factory=list)

    def json(self) -> dict:
        return {"generated_at": utcnow().isoformat(),
                "storage_root": "<data_dir>/attachments", **asdict(self)}


@dataclass(frozen=True)
class _StageSnapshot:
    identity: tuple[int, int]
    keys: tuple[str, ...]
    activity: datetime
    complete: bool


class OrphanRecovery:
    def __init__(self, gc: GcWorker, staging: AttachmentStagingService, engine: Engine) -> None:
        self.database = gc.database
        self.layout = gc.layout
        self.storage_lock = gc.storage_lock
        self.staging = staging
        self.engine = engine
        self.staging_grace = timedelta(seconds=gc.settings.staging_grace_seconds)
        self.quarantine_period = gc.quarantine_period

    def scan_once(self, stop: threading.Event | None = None) -> dict | None:
        report = _ConsistencyReport()
        try:
            with orphan_scan_leadership(self.engine) as leader:
                if not leader:
                    return None
                self._scan(report, stop or threading.Event())
        except (SQLAlchemyError, SQLiteWriteTimeout, OSError, AttachmentStorageError) as exc:
            report.notes.append({"event": "scan_deferred", "error_type": type(exc).__name__})
        body = report.json()
        try:
            self._write_report(body)
        except OSError as exc:
            logger.warning("ORP_REPORT_WRITE_FAILED: %s", type(exc).__name__)
        return body

    def _scan(self, report: _ConsistencyReport, stop: threading.Event) -> None:
        ensure_runtime(self.layout)
        with self.database.factory() as session:
            rows = list(session.execute(select(AttachmentORM.id, AttachmentORM.storage_key)))
        refs = {}
        for attachment_id, key in rows:
            refs.setdefault(key, []).append(attachment_id)
        report.counts["attachment_rows"] = len(rows)
        report.counts["referenced_keys"] = len(refs)
        self._scan_temp(report)
        self._scan_formal(report, refs, stop)
        if not stop.is_set():
            self._scan_quarantine(report, stop)
        if not stop.is_set():
            self._scan_staging(report, stop)

    def _scan_temp(self, report: _ConsistencyReport) -> None:
        times = [
            datetime.fromtimestamp(info.st_mtime, UTC)
            for path in self.layout.temp_dir.iterdir()
            if stat.S_ISREG((info := path.lstat()).st_mode) and not _is_link(info)
        ]
        report.temp_residual = {"count": len(times),
                                "oldest_mtime": min(times).isoformat() if times else None}

    def _scan_formal(self, report: _ConsistencyReport, refs: dict, stop) -> None:
        present = set()
        for path in self._formal_candidates(report):
            if stop.is_set():
                return
            key = path.name
            if not is_valid_storage_key(key):
                report.notes.append({"event": "unrecognized_formal_entry"})
                continue
            expected = self.layout.final_path(key)
            if path != expected:
                safe_relative = "/".join((
                    *(part if _SHARD.fullmatch(part) else "<redacted>"
                      for part in path.relative_to(self.layout.storage_root).parts[:-1]),
                    key,
                ))
                report.misplaced_blobs.append({"storage_key": key, "relative_path": safe_relative})
                continue
            present.add(key)
            report.counts["formal_blobs"] += 1
            try:
                info = _file_info(path, on_volume=self.layout.storage_root)
                with _open_regular(path, on_volume=self.layout.storage_root) as blob:
                    actual = sha256_stream(blob)
                if actual != key:
                    report.hash_mismatched.append({"storage_key": key, "actual_hash": actual})
                    continue
            except (OSError, AttachmentStorageError, StorageRootError):
                report.notes.append({"event": "formal_read_failed", "storage_key": key})
                continue
            with self.database.factory() as session:
                if SQLAlchemyAttachmentRepository(session).count_references(key):
                    continue
            mtime = datetime.fromtimestamp(info.st_mtime, UTC)
            now = utcnow()
            report.orphan_blobs.append({"storage_key": key, "mtime": mtime.isoformat()})
            if mtime > now:
                report.notes.append({"event": "future_mtime", "storage_key": key})
            elif now - mtime >= self.quarantine_period:
                self.database.write(lambda session, key=key: self._enqueue_unreferenced(
                    session, key,
                ))
        for key, ids in refs.items():
            if key not in present:
                report.missing_blobs.extend(
                    {"storage_key": key, "attachment_id": attachment_id} for attachment_id in ids
                )
        for name in ("missing_blobs", "orphan_blobs", "misplaced_blobs", "hash_mismatched"):
            report.counts[name] = len(getattr(report, name))

    def _formal_candidates(self, report: _ConsistencyReport):
        for directory, folders, files in os.walk(self.layout.storage_root, followlinks=False):
            root = Path(directory)
            folders[:] = [
                name for name in folders
                if root / name not in (
                    self.layout.quarantine_dir, self.layout.temp_dir, self.layout.staging_root,
                ) and not name.startswith(".") and not _is_link((root / name).lstat())
            ]
            for name in files:
                path = root / name
                if _is_link(path.lstat()):
                    report.notes.append({"event": "unsafe_formal_entry"})
                else:
                    yield path

    def _enqueue_unreferenced(self, session, key):
        if SQLAlchemyAttachmentRepository(session).count_references(key) == 0:
            return self.database.enqueue(session, key)
        return None

    def _scan_quarantine(self, report: _ConsistencyReport, stop) -> None:
        for path in self.layout.quarantine_dir.iterdir():
            if stop.is_set():
                return
            if path.name == "staging":
                continue
            if stat.S_ISREG(path.lstat().st_mode):
                report.counts["quarantine_files"] += 1
            candidate = _slot_key(path)
            if candidate is None:
                report.quarantine_residual.append({"event": "unrecognized_slot"})
                continue
            key, slot_id = candidate
            try:
                result = self._recover_slot(path, key, slot_id)
            except (StorageLockError, StorageLockTransient, _UnsafeAttachment, OSError,
                    AttachmentStorageError, StorageRootError) as exc:
                result = type(exc).__name__
            report.quarantine_residual.append({"storage_key": key, "event": result})

    def _recover_slot(self, path: Path, key: str, slot_id: UUID) -> str:
        guard = self.storage_lock.acquire_many([key], new_owner())
        if guard is None:
            return "key_lock_busy"
        try:
            if not _present(path):
                return "slot_gone"
            info = _slot_stat(self.layout, path, key)
            if datetime.fromtimestamp(info.st_mtime, UTC) > utcnow():
                return "future_mtime"
            with self.database.factory() as session:
                refs = SQLAlchemyAttachmentRepository(session).count_references(key)
                owner = self.database.repository(session).get_task(slot_id)
            if owner is not None and owner.storage_key != key:
                return "slot_owner_mismatch"
            if refs:
                if not _present(self.layout.final_path(key)):
                    restore_from_quarantine(self.layout, path, key, lock_guard=guard)
                    return "referenced_blob_restored"
                verify_blob(self.layout, key)
            if owner is not None and (owner.status in _BLOCKING or owner.status in _ACTIVE):
                return "owned_slot_preserved"
            receiver = self.database.write(lambda session: self.database.enqueue(session, key))
            if receiver is None:
                return "receiver_unavailable"
            target = self.layout.quarantine_dir / f"{key}.{receiver.id}"
            self._transfer_slot(path, target, key, guard)
            return "receiver_enqueued"
        finally:
            release_storage_guard(guard)

    def _transfer_slot(self, path: Path, target: Path, key: str, guard: LockGuard) -> None:
        owned = _identity(_slot_stat(self.layout, path, key))
        outcome = _link_or_rename(self.layout, key, guard, path, target, owned)
        if outcome == "exists":
            raise _UnsafeAttachment("receiver slot already exists")
        _fsync_dir(target.parent)
        if outcome == "linked":
            _mutate(self.layout, key, guard, os.unlink, path, owned=owned)
            _fsync_dir(path.parent)

    def _scan_staging(self, report: _ConsistencyReport, stop) -> None:
        pending = self.staging.pending_staging_ids()
        if pending is None:
            report.malformed_manifests.append({"event": "pending_manifest_unverifiable"})
            return
        report.counts["pending_staging_refs"] = len(pending)
        quarantine = self.layout.quarantine_dir / "staging"
        quarantine.mkdir(mode=0o700, exist_ok=True)
        self.staging._assert_real_directory(quarantine, root=self.layout.quarantine_dir)
        for root in (self.layout.staging_root, quarantine):
            isolated = root == quarantine
            for path in root.iterdir():
                if stop.is_set():
                    return
                try:
                    staging_id, isolated_at = self._parse_stage(path, isolated)
                except (ValueError, AttachmentStagingError):
                    report.notes.append({"event": "unrecognized_staging_entry"})
                    continue
                if not isolated:
                    report.counts["staging_dirs"] += 1
                    if not (path / ".complete").is_file():
                        report.counts["staging_incomplete"] += 1
                try:
                    action = self._sweep_stage(path, staging_id, isolated_at, quarantine)
                except _PendingManifestUnknown:
                    report.malformed_manifests.append({"event": "pending_manifest_unverifiable"})
                    return
                except (AttachmentStagingError, StorageLockTransient, StorageLockError,
                        AttachmentStorageError, _UnsafeAttachment, OSError) as exc:
                    action = type(exc).__name__
                if action is not None:
                    report.staging_orphans.append({"staging_id": str(staging_id), "event": action})

    @staticmethod
    def _parse_stage(path: Path, isolated: bool) -> tuple[UUID, datetime | None]:
        if not isolated:
            return validate_staging_id(path.name), None
        name, sep, stamp = path.name.partition(".")
        if not sep:
            raise ValueError("missing isolation timestamp")
        when = datetime.strptime(stamp, _STAGE_TIME).replace(tzinfo=UTC)
        if when.strftime(_STAGE_TIME) != stamp:
            raise ValueError("invalid isolation timestamp")
        return validate_staging_id(name), when

    def _stage_snapshot(self, path: Path) -> _StageSnapshot:
        self.staging._assert_real_directory(path, root=path.parent)
        root_info = path.lstat()
        relative = self.staging._regular_relative_files(path)
        directories = self.staging._relative_directories(path)
        if directories - {"blobs"}:
            raise _UnsafeAttachment("unexpected directory in staging")
        if not relative and directories:
            raise _UnsafeAttachment("no staging activity evidence")
        activity, total, keys = [], 0, []
        for name in sorted(relative):
            member = path / name
            info = _file_info(member, on_volume=self.layout.storage_root)
            activity.append(datetime.fromtimestamp(info.st_mtime, UTC))
            if name in {".activity", ".creating", ".complete"} or _MARKER_TEMP.fullmatch(name):
                continue
            if not _STAGED_BLOB.fullmatch(name):
                raise _UnsafeAttachment("unexpected file in staging")
            total += info.st_size
            if (
                len(keys) >= self.database.settings.attachment_import_max_count
                or info.st_size > self.database.settings.attachment_max_bytes
                or total > self.database.settings.attachment_import_max_total_bytes
            ):
                raise _UnsafeAttachment("staging scan budget exceeded")
            with _open_regular(member, on_volume=self.layout.storage_root) as blob:
                keys.append(sha256_stream(blob))
        when = max(activity) if activity else datetime.fromtimestamp(root_info.st_mtime, UTC)
        return _StageSnapshot(_identity(root_info), tuple(sorted(set(keys))), when,
                              ".complete" in relative)

    def _pending(self, staging_id: UUID) -> bool:
        pending = self.staging.pending_staging_ids()
        if pending is None:
            raise _PendingManifestUnknown
        return str(staging_id) in pending

    def _sweep_stage(
        self, path: Path, staging_id: UUID, isolated_at: datetime | None, quarantine: Path,
    ) -> str | None:
        with self.staging.staging_guard(staging_id, wait_seconds=0):
            if not _present(path):
                return None
            pending = self._pending(staging_id)
            if pending and isolated_at is None:
                return None
            snapshot = self._stage_snapshot(path)
            now = utcnow()
            if snapshot.activity > now or (isolated_at is not None and isolated_at > now):
                return "future_staging_mtime"
            if not pending:
                due = (
                    isolated_at + self.quarantine_period if isolated_at is not None
                    else snapshot.activity + self.staging_grace
                )
                if due > now:
                    return None
            guard = self.storage_lock.acquire_many(snapshot.keys, new_owner()) if snapshot.keys else None
            if snapshot.keys and guard is None:
                return "key_lock_busy"
            try:
                if self._stage_snapshot(path) != snapshot:
                    return "staging_changed_during_wait"

                def verify():
                    ensure_runtime(self.layout)
                    if self._pending(staging_id) != pending:
                        raise _UnsafeAttachment("pending ownership changed")
                    if guard is not None:
                        guard.verify_all()

                if isolated_at is None:
                    target = quarantine / f"{staging_id}.{utcnow().strftime(_STAGE_TIME)}"
                    _rename_directory_no_clobber(path, target, verify)
                    return "staging_isolated"
                if pending:
                    target = self.layout.staging_root / str(staging_id)
                    _rename_directory_no_clobber(path, target, verify)
                    return "pending_staging_restored"
                self._purge_stage(path, verify)
                return "isolated_staging_purged"
            finally:
                release_storage_guard(guard)

    def _purge_stage(self, root: Path, verify: Callable[[], None]) -> None:
        def mutate(operation):
            def attempt():
                verify()
                operation()

            retry_windows_busy(attempt)

        def purge(path):
            self.staging._assert_real_directory(path, root=root.parent)
            for child in path.iterdir():
                info = child.lstat()
                if _is_link(info):
                    raise _UnsafeAttachment("unsafe staging child")
                if stat.S_ISDIR(info.st_mode):
                    purge(child)
                    continue
                if not stat.S_ISREG(info.st_mode):
                    raise _UnsafeAttachment("unsafe staging child")
                mutate(child.unlink)
            mutate(path.rmdir)

        purge(root)
        _fsync_dir(root.parent)

    def _write_report(self, body: dict) -> None:
        directory = self.layout.data_dir / "ops"
        directory.mkdir(mode=0o700, exist_ok=True)
        _directory_chain(directory)
        destination = directory / f"attachment-consistency-{utcnow().strftime(_STAGE_TIME)}.json"
        temp = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=directory, prefix=".consistency-", delete=False,
            ) as file:
                temp = Path(file.name)
                json.dump(body, file, ensure_ascii=False, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp, destination)
            _fsync_dir(directory)
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)
        stale = sorted(directory.glob("attachment-consistency-*.json"), reverse=True)[30:]
        for path in stale:
            if stat.S_ISREG(path.lstat().st_mode):
                path.unlink()


def _rename_directory_no_clobber(
    source: Path, target: Path, verify: Callable[[], None],
) -> None:
    def attempt():
        _directory_chain(source)
        _directory_chain(target.parent)
        verify()
        if os.name == "nt":
            os.rename(source, target)
            return
        native_rename = getattr(ctypes.CDLL(None, use_errno=True), "renameat2", None)
        if native_rename is None:
            raise OSError(errno.ENOTSUP, "exclusive directory rename unavailable")
        native_rename.argtypes = [
            ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint,
        ]
        native_rename.restype = ctypes.c_int
        # AT_FDCWD and RENAME_NOREPLACE on Linux.
        if native_rename(-100, os.fsencode(source), -100, os.fsencode(target), 1) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))

    retry_windows_busy(attempt)
    _fsync_dir(source.parent)
    _fsync_dir(target.parent)


class AttachmentMaintenance:
    """A single process worker, stopped before disposing the database and process lock."""

    def __init__(self, gc: GcWorker, recovery: OrphanRecovery) -> None:
        self.gc = gc
        self.recovery = recovery
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="attachment-maintenance", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join()

    def _run(self) -> None:
        self._scan()
        while not self._stop.wait(self.gc.settings.orphan_scan_interval_seconds):
            try:
                self.gc.run_due(self._stop)
            except Exception as exc:  # noqa: BLE001 - retry during the next maintenance cycle
                logger.warning("GC_CYCLE_DEFERRED: %s", type(exc).__name__)
            if not self._stop.is_set():
                self._scan()

    def _scan(self) -> None:
        try:
            self.recovery.scan_once(self._stop)
        except Exception as exc:  # noqa: BLE001 - never silently stop maintenance
            logger.warning("ORP_CYCLE_DEFERRED: %s", type(exc).__name__)
