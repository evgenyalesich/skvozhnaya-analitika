#!/usr/bin/env bash
LOG_DIR="$(dirname "$0")/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/$(basename "$0" .sh).log"
exec > >(tee -a "$LOG_FILE") 2>&1

export TERM="${TERM:-xterm-256color}"
export CLICOLOR=1
export FORCE_COLOR=1
export PYTHONUNBUFFERED=1
mkdir -p "$LOG_DIR"
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
