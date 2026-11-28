"""交互式动态原理沙盒服务单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.sandbox import (
    delete_sandbox,
    extract_and_sanitize_html,
    generate_sandbox,
    get_sandbox,
)
from knowledge_core.model_adapter import (
    ModelAdapter,
    ModelCapability,
    ModelRequest,
    ModelResponse,
)


class _StubAdapter(ModelAdapter):
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
            content=(
                "以下是交互代码：\n```html\n<!doctype html><html><head></head><body>"
                "<script src='https://evil.example/a.js'></script>"
                "<svg viewBox='0 0 720 260'><text x='20' y='40'>TCP 三次握手沙盒</text></svg>"
                "<script>console.log('ok');</script></body></html>\n```"
            ),
            model="stub",
            provider="stub",
        )


class _RetryAdapter(_StubAdapter):
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        if self.calls == 1:
            return ModelResponse(
                content="<!doctype html><html><body><svg></svg><script>const broken = '",
                model="stub",
                provider="stub",
            )
        return await super().generate(request)


def test_extract_and_sanitize_strips_external_scripts() -> None:
    raw = (
        "```html\n<!doctype html><html><head>"
        "<link rel='stylesheet' href='https://cdn.example/x.css'>"
        "</head><body><script src='https://cdn.example/a.js'></script>"
        "<svg viewBox='0 0 100 40'></svg><button>SYN</button></body></html>\n```"
    )
    cleaned = extract_and_sanitize_html(raw)
    assert cleaned.lower().startswith("<!doctype html>")
    assert "cdn.example" not in cleaned
    assert "<button>SYN</button>" in cleaned
    assert "沙盒脚本运行异常" in cleaned


def test_extract_and_sanitize_rejects_truncated_script() -> None:
    truncated = "<!doctype html><html><body><svg></svg><script>const x = 'unclosed"
    with pytest.raises(ValueError, match="截断"):
        extract_and_sanitize_html(truncated)


def test_extract_and_sanitize_rejects_missing_visual_canvas() -> None:
    no_visual = "<!doctype html><html><body><div>纯文字无图</div></body></html>"
    with pytest.raises(ValueError, match="可视化画布"):
        extract_and_sanitize_html(no_visual)


@pytest.mark.asyncio
async def test_generate_sandbox_retries_once_on_truncation(tmp_path: Path) -> None:
    adapter = _RetryAdapter()
    rec = await generate_sandbox(
        adapter,
        data_dir=tmp_path,
        item_id="k-retry-01",
        title="TCP 三次握手",
        content="SYN -> SYN-ACK -> ACK",
    )
    assert adapter.calls == 2
    assert rec.exists is True
    assert rec.html is not None and "TCP 三次握手沙盒" in rec.html


@pytest.mark.asyncio
async def test_sandbox_generate_get_delete_lifecycle(tmp_path: Path) -> None:
    item_id = "k-12345678"
    empty = get_sandbox(tmp_path, item_id)
    assert empty.exists is False
    assert empty.html is None

    created = await generate_sandbox(
        _StubAdapter(),
        data_dir=tmp_path,
        item_id=item_id,
        title="TCP 三次握手",
        content="SYN -> SYN-ACK -> ACK",
        instruction="加入丢包模拟按钮",
    )
    assert created.exists is True
    assert created.html is not None
    assert "TCP 三次握手沙盒" in created.html
    assert "evil.example" not in created.html

    loaded = get_sandbox(tmp_path, item_id)
    assert loaded.exists is True
    assert loaded.html == created.html

    assert delete_sandbox(tmp_path, item_id) is True
    assert get_sandbox(tmp_path, item_id).exists is False
