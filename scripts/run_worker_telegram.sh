#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate

pip install -r backend/requirements.txt

set -a
[ -f "$ROOT/.env" ] && source "$ROOT/.env"
set +a

export PYTHONPATH="$ROOT/backend"

# Telegram-only worker (no scheduler process here).
rq worker -u "$REDIS_URL" "${TELEGRAM_RQ_QUEUE_NAME:-telegram}"
