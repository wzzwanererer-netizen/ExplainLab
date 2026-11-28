#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="${ROOT_DIR}/backend:${ROOT_DIR}/knowledge-core/src${PYTHONPATH:+:$PYTHONPATH}"
exec "${ROOT_DIR}/.venv/bin/python" -m app.mcp_server "$@"
