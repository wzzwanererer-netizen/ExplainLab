"""多格式文档结构化预览解析引擎（Word .docx / Excel .xlsx & .csv / PPT .pptx / PDF）。

全部基于 Python 标准库（zipfile + xml.etree.ElementTree + csv）实现，零重型外部依赖，
100% 离线运行，毫秒级提取标题、段落、表格、多 Sheet 数据、幻灯片要点、备注与内嵌图片。
"""

from __future__ import annotations

import contextlib
import csv
import hashlib
import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

from app.services.agent_hub import vacuum_media_dir
from app.services.media import _CODE_EXTS

_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})


def _store_embedded_image(data_dir: Path, raw: bytes, ext: str) -> str | None:
    ext_low = ext.lower()
    if ext_low not in _IMAGE_EXTS or len(raw) < 128 or len(raw) > 12 * 1024 * 1024:
        return None
    digest = hashlib.sha256(raw).hexdigest()[:16]
    stored = f"{digest}{ext_low}"
    dest = vacuum_media_dir(data_dir) / stored
    if not dest.exists():
        dest.write_bytes(raw)
    return f"/api/agents/media/{stored}"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def parse_docx_preview(path: Path, data_dir: Path) -> dict[str, Any]:
    """解析 .docx 为结构化块列表（heading / paragraph / table / image）。"""
    blocks: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(path) as zf:
            # 1) 解析图片关系映射 rId -> /api/agents/media/...
            rel_images: dict[str, str] = {}
            if "word/_rels/document.xml.rels" in zf.namelist():
                rel_root = ET.fromstring(zf.read("word/_rels/document.xml.rels"))
                for rel in rel_root:
                    rid = rel.attrib.get("Id", "")
                    target = rel.attrib.get("Target", "")
                    if not rid or not target:
                        continue
                    member = f"word/{target.lstrip('/')}"
                    if member in zf.namelist():
                        url = _store_embedded_image(
                            data_dir, zf.read(member), Path(member).suffix
                        )
                        if url:
                            rel_images[rid] = url

            if "word/document.xml" not in zf.namelist():
                return {"kind": "word", "blocks": [], "warning": "未找到 Word 正文内容"}

            doc_root = ET.fromstring(zf.read("word/document.xml"))
            body = next((el for el in doc_root if _local(el.tag) == "body"), None)
            if body is None:
                return {"kind": "word", "blocks": []}

            for child in body:
                tag = _local(child.tag)
                if tag == "p":
                    # 检测是否含内嵌图片 blip
                    for el in child.iter():
                        if _local(el.tag) == "blip":
                            for attr_k, attr_v in el.attrib.items():
                                if attr_k.endswith("embed") and attr_v in rel_images:
                                    blocks.append({"type": "image", "src": rel_images[attr_v]})

                    # 检测标题样式
                    level = 0
                    for el in child.iter():
                        if _local(el.tag) == "pStyle":
                            val = next(iter(el.attrib.values()), "")
                            m = re.search(r"Heading(\d)|标题\s*(\d)", val, re.IGNORECASE)
                            if m:
                                level = min(4, int(m.group(1) or m.group(2)))
                            break

                    text = "".join(
                        el.text for el in child.iter() if _local(el.tag) == "t" and el.text
                    ).strip()
                    if text:
                        if level > 0:
                            blocks.append({"type": "heading", "level": level, "text": text})
                        else:
                            blocks.append({"type": "paragraph", "text": text})

                elif tag == "tbl":
                    rows: list[list[str]] = []
                    for tr in child:
                        if _local(tr.tag) != "tr":
                            continue
                        row_cells: list[str] = []
                        for tc in tr:
                            if _local(tc.tag) != "tc":
                                continue
                            cell_text = " ".join(
                                "".join(
                                    t.text for t in p.iter() if _local(t.tag) == "t" and t.text
                                ).strip()
                                for p in tc
                                if _local(p.tag) == "p"
                            ).strip()
                            row_cells.append(cell_text)
                        if any(row_cells):
                            rows.append(row_cells)
                    if rows:
                        blocks.append({"type": "table", "rows": rows})
    except zipfile.BadZipFile:
        return {
            "kind": "word",
            "blocks": [],
            "warning": "该文件不是标准 .docx（可能是老式 .doc 二进制格式），请下载或用本机 Office/WPS 打开。",
        }
    return {"kind": "word", "blocks": blocks[:600]}


def _col_ref_to_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha()).upper()
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return max(0, idx - 1)


def parse_xlsx_preview(path: Path, *, max_rows: int = 400) -> dict[str, Any]:
    """纯标准库解析 .xlsx 多 Sheet 电子表格。"""
    sheets: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            shared_strings: list[str] = []
            if "xl/sharedStrings.xml" in names:
                ss_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
                for si in ss_root:
                    if _local(si.tag) == "si":
                        txt = "".join(
                            t.text for t in si.iter() if _local(t.tag) == "t" and t.text
                        )
                        shared_strings.append(txt)

            # 解析 workbook 中的 Sheet 名称与路径
            sheet_entries: list[tuple[str, str]] = []
            if "xl/workbook.xml" in names:
                rel_map: dict[str, str] = {}
                if "xl/_rels/workbook.xml.rels" in names:
                    rel_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
                    for rel in rel_root:
                        rid = rel.attrib.get("Id", "")
                        tgt = rel.attrib.get("Target", "").lstrip("/")
                        if rid and tgt:
                            rel_map[rid] = tgt if tgt.startswith("xl/") else f"xl/{tgt}"
                wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
                for sh in wb_root.iter():
                    if _local(sh.tag) == "sheet":
                        sname = sh.attrib.get("name", "Sheet")
                        rid = next(
                            (v for k, v in sh.attrib.items() if k.endswith("id")),
                            "",
                        )
                        member = rel_map.get(rid, "")
                        if member and member in names:
                            sheet_entries.append((sname, member))

            if not sheet_entries:
                for n in sorted(names):
                    if re.match(r"^xl/worksheets/sheet\d+\.xml$", n):
                        sheet_entries.append((Path(n).stem, n))

            for sname, member in sheet_entries[:12]:
                sh_root = ET.fromstring(zf.read(member))
                rows: list[list[str]] = []
                total_rows = 0
                for row_el in sh_root.iter():
                    if _local(row_el.tag) != "row":
                        continue
                    total_rows += 1
                    if len(rows) >= max_rows:
                        continue
                    cells_dict: dict[int, str] = {}
                    max_col = -1
                    for c_el in row_el:
                        if _local(c_el.tag) != "c":
                            continue
                        ref = c_el.attrib.get("r", "")
                        col_idx = _col_ref_to_index(ref) if ref else (max_col + 1)
                        c_type = c_el.attrib.get("t", "")
                        val = ""
                        if c_type == "inlineStr":
                            val = "".join(
                                t.text for t in c_el.iter() if _local(t.tag) == "t" and t.text
                            )
                        else:
                            v_el = next((x for x in c_el if _local(x.tag) == "v"), None)
                            if v_el is not None and v_el.text is not None:
                                if c_type == "s":
                                    try:
                                        val = shared_strings[int(v_el.text)]
                                    except (ValueError, IndexError):
                                        val = v_el.text
                                else:
                                    val = v_el.text
                        cells_dict[col_idx] = val.strip()
                        max_col = max(max_col, col_idx)
                    if max_col >= 0:
                        width = min(max_col + 1, 40)
                        row_vals = [cells_dict.get(i, "") for i in range(width)]
                        if any(row_vals):
                            rows.append(row_vals)
                sheets.append(
                    {
                        "name": sname,
                        "rows": rows,
                        "total_rows": total_rows,
                        "truncated": total_rows > max_rows,
                    }
                )
    except zipfile.BadZipFile:
        return {
            "kind": "excel",
            "sheets": [],
            "warning": "该文件不是标准 .xlsx（可能是老式 .xls 二进制格式），请下载或用本机 Excel/WPS 打开。",
        }
    return {"kind": "excel", "sheets": sheets}


def parse_csv_preview(path: Path, *, max_rows: int = 400) -> dict[str, Any]:
    """解析 CSV（自动兼容 UTF-8 / UTF-8-BOM / GB18030 中文编码）。"""
    raw_bytes = path.read_bytes()
    text = ""
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if not text:
        text = raw_bytes.decode("utf-8", errors="ignore")

    rows: list[list[str]] = []
    total = 0
    for row in csv.reader(io.StringIO(text)):
        total += 1
        if len(rows) < max_rows:
            rows.append([c.strip() for c in row[:40]])
    return {
        "kind": "excel",
        "sheets": [
            {
                "name": path.stem,
                "rows": rows,
                "total_rows": total,
                "truncated": total > max_rows,
            }
        ],
    }


def parse_pptx_preview(path: Path, data_dir: Path) -> dict[str, Any]:
    """纯标准库解析 .pptx 幻灯片（标题 / 要点 / 表格 / 备注 / 内嵌图片）。"""
    slides: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            slide_files = sorted(
                (n for n in names if re.match(r"^ppt/slides/slide\d+\.xml$", n)),
                key=lambda s: int(re.search(r"slide(\d+)\.xml$", s).group(1)),  # type: ignore[union-attr]
            )
            for idx, sf in enumerate(slide_files[:80], start=1):
                s_root = ET.fromstring(zf.read(sf))
                texts: list[str] = []
                tables: list[list[list[str]]] = []

                for p_el in s_root.iter():
                    if _local(p_el.tag) == "p":
                        line = "".join(
                            t.text for t in p_el.iter() if _local(t.tag) == "t" and t.text
                        ).strip()
                        if line:
                            texts.append(line)
                    elif _local(p_el.tag) == "tbl":
                        tbl_rows: list[list[str]] = []
                        for tr in p_el:
                            if _local(tr.tag) != "tr":
                                continue
                            cells: list[str] = []
                            for tc in tr:
                                if _local(tc.tag) != "tc":
                                    continue
                                txt = "".join(
                                    t.text for t in tc.iter() if _local(t.tag) == "t" and t.text
                                ).strip()
                                cells.append(txt)
                            if any(cells):
                                tbl_rows.append(cells)
                        if tbl_rows:
                            tables.append(tbl_rows)

                # 提取幻灯片关联图片与演讲者备注
                images: list[str] = []
                notes_text = ""
                rel_path = f"ppt/slides/_rels/{Path(sf).name}.rels"
                if rel_path in names:
                    rel_root = ET.fromstring(zf.read(rel_path))
                    for rel in rel_root:
                        tgt = rel.attrib.get("Target", "")
                        if not tgt:
                            continue
                        norm = str(Path("ppt/slides", tgt).as_posix())
                        # 规整 ../media/xxx.png -> ppt/media/xxx.png
                        parts: list[str] = []
                        for part in norm.split("/"):
                            if part == "..":
                                if parts:
                                    parts.pop()
                            elif part and part != ".":
                                parts.append(part)
                        member = "/".join(parts)
                        if member not in names:
                            continue
                        if member.startswith("ppt/media/"):
                            url = _store_embedded_image(
                                data_dir, zf.read(member), Path(member).suffix
                            )
                            if url and url not in images:
                                images.append(url)
                        elif member.startswith("ppt/notesSlides/") and member.endswith(".xml"):
                            n_root = ET.fromstring(zf.read(member))
                            n_lines = [
                                t.text.strip()
                                for t in n_root.iter()
                                if _local(t.tag) == "t" and t.text and t.text.strip()
                            ]
                            notes_text = " ".join(n_lines)

                title = texts[0] if texts else f"第 {idx} 页"
                bullets = texts[1:] if len(texts) > 1 else []
                slides.append(
                    {
                        "index": idx,
                        "title": title,
                        "bullets": bullets[:40],
                        "tables": tables,
                        "images": images[:6],
                        "notes": notes_text[:1000],
                    }
                )
    except zipfile.BadZipFile:
        return {
            "kind": "ppt",
            "slides": [],
            "warning": "该文件不是标准 .pptx（可能是老式 .ppt 二进制格式），请下载或用本机 PowerPoint/WPS 打开。",
        }
    return {"kind": "ppt", "slides": slides}


def _decode_zip_filename(info: zipfile.ZipInfo) -> str:
    """修复 Windows 压缩包里常见的 CP437/GBK 中文文件名乱码。"""
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("gb18030")
    except Exception:
        return info.filename


def parse_zip_preview(path: Path, *, max_entries: int = 300) -> dict[str, Any]:
    """透视 .zip 压缩包内的完整文件目录与大小，无需解压即可查看。"""
    entries: list[dict[str, Any]] = []
    total_size = 0
    total_entries = 0
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
            total_entries = len(infos)
            for info in infos:
                total_size += info.file_size
                if len(entries) < max_entries:
                    entries.append(
                        {
                            "name": _decode_zip_filename(info),
                            "size_bytes": info.file_size,
                            "compressed_bytes": info.compress_size,
                            "is_dir": info.is_dir(),
                        }
                    )
    except zipfile.BadZipFile:
        return {"kind": "archive", "entries": [], "warning": "压缩包损坏或不是标准 ZIP 格式。"}
    return {
        "kind": "archive",
        "entries": entries,
        "total_entries": total_entries,
        "total_size_bytes": total_size,
        "truncated": total_entries > max_entries,
    }


def build_document_preview(
    path: Path,
    *,
    kind: str,
    stream_url: str,
    data_dir: Path,
) -> dict[str, Any]:
    """统一文档预览分发入口。"""
    ext = path.suffix.lower()
    if kind == "pdf" or ext == ".pdf":
        return {"kind": "pdf", "stream_url": stream_url}
    if kind == "word" or ext == ".docx":
        return parse_docx_preview(path, data_dir)
    if kind == "excel" or ext == ".xlsx":
        if ext == ".csv":
            return parse_csv_preview(path)
        return parse_xlsx_preview(path)
    if ext == ".csv":
        return parse_csv_preview(path)
    if kind == "ppt" or ext == ".pptx":
        return parse_pptx_preview(path, data_dir)
    if kind == "archive" or ext == ".zip":
        return parse_zip_preview(path)
    if kind == "markdown" or ext in (".md", ".markdown"):
        raw = path.read_text(encoding="utf-8", errors="ignore")[:80000]
        return {"kind": "markdown", "text": raw, "stream_url": stream_url}
    if kind == "html" or ext in (".html", ".htm"):
        raw = path.read_text(encoding="utf-8", errors="ignore")[:120000]
        return {"kind": "html", "html": raw, "text": raw, "stream_url": stream_url}
    if kind == "code" or ext in _CODE_EXTS:
        raw = path.read_text(encoding="utf-8", errors="ignore")[:80000]
        if ext == ".json":
            with contextlib.suppress(Exception):
                raw = json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
        return {
            "kind": "code",
            "language": ext.lstrip(".") or "text",
            "text": raw,
            "stream_url": stream_url,
        }
    if kind in ("image", "audio", "video"):
        return {"kind": kind, "stream_url": stream_url}
    # 纯文本兜底预览
    try:
        snippet = path.read_text(encoding="utf-8", errors="ignore")[:20000]
    except OSError:
        snippet = ""
    return {"kind": "text", "text": snippet, "stream_url": stream_url}
