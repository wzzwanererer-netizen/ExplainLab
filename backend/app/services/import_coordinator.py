"""同步导入协调器（V2 A1-04 D20：单一线程模型，无 async 双架构）。

- 每个身份键一把 ``threading.Lock``；键之间互不阻塞。
- 获取有界等待（默认 10s），超时抛 ``ImportLockTimeout`` → API 稳定码
  ``IMPORT_LOCK_TIMEOUT``。
- 注册表按引用计数回收，避免长期运行键膨胀；锁对象不跨进程。
- 会话不在锁内共享：调用方在获得锁后自行创建新 Session（S1）。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Lock, current_thread

__all__ = ["IMPORT_LOCK_TIMEOUT", "ImportCoordinator", "ImportLockTimeout"]

IMPORT_LOCK_TIMEOUT = "IMPORT_LOCK_TIMEOUT"


class ImportLockTimeout(RuntimeError):
    code = IMPORT_LOCK_TIMEOUT

    def __init__(self, key: str) -> None:
        super().__init__(f"{IMPORT_LOCK_TIMEOUT}: {key}")


@dataclass
class _Entry:
    lock: Lock = field(default_factory=Lock)
    refs: int = 0
    owner: str | None = None


class ImportCoordinator:
    def __init__(self, *, wait_seconds: float = 10.0) -> None:
        self._wait_seconds = wait_seconds
        self._guard = Lock()
        self._entries: dict[str, _Entry] = {}

    @property
    def waiting_keys(self) -> int:
        with self._guard:
            return len(self._entries)

    def is_held(self, key: str) -> bool:
        with self._guard:
            entry = self._entries.get(key)
            return bool(entry and entry.lock.locked())

    @contextmanager
    def keyed(self, key: str) -> Iterator[None]:
        with self._guard:
            entry = self._entries.setdefault(key, _Entry())
            entry.refs += 1
        acquired = entry.lock.acquire(timeout=self._wait_seconds)
        if not acquired:
            self._drop_ref(key, entry)
            raise ImportLockTimeout(key)
        with self._guard:
            entry.owner = current_thread().name
        try:
            yield
        finally:
            with self._guard:
                entry.owner = None
            entry.lock.release()
            self._drop_ref(key, entry)

    def _drop_ref(self, key: str, entry: _Entry) -> None:
        with self._guard:
            entry.refs -= 1
            if entry.refs <= 0 and not entry.lock.locked():
                self._entries.pop(key, None)