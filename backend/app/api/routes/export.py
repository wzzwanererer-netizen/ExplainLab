"""一键生成总结报告路由（Word .docx / 汇报 PPT .pptx / 打印级 PDF & 知识长图 HTML）。"""

from __future__ import annotations

import ipaddress
import json
import re
from typing import Annotated, Literal
from urllib.parse import quote, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.links import sync_links_or_conflict
from app.api.schemas import KnowledgeOut
from app.db.session import get_session
from app.dependencies import get_embedder, get_model_adapter
from app.models import KnowledgeItemORM, KnowledgeSpace
from app.services import doc_export
from app.services.knowledge import SQLAlchemyKnowledgeRepository
from app.services.retrieval import sync_index
from knowledge_core.domain.entities import KnowledgeItem, SourceRef, SourceType
from knowledge_core.model_adapter import ModelAdapter, ModelAdapterError, ModelMessage, ModelRequest
from knowledge_core.ports import Embedder

router = APIRouter(prefix="/export", tags=["export"])


class ExportRequestIn(BaseModel):
    space_id: str | None = Field(default=None, max_length=64)
    item_id: str | None = Field(default=None, max_length=64)
    title: str | None = Field(default=None, max_length=120)
    mode: Literal["pdf", "card"] = "pdf"


class ExportHtmlOut(BaseModel):
    filename: str
    html: str
    item_count: int


def _resolve_export_bundle(
    session: Session,
    payload: ExportRequestIn,
) -> tuple[str, str, list[doc_export.ExportItem]]:
    if payload.item_id:
        row = session.get(KnowledgeItemORM, payload.item_id)
        if row is None:
            raise HTTPException(status_code=404, detail="知识条目不存在")
        space_name = "个人总知识库"
        if row.space_id:
            sp = session.get(KnowledgeSpace, row.space_id)
            if sp:
                space_name = sp.name
        item = doc_export.ExportItem(
            id=row.id,
            title=row.title,
            content=row.content,
            status=row.status,
            updated_at=row.updated_at.isoformat() if row.updated_at else "",
        )
        return (payload.title or row.title), f"所属空间：{space_name}", [item]

    stmt = select(KnowledgeItemORM).where(KnowledgeItemORM.status != "archived")
    space_label = "全库知识总结"
    if payload.space_id:
        sp = session.get(KnowledgeSpace, payload.space_id)
        if sp is None:
            raise HTTPException(status_code=404, detail="知识空间不存在")
        space_label = sp.name
        if sp.kind == "personal":
            stmt = stmt.where(
                (KnowledgeItemORM.space_id == sp.id) | (KnowledgeItemORM.space_id.is_(None))
            )
        else:
            stmt = stmt.where(KnowledgeItemORM.space_id == sp.id)

    rows = list(session.scalars(stmt.order_by(KnowledgeItemORM.updated_at.desc()).limit(60)).all())
    if not rows:
        raise HTTPException(status_code=400, detail="当前空间暂无可导出的知识条目")

    items = [
        doc_export.ExportItem(
            id=r.id,
            title=r.title,
            content=r.content,
            status=r.status,
            updated_at=r.updated_at.isoformat() if r.updated_at else "",
        )
        for r in rows
    ]
    return (payload.title or f"{space_label} · 知识总结报告"), f"知识空间：{space_label}", items


@router.post("/docx")
def export_docx_route(
    payload: ExportRequestIn,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    title, subtitle, items = _resolve_export_bundle(session, payload)
    raw = doc_export.build_docx_bytes(title, subtitle, items)
    fname = doc_export.default_export_filename(title, "docx")
    return Response(
        content=raw,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"},
    )


@router.post("/pptx")
def export_pptx_route(
    payload: ExportRequestIn,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    title, subtitle, items = _resolve_export_bundle(session, payload)
    raw = doc_export.build_pptx_bytes(title, subtitle, items)
    fname = doc_export.default_export_filename(title, "pptx")
    return Response(
        content=raw,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"},
    )


@router.post("/html", response_model=ExportHtmlOut)
def export_html_route(
    payload: ExportRequestIn,
    session: Annotated[Session, Depends(get_session)],
) -> ExportHtmlOut:
    title, subtitle, items = _resolve_export_bundle(session, payload)
    ext = "png" if payload.mode == "card" else "pdf"
    fname = doc_export.default_export_filename(title, ext)
    html = doc_export.build_report_html(title, subtitle, items, mode=payload.mode)
    return ExportHtmlOut(filename=fname, html=html, item_count=len(items))


class ClipUrlIn(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    space_id: str | None = Field(default=None, max_length=64)


def _validate_public_http_url(raw: str) -> str:
    url = raw.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=400, detail="请输入有效的 http:// 或 https:// 网页链接")
    host = (parsed.hostname or "").strip().lower()
    if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or host.endswith(".local"):
        raise HTTPException(status_code=400, detail="不支持剪藏本机地址，请输入公开网页链接")
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise HTTPException(status_code=400, detail="不支持剪藏内网地址，请输入公开网页链接")
    except ValueError:
        pass
    return url


@router.post("/clip-url", response_model=KnowledgeOut, status_code=201)
async def clip_url_route(
    payload: ClipUrlIn,
    session: Annotated[Session, Depends(get_session)],
    embedder: Annotated[Embedder | None, Depends(get_embedder)],
) -> KnowledgeOut:
    url = _validate_public_http_url(payload.url)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers=headers,
        ) as client:
            resp = await client.get(url)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="网页抓取超时，请稍后重试") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"网页抓取失败：{type(exc).__name__}") from exc

    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"目标网页返回错误状态码：{resp.status_code}")

    final_url = str(resp.url)
    ctype = (resp.headers.get("content-type") or "").lower()
    if "text/plain" in ctype or "text/markdown" in ctype:
        text = resp.text.strip()
        first_line = next((ln.lstrip("# ").strip() for ln in text.splitlines() if ln.strip()), "")
        title = (first_line or final_url.split("://", 1)[-1])[:120]
        content = f"> 网页剪藏来源：{final_url}\n\n{text[:15500]}"
    else:
        title, content = doc_export.extract_article_from_html(resp.text, final_url)

    item = KnowledgeItem(
        title=title,
        content=content,
        space_id=payload.space_id,
        source_refs=[
            SourceRef(
                source_type=SourceType.DOCUMENT,
                uri=final_url,
                excerpt="网址一键剪藏",
            )
        ],
    )
    saved = SQLAlchemyKnowledgeRepository(session).save(item)
    sync_links_or_conflict(session, saved)
    session.commit()
    await sync_index(session, embedder, index_ids=[saved.id])
    session.commit()
    return KnowledgeOut.model_validate(saved)


class GenerateStyleIn(BaseModel):
    prompt: str = Field(min_length=2, max_length=300)


class GenerateStyleOut(BaseModel):
    name: str
    englishName: str
    description: str
    mode: Literal["light", "dark"]
    canvasBg: str
    cardBg: str
    accent: str
    secondary: str
    fontMood: Literal["sans", "serif", "mono"]
    texture: Literal["none", "grid", "dots", "aurora"]
    cornerStyle: Literal["sharp", "balanced", "soft"]


_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _safe_hex(val: object, fallback: str) -> str:
    s = str(val or "").strip()
    return s.lower() if _HEX_RE.match(s) else fallback


@router.post("/generate-style", response_model=GenerateStyleOut)
async def generate_style_plugin_route(
    payload: GenerateStyleIn,
    adapter: Annotated[ModelAdapter, Depends(get_model_adapter)],
) -> GenerateStyleOut:
    """AI 一句话生成 UI 风格插件草稿（严格 JSON 输出，由前端编译安装为完整风格插件）。"""
    system_prompt = (
        "你是顶级桌面软件 UI 视觉设计师。请根据用户的一句话风格描述，设计一套高颜值、高对比度、护眼可读的桌面知识库 UI 风格。"
        "你必须只输出一个合法 JSON 对象，不要包含任何解释或 Markdown 代码块，字段严格如下：\n"
        "{\n"
        '  "name": "中文风格名（2-8字）",\n'
        '  "englishName": "English Style Name",\n'
        '  "description": "一句中文视觉描述（15-45字）",\n'
        '  "mode": "light" 或 "dark",\n'
        '  "canvasBg": "#xxxxxx 主画布底色（light模式应浅亮，dark模式应深沉）",\n'
        '  "cardBg": "#xxxxxx 卡片底色（与canvasBg略有层次差）",\n'
        '  "accent": "#xxxxxx 核心强调色（在背景上清晰醒目）",\n'
        '  "secondary": "#xxxxxx 辅助点缀色",\n'
        '  "fontMood": "sans" | "serif" | "mono",\n'
        '  "texture": "none" | "grid" | "dots" | "aurora",\n'
        '  "cornerStyle": "sharp" | "balanced" | "soft"\n'
        "}"
    )
    req = ModelRequest(
        messages=[
            ModelMessage(role="system", content=system_prompt),
            ModelMessage(role="user", content=f"请为以下灵感设计 UI 风格：{payload.prompt.strip()}"),
        ],
        temperature=0.75,
        max_tokens=450,
    )
    try:
        resp = await adapter.generate(req)
    except ModelAdapterError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"AI 风格生成失败（请先检查模型与 Key 设置）：{type(exc).__name__}",
        ) from exc

    raw = (resp.content or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        raise HTTPException(status_code=502, detail="模型未返回有效的风格 JSON，请重试")
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="模型返回的风格 JSON 解析失败，请重试") from exc

    mode: Literal["light", "dark"] = "dark" if data.get("mode") == "dark" else "light"
    font_mood = data.get("fontMood") if data.get("fontMood") in ("sans", "serif", "mono") else "sans"
    texture = data.get("texture") if data.get("texture") in ("none", "grid", "dots", "aurora") else "aurora"
    corner = data.get("cornerStyle") if data.get("cornerStyle") in ("sharp", "balanced", "soft") else "balanced"

    return GenerateStyleOut(
        name=str(data.get("name") or payload.prompt.strip()[:10]).strip()[:24],
        englishName=str(data.get("englishName") or "AI Custom Style").strip()[:40],
        description=str(data.get("description") or f"基于「{payload.prompt.strip()[:30]}」生成的 AI 定制风格。").strip()[:120],
        mode=mode,
        canvasBg=_safe_hex(data.get("canvasBg"), "#111622" if mode == "dark" else "#f6f5f0"),
        cardBg=_safe_hex(data.get("cardBg"), "#181f30" if mode == "dark" else "#ffffff"),
        accent=_safe_hex(data.get("accent"), "#5b91ff" if mode == "dark" else "#3b74e8"),
        secondary=_safe_hex(data.get("secondary"), "#a78bfa" if mode == "dark" else "#64748b"),
        fontMood=font_mood,
        texture=texture,
        cornerStyle=corner,
    )
