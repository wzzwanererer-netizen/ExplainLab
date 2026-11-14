"""跨会话混合检索实现（M3）。

全文（FTS）+ 向量双通道召回，RRF（Reciprocal Rank Fusion）融合排序。
仅依赖端口（KnowledgeRepository/FullTextIndex/VectorStore/Embedder），
不绑定数据库与 Web 框架，可复用于 Nesti。

space_id=None 跨全部空间；限定空间时过滤，个人总知识库聚合未归属条目
（与 M1 语义一致，personal_space_id 由应用层注入）。archived 默认不检索。
"""

from __future__ import annotations

from uuid import UUID

from knowledge_core.domain.entities import KnowledgeItem, KnowledgeStatus
from knowledge_core.ports import (
    Embedder,
    FullTextIndex,
    KnowledgeRepository,
    VectorStore,
)
from knowledge_core.retrieval import RetrievalService, SearchResult

RRF_K = 60


def rrf_fuse(channels: dict[str, list[UUID]], k: int = RRF_K) -> dict[UUID, float]:
    """RRF 融合：score = Σ_channel 1/(k+rank)，rank 从 1 起。"""
    scores: dict[UUID, float] = {}
    for hits in channels.values():
        for rank, item_id in enumerate(hits, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return scores


class HybridRetrievalService(RetrievalService):
    """全文 + 向量混合检索。embedder 为 None 时仅全文通道。"""

    def __init__(
        self,
        items: KnowledgeRepository,
        fts: FullTextIndex,
        vectors: VectorStore,
        embedder: Embedder | None = None,
        *,
        personal_space_id: str | None = None,
        k: int = RRF_K,
        candidate_multiplier: int = 3,
    ) -> None:
        self._items = items
        self._fts = fts
        self._vectors = vectors
        self._embedder = embedder
        self._personal_space_id = personal_space_id
        self._k = k
        self._multiplier = candidate_multiplier

    async def search(
        self,
        query: str,
        *,
        space_id: str | None = None,
        limit: int = 20,
        mode: str = "hybrid",
    ) -> list[SearchResult]:
        query = query.strip()
        if not query or limit <= 0:
            return []
        candidates = max(limit * self._multiplier, limit)

        hits: dict[str, list[UUID]] = {}
        raw: dict[str, dict[UUID, float]] = {}
        if mode in ("hybrid", "fts"):
            fts_hits = self._fts.search(query, candidates)
            hits["fts"] = [i for i, _ in fts_hits]
            raw["fts"] = dict(fts_hits)
        if mode in ("hybrid", "vector") and self._embedder is not None:
            vectors = await self._embedder.embed([query])
            if vectors:
                vec_hits = self._vectors.query(vectors[0], candidates)
                hits["vector"] = [i for i, _ in vec_hits]
                raw["vector"] = dict(vec_hits)

        fused = rrf_fuse(hits, self._k)
        results: list[SearchResult] = []
        for item_id, score in sorted(fused.items(), key=lambda kv: kv[1], reverse=True):
            item = self._items.get(item_id)
            if item is None or item.status == KnowledgeStatus.ARCHIVED:
                continue
            if not self._in_space(item.space_id, space_id):
                continue
            results.append(
                SearchResult(
                    item_id=item_id,
                    score=score,
                    snippet=self._snippet(item, query),
                    title=item.title,
                    space_id=item.space_id,
                    status=item.status.value,
                    channels={
                        ch: raw[ch][item_id] for ch in hits if item_id in raw[ch]
                    },
                )
            )
            if len(results) >= limit:
                break
        return results

    def _in_space(self, item_space: str | None, space_id: str | None) -> bool:
        if space_id is None:
            return True
        if item_space == space_id:
            return True
        return (
            self._personal_space_id is not None
            and space_id == self._personal_space_id
            and item_space is None
        )

    @staticmethod
    def _snippet(item: KnowledgeItem, query: str, width: int = 80) -> str:
        text = item.content
        idx = text.find(query)
        if idx < 0:
            return text[:width]
        start = max(0, idx - width // 2)
        return text[start : start + width]