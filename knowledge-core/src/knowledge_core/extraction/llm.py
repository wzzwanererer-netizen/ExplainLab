"""基于模型的知识提取实现（M1）。

通过 ModelAdapter 调用模型做结构化提取，产出带来源追溯的 KnowledgeItem。
不依赖数据库与 Web 框架；持久化由 KnowledgeService 经仓库端口完成。
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

from knowledge_core.domain.entities import (
    KnowledgeItem,
    KnowledgeStatus,
    SourceRef,
    SourceType,
)
from knowledge_core.extraction import ExtractionService
from knowledge_core.model_adapter.base import ModelAdapter
from knowledge_core.model_adapter.types import ModelMessage, ModelRequest

_SYSTEM_PROMPT = """你是一个知识提取引擎。请从给定对话中提取值得长期保存的知识点。

要求：
1. 只提取明确、可复用、有信息量的知识（概念、结论、方法、事实、决策），忽略寒暄与无关内容。
2. 每条知识包含 title（简短标题，不超过 50 字）与 content（完整、自包含的表述）。
3. 严格只输出 JSON，格式为 {"items": [{"title": "...", "content": "..."}]}，不要输出任何解释或 Markdown。
4. 若没有值得提取的知识，返回 {"items": []}。"""

_EXCERPT_LIMIT = 300


def _parse_items(text: str) -> list[dict]:
    """健壮解析模型输出：兼容代码围栏、前后多余文本、直接数组。失败返回空列表。"""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()

    data = _loads_or_extract(cleaned)
    if isinstance(data, dict):
        items = data.get("items", [])
    elif isinstance(data, list):
        items = data
    else:
        return []
    return [it for it in items if isinstance(it, dict)]


def _loads_or_extract(text: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


class LLMExtractionService(ExtractionService):
    """用模型从对话中提取知识条目。"""

    def __init__(self, adapter: ModelAdapter, *, temperature: float = 0.2) -> None:
        self._adapter = adapter
        self._temperature = temperature

    async def extract(
        self,
        messages: Sequence[ModelMessage],
        *,
        space_id: str | None = None,
        conversation_id: str | None = None,
    ) -> list[KnowledgeItem]:
        if not messages:
            return []
        transcript = "\n".join(f"{m.role}: {m.content}" for m in messages)
        request = ModelRequest(
            messages=[
                ModelMessage(role="system", content=_SYSTEM_PROMPT),
                ModelMessage(role="user", content=transcript),
            ],
            temperature=self._temperature,
        )
        response = await self._adapter.generate(request)
        excerpt = transcript[:_EXCERPT_LIMIT]

        items: list[KnowledgeItem] = []
        for raw in _parse_items(response.content):
            title = str(raw.get("title") or "").strip()
            content = str(raw.get("content") or "").strip()
            if not title or not content:
                continue
            items.append(
                KnowledgeItem(
                    title=title[:500],
                    content=content,
                    status=KnowledgeStatus.DRAFT,
                    space_id=space_id,
                    source_refs=[
                        SourceRef(
                            source_type=SourceType.CONVERSATION,
                            conversation_id=conversation_id,
                            excerpt=excerpt,
                        )
                    ],
                )
            )
        return items