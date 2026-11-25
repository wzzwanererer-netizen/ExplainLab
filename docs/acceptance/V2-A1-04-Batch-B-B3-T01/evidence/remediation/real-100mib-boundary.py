"""Real 100 MiB ZIP budget check against the production parser.

Builds a genuine ZIP archive whose single stored attachment exceeds the
frozen 100 MiB total budget by one byte and feeds it to
``parse_import_zip``.  The parser must reject from central-directory
metadata without extracting the entry.
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))

from backend.app.services.attachment_staging import (  # noqa: E402
    IMPORT_ARCHIVE_INVALID,
    MAX_TOTAL_BYTES,
    AttachmentStagingError,
    parse_import_zip,
)


def main() -> int:
    assert MAX_TOTAL_BYTES == 100 * 1024 * 1024, MAX_TOTAL_BYTES
    print(f"frozen MAX_TOTAL_BYTES = {MAX_TOTAL_BYTES} (100 MiB, not relaxed)")

    entry_size = MAX_TOTAL_BYTES + 1
    payload = b"\x00" * entry_size
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("doc.md", "# demo\n")
        archive.writestr("attachments/huge.txt", payload)
    data = buffer.getvalue()
    print(f"real archive bytes = {len(data)}")
    print(f"declared entry bytes = {entry_size}")

    try:
        parse_import_zip(data)
    except AttachmentStagingError as exc:
        print(f"rejected code = {exc.code}")
        assert exc.code == IMPORT_ARCHIVE_INVALID, exc.code
        return 0
    raise AssertionError("oversized archive was accepted")


if __name__ == "__main__":
    raise SystemExit(main())