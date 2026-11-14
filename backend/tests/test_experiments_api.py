"""M5-T4 实验 API 测试：创建/判分/完成/列表/删除 + 503/502/400/404。

quiz/compare 经 get_model_adapter_optional 注入 StubAdapter（不发真实请求）；
chain 确定性，无需模型；未配置模型时 quiz/compare 如实 503。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_model_adapter_optional

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


@pytest.fixture
def exp_client(client: TestClient, stub_adapter):
    """注入可选模型适配器的客户端；返回 (client, adapter) 以便逐测试设置内容/故障。"""
    client.app.dependency_overrides[get_model_adapter_optional] = lambda: stub_adapter
    return client, stub_adapter


def _create(client: TestClient, title: str, **kw) -> dict:
    resp = client.post("/api/knowledge", json={"title": title, "content": f"{title} 内容", **kw})
    assert resp.status_code == 201
    return resp.json()


def _relate(client: TestClient, source: str, target: str, relation_type: str) -> None:
    resp = client.post(
        f"/api/knowledge/{source}/relations",
        json={"target_id": target, "relation_type": relation_type},
    )
    assert resp.status_code == 201


def _create_quiz(client: TestClient) -> tuple[dict, dict]:
    item = _create(client, "知识图谱")
    resp = client.post(
        "/api/experiments/sessions",
        json={"kind": "quiz", "item_ids": [item["id"]], "count": 5},
    )
    assert resp.status_code == 201
    return item, resp.json()


def test_create_quiz_hides_answers(exp_client):
    client, adapter = exp_client
    adapter.content = _QUIZ_JSON
    item, session = _create_quiz(client)
    assert session["kind"] == "quiz"
    assert session["status"] == "active"
    assert session["item_ids"] == [item["id"]]
    questions = session["payload"]["questions"]
    assert len(questions) == 2
    assert "correct_index" not in questions[0]
    assert "explanation" not in questions[0]
    assert questions[0]["options"] == ["A", "B", "C", "D"]


def test_quiz_requires_model_503(client: TestClient):
    item = _create(client, "X")
    resp = client.post(
        "/api/experiments/sessions", json={"kind": "quiz", "item_ids": [item["id"]]}
    )
    assert resp.status_code == 503


def test_quiz_model_failure_502(exp_client):
    client, adapter = exp_client
    adapter.content = _QUIZ_JSON
    adapter.fail = True
    item = _create(client, "X")
    resp = client.post(
        "/api/experiments/sessions", json={"kind": "quiz", "item_ids": [item["id"]]}
    )
    assert resp.status_code == 502


def test_quiz_empty_model_400(exp_client):
    client, adapter = exp_client
    adapter.content = '{"questions": []}'
    item = _create(client, "X")
    resp = client.post(
        "/api/experiments/sessions", json={"kind": "quiz", "item_ids": [item["id"]]}
    )
    assert resp.status_code == 400


def test_create_compare(exp_client):
    client, adapter = exp_client
    adapter.content = _COMPARE_JSON
    a, b = _create(client, "A"), _create(client, "B")
    resp = client.post(
        "/api/experiments/sessions", json={"kind": "compare", "item_ids": [a["id"], b["id"]]}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["kind"] == "compare"
    assert body["payload"]["compare"]["relation_type"] == "refines"
    assert body["payload"]["compare"]["similarities"] == ["都涉及知识"]


def test_compare_wrong_count_400(exp_client):
    client, adapter = exp_client
    adapter.content = _COMPARE_JSON
    a = _create(client, "A")
    resp = client.post(
        "/api/experiments/sessions", json={"kind": "compare", "item_ids": [a["id"]]}
    )
    assert resp.status_code == 400


def test_compare_requires_model_503(client: TestClient):
    a, b = _create(client, "A"), _create(client, "B")
    resp = client.post(
        "/api/experiments/sessions", json={"kind": "compare", "item_ids": [a["id"], b["id"]]}
    )
    assert resp.status_code == 503


def test_create_chain_no_model(client: TestClient):
    base, mid, top = _create(client, "基础"), _create(client, "进阶"), _create(client, "实战")
    _relate(client, mid["id"], base["id"], "depends_on")
    _relate(client, top["id"], mid["id"], "refines")
    resp = client.post(
        "/api/experiments/sessions", json={"kind": "chain", "item_ids": [top["id"]], "count": 8}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["kind"] == "chain"
    assert body["item_ids"] == [base["id"], mid["id"], top["id"]]
    steps = body["payload"]["steps"]
    assert steps[0]["relation_from_prev"] is None
    assert steps[1]["relation_from_prev"] == "depends_on"
    assert steps[2]["relation_from_prev"] == "refines"


def test_create_unknown_kind_422(client: TestClient):
    resp = client.post(
        "/api/experiments/sessions", json={"kind": "bogus", "item_ids": [str(uuid4())]}
    )
    assert resp.status_code == 422


def test_create_missing_item_404(client: TestClient):
    resp = client.post(
        "/api/experiments/sessions", json={"kind": "chain", "item_ids": [str(uuid4())]}
    )
    assert resp.status_code == 404


def test_create_unknown_space_404(exp_client):
    client, adapter = exp_client
    adapter.content = _QUIZ_JSON
    item = _create(client, "X")
    resp = client.post(
        "/api/experiments/sessions",
        json={"kind": "quiz", "item_ids": [item["id"]], "space_id": "no-such-space"},
    )
    assert resp.status_code == 404


def test_answer_grades_and_validates(exp_client):
    client, adapter = exp_client
    adapter.content = _QUIZ_JSON
    _, session = _create_quiz(client)
    sid = session["id"]
    ok = client.post(f"/api/experiments/sessions/{sid}/answer", json={"index": 0, "value": 1})
    assert ok.status_code == 200
    assert ok.json()["correct"] is True
    assert ok.json()["correct_value"] == 1
    bad = client.post(f"/api/experiments/sessions/{sid}/answer", json={"index": 0, "value": 0})
    assert bad.json()["correct"] is False
    assert bad.json()["explanation"] == "因为B"
    oob = client.post(f"/api/experiments/sessions/{sid}/answer", json={"index": 99, "value": 0})
    assert oob.status_code == 400


def test_answer_non_quiz_400(client: TestClient):
    item = _create(client, "X")
    session = client.post(
        "/api/experiments/sessions", json={"kind": "chain", "item_ids": [item["id"]]}
    ).json()
    resp = client.post(
        f"/api/experiments/sessions/{session['id']}/answer", json={"index": 0, "value": 0}
    )
    assert resp.status_code == 400


def test_complete_scores_and_reveals(exp_client):
    client, adapter = exp_client
    adapter.content = _QUIZ_JSON
    _, session = _create_quiz(client)
    sid = session["id"]
    resp = client.post(
        f"/api/experiments/sessions/{sid}/complete",
        json={"answers": [{"index": 0, "value": 1}, {"index": 1, "value": 1}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["attempt"]["total"] == 2
    assert body["attempt"]["correct_count"] == 1
    assert body["attempt"]["score"] == 0.5
    assert body["session"]["status"] == "completed"
    assert body["session"]["payload"]["questions"][0]["correct_index"] == 1
    assert "explanation" in body["session"]["payload"]["questions"][0]


def test_list_and_filter(exp_client):
    client, adapter = exp_client
    adapter.content = _QUIZ_JSON
    _create_quiz(client)
    item = _create(client, "路径")
    client.post("/api/experiments/sessions", json={"kind": "chain", "item_ids": [item["id"]]})
    assert len(client.get("/api/experiments/sessions").json()) == 2
    assert len(client.get("/api/experiments/sessions", params={"kind": "quiz"}).json()) == 1
    assert len(client.get("/api/experiments/sessions", params={"kind": "chain"}).json()) == 1


def test_get_one_and_delete(exp_client):
    client, adapter = exp_client
    adapter.content = _QUIZ_JSON
    _, session = _create_quiz(client)
    sid = session["id"]
    assert client.get(f"/api/experiments/sessions/{sid}").status_code == 200
    assert client.delete(f"/api/experiments/sessions/{sid}").status_code == 204
    assert client.get(f"/api/experiments/sessions/{sid}").status_code == 404
    assert client.delete(f"/api/experiments/sessions/{sid}").status_code == 404


def test_get_missing_404(client: TestClient):
    assert client.get(f"/api/experiments/sessions/{uuid4()}").status_code == 404