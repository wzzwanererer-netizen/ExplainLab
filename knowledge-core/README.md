# knowledge-core

ExplainLab 的独立知识核心包。

## 独立性约束

- 不依赖 FastAPI / Starlette 等 Web 框架，不依赖前端。
- 仅依赖 Python 标准库与 Pydantic；外部能力（数据库、模型供应商）通过接口注入。
- 知识提取、关系管理、版本管理、来源追溯、检索均可脱离 HTTP 服务纯 Python 调用。
- 本包未来复用于 Nesti；禁止引入 ExplainLab 特有概念。

## 模块

| 模块 | 职责 | M0 状态 |
|---|---|---|
| `domain` | 领域实体（纯 Pydantic 模型） | 骨架 |
| `extraction` | 知识提取接口 | 接口 |
| `relations` | 关系与去重接口 | 接口 |
| `versioning` | 版本管理接口 | 接口 |
| `provenance` | 来源追溯接口 | 接口 |
| `retrieval` | 检索接口 | 接口 |
| `model_adapter` | 统一模型适配层接口 + 注册工厂 | 接口 |

业务实现自 M1 起逐步落地，见仓库根目录 `MILESTONES.md`。