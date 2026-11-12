"""Model Adapter 异常类型。"""

from __future__ import annotations


class ModelAdapterError(Exception):
    """模型适配层基础异常。"""


class AdapterNotFoundError(ModelAdapterError):
    """请求的适配器未注册。"""


class AdapterAlreadyRegisteredError(ModelAdapterError):
    """同名适配器重复注册。"""


class CapabilityNotSupportedError(ModelAdapterError):
    """适配器不支持所请求的能力。"""