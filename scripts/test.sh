#!/usr/bin/env bash
# 全量质量检查：Python 测试 + lint + 前端测试 + 类型检查与构建
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== Python 测试（backend + knowledge-core）=="
uv run pytest

echo "== Python lint =="
uv run ruff check backend knowledge-core

echo "== 前端测试 =="
(cd frontend && npm run test)

echo "== 前端类型检查与生产构建 =="
(cd frontend && npm run build)

echo ""
echo "全部通过"