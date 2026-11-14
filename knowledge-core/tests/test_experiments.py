"""M5 Core 实验测试：实体校验 + quiz/compare/chain 子服务 + 编排（FakeAdapter，不发真实请求）。"""

from __future__ import annotations

import pytest
from helpers import (
    FakeAdapter,
    InMemoryExperimentRepository,
    InMemoryKnowledgeRepository,
    InMemoryRelationRepository,
)
from pydantic import ValidationError

from knowledge_core.domain.entities import (
    KnowledgeItem,
    KnowledgeRelation,
    RelationType,
)
from knowledge_core.experiments import (
    ChainService,
    ExperimentKind,
    ExperimentService,
    ExperimentStatus,
    InvalidExperimentError,
    LLMCompareService,
    LLMQuizService,
    ModelRequiredError,
    QuizQuestion,
    QuizQuestionKind,
)
from knowledge_core.experiments.errors import ExperimentNotFoundError

_QUIZ_JSON = (
    '{"questions": ['
    '{"prompt": "Q1", "kind": "single_choice", "options": ["A","B","C","D"],'
    ' "correct_index": 1, "explanation": "因为B", "source_index": 0},'
    '{"prompt": "Q2", "kind": "true_false", "options": ["正确","错误"],'
    ' "correct_index": 0, "explanation": "对", "source_index": 0}]}'
)

_COMPARE_JSON = (
    '{"similarities": ["都涉及知识"], "differences": ["A 偏定义","B 偏用途"],'
    ' "relationship": "B 细化 A", "relation_type": "refines"}'
)


def _item(title: str, content: str = "内容", space_id: str | None = None) -> KnowledgeItem:
    return KnowledgeItem(title=title, content=content, space_id=space_id)


def _service(adapter: FakeAdapter | None = None):
    items = InMemoryKnowledgeRepository()
    relations = InMemoryRelationRepository()
    experiments = InMemoryExperimentRepository()
    service = ExperimentService(items, relations, experiments, adapter)
    return items, relations, experiments, service


# ---- 实体校验 ----


def test_quiz_question_correct_index_out_of_range():
    with pytest.raises(ValidationError):
        QuizQuestion(
            index=0,
            prompt="Q",
            options=["A", "B"],
            correct_index=5,
            source_item_id=_item("X").id,
        )


def test_quiz_question_defaults_single_choice():
    q = QuizQuestion(
        index=0, prompt="Q", options=["A", "B"], correct_index=0, source_item_id=_item("X").id
    )
    assert q.kind == QuizQuestionKind.SINGLE_CHOICE


# ---- LLMQuizService ----


async def test_quiz_generate_parses_and_maps_source():
    item = _item("知识图谱")
    adapter = FakeAdapter(_QUIZ_JSON)
    questions = await LLMQuizService(adapter).generate([item], count=5)
    assert len(questions) == 2
    assert questions[0].index == 0
    assert questions[1].index == 1
    assert questions[0].correct_index == 1
    assert questions[0].source_item_id == item.id
    assert questions[1].kind == QuizQuestionKind.TRUE_FALSE
    assert adapter.last_request is not None


async def test_quiz_generate_respects_count():
    item = _item("X")
    questions = await LLMQuizService(FakeAdapter(_QUIZ_JSON)).generate([item], count=1)
    assert len(questions) == 1


async def test_quiz_generate_malformed_returns_empty():
    assert await LLMQuizService(FakeAdapter("不是 JSON")).generate([_item("X")]) == []


async def test_quiz_generate_skips_invalid_questions():
    bad = (
        '{"questions": ['
        '{"prompt": "ok", "options": ["A","B"], "correct_index": 0, "source_index": 0},'
        '{"prompt": "bad_correct", "options": ["A","B"], "correct_index": 9, "source_index": 0},'
        '{"prompt": "bad_source", "options": ["A","B"], "correct_index": 0, "source_index": 9},'
        '{"prompt": "bad_options", "options": ["A"], "correct_index": 0, "source_index": 0}]}'
    )
    questions = await LLMQuizService(FakeAdapter(bad)).generate([_item("X")])
    assert len(questions) == 1
    assert questions[0].prompt == "ok"


async def test_quiz_generate_empty_items_skips_model():
    adapter = FakeAdapter(_QUIZ_JSON)
    assert await LLMQuizService(adapter).generate([]) == []
    assert adapter.last_request is None


def test_quiz_grade_correct_and_incorrect():
    q = QuizQuestion(
        index=0,
        prompt="Q",
        options=["A", "B"],
        correct_index=1,
        explanation="B 对",
        source_item_id=_item("X").id,
    )
    assert LLMQuizService.grade(q, 1).correct is True
    feedback = LLMQuizService.grade(q, 0)
    assert feedback.correct is False
    assert feedback.correct_value == 1
    assert feedback.explanation == "B 对"


# ---- LLMCompareService ----


async def test_compare_parses_fields():
    a, b = _item("A"), _item("B")
    result = await LLMCompareService(FakeAdapter(_COMPARE_JSON)).compare(a, b)
    assert result.item_a_id == a.id
    assert result.similarities == ["都涉及知识"]
    assert result.differences == ["A 偏定义", "B 偏用途"]
    assert result.relationship == "B 细化 A"
    assert result.relation_type == RelationType.REFINES


async def test_compare_invalid_relation_type_is_none():
    payload = (
        '{"similarities": [], "differences": [], "relationship": "", "relation_type": "bogus"}'
    )
    result = await LLMCompareService(FakeAdapter(payload)).compare(_item("A"), _item("B"))
    assert result.relation_type is None


async def test_compare_malformed_returns_empty_with_ids():
    a, b = _item("A"), _item("B")
    result = await LLMCompareService(FakeAdapter("oops")).compare(a, b)
    assert result.item_a_id == a.id
    assert result.item_b_id == b.id
    assert result.similarities == []
    assert result.differences == []


async def test_compare_passes_existing_relation_hint():
    adapter = FakeAdapter(_COMPARE_JSON)
    await LLMCompareService(adapter).compare(_item("A"), _item("B"), RelationType.RELATED)
    assert adapter.last_request is not None
    assert "related" in adapter.last_request.messages[-1].content


# ---- ChainService（确定性，无模型） ----


def _chain_pool():
    base = _item("基础概念")
    mid = _item("进阶应用")
    top = _item("综合实战")
    relations = [
        KnowledgeRelation(
            source_id=mid.id, target_id=base.id, relation_type=RelationType.DEPENDS_ON
        ),
        KnowledgeRelation(source_id=top.id, target_id=mid.id, relation_type=RelationType.REFINES),
    ]
    return [base, mid, top], relations


def test_chain_prerequisites_first_seed_last():
    pool, relations = _chain_pool()
    base, mid, top = pool
    steps = ChainService(pool, relations).build(top.id)
    assert [s.item_id for s in steps] == [base.id, mid.id, top.id]
    assert steps[0].relation_from_prev is None
    assert steps[1].relation_from_prev == RelationType.DEPENDS_ON
    assert steps[2].relation_from_prev == RelationType.REFINES
    assert [s.position for s in steps] == [0, 1, 2]


def test_chain_anti_cycle():
    a, b = _item("A"), _item("B")
    relations = [
        KnowledgeRelation(source_id=a.id, target_id=b.id, relation_type=RelationType.DEPENDS_ON),
        KnowledgeRelation(source_id=b.id, target_id=a.id, relation_type=RelationType.DEPENDS_ON),
    ]
    steps = ChainService([a, b], relations).build(a.id)
    assert len(steps) == 2  # 环被 visited 截断，不死循环
    assert {s.item_id for s in steps} == {a.id, b.id}


def test_chain_deterministic_tie_break():
    seed = _item("终点")
    p1, p2 = _item("Alpha"), _item("Beta")
    relations = [
        KnowledgeRelation(
            source_id=seed.id, target_id=p2.id, relation_type=RelationType.DEPENDS_ON
        ),
        KnowledgeRelation(
            source_id=seed.id, target_id=p1.id, relation_type=RelationType.DEPENDS_ON
        ),
    ]
    steps = ChainService([seed, p1, p2], relations).build(seed.id)
    assert [s.title for s in steps] == ["Alpha", "Beta", "终点"]


def test_chain_max_steps_keeps_seed_last():
    pool, relations = _chain_pool()
    top = pool[2]
    steps = ChainService(pool, relations).build(top.id, max_steps=2)
    assert len(steps) == 2
    assert steps[-1].item_id == top.id


def test_chain_seed_not_in_pool_returns_empty():
    pool, relations = _chain_pool()
    assert ChainService(pool, relations).build(_item(" outsider ").id) == []


def test_chain_single_item_no_relations():
    only = _item("孤立")
    steps = ChainService([only], []).build(only.id)
    assert len(steps) == 1
    assert steps[0].item_id == only.id
    assert steps[0].relation_from_prev is None


# ---- ExperimentService 编排 ----


async def test_create_quiz_persists_and_hides_answers():
    items, _, experiments, service = _service(FakeAdapter(_QUIZ_JSON))
    item = items.save(_item("知识图谱"))
    session = await service.create(ExperimentKind.QUIZ, [item.id], count=5)
    assert experiments.get_session(session.id) is not None
    assert session.kind == ExperimentKind.QUIZ
    assert session.status == ExperimentStatus.ACTIVE
    assert len(session.payload["questions"]) == 2
    view = service.public_view(session)
    q0 = view["payload"]["questions"][0]
    assert "correct_index" not in q0
    assert "explanation" not in q0
    assert q0["options"] == ["A", "B", "C", "D"]


async def test_create_quiz_requires_model():
    items, _, _, service = _service(None)
    item = items.save(_item("X"))
    with pytest.raises(ModelRequiredError):
        await service.create(ExperimentKind.QUIZ, [item.id])


async def test_create_quiz_empty_items_invalid():
    _, _, _, service = _service(FakeAdapter(_QUIZ_JSON))
    with pytest.raises(InvalidExperimentError):
        await service.create(ExperimentKind.QUIZ, [])


async def test_create_quiz_model_empty_invalid():
    items, _, _, service = _service(FakeAdapter('{"questions": []}'))
    item = items.save(_item("X"))
    with pytest.raises(InvalidExperimentError):
        await service.create(ExperimentKind.QUIZ, [item.id])


async def test_create_compare_requires_two_items():
    items, _, _, service = _service(FakeAdapter(_COMPARE_JSON))
    item = items.save(_item("A"))
    with pytest.raises(InvalidExperimentError):
        await service.create(ExperimentKind.COMPARE, [item.id])


async def test_create_compare_persists():
    items, relations, _, service = _service(FakeAdapter(_COMPARE_JSON))
    a, b = items.save(_item("A")), items.save(_item("B"))
    relations.save_relation(
        KnowledgeRelation(source_id=b.id, target_id=a.id, relation_type=RelationType.REFINES)
    )
    session = await service.create(ExperimentKind.COMPARE, [a.id, b.id])
    assert session.payload["compare"]["relation_type"] == "refines"
    assert session.item_ids == [a.id, b.id]


async def test_create_compare_requires_model():
    items, _, _, service = _service(None)
    a, b = items.save(_item("A")), items.save(_item("B"))
    with pytest.raises(ModelRequiredError):
        await service.create(ExperimentKind.COMPARE, [a.id, b.id])


async def test_create_chain_deterministic_no_model():
    items, relations, _, service = _service(None)
    base = items.save(_item("基础概念"))
    mid = items.save(_item("进阶应用"))
    top = items.save(_item("综合实战"))
    relations.save_relation(
        KnowledgeRelation(
            source_id=mid.id, target_id=base.id, relation_type=RelationType.DEPENDS_ON
        )
    )
    relations.save_relation(
        KnowledgeRelation(source_id=top.id, target_id=mid.id, relation_type=RelationType.REFINES)
    )
    session = await service.create(ExperimentKind.CHAIN, [top.id], count=8)
    assert session.payload["steps"][0]["item_id"] == str(base.id)
    assert session.item_ids == [base.id, mid.id, top.id]


async def test_create_unknown_kind_invalid():
    _, _, _, service = _service(None)
    with pytest.raises(InvalidExperimentError):
        await service.create("bogus", [])


async def test_create_missing_item_not_found():
    _, _, _, service = _service(None)
    with pytest.raises(ExperimentNotFoundError):
        await service.create(ExperimentKind.CHAIN, [_item("ghost").id])


async def test_answer_grades_and_validates():
    items, _, _, service = _service(FakeAdapter(_QUIZ_JSON))
    item = items.save(_item("X"))
    session = await service.create(ExperimentKind.QUIZ, [item.id])
    assert service.answer(session, 0, 1).correct is True
    assert service.answer(session, 0, 0).correct is False
    with pytest.raises(InvalidExperimentError):
        service.answer(session, 99, 0)
    with pytest.raises(InvalidExperimentError):
        service.answer(session, 0, 99)


async def test_answer_non_quiz_invalid():
    items, _, _, service = _service(None)
    item = items.save(_item("X"))
    session = await service.create(ExperimentKind.CHAIN, [item.id])
    with pytest.raises(InvalidExperimentError):
        service.answer(session, 0, 0)


async def test_complete_quiz_scores_persists_and_reveals():
    items, _, experiments, service = _service(FakeAdapter(_QUIZ_JSON))
    item = items.save(_item("X"))
    session = await service.create(ExperimentKind.QUIZ, [item.id])
    attempt = service.complete(session, [{"index": 0, "value": 1}, {"index": 1, "value": 1}])
    assert attempt.total == 2
    assert attempt.correct_count == 1
    assert attempt.score == 0.5
    assert experiments.list_attempts(session.id) == [attempt]
    updated = experiments.get_session(session.id)
    assert updated.status == ExperimentStatus.COMPLETED
    view = service.public_view(updated)
    assert view["payload"]["questions"][0]["correct_index"] == 1
    assert "explanation" in view["payload"]["questions"][0]


async def test_complete_chain_marks_completed_no_score():
    items, _, experiments, service = _service(None)
    item = items.save(_item("X"))
    session = await service.create(ExperimentKind.CHAIN, [item.id])
    attempt = service.complete(session, [])
    assert attempt.total == 0
    assert attempt.score == 0.0
    assert experiments.get_session(session.id).status == ExperimentStatus.COMPLETED
