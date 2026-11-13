"""服务层异常。"""

from __future__ import annotations


class NotFoundError(Exception):
    """请求的资源不存在（路由层翻译为 404）。"""