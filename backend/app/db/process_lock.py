"""单实例进程锁（V2 A1-04 D13；Windows msvcrt / POSIX fcntl）。

约束：
- 锁文件 ``<data_dir>/.explainlab.process.lock`` 永不删除（避免 inode 替换竞态）。
- 非阻塞尝试 + 有界重试（默认 10s，100ms 起，封顶 500ms）。
- 同进程重复获取必须失败（OS 锁在部分平台同进程不同 fd 可重入，需注册表守护）。
- 不做 PID 存活探测；不自动清理陈旧锁（OS 锁随进程退出释放）。
- 仅单 worker 部署；``workers > 1`` 由启动入口拒绝。
"""

from __future__ import annotations

import errno
import os
import time
from contextlib import suppress
from pathlib import Path
from threading import Lock

__all__ = [
    "BACKEND_ALREADY_RUNNING",
    "ProcessLock",
    "ProcessLockError",
    "process_lock_path",
]

BACKEND_ALREADY_RUNNING = "BACKEND_ALREADY_RUNNING"
LOCK_FILENAME = ".explainlab.process.lock"
_INITIAL_BACKOFF = 0.1
_MAX_BACKOFF = 0.5


class ProcessLockError(RuntimeError):
    """进程锁获取失败（稳定码 ``BACKEND_ALREADY_RUNNING``）。"""

    code = BACKEND_ALREADY_RUNNING

    def __init__(self, message: str = "Backend is already running") -> None:
        super().__init__(f"{BACKEND_ALREADY_RUNNING}: {message}")


_registry_guard = Lock()
_held: set[str] = set()


def process_lock_path(data_dir: Path) -> Path:
    return Path(data_dir) / LOCK_FILENAME


class ProcessLock:
    """持有 OS 级独占锁；``acquire`` 成功后必须 ``release``。"""

    def __init__(
        self,
        data_dir: Path,
        *,
        timeout_seconds: float = 10.0,
        initial_backoff: float = _INITIAL_BACKOFF,
        max_backoff: float = _MAX_BACKOFF,
    ) -> None:
        self.path = process_lock_path(data_dir)
        self._timeout = timeout_seconds
        self._initial_backoff = initial_backoff
        self._max_backoff = max_backoff
        self._fd: int | None = None
        self._key = str(self.path.resolve())
        self._acquired = False

    # -- 状态 ---------------------------------------------------------------
    @property
    def acquired(self) -> bool:
        return self._acquired

    # -- 获取/释放 ----------------------------------------------------------
    def acquire(self) -> None:
        if self._acquired:
            raise ProcessLockError("lock already acquired by this object")
        with _registry_guard:
            if self._key in _held:
                raise ProcessLockError("lock already held in this process")
            _held.add(self._key)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        except OSError as exc:  # 目录不可写/权限
            with _registry_guard:
                _held.discard(self._key)
            raise ProcessLockError(f"cannot open lock file: {exc.errno}") from None
        deadline = time.monotonic() + self._timeout
        backoff = self._initial_backoff
        while True:
            if self._try_lock(fd):
                self._fd = fd
                self._acquired = True
                return
            if time.monotonic() >= deadline:
                os.close(fd)
                with _registry_guard:
                    _held.discard(self._key)
                raise ProcessLockError("timed out waiting for process lock")
            time.sleep(backoff)
            backoff = min(backoff * 2, self._max_backoff)

    def release(self) -> None:
        fd, self._fd = self._fd, None
        self._acquired = False
        try:
            if fd is not None:
                self._unlock(fd)
        finally:
            if fd is not None:
                with suppress(OSError):
                    os.close(fd)
            with _registry_guard:
                _held.discard(self._key)

    def __enter__(self) -> ProcessLock:
        self.acquire()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()

    # -- 平台原语 -----------------------------------------------------------
    def _try_lock(self, fd: int) -> bool:
        if os.name == "nt":
            import msvcrt

            try:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                return True
            except OSError as exc:
                if exc.errno in (errno.EACCES, errno.EDEADLK, errno.EAGAIN, 13, 36):
                    return False
                raise
        else:
            import fcntl

            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except OSError as exc:
                if exc.errno in (errno.EACCES, errno.EAGAIN):
                    return False
                raise

    def _unlock(self, fd: int) -> None:
        if os.name == "nt":
            import msvcrt

            with suppress(OSError):
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            with suppress(OSError):
                fcntl.flock(fd, fcntl.LOCK_UN)