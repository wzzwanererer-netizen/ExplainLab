"""多模态媒体附件（含 HTTP Range 解析）与乱文件夹哨兵单元测试。"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.services.doc_preview import (
    build_document_preview,
    parse_csv_preview,
    parse_docx_preview,
    parse_pptx_preview,
    parse_xlsx_preview,
    parse_zip_preview,
)
from app.services.folder_watcher import (
    add_watched_folder,
    delete_watched_folder,
    extract_file_text,
    list_watched_folders,
    scan_watched_folder,
)
from app.services.media import (
    delete_media,
    get_media_file,
    list_all_media,
    list_media,
    parse_byte_range,
    save_media_bytes,
)


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_media_save_list_range_delete_lifecycle(tmp_path: Path) -> None:
    item_id = "item-media-01"
    data = b"0123456789abcdef" * 10
    rec = save_media_bytes(
        tmp_path,
        item_id,
        filename="demo-clip.mp4",
        content=data,
        mime="video/mp4",
    )
    assert rec.kind == "video"
    assert rec.size_bytes == len(data)

    listed = list_media(tmp_path, item_id)
    assert len(listed) == 1
    assert listed[0].id == rec.id

    found = get_media_file(tmp_path, item_id, rec.id)
    assert found is not None
    assert found[1].read_bytes() == data

    # HTTP Range 解析验证（支持音视频拖动进度条）
    assert parse_byte_range("bytes=0-15", len(data)) == (0, 15)
    assert parse_byte_range("bytes=100-", len(data)) == (100, len(data) - 1)
    assert parse_byte_range("bytes=-16", len(data)) == (len(data) - 16, len(data) - 1)
    assert parse_byte_range("bytes=9999-10000", len(data)) is None

    assert delete_media(tmp_path, item_id, rec.id) is True
    assert list_media(tmp_path, item_id) == []


def test_extract_docx_text_pure_stdlib(tmp_path: Path) -> None:
    docx_path = tmp_path / "notes.docx"
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>华为云校园网安全设计要点</w:t></w:r></w:p></w:body>"
        "</w:document>"
    )
    with zipfile.ZipFile(docx_path, "w") as zf:
        zf.writestr("word/document.xml", xml)

    assert "华为云校园网安全设计要点" in extract_file_text(docx_path)


@pytest.mark.asyncio
async def test_folder_watcher_scans_multimodal_and_deduplicates(tmp_path: Path) -> None:
    db = _make_session()
    messy_dir = tmp_path / "messy_desktop"
    messy_dir.mkdir()
    (messy_dir / "架构备忘.md").write_text("# 本地外脑\n- 严格只读监听\n", encoding="utf-8")
    (messy_dir / "voice_memo.mp3").write_bytes(b"ID3" + b"\x00" * 512)
    (messy_dir / "sketch.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 2048)

    data_dir = tmp_path / "data"
    folder = add_watched_folder(db, data_dir, path=str(messy_dir), use_ai_summary=False)
    assert folder.file_count == 3
    assert folder.space_name == "文件夹 · messy_desktop"

    report1 = await scan_watched_folder(db, None, data_dir=data_dir, folder_id=folder.id)
    assert report1.scanned_files == 3
    assert len(report1.created_items) == 3
    kinds = {it.kind for it in report1.created_items}
    assert kinds == {"document", "audio", "image"}

    # 音频条目应已自动挂载到多模态媒体面板
    audio_item = next(it for it in report1.created_items if it.kind == "audio")
    attached = list_media(data_dir, audio_item.id)
    assert len(attached) == 1
    assert attached[0].kind == "audio"

    # 第二次扫描：游标命中，0 重复扫描
    report2 = await scan_watched_folder(db, None, data_dir=data_dir, folder_id=folder.id)
    assert report2.scanned_files == 0
    assert len(report2.created_items) == 0

    # 新文件放入后立刻被增量发现
    (messy_dir / "new_idea.txt").write_text("新来的灵感笔记", encoding="utf-8")
    report3 = await scan_watched_folder(db, None, data_dir=data_dir, folder_id=folder.id)
    assert report3.scanned_files == 1
    assert len(report3.created_items) == 1
    assert report3.created_items[0].title == "new_idea"

    assert len(list_watched_folders(data_dir)) == 1
    assert delete_watched_folder(data_dir, folder.id) is True
    db.close()


def test_doc_preview_docx_xlsx_csv_pptx_and_library(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"

    # 1) DOCX (标题 + 表格)
    docx_p = tmp_path / "report.docx"
    docx_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>项目总览</w:t></w:r></w:p>'
        "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>模块</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>状态</w:t></w:r></w:p></w:tc></w:tr>"
        "<w:tr><w:tc><w:p><w:r><w:t>阅读器</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>已完成</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
        "</w:body></w:document>"
    )
    with zipfile.ZipFile(docx_p, "w") as zf:
        zf.writestr("word/document.xml", docx_xml)
    docx_res = parse_docx_preview(docx_p, data_dir)
    assert docx_res["kind"] == "word"
    assert docx_res["blocks"][0]["type"] == "heading"
    assert docx_res["blocks"][1]["type"] == "table"
    assert docx_res["blocks"][1]["rows"][1] == ["阅读器", "已完成"]

    # 2) XLSX
    xlsx_p = tmp_path / "budget.xlsx"
    with zipfile.ZipFile(xlsx_p, "w") as zf:
        zf.writestr(
            "xl/sharedStrings.xml",
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<si><t>项目</t></si><si><t>预算</t></si><si><t>ExplainLab</t></si></sst>",
        )
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<sheetData>"
            '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
            '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2"><v>0</v></c></row>'
            "</sheetData></worksheet>",
        )
    xlsx_res = parse_xlsx_preview(xlsx_p)
    assert xlsx_res["kind"] == "excel"
    assert xlsx_res["sheets"][0]["rows"][0] == ["项目", "预算"]
    assert xlsx_res["sheets"][0]["rows"][1] == ["ExplainLab", "0"]

    # 3) CSV (GB18030 中文兼容)
    csv_p = tmp_path / "scores.csv"
    csv_p.write_bytes("姓名,分数\n菲比,100\n".encode("gb18030"))
    csv_res = parse_csv_preview(csv_p)
    assert csv_res["sheets"][0]["rows"][1] == ["菲比", "100"]

    # 4) PPTX
    pptx_p = tmp_path / "deck.pptx"
    with zipfile.ZipFile(pptx_p, "w") as zf:
        zf.writestr(
            "ppt/slides/slide1.xml",
            '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            "<p:cSld><p:spTree><p:sp><p:txBody>"
            "<a:p><a:r><a:t>ExplainLab V3 汇报</a:t></a:r></a:p>"
            "<a:p><a:r><a:t>内置全格式阅读器</a:t></a:r></a:p>"
            "</p:txBody></p:sp></p:spTree></p:cSld></p:sld>",
        )
    pptx_res = parse_pptx_preview(pptx_p, data_dir)
    assert pptx_res["kind"] == "ppt"
    assert pptx_res["slides"][0]["title"] == "ExplainLab V3 汇报"
    assert "内置全格式阅读器" in pptx_res["slides"][0]["bullets"]

    # 5) 独立文件库聚合
    save_media_bytes(data_dir, "k-1", filename="report.docx", content=docx_p.read_bytes())
    save_media_bytes(data_dir, "k-2", filename="deck.pptx", content=pptx_p.read_bytes())
    all_files = list_all_media(data_dir)
    assert {f.kind for f in all_files} == {"word", "ppt"}
    assert len(list_all_media(data_dir, kind="ppt")) == 1

    # 6) ZIP 透视 + MD/HTML/JSON 富预览
    zip_p = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zip_p, "w") as zf:
        zf.writestr("docs/说明.md", "# 标题")
        zf.writestr("src/app.py", "print('hi')")
    zres = parse_zip_preview(zip_p)
    assert zres["kind"] == "archive"
    assert zres["total_entries"] == 2

    md_p = tmp_path / "note.md"
    md_p.write_text("# 测试\n- 要点", encoding="utf-8")
    assert build_document_preview(md_p, kind="markdown", stream_url="/x", data_dir=data_dir)["kind"] == "markdown"

    html_p = tmp_path / "page.html"
    html_p.write_text("<h1>Hello</h1>", encoding="utf-8")
    assert build_document_preview(html_p, kind="html", stream_url="/x", data_dir=data_dir)["kind"] == "html"

    json_p = tmp_path / "cfg.json"
    json_p.write_text('{"a":1,"b":"中"}', encoding="utf-8")
    jres = build_document_preview(json_p, kind="code", stream_url="/x", data_dir=data_dir)
    assert jres["kind"] == "code" and jres["language"] == "json" and '"b": "中"' in jres["text"]
