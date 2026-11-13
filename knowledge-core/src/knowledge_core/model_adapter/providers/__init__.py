"""具体模型供应商适配器。

M1 提供 OpenAI 兼容适配器；后续供应商在此扩展，业务代码只依赖 ModelAdapter 接口。
"""

from knowledge_core.model_adapter.providers.openai_compatible import OpenAICompatibleAdapter

__all__ = ["OpenAICompatibleAdapter"]