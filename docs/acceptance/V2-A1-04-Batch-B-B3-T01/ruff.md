# Ruff

命令：

```bash
uv run ruff check backend knowledge-core
```

结果：`All checks passed!`，exit 0。

原始日志：[evidence/ruff-backend-core.log](evidence/ruff-backend-core.log)

本轮未执行 `ruff format`（AGENTS.md 明确禁止）。

新增/修改文件单独检查同样通过：

```text
backend/app/services/attachment_staging.py
backend/app/services/markdown.py
backend/app/api/routes/import_export.py
backend/tests/test_attachment_staging.py
All checks passed!
```

全仓 `ruff check` 未纳入本轮质量门；历史审计包副本中的旧问题不属 B3-T01 范围，也未修改。