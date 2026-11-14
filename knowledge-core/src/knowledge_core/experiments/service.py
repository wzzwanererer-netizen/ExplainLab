"""实验编排服务（M5）。

统一创建 / 公开视图 / 作答 / 完成四类操作，经端口持久化，按模式分派到
quiz / compare / chain 子服务。Core 不绑定数据库与 Web 框架：
- 测验 / 对比需要 ModelAdapter，未配置时抛 ModelRequiredError（应用层映射 503）；
- 学习路径纯确定性，无需模型；
- 正确答案与解析服务端持有，public_view 仅在会话完成后揭示。
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from knowledge_core.domain.entities import KnowledgeItem, RelationType, utcnow
from knowledge_core.experiments.chain import ChainService
from knowledge_core.experiments.compare import LLMCompareService
from knowledge_core.experiments.entities import (
    AnswerFeedback,
    ExperimentAttempt,
    ExperimentKind,
    ExperimentSession,
    ExperimentStatus,
)
from knowledge_core.experiments.errors import (
    ExperimentNotFoundError,
    InvalidExperimentError,
    ModelRequiredError,
)
from knowledge_core.experiments.quiz import LLMQuizService
from knowledge_core.model_adapter.base import ModelAdapter
from knowledge_core.ports import (
    ExperimentRepository,
    KnowledgeRepository,
    RelationRepository,
)


class ExperimentService:
    """实验会话编排。"""

    def __init__(
        self,
        items: KnowledgeRepository,
        relations: RelationRepository,
        experiments: ExperimentRepository,
        adapter: ModelAdapter | None = None,
        *,
        quiz_temperature: float = 0.4,
        compare_temperature: float = 0.3,
    ) -> None:
        self._items = items
        self._relations = relations
        self._experiments = experiments
        self._adapter = adapter
        self._quiz_temperature = quiz_temperature
        self._compare_temperature = compare_temperature

    async def create(
        self,
        kind: ExperimentKind | str,
        item_ids: Sequence[UUID],
        *,
        space_id: str | None = None,
        include_unassigned: bool = False,
        count: int = 5,
        seed_id: UUID | None = None,
    ) -> ExperimentSession:
        """创建一次实验会话并持久化。"""
        try:
            kind = ExperimentKind(kind)
        except ValueError as exc:
            raise InvalidExperimentError(f"未知实验模式: {kind}") from exc

        selected: list[KnowledgeItem] = []
        for item_id in item_ids:
            item = self._items.get(item_id)
            if item is None:
                raise ExperimentNotFoundError(f"知识条目不存在: {item_id}")
            selected.append(item)

        if kind == ExperimentKind.QUIZ:
            session = await self._create_quiz(selected, space_id, count)
        elif kind == ExperimentKind.COMPARE:
            session = await self._create_compare(selected, space_id)
        else:
            session = self._create_chain(selected, space_id, include_unassigned, count, seed_id)
        return self._experiments.save_session(session)

    async def _create_quiz(
        self, items: list[KnowledgeItem], space_id: str | None, count: int
    ) -> ExperimentSession:
        if not items:
            raise InvalidExperimentError("测验至少需要 1 条知识")
        if self._adapter is None:
            raise ModelRequiredError("测验需要配置模型")
        questions = await LLMQuizService(
            self._adapter, temperature=self._quiz_temperature
        ).generate(items, count)
        if not questions:
            raise InvalidExperimentError("模型未生成有效题目")
        title = f"知识测验 · {items[0].title}"
        if len(items) > 1:
            title += f" 等 {len(items)} 条"
        return ExperimentSession(
            kind=ExperimentKind.QUIZ,
            title=title,
            space_id=space_id,
            item_ids=[i.id for i in items],
            payload={"questions": [q.model_dump(mode="json") for q in questions]},
        )

    async def _create_compare(
        self, items: list[KnowledgeItem], space_id: str | None
    ) -> ExperimentSession:
        if len(items) != 2:
            raise InvalidExperimentError("对比需要恰好 2 条知识")
        if self._adapter is None:
            raise ModelRequiredError("对比需要配置模型")
        existing = self._find_relation_type(items[0].id, items[1].id)
        result = await LLMCompareService(
            self._adapter, temperature=self._compare_temperature
        ).compare(items[0], items[1], existing)
        return ExperimentSession(
            kind=ExperimentKind.COMPARE,
            title=f"知识对比 · {items[0].title} ↔ {items[1].title}",
            space_id=space_id,
            item_ids=[i.id for i in items],
            payload={"compare": result.model_dump(mode="json")},
        )

    def _create_chain(
        self,
        items: list[KnowledgeItem],
        space_id: str | None,
        include_unassigned: bool,
        count: int,
        seed_id: UUID | None,
    ) -> ExperimentSession:
        if not items:
            raise InvalidExperimentError("学习路径至少需要 1 条知识")
        seed = seed_id or items[0].id
        pool = self._items.list(space_id=space_id, include_unassigned=include_unassigned)
        steps = ChainService(pool, self._relations.list_all_relations()).build(
            seed, max_steps=count
        )
        if not steps:
            raise InvalidExperimentError("无法装配学习路径")
        seed_item = next((i for i in items if i.id == seed), items[0])
        return ExperimentSession(
            kind=ExperimentKind.CHAIN,
            title=f"学习路径 · {seed_item.title}",
            space_id=space_id,
            item_ids=[s.item_id for s in steps],
            payload={"steps": [s.model_dump(mode="json") for s in steps]},
        )

    def _find_relation_type(self, a: UUID, b: UUID) -> RelationType | None:
        for relation in self._relations.list_all_relations():
            if {relation.source_id, relation.target_id} == {a, b}:
                return relation.relation_type
        return None

    def public_view(self, session: ExperimentSession) -> dict:
        """对外视图：测验未完成时隐藏正确答案与解析。"""
        data = session.model_dump(mode="json")
        if session.kind == ExperimentKind.QUIZ:
            reveal = session.status == ExperimentStatus.COMPLETED
            questions = []
            for q in session.payload.get("questions", []):
                pub = {
                    key: q[key] for key in ("index", "prompt", "kind", "options", "source_item_id")
                }
                if reveal:
                    pub["correct_index"] = q["correct_index"]
                    pub["explanation"] = q["explanation"]
                questions.append(pub)
            data["payload"] = {"questions": questions}
        return data

    def answer(self, session: ExperimentSession, index: int, value: int) -> AnswerFeedback:
        """单题即时判分（仅测验）。"""
        if session.kind != ExperimentKind.QUIZ:
            raise InvalidExperimentError("仅测验支持作答")
        questions = session.payload.get("questions", [])
        if not isinstance(index, int) or not 0 <= index < len(questions):
            raise InvalidExperimentError("题目序号越界")
        question = questions[index]
        options = question.get("options", [])
        if not isinstance(value, int) or not 0 <= value < len(options):
            raise InvalidExperimentError("选项序号越界")
        return AnswerFeedback(
            correct=value == question["correct_index"],
            correct_value=question["correct_index"],
            explanation=question.get("explanation", ""),
        )

    def complete(self, session: ExperimentSession, answers: Sequence[dict]) -> ExperimentAttempt:
        """完成会话：测验判分汇总并持久化作答记录，其余模式仅标记完成。"""
        if session.kind == ExperimentKind.QUIZ:
            questions = session.payload.get("questions", [])
            graded: list[dict] = []
            correct_count = 0
            for ans in answers:
                idx = ans.get("index")
                val = ans.get("value")
                if not isinstance(idx, int) or not 0 <= idx < len(questions):
                    continue
                ok = isinstance(val, int) and val == questions[idx]["correct_index"]
                correct_count += int(ok)
                graded.append({"index": idx, "value": val, "correct": ok})
            total = len(questions)
            attempt = ExperimentAttempt(
                session_id=session.id,
                answers=graded,
                correct_count=correct_count,
                total=total,
                score=correct_count / total if total else 0.0,
            )
        else:
            attempt = ExperimentAttempt(session_id=session.id)
        self._experiments.save_attempt(attempt)
        updated = session.model_copy(
            update={"status": ExperimentStatus.COMPLETED, "updated_at": utcnow()}
        )
        self._experiments.update_session(updated)
        return attempt
