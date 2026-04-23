#!/usr/bin/env bash
# Realtime Telegram channel membership monitor
# Listens to join/leave events in KD and Salun channels
# and saves them to the database in real time.
#
# Usage:
#   ./scripts/run_tg_realtime.sh
#
# Prerequisites:
#   MTProto session must be authorized.
#   Run  ./scripts/bootstrap_telegram_membership.sh login  if not yet done.

LOG_DIR="$(dirname "$0")/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/tg_realtime.log"
exec > >(tee -a "$LOG_FILE") 2>&1

export TERM="${TERM:-xterm-256color}"
export PYTHONUNBUFFERED=1

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q -r backend/requirements.txt

set -a
[[ -f "$ROOT/.env" ]] && source "$ROOT/.env"
set +a

export PYTHONPATH="$ROOT/backend"
export TELEGRAM_MEMBERSHIP_ENABLED="${TELEGRAM_MEMBERSHIP_ENABLED:-true}"
export TELEGRAM_MEMBERSHIP_REALTIME_ENABLED=true

SESSION_NAME="${TELEGRAM_MTPROTO_SESSION_NAME:-analytics_membership}"
SESSION_FILE="$ROOT/${SESSION_NAME}.session"

if [[ ! -f "$SESSION_FILE" ]]; then
  echo "MTProto session not found: $SESSION_FILE"
  echo "Run: ./scripts/bootstrap_telegram_membership.sh login"
  exit 1
fi

CHANNEL_LABEL="Карточный Домик (${TELEGRAM_CHANNEL_ID:-?})"
COMMUNITY_LABEL="Салун (${TELEGRAM_COMMUNITY_ID:-?})"

echo ""
echo "=================================================="
echo "  REALTIME MONITOR: TELEGRAM КАНАЛЫ"
echo "=================================================="
echo "  • $CHANNEL_LABEL"
echo "  • $COMMUNITY_LABEL"
echo "  Лог: $LOG_FILE"
echo "  Остановка: Ctrl+C"
echo "=================================================="
echo ""

exec .venv/bin/python -m app.ingestion.telegram_membership_realtime
