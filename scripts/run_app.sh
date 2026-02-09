#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate

pip install -r backend/requirements.txt

if [ -f "frontend/package.json" ]; then
  (cd frontend && npm install && npm run build)
fi

set -a
[ -f "$ROOT/.env" ] && source "$ROOT/.env"
set +a

(cd backend && "$ROOT/.venv/bin/alembic" upgrade head)

python run.py
