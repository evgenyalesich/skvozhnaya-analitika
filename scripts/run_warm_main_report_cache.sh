#!/usr/bin/env bash
# Background warmer for main report cache.
# Rebuilds Redis cache for recently used filter profiles.
#
# ENV:
#   MAIN_REPORT_WARM_INTERVAL_MINUTES (default: 15)
#   MAIN_REPORT_WARM_MAX_PROFILES (default: 20)

LOG_DIR="$(dirname "$0")/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/run_warm_main_report_cache.log"
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
export MAIN_REPORT_WARM_INTERVAL_MINUTES="${MAIN_REPORT_WARM_INTERVAL_MINUTES:-15}"
export MAIN_REPORT_WARM_MAX_PROFILES="${MAIN_REPORT_WARM_MAX_PROFILES:-20}"

echo "Main report cache warmer started. Interval=${MAIN_REPORT_WARM_INTERVAL_MINUTES} min, max_profiles=${MAIN_REPORT_WARM_MAX_PROFILES}"

while true; do
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Warming main report cache..."
  .venv/bin/python - <<'PY'
import asyncio
import os
from app.services.main_report_cache_warmer import warm_main_report_cache

async def main():
    max_profiles = int(os.getenv("MAIN_REPORT_WARM_MAX_PROFILES", "20"))
    warmed = await warm_main_report_cache(max_profiles=max_profiles)
    print(f"warmed_profiles={warmed}")

asyncio.run(main())
PY
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Warm pass done. Sleeping..."
  sleep "$((MAIN_REPORT_WARM_INTERVAL_MINUTES * 60))"
done

