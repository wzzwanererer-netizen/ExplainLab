"""实验模块异常类型。"""

from __future__ import annotations


class ExperimentError(Exception):
    """实验模块基础异常。"""


class InvalidExperimentError(ExperimentError):
    """请求参数或作答不合法（映射 400）。"""


class ExperimentNotFoundError(ExperimentError):
    """实验会话或知识条目不存在（映射 404）。"""


class ModelRequiredError(ExperimentError):
    """该实验模式需要模型但未配置（映射 503）。"""
