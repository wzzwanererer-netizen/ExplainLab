"""Knowledge Core：ExplainLab 独立知识核心。

本包不依赖 Web 框架与前端，可复用于 Nesti。
V1.0（M0–M5）已落地完整业务实现：知识提取、关系与去重、版本管理、来源追溯、
重要变更审核、混合检索、知识地图、交互式实验，以及统一 Model Adapter。
各服务模块按「抽象接口（ABC）+ 具体实现」分层；持久化与模型能力经 ports.py
的 Protocol 端口由应用层注入，核心不绑定任何数据库或供应商 SDK。
"""

__version__ = "0.1.0"