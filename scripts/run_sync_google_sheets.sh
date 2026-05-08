#!/usr/bin/env bash
# Dedicated Google Sheets sync runner.
# Runs sync in an infinite loop with configurable interval.
#
# ENV:
#   GOOGLE_SHEETS_SYNC_INTERVAL_MINUTES (default: 60)

LOG_DIR="$(dirname "$0")/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/run_sync_google_sheets.log"
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
export GOOGLE_SHEETS_SYNC_INTERVAL_MINUTES="${GOOGLE_SHEETS_SYNC_INTERVAL_MINUTES:-60}"

echo "Google Sheets sync runner started. Interval=${GOOGLE_SHEETS_SYNC_INTERVAL_MINUTES} min"

while true; do
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Google Sheets sync..."
  .venv/bin/python -c "from app.worker.runtime.tasks_runtime_jobs import run_google_sheets_job; run_google_sheets_job()"
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Google Sheets sync finished. Sleeping..."
  sleep "$((GOOGLE_SHEETS_SYNC_INTERVAL_MINUTES * 60))"
done

