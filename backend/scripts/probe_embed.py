"""只读探测 embed 端点能力（M3-T4）。

用法（任意目录，经 uv 工作区环境）：
    uv run python backend/scripts/probe_embed.py

读取 backend/.env 的 EMBED_*，调用 /embeddings 探测，打印
not_configured / supported / unsupported 及模型 / 维度。
不写入任何数据、不打印密钥；base_url 原样使用，不经代理。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from app.core.config import Settings
from app.services.model import build_embed_adapter
from app.services.retrieval import probe_embed_capability

BACKEND_DIR = Path(__file__).resolve().parents[1]


async def main() -> None:
    # Windows 控制台默认 GBK，强制 UTF-8 输出，避免中文乱码（证据需干净 UTF-8）。
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    settings = Settings(_env_file=str(BACKEND_DIR / ".env"))
    adapter = build_embed_adapter(settings)
    status = await probe_embed_capability(adapter)
    print(f"embed 能力: {status}")
    if adapter is None:
        print(
            "未配置 EMBED_BASE_URL / EMBED_API_KEY / EMBED_MODEL："
            "向量通道关闭，仅全文检索。"
        )
        return
    print(f"端点: {settings.embed_base_url}  模型: {settings.embed_model}")
    if status == "supported":
        vectors = await adapter.embed(["能力探测"])
        print(f"向量维度: {len(vectors[0])}")
    else:
        print(
            "端点未提供可用的 /embeddings（如 DeepSeek 聊天端点）。"
            "请更换支持 embed 的供应商后重试。"
        )


if __name__ == "__main__":
    asyncio.run(main())