"""零额外依赖的 Nesti 知识一键生成引擎（支持 Word .docx / 演示 PPT .pptx / 打印级 PDF & 长图 HTML）。

- 纯 Python 标准库（zipfile + xml.sax.saxutils）生成标准 OOXML Word (.docx) 与 16:9 PowerPoint (.pptx)，
  兼容 Microsoft Office、WPS 与 LibreOffice，无需安装 LibreOffice 或 LaTeX；
- 生成 Nesti Fluent 2.0 杂志级 A4 HTML（供 Electron 原生 printToPDF / capturePage 或浏览器直接出高清 PDF / 长图）。
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape as html_escape
from html.parser import HTMLParser
from xml.sax.saxutils import escape as xml_escape


@dataclass(slots=True)
class ExportItem:
    id: str
    title: str
    content: str
    status: str
    updated_at: str


def _clean_md_line(line: str) -> str:
    txt = re.sub(r"!\[[^\]]*\]\([^)]+\)", "[图片]", line)
    txt = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", txt)
    txt = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", lambda m: m.group(2) or m.group(1), txt)
    txt = re.sub(r"[`*_~]+", "", txt)
    return txt.strip()


def _extract_bullets(content: str, max_points: int = 6) -> list[str]:
    """从 Markdown 正文中提取适合 PPT 幻灯片展示的精炼要点。"""
    points: list[str] = []
    in_code = False
    for raw in content.splitlines():
        s = raw.strip()
        if s.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not s or s.startswith("|") or s.startswith("---"):
            continue
        clean = _clean_md_line(re.sub(r"^[#>\-*\d.\s]+", "", s))
        if len(clean) < 4:
            continue
        if len(clean) > 68:
            clean = clean[:66] + "…"
        points.append(clean)
        if len(points) >= max_points:
            break
    if not points:
        fallback = _clean_md_line(content)
        if fallback:
            points.append(fallback[:120])
    return points


def _safe_filename_stem(name: str) -> str:
    stem = re.sub(r'[\\/:*?"<>|\r\n]+', "_", name.strip())
    return (stem[:48] or "Nesti_知识总结").strip("_ ")


def default_export_filename(title: str, ext: str) -> str:
    ymd = datetime.now(UTC).strftime("%Y%m%d")
    return f"Nesti-{_safe_filename_stem(title)}-{ymd}.{ext.lstrip('.')}"


# =====================================================================
# 1. 标准 OOXML Word (.docx) 生成（纯标准库，完美兼容 Word / WPS）
# =====================================================================

_DOCX_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""

_DOCX_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

_DOCX_DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

_DOCX_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault>
      <w:rPr>
        <w:rFonts w:ascii="Segoe UI" w:hAnsi="Segoe UI" w:eastAsia="Microsoft YaHei"/>
        <w:color w:val="1E2433"/>
        <w:sz w:val="21"/>
      </w:rPr>
    </w:rPrDefault>
  </w:docDefaults>
</w:styles>"""


def _w_p(
    text: str,
    *,
    bold: bool = False,
    size_half_pt: int = 21,
    color: str = "1E2433",
    space_before: int = 60,
    space_after: int = 100,
    shade: str | None = None,
    mono: bool = False,
    indent_left: int = 0,
) -> str:
    shd = f'<w:shd w:val="clear" w:color="auto" w:fill="{shade}"/>' if shade else ""
    ind = f'<w:ind w:left="{indent_left}"/>' if indent_left else ""
    font = (
        '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:eastAsia="Microsoft YaHei"/>'
        if mono
        else '<w:rFonts w:ascii="Segoe UI" w:hAnsi="Segoe UI" w:eastAsia="Microsoft YaHei"/>'
    )
    b = "<w:b/>" if bold else ""
    return (
        "<w:p>"
        f'<w:pPr><w:spacing w:before="{space_before}" w:after="{space_after}"/>{shd}{ind}</w:pPr>'
        f'<w:r><w:rPr>{font}{b}<w:color w:val="{color}"/><w:sz w:val="{size_half_pt}"/></w:rPr>'
        f'<w:t xml:space="preserve">{xml_escape(text)}</w:t></w:r>'
        "</w:p>"
    )


def build_docx_bytes(title: str, subtitle: str, items: list[ExportItem]) -> bytes:
    """将知识条目列表生成为可直接编辑的标准 Word (.docx) 报告。"""
    now_str = datetime.now(UTC).strftime("%Y-%m-%d")
    paras: list[str] = [
        _w_p("NESTI · AI WORKSPACE", bold=True, size_half_pt=18, color="3B74E8", space_before=0, space_after=40),
        _w_p(title, bold=True, size_half_pt=40, color="1E2433", space_before=40, space_after=80),
        _w_p(
            f"{subtitle}  |  共 {len(items)} 条知识  |  导出日期 {now_str}",
            size_half_pt=19,
            color="526077",
            space_before=0,
            space_after=220,
        ),
    ]

    if len(items) > 1:
        paras.append(
            _w_p("目录概览", bold=True, size_half_pt=26, color="3B74E8", space_before=120, space_after=80)
        )
        for idx, it in enumerate(items, start=1):
            paras.append(
                _w_p(
                    f"{idx:02d}. {it.title}",
                    size_half_pt=20,
                    color="1E2433",
                    space_before=20,
                    space_after=40,
                    indent_left=240,
                )
            )

    for idx, it in enumerate(items, start=1):
        heading = f"{idx:02d}  {it.title}" if len(items) > 1 else it.title
        paras.append(
            _w_p(heading, bold=True, size_half_pt=28, color="3B74E8", space_before=240, space_after=100)
        )
        in_code = False
        code_buf: list[str] = []
        for raw_line in it.content.splitlines():
            stripped = raw_line.strip()
            if stripped.startswith("```"):
                if in_code and code_buf:
                    for cl in code_buf[:40]:
                        paras.append(
                            _w_p(cl or " ", size_half_pt=18, color="1E2433", space_before=0, space_after=20, shade="F3F6FC", mono=True, indent_left=240)
                        )
                    code_buf.clear()
                in_code = not in_code
                continue
            if in_code:
                code_buf.append(raw_line)
                continue
            if not stripped:
                continue
            if stripped.startswith("#"):
                clean_h = _clean_md_line(stripped.lstrip("#").strip())
                if clean_h:
                    paras.append(
                        _w_p(clean_h, bold=True, size_half_pt=23, color="1E2433", space_before=140, space_after=60)
                    )
            elif stripped.startswith(("- ", "* ", "• ")):
                clean_b = _clean_md_line(stripped[2:])
                if clean_b:
                    paras.append(
                        _w_p(f"•  {clean_b}", size_half_pt=20, space_before=20, space_after=50, indent_left=260)
                    )
            else:
                clean_p = _clean_md_line(stripped)
                if clean_p:
                    paras.append(_w_p(clean_p, size_half_pt=21, space_before=40, space_after=80))

        if code_buf:
            for cl in code_buf[:40]:
                paras.append(
                    _w_p(cl or " ", size_half_pt=18, color="1E2433", space_before=0, space_after=20, shade="F3F6FC", mono=True, indent_left=240)
                )

    doc_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(paras)
        + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr>'
        "</w:body></w:document>"
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _DOCX_CONTENT_TYPES.encode("utf-8"))
        zf.writestr("_rels/.rels", _DOCX_RELS.encode("utf-8"))
        zf.writestr("word/_rels/document.xml.rels", _DOCX_DOC_RELS.encode("utf-8"))
        zf.writestr("word/styles.xml", _DOCX_STYLES.encode("utf-8"))
        zf.writestr("word/document.xml", doc_xml.encode("utf-8"))
    return buf.getvalue()


# =====================================================================
# 2. 标准 16:9 OOXML PowerPoint (.pptx) 生成（纯标准库，兼容 PPT / WPS）
# =====================================================================

_PPTX_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>"""

_PPTX_THEME = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Nesti">
  <a:themeElements>
    <a:clrScheme name="Nesti">
      <a:dk1><a:srgbClr val="1E2433"/></a:dk1>
      <a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>
      <a:dk2><a:srgbClr val="3B74E8"/></a:dk2>
      <a:lt2><a:srgbClr val="F3F6FC"/></a:lt2>
      <a:accent1><a:srgbClr val="3B74E8"/></a:accent1>
      <a:accent2><a:srgbClr val="7BB8FF"/></a:accent2>
      <a:accent3><a:srgbClr val="0E9F75"/></a:accent3>
      <a:accent4><a:srgbClr val="F59E0B"/></a:accent4>
      <a:accent5><a:srgbClr val="8B5CF6"/></a:accent5>
      <a:accent6><a:srgbClr val="EC4899"/></a:accent6>
      <a:hlink><a:srgbClr val="3B74E8"/></a:hlink>
      <a:folHlink><a:srgbClr val="526077"/></a:folHlink>
    </a:clrScheme>
    <a:fontScheme name="Nesti">
      <a:majorFont><a:latin typeface="Segoe UI"/><a:ea typeface="Microsoft YaHei"/><a:cs typeface=""/></a:majorFont>
      <a:minorFont><a:latin typeface="Segoe UI"/><a:ea typeface="Microsoft YaHei"/><a:cs typeface=""/></a:minorFont>
    </a:fontScheme>
    <a:fmtScheme name="Nesti">
      <a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>
      <a:lnStyleLst><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>
      <a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>
      <a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>
    </a:fmtScheme>
  </a:themeElements>
</a:theme>"""

_PPTX_SLIDE_MASTER = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val="FAFBFD"/></a:solidFill><a:effectLst/></p:bgPr></p:bg><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>
  <p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
  <p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>
</p:sldMaster>"""

_PPTX_SLIDE_MASTER_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>"""

_PPTX_SLIDE_LAYOUT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank">
  <p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>
</p:sldLayout>"""

_PPTX_SLIDE_LAYOUT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>"""

_PPTX_SLIDE_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
</Relationships>"""


def _ppt_rect(shape_id: int, x: int, y: int, cx: int, cy: int, fill_hex: str) -> str:
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{shape_id}" name="Rect{shape_id}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        f'<a:solidFill><a:srgbClr val="{fill_hex}"/></a:solidFill><a:ln><a:noFill/></a:ln></p:spPr></p:sp>'
    )


def _ppt_textbox(
    shape_id: int,
    x: int,
    y: int,
    cx: int,
    cy: int,
    lines: list[tuple[str, int, str, bool]],
) -> str:
    p_xml = []
    for text, sz_hundredths, color_hex, bold in lines:
        b = ' b="1"' if bold else ""
        p_xml.append(
            "<a:p><a:pPr><a:spcAft><a:spcPts val=\"800\"/></a:spcAft></a:pPr>"
            f'<a:r><a:rPr lang="zh-CN" sz="{sz_hundredths}"{b} dirty="0">'
            f'<a:solidFill><a:srgbClr val="{color_hex}"/></a:solidFill>'
            '<a:latin typeface="Segoe UI"/><a:ea typeface="Microsoft YaHei"/>'
            f"</a:rPr><a:t>{xml_escape(text)}</a:t></a:r></a:p>"
        )
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{shape_id}" name="Text{shape_id}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>'
        f'<p:txBody><a:bodyPr wrap="square"/><a:lstStyle/>{"".join(p_xml)}</p:txBody></p:sp>'
    )


def _wrap_slide(shapes_xml: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        "<p:cSld><p:spTree>"
        '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        "<p:grpSpPr/>"
        f"{shapes_xml}"
        "</p:spTree></p:cSld></p:sld>"
    )


def build_pptx_bytes(title: str, subtitle: str, items: list[ExportItem]) -> bytes:
    """将知识条目列表生成为 Nesti 16:9 演示文稿 (.pptx)。"""
    # 16:9 widescreen: 12192000 x 6858000 EMU (13.333" x 7.5")
    now_str = datetime.now(UTC).strftime("%Y-%m-%d")
    slides: list[str] = []

    # Slide 1: Cover
    cover_shapes = (
        _ppt_rect(2, 0, 0, 12192000, 160000, "3B74E8")
        + _ppt_rect(3, 8200000, 0, 3992000, 6858000, "EDF3FC")
        + _ppt_textbox(
            4,
            900000,
            1650000,
            7000000,
            3600000,
            [
                ("NESTI · AI WORKSPACE", 1400, "3B74E8", True),
                (title[:42], 3600, "1E2433", True),
                (f"{subtitle}  ·  共 {len(items)} 项核心知识", 1600, "526077", False),
                (f"生成日期：{now_str}", 1200, "8695AB", False),
            ],
        )
    )
    slides.append(_wrap_slide(cover_shapes))

    # Slide 2: Agenda (if > 1 item)
    if len(items) > 1:
        toc_lines: list[tuple[str, int, str, bool]] = [
            ("CONTENTS · 目录概览", 1200, "3B74E8", True),
            ("本汇报涵盖的核心主题", 2400, "1E2433", True),
        ]
        for idx, it in enumerate(items[:10], start=1):
            toc_lines.append((f"{idx:02d}   {it.title[:48]}", 1500, "1E2433", False))
        if len(items) > 10:
            toc_lines.append((f"……以及其余 {len(items) - 10} 项专题内容", 1300, "8695AB", False))
        slides.append(
            _wrap_slide(
                _ppt_rect(2, 0, 0, 12192000, 90000, "3B74E8")
                + _ppt_textbox(3, 850000, 700000, 10400000, 5600000, toc_lines)
            )
        )

    # Content Slides (cap at 24 slides for crisp presentation decks)
    for idx, it in enumerate(items[:24], start=1):
        bullets = _extract_bullets(it.content, max_points=6)
        lines: list[tuple[str, int, str, bool]] = [
            (f"{idx:02d} / {min(len(items), 24):02d}   ·   NESTI KNOWLEDGE BRIEF", 1100, "3B74E8", True),
            (it.title[:46], 2400, "1E2433", True),
        ]
        for pt in bullets:
            lines.append((f"▪  {pt}", 1500, "334155", False))
        slide_xml = _wrap_slide(
            _ppt_rect(2, 0, 0, 12192000, 80000, "3B74E8")
            + _ppt_rect(3, 750000, 1520000, 10692000, 18000, "DCE8FB")
            + _ppt_textbox(4, 750000, 520000, 10692000, 5700000, lines)
        )
        slides.append(slide_xml)

    # Closing Slide
    slides.append(
        _wrap_slide(
            _ppt_rect(2, 0, 0, 12192000, 120000, "3B74E8")
            + _ppt_textbox(
                3,
                1200000,
                2500000,
                9800000,
                2000000,
                [
                    ("THANK YOU", 3200, "3B74E8", True),
                    ("由 Nesti · AI 工作空间（ExplainLab V3）一键生成", 1600, "526077", False),
                ],
            )
        )
    )

    sld_id_lst = "".join(
        f'<p:sldId id="{256 + i}" r:id="rId{i + 2}"/>' for i in range(len(slides))
    )
    pres_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
        f"<p:sldIdLst>{sld_id_lst}</p:sldIdLst>"
        '<p:sldSz cx="12192000" cy="6858000"/>'
        '<p:notesSz cx="6858000" cy="9144000"/>'
        "</p:presentation>"
    )
    pres_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>'
        + "".join(
            f'<Relationship Id="rId{i + 2}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{i + 1}.xml"/>'
            for i in range(len(slides))
        )
        + "</Relationships>"
    )
    ct_overrides = "".join(
        f'<Override PartName="/ppt/slides/slide{i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        for i in range(len(slides))
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
        '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
        '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
        '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
        f"{ct_overrides}</Types>"
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types.encode("utf-8"))
        zf.writestr("_rels/.rels", _PPTX_RELS.encode("utf-8"))
        zf.writestr("ppt/presentation.xml", pres_xml.encode("utf-8"))
        zf.writestr("ppt/_rels/presentation.xml.rels", pres_rels.encode("utf-8"))
        zf.writestr("ppt/theme/theme1.xml", _PPTX_THEME.encode("utf-8"))
        zf.writestr("ppt/slideMasters/slideMaster1.xml", _PPTX_SLIDE_MASTER.encode("utf-8"))
        zf.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", _PPTX_SLIDE_MASTER_RELS.encode("utf-8"))
        zf.writestr("ppt/slideLayouts/slideLayout1.xml", _PPTX_SLIDE_LAYOUT.encode("utf-8"))
        zf.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", _PPTX_SLIDE_LAYOUT_RELS.encode("utf-8"))
        for i, sxml in enumerate(slides, start=1):
            zf.writestr(f"ppt/slides/slide{i}.xml", sxml.encode("utf-8"))
            zf.writestr(f"ppt/slides/_rels/slide{i}.xml.rels", _PPTX_SLIDE_RELS.encode("utf-8"))
    return buf.getvalue()


# =====================================================================
# 3. 杂志级 Nesti Editorial HTML 生成（供原生 printToPDF & 长图 PNG）
# =====================================================================

def _md_to_clean_html(content: str, api_origin: str = "http://127.0.0.1:8000") -> str:
    blocks: list[str] = []
    in_code = False
    code_lines: list[str] = []
    list_buf: list[str] = []

    def flush_list() -> None:
        if list_buf:
            blocks.append("<ul>" + "".join(f"<li>{x}</li>" for x in list_buf) + "</ul>")
            list_buf.clear()

    def inline_fmt(s: str) -> str:
        # 保留图片（将相对 /api/... 转为绝对本地地址供离屏窗口加载）
        img_m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", s.strip())
        if img_m:
            alt, url = img_m.group(1), img_m.group(2).strip()
            if url.startswith("/api/"):
                url = api_origin.rstrip("/") + url
            return f'<figure><img src="{html_escape(url)}" alt="{html_escape(alt)}"/></figure>'
        esc = html_escape(s)
        esc = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", esc)
        esc = re.sub(r"`([^`]+)`", r"<code>\1</code>", esc)
        esc = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", lambda m: f'<span class="wiki">{m.group(2) or m.group(1)}</span>', esc)
        return esc

    for raw in content.splitlines():
        s = raw.strip()
        if s.startswith("```"):
            flush_list()
            if in_code:
                blocks.append(f"<pre><code>{html_escape(chr(10).join(code_lines))}</code></pre>")
                code_lines.clear()
            in_code = not in_code
            continue
        if in_code:
            code_lines.append(raw)
            continue
        if not s:
            flush_list()
            continue
        if s.startswith("### "):
            flush_list()
            blocks.append(f"<h4>{inline_fmt(s[4:])}</h4>")
        elif s.startswith("## "):
            flush_list()
            blocks.append(f"<h3>{inline_fmt(s[3:])}</h3>")
        elif s.startswith("# "):
            flush_list()
            blocks.append(f"<h3>{inline_fmt(s[2:])}</h3>")
        elif s.startswith(("- ", "* ")):
            list_buf.append(inline_fmt(s[2:]))
        else:
            flush_list()
            blocks.append(f"<p>{inline_fmt(s)}</p>")

    flush_list()
    if code_lines:
        blocks.append(f"<pre><code>{html_escape(chr(10).join(code_lines))}</code></pre>")
    return "\n".join(blocks)


def build_report_html(
    title: str,
    subtitle: str,
    items: list[ExportItem],
    *,
    mode: str = "pdf",
    api_origin: str = "http://127.0.0.1:8000",
) -> str:
    """生成 Nesti Fluent 2.0 杂志级 HTML（mode='pdf' 适配 A4 打印分页；mode='card' 适配高清分享长图）。"""
    now_str = datetime.now(UTC).strftime("%Y-%m-%d")
    is_card = mode == "card"
    max_w = "780px" if is_card else "820px"

    toc_html = ""
    if not is_card and len(items) > 1:
        toc_items = "".join(
            f'<li><span class="idx">{i:02d}</span><span>{html_escape(it.title)}</span></li>'
            for i, it in enumerate(items, start=1)
        )
        toc_html = f'<section class="toc"><div class="eyebrow">00 · 目录概览</div><ol>{toc_items}</ol></section>'

    cards_html = []
    for i, it in enumerate(items, start=1):
        body = _md_to_clean_html(it.content, api_origin=api_origin)
        idx_tag = f'<div class="eyebrow">{i:02d} / {len(items):02d}</div>' if len(items) > 1 else ""
        cards_html.append(
            f'<article class="entry">{idx_tag}<h2>{html_escape(it.title)}</h2><div class="body">{body}</div></article>'
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>{html_escape(title)}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: {"28px" if is_card else "24px 30px"};
      background: {"#EDF3FC" if is_card else "#FFFFFF"};
      color: #1E2433;
      font-family: "Segoe UI Variable", "Segoe UI", "Microsoft YaHei", sans-serif;
      line-height: 1.7;
      font-size: 13.5px;
    }}
    .sheet {{
      max-width: {max_w};
      margin: 0 auto;
      background: #FFFFFF;
      {"border-radius: 20px; border: 1px solid rgba(30,36,51,0.08); box-shadow: 0 18px 40px -16px rgba(30,36,51,0.16); padding: 34px 38px;" if is_card else ""}
    }}
    .hero {{
      border-bottom: 2px solid #3B74E8;
      padding-bottom: 18px;
      margin-bottom: 24px;
    }}
    .eyebrow {{
      font-family: Consolas, monospace;
      font-size: 10.5px;
      font-weight: 600;
      letter-spacing: 0.16em;
      color: #3B74E8;
      text-transform: uppercase;
      margin-bottom: 6px;
    }}
    h1 {{ margin: 0 0 8px; font-size: 26px; line-height: 1.28; color: #1E2433; }}
    .meta {{ font-size: 12px; color: #526077; }}
    .toc {{
      background: #FAFBFD;
      border: 1px solid rgba(30,36,51,0.08);
      border-radius: 12px;
      padding: 16px 20px;
      margin-bottom: 26px;
    }}
    .toc ol {{ list-style: none; padding: 0; margin: 8px 0 0; columns: 2; column-gap: 24px; }}
    .toc li {{ font-size: 12.5px; padding: 3px 0; break-inside: avoid; display: flex; gap: 8px; }}
    .toc .idx {{ font-family: Consolas, monospace; color: #3B74E8; font-weight: 600; }}
    .entry {{
      padding: 18px 0;
      border-bottom: 1px solid rgba(30,36,51,0.08);
      page-break-inside: avoid;
    }}
    .entry:last-child {{ border-bottom: none; }}
    h2 {{ margin: 0 0 10px; font-size: 17px; color: #1E2433; }}
    h3, h4 {{ margin: 12px 0 6px; font-size: 14px; color: #2B3B55; }}
    p {{ margin: 6px 0; }}
    ul {{ margin: 6px 0 10px 20px; padding: 0; }}
    li {{ margin: 3px 0; }}
    code {{
      font-family: Consolas, monospace;
      background: #F3F6FC;
      padding: 1px 5px;
      border-radius: 4px;
      font-size: 12px;
    }}
    pre {{
      background: #F3F6FC;
      border: 1px solid rgba(59,116,232,0.14);
      border-radius: 8px;
      padding: 10px 14px;
      overflow-x: auto;
      font-size: 11.5px;
      line-height: 1.5;
    }}
    pre code {{ background: transparent; padding: 0; }}
    .wiki {{
      color: #3B74E8;
      background: rgba(59,116,232,0.09);
      padding: 1px 6px;
      border-radius: 4px;
      font-weight: 500;
    }}
    figure {{ margin: 12px 0; }}
    img {{ max-width: 100%; border-radius: 10px; border: 1px solid rgba(30,36,51,0.08); }}
    footer {{
      margin-top: 24px;
      padding-top: 12px;
      border-top: 1px solid rgba(30,36,51,0.08);
      display: flex;
      justify-content: space-between;
      font-size: 11px;
      color: #8695AB;
    }}
    @media print {{
      body {{ padding: 0; background: #FFFFFF; }}
      .sheet {{ max-width: 100%; border: none; box-shadow: none; padding: 0; }}
    }}
  </style>
</head>
<body>
  <div class="sheet">
    <header class="hero">
      <div class="eyebrow">NESTI · AI WORKSPACE · KNOWLEDGE REPORT</div>
      <h1>{html_escape(title)}</h1>
      <div class="meta">{html_escape(subtitle)} · 共 {len(items)} 条知识 · 生成于 {now_str}</div>
    </header>
    {toc_html}
    {"".join(cards_html)}
    <footer>
      <span>Nesti · AI 工作空间（ExplainLab V3）</span>
      <span>本地隐私生成 · {now_str}</span>
    </footer>
  </div>
</body>
</html>"""


class _ArticleHTMLParser(HTMLParser):
    """轻量零依赖 HTML 正文提取器：过滤脚本/导航/页脚，转为干净 Markdown。"""

    _SKIP_TAGS = frozenset(
        {"script", "style", "noscript", "svg", "nav", "footer", "aside", "iframe", "form", "button"}
    )
    _HEADING_PREFIX = {"h1": "# ", "h2": "## ", "h3": "### ", "h4": "#### "}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = False
        self._in_pre = False
        self._current_block: list[str] = []
        self._block_prefix = ""
        self.page_title = ""
        self.blocks: list[str] = []

    def _flush(self) -> None:
        text = "".join(self._current_block)
        self._current_block.clear()
        if self._in_pre:
            cleaned = text.strip("\r\n")
            if cleaned:
                self.blocks.append(f"```\n{cleaned[:2400]}\n```")
            return
        cleaned = re.sub(r"\s+", " ", text).strip()
        if len(cleaned) >= 2:
            self.blocks.append(f"{self._block_prefix}{cleaned}")
        self._block_prefix = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth > 0:
            return
        if t == "title":
            self._in_title = True
            return
        if t == "pre":
            self._flush()
            self._in_pre = True
            return
        if t in self._HEADING_PREFIX:
            self._flush()
            self._block_prefix = self._HEADING_PREFIX[t]
        elif t == "li":
            self._flush()
            self._block_prefix = "- "
        elif t == "blockquote":
            self._flush()
            self._block_prefix = "> "
        elif t in ("p", "div", "article", "section", "tr", "br"):
            if t == "br":
                self._current_block.append(" ")
            else:
                self._flush()

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in self._SKIP_TAGS:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return
        if self._skip_depth > 0:
            return
        if t == "title":
            self._in_title = False
            return
        if t == "pre":
            self._flush()
            self._in_pre = False
            return
        if t in ("h1", "h2", "h3", "h4", "p", "li", "blockquote", "tr"):
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if self._in_title:
            self.page_title += data
            return
        self._current_block.append(data)


def extract_article_from_html(html_text: str, url: str) -> tuple[str, str]:
    """从网页 HTML 提取 (标题, Markdown 正文)。"""
    parser = _ArticleHTMLParser()
    parser.feed(html_text or "")
    parser.close()
    parser._flush()

    title = re.sub(r"\s+", " ", parser.page_title).strip()
    if not title:
        for blk in parser.blocks:
            if blk.startswith("# "):
                title = blk[2:].strip()
                break
    if not title:
        title = url.split("://", 1)[-1][:60]
    title = title[:120]

    # 去重连续重复段落，控制单篇最大 16000 字符
    deduped: list[str] = []
    seen: set[str] = set()
    for blk in parser.blocks:
        key = blk.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(key)

    header = f"> 网页剪藏来源：{url}\n\n"
    body = "\n\n".join(deduped)
    if len(body) > 15500:
        body = body[:15500].rstrip() + "\n\n…（已自动截断超长网页正文）"
    if not body.strip():
        body = "（该网页主要为动态脚本渲染内容，未能直接提取静态正文，可复制关键片段补充。）"
    return title, header + body
