"""Model Adapter 公共异常契约。

所有供应商适配器必须把底层故障映射到下列公共异常类型；业务代码只依赖本契约，
不依赖任何供应商 SDK 的异常。``retryable`` 标记是否值得重试：

- 可重试（retryable=True）：超时、供应商暂时不可用、限流——重试可能成功。
- 不可重试（retryable=False）：能力不支持、响应格式错误、鉴权失败、配置错误——重试无益。

STREAM 能力未实现时，适配器不得在 capabilities() 中声明 STREAM，
请求未声明的能力应抛出 CapabilityNotSupportedError，不得虚假返回成功。
"""

from __future__ import annotations


class ModelAdapterError(Exception):
    """模型适配层基础异常。``retryable`` 标记是否值得重试。"""

    retryable: bool = False


class AdapterNotFoundError(ModelAdapterError):
    """请求的适配器未注册（配置问题，不可重试）。"""


class AdapterAlreadyRegisteredError(ModelAdapterError):
    """同名适配器重复注册（配置问题，不可重试）。"""


class CapabilityNotSupportedError(ModelAdapterError):
    """适配器不支持所请求的能力（不可重试）。"""


class ModelTimeoutError(ModelAdapterError):
    """请求超时（可重试）。"""

    retryable = True


class ProviderUnavailableError(ModelAdapterError):
    """供应商不可用：网络故障或 5xx（可重试）。"""

    retryable = True


class RateLimitError(ModelAdapterError):
    """供应商限流 429（可重试，宜退避）。"""

    retryable = True


class AuthenticationError(ModelAdapterError):
    """鉴权失败 401/403（密钥错误，不可重试）。"""


class MalformedResponseError(ModelAdapterError):
    """响应格式错误：非法 JSON 或缺少必需字段（不可重试）。"""


def is_retryable(exc: BaseException) -> bool:
    """判断异常是否可重试；非适配层异常一律视为不可重试。"""
    return isinstance(exc, ModelAdapterError) and exc.retryable