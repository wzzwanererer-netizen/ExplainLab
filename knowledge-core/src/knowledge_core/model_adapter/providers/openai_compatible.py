"""OpenAI 兼容接口适配器。

覆盖任意 OpenAI Chat Completions 兼容端点（DeepSeek / 通义千问 / Kimi / 智谱 / OpenAI 等）。
这是通用能力，可复用于 Nesti。base_url / api_key / model 由调用方注入，
本类不读取环境变量，也不替换任何代理地址——请求发往调用方给定的真实 base_url。
"""

from __future__ import annotations

from collections.abc import Sequence

import httpx

from knowledge_core.model_adapter.base import ModelAdapter
from knowledge_core.model_adapter.errors import ModelAdapterError
from knowledge_core.model_adapter.types import (
    ModelCapability,
    ModelRequest,
    ModelResponse,
    TokenUsage,
)


class OpenAICompatibleAdapter(ModelAdapter):
    """OpenAI 兼容供应商适配器。

    Args:
        base_url: 真实 API 根地址（如 https://api.deepseek.com/v1），原样使用。
        api_key: 密钥，仅由后端注入。
        default_model: 默认聊天模型名。
        embed_model: 向量模型名；None 时复用 default_model。
        timeout: 单次请求超时（秒）。
        provider_name: 供应商标识。
        transport: 可选 httpx 传输层，测试可注入 MockTransport（不发真实网络请求）。
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        default_model: str,
        embed_model: str | None = None,
        timeout: float = 60.0,
        provider_name: str = "openai-compatible",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._default_model = default_model
        self._embed_model = embed_model or default_model
        self._timeout = timeout
        self._provider_name = provider_name
        self._transport = transport

    @property
    def provider(self) -> str:
        return self._provider_name

    @property
    def default_model(self) -> str:
        return self._default_model

    def capabilities(self) -> set[ModelCapability]:
        return {ModelCapability.GENERATE, ModelCapability.EMBED}

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=self._timeout,
            transport=self._transport,
            # 直连调用方给定的真实 base_url：不读取环境代理变量（HTTP(S)_PROXY/ALL_PROXY），
            # 杜绝任何代理替换；同时规避 httpx 0.28 解析 NO_PROXY 中 IPv6 项（如 [::1]）的缺陷。
            trust_env=False,
        )

    async def generate(self, request: ModelRequest) -> ModelResponse:
        model = request.model or self._default_model
        payload: dict = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        data = await self._post("/chat/completions", payload)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelAdapterError(f"模型响应结构异常: {str(data)[:500]}") from exc

        usage = None
        raw_usage = data.get("usage")
        if isinstance(raw_usage, dict):
            usage = TokenUsage(
                prompt_tokens=raw_usage.get("prompt_tokens", 0),
                completion_tokens=raw_usage.get("completion_tokens", 0),
                total_tokens=raw_usage.get("total_tokens", 0),
            )
        return ModelResponse(
            content=content,
            model=data.get("model", model),
            provider=self._provider_name,
            usage=usage,
        )

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = {"model": self._embed_model, "input": list(texts)}
        data = await self._post("/embeddings", payload)
        try:
            ordered = sorted(data["data"], key=lambda d: d["index"])
            return [item["embedding"] for item in ordered]
        except (KeyError, TypeError) as exc:
            raise ModelAdapterError(f"向量响应结构异常: {str(data)[:500]}") from exc

    async def _post(self, path: str, payload: dict) -> dict:
        async with self._client() as client:
            try:
                response = await client.post(path, json=payload)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise ModelAdapterError(
                    f"模型接口返回错误 {exc.response.status_code}: {exc.response.text[:500]}"
                ) from exc
            except httpx.HTTPError as exc:
                raise ModelAdapterError(f"模型接口请求失败: {exc}") from exc
            return response.json()