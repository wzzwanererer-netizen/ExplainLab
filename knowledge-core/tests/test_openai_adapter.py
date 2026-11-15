"""OpenAI 兼容适配器测试：使用 httpx.MockTransport，不发真实网络请求。

断言请求发往调用方给定的 base_url（原样，不替换代理），并校验请求/响应处理。
"""

from __future__ import annotations

import json

import httpx
import pytest

from knowledge_core.model_adapter import (
    AuthenticationError,
    MalformedResponseError,
    ModelAdapterError,
    ModelCapability,
    ModelMessage,
    ModelRequest,
    ModelTimeoutError,
    OpenAICompatibleAdapter,
    ProviderUnavailableError,
    RateLimitError,
    is_retryable,
)

BASE_URL = "https://api.example.com/v1"


def make_adapter(handler, **kwargs) -> OpenAICompatibleAdapter:
    return OpenAICompatibleAdapter(
        base_url=BASE_URL,
        api_key="test-key",
        default_model="test-model",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def user_request() -> ModelRequest:
    return ModelRequest(messages=[ModelMessage(role="user", content="hi")])


async def test_generate_success_and_request_shape():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "你好"}}],
                "model": "test-model",
                "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            },
        )

    adapter = make_adapter(handler)
    resp = await adapter.generate(user_request())

    assert resp.content == "你好"
    assert resp.provider == "openai-compatible"
    assert resp.usage is not None and resp.usage.total_tokens == 3
    # base_url 原样使用，路径正确拼接，无任何代理替换
    assert seen["url"] == f"{BASE_URL}/chat/completions"
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"]["model"] == "test-model"
    assert seen["body"]["messages"] == [{"role": "user", "content": "hi"}]


async def test_generate_respects_model_override_and_max_tokens():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    adapter = make_adapter(handler)
    await adapter.generate(
        ModelRequest(
            messages=[ModelMessage(role="user", content="x")],
            model="custom-model",
            max_tokens=128,
        )
    )
    assert seen["body"]["model"] == "custom-model"
    assert seen["body"]["max_tokens"] == 128


async def test_generate_http_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    adapter = make_adapter(handler)
    with pytest.raises(ModelAdapterError, match="401"):
        await adapter.generate(user_request())


async def test_generate_malformed_response_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    adapter = make_adapter(handler)
    with pytest.raises(ModelAdapterError, match="结构异常"):
        await adapter.generate(user_request())


async def test_embed_sorts_by_index():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["input"] == ["a", "b"]
        assert str(request.url) == f"{BASE_URL}/embeddings"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.2]},
                    {"index": 0, "embedding": [0.1]},
                ]
            },
        )

    adapter = make_adapter(handler)
    vectors = await adapter.embed(["a", "b"])
    assert vectors == [[0.1], [0.2]]


async def test_embed_empty_returns_empty():
    adapter = make_adapter(lambda request: httpx.Response(200, json={"data": []}))
    assert await adapter.embed([]) == []


async def test_embed_uses_embed_model():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.0]}]})

    adapter = make_adapter(handler, embed_model="embed-model")
    await adapter.embed(["x"])
    assert seen["body"]["model"] == "embed-model"


async def test_client_ignores_env_proxy_and_ipv6_no_proxy(monkeypatch):
    # 回归 httpx 0.28 缺陷：trust_env=True 时解析 NO_PROXY 中的 IPv6 项（[::1]）会崩溃。
    # 适配器须 trust_env=False：直连调用方真实 base_url，不读取/使用任何环境代理。
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1,[::1],::1")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:8080")
    adapter = OpenAICompatibleAdapter(
        base_url=BASE_URL, api_key="test-key", default_model="test-model"
    )
    async with adapter._client() as client:
        assert client.trust_env is False


class _RaisingTransport(httpx.AsyncBaseTransport):
    """在传输层精确抛出指定异常，模拟真实网络故障（不发真实请求）。"""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        raise self._exc


def _adapter_with_transport(transport: httpx.AsyncBaseTransport) -> OpenAICompatibleAdapter:
    return OpenAICompatibleAdapter(
        base_url=BASE_URL, api_key="test-key", default_model="test-model", transport=transport
    )


async def test_generate_timeout_maps_to_retryable():
    adapter = _adapter_with_transport(_RaisingTransport(httpx.ReadTimeout("read timed out")))
    with pytest.raises(ModelTimeoutError) as ei:
        await adapter.generate(user_request())
    assert is_retryable(ei.value)


async def test_generate_network_error_maps_to_unavailable():
    adapter = _adapter_with_transport(_RaisingTransport(httpx.ConnectError("connection refused")))
    with pytest.raises(ProviderUnavailableError) as ei:
        await adapter.generate(user_request())
    assert is_retryable(ei.value)


async def test_generate_server_error_maps_to_unavailable():
    adapter = make_adapter(lambda request: httpx.Response(503, text="service unavailable"))
    with pytest.raises(ProviderUnavailableError, match="503") as ei:
        await adapter.generate(user_request())
    assert is_retryable(ei.value)


async def test_generate_rate_limit_maps_to_retryable():
    adapter = make_adapter(lambda request: httpx.Response(429, text="slow down"))
    with pytest.raises(RateLimitError, match="429") as ei:
        await adapter.generate(user_request())
    assert is_retryable(ei.value)


async def test_generate_auth_error_not_retryable():
    adapter = make_adapter(lambda request: httpx.Response(403, text="forbidden"))
    with pytest.raises(AuthenticationError, match="403") as ei:
        await adapter.generate(user_request())
    assert not is_retryable(ei.value)


async def test_generate_invalid_json_maps_to_malformed():
    adapter = make_adapter(lambda request: httpx.Response(200, text="this is not json"))
    with pytest.raises(MalformedResponseError, match="结构异常") as ei:
        await adapter.generate(user_request())
    assert not is_retryable(ei.value)


async def test_capabilities_do_not_claim_stream():
    """M0-04：STREAM 未实现，不得虚假声明支持。"""
    adapter = make_adapter(lambda request: httpx.Response(200, json={}))
    caps = adapter.capabilities()
    assert ModelCapability.STREAM not in caps
    assert ModelCapability.GENERATE in caps
    assert ModelCapability.EMBED in caps