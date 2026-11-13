"""基于模型的去重判定与关系推断实现（M2）。

仅使用 ModelAdapter.generate（不依赖 embed）：先词面召回候选，再让模型判定
「是否同一知识」与「关系类型 + 置信度」。解析失败如实返回空列表，不造假。
不依赖数据库与 Web 框架；关系持久化由应用层经 RelationRepository 完成。
"""

from __future__ import annotations

from collections.abc import Sequence

from knowledge_core.domain.entities import (
    KnowledgeItem,
    KnowledgeRelation,
    RelationOrigin,
    RelationType,
)
from knowledge_core.model_adapter.base import ModelAdapter
from knowledge_core.model_adapter.types import ModelMessage, ModelRequest
from knowledge_core.parsing import extract_json
from knowledge_core.relations import DuplicateMatch, RelationService
from knowledge_core.relations.lexical import recall_candidates

_DUP_PROMPT = """你是知识去重判定引擎。给定一条目标知识与若干候选知识，判断哪些候选与目标表达“同一知识”（含义重复，允许措辞不同）。

要求：
1. 仅对确实重复的候选置 same=true；部分相关但不重复的置 same=false。
2. confidence 为 0 到 1 的判定置信度。
3. 严格只输出 JSON，格式为 {"duplicates": [{"index": <候选序号,从0开始>, "same": true/false, "confidence": <0..1>}]}，不要输出任何解释或 Markdown。"""

_REL_PROMPT = """你是知识关系推断引擎。给定一条目标知识与若干候选知识，推断目标与候选之间的关系。

要求：
1. 关系类型仅限：related（相关）、depends_on（目标依赖候选）、refines（目标细化候选）、contradicts（矛盾）。
2. 无明确关系的候选不要列出。
3. confidence 为 0 到 1 的推断置信度。
4. 严格只输出 JSON，格式为 {"relations": [{"index": <候选序号,从0开始>, "type": "<类型>", "confidence": <0..1>}]}，不要输出任何解释或 Markdown。"""

_REL_TYPES = {
    RelationType.RELATED,
    RelationType.DEPENDS_ON,
    RelationType.REFINES,
    RelationType.CONTRADICTS,
}


def _format_block(item: KnowledgeItem) -> str:
    return f"title: {item.title}\ncontent: {item.content}"


def _format_candidates(candidates: Sequence[KnowledgeItem]) -> str:
    return "\n".join(
        f"[{i}] {_format_block(c)}" for i, c in enumerate(candidates)
    )


def _clamp(value: object, default: float) -> float:
    try:
        num = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, num))


class LLMRelationService(RelationService):
    """词面召回 + LLM 判定的去重与关系推断。"""

    def __init__(
        self,
        adapter: ModelAdapter,
        *,
        temperature: float = 0.1,
        recall_threshold: float = 0.5,
        top_k: int = 5,
    ) -> None:
        self._adapter = adapter
        self._temperature = temperature
        self._recall_threshold = recall_threshold
        self._top_k = top_k

    async def _generate(self, system: str, user: str) -> object:
        response = await self._adapter.generate(
            ModelRequest(
                messages=[
                    ModelMessage(role="system", content=system),
                    ModelMessage(role="user", content=user),
                ],
                temperature=self._temperature,
            )
        )
        return extract_json(response.content)

    async def find_duplicates(
        self,
        item: KnowledgeItem,
        candidates: Sequence[KnowledgeItem],
    ) -> list[DuplicateMatch]:
        recalled = recall_candidates(
            item,
            candidates,
            threshold=self._recall_threshold,
            top_k=self._top_k,
        )
        if not recalled:
            return []
        pool = [c for c, _ in recalled]
        user = f"目标：\n{_format_block(item)}\n\n候选：\n{_format_candidates(pool)}"
        data = await self._generate(_DUP_PROMPT, user)
        if not isinstance(data, dict):
            return []
        matches: list[DuplicateMatch] = []
        for raw in data.get("duplicates", []):
            if not isinstance(raw, dict) or not raw.get("same"):
                continue
            idx = raw.get("index")
            if not isinstance(idx, int) or not 0 <= idx < len(pool):
                continue
            matches.append(
                DuplicateMatch(
                    item_id=pool[idx].id,
                    score=_clamp(raw.get("confidence"), recalled[idx][1]),
                )
            )
        return matches

    async def infer_relations(
        self,
        item: KnowledgeItem,
        candidates: Sequence[KnowledgeItem],
    ) -> list[KnowledgeRelation]:
        recalled = recall_candidates(
            item,
            candidates,
            threshold=self._recall_threshold,
            top_k=self._top_k,
        )
        if not recalled:
            return []
        pool = [c for c, _ in recalled]
        user = f"目标：\n{_format_block(item)}\n\n候选：\n{_format_candidates(pool)}"
        data = await self._generate(_REL_PROMPT, user)
        if not isinstance(data, dict):
            return []
        relations: list[KnowledgeRelation] = []
        for raw in data.get("relations", []):
            if not isinstance(raw, dict):
                continue
            idx = raw.get("index")
            if not isinstance(idx, int) or not 0 <= idx < len(pool):
                continue
            try:
                rel_type = RelationType(str(raw.get("type")))
            except ValueError:
                continue
            if rel_type not in _REL_TYPES:
                continue
            target = pool[idx]
            if target.id == item.id:
                continue
            relations.append(
                KnowledgeRelation(
                    source_id=item.id,
                    target_id=target.id,
                    relation_type=rel_type,
                    confidence=_clamp(raw.get("confidence"), 0.5),
                    origin=RelationOrigin.LLM,
                )
            )
        return relations