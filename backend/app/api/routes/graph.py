"""M4 知识地图路由：节点 + 边只读视图。

GET /api/graph：装配 Knowledge Core 图服务（空间过滤 + 归档开关）。
图是现有 knowledge_item + knowledge_relation 的视图，无新增表 / 迁移。
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Annotated
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import GraphEdgeOut, GraphNodeOut, GraphOut
from app.db.session import get_session
from app.models import KnowledgeItemORM
from app.services.graph import build_graph_service
from app.services.spaces import get_space

router = APIRouter(tags=["graph"])

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]")
_TAG_RE = re.compile(r"(?:^|[\s(（\[【])#([\w\u4e00-\u9fff\-_/]{2,24})")
_EN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,24}")
_ZH_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,6}")

_STOP_TAGS = {"文件夹收编", "桌面", "下载", "导入", "文档", "笔记", "草稿"}
_STOP_TOKENS = {
    "the", "and", "for", "with", "from", "this", "that", "into", "using",
    "项目", "方案", "设计", "规划", "总结", "说明", "文档", "问题", "测试",
    "功能", "系统", "实现", "配置", "分析", "记录", "方法", "机制", "使用",
    "优化", "修复", "更新", "改造", "架构", "指南", "演示", "流程", "管理",
}


def _extract_title_tokens(title: str) -> set[str]:
    tokens: set[str] = set()
    for m in _EN_TOKEN_RE.findall(title):
        low = m.lower()
        if low not in _STOP_TOKENS and not low.isdigit():
            tokens.add(low)
    for m in _ZH_TOKEN_RE.findall(title):
        if m not in _STOP_TOKENS:
            tokens.add(m)
            # 对 4~6 字中文复合词额外取首尾 2 字核心词干（如「网络安全项目」→「网络安全」）
            if len(m) >= 4:
                head2 = m[:2]
                if head2 not in _STOP_TOKENS:
                    tokens.add(head2)
    return tokens


def _infer_implicit_edges(
    session: Session,
    nodes: list[GraphNodeOut],
    existing_edges: list[GraphEdgeOut],
) -> list[GraphEdgeOut]:
    """零 Token 自动发现隐式关联边（[[双链]] + 共享 #标签 + 标题强主题词），让星图不再孤立零连线。"""
    if len(nodes) < 2:
        return []

    node_ids = [str(n.id) for n in nodes]
    rows = session.execute(
        select(KnowledgeItemORM.id, KnowledgeItemORM.title, KnowledgeItemORM.content).where(
            KnowledgeItemORM.id.in_(node_ids)
        )
    ).all()
    by_id = {str(r[0]): (str(r[1] or ""), str(r[2] or "")) for r in rows}
    title_to_id = {t.strip().lower(): nid for nid, (t, _) in by_id.items() if t.strip()}

    seen_pairs: set[tuple[str, str]] = set()
    for e in existing_edges:
        a, b = sorted((str(e.source_id), str(e.target_id)))
        seen_pairs.add((a, b))

    inferred: list[GraphEdgeOut] = []
    auto_degree: dict[str, int] = defaultdict(int)

    def _try_add(src: str, dst: str, confidence: float, key_tag: str) -> None:
        if src == dst:
            return
        a, b = sorted((src, dst))
        if (a, b) in seen_pairs:
            return
        if auto_degree[src] >= 4 or auto_degree[dst] >= 4:
            return
        seen_pairs.add((a, b))
        auto_degree[src] += 1
        auto_degree[dst] += 1
        inferred.append(
            GraphEdgeOut(
                id=uuid5(NAMESPACE_URL, f"auto:{key_tag}:{a}:{b}"),
                source_id=UUID(a),
                target_id=UUID(b),
                relation_type="related",
                confidence=confidence,
                origin="manual",
            )
        )

    # 1. 显式 [[双链]]
    for nid, (_, content) in by_id.items():
        for raw_link in _WIKILINK_RE.findall(content):
            target = title_to_id.get(raw_link.strip().lower())
            if target:
                _try_add(nid, target, 0.95, "wiki")

    # 2. 共享非泛化 #标签
    tag_buckets: dict[str, list[str]] = defaultdict(list)
    for nid, (_, content) in by_id.items():
        for tag in set(_TAG_RE.findall(content)):
            clean_tag = tag.strip().lower()
            if clean_tag and clean_tag not in _STOP_TAGS:
                tag_buckets[clean_tag].append(nid)
    for tag, members in tag_buckets.items():
        if 2 <= len(members) <= 10:
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    _try_add(members[i], members[j], 0.85, f"tag-{tag[:6]}")

    # 3. 标题核心项目/主题词共现（每个词仅在 2..10 个节点间连线，避免超级节点糊成毛线团）
    token_buckets: dict[str, list[str]] = defaultdict(list)
    for nid, (title, _) in by_id.items():
        for tok in _extract_title_tokens(title):
            token_buckets[tok].append(nid)

    pair_scores: dict[tuple[str, str], int] = defaultdict(int)
    for members in token_buckets.values():
        if 2 <= len(members) <= 18:
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    a, b = sorted((members[i], members[j]))
                    pair_scores[(a, b)] += 1

    for (a, b), score in sorted(pair_scores.items(), key=lambda kv: kv[1], reverse=True):
        conf = min(0.88, 0.68 + 0.08 * score)
        _try_add(a, b, round(conf, 2), "topic")

    return inferred


@router.get("/graph", response_model=GraphOut)
def get_graph(
    session: Annotated[Session, Depends(get_session)],
    space_id: str | None = None,
    include_archived: bool = False,
) -> GraphOut:
    include_unassigned = False
    if space_id is not None:
        space = get_space(session, space_id)
        if space is None:
            raise HTTPException(status_code=404, detail=f"知识空间不存在: {space_id}")
        include_unassigned = space.kind == "personal"
    graph = build_graph_service(session).build_graph(
        space_id=space_id,
        include_unassigned=include_unassigned,
        include_archived=include_archived,
    )
    node_outs = [GraphNodeOut.model_validate(n) for n in graph.nodes]
    edge_outs = [GraphEdgeOut.model_validate(e) for e in graph.edges]
    edge_outs.extend(_infer_implicit_edges(session, node_outs, edge_outs))
    return GraphOut(nodes=node_outs, edges=edge_outs)