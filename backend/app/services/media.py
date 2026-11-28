"""知识条目多模态媒体附件服务（图片 / 音频 / 视频 / PDF / 通用文件）。

采用「轻库重盘」架构：文件按 `data_dir/media/{item_id}/{media_id}_{safe_name}` 隔离落盘，
元数据存 `index.json`，支持零额外依赖的原始二进制流上传与 HTTP Range (206) 分片流式播放，
让视频/音频拖动进度条丝滑不卡顿，且 SQLite / PostgreSQL 双库通用、零迁移负担。
"""

from __future__ import annotations

import ctypes
import json
import mimetypes
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

_VALID_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9\u4e00-\u9fff._\- ]+")
MAX_MEDIA_BYTES = 120 * 1024 * 1024  # 单文件上限 120 MB（足以覆盖短视频与长录音）

_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"})
_AUDIO_EXTS = frozenset({".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".opus"})
_VIDEO_EXTS = frozenset({".mp4", ".webm", ".mov", ".mkv", ".m4v"})
_WORD_EXTS = frozenset({".docx", ".doc"})
_EXCEL_EXTS = frozenset({".xlsx", ".xls", ".csv"})
_PPT_EXTS = frozenset({".pptx", ".ppt"})
_ARCHIVE_EXTS = frozenset({".zip"})
_MARKDOWN_EXTS = frozenset({".md", ".markdown"})
_HTML_EXTS = frozenset({".html", ".htm"})
_CODE_EXTS = frozenset(
    {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".sql",
        ".css",
        ".sh",
        ".ps1",
        ".java",
        ".go",
        ".rs",
        ".c",
        ".cpp",
        ".h",
        ".xml",
    }
)


@dataclass
class MediaRecord:
    id: str
    item_id: str
    filename: str
    stored_name: str
    kind: str  # "image" | "audio" | "video" | "pdf" | "file"
    mime: str
    size_bytes: int
    created_at: str


def _validate_id(raw: str, label: str) -> str:
    if not _VALID_ID.match(raw):
        raise ValueError(f"非法的 {label}: {raw}")
    return raw


def _item_dir(data_dir: Path, item_id: str) -> Path:
    _validate_id(item_id, "知识条目 ID")
    root = (data_dir / "media").resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = (root / item_id).resolve()
    if target.parent != root:
        raise ValueError("非法的媒体存储路径")
    target.mkdir(parents=True, exist_ok=True)
    return target


def _index_path(data_dir: Path, item_id: str) -> Path:
    return _item_dir(data_dir, item_id) / "index.json"


def _load_index(data_dir: Path, item_id: str) -> list[MediaRecord]:
    idx = _index_path(data_dir, item_id)
    if not idx.is_file():
        return []
    try:
        raw = json.loads(idx.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return []
        return [MediaRecord(**row) for row in raw if isinstance(row, dict)]
    except Exception:
        return []


def _save_index(data_dir: Path, item_id: str, records: list[MediaRecord]) -> None:
    idx = _index_path(data_dir, item_id)
    idx.write_text(
        json.dumps([asdict(r) for r in records], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def classify_media_kind(filename: str, mime: str) -> str:
    ext = Path(filename).suffix.lower()
    m = mime.lower()
    if ext in _IMAGE_EXTS or m.startswith("image/"):
        return "image"
    if ext in _AUDIO_EXTS or m.startswith("audio/"):
        return "audio"
    if ext in _VIDEO_EXTS or m.startswith("video/"):
        return "video"
    if ext == ".pdf" or m == "application/pdf":
        return "pdf"
    if ext in _WORD_EXTS or "wordprocessingml" in m or m == "application/msword":
        return "word"
    if ext in _EXCEL_EXTS or "spreadsheetml" in m or m == "text/csv":
        return "excel"
    if ext in _PPT_EXTS or "presentationml" in m:
        return "ppt"
    if ext in _ARCHIVE_EXTS or m == "application/zip":
        return "archive"
    if ext in _MARKDOWN_EXTS or m == "text/markdown":
        return "markdown"
    if ext in _HTML_EXTS or m == "text/html":
        return "html"
    if ext in _CODE_EXTS or m == "application/json":
        return "code"
    return "file"


def _sanitize_filename(filename: str) -> str:
    base = Path(filename.strip() or "file.bin").name
    cleaned = _UNSAFE_NAME.sub("_", base).strip(". ")
    if not cleaned:
        cleaned = "file.bin"
    return cleaned[:100]


def list_media(data_dir: Path, item_id: str) -> list[MediaRecord]:
    _validate_id(item_id, "知识条目 ID")
    root = (data_dir / "media" / item_id).resolve()
    if not root.is_dir():
        return []
    records = _load_index(data_dir, item_id)
    return [r for r in records if (root / r.stored_name).is_file()]


def save_media_bytes(
    data_dir: Path,
    item_id: str,
    *,
    filename: str,
    content: bytes,
    mime: str | None = None,
) -> MediaRecord:
    if not content:
        raise ValueError("上传文件内容为空")
    if len(content) > MAX_MEDIA_BYTES:
        raise ValueError(f"文件过大（上限 {MAX_MEDIA_BYTES // (1024 * 1024)} MB）")

    safe_name = _sanitize_filename(filename)
    guessed_mime = (mime or "").split(";")[0].strip()
    if not guessed_mime or guessed_mime == "application/octet-stream":
        guessed_mime = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"

    media_id = uuid4().hex[:16]
    stored_name = f"{media_id}_{safe_name}"
    target_dir = _item_dir(data_dir, item_id)
    dest = (target_dir / stored_name).resolve()
    if dest.parent != target_dir:
        raise ValueError("非法的目标文件路径")
    dest.write_bytes(content)

    record = MediaRecord(
        id=media_id,
        item_id=item_id,
        filename=safe_name,
        stored_name=stored_name,
        kind=classify_media_kind(safe_name, guessed_mime),
        mime=guessed_mime,
        size_bytes=len(content),
        created_at=datetime.now(UTC).isoformat(),
    )
    records = _load_index(data_dir, item_id)
    records.insert(0, record)
    _save_index(data_dir, item_id, records)
    return record


def get_media_file(data_dir: Path, item_id: str, media_id: str) -> tuple[MediaRecord, Path] | None:
    _validate_id(item_id, "知识条目 ID")
    _validate_id(media_id, "媒体 ID")
    target_dir = (data_dir / "media" / item_id).resolve()
    if not target_dir.is_dir():
        return None
    for rec in _load_index(data_dir, item_id):
        if rec.id == media_id:
            fpath = (target_dir / rec.stored_name).resolve()
            if fpath.parent == target_dir and fpath.is_file():
                return rec, fpath
    return None


def list_all_media(data_dir: Path, *, kind: str | None = None) -> list[MediaRecord]:
    """汇总全库所有知识条目下的多模态媒体与文档附件（独立文件库视图，不脱离原知识归属）。"""
    root = (data_dir / "media").resolve()
    if not root.is_dir():
        return []
    out: list[MediaRecord] = []
    for child in root.iterdir():
        if not child.is_dir() or not _VALID_ID.match(child.name):
            continue
        for rec in list_media(data_dir, child.name):
            # 兼容历史记录：若之前把 .docx/.xlsx/.pptx 归为 file，动态矫正分类
            fixed_kind = classify_media_kind(rec.filename, rec.mime)
            if fixed_kind != rec.kind:
                rec = MediaRecord(**{**asdict(rec), "kind": fixed_kind})
            if kind and kind != "all" and rec.kind != kind:
                continue
            out.append(rec)
    out.sort(key=lambda r: r.created_at, reverse=True)
    # 按 (文件名, 大小) 去重，避免同一会话提炼出多条知识或重复导入时在文件库刷屏
    deduped: list[MediaRecord] = []
    seen_keys: set[tuple[str, int]] = set()
    for rec in out:
        key = (rec.filename.strip().lower(), int(rec.size_bytes))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(rec)
    return deduped


def _win32_reveal_path(path: Path) -> bool:
    """使用 Win32 原生 SHOpenFolderAndSelectItems 高亮选中文件（不受空格/逗号/中文/长路径影响）。"""
    try:
        ole32 = ctypes.windll.ole32
        shell32 = ctypes.windll.shell32
        ole32.CoInitialize(None)
        shell32.ILCreateFromPathW.argtypes = [ctypes.c_wchar_p]
        shell32.ILCreateFromPathW.restype = ctypes.c_void_p
        shell32.SHOpenFolderAndSelectItems.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.c_ulong,
        ]
        shell32.SHOpenFolderAndSelectItems.restype = ctypes.c_long
        shell32.ILFree.argtypes = [ctypes.c_void_p]
        pidl = shell32.ILCreateFromPathW(str(path))
        if not pidl:
            return False
        try:
            hr = shell32.SHOpenFolderAndSelectItems(pidl, 0, None, 0)
            return hr == 0
        finally:
            shell32.ILFree(pidl)
    except Exception:
        return False


def reveal_media_in_file_manager(
    data_dir: Path,
    item_id: str,
    media_id: str,
    *,
    open_os: bool = True,
) -> str:
    """在系统资源管理器中打开并高亮选中该附件的本地落盘文件，并返回真实路径供桌面端调用。"""
    found = get_media_file(data_dir, item_id, media_id)
    if found is None:
        raise ValueError("媒体附件不存在")
    _, path = found
    path_str = str(path.resolve())
    if not open_os:
        return path_str
    if sys.platform == "win32":
        if not _win32_reveal_path(path.resolve()):
            rc = ctypes.windll.shell32.ShellExecuteW(
                None, "open", "explorer.exe", f'/select,"{path_str}"', None, 1
            )
            if rc <= 32:
                os.startfile(str(path.parent))  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path_str])
    else:
        subprocess.Popen(["xdg-open", str(path.parent)])
    return path_str


def delete_media(data_dir: Path, item_id: str, media_id: str) -> bool:
    _validate_id(item_id, "知识条目 ID")
    _validate_id(media_id, "媒体 ID")
    target_dir = (data_dir / "media" / item_id).resolve()
    if not target_dir.is_dir():
        return False
    records = _load_index(data_dir, item_id)
    kept: list[MediaRecord] = []
    deleted = False
    for rec in records:
        if rec.id == media_id:
            fpath = (target_dir / rec.stored_name).resolve()
            if fpath.parent == target_dir and fpath.is_file():
                fpath.unlink(missing_ok=True)
            deleted = True
        else:
            kept.append(rec)
    if deleted:
        _save_index(data_dir, item_id, kept)
    return deleted


def parse_byte_range(range_header: str, file_size: int) -> tuple[int, int] | None:
    """解析 HTTP Range 头（bytes=start-end），用于音视频流式拖动播放。"""
    if not range_header or not range_header.lower().startswith("bytes="):
        return None
    spec = range_header[6:].split(",")[0].strip()
    if "-" not in spec:
        return None
    start_s, end_s = spec.split("-", 1)
    try:
        if not start_s:
            suffix_len = int(end_s)
            if suffix_len <= 0:
                return None
            start = max(0, file_size - suffix_len)
            end = file_size - 1
        else:
            start = int(start_s)
            end = int(end_s) if end_s else file_size - 1
    except ValueError:
        return None
    if start < 0 or start >= file_size:
        return None
    end = min(end, file_size - 1)
    if end < start:
        return None
    return start, end
