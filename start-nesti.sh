#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

echo "=================================================="
echo "  Nesti · AI Workspace (ExplainLab V3) Launcher"
echo "  Platform: $(uname -s) ($(uname -m))"
echo "=================================================="

if ! command -v uv >/dev/null 2>&1; then
  echo "[Error] uv not found. Install uv first:"
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "[Error] Node.js / npm (22+) not found: https://nodejs.org"
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "[1/4] Installing Python dependencies (uv sync --locked)..."
  uv sync --locked
fi

echo "[2/4] Initializing SQLite database (alembic upgrade head)..."
(cd backend && ../.venv/bin/python -m alembic upgrade head)

if [ ! -f "frontend/dist/index.html" ]; then
  echo "[3/4] Building frontend..."
  (cd frontend && npm ci && npm run build)
fi

if [ ! -d "desktop/node_modules/electron" ]; then
  echo "[4/4] Installing Electron desktop shell..."
  (cd desktop && npm ci)
fi

echo "[OK] Launching Nesti Desktop..."
cd desktop
exec npx electron .
