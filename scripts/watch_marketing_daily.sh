#!/usr/bin/env bash
set -euo pipefail

ROOT_ANALYTICS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT_MYMEET="/home/fervuld/prod/mymeetai_tgbot-main_new"

APP_LOG="$ROOT_ANALYTICS/scripts/logs/run_app.log"
WORKER_LOG="$ROOT_ANALYTICS/scripts/logs/run_worker.log"
MYMEET_BACKEND_LOG="$ROOT_MYMEET/logs/backend.log"
MYMEET_BOT_LOG="$ROOT_MYMEET/logs/bot.log"

mkdir -p "$(dirname "$APP_LOG")"
mkdir -p "$ROOT_MYMEET/logs"

touch "$APP_LOG" "$WORKER_LOG" "$MYMEET_BACKEND_LOG" "$MYMEET_BOT_LOG"

echo "Watching Marketing Daily logs..."
echo "Analytics app:    $APP_LOG"
echo "Analytics worker: $WORKER_LOG"
echo "MyMeet backend:   $MYMEET_BACKEND_LOG"
echo "MyMeet bot:       $MYMEET_BOT_LOG"
echo
echo "Ctrl+C to stop"
echo

tail -F "$APP_LOG" "$WORKER_LOG" "$MYMEET_BACKEND_LOG" "$MYMEET_BOT_LOG" | \
awk '
  /^==> .* <==$/ {
    source=$0
    gsub(/^==> /, "", source)
    gsub(/ <==$/, "", source)
    next
  }
  {
    line=$0
    lower=tolower(line)
    if (
      index(lower, "marketing daily") > 0 ||
      index(lower, "marketing_daily") > 0 ||
      index(lower, "daily skipped") > 0 ||
      index(lower, "delivery result") > 0 ||
      index(lower, "alert | marketing daily") > 0 ||
      index(lower, "marketing_daily_delivery") > 0
    ) {
      print "[" source "] " line
      fflush()
    }
  }
'
