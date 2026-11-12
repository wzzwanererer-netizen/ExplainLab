"""与供应商无关的模型请求 / 响应类型。"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class ModelCapability(StrEnum):
    """适配器声明的能力。"""

    GENERATE = "generate"
    EMBED = "embed"
    STREAM = "stream"


class ModelMessage(BaseModel):
    """一条对话消息。"""

    role: Literal["system", "user", "assistant"]
    content: str


class ModelRequest(BaseModel):
    """文本生成请求。"""

    messages: list[ModelMessage] = Field(min_length=1)
    model: str | None = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, gt=0)


class TokenUsage(BaseModel):
    """Token 用量统计（供应商未提供时为 None）。"""

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class ModelResponse(BaseModel):
    """文本生成响应。"""

    content: str
    model: str
    provider: str
    usage: TokenUsage | None = None