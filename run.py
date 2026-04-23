#!/usr/bin/env python3
import os
import signal
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV_BIN = ROOT / ".venv" / "bin"
BACKEND_CMD = [str(VENV_BIN / "python"), "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
FRONTEND_CMD = ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "4173"]


def load_env(env_path: Path) -> dict:
    env = {}
    if not env_path.exists():
        return env
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env.setdefault(key.strip(), value.strip())
    return env


def run():
    if not VENV_BIN.exists():
        print("ERROR: .venv not found. Run: python3 -m venv .venv && . .venv/bin/activate && pip install -r backend/requirements.txt")
        sys.exit(1)

    env = os.environ.copy()
    env.update(load_env(ROOT / ".env"))

    backend = subprocess.Popen(
        BACKEND_CMD,
        cwd=str(ROOT / "backend"),
        env=env,
    )
    frontend = subprocess.Popen(
        FRONTEND_CMD,
        cwd=str(ROOT / "frontend"),
        env=env,
    )
    def shutdown(_sig, _frame):
        for proc in (frontend, backend):
            if proc.poll() is None:
                proc.terminate()
        for proc in (frontend, backend):
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    exit_codes = []
    for proc in (backend, frontend):
        try:
            exit_codes.append(proc.wait())
        except KeyboardInterrupt:
            shutdown(None, None)
            exit_codes.append(0)

    sys.exit(max(exit_codes))


if __name__ == "__main__":
    run()
