"""乱文件夹哨兵（Folder Watcher）：严格只读监听本地杂乱文件夹并自动收编进知识库。

支持：
- L1 免费极速收编（零 Token）：抽取 `.md / .txt / .docx / .pdf / 代码 / CSV / 图片 / 音视频`
  内容与元数据，写入指定专题空间，并记录原始本地路径；
- L2 可选 AI 智能总结：将杂乱文档提炼成条理清晰的 Markdown 卡片与 `#标签`；
- 游标去重：仅增量扫描新增或修改过的文件，不重复入库；
- 严格只读：绝不移动、修改或删除用户原文件。
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import KnowledgeItemORM, KnowledgeSpace
from app.services.agent_hub import sanitize_sensitive_text, vacuum_media_dir
from app.services.knowledge import SQLAlchemyKnowledgeRepository
from app.services.media import list_media, save_media_bytes
from knowledge_core.domain.entities import (
    KnowledgeItem,
    KnowledgeStatus,
    SourceRef,
    SourceType,
)
from knowledge_core.model_adapter import ModelAdapter, ModelMessage, ModelRequest

_SKIP_DIRS = frozenset(
    {
        ".git",
        ".svn",
        ".hg",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        "dist",
        "build",
        ".next",
        ".cache",
        "$recycle.bin",
        "system volume information",
    }
)

_TEXT_EXTS = frozenset(
    {
        ".md",
        ".markdown",
        ".txt",
        ".csv",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".java",
        ".go",
        ".rs",
        ".c",
        ".cpp",
        ".h",
        ".sql",
        ".html",
        ".css",
        ".sh",
        ".ps1",
        ".log",
    }
)
_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})
_AV_EXTS = frozenset({".mp3", ".wav", ".m4a", ".ogg", ".flac", ".mp4", ".webm", ".mov"})
_DOC_EXTS = frozenset({".docx", ".doc", ".pdf", ".xlsx", ".xls", ".pptx", ".ppt", ".zip"})
_SUPPORTED_EXTS = _TEXT_EXTS | _IMAGE_EXTS | _AV_EXTS | _DOC_EXTS

MAX_SCAN_FILE_BYTES = 25 * 1024 * 1024  # 超过 25 MB 的超大文件跳过，避免卡顿

_FOLDER_SUMMARY_PROMPT = """你是 ExplainLab 个人知识库的「文件夹资料整理管家」。
请阅读这份从用户本地文件夹扫描到的文件摘录，用简洁清晰的中文 Markdown 总结出它的核心知识要点（3~6 条要点，末尾附 2~4 个 `#标签`）。
要求：
1. 直接输出整理好的 Markdown 正文，不要重复输出文件名标题，也不要寒暄。
2. 严禁包含任何 API Key、密码或敏感凭证。
"""


@dataclass
class WatchedFolder:
    id: str
    name: str
    path: str
    space_id: str
    space_name: str
    enabled: bool = True
    use_ai_summary: bool = False
    file_count: int = 0
    indexed_count: int = 0
    last_scan_at: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class FolderScanCreatedItem:
    id: str
    title: str
    file_path: str
    kind: str


@dataclass
class FolderScanReport:
    folder_id: str
    scanned_files: int = 0
    skipped_files: int = 0
    created_items: list[FolderScanCreatedItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _state_path(data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "watched_folders.json"


def _load_state(data_dir: Path) -> dict[str, Any]:
    path = _state_path(data_dir)
    if not path.is_file():
        return {"folders": [], "cursors": {}}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            parsed.setdefault("folders", [])
            parsed.setdefault("cursors", {})
            return parsed
    except Exception:
        pass
    return {"folders": [], "cursors": {}}


def _save_state(data_dir: Path, state: dict[str, Any]) -> None:
    _state_path(data_dir).write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_preset_folders() -> list[dict[str, str]]:
    """返回本机常见杂乱文件夹快捷入口（桌面 / 下载 / 文档）。"""
    home = Path.home()
    candidates = [
        ("桌面 (Desktop)", home / "Desktop"),
        ("下载 (Downloads)", home / "Downloads"),
        ("文档 (Documents)", home / "Documents"),
    ]
    return [
        {"label": label, "path": str(p.resolve())}
        for label, p in candidates
        if p.is_dir()
    ]


def _list_folder_files(folder_path: Path, *, max_depth: int = 3) -> list[Path]:
    if not folder_path.is_dir():
        return []
    found: list[Path] = []
    root_depth = len(folder_path.parts)
    try:
        for dirpath, dirnames, filenames in os.walk(folder_path):
            cur = Path(dirpath)
            depth = len(cur.parts) - root_depth
            dirnames[:] = [
                d
                for d in dirnames
                if depth < max_depth
                and not d.startswith(".")
                and d.lower() not in _SKIP_DIRS
            ]
            for fname in filenames:
                if fname.startswith(".") or fname.startswith("~$"):
                    continue
                fpath = cur / fname
                if fpath.suffix.lower() not in _SUPPORTED_EXTS:
                    continue
                try:
                    st = fpath.stat()
                    if 0 < st.st_size <= MAX_SCAN_FILE_BYTES:
                        found.append(fpath)
                except OSError:
                    continue
    except OSError:
        return []
    # 优先收编 Word / Excel / PPT / PDF 等核心办公文档，避免被海量零散文本/日志淹没
    priority_exts = frozenset({".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".pdf", ".csv"})
    return sorted(
        found,
        key=lambda p: (0 if p.suffix.lower() in priority_exts else 1, -p.stat().st_mtime),
    )


def _file_sig(path: Path) -> str:
    st = path.stat()
    return f"{int(st.st_mtime)}:{st.st_size}"


def list_watched_folders(data_dir: Path) -> list[WatchedFolder]:
    state = _load_state(data_dir)
    cursors: dict[str, str] = state.get("cursors", {})
    out: list[WatchedFolder] = []
    for raw in state.get("folders", []):
        if not isinstance(raw, dict):
            continue
        folder = WatchedFolder(**raw)
        files = _list_folder_files(Path(folder.path))
        folder.file_count = len(files)
        folder.indexed_count = sum(
            1 for f in files if cursors.get(str(f.resolve())) == _file_sig(f)
        )
        out.append(folder)
    return out


def add_watched_folder(
    session: Session,
    data_dir: Path,
    *,
    path: str,
    name: str | None = None,
    space_id: str | None = None,
    use_ai_summary: bool = False,
) -> WatchedFolder:
    resolved = Path(path.strip()).expanduser().resolve()
    if not resolved.is_dir():
        raise ValueError(f"文件夹不存在或无法访问: {resolved}")

    state = _load_state(data_dir)
    for raw in state["folders"]:
        if Path(raw["path"]).resolve() == resolved:
            return WatchedFolder(**raw)

    display_name = (name or resolved.name or "本地文件夹").strip()[:60]
    if space_id:
        space = session.get(KnowledgeSpace, space_id)
        if space is None:
            raise ValueError(f"目标知识空间不存在: {space_id}")
    else:
        sp_name = f"文件夹 · {display_name}"
        space = session.scalar(
            select(KnowledgeSpace).where(func.lower(KnowledgeSpace.name) == sp_name.lower())
        )
        if space is None:
            space = KnowledgeSpace(
                id=str(uuid4()),
                name=sp_name,
                kind="project",
                description=f"由文件夹哨兵自动收编：{resolved}",
            )
            session.add(space)
            session.commit()

    folder = WatchedFolder(
        id=uuid4().hex[:12],
        name=display_name,
        path=str(resolved),
        space_id=space.id,
        space_name=space.name,
        enabled=True,
        use_ai_summary=use_ai_summary,
    )
    state["folders"].append(asdict(folder))
    _save_state(data_dir, state)
    files = _list_folder_files(resolved)
    folder.file_count = len(files)
    return folder


def update_watched_folder(
    data_dir: Path,
    folder_id: str,
    *,
    enabled: bool | None = None,
    use_ai_summary: bool | None = None,
) -> WatchedFolder | None:
    state = _load_state(data_dir)
    for raw in state["folders"]:
        if raw.get("id") == folder_id:
            if enabled is not None:
                raw["enabled"] = enabled
            if use_ai_summary is not None:
                raw["use_ai_summary"] = use_ai_summary
            _save_state(data_dir, state)
            return WatchedFolder(**raw)
    return None


def delete_watched_folder(data_dir: Path, folder_id: str) -> bool:
    state = _load_state(data_dir)
    before = len(state["folders"])
    state["folders"] = [r for r in state["folders"] if r.get("id") != folder_id]
    if len(state["folders"]) == before:
        return False
    _save_state(data_dir, state)
    return True


def _extract_docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as zf:
            xml_bytes = zf.read("word/document.xml")
        root = ET.fromstring(xml_bytes)
        paragraphs: list[str] = []
        for p in root.iter():
            if p.tag.endswith("}p"):
                texts = [t.text for t in p.iter() if t.tag.endswith("}t") and t.text]
                if texts:
                    paragraphs.append("".join(texts))
        return "\n".join(paragraphs).strip()
    except Exception:
        return ""


def _extract_pdf_text(path: Path) -> str:
    try:
        import pypdf  # type: ignore[import-not-found]

        reader = pypdf.PdfReader(str(path))
        parts = [(page.extract_text() or "").strip() for page in reader.pages[:15]]
        return "\n\n".join(p for p in parts if p).strip()
    except Exception:
        pass
    # 纯标准库兜底：尝试抓取未压缩 PDF 文本流中的可读片段
    try:
        raw = path.read_bytes()[:512 * 1024]
        matches = re.findall(rb"\(([^()\\]{4,200})\)", raw)
        decoded = [m.decode("utf-8", errors="ignore").strip() for m in matches[:80]]
        return "\n".join(d for d in decoded if d).strip()
    except Exception:
        return ""


def extract_file_text(path: Path, *, max_chars: int = 8000) -> str:
    ext = path.suffix.lower()
    if ext in _TEXT_EXTS:
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
    elif ext == ".docx":
        text = _extract_docx_text(path)
    elif ext == ".pdf":
        text = _extract_pdf_text(path)
    else:
        text = ""
    return sanitize_sensitive_text(text[:max_chars])


async def scan_watched_folder(
    session: Session,
    adapter: ModelAdapter | None,
    *,
    data_dir: Path,
    folder_id: str,
    max_files: int = 12,
) -> FolderScanReport:
    """增量扫描单个监控文件夹，将新增或改动的文件收编入对应知识空间。"""
    state = _load_state(data_dir)
    raw_folder = next((r for r in state["folders"] if r.get("id") == folder_id), None)
    if raw_folder is None:
        raise ValueError(f"监控文件夹不存在: {folder_id}")

    folder = WatchedFolder(**raw_folder)
    root = Path(folder.path)
    if not root.is_dir():
        raise ValueError(f"文件夹路径不可访问: {folder.path}")

    cursors: dict[str, str] = state.setdefault("cursors", {})
    files = _list_folder_files(root)
    pending = [f for f in files if cursors.get(str(f.resolve())) != _file_sig(f)][:max_files]

    report = FolderScanReport(folder_id=folder_id)
    if not pending:
        raw_folder["last_scan_at"] = datetime.now(UTC).isoformat()
        _save_state(data_dir, state)
        return report

    existing_by_title = {
        row.title.strip().lower(): row
        for row in session.scalars(
            select(KnowledgeItemORM).where(KnowledgeItemORM.space_id == folder.space_id)
        ).all()
    }
    repo = SQLAlchemyKnowledgeRepository(session)
    media_root = vacuum_media_dir(data_dir)
    attachable_exts = _AV_EXTS | _DOC_EXTS | {".csv"}

    for fpath in pending:
        fkey = str(fpath.resolve())
        sig = _file_sig(fpath)
        ext = fpath.suffix.lower()
        rel_display = str(fpath.relative_to(root))
        title = fpath.stem[:100]
        report.scanned_files += 1

        existing_row = existing_by_title.get(title.lower())
        if existing_row is not None:
            # 同名不同格式（例如 论文.docx 与 论文.pdf）：直接将孪生文件合并挂载到同一张知识卡片下
            if ext in attachable_exts:
                already_files = {m.filename for m in list_media(data_dir, existing_row.id)}
                if fpath.name not in already_files:
                    try:
                        save_media_bytes(
                            data_dir,
                            existing_row.id,
                            filename=fpath.name,
                            content=fpath.read_bytes(),
                        )
                        report.created_items.append(
                            FolderScanCreatedItem(
                                id=existing_row.id,
                                title=f"{existing_row.title} (+{fpath.suffix})",
                                file_path=str(fpath),
                                kind="document",
                            )
                        )
                    except Exception as exc:
                        report.errors.append(f"{rel_display}: {type(exc).__name__}")
                else:
                    report.skipped_files += 1
            else:
                report.skipped_files += 1
            cursors[fkey] = sig
            continue

        try:
            if ext in _IMAGE_EXTS:
                raw_bytes = fpath.read_bytes()
                digest = hashlib.sha256(raw_bytes).hexdigest()[:16]
                stored_name = f"{digest}{ext}"
                dest = media_root / stored_name
                if not dest.exists():
                    dest.write_bytes(raw_bytes)
                content = (
                    f"![{title}](/api/agents/media/{stored_name})\n"
                    f"**{title}**\n"
                    f"- 来源路径：`{rel_display}`\n"
                    f"- 文件大小：{round(len(raw_bytes) / 1024, 1)} KB\n"
                    f"> 由文件夹哨兵自动收编自「{folder.name}」\n\n"
                    f"#文件夹收编 #图片素材 #{folder.name}"
                )
                kind = "image"
                attach_av = False
            elif ext in _AV_EXTS:
                size_mb = round(fpath.stat().st_size / (1024 * 1024), 2)
                kind = "audio" if ext in {".mp3", ".wav", ".m4a", ".ogg", ".flac"} else "video"
                content = (
                    f"## 音视频资料 · {title}\n"
                    f"- 来源路径：`{rel_display}`\n"
                    f"- 媒体类型：{kind.upper()}（{size_mb} MB）\n"
                    f"- 已自动挂载到下方「附件 / 音视频」面板，可直接原位播放与拖动进度条。\n\n"
                    f"#文件夹收编 #{kind} #{folder.name}"
                )
                attach_av = True
            else:
                extracted = extract_file_text(fpath)
                kind = "document"
                attach_av = False
                if folder.use_ai_summary and adapter is not None and len(extracted) >= 120:
                    try:
                        resp = await adapter.generate(
                            ModelRequest(
                                messages=[
                                    ModelMessage(role="system", content=_FOLDER_SUMMARY_PROMPT),
                                    ModelMessage(
                                        role="user",
                                        content=f"文件名：{rel_display}\n\n内容摘录：\n{extracted}",
                                    ),
                                ],
                                temperature=0.25,
                                max_tokens=1200,
                            )
                        )
                        body = sanitize_sensitive_text(resp.content.strip())
                    except Exception:
                        body = extracted[:2500]
                else:
                    body = extracted[:3000] if extracted else f"本地文档文件：`{rel_display}`（暂未提取到纯文本内容）"

                content = (
                    f"{body}\n\n"
                    f"> 原文件：`{rel_display}` · 所属监控目录：{folder.name}\n\n"
                    f"#文件夹收编 #{folder.name}"
                )

            item = KnowledgeItem(
                title=title,
                content=content,
                status=KnowledgeStatus.DRAFT,
                space_id=folder.space_id,
                source_refs=[
                    SourceRef(
                        source_type=SourceType.DOCUMENT,
                        uri=fpath.as_uri(),
                        excerpt=str(fpath),
                    )
                ],
            )
            saved = repo.save(item)
            saved_orm = session.get(KnowledgeItemORM, str(saved.id))
            if saved_orm is not None:
                existing_by_title[title.lower()] = saved_orm

            # 音视频、Office/PDF 文档或 ZIP 同步挂载到多模态媒体面板，卡片内即可直接原位阅读/播放
            if attach_av or ext in _DOC_EXTS or ext == ".csv":
                save_media_bytes(
                    data_dir,
                    str(saved.id),
                    filename=fpath.name,
                    content=fpath.read_bytes(),
                )

            report.created_items.append(
                FolderScanCreatedItem(
                    id=str(saved.id),
                    title=saved.title,
                    file_path=str(fpath),
                    kind=kind,
                )
            )
            cursors[fkey] = sig
        except Exception as exc:
            report.errors.append(f"{rel_display}: {type(exc).__name__}")

    session.commit()
    raw_folder["last_scan_at"] = datetime.now(UTC).isoformat()
    _save_state(data_dir, state)
    return report


def reveal_in_file_manager(data_dir: Path, raw_path: str) -> str:
    """在系统文件管理器中定位并高亮原文件（严格限定在已登记监控目录内）。"""
    target = Path(raw_path.strip()).resolve()
    if not target.exists():
        raise ValueError("目标文件或目录不存在")

    allowed_roots = [Path(f.path).resolve() for f in list_watched_folders(data_dir)]
    if not any(target == r or r in target.parents for r in allowed_roots):
        raise ValueError("仅允许打开已登记监控目录内的文件")

    target_str = str(target)
    if sys.platform == "win32":
        args = f'/select,"{target_str}"' if target.is_file() else f'"{target_str}"'
        rc = ctypes.windll.shell32.ShellExecuteW(None, "open", "explorer.exe", args, None, 1)
        if rc <= 32:
            subprocess.Popen(f"explorer.exe {args}")
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", target_str])
    else:
        subprocess.Popen(["xdg-open", str(target.parent if target.is_file() else target)])
    return target_str
