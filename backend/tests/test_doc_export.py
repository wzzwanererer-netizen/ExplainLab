"""一键生成办公成品（Word .docx / PPT .pptx / 打印级 PDF & 长图 HTML）单元测试。"""

from __future__ import annotations

import io
import zipfile

from app.services.doc_export import (
    ExportItem,
    build_docx_bytes,
    build_pptx_bytes,
    build_report_html,
    extract_article_from_html,
)


def _sample_items() -> list[ExportItem]:
    return [
        ExportItem(
            id="k1",
            title="Nesti 长期记忆架构",
            content="## 核心设计\n- 本地 SQLite FTS5 + 语义向量混合检索\n- 支持 [[跨 Agent 无缝接力]]\n```python\nprint('ok')\n```",
            status="active",
            updated_at="2026-11-28T00:00:00Z",
        ),
        ExportItem(
            id="k2",
            title="跨 Agent 无缝接力",
            content="通过只读 MCP 工具列表与读取本地会话，零污染知识库。",
            status="draft",
            updated_at="2026-11-28T00:00:00Z",
        ),
    ]


def test_build_docx_and_pptx_produce_valid_ooxml_packages() -> None:
    items = _sample_items()
    docx_raw = build_docx_bytes("Nesti 专题总结", "知识空间：个人总知识库", items)
    with zipfile.ZipFile(io.BytesIO(docx_raw), "r") as zf:
        names = set(zf.namelist())
        assert "[Content_Types].xml" in names
        assert "word/document.xml" in names
        xml_text = zf.read("word/document.xml").decode("utf-8")
        assert "Nesti 长期记忆架构" in xml_text
        assert "跨 Agent 无缝接力" in xml_text

    pptx_raw = build_pptx_bytes("Nesti 汇报演示", "知识空间：个人总知识库", items)
    with zipfile.ZipFile(io.BytesIO(pptx_raw), "r") as zf:
        names = set(zf.namelist())
        assert "ppt/presentation.xml" in names
        assert "ppt/slides/slide1.xml" in names
        assert "ppt/slides/slide3.xml" in names
        slide3 = zf.read("ppt/slides/slide3.xml").decode("utf-8")
        assert "Nesti 长期记忆架构" in slide3


def test_build_report_html_supports_pdf_and_card_modes() -> None:
    items = _sample_items()
    pdf_html = build_report_html("专题总结", "个人总知识库", items, mode="pdf")
    assert "NESTI · AI WORKSPACE" in pdf_html
    assert "目录概览" in pdf_html
    assert "Nesti 长期记忆架构" in pdf_html

    card_html = build_report_html("单篇卡片", "个人总知识库", [items[0]], mode="card")
    assert "#EDF3FC" in card_html
    assert "Nesti 长期记忆架构" in card_html


def test_extract_article_from_html_strips_scripts_and_formats_markdown() -> None:
    sample_html = """
    <html>
      <head>
        <title>深入理解 Hybrid Retrieval - 技术博客</title>
        <style>.nav { display: none; }</style>
        <script>console.log("ignore me");</script>
      </head>
      <body>
        <nav>首页 | 关于</nav>
        <article>
          <h1>Hybrid Retrieval 实战</h1>
          <p>结合 FTS5 关键词召回与语义向量召回，可以显著提升中文命中率。</p>
          <h2>关键步骤</h2>
          <ul>
            <li>建立 trigram 全文索引</li>
            <li>使用 RRF 融合排序</li>
          </ul>
          <pre>score = 1 / (60 + rank)</pre>
        </article>
        <footer>Copyright 2026</footer>
      </body>
    </html>
    """
    title, md = extract_article_from_html(sample_html, "https://example.com/hybrid")
    assert title == "深入理解 Hybrid Retrieval - 技术博客"
    assert "网页剪藏来源：https://example.com/hybrid" in md
    assert "结合 FTS5 关键词召回" in md
    assert "## 关键步骤" in md
    assert "- 建立 trigram 全文索引" in md
    assert "score = 1 / (60 + rank)" in md
    assert "ignore me" not in md
    assert "Copyright 2026" not in md
