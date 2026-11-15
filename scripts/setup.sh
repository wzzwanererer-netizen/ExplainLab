#!/usr/bin/env bash
# ExplainLab 首次安装：Python 依赖 + 前端依赖 + 数据库迁移
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[1/3] 安装 Python 依赖（uv workspace -> .venv，锁定 uv.lock，含 dev/test 依赖组）..."
uv sync --locked

echo "[2/3] 安装前端依赖（npm ci，锁定 package-lock.json，与 package.json 一致）..."
(cd frontend && npm ci)

echo "[3/3] 初始化数据库（Alembic upgrade head）..."
(cd backend && uv run alembic upgrade head)

echo ""
echo "安装完成。启动开发服务：bash scripts/dev.sh"