from __future__ import annotations

from base64 import b64encode
from unittest.mock import patch

import pytest

from app.services import attachment_validation as validation


def _validate(data: bytes, mime: str, filename: str = "attachment.txt"):
    return validation.validate_attachment_upload(filename, mime, b64encode(data).decode("ascii"))


@pytest.mark.parametrize(("mime", "data"), [
    ("image/png", b"\x89PNG\r\n\x1a\nrest"),
    ("image/jpeg", b"\xff\xd8\xffrest"),
    ("image/gif", b"GIF87arest"),
    ("image/gif", b"GIF89arest"),
    ("image/webp", b"RIFF\x04\x00\x00\x00WEBPrest"),
    ("application/pdf", b"%PDF-1.7\n"),
])
def test_binary_magic_and_declared_mime_are_authoritative(mime, data):
    result = _validate(data, f" {mime.upper()}; parameter=value", "mismatched.txt")
    assert (result.filename, result.mime, result.data) == ("mismatched.txt", mime, data)


@pytest.mark.parametrize("mime", ["text/plain", "text/markdown", "text/csv"])
@pytest.mark.parametrize("text", ["普通文本", "# Markdown", "a,b\n1,2", "\ufeff仓库", "<svg/>"])
def test_text_subtypes_share_utf8_validation_and_keep_declared_mime(mime, text):
    data = text.encode()
    result = _validate(data, mime, "中文说明.svg")
    assert (result.mime, result.data) == (mime, data)


@pytest.mark.parametrize(("mime", "data"), [
    ("image/png", b"\xff\xd8\xffrest"),
    ("image/png", b"plain text"),
    ("image/webp", b"RIFF0000WAVE"),
    ("image/webp", b"RIFF0000WEB"),
    ("image/gif", b"GIF88a"),
    ("text/plain", b"\x89PNG\r\n\x1a\n"),
    ("text/plain", b"%PDF-1.7"),  # Valid UTF-8 without NUL, but known binary magic.
    ("text/markdown", b"GIF89a"),
    ("text/csv", b"not\x00text"),
    ("text/csv", b"not\xffutf8"),
])
def test_invalid_magic_or_text_is_rejected(mime, data):
    with pytest.raises(validation.AttachmentValidationError) as caught:
        _validate(data, mime, "pretends-to-be.png")
    assert caught.value.code == validation.ATTACHMENT_CONTENT_MISMATCH


@pytest.mark.parametrize("mime", ["image/svg+xml", " IMAGE/SVG+XML; x=y ", "application/zip", ""])
def test_unsupported_mime_is_rejected_even_if_configured(mime):
    with pytest.raises(validation.AttachmentValidationError) as caught:
        validation.validate_attachment_upload(
            "vector.svg", mime, "PHN2Zy8+", mime_allowlist={mime.partition(";")[0].strip().lower()}
        )
    assert caught.value.code == validation.ATTACHMENT_MIME_UNSUPPORTED


@pytest.mark.parametrize("encoded", ["YQ", "YQ=", "YQ===", "YQ==\n", "Y!==", "é===", "_w==",
                                    "YWJj====", "YR==", "YWJ=", "YQ==Yg=="])
def test_rejects_nonstandard_or_invalid_base64(encoded):
    with pytest.raises(validation.AttachmentValidationError) as caught:
        validation.validate_attachment_upload("note.txt", "text/plain", encoded)
    assert caught.value.code == validation.ATTACHMENT_BASE64_INVALID


def test_empty_attachment_reports_its_own_error():
    with pytest.raises(validation.AttachmentValidationError) as caught:
        _validate(b"", "text/plain")
    assert caught.value.code == validation.ATTACHMENT_EMPTY


def test_attachment_size_limit_checks_actual_decoded_bytes():
    data = b"a" * (10 * 1024 * 1024)
    assert _validate(data, "text/plain").data == data
    # 10 MiB and 10 MiB + 1 have the same encoded length, so the byte gate matters.
    assert len(b64encode(data)) == len(b64encode(data + b"b"))
    with pytest.raises(validation.AttachmentValidationError) as caught:
        _validate(data + b"b", "text/plain")
    assert caught.value.code == validation.ATTACHMENT_TOO_LARGE


def test_11_mib_is_rejected_before_decoding():
    encoded = b64encode(b"a" * (11 * 1024 * 1024)).decode("ascii")
    with (
        patch.object(validation.base64, "b64decode") as decode,
        pytest.raises(validation.AttachmentValidationError) as caught,
    ):
        validation.validate_attachment_upload("note.txt", "text/plain", encoded)
    assert caught.value.code == validation.ATTACHMENT_TOO_LARGE
    decode.assert_not_called()


def test_optional_settings_can_narrow_frozen_limits():
    with pytest.raises(validation.AttachmentValidationError) as caught:
        validation.validate_attachment_upload("note.txt", "text/plain", "YWJj", max_bytes=2)
    assert caught.value.code == validation.ATTACHMENT_TOO_LARGE

    with pytest.raises(validation.AttachmentValidationError) as caught:
        validation.validate_attachment_upload(
            "note.txt", "text/plain", "YWJj", mime_allowlist={"application/pdf"}
        )
    assert caught.value.code == validation.ATTACHMENT_MIME_UNSUPPORTED


@pytest.mark.parametrize(("raw", "safe"), [
    ("../../evil.png", "evil.png"),
    (r"C:\x.png", "x.png"),
    (r"\\server\share\说明..稿.pdf", "说明.稿.pdf"),
    ("目录/中\r\n\t\x00\u0085文:说明.pdf", "中文_说明.pdf"),
    ('name"with?quotes. ', "name_with_quotes"),
    ("NUL.txt", "_NUL.txt"),
    ("cOm¹.pdf", "_cOm¹.pdf"),
    (" LPT1. ", "_LPT1"),
    ("便签📎.md", "便签📎.md"),
    ("a" * 500, "a" * 500),
])
def test_filename_sanitization(raw, safe):
    assert validation.sanitize_attachment_filename(raw) == safe


@pytest.mark.parametrize("raw", ["", "  ", "..", "dir/", "\x00\r\n", "a" * 501])
def test_empty_or_oversized_display_name_is_rejected(raw):
    with pytest.raises(validation.AttachmentValidationError) as caught:
        _validate(b"ok", "text/plain", raw)
    assert caught.value.code == validation.ATTACHMENT_FILENAME_INVALID
