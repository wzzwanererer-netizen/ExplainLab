"""可靠完整写入（V2 A1-04 Batch A 整改 P2）。

``os.write`` 允许短写；单次调用后直接 fsync/发布可能把截断内容变成正式文件。
本模块只负责把给定字节全部写入描述符：

- 循环直到全部字节写完；
- 返回 0 视为失败（``OSError(EIO)``），避免无限循环；
- 写入异常原样传播，调用方不得在异常后 fsync/rename 发布；
- 不改变文件打开模式、权限、fsync、原子替换与上层层级。
"""

from __future__ import annotations

import errno
import os

__all__ = ["write_all"]


def write_all(fd: int, payload: bytes | bytearray | memoryview) -> None:
    view = memoryview(payload)
    total = len(view)
    offset = 0
    while offset < total:
        try:
            written = os.write(fd, view[offset:])
        except InterruptedError:
            continue
        if written <= 0:
            raise OSError(errno.EIO, "write_all: os.write returned 0")
        offset += written