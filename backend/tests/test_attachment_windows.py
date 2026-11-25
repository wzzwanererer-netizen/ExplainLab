"""Windows 真实文件系统专项（B1-T01/T02，仅在 win32 运行）。

覆盖真实共享冲突 ``winerror 32`` 的有界重试、no-clobber rename 的目标存在行为、
真实 junction 根拒绝。POSIX 仍需在 Linux 环境单独取证，本文件不能替代。
"""

from __future__ import annotations

import errno
import hashlib
import os
import stat
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app, init_db
from app.services import attachment_storage as storage

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows 真机专项")


def _layout(tmp_path: Path) -> storage.StorageLayout:
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        data_dir=tmp_path / "data",
        _env_file=None,
    )
    return storage.validate_storage_roots(settings)


def test_windows_real_sharing_violation_exhausts_retry(tmp_path: Path):
    path = tmp_path / "held.bin"
    path.write_bytes(b"held")
    with path.open("rb"):
        with pytest.raises(storage.AttachmentStorageError) as exc:
            storage.retry_windows_busy(
                lambda: os.unlink(path),
                initial_delay=0.01,
                max_delay=0.02,
                budget=0.05,
            )
        assert exc.value.code == storage.ATTACHMENT_WRITE_BUSY
        assert path.exists()
    # 句柄关闭后同一操作成功。
    storage.retry_windows_busy(lambda: os.unlink(path))
    assert not path.exists()


def test_windows_real_sharing_violation_retries_then_succeeds(tmp_path: Path):
    path = tmp_path / "released.bin"
    path.write_bytes(b"released")
    handle = path.open("rb")
    calls = {"n": 0}

    def close_then_unlink():
        calls["n"] += 1
        if calls["n"] == 2:
            handle.close()
        os.unlink(path)

    storage.retry_windows_busy(
        close_then_unlink, initial_delay=0.02, max_delay=0.02, budget=0.5
    )
    assert calls["n"] == 2
    assert not path.exists()


def test_windows_rename_never_overwrites_existing_target(tmp_path: Path):
    source = tmp_path / "source.bin"
    target = tmp_path / "target.bin"
    source.write_bytes(b"source")
    target.write_bytes(b"target")
    with pytest.raises(FileExistsError):
        os.rename(source, target)
    assert source.read_bytes() == b"source"
    assert target.read_bytes() == b"target"


def _make_junction(link: Path, target: Path) -> bool:
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0 and link.exists()


def test_windows_real_junction_root_rejected(tmp_path: Path):
    layout = _layout(tmp_path)
    real = layout.data_dir / "real-staging"
    real.mkdir()
    junction = layout.data_dir / "linked-staging"
    if not _make_junction(junction, real):
        pytest.skip("mklink /J unavailable")
    hijacked = replace(layout, staging_root=junction)
    with pytest.raises(storage.AttachmentStorageError) as exc:
        storage.ensure_runtime(hijacked)
    assert exc.value.code == storage.ATTACHMENT_STORAGE_UNAVAILABLE
    assert real.is_dir()


def _snapshot(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): (
            "directory" if path.is_dir() else hashlib.sha256(path.read_bytes()).hexdigest()
        )
        for path in root.rglob("*")
    }


def _assert_startup_rejected(settings: Settings, reason: str) -> None:
    application = create_app(settings)
    with (
        patch("app.main.init_db", wraps=init_db) as database_init,
        patch.object(Path, "mkdir", autospec=True, side_effect=Path.mkdir) as mkdir,
        pytest.raises(storage.StorageRootError, match=reason),
        TestClient(application),
    ):
        pytest.fail("invalid storage configuration reached the application startup")
    database_init.assert_not_called()
    mkdir.assert_not_called()


@pytest.mark.parametrize("junction_at", ["database-ancestor", "attachment", "staging"])
def test_t01_windows_lifespan_rejects_real_junction(tmp_path: Path, junction_at: str):
    root = tmp_path / "data"
    root.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    (target / "keep.bin").write_bytes(b"existing junction target")
    junction = root / "junction"
    try:
        completed = subprocess.run(
            ["cmd", "/d", "/c", "mklink", "/J", str(junction), str(target)],
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            print(f"mklink /J exit={completed.returncode}; stdout={completed.stdout!r}; "
                  f"stderr={completed.stderr!r}")
            pytest.skip(f"normal Windows token could not create junction (exit {completed.returncode})")
        assert junction.lstat().st_reparse_tag == stat.IO_REPARSE_TAG_MOUNT_POINT
        assert junction.samefile(target)
        before = _snapshot(target)
        db = junction / "nested" / "test.db" if junction_at == "database-ancestor" else root / "test.db"
        settings = Settings(
            database_url=f"sqlite:///{db.as_posix()}",
            data_dir=root,
            attachment_storage_root=junction if junction_at == "attachment" else root / "store",
            attachment_staging_root=junction if junction_at == "staging" else root / "staging",
            _env_file=None,
        )
        _assert_startup_rejected(settings, "storage directory component is not a real directory")
        assert not db.exists()
        assert {item.name for item in root.iterdir()} == {"junction"}
        assert _snapshot(target) == before
        print(f"{junction_at}: junction tag={junction.lstat().st_reparse_tag:#x}; target={before}")
    finally:
        if os.path.lexists(junction):
            junction.rmdir()


def test_t01_windows_lifespan_rejects_root_on_real_other_drive(tmp_path: Path):
    other_parent = Path(os.environ.get("EXPLAINLAB_T01_OTHER_VOLUME", tempfile.gettempdir()))
    if other_parent.stat().st_dev == tmp_path.stat().st_dev:
        pytest.skip("no writable second Windows volume selected")
    with tempfile.TemporaryDirectory(dir=other_parent, prefix="explainlab-t01-") as path:
        target = Path(path)
        (target / "keep.bin").write_bytes(b"existing other-volume target")
        before = _snapshot(target)
        data = tmp_path / "data"
        db = tmp_path / "test.db"
        config = dict(
            database_url=f"sqlite:///{db.as_posix()}",
            data_dir=data,
            _env_file=None,
        )
        reason = r"attachment_staging_root must be inside data_dir"
        with pytest.raises(ValidationError, match=reason):
            Settings(**config, attachment_staging_root=target)
        # Programmatically supplied settings still face the application's preflight.
        settings = Settings(**config).model_copy(update={"attachment_staging_root": target})
        _assert_startup_rejected(settings, reason)
        assert not data.exists()
        assert not db.exists()
        assert _snapshot(target) == before
        print(f"distinct devices {tmp_path.stat().st_dev}, {target.stat().st_dev}; target={before}")


def test_windows_final_path_uses_lowercase_key_namespace(tmp_path: Path):
    layout = _layout(tmp_path)
    key = "abcdef" + "0" * 58
    path = layout.final_path(key)
    assert path.name == key
    assert path.parent.name == key[2:4]
    assert path.parent.parent.name == key[:2]


def test_windows_busy_error_classification_keeps_errno_semantics():
    busy = storage.AttachmentStorageError(storage.ATTACHMENT_WRITE_BUSY)
    assert busy.code == "ATTACHMENT_WRITE_BUSY"
    # 权限拒绝与占用不得混用同一分支。
    permission = OSError(errno.EACCES, "denied")
    assert storage._is_busy(permission) is False
    assert storage._is_permission(permission) is True
    real_busy = OSError(errno.EACCES, "busy")
    real_busy.winerror = 32
    assert storage._is_busy(real_busy) is True
