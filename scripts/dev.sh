#!/usr/bin/env bash
# 同时启动前后端开发服务；Ctrl+C 一起退出。
# Windows 建议使用 dev.ps1（独立窗口，日志清晰，关闭即停止）。
set -euo pipefail
cd "$(dirname "$0")/.."

(cd backend && uv run uvicorn app.main:app --reload --port 8000) &
BACKEND_PID=$!

(cd frontend && npm run dev) &
FRONTEND_PID=$!

cleanup() {
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "后端: http://127.0.0.1:8000/api/health"
echo "前端: http://localhost:5173"
echo "按 Ctrl+C 停止全部服务"
wait