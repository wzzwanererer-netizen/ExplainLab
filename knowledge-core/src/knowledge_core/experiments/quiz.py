"""基于模型的测验生成与服务端判分（M5）。

仅使用 ModelAdapter.generate：让模型围绕给定知识出题（单选 / 判断），
正确答案与解析由服务端持有，未作答不下发。解析失败如实返回空列表，不造假。
判分为确定性比较（选项序号），不依赖模型阅卷。
"""

from __future__ import annotations

from collections.abc import Sequence

from knowledge_core.domain.entities import KnowledgeItem
from knowledge_core.experiments.entities import (
    AnswerFeedback,
    QuizQuestion,
    QuizQuestionKind,
)
from knowledge_core.model_adapter.base import ModelAdapter
from knowledge_core.model_adapter.types import ModelMessage, ModelRequest
from knowledge_core.parsing import extract_json

_QUIZ_PROMPT = """你是知识测验出题引擎。围绕给定的若干条知识，生成测验题，帮助学习者检验理解。

要求：
1. 题目须紧扣所给知识内容，不要编造知识中不存在的事实。
2. 题型 kind 仅限 single_choice（单选，4 个选项）或 true_false（判断，选项固定为 ["正确","错误"]）。
3. correct_index 为正确选项序号（从 0 开始），必须落在 options 范围内。
4. source_index 指明该题主要考查哪条知识（从 0 开始的候选序号）。
5. explanation 用一句话说明为何正确。
6. 严格只输出 JSON，格式为 {"questions": [{"prompt": "<题干>", "kind": "<题型>", "options": ["..."], "correct_index": <int>, "explanation": "<解析>", "source_index": <int>}]}，不要输出任何解释或 Markdown。"""


def _format_block(item: KnowledgeItem) -> str:
    return f"title: {item.title}\ncontent: {item.content}"


def _format_items(items: Sequence[KnowledgeItem]) -> str:
    return "\n".join(f"[{i}] {_format_block(it)}" for i, it in enumerate(items))


class LLMQuizService:
    """LLM 出题 + 确定性判分。"""

    def __init__(self, adapter: ModelAdapter, *, temperature: float = 0.4) -> None:
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

    async def generate(self, items: Sequence[KnowledgeItem], count: int = 5) -> list[QuizQuestion]:
        """围绕 items 生成至多 count 道题；解析失败返回空列表。"""
        if not items or count <= 0:
            return []
        user = f"请生成 {count} 道题。\n\n知识：\n{_format_items(items)}"
        data = await self._generate(_QUIZ_PROMPT, user)
        if not isinstance(data, dict):
            return []
        questions: list[QuizQuestion] = []
        for raw in data.get("questions", []):
            if len(questions) >= count:
                break
            question = self._parse_question(raw, items, len(questions))
            if question is not None:
                questions.append(question)
        return questions

    @staticmethod
    def _parse_question(
        raw: object, items: Sequence[KnowledgeItem], index: int
    ) -> QuizQuestion | None:
        if not isinstance(raw, dict):
            return None
        prompt = raw.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return None
        try:
            kind = QuizQuestionKind(str(raw.get("kind", "single_choice")))
        except ValueError:
            return None
        options = raw.get("options")
        if not isinstance(options, list) or len(options) < 2:
            return None
        if not all(isinstance(o, str) and o.strip() for o in options):
            return None
        correct = raw.get("correct_index")
        if not isinstance(correct, int) or not 0 <= correct < len(options):
            return None
        source = raw.get("source_index")
        if not isinstance(source, int) or not 0 <= source < len(items):
            return None
        explanation = raw.get("explanation", "")
        if not isinstance(explanation, str):
            explanation = ""
        return QuizQuestion(
            index=index,
            prompt=prompt.strip(),
            kind=kind,
            options=[o.strip() for o in options],
            correct_index=correct,
            explanation=explanation.strip(),
            source_item_id=items[source].id,
        )

    @staticmethod
    def grade(question: QuizQuestion, value: int) -> AnswerFeedback:
        """确定性判分：选项序号比对，返回正确答案与解析。"""
        return AnswerFeedback(
            correct=value == question.correct_index,
            correct_value=question.correct_index,
            explanation=question.explanation,
        )
