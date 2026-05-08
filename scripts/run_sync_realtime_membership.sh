#!/usr/bin/env bash
# Realtime Telegram membership sync runner.
# Wrapper around existing realtime monitor script.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT/scripts/run_tg_realtime.sh"

