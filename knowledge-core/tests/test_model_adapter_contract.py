"""M0-04：Model Adapter 公共失败契约（假供应商模拟，契约与供应商无关）。

用 FakeProvider 模拟五种场景：正常 / 超时 / 供应商不可用 / 不支持能力 / 响应格式错误，
验证所有供应商都遵循同一公共异常契约与可重试分类；STREAM 未实现不得虚假声明。
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from knowledge_core.model_adapter import (
    AuthenticationError,
    CapabilityNotSupportedError,
    MalformedResponseError,
    ModelAdapter,
    ModelAdapterError,
    ModelCapability,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelTimeoutError,
    ProviderUnavailableError,
    RateLimitError,
    is_retryable,
)


class FakeProvider(ModelAdapter):
    """假供应商：按预设行为返回或抛出公共异常，不发起任何网络请求。"""

    def __init__(
        self, *, behavior: str = "ok", caps: set[ModelCapability] | None = None
    ) -> None:
        self._behavior = behavior
        self._caps = caps if caps is not None else {ModelCapability.GENERATE}

    @property
    def provider(self) -> str:
        return "fake"

    @property
    def default_model(self) -> str:
        return "fake-model"

    def capabilities(self) -> set[ModelCapability]:
        return set(self._caps)

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if self._behavior == "timeout":
            raise ModelTimeoutError("请求超时")
        if self._behavior == "unavailable":
            raise ProviderUnavailableError("供应商不可用")
        if self._behavior == "malformed":
            raise MalformedResponseError("响应结构异常")
        if self._behavior == "unsupported":
            raise CapabilityNotSupportedError("不支持该能力")
        return ModelResponse(content="ok", model="fake-model", provider="fake")

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if ModelCapability.EMBED not in self._caps:
            raise CapabilityNotSupportedError("不支持 embed")
        return [[0.0] for _ in texts]


def _req() -> ModelRequest:
    return ModelRequest(messages=[ModelMessage(role="user", content="hi")])


async def test_fake_provider_normal_response():
    resp = await FakeProvider().generate(_req())
    assert resp.content == "ok"
    assert resp.provider == "fake"


async def test_fake_provider_timeout_is_retryable():
    with pytest.raises(ModelTimeoutError) as ei:
        await FakeProvider(behavior="timeout").generate(_req())
    assert is_retryable(ei.value)


async def test_fake_provider_unavailable_is_retryable():
    with pytest.raises(ProviderUnavailableError) as ei:
        await FakeProvider(behavior="unavailable").generate(_req())
    assert is_retryable(ei.value)


async def test_fake_provider_unsupported_capability_not_retryable():
    # 只声明 GENERATE 的供应商，请求 embed → CapabilityNotSupportedError
    with pytest.raises(CapabilityNotSupportedError) as ei:
        await FakeProvider(caps={ModelCapability.GENERATE}).embed(["x"])
    assert not is_retryable(ei.value)


async def test_fake_provider_malformed_response_not_retryable():
    with pytest.raises(MalformedResponseError) as ei:
        await FakeProvider(behavior="malformed").generate(_req())
    assert not is_retryable(ei.value)


def test_stream_not_claimed_by_fake_provider():
    assert ModelCapability.STREAM not in FakeProvider().capabilities()


@pytest.mark.parametrize(
    ("exc_type", "retryable"),
    [
        (ModelTimeoutError, True),
        (ProviderUnavailableError, True),
        (RateLimitError, True),
        (AuthenticationError, False),
        (MalformedResponseError, False),
        (CapabilityNotSupportedError, False),
        (ModelAdapterError, False),
    ],
)
def test_retryable_classification(exc_type: type[ModelAdapterError], retryable: bool):
    exc = exc_type("x")
    assert isinstance(exc, ModelAdapterError)
    assert is_retryable(exc) is retryable


def test_non_adapter_error_not_retryable():
    assert not is_retryable(ValueError("x"))
    assert not is_retryable(RuntimeError("x"))