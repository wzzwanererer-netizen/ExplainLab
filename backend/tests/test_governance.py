"""M2 治理 API 测试：关系 / 版本 / 审核门禁 / 查重分析 / 合并闭环。"""

from __future__ import annotations

from fastapi.testclient import TestClient

_MISSING_UUID = "00000000-0000-0000-0000-000000000000"


def _create(client: TestClient, title: str = "知识", content: str = "内容") -> dict:
    resp = client.post("/api/knowledge", json={"title": title, "content": content})
    assert resp.status_code == 201
    return resp.json()


def _publish(client: TestClient, item_id: str) -> None:
    resp = client.patch(f"/api/knowledge/{item_id}", json={"status": "active"})
    assert resp.status_code == 200  # draft→active 发布不进审核


def test_relation_crud(client: TestClient):
    a = _create(client, "A")
    b = _create(client, "B")
    resp = client.post(
        f"/api/knowledge/{a['id']}/relations",
        json={"target_id": b["id"], "relation_type": "related"},
    )
    assert resp.status_code == 201
    rel = resp.json()
    assert rel["origin"] == "manual"
    assert rel["relation_type"] == "related"

    # 双向可见：source 与 target 都能列出该关系
    assert len(client.get(f"/api/knowledge/{a['id']}/relations").json()) == 1
    assert len(client.get(f"/api/knowledge/{b['id']}/relations").json()) == 1

    # 重复三元组 409；自环 400；目标不存在 404
    dup = client.post(
        f"/api/knowledge/{a['id']}/relations",
        json={"target_id": b["id"], "relation_type": "related"},
    )
    assert dup.status_code == 409
    self_rel = client.post(
        f"/api/knowledge/{a['id']}/relations",
        json={"target_id": a["id"], "relation_type": "related"},
    )
    assert self_rel.status_code == 400
    missing = client.post(
        f"/api/knowledge/{a['id']}/relations",
        json={"target_id": _MISSING_UUID, "relation_type": "related"},
    )
    assert missing.status_code == 404

    assert client.delete(f"/api/relations/{rel['id']}").status_code == 204
    assert client.get(f"/api/knowledge/{a['id']}/relations").json() == []
    assert client.delete(f"/api/relations/{rel['id']}").status_code == 404


def test_active_update_gated_then_approve(client: TestClient):
    item = _create(client, "原标题", "原内容")
    _publish(client, item["id"])

    resp = client.patch(f"/api/knowledge/{item['id']}", json={"title": "新标题"})
    assert resp.status_code == 202
    review = resp.json()
    assert review["status"] == "pending"
    assert review["action"] == "update_item"
    assert review["payload"]["title"] == "新标题"

    # 未批准前不应用
    assert client.get(f"/api/knowledge/{item['id']}").json()["title"] == "原标题"
    pending = client.get("/api/reviews?status=pending").json()
    assert [r["id"] for r in pending] == [review["id"]]

    approved = client.post(f"/api/reviews/{review['id']}/approve", json={"note": "同意"})
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["resolution_note"] == "同意"
    assert client.get(f"/api/knowledge/{item['id']}").json()["title"] == "新标题"

    # 批准时建立「编辑前快照」（发布草稿时也有一条快照，共 2 条）
    versions = client.get(f"/api/knowledge/{item['id']}/versions").json()
    assert len(versions) == 2
    assert versions[-1]["title"] == "原标题"
    assert versions[-1]["change_summary"] == "编辑前快照"

    # 已处理的审核单不能重复批准
    assert client.post(f"/api/reviews/{review['id']}/approve").status_code == 409


def test_active_update_reject_no_side_effect(client: TestClient):
    item = _create(client, "原标题", "原内容")
    _publish(client, item["id"])
    review = client.patch(
        f"/api/knowledge/{item['id']}", json={"content": "改后"}
    ).json()
    assert client.get(f"/api/knowledge/{item['id']}").json()["content"] == "原内容"

    rejected = client.post(f"/api/reviews/{review['id']}/reject", json={"note": "不妥"})
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert client.get(f"/api/knowledge/{item['id']}").json()["content"] == "原内容"
    # 驳回不产生编辑快照（仅发布草稿时的那一条）
    versions = client.get(f"/api/knowledge/{item['id']}/versions").json()
    assert len(versions) == 1
    assert versions[0]["change_summary"] == "编辑前快照"


def test_draft_update_direct(client: TestClient):
    item = _create(client)
    resp = client.patch(f"/api/knowledge/{item['id']}", json={"title": "改"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "改"
    assert client.get("/api/reviews").json() == []


def test_active_delete_gated_then_approve(client: TestClient):
    item = _create(client)
    _publish(client, item["id"])
    resp = client.delete(f"/api/knowledge/{item['id']}")
    assert resp.status_code == 202
    assert resp.json()["action"] == "delete_item"
    assert client.get(f"/api/knowledge/{item['id']}").status_code == 200

    assert (
        client.post(f"/api/reviews/{resp.json()['id']}/approve").status_code == 200
    )
    assert client.get(f"/api/knowledge/{item['id']}").status_code == 404


def test_restore_draft_direct_and_active_gated(client: TestClient):
    item = _create(client, "标题", "v1")
    client.patch(f"/api/knowledge/{item['id']}", json={"content": "v2"})
    versions = client.get(f"/api/knowledge/{item['id']}/versions").json()
    assert [v["content"] for v in versions] == ["v1"]

    # 草稿回滚直接应用，且先快照回滚前状态（历史线性）
    resp = client.post(f"/api/knowledge/{item['id']}/versions/1/restore")
    assert resp.status_code == 200
    assert resp.json()["content"] == "v1"
    versions = client.get(f"/api/knowledge/{item['id']}/versions").json()
    assert [v["content"] for v in versions] == ["v1", "v2"]

    # active 回滚进审核
    _publish(client, item["id"])
    edit = client.patch(f"/api/knowledge/{item['id']}", json={"content": "v3"})
    assert edit.status_code == 202
    assert client.post(f"/api/reviews/{edit.json()['id']}/approve").status_code == 200
    gated = client.post(f"/api/knowledge/{item['id']}/versions/1/restore")
    assert gated.status_code == 202
    assert gated.json()["action"] == "restore_version"
    assert client.get(f"/api/knowledge/{item['id']}").json()["content"] == "v3"
    assert client.post(f"/api/reviews/{gated.json()['id']}/approve").status_code == 200
    assert client.get(f"/api/knowledge/{item['id']}").json()["content"] == "v1"

    assert (
        client.post(f"/api/knowledge/{item['id']}/versions/99/restore").status_code
        == 404
    )


def test_submit_review_direct_and_gated(client: TestClient):
    item = _create(client)
    direct = client.post(
        "/api/reviews",
        json={
            "item_id": item["id"],
            "action": "update_item",
            "payload": {"title": "直接改"},
        },
    )
    assert direct.status_code == 200
    assert direct.json() == {"applied": True, "review": None}
    assert client.get(f"/api/knowledge/{item['id']}").json()["title"] == "直接改"

    _publish(client, item["id"])
    gated = client.post(
        "/api/reviews",
        json={
            "item_id": item["id"],
            "action": "update_item",
            "payload": {"title": "审核改"},
            "reason": "重要变更",
        },
    )
    assert gated.status_code == 201
    body = gated.json()
    assert body["applied"] is False
    assert body["review"]["status"] == "pending"
    assert body["review"]["reason"] == "重要变更"

    assert client.post(
        "/api/reviews",
        json={"item_id": _MISSING_UUID, "action": "delete_item"},
    ).status_code == 404


def test_merge_review_loop(client: TestClient):
    source = _create(client, "重复条目", "同一知识")
    target = _create(client, "保留条目", "同一知识")
    client.post(
        f"/api/knowledge/{source['id']}/sources",
        json={"source_type": "document", "uri": "https://example.com/doc"},
    )

    resp = client.post(
        "/api/reviews",
        json={
            "item_id": source["id"],
            "action": "merge_duplicate",
            "payload": {"target_id": target["id"]},
        },
    )
    assert resp.status_code == 201  # 合并任何状态都进审核
    review_id = resp.json()["review"]["id"]
    # 未批准前双方不变
    assert client.get(f"/api/knowledge/{source['id']}").json()["status"] == "draft"

    assert client.post(f"/api/reviews/{review_id}/approve").status_code == 200
    merged_source = client.get(f"/api/knowledge/{source['id']}").json()
    assert merged_source["status"] == "archived"  # 归档而非硬删

    relations = client.get(f"/api/knowledge/{source['id']}/relations").json()
    assert any(
        r["relation_type"] == "duplicate_of"
        and r["target_id"] == target["id"]
        and r["origin"] == "dedup"
        for r in relations
    )
    # 源来源并入目标（目标原有 manual + 并入的 manual/document）
    target_refs = client.get(f"/api/knowledge/{target['id']}").json()["source_refs"]
    assert any(r["uri"] == "https://example.com/doc" for r in target_refs)
    assert len(target_refs) == 3

    # 合并前快照保留
    versions = client.get(f"/api/knowledge/{source['id']}/versions").json()
    assert versions[0]["change_summary"] == "合并前快照"

    # 参数校验：缺 target_id 400；目标不存在 404
    assert client.post(
        "/api/reviews",
        json={
            "item_id": source["id"],
            "action": "merge_duplicate",
            "payload": {},
        },
    ).status_code == 400
    assert client.post(
        "/api/reviews",
        json={
            "item_id": source["id"],
            "action": "merge_duplicate",
            "payload": {"target_id": _MISSING_UUID},
        },
    ).status_code == 404


def test_attach_source_and_trace(client: TestClient):
    item = _create(client)
    resp = client.post(
        f"/api/knowledge/{item['id']}/sources",
        json={
            "source_type": "document",
            "uri": "https://example.com",
            "excerpt": "原文摘录",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["source_type"] == "document"
    refs = client.get(f"/api/knowledge/{item['id']}").json()["source_refs"]
    assert any(r["uri"] == "https://example.com" and r["excerpt"] == "原文摘录" for r in refs)
    assert (
        client.post(
            f"/api/knowledge/{_MISSING_UUID}/sources",
            json={"source_type": "manual"},
        ).status_code
        == 404
    )


def test_duplicates_without_model_config_returns_503(client: TestClient):
    item = _create(client)
    assert client.get(f"/api/knowledge/{item['id']}/duplicates").status_code == 503
    assert client.post(f"/api/knowledge/{item['id']}/analyze").status_code == 503


def test_duplicates_and_analyze_with_stub(model_client: TestClient, stub_adapter):
    stub_adapter.content = (
        '{"duplicates": [{"index": 0, "same": true, "confidence": 0.9}],'
        ' "relations": [{"index": 0, "type": "related", "confidence": 0.8}]}'
    )
    text = "Python 的 GIL 是全局解释器锁，它限制同一时刻只有一个线程执行字节码。"
    a = _create(model_client, "Python GIL", text)
    b = _create(model_client, "Python GIL 全局解释器锁", text)

    dups = model_client.get(f"/api/knowledge/{a['id']}/duplicates")
    assert dups.status_code == 200
    assert dups.json()[0]["item_id"] == b["id"]
    assert dups.json()[0]["title"] == b["title"]

    analyzed = model_client.post(f"/api/knowledge/{a['id']}/analyze")
    assert analyzed.status_code == 200
    body = analyzed.json()
    assert body["duplicates"][0]["item_id"] == b["id"]
    assert body["relations"][0]["relation_type"] == "related"
    assert body["relations"][0]["origin"] == "llm"

    # 关系已落库；重复分析不产生重复关系
    assert len(model_client.get(f"/api/knowledge/{a['id']}/relations").json()) == 1
    model_client.post(f"/api/knowledge/{a['id']}/analyze")
    assert len(model_client.get(f"/api/knowledge/{a['id']}/relations").json()) == 1


def test_analyze_malformed_model_output_returns_empty(
    model_client: TestClient, stub_adapter
):
    stub_adapter.content = "这不是 JSON"
    a = _create(model_client, "Python GIL", "全局解释器锁限制线程并行执行字节码。")
    _create(model_client, "Python GIL 锁", "全局解释器锁限制线程并行执行字节码。")
    resp = model_client.post(f"/api/knowledge/{a['id']}/analyze")
    assert resp.status_code == 200
    assert resp.json() == {"duplicates": [], "relations": []}


def test_delete_item_cascades_governance_rows(client: TestClient):
    """删除条目须级联清理关系 / 版本 / 审核（SQLite 外键 CASCADE），不留孤儿。"""
    a = _create(client, "A", "a")
    b = _create(client, "B", "b")
    client.post(
        f"/api/knowledge/{a['id']}/relations",
        json={"target_id": b["id"], "relation_type": "related"},
    )
    client.patch(f"/api/knowledge/{a['id']}", json={"content": "a2"})  # 草稿编辑建版本
    _publish(client, a["id"])
    edit = client.patch(f"/api/knowledge/{a['id']}", json={"title": "A3"})
    assert edit.status_code == 202  # 留下一个待审核单

    assert len(client.get(f"/api/knowledge/{b['id']}/relations").json()) == 1
    assert len(client.get(f"/api/knowledge/{a['id']}/versions").json()) >= 1

    deleted = client.delete(f"/api/knowledge/{a['id']}")
    assert deleted.status_code == 202
    # 批准删除：级联删审核单自身不应导致失败
    assert client.post(f"/api/reviews/{deleted.json()['id']}/approve").status_code == 200
    assert client.get(f"/api/knowledge/{a['id']}").status_code == 404

    # 关系随源条目级联清理；引用该条目的审核单亦不残留
    assert client.get(f"/api/knowledge/{b['id']}/relations").json() == []
    rv = client.get("/api/reviews")
    assert rv.status_code == 200, rv.text
    assert all(r["item_id"] != a["id"] for r in rv.json())