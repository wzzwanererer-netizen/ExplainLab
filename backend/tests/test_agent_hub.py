"""Agent 副库管理中心与本地会话吸尘器单元测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.services.agent_hub import (
    add_or_connect_agent,
    discover_agents,
    extract_dialogue_from_session_file,
    ingest_session_images,
    list_agent_sessions,
    resolve_vacuum_media_path,
    sanitize_sensitive_text,
    vacuum_agent_sessions,
)
from knowledge_core.model_adapter import (
    ModelAdapter,
    ModelCapability,
    ModelRequest,
    ModelResponse,
)


class _StubVacuumAdapter(ModelAdapter):
    @property
    def provider(self) -> str:
        return "stub"

    @property
    def default_model(self) -> str:
        return "stub-model"

    def capabilities(self) -> set[ModelCapability]:
        return {ModelCapability.GENERATE}

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        return []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            content=json.dumps(
                {
                    "items": [
                        {
                            "title": "华为云校园网络安全项目架构",
                            "content": "## 核心方案\n- 零信任边界防护与日志审计\n#华为云 #网络安全",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            model="stub",
            provider="stub",
        )


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_sanitize_sensitive_text_redacts_secrets() -> None:
    raw = "请使用 sk-1234567890abcdefghij 和 api_key=my_secret_value_999 以及 Bearer eyJhbGciOiJIUzI1NiJ9.aaa"
    cleaned = sanitize_sensitive_text(raw)
    assert "sk-1234567890" not in cleaned
    assert "my_secret_value_999" not in cleaned
    assert "eyJhbGciOiJIUzI1NiJ9" not in cleaned
    assert "[REDACTED" in cleaned


def test_extract_dialogue_from_jsonl(tmp_path: Path) -> None:
    f = tmp_path / "chat.jsonl"
    f.write_text(
        "\n".join(
            [
                json.dumps({"role": "user", "content": "咱们设计一下华为云校园网络安全项目架构"}),
                json.dumps({"role": "assistant", "content": "建议采用分区分域隔离与实时告警审计。"}),
            ]
        ),
        encoding="utf-8",
    )
    dialogue = extract_dialogue_from_session_file(f)
    assert "[用户]" in dialogue
    assert "[助手]" in dialogue
    assert "华为云校园网络安全" in dialogue


@pytest.mark.asyncio
async def test_add_agent_and_vacuum_deduplicates_cursor(tmp_path: Path) -> None:
    db = _make_session()
    sessions_dir = tmp_path / "mock_agent_sessions"
    sessions_dir.mkdir()
    chat_file = sessions_dir / "session-001.jsonl"
    chat_file.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "role": "user",
                        "content": "我们在做华为云校园网络安全项目，重点解决宿舍网与实验室流量异常检测与告警联动问题。",
                    }
                ),
                json.dumps(
                    {
                        "role": "assistant",
                        "content": "可以采用华为云态势感知 + 本地探针 + 自动化隔离策略，形成检测-研判-处置闭环。",
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    added = add_or_connect_agent(
        db,
        tmp_path,
        name="MyPetAgent",
        session_dir=str(sessions_dir),
        write_rule=False,
    )
    assert added.connected is True
    assert added.space_name == "Agent · MyPetAgent"
    assert added.space_id is not None
    assert added.unprocessed_count == 1

    # 第一次吸尘：提炼并写入 1 条知识
    report1 = await vacuum_agent_sessions(
        db,
        _StubVacuumAdapter(),
        data_dir=tmp_path,
        agent_name="MyPetAgent",
    )
    assert report1.scanned_sessions == 1
    assert len(report1.created_items) == 1
    assert report1.created_items[0].title == "华为云校园网络安全项目架构"

    # 第二次吸尘：游标已记录，不再重复扫描
    report2 = await vacuum_agent_sessions(
        db,
        _StubVacuumAdapter(),
        data_dir=tmp_path,
        agent_name="MyPetAgent",
    )
    assert report2.scanned_sessions == 0
    assert len(report2.created_items) == 0

    all_agents = discover_agents(db, tmp_path)
    mine = next(a for a in all_agents if a.name == "MyPetAgent")
    assert mine.item_count == 1
    assert mine.unprocessed_count == 0

    # 自定义吸尘列表：可见所有条目并支持精确勾选
    previews = list_agent_sessions(db, tmp_path, "MyPetAgent")
    assert len(previews) == 1
    assert previews[0].processed is True
    assert "华为云校园网络安全" in previews[0].preview

    # 即使已处理过，自定义勾选也可重新扫描
    report3 = await vacuum_agent_sessions(
        db,
        _StubVacuumAdapter(),
        data_dir=tmp_path,
        agent_name="MyPetAgent",
        session_files=[previews[0].file_path],
    )
    assert report3.scanned_sessions == 1
    db.close()


def test_extract_dialogue_from_antigravity_transcript(tmp_path: Path) -> None:
    f = tmp_path / "transcript.jsonl"
    f.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "USER_INPUT",
                        "content": "<USER_REQUEST>\n我们规划一下 Nesti 3D 桌宠长期记忆架构\n</USER_REQUEST>",
                    }
                ),
                json.dumps(
                    {
                        "type": "PLANNER_RESPONSE",
                        "response": "建议采用 ExplainLab 作为长期海马体并通过 MCP 协议连接。",
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    dialogue = extract_dialogue_from_session_file(f)
    assert "[用户] 我们规划一下 Nesti 3D 桌宠长期记忆架构" in dialogue
    assert "[助手] 建议采用 ExplainLab" in dialogue


def test_ingest_session_images_discovers_and_serves_safely(tmp_path: Path) -> None:
    conv = tmp_path / "conv-123"
    logs = conv / ".system_generated" / "logs"
    logs.mkdir(parents=True)
    transcript = logs / "transcript.jsonl"
    transcript.write_text("{}\n", encoding="utf-8")
    img = conv / "phoebe_turnaround.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"0" * 2048)

    data_dir = tmp_path / "data"
    ingested = ingest_session_images(transcript, "", data_dir)
    assert len(ingested) == 1
    stem, url, stored_path = ingested[0]
    assert stem == "phoebe_turnaround"
    assert url.startswith("/api/agents/media/")
    assert stored_path.is_file()
    fname = url.split("/")[-1]
    assert resolve_vacuum_media_path(data_dir, fname) is not None
    assert resolve_vacuum_media_path(data_dir, "../secret.jpg") is None


def test_detect_completed_agent_tasks_and_dismiss(tmp_path: Path) -> None:
    import os
    import time

    from app.services.agent_hub import (
        detect_completed_agent_tasks,
        dismiss_task_suggestion,
    )

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    sdir = tmp_path / "sessions"
    sdir.mkdir()
    add_or_connect_agent(
        db,
        tmp_path,
        name="PopAgent",
        session_dir=str(sdir),
        write_rule=False,
    )

    # 1. Cold start sets baseline_ts and does not flood old sessions
    assert detect_completed_agent_tasks(db, tmp_path, idle_seconds=1.0) == []

    # 2. Simulate a session written after baseline and settled for 30s
    f = sdir / "task_done.jsonl"
    f.write_text(
        json.dumps({"role": "user", "content": "帮我完成任务弹窗功能设计"}) + "\n"
        + json.dumps({"role": "assistant", "content": "已完成并验证通过。" * 40}) + "\n",
        encoding="utf-8",
    )
    now = time.time()
    # Set baseline 60s earlier and file mtime 20s ago so it qualifies as settled
    state_file = tmp_path / "agent_notify_state.json"
    state_file.write_text(json.dumps({"baseline_ts": now - 60.0}), encoding="utf-8")
    os.utime(f, (now - 20.0, now - 20.0))

    found = detect_completed_agent_tasks(db, tmp_path, idle_seconds=5.0)
    assert len(found) == 1
    assert found[0].agent_name == "PopAgent"
    assert "任务弹窗" in found[0].label
    assert "已完成并验证通过" in found[0].preview

    # 3. Polling again for same snapshot returns empty (never repeats), and even small appends during cooldown don't re-trigger
    assert detect_completed_agent_tasks(db, tmp_path, idle_seconds=5.0) == []
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"role": "user", "content": "好的"}) + "\n")
    os.utime(f, (now - 10.0, now - 10.0))
    assert detect_completed_agent_tasks(db, tmp_path, idle_seconds=5.0, cooldown_seconds=600.0) == []

    # 4. include_latest=True returns the latest session for 1-click popup testing
    latest = detect_completed_agent_tasks(db, tmp_path, include_latest=True)
    assert len(latest) == 1

    # 5. Explicit dismiss works cleanly
    dismiss_task_suggestion(tmp_path, file_path=latest[0].file_path, signature=latest[0].signature)
    assert detect_completed_agent_tasks(db, tmp_path, idle_seconds=5.0) == []
    db.close()


def test_handoff_list_and_read_readonly_with_path_guard(tmp_path: Path) -> None:
    from sqlalchemy import select

    from app.models import KnowledgeItemORM
    from app.services.agent_hub import list_handoff_sessions, read_handoff_session

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    sdir = tmp_path / "codex_like"
    sdir.mkdir()
    add_or_connect_agent(
        db,
        tmp_path,
        name="HandoffCodex",
        session_dir=str(sdir),
        write_rule=False,
    )

    conv = sdir / "session_alpha.jsonl"
    conv.write_text(
        json.dumps({"role": "user", "content": "我们来设计一个跨 Agent 无缝接力架构，密钥 sk-1234567890abcdef123456"})
        + "\n"
        + json.dumps({"role": "assistant", "content": "好的，我们可以只读暴露两个 MCP 工具，绝不污染知识库。"})
        + "\n",
        encoding="utf-8",
    )

    found = list_handoff_sessions(db, tmp_path, agent_name="HandoffCodex", keyword="无缝接力")
    assert len(found) == 1
    assert found[0].agent_name == "HandoffCodex"

    content = read_handoff_session(db, tmp_path, file_path=found[0].file_path, max_chars=4000)
    assert "跨 Agent 无缝接力架构" in content.dialogue
    assert "sk-1234567890abcdef123456" not in content.dialogue
    # Strictly zero writes to knowledge base!
    assert db.scalars(select(KnowledgeItemORM)).all() == []

    # Security guard: reject arbitrary file outside known session dirs
    outside = tmp_path / "secret.env"
    outside.write_text("SECRET=123", encoding="utf-8")
    with pytest.raises(PermissionError):
        read_handoff_session(db, tmp_path, file_path=str(outside))

    db.close()
