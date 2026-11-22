"""后端测试夹具：每个测试使用独立的临时 SQLite 数据库。

模型相关测试通过本地 StubAdapter 注入，不发起任何网络请求。
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.models  # noqa: F401  确保 ORM 元数据注册
from app.core.config import Settings
from app.db.base import Base
from app.db.session import create_engine_from_url, dispose_db
from app.dependencies import get_model_adapter
from app.main import create_app
from knowledge_core.model_adapter import (
    ModelAdapter,
    ModelAdapterError,
    ModelCapability,
    ModelRequest,
    ModelResponse,
)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        data_dir=tmp_path / "data",
        model_provider=None,
        model_base_url=None,
        model_api_key=None,
        model_name=None,
        _env_file=None,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    # 启动流程会初始化默认知识空间，须先建表（测试不走 Alembic，迁移一致性另有专测）
    engine = create_engine_from_url(settings.database_url)
    Base.metadata.create_all(engine)
    engine.dispose()
    with TestClient(app) as test_client:
        yield test_client
    dispose_db()


class StubAdapter(ModelAdapter):
    """测试替身：返回预设内容或模拟故障，不发起任何网络请求。"""

    def __init__(self, content: str = "好的", *, fail: bool = False) -> None:
        self.content = content
        self.fail = fail
        self.requests: list[ModelRequest] = []

    @property
    def provider(self) -> str:
        return "stub"

    @property
    def default_model(self) -> str:
        return "stub-model"

    def capabilities(self) -> set[ModelCapability]:
        return {ModelCapability.GENERATE}

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if self.fail:
            raise ModelAdapterError("模拟模型故障")
        return ModelResponse(content=self.content, model="stub-model", provider="stub")

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]


@pytest.fixture
def stub_adapter() -> StubAdapter:
    return StubAdapter()


@pytest.fixture
def model_client(client: TestClient, stub_adapter: StubAdapter) -> TestClient:
    """注入 stub 适配器的客户端，用于对话 / 提取的成功路径测试。"""
    client.app.dependency_overrides[get_model_adapter] = lambda: stub_adapter
    return client