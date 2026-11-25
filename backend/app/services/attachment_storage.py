"""附件物理存储（V2 A1-04 Batch B，B1-T01/T02）。

本模块只做内容寻址物理存储：根目录校验、SHA-256、临时写、no-clobber 发布、
同句柄校验读取、quarantine 移动/恢复与 Windows 占用重试。**不查 DB、不判断引用、
不 commit、不加锁**；调用方必须先成功取得 ``StorageKeyLock`` 才能发布或移动。

冻结契约见 ``docs/plans/V2-A1-04-Batch-B/storage-and-lock-contract.md``。
实现与契约冲突时以该文件为准；架构变更须走正式审批。
"""

from __future__ import annotations

import contextlib
import errno
import hashlib
import logging
import os
import re
import stat
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import BinaryIO
from urllib.parse import unquote

from sqlalchemy.engine import make_url

from app.db.storage_lock import LockGuard, StorageLeaseLost
from app.services.file_write import write_all

__all__ = [
    "ATTACHMENT_BLOB_CORRUPTED",
    "ATTACHMENT_BLOB_MISSING",
    "ATTACHMENT_HASH_MISMATCH",
    "ATTACHMENT_KEY_COLLISION",
    "ATTACHMENT_STORAGE_CROSS_VOLUME",
    "ATTACHMENT_STORAGE_UNAVAILABLE",
    "ATTACHMENT_WRITE_BUSY",
    "ATTACHMENT_WRITE_CORRUPTED",
    "ATTACHMENT_WRITE_FAILED",
    "AttachmentStorageError",
    "PublishResult",
    "StorageLayout",
    "StorageRootError",
    "TempBlob",
    "copy_to_temp",
    "delete_blob",
    "delete_path",
    "ensure_runtime",
    "final_path_for",
    "is_valid_storage_key",
    "iter_file",
    "move_to_quarantine",
    "open_verified_blob",
    "publish_no_clobber",
    "restore_from_quarantine",
    "retry_windows_busy",
    "sha256_bytes",
    "sha256_file",
    "sha256_stream",
    "shard_parts",
    "validate_storage_roots",
    "verify_blob",
    "write_temp",
]

logger = logging.getLogger(__name__)

ATTACHMENT_STORAGE_UNAVAILABLE = "ATTACHMENT_STORAGE_UNAVAILABLE"
ATTACHMENT_STORAGE_CROSS_VOLUME = "ATTACHMENT_STORAGE_CROSS_VOLUME"
ATTACHMENT_WRITE_FAILED = "ATTACHMENT_WRITE_FAILED"
ATTACHMENT_WRITE_BUSY = "ATTACHMENT_WRITE_BUSY"
ATTACHMENT_WRITE_CORRUPTED = "ATTACHMENT_WRITE_CORRUPTED"
ATTACHMENT_HASH_MISMATCH = "ATTACHMENT_HASH_MISMATCH"
ATTACHMENT_KEY_COLLISION = "ATTACHMENT_KEY_COLLISION"
ATTACHMENT_BLOB_MISSING = "ATTACHMENT_BLOB_MISSING"
ATTACHMENT_BLOB_CORRUPTED = "ATTACHMENT_BLOB_CORRUPTED"

_KEY_RE = re.compile(r"^[0-9a-f]{64}$")
_CHUNK_SIZE = 1024 * 1024
_WINDOWS_LONG_PATH_WARNING = 240

# Windows 占用重试参数（storage §6）；测试可缩短预算，不改变生产默认。
WINDOWS_BUSY_INITIAL_DELAY = 0.1
WINDOWS_BUSY_MAX_DELAY = 1.0
WINDOWS_BUSY_BUDGET = 5.0

_BINARY = getattr(os, "O_BINARY", 0)
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400


class StorageRootError(RuntimeError):
    """启动期存储根不可用（稳定码 ``ATTACHMENT_STORAGE_UNAVAILABLE``）。"""

    code = ATTACHMENT_STORAGE_UNAVAILABLE

    def __init__(self, message: str = "") -> None:
        detail = f": {message}" if message else ""
        super().__init__(f"{self.code}{detail}")


class AttachmentStorageError(RuntimeError):
    """运行期存储错误，携带冻结稳定错误码。"""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        detail = f": {message}" if message else ""
        super().__init__(f"{code}{detail}")


@dataclass(frozen=True)
class StorageLayout:
    """已验证/待验证的存储根布局。"""

    data_dir: Path
    storage_root: Path
    staging_root: Path
    quarantine_dir: Path
    temp_dir: Path
    root_identities: tuple[tuple[int, int], ...] = ()

    def final_path(self, storage_key: str) -> Path:
        return final_path_for(self.storage_root, storage_key)

    def temp_path(self) -> Path:
        return self.temp_dir / f"{uuid.uuid4().hex}.part"


@dataclass(frozen=True)
class TempBlob:
    path: Path
    size: int
    sha256: str
    identity: tuple[int, int]


@dataclass(frozen=True)
class PublishResult:
    path: Path
    size: int
    reused: bool


def is_valid_storage_key(storage_key: str) -> bool:
    return isinstance(storage_key, str) and _KEY_RE.fullmatch(storage_key) is not None


def shard_parts(storage_key: str) -> tuple[str, str]:
    if not is_valid_storage_key(storage_key):
        raise AttachmentStorageError(ATTACHMENT_WRITE_FAILED, "invalid storage key")
    return storage_key[:2], storage_key[2:4]


def final_path_for(storage_root: Path, storage_key: str) -> Path:
    first, second = shard_parts(storage_key)
    return Path(storage_root) / first / second / storage_key


def sha256_bytes(payload: bytes | bytearray | memoryview) -> str:
    return hashlib.sha256(memoryview(payload)).hexdigest()


def sha256_stream(stream: BinaryIO, *, chunk_size: int = _CHUNK_SIZE) -> str:
    digest = hashlib.sha256()
    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: Path, *, chunk_size: int = _CHUNK_SIZE) -> str:
    with open(path, "rb") as handle:
        return sha256_stream(handle, chunk_size=chunk_size)


def iter_file(handle: BinaryIO, *, chunk_size: int = _CHUNK_SIZE) -> Iterable[bytes]:
    while True:
        chunk = handle.read(chunk_size)
        if not chunk:
            return
        yield chunk


def _is_windows() -> bool:
    return os.name == "nt"


def _winerror(exc: OSError) -> int | None:
    value = getattr(exc, "winerror", None)
    return int(value) if value else None


def _is_link(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT
    )


def _identity(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


def _directory_chain(path: Path, *, allow_missing: bool = False) -> Path:
    if not path.is_absolute() or ".." in path.parts:
        raise StorageRootError("invalid absolute storage path")
    current = Path(path.anchor)
    for part in ("", *path.parts[1:]):
        if ":" in part or (_is_windows() and (
            part.endswith((" ", ".")) or PureWindowsPath(part).is_reserved()
        )):
            raise StorageRootError("invalid storage path component")
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            if allow_missing:
                return current.parent
            raise
        if _is_link(info) or not stat.S_ISDIR(info.st_mode):
            raise StorageRootError("storage directory component is not a real directory")
    return current


def _file_info(path: Path, *, on_volume: Path) -> os.stat_result:
    _directory_chain(path.parent)
    info = path.lstat()
    if _is_link(info) or not stat.S_ISREG(info.st_mode):
        raise AttachmentStorageError(ATTACHMENT_STORAGE_UNAVAILABLE, "not a regular file")
    if _st_dev(path) != _st_dev(on_volume):
        raise AttachmentStorageError(ATTACHMENT_STORAGE_CROSS_VOLUME)
    return info


def _open_regular(path: Path, *, on_volume: Path) -> BinaryIO:
    before = _file_info(path, on_volume=on_volume)
    fd = os.open(
        path, os.O_RDONLY | _BINARY | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0),
    )
    try:
        actual = os.fstat(fd)
        if (
            not stat.S_ISREG(actual.st_mode)
            or _identity(actual) != _identity(before)
            or _identity(actual) != _identity(_file_info(path, on_volume=on_volume))
        ):
            raise AttachmentStorageError(ATTACHMENT_STORAGE_UNAVAILABLE, "file identity changed")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def _mode_700(path: Path) -> None:
    # 权限尽力而为；不因 chmod 平台差异阻断启动。
    with contextlib.suppress(OSError):
        os.chmod(path, 0o700)


def _st_dev(path: Path) -> int:
    return path.stat().st_dev


def _same_volume(paths: Iterable[Path]) -> bool:
    devices = {_st_dev(path) for path in paths}
    return len(devices) <= 1


def _is_relative_or_equal(parent: Path, child: Path) -> bool:
    if parent == child:
        return True
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _sqlite_db_path(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite"):
        return None
    url = make_url(database_url)
    name = url.database
    if not name or name == ":memory:" or url.query.get("mode") == "memory":
        return None
    if url.query.get("uri") == "true" and name.startswith("file:"):
        name = unquote(name.removeprefix("file:"))
        if name.startswith("///"):
            name = name[2:]
        if _is_windows() and re.match(r"^/[A-Za-z]:", name):
            name = name[1:]
        if name == ":memory:":
            return None
    path = Path(name)
    return path if path.is_absolute() else Path.cwd() / path


def _reserved_paths(settings) -> tuple[list[Path], list[Path]]:
    data_dir = Path(settings.data_dir)
    files = [
        data_dir / ".explainlab.process.lock",
        data_dir / "source-instance-id",
        data_dir / "source-identity-journal.json",
    ]
    db_path = _sqlite_db_path(settings.database_url)
    if db_path is not None:
        files.append(db_path)
    dirs = [
        data_dir / "source-identity-journal.archive",
        data_dir / "ops",
    ]
    return files, dirs


def _assert_not_reserved(path: Path, reserved_files: list[Path], reserved_dirs: list[Path]) -> None:
    for reserved in reserved_files:
        if _is_relative_or_equal(path, reserved) or _is_relative_or_equal(reserved, path):
            raise StorageRootError("storage root overlaps a reserved data file")
    for reserved in reserved_dirs:
        if (
            path == reserved
            or _is_relative_or_equal(path, reserved)
            or _is_relative_or_equal(reserved, path)
        ):
            raise StorageRootError("storage root overlaps a reserved data directory")


def _check_root_relationships(
    data_dir: Path, storage_root: Path, staging_root: Path, quarantine_dir: Path
) -> None:
    if not _is_relative_or_equal(data_dir, storage_root) or storage_root == data_dir:
        raise StorageRootError("attachment_storage_root must be inside data_dir")
    if not _is_relative_or_equal(data_dir, staging_root) or staging_root == data_dir:
        raise StorageRootError("attachment_staging_root must be inside data_dir")
    if _is_relative_or_equal(storage_root, staging_root) or _is_relative_or_equal(
        staging_root, storage_root
    ):
        raise StorageRootError("storage and staging roots overlap")
    if quarantine_dir.parent != storage_root:
        raise StorageRootError("quarantine must be a direct child of storage root")
    name = quarantine_dir.name.lower() if _is_windows() else quarantine_dir.name
    if name in (".tmp", "staging"):
        raise StorageRootError("quarantine collides with reserved storage subtree")
    if len(name) == 2 and all(ch in "0123456789abcdef" for ch in name):
        raise StorageRootError("quarantine collides with shard namespace")


def _directory_ancestors(path: Path) -> set[tuple[int, int]]:
    return {_identity(part.lstat()) for part in (path, *path.parents)}


def preflight_storage_roots(settings) -> StorageLayout:
    """Check the full lexical configuration before startup can create directories."""
    data_dir = Path(settings.data_dir)
    storage_root = Path(settings.attachment_storage_root)
    staging_root = Path(settings.attachment_staging_root)
    quarantine_dir = Path(settings.attachment_quarantine_dir)
    temp_dir = storage_root / ".tmp"
    _check_root_relationships(data_dir, storage_root, staging_root, quarantine_dir)
    reserved_files, reserved_dirs = _reserved_paths(settings)
    for path in (storage_root, staging_root):
        _assert_not_reserved(path, reserved_files, reserved_dirs)

    roots = (data_dir, storage_root, staging_root, quarantine_dir, temp_dir)
    try:
        db_path = _sqlite_db_path(settings.database_url)
        if db_path is not None:
            _directory_chain(db_path.parent, allow_missing=True)
            try:
                db_info = db_path.lstat()
            except FileNotFoundError:
                pass
            else:
                if _is_link(db_info) or not stat.S_ISREG(db_info.st_mode):
                    raise StorageRootError("SQLite database path is not a regular file")
        existing = [_directory_chain(path, allow_missing=True) for path in roots]
        canonical = tuple(
            parent.resolve(strict=True) / path.relative_to(parent)
            for path, parent in zip(roots, existing, strict=True)
        )
        _check_root_relationships(*canonical[:4])
        for path in canonical[1:3]:
            _assert_not_reserved(
                path, [item.resolve() for item in reserved_files],
                [item.resolve() for item in reserved_dirs],
            )
        for root_index, other_index in ((1, 2), (2, 1), (3, 4), (4, 3)):
            root = roots[root_index]
            if root == existing[root_index] and _identity(root.lstat()) in _directory_ancestors(
                existing[other_index]
            ):
                raise StorageRootError("storage directories overlap by directory identity")
        if not _same_volume(existing[1:]):
            raise StorageRootError("attachment roots are on different volumes")
    except OSError as exc:
        raise StorageRootError(f"cannot inspect storage directory ({exc.errno})") from None
    return StorageLayout(*roots)


def _roots(layout: StorageLayout) -> tuple[Path, ...]:
    return (
        layout.data_dir, layout.storage_root, layout.staging_root, layout.quarantine_dir,
        layout.temp_dir,
    )


def validate_storage_roots(settings) -> StorageLayout:
    layout = preflight_storage_roots(settings)
    roots = _roots(layout)
    try:
        for path in roots:
            _directory_chain(path, allow_missing=True)
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            _directory_chain(path)
        preflight_storage_roots(settings)
        for path in roots:
            _directory_chain(path)
            _mode_700(path)
        identities = tuple(_identity(path.lstat()) for path in roots)
    except OSError as exc:
        raise StorageRootError(f"cannot initialize storage directory ({exc.errno})") from None
    for path in roots[1:4]:
        if len(str(path)) > _WINDOWS_LONG_PATH_WARNING:
            logger.warning("attachment storage path exceeds %d chars", _WINDOWS_LONG_PATH_WARNING)
    return StorageLayout(*roots, root_identities=identities)


def ensure_runtime(layout: StorageLayout) -> None:
    try:
        roots = _roots(layout)
        for path in roots:
            _directory_chain(path)
        if not _same_volume(roots[1:]):
            raise AttachmentStorageError(ATTACHMENT_STORAGE_CROSS_VOLUME)
        if layout.root_identities and tuple(
            _identity(path.lstat()) for path in roots
        ) != layout.root_identities:
            raise StorageRootError("storage directory identity changed")
    except (StorageRootError, OSError) as exc:
        raise AttachmentStorageError(ATTACHMENT_STORAGE_UNAVAILABLE, str(exc)) from exc


def _fsync_dir(path: Path) -> None:
    if _is_windows():
        return
    try:
        _directory_chain(path)
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        raise AttachmentStorageError(
            ATTACHMENT_WRITE_FAILED, f"directory sync failed ({exc.errno})"
        ) from exc


def _fsync_file(fd: int) -> None:
    os.fsync(fd)


@contextlib.contextmanager
def _exclusive_temp(path: Path):
    # A failed exclusive open never confers ownership of the path.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _BINARY, 0o600)
    owned = None
    try:
        try:
            owned = _identity(os.fstat(fd))
            yield fd, owned
        finally:
            os.close(fd)
    except BaseException:
        if owned is not None:
            _unlink_owned(path, owned)
        raise


def _unlink_owned(path: Path, owned: tuple[int, int]) -> None:
    with contextlib.suppress(OSError, StorageRootError):
        _directory_chain(path.parent)
        info = path.lstat()
        if not _is_link(info) and _identity(info) == owned:
            os.unlink(path)


def write_temp(
    layout: StorageLayout,
    payload: bytes | bytearray | memoryview,
    *,
    path: Path | None = None,
) -> TempBlob:
    ensure_runtime(layout)
    temp = Path(path) if path is not None else layout.temp_path()
    if temp.parent != layout.temp_dir or not re.fullmatch(r"[a-f0-9]{32}\.part", temp.name):
        raise AttachmentStorageError(ATTACHMENT_WRITE_FAILED, "invalid temp path")
    view = memoryview(payload)
    try:
        with _exclusive_temp(temp) as (fd, owned):
            write_all(fd, view)
            _fsync_file(fd)
            with _open_regular(temp, on_volume=layout.storage_root) as handle:
                if _identity(os.fstat(handle.fileno())) != owned:
                    raise AttachmentStorageError(ATTACHMENT_WRITE_FAILED, "temp identity changed")
                digest = sha256_stream(handle)
        return TempBlob(path=temp, size=len(view), sha256=digest, identity=owned)
    except OSError as exc:
        raise AttachmentStorageError(
            ATTACHMENT_WRITE_FAILED, f"temp write failed ({exc.errno})"
        ) from exc


def copy_to_temp(layout: StorageLayout, source: Path, *, chunk_size: int = _CHUNK_SIZE) -> TempBlob:
    ensure_runtime(layout)
    source = Path(source)
    if not any(source.is_relative_to(root) for root in (layout.staging_root, layout.quarantine_dir)):
        raise AttachmentStorageError(ATTACHMENT_WRITE_FAILED, "copy source outside staging/quarantine")
    temp = layout.temp_path()
    digest = hashlib.sha256()
    size = 0
    try:
        with (
            _open_regular(source, on_volume=layout.storage_root) as reader,
            _exclusive_temp(temp) as (fd, owned),
        ):
            for chunk in iter_file(reader, chunk_size=chunk_size):
                write_all(fd, chunk)
                digest.update(chunk)
                size += len(chunk)
            _fsync_file(fd)
        return TempBlob(path=temp, size=size, sha256=digest.hexdigest(), identity=owned)
    except (OSError, StorageRootError) as exc:
        raise AttachmentStorageError(ATTACHMENT_WRITE_FAILED, "copy failed") from exc


def _is_busy(exc: OSError) -> bool:
    return _is_windows() and _winerror(exc) in (32, 33)


def _is_cross_volume(exc: OSError) -> bool:
    native = _winerror(exc)
    return native == 17 if native is not None else exc.errno == errno.EXDEV


def _is_target_exists(exc: OSError) -> bool:
    native = _winerror(exc)
    return native in (80, 183) if native is not None else isinstance(exc, FileExistsError)


def _is_unsupported_link(exc: OSError) -> bool:
    native = _winerror(exc)
    if native is not None:
        return native in (1, 50)
    return exc.errno in {
        getattr(errno, "ENOSYS", -1),
        getattr(errno, "ENOTSUP", -1),
        getattr(errno, "EOPNOTSUPP", -1),
    }


def _is_permission(exc: OSError) -> bool:
    native = _winerror(exc)
    return native in (5, 1314) if native is not None else exc.errno in (errno.EACCES, errno.EPERM)


def _classify_io_error(exc: OSError) -> AttachmentStorageError:
    if _is_cross_volume(exc):
        return AttachmentStorageError(ATTACHMENT_STORAGE_CROSS_VOLUME)
    if _is_busy(exc):
        return AttachmentStorageError(ATTACHMENT_WRITE_BUSY)
    if _is_permission(exc):
        return AttachmentStorageError(ATTACHMENT_WRITE_FAILED, "permission denied")
    if _is_unsupported_link(exc):
        return AttachmentStorageError(ATTACHMENT_WRITE_FAILED, "operation unsupported")
    return AttachmentStorageError(ATTACHMENT_WRITE_FAILED)


def retry_windows_busy(
    operation,
    *,
    initial_delay: float | None = None,
    max_delay: float | None = None,
    budget: float | None = None,
):
    """Windows sharing/lock violation 有界重试；其他错误原样抛出。"""
    deadline = time.monotonic() + (WINDOWS_BUSY_BUDGET if budget is None else budget)
    delay = WINDOWS_BUSY_INITIAL_DELAY if initial_delay is None else initial_delay
    max_delay = WINDOWS_BUSY_MAX_DELAY if max_delay is None else max_delay
    while True:
        try:
            return operation()
        except OSError as exc:
            if not _is_busy(exc):
                raise
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AttachmentStorageError(ATTACHMENT_WRITE_BUSY) from None
            time.sleep(min(delay, remaining))
            if time.monotonic() >= deadline:
                raise AttachmentStorageError(ATTACHMENT_WRITE_BUSY) from None
            delay = min(delay * 2, max_delay)


def _fence(lock_guard: LockGuard | None, storage_key: str) -> None:
    if not isinstance(lock_guard, LockGuard) or lock_guard.lease_for(storage_key) is None:
        raise StorageLeaseLost("an acquired StorageKeyLock for this key is required")
    lock_guard.verify_all()


def _mutate(
    layout, storage_key, lock_guard, operation, source, target=None, *, owned=None, on_error=None,
):
    def attempt():
        ensure_runtime(layout)
        info = _file_info(source, on_volume=layout.storage_root)
        if owned is not None and _identity(info) != owned:
            raise AttachmentStorageError(ATTACHMENT_WRITE_FAILED, "source identity changed")
        if target is not None:
            _directory_chain(target.parent)
            if not _same_volume((layout.storage_root, target.parent)):
                raise AttachmentStorageError(ATTACHMENT_STORAGE_CROSS_VOLUME)
        _fence(lock_guard, storage_key)
        try:
            if target is None:
                return operation(source)
            return operation(source, target)
        except OSError as exc:
            if on_error is None or _is_busy(exc):
                raise
            return on_error(exc)

    return retry_windows_busy(attempt)


def _link_or_rename(layout, key, guard, source, target, owned) -> str:
    def link_error(exc: OSError) -> str:
        if _is_target_exists(exc):
            return "exists"
        if not _is_unsupported_link(exc) or _is_permission(exc):
            raise _classify_io_error(exc) from exc
        if not _is_windows():
            raise AttachmentStorageError(
                ATTACHMENT_STORAGE_UNAVAILABLE, "hard link unsupported"
            ) from exc
        return "rename"

    def rename_error(exc: OSError) -> str:
        if _is_target_exists(exc):
            return "exists"
        raise _classify_io_error(exc) from exc

    outcome = _mutate(layout, key, guard, os.link, source, target, owned=owned, on_error=link_error)
    if outcome == "rename":
        return _mutate(
            layout, key, guard, os.rename, source, target, owned=owned, on_error=rename_error,
        ) or "renamed"
    return outcome or "linked"


def _verify_existing(
    layout: StorageLayout, final: Path, key: str, expected_size: int
) -> PublishResult:
    try:
        with _open_regular(final, on_volume=layout.storage_root) as handle:
            size = os.fstat(handle.fileno()).st_size
            if size == expected_size and sha256_stream(handle) == key:
                return PublishResult(path=final, size=size, reused=True)
    except (AttachmentStorageError, StorageRootError, OSError) as exc:
        if getattr(exc, "code", None) == ATTACHMENT_STORAGE_CROSS_VOLUME:
            raise
        raise AttachmentStorageError(ATTACHMENT_KEY_COLLISION, "untrusted target") from exc
    raise AttachmentStorageError(ATTACHMENT_KEY_COLLISION)


def _prepare_shard(layout, final, key, guard) -> None:
    try:
        parent = _directory_chain(final.parent, allow_missing=True)
        if not _same_volume((parent, layout.storage_root)):
            raise AttachmentStorageError(ATTACHMENT_STORAGE_CROSS_VOLUME)
        _fence(guard, key)
        final.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        _directory_chain(final.parent)
    except (OSError, StorageRootError) as exc:
        raise AttachmentStorageError(ATTACHMENT_WRITE_FAILED, "invalid shard") from exc


def _fsync_parent_chain(path: Path, stop: Path) -> None:
    if _is_windows():
        return
    current = path
    while True:
        _fsync_dir(current)
        if current == stop or current.parent == current:
            break
        current = current.parent


def publish_no_clobber(
    layout: StorageLayout,
    temp_blob: TempBlob,
    storage_key: str,
    *,
    lock_guard: LockGuard | None,
) -> PublishResult:
    _fence(lock_guard, storage_key)
    ensure_runtime(layout)
    temp = temp_blob.path
    if temp.parent != layout.temp_dir:
        raise AttachmentStorageError(ATTACHMENT_WRITE_FAILED, "temp path outside .tmp")
    owned = temp_blob.identity
    try:
        with _open_regular(temp, on_volume=layout.storage_root) as handle:
            info = os.fstat(handle.fileno())
            if _identity(info) != owned:
                raise AttachmentStorageError(ATTACHMENT_WRITE_FAILED, "temp identity changed")
            if sha256_stream(handle) != storage_key:
                raise AttachmentStorageError(ATTACHMENT_HASH_MISMATCH)

        final = layout.final_path(storage_key)
        _prepare_shard(layout, final, storage_key, lock_guard)
        try:
            final.lstat()
        except FileNotFoundError:
            outcome = _link_or_rename(layout, storage_key, lock_guard, temp, final, owned)
        else:
            outcome = "exists"
        if outcome == "exists":
            result = _verify_existing(layout, final, storage_key, info.st_size)
            _fsync_parent_chain(final.parent, layout.storage_root)
            return result

        try:
            size = verify_blob(layout, storage_key, expected_size=info.st_size)
        except (AttachmentStorageError, OSError) as exc:
            try:
                move_to_quarantine(layout, storage_key, task_id=None, lock_guard=lock_guard)
            except (AttachmentStorageError, StorageLeaseLost, OSError):
                logger.error("failed to quarantine corrupt publish; evidence preserved")
            raise AttachmentStorageError(ATTACHMENT_WRITE_CORRUPTED) from exc
        _fsync_parent_chain(final.parent, layout.storage_root)
        return PublishResult(path=final, size=size, reused=False)
    except (OSError, StorageRootError) as exc:
        raise AttachmentStorageError(ATTACHMENT_WRITE_FAILED, "publication failed") from exc
    finally:
        _unlink_owned(temp, owned)


def open_verified_blob(
    layout: StorageLayout,
    storage_key: str,
    *,
    expected_size: int | None = None,
) -> BinaryIO:
    """只打开正式 blob 一次；同句柄完成 size/hash 校验后 ``seek(0)`` 交给调用方。"""
    if not is_valid_storage_key(storage_key):
        raise AttachmentStorageError(ATTACHMENT_BLOB_MISSING, "invalid key")
    ensure_runtime(layout)
    path = layout.final_path(storage_key)
    try:
        # 句柄由调用方持有直到流式输出结束，不能交给 with 块自动关闭。
        handle = _open_regular(path, on_volume=layout.storage_root)
    except FileNotFoundError:
        raise AttachmentStorageError(ATTACHMENT_BLOB_MISSING) from None
    except (StorageRootError, OSError) as exc:
        raise AttachmentStorageError(ATTACHMENT_STORAGE_UNAVAILABLE, "open failed") from exc
    try:
        size = os.fstat(handle.fileno()).st_size
        if expected_size is not None and size != expected_size:
            raise AttachmentStorageError(ATTACHMENT_BLOB_CORRUPTED, "size mismatch")
        digest = sha256_stream(handle)
        if digest != storage_key:
            raise AttachmentStorageError(ATTACHMENT_BLOB_CORRUPTED, "hash mismatch")
        handle.seek(0)
        return handle
    except BaseException:
        handle.close()
        raise


def verify_blob(
    layout: StorageLayout,
    storage_key: str,
    *,
    expected_size: int | None = None,
) -> int:
    handle = open_verified_blob(layout, storage_key, expected_size=expected_size)
    try:
        return os.fstat(handle.fileno()).st_size
    finally:
        handle.close()


def _quarantine_slot(layout: StorageLayout, path: Path, key: str) -> Path:
    prefix, _, suffix = path.name.partition(".")
    try:
        valid = str(uuid.UUID(suffix)) == suffix
    except ValueError:
        valid = False
    if path.parent != layout.quarantine_dir or prefix != key or not valid:
        raise AttachmentStorageError(ATTACHMENT_WRITE_FAILED, "invalid quarantine slot")
    return path


def move_to_quarantine(
    layout: StorageLayout,
    storage_key: str,
    *,
    task_id: uuid.UUID | str | None,
    lock_guard: LockGuard | None = None,
) -> Path:
    _fence(lock_guard, storage_key)
    ensure_runtime(layout)
    slot_id = uuid.uuid4() if task_id is None else task_id
    target = _quarantine_slot(
        layout, layout.quarantine_dir / f"{storage_key}.{slot_id}", storage_key
    )
    source = layout.final_path(storage_key)
    try:
        owned = _identity(_file_info(source, on_volume=layout.storage_root))
        outcome = _link_or_rename(layout, storage_key, lock_guard, source, target, owned)
        if outcome == "exists":
            raise AttachmentStorageError(ATTACHMENT_KEY_COLLISION)
        if outcome == "linked":
            # Preserve both names if the quarantine link cannot be made durable or
            # ownership changes between link and source unlink.
            _fsync_dir(target.parent)
            _mutate(layout, storage_key, lock_guard, os.unlink, source, owned=owned)
        _fsync_dir(source.parent)
        return target
    except (OSError, StorageRootError) as exc:
        raise AttachmentStorageError(ATTACHMENT_WRITE_FAILED, "quarantine move failed") from exc


def restore_from_quarantine(
    layout: StorageLayout,
    source: Path,
    storage_key: str,
    *,
    lock_guard: LockGuard | None,
) -> PublishResult:
    _fence(lock_guard, storage_key)
    ensure_runtime(layout)
    source = _quarantine_slot(layout, Path(source), storage_key)
    temp = copy_to_temp(layout, source)
    try:
        if temp.sha256 != storage_key:
            raise AttachmentStorageError(ATTACHMENT_HASH_MISMATCH)
        return publish_no_clobber(layout, temp, storage_key, lock_guard=lock_guard)
    finally:
        _unlink_owned(temp.path, temp.identity)


def delete_path(
    layout: StorageLayout, path: Path, storage_key: str, *, lock_guard: LockGuard | None = None
) -> bool:
    _fence(lock_guard, storage_key)
    ensure_runtime(layout)
    path = Path(path)
    if path != layout.final_path(storage_key):
        _quarantine_slot(layout, path, storage_key)
    try:
        owned = _identity(_file_info(path, on_volume=layout.storage_root))
        _mutate(layout, storage_key, lock_guard, os.unlink, path, owned=owned)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise _classify_io_error(exc) from exc
    except StorageRootError as exc:
        raise AttachmentStorageError(ATTACHMENT_STORAGE_UNAVAILABLE, str(exc)) from exc
    _fsync_dir(path.parent)
    return True


def delete_blob(
    layout: StorageLayout, storage_key: str, *, lock_guard: LockGuard | None = None
) -> bool:
    return delete_path(layout, layout.final_path(storage_key), storage_key, lock_guard=lock_guard)
