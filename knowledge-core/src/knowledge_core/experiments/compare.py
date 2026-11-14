"""基于模型的两条知识结构化对比（M5）。

仅使用 ModelAdapter.generate：产出相同点 / 不同点 / 关系判定。
若已有关系（来自 M2 关系库）则作为提示传入，模型可参考但独立给出判断。
解析失败如实返回空对比（仅含两条知识 id），不造假。
"""

from __future__ import annotations

from knowledge_core.domain.entities import KnowledgeItem, RelationType
from knowledge_core.experiments.entities import CompareResult
from knowledge_core.model_adapter.base import ModelAdapter
from knowledge_core.model_adapter.types import ModelMessage, ModelRequest
from knowledge_core.parsing import extract_json

_COMPARE_PROMPT = """你是知识对比引擎。给定两条知识 A 与 B，结构化对比它们的异同与关系。

要求：
1. similarities / differences 各为若干条简短中文要点（字符串数组），紧扣内容，不编造。
2. relationship 用一句话概括两者关系。
3. relation_type 仅限 related / depends_on / refines / contradicts / duplicate_of，无法判定则为 null。
4. 严格只输出 JSON，格式为 {"similarities": ["..."], "differences": ["..."], "relationship": "<一句话>", "relation_type": "<类型或null>"}，不要输出任何解释或 Markdown。"""


def _format_block(label: str, item: KnowledgeItem) -> str:
    return f"{label}:\ntitle: {item.title}\ncontent: {item.content}"


def _str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [v.strip() for v in value if isinstance(v, str) and v.strip()]


class LLMCompareService:
    """LLM 结构化对比。"""

    def __init__(self, adapter: ModelAdapter, *, temperature: float = 0.3) -> None:
        self._adapter = adapter
        self._temperature = temperature

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

    async def compare(
        self,
        a: KnowledgeItem,
        b: KnowledgeItem,
        existing_relation: RelationType | None = None,
    ) -> CompareResult:
        """对比 a 与 b；解析失败返回仅含 id 的空对比。"""
        hint = (
            f"\n\n已知关系提示（仅供参考）：{existing_relation.value}"
            if existing_relation is not None
            else ""
        )
        user = f"{_format_block('A', a)}\n\n{_format_block('B', b)}{hint}"
        data = await self._generate(_COMPARE_PROMPT, user)
        if not isinstance(data, dict):
            return CompareResult(item_a_id=a.id, item_b_id=b.id)
        relation_type: RelationType | None = None
        raw_type = data.get("relation_type")
        if isinstance(raw_type, str):
            try:
                relation_type = RelationType(raw_type)
            except ValueError:
                relation_type = None
        relationship = data.get("relationship", "")
        if not isinstance(relationship, str):
            relationship = ""
        return CompareResult(
            item_a_id=a.id,
            item_b_id=b.id,
            similarities=_str_list(data.get("similarities")),
            differences=_str_list(data.get("differences")),
            relationship=relationship.strip(),
            relation_type=relation_type,
        )
