"""附件物理存储与存储根启动校验（B1-T01/T02，真实文件系统）。

覆盖：默认配置/路径派生、重叠/越界/链接拒绝、同卷校验、SHA-256、分片、
临时写、no-clobber 发布（复用/冲突/并发/发布后损坏）、F12 错误分类、
同句柄校验读取、quarantine 移动/恢复/删除。
"""

from __future__ import annotations

import errno
import os
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from threading import Barrier, Thread
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.db.session import create_engine_from_url
from app.db.storage_lock import SQLiteStorageKeyLock, new_owner
from app.models import StorageLockORM
from app.services import attachment_storage as storage
from app.services.attachment_storage import (
    ATTACHMENT_HASH_MISMATCH,
    ATTACHMENT_KEY_COLLISION,
    ATTACHMENT_STORAGE_CROSS_VOLUME,
    ATTACHMENT_STORAGE_UNAVAILABLE,
    ATTACHMENT_WRITE_BUSY,
    ATTACHMENT_WRITE_CORRUPTED,
    ATTACHMENT_WRITE_FAILED,
    AttachmentStorageError,
    StorageRootError,
    validate_storage_roots,
)


def _settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "database_url": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        "data_dir": tmp_path / "data",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux real filesystem mount required")
def test_t01_linux_lifespan_rejects_real_separate_mount(tmp_path: Path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    mount = Path("/dev/shm")
    if not mount.is_mount() or mount.stat().st_dev == tmp_path.stat().st_dev:
        pytest.skip("no distinct /dev/shm filesystem for application volume check")
    source = tmp_path / "storage"
    source.mkdir()
    source_file = source / "keep.bin"
    source_file.write_bytes(b"existing storage content")
    source_hash = storage.sha256_file(source_file)
    db = tmp_path / "test.db"
    with tempfile.TemporaryDirectory(dir=mount, prefix="explainlab-t01-") as target:
        staging = Path(target) / "not-created"
        common_root = Path(os.path.commonpath((source, staging)))
        settings = _settings(
            tmp_path, data_dir=common_root, attachment_storage_root=source,
            attachment_staging_root=staging,
        )
        with (
            pytest.raises(StorageRootError, match="attachment roots are on different volumes"),
            TestClient(create_app(settings)),
        ):
            pytest.fail("separate physical mounts reached application startup")
        assert set(tmp_path.iterdir()) == {source}
        assert set(source.iterdir()) == {source_file}
        assert storage.sha256_file(source_file) == source_hash
        assert not db.exists()
        assert not list(Path(target).iterdir())
        print(f"distinct devices {source.stat().st_dev}, {mount.stat().st_dev}; "
              f"source SHA-256={source_hash}")


def _layout(tmp_path: Path) -> storage.StorageLayout:
    layout = validate_storage_roots(_settings(tmp_path))
    engine = create_engine_from_url(f"sqlite:///{(layout.data_dir / 'test-lock.db').as_posix()}")
    try:
        StorageLockORM.__table__.create(engine)
    finally:
        engine.dispose()
    return layout


@contextmanager
def _guard(layout, key, *, ttl=60):
    engine = create_engine_from_url(f"sqlite:///{(layout.data_dir / 'test-lock.db').as_posix()}")
    manager = SQLiteStorageKeyLock(sessionmaker(engine), heartbeat_seconds=0)
    try:
        guard = manager.acquire_many([key], new_owner(), ttl_seconds=ttl)
        assert guard is not None
        with guard:
            yield guard
    finally:
        engine.dispose()


def _publish_temp(layout, temp, key):
    with _guard(layout, key) as guard:
        return storage.publish_no_clobber(layout, temp, key, lock_guard=guard)


def _publish(layout: storage.StorageLayout, payload: bytes, key: str | None = None):
    key = key or storage.sha256_bytes(payload)
    temp = storage.write_temp(layout, payload)
    return _publish_temp(layout, temp, key)


@pytest.mark.parametrize(
    "failure, expected_link, expected_rename, source_remains",
    [
        ("preflight", 0, 0, True),
        ("unsupported", 1, 1, False),
        ("permission", 1, 0, True),
        ("unknown", 1, 0, True),
        ("rename-exists", 1, 1, True),
    ],
)
def test_f12_only_link_syscall_may_authorize_fallback(
    tmp_path, monkeypatch, failure, expected_link, expected_rename, source_remains,
):
    layout = _layout(tmp_path)
    published = _publish(layout, b"original")
    key = published.path.name
    task_id = uuid.uuid4()
    target = layout.quarantine_dir / f"{key}.{task_id}"
    if failure == "rename-exists":
        target.write_bytes(b"previous generation")
    counts = {"link": 0, "rename": 0, "metadata": 0}
    actual_info = storage._file_info
    actual_rename = os.rename

    def windows_error(code):
        error = OSError(errno.EIO, "injected Windows operation")
        error.winerror = code
        return error

    def file_info(path, *, on_volume):
        counts["metadata"] += 1
        if failure == "preflight" and counts["metadata"] == 2:
            raise windows_error(50)
        return actual_info(path, on_volume=on_volume)

    def link(source, destination):
        counts["link"] += 1
        raise windows_error({"permission": 5, "unknown": 1234}.get(failure, 50))

    def rename(source, destination):
        counts["rename"] += 1
        if failure == "rename-exists":
            raise windows_error(183)
        actual_rename(source, destination)

    monkeypatch.setattr(storage, "_is_windows", lambda: True)
    monkeypatch.setattr(storage, "_file_info", file_info)
    monkeypatch.setattr(storage.os, "link", link)
    monkeypatch.setattr(storage.os, "rename", rename)
    with _guard(layout, key) as guard:
        if source_remains:
            with pytest.raises(AttachmentStorageError) as error:
                storage.move_to_quarantine(layout, key, task_id=task_id, lock_guard=guard)
            assert error.value.code == (
                ATTACHMENT_KEY_COLLISION if failure == "rename-exists" else ATTACHMENT_WRITE_FAILED
            )
        else:
            assert storage.move_to_quarantine(layout, key, task_id=task_id, lock_guard=guard) == target
    assert (counts["link"], counts["rename"]) == (expected_link, expected_rename)
    assert published.path.exists() is source_remains
    if source_remains:
        assert published.path.read_bytes() == b"original"
    if failure == "rename-exists":
        assert target.read_bytes() == b"previous generation"
    elif not source_remains:
        assert target.read_bytes() == b"original"


@pytest.mark.parametrize("same_path", [False, True])
@pytest.mark.parametrize("driver_suffix", ["", "+pysqlite"])
def test_lifespan_rejects_missing_sqlite_db_path_as_storage_root(
    tmp_path, same_path, driver_suffix,
):
    from fastapi.testclient import TestClient

    from app.main import create_app

    data_dir = tmp_path / "data"
    db_path = data_dir / "db-not-created"
    storage_root = db_path if same_path else db_path / "attachments"
    settings = _settings(
        tmp_path, data_dir=data_dir,
        database_url=f"sqlite{driver_suffix}:///{db_path.as_posix()}?timeout=3",
        attachment_storage_root=storage_root,
    )
    with pytest.raises(StorageRootError, match="reserved data file"), TestClient(create_app(settings)):
        pytest.fail("startup must reject this reserved-file overlap")
    assert not data_dir.exists()
    assert not db_path.exists()


def test_sqlite_db_reserved_path_allows_independent_storage_roots(tmp_path):
    data_dir = tmp_path / "data"
    db_path = data_dir / "db-not-created"
    settings = _settings(
        tmp_path, data_dir=data_dir, database_url=f"sqlite:///{db_path.as_posix()}",
        attachment_storage_root=data_dir / "dedicated-attachments",
    )
    layout = validate_storage_roots(settings)
    assert layout.storage_root.is_dir()
    assert not db_path.exists()


def test_sqlite_db_parent_symlink_or_junction_is_rejected_before_mkdir(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    alias = data_dir / "redirected-db-parent"
    try:
        alias.symlink_to(target, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(alias), str(target)],
            check=False, capture_output=True,
        )
        if result.returncode != 0:
            pytest.skip("cannot create a Windows junction or symlink")
    settings = _settings(
        tmp_path, data_dir=data_dir, database_url=f"sqlite:///{(alias / 'app.db').as_posix()}",
    )
    with pytest.raises(StorageRootError, match="not a real directory"):
        validate_storage_roots(settings)
    assert not (data_dir / "attachments").exists()
    assert not (target / "app.db").exists()


def test_sqlite_db_parent_reparse_flag_rejected_before_side_effects(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    db_parent = data_dir / "redirected-db-parent"
    db_parent.mkdir(parents=True)
    original = Path.lstat

    def lstat(path):
        info = original(path)
        if path == db_parent:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    monkeypatch.setattr(Path, "lstat", lstat)
    settings = _settings(
        tmp_path, data_dir=data_dir, database_url=f"sqlite:///{(db_parent / 'app.db').as_posix()}",
    )
    with pytest.raises(StorageRootError, match="not a real directory"):
        validate_storage_roots(settings)
    assert not (data_dir / "attachments").exists()
    assert not (db_parent / "app.db").exists()


# --- T01：配置与根校验 -------------------------------------------------------


def test_frozen_defaults_are_derived_from_data_dir(tmp_path: Path):
    settings = _settings(tmp_path)
    assert settings.attachment_storage_root == (tmp_path / "data" / "attachments").resolve()
    assert settings.attachment_staging_root == (tmp_path / "data" / "import-staging").resolve()
    assert settings.attachment_quarantine_dir == (
        tmp_path / "data" / "attachments" / "_quarantine"
    ).resolve()
    assert settings.attachment_max_bytes == 10 * 1024 * 1024
    assert settings.attachment_import_max_count == 100
    assert settings.attachment_import_max_total_bytes == 100 * 1024 * 1024
    assert settings.staging_grace_seconds == 86400
    assert settings.storage_lock_ttl_seconds == 60
    assert settings.storage_lock_heartbeat_seconds == 15
    assert settings.storage_lock_wait_seconds == 10
    assert settings.gc_max_attempts == 8
    assert settings.gc_retry_base_seconds == 60
    assert settings.gc_retry_max_seconds == 21600
    assert settings.gc_quarantine_seconds == 86400
    assert settings.orphan_scan_interval_seconds == 300
    assert "image/png" in settings.attachment_mime_allowlist
    assert "image/svg+xml" not in settings.attachment_mime_allowlist


def test_validate_creates_real_directories_and_reports_same_volume(tmp_path: Path):
    layout = _layout(tmp_path)
    assert layout.storage_root.is_dir()
    assert layout.staging_root.is_dir()
    assert layout.quarantine_dir.is_dir()
    assert layout.temp_dir.is_dir()
    assert layout.quarantine_dir.parent == layout.storage_root
    storage.ensure_runtime(layout)


def test_relative_root_resolves_against_data_dir(tmp_path: Path):
    settings = _settings(
        tmp_path,
        attachment_storage_root="store/attachments",
        attachment_staging_root="store/staging",
    )
    assert settings.attachment_storage_root == (tmp_path / "data" / "store" / "attachments").resolve()
    assert settings.attachment_staging_root == (tmp_path / "data" / "store" / "staging").resolve()


@pytest.mark.parametrize(
    "overrides",
    [
        {"attachment_storage_root": "../escape"},
        {"attachment_storage_root": ".."},
        {"attachment_staging_root": "../escape"},
        {"attachment_quarantine_dir": "../q"},
    ],
)
def test_parent_escape_rejected(tmp_path: Path, overrides):
    with pytest.raises(ValidationError):
        _settings(tmp_path, **overrides)


def test_root_outside_data_dir_rejected(tmp_path: Path):
    with pytest.raises(ValidationError):
        _settings(tmp_path, attachment_storage_root=tmp_path / "outside")


def test_storage_and_staging_overlap_rejected(tmp_path: Path):
    with pytest.raises(ValidationError):
        _settings(
            tmp_path,
            attachment_storage_root="attachments",
            attachment_staging_root="attachments/staging",
        )
    with pytest.raises(ValidationError):
        _settings(
            tmp_path,
            attachment_storage_root="attachments",
            attachment_staging_root="attachments",
        )


def test_quarantine_must_be_direct_child_of_storage(tmp_path: Path):
    with pytest.raises(ValidationError):
        _settings(
            tmp_path,
            attachment_storage_root="attachments",
            attachment_quarantine_dir="quarantine",
        )
    with pytest.raises(ValidationError):
        _settings(
            tmp_path,
            attachment_storage_root="attachments",
            attachment_quarantine_dir="attachments/deep/q",
        )


def test_quarantine_name_collides_with_shard_namespace_rejected(tmp_path: Path):
    with pytest.raises(ValidationError):
        _settings(
            tmp_path,
            attachment_storage_root="attachments",
            attachment_quarantine_dir="attachments/ab",
        )


def test_directory_creation_failure_fails_closed(tmp_path: Path):
    settings = _settings(tmp_path)
    settings.data_dir.mkdir(parents=True)
    settings.attachment_storage_root.write_bytes(b"not a directory")
    with pytest.raises(StorageRootError):
        validate_storage_roots(settings)
    # 失败不删除已有文件，也不降级到临时目录。
    assert settings.attachment_storage_root.is_file()


def test_cross_volume_detected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    settings = _settings(tmp_path)

    def fake_st_dev(path: Path) -> int:
        return 2 if path.name == "import-staging" else 1

    monkeypatch.setattr(storage, "_st_dev", fake_st_dev)
    with pytest.raises(StorageRootError):
        validate_storage_roots(settings)


def test_reserved_data_file_overlap_rejected(tmp_path: Path):
    settings = _settings(
        tmp_path,
        attachment_storage_root="attachments",
        attachment_staging_root="staging",
    )
    # 把 SQLite DB 放进正式根：启动必须拒绝，而不是让 blob 与 DB 混放。
    settings.database_url = f"sqlite:///{(settings.attachment_storage_root / 'x.db').as_posix()}"
    with pytest.raises(StorageRootError):
        validate_storage_roots(settings)


def _make_junction(link: Path, target: Path) -> bool:
    if sys.platform != "win32":
        return False
    try:
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    return completed.returncode == 0 and link.exists()


def test_link_or_junction_root_rejected(tmp_path: Path):
    layout = _layout(tmp_path)
    target = layout.data_dir / "real-staging"
    target.mkdir()
    link = layout.data_dir / "linked-staging"
    created = _make_junction(link, target)
    if not created:
        try:
            os.symlink(target, link, target_is_directory=True)
            created = True
        except (OSError, NotImplementedError):
            created = False
    if not created:
        pytest.skip("cannot create symlink/junction in this environment")
    hijacked = replace(layout, staging_root=link)
    with pytest.raises(AttachmentStorageError) as exc:
        storage.ensure_runtime(hijacked)
    assert exc.value.code == ATTACHMENT_STORAGE_UNAVAILABLE
    assert target.is_dir()


# --- T02：hash / 分片 / 临时写 / 发布 ---------------------------------------


def test_sha256_known_vector(tmp_path: Path):
    assert storage.sha256_bytes(b"hello") == (
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )
    path = tmp_path / "x.bin"
    path.write_bytes(b"hello")
    assert storage.sha256_file(path) == storage.sha256_bytes(b"hello")
    with path.open("rb") as handle:
        assert storage.sha256_stream(handle) == storage.sha256_bytes(b"hello")


def test_key_validation_and_shards(tmp_path: Path):
    key = "ab" + "cd" + "0" * 60
    assert storage.is_valid_storage_key(key)
    assert storage.shard_parts(key) == ("ab", "cd")
    assert storage.final_path_for(tmp_path, key) == tmp_path / "ab" / "cd" / key
    for bad in ("", "AB" + "0" * 62, "0" * 63, "g" * 64, "../" + "0" * 61):
        assert not storage.is_valid_storage_key(bad)
        with pytest.raises(AttachmentStorageError):
            storage.shard_parts(bad)


def test_write_temp_hashes_actual_bytes_and_no_residue_on_success(tmp_path: Path):
    layout = _layout(tmp_path)
    payload = b"hello attachment"
    temp = storage.write_temp(layout, payload)
    assert temp.path.is_file()
    assert temp.size == len(payload)
    assert temp.sha256 == storage.sha256_bytes(payload)
    temp.path.unlink()
    assert list(layout.temp_dir.iterdir()) == []


def test_publish_new_blob_and_reuse_same_hash(tmp_path: Path):
    layout = _layout(tmp_path)
    payload = b"same content"
    key = storage.sha256_bytes(payload)
    first = _publish(layout, payload, key)
    assert first.reused is False
    assert first.path == layout.final_path(key)
    assert first.path.read_bytes() == payload
    assert first.size == len(payload)
    assert list(layout.temp_dir.iterdir()) == []

    second = _publish(layout, payload, key)
    assert second.reused is True
    assert second.path == first.path
    assert storage.sha256_file(second.path) == key


def test_publish_collision_never_overwrites(tmp_path: Path):
    layout = _layout(tmp_path)
    original = b"original"
    key = storage.sha256_bytes(original)
    final = layout.final_path(key)
    final.parent.mkdir(parents=True, exist_ok=True)
    final.write_bytes(b"tampered existing blob")

    with pytest.raises(AttachmentStorageError) as exc:
        _publish(layout, original, key)
    assert exc.value.code == ATTACHMENT_KEY_COLLISION
    assert final.read_bytes() == b"tampered existing blob"
    assert list(layout.temp_dir.iterdir()) == []


def test_publish_requires_lock_guard(tmp_path: Path):
    layout = _layout(tmp_path)
    temp = storage.write_temp(layout, b"x")
    with pytest.raises(RuntimeError):
        storage.publish_no_clobber(layout, temp, storage.sha256_bytes(b"x"), lock_guard=None)


def test_publish_concurrent_same_key(tmp_path: Path):
    layout = _layout(tmp_path)
    payload = b"concurrent content"
    key = storage.sha256_bytes(payload)
    barrier = Barrier(6)
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            barrier.wait(timeout=5)
            _publish(layout, payload, key)
        except BaseException as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [Thread(target=worker) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert errors == []
    final = layout.final_path(key)
    assert final.read_bytes() == payload
    assert list(layout.temp_dir.iterdir()) == []


class _Busy(OSError):
    winerror = 32


def test_f12_cross_volume(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    layout = _layout(tmp_path)
    payload = b"cross"
    key = storage.sha256_bytes(payload)
    temp = storage.write_temp(layout, payload)

    def fake_link(*_args, **_kwargs):
        raise OSError(errno.EXDEV, "cross device")

    monkeypatch.setattr(storage.os, "link", fake_link)
    with pytest.raises(AttachmentStorageError) as exc:
        _publish_temp(layout, temp, key)
    assert exc.value.code == ATTACHMENT_STORAGE_CROSS_VOLUME
    assert not layout.final_path(key).exists()


def test_f12_permission_denied_fails_without_rename(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    layout = _layout(tmp_path)
    payload = b"perm"
    key = storage.sha256_bytes(payload)
    temp = storage.write_temp(layout, payload)
    rename_called = False

    def fake_link(*_args, **_kwargs):
        raise PermissionError(errno.EACCES, "denied")

    def fake_rename(*_args, **_kwargs):
        nonlocal rename_called
        rename_called = True
        raise AssertionError("rename must not be used for permission denied")

    monkeypatch.setattr(storage.os, "link", fake_link)
    monkeypatch.setattr(storage.os, "rename", fake_rename)
    with pytest.raises(AttachmentStorageError) as exc:
        _publish_temp(layout, temp, key)
    assert exc.value.code == ATTACHMENT_WRITE_FAILED
    assert rename_called is False


def test_f12_busy_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    layout = _layout(tmp_path)
    payload = b"busy then ok"
    key = storage.sha256_bytes(payload)
    temp = storage.write_temp(layout, payload)
    real_link = os.link
    calls = {"n": 0}

    def flaky_link(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _Busy(errno.EACCES, "sharing violation")
        return real_link(src, dst)

    monkeypatch.setattr(storage, "_is_windows", lambda: True)
    monkeypatch.setattr(storage, "WINDOWS_BUSY_INITIAL_DELAY", 0.001)
    monkeypatch.setattr(storage, "WINDOWS_BUSY_MAX_DELAY", 0.001)
    monkeypatch.setattr(storage, "WINDOWS_BUSY_BUDGET", 0.05)
    monkeypatch.setattr(storage.os, "link", flaky_link)
    result = _publish_temp(layout, temp, key)
    assert result.reused is False
    assert calls["n"] >= 2


def test_f12_busy_exhausted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    layout = _layout(tmp_path)
    payload = b"always busy"
    key = storage.sha256_bytes(payload)
    temp = storage.write_temp(layout, payload)

    def fake_link(*_args, **_kwargs):
        raise _Busy(errno.EACCES, "sharing violation")

    monkeypatch.setattr(storage, "_is_windows", lambda: True)
    monkeypatch.setattr(storage, "WINDOWS_BUSY_INITIAL_DELAY", 0.001)
    monkeypatch.setattr(storage, "WINDOWS_BUSY_MAX_DELAY", 0.001)
    monkeypatch.setattr(storage, "WINDOWS_BUSY_BUDGET", 0.01)
    monkeypatch.setattr(storage.os, "link", fake_link)
    with pytest.raises(AttachmentStorageError) as exc:
        _publish_temp(layout, temp, key)
    assert exc.value.code == ATTACHMENT_WRITE_BUSY


def test_f12_busy_budget_prevents_a_new_syscall_after_sleep(monkeypatch: pytest.MonkeyPatch):
    now = 0.0
    attempts = 0

    def sleep(seconds):
        nonlocal now
        now += seconds

    def first_call_is_busy():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _Busy(errno.EACCES, "sharing violation")

    monkeypatch.setattr(storage, "_is_windows", lambda: True)
    monkeypatch.setattr(storage, "time", SimpleNamespace(monotonic=lambda: now, sleep=sleep))

    with pytest.raises(AttachmentStorageError) as exc:
        storage.retry_windows_busy(first_call_is_busy, initial_delay=0.1, budget=0.05)

    assert exc.value.code == ATTACHMENT_WRITE_BUSY
    assert attempts == 1


def test_f12_unsupported_link_posix_fails_without_rename(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    layout = _layout(tmp_path)
    payload = b"unsupported posix"
    key = storage.sha256_bytes(payload)
    temp = storage.write_temp(layout, payload)

    def fake_link(*_args, **_kwargs):
        raise OSError(getattr(errno, "EOPNOTSUPP", errno.ENOSYS), "unsupported")

    monkeypatch.setattr(storage, "_is_windows", lambda: False)
    monkeypatch.setattr(storage.os, "link", fake_link)
    with pytest.raises(AttachmentStorageError) as exc:
        _publish_temp(layout, temp, key)
    assert exc.value.code == ATTACHMENT_STORAGE_UNAVAILABLE
    assert not layout.final_path(key).exists()


def test_f12_unsupported_link_windows_uses_no_clobber_rename(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    layout = _layout(tmp_path)
    payload = b"unsupported windows"
    key = storage.sha256_bytes(payload)
    temp = storage.write_temp(layout, payload)

    def fake_link(*_args, **_kwargs):
        error = OSError(errno.ENOSYS, "not supported")
        error.winerror = 50
        raise error

    monkeypatch.setattr(storage, "_is_windows", lambda: True)
    monkeypatch.setattr(storage.os, "link", fake_link)
    result = _publish_temp(layout, temp, key)
    assert result.reused is False
    assert result.path.read_bytes() == payload
    assert not temp.path.exists()


def test_f12_unknown_io_error_not_downgraded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    layout = _layout(tmp_path)
    payload = b"unknown"
    key = storage.sha256_bytes(payload)
    temp = storage.write_temp(layout, payload)

    def fake_link(*_args, **_kwargs):
        raise OSError(errno.EIO, "unknown")

    monkeypatch.setattr(storage.os, "link", fake_link)
    with pytest.raises(AttachmentStorageError) as exc:
        _publish_temp(layout, temp, key)
    assert exc.value.code == ATTACHMENT_WRITE_FAILED


def test_publish_hash_mismatch_removes_temp(tmp_path: Path):
    layout = _layout(tmp_path)
    temp = storage.write_temp(layout, b"actual")
    with pytest.raises(AttachmentStorageError) as exc:
        _publish_temp(layout, temp, "0" * 64)
    assert exc.value.code == ATTACHMENT_HASH_MISMATCH
    assert not temp.path.exists()


def test_publish_post_verify_corruption_quarantines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    layout = _layout(tmp_path)
    payload = b"corrupt me"
    key = storage.sha256_bytes(payload)
    temp = storage.write_temp(layout, payload)
    real_link = os.link

    def corrupt_after_link(source, target):
        real_link(source, target)
        if target == layout.final_path(key):
            target.write_bytes(b"damaged after link")

    monkeypatch.setattr(storage.os, "link", corrupt_after_link)
    with pytest.raises(AttachmentStorageError) as exc:
        _publish_temp(layout, temp, key)
    assert exc.value.code == ATTACHMENT_WRITE_CORRUPTED
    assert not layout.final_path(key).exists()
    quarantined = list(layout.quarantine_dir.iterdir())
    assert len(quarantined) == 1
    assert quarantined[0].name.startswith(key + ".")


# --- 读取 / quarantine -------------------------------------------------------


def test_open_verified_same_handle_and_close(tmp_path: Path):
    layout = _layout(tmp_path)
    payload = b"stream me"
    key = storage.sha256_bytes(payload)
    _publish(layout, payload, key)
    handle = storage.open_verified_blob(layout, key, expected_size=len(payload))
    try:
        assert handle.read() == payload
        assert handle.closed is False
    finally:
        handle.close()
    assert handle.closed is True


@pytest.mark.skipif(os.name == "nt", reason="Windows 打开文件默认拒绝 rename，句柄路径替换另行取证")
def test_verified_handle_survives_path_replacement(tmp_path: Path):
    layout = _layout(tmp_path)
    payload = b"original bytes"
    key = storage.sha256_bytes(payload)
    result = _publish(layout, payload, key)
    handle = storage.open_verified_blob(layout, key)
    try:
        replacement = layout.temp_dir / "replacement"
        replacement.write_bytes(b"attacker")
        os.replace(result.path, layout.temp_dir / "moved")
        os.replace(replacement, result.path)
        assert handle.read() == payload
    finally:
        handle.close()


def test_open_verified_missing_and_corrupt(tmp_path: Path):
    layout = _layout(tmp_path)
    missing_key = "a" * 64
    with pytest.raises(AttachmentStorageError) as exc:
        storage.open_verified_blob(layout, missing_key)
    assert exc.value.code == "ATTACHMENT_BLOB_MISSING"

    payload = b"good"
    key = storage.sha256_bytes(payload)
    result = _publish(layout, payload, key)
    with pytest.raises(AttachmentStorageError):
        storage.open_verified_blob(layout, key, expected_size=999)
    result.path.write_bytes(b"tampered")
    with pytest.raises(AttachmentStorageError) as exc:
        storage.open_verified_blob(layout, key)
    assert exc.value.code == "ATTACHMENT_BLOB_CORRUPTED"


def test_quarantine_move_restore_and_delete(tmp_path: Path):
    layout = _layout(tmp_path)
    payload = b"gc candidate"
    key = storage.sha256_bytes(payload)
    result = _publish(layout, payload, key)
    task_id = uuid.uuid4()
    with _guard(layout, key) as guard:
        quarantined = storage.move_to_quarantine(layout, key, task_id=task_id, lock_guard=guard)
    assert quarantined == layout.quarantine_dir / f"{key}.{task_id}"
    assert quarantined.read_bytes() == payload
    assert not result.path.exists()

    with _guard(layout, key) as guard:
        restored = storage.restore_from_quarantine(layout, quarantined, key, lock_guard=guard)
    assert restored.path.read_bytes() == payload
    assert quarantined.exists()  # 保留隔离源
    with _guard(layout, key) as guard:
        assert storage.delete_blob(layout, key, lock_guard=guard) is True
        assert not restored.path.exists()
        assert storage.delete_blob(layout, key, lock_guard=guard) is False


def test_quarantine_move_never_overwrites_existing_slot(tmp_path: Path):
    layout = _layout(tmp_path)
    payload = b"slot"
    key = storage.sha256_bytes(payload)
    _publish(layout, payload, key)
    task_id = uuid.uuid4()
    existing = layout.quarantine_dir / f"{key}.{task_id}"
    existing.write_bytes(payload)

    with _guard(layout, key) as guard, pytest.raises(AttachmentStorageError) as exc:
        storage.move_to_quarantine(layout, key, task_id=task_id, lock_guard=guard)
    assert exc.value.code == ATTACHMENT_KEY_COLLISION
    assert existing.read_bytes() == payload
    assert layout.final_path(key).exists()


# --- 启动装配 ---------------------------------------------------------------


def test_lifespan_validates_roots_and_exposes_layout(tmp_path: Path):
    from fastapi.testclient import TestClient

    from app.db.base import Base
    from app.db.session import create_engine_from_url, dispose_db
    from app.main import create_app

    settings = _settings(tmp_path)
    engine = create_engine_from_url(settings.database_url)
    Base.metadata.create_all(engine)
    engine.dispose()
    try:
        with TestClient(create_app(settings)) as client:
            layout = client.app.state.attachment_storage
            assert layout.storage_root.is_dir()
            assert layout.staging_root.is_dir()
            assert layout.quarantine_dir.is_dir()
    finally:
        dispose_db()


def test_lifespan_refuses_invalid_storage_root(tmp_path: Path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    settings = _settings(tmp_path)
    settings.data_dir.mkdir(parents=True)
    settings.attachment_storage_root.write_bytes(b"file blocks directory creation")
    with pytest.raises(StorageRootError), TestClient(create_app(settings)):
        pass


def test_lifespan_refuses_cross_volume(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    settings = _settings(tmp_path)

    def fake_st_dev(path: Path) -> int:
        return 2 if path.name == "import-staging" else 1

    monkeypatch.setattr(storage, "_st_dev", fake_st_dev)
    with pytest.raises(StorageRootError), TestClient(create_app(settings)):
        pass

@pytest.mark.parametrize("operation", ["publish", "restore", "isolate", "delete", "purge"])
@pytest.mark.parametrize("invalid", ["missing", "dummy", "released", "expired", "wrong-key", "token"])
def test_final_mutations_reject_invalid_guards(tmp_path, operation, invalid):
    from sqlalchemy import update

    from app.db.storage_lock import StorageLeaseLost

    layout = _layout(tmp_path)
    payload = b"guarded"
    key = storage.sha256_bytes(payload)
    final = layout.final_path(key)
    if operation in {"isolate", "delete"}:
        _publish(layout, payload)
    temp = storage.write_temp(layout, payload)
    task_id = uuid.uuid4()
    slot = layout.quarantine_dir / f"{key}.{task_id}"
    if operation in {"restore", "purge"}:
        slot.write_bytes(payload)
    guard_key = key if invalid != "wrong-key" else "a" * 64
    with _guard(layout, guard_key) as acquired:
        guard = {"missing": None, "dummy": object()}.get(invalid, acquired)
        if invalid == "released":
            acquired.release()
        if invalid in {"expired", "token"}:
            from datetime import timedelta

            from knowledge_core.domain.entities import utcnow

            engine = create_engine_from_url(
                f"sqlite:///{(layout.data_dir / 'test-lock.db').as_posix()}"
            )
            try:
                with engine.begin() as conn:
                    changes = (
                        {"lease_token": 999} if invalid == "token"
                        else {"lease_expires_at": utcnow() - timedelta(seconds=1)}
                    )
                    conn.execute(
                        update(StorageLockORM).where(StorageLockORM.storage_key == key)
                        .values(**changes)
                    )
            finally:
                engine.dispose()
        with pytest.raises(StorageLeaseLost):
            if operation == "publish":
                storage.publish_no_clobber(layout, temp, key, lock_guard=guard)
            elif operation == "restore":
                storage.restore_from_quarantine(layout, slot, key, lock_guard=guard)
            elif operation == "isolate":
                storage.move_to_quarantine(layout, key, task_id=task_id, lock_guard=guard)
            elif operation == "purge":
                storage.delete_path(layout, slot, key, lock_guard=guard)
            else:
                storage.delete_blob(layout, key, lock_guard=guard)
    assert temp.path.read_bytes() == payload
    assert final.exists() is (operation in {"isolate", "delete"})
    assert slot.exists() is (operation in {"restore", "purge"})


def test_windows_retry_rechecks_fence_after_sharing_violation(tmp_path, monkeypatch):
    from app.db.storage_lock import StorageLeaseLost

    layout = _layout(tmp_path)
    payload = b"lease lost during retry"
    key = storage.sha256_bytes(payload)
    temp = storage.write_temp(layout, payload)
    monkeypatch.setattr(storage, "_is_windows", lambda: True)
    monkeypatch.setattr(storage, "WINDOWS_BUSY_INITIAL_DELAY", 0.001)
    with _guard(layout, key) as guard:
        calls = []

        def busy_then_lease_lost(*_args):
            calls.append(True)
            guard.release()
            raise _Busy(errno.EACCES, "sharing violation")

        monkeypatch.setattr(storage.os, "link", busy_then_lease_lost)
        with pytest.raises(StorageLeaseLost):
            storage.publish_no_clobber(layout, temp, key, lock_guard=guard)
    assert len(calls) == 1
    assert not layout.final_path(key).exists()


def test_settings_to_lifespan_rejects_link_without_writing_target(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    target = tmp_path / "external"
    target.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    link = data / "middle"
    if not _make_junction(link, target):
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            pytest.skip("directory link creation unavailable")
    settings = _settings(
        tmp_path, attachment_storage_root="middle/attachments",
        database_url=f"sqlite:///{(link / 'unexpected' / 'db.sqlite').as_posix()}",
    )
    assert settings.attachment_storage_root == link / "attachments"
    with pytest.raises(StorageRootError), TestClient(create_app(settings)):
        pass
    assert not list(target.iterdir())
    assert not (data / ".explainlab.process.lock").exists()


def test_startup_checks_volume_before_mutating_other_roots(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    settings.attachment_staging_root.mkdir(parents=True)
    monkeypatch.setattr(storage, "_st_dev", lambda p: 2 if p == settings.attachment_staging_root else 1)
    with pytest.raises(StorageRootError):
        validate_storage_roots(settings)
    assert not settings.attachment_storage_root.exists()


def test_read_rejects_path_identity_changed_during_open(tmp_path, monkeypatch):
    layout = _layout(tmp_path)
    payload = b"same hash but different file"
    result = _publish(layout, payload)
    key = storage.sha256_bytes(payload)
    replacement = layout.temp_dir / "replacement"
    replacement.write_bytes(payload)
    real_open = storage.os.open

    def swap_then_open(path, *args, **kwargs):
        if Path(path) == result.path:
            os.replace(replacement, result.path)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(storage.os, "open", swap_then_open)
    with pytest.raises(AttachmentStorageError, match="identity changed"):
        storage.open_verified_blob(layout, key)


def test_runtime_rejects_replaced_root_and_nonregular_blob(tmp_path):
    layout = _layout(tmp_path)
    payload = b"replaced"
    key = storage.sha256_bytes(payload)
    final = layout.final_path(key)
    final.mkdir(parents=True)
    with pytest.raises(AttachmentStorageError, match="not a regular file"):
        storage.open_verified_blob(layout, key)
    with _guard(layout, key) as guard, pytest.raises(
        AttachmentStorageError, match="not a regular file"
    ):
        storage.delete_blob(layout, key, lock_guard=guard)
    layout.quarantine_dir.rename(layout.storage_root / "old-quarantine")
    layout.quarantine_dir.mkdir()
    with pytest.raises(AttachmentStorageError, match="identity changed"):
        storage.ensure_runtime(layout)


def test_quarantine_path_traversal_is_rejected(tmp_path):
    layout = _layout(tmp_path)
    payload = b"path-safe"
    key = storage.sha256_bytes(payload)
    with _guard(layout, key) as guard:
        with pytest.raises(AttachmentStorageError, match="invalid quarantine slot"):
            storage.move_to_quarantine(layout, key, task_id="../outside", lock_guard=guard)
        with pytest.raises(AttachmentStorageError, match="invalid quarantine slot"):
            storage.restore_from_quarantine(
                layout, layout.quarantine_dir / ".." / f"{key}.{uuid.uuid4()}",
                key, lock_guard=guard,
            )


def test_exclusive_temp_collision_never_unlinks_existing(tmp_path):
    layout = _layout(tmp_path)
    temp = layout.temp_path()
    temp.write_bytes(b"already owned")
    with pytest.raises(AttachmentStorageError) as exc:
        storage.write_temp(layout, b"other", path=temp)
    assert isinstance(exc.value.__cause__, FileExistsError)
    assert temp.read_bytes() == b"already owned"


@pytest.mark.parametrize("failure", ["write_all", "_fsync_file"])
def test_exclusive_temp_cleans_only_its_own_file(tmp_path, monkeypatch, failure):
    layout = _layout(tmp_path)
    temp = layout.temp_path()
    other = layout.temp_path()
    other.write_bytes(b"another attempt")

    def fail(*_args):
        raise OSError(errno.EIO, "injected failure")

    monkeypatch.setattr(storage, failure, fail)
    with pytest.raises(AttachmentStorageError):
        storage.write_temp(layout, b"payload", path=temp)
    assert not temp.exists()
    assert other.read_bytes() == b"another attempt"


def test_concurrent_temp_creation_cannot_delete_the_winner(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    layout = _layout(tmp_path)
    path = layout.temp_path()
    barrier = Barrier(2)

    def write(payload):
        barrier.wait(timeout=2)
        try:
            return storage.write_temp(layout, payload, path=path)
        except AttachmentStorageError as exc:
            assert isinstance(exc.__cause__, FileExistsError)
            return None

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(write, (b"first", b"second")))
    winner, = [result for result in results if result is not None]
    assert storage.sha256_file(path) == winner.sha256


@pytest.mark.parametrize("native", [18, 55, 234])
def test_f12_unknown_native_code_never_uses_errno_fallback(tmp_path, monkeypatch, native):
    layout = _layout(tmp_path)
    payload = b"native error"
    key = storage.sha256_bytes(payload)
    temp = storage.write_temp(layout, payload)
    monkeypatch.setattr(storage, "_is_windows", lambda: True)

    def fail(*_args):
        exc = OSError(errno.ENOTSUP, "injected Windows error")
        exc.winerror = native
        raise exc

    def unexpected(*_args):
        pytest.fail("must not fall back for this native error")

    monkeypatch.setattr(storage.os, "link", fail)
    monkeypatch.setattr(storage.os, "rename", unexpected)
    with pytest.raises(AttachmentStorageError) as exc:
        _publish_temp(layout, temp, key)
    assert exc.value.code == ATTACHMENT_WRITE_FAILED
    assert not layout.final_path(key).exists()
    assert not temp.path.exists()


@pytest.mark.parametrize("fail_at", ["open", "fsync"])
def test_directory_sync_error_is_reported_and_blob_is_left_for_orp(tmp_path, monkeypatch, fail_at):
    layout = _layout(tmp_path)
    payload = b"blob before directory sync"
    key = storage.sha256_bytes(payload)
    temp = storage.write_temp(layout, payload)
    real_fsync, real_open, real_close = os.fsync, os.open, os.close
    sentinel = 123456
    closed = []

    def open_dir(path, flags, *args, **kwargs):
        if Path(path) == layout.final_path(key).parent:
            if fail_at == "open":
                raise OSError(errno.EIO, "directory open")
            return sentinel
        return real_open(path, flags, *args, **kwargs)

    def sync(fd):
        if fd == sentinel:
            raise OSError(errno.EIO, "directory fsync")
        return real_fsync(fd)

    def close(fd):
        if fd == sentinel:
            closed.append(fd)
            return
        real_close(fd)

    monkeypatch.setattr(storage, "_is_windows", lambda: False)
    monkeypatch.setattr(storage.os, "open", open_dir)
    monkeypatch.setattr(storage.os, "fsync", sync)
    monkeypatch.setattr(storage.os, "close", close)
    with pytest.raises(AttachmentStorageError, match="directory sync failed"):
        _publish_temp(layout, temp, key)
    assert layout.final_path(key).read_bytes() == payload
    assert not temp.path.exists()
    assert closed == ([sentinel] if fail_at == "fsync" else [])


def test_lifespan_assembles_gc_settings_and_transaction(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    settings = _settings(tmp_path, gc_max_attempts=2, gc_quarantine_seconds=90000)
    engine = create_engine_from_url(settings.database_url)
    from app.db.base import Base

    Base.metadata.create_all(engine)
    engine.dispose()
    from time import monotonic

    from knowledge_core.domain.entities import GcTask

    with TestClient(create_app(settings)) as client:
        state = client.app.state

        def work(session):
            repo = state.gc_task_repository_factory(session)
            assert repo.max_attempts == 2
            assert repo.quarantine_period.total_seconds() == 90000
            task = repo.save_task(GcTask(storage_key="a" * 64, attempts=2))
            assert repo.claim(task.id, owner="worker", lease_ttl_seconds=60) is None
            return task.id

        task_id = state.gc_task_write_transaction(work, deadline=monotonic() + 2)
        stored = state.gc_task_write_transaction(
            lambda session: state.gc_task_repository_factory(session).get_task(task_id),
            deadline=monotonic() + 2,
        )
        assert stored.attempts == 2


def test_publish_does_not_unlink_replacement_at_temp_path(tmp_path):
    layout = _layout(tmp_path)
    payload = b"original temporary content"
    key = storage.sha256_bytes(payload)
    temp = storage.write_temp(layout, payload)
    original = layout.temp_path()
    temp.path.rename(original)
    temp.path.write_bytes(payload)
    with pytest.raises(AttachmentStorageError, match="temp identity changed"):
        _publish_temp(layout, temp, key)
    assert temp.path.read_bytes() == payload
    assert original.read_bytes() == payload
    assert not layout.final_path(key).exists()



def test_settings_to_lifespan_rejects_injected_reparse_component_before_side_effects(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from app.main import create_app

    data = tmp_path / "data"
    component = data / "middle"
    component.mkdir(parents=True)
    lstat = Path.lstat

    def inspect(path, *args, **kwargs):
        info = lstat(path, *args, **kwargs)
        if path == component:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    monkeypatch.setattr(Path, "lstat", inspect)
    settings = _settings(tmp_path, attachment_storage_root="middle/attachments")
    assert settings.attachment_storage_root == component / "attachments"
    with pytest.raises(StorageRootError, match="not a real directory"), TestClient(
        create_app(settings)
    ):
        pytest.fail("must reject the reparse point before startup")
    assert not list(component.iterdir())
    assert not (data / ".explainlab.process.lock").exists()


@pytest.mark.parametrize("matching", [True, False])
def test_link_target_appearing_after_precheck_is_revalidated(tmp_path, monkeypatch, matching):
    layout = _layout(tmp_path)
    payload = b"claim the path"
    key = storage.sha256_bytes(payload)
    target = layout.final_path(key)
    temp = storage.write_temp(layout, payload)
    competing = payload if matching else b"competing content"

    def target_appears(_source, final):
        assert final == target
        target.write_bytes(competing)
        raise FileExistsError(errno.EEXIST, "contender created the target")

    monkeypatch.setattr(storage.os, "link", target_appears)
    if matching:
        assert _publish_temp(layout, temp, key).reused
    else:
        with pytest.raises(AttachmentStorageError) as exc:
            _publish_temp(layout, temp, key)
        assert exc.value.code == ATTACHMENT_KEY_COLLISION
    assert target.read_bytes() == competing
    assert not temp.path.exists()



def test_startup_rejects_same_directory_identity_with_distinct_lexical_roots(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    settings.attachment_storage_root.mkdir(parents=True)
    settings.attachment_staging_root.mkdir(parents=True)
    real = Path.lstat
    storage_info = real(settings.attachment_storage_root)

    def alias(path, *args, **kwargs):
        if path == settings.attachment_staging_root:
            return storage_info
        return real(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", alias)
    with pytest.raises(StorageRootError, match="overlap by directory identity"):
        validate_storage_roots(settings)
    assert not settings.attachment_quarantine_dir.exists()
