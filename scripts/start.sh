#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export BACKEND_PORT="${BACKEND_PORT:-17000}"

if [[ ! -d backend/.venv ]]; then
  python3 -m venv backend/.venv
fi
# shellcheck disable=SC1091
source backend/.venv/bin/activate
pip install -r backend/requirements.txt

if [[ ! -f backend/.env ]] && [[ -f .env.example ]]; then
  cp .env.example backend/.env
  echo "Created backend/.env from .env.example — edit if needed."
fi

(cd frontend && npm ci)
(cd frontend && npm run dev) &
FE_PID=$!

cleanup() {
  kill "$FE_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

sleep 2
cd backend
uvicorn app.main:app --reload --port "$BACKEND_PORT"
