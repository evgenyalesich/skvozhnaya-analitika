#!/usr/bin/env bash
# Show Telegram membership comparison report.
# Compares channel subscribers with raw_bot_users table.
#
# Usage:
#   ./scripts/tg_membership_report.sh

export PYTHONUNBUFFERED=1
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d ".venv" ]]; then
  echo "Virtualenv not found. Run bootstrap_telegram_membership.sh first."
  exit 1
fi

source .venv/bin/activate

set -a
[[ -f "$ROOT/.env" ]] && source "$ROOT/.env"
set +a

export PYTHONPATH="$ROOT/backend"

exec .venv/bin/python -m app.ingestion.telegram_membership_report
