"""Canonical JSON v1（V2 A1-04 D23 Journal/身份审计专用）。

与 A1-02 Core ``markdown/canonical.py``（任意 JSON 规范化）**互不影响**：
本模块只服务 Journal 与身份审计摘要，规则固定在冻结设计 §22：

- UTF-8，无 BOM/尾随换行，紧凑 ````,``/``:`` 分隔，非 ASCII 原样保留。
- 转义 ``"``/``\\``；``\\b\\t\\n\\f\\r``；其余 U+0000–U+001F 用 ``\\u00xx`` 小写。
- 对象键按码点排序；**折叠前**拒绝重复键（含 ``"a"`` 与 ``"\\u0061"``）。
- 仅接受非负整数（拒绝负数/浮点/NaN/Infinity）；合法代理对合并，孤立代理拒绝。
- 解析后必须满足 ``canonical_dumps(loads(text)) == text``（严格字节级规范）。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

__all__ = [
    "CanonicalJsonError",
    "canonical_bytes",
    "canonical_dumps",
    "canonical_loads",
    "sha256_canonical",
]

_DIGEST_PREFIX = "sha256:"


class CanonicalJsonError(ValueError):
    """Canonical JSON v1 违规。"""


_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\f": "\\f",
    "\r": "\\r",
}


def _encode_string(value: str) -> str:
    out: list[str] = ['"']
    for char in value:
        code = ord(char)
        if char in _ESCAPES:
            out.append(_ESCAPES[char])
        elif 0xD800 <= code <= 0xDFFF:
            raise CanonicalJsonError("isolated surrogate not allowed")
        elif code < 0x20:
            out.append(f"\\u00{code:02x}")
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def _encode(value: Any, depth: int = 0) -> str:
    if depth > 128:
        raise CanonicalJsonError("nesting too deep")
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _encode_string(value)
    if isinstance(value, int):
        if value < 0:
            raise CanonicalJsonError("negative integer not allowed")
        return str(value)
    if isinstance(value, float):
        raise CanonicalJsonError("float not allowed")
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise CanonicalJsonError("object keys must be strings")
        parts = []
        for key in sorted(value):
            parts.append(f"{_encode_string(key)}:{_encode(value[key], depth + 1)}")
        return "{" + ",".join(parts) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_encode(item, depth + 1) for item in value) + "]"
    raise CanonicalJsonError(f"unsupported type: {type(value).__name__}")


def canonical_dumps(value: Any) -> str:
    text = _encode(value)
    text.encode("utf-8", "strict")  # 保证可编码、无孤立代理残留
    return text


def canonical_bytes(value: Any) -> bytes:
    return canonical_dumps(value).encode("utf-8")


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in pairs:
        if key in result:
            raise CanonicalJsonError(f"duplicate key: {key!r}")
        result[key] = item
    return result


def _reject_constant(token: str) -> Any:
    raise CanonicalJsonError(f"non-finite number not allowed: {token}")


def _reject_float(token: str) -> Any:
    raise CanonicalJsonError(f"float not allowed: {token}")


def _parse_int(token: str) -> int:
    if token.startswith("-"):
        raise CanonicalJsonError("negative integer not allowed")
    return int(token)


def canonical_loads(data: str | bytes) -> Any:
    raw = data.encode("utf-8") if isinstance(data, str) else bytes(data)
    if raw.startswith(b"\xef\xbb\xbf"):
        raise CanonicalJsonError("BOM not allowed")
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise CanonicalJsonError("invalid UTF-8") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_no_duplicates,
            parse_constant=_reject_constant,
            parse_float=_reject_float,
            parse_int=_parse_int,
        )
    except CanonicalJsonError:
        raise
    except json.JSONDecodeError as exc:
        raise CanonicalJsonError(f"invalid JSON: {exc.msg}") from exc
    # 严格字节级：必须已是规范形式（无空白/尾随换行/非规范转义）。
    if canonical_dumps(value) != text:
        raise CanonicalJsonError("document is not canonical JSON v1")
    return value


def sha256_canonical(value: Any) -> str:
    return _DIGEST_PREFIX + hashlib.sha256(canonical_bytes(value)).hexdigest()