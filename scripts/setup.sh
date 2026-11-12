#!/usr/bin/env bash
# ExplainLab 首次安装：Python 依赖 + 前端依赖 + 数据库迁移
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[1/3] 安装 Python 依赖（uv workspace -> .venv）..."
uv sync

echo "[2/3] 安装前端依赖（npm -> frontend/node_modules）..."
(cd frontend && npm install)

echo "[3/3] 初始化数据库（Alembic upgrade head）..."
(cd backend && uv run alembic upgrade head)

echo ""
echo "安装完成。启动开发服务：bash scripts/dev.sh"