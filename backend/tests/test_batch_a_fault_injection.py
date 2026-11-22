"""A1-04 P2 故障注入：InterruptedError / fsync / close / replace / link / 归档竞态。

真实文件描述符与真实临时目录；通过替换模块内 ``os`` 函数注入失败，验证：
不发布半成品、不覆盖既有 ID/归档、不删除已完整写入的 ID、失败路径可恢复。
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

import app.services.source_identity as source_identity
import app.services.source_instance_id as source_instance_id
from app.services.source_identity import (
    JOURNAL_CORRUPT,
    SourceIdentityError,
    SourceIdentityService,
)
from app.services.source_instance_id import SourceInstanceIdStore


def _instance(client) -> SourceIdentityService:
    return client.app.state.source_identity


def _real_close_then_raise(monkeypatch, *, fail_on: int) -> None:
    real_close = os.close
    calls = 0

    def wrapper(fd):
        nonlocal calls
        calls += 1
        real_close(fd)
        if calls == fail_on:
            raise OSError("injected close failure")

    monkeypatch.setattr(source_identity.os, "close", wrapper)


class TestFsyncFailure:
    """P2-02：fsync 失败不得发布不完整文件；旧文件保持。"""

    def test_journal_current_fsync_failure_preserves_old(self, client, monkeypatch):
        journal = _instance(client).journal
        journal.current.parent.mkdir(parents=True, exist_ok=True)
        journal.current.write_bytes(b"old-current")

        def boom(fd):
            raise OSError("injected fsync failure")

        monkeypatch.setattr(source_identity.os, "fsync", boom)
        with pytest.raises(OSError, match="injected fsync"):
            journal._atomic_write(journal.current, b"new-current")
        assert journal.current.read_bytes() == b"old-current"
        assert not [p for p in journal.data_dir.iterdir() if p.name.endswith(".tmp")]

    def test_journal_archive_fsync_failure_publishes_no_archive(
        self, client, monkeypatch
    ):
        journal = _instance(client).journal
        record = {"phase": "COMMITTED", "operation_id": str(uuid.uuid4()), "v": 1}

        def boom(fd):
            raise OSError("injected archive fsync")

        monkeypatch.setattr(source_identity.os, "fsync", boom)
        with pytest.raises(OSError, match="injected archive fsync"):
            journal.archive_committed(record)
        target = journal.archive_dir / f"{record['operation_id']}.json"
        assert target.exists() is False
        assert not [p for p in journal.archive_dir.iterdir() if p.name.endswith(".tmp")]

    def test_id_create_fsync_failure_publishes_no_id(self, tmp_path: Path, monkeypatch):
        store = SourceInstanceIdStore(tmp_path)

        def boom(fd):
            raise OSError("injected id fsync")

        monkeypatch.setattr(source_instance_id.os, "fsync", boom)
        with pytest.raises(OSError, match="injected id fsync"):
            store.ensure()
        assert store.path.exists() is False
        assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]

    def test_id_fallback_fsync_failure_removes_partial(
        self, tmp_path: Path, monkeypatch
    ):
        store = SourceInstanceIdStore(tmp_path)

        def no_link(*args, **kwargs):
            raise OSError("hardlink unsupported")

        def boom(fd):
            raise OSError("injected fallback fsync")

        monkeypatch.setattr(source_instance_id.os, "link", no_link)
        monkeypatch.setattr(source_instance_id.os, "fsync", boom)
        with pytest.raises(OSError, match="injected fallback fsync"):
            store.ensure()
        assert store.path.exists() is False
        assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]

    def test_id_replace_fsync_failure_preserves_old(self, tmp_path: Path, monkeypatch):
        store = SourceInstanceIdStore(tmp_path)
        old = store.ensure()
        new = "f0e8400a-e29b-41d4-a716-446655440099"

        def boom(fd):
            raise OSError("injected replace fsync")

        monkeypatch.setattr(source_instance_id.os, "fsync", boom)
        with pytest.raises(OSError, match="injected replace fsync"):
            store.replace(new)
        assert store.read() == old
        assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]


class TestCloseFailure:
    """P2-03：close 失败不得发布错误正式文件，也不得删除已写入的 ID。"""

    def test_journal_current_close_failure_preserves_old(self, client, monkeypatch):
        journal = _instance(client).journal
        journal.current.parent.mkdir(parents=True, exist_ok=True)
        journal.current.write_bytes(b"old-current")
        _real_close_then_raise(monkeypatch, fail_on=1)

        with pytest.raises(OSError, match="injected close"):
            journal._atomic_write(journal.current, b"new-current")
        assert journal.current.read_bytes() == b"old-current"
        assert not [p for p in journal.data_dir.iterdir() if p.name.endswith(".tmp")]

    def test_journal_archive_close_failure_publishes_no_archive(
        self, client, monkeypatch
    ):
        journal = _instance(client).journal
        record = {"phase": "COMMITTED", "operation_id": str(uuid.uuid4()), "v": 1}
        _real_close_then_raise(monkeypatch, fail_on=1)

        with pytest.raises(OSError, match="injected close"):
            journal.archive_committed(record)
        target = journal.archive_dir / f"{record['operation_id']}.json"
        assert target.exists() is False
        assert not [p for p in journal.archive_dir.iterdir() if p.name.endswith(".tmp")]

    def test_id_create_close_failure_publishes_no_id(self, tmp_path: Path, monkeypatch):
        store = SourceInstanceIdStore(tmp_path)
        _real_close_then_raise(monkeypatch, fail_on=1)

        with pytest.raises(OSError, match="injected close"):
            store.ensure()
        assert store.path.exists() is False
        assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]

    def test_id_replace_close_failure_preserves_old(self, tmp_path: Path, monkeypatch):
        store = SourceInstanceIdStore(tmp_path)
        old = store.ensure()
        new = "f0e8400a-e29b-41d4-a716-446655440099"
        _real_close_then_raise(monkeypatch, fail_on=1)

        with pytest.raises(OSError, match="injected close"):
            store.replace(new)
        assert store.read() == old
        assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]

    def test_fallback_close_failure_keeps_fully_written_valid_id(
        self, tmp_path: Path, monkeypatch
    ):
        store = SourceInstanceIdStore(tmp_path)

        def no_link(*args, **kwargs):
            raise OSError("hardlink unsupported")

        monkeypatch.setattr(source_instance_id.os, "link", no_link)
        # 第 1 次 close 关闭 tmp（正常）；第 2 次 close 关闭正式 ID 后抛错。
        _real_close_then_raise(monkeypatch, fail_on=2)

        with pytest.raises(OSError, match="injected close"):
            store.ensure()
        assert store.path.exists() is True
        assert store.read()
        assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]


class TestReplaceFailure:
    """P2-04：os.replace 失败保持旧文件，临时文件清理。"""

    def test_journal_current_replace_failure_preserves_old(self, client, monkeypatch):
        journal = _instance(client).journal
        journal.current.parent.mkdir(parents=True, exist_ok=True)
        journal.current.write_bytes(b"old-current")

        def boom(src, dst):
            raise OSError("injected replace failure")

        monkeypatch.setattr(source_identity.os, "replace", boom)
        with pytest.raises(OSError, match="injected replace"):
            journal._atomic_write(journal.current, b"new-current")
        assert journal.current.read_bytes() == b"old-current"
        assert not [p for p in journal.data_dir.iterdir() if p.name.endswith(".tmp")]

    def test_archive_uses_no_overwrite_link_not_replace(self, client, monkeypatch):
        # P2-06 起归档改为硬链接发布；replace 失败不再影响归档原子落位。
        journal = _instance(client).journal
        record = {"phase": "COMMITTED", "operation_id": str(uuid.uuid4()), "v": 1}

        def boom(src, dst):
            raise OSError("injected replace failure")

        monkeypatch.setattr(source_identity.os, "replace", boom)
        journal.archive_committed(record)
        target = journal.archive_dir / f"{record['operation_id']}.json"
        assert target.exists() is True
        assert not [p for p in journal.archive_dir.iterdir() if p.name.endswith(".tmp")]

    def test_id_replace_failure_preserves_old(self, tmp_path: Path, monkeypatch):
        store = SourceInstanceIdStore(tmp_path)
        old = store.ensure()
        new = "f0e8400a-e29b-41d4-a716-446655440099"

        def boom(src, dst):
            raise OSError("injected replace failure")

        monkeypatch.setattr(source_instance_id.os, "replace", boom)
        with pytest.raises(OSError, match="injected replace"):
            store.replace(new)
        assert store.read() == old
        assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]


class TestLinkFileExists:
    """P2-05：os.link FileExistsError 不得覆盖/删除既有 ID。"""

    def test_link_exists_returns_existing_without_overwrite(
        self, tmp_path: Path, monkeypatch
    ):
        store = SourceInstanceIdStore(tmp_path)
        existing = "f0e8400a-e29b-41d4-a716-446655440099"
        real_link = os.link

        def race_link(src, dst):
            store.path.write_bytes((existing + "\n").encode("ascii"))
            return real_link(src, dst)

        monkeypatch.setattr(source_instance_id.os, "link", race_link)
        assert store.ensure() == existing
        assert store.read() == existing
        assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]

    def test_link_exists_with_invalid_existing_fails_without_deleting(
        self, tmp_path: Path, monkeypatch
    ):
        store = SourceInstanceIdStore(tmp_path)
        real_link = os.link

        def race_link(src, dst):
            store.path.write_bytes(b"not-a-uuid\n")
            return real_link(src, dst)

        monkeypatch.setattr(source_instance_id.os, "link", race_link)
        with pytest.raises(source_instance_id.SourceInstanceIdError) as excinfo:
            store.ensure()
        assert excinfo.value.code == source_instance_id.SOURCE_INSTANCE_ID_INVALID
        assert store.path.read_bytes() == b"not-a-uuid\n"
        assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]


class TestArchiveNoOverwrite:
    """P2-06：归档发布不覆盖已有记录（含检查-发布竞态）。"""

    @staticmethod
    def _record(operation_id: str | None = None, value: int = 1) -> dict:
        return {
            "phase": "COMMITTED",
            "operation_id": operation_id or str(uuid.uuid4()),
            "v": value,
        }

    def test_different_operation_ids_both_archived(self, client):
        journal = _instance(client).journal
        first = self._record()
        second = self._record()
        journal.archive_committed(first)
        journal.archive_committed(second)
        names = {path.name for path in journal.archive_dir.glob("*.json")}
        assert names == {
            f"{first['operation_id']}.json",
            f"{second['operation_id']}.json",
        }

    def test_same_operation_same_content_is_idempotent(self, client, monkeypatch):
        journal = _instance(client).journal
        record = self._record()
        journal.archive_committed(record)
        target = journal.archive_dir / f"{record['operation_id']}.json"
        before = target.read_bytes()

        def no_link(*args, **kwargs):  # pragma: no cover - 不应被调用
            raise AssertionError("same content must return before publishing")

        monkeypatch.setattr(source_identity.os, "link", no_link)
        with _instance(client).identity_guard():
            journal.archive_committed(record)
        assert target.read_bytes() == before

    def test_same_operation_different_content_fails_closed(self, client):
        journal = _instance(client).journal
        record = self._record()
        journal.archive_committed(record)
        target = journal.archive_dir / f"{record['operation_id']}.json"
        before = target.read_bytes()
        changed = dict(record, v=2)
        with (
            _instance(client).identity_guard(),
            pytest.raises(SourceIdentityError) as excinfo,
        ):
            journal.archive_committed(changed)
        assert excinfo.value.code == JOURNAL_CORRUPT
        assert target.read_bytes() == before

    def test_publish_race_existing_conflict_does_not_overwrite(
        self, client, monkeypatch
    ):
        journal = _instance(client).journal
        record = self._record()
        target = journal.archive_dir / f"{record['operation_id']}.json"
        conflict = b"preexisting-conflict"
        real_link = os.link

        def race_link(src, dst):
            target.write_bytes(conflict)
            return real_link(src, dst)

        monkeypatch.setattr(source_identity.os, "link", race_link)
        with (
            _instance(client).identity_guard(),
            pytest.raises(SourceIdentityError) as excinfo,
        ):
            journal.archive_committed(record)
        assert excinfo.value.code == JOURNAL_CORRUPT
        assert target.read_bytes() == conflict
        assert not [p for p in journal.archive_dir.iterdir() if p.name.endswith(".tmp")]

    def test_publish_race_same_content_is_accepted(self, client, monkeypatch):
        journal = _instance(client).journal
        record = self._record()
        target = journal.archive_dir / f"{record['operation_id']}.json"
        payload = source_identity.canonical_dumps(record).encode("utf-8")
        real_link = os.link

        def race_link(src, dst):
            target.write_bytes(payload)
            return real_link(src, dst)

        monkeypatch.setattr(source_identity.os, "link", race_link)
        with _instance(client).identity_guard():
            journal.archive_committed(record)
        assert target.read_bytes() == payload
        assert not [p for p in journal.archive_dir.iterdir() if p.name.endswith(".tmp")]


class TestWriteAllInterrupted:
    """P2-01：InterruptedError 重试；随后 OSError 不得吞掉或重复写。"""

    @staticmethod
    def _open_temp(tmp_path: Path):
        path = tmp_path / "interrupted.bin"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        return path, fd

    def test_first_write_interrupted_then_succeeds(self, tmp_path: Path, monkeypatch):
        import app.services.file_write as file_write
        from app.services.file_write import write_all

        path, fd = self._open_temp(tmp_path)
        real_write = os.write
        calls = 0

        def interrupted_once(descriptor, data):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise InterruptedError("injected EINTR")
            return real_write(descriptor, data)

        try:
            monkeypatch.setattr(file_write.os, "write", interrupted_once)
            write_all(fd, b"abcdefghij")
        finally:
            os.close(fd)
        assert path.read_bytes() == b"abcdefghij"
        assert calls == 2

    def test_multiple_consecutive_interruptions(self, tmp_path: Path, monkeypatch):
        import app.services.file_write as file_write
        from app.services.file_write import write_all

        path, fd = self._open_temp(tmp_path)
        real_write = os.write
        calls = 0

        def interrupted_many(descriptor, data):
            nonlocal calls
            calls += 1
            if calls <= 4:
                raise InterruptedError("injected EINTR")
            return real_write(descriptor, data)

        try:
            monkeypatch.setattr(file_write.os, "write", interrupted_many)
            write_all(fd, b"abcdef")
        finally:
            os.close(fd)
        assert path.read_bytes() == b"abcdef"
        assert calls == 5

    def test_interrupted_then_oserror_propagates_without_duplicates(
        self, tmp_path: Path, monkeypatch
    ):
        import app.services.file_write as file_write
        from app.services.file_write import write_all

        path, fd = self._open_temp(tmp_path)
        real_write = os.write
        calls = 0

        def interrupted_then_fail(descriptor, data):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise InterruptedError("injected EINTR")
            if calls == 2:
                raw = bytes(data)
                chunk = raw[: max(1, len(raw) // 3)]
                real_write(descriptor, chunk)
                return len(chunk)
            raise OSError("injected write failure")

        try:
            monkeypatch.setattr(file_write.os, "write", interrupted_then_fail)
            with pytest.raises(OSError, match="injected write failure"):
                write_all(fd, b"abcdef")
        finally:
            os.close(fd)
        assert path.read_bytes() == b"ab"
        assert calls == 3