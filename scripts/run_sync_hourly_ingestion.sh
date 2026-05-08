#!/usr/bin/env bash
# Dedicated hourly ingestion runner.
# Runs bot DB ingestion + aggregates in an infinite loop.
#
# ENV:
#   INGESTION_SYNC_INTERVAL_MINUTES (default: 60)
#   POKERHUB_SYNC_INTERVAL_HOURS (default: 24)

LOG_DIR="$(dirname "$0")/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/run_sync_hourly_ingestion.log"
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
export INGESTION_SYNC_INTERVAL_MINUTES="${INGESTION_SYNC_INTERVAL_MINUTES:-60}"
export POKERHUB_SYNC_INTERVAL_HOURS="${POKERHUB_SYNC_INTERVAL_HOURS:-24}"
STATE_DIR="$ROOT/scripts/.state"
mkdir -p "$STATE_DIR"
POKERHUB_STAMP_FILE="$STATE_DIR/last_pokerhub_sync.ts"

echo "Hourly ingestion runner started. Interval=${INGESTION_SYNC_INTERVAL_MINUTES} min. PokerHub interval=${POKERHUB_SYNC_INTERVAL_HOURS} h"

should_run_pokerhub() {
  local now last_run min_age
  now="$(date +%s)"
  min_age="$((POKERHUB_SYNC_INTERVAL_HOURS * 3600))"
  if [[ "$min_age" -le 0 ]]; then
    return 1
  fi
  if [[ ! -f "$POKERHUB_STAMP_FILE" ]]; then
    return 0
  fi
  last_run="$(cat "$POKERHUB_STAMP_FILE" 2>/dev/null || echo 0)"
  [[ $((now - last_run)) -ge "$min_age" ]]
}

while true; do
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting ingestion sync..."
  .venv/bin/python -c "from app.worker.runtime.tasks_runtime_jobs import run_ingestion_job; run_ingestion_job()"
  if should_run_pokerhub; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting PokerHub sync..."
    .venv/bin/python -c "from app.worker.runtime.tasks_runtime_jobs import run_pokerhub_cache_job; run_pokerhub_cache_job()"
    date +%s > "$POKERHUB_STAMP_FILE"
  fi
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Ingestion sync finished. Sleeping..."
  sleep "$((INGESTION_SYNC_INTERVAL_MINUTES * 60))"
done
