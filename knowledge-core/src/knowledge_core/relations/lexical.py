"""词面相似度与去重候选召回（纯函数，无模型、无数据库）。

M2 去重的第一阶段：用规范化 + char-bigram 余弦做候选召回，
把昂贵的 LLM 判定限制在少量高相似候选上。语义向量召回留待 M3。
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence

from knowledge_core.domain.entities import KnowledgeItem

_NON_WORD = re.compile(r"[^\w一-鿿]+")


def normalize(text: str) -> str:
    """小写并去除标点/空白，保留字母数字与中日韩文字。"""
    return _NON_WORD.sub("", text.lower())


def _bigrams(text: str) -> Counter:
    if not text:
        return Counter()
    if len(text) < 2:
        return Counter([text])
    return Counter(text[i : i + 2] for i in range(len(text) - 1))


def _cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[t] * b[t] for t in set(a) & set(b))
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def text_similarity(
    title_a: str, content_a: str, title_b: str, content_b: str
) -> float:
    """标题与内容词面相似度的加权组合，取值 [0, 1]。"""
    ta, tb = normalize(title_a), normalize(title_b)
    title_sim = 1.0 if ta and ta == tb else _cosine(_bigrams(ta), _bigrams(tb))
    ca, cb = normalize(content_a), normalize(content_b)
    content_sim = 1.0 if ca and ca == cb else _cosine(_bigrams(ca), _bigrams(cb))
    return 0.4 * title_sim + 0.6 * content_sim


def recall_candidates(
    item: KnowledgeItem,
    candidates: Sequence[KnowledgeItem],
    *,
    threshold: float = 0.5,
    top_k: int = 5,
) -> list[tuple[KnowledgeItem, float]]:
    """返回与 item 词面相似度不低于阈值的候选，按相似度降序、最多 top_k 个。"""
    scored: list[tuple[KnowledgeItem, float]] = []
    for cand in candidates:
        if cand.id == item.id:
            continue
        score = text_similarity(item.title, item.content, cand.title, cand.content)
        if score >= threshold:
            scored.append((cand, score))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:top_k]