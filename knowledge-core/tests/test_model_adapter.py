"""Model Adapter 接口与注册工厂测试。

DummyAdapter 是测试基建，不是产品功能；M0 不包含任何真实供应商实现。
"""

from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from knowledge_core.model_adapter import (
    AdapterAlreadyRegisteredError,
    AdapterNotFoundError,
    AdapterRegistry,
    ModelAdapter,
    ModelCapability,
    ModelMessage,
    ModelRequest,
    ModelResponse,
)


class DummyAdapter(ModelAdapter):
    """测试用最小实现，验证接口契约可被满足。"""

    @property
    def provider(self) -> str:
        return "dummy"

    @property
    def default_model(self) -> str:
        return "dummy-model"

    def capabilities(self) -> set[ModelCapability]:
        return {ModelCapability.GENERATE, ModelCapability.EMBED}

    async def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            content="ok",
            model=request.model or self.default_model,
            provider=self.provider,
        )

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]


class TestModelTypes:
    def test_request_requires_messages(self):
        with pytest.raises(ValidationError):
            ModelRequest(messages=[])

    def test_temperature_bounds(self):
        msg = ModelMessage(role="user", content="hi")
        with pytest.raises(ValidationError):
            ModelRequest(messages=[msg], temperature=3.0)

    def test_message_role_literal(self):
        with pytest.raises(ValidationError):
            ModelMessage(role="tool", content="x")  # type: ignore[arg-type]


class TestAdapterContract:
    def test_abstract_cannot_instantiate(self):
        with pytest.raises(TypeError):
            ModelAdapter()  # type: ignore[abstract]

    async def test_dummy_generate(self):
        adapter = DummyAdapter()
        resp = await adapter.generate(
            ModelRequest(messages=[ModelMessage(role="user", content="hi")])
        )
        assert resp.provider == "dummy"
        assert resp.model == "dummy-model"

    async def test_dummy_embed_length(self):
        adapter = DummyAdapter()
        vectors = await adapter.embed(["a", "b", "c"])
        assert len(vectors) == 3


class TestAdapterRegistry:
    def test_register_and_resolve(self):
        registry = AdapterRegistry()
        adapter = DummyAdapter()
        registry.register(adapter)
        assert registry.resolve("dummy") is adapter
        assert "dummy" in registry
        assert len(registry) == 1

    def test_custom_name(self):
        registry = AdapterRegistry()
        registry.register(DummyAdapter(), name="primary")
        assert registry.names() == ["primary"]
        assert registry.resolve("primary").provider == "dummy"

    def test_duplicate_rejected(self):
        registry = AdapterRegistry()
        registry.register(DummyAdapter())
        with pytest.raises(AdapterAlreadyRegisteredError):
            registry.register(DummyAdapter())

    def test_resolve_missing(self):
        registry = AdapterRegistry()
        with pytest.raises(AdapterNotFoundError):
            registry.resolve("nope")

    def test_unregister(self):
        registry = AdapterRegistry()
        registry.register(DummyAdapter())
        registry.unregister("dummy")
        registry.unregister("dummy")  # 幂等
        assert len(registry) == 0