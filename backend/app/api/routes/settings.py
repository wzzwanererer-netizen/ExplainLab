"""模型与 API Key 可视化配置路由（热更新 backend/.env，严守脱敏红线）。

安全约束（AGENTS.md §9）：
- GET 绝不回传明文 API Key，仅返回是否已配置与脱敏掩码（如 `sk-****abcd`）；
- 测试连通性直连用户填写的真实 base_url（trust_env=False），失败只返回稳定错误码与友好提示，
  绝不回传 str(exc) 或密钥文本。
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.core.config import BACKEND_DIR, Settings, get_settings
from knowledge_core.model_adapter import (
    AuthenticationError,
    ModelAdapterError,
    ModelMessage,
    ModelRequest,
    ModelTimeoutError,
    OpenAICompatibleAdapter,
    ProviderUnavailableError,
    RateLimitError,
)

router = APIRouter(prefix="/settings", tags=["settings"])

_ENV_LINE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")


class ModelSettingsOut(BaseModel):
    model_provider: str | None
    model_base_url: str | None
    model_name: str | None
    model_api_key_set: bool
    model_api_key_masked: str | None
    embed_base_url: str | None
    embed_model: str | None
    embed_api_key_set: bool
    embed_api_key_masked: str | None
    env_file: str


class ModelSettingsUpdateIn(BaseModel):
    model_base_url: str | None = Field(default=None, max_length=300)
    model_name: str | None = Field(default=None, max_length=120)
    model_api_key: str | None = Field(default=None, max_length=300)
    clear_model_api_key: bool = False
    embed_base_url: str | None = Field(default=None, max_length=300)
    embed_model: str | None = Field(default=None, max_length=120)
    embed_api_key: str | None = Field(default=None, max_length=300)
    clear_embed_api_key: bool = False


class ModelTestIn(BaseModel):
    base_url: str = Field(min_length=1, max_length=300)
    model_name: str = Field(min_length=1, max_length=120)
    api_key: str | None = Field(default=None, max_length=300)


class ModelTestOut(BaseModel):
    ok: bool
    latency_ms: int
    error_code: str | None = None
    message: str


def _mask_secret(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.strip()
    if len(s) <= 8:
        return "****"
    return f"{s[:4]}****{s[-4:]}"


def _serialize_settings(settings: Settings, env_path: Path) -> ModelSettingsOut:
    model_raw = settings.model_api_key.get_secret_value() if settings.model_api_key else None
    embed_raw = settings.embed_api_key.get_secret_value() if settings.embed_api_key else None
    return ModelSettingsOut(
        model_provider=settings.model_provider,
        model_base_url=settings.model_base_url,
        model_name=settings.model_name,
        model_api_key_set=bool(model_raw),
        model_api_key_masked=_mask_secret(model_raw),
        embed_base_url=settings.embed_base_url,
        embed_model=settings.embed_model,
        embed_api_key_set=bool(embed_raw),
        embed_api_key_masked=_mask_secret(embed_raw),
        env_file=str(env_path),
    )


def _format_env_value(value: str) -> str:
    cleaned = value.replace("\r", "").replace("\n", "").strip()
    if any(ch in cleaned for ch in (" ", "#", '"', "'")):
        escaped = cleaned.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return cleaned


def update_env_file(env_path: Path, updates: dict[str, str | None]) -> None:
    """安全更新 .env 文件中的指定键，保留注释及其他配置行不变。"""
    lines: list[str] = []
    if env_path.is_file():
        lines = env_path.read_text(encoding="utf-8", errors="ignore").splitlines()

    seen: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        m = _ENV_LINE_RE.match(line)
        if m and m.group(1) in updates:
            key = m.group(1)
            seen.add(key)
            val = updates[key]
            if val is not None:
                new_lines.append(f"{key}={_format_env_value(val)}")
            else:
                new_lines.append(f"{key}=")
        else:
            new_lines.append(line)

    for key, val in updates.items():
        if key not in seen and val is not None:
            new_lines.append(f"{key}={_format_env_value(val)}")

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")


def _env_path_for(request: Request) -> Path:
    custom = getattr(request.app.state, "env_file_path", None)
    return Path(custom) if custom else (BACKEND_DIR / ".env")


@router.get("/models", response_model=ModelSettingsOut)
def get_model_settings(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ModelSettingsOut:
    return _serialize_settings(settings, _env_path_for(request))


@router.put("/models", response_model=ModelSettingsOut)
def put_model_settings(
    payload: ModelSettingsUpdateIn,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ModelSettingsOut:
    env_path = _env_path_for(request)
    updates: dict[str, str | None] = {}

    if payload.model_base_url is not None:
        base = payload.model_base_url.strip()
        updates["MODEL_BASE_URL"] = base or None
        updates["MODEL_PROVIDER"] = "openai-compatible" if base else None
    if payload.model_name is not None:
        updates["MODEL_NAME"] = payload.model_name.strip() or None
    if payload.clear_model_api_key:
        updates["MODEL_API_KEY"] = None
    elif payload.model_api_key is not None and payload.model_api_key.strip():
        updates["MODEL_API_KEY"] = payload.model_api_key.strip()

    if payload.embed_base_url is not None:
        updates["EMBED_BASE_URL"] = payload.embed_base_url.strip() or None
    if payload.embed_model is not None:
        updates["EMBED_MODEL"] = payload.embed_model.strip() or None
    if payload.clear_embed_api_key:
        updates["EMBED_API_KEY"] = None
    elif payload.embed_api_key is not None and payload.embed_api_key.strip():
        updates["EMBED_API_KEY"] = payload.embed_api_key.strip()

    update_env_file(env_path, updates)

    # 热刷新运行时 Settings（保留现有 database_url 与 data_dir，不中断正在运行的后端）
    get_settings.cache_clear()
    reloaded = Settings(
        _env_file=str(env_path),  # type: ignore[call-arg]
        database_url=settings.database_url,
        data_dir=settings.data_dir,
    )
    request.app.dependency_overrides[get_settings] = lambda: reloaded
    return _serialize_settings(reloaded, env_path)


@router.post("/models/test", response_model=ModelTestOut)
async def test_model_connection(
    payload: ModelTestIn,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ModelTestOut:
    api_key = (payload.api_key or "").strip()
    if not api_key and settings.model_api_key:
        api_key = settings.model_api_key.get_secret_value()
    # Ollama 等本地模型允许免 Key（传占位符即可通过 OpenAI 兼容头）
    if not api_key and ("127.0.0.1" in payload.base_url or "localhost" in payload.base_url):
        api_key = "ollama"
    if not api_key:
        return ModelTestOut(
            ok=False,
            latency_ms=0,
            error_code="missing_api_key",
            message="请填写 API Key 后再测试连接（本机 Ollama 可留空）。",
        )

    adapter = OpenAICompatibleAdapter(
        base_url=payload.base_url.strip(),
        api_key=api_key,
        default_model=payload.model_name.strip(),
        timeout_seconds=15.0,
    )
    t0 = time.perf_counter()
    try:
        await adapter.generate(
            ModelRequest(
                messages=[ModelMessage(role="user", content="hi")],
                max_tokens=8,
                temperature=0.0,
            )
        )
        ms = int((time.perf_counter() - t0) * 1000)
        return ModelTestOut(
            ok=True,
            latency_ms=ms,
            message=f"连接成功！模型「{payload.model_name.strip()}」响应正常（{ms} ms）。",
        )
    except AuthenticationError:
        return ModelTestOut(
            ok=False,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            error_code="authentication_error",
            message="鉴权失败：请检查 API Key 是否正确或账户余额是否充足。",
        )
    except RateLimitError:
        return ModelTestOut(
            ok=False,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            error_code="rate_limit",
            message="触发频率限制（429），密钥有效但当前请求受限。",
        )
    except ModelTimeoutError:
        return ModelTestOut(
            ok=False,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            error_code="timeout",
            message="请求超时：请检查 Base URL 是否可达或本地 Ollama 服务是否已启动。",
        )
    except (ProviderUnavailableError, ModelAdapterError):
        return ModelTestOut(
            ok=False,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            error_code="provider_unavailable",
            message="无法连接模型服务：请核对 Base URL 与模型名称是否正确。",
        )
