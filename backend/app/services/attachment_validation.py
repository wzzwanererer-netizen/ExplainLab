"""Pure validation for the frozen Batch B attachment upload contract."""

from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import PureWindowsPath

from app.core.config import DEFAULT_ATTACHMENT_MIME_ALLOWLIST

ATTACHMENT_BASE64_INVALID = "ATTACHMENT_BASE64_INVALID"
ATTACHMENT_CONTENT_MISMATCH = "ATTACHMENT_CONTENT_MISMATCH"
ATTACHMENT_EMPTY = "ATTACHMENT_EMPTY"
ATTACHMENT_FILENAME_INVALID = "ATTACHMENT_FILENAME_INVALID"
ATTACHMENT_MIME_UNSUPPORTED = "ATTACHMENT_MIME_UNSUPPORTED"
ATTACHMENT_TOO_LARGE = "ATTACHMENT_TOO_LARGE"

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_FILENAME_LENGTH = 500
_TEXT_MIMES = frozenset({"text/plain", "text/markdown", "text/csv"})
_BINARY_SIGNATURES = (
    ("image/png", (b"\x89PNG\r\n\x1a\n",)),
    ("image/jpeg", (b"\xff\xd8\xff",)),
    ("image/gif", (b"GIF87a", b"GIF89a")),
    ("application/pdf", (b"%PDF-",)),
)
_UNSAFE_FILENAME_CHARACTERS = str.maketrans({char: "_" for char in '/\\:<>"|?*'})


class AttachmentValidationError(ValueError):
    """A rejected upload, carrying only a stable error code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ValidatedAttachment:
    filename: str
    mime: str
    data: bytes


def sanitize_attachment_filename(filename: str) -> str:
    """Return a display name from either Windows or POSIX spelling."""
    if not 1 <= len(filename) <= MAX_FILENAME_LENGTH:
        raise AttachmentValidationError(ATTACHMENT_FILENAME_INVALID)
    basename = filename.replace("\\", "/").rsplit("/", 1)[-1]
    basename = "".join(
        char for char in basename if unicodedata.category(char) not in {"Cc", "Cs"}
    )
    name = re.sub(r"\.{2,}", ".", basename.translate(_UNSAFE_FILENAME_CHARACTERS))
    name = name.strip().rstrip(". ")
    if name and PureWindowsPath(name).is_reserved():
        name = f"_{name}"
    if not name or len(name) > MAX_FILENAME_LENGTH:
        raise AttachmentValidationError(ATTACHMENT_FILENAME_INVALID)
    return name


def _decode_base64(encoded: str, max_bytes: int) -> bytes:
    if len(encoded) > 4 * ((max_bytes + 2) // 3):
        raise AttachmentValidationError(ATTACHMENT_TOO_LARGE)
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise AttachmentValidationError(ATTACHMENT_BASE64_INVALID) from None

    # Strict decoding alone permits some redundant padding and nonzero pad bits.
    if len(encoded) != 4 * ((len(data) + 2) // 3):
        raise AttachmentValidationError(ATTACHMENT_BASE64_INVALID)
    remainder = len(data) % 3
    if remainder and base64.b64encode(data[-remainder:]).decode("ascii") != encoded[-4:]:
        raise AttachmentValidationError(ATTACHMENT_BASE64_INVALID)
    if not data:
        raise AttachmentValidationError(ATTACHMENT_EMPTY)
    if len(data) > max_bytes:
        raise AttachmentValidationError(ATTACHMENT_TOO_LARGE)
    return data


def _binary_mime(header: bytes) -> str | None:
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    for mime, signatures in _BINARY_SIGNATURES:
        if header.startswith(signatures):
            return mime
    return None


def _validate_content(data: bytes, mime: str) -> None:
    detected = _binary_mime(data[:16])
    if mime in _TEXT_MIMES:
        if detected is not None or b"\x00" in data:
            raise AttachmentValidationError(ATTACHMENT_CONTENT_MISMATCH)
        try:
            data.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise AttachmentValidationError(ATTACHMENT_CONTENT_MISMATCH) from None
    elif detected != mime:
        raise AttachmentValidationError(ATTACHMENT_CONTENT_MISMATCH)


def validate_attachment_upload(
    filename: str,
    declared_mime: str,
    content_base64: str,
    *,
    max_bytes: int = MAX_ATTACHMENT_BYTES,
    mime_allowlist: Collection[str] = DEFAULT_ATTACHMENT_MIME_ALLOWLIST,
) -> ValidatedAttachment:
    """Validate upload fields and return the safe name, declared MIME, and bytes."""
    mime = declared_mime.partition(";")[0].strip().lower()
    if mime not in DEFAULT_ATTACHMENT_MIME_ALLOWLIST or mime not in mime_allowlist:
        raise AttachmentValidationError(ATTACHMENT_MIME_UNSUPPORTED)

    data = _decode_base64(content_base64, min(max_bytes, MAX_ATTACHMENT_BYTES))
    _validate_content(data, mime)
    return ValidatedAttachment(sanitize_attachment_filename(filename), mime, data)
