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
export RQ_QUEUE_NAME="${RQ_QUEUE_NAME:-default}"
export WORKER_HOURLY_SCHEDULER=1

# Start the periodic scheduler in a lightweight background process.
# It will enqueue ingestion/telegram/pokerhub jobs on intervals.
python -c "import app.worker.tasks; import time; time.sleep(10**9)" &

rq worker -u "$REDIS_URL" "${RQ_QUEUE_NAME:-default}"
