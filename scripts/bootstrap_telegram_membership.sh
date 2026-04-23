#!/usr/bin/env bash
LOG_DIR="$(dirname "$0")/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/$(basename "$0" .sh).log"
exec > >(tee -a "$LOG_FILE") 2>&1

export TERM="${TERM:-xterm-256color}"
export CLICOLOR=1
export FORCE_COLOR=1
export PYTHONUNBUFFERED=1
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${1:-bootstrap}"

if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate

pip install -r backend/requirements.txt

set -a
[[ -f "$ROOT/.env" ]] && source "$ROOT/.env"
set +a

export PYTHONPATH="$ROOT/backend"
export TELEGRAM_MEMBERSHIP_ENABLED="${TELEGRAM_MEMBERSHIP_ENABLED:-false}"
export TELEGRAM_MEMBERSHIP_REALTIME_ENABLED="${TELEGRAM_MEMBERSHIP_REALTIME_ENABLED:-false}"
export TELEGRAM_MEMBERSHIP_RESOLVE_JOINED_AT="${TELEGRAM_MEMBERSHIP_RESOLVE_JOINED_AT:-true}"
export TELEGRAM_MEMBERSHIP_JOINED_AT_CONCURRENCY="${TELEGRAM_MEMBERSHIP_JOINED_AT_CONCURRENCY:-5}"

if [[ -z "${TELEGRAM_API_ID:-}" || -z "${TELEGRAM_API_HASH:-}" ]]; then
  echo "TELEGRAM_API_ID/TELEGRAM_API_HASH are required in .env"
  exit 1
fi

if [[ -z "${TELEGRAM_CHANNEL_ID:-}" || -z "${TELEGRAM_COMMUNITY_ID:-}" ]]; then
  echo "TELEGRAM_CHANNEL_ID/TELEGRAM_COMMUNITY_ID are required in .env"
  exit 1
fi

export TELEGRAM_MEMBERSHIP_CHAT_IDS_CSV="${TELEGRAM_MEMBERSHIP_CHAT_IDS_CSV:-$TELEGRAM_CHANNEL_ID,$TELEGRAM_COMMUNITY_ID}"
SESSION_NAME="${TELEGRAM_MTPROTO_SESSION_NAME:-analytics_membership}"
SESSION_FILE="$ROOT/${SESSION_NAME}.session"

run_login() {
  echo "Starting MTProto login..."
  .venv/bin/python -m app.ingestion.telegram_membership_login
}

run_sync() {
  echo "Starting Telegram membership full sync for chats: ${TELEGRAM_MEMBERSHIP_CHAT_IDS_CSV}"
  echo "Joined-at resolution concurrency: ${TELEGRAM_MEMBERSHIP_JOINED_AT_CONCURRENCY}"
  .venv/bin/python -m app.ingestion.telegram_membership_sync
}

case "$MODE" in
  login)
    run_login
    ;;
  sync)
    run_sync
    ;;
  bootstrap)
    if [[ ! -f "$SESSION_FILE" ]]; then
      echo "MTProto session not found at $SESSION_FILE"
      run_login
    else
      echo "Using existing MTProto session: $SESSION_FILE"
    fi
    run_sync
    ;;
  *)
    echo "Usage: $0 [login|sync|bootstrap]"
    exit 1
    ;;
esac
