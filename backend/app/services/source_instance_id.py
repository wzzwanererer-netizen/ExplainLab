"""``source-instance-id`` 生命周期（V2 A1-04 D13 / D23）。

文件：``<data_dir>/source-instance-id``，内容为规范小写 UUIDv4 单行。
- 仅在进程锁获取成功后调用 ``ensure``；已存在则严格校验、绝不覆盖。
- 首次创建使用「临时文件 + fsync + 原子 non-overwrite 链接」；目标已存在时失败而非截断。
- 损坏/不可读一律 fail-closed，不自动重建、不猜测。
- 轮换 ``replace`` 只供离线 CLI/Journal ROTATE 恢复流程调用。
"""

from __future__ import annotations

import os
import uuid
from contextlib import suppress
from pathlib import Path

from app.services.file_write import write_all

__all__ = [
    "SOURCE_INSTANCE_ID_INVALID",
    "SOURCE_INSTANCE_ID_UNAVAILABLE",
    "SourceInstanceIdError",
    "SourceInstanceIdStore",
]

SOURCE_INSTANCE_ID_INVALID = "SOURCE_INSTANCE_ID_INVALID"
SOURCE_INSTANCE_ID_UNAVAILABLE = "SOURCE_INSTANCE_ID_UNAVAILABLE"
FILENAME = "source-instance-id"
_BINARY = getattr(os, "O_BINARY", 0)


class SourceInstanceIdError(RuntimeError):
    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        detail = f": {message}" if message else ""
        super().__init__(f"{code}{detail}")


def _canonical(value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise SourceInstanceIdError(SOURCE_INSTANCE_ID_INVALID, "not a UUID") from exc
    if str(parsed) != value:
        raise SourceInstanceIdError(
            SOURCE_INSTANCE_ID_INVALID, "UUID must be canonical lowercase form"
        )
    if parsed.version != 4:
        raise SourceInstanceIdError(SOURCE_INSTANCE_ID_INVALID, "UUID must be v4")
    return value


def _sync_dir(path: Path) -> None:
    """尽力 fsync 目录（Windows 不可靠；不宣称掉电持久性）。"""
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


class SourceInstanceIdStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / FILENAME

    # -- 读取 ---------------------------------------------------------------
    def read(self) -> str:
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError as exc:
            raise SourceInstanceIdError(
                SOURCE_INSTANCE_ID_UNAVAILABLE, "source-instance-id missing"
            ) from exc
        except OSError as exc:
            raise SourceInstanceIdError(
                SOURCE_INSTANCE_ID_UNAVAILABLE, f"unreadable ({exc.errno})"
            ) from exc
        return self._parse(raw)

    @staticmethod
    def _parse(raw: bytes) -> str:
        if raw.startswith(b"\xef\xbb\xbf"):
            raise SourceInstanceIdError(SOURCE_INSTANCE_ID_INVALID, "BOM not allowed")
        try:
            text = raw.decode("ascii")
        except UnicodeDecodeError as exc:
            raise SourceInstanceIdError(
                SOURCE_INSTANCE_ID_INVALID, "non-ASCII content"
            ) from exc
        if text.endswith("\n"):
            text = text[:-1]
        if "\n" in text or "\r" in text or text.strip() != text:
            raise SourceInstanceIdError(
                SOURCE_INSTANCE_ID_INVALID, "must be a single line without padding"
            )
        return _canonical(text)

    def exists(self) -> bool:
        return self.path.exists()

    # -- 创建 ---------------------------------------------------------------
    def ensure(self) -> str:
        """读取已有 ID；不存在时生成并原子创建。必须已持有进程锁。"""
        if self.path.exists():
            return self.read()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        new_id = str(uuid.uuid4())
        payload = (new_id + "\n").encode("ascii")
        tmp = self.data_dir / f".{FILENAME}.{uuid.uuid4().hex}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _BINARY, 0o600)
        try:
            try:
                write_all(fd, payload)
                os.fsync(fd)
            finally:
                os.close(fd)
            try:
                os.link(tmp, self.path)  # 目标存在 → FileExistsError，绝不覆盖
            except FileExistsError:
                return self.read()
            except OSError:
                # 不支持硬链接的文件系统：退回 O_EXCL 独占创建。
                try:
                    target = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _BINARY, 0o600)
                except FileExistsError:
                    return self.read()
                write_ok = False
                try:
                    try:
                        write_all(target, payload)
                        os.fsync(target)
                        # fsync 成功即视为完整内容已落盘；此后 close 失败
                        # 不得删除已有效的正式 ID。
                        write_ok = True
                    finally:
                        os.close(target)
                except BaseException:
                    if not write_ok:
                        # 不支持硬链接时只能直接写目标；写入/fsync 失败必须
                        # 移除半成品，绝不让截断文件以正式 ID 身份留下。
                        with suppress(OSError):
                            os.unlink(self.path)
                    raise
        finally:
            with suppress(OSError):
                os.unlink(tmp)
        _sync_dir(self.data_dir)
        return new_id

    # -- 轮换（ROTATE）/ 恢复 ----------------------------------------------
    def replace(self, new_id: str) -> None:
        """原子替换现有 ID（仅 ROTATE 事务/恢复调用）。"""
        _canonical(new_id)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.data_dir / f".{FILENAME}.{uuid.uuid4().hex}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _BINARY, 0o600)
        try:
            try:
                write_all(fd, (new_id + "\n").encode("ascii"))
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(tmp, self.path)
        finally:
            with suppress(OSError):
                os.unlink(tmp)
        _sync_dir(self.data_dir)